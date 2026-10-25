"""A scripted stand-in for the model, used ONLY by the offline tests.

It lets the test suite exercise every non-AI part of Culprit (graph, worktrees, pytest
checks, git bisect, Bandit, fix verification, regression test, report) without Ollama.
Real runs always use a local Gemma model through Ollama (culprit/llm.py).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from culprit.codeunits import find_unit, units_in_source
from culprit.explain import Explanation
from culprit.llm import LLMStats
from culprit.locate import Keywords

REF = Path(__file__).parent / "reference_tests"

KEYWORDS = {
    "email_plus": ["email", "validate", "signup"],
    "discount_twice": ["discount", "checkout", "coupon"],
    "pagination_repeat": ["paginate", "page", "orders"],
    "tax_rounding": ["tax", "invoice", "lines"],
    "coupon_case": ["coupon", "code"],
    "sql_login_bypass": ["login", "password", "query"],
    "hardcoded_token": ["token", "payment", "pricing"],
}

BROKEN_TEST = "from shop.does_not_exist import nothing\n\n\ndef test_culprit_repro():\n    assert nothing()\n"


class ScriptedLLM:
    model = "scripted-stand-in"

    def __init__(self, repo: Path, bug_id: str, culprit_sha: str, broken_first: bool = False):
        self.repo, self.bug_id, self.culprit = repo, bug_id, culprit_sha
        self.broken_first = broken_first
        self.stats = LLMStats()
        self._repro_calls = 0

    def json(self, system, user, schema, purpose="", retries=3):
        self.stats.calls += 1
        if schema is Keywords:
            return Keywords(keywords=KEYWORDS[self.bug_id])
        if schema is Explanation:
            return Explanation(summary="scripted summary", root_cause="scripted root cause", risk="medium")
        raise AssertionError(f"unexpected schema {schema}")

    def code(self, system, user, purpose="", history=None):
        self.stats.calls += 1
        if purpose == "repro":
            self._repro_calls += 1
            if self.broken_first and self._repro_calls == 1:
                return BROKEN_TEST                  # exercises the retry-with-feedback path
            return (REF / f"{self.bug_id}.py").read_text()
        if purpose == "fix":
            m = re.search(r"Current code of (\S+) in (\S+):", user)
            if not m:                               # follow-up attempt: reuse the first prompt
                m = re.search(r"Current code of (\S+) in (\S+):", history[0]["content"])
            qual, file = m.group(1), m.group(2)
            parent = subprocess.run(["git", "show", f"{self.culprit}^:{file}"], cwd=self.repo,
                                    capture_output=True, text=True, check=True).stdout
            units = units_in_source(parent, file)
            unit = find_unit(units, qual) or find_unit(units, f"<module>:{qual}")
            return unit.source + "\n"
        raise AssertionError(f"unexpected purpose {purpose}")
