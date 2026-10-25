"""The whole Culprit run: locate -> reproduce -> bisect -> explain -> fix -> report."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import report as report_writer
from . import security
from .bisect import bisect
from .codeunits import find_unit, units_in_source
from .explain import explain
from .fix import make_fix
from .gitutil import GitError, commit_info, git, rev_parse, tracked_changes
from .graph import load_graph
from .locate import locate
from .repro import reproduce
from .ui import UI


@dataclass
class RunResult:
    report: str
    repo: str
    model: str
    mode: str
    status: str = "started"
    bad: str = ""
    good: str = ""
    good_auto: bool = False
    graph_source: str = ""
    keywords: list[str] = field(default_factory=list)
    located: list[str] = field(default_factory=list)
    security_findings: list[str] = field(default_factory=list)
    test_code: str = ""
    bad_reason: str = ""
    repro_attempts: int = 0
    culprit: dict = field(default_factory=dict)
    bisect_steps: int = 0
    bisect_guided: bool = False
    bisect_range: int = 0
    bisect_guided_range: int = 0
    bisect_verified: bool = False
    bisect_method: str = "pytest"
    explanation: dict = field(default_factory=dict)
    blast: list = field(default_factory=list)
    diff: str = ""
    fix: dict = field(default_factory=dict)
    seconds: float = 0.0
    llm_calls: int = 0
    llm_retries: int = 0
    tokens_per_sec: float = 0.0
    error: str = ""
    report_path: str = ""


def _finish(res: RunResult, llm, t0: float, status: str) -> RunResult:
    res.status = status
    res.seconds = time.time() - t0
    stats = getattr(llm, "stats", None)
    if stats:
        res.llm_calls, res.llm_retries, res.tokens_per_sec = stats.calls, stats.retries, stats.tokens_per_sec
    return res


def run(repo: Path, report: str, llm, good: str | None = None, bad: str = "HEAD", security_mode: bool = False,
        do_fix: bool = True, runs: int = 3, guided: bool = True, use_graphify: bool = True,
        out_dir: Path | None = None, ui: UI | None = None) -> RunResult:
    ui = ui or UI()
    t0 = time.time()
    repo = repo.resolve()
    res = RunResult(report=report, repo=str(repo), model=getattr(llm, "model", "?"),
                    mode="security" if security_mode else "normal")
    try:
        git(repo, "rev-parse", "--git-dir")
        bad_sha = rev_parse(repo, bad)
        good_sha = rev_parse(repo, good) if good else None
    except GitError as exc:
        res.error = str(exc)
        ui.fail(res.error)
        return _finish(res, llm, t0, "error")
    if tracked_changes(repo):
        ui.warn("You have uncommitted changes. Culprit only reads commits, so they are ignored.")
    res.bad = bad_sha

    # 1 ---------------------------------------------------------------- locate
    ui.step(1, "Locate the code")
    with ui.working("building code map"):
        graph = load_graph(repo, use_graphify=use_graphify, log=ui.info)
    res.graph_source = graph.source
    ui.info(f"code map: {len(graph.code_nodes())} functions from "
            f"{'Graphify graph.json' if graph.source == 'graphify' else 'built-in AST graph'}")
    findings: list[security.Finding] = []
    if security_mode:
        with ui.working("running Bandit security scan"):
            findings = security.scan(repo)
        res.security_findings = [f.short() for f in findings]
        for f in findings:
            ui.warn(f"Bandit: {f.short()}")
    with ui.working("asking the model for search keywords"):
        units, keywords = locate(repo, report, graph, llm, findings)
    res.keywords = keywords
    res.located = [u.label() for u in units]
    if not units:
        ui.case_open("No code related to this bug report was found.",
                     ["name the feature or function in the report (e.g. coupon, login, checkout)",
                      "check you are inside the right project folder"])
        return _finish(res, llm, t0, "not_located")
    ui.ok("most relevant: " + ", ".join(res.located))

    # 2 ---------------------------------------------------------------- reproduce
    ui.step(2, "Reproduce the bug")
    with ui.working("model is writing a test; pytest is checking it"):
        rep = reproduce(repo, bad_sha, good_sha, report, units, llm, log=ui.info)
    res.repro_attempts = rep.attempts
    bandit_rule = bandit_file = None
    if rep.ok:
        res.test_code, res.good, res.good_auto = rep.test_code, rep.good, rep.good_auto
        res.bad_reason = rep.bad_result.reason if rep.bad_result else ""
        ui.ok(f"test fails on the buggy code ({res.bad_reason})")
        ui.ok(f"test passes at {'auto-found ' if rep.good_auto else ''}good commit {rep.good[:8]}")
        ui.code(rep.test_code, "reproduction test")
    else:
        located_files = {u.file for u in units}
        sec = [f for f in findings if f.file in located_files]
        if security_mode and sec:
            bandit_rule, bandit_file = sec[0].rule, sec[0].file
            res.good = good_sha or git(repo, "rev-list", "--max-parents=0", bad_sha).splitlines()[0]
            res.bisect_method = f"bandit {bandit_rule}"
            ui.warn(f"no valid test after {rep.attempts} attempts; falling back to bisecting on "
                    f"Bandit rule {bandit_rule} in {bandit_file}")
        else:
            for n in rep.notes:
                ui.info(n)
            ui.case_open(f"Could not write a test that proves this bug ({rep.attempts} attempts). Culprit only "
                         "reports what it can prove, so it stopped here.",
                         ["give an input and the expected result, e.g. \"save10 should give 10% off\"",
                          "pass --good <commit> if you know where it still worked",
                          "try a bigger model with --model"])
            return _finish(res, llm, t0, "not_reproduced")

    # 3 ---------------------------------------------------------------- bisect
    ui.step(3, "Bisect the history")
    paths = sorted({u.file for u in units}) if guided else None
    with ui.working("git bisect is testing commits"):
        bis = bisect(repo, res.good, bad_sha, test_code=res.test_code or None, paths=paths, runs=runs,
                     bandit_rule=bandit_rule, bandit_file=bandit_file, log=ui.info)
    res.bisect_steps, res.bisect_guided = bis.steps, bis.guided
    res.bisect_range, res.bisect_guided_range, res.bisect_verified = bis.range_size, bis.guided_range, bis.verified
    if not bis.ok:
        res.error = "; ".join(bis.notes)
        ui.case_open("git bisect could not pin down a single commit.",
                     ["the bug may be older than the good commit: pass an older --good",
                      "the bug may come from several commits together"])
        return _finish(res, llm, t0, "not_bisected")
    info = commit_info(repo, bis.culprit)
    res.culprit = {"sha": info.sha, "author": info.author, "date": info.date, "message": info.message}
    ui.culprit(info.sha, info.author, info.date, info.message, res.bisect_steps,
               f"graph-guided over {res.bisect_guided_range} of {res.bisect_range} commits" if res.bisect_guided
               else f"{res.bisect_range} commits searched")

    # 4 ---------------------------------------------------------------- explain
    ui.step(4, "Explain the culprit commit")
    with ui.working("model is reading the diff and the blast radius"):
        exp = explain(repo, info, report, graph, llm)
    res.explanation = exp.explanation.model_dump()
    res.blast = exp.blast
    res.diff = exp.diff
    ui.ok(exp.explanation.summary)
    ui.ok(f"root cause: {exp.explanation.root_cause}")
    if exp.blast:
        ui.info("blast radius: " + ", ".join(f"{q} ({h})" for q, _, h in exp.blast[:8]))

    # security rule for fix verification: a finding inside the changed code at the bad commit
    if security_mode and not bandit_rule:
        for c in exp.changed:
            src = git(repo, "show", f"{bad_sha}:{c.unit.file}", check=False)
            u = find_unit(units_in_source(src, c.unit.file), c.unit.qualname) if src else None
            for f in findings:
                if u and f.file == u.file and u.start <= f.line <= u.end:
                    bandit_rule = f.rule
                    break
            if bandit_rule:
                break

    # 5 ---------------------------------------------------------------- fix
    if do_fix and res.test_code:
        ui.step(5, "Fix it and prove it")
        with ui.working("model is writing a fix; tests are checking it"):
            fx = make_fix(repo, bad_sha, info, report, exp, res.test_code, llm, bandit_rule=bandit_rule,
                          log=ui.info)
        res.fix = {"ok": fx.ok, "branch": fx.branch, "target": fx.target, "attempts": fx.attempts,
                   "patch": fx.patch, "regression_test": fx.regression_test,
                   "security_cleared": fx.security_cleared, "notes": fx.notes}
        if fx.ok:
            ui.ok(f"verified fix on branch [bold]{fx.branch}[/bold] (not merged)")
            ui.ok(f"regression test saved as {fx.regression_test}")
        else:
            ui.warn("no verified fix; the culprit and explanation above still stand")

    _finish(res, llm, t0, "found" if not res.fix or res.fix.get("ok") else "found_no_fix")
    out = out_dir or (Path.cwd() / "culprit-out" / info.short)
    report_path = report_writer.write(out, res)
    res.report_path = str(report_path)
    report_writer.write(out, res)   # rewrite so result.json includes report_path
    fixed = res.fix.get("ok")
    rows = [("culprit", f"[bold #ff4f61]{info.short}[/]  \"{info.message}\"  ({info.author}, {info.date})"),
            ("why", exp.explanation.root_cause),
            ("fix", f"[#3fb950]verified[/] on branch [bold]{res.fix['branch']}[/] + regression test" if fixed
             else ("skipped (--no-fix)" if not do_fix else "not produced; the culprit above still stands")),
            ("speed", f"{res.seconds:.0f}s · {res.tokens_per_sec:.1f} tokens/sec · {res.llm_calls} model calls"),
            ("report", str(report_path))]
    nxt = [("see the fix", f"git diff HEAD {res.fix['branch']}"),
           ("keep it", f"git merge {res.fix['branch']}"),
           ("share it", f"git push origin {res.fix['branch']}")] if fixed else []
    nxt.append(("read the evidence", f"open {report_path}"))
    ui.case_closed(rows, nxt)
    return res
