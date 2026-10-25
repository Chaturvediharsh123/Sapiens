"""End-to-end test of the Culprit harness on the demo repo, without a model.

Run: pytest -q tests/
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from culprit.pipeline import run  # noqa: E402
from culprit.ui import UI  # noqa: E402
from scripted_llm import ScriptedLLM  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    target = tmp_path_factory.mktemp("demo") / "demo-shop"
    subprocess.run([sys.executable, str(ROOT / "demo" / "make_demo_repo.py"), str(target)],
                   check=True, capture_output=True)
    bugs = {b["id"]: b for b in yaml.safe_load((ROOT / "bench" / "bugs.yaml").read_text())["bugs"]}
    return target, bugs


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.parametrize("bug_id", ["email_plus", "discount_twice", "pagination_repeat", "tax_rounding",
                                    "coupon_case", "sql_login_bypass", "hardcoded_token"])
@pytest.mark.parametrize("good_given", [True, False], ids=["good-given", "good-auto"])
def test_finds_and_fixes_every_planted_bug(demo, tmp_path, bug_id, good_given):
    repo, bugs = demo
    bug = bugs[bug_id]
    llm = ScriptedLLM(repo, bug_id, bug["culprit"])
    res = run(repo, bug["report"], llm, good=bug["good"] if good_given else None,
              security_mode=bug["mode"] == "security", out_dir=tmp_path / "out", ui=UI(quiet=True))
    assert res.status == "found", (res.status, res.error)
    assert res.culprit["sha"] == bug["culprit"]
    assert res.bisect_verified
    assert res.fix["ok"], res.fix
    assert res.fix["regression_test"] in git(repo, "show", "--name-only", "--format=", res.fix["branch"])
    if bug["mode"] == "security":
        assert res.fix["security_cleared"] is True
    assert (tmp_path / "out" / "report.md").exists()
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""   # user's checkout untouched


def test_auto_finds_good_commit_and_retries_broken_test(demo, tmp_path):
    repo, bugs = demo
    bug = bugs["coupon_case"]
    llm = ScriptedLLM(repo, "coupon_case", bug["culprit"], broken_first=True)
    res = run(repo, bug["report"], llm, good=None, do_fix=False, out_dir=tmp_path / "out", ui=UI(quiet=True))
    assert res.status == "found"
    assert res.good_auto
    assert res.repro_attempts == 2
    assert res.culprit["sha"] == bug["culprit"]


def test_graph_guided_bisect_uses_fewer_runs(demo, tmp_path):
    repo, bugs = demo
    bug = bugs["pagination_repeat"]
    guided = run(repo, bug["report"], ScriptedLLM(repo, bug["id"], bug["culprit"]), good=bug["good"],
                 do_fix=False, out_dir=tmp_path / "a", ui=UI(quiet=True))
    full = run(repo, bug["report"], ScriptedLLM(repo, bug["id"], bug["culprit"]), good=bug["good"],
               do_fix=False, guided=False, out_dir=tmp_path / "b", ui=UI(quiet=True))
    assert guided.culprit["sha"] == full.culprit["sha"] == bug["culprit"]
    assert guided.bisect_steps < full.bisect_steps
