# Evaluation Contract

Audit date: 2026-06-04  
Repo root: `/Users/miguelmoreno/Documents/MoviaVentaAgente`

This document describes what the validation harness currently scores. It distinguishes dataset expectations from fields the current agent actually emits.

## Source Evidence

- Validation plan: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_validation_plan.md`
- Validation dataset: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_difficult_lead_validation_scenarios.json`
- Dataset loader: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/dataset.py`
- Runner: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/runner.py`
- Scoring: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py`
- Capability filter: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/capabilities.py`
- Framework adapters: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/frameworks.py`
- Reports: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/reporting.py`

## Dataset Shape

Fact: the validation package contains 5 scenarios and 60 total user turns. Evidence: `validate_dataset` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/dataset.py:40-81` and the baseline dataset summary.

Fact: the validation plan asks for 12 user turns per scenario. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_validation_plan.md:11-15`.

Fact: scenario IDs are:

- `MOVIA-VAL-001`
- `MOVIA-VAL-002`
- `MOVIA-VAL-003`
- `MOVIA-VAL-004`
- `MOVIA-VAL-005`

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`.

## Evaluation Objective

Fact: the validation plan objective is to test difficult inbound leads from Facebook Ads into WhatsApp and measure commercial accuracy, policy compliance, source selection, objection handling, memory consistency, scope control, and sales progression. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_validation_plan.md:7-21`.

Fact: the plan explicitly says not to evaluate only final natural-language answers; routing, memory, sources, and policy compliance should also be evaluated. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_validation_plan.md:1734-1742`.

## Supported Expected Fields

Fact: the current dataset validator recognizes these expected fields:

- `current_stage`
- `macro_action`
- `micro_action`
- `objection_type`
- `objection_flow_step`
- `expected_sources`
- `rag_used`
- `structured_used`
- `json_used`
- `final_cta_type`

Evidence: `SUPPORTED_EXPECTED_FIELDS` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/dataset.py:20-31`.

Fact: the baseline dataset summary had no unsupported expected fields. Evidence: `dataset_summary.unsupported_expected_fields` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`.

Inference: field names are supported, but field values may still be outside the current agent's real vocabulary.

## Expected Trace Vocabulary

Fact: the dataset expects stages that include:

- `comparing`
- `discovery`
- `educating`
- `narrow_solution`
- `objection_handling`
- `post_purchase`
- `qualified`
- `ready_to_start`
- `solution_recommended`
- `unknown_recovery`

Fact: the dataset expects macro actions that include:

- `answer_and_advance`
- `answer_unknown_safely`
- `compare_alternative`
- `direct_close`
- `explain_process`
- `handle_objection`
- `handoff_to_miguel`
- `narrow_solution`
- `persuade_value`
- `recommend_solution`
- `risk_reversal`
- `soft_close`

Fact: the dataset expects CTA values:

- `explain_next_step`
- `redirect_to_miguel`
- `send_app_link`
- `soft_close`
- `soft_question`

Fact: the dataset expects objection flow steps:

- `ask_open_question`
- `clarify_value`
- `thank_empathize_ask_open_question`
- `tie_solution`

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_difficult_lead_validation_scenarios.json`.

## Source Expectations

Fact: expected source labels include:

- `json.cta_rules`
- `json.objection_playbook`
- `json.platform_steps`
- `json.post_purchase_handoff`
- `json.sales_actions`
- `memory.conversation_summary`
- `memory.lead_profile`
- `postgres.channels`
- `postgres.official_links`
- `postgres.policies`
- `postgres.product_actions`
- `postgres.product_features`
- `postgres.products`
- `rag.comparisons.manychat`
- `rag.comparisons.whatsapp_business_only`
- `rag.overview`
- `rag.use_cases.beauty_barbershop`
- `rag.use_cases.dental`
- `rag.use_cases.home_services`
- `rag.use_cases.suppliers_operations`

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_difficult_lead_validation_scenarios.json`.

Fact: the evaluator marks unsupported source labels as `not_applicable`. Evidence: `_score_expected_sources` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:169-213`.

Fact: current structured source capabilities are only:

- `postgres.products`
- `postgres.policies`
- `postgres.official_links`

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/capabilities.py:10-14`.

Fact: the current RAG files under `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/movia_knowledge_source/rag_docs/` do not include dedicated `beauty_barbershop`, `suppliers_operations`, `home_services`, or `whatsapp_business_only` files. Existing RAG docs include dental, general services, real estate, restaurants, ManyChat, basic chatbot, human receptionist, and overview docs.

Inference: unsupported expected sources should not be treated as agent failures because the current agent cannot emit them.

## Scoring Rules

Fact: expected field comparisons are exact equality checks. Evidence: `_score_expected_fields` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:111-166`.

Fact: expected-source scoring computes recall against only applicable current source capabilities. Evidence: `_score_expected_sources` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:169-213`.

Fact: deterministic hard failures cover unsupported prices, unofficial links, future channels sold as available, unavailable products sold as active, refund-policy errors, wrong deposit percentages, missed post-purchase handoff, Captura external-action overpromises, and cross-scenario memory leakage. Evidence: `detect_hard_failures` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:216-339`.

Fact: category weights are:

| Category | Weight |
|---|---:|
| `commercial_accuracy` | 0.20 |
| `policy_compliance` | 0.20 |
| `sales_progression` | 0.15 |
| `memory_consistency` | 0.15 |
| `scope_control` | 0.10 |
| `objection_handling` | 0.10 |
| `source_selection` | 0.10 |

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:19-27`.

Fact: pass policy requires no hard failures, overall score at least `0.80`, and category scores meeting thresholds. Evidence: `passes_policy` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/scoring.py:424-434`.

## Runner Contract

Fact: the runner replays scripted turns against the real agent without seeding the lead profile into memory. Evidence: `_run_scenario` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/runner.py:126-213`.

Fact: evaluation leads use `channel="evaluation"` and external IDs shaped as `{run_id}:{scenario_id}:r{repeat}`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/runner.py:133-156`.

Fact: the runner captures:

- response text and message parts
- analysis
- lead state
- selected action
- knowledge plan
- retrieved sources
- response metadata
- token usage
- latency
- metrics
- hard failures

Evidence: `TurnEvaluationResult` construction in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/runner.py:168-186`.

## RAGAS And DeepEval Contract

Fact: RAGAS is skipped when a turn has no retrieved sources. Evidence: `RagasEvaluator.evaluate_turn` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/frameworks.py:54-64`.

Fact: RAGAS requires OpenAI credentials and an enabled OpenAI client. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/frameworks.py:15-52`.

Fact: DeepEval is scenario-level and requires OpenAI credentials plus the `deepeval` package. Evidence: `DeepEvalEvaluator` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/frameworks.py:124-244`.

Fact: the full baseline run was run with RAGAS and DeepEval skipped. Evidence: `notes` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json`.

## Baseline Result

Fact: baseline run `movia-eval-20260604T025630Z-4a5bf4` failed pass policy with:

| Metric | Value |
|---|---:|
| Overall applicable score | 0.7889 |
| Commercial accuracy | 1.0000 |
| Policy compliance | 1.0000 |
| Memory consistency | 1.0000 |
| Scope control | 1.0000 |
| Source selection | 0.7685 |
| Objection handling | 0.5083 |
| Sales progression | 0.0750 |
| Hard failures | 0 |

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/summary.md`.

Inference: current evaluation failure is trace-alignment and behavior-quality related, not a verified commercial-policy hard failure in this baseline.
