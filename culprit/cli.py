"""Command line entry point.

    culprit "login crashes when the email has a + sign"
    culprit "login works with a wrong password" --security
    culprit doctor
"""
from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host_default = DEFAULT_HOST
    if argv and argv[0] == "doctor":
        ap = argparse.ArgumentParser(prog="culprit doctor")
        ap.add_argument("--host", default=host_default)
        ap.add_argument("--model")
        a = ap.parse_args(argv[1:])
        return doctor(a.host, a.model)

    ap = argparse.ArgumentParser(
        prog="culprit",
        description="Find which commit introduced a bug (or a security hole), explain it, and propose a "
                    "verified fix. Runs fully offline with a local Gemma model via Ollama.")
    ap.add_argument("report", help="the bug report in plain words")
    ap.add_argument("--repo", default=".", help="path to the git repo (default: current folder)")
    ap.add_argument("--good", help="a commit where it still worked (optional: found automatically)")
    ap.add_argument("--bad", default="HEAD", help="a commit where it is broken (default: HEAD)")
    ap.add_argument("--security", action="store_true", help="security mode: also use Bandit findings")
    ap.add_argument("--no-fix", action="store_true", help="stop after finding and explaining the culprit")
    ap.add_argument("--no-guided", action="store_true", help="always bisect the full range")
    ap.add_argument("--no-graphify", action="store_true", help="use the built-in AST graph instead of Graphify")
    ap.add_argument("--runs", type=int, default=3, help="test runs per bisect step (flaky-test guard)")
    ap.add_argument("--model", help="Ollama model (default: $CULPRIT_MODEL or the smallest gemma4)")
    ap.add_argument("--host", default=host_default, help="Ollama host")
    ap.add_argument("--ctx", type=int, default=4096, help="model context window")
    ap.add_argument("--out", help="folder for report.md (default: ./culprit-out/<sha>)")
    a = ap.parse_args(argv)

    ui = UI()
    try:
        model = resolve_model(a.model, a.host)
    except LLMError as exc:
        ui.fail(str(exc))
        return 2
    repo = Path(a.repo).resolve()
    ui.header(a.report, model, str(repo))
    llm = OllamaLLM(model, a.host, num_ctx=a.ctx)
    res = run(repo, a.report, llm, good=a.good, bad=a.bad, security_mode=a.security, do_fix=not a.no_fix,
              runs=a.runs, guided=not a.no_guided, use_graphify=not a.no_graphify,
              out_dir=Path(a.out) if a.out else None, ui=ui)
    return 0 if res.status in ("found", "found_no_fix") else 1


if __name__ == "__main__":
    sys.exit(main())
