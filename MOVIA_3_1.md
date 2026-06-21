# MOVIA REQUIREMENT SEMANTICS V3.1 — OBSERVED PROBLEMS, REQUESTED CAPABILITIES, REQUESTED ACTIONS AND FULL LIVE REPLAY

## Purpose

The current MovIA architecture is structurally sound:

* the Analyzer LLM produces linguistic observations;
* deterministic normalization prevents impossible states;
* deterministic derivation calculates commercial consequences;
* the Sales Policy Planner selects stages, actions and CTAs;
* the response generator writes the natural WhatsApp response;
* parallel objection handling, memory, source routing and claim constraints already exist;
* Analyzer V3 targeted validation eliminated the previously defined critical failures.

The remaining semantic problem is that the analyzer currently mixes:

1. a business problem the lead is describing;
2. a capability the lead explicitly wants the future MovIA agent to perform;
3. an external action the lead wants the future MovIA agent to execute.

This causes valid but semantically incorrect states.

Example:

```text
User:
“Tenemos una clínica dental y nos llegan muchos WhatsApps de anuncios.”

Incorrect interpretation:
requested capability = answer_questions
action requirement = answers_only
recommended product = MovIA Captura
macro action = recommend_solution
```

The user described a situation, but did not yet say what the future agent must do.

The correct interpretation is:

```text
observed business problem = high message volume
business type = dental
channel = WhatsApp
requirement class = unknown
recommended product = none
macro action = discover_need
```

This plan introduces strict separation between:

```text
observed_business_problems
requested_agent_capabilities
requested_agent_actions
```

It also separates the current-turn requirement signal from the persisted lead requirement profile, so the absence of a new requirement in a later message cannot erase previously confirmed needs.

After implementation, run the full live Atomic and Coherent suites exactly once each.

---

# EXECUTION MODE

This is a four-phase master plan.

Do not implement all four phases in one run.

For the first Codex run:

1. Read the complete specification.
2. Inspect the repository and current Analyzer V3 implementation.
3. Read:

   * `PLAN_ANALYZER_V3.md`
   * Analyzer V3 architecture documents
   * Analyzer V3 Phase 1–4 reports
   * Analyzer V3 targeted source run: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260606T235650Z-1df8be/`
   * Analyzer V3 targeted passed artifact: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`
   * Atomic live OpenAI baseline: `artifacts/evaluations/phase6-atomic-db-openai/movia-eval-20260606T193317Z-bd6909/run.json`
   * Coherent live OpenAI baseline: `artifacts/evaluations/phase6-coherent-db-openai/movia-eval-20260606T194627Z-44595c/run.json`
   * current analyzer schema and prompt
   * normalizer and derivation services
   * lead-profile merge logic
   * Sales Policy Planner
   * product-fit resolver
   * stage transition logic
   * direct-close gates
   * evaluation contracts and metrics
4. Create:

   * `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`
5. Document:

   * all four phases;
   * dependencies;
   * files expected to change;
   * contract-version changes;
   * migrations, if any;
   * tests;
   * evaluation commands;
   * risks;
   * unresolved repository conflicts.
6. Implement **Phase 1 only**.
7. Run Phase 1 offline tests.
8. Produce:

   * `docs/implementation/PHASE_REQUIREMENT_V3_1_REPORT.md`
9. Update the plan.
10. Stop.

For later runs, Miguel will explicitly request:

```text
Continue PLAN_REQUIREMENT_SEMANTICS_V3_1.md.
Implement Phase N only.
Run only the Phase N tests, update the plan, produce the phase report, and stop.
```

---

# GLOBAL RESPONSIBILITY BOUNDARIES

## Analyzer LLM

The Analyzer LLM observes language.

It may identify:

* current conversational intent;
* facts about the lead or business;
* business problems described by the lead;
* capabilities explicitly requested for the future agent;
* external actions explicitly requested for the future agent;
* sales capabilities requested for the future agent;
* explicitly requested product;
* objection candidate;
* purchase readiness;
* prior-conversation reference;
* post-purchase signal;
* literal evidence spans;
* confidence.

It must not decide:

* requirement class;
* product fit;
* recommended product;
* selected product;
* sales stage;
* macro action;
* micro action;
* CTA;
* next question;
* source routing;
* closing permission.

