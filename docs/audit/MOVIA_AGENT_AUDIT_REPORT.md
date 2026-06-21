# MovIA Agent Audit Report

Audit date: 2026-06-04  
Repo root: `/Users/miguelmoreno/Documents/MoviaVentaAgente`  
Baseline run: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/`

This audit was performed before behavioral changes. Runtime code, prompts, database schema, thresholds, and validation datasets were not modified for this audit.

## Documents Produced

- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/ACTUAL_AGENT_CONTRACT.md`
- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/ACTUAL_SALES_POLICY_FLOW.md`
- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/EVALUATION_CONTRACT.md`
- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/THREE_WAY_ALIGNMENT.md`
- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/EVALUATION_ROOT_CAUSES.md`
- `/Users/miguelmoreno/Documents/MoviaVentaAgente/docs/audit/TOKEN_COST_AUDIT.md`

## Executive Summary

Fact: the current agent has the intended LangGraph skeleton: memory load, turn analysis, lead update, sales planning, knowledge planning, structured/JSON/RAG fetches, context merge, response generation, and memory save. Evidence: `MoviaSalesAgent._build_graph` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:35-60`.

Fact: the baseline 60-turn evaluation failed pass policy with overall score `0.7889`, but had zero hard failures.

Fact: deterministic commercial safety categories passed:

- `commercial_accuracy`: `1.0`
- `policy_compliance`: `1.0`
- `memory_consistency`: `1.0`
- `scope_control`: `1.0`

Fact: low categories were:

- `sales_progression`: `0.075`
- `objection_handling`: `0.5083`
- `source_selection`: `0.7685`

Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/summary.md`.

Inference: current failures are primarily trace-contract and routing-taxonomy failures, not verified commercial-policy hallucinations.

## Most Important Findings

1. Fact: analysis emits free-form values. `intent`, `topics`, `objection_type`, and `buying_signal` are strings without enum constraints. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/services/openai_service.py:14-69`.

2. Fact: the deterministic planner has a smaller runtime action vocabulary than the validation package expects. Evidence: `SalesPolicyPlanner.plan` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/planners.py:8-67`.

3. Fact: baseline emitted only four macro actions: `handle_objection`, `recommend_solution`, `direct_close`, and `handoff_to_miguel`. Evidence: baseline `run.json`.

4. Fact: current stage is derived from the selected action and is not a separate sales-state machine. Evidence: `_stage_for_action` and `_lead_state_for_response` in `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/agent/graph.py:234-243` and `280-294`.

5. Fact: the validation dataset expects detailed stages and action labels that current runtime does not emit, such as `educating`, `comparing`, `ready_to_start`, `answer_and_advance`, `risk_reversal`, and `answer_unknown_safely`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/movia_validation_package/movia_difficult_lead_validation_scenarios.json`.

6. Fact: current structured source labels are limited to `postgres.products`, `postgres.policies`, and `postgres.official_links`. Evidence: `/Users/miguelmoreno/Documents/MoviaVentaAgente/src/movia_sales_agent/evaluation/capabilities.py:10-14`.

7. Fact: RAG was retrieved on only 2 of 60 baseline turns. Evidence: baseline `run.json`.

8. Fact: token cost is dominated by response input context: 236,009 response input tokens out of 298,453 total agent tokens. Evidence: baseline `run.json`.

## Baseline Metrics

| Metric | Value |
|---|---:|
| Overall score | 0.7889 |
| Hard failures | 0 |
| Total agent tokens | 298,453 |
| Average tokens per turn | 4,974.2 |
| Average latency | 11,089.42 ms |
| RAG turns | 2 / 60 |
| Responses split into 2 WhatsApp parts | 8 / 60 |

## What The Audit Does Not Claim

Fact: RAGAS and DeepEval were skipped in the full baseline. Evidence: `notes` in baseline `run.json`.

Therefore, this report does not claim a full live RAGAS/DeepEval quality score.

Fact: there were no hard commercial failures in the deterministic baseline.

Therefore, this report does not claim the agent is hallucinating prices, refund rules, official links, unavailable channels, or unavailable products in the evaluated run.

## Recommended Reading Order

1. `ACTUAL_AGENT_CONTRACT.md` for what the agent actually emits.
2. `ACTUAL_SALES_POLICY_FLOW.md` for the current routing flow.
3. `EVALUATION_CONTRACT.md` for what the harness scores.
4. `THREE_WAY_ALIGNMENT.md` for mismatches across implementation, intended architecture, and validation expectations.
5. `EVALUATION_ROOT_CAUSES.md` for likely causes of current score failures.
6. `TOKEN_COST_AUDIT.md` for cost and latency evidence.

## Audit Stop Point

This audit stops at documentation. It intentionally does not alter:

- runtime code
- prompts
- gold validation dataset
- database migrations or schemas
- scoring thresholds
- environment variables
