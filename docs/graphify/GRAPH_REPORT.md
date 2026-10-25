# Graph Report - culprit  (2026-10-25)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 300 nodes · 777 edges · 16 communities (10 shown, 6 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 42 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f895b66e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- fix.py
- cli.py
- pipeline.py
- graph.py
- sandbox.py
- test_llm_client.py
- test_offline_pipeline.py
- make_demo_repo.py
- steps
- bugs
- shop_pricing
- culprit

## God Nodes (most connected - your core abstractions)
1. `run()` - 29 edges
2. `git()` - 24 edges
3. `UI` - 22 edges
4. `CodeUnit` - 20 edges
5. `make_fix()` - 18 edges
6. `units_in_source()` - 16 edges
7. `CodeGraph` - 15 edges
8. `OllamaLLM` - 14 edges
9. `changed_units()` - 13 edges
10. `explain()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_finds_and_fixes_every_planted_bug()` --uses--> `UI`  [INFERRED]
  tests/test_offline_pipeline.py → culprit/ui.py
- `ScriptedLLM` --uses--> `Keywords`  [INFERRED]
  tests/scripted_llm.py → culprit/locate.py
- `test_picks_smallest_gemma()` --calls--> `resolve_model()`  [EXTRACTED]
  tests/test_llm_client.py → culprit/llm.py
- `test_json_retries_until_valid_and_is_deterministic()` --calls--> `OllamaLLM`  [EXTRACTED]
  tests/test_llm_client.py → culprit/llm.py
- `test_thinking_text_is_removed()` --calls--> `OllamaLLM`  [EXTRACTED]
  tests/test_llm_client.py → culprit/llm.py

## Import Cycles
- None detected.

## Communities (16 total, 6 thin omitted)

### Community 0 - "fix.py"
Cohesion: 0.08
Nodes (28): CodeUnit, extract_replacement(), find_unit(), module_name(), replace_unit(), _stmt_name(), unit_at_line(), units_in_source() (+20 more)

### Community 1 - "cli.py"
Cohesion: 0.09
Nodes (11): main(), doctor(), main(), extract_code(), list_models(), LLMError, OllamaLLM, resolve_model() (+3 more)

### Community 2 - "pipeline.py"
Cohesion: 0.14
Nodes (24): bisect(), BisectResult, _run_bisect(), verify(), commit_count(), commit_info(), commits_between(), git() (+16 more)

### Community 3 - "graph.py"
Cohesion: 0.13
Nodes (12): build_ast_graph(), add(), build_graphify(), CodeGraph, graphify_available(), graphify_cmd(), _is_test_file(), load_graph() (+4 more)

### Community 4 - "sandbox.py"
Cohesion: 0.15
Nodes (10): main(), _classify(), _env(), run_suite(), run_test(), run_test_n(), _temp_file(), TestResult (+2 more)

### Community 5 - "test_llm_client.py"
Cohesion: 0.11
Nodes (9): _preference(), usable_models(), Keywords, Handler, host(), test_any_installed_chat_model_is_used_when_no_gemma4(), test_json_retries_until_valid_and_is_deterministic(), test_picks_smallest_gemma() (+1 more)

### Community 6 - "test_offline_pipeline.py"
Cohesion: 0.15
Nodes (8): Explanation, LLMStats, ScriptedLLM, demo(), git(), test_auto_finds_good_commit_and_retries_broken_test(), test_finds_and_fixes_every_planted_bug(), test_graph_guided_bisect_uses_fewer_runs()

### Community 7 - "make_demo_repo.py"
Cohesion: 0.26
Nodes (5): build(), edit(), git(), main(), write_bugs_yaml()

### Community 8 - "steps"
Cohesion: 0.18
Nodes (10): jobs, offline-tests, name, runs-on, steps, run, uses, with (+2 more)

### Community 9 - "bugs"
Cohesion: 0.25
Nodes (7): bugs, culprit, culprit_message, good, id, mode, report

## Knowledge Gaps
- **1 isolated node(s):** `culprit`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 99 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run()` connect `pipeline.py` to `fix.py`, `cli.py`, `graph.py`, `sandbox.py`, `test_offline_pipeline.py`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `CodeUnit` (e.g. with `changed_units()` and `ChangedUnit`) actually correct?**
  _`CodeUnit` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `culprit` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `fix.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08022598870056497 - nodes in this community are weakly interconnected._
- **Why does `UI` connect `cli.py` to `pipeline.py`, `test_offline_pipeline.py`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Should `cli.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08687943262411348 - nodes in this community are weakly interconnected._
- **Why does `CodeUnit` connect `fix.py` to `pipeline.py`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._