## Deterministic normalization and derivation

Code must calculate:

* valid evidence;
* current-turn requirement delta;
* persisted requirement profile;
* requirement class;
* product fit;
* standard-scope compatibility;
* action count;
* known and missing slots;
* requested/recommended/selected product differences;
* product availability;
* direct-close eligibility;
* contradictions and warnings.

## Sales Policy Planner

Code must decide:

* sales stage;
* macro action;
* micro action;
* next commercial goal;
* CTA;
* next question key;
* objection overlay;
* source plan;
* closing behavior.

## Response generator

The response generator must continue writing the natural response from the compact deterministic package.

Do not redesign its style or tone during this plan.

---

# MODEL RESTRICTIONS

This task changes Codex implementation behavior only.

Do not change the production agent models during this task:

```text
Analyzer model: current gpt-4.1-mini configuration
Response model: current gpt-4.1-mini configuration
Embedding model: current configured embedding model
```

The purpose is to measure the contract improvement independently from a model change.

A future task may benchmark alternative analyzer models.

---

# PHASE 1 — STRICT SEMANTIC ANALYZER CONTRACT

## Objective

Introduce three independent Analyzer LLM fields:

```text
observed_business_problems
requested_agent_capabilities
requested_agent_actions
```

The distinction must be reflected in:

* runtime schema;
* prompt;
* evidence validation;
* trace metadata;
* documentation;
* unit tests.

Do not yet change product recommendation or planner behavior in Phase 1 unless required to compile against the new contract.

---

## 1. Contract version

Bump the analyzer contract from:

```text
3.0
```

to:

```text
3.1
```

Use a minimal corresponding version bump for normalized-turn or commercial contracts only if their public schemas actually change.

Do not preserve independently generated legacy aliases.

If a transitional adapter is required internally:

* derive it exclusively from the V3.1 fields;
* mark it temporary;
* do not allow old and new fields to compete.
* the current runtime still consumes legacy planner-compatible fields, so any temporary adapter must remain one-way from V3.1 semantics into downstream compatibility state.

---

## 2. `observed_business_problems`

This field describes the lead’s current situation, pain, inefficiency or business symptom.

It does not describe what the future agent has been asked to do.

Schema:

```json
{
  "observed_business_problems": [
    {
      "type": "slow_response",
      "evidence_span": "preguntan precios y nadie contesta rápido",
      "observation_strength": "explicit"
    }
  ]
}
```

Initial closed taxonomy should cover current MovIA use cases without becoming excessively broad.

Possible canonical values:

```text
high_message_volume
slow_response
lead_drop_off
repetitive_questions
manual_data_capture
manual_follow_up
missed_leads
disorganized_information
manual_quoting
manual_scheduling
manual_order_processing
support_bottleneck
unknown_business_problem
```

Rules:

* An observed problem may be explicit or strongly implied.
* It requires literal evidence from the current user message.
* It may influence personalization, persuasion and discovery.
* It must never directly set a product recommendation.
* It must never directly set `answers_only`.
* It must never directly set `external_actions_required`.

Examples:

```text
“Nos llegan muchos mensajes.”
→ high_message_volume
```

```text
“Preguntan precios y nadie responde rápido.”
→ slow_response + lead_drop_off
```

```text
“Todo lo registramos manualmente.”
→ manual_data_capture
```

---

## 3. `requested_agent_capabilities`

This field describes behavior the lead wants the **future MovIA agent** to perform inside the conversational channel, without an external operational side effect.

Schema:

```json
{
  "requested_agent_capabilities": [
    {
      "type": "answer_customer_questions",
      "evidence_span": "solo quiero que responda dudas",
      "requirement_strength": "explicit"
    }
  ]
}
```

Informational/conversational capability taxonomy:

```text
answer_customer_questions
provide_prices
provide_catalog_information
capture_lead_data
qualify_leads
redirect_to_human
understand_audio
understand_images
explain_business_process
collect_order_information
```

Commercial/sales capability taxonomy:

```text
persuade_leads
handle_sales_objections
recommend_products_commercially
close_sale
```

Rules:

