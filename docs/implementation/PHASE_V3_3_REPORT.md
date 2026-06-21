# Phase V3.3 Report: Memory Correction And Memory Evaluation

Date: 2026-06-05

## Summary

Phase V3.3 is complete. The agent now calculates structured memory in deterministic code, avoids repeat questions for known slots, derives product fit from action requirement, retrieves prior conversation evidence only when needed, and emits deterministic memory metrics.

No production migration was created or applied. No full scripted replay was run.

## Files Changed

- `docs/architecture/CONVERSATIONAL_MEMORY_V3.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- `docs/implementation/PHASE_V3_3_REPORT.md`
- `movia_validation_package/movia_coherent_scripted_conversations.json`
- `src/movia_sales_agent/contracts/commercial.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/openai_service.py`
- `src/movia_sales_agent/agent/memory.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/evaluation/scoring.py`
- `tests/test_memory_v3.py`
- `tests/test_response_context.py`
- `tests/test_evaluation.py`
- `PLAN_V3.md`

## Runtime Changes

- Added deterministic structured memory:
  - `known_slots`
  - `missing_slots`
  - `forbidden_question_keys`
  - derived `known_product_fit`
- Added prior-reference fields to `TurnAnalysis`.
- Added conditional prior-message retrieval from the current lead's recent message buffer.
- Added compact `memory_context` to the response package.
- Added a post-generation memory validator that corrects forbidden repeated questions without a second LLM call.
- Added memory retrieval metadata:
  - `conversation_memory_lookup`
  - `conversation_memory_evidence`

## Evaluation Changes

Added deterministic memory metrics:

- `memory.known_slot_repetition`
- `memory.historical_reference_accuracy`
- `memory.prior_commitment_consistency`
- `memory.contextual_personalization`

Added two coherent memory scenarios:

- `MOVIA-MEM-001`: structured-slot memory and no repeated discovery.
- `MOVIA-MEM-002`: historical reference retrieval and consistency.

The coherent suite now has 7 scenarios and 57 turns.

## Tests Run

```bash
.venv/bin/python -m compileall src/movia_sales_agent
.venv/bin/pytest tests/test_memory_v3.py -q
.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py tests/test_memory_v3.py -q
.venv/bin/pytest -q
.venv/bin/movia-eval validate-dataset
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
```

Results:

- Phase 3 memory tests: `7 passed, 1 warning`.
- Targeted suite: `66 passed, 1 warning`.
- Full local pytest: `75 passed, 1 warning`.
- Atomic dataset validation passed: 5 scenarios, 60 turns.
- Coherent dataset validation passed: 7 scenarios, 57 turns.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Turn 4 regression passes: completed.
- Known slots are never casually re-requested: completed by planner contract and response validator.
- Question CTAs cannot have null question keys: completed for `soft_question` and `discovery_question`.
- Historical retrieval runs only when needed: completed.
- Prior references return relevant evidence: completed.
- No cross-lead contamination: completed for in-memory/offline lead isolation.
- No large unconditional token increase: completed; memory evidence is included only for prior-reference turns.

## Unresolved Issues

- Prior-message retrieval currently uses recent message pairs only; Postgres full-text and semantic fallback remain future enhancements.
- Memory scenarios are structurally valid but not replay-calibrated.
- Existing environment warnings remain unchanged.

## Exact Next Task

Begin Phase V3.4 only: RAG audit and routing improvement, using `PLAN_V3.md` as the operational tracker.
