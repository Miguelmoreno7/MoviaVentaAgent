# Phase Analyzer V3.3 Report: Sales Policy Planner Integration

Date: 2026-06-06

## Summary

Phase Analyzer V3.3 is complete.

The Sales Policy Planner now receives the normalized-turn contract directly. The analyzer still only observes, the normalizer still derives dependent facts, and the planner owns commercial decisions. The response package now carries explicit turn signals and hard claim constraints for unavailable channels, unavailable products, and Captura external-action limits.

No datasets were modified. No migrations were created or applied. No targeted live validation or full replay was run.

## Files Changed

- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/agent/response.py`
- `tests/test_agent_policy.py`
- `tests/test_response_context.py`
- `PLAN_ANALYZER_V3.md`
- `docs/implementation/PHASE_ANALYZER_V3_3_REPORT.md`

## Implemented

- Added `normalized_turn` to planner state and graph planner calls.
- Exposed normalized planner inputs:
  - `action_requirement`
  - `requested_product`
  - `recommended_product`
  - `selected_product`
  - `product_preference_mismatch`
  - `known_slots`
  - `missing_slots`.
- Updated planner priority:
  - unknown action requirement stays discovery;
  - product mismatch routes to `narrow_solution`;
  - external actions route to MovIA Híbrido instead of Captura;
  - evidence-backed product fit can recommend solution before generic slot completion;
  - soft close still wins after a recommendation has already been communicated.
- Enforced `next_question_key` for question CTAs, including objection questions.
- Added response-package `turn_signal_context`.
- Added response-package `claim_constraints`.
- Updated fallback responses so recommendation is no longer a generic catch-all.
- Added deterministic fallback wording for:
  - channel availability;
  - product mismatch;
  - external-action routing.

## Claim Constraints Added

- Only WhatsApp Business is currently available.
- Facebook and Instagram are upcoming/not available.
- No MovIA product should be described as currently multichannel.
- Captura may collect order information inside WhatsApp.
- Captura may not create, register, or write orders in external systems.
- External-action requests should route to Híbrido.
- MovIA Ventas and MovIA Pro Comercial remain not available.

## Tests Run

```bash
.venv/bin/pytest tests/test_agent_policy.py tests/test_memory_v3.py tests/test_response_context.py tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py -q
.venv/bin/pytest -q
```

Results:

- Targeted Phase 3 regression pack: `65 passed, 1 warning`.
- Full local pytest suite: `125 passed, 1 warning`.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Analyzer only observes: completed.
- Normalizer only derives: completed.
- Planner only decides: completed.
- Generator only writes from selected planner action and constraints: completed.
- No automatic Captura recommendation without evidence: completed.
- No Captura recommendation for external actions: completed.
- No unsupported channel claims in fallback or package constraints: completed.
- No unavailable-product active-sale claim in fallback or package constraints: completed.
- No null question key for question CTAs: completed.
- Existing Atomic/Coherent datasets unchanged: completed.

## Unresolved Issues

- Live OpenAI targeted validation was not run in this phase.
- `TurnAnalysis` compatibility remains present because downstream runtime and tests still consume it.
- Response-package constraints reduce live-model risk, but deterministic post-generation claim validation may still be useful if Phase 4 finds new wording failures.

## Exact Next Task

Implement Phase 4 only: targeted live validation for the highest-risk Analyzer V3 cases, without modifying gold datasets and without running the full replay.
