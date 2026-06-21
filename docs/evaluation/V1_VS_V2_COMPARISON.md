# MovIA V1 vs V2 Scripted Replay Comparison

Date: 2026-06-05  
Dataset: `movia_validation_package/movia_difficult_lead_validation_scenarios.json`  
Replay mode: scripted replay only, 5 scenarios, 60 user turns

## Runs

| Run | Artifact | Notes |
|---|---|---|
| V1 baseline | `artifacts/evaluations/movia-eval-20260604T025630Z-4a5bf4/run.json` | Existing baseline from audit. |
| V2 final replay | `artifacts/evaluations/movia-eval-20260605T060417Z-bef7a2/run.json` | Live OpenAI replay with `MOVIA_DISABLE_DATABASE=true`, `--skip-ragas`, `--skip-deepeval`. |
| V2 DB smoke | `artifacts/evaluations/movia-eval-20260605T060323Z-3ec591/run.json` | One-turn DB-mode smoke failed because remote DB lacks Phase 3 stage columns. |

The V2 DB-mode smoke failed on `stage_updated_at` missing from `movia_lead_profiles`. Production migrations were not applied during this replay. To avoid production writes while still measuring live model behavior, the completed 60-turn V2 replay used local seed facts and in-memory evaluation leads with OpenAI enabled.

## Headline Metrics

| Metric | V1 | V2 | Delta |
|---|---:|---:|---:|
| Overall score | 0.7889 | 0.8505 | +0.0616 (+7.8%) |
| Commercial accuracy | 1.0000 | 1.0000 | 0.0000 (0.0%) |
| Policy compliance | 1.0000 | 1.0000 | 0.0000 (0.0%) |
| Scope control | 1.0000 | 1.0000 | 0.0000 (0.0%) |
| Memory consistency | 1.0000 | 1.0000 | 0.0000 (0.0%) |
| Source selection | 0.7685 | 0.8858 | +0.1173 (+15.3%) |
| Objection handling | 0.5083 | 0.5000 | -0.0083 (-1.6%) |
| Sales progression | 0.0750 | 0.4125 | +0.3375 (+450.0%) |
| Hard failures | 0 | 0 | 0 |
| Avg tokens/turn | 4,974.2 | 2,712.8 | -2,261.4 (-45.5%) |
| Avg response input | 3,933.5 | 1,253.1 | -2,680.4 (-68.1%) |
| Avg latency ms | 11,089.4 | 5,780.9 | -5,308.5 (-47.9%) |
| Direct-close count | 12 | 1 | -11 (-91.7%) |
| RAG turn count | 2 | 10 | +8 (+400.0%) |

## Acceptance Targets

| Target | V2 | Status |
|---|---:|---|
| `hard_failures = 0` | 0 | PASS |
| `commercial_accuracy >= 0.95` | 1.0000 | PASS |
| `policy_compliance >= 0.95` | 1.0000 | PASS |
| `scope_control >= 0.95` | 1.0000 | PASS |
| `memory_consistency >= 0.95` | 1.0000 | PASS |
| `source_selection >= 0.85` | 0.8858 | PASS |
| `objection_handling >= 0.75` | 0.5000 | FAIL |
| `sales_progression >= 0.75` | 0.4125 | FAIL |
| `overall_score >= 0.85` | 0.8505 | PASS |
| `free_form_taxonomy_values = 0` | 0 | PASS |
| `unreachable_gold_actions = 0` | 0 | PASS |
| `premature_direct_close_cases = 0` | 0 | PASS |
| `repeated_first_response_for_same_objection = 0` | 0 | PASS |

V2 does not pass the run-level policy because `objection_handling` and `sales_progression` are below threshold.

## Structural Counts

| Count | V1 | V2 | Delta |
|---|---:|---:|---:|
| Premature direct closes | 12 | 0 | -12 |
| Repeated first objection steps | 0 | 0 | 0 |
| Invalid/free-form taxonomy values | 362 | 0 | -362 |
| Dataset/runtime contract mismatches | 62 | 0 | -62 |

## Action Distribution

