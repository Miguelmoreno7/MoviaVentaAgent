# MovIA Sales Agent V2 Operational Plan

Last updated: 2026-06-05  
Master reference: `PLANV2.md`  
Current phase: Final scripted replay complete; follow-up tuning or DB-mode rerun decision needed.

## Decisions

- `PLANV2.md` is the durable master specification for all V2 phases.
- Phase work uses targeted unit/regression tests only; the full 60-turn replay is deferred until all implementation phases are complete.
- V2 does not preserve the old public/debug schema as a compatibility constraint during implementation.
- The gold validation dataset was aligned during Phase 5 using V2 runtime traces; do not modify it again until Phase 6 or final replay explicitly requires it.
- No production migrations, deployments, or production data changes are allowed.
- Phase 2 emits V2 `target_stage` on the planner trace.
- Phase 3 resolves planner `target_stage` through `SalesStageTransitionService` and persists V2 stage state.
- Phase 4 persists active objection state and advances objection-flow steps across turns.
- Phase 5 makes evaluator/gold validation strict for V2 contract values and supported source labels.
- Phase 6 compacts response-generation context and logs response-package token estimates.
- `direct_close` is gated by deterministic code through `can_direct_close(state)`.
- Final scripted replay was run with live OpenAI and `MOVIA_DISABLE_DATABASE=true` after a one-turn DB-mode smoke exposed missing remote V2 migration columns. Production migrations were not applied.
- RAGAS and DeepEval judges were skipped in the final replay because judge credentials were not configured.

## Current Repository Conflicts

- The Phase 3 V2 stage migration exists locally but has not been applied to production.
- The Phase 4 active-objection migration exists locally but has not been applied to production.
- The remote DB still lacks V2 stage columns such as `stage_updated_at`, so DB-mode replay is blocked until the local Phase 3 and Phase 4 migrations are applied to a safe evaluation/staging database.
- V2 final replay did not produce hard failures, free-form taxonomy values, unreachable gold actions, premature direct closes, or repeated first objection steps.
- V2 final replay failed the run-level policy because `objection_handling` and `sales_progression` remain below target.

## Phase 1: Align And Close The Taxonomy

Status: completed.

Dependencies:

- Audit docs in `docs/audit/`.
- Master spec in `PLANV2.md`.

Files changed:

- `src/movia_sales_agent/contracts/commercial.py`
- `src/movia_sales_agent/contracts/__init__.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/openai_service.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/evaluation/dataset.py`
- `src/movia_sales_agent/evaluation/models.py`
- `tests/test_commercial_contract.py`
- `tests/test_agent_policy.py`
- `tests/test_evaluation.py`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- `docs/implementation/PHASE_1_REPORT.md`
- `PLAN.md`

Migrations:

- None.

Acceptance criteria:

- Commercial labels are enum-constrained in runtime models.
- OpenAI structured-output schema uses Contract V2 enums.
- Offline heuristic emits canonical V2 labels.
- Unknown/free-form commercial labels are rejected by Pydantic.
- Runtime and evaluator can load the same Contract V2.
- Contract JSON matches the Python source of truth.
- Gold dataset unchanged.
- Full evaluation not run.

Tests:

- `.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_evaluation.py`
- Result: 23 passed.

## Phase 2: Complete The Sales Policy Planner

Status: completed.

Depends on:

- Phase 1 Contract V2 enums.

Expected files to change:

- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/contracts/commercial.py`
- `src/movia_sales_agent/services/openai_service.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/agent/graph.py`
- `tests/test_agent_policy.py`
- `tests/test_commercial_contract.py`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- `docs/implementation/PHASE_2_REPORT.md`

Migrations:

- None.

Acceptance criteria:

- All 13 macroactions are reachable through valid input state tests: completed.
- Direct close requires `explicit_start_intent=true` and no unresolved hard objection: completed.
- Known premature direct-close examples no longer route to `direct_close`: completed for sarcastic opener, pain description, price question, free-trial objection, supplier workflow, and ManyChat comparison.
- Exact questions can use `answer_and_advance`: completed.
- Skeptical-but-not-blocking statements can route to `persuade_value`: completed.
- Captura/Hibrido narrowing is deterministic: completed through `action_requirement` and product-fit facts.
- Planner output includes stable reason codes: completed.

Tests:

- `.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_evaluation.py tests/test_api.py`
- Result: 34 passed.
- `.venv/bin/pytest tests`
- Result: 41 passed.

Exact next task:

- Begin Phase 3 by designing `SalesStageTransitionService`, local-only stage-machine migration fields, and tests proving stage persists independently from the current macroaction.

## Phase 3: Persistent Sales-Stage Machine

Status: completed.

Depends on:

- Phase 2 planner outputs and reason codes.

Expected files to change:

- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/db/repository.py`
- `src/movia_sales_agent/agent/stages.py`
- `src/movia_sales_agent/models/schemas.py`
- `supabase/migrations/202606040001_stage_machine_v2.sql`
- `tests/test_stage_machine.py`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/implementation/PHASE_3_REPORT.md`

Migrations:

- Local-only migration added for V2 stage constraint plus `previous_stage`, `stage_before_objection`, `stage_entered_at`, `stage_updated_at`, `stage_reason_code`, and `stage_reason`.
- Not applied to production.

Acceptance criteria:

- `current_stage` is no longer derived only from current macroaction: completed.
- Stage persists between turns in local/offline repository fallback and DB-mode repository persistence is implemented: completed.
- Objection handling preserves previous stage and `stage_before_objection`: completed.
- Invalid transitions are explicitly normalized with `invalid_transition`: completed.
- Evaluator reads the real stage from `ChatResponse.lead_state`: completed.

Tests:

- `.venv/bin/pytest tests/test_stage_machine.py tests/test_agent_policy.py tests/test_api.py tests/test_evaluation.py`
- Result: 35 passed.
- `.venv/bin/pytest tests`
- Result: 46 passed.

Exact next task:

- Begin Phase 4 by persisting active objection state and advancing objection-flow steps without resetting to the first step.

## Phase 4: Persistent Objection Flow

Status: completed.

Depends on:

- Phase 3 persistent stage state.

Expected files to change:

- `src/movia_sales_agent/agent/objections.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/agent/stages.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/db/repository.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/openai_service.py`
- `supabase/migrations/202606040002_active_objection_v2.sql`
- `tests/test_objection_flow.py`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/implementation/PHASE_4_REPORT.md`

Migrations:

- Local-only migration added for `active_objection jsonb not null default '{}'::jsonb`, JSON object check, and partial GIN index.
- Not applied to production.

Acceptance criteria:

- Active objections persist across turns: completed.
- The same objection does not reset to the first step every turn: completed.
- Objection flow progresses through canonical steps: completed.
- Resolved objections return to an appropriate previous stage: completed.
- No premature direct close during unresolved hard objections: completed.

Tests:

- `.venv/bin/pytest tests/test_objection_flow.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_api.py tests/test_evaluation.py`
- Result: 47 passed.
- `.venv/bin/pytest tests`
- Result: 58 passed.

Exact next task:

- Begin Phase 5 by aligning evaluator/gold expected values to Contract V2 runtime traces and adding contract-version compatibility checks.

## Phase 5: Evaluator Alignment

Status: completed.

Depends on:

- Runtime Contract V2, planner, stage machine, and objection flow.

Files changed:

