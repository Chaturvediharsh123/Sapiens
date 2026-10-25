"""The command `git bisect run` calls at every step.

Exit codes follow git's contract: 0 = good, 1 = bad, 125 = skip this commit.
Flaky-test guard: the test runs N times; if results disagree, the commit is skipped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .sandbox import run_test_n
from .security import scan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", help="path to the reproduction test file")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--bandit-rule")
    ap.add_argument("--bandit-file")
    args = ap.parse_args()
    cwd = Path.cwd()

    if args.bandit_rule:
        hits = [f for f in scan(cwd, [args.bandit_rule]) if not args.bandit_file or f.file == args.bandit_file]
        return 1 if hits else 0

    verdict, _ = run_test_n(cwd, Path(args.test).read_text(), args.runs)
    return {"pass": 0, "fail": 1}.get(verdict, 125)


if __name__ == "__main__":
    sys.exit(main())
