"""Step 1 - Locate: turn a bug report into the 3-5 code units most likely involved."""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .codeunits import CodeUnit, unit_at_line, units_in_source
from .graph import CodeGraph
from .prompts import KEYWORDS_SYSTEM
from .security import Finding

STOPWORDS = set("""a an the and or but is are was were be been it its this that these those with without
for from into onto of on in at to by as when while after before should would could can cannot does do
did not no yes than then there their them they we you he she our your my me i us via per like e.g eg
example stops working broken bug wrong error fails failing failed instead being some many small""".split())


class Keywords(BaseModel):
    keywords: list[str] = Field(default_factory=list)


def heuristic_keywords(report: str) -> list[str]:
    words = re.findall(r"[a-zA-Z_][a-zA-Z_]+", report.lower())
    seen, out = set(), []
    for w in words:
        if len(w) >= 3 and w not in STOPWORDS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _name_tokens(name: str) -> list[str]:
    parts = re.split(r"[_\W]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", name))
    return [p.lower() for p in parts if p]


def _match(kw: str, token: str) -> float:
    if kw == token:
        return 3.0
    if len(kw) >= 4 and len(token) >= 4 and (kw.startswith(token[:5]) or token.startswith(kw[:5])):
        return 2.0
    return 0.0


def score_nodes(graph: CodeGraph, keywords: list[str], llm_keywords: set[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for n in graph.code_nodes():
        tokens = _name_tokens(n.qual) + _name_tokens(Path(n.file).stem)
        doc = n.doc.lower()
        s = 0.0
        for kw in keywords:
            weight = 1.5 if kw in llm_keywords else 1.0
            best = max((_match(kw, t) for t in tokens), default=0.0)
            if not best and kw in doc:
                best = 1.0
            s += best * weight
        if s:
            scores[n.id] = s
    # one hop along the call graph: neighbours of strong candidates get some credit
    top = sorted(scores, key=scores.get, reverse=True)[:3]
    for nid in top:
        for nb in graph.neighbours(nid):
            if nb in graph.nodes and not graph.nodes[nb].is_test:
                scores[nb] = scores.get(nb, 0.0) + 0.4 * scores[nid]
    return scores


def locate(repo: Path, report: str, graph: CodeGraph, llm, findings: list[Finding] | None = None,
           top_n: int = 4) -> tuple[list[CodeUnit], list[str]]:
    llm_kw: list[str] = []
    try:
        llm_kw = [k.lower().strip() for k in
                  llm.json(KEYWORDS_SYSTEM, f"Bug report: {report}", Keywords, purpose="keywords").keywords
                  if k.strip()]
    except Exception:            # keywords are a hint; the heuristic still works without them
        llm_kw = []
    keywords = list(dict.fromkeys(llm_kw + heuristic_keywords(report)))
    scores = score_nodes(graph, keywords, set(llm_kw))

    file_cache: dict[str, list[CodeUnit]] = {}

    def units_for(file: str) -> list[CodeUnit]:
        if file not in file_cache:
            path = repo / file
            file_cache[file] = units_in_source(path.read_text(errors="replace"), file) if path.exists() else []
        return file_cache[file]

    picked: dict[str, CodeUnit] = {}
    for nid in sorted(scores, key=scores.get, reverse=True):
        node = graph.nodes[nid]
        unit = unit_at_line(units_for(node.file), node.line + 1) or unit_at_line(units_for(node.file), node.line)
        if unit and unit.label() not in picked:
            unit.score = scores[nid]
            picked[unit.label()] = unit
        if len(picked) >= top_n:
            break

    # security mode: Bandit findings point straight at code, including module-level statements
    for f in findings or []:
        unit = unit_at_line(units_for(f.file), f.line)
        if unit is None:
            continue
        relevant = any(k in unit.source.lower() for k in keywords)
        if relevant and unit.label() not in picked:
            unit.score = 10.0
            picked[unit.label()] = unit
        elif unit.label() in picked:
            picked[unit.label()].score += 5.0

    units = sorted(picked.values(), key=lambda u: u.score, reverse=True)[:top_n + 1]
    return units, keywords
