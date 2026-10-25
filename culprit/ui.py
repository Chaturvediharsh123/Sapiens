"""Live terminal output (Rich): branded header, step rail, timings, the culprit reveal, verdicts."""
from __future__ import annotations

import contextlib
import time

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

RED = "#ff4f61"
GREEN = "#3fb950"
AMBER = "#e3b341"
DIM = "grey58"
INK = "bold white"

STEPS = ["Locate", "Reproduce", "Bisect", "Explain", "Fix"]
NOTES = {
    1: "Graphify code map + model keywords",
    2: "model writes a test, pytest checks it",
    3: "git bisect, no AI",
    4: "model reads the culprit diff",
    5: "model rewrites one function, tests prove it",
}


class UI:
    def __init__(self, quiet: bool = False):
        self.console = Console(quiet=quiet, highlight=False)
        self._step = 0
        self._t_step = None
        self._t_run = time.time()

    # ------------------------------------------------------------------ header
    def header(self, report: str, model: str, repo: str, mode: str = "normal") -> None:
        from . import __version__
        self._t_run = time.time()
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=DIM, no_wrap=True)
        grid.add_column()
        grid.add_row("bug", Text(report, style=INK))
        grid.add_row("repo", repo)
        grid.add_row("model", f"{model} [{DIM}]· runs on this machine[/]")
        if mode == "security":
            grid.add_row("mode", f"[{AMBER}]security[/] [{DIM}]· Bandit findings guide the search and verify the fix[/]")
        title = Text.assemble(("◉ ", RED), ("CULPRIT", f"bold {RED}"), (f"  v{__version__}", DIM))
        sub = Text("find the commit that broke it · prove the fix", style=DIM)
        self.console.print(Panel(grid, title=title, title_align="left", subtitle=sub, subtitle_align="right",
                                 border_style=RED, box=box.HEAVY, padding=(1, 2)))

    # ------------------------------------------------------------------ steps
    def _rail(self, current: int) -> Text:
        t = Text("  ")
        for i, name in enumerate(STEPS, start=1):
            if i < current:
                t.append("● ", style=GREEN)
                t.append(name, style=GREEN)
            elif i == current:
                t.append("◉ ", style=f"bold {RED}")
                t.append(name.upper(), style=f"bold {RED}")
            else:
                t.append("○ ", style=DIM)
                t.append(name, style=DIM)
            if i < len(STEPS):
                t.append("  ──  ", style=GREEN if i < current else DIM)
        return t

    def _close_step(self) -> None:
        if self._t_step is not None:
            self.console.print(f"  [{DIM}]└ done in {time.time() - self._t_step:.1f}s[/]")
            self._t_step = None

    def step(self, n: int, title: str) -> None:
        self._close_step()
        self._step = n
        self.console.print()
        self.console.print(self._rail(n))
        label = Text.assemble((f" STEP {n}/{len(STEPS)} ", f"bold white on {RED}"), ("  ", ""), (title, "bold"),
                              (f"   {NOTES.get(n, '')}", DIM))
        self.console.print(label)
        self._t_step = time.time()

    # ------------------------------------------------------------------ lines
    def info(self, msg: str) -> None:
        self.console.print(f"  [{DIM}]│[/] [{DIM}]{msg.strip()}[/]")

    def ok(self, msg: str) -> None:
        self.console.print(f"  [{GREEN}]✓[/] {msg}")

    def warn(self, msg: str) -> None:
        self.console.print(f"  [{AMBER}]![/] {msg}")

    def fail(self, msg: str) -> None:
        self.console.print(f"  [{RED}]✗[/] {msg}")

    @contextlib.contextmanager
    def working(self, msg: str):
        with self.console.status(f"[{DIM}]{msg}[/]", spinner="dots", spinner_style=RED):
            yield

    def code(self, text: str, title: str) -> None:
        from rich.syntax import Syntax
        self.console.print(Panel(Syntax(text.rstrip(), "python", theme="monokai", line_numbers=False,
                                        background_color="default"),
                                 title=f"[{DIM}]{title}[/]", title_align="left", border_style="grey30",
                                 box=box.ROUNDED, padding=(0, 1)))

    # ------------------------------------------------------------------ the reveal
    def culprit(self, sha: str, author: str, date: str, message: str, runs: int, scope: str) -> None:
        body = Text.assemble(
            (sha[:8], f"bold {RED}"), ("  ", ""), (f'"{message}"', INK), ("\n", ""),
            (f"by {author} on {date}", "white"), ("\n", ""),
            (f"{runs} test run{'s' if runs != 1 else ''} · {scope} · verified at its parent commit", DIM),
        )
        self.console.print(Panel(body, title=Text("CULPRIT FOUND", style=f"bold {RED}"), title_align="left",
                                 border_style=RED, box=box.DOUBLE, padding=(0, 2)))

    # ------------------------------------------------------------------ verdicts
    def case_closed(self, rows: list[tuple[str, str]], next_steps: list[tuple[str, str]]) -> None:
        self._close_step()
        t = Table.grid(padding=(0, 2))
        t.add_column(style=f"bold {DIM}", no_wrap=True)
        t.add_column()
        for k, v in rows:
            t.add_row(k, v)
        parts = [t]
        if next_steps:
            nxt = Table.grid(padding=(0, 2))
            nxt.add_column(style=DIM, no_wrap=True)
            nxt.add_column(style="bold cyan")
            for what, cmd in next_steps:
                nxt.add_row(what, cmd)
            parts += [Rule(style="grey30"), Text("next", style=f"bold {DIM}"), nxt]
        self.console.print()
        self.console.print(Panel(Group(*parts), title=Text("✓ CASE CLOSED", style=f"bold {GREEN}"),
                                 title_align="left", border_style=GREEN, box=box.HEAVY, padding=(1, 2),
                                 subtitle=Text(f"total {time.time() - self._t_run:.0f}s", style=DIM),
                                 subtitle_align="right"))

    def case_open(self, what: str, tips: list[str]) -> None:
        self._close_step()
        body = [Text(what, style=INK)]
        if tips:
            body.append(Text("\ntry:", style=f"bold {DIM}"))
            body += [Text.assemble(("  • ", AMBER), (tip, "white")) for tip in tips]
        self.console.print()
        self.console.print(Panel(Group(*body), title=Text("✗ CASE STILL OPEN", style=f"bold {RED}"),
                                 title_align="left", border_style=RED, box=box.HEAVY, padding=(1, 2)))

    def problem(self, title: str, detail: str, fixes: list[str]) -> None:
        """A friendly error before anything runs."""
        body = [Text(detail, style="white")]
        if fixes:
            body.append(Text(""))
            body += [Text.assemble(("  → ", AMBER), (f, "bold cyan" if f.startswith(("culprit", "cd ", "ollama", "git ", "pip")) else "white"))
                     for f in fixes]
        self.console.print(Panel(Group(*body), title=Text(f"✗ {title}", style=f"bold {RED}"), title_align="left",
                                 border_style=RED, box=box.ROUNDED, padding=(1, 2)))

    # kept for compatibility with older callers
    def summary(self, rows: list[tuple[str, str]], title: str, good: bool) -> None:
        if good:
            self.case_closed(rows, [])
        else:
            self.case_open(title, [])
