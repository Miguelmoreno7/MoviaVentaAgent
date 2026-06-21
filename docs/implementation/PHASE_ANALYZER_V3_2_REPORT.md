# Phase Analyzer V3.2 Report: Deterministic Normalization And Derivation

Date: 2026-06-06

## Summary

Phase Analyzer V3.2 is complete.

Implemented a deterministic normalized-turn layer after Analyzer Contract V3. The analyzer still observes language only; the new normalizer derives dependent commercial fields, validates evidence, separates requested/recommended/selected product, computes known and missing slots, and records parser-versus-LLM telemetry.

No datasets were modified. No migrations were created or applied. No full validation replay was run.

## Files Changed

- `src/movia_sales_agent/analyzer/__init__.py`
- `src/movia_sales_agent/analyzer/contract_v3.py`
- `src/movia_sales_agent/analyzer/normalizer.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/openai_service.py`
- `docs/architecture/NORMALIZED_TURN_CONTRACT_V3.md`
- `tests/test_analyzer_contract_v3.py`
- `tests/test_analyzer_normalization_v3.py`
- `docs/implementation/PHASE_ANALYZER_V3_2_REPORT.md`
- `PLAN_ANALYZER_V3.md`

## Implemented

- Added `NormalizedTurn`.
- Added deterministic derivation for:
  - `has_objection`
  - `has_prior_reference`
  - `explicit_start_intent`
  - `is_post_purchase`
  - `action_requirement`
  - `requested_product`
  - `recommended_product`
  - `selected_product`
  - `product_preference_mismatch`
  - known slots and missing slots.
- Added invariant/contradiction recording.
- Added evidence revalidation during normalization.
- Added parser/LLM comparison telemetry:
  - agreement
  - parser-only
  - LLM-only
  - conflict.
- Added graph node:

```text
analyze_turn
→ normalize_and_derive_turn
→ update_lead_state
```

- Added normalized-turn and parser/LLM telemetry traces to `response_metadata`.
- Preserved parser non-authority: parser-only values do not change normalized action requirement, product recommendation or planner behavior.
- Added deterministic compatibility conversion from `NormalizedTurn` to current `TurnAnalysis`.

## Compatibility Note

The Sales Policy Planner still consumes `TurnAnalysis`. Phase 2 converts the normalized result into planner-compatible `TurnAnalysis` so the current runtime remains stable.

Phase 3 should move planner integration to the normalized contract directly and remove more of the compatibility dependency.

## Tests Run

```bash
.venv/bin/pytest tests/test_analyzer_normalization_v3.py -q
.venv/bin/pytest tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py -q
.venv/bin/pytest tests/test_objection_flow.py -q
.venv/bin/pytest tests/test_agent_policy.py tests/test_response_context.py tests/test_api.py tests/test_objection_flow.py tests/test_memory_v3.py tests/test_rag_v3.py tests/test_evaluation.py -q
.venv/bin/python -m compileall src/movia_sales_agent/analyzer src/movia_sales_agent/services/openai_service.py src/movia_sales_agent/agent/graph.py
.venv/bin/pytest -q
```

Results:

- Phase 2 normalization tests: `13 passed, 1 warning`.
- Analyzer contract + normalization tests: `28 passed, 1 warning`.
- Objection flow regression: `13 passed, 1 warning`.
- Wider regression pack: `64 passed, 1 warning`.
- Compile check: passed.
- Full local pytest: `118 passed, 1 warning`.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Impossible analyzer states are normalized before planner compatibility: completed.
- `action_requirement` does not default to answers-only without valid evidence: completed.
- External actions derive Híbrido, not Captura: completed.
- Historical references require valid evidence and false "antes de pagar" references stay false: completed.
- Explicit start requires valid evidence: completed.
- Product recommendation is deterministic: completed.
- Parser remains non-authoritative: completed.
- Parser/LLM telemetry is visible: completed.

## Unresolved Issues

- Planner still consumes `TurnAnalysis`.
- Response package still receives planner-compatible legacy fields.
- Live OpenAI targeted validation was not run in this phase.
- Phase 3 must add planner-level constraints for unsupported channels and Captura external-action claims.

## Exact Next Task

Implement Phase 3 only: Sales Policy Planner integration with the normalized contract, CTA/next-question compatibility, and response-package claim constraints.

