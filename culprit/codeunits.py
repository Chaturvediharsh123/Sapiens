"""Split Python files into 'code units' (functions, methods, top-level statements).

Culprit reads, explains and rewrites code one unit at a time, so a small model only
ever sees a few lines instead of whole files.
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field


@dataclass
class CodeUnit:
    file: str            # repo-relative path, e.g. shop/pricing.py
    qualname: str        # validate_email, Cart.total, <module>:PAYMENT_API_TOKEN
    kind: str            # "function" | "statement"
    start: int           # first line (1-based, includes decorators)
    end: int             # last line (inclusive)
    source: str
    indent: str = ""
    score: float = field(default=0.0, compare=False)

    @property
    def module(self) -> str:
        return module_name(self.file)

    @property
    def name(self) -> str:
        return self.qualname.split(":")[-1].split(".")[-1]

    def import_hint(self) -> str:
        top = self.qualname.split(":")[-1].split(".")[0]
        if self.kind == "statement":
            return f"import {self.module}  # then use {self.module}.{top}"
        return f"from {self.module} import {top}"

    def label(self) -> str:
        return f"{self.file}::{self.qualname.replace('<module>:', '')}"


def module_name(path: str) -> str:
    mod = path[:-3] if path.endswith(".py") else path
    mod = mod.replace("\\", "/").replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


def _stmt_name(node: ast.stmt) -> str:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        return ",".join(names) or f"line{node.lineno}"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "import:" + ",".join(a.asname or a.name for a in node.names)
    return f"{type(node).__name__.lower()}@{node.lineno}"


def units_in_source(source: str, file: str) -> list[CodeUnit]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()

    def make(node, qualname, kind):
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        end = node.end_lineno or node.lineno
        text = "\n".join(lines[start - 1:end])
        indent = lines[start - 1][: len(lines[start - 1]) - len(lines[start - 1].lstrip())]
        return CodeUnit(file, qualname, kind, start, end, text, indent)

    units: list[CodeUnit] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append(make(node, node.name, "function"))
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    units.append(make(sub, f"{node.name}.{sub.name}", "function"))
                else:
                    units.append(make(sub, f"{node.name}:{_stmt_name(sub)}", "statement"))
        else:
            units.append(make(node, f"<module>:{_stmt_name(node)}", "statement"))
    return units


def unit_at_line(units: list[CodeUnit], line: int) -> CodeUnit | None:
    hits = [u for u in units if u.start <= line <= u.end]
    return min(hits, key=lambda u: u.end - u.start) if hits else None


def find_unit(units: list[CodeUnit], qualname: str) -> CodeUnit | None:
    for u in units:
        if u.qualname == qualname:
            return u
    return None


def extract_replacement(new_code: str, unit: CodeUnit) -> str | None:
    """From the model's answer, keep only the code that replaces `unit`."""
    code = textwrap.dedent(new_code).strip("\n")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    lines = code.splitlines()
    if unit.kind == "function":
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == unit.name:
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                seg = "\n".join(lines[start - 1:node.end_lineno])
                return textwrap.dedent(seg)
        return None
    # statement: prefer the assignment to the same name, otherwise take everything
    target = unit.qualname.split(":")[-1]
    for node in tree.body:
        if _stmt_name(node) == target:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return code if len(lines) <= 6 else None


def replace_unit(source: str, unit: CodeUnit, replacement: str) -> str:
    lines = source.splitlines()
    new_lines = [(unit.indent + ln) if ln.strip() else "" for ln in replacement.splitlines()]
    out = lines[: unit.start - 1] + new_lines + lines[unit.end:]
    return "\n".join(out) + ("\n" if source.endswith("\n") else "")
