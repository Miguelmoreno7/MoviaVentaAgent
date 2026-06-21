# MOVIA Requirement Semantics V3.1 Execution Tracker

Last updated: 2026-06-11

Current status: Phase 4 complete; stop before Phase 5.

## Current Decisions

* `MOVIA_3_1.md` is the master specification for this iteration.
* Phase 1 updates only the analyzer-layer semantics and compatibility bridge.
* Default requirement-profile persistence for later phases is `movia_lead_profiles.profile_data.requirement_profile`.
* Later live smoke and full replay phases use the currently configured DB by default, with evaluation isolation provided by `channel="evaluation"` and run-scoped lead IDs.
* Phase 4 comparisons are pinned to the current Atomic, Coherent, and Analyzer V3 targeted artifacts referenced in `MOVIA_3_1.md`.
* The current runtime still consumes legacy planner-compatible fields, so any temporary adapter must remain one-way from V3.1 semantics into compatibility state.

## Current Repository Conflicts And Risks

* The offline runtime still depends on `heuristic_analysis()` and `legacy_analysis_to_observation()` when OpenAI is disabled, so later phases should keep validating both the OpenAI and fallback paths.
* Downstream runtime still reads compatibility fields such as `requested_capabilities`, `requested_actions`, `action_requirement`, and `known_product_fit`; those are now derived one-way from V3.1 semantics but are not yet removed.
* `confirmed_product` is still relatively thin and currently depends on explicit persisted state or selected-product compatibility.
* Compatibility aliases (`action_requirement`, `known_product_fit`) are still present as derived fields while planner/memory/response complete the transition.

## Phase 1: Strict Semantic Analyzer Contract

Status: complete.

Depends on:

* Analyzer V3 runtime and targeted validation findings.
* Existing planner-compatible downstream runtime.

Expected files to change:

* `MOVIA_3_1.md`
* `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`
* `src/movia_sales_agent/analyzer/contract_v3.py`
* `src/movia_sales_agent/analyzer/normalizer.py`
* `src/movia_sales_agent/analyzer/shadow_parser.py`
* `src/movia_sales_agent/services/openai_service.py`
* `src/movia_sales_agent/agent/response.py`
* `tests/test_analyzer_contract_v3.py`
* `tests/test_analyzer_normalization_v3.py`
* `docs/architecture/ANALYZER_CONTRACT_V3_1.md`
* `docs/architecture/ANALYZER_CONTRACT_V3_1.json`
* `docs/implementation/PHASE_REQUIREMENT_V3_1_REPORT.md`

Acceptance target:

* Analyzer contract version is `3.1`.
* Analyzer emits `observed_business_problems`, explicit future-agent capabilities, explicit future-agent actions, and declared external-action count.
* Business problems do not become future-agent capabilities.
* Current salesperson questions do not leak into future-agent capability state.
* Invalid evidence is sanitized field-locally without full analyzer fallback when the rest of the payload is usable.
* Downstream runtime still compiles and runs through a one-way compatibility bridge only.

Completed work:

* Updated `MOVIA_3_1.md` with pinned baseline artifacts, persistence defaults, live DB defaults, and the one-way compatibility note.
* Bumped analyzer contract runtime to `3.1`.
* Added `observed_business_problems`, `requested_agent_capabilities`, `requested_agent_actions`, and `declared_external_action_count`.
* Updated sanitizer behavior to repair or drop invalid evidence locally.
* Updated shadow parser telemetry naming to compare observed problems, requested capabilities, and requested actions.
* Added a one-way compatibility bridge so legacy planner/runtime fields are derived from V3.1 semantics only.
* Generated `docs/architecture/ANALYZER_CONTRACT_V3_1.json` and added `docs/architecture/ANALYZER_CONTRACT_V3_1.md`.
* Ran offline Phase 1 tests successfully.

Unresolved issues:

* The planner and memory layers still consume compatibility aliases instead of native V3.1 requirement-profile state.
* Supplier/workflow pain without explicit future-agent wording now stays in discovery rather than auto-creating external-action requirements; later phases should decide whether product-fit inference belongs in a separate deterministic layer.

Exact next task:

* Start Phase 2 only: persist the requirement profile under `movia_lead_profiles.profile_data.requirement_profile`, adapt planner-facing state to consume it deterministically, and keep the one-way compatibility bridge intact until Phase 2 is complete.

## Phase 2: Requirement Profile, Product Fit, And Planner Integration

Status: complete.

Expected files changed:

* `src/movia_sales_agent/agent/requirements.py`
* `src/movia_sales_agent/agent/memory.py`
* `src/movia_sales_agent/agent/planners.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/agent/response.py`
* `src/movia_sales_agent/services/openai_service.py`
* `tests/test_requirement_profile_v3.py`
* `tests/test_memory_v3.py`
* `tests/test_agent_policy.py`
* `tests/test_response_context.py`
* `docs/architecture/REQUIREMENT_PROFILE_V3_1.md`
* `docs/implementation/PHASE_REQUIREMENT_V3_2_REPORT.md`

Completed work:

* Added a deterministic requirement-profile service and persisted it under `profile_data.requirement_profile`.
* Added current-turn requirement delta calculation with `no_update`, `merge`, and explicit-removal/correction scaffolding.
* Derived `requirement_class`, compatibility `action_requirement`, deterministic product fit, and scope flags from the persisted profile.
* Integrated planner state and direct-close gating with requirement-profile outputs.
* Updated response-package context with compact requirement summary and scope metadata.
* Tightened the offline heuristic fallback so future-agent requirements require future-agent wording.
* Added Phase 2 regression tests and passed them offline.

Tests run:

* `PYTHONPATH=src .venv/bin/pytest tests/test_requirement_profile_v3.py tests/test_memory_v3.py tests/test_agent_policy.py tests/test_response_context.py -q`
* Result: `44 passed`