* The capability must be requested for the future agent.
* A current question directed at the MovIA salesperson is not automatically a requested future-agent capability.
* Literal evidence is mandatory.
* `requirement_strength` may be:

  * `explicit`
  * `unambiguous_implicit`
* Do not emit weak inferred capabilities.
* Weak assumptions belong in observed problems or nowhere.

Critical distinctions:

```text
“¿Cuánto cuesta Captura?”
→ current intent = pricing_question
→ requested_agent_capabilities = []
```

```text
“Quiero que mi agente les dé los precios.”
→ requested_agent_capabilities = [provide_prices]
```

```text
“Los clientes preguntan precios.”
→ observed_business_problem
→ not a requested capability
```

```text
“Quiero que el agente cierre ventas.”
→ requested_agent_capabilities = [close_sale]
→ not answer_customer_questions
```

---

## 4. `requested_agent_actions`

This field describes external operational actions, integrations or side effects the lead wants the future agent to execute.

Schema:

```json
{
  "requested_agent_actions": [
    {
      "type": "generate_quote",
      "evidence_span": "necesito que cotice",
      "requirement_strength": "explicit"
    },
    {
      "type": "write_external_system",
      "evidence_span": "que registre pedidos en mi sistema",
      "requirement_strength": "explicit"
    }
  ]
}
```

Canonical values:

```text
schedule_appointment
generate_quote
create_order
read_external_system
write_external_system
update_external_record
send_reminder
follow_up_lead
send_notification
take_payment
unknown_external_action
```

Rules:

* Literal evidence is mandatory.
* The action must be requested for the future agent.
* Merely mentioning that the business currently performs an action manually does not necessarily mean the future agent must perform it.
* When the desired automation is unambiguous but the exact action type is unclear, use `unknown_external_action`.
* At least one external-action observation is enough to derive an external-action requirement later.

Examples:

```text
“Quiero que agende pacientes.”
→ schedule_appointment
```

```text
“Necesito que cotice y registre pedidos en mi sistema.”
→ generate_quote + create_order + write_external_system
```

```text
“Actualmente mi recepcionista agenda todo manualmente.”
→ observed problem = manual_scheduling
→ requested action remains empty unless automation is requested
```

---

## 5. Declared action count

Add an independent extracted fact for statements such as:

```text
“Son como cinco acciones.”
```

Suggested field:

```json
{
  "declared_external_action_count": 5
}
```

Rules:

* It is an observation, not a product decision.
* It requires literal evidence.
* It may update persisted scope even when the user does not repeat the action names.
* It must not reset previously known actions.

---

## 6. Current intent versus future-agent requirement

The analyzer prompt must explicitly distinguish:

```text
What the user wants MovIA’s sales agent to answer now
```

from:

```text
What the user wants their future purchased agent to do
```

Examples must include:

```text
“Explícame cuánto cuesta.”
→ current intent only
```

```text
“Quiero que el agente explique precios a mis clientes.”
→ future-agent capability
```

```text
“¿Me puedes agendar una llamada?”
→ current conversational request, not necessarily a future-agent action
```

```text
“Quiero que mi agente agende pacientes.”
→ future-agent action
```

---

## 7. Evidence validation

For all three semantic fields:

* evidence must be a literal normalized substring of the current message;
* do not use prior-history text as current evidence;
* do not emit full-message evidence when only a smaller span supports the label;
* invalid evidence is sanitized before runtime normalization;
* sanitized observations are logged;
* sanitization must not cause a complete fallback when the rest of the analyzer output is usable.

---

## 8. Parser shadow

Keep the parser non-authoritative.

Update its telemetry naming to compare:

```text
observed problem candidates
requested capability candidates
requested action candidates
```

Do not let it:

* override the LLM;
* choose a product;
* choose a stage;
* choose a commercial action.

Normalize aliases such as:

```text
WhatsApps
WhatsApp
whatsapp_business
```

before counting parser/LLM conflicts.

Do not expand the parser substantially in this phase.

---

## 9. Phase 1 tests

Add tests covering at least:

