# Evaluation Root Causes

Audit date: 2026-06-04  
Repo root: `/Users/miguelmoreno/Documents/MoviaVentaAgente`  
Baseline run: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`

This document identifies likely root causes for the baseline validation result. It does not prescribe runtime changes.

## Baseline Failure Pattern

Fact: the full run failed pass policy with overall score `0.7889` and no hard failures.

Fact: category scores were:

| Category | Score |
|---|---:|
| `commercial_accuracy` | 1.0000 |
| `policy_compliance` | 1.0000 |
| `memory_consistency` | 1.0000 |
| `scope_control` | 1.0000 |
| `source_selection` | 0.7685 |
| `objection_handling` | 0.5083 |
| `sales_progression` | 0.0750 |

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/summary.md`.

Inference: the agent is not failing because of verified price/refund/channel/product hallucinations in this run. It is failing mostly because expected trace labels and actual emitted trace labels do not match.

## RC1: Analyzer Emits Free-Form Taxonomy

Fact: `ANALYSIS_SCHEMA` constrains field types but not enum values for `intent`, `topics`, `objection_type`, or `buying_signal`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/services/openai_service.py:14-69`.

Fact: `analyze_turn_with_usage` asks the model to classify the turn but does not provide an allowed vocabulary in the prompt. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/services/openai_service.py:87-124`.

Fact: baseline emitted many one-off intent/topic/objection strings, including values such as `preference for a better-known competitor`, `precio y conversion baja`, `service_unavailability`, and `Repeticion de pregunta ya respondida`.

Fact: `SalesPolicyPlanner.plan` reuses `analysis.objection_type` as `micro_action` for objection routes. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:30-38`.

Affected metrics:

- `trace.micro_action`: failed on all 60 turns.
- `trace.objection_type`: failed on 31 turns.
- `trace.objection_flow_step`: failed on 28 turns.

Inference: free-form analysis directly propagates into free-form planner labels, which cannot match the fixed validation dataset vocabulary.

## RC2: Planner Runtime Vocabulary Is Smaller Than The Dataset Vocabulary

Fact: the schema enum includes 13 possible macro actions. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/models/schemas.py:8-22`.

Fact: current planner code has branches for only 8 macro actions. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:8-67`.

Fact: the baseline emitted only 4 macro actions:

| Actual macro | Count |
|---|---:|
| `handle_objection` | 27 |
| `recommend_solution` | 19 |
| `direct_close` | 12 |
| `handoff_to_miguel` | 2 |

Fact: the validation dataset expects 12 macro actions, including `answer_and_advance`, `narrow_solution`, `persuade_value`, `risk_reversal`, and `answer_unknown_safely`.

Affected metrics:

- `trace.macro_action`: failed on 43 turns.
- `trace.current_stage`: failed on 59 turns because stage is derived from macro action.
- `trace.final_cta_type`: failed on 60 turns because CTA vocabulary is also narrower.

Inference: many expected actions are not reachable in current runtime, so failures are structural rather than isolated response mistakes.

## RC3: Stage Is Not A Sales-State Machine

Fact: current response stage is derived from current action with a small mapping. Evidence: `_lead_state_for_response` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:280-294`.

Fact: current persisted stage is also derived from current action. Evidence: `_stage_for_action` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:234-243`.

Fact: database allowed stages are compressed: `new`, `discovery`, `qualified`, `recommended`, `closing`, `handoff`, `unknown`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/supabase/migrations/202606030001_init_movia_sales_agent.sql:121-124`.

Fact: validation expects finer-grained stages: `educating`, `comparing`, `objection_handling`, `ready_to_start`, `solution_recommended`, `post_purchase`, and `unknown_recovery`, among others.

Affected metric:

- `trace.current_stage`: failed on 59 of 60 turns.

Inference: almost all stage failures are expected because the implementation does not expose the validation package's sales-stage vocabulary.

## RC4: Priority Order Over-Routes To Direct Close And Objection Handling

Fact: `wants_to_start` is checked before `has_objection`, platform, comparison, discovery, and recommendation. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:21-29`.

Fact: `has_objection` is checked before platform, comparison, discovery, and recommendation. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:30-38`.

Fact: baseline turns where `wants_to_start` was true included messages that were not clean close requests, such as:

