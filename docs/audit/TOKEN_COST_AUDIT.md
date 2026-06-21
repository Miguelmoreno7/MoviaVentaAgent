# Token Cost Audit

Audit date: 2026-06-04  
Baseline run: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`

This document audits token usage for the full 60-turn validation baseline. It does not change cost settings or prompts.

## Baseline Totals

Fact: the full baseline consumed:

| Token type | Count |
|---|---:|
| Input tokens | 283,721 |
| Output tokens | 14,732 |
| Total tokens | 298,453 |

Evidence: `agent_token_usage` in baseline `run.json`.

## Operation Breakdown

Fact: token usage by operation:

| Operation | Calls | Input tokens | Output tokens | Total tokens | Share of total |
|---|---:|---:|---:|---:|---:|
| `response` | 60 | 236,009 | 6,990 | 242,999 | 81.4% |
| `analysis` | 60 | 47,667 | 7,742 | 55,409 | 18.6% |
| `embedding` | 60 entries, 2 live OpenAI calls | 45 | 0 | 45 | ~0.0% |

Evidence: per-call `token_usage.calls` in baseline `run.json`.

Inference: response generation input is the dominant cost driver.

## Model Breakdown

Fact: the baseline used:

| Operation | Model | Calls | Total tokens |
|---|---|---:|---:|
| `analysis` | `gpt-4.1-mini` | 60 | 55,409 |
| `response` | `gpt-4.1-mini` | 60 | 242,999 |
| `embedding` | `text-embedding-3-small` | 60 token-usage entries, 2 live OpenAI calls | 45 |

Evidence: baseline `run.json`.

Fact: settings support split models through `OPENAI_ANALYSIS_MODEL`, `OPENAI_RESPONSE_MODEL`, and `OPENAI_EVAL_MODEL`, falling back to `OPENAI_MODEL`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/config/settings.py:31-62`.

## Per-Turn Cost Shape

Fact: per-turn total tokens across 60 turns:

| Statistic | Value |
|---|---:|
| Average tokens per turn | 4,974.2 |
| Minimum turn tokens | 2,231 |
| Maximum turn tokens | 6,111 |

Fact: per-call token ranges:

| Field | Min | Average | Max |
|---|---:|---:|---:|
| analysis input | 266 | 794.5 | 975 |
| analysis output | 102 | 129.0 | 170 |
| response input | 1,640 | 3,933.5 | 4,879 |
| response output | 50 | 116.5 | 182 |

Evidence: baseline `run.json`.

## Highest Token Turns

Fact: the highest-token turns were:

| Scenario turn | Tokens | Macro | User message |
|---|---:|---|---|
| `MOVIA-VAL-001#12` | 6,111 | `handle_objection` | "Ok, si desde el mensaje 2 te dije clinica dental..." |
| `MOVIA-VAL-001#4` | 6,009 | `direct_close` | "Solo responder. Cuanto cuesta el chiste?" |
| `MOVIA-VAL-002#5` | 5,940 | `handle_objection` | "No, los tengo en una imagen del menu pegada en la pared." |
| `MOVIA-VAL-003#6` | 5,882 | `handle_objection` | "Y si no pago la mensualidad un mes?" |
| `MOVIA-VAL-005#5` | 5,862 | `direct_close` | "Dame prueba gratis sin deposito y si funciona pago." |

Evidence: baseline `run.json`.

Inference: the expensive turns are not only RAG turns. Most cost comes from large structured/JSON/recent-message context sent to response generation.

## Why Response Input Is Large

Fact: `build_generation_context` serializes the following into the response-generation prompt:

- current `analysis`
- current `sales_plan`
- `structured_context`
- `json_context`
- first 5 RAG chunks
- last 6 recent messages
- response requirements

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/response.py:23-46`.

Fact: `generate_response_with_usage` sends the system prompt plus a JSON object containing the user message and full generation context. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/services/openai_service.py:130-155`.

Fact: JSON playbooks are loaded as full config objects for requested sources. Evidence: `fetch_json_playbooks_node` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:138-143`.

Fact: all plans start with `tone_rules`, `cta_rules`, and `sales_actions`. Evidence: `KnowledgePlanner.plan` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:91-97`.

Inference: every response call carries a base JSON/playbook payload even when the user asks a simple question.

## RAG Cost

Fact: baseline RAG retrieval happened on only 2 turns:

- `MOVIA-VAL-001#2`
- `MOVIA-VAL-001#12`

Fact: both retrieved `rag_docs/use_cases/dental.md`.

Fact: embedding token usage was only 45 tokens total.

Evidence: baseline `run.json`.

Inference: RAG is not a material token-cost driver in this baseline.

## Evaluator Cost

Fact: full baseline notes:

- `RAGAS skipped: Disabled by run configuration.`
- `DeepEval skipped: Disabled by run configuration.`

Evidence: baseline `run.json`.

Inference: the 298,453 token total is agent cost only, not RAGAS/DeepEval judge cost.

## Latency

Fact: latency over the 60-turn run:

| Statistic | Value |
|---|---:|
| Average latency | 11,089.42 ms |
| Max latency | 16,022.98 ms |
| Max-latency turn | `MOVIA-VAL-002#9` |

Evidence: baseline `run.json`.

Inference: latency roughly tracks two LLM calls per turn plus DB/retrieval overhead.

## WhatsApp Message Parts

Fact: baseline WhatsApp split distribution:

| Message parts | Turns |
|---:|---:|
| 1 | 52 |
| 2 | 8 |

Evidence: `response_messages` in baseline `run.json`.

Fact: split limits are 520 soft characters and 900 hard characters. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/whatsapp/formatting.py:6-14`.

Inference: message splitting is working, but response generation still often produces long single responses before splitting.

## Cost Drivers Ranked

1. Fact: response-generation input accounts for 236,009 of 298,453 tokens.
2. Fact: analysis input accounts for 47,667 tokens.
3. Fact: response output is small by comparison at 6,990 tokens.
4. Fact: embeddings are negligible in this baseline at 45 tokens.
5. Fact: evaluator judge calls did not contribute to the baseline total.

## Audit Conclusion

Inference: the cheapest next improvements, if/when code changes are allowed, would likely be context compaction and stable symbolic planning. The audit does not implement those changes.