```text
Business problem does not become a capability.
Current pricing question does not become provide_prices.
Future-agent pricing behavior becomes provide_prices.
Manual scheduling problem does not automatically become schedule_appointment.
Explicit scheduling request becomes schedule_appointment.
Sales-closing request becomes close_sale.
External-system registration produces write_external_system.
Evidence is literal.
Weak inference cannot create requested capability.
Weak inference cannot create requested action.
Legacy requested_capabilities cannot independently enter runtime.
```

---

## 10. Phase 1 deliverables

Create:

* Analyzer Contract V3.1 code;
* analyzer prompt updates;
* schema/documentation updates;
* parser-shadow telemetry compatibility;
* evidence sanitizer updates;
* Phase 1 tests;
* `docs/architecture/ANALYZER_CONTRACT_V3_1.md`;
* `docs/implementation/PHASE_REQUIREMENT_V3_1_REPORT.md`.

---

## 11. Phase 1 restrictions

* Do not run Atomic.
* Do not run Coherent.
* Do not run targeted live validation.
* Do not call the response generator.
* Do not change product resolution yet.
* Do not change the production agent model.
* Do not modify gold datasets.
* Stop after offline Phase 1 tests pass.

---

# PHASE 2 — DETERMINISTIC REQUIREMENT PROFILE, PRODUCT FIT AND PLANNER INTEGRATION

## Objective

Convert the three semantic observation fields into a persistent deterministic requirement profile.

The current turn must contribute a delta.

It must not replace the entire persisted profile.

---

## 1. Current-turn requirement delta

Create a deterministic result such as:

```json
{
  "current_turn_requirement_delta": {
    "update_type": "merge",
    "new_observed_problems": [],
    "new_informational_capabilities": [],
    "new_sales_capabilities": [],
    "new_external_actions": [],
    "declared_external_action_count": null
  }
}
```

Canonical update types:

```text
no_update
merge
explicit_correction
explicit_removal
```

The absence of new requirements means:

```text
no_update
```

It does not mean:

```text
unknown
```

---

## 2. Persisted requirement profile

Create or extend a persistent structure such as:

```json
{
  "requirement_profile_version": "1.0",

  "observed_business_problems": [],

  "informational_capabilities": [],

  "sales_capabilities": [],

  "external_actions": [],

  "declared_external_action_count": null,

  "requirement_class": "unknown",

  "first_confirmed_turn": null,
  "last_updated_turn": null,

  "sources": {}
}
```

Persist:

* canonical type;
* evidence;
* source turn;
* confidence/strength;
* active status.

Do not persist hidden reasoning.

Default persistence strategy:

* store the requirement profile under `movia_lead_profiles.profile_data.requirement_profile`;
* do not add a dedicated DB column or normalized requirement tables unless a later phase proves JSONB storage is insufficient.

---

## 3. Merge semantics

Rules:

```text
No new requirement in current turn
→ preserve persisted profile
```

```text
New capability/action
→ union/merge with persisted profile
```

```text
Explicit correction
→ replace the corrected item
```

```text
Explicit removal
→ remove only the explicitly rejected item
```

Examples:

```text
Turn 5:
“Necesito cotizar y registrar pedidos.”
→ external actions persisted
```

```text
Turn 6:
“Son como cinco acciones.”
→ preserve existing external actions
→ update declared action count to 5
```

```text
Turn 7:
“En realidad ya no necesito que agende.”
→ remove schedule_appointment only
```

Never reset the profile merely because the current message lacks a new capability.

---

## 4. Deterministic requirement class

Create a canonical derived enum:

```text
unknown
informational_only
external_actions
sales_persuasion
mixed_advanced
```

Rules:

```python
if sales_capabilities and external_actions:
    requirement_class = "mixed_advanced"

elif sales_capabilities:
    requirement_class = "sales_persuasion"

elif external_actions:
    requirement_class = "external_actions"

elif informational_capabilities:
    requirement_class = "informational_only"

else:
    requirement_class = "unknown"
```

Observed business problems must not affect this calculation.

If backward compatibility requires `action_requirement`, derive it from `requirement_class`. Do not maintain independent values.

---

## 5. Deterministic product fit

Use current official product policies as the source of truth.

Minimum behavior:

```text
unknown
→ no recommendation
→ discovery
```

```text
informational_only
→ MovIA Captura
```

```text
external_actions
→ MovIA Híbrido when within standard supported scope
```

