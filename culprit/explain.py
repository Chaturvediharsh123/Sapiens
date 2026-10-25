"""Step 4 - Explain: what the culprit commit changed, why it broke, and its blast radius."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .codeunits import CodeUnit, unit_at_line, units_in_source
from .gitutil import CommitInfo, git, show_file
from .graph import CodeGraph
from .prompts import EXPLAIN_SYSTEM, EXPLAIN_USER


class Explanation(BaseModel):
    summary: str
    root_cause: str
    risk: Literal["low", "medium", "high"] = "medium"


@dataclass
class ChangedUnit:
    unit: CodeUnit          # the unit as it looks in the culprit commit
    diff: str               # the diff hunks touching it


@dataclass
class ExplainResult:
    explanation: Explanation
    changed: list[ChangedUnit]
    diff: str
    blast: list[tuple[str, str, int]] = field(default_factory=list)   # (qualname, file, hops)


def _is_test(path: str) -> bool:
    name = Path(path).name
    return "tests/" in path or name.startswith("test_")


def culprit_diff(repo: Path, sha: str) -> str:
    return git(repo, "diff", "--unified=2", f"{sha}^", sha, "--", "*.py")


def changed_units(repo: Path, sha: str) -> list[ChangedUnit]:
    """Map every changed line of the culprit commit to the code unit that contains it."""
    raw = git(repo, "diff", "--unified=0", f"{sha}^", sha, "--", "*.py")
    out: dict[str, ChangedUnit] = {}
    file = None
    hunk_lines: list[str] = []
    hunks: list[tuple[str, int, int, str]] = []

    def flush():
        if file and hunk_lines:
            hunks.append((file, cur_start, cur_count, "\n".join(hunk_lines)))

    cur_start = cur_count = 0
    for line in raw.splitlines():
        if line.startswith("+++ "):
            flush()
            hunk_lines = []
            file = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            flush()
            hunk_lines = [line]
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            cur_start, cur_count = int(m.group(1)), int(m.group(2) or 1)
        elif file and hunk_lines:
            hunk_lines.append(line)
    flush()

    cache: dict[str, list[CodeUnit]] = {}
    for f, start, count, text in hunks:
        if _is_test(f):
            continue
        if f not in cache:
            src = show_file(repo, sha, f)
            cache[f] = units_in_source(src, f) if src else []
        lines = range(start, start + count) if count else [max(start, 1), start + 1]
        for ln in lines:
            u = unit_at_line(cache[f], ln)
            if u:
                key = u.label()
                if key in out:
                    if text not in out[key].diff:
                        out[key].diff += "\n" + text
                else:
                    out[key] = ChangedUnit(u, text)
    # functions first, imports last: the function is usually where the behaviour broke
    return sorted(out.values(), key=lambda c: (c.unit.kind != "function", ":import" in c.unit.qualname))


def blast_radius(graph: CodeGraph, changed: list[ChangedUnit]) -> list[tuple[str, str, int]]:
    seen: dict[str, tuple[str, str, int]] = {}
    for c in changed:
        node = graph.node_at(c.unit.file, (c.unit.start, c.unit.end))
        if not node:
            continue
        for n, hops in graph.blast_radius(node.id, depth=2):
            key = f"{n.file}::{n.qual}"
            if key not in seen or seen[key][2] > hops:
                seen[key] = (n.qual, n.file, hops)
    return sorted(seen.values(), key=lambda t: (t[2], t[1], t[0]))


def explain(repo: Path, info: CommitInfo, report: str, graph: CodeGraph, llm) -> ExplainResult:
    diff = culprit_diff(repo, info.sha)
    changed = changed_units(repo, info.sha)
    blast = blast_radius(graph, changed)
    blast_txt = "\n".join(f"- {q} ({f}){' [test]' if _is_test(f) else ''}, {h} hop(s) away"
                          for q, f, h in blast[:12]) or "- nothing else calls it"
    try:
        exp = llm.json(EXPLAIN_SYSTEM,
                       EXPLAIN_USER.format(report=report, sha=info.short, author=info.author,
                                           message=info.message, diff=diff[:2500], blast=blast_txt),
                       Explanation, purpose="explain")
    except Exception as exc:     # explanation is helpful, not essential: never lose the culprit over it
        exp = Explanation(summary=f'Commit "{info.message}" changed '
                                  f'{", ".join(c.unit.qualname for c in changed) or "code"}.',
                          root_cause=f"(model explanation unavailable: {exc})", risk="medium")
    return ExplainResult(exp, changed, diff, blast)
