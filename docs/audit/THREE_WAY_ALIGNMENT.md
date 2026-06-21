# Three-Way Alignment

Audit date: 2026-06-04  
Repo root: `/Users/miguelmoreno/Documents/MoviaVentaAgente`

This document compares three layers:

1. Actual implementation
2. Intended architecture from project/design documents
3. Validation package expectations

## Source Evidence

- Actual implementation: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/`
- Database schema: `/Users/miguelmoreno/Documents/MoviaVentaAgente/supabase/migrations/202606030001_init_movia_sales_agent.sql`
- Knowledge package: `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/movia_knowledge_source/`
- Validation plan: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_validation_plan.md`
- Validation JSON: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_difficult_lead_validation_scenarios.json`
- Baseline run: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`

## Alignment Matrix

| Area | Actual Implementation | Intended Architecture | Validation Expectations | Alignment |
|---|---|---|---|---|
| Graph nodes | Implements the planned graph nodes from memory load to save. Evidence: `MoviaSalesAgent._build_graph` in `src/movia_sales_agent/agent/graph.py:35-60`. | LangGraph flow with load/analyze/plan/fetch/merge/generate/save. | Requires debug trace for routing, memory, sources, and response. | Aligned structurally. |
| Analyzer schema | Free-form `intent`, `topics`, `objection_type`, and `buying_signal`. Evidence: `ANALYSIS_SCHEMA` in `src/movia_sales_agent/services/openai_service.py:14-69`. | Structured analysis was intended. | Expects stable categories such as `pricing_question`, `comparison_question`, `trust_objection`, `price_objection`. | Partially aligned; field names exist, values are not controlled. |
| Macro actions | Enum includes 13 actions, planner emitted only 4 in baseline. Evidence: `SalesAction` in `models/schemas.py:8-22`, planner in `agent/planners.py:8-67`, baseline `run.json`. | Deterministic commercial routing with discovery, recommendation, objections, close, handoff. | Expects 12 macro-action labels across 60 turns. | Mismatch in runtime reachability. |
| Micro actions | Free-form strings; objections reuse analyzer `objection_type`. Evidence: `SalesPlan` in `models/schemas.py:49-55`, planner in `agent/planners.py:30-38`. | Commercial micro-actions should explain the selected next sales move. | Expects fixed labels such as `answer_price_then_explain_scope`, `compare_manychat`, `risk_reversal`, `send_app_link`. | Mismatch. |
| Stages | Database and API use compressed stages: `new`, `discovery`, `qualified`, `recommended`, `closing`, `handoff`, `unknown`. Evidence: migration `202606030001_init_movia_sales_agent.sql:121-124`, `_lead_state_for_response` in `agent/graph.py:280-294`. | Stages were intended to reflect sales progression. | Expects `educating`, `comparing`, `objection_handling`, `ready_to_start`, `solution_recommended`, and other detailed stages. | Mismatch. |
| Source labels | Structured emitted labels are only products, policies, official links. JSON labels are config stems. RAG labels are file-derived. Evidence: `fetch_structured_data_node` in `agent/graph.py:127-136`, `capabilities.py:10-45`. | Exact facts in Postgres, playbooks in JSON, explanatory docs in RAG. | Expects product features, product actions, channels, memory sources, and several RAG docs that are not emitted. | Partially aligned. |
| RAG behavior | RAG only runs when planner adds `rag_queries`; baseline retrieved RAG on 2/60 turns. Evidence: `KnowledgePlanner.plan` in `agent/planners.py:89-126`, baseline `run.json`. | RAG used for explanations, comparisons, and use cases. | Expects RAG on many comparison/use-case turns. | Mismatch in trigger coverage. |
| Commercial facts | Current products/policies/links are in DB/seeds and hard-fail rules found no commercial errors. Evidence: baseline `summary.md`. | Supabase and knowledge package are source of truth. | Requires no invented prices, channels, refund policy, or unavailable products as active. | Aligned in baseline. |
| Product status | Seeds mark MovIA Ventas and Pro Comercial as `not_available`. Evidence: `docs/movia_knowledge_source/config/products.seed.json`. | User assumption says Ventas and Pro Comercial are not available and must not be sold as active. | Validation plan text says `coming_soon`, but also says not to sell them as available. | Acceptable; current authoritative data is stricter. |
| WhatsApp webhook | POST-only webhook receives dispatcher payload; no GET verification. Evidence: `/src/movia_sales_agent/api/main.py:57-86`. | Earlier correction dismissed Meta verify token and GET verification. | Evaluation uses `/chat`/agent runner, not webhook verification. | Aligned. |
| WhatsApp formatting | Splits long responses into multiple message parts. Evidence: `split_whatsapp_messages` in `whatsapp/formatting.py:10-128`. | WhatsApp-first readability was requested. | Runner captures `response_messages`. | Aligned. |
| Memory isolation | Evaluation uses tagged leads and `channel="evaluation"`. Evidence: `EvaluationRunner._run_scenario` in `evaluation/runner.py:133-156`. | Scenarios should not share memory. | Cross-scenario memory leakage is a hard fail. | Aligned in baseline: no hard failures. |

