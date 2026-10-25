"""Write the evidence report (report.md) and machine-readable result.json."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path


def _plain(obj):
    if is_dataclass(obj):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


def write(out_dir: Path, run) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# Culprit report", "", f"**Bug report:** {run.report}", "",
          f"- Repo: `{run.repo}`", f"- Model: `{run.model}` (local, via Ollama)",
          f"- Mode: {run.mode}", f"- Status: **{run.status}**", ""]

    if run.located:
        md += ["## 1. Located code (Graphify)", ""]
        md += [f"- `{u}`" for u in run.located] + [""]
    if run.test_code:
        md += ["## 2. Reproduction test", "",
               f"Fails at the bad commit (`{run.bad[:8]}`): {run.bad_reason}",
               f"Passes at the good commit (`{run.good[:8]}`){' (found automatically)' if run.good_auto else ''}.",
               "", "```python", run.test_code.rstrip(), "```", ""]
    if run.culprit:
        c = run.culprit
        md += ["## 3. Culprit commit", "",
               f"**`{c['sha'][:8]}`** by {c['author']} on {c['date']}: \"{c['message']}\"", "",
               f"- Bisect: {run.bisect_steps} test runs, "
               f"{'graph-guided over ' + str(run.bisect_guided_range) + ' of ' if run.bisect_guided else 'full range of '}"
               f"{run.bisect_range} commits",
               f"- Verified: test passes at the parent commit and fails at the culprit: "
               f"{'yes' if run.bisect_verified else 'no'}", ""]
    if run.explanation:
        e = run.explanation
        md += ["## 4. Why it broke", "", f"**What changed:** {e['summary']}", "",
               f"**Root cause:** {e['root_cause']}", "", f"**Risk:** {e['risk']}", ""]
        if run.blast:
            md += ["**Blast radius** (code that calls the changed code):", ""]
            md += [f"- `{q}` in {f} ({h} hop{'s' if h > 1 else ''})" for q, f, h in run.blast] + [""]
        if run.diff:
            md += ["<details><summary>Culprit diff</summary>", "", "```diff", run.diff[:6000], "```",
                   "", "</details>", ""]
    if run.fix:
        f = run.fix
        md += ["## 5. Fix", ""]
        if f.get("ok"):
            md += [f"Verified fix committed on branch **`{f['branch']}`** (not merged).", "",
                   "- Reproduction test passes", "- No new failures in the existing test suite"]
            if f.get("security_cleared") is not None:
                md += [f"- Bandit finding cleared: {'yes' if f['security_cleared'] else 'no'}"]
            md += [f"- Regression test saved as `{f['regression_test']}`", "",
                   "```diff", f["patch"][:6000], "```", ""]
        else:
            md += ["No verified fix was found. Notes:", ""] + [f"- {n}" for n in f.get("notes", [])] + [""]
    md += ["## Run stats", "",
           f"- Total time: {run.seconds:.1f}s",
           f"- Model calls: {run.llm_calls}, retries: {run.llm_retries}",
           f"- Generation speed: {run.tokens_per_sec:.1f} tokens/sec", ""]
    path = out_dir / "report.md"
    path.write_text("\n".join(md))
    (out_dir / "result.json").write_text(json.dumps(_plain(run), indent=2, default=str))
    return path
