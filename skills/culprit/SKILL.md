---
name: culprit
description: Find which git commit introduced a bug or security hole in a Python repo, explain why, and produce a verified fix on a new branch. Use when the user reports a regression ("it worked before", "broke after an update", "since last week"), asks which commit broke something, or reports a security issue such as SQL injection or a hardcoded secret.
---

# Culprit

Culprit runs fully offline with a local Gemma model (Ollama). It writes a test that
reproduces the bug, runs `git bisect` to find the exact commit, explains it, and commits a
verified fix plus a regression test on a branch named `culprit/fix-<sha>`. It never
merges and never changes the user's checkout.

## When to use
- A Python repo with git history and pytest, and a bug that used to work.
- A security problem in the user's own code (add `--security`).

## Steps
1. Check the tool is ready: `culprit doctor`. If Ollama is not running, ask the user to
   start it (`ollama serve`) rather than switching to a hosted model.
2. Run Culprit from the repo root with the user's own words as the report:
   `culprit "<bug report>"`
   - Add `--good <sha or tag>` if the user knows when it last worked.
   - Add `--security` for security issues.
   - Add `--no-fix` if the user only wants to know which commit caused it.
3. Read `culprit-out/<sha>/report.md` and tell the user:
   - the culprit commit (sha, author, message) and why it broke,
   - the blast radius (other code that calls the changed code),
   - the fix branch name and that the reproduction and regression tests pass.
4. Do not merge or push the fix branch. Let the user review it
   (`git diff HEAD culprit/fix-<sha>`).

## If it fails
- "could not write a valid reproduction test": ask the user for a more specific report
  (inputs, expected vs actual output, function or feature name) and run again.
- "bisect could not pin down a single commit": the bug may predate the good commit or
  come from several commits; ask for an older `--good`.

## Requirements
Ollama with a Gemma 4 model, Python 3.10+, git, pytest. Optional: Graphify
(`uv tool install graphifyy`) for the code map, Bandit for `--security`.