- `MOVIA-VAL-001#3`: "De Facebook Ads a WhatsApp. La gente pregunta precio y luego desaparece."
- `MOVIA-VAL-003#4`: "Entonces si quiero que cotice fumigacion por metros cuadrados, entra o no?"
- `MOVIA-VAL-004#1`: "Tengo proveedores que mandan ticket de compra..."
- `MOVIA-VAL-005#5`: "Dame prueba gratis sin deposito y si funciona pago."

Evidence: baseline `run.json`.

Inference: analyzer overclassification plus planner priority order can turn discovery/scope/free-trial turns into `direct_close`.

## RC5: Knowledge Planner Has Limited Trigger Coverage

Fact: `KnowledgePlanner.plan` adds RAG queries only for `industry_fit_question` and `comparison_question`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:89-126`.

Fact: `_rag_metadata_filter` only maps business types for `dental`, `restaurant`, and `real_estate`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:297-305`.

Fact: baseline retrieved RAG on only 2 of 60 turns, both from `rag_docs/use_cases/dental.md`.

Affected metrics:

- `trace.rag_used`: failed on 14 turns.
- `source.expected_recall`: failed on 34 turns.

Inference: RAG is not overused; it is under-triggered relative to the validation package.

## RC6: Source Labels Are Coarser Than Expected

Fact: current structured source labels are only `postgres.products`, `postgres.policies`, and `postgres.official_links`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/capabilities.py:10-14`.

Fact: product features are fetched as part of products, not emitted as `postgres.product_features`. Evidence: `MoviaRepository.fetch_products` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/db/repository.py:29-54`.

Fact: the evaluator marked the following expected labels as not applicable in the baseline:

- `postgres.product_features`
- `postgres.product_actions`
- `postgres.channels`
- `memory.lead_profile`
- `memory.conversation_summary`
- `rag.use_cases.beauty_barbershop`
- `rag.use_cases.suppliers_operations`
- `rag.use_cases.home_services`
- `rag.comparisons.whatsapp_business_only`

Evidence: `not_applicable` metrics in baseline `run.json`.

Inference: some source-selection expectations are dataset-contract mismatches, not retrieval mistakes.

## RC7: RAGAS And DeepEval Were Not Part Of The Baseline Score

Fact: full baseline notes say RAGAS and DeepEval were skipped. Evidence: `notes` in baseline `run.json`.

Fact: RAGAS was skipped on 58 turns because no RAG context was retrieved and skipped on 2 turns because the full run configuration did not enable a live RAGAS client. Evidence: `ragas.rag_quality` metrics in baseline `run.json` and `RagasEvaluator.evaluate_turn` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/frameworks.py:54-75`.

Inference: current pass/fail should not be interpreted as a full RAGAS/DeepEval quality result. It is primarily deterministic trace/rule scoring.

## RC8: Token Cost Is Dominated By Response Input Context

Fact: total agent token usage was `298,453` tokens:

| Operation | Total tokens |
|---|---:|
| response | 242,999 |
| analysis | 55,409 |
| embedding | 45 |

Fact: response input alone was `236,009` tokens.

Evidence: baseline `run.json`.

Fact: `build_generation_context` includes analysis, sales plan, structured context, JSON context, up to 5 RAG chunks, recent messages, and response requirements. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/response.py:23-46`.

Inference: the cost issue is primarily large per-turn response context, not hidden evaluator calls or excessive RAG embeddings in the baseline.

## Root Cause Summary

| Root cause | Main evidence | Primary impacted score |
|---|---|---|
| Free-form analyzer values | `openai_service.py:14-69`, baseline traces | micro action, objection type |
| Narrow reachable planner actions | `planners.py:8-67`, baseline action counts | macro action, CTA |
| Action-derived stage mapping | `graph.py:234-243`, `graph.py:280-294` | current stage |
| Limited RAG/source trigger coverage | `planners.py:89-126`, baseline RAG count | source selection |
| Unsupported expected source labels | `capabilities.py:10-45`, RAG docs folder | not-applicable source metrics |
| Response context bloat | `response.py:23-46`, token breakdown | token usage/cost |

## Non-Root-Causes In This Baseline

Fact: there were zero hard failures.

Fact: deterministic commercial accuracy, policy compliance, memory consistency, and scope control scores were all `1.0`.

Inference: there is no evidence in this baseline that the agent systematically invented official prices, sold unavailable products/channels as active, broke refund/deposit rules, or leaked memory across scenarios.
