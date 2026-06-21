# Commercial Contract V2

Version: `2.0`

`src/movia_sales_agent/contracts/commercial.py` is the runtime source of truth. This document and `COMMERCIAL_CONTRACT_V2.json` are checked against that source by Phase 1 tests.

## Purpose

Commercial Contract V2 closes the sales-agent taxonomy so the analyzer, planner, runtime traces, tests, and evaluator use the same canonical labels.

The analysis LLM may interpret language and extract signals, but deterministic code owns commercial routing decisions. The response LLM may phrase the final WhatsApp response, but it must not invent arbitrary commercial actions.

## Canonical Groups

- `Intent`: primary and secondary user intent labels.
- `Topic`: normalized commercial and knowledge-routing topics.
- `ObjectionType`: closed objection taxonomy, including `none`.
- `ObjectionStrength`: `none`, `soft`, or `hard`.
- `ObjectionRelation`: current-turn relationship to any objection: `none`, `new`, `continuation`, `reaffirmed`, `clarified`, `resolved`, or `unrelated`.
- `ObjectionStatus`: persisted objection lifecycle: `none`, `active`, `paused`, or `resolved`.
- `ConversationMode`: separate overlay mode: `normal` or `handling_objection`.
- `ReferenceType`: prior-message reference category for conversational memory retrieval.
- `BuyingSignal`: `none`, `low`, `medium`, `high`, or `explicit_start`.
- `ActionRequirement`: `answers_only`, `external_actions_required`, or `unknown`.
- `ProductFit`: deterministic product-fit labels for available and unavailable products.
- `SalesStage`: commercial-funnel stage vocabulary. `objection_handling` remains only for migration compatibility and must not be targeted for new persisted stages.
- `MacroAction`: the 13 canonical commercial actions.
- `MicroAction`: closed microactions grouped by macroaction.
- `CTAType`: deterministic CTA categories.
- `ObjectionFlowStep`: milestones for the later persistent objection flow.
- `PlannerReasonCode`: stable debug labels explaining why the deterministic planner chose a route.
- `ActiveObjection`: persisted JSON state for the current objection-flow position.

## Runtime Rules

- `TurnAnalysis.primary_intent`, `secondary_intents`, `topics`, `objection_type`, `objection_strength`, and `buying_signal` are enum-constrained.
- `SalesPlan.macro_action`, `micro_action`, `cta_type`, `objection_flow_step`, `target_stage`, and `reason_code` are enum-constrained.
- `explicit_start_intent` replaces the old broad `wants_to_start` flag.
- `objection_relation` distinguishes new, continuing, clarified, resolved and unrelated objection turns without adding another LLM call.
- `references_prior_message`, `reference_type`, `reference_query`, `referenced_topics`, `explicit_turn_number`, and `reference_confidence` drive conditional memory retrieval.
- A price question is not a price objection.
- A sarcastic or skeptical tone can set `skeptical_tone=true` without forcing `has_objection=true`.
- All 13 macroactions are reachable through deterministic planner branches.
- `direct_close` requires an explicit start request, no post-purchase state, no unresolved hard objection, and a valid available product or general app entry path.
- `target_stage` is emitted by the planner and resolved by `SalesStageTransitionService` against persisted stage state.
- Persisted `current_stage` is updated independently from the current macroaction. `conversation_mode` carries objection-overlay state.
- Soft concerns stay inline by default and do not create a persistent `active_objection`.
- Hard objections persist across turns independently from `current_stage`.
- Active objections advance through canonical `ObjectionFlowStep` values based on semantic relation signals, not turn count.
- Known structured slots are calculated deterministically and exposed as forbidden question keys to prevent repeated discovery.
- Question CTAs must include a canonical `next_question_key`; if no safe question remains, the CTA is downgraded to `none`.
- Prior conversation evidence is retrieved only when the analysis marks a prior-message reference.
- Objection playbook routing loads only the relevant objection entry for the active or newly detected objection.

## Deferred Work

- Phase 5 aligns the gold dataset and evaluator pass/fail contract.
- Phase 6 compacts response context and token usage.
