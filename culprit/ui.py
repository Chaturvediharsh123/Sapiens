"""Live terminal output (Rich)."""
from __future__ import annotations

import contextlib

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class UI:
    def __init__(self, quiet: bool = False):
        self.console = Console(quiet=quiet, highlight=False)

    def header(self, report: str, model: str, repo: str) -> None:
        self.console.print(Panel.fit(f"[bold]{report}[/bold]\n[dim]repo: {repo}   model: {model} (local)[/dim]",
                                     title="[bold red]Culprit[/bold red]", border_style="red"))

    def step(self, n: int, title: str) -> None:
        self.console.print(f"\n[bold cyan]{n}. {title}[/bold cyan]")

    def info(self, msg: str) -> None:
        self.console.print(f"[dim]{msg}[/dim]")

    def ok(self, msg: str) -> None:
        self.console.print(f"  [green]✓[/green] {msg}")

    def warn(self, msg: str) -> None:
        self.console.print(f"  [yellow]![/yellow] {msg}")

    def fail(self, msg: str) -> None:
        self.console.print(f"  [red]✗[/red] {msg}")

    @contextlib.contextmanager
    def working(self, msg: str):
        with self.console.status(f"[dim]{msg}[/dim]", spinner="dots"):
            yield

    def code(self, text: str, title: str) -> None:
        from rich.syntax import Syntax
        self.console.print(Panel(Syntax(text.rstrip(), "python", theme="ansi_dark", line_numbers=False),
                                 title=title, border_style="dim"))

    def summary(self, rows: list[tuple[str, str]], title: str, good: bool) -> None:
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold")
        t.add_column()
        for k, v in rows:
            t.add_row(k, v)
        self.console.print()
        self.console.print(Panel(t, title=title, border_style="green" if good else "red"))
