# Phase 2 Report: Complete The Sales Policy Planner

Date: 2026-06-04  
Master reference: `PLANV2.md`  
Operational plan: `PLAN.md`

## Summary

Phase 2 replaces the partial Phase 1 planner with a deterministic policy planner that makes all 13 Contract V2 macroactions reachable, adds stable planner reason codes, and gates `direct_close` through code instead of analyzer enthusiasm.

No production migrations, deployments, or full validation replay were run.

## Completed Work

- Added canonical planner support enums:
  - `ActionRequirement`
  - `ProductFit`
  - `PlannerReasonCode`
- Extended `SalesPlan` with:
  - `target_stage`
  - `reason_code`
  - `next_question_key`
- Added `PlannerState`, `build_planner_state(...)`, and `can_direct_close(state)`.
- Implemented the Phase 2 deterministic priority order:
  - post-purchase/support handoff
  - active objection continuation
  - new hard objections
  - gated direct close
  - exact informational answer-and-advance
  - process/policy/risk explanations
  - comparisons
  - unknown recovery
  - skeptical value persuasion
  - soft objection handling
  - Captura/Híbrido narrowing
  - discovery
  - recommendation
  - soft close
- Updated heuristic analysis to extract planner facts such as:
  - `action_requirement=answers_only`
  - `action_requirement=external_actions_required`
  - `known_product_fit=movia_captura`
  - `known_product_fit=movia_hibrido`
  - unavailable product interest for MovIA Ventas and Pro Comercial
- Fixed premature-routing regressions:
  - sarcastic opener routes to `persuade_value`, not hard objection or direct close
  - pain description with “pregunta precio” is not a price question
  - “Solo responder. ¿Cuánto cuesta?” routes to `answer_and_advance`
  - free-trial request routes to `handle_objection`
  - supplier ticket/photo workflow routes to Híbrido narrowing
  - ManyChat comparison routes to `compare_alternative`
- Updated fallback responses for newly reachable actions.
- Updated knowledge planning for risk reversal, comparison, persuasion, and answer-and-advance routes.
- Regenerated `docs/architecture/COMMERCIAL_CONTRACT_V2.json` from the Python source of truth.

## Files Changed

- `src/movia_sales_agent/contracts/commercial.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/services/openai_service.py`
- `tests/test_agent_policy.py`
- `tests/test_commercial_contract.py`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- `PLAN.md`
- `docs/implementation/PHASE_2_REPORT.md`

## Tests Run

```bash
.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_evaluation.py tests/test_api.py
```

Result: 34 passed.

```bash
.venv/bin/pytest tests
```

Result: 41 passed.

Warnings observed:

- `urllib3` LibreSSL/OpenSSL compatibility warning.
- LangGraph pending deprecation warning for default serializer settings.

## Guardrails Verified

- Full 60-turn evaluation was not run.
- Gold validation dataset was not modified.
- No Supabase migration was added or applied.
- No deployment or production data change was performed.
- Phase 3 was not started.

## Deferred Issues

- Planner `target_stage` is emitted for traceability, but persisted `current_stage` still uses the existing compressed action projection. Phase 3 must replace this with a real stage transition service.
- Active objection continuation can be consumed by the planner, but active objection state is not yet persisted. That remains Phase 4.
- Response context is still broad and token-heavy. Token reduction remains Phase 6.
- Evaluation gold labels are still deferred to Phase 5.

## Exact Next Task

Begin Phase 3 by designing and testing `SalesStageTransitionService`, including local-only migration fields for persistent stage state and unit tests proving stage progression is independent from the current macroaction.
