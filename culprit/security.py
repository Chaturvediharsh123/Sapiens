"""Bandit integration (a Python security scanner, no AI) for security mode."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDES = "./.git,./graphify-out,./culprit-out,./venv,./.venv,./tests,./test"


@dataclass
class Finding:
    rule: str          # e.g. B608
    name: str          # e.g. hardcoded_sql_expressions
    file: str          # repo-relative
    line: int
    severity: str
    text: str

    def short(self) -> str:
        return f"{self.rule} {self.name} at {self.file}:{self.line} ({self.severity}): {self.text}"


def bandit_available() -> bool:
    proc = subprocess.run([sys.executable, "-m", "bandit", "--version"], capture_output=True)
    return proc.returncode == 0


def scan(root: Path, rules: list[str] | None = None) -> list[Finding]:
    args = [sys.executable, "-m", "bandit", "-q", "-f", "json", "-r", ".", "-x", EXCLUDES]
    if rules:
        args += ["-t", ",".join(rules)]
    proc = subprocess.run(args, cwd=str(root), capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return []
    out = []
    for r in data.get("results", []):
        file = r["filename"].replace("\\", "/").removeprefix("./")
        out.append(Finding(r["test_id"], r["test_name"], file, r["line_number"],
                           r["issue_severity"], r["issue_text"]))
    return out


def has_finding(root: Path, rule: str, file: str | None = None) -> bool:
    return any(f.file == file or file is None for f in scan(root, [rule]))