```text
sales_persuasion
→ MovIA Ventas conceptual fit
→ currently unavailable
```

```text
mixed_advanced
→ do not silently recommend Captura
→ explain availability/scope
→ require clarification or custom review
```

External-action count:

```text
1–2 supported actions
→ standard Híbrido fit
```

```text
more than 2 actions
→ exceeds standard Híbrido scope
→ custom scope review required
→ do not promise standard-package coverage
```

Do not automatically recommend Pro Comercial unless current official policy explicitly permits it.

---

## 6. Requested, recommended, confirmed and selected product

Maintain separately:

```text
requested_product
recommended_product
confirmed_product
selected_product
```

Rules:

* `requested_product`: explicitly mentioned preference.
* `recommended_product`: deterministic fit.
* `confirmed_product`: product whose fit has been communicated and accepted.
* `selected_product`: available product the user explicitly chooses.

Do not overwrite a requested product with a recommendation.

Do not treat a recommendation as user confirmation.

---

## 7. Product-fit mismatch

Derive:

```text
product_preference_mismatch
unsupported_scope
product_unavailable
custom_scope_review_required
```

Examples:

```text
User requests Híbrido but only informational needs are known
→ explain difference
→ ask whether external actions are required
```

```text
User requests Captura but needs external-system writes
→ block Captura recommendation
→ explain Híbrido requirement
```

```text
User requests Ventas
→ acknowledge requested product
→ explain current unavailability
```

---

## 8. Discovery before recommendation

Planner rule:

```text
requirement_class = unknown
→ do not recommend a product
→ discover_need or answer_and_advance with a requirement question
```

Recommended discovery question:

```text
“¿Buscas únicamente responder y filtrar esos mensajes o también necesitas acciones como agendar, cotizar o registrar información en otro sistema?”
```

Do not ask already-known business type, channel or pain.

Observed problems may personalize the question but cannot skip discovery.

---

## 9. Sales capabilities

Ensure:

```text
persuade_leads
handle_sales_objections
close_sale
```

never derive Captura.

They should derive:

```text
sales_persuasion
→ MovIA Ventas conceptual fit
→ unavailable now
```

The response may explain what current available products can and cannot do without misrepresenting them as sales agents.

---

## 10. Direct-close gate

Before `direct_close`, require:

```text
explicit_start_intent = true
```

and:

```text
confirmed_product or selected_product exists
```

and:

```text
selected/confirmed product is currently available
```

and:

```text
no unresolved requirement mismatch
```

and:

```text
no unsupported scope
```

If the user says:

```text
“Pásame el link y ya.”
```

but product fit is unresolved or inconsistent with persisted needs:

```text
do not direct-close with a guessed product
→ clarify product/scope first
```

If the product is confirmed and compatible:

```text
direct close is allowed
```

---

## 11. Planner integration

Update planner inputs to consume:

```text
requirement_profile
requirement_class
requested_product
recommended_product
confirmed_product
selected_product
scope flags
known slots
missing slots
```

Do not read legacy independently generated product-fit values.

Update:

* stage logic;
* macro-action selection;
* micro-action mapping;
* CTA selection;
* next-question selection;
* product recommendation;
* closing permission.

Preserve parallel objection behavior.

---

## 12. Response-package integration

Provide only the compact requirement summary needed by the generator:

```json
{
  "observed_problems": [],
  "confirmed_requirements": {
    "informational_capabilities": [],
    "sales_capabilities": [],
    "external_actions": []
  },
  "requirement_class": "external_actions",
  "recommended_product": "movia_hibrido",
  "scope_flags": []
}
```

Do not send the complete analyzer observation and complete persisted profile redundantly if the generator does not need both.

Preserve existing response style.

---

## 13. Phase 2 tests

Required regressions:

### Situation only

```text
“Tengo una clínica dental y recibimos muchos WhatsApps.”
```

Expected:

```text
observed problem present
requirement class unknown
no product recommendation
discovery
```

### Situation plus informational request

```text
“Recibimos muchos mensajes y solo quiero que responda dudas.”
```

Expected:

```text
informational_only
Captura
```

### Situation plus external action

```text
“Recibimos muchos mensajes y también quiero que agende.”
```

