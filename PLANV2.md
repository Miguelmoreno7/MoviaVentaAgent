# MOVIA SALES AGENT V2 — COMMERCIAL CONTRACT ALIGNMENT, IMPLEMENTATION AND RE-EVALUATION

We completed a read-only audit of the current MovIA sales agent.

Use the following audit documents as mandatory source material:

* `docs/audit/ACTUAL_AGENT_CONTRACT.md`
* `docs/audit/ACTUAL_SALES_POLICY_FLOW.md`
* `docs/audit/EVALUATION_CONTRACT.md`
* `docs/audit/THREE_WAY_ALIGNMENT.md`
* `docs/audit/EVALUATION_ROOT_CAUSES.md`
* `docs/audit/TOKEN_COST_AUDIT.md`
* `docs/audit/MOVIA_AGENT_AUDIT_REPORT.md`

This task is no longer an audit.

The goal is to implement a complete, internally consistent commercial contract for the MovIA conversational sales agent and then rerun the deterministic 60-turn validation.

Do not optimize for passing the test through weaker expectations. Fix the runtime contract, then align the evaluator to the same authoritative contract.

---

# 1. Current confirmed problems

The audit confirmed:

1. The LangGraph skeleton is structurally correct.
2. `intent`, `topics`, `objection_type`, and `buying_signal` currently allow free-form strings.
3. `micro_action`, `cta_type`, and `objection_flow_step` also allow free-form strings.
4. The schema declares 13 macroactions, but several are unreachable.
5. The baseline emitted only:

   * `handle_objection`
   * `recommend_solution`
   * `direct_close`
   * `handoff_to_miguel`
6. `current_stage` is derived directly from the current macroaction.
7. There is no independent persistent sales-stage machine.
8. `wants_to_start` is frequently overclassified.
9. `wants_to_start` has enough priority to force premature `direct_close`.
10. The objection methodology is not implemented as a persistent multistep flow.
11. Every objection currently restarts at `first_response`.
12. RAG routing is too limited.
13. The evaluator expects actions, stages and source labels that runtime cannot currently emit.
14. Response generation accounts for most token use because complete config objects are repeatedly serialized.

Preserve the parts that already work:

* commercial accuracy
* official pricing
* policies
* scope control
* memory isolation
* structured sources
* WhatsApp message splitting
* zero hard failures

Do not regress these categories.

---

# 2. Implementation principles

The final architecture must follow these principles:

## 2.1 LLM responsibilities

The analysis LLM may:

* interpret natural language;
* identify canonical intents;
* identify explicit user signals;
* extract lead information;
* identify possible objections;
* estimate confidence.

The response LLM may:

* formulate the final natural response;
* adapt tone;
* explain value;
* persuade within the selected strategy.

## 2.2 Deterministic-code responsibilities

Code must decide:

* current sales stage;
* allowed stage transition;
* macroaction;
* microaction;
* CTA type;
* whether a direct close is permitted;
* which sources are necessary;
* whether RAG is necessary;
* how an objection advances;
* whether a product is available;
* whether information is exact or explanatory.

The response LLM must never choose an arbitrary commercial action.

## 2.3 Contract rule

Runtime, prompts, persisted state, tests and evaluation datasets must consume the same canonical enums.

There must be one authoritative commercial contract.

---

# 3. Execution strategy

Implement this work in six phases.

Do not attempt a blind one-shot rewrite.

For every phase:

1. Document the design.
2. Add or update tests.
3. Implement locally.
4. Run relevant unit tests.
5. Produce a short phase report.
6. Do not apply production migrations.
7. Do not deploy to production.

Create a working branch if the repository uses Git.

Suggested branch:

`feature/movia-commercial-contract-v2`

---

# PHASE 1 — ALIGN AND CLOSE THE TAXONOMY

## 4. Create an authoritative commercial contract

Create:

