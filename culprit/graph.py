"""Code map for locating the bug and computing the blast radius.

Primary source: Graphify's graph.json (built locally with tree-sitter, no LLM, via
`graphify . --code-only`). If Graphify is not installed, Culprit builds an equivalent
call graph itself with Python's `ast` module, so the tool always works.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "graphify-out", "culprit-out", "venv", ".venv", "node_modules",
             "__pycache__", ".pytest_cache", "build", "dist"}


@dataclass
class Node:
    id: str
    name: str          # bare name, e.g. validate_email or total
    qual: str          # Cart.total / validate_email
    file: str
    line: int
    doc: str = ""
    is_test: bool = False


@dataclass
class CodeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    calls: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))      # caller -> callees
    callers: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))    # callee -> callers
    source: str = "ast"

    def add_call(self, a: str, b: str) -> None:
        if a in self.nodes and b in self.nodes and a != b:
            self.calls[a].add(b)
            self.callers[b].add(a)

    def code_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if not n.is_test]

    def node_at(self, file: str, line_range: tuple[int, int]) -> Node | None:
        lo, hi = line_range
        hits = [n for n in self.nodes.values() if n.file == file and lo <= n.line <= hi]
        return min(hits, key=lambda n: n.line) if hits else None

    def neighbours(self, node_id: str) -> set[str]:
        return set(self.calls.get(node_id, ())) | set(self.callers.get(node_id, ()))

    def blast_radius(self, node_id: str, depth: int = 2) -> list[tuple[Node, int]]:
        """Everything that (transitively) calls node_id, up to `depth` hops."""
        seen = {node_id: 0}
        frontier = [node_id]
        for d in range(1, depth + 1):
            nxt = []
            for nid in frontier:
                for c in self.callers.get(nid, ()):
                    if c not in seen:
                        seen[c] = d
                        nxt.append(c)
            frontier = nxt
        return [(self.nodes[n], d) for n, d in seen.items() if n != node_id]


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    return "tests/" in path.replace("\\", "/") or name.startswith("test_") or name.endswith("_test.py")


# ---------------------------------------------------------------- Graphify backend

def graphify_cmd() -> str | None:
    """Find Graphify on PATH, or next to this Python (e.g. `pipx inject culprit graphifyy`)."""
    found = shutil.which("graphify")
    if found:
        return found
    for name in ("graphify", "graphify.exe"):
        candidate = Path(sys.executable).parent / name
        if candidate.exists():
            return str(candidate)
    return None


def graphify_available() -> bool:
    return graphify_cmd() is not None


def build_graphify(repo: Path, log=print) -> Path | None:
    """Run Graphify in code-only mode (local AST, no API key) and return graph.json."""
    cmd = graphify_cmd()
    if not cmd:
        return None
    proc = subprocess.run([cmd, ".", "--code-only"], cwd=str(repo),
                          capture_output=True, text=True, timeout=600)
    path = repo / "graphify-out" / "graph.json"
    if proc.returncode != 0 or not path.exists():
        log(f"Graphify failed, using built-in AST graph: {proc.stderr.strip()[:200]}")
        return None
    return path


def load_graphify(path: Path) -> CodeGraph:
    data = json.loads(path.read_text())
    g = CodeGraph(source="graphify")
    raw = {n["id"]: n for n in data.get("nodes", [])}
    for nid, n in raw.items():
        if not n.get("_callable") or n.get("_callable_class") or not n.get("source_file"):
            continue
        label = n.get("label", "")
        name = label.strip().lstrip(".").removesuffix("()")
        loc = re.match(r"L(\d+)", n.get("source_location") or "")
        file = n["source_file"].replace("\\", "/")
        g.nodes[nid] = Node(nid, name, name, file, int(loc.group(1)) if loc else 0,
                            is_test=_is_test_file(file))
    # class prefix for methods: "method" edges go class -> method
    for link in data.get("links", []):
        rel = link.get("relation")
        s, t = link.get("source"), link.get("target")
        if rel == "method" and s in raw and t in g.nodes:
            g.nodes[t].qual = f"{raw[s].get('label', '')}.{g.nodes[t].name}"
        elif rel == "calls":
            g.add_call(s, t)
        elif rel == "rationale_for":
            # docstring node -> function node (either direction, be tolerant)
            doc, fn = (s, t) if t in g.nodes else (t, s)
            if fn in g.nodes and doc in raw:
                g.nodes[fn].doc = raw[doc].get("label", "")
    return g


# ---------------------------------------------------------------- built-in AST backend

def build_ast_graph(repo: Path) -> CodeGraph:
    g = CodeGraph(source="ast")
    by_name: dict[str, list[str]] = defaultdict(list)
    bodies: dict[str, ast.AST] = {}
    for py in sorted(repo.rglob("*.py")):
        rel = py.relative_to(repo).as_posix()
        if set(Path(rel).parts) & SKIP_DIRS:
            continue
        try:
            tree = ast.parse(py.read_text(errors="replace"))
        except SyntaxError:
            continue

        def add(fn, qual):
            nid = f"{rel}::{qual}"
            g.nodes[nid] = Node(nid, fn.name, qual, rel, fn.lineno,
                                doc=(ast.get_docstring(fn) or "").splitlines()[0] if ast.get_docstring(fn) else "",
                                is_test=_is_test_file(rel))
            by_name[fn.name].append(nid)
            bodies[nid] = fn

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add(node, node.name)
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add(sub, f"{node.name}.{sub.name}")
    for nid, fn in bodies.items():
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            f = call.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            for target in by_name.get(name or "", []):
                g.add_call(nid, target)
    return g


def load_graph(repo: Path, use_graphify: bool = True, log=print) -> CodeGraph:
    if use_graphify:
        path = repo / "graphify-out" / "graph.json"
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True,
                              text=True).stdout.strip()
        fresh = False
        if path.exists():
            try:
                fresh = json.loads(path.read_text()).get("built_at_commit") == head
            except json.JSONDecodeError:
                fresh = False
        if not fresh:
            path = build_graphify(repo, log=log) or path
        if path.exists():
            try:
                g = load_graphify(path)
                if g.code_nodes():
                    return g
            except (json.JSONDecodeError, KeyError) as exc:
                log(f"Could not read graph.json ({exc}); using built-in AST graph")
    return build_ast_graph(repo)
