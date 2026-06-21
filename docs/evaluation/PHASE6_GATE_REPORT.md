# Phase 6 Gate Report

Date: 2026-06-06

## Recommendation

```text
NOT READY
```

Reason: one or more deterministic validation suites failed Phase 6 gates.

Adaptive hybrid was not run because deterministic gates did not pass.

## Database

| Check | Value |
|---|---|
| Ready | true |
| Missing migrations | none |
| Missing columns | none |
| `movia_conversation_messages` rows | 494 |
| `movia_knowledge_chunks` rows | 13 |
| `movia_knowledge_documents` rows | 13 |
| `movia_lead_profiles` rows | 48 |
| `movia_policies` rows | 5 |
| `movia_products` rows | 4 |

## Atomic Scripted DB Deterministic Run

Run ID:

```text
movia-eval-20260606T064839Z-e61463
```

Artifacts:

- `artifacts/evaluations/phase6-atomic-db-deterministic/movia-eval-20260606T064839Z-e61463/run.json`
- `artifacts/evaluations/phase6-atomic-db-deterministic/movia-eval-20260606T064839Z-e61463/summary.md`

Summary:

| Metric | Value |
|---|---:|
| Overall score | 0.9626 |
| Hard failures | 0 |
| Commercial accuracy | 1.000 |
| Policy compliance | 1.000 |
| Scope control | 1.000 |
| Memory consistency | 0.905 |
| Source selection | 0.975 |
| Response quality | 0.887 |
| Sales progression | 0.858 diagnostic |
| Objection handling | 0.967 diagnostic |

Gates:

| Gate | Threshold | Actual | Status |
|---|---:|---:|---|
| Hard failures | 0 | 0 | pass |
| Commercial accuracy | 0.950 | 1.000 | pass |
| Policy compliance | 0.950 | 1.000 | pass |
| Scope control | 0.950 | 1.000 | pass |
| Memory consistency | 0.800 | 0.905 | pass |
| Source selection | 0.700 | 0.975 | pass |
| Response quality | 0.750 | 0.887 | pass |
| Known-slot critical repetitions | 0 | 0 | pass |
| Premature direct closes | 0 | 0 | pass |
| Irrelevant RAG injection | 0 | 0 | pass |

Atomic sales progression and objection handling are diagnostic by V3 design and did not affect the atomic gate.

## Coherent Scripted DB Deterministic Run

Run ID:

```text
movia-eval-20260606T065555Z-7b83ad
```

Artifacts:

- `artifacts/evaluations/phase6-coherent-db-deterministic/movia-eval-20260606T065555Z-7b83ad/run.json`
- `artifacts/evaluations/phase6-coherent-db-deterministic/movia-eval-20260606T065555Z-7b83ad/summary.md`

Summary:

| Metric | Value |
|---|---:|
| Overall score | 0.8454 |
| Hard failures | 0 |
| Commercial accuracy | 1.000 |
| Policy compliance | 1.000 |
| Scope control | 1.000 |
| Memory consistency | 0.872 |
| Source selection | 0.830 |
| Response quality | 0.889 |
| Sales progression | 0.289 |
| Objection handling | 0.816 |

Gates:

| Gate | Threshold | Actual | Status |
|---|---:|---:|---|
| Hard failures | 0 | 0 | pass |
| Commercial accuracy | 0.950 | 1.000 | pass |
| Policy compliance | 0.950 | 1.000 | pass |
| Scope control | 0.950 | 1.000 | pass |
| Memory consistency | 0.800 | 0.872 | pass |
| Source selection | 0.700 | 0.830 | pass |
| Response quality | 0.750 | 0.889 | pass |
| Sales progression | 0.700 | 0.289 | fail |
| Objection handling | 0.700 | 0.816 | pass |
| Known-slot critical repetitions | 0 | 4 | fail |
| Premature direct closes | 0 | 0 | pass |
| Irrelevant RAG injection | 0 | 0 | pass |

## Failure Inventory

Top coherent failed metric counts:

| Failed Metric | Count |
|---|---:|
| `trace.micro_action` | 43 |
| `trace.macro_action` | 41 |
| `trace.current_stage` | 40 |
| `trace.final_cta_type` | 38 |
| `source.expected_recall` | 23 |
| `response_quality.overall` | 20 |
| `response_quality.critical_defects` | 20 |
| `trace.structured_used` | 18 |
| `memory.known_slot_repetition` | 15 |
| `trace.objection_type` | 11 |

Critical response defect counts:

| Defect | Count |
|---|---:|
| `poor_next_step` | 10 |
| `did_not_answer_question` | 8 |
| `asked_known_information` | 4 |

## Result

The migrated database and deterministic atomic capability gates are ready.

The agent is not ready for adaptive hybrid or production pilot because coherent conversation progression and known-slot repetition gates failed.

## OpenAI Replay Addendum

After the deterministic baseline, I retried the live OpenAI path.

Direct OpenAI smoke:

| Check | Result |
|---|---:|
| text `responses.create` | 2.48s |
| JSON-schema `responses.create` | 2.23s |
| two-turn MovIA smoke tokens | 2,389 |

Atomic DB OpenAI run:

| Metric | Value |
|---|---:|
| Run ID | `movia-eval-20260606T193317Z-bd6909` |
| Overall score | 0.9133 |
| Hard failures | 0 |
| Input tokens | 176,473 |
| Output tokens | 19,774 |
| Total tokens | 196,247 |

Coherent DB OpenAI run:

| Metric | Value |
|---|---:|
| Run ID | `movia-eval-20260606T194627Z-44595c` |
| Overall score | 0.8267 |
| Hard failures | 2 |
| Input tokens | 154,954 |
| Output tokens | 18,912 |
| Total tokens | 173,866 |

Combined OpenAI agent tokens:

| Input Tokens | Output Tokens | Total Tokens |
|---:|---:|---:|
| 331,427 | 38,686 | 370,113 |

OpenAI coherent hard failures:

| Conversation | Turn | Failure |
|---|---:|---|
| `MOVIA-COH-004` | 2 | `future_channel_sold_as_available`: response presents Instagram as currently available. |
| `MOVIA-COH-004` | 5 | `captura_scope_overpromise`: response claims MovIA Captura performs unsupported external actions. |

The earlier OpenAI block was not reproduced. No fallback implementation was added in this pass.
