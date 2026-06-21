# Phase V3.4 Report: RAG Audit And Routing Improvement

Date: 2026-06-05

## Summary

Phase V3.4 is complete. RAG routing is now deterministic, filtered, thresholded and evaluated separately from generic expected source-label matching.

No production migration was created or applied. No full scripted replay was run.

## Files Changed

- `docs/audit/RAG_USAGE_AUDIT_V3.md`
- `docs/architecture/RAG_ROUTING_POLICY_V3.md`
- `docs/implementation/PHASE_V3_4_REPORT.md`
- `src/movia_sales_agent/agent/rag_policy.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/rag.py`
- `src/movia_sales_agent/ingestion/chunker.py`
- `src/movia_sales_agent/evaluation/scoring.py`
- `tests/test_rag_v3.py`
- `PLAN_V3.md`

## Runtime Changes

- Added `build_rag_route(...)` as the deterministic RAG routing policy.
- Added `rag_metadata_filter` and `rag_routing_reason` to `KnowledgePlan`.
- Kept exact factual questions on structured/JSON sources only.
- Routed industry questions to filtered use-case docs.
- Routed comparison questions to filtered comparison docs.
- Removed unfiltered retrieval fallback when a filtered search returns no rows.
- Added `MIN_RAG_SIMILARITY = 0.58`.
- Limited retained RAG chunks to top three.
- Added local keyword fallback normalization and metadata filtering.
- Added canonical metadata aliases for future ingestion:
  - `comparison_target`
  - `product`

## Evaluation Changes

Added deterministic RAG metrics:

- `rag.retrieval_necessity`
- `rag.routing_accuracy`
- `rag.context_relevance`
- `rag.answer_groundedness`

These metrics stay in the `source_selection` category and remain separate from future response-quality scoring.

## Smoke Audit

Offline runtime smoke produced:

- `¿Cuánto cuesta?`: no RAG, `rag_chunk_count=0`.
- `¿Cuál es el plan más barato y por qué me conviene para una clínica dental?`: filter `{"topic":"use_cases","industry":"dental"}`, retrieved `rag_docs/use_cases/dental.md`.
- `¿Esto es como ManyChat?`: filter `{"topic":"comparisons","comparison":"manychat"}`, retrieved `rag_docs/comparisons/manychat.md`.

## Tests Run

```bash
.venv/bin/pytest tests/test_rag_v3.py -q
.venv/bin/python -m compileall src/movia_sales_agent
.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py tests/test_memory_v3.py tests/test_rag_v3.py -q
.venv/bin/pytest -q
.venv/bin/movia-eval validate-dataset
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
```

Results:

- Phase 4 RAG tests: `5 passed, 1 warning`.
- Compileall: passed.
- Targeted regression suite: `71 passed, 1 warning`.
- Full local pytest: `80 passed, 1 warning`.
- Atomic dataset validation passed: 5 scenarios, 60 turns.
- Coherent dataset validation passed: 7 scenarios, 57 turns.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Exact price/policy/platform questions do not trigger unnecessary RAG: completed.
- Industry questions use relevant industry documents: completed for dental use case.
- Comparison questions use relevant comparison documents: completed for ManyChat.
- Irrelevant low-score chunks are rejected: completed.
- RAG metrics evaluate necessity, routing, relevance and groundedness: completed.
- No commercial fact is overridden by RAG: completed by structured-source routing.
- Average context does not grow significantly: completed by top-three limit and filtered retrieval.

## Unresolved Issues

- Existing remote RAG rows may need re-ingestion before they include new alias metadata fields.
- Deterministic groundedness uses visible metadata terms; judge-based semantic groundedness remains Phase 5 or evaluation-only future work.
- No RAGAS run was executed in this phase.

## Exact Next Task

Begin Phase V3.5 only: response-quality evaluation, using `PLAN_V3.md` as the operational tracker.
