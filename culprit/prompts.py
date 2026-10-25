"""Prompts, kept short so a small local model stays fast and focused."""

KEYWORDS_SYSTEM = """You help locate a bug in a Python codebase.
Return JSON with "keywords": 3 to 6 short lowercase words likely to appear in the names
of the functions involved (e.g. "email", "coupon", "paginate", "login", "tax").
Use single words, no sentences."""

REPRO_SYSTEM = """You write ONE pytest test that reproduces a reported bug.
Rules:
- Name the test function test_culprit_repro.
- The test must FAIL on the current buggy code and PASS once the bug is fixed.
- Assert the CORRECT behaviour described in the bug report.
- Import from the project exactly as shown in the "How to import" lines.
- Use only the standard library and pytest. No network, no files, no randomness.
- If the bug is about a module-level setting read at import time, use
  monkeypatch.setenv(...) and importlib.reload(module) before checking it.
- Reply with only one ```python code block."""

REPRO_USER = """Bug report:
{report}

Relevant code (current version):
{code}

How to import:
{imports}
{example}
Write the test."""

EXPLAIN_SYSTEM = """You explain which commit introduced a bug, for a developer.
Return JSON with:
- "summary": one sentence, what the commit changed.
- "root_cause": one or two sentences, why that change causes the reported bug.
- "risk": "low", "medium" or "high" (how much other code is affected).
Be specific and short. Plain English."""

EXPLAIN_USER = """Bug report: {report}

Culprit commit {sha} by {author}: "{message}"

Diff of the culprit commit:
{diff}

Code that calls the changed code (blast radius):
{blast}"""

FIX_SYSTEM = """You fix a regression in Python code.
Rules:
- Return the corrected version of ONLY the code unit you are given, complete, with the same
  name and signature (for a function: the whole def; for a statement: the statement).
- Make the smallest change that fixes the bug. The diff of the commit that introduced the
  bug shows what used to work.
- Keep any later unrelated changes.
- Reply with only one ```python code block."""

FIX_USER = """Bug report: {report}

The bug was introduced by commit {sha} ("{message}"). Its diff:
{diff}

Why it broke: {root_cause}

Current code of {qualname} in {file}:
```python
{code}
```
{extra}
Return the fixed {kind}."""
