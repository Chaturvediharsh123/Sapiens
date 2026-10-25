"""Step 2 - Reproduce: the model writes a test; real runs decide whether it is valid.

A test is accepted only if it FAILS at the bad commit and PASSES at a good commit.
That check is what makes the later bisect trustworthy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .codeunits import CodeUnit
from .gitutil import commit_count, git, short, worktree
from .prompts import REPRO_SYSTEM, REPRO_USER
from .sandbox import TestResult, run_test


@dataclass
class ReproResult:
    ok: bool
    test_code: str = ""
    good: str = ""
    good_auto: bool = False
    attempts: int = 0
    bad_result: TestResult | None = None
    notes: list[str] = field(default_factory=list)


def run_at(repo: Path, rev: str, test_code: str) -> TestResult:
    with worktree(repo, rev) as wt:
        return run_test(wt, test_code)


def find_good(repo: Path, bad: str, test_code: str, log=lambda m: None) -> str | None:
    """Walk back 1, 2, 4, 8, ... commits until the test passes (auto-find good commit)."""
    total = commit_count(repo, bad)
    offsets, k = [], 1
    while k < total:
        offsets.append(k)
        k *= 2
    if total > 1 and (total - 1) not in offsets:
        offsets.append(total - 1)             # the very first commit
    def status(k: int) -> tuple[str, str]:
        rev = git(repo, "rev-parse", f"{bad}~{k}")
        res = run_at(repo, rev, test_code)
        log(f"  {bad[:8]}~{k} ({short(rev)}): {res.status}")
        return res.status, rev

    last_fail = 0
    for k in offsets:
        st, rev = status(k)
        if st == "pass":
            return rev
        if st == "fail":
            last_fail = k
            continue
        # "error": this old commit can't even run the test (e.g. the feature didn't exist yet).
        # The last working version, if any, lies between the last failing and this commit.
        lo, hi = last_fail, k
        while hi - lo > 1:
            mid = (lo + hi) // 2
            st, rev = status(mid)
            if st == "pass":
                return rev
            if st == "fail":
                lo = mid
            else:
                hi = mid
        return None
    return None


def _example_test(repo: Path) -> str:
    for pattern in ("tests/test_*.py", "test/test_*.py", "test_*.py"):
        for p in sorted(repo.glob(pattern)):
            text = p.read_text(errors="replace")
            lines = text.splitlines()[:14]
            return f"\nExample of an existing test in this project ({p.relative_to(repo).as_posix()}):\n" \
                   "```python\n" + "\n".join(lines) + "\n```\n"
    return ""


def reproduce(repo: Path, bad: str, good: str | None, report: str, units: list[CodeUnit], llm,
              max_attempts: int = 3, log=lambda m: None) -> ReproResult:
    code = "\n\n".join(f"# {u.file}\n{u.source}" for u in units)
    imports = "\n".join(dict.fromkeys(u.import_hint() for u in units))
    user = REPRO_USER.format(report=report, code=code, imports=imports, example=_example_test(repo))
    history: list[dict] = []
    result = ReproResult(ok=False)
    feedback = None
    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        prompt = user if feedback is None else feedback
        test_code = llm.code(REPRO_SYSTEM, prompt, purpose="repro", history=history)
        history += [{"role": "user", "content": prompt},
                    {"role": "assistant", "content": f"```python\n{test_code}```"}]
        bad_res = run_at(repo, bad, test_code)
        log(f"  attempt {attempt}: at bad commit -> {bad_res.short()}")
        if bad_res.status != "fail":
            why = ("it PASSED, so it does not catch the bug" if bad_res.status == "pass"
                   else f"it could not run properly: {bad_res.reason}")
            feedback = (f"On the current buggy code your test did not fail correctly: {why}.\n"
                        f"pytest output:\n{bad_res.output[-1500:]}\n"
                        "Fix the test. It must fail because of the bug. Reply with one ```python block.")
            result.notes.append(f"attempt {attempt}: {why}")
            continue
        result.bad_result = bad_res
        if good:
            good_res = run_at(repo, good, test_code)
            log(f"  attempt {attempt}: at good commit {short(good)} -> {good_res.short()}")
            if good_res.status == "pass":
                result.ok, result.test_code, result.good = True, test_code, good
                return result
            feedback = (f"Your test also fails on an older commit where the feature worked "
                        f"({good_res.reason}), so it is testing something else.\n"
                        f"pytest output:\n{good_res.output[-1200:]}\n"
                        "Make the test check only the behaviour in the bug report. Reply with one ```python block.")
            result.notes.append(f"attempt {attempt}: also fails at good commit")
            continue
        log("  no good commit given: searching history for the last version where the test passes")
        found = find_good(repo, bad, test_code, log=log)
        if found:
            result.ok, result.test_code, result.good, result.good_auto = True, test_code, found, True
            return result
        feedback = ("Your test fails on every older commit too, so it does not isolate this bug. "
                    "Make it check only the behaviour in the bug report. Reply with one ```python block.")
        result.notes.append(f"attempt {attempt}: never passes in history")
    return result