Expected:

```text
external_actions
Híbrido
```

### Current question, not future capability

```text
“¿Cuánto cuesta Captura?”
```

Expected:

```text
pricing intent
no requested future-agent capability
```

### Future pricing capability

```text
“Quiero que el agente les dé precios a mis clientes.”
```

Expected:

```text
provide_prices
informational_only
```

### Sales requirement

```text
“Quiero que cierre ventas automáticamente.”
```

Expected:

```text
close_sale
sales_persuasion
Ventas conceptual fit
unavailable
never Captura
```

### Persisted external actions

```text
Turn 1:
“Necesito cotizar y registrar pedidos en mi sistema.”

Turn 2:
“Son como cinco acciones.”
```

Expected:

```text
external actions preserved
declared count = 5
custom scope review required
```

### Explicit start with mismatch

```text
Persisted requirement:
external system + 5 actions

User:
“Pásame el link y ya.”
```

Expected:

```text
do not close as Captura
clarify product/scope
```

### Explicit start after confirmation

```text
Confirmed compatible Híbrido
User:
“Pásame el link.”
```

Expected:

```text
direct close allowed
```

---

## 14. Phase 2 deliverables

Create:

* requirement-delta service;
* persisted requirement-profile service;
* deterministic requirement-class resolver;
* product-fit resolver changes;
* planner integration;
* direct-close gate;
* response-package compatibility;
* persistence migration if needed;
* tests;
* `docs/architecture/REQUIREMENT_PROFILE_V3_1.md`;
* `docs/implementation/PHASE_REQUIREMENT_V3_2_REPORT.md`.

---

## 15. Phase 2 restrictions

* Do not run Atomic.
* Do not run Coherent.
* Do not run targeted live suites.
* Do not run Adaptive Hybrid.
* Do not change the production LLM models.
* Stop after offline tests pass.

---

# PHASE 3 — OFFLINE REGRESSION, EVALUATOR ALIGNMENT AND LIVE SMOKE

## Objective

Complete all offline validation and evaluator compatibility before spending tokens on the full live replay.

---

## 1. Evaluator alignment

Update evaluators to read the new canonical fields.

Do not change:

* user messages;
* scripted lead turns;
* ideal visible responses;
* commercial policies;
* thresholds merely to make the new implementation pass.

Minimal schema/path migration is allowed.

Document every evaluator adjustment.

---

## 2. Add semantic metrics

Add or expose these deterministic checks:

```text
problem_capability_leakage
current_question_future_capability_leakage
requirement_profile_reset
premature_product_recommendation
sales_capability_misrouted
external_action_scope_miss
wrong_product_direct_close
unsupported_standard_scope_claim
```

Definitions:

### `problem_capability_leakage`

A business problem was incorrectly treated as a requested future-agent capability.

### `current_question_future_capability_leakage`

A question directed at MovIA was incorrectly treated as a future-agent requirement.

### `requirement_profile_reset`

A later turn erased known requirements without explicit correction/removal.

### `premature_product_recommendation`

A product was recommended while requirement class remained unknown.

### `sales_capability_misrouted`

A sales requirement was routed to Captura or Híbrido as though it were only informational.

### `external_action_scope_miss`

The agent failed to preserve or count required external actions.

### `wrong_product_direct_close`

The agent closed with a product inconsistent with the persisted requirement profile.

---

## 3. Offline tests

Run the complete offline test suite as many times as needed until green.

Offline iterations are allowed.

Include:

* analyzer contract tests;
* evidence sanitizer tests;
* normalizer tests;
* requirement-profile merge tests;
* planner tests;
* stage tests;
* objection tests;
* response-package tests;
* evaluator tests;
* persistence tests;
* full repository test suite.

---

## 4. Static artifact checks

Verify:

* no legacy independent `requested_capabilities`;
* no legacy independent `requested_actions`;
* no product recommendation from observed problems;
* no current-turn empty result resetting persisted profile;
* no direct-close path bypassing product confirmation;
* no response package carrying redundant complete state unnecessarily.

---

## 5. One live smoke only

After all offline tests pass, run exactly one live turn to verify:

