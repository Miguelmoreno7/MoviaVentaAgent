# Token Cost V2 Report

Date: 2026-06-04  
Master reference: `PLANV2.md`  
Phase: 6, compact response context

## Summary

Phase 6 reduces response-generation input by replacing broad debug-style context with a compact symbolic response package.

The full 60-turn evaluation replay was not run in this phase. The full replay remains the next step after all six phases. This report uses:

- the existing full baseline audit from `docs/audit/TOKEN_COST_AUDIT.md`;
- a same-message 10-turn smoke estimate before and after Phase 6 code changes.

## Existing Full Baseline

From `docs/audit/TOKEN_COST_AUDIT.md`:

| Metric | Baseline |
|---|---:|
| Total agent tokens | 298,453 |
| Avg total tokens / turn | 4,974.2 |
| Avg response input tokens / turn | 3,933.5 |
| Response input share | 236,009 tokens |

The audit identified response-generation input as the dominant cost driver.

## Same-Smoke Estimate

The smoke set used 10 representative WhatsApp turns covering skeptical opener, dental context, price, objections, platform process, comparison, direct-start pressure during an objection, and post-purchase handoff.

| Metric | Before Phase 6 | After Phase 6 | Delta |
|---|---:|---:|---:|
| Avg estimated response input / turn | 2,422.1 | 1,143.7 | -52.8% |
| Max estimated response input / turn | 3,453 | 1,586 | -54.1% |
| Avg estimated context package / turn | 2,217.7 | 939.5 | -57.6% |

These are estimates using the repository tokenizer heuristic (`len(text) // 4`) against the exact serialized response payload shape. They are not a replacement for the final 60-turn replay with actual provider usage.

## After-Smoke Section Averages

| Section | Avg estimated tokens |
|---|---:|
| `system_prompt` | 188.0 |
| `commercial_instruction` | 105.6 |
| `lead_context` | 92.0 |
| `official_facts` | 237.5 |
| `playbook` | 232.9 |
| `rag_context` | 90.9 |
| `recent_messages` | 87.2 |
| `response_requirements` | 50.0 |

## What Changed

The response generator now receives:

- `commercial_instruction`
- `lead_context`
- `official_facts`
- `playbook_instruction`
- bounded `rag_context`
- relevant compact `recent_messages`
- short response requirements

It no longer receives complete runtime traces, complete product/policy rows, complete JSON config objects, five full RAG chunks, or a blind six-message history window.

## Instrumentation

Every `ChatResponse.response_metadata` now includes:

```text
response_package_token_estimates
```

The response token-usage call details also include:

```text
details.response_package_estimates
```

Evaluation reports now include a token summary and response-package section averages.

## Full Replay Targets

Phase 6 targets remain to be measured on the final scripted replay:

| Target | Status |
|---|---|
| Avg total agent tokens / turn <= 3,500 | Deferred to final replay |
| Avg response input tokens / turn <= 2,500 | Likely improved; deferred to final replay |
| No increase in hard failures | Unit guardrails passed; deferred to final replay |
| No commercial accuracy regression | Unit guardrails passed; deferred to final replay |
| No policy compliance regression | Unit guardrails passed; deferred to final replay |

## Guardrails

- No new always-on LLM calls were added.
- RAG remains conditional on `KnowledgePlan.rag_queries`.
- RAG context is capped to 3 deduplicated chunks and 1,500 total characters.
- Structured official facts still override RAG.
- No production migrations or deployments were performed.