## Concrete Mismatch Examples

| Scenario turn | Expected | Actual | Likely source |
|---|---|---|---|
| `MOVIA-VAL-001#1` | `answer_and_advance`, `discovery`, `answer_scope_then_discover_business` | `handle_objection`, `qualified`, free-form distrust micro-action | Analyzer marked the sarcastic opener as an objection; planner puts objections before discovery. |
| `MOVIA-VAL-001#3` | `narrow_solution`, `qualified`, `differentiate_captura_vs_hibrido` | `direct_close`, `closing`, `send_app_link_and_deposit_step` | Analyzer set `wants_to_start`; direct close has high priority. |
| `MOVIA-VAL-001#5` | `compare_alternative`, `comparing`, `compare_manychat` | `handle_objection`, `qualified`, `preference for a better-known competitor` | Objection route outranked comparison route, and topic taxonomy was not stable. |
| `MOVIA-VAL-002#3` | `answer_unknown_safely`, `unknown_recovery` | `recommend_solution`, `recommended` | `answer_unknown_safely` is enum-valid but not planner-reachable. |
| `MOVIA-VAL-005#5` | `handle_objection`, `wants_free_trial` | `direct_close`, `send_app_link_and_deposit_step` | Analyzer set `wants_to_start`; direct close outranked free-trial objection handling. |

Evidence: actual/expected traces in `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`.

## Source-Taxonomy Mismatches

Fact: the validation package expects these unsupported source labels and the evaluator marks them `not_applicable`:

| Unsupported expected label | Count in baseline not-applicable metrics | Reason |
|---|---:|---|
| `postgres.product_features` | 16 | Product features are joined inside `postgres.products`, not emitted as a separate source label. |
| `postgres.product_actions` | 7 | No current structured source capability emits this label. |
| `memory.lead_profile` | 7 | Memory influences state but is not emitted as a source label. |
| `postgres.channels` | 2 | Channel table exists, but current fetcher does not expose `postgres.channels`. |
| `rag.use_cases.beauty_barbershop` | 4 | No corresponding RAG file exists. |
| `rag.use_cases.suppliers_operations` | 1 | No corresponding RAG file exists. |
| `rag.use_cases.home_services` | 1 | No exact corresponding emitted RAG label exists. |
| `rag.comparisons.whatsapp_business_only` | 1 | No corresponding RAG file exists. |
| `memory.conversation_summary` | 1 | Summary table exists, but graph does not read/write or emit summaries. |

Evidence: `not_applicable` metrics in baseline `run.json`, source capabilities in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/capabilities.py:10-45`, RAG files in `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/movia_knowledge_source/rag_docs/`.

## Most Important Alignment Conclusion

Fact: the agent passed deterministic commercial, policy, memory, and scope hard-rule checks in the baseline.

Fact: the agent failed mostly on trace agreement:

- `trace.current_stage`: 59 failures
- `trace.final_cta_type`: 60 failures
- `trace.macro_action`: 43 failures
- `trace.micro_action`: 60 failures
- `trace.objection_type`: 31 failures
- `trace.objection_flow_step`: 28 failures
- `source.expected_recall`: 34 failures

Evidence: baseline `run.json`.

Inference: the current problem is not that the agent lacks all core architecture. The main issue is that the runtime taxonomy is much smaller and less controlled than the validation taxonomy.