| Macro action | V1 | V2 | Delta |
|---|---:|---:|---:|
| `answer_and_advance` | 0 | 15 | +15 |
| `answer_unknown_safely` | 0 | 1 | +1 |
| `direct_close` | 12 | 1 | -11 |
| `explain_process` | 0 | 1 | +1 |
| `handle_objection` | 27 | 33 | +6 |
| `handoff_to_miguel` | 2 | 2 | 0 |
| `narrow_solution` | 0 | 4 | +4 |
| `persuade_value` | 0 | 1 | +1 |
| `recommend_solution` | 19 | 0 | -19 |
| `risk_reversal` | 0 | 2 | +2 |

## Stage Distribution

| Stage | V1 | V2 | Delta |
|---|---:|---:|---:|
| `closing` | 12 | 2 | -10 |
| `educating` | 0 | 7 | +7 |
| `handoff` | 2 | 0 | -2 |
| `new` | 0 | 1 | +1 |
| `objection_handling` | 0 | 47 | +47 |
| `qualified` | 27 | 2 | -25 |
| `recommended` | 19 | 0 | -19 |
| `unknown_recovery` | 0 | 1 | +1 |

## Objection-Type Distribution

V1 used many free-form objection labels. V2 emits only Contract V2 labels.

| Objection type | V2 count |
|---|---:|
| `none` | 30 |
| `trust_objection` | 11 |
| `price_objection` | 11 |
| `scope_objection` | 2 |
| `fear_wrong_answers` | 2 |
| `wants_free_trial` | 2 |
| `competitor_comparison` | 1 |
| `support_concern` | 1 |

## CTA Distribution

| CTA | V1 | V2 | Delta |
|---|---:|---:|---:|
| `direct_close` | 12 | 1 | -11 |
| `discovery_question` | 0 | 4 | +4 |
| `explain_next_step` | 0 | 1 | +1 |
| `handoff` | 2 | 0 | -2 |
| `objection_question` | 27 | 33 | +6 |
| `redirect_to_miguel` | 0 | 2 | +2 |
| `soft_close` | 19 | 0 | -19 |
| `soft_question` | 0 | 19 | +19 |

## Token Breakdown

| Operation | V1 tokens | V2 tokens | Delta |
|---|---:|---:|---:|
| `analysis` | 55,409 | 81,714 | +26,305 |
| `response` | 242,999 | 81,056 | -161,943 |
| `embedding` | 45 | 0 | -45 |
| Total | 298,453 | 162,770 | -135,683 |

Response input dropped from 236,009 to 75,186 tokens. The analysis step increased because the V2 structured-output schema is stricter and richer, but the response-context savings more than offset that increase.

## Failure Shape

V2 hard failures: none.

Top V2 soft trace mismatches:

| Metric | Failed count |
|---|---:|
| `trace.micro_action` | 42 |
| `trace.macro_action` | 36 |
| `trace.objection_flow_step` | 32 |
| `trace.final_cta_type` | 32 |
| `trace.current_stage` | 31 |
| `trace.objection_type` | 28 |
| `trace.structured_used` | 17 |
| `source.expected_recall` | 13 |
| `trace.rag_used` | 7 |

Interpretation: the V2 runtime is commercially safer and cheaper, but the planner now remains in `objection_handling` for too much of the replay. That preserves safety and prevents premature close, but it hurts sales progression and aligned objection-flow scoring.

## Result

V2 improves the core safety and cost targets:

- hard failures remain at 0;
- commercial, policy, scope and memory scores remain 1.0000;
- response input is down 68.1%;
- total tokens per turn are down 45.5%;
- premature direct closes are eliminated;
- free-form taxonomy values are eliminated;
- dataset/runtime contract mismatches are eliminated.

V2 still needs follow-up before it can be considered a passing final run:

- reduce over-sticky active objections;
- improve progression out of `objection_handling`;
- recalibrate expected objection-flow continuation when the lead asks unrelated exact questions;
- optionally rerun in full DB mode after applying the Phase 3 and Phase 4 migrations to the evaluation database.
