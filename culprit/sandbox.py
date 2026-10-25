"""Run the reproduction test inside a checkout and classify the result.

pass  -> the test passed (behaviour is correct at this commit)
fail  -> the test failed for a real reason (an assertion or the reported exception)
error -> the test could not run properly (import error, syntax error, typo in the test)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

TEST_FILE = "test_culprit_repro.py"

# Failures with these exception types mean the *test* is broken, not the code under test.
TEST_BUG_TYPES = {
    "NameError", "ImportError", "ModuleNotFoundError", "SyntaxError",
    "IndentationError", "TabError",
}


@dataclass
class TestResult:
    __test__ = False     # not a pytest test class
    status: str         # "pass" | "fail" | "error"
    reason: str          # first line of the failure, e.g. "AssertionError: assert 0 == 10"
    output: str          # trimmed pytest output, used as feedback for the model

    def short(self) -> str:
        return f"{self.status} ({self.reason})" if self.reason else self.status


def _env(workdir: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(workdir) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_test(workdir: Path, test_code: str, timeout: int = 60) -> TestResult:
    """Write the test into `workdir`, run it once with pytest, classify the outcome."""
    test_path = workdir / TEST_FILE
    test_path.write_text(test_code)
    report = Path(tempfile.mkstemp(prefix="culprit-junit-", suffix=".xml")[1])
    try:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "--tb=short", f"--junitxml={report}", TEST_FILE],
                cwd=str(workdir), capture_output=True, text=True, timeout=timeout,
                env=_env(workdir),
            )
        except subprocess.TimeoutExpired:
            return TestResult("error", "timeout", f"test timed out after {timeout}s")
        output = (proc.stdout + proc.stderr)[-3000:]
        return _classify(proc.returncode, report, output)
    finally:
        test_path.unlink(missing_ok=True)
        report.unlink(missing_ok=True)


def _classify(returncode: int, report: Path, output: str) -> TestResult:
    if returncode == 0:
        return TestResult("pass", "", output)
    if returncode == 5:
        return TestResult("error", "no test function found", output)
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, FileNotFoundError):
        return TestResult("error", f"pytest exit code {returncode}", output)
    for case in root.iter("testcase"):
        err = case.find("error")
        if err is not None:
            return TestResult("error", (err.get("message") or "error").splitlines()[0], output)
        fail = case.find("failure")
        if fail is not None:
            msg = (fail.get("message") or "failure").splitlines()[0]
            exc_type = msg.split(":", 1)[0].strip()
            if exc_type in TEST_BUG_TYPES:
                return TestResult("error", msg, output)
            return TestResult("fail", msg, output)
    return TestResult("error", f"pytest exit code {returncode}", output)


def run_test_n(workdir: Path, test_code: str, runs: int) -> tuple[str, list[TestResult]]:
    """Run the test `runs` times (flaky-test guard). Returns 'pass', 'fail' or 'flaky/error'."""
    results = [run_test(workdir, test_code) for _ in range(max(1, runs))]
    statuses = {r.status for r in results}
    if statuses == {"pass"}:
        return "pass", results
    if statuses == {"fail"}:
        return "fail", results
    return ("flaky" if len(statuses) > 1 else "error"), results


def run_suite(workdir: Path, timeout: int = 300) -> tuple[set[str], str]:
    """Run the project's own tests. Returns the set of failing test ids and the output."""
    report = Path(tempfile.mkstemp(prefix="culprit-suite-", suffix=".xml")[1])
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line",
             f"--junitxml={report}", "--ignore=graphify-out", "--ignore=culprit-out"],
            cwd=str(workdir), capture_output=True, text=True, timeout=timeout,
            env=_env(workdir),
        )
        failing: set[str] = set()
        try:
            for case in ET.parse(report).getroot().iter("testcase"):
                if case.find("failure") is not None or case.find("error") is not None:
                    failing.add(f"{case.get('classname')}::{case.get('name')}")
        except (ET.ParseError, FileNotFoundError):
            if proc.returncode not in (0, 5):
                failing.add("<suite could not run>")
        return failing, (proc.stdout + proc.stderr)[-2000:]
    finally:
        report.unlink(missing_ok=True)
