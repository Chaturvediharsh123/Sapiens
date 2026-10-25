"""Benchmark Culprit on the demo repo: every planted bug, N runs each (default 3).

    python bench/run_bench.py                     # all 7 bugs x 3 runs, real local model
    python bench/run_bench.py --bugs email_plus,coupon_case --runs 3
    python bench/run_bench.py --auto-good         # don't tell Culprit the good commit

Writes bench/results.json and bench/RESULTS.md (paste the table into the README).
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from culprit.llm import DEFAULT_HOST, OllamaLLM, list_models, resolve_model  # noqa: E402
from culprit.pipeline import run  # noqa: E402
from culprit.ui import UI  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT / "demo-shop"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--bugs", help="comma-separated bug ids (default: all)")
    ap.add_argument("--model")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--auto-good", action="store_true", help="let Culprit find the good commit itself")
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="show the full live output of every run")
    a = ap.parse_args()

    con = Console()
    repo = Path(a.repo).resolve()
    if not (repo / ".git").exists():
        con.print(f"[dim]building demo repo at {repo}[/dim]")
        subprocess.run([sys.executable, str(ROOT / "demo" / "make_demo_repo.py"), str(repo)], check=True)
    bugs = yaml.safe_load((ROOT / "bench" / "bugs.yaml").read_text())["bugs"]
    if a.bugs:
        wanted = set(a.bugs.split(","))
        bugs = [b for b in bugs if b["id"] in wanted]

    model = resolve_model(a.model, a.host)
    details = next((m.get("details", {}) for m in list_models(a.host) if m["name"] == model), {})
    con.print(f"[bold]Culprit benchmark[/bold]  model={model} ({details.get('parameter_size', '?')}, "
              f"{details.get('quantization_level', '?')})  runs={a.runs}  bugs={len(bugs)}")

    rows = []
    for bug in bugs:
        for i in range(1, a.runs + 1):
            llm = OllamaLLM(model, a.host)
            t = time.time()
            res = run(repo, bug["report"], llm, good=None if a.auto_good else bug["good"],
                      security_mode=bug["mode"] == "security", do_fix=not a.no_fix,
                      out_dir=ROOT / "bench" / "runs" / bug["id"] / f"run{i}", ui=UI(quiet=not a.verbose))
            row = {
                "bug": bug["id"], "mode": bug["mode"], "run": i, "status": res.status,
                "culprit_found": res.culprit.get("sha", "")[:8],
                "culprit_correct": res.culprit.get("sha") == bug["culprit"],
                "verified": res.bisect_verified,
                "bisect_runs": res.bisect_steps, "guided": res.bisect_guided,
                "repro_attempts": res.repro_attempts,
                "fix_ok": bool(res.fix.get("ok")),
                "security_cleared": res.fix.get("security_cleared"),
                "seconds": round(time.time() - t, 1),
                "tokens_per_sec": round(res.tokens_per_sec, 1),
            }
            rows.append(row)
            mark = "[green]✓[/green]" if row["culprit_correct"] else "[red]✗[/red]"
            con.print(f"  {mark} {bug['id']:<20} run {i}: culprit {row['culprit_found'] or '-':<9} "
                      f"fix {'✓' if row['fix_ok'] else '✗'}  {row['seconds']}s  {row['tokens_per_sec']} tok/s")

    n = len(rows)
    correct = sum(r["culprit_correct"] for r in rows)
    fixes = sum(r["fix_ok"] for r in rows)
    sec_rows = [r for r in rows if r["mode"] == "security"]
    sec_ok = sum(1 for r in sec_rows if r["security_cleared"])
    consistent = sum(1 for b in bugs if len({r["culprit_found"] for r in rows if r["bug"] == b["id"]}) == 1)
    tps = [r["tokens_per_sec"] for r in rows if r["tokens_per_sec"]]
    summary = {
        "model": model, "parameters": details.get("parameter_size"), "quantization": details.get("quantization_level"),
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "runs_per_bug": a.runs, "total_runs": n, "culprit_correct": correct, "fixes_verified": fixes,
        "security_cleared": f"{sec_ok}/{len(sec_rows)}", "bugs_consistent_across_runs": f"{consistent}/{len(bugs)}",
        "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 1) if n else 0,
        "avg_tokens_per_sec": round(sum(tps) / len(tps), 1) if tps else 0,
        "best_tokens_per_sec": max(tps) if tps else 0,
    }

    table = Table(title="Culprit benchmark")
    for col in ("bug", "mode", "runs", "culprit correct", "same answer every run", "fix verified", "avg s", "tok/s"):
        table.add_column(col)
    md = ["| Bug | Mode | Culprit correct | Same answer all runs | Fix verified | Avg time (s) | Tokens/s |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for b in bugs:
        rs = [r for r in rows if r["bug"] == b["id"]]
        same = len({r["culprit_found"] for r in rs}) == 1
        cells = [b["id"], b["mode"], str(len(rs)), f"{sum(r['culprit_correct'] for r in rs)}/{len(rs)}",
                 "yes" if same else "no", f"{sum(r['fix_ok'] for r in rs)}/{len(rs)}",
                 f"{sum(r['seconds'] for r in rs) / len(rs):.1f}",
                 f"{sum(r['tokens_per_sec'] for r in rs) / len(rs):.1f}"]
        table.add_row(*cells)
        md.append("| " + " | ".join(cells[:2] + cells[3:]) + " |")
    con.print(table)
    con.print(f"[bold]Culprit correct {correct}/{n}, fixes verified {fixes}/{n}, Bandit findings cleared "
              f"{summary['security_cleared']}, consistent {summary['bugs_consistent_across_runs']}, "
              f"avg {summary['avg_tokens_per_sec']} tokens/sec[/bold]")

    out = ROOT / "bench"
    (out / "results.json").write_text(json.dumps({"summary": summary, "runs": rows}, indent=2))
    header = [f"Model: `{model}` ({summary['parameters']}, {summary['quantization']}) on {summary['machine']}",
              f"Runs per bug: {a.runs}. Good commit {'found automatically' if a.auto_good else 'given'}.", "",
              f"**Culprit correct {correct}/{n} · fixes verified {fixes}/{n} · Bandit findings cleared "
              f"{summary['security_cleared']} · same answer every run {summary['bugs_consistent_across_runs']} · "
              f"avg {summary['avg_tokens_per_sec']} tokens/sec (best {summary['best_tokens_per_sec']})**", ""]
    (out / "RESULTS.md").write_text("\n".join(header + md) + "\n")
    con.print(f"[dim]wrote {out / 'results.json'} and {out / 'RESULTS.md'}[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
