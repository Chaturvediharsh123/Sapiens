"""Build the Culprit demo repo: a tiny Python shop app with 30 commits and 7 planted bugs.

Usage:
    python demo/make_demo_repo.py [TARGET_DIR]        # default: ./demo-shop

Same as `culprit demo --build`. Also writes bench/bugs.yaml with each bug's culprit sha.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from culprit.demo import build, write_bugs_yaml  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-shop").resolve()
    info = build(target)
    write_bugs_yaml(info, ROOT / "bench" / "bugs.yaml")
    print(f"Built {target} with {len(info['shas'])} commits and {len(info['culprits'])} planted bugs.")
    print(f"Wrote {ROOT / 'bench' / 'bugs.yaml'}")


if __name__ == "__main__":
    main()
