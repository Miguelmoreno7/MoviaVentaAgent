# Evaluation Strategy V3

Date: 2026-06-05  
Contract: `evaluation_contract_version = "3.0"`  
Runtime commercial contract: `commercial_contract_version = "2.0"`

## Purpose

V3 separates what each validation format can fairly measure.

The existing 60-turn difficult-lead replay remains valuable, but its user turns are fixed in advance and do not react to the assistant's actual answers. It is therefore an atomic capability regression suite, not a causal sales-conversation benchmark.

The evaluator must not collapse capability correctness, coherent sales progression, response quality and deployment readiness into one unlabeled score.

## Suite A: Atomic Scripted Capability Replay

Dataset:

`movia_validation_package/movia_difficult_lead_validation_scenarios.json`

Metadata:

```json
{
  "evaluation_contract_version": "3.0",
  "suite_type": "atomic_scripted",
  "causal_continuity": false,
  "agent_contract_version": "2.0",
  "run_mode": "scripted_replay"
}
```

Valid measures:

- deterministic regression;
- intent and action routing diagnostics;
- commercial taxonomy;
- exact information retrieval;
- source routing;
- policy compliance;
- scope control;
- isolated memory usage;
- response to difficult inputs;
- prevention of invalid closing.

Diagnostic-only measures:

- global funnel progression;
- full objection resolution;
- whether the lead became convinced;
- final conversion.

Atomic scripts still emit trace mismatches for stages, actions and objections, but `sales_progression` and `objection_resolution` are `low_diagnostic` for this suite and do not control the primary pass score.

## Suite B: Coherent Scripted Conversations

Dataset:

`movia_validation_package/movia_coherent_scripted_conversations.json`

Metadata:

```json
{
  "evaluation_contract_version": "3.0",
  "suite_type": "coherent_scripted",
  "causal_continuity": true,
  "agent_contract_version": "2.0",
  "run_mode": "scripted_replay"
}
```

This suite contains five deterministic conversations with 8-15 user turns each:

1. Successful sale ending in app registration.
2. Interested lead ending in the 10-message demo.
3. Real blocking objection that is resolved.
4. Lead that should not be closed.
5. Lead whose needs reveal that MovIA Hibrido is required.

Valid measures:

- sales progression;
- stage transitions;
- objection lifecycle;
- recommendation quality;
- soft close;
- direct close;
- conversation coherence.

The expected next lead message in this suite is written to respond coherently to the expected prior assistant behavior. This is the suite where progression and objection resolution become authoritative.

## Suite C: Adaptive Hybrid Predeploy

Interface:

`movia_validation_package/movia_adaptive_hybrid_predeploy_interface.json`

Metadata:

```json
{
  "evaluation_contract_version": "3.0",
  "suite_type": "adaptive_hybrid",
  "predeploy_only": true,
  "enabled": false,
  "run_mode": "adaptive_hybrid"
}
```

Phase 1 defines the interface only. It must not run until Phases 2-5 pass deterministic gates.

Future hybrid runs will combine:

- fixed regression replay;
- adaptive lead simulation that reacts to actual agent responses.

## Applicability Matrix

| Metric | Atomic | Coherent | Adaptive |
|---|---|---|---|
| Commercial accuracy | High | High | High |
| Policy compliance | High | High | High |
| Scope control | High | High | High |
| Intent/action routing | High | High | Medium |
| Source selection | High | High | Medium |
| Memory persistence | Medium | High | High |
| Sales progression | Low diagnostic | High | High |
| Objection resolution | Low diagnostic | High | High |
| Conversion behavior | Not applicable | Medium | High |
| Response quality | Sampled | High | High |

The machine-readable source of truth for this matrix is:

`src/movia_sales_agent/evaluation/contracts_v3.py`

## Reporting Model

Every run should report separate groups:

- `capability`;
- `progression`;
- `memory`;
- `retrieval`;
- `response_quality`;
- `critical_rules`.

Reports must continue to distinguish:

- hard failures;
- deterministic rule failures;
- soft trace mismatches;
- judge failures;
- partial retrieval matches;
- skipped metrics;
- not applicable metrics.

`overall_score` in V3 means the primary applicable score for the suite, not a universal deployment score.

For `atomic_scripted`, the primary applicable score excludes `sales_progression` and `objection_handling` categories from the pass denominator.

For `coherent_scripted`, progression and objection lifecycle are authoritative and included.

For `adaptive_hybrid`, all applicable dimensions become deployment-relevant after deterministic gates pass.

## Dataset Validation Rules

All scripted datasets must include:

```json
{
  "evaluation_contract_version": "3.0",
  "suite_type": "...",
  "causal_continuity": true,
  "agent_contract_version": "2.0",
  "dataset_version": "...",
  "run_mode": "scripted_replay"
}
```

Atomic suite validation:

- exactly five scenarios;
- exactly 60 turns;
- exactly 12 turns per scenario;
- `causal_continuity=false`.

Coherent suite validation:

- at least five scenarios;
- 8-15 turns per scenario;
- ordered turn IDs from 1;
- `causal_continuity=true`.

Adaptive hybrid:

- uses the separate disabled predeploy interface;
- cannot be loaded as a scripted `ValidationDataset` in Phase 1;
- must not be executed before deterministic gates pass.

## Phase 1 Boundary

Phase 1 changes the evaluator contract and datasets only.

It does not change:

- agent runtime behavior;
- objection handling;
- memory logic;
- RAG routing or retrieval;
- migrations;
- evaluation thresholds for deployment;
- previous V2 artifacts.
