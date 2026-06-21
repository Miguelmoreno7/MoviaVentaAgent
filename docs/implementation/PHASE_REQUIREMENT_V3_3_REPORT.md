# Phase Requirement Semantics V3.3 Report

Date: `2026-06-11`

Status: Phase 3 complete.

## Scope Completed

Phase 3 only:

- aligned deterministic evaluator scoring with the persisted V3.1 requirement profile;
- added semantic requirement metrics for leakage, reset, routing, scope, and close-quality failures;
- updated stale tests to reflect the Phase 2 direct-close gate and custom-review semantics;
- tightened the analyzer contract JSON artifact so it documents all V3.1 semantic fields;
- ran the complete offline repository test suite;
- ran exactly one live smoke turn with `channel="evaluation"` and a run-scoped lead ID.

No Atomic, Coherent, Adaptive Hybrid, targeted live suite, full replay, RAGAS, or DeepEval run was executed.

## Files Changed

- `src/movia_sales_agent/evaluation/scoring.py`
- `src/movia_sales_agent/analyzer/contract_v3.py`
- `docs/architecture/ANALYZER_CONTRACT_V3_1.json`
- `tests/test_semantic_requirement_metrics_v3.py`
- `tests/test_analyzer_normalization_v3.py`
- `tests/test_api.py`
- `tests/test_objection_flow.py`
- `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`

## Evaluator Adjustments

Added deterministic metrics:

- `semantic.problem_capability_leakage`
- `semantic.current_question_future_capability_leakage`
- `semantic.requirement_profile_reset`
- `semantic.premature_product_recommendation`
- `semantic.sales_capability_misrouted`
- `semantic.external_action_scope_miss`
- `semantic.wrong_product_direct_close`
- `semantic.unsupported_standard_scope_claim`

The metrics read only emitted runtime data: normalized turn fields, selected action, response text, lead-state `profile_data.requirement_profile`, scope flags, and turn history. No gold dataset fields, user messages, scripted turns, ideal responses, policies, or thresholds were changed.

## Static Checks

- Contract JSON includes `observed_business_problems`, `requested_agent_capabilities`, `requested_agent_actions`, and `declared_external_action_count`.
- Contract JSON excludes legacy public names `requested_capabilities` and `requested_actions`.
- Legacy `requested_capabilities` / `requested_actions` remain only as derived compatibility aliases in runtime context and parser telemetry.
- Direct-close tests now require selected/confirmed compatible product context.
- External-system write requirements now score as custom review rather than default Híbrido.

## Tests Run

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_semantic_requirement_metrics_v3.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_analyzer_contract_v3.py::test_contract_json_matches_runtime_source tests/test_semantic_requirement_metrics_v3.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_analyzer_normalization_v3.py::test_graph_exposes_normalized_turn_and_uses_it_for_memory tests/test_api.py::test_health_and_chat_endpoint tests/test_objection_flow.py::test_explicit_start_after_semantic_resolution_can_direct_close -q
PYTHONPATH=src .venv/bin/pytest -q
```

Final result:

- `161 passed`
- `1 warning` from `urllib3` / LibreSSL in the local environment

## Live Smoke

Artifact:

```text
artifacts/evaluations/requirement-v3-phase3-smoke/phase3-smoke-20260611T055027Z-f7310d/smoke.json
```

Result:

- passed: `true`
- action: `recommend_solution`
- analyzer contract: `3.1`
- response source: `openai`
- usage providers: `openai`, `none` for no-RAG embedding call
- fallback call count: `0`
- total tokens: `4,233`
- requirement class: `informational_only`
- recommended product: `movia_captura`

## Unresolved Issues

- Compatibility aliases still exist internally for downstream planner/response paths, but remain derived from V3.1 semantics.
- The semantic metrics are deterministic heuristics over emitted runtime state; Phase 4 full replay will show whether any metric needs reporting calibration, but code must not be changed automatically after the frozen full replay begins.
- `confirmed_product` remains thin and may need a stronger confirmation transition in a future development iteration.

## Exact Next Task

Phase 4 only:

- freeze current behavior and record revision/configuration;
- run exactly one full Atomic live replay and exactly one full Coherent live replay;
- do not modify code, evaluator logic, prompts, or gold expectations after either full replay starts;
- preserve artifacts and report findings.
