# Culprit

**An offline agent that finds the exact commit that broke your code (or made it hackable), explains why, and proves a fix.**

Give Culprit a bug report in plain words. It locates the code with a [Graphify](https://github.com/Graphify-Labs/graphify) code map, writes a test that reproduces the bug, runs `git bisect` to pin down the guilty commit, explains it, and commits a verified fix plus a regression test on a new branch. The model is a local open-weight **Gemma 4** running through **Ollama**: no internet, no hosted AI, and your code never leaves your machine.

```
$ culprit "Login succeeds with a wrong password that contains a quote, like x' OR '1'='1" --security

1. Locate the code (Graphify code map)
  code map: 22 functions from Graphify graph.json
  ! Bandit: B608 hardcoded_sql_expressions at shop/db.py:18 (MEDIUM)
  ✓ most relevant: shop/db.py::check_login
2. Reproduce the bug with a test
  ✓ test fails on the buggy code (assert not True)
  ✓ test passes at auto-found good commit f1e46e0c
3. Bisect the history (git bisect, no AI)
  graph-guided over 4 of 8 commits: 2 test runs -> ffecf651 (verified)
  ✓ culprit: ffecf651 by Karan on 2026-10-09: "Inline login query for readability"
4. Explain the culprit commit
5. Fix it and prove the fix
  attempt 1: repro test pass, new suite failures 0, B608 cleared
  ✓ verified fix on branch culprit/fix-ffecf651 (not merged)
  ✓ regression test saved as tests/test_culprit_regression_ffecf651.py
```

> Built at **Hacktoberfest Hack Day Jaipur x Hack IT Sapiens** (25 Oct 2026) for the *Best Local Agentic Tool* and *Best Open-Source AI Project* tracks.

---

## The problem

"It worked last week." Finding which of dozens of commits broke something costs developers hours, and in busy open-source projects (hello, Hacktoberfest) regressions and security holes slip in through ordinary-looking commits. `git bisect` can find the commit exactly, but only if someone first writes a test that detects the bug, and that is the slow part most people skip. Many teams also cannot paste private code into hosted AI tools.

## How it works: the model proposes, real tools verify

| Step | What happens | Checked by |
| --- | --- | --- |
| 1. Locate | Gemma turns the report into keywords; Graphify's code map (functions, calls, docstrings) ranks the 3-5 most relevant functions | Graphify `graph.json` (tree-sitter, no LLM) |
| 2. Reproduce | Gemma writes a pytest test for the bug | Must **fail** at the bad commit and **pass** at a good one, or it is rejected and retried with the error as feedback (max 3) |
| 3. Bisect | `git bisect run` with that test | Exact search, no AI. Result double-checked: passes at the culprit's parent, fails at the culprit |
| 4. Explain | Gemma reads the culprit diff + the blast radius (everything that calls the changed code, 2 hops, from the graph) | |
| 5. Fix | Gemma rewrites only the broken function/statement | Repro test passes, no new failures in the project's test suite, Bandit finding gone (security mode). Committed on `culprit/fix-<sha>` with a regression test. Never merged |

Because the AI only *proposes* and every step is confirmed by pytest, git or Bandit, a small model on a laptop gives answers you can trust, and the same answer every run (temperature 0, fixed seed, exact bisect).

### Features

- **Graph-guided bisect**: bisect only over commits that touched the files Graphify located, so fewer test runs; automatically falls back to a full bisect if the result fails verification.
- **Auto-find the good commit**: no need to know when it last worked; Culprit tests 1, 2, 4, 8 … commits back until the test passes.
- **Flaky-test guard**: each bisect step runs the test 3 times; inconsistent results mark the commit as *skip* instead of giving a wrong answer.
- **Regression test saved**: the reproduction test is committed with the fix, so the bug can't silently return.
- **Security mode** (`--security`): Bandit (no AI) points at risky code, and the fix is only accepted when the Bandit finding is gone. If no valid test can be written, Culprit can bisect on the Bandit rule itself.
- **Evidence report**: `culprit-out/<sha>/report.md` contains the test, bisect stats, culprit diff, explanation, blast radius and fix patch; `result.json` has the same data for tools.
- **Your checkout is never touched**: every run happens in throwaway `git worktree`s.

---

## Quick start

Requirements: Python 3.10+, git, [Ollama](https://ollama.com). Tested target: an 8 GB RAM laptop.

```bash
# 1. local model (pick the smallest Gemma 4 size in the Ollama library that fits your RAM)
ollama pull gemma4            # or a specific size tag, e.g. ollama pull gemma4:<size>

# 2. Culprit
git clone https://github.com/<your-team>/culprit && cd culprit
pip install -e .

# 3. Graphify code map (optional but recommended; Culprit falls back to a built-in AST graph)
uv tool install graphifyy     # or: pip install graphifyy

# 4. check everything, including model size and tokens/sec
culprit doctor
```

Culprit picks the smallest installed `gemma4*` model automatically. Override with `--model` or `CULPRIT_MODEL`.

### Try it on the demo repo (7 planted bugs)

```bash
python demo/make_demo_repo.py demo-shop       # 30 commits, 5 normal + 2 security bugs
cd demo-shop

culprit "Coupon code SAVE10 stops working when the customer types it in lowercase (save10)"
culprit "Order list pagination is broken: page 2 repeats the last item of page 1"
culprit "Login succeeds with a wrong password that contains a quote, like x' OR '1'='1" --security
```

### Use it on your own repo

```bash
cd your-python-project
culprit "signup fails for emails with a + sign"            # good commit found automatically
culprit "discount applied twice" --good v1.2.0              # or tell it where it last worked
culprit "API token is hardcoded in config" --security
culprit "checkout total is wrong" --no-fix                  # stop after finding + explaining
```

Options: `--good`, `--bad` (default `HEAD`), `--security`, `--no-fix`, `--no-guided`, `--no-graphify`, `--runs` (flaky guard, default 3), `--model`, `--host`, `--ctx` (default 4096), `--out`.

Graphify is run as `graphify . --code-only`, which parses code locally with tree-sitter and needs no API key. It writes `graphify-out/` in your repo; add it to `.gitignore`.

---

## Use as an agent skill

`skills/culprit/SKILL.md` follows the Agent Skills format, so coding agents (Claude Code, Gemini CLI, Codex, …) can call Culprit when you say "find what broke login". Copy the folder into your agent's skills directory. The agent only runs the CLI; all model calls inside Culprit stay local.

---

## Benchmark

```bash
python bench/run_bench.py            # 7 bugs x 3 runs with the local model
python bench/run_bench.py --auto-good
```

It prints a table and writes `bench/results.json` and `bench/RESULTS.md`.

<!-- TEAM: paste the contents of bench/RESULTS.md here after running the benchmark on the demo laptop -->
**Results:** _run `python bench/run_bench.py` and paste `bench/RESULTS.md` here._

### Model and hardware

<!-- TEAM: fill from `culprit doctor` output -->
| | |
| --- | --- |
| Model | Gemma 4 `<tag>` via Ollama (open weights) |
| Parameters | `<from culprit doctor>` |
| Quantization | `<from culprit doctor>` |
| Minimum hardware tested | `<CPU>`, 8 GB RAM, `<OS>`, no GPU |
| Generation speed | `<best tokens/sec from benchmark>` |

---

## Track requirements

| Requirement | How Culprit meets it |
| --- | --- |
| One clearly defined task | Bug report in → guilty commit + verified fix out |
| Local inference only | Gemma 4 through Ollama on the laptop; no hosted model APIs anywhere |
| Open-source / open-weight model | Gemma 4 |
| Non-generative external tools | git, pytest, Graphify (`--code-only`, tree-sitter), Bandit |
| Public repo, open-source license | MIT |
| Model, parameter count, hardware | Table above, filled from `culprit doctor` |
| 3 repeated runs, consistent output | `bench/run_bench.py` runs every bug 3 times and reports "same answer every run" |
| Agent skill / model harness | Culprit is a verification harness around a small model, and ships a SKILL.md |

## Tests

```bash
pip install pytest pyyaml
pytest -q tests/
```

The offline suite (`tests/test_offline_pipeline.py`) runs the full pipeline on all 7 planted bugs with a scripted stand-in for the model, testing every non-AI part: worktrees, pytest checks, graph-guided and full bisect, auto good-commit search, retry on a broken test, Bandit, fix verification and regression tests. `tests/test_llm_client.py` tests the Ollama client against a local server that speaks Ollama's API. Real runs always use Gemma.

## Project layout

```
culprit/
  cli.py         command line + `culprit doctor`
  pipeline.py    locate -> reproduce -> bisect -> explain -> fix -> report
  llm.py         Ollama client: temperature 0, seed, JSON schema output, retries, tokens/sec
  graph.py       Graphify graph.json loader + built-in AST fallback, blast radius
  locate.py      keyword + graph ranking of relevant code
  repro.py       test generation, validation, auto good-commit search
  bisect.py      graph-guided git bisect with verification and fallback
  bisect_step.py the command git bisect runs (flaky-test guard, Bandit mode)
  explain.py     culprit diff -> changed functions -> explanation + blast radius
  fix.py         rewrite one unit, verify with tests + Bandit, commit on a branch
  security.py    Bandit scanner
  sandbox.py     run pytest in a worktree and classify the result
  codeunits.py   split files into functions/statements, replace one safely
  report.py      report.md + result.json
demo/make_demo_repo.py   deterministic demo repo with 7 planted bugs
bench/                   benchmark + bug list
skills/culprit/SKILL.md  agent skill
```

## Limitations

- Python projects tested with pytest (other languages are future work; Graphify already maps 36 languages).
- The bug must be something a test can observe, and introduced by a single commit.
- Security mode covers what Bandit detects; only test code you own.

## License

MIT, see [LICENSE](LICENSE).