* `src/movia_sales_agent/contracts/commercial.py`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.json`

Use Pydantic/enum types as the runtime source of truth.

The JSON document may be generated from the code enums or validated against them.

Do not maintain independent duplicate lists manually.

---

## 5. Canonical intent contract

Replace free-form `intent` with:

```text
greeting
general_info
pricing_question
cheapest_plan_question
product_scope_question
product_recommendation_question
platform_steps_question
onboarding_question
policy_question
channel_question
integration_question
industry_fit_question
comparison_question
explicit_start_request
post_purchase_request
support_request
unknown
```

Support compound messages through:

```json
{
  "primary_intent": "pricing_question",
  "secondary_intents": ["industry_fit_question"]
}
```

Do not create free-form compound intent strings.

`secondary_intents` must use the same enum.

---

## 6. Canonical topic contract

Create a closed `Topic` enum.

Initial values:

```text
pricing
product_scope
product_recommendation
platform_process
onboarding
deposit
final_payment
monthly_payment
refund_policy
support
token_usage
whatsapp
facebook
instagram
integration
business_fit
industry_use_case
competitor_comparison
human_handoff
demo
documents
conversation_examples
client_review
activation
post_purchase
unknown
```

The analysis LLM must only return these values.

---

## 7. Canonical objection contract

Create:

```text
none
price_objection
trust_objection
fear_wrong_answers
already_have_person
already_use_whatsapp_business
need_to_think
wants_free_trial
competitor_comparison
not_sure_if_needed
scope_objection
channel_connection_concern
support_concern
```

Add:

```text
objection_strength:
- none
- soft
- hard
```

Important distinction:

A sarcastic or skeptical tone does not automatically mean a blocking objection.

Examples:

```text
“Seguro es otro bot que contesta tonterías.”
```

May be:

```json
{
  "skeptical_tone": true,
  "has_objection": false,
  "objection_type": "none",
  "objection_strength": "soft"
}
```

unless the user is explicitly rejecting or blocking the purchase.

A price question is not a price objection.

```text
“¿Cuánto cuesta?”
```

must not become `price_objection`.

A price objection requires resistance such as:

```text
“Está demasiado caro.”
“No pienso pagar eso.”
“Se sale de mi presupuesto.”
```

---

## 8. Canonical buying-signal contract

Create:

```text
none
low
medium
high
explicit_start
```

Separate:

```text
buying_signal
```

from:

```text
explicit_start_intent
```

`explicit_start_intent` must be a boolean with strict semantics.

It may be true only when the user clearly asks to begin, contract or receive the initiation link.

Positive examples:

```text
“Quiero empezar.”
“Pásame el link.”
“¿Dónde pago?”
“Quiero contratar Captura.”
“Vamos a hacerlo.”
“¿Cómo inicio mi proyecto?”
```

Negative examples:

```text
“¿Cuánto cuesta?”
“Me interesa.”
“Pierdo muchos leads.”
“Quiero que cotice.”
“Dame prueba gratis.”
“Tengo proveedores que mandan tickets.”
```

Code must gate `direct_close` behind `explicit_start_intent`.

Do not use a vague LLM interpretation of “interest” as direct-start intent.

---

## 9. Canonical sales-stage contract

Implement these persistent stages:

```text
new
discovery
educating
comparing
objection_handling
qualified
solution_recommended
ready_to_start
closing
post_purchase
handoff
unknown_recovery
```

Stages must represent conversation progression, not the action selected in the current turn.

Create a migration locally if needed.

Do not apply it to production.

The persisted lead state should include:

```text
current_stage
previous_stage
stage_before_objection
stage_updated_at
stage_reason
```

---

## 10. Canonical macroaction contract

All these macroactions must exist and be reachable:

```text
answer_and_advance
discover_need
narrow_solution
recommend_solution
persuade_value
handle_objection
risk_reversal
compare_alternative
explain_process
soft_close
direct_close
handoff_to_miguel
answer_unknown_safely
```

Add a unit test proving that every macroaction is reachable through at least one valid input state.

No enum value may remain documented but unreachable.

---

## 11. Canonical microaction contract

Replace free-form microactions with a closed enum.

### `answer_and_advance`

```text
answer_price_then_explain_scope
answer_scope_then_discover_business
answer_channel_then_discover_main_channel
answer_process_then_explain_next_step
answer_policy_then_reduce_risk
answer_general_then_discover_need
```

### `discover_need`

```text
ask_business_type
ask_main_channel
ask_pain_or_goal
ask_message_volume
ask_action_requirement
ask_current_process
```

### `narrow_solution`

```text
differentiate_captura_vs_hibrido
determine_if_external_actions_are_needed
route_to_available_products
clarify_action_count
clarify_operational_scope
```

### `recommend_solution`

```text
recommend_movia_captura
recommend_movia_hibrido
recommend_demo
explain_ventas_not_available
explain_pro_comercial_not_available
```

### `persuade_value`

```text
industry_specific_value
logical_value
opportunity_cost
status_quo_cost
response_speed_value
human_team_support_value
```

### `handle_objection`

```text
validate_and_clarify_objection
clarify_objection_value
tie_solution_to_objection
provide_objection_proof
close_or_continue_objection
```

### `risk_reversal`

```text
explain_testing_before_release
explain_client_review
explain_adjustments_before_approval
explain_human_handoff
explain_official_meta_connection
```

### `compare_alternative`

```text
compare_manychat
compare_basic_chatbot
compare_human_receptionist
compare_whatsapp_business_only
compare_custom_development
```

### `explain_process`

```text
explain_app_registration
explain_customer_workspace
explain_demo
explain_agent_creation
explain_deposit
explain_documents
explain_conversation_examples
explain_whatsapp_integration
explain_client_review
explain_final_payment
explain_activation
```

### `soft_close`

```text
invite_to_demo
invite_to_start
confirm_solution_fit
ask_permission_to_send_link
```

### `direct_close`

```text
send_app_link
send_app_link_and_deposit_step
explain_immediate_next_step
```

### `handoff_to_miguel`

```text
redirect_post_purchase
redirect_connection_issue
redirect_custom_scope
redirect_existing_client
```

### `answer_unknown_safely`

```text
clarify_scope
acknowledge_limit
recover_to_automation_need
ask_single_clarifying_question
```

---

## 12. Canonical CTA contract

Create:

```text
none
soft_question
discovery_question
objection_question
explain_next_step
soft_close
ask_permission_to_send_link
send_app_link
direct_close
redirect_to_miguel
```

CTA selection must be deterministic from macroaction/microaction.

The LLM may phrase the CTA naturally, but it cannot select its type.

---

## 13. Canonical objection-flow contract

Implement these milestones:

```text
none
thank_empathize_ask_open_question
clarify_value
tie_solution
provide_proof
close_or_continue
resolved
```

The first milestone represents the first three Salesforce principles in one conversational response:

1. thank;
2. empathize;
3. ask an open question.

Do not send seven objection steps in one answer.

---

## 14. Analyze-turn schema

Update `TurnAnalysis` to return only canonical values.

Suggested shape:

```json
{
  "primary_intent": "pricing_question",
  "secondary_intents": ["industry_fit_question"],
  "topics": ["pricing", "business_fit"],
  "skeptical_tone": false,
  "has_objection": false,
  "objection_type": "none",
  "objection_strength": "none",
  "business_type": "dental",
  "main_channel": "whatsapp",
  "pain": "leads disappear after asking price",
  "urgency": null,
  "buying_signal": "medium",
  "explicit_start_intent": false,
  "is_post_purchase": false,
  "confidence": {
    "intent": 0.92,
    "objection": 0.88,
    "start_intent": 0.97
  },
  "lead_updates": {}
}
```

Use strict structured output.

Reject or normalize unknown enum values.

Do not silently accept free-form taxonomy.

---

## 15. Phase 1 acceptance criteria

Phase 1 is complete when:

* all taxonomies are enum-constrained;
* no free-form objection type is accepted;
* no free-form microaction is accepted;
* all enum values are documented;
* runtime and evaluator can import or load the same contract;
* unit tests cover schema rejection and normalization;
* old traces can be mapped to the new contract where feasible.

Produce:

`docs/implementation/PHASE_1_REPORT.md`

---

# PHASE 2 — COMPLETE THE SALES POLICY PLANNER

## 16. Build the full deterministic policy planner

Refactor the planner so all canonical macroactions are reachable.

Do not ask the response LLM which macroaction should be used.

Planner inputs:

```text
analysis
lead_profile
current_stage
previous_stage
active_objection
last_macro_action
last_micro_action
last_cta
known_product_fit
conversation facts
```

Planner output:

```json
{
  "macro_action": "narrow_solution",
  "micro_action": "differentiate_captura_vs_hibrido",
  "commercial_goal": "Determine whether the lead only needs answers or external actions.",
  "cta_type": "discovery_question",
  "next_question_key": "needs_external_actions",
  "objection_flow_step": "none",
  "target_stage": "qualified",
  "reason_code": "ACTION_REQUIREMENT_UNKNOWN"
}
```

Use stable `reason_code` enums for debugging.

---

## 17. New priority order

Implement this conceptual priority order:

```text
1. Explicit post-purchase/support handoff.
2. Active objection continuation.
3. New hard objection.
4. Explicit start request.
5. Exact informational question.
6. Platform/process/policy explanation.
7. Comparison.
8. Unknown/out-of-scope recovery.
9. Missing discovery information.
10. Need to distinguish Captura vs Híbrido.
11. Recommend solution.
12. Persuade value.
13. Soft close.
```

Important:

`explicit_start_intent` must not always outrank an unresolved hard objection.

Example:

```text
“Dame prueba gratis sin depósito y si funciona pago.”
```

This is not `direct_close`.

It is:

```text
has_objection = true
objection_type = wants_free_trial
macro_action = handle_objection
```

---

## 18. Direct-close gate

Create a deterministic function:

```text
can_direct_close(state) -> bool
```

It should require:

```text
explicit_start_intent == true
AND
is_post_purchase == false
AND
no unresolved hard objection
AND
a valid available product or valid general app entry path
```

A price question must never be sufficient.

A pain description must never be sufficient.

A feature request must never be sufficient.

Add regression tests based on the baseline premature-closing turns.

---

## 19. Discovery and qualification

Define minimum discovery fields:

```text
business_type
main_channel
pain_or_goal
action_requirement
```

`action_requirement` values:

```text
answers_only
external_actions_required
unknown
```

Do not require every field before answering a direct user question.

Use:

```text
answer_and_advance
```

when the user asks an exact question but discovery is incomplete.

Example:

```text
User asks price.
→ answer exact price.
→ ask one missing discovery question.
```

Do not force a generic discovery response before answering.

---

## 20. Product narrowing logic

Implement deterministic rules:

```text
answers_only
→ MovIA Captura candidate
```

```text
external actions required and no more than 2 agreed simple actions
→ MovIA Híbrido candidate
```

```text
sales persuasion requested
→ explain that MovIA Ventas is not currently available
```

```text
advanced agentic/custom consulting requested
→ explain Pro Comercial is not currently available or redirect for custom review
```

Do not sell unavailable products as active.

---

## 21. Persuasion logic

Implement `persuade_value` as a real reachable action.

It should activate when:

* the user asks why MovIA is useful;
* the user asks whether it fits their industry;
* the user is skeptical but not presenting a blocking objection;
* value needs to be explained after discovery;
* a recommendation exists but the user has not shown readiness.

Select a canonical microaction based on available context.

Example:

```text
Dental clinic + leads disappear after asking price
→ industry_specific_value or opportunity_cost
```

---

## 22. Soft-close logic

`soft_close` is not equivalent to `direct_close`.

Use soft close when:

* a suitable product has been recommended;
* the user has medium/high buying signal;
* there is no unresolved objection;
* the user has not explicitly requested the link.

Examples:

```text
“¿Te gustaría probar primero el demo de 10 mensajes?”
“¿Quieres que te explique cómo iniciar el registro?”
“¿Te paso el siguiente paso?”
```

Only move to `ready_to_start`, not necessarily `closing`.

---

## 23. Phase 2 acceptance criteria

* All 13 macroactions have reachable tests.
* Direct close only occurs with explicit start intent.
* The four known premature-closing examples no longer direct-close.
* Skeptical statements can route to `persuade_value`.
* Exact questions route through `answer_and_advance`.
* Captura/Híbrido differentiation is deterministic.
* Every plan contains stable reason codes.

Produce:

`docs/implementation/PHASE_2_REPORT.md`

---

# PHASE 3 — IMPLEMENT A REAL PERSISTENT SALES-STAGE MACHINE

## 24. Separate stage from action

Remove action-to-stage projection as the primary stage mechanism.

`current_stage` must persist independently.

A macroaction describes what to do now.

A stage describes where the lead is commercially.

Example:

```text
current_stage = discovery
macro_action = answer_and_advance
```

This is valid.

Example:

```text
current_stage = solution_recommended
macro_action = handle_objection
```

The temporary response may enter objection handling while preserving the prior stage.

---

## 25. Stage transitions

Implement a deterministic transition service:

```text
SalesStageTransitionService
```

Suggested transitions:

```text
new
→ discovery
```

```text
discovery
→ educating
→ qualified
```

```text
educating
→ discovery
→ qualified
→ comparing
```

```text
qualified
→ solution_recommended
→ comparing
→ objection_handling
```

```text
solution_recommended
→ comparing
→ objection_handling
→ ready_to_start
```

```text
ready_to_start
→ closing
→ objection_handling
```

```text
objection_handling
→ stage_before_objection
→ ready_to_start
→ discovery
```

```text
closing
→ post_purchase
→ handoff
```

```text
unknown_recovery
→ discovery
→ educating
```

Allow controlled nonlinear transitions.

Do not assume every lead follows a linear funnel.

---

## 26. Stage rules

Examples:

* A lead cannot become `qualified` merely because there is an objection.
* A lead cannot become `closing` merely because a direct question was asked.
* `ready_to_start` requires explicit readiness or a confirmed soft close.
* `closing` requires link/payment initiation behavior.
* `post_purchase` requires explicit post-purchase context.
* `objection_handling` stores the previous stage.
* When an objection is resolved, return to the appropriate previous stage.

Persist:

```text
stage_reason_code
stage_entered_at
previous_stage
stage_before_objection
```

---

## 27. Database changes

Create a local migration for the new stage enum/check constraint and new state fields.

Do not apply to production.

If existing data must be migrated, provide a reversible mapping:

```text
qualified → qualified
recommended → solution_recommended
closing → closing
handoff → handoff
unknown → unknown_recovery
```

Document rollback.

---

## 28. Phase 3 acceptance criteria

* `current_stage` is no longer calculated only from macroaction.
* Stage persists between turns.
* Objection handling preserves the previous stage.
* Stage transitions have unit tests.
* Invalid transitions are rejected or explicitly normalized.
* The evaluator reads the persisted real stage.

Produce:

`docs/implementation/PHASE_3_REPORT.md`

---

# PHASE 4 — IMPLEMENT THE SALESFORCE-STYLE OBJECTION FLOW

## 29. Persistent active-objection state

Add a persistent objection state, preferably JSONB or a dedicated model.

Suggested shape:

```json
{
  "active": true,
  "type": "price_objection",
  "strength": "hard",
  "current_step": "thank_empathize_ask_open_question",
  "started_turn": 5,
  "last_updated_turn": 5,
  "stage_before_objection": "solution_recommended",
  "evidence": "Se me hace demasiado caro.",
  "resolved": false
}
```

---

## 30. Objection progression

### First objection turn

Use:

```text
thank_empathize_ask_open_question
```

Goal:

* acknowledge without defensiveness;
* empathize;
* ask one open question to discover the real blocker.

### Next relevant turn

Use:

```text
clarify_value
```

Goal:

* determine whether the blocker is price, trust, uncertainty, scope or timing.

### Next turn

Use:

```text
tie_solution
```

Goal:

* connect the appropriate MovIA capability to the discovered concern.

### When evidence is needed

Use:

```text
provide_proof
```

Proof may include:

* review/testing process;
* official Meta integration;
* client approval before final payment;
* scope guarantees;
* exact product limitations;
* relevant use case.

Do not invent testimonials or numerical outcomes.

### Final step

Use:

```text
close_or_continue
```

Then:

* return to the previous stage;
* soft-close;
* continue discovery;
* mark objection resolved.

---

## 31. Objection continuity rules

* Do not reset the same objection to the first step every turn.
* Do not force objection handling when the user changes topics temporarily.
* Preserve the active objection as paused when appropriate.
* Detect whether a new objection replaces or supplements the existing one.
* Do not treat every skeptical phrase as an objection.
* Do not ask multiple objection questions in one response.
* Do not give a long defensive monologue.

---

## 32. Objection-specific information routing

Only load the relevant objection playbook entry.

Example:

```text
price_objection
→ objection_playbook.price_objection
```

Do not send the complete objection file.

Use RAG only when explanatory evidence is necessary.

Use Postgres for exact prices and policies.

---

## 33. Phase 4 tests

Add multi-turn tests for:

* price objection;
* distrust;
* fear of wrong answers;
* already has an employee;
* already uses WhatsApp Business;
* wants free trial;
* needs to think;
* competitor comparison;
* support concern.

Each test must verify:

* correct type;
* correct step;
* progression between steps;
* no repeated first step;
* return to previous stage;
* no premature direct close.

Produce:

`docs/implementation/PHASE_4_REPORT.md`

---

# PHASE 5 — ALIGN THE EVALUATOR WITH THE AUTHORITATIVE CONTRACT

## 34. Shared contract

The evaluator must consume the same contract version as runtime.

Add:

```text
commercial_contract_version = "2.0"
```

to:

* runtime traces;
* evaluation results;
* gold dataset metadata;
* summary reports.

The evaluator must fail early if contract versions are incompatible.

---

## 35. Validate expected values

The dataset validator currently validates field names but not necessarily runtime vocabulary.

Update it to validate:

* stages;
* macroactions;
* microactions;
* objection types;
* objection-flow steps;
* CTA values;
* source labels.

Invalid or unreachable expected values must fail dataset validation before the agent run.

---

## 36. Align the gold dataset

Update the 60-turn gold dataset only after the runtime contract is implemented.

Do not alter ideal business behavior merely to match current output.

For every turn:

1. Re-evaluate expected stage.
2. Re-evaluate macroaction.
3. Re-evaluate microaction.
4. Re-evaluate objection status.
5. Re-evaluate CTA.
6. Re-evaluate expected sources.
7. Ensure values exist in Contract V2.

Preserve the difficult personas and user messages.

Do not make tests easier.

---

## 37. Source capability alignment

Update source capabilities to reflect actual observable sources.

Decide one canonical approach:

### Option A: granular sources

```text
postgres.products
postgres.product_features
postgres.product_actions
postgres.channels
```

### Option B: bundled source

```text
postgres.products
```

with attached feature/action/channel data.

Use one approach consistently in runtime and evaluator.

Do not expect labels runtime cannot emit.

Add missing RAG documents only if they are genuinely needed:

* beauty/barbershop;
* suppliers/operations;
* home services;
* WhatsApp Business comparison.

Do not create placeholder documents with invented claims.

---

## 38. Improve evaluation reporting

Separate these counters:

```text
hard_failures
rule_failures
soft_trace_mismatches
partial_source_matches
judge_failures
skipped_metrics
not_applicable_metrics
```

Do not present every soft trace mismatch simply as a generic failed metric.

Add root-cause grouping.

Example:

```json
{
  "root_cause": "premature_start_intent",
  "affected_turns": 4,
  "affected_metrics": [
    "current_stage",
    "macro_action",
    "micro_action",
    "cta_type",
    "source_selection"
  ]
}
```

Add exact pass-policy thresholds to `summary.md`.

---

## 39. Evaluation rules

Preserve hard-failure detection for:

* incorrect prices;
* invalid deposit percentage;
* false refund claims;
* unavailable channels sold as active;
* unavailable products sold as active;
* Captura overpromising external actions;
* missed post-purchase handoff;
* cross-scenario memory leakage.

Do not weaken these checks.

---

## 40. Phase 5 acceptance criteria

* Runtime and evaluator share Contract V2.
* Dataset contains no unreachable values.
* Unsupported sources are not silently expected.
* Summary separates soft mismatches from hard/rule failures.
* Gold messages remain difficult.
* The test no longer penalizes the runtime for nonexistent vocabulary.

Produce:

`docs/implementation/PHASE_5_REPORT.md`

---

# PHASE 6 — COMPACT RESPONSE CONTEXT AND REDUCE TOKEN COST

## 41. Current baseline

The baseline used approximately:

```text
298,453 total tokens
4,974 average tokens per turn
3,933 average response-input tokens
```

Most cost comes from the response generator.

Do not add more always-on LLM calls in this phase.

---

## 42. Selective JSON loading

Current behavior sends complete config objects.

Change it so the generator receives only:

```text
selected sales action entry
selected microaction entry
selected CTA rule
selected tone subset
selected objection entry if active
selected process step if requested
```

Do not send complete:

* `sales_actions.json`
* `objection_playbook.json`
* `cta_rules.json`
* `platform_steps.json`

unless explicitly required for debugging outside the model prompt.

---

## 43. Symbolic response package

Create a compact response contract.

Example:

```json
{
  "commercial_instruction": {
    "stage": "qualified",
    "macro_action": "narrow_solution",
    "micro_action": "differentiate_captura_vs_hibrido",
    "goal": "Determine whether external actions are required.",
    "cta_type": "discovery_question"
  },
  "lead_context": {
    "business_type": "dental",
    "main_channel": "whatsapp",
    "pain": "leads disappear after asking price",
    "action_requirement": "unknown"
  },
  "official_facts": {
    "captura": {
      "setup": 4900,
      "monthly": 450,
      "external_actions": false
    },
    "hibrido": {
      "setup": 7500,
      "monthly": 550,
      "max_actions": 2
    }
  },
  "playbook_instruction": {
    "ask": "whether the business needs scheduling or only answering"
  },
  "rag_context": []
}
```

The generator does not need debug traces, complete schemas or unrelated products.

---

## 44. Conversation context

Use:

* structured lead profile;
* persistent stage;
* active objection;
* last relevant action;
* a small recent-message window.

Do not blindly send six messages if fewer are relevant.

Implement a simple relevance/recency strategy.

Do not introduce an LLM summarizer in this phase unless justified by measured savings.

The existing conversation-summary table may remain unused until a separate memory feature is designed.

---

## 45. RAG limits

Use:

* only when the knowledge planner requests it;
* top 1–3 chunks;
* metadata filtering;
* deduplication;
* maximum character/token budget.

Do not send five chunks by default.

Structured facts always override RAG.

---

## 46. Prompt caching and static context

Where supported:

* keep stable system instructions stable;
* avoid changing order unnecessarily;
* separate static and dynamic prompt sections;
* enable provider-side prompt caching if available and measurable.

Do not claim savings without measuring them.

---

## 47. Token instrumentation

Log estimated or actual tokens by response-package section:

```text
system_prompt
commercial_instruction
lead_context
official_facts
playbook
rag_context
recent_messages
```

Create:

`docs/implementation/TOKEN_COST_V2_REPORT.md`

Compare before and after.

---

## 48. Phase 6 targets

Targets for the 60-turn replay:

```text
average total agent tokens per turn <= 3,500
average response input tokens <= 2,500
no increase in hard failures
no reduction in commercial accuracy
no reduction in policy compliance
```

Treat these as optimization targets, not reasons to remove required evidence.

Correctness remains the first priority.

Produce:

`docs/implementation/PHASE_6_REPORT.md`

---

# 49. FINAL SCRIPTED REPLAY

After completing all six phases, rerun the exact same five scenarios and 60 user turns using Scripted Replay Only.

Do not run adaptive simulation yet.

Generate a new run ID and preserve the old baseline.

---

## 50. Required before/after comparison

Create:

`docs/evaluation/V1_VS_V2_COMPARISON.md`

Include:

| Metric              | V1 | V2 | Delta |
| ------------------- | -: | -: | ----: |
| Overall score       |    |    |       |
| Commercial accuracy |    |    |       |
| Policy compliance   |    |    |       |
| Scope control       |    |    |       |
| Memory consistency  |    |    |       |
| Source selection    |    |    |       |
| Objection handling  |    |    |       |
| Sales progression   |    |    |       |
| Hard failures       |    |    |       |
| Avg tokens/turn     |    |    |       |
| Avg response input  |    |    |       |
| Avg latency         |    |    |       |
| Direct-close count  |    |    |       |
| RAG turn count      |    |    |       |

Also report:

* action distribution;
* stage distribution;
* objection-type distribution;
* CTA distribution;
* number of premature closes;
* number of repeated objection first steps;
* number of invalid/free-form taxonomy values;
* number of dataset/runtime contract mismatches.

---

# 51. V2 acceptance targets

The implementation should aim for:

```text
hard_failures = 0
commercial_accuracy >= 0.95
policy_compliance >= 0.95
scope_control >= 0.95
memory_consistency >= 0.95
source_selection >= 0.85
objection_handling >= 0.75
sales_progression >= 0.75
overall_score >= 0.85
```

Additional structural requirements:

```text
free_form_taxonomy_values = 0
unreachable_gold_actions = 0
premature_direct_close_cases = 0
repeated_first_response_for_same_objection = 0
```

Do not falsify results to meet these targets.

If a target is not met, report the evidence and remaining root cause.

---

# 52. Regression tests required

Add explicit regression tests for these baseline failures:

## Sarcastic opener

```text
“Vi su anuncio. Seguro es otro bot que contesta tonterías.”
```

Expected:

* not automatically a hard objection;
* answer and explain value;
* ask for business type;
* no direct close.

## Pain description

```text
“De Facebook Ads a WhatsApp. La gente pregunta precio y luego desaparece.”
```

Expected:

* explicit_start_intent = false;
* no direct close;
* narrow Captura versus Híbrido;
* ask whether actions are needed.

## Price question

```text
“Solo responder. ¿Cuánto cuesta?”
```

Expected:

* answer exact Captura price;
* no automatic direct close;
* soft next step.

## Free-trial objection

```text
“Dame prueba gratis sin depósito y si funciona pago.”
```

Expected:

* wants_free_trial objection;
* no direct close;
* explain demo and deposit policy accurately.

## Supplier workflow

```text
“Tengo proveedores que mandan ticket, foto y datos de garantía.”
```

Expected:

* explicit_start_intent = false;
* recognize external/process actions;
* narrow toward Híbrido;
* no direct close.

## ManyChat comparison

Expected:

* comparison intent;
* compare alternative;
* do not treat as generic trust objection;
* use appropriate comparison source.

---

# 53. Future ML readiness

Do not train a machine-learning model in this task.

However, make traces suitable for future supervised training.

Persist or export canonical labels:

```text
primary_intent
secondary_intents
topics
has_objection
objection_type
objection_strength
buying_signal
explicit_start_intent
current_stage
macro_action
micro_action
cta_type
objection_flow_step
reason_code
```

Create:

`docs/ml/FUTURE_CLASSIFIER_DATA_CONTRACT.md`

Explain how evaluation and future real conversations can be exported as training rows.

Do not store hidden chain-of-thought.

Store only observable inputs, canonical labels, confidence and outcomes.

---

# 54. Final deliverables

Provide:

1. Commercial Contract V2 code.
2. Commercial Contract V2 documentation and JSON.
3. Strict analysis schema.
4. Completed deterministic Sales Policy Planner.
5. Persistent stage machine.
6. Persistent objection flow.
7. Database migration files, local only.
8. Updated evaluator and capability contract.
9. Updated 60-turn gold dataset.
10. Context-compaction implementation.
11. Unit and regression tests.
12. New evaluation artifacts.
13. V1 vs V2 comparison.
14. Token-cost comparison.
15. Future classifier data contract.
16. List of files changed.
17. Any unresolved product decisions.

---

# 55. Implementation restrictions

* Do not deploy.
* Do not modify production data.
* Do not weaken hard-failure rules.
* Do not mark unsupported products as available.
* Do not add unverified business claims.
* Do not invent testimonials or sales results.
* Do not add another always-on LLM.
* Do not use free-form commercial labels.
* Do not derive stage solely from current action.
* Do not direct-close without explicit start intent.
* Do not load entire JSON playbooks into every response prompt.
* Do not delete the V1 evaluation artifacts.
* Preserve backward-compatible API behavior where practical.
* Document breaking changes explicitly.

Start by producing a concise file-level implementation plan based on the current repository.

Then execute the six phases sequentially and report results honestly.