- `src/movia_sales_agent/evaluation/models.py`
- `src/movia_sales_agent/evaluation/dataset.py`
- `src/movia_sales_agent/evaluation/capabilities.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `movia_validation_package/movia_difficult_lead_validation_scenarios.json`
- `tests/test_evaluation.py`
- `docs/implementation/PHASE_5_REPORT.md`

Migrations:

- None expected.

Acceptance criteria:

- Runtime and evaluator share `commercial_contract_version="2.0"`: completed.
- Dataset expected values validate against Contract V2: completed.
- Gold dataset contains no unreachable values for expected trace/source fields: completed.
- Unsupported sources are not silently expected by the gold dataset: completed.
- Reporting separates hard failures, rule failures, soft trace mismatches, partial source matches, judge failures, skipped metrics, and not-applicable metrics: completed.
- Hard-failure rules are preserved: completed.

Tests:

- `.venv/bin/pytest tests/test_evaluation.py tests/test_commercial_contract.py tests/test_agent_policy.py`
- Result: 34 passed.
- `.venv/bin/movia-eval validate-dataset`
- Result: valid, 5 scenarios, 60 turns, no unsupported expected fields or sources.
- `.venv/bin/pytest tests`
- Result: 60 passed.

Exact next task:

- Begin Phase 6 by measuring current token/context usage on targeted smoke turns, then reduce response context/package size without changing commercial behavior.

## Phase 6: Token Cost Reduction

Status: completed.

Depends on:

- Stable V2 runtime behavior from Phases 1-5.

Files changed:

- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `tests/test_response_context.py`
- `docs/implementation/TOKEN_COST_V2_REPORT.md`
- `docs/implementation/PHASE_6_REPORT.md`
- `PLAN.md`

Migrations:

- None expected.

Acceptance criteria:

- Average total agent tokens per turn target <= 3,500: completed in final replay at 2,712.8.
- Average response input tokens target <= 2,500: completed in final replay at 1,253.1.
- No increase in hard failures: completed in final replay with 0 hard failures.
- No regression in commercial accuracy or policy compliance: completed in final replay with both at 1.0000.
- Token savings are measured, not claimed: completed through same-smoke before/after estimates and package section logging.

Tests:

- `.venv/bin/pytest tests/test_response_context.py tests/test_agent_policy.py tests/test_api.py tests/test_evaluation.py tests/test_objection_flow.py tests/test_stage_machine.py`
- Result: 53 passed.
- `.venv/bin/pytest tests`
- Result: 64 passed.
- `.venv/bin/movia-eval validate-dataset`
- Result: valid, 5 scenarios, 60 turns, no unsupported expected fields or sources.

Exact next task:

- Decide whether the next iteration should first tune objection handling/sales progression, or apply the Phase 3 and Phase 4 migrations to a non-production evaluation database and rerun in DB mode.

## Final Replay

Status: completed.

Depends on:

- Completion of all six phases.

Deliverables:

- V1 baseline preserved: `artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`.
- V2 DB-mode smoke artifact: `artifacts/evaluations/movia-eval-20260605T060323Z-3ec591/run.json`.
- V2 final scripted replay artifact: `artifacts/evaluations/movia-eval-20260605T060417Z-bef7a2/run.json`.
- V2 final replay summary: `artifacts/evaluations/movia-eval-20260605T060417Z-bef7a2/summary.md`.
- V1/V2 comparison report: `docs/evaluation/V1_VS_V2_COMPARISON.md`.

Acceptance targets:

- `hard_failures = 0`: passed with 0.
- `commercial_accuracy >= 0.95`: passed with 1.0000.
- `policy_compliance >= 0.95`: passed with 1.0000.
- `scope_control >= 0.95`: passed with 1.0000.
- `memory_consistency >= 0.95`: passed with 1.0000.
- `source_selection >= 0.85`: passed with 0.8858.
- `objection_handling >= 0.75`: failed with 0.5000.
- `sales_progression >= 0.75`: failed with 0.4125.
- `overall_score >= 0.85`: passed with 0.8505.
- `free_form_taxonomy_values = 0`: passed with 0.
- `unreachable_gold_actions = 0`: passed with 0.
- `premature_direct_close_cases = 0`: passed with 0.
- `repeated_first_response_for_same_objection = 0`: passed with 0.

Replay commands and results:

- `.venv/bin/movia-eval validate-dataset`: valid, 5 scenarios, 60 turns, contract `2.0`, no unsupported expected fields or sources.
- `.venv/bin/movia-eval run --scenario MOVIA-VAL-001 --max-turns 1 --skip-ragas --skip-deepeval --no-fail-exit`: DB-mode smoke failed because remote `movia_lead_profiles` lacks `stage_updated_at`.
- `MOVIA_DISABLE_DATABASE=true .venv/bin/movia-eval run --scenario all --skip-ragas --skip-deepeval --no-fail-exit`: completed 5 scenarios and 60 turns with live OpenAI, no production DB writes, overall score 0.8505, 0 hard failures, run-level status failed because objection handling and sales progression were below target.

Exact next task:

- Tune planner/objection-flow progression so valid exact questions and resolved objections can leave `objection_handling` sooner, then rerun the scripted replay. Separately, apply V2 migrations to a non-production evaluation database before attempting a DB-mode replay.
