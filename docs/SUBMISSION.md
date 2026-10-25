# Submission kit (Hacktoberfest Hack Day Jaipur)

Tracks: **Best Open-Source AI Project** and **Best Local Agentic Tool / Edge AI**. Submissions close 5:00 PM IST.

## Run order on the demo laptop

```bash
ollama list                         # any chat model works; we use qwen2.5-coder:3b
pip install -e . && pip install graphifyy
culprit doctor                      # copy model name, parameters, quantization, tokens/sec
python demo/make_demo_repo.py demo-shop
cd demo-shop && culprit "Coupon code SAVE10 stops working when the customer types it in lowercase (save10)"
cd .. && python bench/run_bench.py  # 7 bugs x 3 runs -> bench/RESULTS.md
```

Then paste `bench/RESULTS.md` and the `culprit doctor` numbers into the README sections marked TEAM, commit, push.

If the model struggles on a bug, try a more specific report (name the function or give an input and expected output), or `--ctx 8192` if RAM allows. Record what you changed; never edit the results by hand.

## Form fields

**Project name:** Culprit

**Description:**
Culprit is an offline agent that finds the exact git commit that introduced a bug or a security hole, explains why, and proves a fix. You describe the bug in plain words. A local open-weight model (qwen2.5-coder:3b via Ollama; any Ollama chat model works) proposes, and real tools verify every step: Graphify's code map locates the relevant functions, the model writes a reproduction test that must fail on the buggy code and pass on an older commit, `git bisect` pins down the culprit exactly (graph-guided, with a flaky-test guard), the model explains the diff and its blast radius, and a fix is only accepted when the test passes, the project's suite has no new failures and, in security mode, the Bandit finding is gone. The fix and a regression test land on a new branch; nothing is merged and nothing leaves the laptop. It also ships as an Agent Skill (SKILL.md) so coding agents can use it. Benchmark on a 30-commit demo repo with 7 planted bugs (5 regressions, 2 security), 3 runs each: <paste summary line from bench/RESULTS.md>.

**Technologies:** Python, Ollama, qwen2.5-coder:3b (open weights), Graphify, git bisect, pytest, Bandit, pydantic, Rich

**Source code:** https://github.com/Chaturvediharsh123/Sapiens (MIT)

**Live demo:** screen recording of one full run + the benchmark (see below)

**Prize categories:** Best Open-Source AI Project, Best Local Agentic Tool / Edge AI

## Demo video (about 2 minutes)

1. Turn Wi-Fi off on camera.
2. `cd demo-shop && culprit "Order list pagination is broken: page 2 repeats the last item of page 1"`
3. Let it run through all 5 steps; pause on the culprit line and the verified fix.
4. Security: `culprit "Login succeeds with a wrong password that contains a quote, like x' OR '1'='1" --security`
5. Show `culprit-out/<sha>/report.md` and `git diff HEAD culprit/fix-<sha>`.
6. Show the benchmark table (`bench/RESULTS.md`).

## 2-minute pitch

1. **Problem (20 s):** "It worked last week" costs developers hours. Security holes slip in through ordinary commits. Private code can't go to hosted AI.
2. **Demo (60 s):** bug report in, Graphify locates, test fails, bisect finds the commit, fix goes green. Then security mode on the login hole. Wi-Fi off.
3. **Numbers (20 s):** culprit accuracy across 21 runs, same answer every run, tokens/sec, 8 GB laptop.
4. **Why it matters (20 s):** the model proposes, tools verify, so a small local model gives trustworthy answers. Open source, CLI + agent skill.

## Likely judge questions

- **"Isn't this a repo chatbot?"** A chatbot tells you what code says. Culprit tells you which commit broke it and proves it with a failing test, then proves the fix.
- **"Isn't this just git bisect?"** Bisect needs a test that detects the bug; writing it is the slow part. Culprit writes and validates that test from a plain-English report, then explains and fixes.
- **"How do you know the model isn't wrong?"** It can be wrong; it's never trusted. A test is only accepted if it fails at the bad commit and passes at a good one; the culprit is re-checked at its parent; a fix needs green tests and a cleared Bandit finding.
- **"Why is Graphify needed?"** A small model can't read a whole repo. The graph picks the 3-5 functions that matter, narrows bisect to commits that touched them, and gives the blast radius.
