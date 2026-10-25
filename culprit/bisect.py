"""Step 3 - Bisect: `git bisect run` finds the first bad commit exactly. No AI involved.

Graph-guided mode limits bisect to commits that touched the files Graphify located,
so fewer test runs are needed. The answer is always double-checked (test passes at
the culprit's parent and fails at the culprit); if that check fails, Culprit falls
back to a full bisect.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .gitutil import commits_between, git, worktree
from .repro import run_at

PKG_PARENT = str(Path(__file__).resolve().parent.parent)


@dataclass
class BisectResult:
    ok: bool
    culprit: str = ""
    steps: int = 0
    guided: bool = False
    range_size: int = 0
    guided_range: int = 0
    verified: bool = False
    log: str = ""
    notes: list[str] = field(default_factory=list)


def _run_bisect(repo: Path, good: str, bad: str, step_cmd: list[str], paths: list[str] | None) -> BisectResult:
    with worktree(repo, bad) as wt:
        env = dict(os.environ)
        env["PYTHONPATH"] = PKG_PARENT + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        start = ["bisect", "start", bad, good] + (["--", *paths] if paths else [])
        try:
            git(wt, *start, env=env)
            proc = subprocess.run(["git", "bisect", "run", *step_cmd], cwd=str(wt),
                                  capture_output=True, text=True, env=env, timeout=1800)
            out = proc.stdout + proc.stderr
            steps = len(re.findall(r"^running ", out, flags=re.M))
            m = re.search(r"^([0-9a-f]{40}) is the first bad commit", out, flags=re.M)
            return BisectResult(ok=bool(m), culprit=m.group(1) if m else "", steps=steps,
                                guided=bool(paths), log=out[-4000:])
        finally:
            subprocess.run(["git", "bisect", "reset"], cwd=str(wt), capture_output=True, env=env)


def verify(repo: Path, culprit: str, test_code: str | None) -> bool:
    if test_code is None:
        return True
    parent = git(repo, "rev-parse", f"{culprit}^")
    return run_at(repo, parent, test_code).status == "pass" and run_at(repo, culprit, test_code).status == "fail"


def bisect(repo: Path, good: str, bad: str, test_code: str | None = None, paths: list[str] | None = None,
           runs: int = 3, bandit_rule: str | None = None, bandit_file: str | None = None,
           log=lambda m: None) -> BisectResult:
    tmpdir = Path(tempfile.mkdtemp(prefix="culprit-bisect-"))
    if bandit_rule:
        step = [sys.executable, "-m", "culprit.bisect_step", "--bandit-rule", bandit_rule]
        if bandit_file:
            step += ["--bandit-file", bandit_file]
        verify_code = None
    else:
        test_path = tmpdir / "test_culprit_repro.py"      # kept outside the repo: checkouts can't delete it
        test_path.write_text(test_code or "")
        step = [sys.executable, "-m", "culprit.bisect_step", "--test", str(test_path), "--runs", str(runs)]
        verify_code = test_code

    full_range = commits_between(repo, good, bad)
    attempts: list[list[str] | None] = []
    if paths:
        attempts.append(sorted(set(paths)))
    attempts.append(None)

    last = BisectResult(ok=False)
    for p in attempts:
        res = _run_bisect(repo, good, bad, step, p)
        res.range_size = full_range
        res.guided_range = commits_between(repo, good, bad, p) if p else full_range
        label = f"graph-guided over {res.guided_range} of {full_range} commits" if p else f"full range of {full_range} commits"
        if res.ok:
            res.verified = verify(repo, res.culprit, verify_code)
            log(f"  {label}: {res.steps} test runs -> {res.culprit[:8]} "
                f"({'verified' if res.verified else 'NOT verified'})")
            if res.verified:
                return res
            res.notes.append(f"{label}: result failed verification")
        else:
            log(f"  {label}: no single culprit found")
            res.notes.append(f"{label}: no single culprit")
        last = res
    last.ok = False
    return last
