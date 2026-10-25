"""Step 5 - Fix: rewrite the broken unit, then prove the fix with real test runs.

A fix is accepted only if:
  1. the reproduction test now passes,
  2. the project's own test suite has no new failures,
  3. (security mode) the Bandit finding in that file is gone.
The accepted fix is committed on a new branch `culprit/fix-<sha>` together with the
reproduction test saved as a permanent regression test. Nothing is merged.
"""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .codeunits import CodeUnit, extract_replacement, find_unit, replace_unit, units_in_source
from .explain import ExplainResult
from .gitutil import CommitInfo, git, worktree
from .prompts import FIX_SYSTEM, FIX_USER
from .sandbox import run_suite, run_test
from .security import scan


@dataclass
class FixResult:
    ok: bool
    branch: str = ""
    target: str = ""
    attempts: int = 0
    patch: str = ""
    regression_test: str = ""
    suite_failures: list[str] = field(default_factory=list)
    security_cleared: bool | None = None
    notes: list[str] = field(default_factory=list)


def _branch_exists(repo: Path, name: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                          cwd=str(repo), capture_output=True).returncode == 0


def _pick_target(repo: Path, bad: str, exp: ExplainResult) -> tuple[CodeUnit, str] | None:
    """The changed unit to rewrite, as it looks at the bad commit (HEAD)."""
    for c in exp.changed:
        if ":import:" in c.unit.qualname:
            continue
        src = git(repo, "show", f"{bad}:{c.unit.file}")
        unit = find_unit(units_in_source(src, c.unit.file), c.unit.qualname)
        if unit:
            return unit, c.diff
    return None


def make_fix(repo: Path, bad: str, info: CommitInfo, report: str, exp: ExplainResult, test_code: str,
             llm, bandit_rule: str | None = None, max_attempts: int = 3, log=lambda m: None) -> FixResult:
    picked = _pick_target(repo, bad, exp)
    if not picked:
        return FixResult(False, notes=["could not find the changed code at the bad commit"])
    unit, unit_diff = picked
    result = FixResult(False, target=unit.label())

    branch = f"culprit/fix-{info.short}"

    with worktree(repo, bad) as base:
        baseline, _ = run_suite(base)
        before_findings = ({f.line for f in scan(base, [bandit_rule]) if f.file == unit.file}
                           if bandit_rule else set())

    extra = ""
    if bandit_rule:
        extra = (f"\nSecurity scanner finding to remove: {bandit_rule} in {unit.file}. "
                 "Use a safe pattern (parameterized SQL query, or read secrets from os.environ).\n")
    user = FIX_USER.format(report=report, sha=info.short, message=info.message, diff=unit_diff[:2000],
                           root_cause=exp.explanation.root_cause, qualname=unit.qualname.replace("<module>:", ""),
                           file=unit.file, code=unit.source, extra=extra, kind=unit.kind)
    history: list[dict] = []
    feedback = None
    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        if _branch_exists(repo, branch):
            git(repo, "branch", "-D", branch)
        prompt = user if feedback is None else feedback
        answer = llm.code(FIX_SYSTEM, prompt, purpose="fix", history=history)
        history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": f"```python\n{answer}```"}]
        replacement = extract_replacement(answer, unit)
        if replacement is None:
            feedback = (f"I could not find a complete `{unit.name}` {unit.kind} in your answer, or it was not "
                        "valid Python. Return the whole fixed unit in one ```python block.")
            result.notes.append(f"attempt {attempt}: unusable answer")
            continue

        with worktree(repo, bad, branch=branch) as wt:
            path = wt / unit.file
            new_src = replace_unit(path.read_text(), unit, replacement)
            try:
                ast.parse(new_src)
            except SyntaxError as exc:
                feedback = f"Your fix makes the file invalid Python: {exc}. Try again."
                result.notes.append(f"attempt {attempt}: syntax error")
                continue
            path.write_text(new_src)

            repro = run_test(wt, test_code)
            failing, suite_out = run_suite(wt)
            new_failures = sorted(failing - baseline)
            sec_ok = None
            if bandit_rule:
                after = {f.line for f in scan(wt, [bandit_rule]) if f.file == unit.file}
                sec_ok = not after or len(after) < len(before_findings)
            log(f"  attempt {attempt}: repro test {repro.status}, new suite failures {len(new_failures)}"
                + (f", {bandit_rule} {'cleared' if sec_ok else 'still present'}" if bandit_rule else ""))

            if repro.status == "pass" and not new_failures and sec_ok is not False:
                reg_name = f"tests/test_culprit_regression_{info.short}.py"
                reg_path = wt / reg_name
                reg_path.parent.mkdir(parents=True, exist_ok=True)
                reg_path.write_text(f"# Regression test added by Culprit for: {report}\n"
                                    f"# Bug introduced in {info.short} ({info.message})\n" + test_code)
                git(wt, "add", unit.file, reg_name)
                msg = (f"Fix regression from {info.short}: {info.message}\n\n{report}\n\n"
                       f"Root cause: {exp.explanation.root_cause}\n\nFound and verified by Culprit.")
                git(wt, "-c", "user.name=Culprit", "-c", "user.email=culprit@localhost",
                    "commit", "-q", "-m", msg)
                result.ok = True
                result.branch = branch
                result.regression_test = reg_name
                result.security_cleared = sec_ok
                result.patch = git(repo, "diff", bad, branch)
                return result

            problems = []
            if repro.status != "pass":
                problems.append(f"the reproduction test still {repro.status}s:\n{repro.output[-1200:]}")
            if new_failures:
                problems.append(f"these existing tests now fail: {', '.join(new_failures)}\n{suite_out[-800:]}")
            if sec_ok is False:
                problems.append(f"the security scanner still reports {bandit_rule}")
            feedback = "Your fix did not work: " + "\n".join(problems) + \
                       f"\nReturn the corrected `{unit.name}` again in one ```python block."
            result.notes.append(f"attempt {attempt}: " + "; ".join(p.split(':')[0] for p in problems))
    if _branch_exists(repo, branch):
        git(repo, "branch", "-D", branch, check=False)
    return result
