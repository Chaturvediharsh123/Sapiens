# Culprit

**An offline agent that finds the exact commit that broke your code (or made it hackable), explains why, and proves a fix.**

**[Interactive code graph](https://chaturvediharsh123.github.io/Sapiens/docs/graphify/graph.html)** · [Quick start](#quick-start) · [How it works](#how-it-works-the-model-proposes-real-tools-verify) · [Results](#results) · [Demo repo](#try-it-on-the-demo-repo-7-planted-bugs) · [Agent skill](#use-as-an-agent-skill)

Give Culprit a bug report in plain words. It locates the code with a [Graphify](https://github.com/Graphify-Labs/graphify) code map, writes a test that reproduces the bug, runs `git bisect` to pin down the guilty commit, explains it, and commits a verified fix plus a regression test on a new branch. The model is any local open-weight model running through **Ollama** (Gemma, Qwen, Llama, Mistral…): no internet, no hosted AI, and your code never leaves your machine.

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
| 1. Locate | The model turns the report into keywords; Graphify's code map (functions, calls, docstrings) ranks the 3-5 most relevant functions | Graphify `graph.json` (tree-sitter, no LLM) |
| 2. Reproduce | The model writes a pytest test for the bug | Must **fail** at the bad commit and **pass** at a good one, or it is rejected and retried with the error as feedback (max 3) |
| 3. Bisect | `git bisect run` with that test | Exact search, no AI. Result double-checked: passes at the culprit's parent, fails at the culprit |
| 4. Explain | The model reads the culprit diff + the blast radius (everything that calls the changed code, 2 hops, from the graph) | |
| 5. Fix | The model rewrites only the broken function/statement | Repro test passes, no new failures in the project's test suite, Bandit finding gone (security mode). Committed on `culprit/fix-<sha>` with a regression test. Never merged |

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

Requirements: Python 3.10+, git, [Ollama](https://ollama.com). Runs on a normal laptop (no GPU needed).

### Install in two commands

```bash
pip install pipx
pipx install "culprit @ git+https://github.com/Chaturvediharsh123/Sapiens.git"
pipx inject culprit graphifyy        # optional: Graphify code map
```

pipx gives you a global `culprit` command in its own sandbox: no virtual environment to create or activate.

### Get a model (skip if you already have one in Ollama)

```bash
ollama pull qwen2.5-coder:3b         # small and good at code; any other chat model works too
culprit doctor                       # checks git, pytest, Ollama, the model, and tokens/sec
```

**Any open model you already have in Ollama works.** With no settings, Culprit picks the best installed one automatically: Gemma 4 first, then code models (like `qwen2.5-coder`), then other chat models (Llama, Gemma 3, Mistral, Qwen…). It skips embedding models and prefers laptop-sized models over huge ones. To choose yourself, use `--model llama3.2:3b` or set `CULPRIT_MODEL`.

### Choose your model

Culprit works with **any chat model in Ollama**. See what you have with `ollama list`.

| What you want | How |
| --- | --- |
| Let Culprit pick | Do nothing. It picks the best installed model (Gemma 4, then code models, then other chat models). |
| Use a model for one run | `culprit "bug report" --model gemma3:4b` |
| Use a model for every run (Git Bash, Mac, Linux) | `export CULPRIT_MODEL=gemma3:4b` |
| Use a model for every run (Windows CMD) | `set CULPRIT_MODEL=gemma3:4b` |
| Use a model for every run (PowerShell) | `$env:CULPRIT_MODEL="gemma3:4b"` |
| Get a new model | `ollama pull llama3.2:3b` |
| Check which model will be used | `culprit doctor` |

Use the exact name `ollama list` shows. Embedding models such as `nomic-embed-text` cannot be used. Models from about 3B to 8B parameters work well on a laptop; code models like `qwen2.5-coder` are good at writing the tests and fixes. If Ollama runs on another machine, pass `--host http://that-machine:11434`.

### Developer install (to change the code)

```bash
git clone https://github.com/Chaturvediharsh123/Sapiens.git culprit && cd culprit
python -m venv .venv && source .venv/bin/activate      # Windows Git Bash: source .venv/Scripts/activate
pip install -e . && pip install graphifyy
```

On Windows, also run `export PYTHONUTF8=1` (Git Bash) so the terminal output's ✓ symbols print correctly.

### Try it on the demo repo (7 planted bugs)

Fastest way, works right after installing:

```bash
culprit demo            # list the 7 planted bugs
culprit demo coupon     # build the demo shop and investigate one
culprit demo login      # a security bug (SQL injection in login)
```

Or build it by hand:

The demo generator lives in this repo, so clone it first if you installed with pipx.

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

`skills/culprit/SKILL.md` follows the Agent Skills format, so coding agents that support skills can call Culprit when you say "find what broke login". Copy the folder into your agent's skills directory. The agent only runs the CLI; all model calls inside Culprit stay local.

---

## Results

### Real runs on a laptop

Completed runs with `qwen2.5-coder:3b` on a 16 GB Windows laptop, no GPU, Wi-Fi not needed. Every culprit below matches the commit where the bug was actually planted.

| Bug report | Culprit found | Correct | Fix verified | Time | Speed |
| --- | --- | --- | --- | --- | --- |
| Coupon SAVE10 fails in lowercase | `220f05df` "Simplify coupon lookup" (Aman) | yes | yes | 63 s | 14.2 tok/s |
| Signup rejects emails with a + sign (run 2) | `2d933b90` "Clean up email validation pattern" (Rahul) | yes | yes | 88 s | 12.0 tok/s |
| Signup rejects emails with a + sign (run 3) | `2d933b90` "Clean up email validation pattern" (Rahul) | yes | yes | 91 s | 12.4 tok/s |

The two email runs wrote different reproduction tests but reached the same commit and the same fix: the model's wording can vary, while `git bisect` makes the answer exact.

### Run the full benchmark

```bash
python bench/run_bench.py            # all 7 bugs x 3 runs with your local model
python bench/run_bench.py --auto-good  # also let Culprit find the good commit itself
```

It prints a table and writes `bench/results.json` and `bench/RESULTS.md` (culprit accuracy, fixes verified, Bandit findings cleared, same answer across runs, tokens/sec).

### Model and hardware

| | |
| --- | --- |
| Model | `qwen2.5-coder:3b` via Ollama (open weights); any Ollama chat model works |
| Parameters | 3.1B |
| Quantization | Q4_K_M |
| Minimum hardware tested | Windows 11 laptop, 16 GB RAM, CPU only (no GPU) |
| Generation speed | 23 to 28 tokens/sec in `culprit doctor`; 12 to 14 tokens/sec during full runs |

---

## Code map (Graphify)

`docs/graphify/` holds Graphify's map of this repository, built locally with `graphify . --code-only` and `GRAPHIFY_BACKEND=none graphify cluster-only .` (tree-sitter parsing, no AI, zero tokens):

- **[Open the interactive graph](https://chaturvediharsh123.github.io/Sapiens/docs/graphify/graph.html)** ([`graph.html`](docs/graphify/graph.html), 300 nodes, 777 edges, 16 clusters). The investigation pipeline is highlighted in red: click a step under "Follow the investigation" to fly to it and spotlight its neighbours. The file works offline too: download it and open it in a browser.
- [`GRAPH_REPORT.md`](docs/graphify/GRAPH_REPORT.md): most connected functions, clusters and cross-file links.
- [`graph.json`](docs/graphify/graph.json): the raw graph, the same format Culprit reads to locate bugs.

## Track requirements

| Requirement | How Culprit meets it |
| --- | --- |
| One clearly defined task | Bug report in → guilty commit + verified fix out |
| Local inference only | Ollama on the laptop; no hosted model APIs anywhere |
| Open-source / open-weight model | qwen2.5-coder:3b (also works with Gemma, Llama, Mistral and other Ollama models) |
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

The offline suite (`tests/test_offline_pipeline.py`) runs the full pipeline on all 7 planted bugs with a scripted stand-in for the model, testing every non-AI part: worktrees, pytest checks, graph-guided and full bisect, auto good-commit search, retry on a broken test, Bandit, fix verification and regression tests. `tests/test_llm_client.py` tests the Ollama client against a local server that speaks Ollama's API. Real runs always use a local model through Ollama.

## Project layout

```
culprit/
  cli.py         command line + `culprit doctor`
  pipeline.py    locate -> reproduce -> bisect -> explain -> fix -> report
  llm.py         Ollama client: model auto-pick, temperature 0, seed, JSON schema output, retries, tokens/sec
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
