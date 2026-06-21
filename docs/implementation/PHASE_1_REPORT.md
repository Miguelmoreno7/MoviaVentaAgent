# Phase 1 Report: Align And Close The Taxonomy

Date: 2026-06-04  
Status: completed  
Scope: Phase 1 only

## Summary

Phase 1 introduced Commercial Contract V2 as the canonical runtime taxonomy and updated runtime schemas, analysis, planner references, fallback response references, and evaluator metadata/hooks to consume canonical values.

No gold dataset changes, migrations, production changes, deployments, or full evaluation replay were performed.

## Completed Work

- Added `src/movia_sales_agent/contracts/commercial.py` with Contract V2 enums and `commercial_contract_version = "2.0"`.
- Added checked-in architecture artifacts:
  - `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
  - `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- Replaced free-form `TurnAnalysis.intent` with `primary_intent` and `secondary_intents`.
- Replaced broad `wants_to_start` with strict `explicit_start_intent`.
- Added `skeptical_tone`, `objection_strength`, and confidence fields.
- Enum-constrained `SalesPlan.macro_action`, `micro_action`, `cta_type`, and `objection_flow_step`.
- Updated OpenAI structured-output schema to use Contract V2 enums.
- Updated offline heuristic analysis to emit canonical V2 values.
- Updated current planner and fallback response references from V1 topic/action strings to V2 values, only enough for Phase 1 compatibility.
- Added evaluator contract-version metadata and a contract-value helper without enforcing it against the current gold dataset.
- Added/updated Phase 1 tests.

## Tests Run

```bash
.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_evaluation.py
```

Result:

```text
23 passed, 1 warning
```

Warnings:

- urllib3/OpenSSL compatibility warning from the local Python environment.
- LangGraph pending deprecation warning from installed dependency.

## Files Changed

- `PLAN.md`
- `src/movia_sales_agent/contracts/__init__.py`
- `src/movia_sales_agent/contracts/commercial.py`
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

## Deferred Issues

- The planner is still not the complete Phase 2 deterministic planner.
- Not all 13 macroactions are reachable yet.
- Current stage persistence still uses the V1 database constraint and action-derived mapping.
- Objection flow is not persistent and does not progress through multi-turn state yet.
- The gold dataset is not aligned to Contract V2 yet.
- Response context is not compacted yet.

## Guardrails Confirmed

- `movia_validation_package/movia_difficult_lead_validation_scenarios.json` was not modified.
- No migration file was added or applied.
- No full evaluation replay was run.
- Phase 2 was not started.

## Exact Next Task

Begin Phase 2 by writing planner tests for:

- all 13 macroactions reachable;
- `can_direct_close(state)`;
- premature direct-close regressions;
- exact question routing through `answer_and_advance`;
- skeptical-but-not-blocking routing through `persuade_value`;
- deterministic Captura/Hibrido narrowing.
