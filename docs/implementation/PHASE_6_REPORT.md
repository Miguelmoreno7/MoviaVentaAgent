# Phase 6 Report: Compact Response Context

Date: 2026-06-04  
Master reference: `PLANV2.md`  
Operational plan: `PLAN.md`

## Summary

Phase 6 implements compact response packaging and token instrumentation. The response generator now receives a smaller symbolic context instead of broad debug traces, full JSON config objects, full structured rows, and a blind six-message history window.

No full 60-turn evaluation replay, production migration, deployment, or production data change was performed.

## Completed Work

- Replaced broad generation context with a compact package:
  - `commercial_instruction`
  - `lead_context`
  - `official_facts`
  - `playbook_instruction`
  - bounded `rag_context`
  - relevant compact `recent_messages`
  - short `response_requirements`
- Added selective JSON extraction:
  - selected sales-action entry;
  - selected CTA rule;
  - selected tone subset;
  - selected objection entry;
  - selected platform/process steps;
  - selected source-routing rule for comparison turns.
- Added compact official facts:
  - product prices, availability, delivery time and action scope;
  - policy facts for deposit, refund, final payment, monthly billing and token usage;
  - official app link when requested.
- Added RAG bounds:
  - maximum 3 deduplicated chunks;
  - maximum 650 characters per chunk;
  - maximum 1,500 total RAG characters;
  - compact metadata only.
- Added simple recent-message relevance and recency selection:
  - last two messages are kept;
  - older user messages are kept only when term-relevant;
  - content is truncated.
- Added token instrumentation:
  - `response_metadata.response_package_token_estimates`;
  - response call `details.response_package_estimates`;
  - evaluation Markdown token summary and section averages.
- Preserved offline fallback behavior against compact context.

## Files Changed

- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `tests/test_response_context.py`
- `docs/implementation/TOKEN_COST_V2_REPORT.md`
- `docs/implementation/PHASE_6_REPORT.md`
- `PLAN.md`

## Measurement

Same 10-turn smoke estimate:

| Metric | Before Phase 6 | After Phase 6 | Delta |
|---|---:|---:|---:|
| Avg estimated response input / turn | 2,422.1 | 1,143.7 | -52.8% |
| Max estimated response input / turn | 3,453 | 1,586 | -54.1% |
| Avg estimated context package / turn | 2,217.7 | 939.5 | -57.6% |

The full 60-turn replay was not run, so full-run actual token targets remain deferred.

## Tests Run

```bash
.venv/bin/pytest tests/test_response_context.py tests/test_agent_policy.py tests/test_api.py tests/test_evaluation.py tests/test_objection_flow.py tests/test_stage_machine.py
```

Result: 53 passed.

```bash
.venv/bin/pytest tests
```

Result: 64 passed.

```bash
.venv/bin/movia-eval validate-dataset
```

Result: valid dataset, 5 scenarios, 60 turns, `commercial_contract_version="2.0"`, no unsupported expected fields, no unsupported expected sources.

Warnings observed:

- `urllib3` LibreSSL/OpenSSL compatibility warning.
- LangGraph pending deprecation warning for default serializer settings.

## Guardrails Verified

- No new always-on LLM calls were added.
- Full 60-turn evaluation replay was not run.
- No production migrations were applied.
- No deployment or production data change was performed.
- Final replay was not started.

## Deferred Issues

- Full actual token usage must be measured in final scripted replay.
- RAGAS and DeepEval live judge behavior remains deferred to final replay.
- Phase 3 and Phase 4 migrations still exist locally but have not been applied to production.

## Exact Next Task

Run the final scripted replay over the five scenarios and 60 user turns, preserve the previous baseline, and produce `docs/evaluation/V1_VS_V2_COMPARISON.md`.