```text
OpenAI analyzer accepts V3.1 schema
provider = OpenAI
fallback = 0
normalizer succeeds
DB persistence succeeds
response generator succeeds
token usage is recorded
```

Use one simple non-destructive scenario.

This smoke is operational only.

Do not treat it as behavioral validation.

Do not run a targeted live suite.

Default live DB assumption:

* use the currently configured database by default;
* evaluation isolation relies on `channel="evaluation"` and run-scoped `external_user_id` values already used by the replay runner;
* a separate staging DB is not required by default for V3.1.

---

## 6. Smoke failure behavior

If the one-turn smoke fails because of:

* schema rejection;
* provider timeout;
* DB serialization;
* missing migration;
* runtime exception;

fix the operational defect and repeat only the one-turn smoke.

Do not start the full replay until the smoke passes.

---

## 7. Phase 3 deliverables

Create:

* evaluator compatibility changes;
* semantic metrics;
* complete offline test results;
* one-turn live smoke artifact;
* provider/fallback confirmation;
* `docs/implementation/PHASE_REQUIREMENT_V3_3_REPORT.md`.

---

## 8. Phase 3 restrictions

* Do not run Atomic.
* Do not run Coherent.
* Do not run Adaptive Hybrid.
* Do not modify agent behavior based on a live full-suite result because no full suite is run in this phase.
* Stop after offline tests and the one-turn live smoke pass.

---

# PHASE 4 — ONE-TIME FULL LIVE ATOMIC AND COHERENT REPLAY

## Objective

Run the complete live Atomic and Coherent suites exactly once each after the implementation is frozen.

This phase is evaluation, not an automatic development loop.

---

## 1. Freeze behavior before running

Before the replay:

* all offline tests must pass;
* the live smoke must pass;
* commit or record the exact code revision;
* record all contract versions;
* record model configuration;
* record DB mode;
* record evaluator version.

Do not change code after beginning the full replay.

---

## 2. Live configuration

Required:

```text
OpenAI enabled
Analyzer provider = OpenAI
Response provider = OpenAI
DB persistence enabled
Fallback count must be reported
Agent behavior evaluated = true
```

Keep:

```text
Analyzer model = current gpt-4.1-mini
Response model = current gpt-4.1-mini
```

Use the same comparable settings as the previous valid live baseline.

Do not run:

```text
Adaptive Hybrid
RAGAS
DeepEval
new external judge suites
```

unless they were part of the exact prior baseline being compared.

Preserve normal RAG behavior when naturally selected by the agent.

---

## 3. Exactly two full runs

Execute:

```text
1. Full Atomic live replay
2. Full Coherent live replay
```

Expected scale:

```text
Atomic: current complete Atomic dataset
Coherent: current complete Coherent dataset
```

Do not execute the complete suites more than once.

---

## 4. No automatic development loop

After either full replay completes:

```text
Do not modify runtime code.
Do not modify evaluator code.
Do not modify prompts.
Do not modify gold expectations.
Do not rerun the full suite.
```

If failures appear:

* preserve the artifacts;
* diagnose them;
* report them;
* stop.

The user will decide whether a new development iteration is justified.

---

## 5. Operational retry versus semantic rerun

Allowed:

```text
A transient API failure retries the individual request according to existing bounded retry policy.
```

Allowed:

```text
An interrupted run resumes from its last checkpoint under the same run ID.
```

Not allowed:

```text
Starting a new Atomic or Coherent run after observing a behavioral failure.
```

Not allowed:

```text
Patching the agent and automatically rerunning the suite.
```

Resume is not a new evaluation.

A new run requires explicit user authorization.

---

## 6. Required metadata

Every run must report:

```text
run_id
code revision
analyzer contract version
normalized contract version
commercial contract version
evaluation contract version
OpenAI enabled
analyzer provider
response provider
fallback count
database mode
model names
scenario count
turn count
retry count
resume count
token usage
latency
```

---

## 7. Required comparison

Compare against:

* Atomic live OpenAI baseline: `artifacts/evaluations/phase6-atomic-db-openai/movia-eval-20260606T193317Z-bd6909/run.json`;
* Coherent live OpenAI baseline: `artifacts/evaluations/phase6-coherent-db-openai/movia-eval-20260606T194627Z-44595c/run.json`;
* Analyzer V3 targeted source run: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260606T235650Z-1df8be/`;
* Analyzer V3 targeted passed artifact: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`.

