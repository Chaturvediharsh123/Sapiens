"""Command line entry point.

    culprit "login crashes when the email has a + sign"
    culprit "login works with a wrong password" --security
    culprit doctor
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .graph import graphify_available
from .llm import DEFAULT_HOST, LLMError, OllamaLLM, list_models, resolve_model
from .pipeline import run
from .security import bandit_available
from .ui import UI


def doctor(host: str, model: str | None) -> int:
    ui = UI()
    ui.console.print(f"[bold]Culprit {__version__} doctor[/bold]\n")
    ok = True

    def check(name, passed, detail="", required=True):
        nonlocal ok
        mark = "[green]✓[/green]" if passed else ("[red]✗[/red]" if required else "[yellow]![/yellow]")
        ui.console.print(f"  {mark} {name}  [dim]{detail}[/dim]")
        if required and not passed:
            ok = False

    check("Python 3.10+", sys.version_info >= (3, 10), platform.python_version())
    check("git", shutil.which("git") is not None)
    pytest_ok = subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True).returncode == 0
    check("pytest", pytest_ok)
    g_ok, b_ok = graphify_available(), bandit_available()
    check("Graphify (code map)", g_ok,
          "" if g_ok else "uv tool install graphifyy  (optional: built-in AST graph is used without it)",
          required=False)
    check("Bandit (security mode)", b_ok, "" if b_ok else "pip install bandit", required=False)
    try:
        models = [m["name"] for m in list_models(host)]
        check(f"Ollama at {host}", True, f"{len(models)} model(s) installed")
    except Exception as exc:
        check(f"Ollama at {host}", False, f"start it with `ollama serve` ({exc.__class__.__name__})")
        return 1
    try:
        name = resolve_model(model, host)
        info = next((m for m in list_models(host) if m["name"].startswith(name)), {})
        size = info.get("details", {}).get("parameter_size", "?")
        check("model", True, f"{name}  (parameters: {size}, quantization: "
                             f"{info.get('details', {}).get('quantization_level', '?')})")
        llm = OllamaLLM(name, host)
        t = time.time()
        llm._chat([{"role": "user", "content": "Reply with the single word: ready"}], purpose="doctor")
        check("model responds", True, f"{time.time() - t:.1f}s, {llm.stats.tokens_per_sec:.1f} tokens/sec")
    except LLMError as exc:
        check("model", False, str(exc))
    ui.console.print("\n[green]All set.[/green]" if ok else "\n[red]Fix the items above first.[/red]")
    return 0 if ok else 1


def _utf8() -> None:
    """Windows terminals: print ✓ and friends without needing PYTHONUTF8."""
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def welcome(ui: UI) -> int:
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    t = Table.grid(padding=(0, 3))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column(style="grey70")
    for cmd, what in [
        ('culprit "describe the bug"', "find the commit that broke it, explain it, prove a fix"),
        ('culprit "..." --security', "security issues: Bandit guides the search and checks the fix"),
        ('culprit "..." --good v1.2', "tell it where things still worked (optional)"),
        ('culprit "..." --no-fix', "stop after finding and explaining the culprit"),
        ("culprit demo", "try it on a demo shop with 7 planted bugs"),
        ("culprit doctor", "check git, pytest, Graphify, Bandit, Ollama and the model"),
        ("culprit --help", "all options"),
    ]:
        t.add_row(cmd, what)
    title = Text.assemble(("◉ ", "#ff4f61"), ("CULPRIT", "bold #ff4f61"), (f"  v{__version__}", "grey58"))
    ui.console.print(Panel(t, title=title, title_align="left", border_style="#ff4f61", padding=(1, 2),
                           subtitle=Text("offline · your code never leaves this machine", style="grey58"),
                           subtitle_align="right"))
    return 0


def preflight(ui: UI, repo: Path, good: str | None, bad: str) -> Path | None:
    """Catch the common mistakes before any model call. Returns the repo root or None."""
    if not shutil.which("git"):
        ui.problem("git is not installed", "Culprit reads your project's git history.",
                   ["install Git from git-scm.com, then open a new terminal"])
        return None
    if not repo.exists():
        ui.problem("Folder not found", f"{repo} does not exist.", ["check the path you passed to --repo"])
        return None
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(repo), capture_output=True, text=True)
    if top.returncode != 0:
        fixes = ["cd into your project folder (the one with the .git folder), or pass --repo PATH"]
        if (repo / "demo-shop" / ".git").exists():
            fixes.insert(0, "cd demo-shop")
        fixes.append("culprit demo   (to try it on the demo shop)")
        ui.problem("Not a git repository", f"{repo} has no git history to investigate.", fixes)
        return None
    root = Path(top.stdout.strip())
    if (root / "culprit" / "pipeline.py").exists() and (root / "pyproject.toml").exists() and \
            'name = "culprit"' in (root / "pyproject.toml").read_text(errors="ignore"):
        fixes = ["cd demo-shop" if (root / "demo-shop" / ".git").exists() else "culprit demo coupon",
                 "or cd into the project you want to investigate"]
        ui.problem("This is Culprit's own source code",
                   "You are inside the Culprit project, not the project with the bug.", fixes)
        return None
    count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=str(root), capture_output=True, text=True)
    if count.returncode != 0 or int(count.stdout.strip() or 0) < 2:
        ui.problem("Not enough history", "Culprit needs at least 2 commits to compare.",
                   ["commit your work, then run Culprit when a later commit breaks something"])
        return None
    py = subprocess.run(["git", "ls-files", "*.py"], cwd=str(root), capture_output=True, text=True)
    if not py.stdout.strip():
        ui.problem("No Python code found", "Culprit currently works on Python projects tested with pytest.", [])
        return None
    for label, rev in (("--bad", bad), ("--good", good)):
        if rev and subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], cwd=str(root),
                                  capture_output=True).returncode != 0:
            ui.problem(f"Unknown commit for {label}", f"'{rev}' is not a commit, branch or tag in this repo.",
                       ["git log --oneline   (to see commit ids)"])
            return None
    subprocess.run(["git", "worktree", "prune"], cwd=str(root), capture_output=True)
    return root


def get_model(ui: UI, requested: str | None, host: str) -> str | None:
    try:
        return resolve_model(requested, host)
    except LLMError as exc:
        msg = str(exc)
        if "Cannot reach Ollama" in msg:
            ui.problem("Ollama is not running", f"Culprit needs a local model from Ollama at {host}.",
                       ["open the Ollama app (or run: ollama serve), then try again"])
        elif "not installed" in msg:
            ui.problem("Model not installed", msg.split(" Run ")[0], [f"ollama pull {requested}", "ollama list"])
        else:
            ui.problem("No model available", msg, ["ollama pull qwen2.5-coder:3b"])
        return None


def add_run_options(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--no-fix", action="store_true", help="stop after finding and explaining the culprit")
    ap.add_argument("--no-guided", action="store_true", help="always bisect the full range")
    ap.add_argument("--no-graphify", action="store_true", help="use the built-in AST graph instead of Graphify")
    ap.add_argument("--runs", type=int, default=3, help="test runs per bisect step (flaky-test guard)")
    ap.add_argument("--model", help="Ollama model (default: $CULPRIT_MODEL or the best installed model)")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Ollama host")
    ap.add_argument("--ctx", type=int, default=4096, help="model context window")
    ap.add_argument("--out", help="folder for report.md (default: ./culprit-out/<sha>)")


def investigate(ui: UI, a, repo: Path, report: str, security: bool, good: str | None, bad: str) -> int:
    model = get_model(ui, a.model, a.host)
    if not model:
        return 2
    ui.header(report, model, str(repo), mode="security" if security else "normal")
    llm = OllamaLLM(model, a.host, num_ctx=a.ctx)
    res = run(repo, report, llm, good=good, bad=bad, security_mode=security, do_fix=not a.no_fix,
              runs=a.runs, guided=not a.no_guided, use_graphify=not a.no_graphify,
              out_dir=Path(a.out) if a.out else None, ui=ui)
    return 0 if res.status in ("found", "found_no_fix") else 1


def demo(ui: UI, argv: list[str]) -> int:
    from rich.table import Table
    from . import demo as d
    ap = argparse.ArgumentParser(prog="culprit demo", description="Try Culprit on a demo shop with 7 planted bugs.")
    ap.add_argument("bug", nargs="?", help="one of: " + ", ".join(d.ALIASES))
    ap.add_argument("--dir", default="demo-shop", help="where to build the demo repo (default: ./demo-shop)")
    ap.add_argument("--fresh", action="store_true", help="rebuild the demo repo from scratch")
    add_run_options(ap)
    a = ap.parse_args(argv)
    target = Path(a.dir).resolve()
    if not a.bug:
        t = Table(box=None, padding=(0, 2), header_style="bold grey58")
        t.add_column("name", style="bold cyan", no_wrap=True)
        t.add_column("mode")
        t.add_column("bug report Culprit receives")
        for full, meta in d.BUGS.items():
            mode = "[#e3b341]security[/]" if meta["mode"] == "security" else "normal"
            t.add_row(d.SHORT[full], mode, meta["report"])
        ui.console.print("\n[bold]Demo shop:[/] 30 commits by 5 developers, 7 bugs planted at known commits.\n")
        ui.console.print(t)
        ui.console.print("\n[grey58]run one:[/] [bold cyan]culprit demo coupon[/]   "
                         "[grey58]rebuild:[/] [bold cyan]culprit demo coupon --fresh[/]\n")
        return 0
    key = d.ALIASES.get(a.bug.lower(), a.bug.lower())
    if key not in d.BUGS:
        ui.problem("Unknown demo bug", f"'{a.bug}' is not one of the demo bugs.",
                   ["culprit demo   (to list them)"] + [f"culprit demo {x}" for x in list(d.ALIASES)[:3]])
        return 2
    if a.fresh or not (target / ".git").exists():
        with ui.working(f"building demo shop at {target}"):
            d.build(target)
        ui.ok(f"demo shop ready at {target} (30 commits, 7 planted bugs)")
    bug = d.BUGS[key]
    return investigate(ui, a, target, bug["report"], bug["mode"] == "security", None, "HEAD")


def main(argv: list[str] | None = None) -> int:
    _utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    ui = UI()
    try:
        if not argv:
            return welcome(ui)
        if argv[0] in ("--version", "-V", "version"):
            ui.console.print(f"culprit {__version__}")
            return 0
        if argv[0] == "doctor":
            ap = argparse.ArgumentParser(prog="culprit doctor")
            ap.add_argument("--host", default=DEFAULT_HOST)
            ap.add_argument("--model")
            a = ap.parse_args(argv[1:])
            return doctor(a.host, a.model)
        if argv[0] == "demo":
            return demo(ui, argv[1:])

        ap = argparse.ArgumentParser(
            prog="culprit",
            description="Find which commit introduced a bug (or a security hole), explain it, and prove a fix. "
                        "Runs fully offline with a local model via Ollama.",
            epilog='examples:  culprit "coupon save10 gives no discount"   |   culprit demo   |   culprit doctor')
        ap.add_argument("report", help="the bug report in plain words")
        ap.add_argument("--repo", default=".", help="path to the git repo (default: current folder)")
        ap.add_argument("--good", help="a commit where it still worked (optional: found automatically)")
        ap.add_argument("--bad", default="HEAD", help="a commit where it is broken (default: HEAD)")
        ap.add_argument("--security", action="store_true", help="security mode: also use Bandit findings")
        add_run_options(ap)
        a = ap.parse_args(argv)
        if len(a.report.split()) < 3:
            ui.problem("Bug report too short", f'"{a.report}" is too vague for Culprit to write a test from.',
                       ['describe what goes wrong, e.g. culprit "coupon SAVE10 gives no discount when typed in lowercase"'])
            return 2
        root = preflight(ui, Path(a.repo).resolve(), a.good, a.bad)
        if not root:
            return 2
        return investigate(ui, a, root, a.report, a.security, a.good, a.bad)
    except KeyboardInterrupt:
        ui.console.print("\n[#e3b341]Stopped.[/] Your checkout and branches were not changed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