Exact next task:

* Start Phase 3 only: align offline regression and evaluator compatibility with the new persisted requirement profile, then run only the approved Phase 3 offline/smoke checks.

## Phase 3: Offline Regression, Evaluator Alignment, And Live Smoke

Status: complete.

Expected files changed:

* `src/movia_sales_agent/evaluation/scoring.py`
* `src/movia_sales_agent/analyzer/contract_v3.py`
* `docs/architecture/ANALYZER_CONTRACT_V3_1.json`
* `tests/test_semantic_requirement_metrics_v3.py`
* `tests/test_analyzer_normalization_v3.py`
* `tests/test_api.py`
* `tests/test_objection_flow.py`
* `docs/implementation/PHASE_REQUIREMENT_V3_3_REPORT.md`
* `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`

Completed work:

* Added deterministic evaluator metrics for problem/capability leakage, current-question leakage, requirement-profile reset, premature recommendation, sales-capability misrouting, external-action scope misses, wrong-product direct close, and unsupported standard-scope claims.
* Updated stale tests to match the Phase 2 direct-close gate and custom-review behavior for external-system actions.
* Added Phase 3 semantic evaluator unit coverage.
* Updated the generated analyzer contract artifact to include all public V3.1 semantic fields, including `declared_external_action_count`.
* Verified the public analyzer contract JSON does not expose legacy `requested_capabilities` or `requested_actions`.
* Ran the complete offline repository suite successfully.
* Ran exactly one live smoke turn with `channel="evaluation"` and a run-scoped lead ID.

Tests and checks run:

* `PYTHONPATH=src .venv/bin/pytest tests/test_semantic_requirement_metrics_v3.py -q`
* `PYTHONPATH=src .venv/bin/pytest tests/test_analyzer_contract_v3.py::test_contract_json_matches_runtime_source tests/test_semantic_requirement_metrics_v3.py -q`
* `PYTHONPATH=src .venv/bin/pytest tests/test_analyzer_normalization_v3.py::test_graph_exposes_normalized_turn_and_uses_it_for_memory tests/test_api.py::test_health_and_chat_endpoint tests/test_objection_flow.py::test_explicit_start_after_semantic_resolution_can_direct_close -q`
* `PYTHONPATH=src .venv/bin/pytest -q`
* Static contract check for required V3.1 semantic fields and legacy public aliases.

Final offline result:

* `161 passed`
* `1 warning` from `urllib3` / LibreSSL in the local environment

Live smoke:

* Artifact: `artifacts/evaluations/requirement-v3-phase3-smoke/phase3-smoke-20260611T055027Z-f7310d/smoke.json`
* Result: passed
* Response source: `openai`
* Fallback call count: `0`
* Total tokens: `4,233`
* Action: `recommend_solution`
* Recommended product: `movia_captura`

Unresolved issues:

* Compatibility aliases are still present internally for planner/response payloads, but remain derived from V3.1 semantics.
* The Phase 3 metrics are deterministic checks over emitted runtime fields and may need reporting calibration after Phase 4 artifacts are reviewed by the user.
* `confirmed_product` remains a thin state and may need stronger confirmation logic in a future development iteration.

Exact next task:

* Start Phase 4 only: freeze current behavior/configuration, then run exactly one full Atomic live replay and exactly one full Coherent live replay. Do not modify runtime code, evaluator code, prompts, or gold expectations after full replay begins.

## Phase 4: One-Time Full Live Atomic And Coherent Replay

Status: complete.

Completed work:

* Validated the Atomic and Coherent datasets structurally before replay.
* Recorded freeze metadata before running full live suites.
* Ran exactly one full Atomic live replay.
* Ran exactly one full Coherent live replay.
* Skipped RAGAS and DeepEval by configuration, matching Phase 4 restrictions.
* Preserved full run artifacts and generated a compact comparison artifact.
* Created `docs/implementation/PHASE_REQUIREMENT_V3_4_REPORT.md`.
* Did not modify runtime code, evaluator code, prompts, gold expectations, or migrations after the full replay began.

Atomic live replay:

* Run ID: `movia-eval-20260611T055355Z-a0d168`
* Artifact: `artifacts/evaluations/requirement-v3-phase4-atomic-live/movia-eval-20260611T055355Z-a0d168/run.json`
* Result: failed
* Overall score: `0.9548`
* Hard failures: `1`
* Fallback count: `0`
* Total tokens: `282,865`

Coherent live replay:

* Run ID: `movia-eval-20260611T060949Z-4fcc86`
* Artifact: `artifacts/evaluations/requirement-v3-phase4-coherent-live/movia-eval-20260611T060949Z-4fcc86/run.json`
* Result: failed
* Overall score: `0.8851`
* Hard failures: `1`
* Fallback count: `0`
* Total tokens: `263,791`

Comparison:

* Artifact: `artifacts/evaluations/requirement-v3-phase4-comparison.json`
* Atomic baseline delta: `+0.0415` overall, `+1` hard failure.
* Coherent baseline delta: `+0.0584` overall, `-1` hard failure.

Unresolved issues:

* Atomic emitted `cross_scenario_memory_leak` on `MOVIA-VAL-003` turn `2`.
* Coherent emitted `incorrect_deposit_percentage` on `MOVIA-COH-003` turn `6`.
* Requirement-profile reset metrics remain visible in both suites.
* Coherent has two wrong-product direct-close semantic metric failures.
* Source/RAG metrics degraded against baseline and run artifacts emitted zero retrieved sources.

Exact next task:

* Start Phase 5 only if approved: analyze preserved Phase 4 artifacts, classify true defects versus evaluator calibration issues, and design bounded fixes without automatically rerunning full live suites.
