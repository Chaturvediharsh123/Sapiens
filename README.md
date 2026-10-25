# Culprit

**An offline AI detective: describe a bug, and Culprit finds the exact commit that caused it, explains why, and hands you a tested fix. Your code never leaves your laptop.**

[Interactive code graph](https://chaturvediharsh123.github.io/Sapiens/docs/graphify/graph.html) · [Quick start](#quick-start) · [How it works](#how-it-works) · [Results](#results) · [Choose your model](#choose-your-model)

```
$ culprit demo coupon

  ● Locate  ──  ● Reproduce  ──  ◉ BISECT  ──  ○ Explain  ──  ○ Fix
 STEP 3/5   Bisect the history   git bisect, no AI
╔═ CULPRIT FOUND ═══════════════════════════════════════════════╗
║  220f05df  "Simplify coupon lookup"                            ║
║  by Aman on 2026-10-08                                         ║
║  1 test run · graph-guided over 2 of 8 commits · verified      ║
╚════════════════════════════════════════════════════════════════╝
  ...
┏━ ✓ CASE CLOSED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  fix      verified on branch culprit/fix-220f05df + regression test
┃  next     git diff HEAD culprit/fix-220f05df
```

> Built at **Hacktoberfest Hack Day Jaipur x Hack IT Sapiens** (25 Oct 2026) for the *Best Local Agentic Tool* and *Best Open-Source AI Project* tracks.

## The problem

"It worked last week." Finding which of hundreds of commits broke something costs developers hours. `git bisect` can find it exactly, but only if someone first writes a test that catches the bug, which is the slow part. And many teams can't paste private code into hosted AI tools.

## How it works

The model proposes; real tools verify every step.

| Step | What happens | Verified by |
| --- | --- | --- |
| 1. Locate | A [Graphify](https://github.com/Graphify-Labs/graphify) code map finds the 3 to 5 functions involved | Graphify (tree-sitter, no AI) |
| 2. Reproduce | The model writes a test for the bug | Must fail now and pass on an older commit, or it is retried with the error |
| 3. Bisect | `git bisect` searches history with that test | Exact, no AI; re-checked at the culprit's parent |
| 4. Explain | The model explains the culprit diff and what else it affects | |
| 5. Fix | The model rewrites only the broken function | Test passes, no existing test breaks, Bandit finding gone (security mode) |

The fix lands on a new branch `culprit/fix-<sha>` with a regression test. Nothing is merged, and your checkout is never touched. A full evidence report is saved to `culprit-out/<sha>/report.md`.

Also included: bisect limited to files the graph located (fewer test runs), automatic search for the last good commit, a flaky-test guard (each step runs 3 times), and **security mode** (`--security`) that finds the commit that made your app hackable.

## Quick start

Needs Python 3.10+, Git and [Ollama](https://ollama.com). No GPU.

```bash
pip install pipx
pipx install "culprit @ git+https://github.com/Chaturvediharsh123/Sapiens.git"
pipx inject culprit graphifyy          # Graphify code map (optional)
ollama pull qwen2.5-coder:3b           # skip if you already have a model
culprit doctor                         # checks everything
```

**Try the demo** (a shop app with 30 commits and 7 planted bugs):

```bash
culprit demo            # list the bugs
culprit demo coupon     # investigate one
culprit demo login      # security bug: SQL injection in login
```

**Use it on your project** (Python + pytest + git):

```bash
cd your-project
culprit "coupon SAVE10 gives no discount when typed in lowercase"
culprit "discount applied twice" --good v1.2.0     # optional: where it still worked
culprit "login works with a wrong password" --security
culprit "checkout total is wrong" --no-fix         # find and explain only
```

Write the report like you'd tell a teammate: name the feature, give an input and the expected result. Run `culprit --help` for all options.

## Choose your model

Any chat model in Ollama works (`ollama list` shows yours). With no settings, Culprit picks the best one installed: Gemma 4, then code models, then other chat models.

| To | Run |
| --- | --- |
| Use a model once | `culprit "bug" --model gemma3:4b` |
| Use it every time (Git Bash, Mac, Linux) | `export CULPRIT_MODEL=gemma3:4b` |
| Use it every time (Windows CMD / PowerShell) | `set CULPRIT_MODEL=gemma3:4b` / `$env:CULPRIT_MODEL="gemma3:4b"` |
| See which model will be used | `culprit doctor` |

Use the exact name from `ollama list`. Embedding models (like `nomic-embed-text`) won't work. 3B to 8B models suit a laptop; code models such as `qwen2.5-coder` write the best tests and fixes.

## Results

Real runs with `qwen2.5-coder:3b` on a 16 GB Windows laptop, CPU only, offline. Every culprit matches the commit where the bug was planted.

| Bug report | Culprit found | Correct | Fix verified | Time |
| --- | --- | --- | --- | --- |
| Coupon SAVE10 fails in lowercase | `220f05df` "Simplify coupon lookup" | yes | yes | 63 s |
| Signup rejects emails with a + (run 2) | `2d933b90` "Clean up email validation pattern" | yes | yes | 88 s |
| Signup rejects emails with a + (run 3) | `2d933b90` "Clean up email validation pattern" | yes | yes | 91 s |

| Model | Parameters | Quantization | Hardware | Speed |
| --- | --- | --- | --- | --- |
| `qwen2.5-coder:3b` (Ollama) | 3.1B | Q4_K_M | Windows 11, 16 GB RAM, no GPU | 23 to 28 tok/s (doctor), 12 to 14 tok/s in runs |

Run the full benchmark (7 bugs × 3 runs): `python bench/run_bench.py` → `bench/RESULTS.md`.

## Code map

Graphify's map of this repo, built locally with zero AI tokens: **[open the interactive graph](https://chaturvediharsh123.github.io/Sapiens/docs/graphify/graph.html)** (300 nodes, 777 edges). The investigation pipeline is highlighted in red; click a step to spotlight it. Files: [`graph.html`](docs/graphify/graph.html) (works offline), [`GRAPH_REPORT.md`](docs/graphify/GRAPH_REPORT.md), [`graph.json`](docs/graphify/graph.json).

## Agent skill

[`skills/culprit/SKILL.md`](skills/culprit/SKILL.md) lets coding agents that support skills run Culprit when you say "find what broke login". All model calls stay local.

## Development

```bash
git clone https://github.com/Chaturvediharsh123/Sapiens.git && cd Sapiens
pip install -e . graphifyy
pytest -q tests/        # 21 tests, no model needed
```

`culprit/`: `cli.py` (commands), `pipeline.py` (the 5 steps), `locate.py`, `repro.py`, `bisect.py`, `explain.py`, `fix.py`, `llm.py` (Ollama client), `graph.py` (Graphify + fallback), `security.py` (Bandit), `demo.py` (demo shop), `ui.py` (terminal output).

## Limitations

- Python projects tested with pytest, for now.
- The bug must be visible to a test and introduced by one commit.
- Security mode covers what Bandit detects. Only test code you own.

## License

MIT, see [LICENSE](LICENSE).