Report separately:

### Contract safety

```text
hard failures
impossible states
false prior references
hallucinated turn numbers
contradictions
fallbacks
```

### Requirement semantics

```text
problem-capability leakage
current-question capability leakage
requirement-profile resets
external-action misses
sales-capability misroutes
premature recommendations
unsupported scope
wrong-product closes
```

### Commercial performance

```text
sales progression
objection handling
stage distribution
macro-action distribution
micro-action distribution
CTA distribution
successful closes
correct non-closes
product recommendation accuracy
```

### Memory

```text
known-slot repetition
historical reference detection
historical reference resolution
prior commitment consistency
cross-lead contamination
```

### Sources and RAG

```text
source routing
RAG activation
retrieved-source count
empty retrievals
context relevance metrics currently available
```

### Response quality

```text
visible response quality
directness
non-repetition
next-step quality
critical response defects
```

### Performance

```text
analyzer tokens per turn
response tokens per turn
total tokens per turn
analyzer latency
response latency
DB/retrieval latency if available
total latency
```

---

## 8. Acceptance interpretation

Atomic remains authoritative primarily for:

* capabilities;
* hard rules;
* classification;
* source routing;
* policy;
* scope;
* regression.

Coherent remains authoritative primarily for:

* progression;
* multi-turn requirement persistence;
* recommendation;
* objections;
* memory use;
* closing.

Do not compare Atomic and Coherent progression as if they measure the same thing.

---

## 9. Adaptive Hybrid decision

Do not run Adaptive Hybrid automatically.

At the end, return one recommendation:

```text
NOT READY FOR ADAPTIVE HYBRID
```

or:

```text
READY FOR ADAPTIVE HYBRID
```

Recommended minimum gates:

```text
hard failures = 0
fallbacks = 0
impossible states = 0
critical requirement-profile resets = 0
wrong-product direct closes = 0
external-action critical misses = 0
unsupported channel claims = 0
Captura external-action overpromises = 0
premature product recommendations = 0 or explicitly reviewed benign cases
true memory-reference scenarios pass
successful coherent sale can reach an appropriate close
non-closing coherent scenario does not force a close
```

Do not start Adaptive Hybrid in this phase.

---

## 10. Phase 4 deliverables

Create:

* Atomic live artifacts;
* Coherent live artifacts;
* provider/fallback audit;
* V3 previous versus V3.1 comparison;
* requirement-semantics report;
* commercial-progression report;
* token and latency report;
* conversation-readable Markdown output;
* Adaptive Hybrid readiness recommendation;
* `docs/implementation/PHASE_REQUIREMENT_V3_4_REPORT.md`.

---

# GLOBAL COST AND LOOP CONTROLS

## Allowed repetitions

```text
Unit tests:
unlimited offline repetitions as needed.

Static checks:
unlimited offline repetitions as needed.

One-turn smoke:
repeat only for operational/schema failures.

Atomic full live:
one completed run.

Coherent full live:
one completed run.
```

## Forbidden behavior

Do not:

* rerun all live suites after every code fix;
* patch behavior after inspecting a completed full replay;
* optimize thresholds to force a pass;
* silently use fallback and call the run live;
* change production agent models during comparison;
* run Adaptive Hybrid;
* run additional targeted live suites;
* deploy automatically.

---

# FINAL TARGET ARCHITECTURE

```text
load memory
→ shadow parser
→ Analyzer V3.1
    ├─ observed business problems
    ├─ requested future-agent capabilities
    └─ requested future-agent actions
→ evidence sanitizer
→ current-turn requirement delta
→ persisted requirement-profile merge
→ deterministic requirement class
→ deterministic product-fit resolver
→ Sales Policy Planner
→ stage transition
→ objection overlay
→ source planning
→ compact response package
→ response generator
→ critical output validation
→ persistence
```

The final responsibility boundary must remain:

```text
LLM observes.
Code normalizes and derives.
Planner decides.
Generator writes.
```

Start by creating `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`, implement Phase 1 only, run Phase 1 offline tests, produce the report, update the plan, and stop.
