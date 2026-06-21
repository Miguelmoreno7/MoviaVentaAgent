# MOVIA ANALYZER CONTRACT V3 — SIMPLIFICATION, DETERMINISTIC DERIVATION AND TARGETED VALIDATION

## Purpose

The current MovIA runtime architecture is structurally strong:

* commercial facts come from controlled sources;
* policies and product scope are deterministic;
* sales stages and objections have defined behavior;
* objections operate as a parallel overlay;
* response generation produces generally strong, natural answers;
* the response generator should remain unchanged unless an interface adjustment is strictly required.

The main remaining weakness is `analyze_turn`.

The current analyzer is responsible for too many outputs, including fields that:

* depend on one another;
* can be calculated deterministically;
* can create impossible combinations;
* belong to the Sales Policy Planner rather than language understanding.

Examples of invalid or harmful combinations include:

```text
has_objection = false
objection_type = price_objection
```

```text
references_prior_message = false
reference_type = explicit_turn
explicit_turn_number = 6
```

```text
action_requirement = external_actions_required
known_product_fit = movia_captura
```

The objective of this plan is to redesign the analyzer so that:

1. The LLM only produces independent linguistic observations.
2. Code derives all logically dependent fields.
3. The Sales Policy Planner continues making commercial decisions.
4. The response generator continues only generating the final natural response.
5. A lightweight parser runs in shadow mode to collect high-precision signals without controlling runtime behavior.
6. Existing Atomic and Coherent datasets remain unchanged.
7. Only a targeted subset of the most difficult existing cases is rerun initially.

This is a master plan. Implement one phase at a time.

---

# EXECUTION MODE

Do not implement all phases in one run.

For the first run:

1. Read this complete specification.
2. Inspect the current repository.
3. Read:

   * `PLAN_V3.md`
   * latest Phase V3 reports;
   * current analyzer schema and prompt;
   * current parser or preprocessing code, if any;
   * current normalizers;
   * Sales Policy Planner;
   * stage transition service;
   * objection overlay;
   * response-package builder;
   * latest live Atomic and Coherent run artifacts.
4. Create:

   * `PLAN_ANALYZER_V3.md`
5. Document:

   * four phases;
   * dependencies;
   * affected files;
   * schema changes;
   * compatibility impact;
   * tests;
   * risks;
   * unresolved decisions.
6. Implement **Phase 1 only**.
7. Run Phase 1 tests.
8. Produce:

   * `docs/implementation/PHASE_ANALYZER_V3_1_REPORT.md`
9. Update `PLAN_ANALYZER_V3.md`.
10. Stop.

For later runs, Miguel will request:

```text
Continue PLAN_ANALYZER_V3.md and implement Phase N only.
Run the Phase N tests, update the plan, produce the phase report, and stop.
```

---

# GLOBAL RESPONSIBILITY BOUNDARIES

## Analyzer LLM

The analyzer may only interpret language.

It may identify:

* intent;
* facts explicitly or semantically communicated;
* requested capabilities;
* requested external actions;
* requested product;
* objection candidate;
* purchase-readiness signal;
* prior-conversation reference;
* evidence spans;
* confidence.

It must not decide:

* product fit;
* recommended product;
* sales stage;
* macro action;
* micro action;
* CTA;
* next question;
* source routing;
* closing permission.

## Deterministic normalizer and derivation layer

Code must calculate:

* `has_objection`;
* `has_prior_reference`;
* `explicit_start_intent`;
* `action_requirement`;
* `known_product_fit`;
* `recommended_product`;
* `product_preference_mismatch`;
* known slots;
* missing slots;
* cross-field contradictions;
* whether a candidate output has valid evidence;
* whether a specialist verification would eventually be required.

## Sales Policy Planner

Code must decide:

* sales stage;
* macro action;
* micro action;
* CTA type;
* next question key;
* objection overlay;
* closing permission;
* source plan;
* product recommendation strategy.

## Response generator

The response generator must:

* receive the normalized commercial instruction;
* receive exact official facts;
* receive the selected action;
* receive only relevant memory and RAG context;
* produce the natural WhatsApp response.

Do not ask the response generator to repair analyzer logic.

Do not redesign its tone or writing style in this plan.

---

# PHASE 1 — NEW ANALYZER CONTRACT AND SHADOW PARSER

## Objective

Replace the current redundant analyzer contract with a compact contract containing only independent linguistic observations.

Add a lightweight parser before the analyzer, but run it in shadow mode only.

The parser must not control runtime decisions during this phase.

---

## 1. Create an independent analyzer contract version

Add:

```text
analyzer_contract_version = "3.0"
```

Do not change:

```text
commercial_contract_version
evaluation_contract_version
```

unless required for compatibility metadata.

Create documentation:

* `docs/architecture/ANALYZER_CONTRACT_V3.md`
* `docs/architecture/ANALYZER_CONTRACT_V3.json`

Use the runtime schema as the source of truth.

---

## 2. New analyzer output

The analyzer should return a structure similar to:

```json
{
  "analyzer_contract_version": "3.0",

  "primary_intent": "product_scope_question",
  "secondary_intents": ["pricing_question"],

  "extracted_facts": {
    "business_type": "dental",
    "main_channel": "whatsapp",
    "pain_or_goal": "los leads desaparecen después de preguntar precio",
    "urgency": null
  },

  "requested_capabilities": [
    {
      "type": "answer_questions",
      "evidence_span": "solo quiero que responda dudas"
    },
    {
      "type": "capture_lead_data",
      "evidence_span": "capture datos del paciente"
    }
  ],

  "requested_actions": [],

  "requested_product": {
    "product": "none",
    "evidence_span": null
  },

  "objection_candidate": {
    "type": "none",
    "strength": "none",
    "relation": "none",
    "evidence_span": null
  },

  "purchase_readiness": {
    "level": "medium",
    "evidence_span": "cuánto cuesta"
  },

  "prior_reference": {
    "type": "none",
    "topic_hint": null,
    "evidence_span": null
  },

  "post_purchase_signal": {
    "detected": false,
    "evidence_span": null
  },

  "confidence": {
    "intent": 0.94,
    "facts": 0.90,
    "capabilities": 0.91,
    "actions": 0.93,
    "objection": 0.88,
    "purchase_readiness": 0.82,
    "prior_reference": 0.98,
    "post_purchase": 0.98
  }
}
```

The exact repository syntax may differ, but preserve the responsibility boundaries.

---

## 3. Remove dependent fields from the analyzer

The analyzer must no longer produce:

```text
has_objection
references_prior_message
explicit_turn_number
explicit_start_intent
action_requirement
known_product_fit
recommended_product
sales_stage
macro_action
micro_action
cta_type
next_question
next_question_key
needs_rag
```

Remove old-field runtime use.

Do not preserve competing legacy aliases unless an internal migration absolutely requires temporary compatibility.

If compatibility is temporarily necessary:

* calculate aliases only from the normalized V3 result;
* never let aliases contain independently generated values;
* document their removal.

---

## 4. Canonical requested-capability taxonomy

Create or reuse a closed enum for informational and conversational capabilities.

Initial canonical values:

```text
answer_questions
provide_prices
provide_catalog_information
capture_lead_data
qualify_leads
redirect_to_human
understand_audio
understand_images
explain_process
provide_follow_up_information
```

Do not create product-specific values.

The analyzer identifies what the lead needs, not which product solves it.

---

## 5. Canonical requested-action taxonomy

Create a closed enum for actions that interact with external processes or systems.

Initial canonical values:

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

Examples:

```text
“Quiero que agende pacientes.”
→ schedule_appointment
```

```text
“Necesito que cotice.”
→ generate_quote
```

```text
“Que registre pedidos en mi sistema.”
→ create_order + write_external_system
```

The analyzer must attach a literal `evidence_span` for every requested action.

---

## 6. Requested product

The analyzer may identify a product explicitly mentioned by the user:

```text
none
movia_captura
movia_hibrido
movia_ventas
movia_pro_comercial
unknown_product
```

It must not recommend a product.

Return:

```json
{
  "product": "movia_hibrido",
  "evidence_span": "yo quiero el Híbrido"
}
```

Distinguish later between:

```text
requested_product
recommended_product
selected_product
```

---

## 7. Objection candidate

Reuse the canonical objection enum.

The analyzer should only produce:

```text
type
strength
relation
evidence_span
```

Example:

```json
{
  "type": "price_objection",
  "strength": "hard",
  "relation": "new",
  "evidence_span": "se me hace demasiado caro"
}
```

Remove `has_objection` from the LLM schema.

A price question is not a price objection:

```text
“¿Cuánto cuesta?”
→ type = none
```

Resistance is required:

```text
“No pienso pagar eso.”
→ price_objection
```

---

## 8. Purchase readiness

Keep one canonical readiness observation:

```text
none
low
medium
high
explicit_start
```

Require an evidence span for:

```text
high
explicit_start
```

Examples:

```text
“¿Cuánto cuesta?”
→ medium
```

```text
“Me interesa, explícame el proceso.”
→ high
```

```text
“Pásame el link y ya.”
→ explicit_start
```

Do not return both `buying_signal` and `explicit_start_intent` from the LLM.

---

## 9. Prior-reference contract

Remove from the primary analyzer contract:

```text
explicit_turn
explicit_turn_number
```

Use:

```text
none
implicit_prior_reference
topic_reference
entity_reference
assistant_commitment_reference
```

Examples:

```text
“Como te dije antes, solo quiero respuestas.”
→ implicit_prior_reference
```

```text
“Lo que te comenté de mis proveedores.”
→ topic_reference
topic_hint = "proveedores"
```

```text
“Tú dijiste que el depósito era del 50%.”
→ assistant_commitment_reference
```

Require:

```text
evidence_span
```

when type is not `none`.

Do not require or invent a turn number.

The memory retriever should resolve the reference through topic, entity and evidence, not through a fabricated number.

---

## 10. Evidence-span validation

For these fields, evidence is mandatory:

* requested actions;
* explicit product request;
* objection candidate when type is not `none`;
* explicit/high purchase readiness;
* prior reference;
* post-purchase signal.

The evidence span must:

1. Exist in the current user message.
2. Match after basic normalization:

   * case;
   * accents;
   * whitespace;
   * punctuation.
3. Not be invented from prior context.
4. Be logged for evaluation.

During Phase 1, implement schema and validation behavior.

Do not yet derive all downstream commercial fields.

---

## 11. Shadow parser

Create a lightweight parser node before the analyzer.

Possible graph position:

```text
load_memory
→ parse_explicit_signals_shadow
→ analyze_turn_v3
→ ...
```

The parser may use:

* text normalization;
* regex;
* phrase dictionaries;
* fuzzy matching;
* token or lemma matching where already available.

It should output candidates such as:

```json
{
  "action_candidates": [
    {
      "type": "generate_quote",
      "evidence_span": "que cotice"
    }
  ],
  "product_candidates": [],
  "purchase_cue_candidates": [
    {
      "type": "explicit_start",
      "evidence_span": "pásame el link"
    }
  ],
  "prior_reference_candidates": [],
  "channel_candidates": ["whatsapp"],
  "negation_candidates": []
}
```

Important:

```text
shadow_parser_may_observe = true
shadow_parser_may_override = false
shadow_parser_may_choose_product = false
shadow_parser_may_choose_action = false
```

Do not feed parser results to the LLM during this phase.

Do not use parser results to alter runtime decisions.

Store parser results in traces for later comparison.

---

## 12. Phase 1 tests

Add tests for:

* schema rejects `has_objection`;
* schema rejects `known_product_fit`;
* schema rejects `explicit_turn_number`;
* objection requires evidence;
* prior reference requires evidence;
* explicit start requires evidence;
* requested actions require evidence;
* evidence must exist in the message;
* shadow parser never modifies analyzer result;
* shadow parser never changes planner behavior;
* parser traces are persisted or observable;
* existing response generator remains unchanged.

---

## 13. Phase 1 deliverables

Create:

* Analyzer Contract V3 code;
* Analyzer Contract V3 documentation;
* new analyzer prompt/schema;
* shadow-parser implementation;
* trace output for parser candidates;
* schema tests;
* `docs/implementation/PHASE_ANALYZER_V3_1_REPORT.md`.

---

## 14. Phase 1 acceptance criteria

* Analyzer returns only independent observations.
* No product recommendation is generated by the analyzer.
* No commercial action or stage is generated by the analyzer.
* No redundant booleans are generated.
* No turn number is invented.
* Evidence validation exists.
* Parser runs in shadow mode only.
* Response generator behavior is unchanged.

Stop after Phase 1.

---

# PHASE 2 — DETERMINISTIC NORMALIZATION AND DERIVATION

## Objective

Create a deterministic layer that consumes Analyzer Contract V3 and produces a logically consistent normalized commercial interpretation.

Suggested node:

```text
analyze_turn_v3
→ normalize_and_derive_turn
→ update_lead_state
```

---

## 1. Normalized turn contract

Create a structure such as:

```json
{
  "has_objection": false,
  "has_prior_reference": false,
  "explicit_start_intent": false,
  "is_post_purchase": false,

  "action_requirement": "answers_only",

  "requested_product": "none",
  "recommended_product": "movia_captura",
  "selected_product": null,
  "product_preference_mismatch": false,

  "known_slots": [
    "business_type",
    "main_channel",
    "pain_or_goal",
    "action_requirement"
  ],

  "missing_slots": [],

  "contradictions": [],
  "normalization_warnings": []
}
```

This is not generated by an LLM.

---

## 2. Objection derivation

Derive:

```python
has_objection = objection_candidate.type != "none"
```

If:

```text
type = none
```

force:

```text
strength = none
relation = none
evidence_span = null
```

If evidence is invalid:

```text
objection_candidate = none
```

and log:

```text
invalid_objection_evidence
```

---

## 3. Prior-reference derivation

Derive:

```python
has_prior_reference = prior_reference.type != "none"
```

If evidence is missing or invalid:

```text
prior_reference = none
has_prior_reference = false
```

Never fabricate a turn number.

Historical retrieval runs only when normalized `has_prior_reference=true`.

---

## 4. Explicit-start derivation

Derive:

```python
explicit_start_intent = (
    purchase_readiness.level == "explicit_start"
    and evidence_is_valid
)
```

Examples:

```text
“Pásame el link.”
→ true
```

```text
“¿Cuánto cuesta?”
→ false
```

```text
“Antes de pagar quiero entender.”
→ false
```

---

## 5. Action-requirement derivation

Canonical values:

```text
unknown
answers_only
external_actions_required
```

Rules:

```python
if requested_actions:
    action_requirement = "external_actions_required"

elif requested_capabilities:
    action_requirement = "answers_only"

else:
    action_requirement = "unknown"
```

Do not default to `answers_only`.

No evidence means `unknown`.

---

## 6. Product recommendation derivation

Derive product recommendation through code:

```python
if action_requirement == "answers_only":
    recommended_product = "movia_captura"

elif action_requirement == "external_actions_required":
    recommended_product = "movia_hibrido"

else:
    recommended_product = None
```

Apply official availability separately.

Do not recommend:

```text
movia_ventas
movia_pro_comercial
```

as currently available.

---

## 7. Requested, recommended and selected product

Keep independent:

```text
requested_product
recommended_product
selected_product
```

Derive:

```python
product_preference_mismatch = (
    requested_product not in {None, "none"}
    and recommended_product is not None
    and requested_product != recommended_product
)
```

The user may still select an available product different from the recommendation.

Do not force Captura merely because it is recommended.

If the user explicitly requests Híbrido while the recommendation is Captura:

* explain the fit difference;
* clarify whether external actions are needed;
* allow selection if the user confirms.

If the requested product is unavailable:

* deterministic availability rule overrides;
* do not mark it selected.

---

## 8. Known and missing slots

Calculate known slots from persisted profile plus current extracted facts.

Core commercial slots:

```text
business_type
main_channel
pain_or_goal
action_requirement
```

Do not ask again for a known slot.

Do not treat `known_product_fit` as a required analyzer output.

---

## 9. Cross-field invariant validator

Reject or normalize contradictions such as:

```text
objection type none + hard strength
```

```text
prior-reference type none + evidence
```

```text
explicit start without evidence
```

```text
external actions required + Captura recommendation
```

```text
requested action present + action requirement answers_only
```

```text
unavailable product selected
```

Add:

```text
contradiction_code
original_values
normalized_values
```

to traces.

---

## 10. Parser-versus-LLM telemetry

Compare shadow-parser candidates with analyzer observations.

Record:

```text
agreement
parser_only
llm_only
conflict
```

Do not let the parser override the LLM yet.

Examples:

```text
parser detects generate_quote
LLM detects generate_quote
→ agreement
```

```text
parser detects prior reference
LLM returns none
→ conflict
```

This information will support future regex rules or ML training.

---

## 11. Phase 2 regression tests

Required cases:

### Price question

```text
“¿Cuánto cuesta?”
```

Expected:

```text
no objection
no explicit start
action requirement unknown unless prior context exists
```

### Answers only

```text
“Solo quiero que responda dudas y capture datos.”
```

Expected:

```text
requested capabilities detected
action requirement answers_only
recommended product Captura
```

### External actions

```text
“Necesito que cotice y registre pedidos en mi sistema.”
```

Expected:

```text
generate_quote
create_order
write_external_system
external_actions_required
recommended product Híbrido
never Captura
```

### Explicit start

```text
“No quiero hablar con nadie, pásame el link y ya.”
```

Expected:

```text
explicit_start_intent true
not need_to_think
```

### No historical reference

```text
“Antes de pagar quiero entender cómo empiezo.”
```

Expected:

```text
has_prior_reference false
```

### Historical reference

```text
“Como te dije antes, solo necesito respuestas.”
```

Expected:

```text
has_prior_reference true
valid evidence
```

---

## 12. Phase 2 deliverables

Create:

* deterministic normalizer;
* deterministic derivation service;
* normalized-turn contract;
* invariant validator;
* parser/LLM comparison telemetry;
* tests;
* `docs/implementation/PHASE_ANALYZER_V3_2_REPORT.md`.

---

## 13. Phase 2 acceptance criteria

* Impossible analyzer states cannot reach the planner.
* `action_requirement` never defaults to answers-only without evidence.
* External actions can never derive Captura.
* Historical references require valid evidence.
* Explicit start requires valid evidence.
* Product recommendation is deterministic.
* Parser remains non-authoritative.

Stop after Phase 2.

---

# PHASE 3 — SALES POLICY PLANNER INTEGRATION

## Objective

Adapt the existing deterministic Sales Policy Planner to consume the new normalized contract.

Do not rewrite the planner unnecessarily.

Do not move commercial decisions back into the analyzer.

Do not redesign response wording.

---

## 1. Planner inputs

The planner should consume:

```text
primary_intent
secondary_intents
extracted facts
normalized objection
purchase readiness
explicit_start_intent
action_requirement
requested_product
recommended_product
selected_product
product_preference_mismatch
known_slots
missing_slots
current sales stage
active objection overlay
last action
```

---

## 2. Sales-stage derivation

Sales stage remains deterministic.

General principles:

```text
action requirement unknown
→ discovery
```

```text
informational process/pricing question
→ educating
```

```text
core business context + pain + action requirement known
→ qualified
```

```text
recommendation communicated
→ solution_recommended
```

```text
recommendation accepted or next step requested
→ ready_to_start
```

```text
explicit start + closing allowed
→ closing
```

Do not enter `solution_recommended` merely because:

* business type is known;
* WhatsApp is mentioned;
* the analyzer defaulted a need.

---

## 3. Macro-action rules

Illustrative priority:

```python
if is_post_purchase:
    handoff_to_miguel

elif blocking_hard_objection:
    handle_objection

elif explicit_start_intent and can_direct_close:
    direct_close

elif primary_intent == "pricing_question":
    answer_and_advance

elif primary_intent in PROCESS_INTENTS:
    explain_process

elif primary_intent == "comparison_question":
    compare_alternative

elif action_requirement == "unknown":
    discover_need

elif product_preference_mismatch:
    narrow_solution

elif recommended_product and not recommendation_communicated:
    recommend_solution

elif purchase_readiness in {"high", "explicit_start"}:
    soft_close

else:
    persuade_value
```

The final implementation must follow the current repository's canonical action enum.

---

## 4. Micro-action derivation

Micro action must be selected by deterministic mapping.

Examples:

```text
pricing question
→ answer_price_then_explain_scope
```

```text
action requirement unknown
→ ask_action_requirement
```

```text
external actions required
→ recommend_movia_hibrido
```

```text
answers only
→ recommend_movia_captura
```

```text
product mismatch
→ differentiate_captura_vs_hibrido
```

---

## 5. CTA and next-question rules

Any question CTA requires:

```text
next_question_key != null
```

The next question must be selected from missing information or the commercial action.

Examples:

```text
action requirement unknown
→ next_question_key = action_requirement
```

```text
recommendation communicated
→ next_question_key = confirm_solution_fit
```

```text
explicit start
→ send_app_link
```

Do not let the generator invent generic discovery questions.

---

## 6. Known-slot protection

Before response generation, provide:

```text
known_slots
forbidden_question_keys
```

Examples:

```text
business type known
→ forbid ask_business_type
```

```text
channel known
→ forbid ask_main_channel
```

The response generator may mention known information.

It must not ask for it again.

---

## 7. Response-package constraints

Do not redesign response style.

Only adjust the package so it receives:

* selected macro action;
* selected micro action;
* exact CTA;
* next question;
* official product facts;
* requested capabilities/actions;
* recommended product;
* requested product;
* forbidden claims;
* known slots.

Add deterministic constraints:

```text
Captura may collect order information in WhatsApp.
Captura may not create or register the order in an external system.
```

```text
Only WhatsApp is currently available.
Do not describe any MovIA product as currently multichannel.
```

These constraints prevent the two latest live hard failures.

---

## 8. Phase 3 tests

Add tests proving:

* first business message does not automatically recommend Captura;
* discovery happens when action requirement is unknown;
* Captura is never recommended for external actions;
* explicit-start language is not classified as need-to-think;
* unavailable channels cannot be presented as available;
* unavailable products cannot be presented as available;
* question CTA always has a question key;
* known slots are not asked again;
* response generator receives no analyzer-derived product choice;
* response style/model remain unchanged.

---

## 9. Phase 3 deliverables

Create:

* planner integration;
* stage integration;
* CTA/next-question integration;
* response-package compatibility changes;
* critical claim constraints;
* tests;
* `docs/implementation/PHASE_ANALYZER_V3_3_REPORT.md`.

---

## 10. Phase 3 acceptance criteria

* Analyzer only observes.
* Normalizer only derives.
* Planner only decides.
* Generator only writes.
* No automatic Captura recommendation without evidence.
* No unsupported external-action claims.
* No unsupported channel claims.
* No null question key for question CTAs.
* Existing Atomic/Coherent datasets remain unchanged.

Stop after Phase 3.

---

# PHASE 4 — TARGETED LIVE VALIDATION

## Objective

Validate the new contract using only the most damaging existing cases before rerunning the full 117-turn suites.

Do not modify:

* Atomic dataset;
* Coherent dataset;
* gold expectations;
* thresholds;
* response-quality rubric.

Do not run Adaptive Hybrid.

Do not change models during this phase.

Continue using the current production analyzer model for an apples-to-apples comparison.

---

## 1. Create a targeted-run manifest

Do not copy or rewrite the datasets.

Create a manifest that references existing:

```text
scenario IDs
turn IDs
turn ranges
```

Example location:

* `movia_validation_package/analyzer_v3_targeted_manifest.json`

The manifest must not contain rewritten user messages or gold values.

---

## 2. Required targeted cases

Include at minimum:

### Premature recommendation

From `MOVIA-COH-001`:

* initial dental-clinic message;
* pain clarification;
* answer-only versus external-action clarification;
* first recommendation.

Goal:

```text
Do not recommend Captura before action requirement is known.
```

### External action and Captura hard failure

From `MOVIA-COH-004`:

* “Necesito que cotice y registre pedidos en mi sistema.”
* associated follow-up turns.

Goal:

```text
external_actions_required
recommended_product = MovIA Híbrido
no Captura overpromise
```

### Instagram channel hard failure

From `MOVIA-COH-004`:

* Instagram-only turn;
* related product/channel response.

Goal:

```text
Only WhatsApp currently available.
No unsupported multichannel claim.
```

### Explicit start versus need-to-think

Use the existing turn containing:

```text
“No quiero hablar con nadie, pásame el link y ya.”
```

Goal:

```text
purchase readiness = explicit_start
not need_to_think
```

### False historical references

Select at least 8–12 existing Coherent turns that incorrectly produced:

```text
references_prior_message = true
explicit turn references
```

Include normal messages such as:

```text
“Antes de pagar quiero entender cómo empiezo.”
“Solo quiero que responda dudas.”
“¿Cuánto cuesta Captura?”
```

Goal:

```text
prior reference = none
```

### True historical references

Use turns from:

```text
MOVIA-MEM-001
MOVIA-MEM-002
```

Goal:

```text
real prior references remain detected and resolved.
```

### Sarcastic soft concern

Use the Atomic sarcastic opener.

Goal:

```text
soft inline concern
no impossible objection state
no persistent hard objection
```

### Price question

Use an existing Atomic price turn.

Goal:

```text
pricing intent
not price objection
not explicit start
```

---

## 3. Validation modes

Run two modes.

### A. Analyzer-only replay

Run:

```text
shadow parser
analyzer
normalizer
derivation
planner
```

Do not call the response generator.

Measure:

```text
analyzer input/output tokens
latency
parser/LLM agreement
contradictions before normalization
contradictions after normalization
intent accuracy
objection precision
action requirement accuracy
prior reference precision
explicit start precision
product recommendation correctness
```

### B. Targeted live agent replay

Run the same targeted cases through the full live agent:

```text
OpenAI enabled
DB enabled
response generator enabled
RAG only when naturally selected
```

Do not run RAGAS or DeepEval initially.

---

## 4. Required comparisons

Compare previous V3 live output versus Analyzer Contract V3.

Report:

| Metric                            | Previous V3 | Analyzer V3 | Delta |
| --------------------------------- | ----------: | ----------: | ----: |
| Impossible states                 |             |             |       |
| False prior references            |             |             |       |
| Hallucinated turn numbers         |             |             |       |
| External action misses            |             |             |       |
| Premature Captura recommendations |             |             |       |
| Explicit-start false negatives    |             |             |       |
| Objection contradictions          |             |             |       |
| Hard failures                     |             |             |       |
| Analyzer tokens per turn          |             |             |       |
| Analyzer latency                  |             |             |       |
| Full agent tokens per turn        |             |             |       |

---

## 5. Parser shadow report

Create:

* `docs/evaluation/PARSER_SHADOW_COMPARISON.md`

Include:

```text
parser true positives
parser false positives
parser false negatives
LLM-only correct detections
parser/LLM conflicts
patterns that may later become deterministic rules
patterns that must remain semantic
```

Do not promote parser rules to production behavior in this phase.

---

## 6. Model restriction

Do not change:

```text
gpt-4.1-mini
```

during this targeted validation.

The objective is to measure the effect of the new contract independently from model quality.

A separate future task will benchmark:

```text
gpt-4.1-mini
gpt-5-mini
gpt-5.4-nano
gpt-5.4-mini
```

using the same analyzer-only dataset.

---

## 7. Phase 4 gates

Required:

```text
hard failures = 0
hallucinated turn numbers = 0
impossible normalized states = 0
external action critical misses = 0
Captura external-action overpromises = 0
unsupported channel claims = 0
false prior-reference rate materially reduced
explicit-start critical cases pass
```

Do not require perfect trace agreement for every soft action.

---

## 8. Full replay decision

Only recommend rerunning the full Atomic and Coherent suites if the targeted gates pass.

Do not run full suites automatically.

End with:

```text
TARGETED CONTRACT VALIDATION PASSED
```

or:

```text
TARGETED CONTRACT VALIDATION FAILED
```

and list exact blockers.

---

## 9. Phase 4 deliverables

Create:

* targeted manifest;
* analyzer-only results;
* targeted live results;
* previous-versus-new comparison;
* parser-shadow report;
* token/latency comparison;
* recommendation on full replay;
* `docs/implementation/PHASE_ANALYZER_V3_4_REPORT.md`.

---

# FINAL TARGET ARCHITECTURE

```text
load memory
→ shadow parser
→ analyzer linguistic observations
→ evidence validator
→ deterministic normalization
→ deterministic derivation
→ update structured lead facts
→ Sales Policy Planner
→ stage transition
→ objection overlay
→ knowledge planning
→ structured / JSON / RAG retrieval
→ compact response package
→ response generator
→ critical output validation
→ persistence
```

The contract boundary must remain:

```text
LLM observes.
Code derives.
Planner decides.
Generator writes.
```

Start by creating `PLAN_ANALYZER_V3.md`, implement Phase 1 only, run Phase 1 tests, update the plan, produce the Phase 1 report, and stop.

---

# OPERATIONAL EXECUTION TRACKER

Last updated: 2026-06-07

Current status: Phase 4 completed; targeted contract validation passed and full Atomic/Coherent replay is recommended next.

## Current Decisions

* `PLAN_ANALYZER_V3.md` remains the master analyzer V3 implementation plan.
* Phase 1 introduces `analyzer_contract_version = "3.0"` without changing `commercial_contract_version` or `evaluation_contract_version`.
* The analyzer LLM schema now produces `AnalyzerTurnObservation`, not legacy `TurnAnalysis`.
* Phase 2 adds `NormalizedTurn` as the deterministic derivation layer after analyzer observation.
* Phase 3 passes `NormalizedTurn` into the Sales Policy Planner as an explicit planner input while preserving the current `TurnAnalysis` compatibility object.
* Evidence-backed external-action requirements now route to MovIA Híbrido recommendations unless there is a product-preference mismatch that needs narrowing.
* Unknown action requirement remains discovery and does not default into Captura.
* Response generation packages now include turn-signal context and deterministic claim constraints for channels, unavailable products, and Captura external-action limits.
* The shadow parser is trace-only and cannot override analyzer output, planner decisions, product selection, or runtime actions.
* Parser/LLM comparison telemetry is recorded from normalized turn output.
* Phase 4 targeted manifest is reference-only and does not copy, alter, or reinterpret gold messages.
* Phase 4 final passed artifact is `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`.
* The Phase 4 final artifact rescored completed all-OpenAI live records from `analyzer-v3-targeted-20260606T235650Z-1df8be` after fixing a safe-negation detector false positive.
* Gold datasets and validation expectations remain unchanged.
* No migrations, deployments, RAGAS, DeepEval, adaptive hybrid, or full replay were run in Phase 4.

## Current Repository Conflicts And Risks

* `TurnAnalysis` compatibility conversion still exists for downstream runtime behavior and should not be removed until later phases prove all consumers use normalized fields safely.
* No live OpenAI replay was run with Analyzer Contract V3 in Phase 1.
* The strict OpenAI JSON schema is generated from the runtime Pydantic model with all object properties required.
* Analyzer and full-agent token usage increased in the completed all-OpenAI targeted source run because fallback analysis was eliminated for targeted records.
* A duplicate live targeted rerun after the detector fix hung after creating an empty artifact directory and was terminated; the final report uses the completed all-OpenAI source run and corrected rescore.

## Phase 1: New Analyzer Contract And Shadow Parser

Status: completed.

Depends on:

* Current V3 commercial contract.
* Existing planner, stage, objection, memory, response package and API behavior.
* Latest Phase V3.6 reports and OpenAI replay findings.

Files changed:

* `src/movia_sales_agent/analyzer/__init__.py`
* `src/movia_sales_agent/analyzer/contract_v3.py`
* `src/movia_sales_agent/analyzer/shadow_parser.py`
* `src/movia_sales_agent/models/schemas.py`
* `src/movia_sales_agent/services/openai_service.py`
* `src/movia_sales_agent/agent/graph.py`
* `docs/architecture/ANALYZER_CONTRACT_V3.md`
* `docs/architecture/ANALYZER_CONTRACT_V3.json`
* `tests/test_analyzer_contract_v3.py`
* `docs/implementation/PHASE_ANALYZER_V3_1_REPORT.md`
* `PLAN_ANALYZER_V3.md`

Schema changes:

* Added `AnalyzerTurnObservation`.
* Added requested capability taxonomy.
* Added requested action taxonomy.
* Added requested product taxonomy.
* Added analyzer-specific prior-reference taxonomy without turn numbers.
* Added evidence-span validation for required fields.
* Removed dependent fields from the LLM structured-output schema.

Migrations:

* None.

Tests:

* `.venv/bin/pytest tests/test_analyzer_contract_v3.py -q`
  * Result: 15 passed, 1 warning.
* `.venv/bin/pytest tests/test_agent_policy.py tests/test_response_context.py tests/test_api.py tests/test_objection_flow.py tests/test_memory_v3.py -q`
  * Result: 45 passed, 1 warning.
* `.venv/bin/python -m compileall src/movia_sales_agent/analyzer src/movia_sales_agent/services/openai_service.py src/movia_sales_agent/agent/graph.py`
  * Result: passed.
* `.venv/bin/pytest -q`
  * Result: 105 passed, 1 warning.

Acceptance criteria:

* Analyzer returns only independent observations: completed for the OpenAI schema.
* No product recommendation is generated by the analyzer schema: completed.
* No commercial action or stage is generated by the analyzer schema: completed.
* No redundant booleans are generated by the analyzer schema: completed.
* No turn number is invented by the analyzer schema: completed.
* Evidence validation exists: completed.
* Parser runs in shadow mode only: completed.
* Response generator behavior remains compatible: completed.

Unresolved issues:

* Temporary adapter derives legacy `TurnAnalysis` aliases for existing runtime services.
* Deterministic normalized-turn contract is not implemented yet.
* Parser/LLM comparison telemetry is not implemented yet.
* Planner and response package still consume legacy fields.

Exact next task:

* Implement Phase 2 only: deterministic normalization and derivation from Analyzer Contract V3.

## Phase 2: Deterministic Normalization And Derivation

Status: completed.

Depends on:

* Phase 1 V3 analyzer observation schema.
* Phase 1 shadow parser trace output.

Files changed:

* `src/movia_sales_agent/analyzer/__init__.py`
* `src/movia_sales_agent/analyzer/contract_v3.py`
* `src/movia_sales_agent/analyzer/normalizer.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/models/schemas.py`
* `src/movia_sales_agent/services/openai_service.py`
* `docs/architecture/NORMALIZED_TURN_CONTRACT_V3.md`
* `tests/test_analyzer_contract_v3.py`
* `tests/test_analyzer_normalization_v3.py`
* `docs/implementation/PHASE_ANALYZER_V3_2_REPORT.md`
* `PLAN_ANALYZER_V3.md`

Schema and runtime changes:

* Added `NormalizedTurn`.
* Added deterministic normalization and derivation service.
* Added graph node:

```text
analyze_turn
→ normalize_and_derive_turn
→ update_lead_state
```

* Added parser/LLM telemetry to normalized turn output.
* Added normalized-turn trace to response metadata.
* Converted normalized turn into current `TurnAnalysis` for planner compatibility.

Migrations:

* None.

Tests:

* `.venv/bin/pytest tests/test_analyzer_normalization_v3.py -q`
  * Result: 13 passed, 1 warning.
* `.venv/bin/pytest tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py -q`
  * Result: 28 passed, 1 warning.
* `.venv/bin/pytest tests/test_objection_flow.py -q`
  * Result: 13 passed, 1 warning.
* `.venv/bin/pytest tests/test_agent_policy.py tests/test_response_context.py tests/test_api.py tests/test_objection_flow.py tests/test_memory_v3.py tests/test_rag_v3.py tests/test_evaluation.py -q`
  * Result: 64 passed, 1 warning.
* `.venv/bin/python -m compileall src/movia_sales_agent/analyzer src/movia_sales_agent/services/openai_service.py src/movia_sales_agent/agent/graph.py`
  * Result: passed.
* `.venv/bin/pytest -q`
  * Result: 118 passed, 1 warning.

Acceptance:

* Impossible analyzer states cannot reach the planner.
* `action_requirement` never defaults to answers-only without evidence.
* External actions can never derive Captura.
* Historical references require valid evidence.
* Explicit start requires valid evidence.
* Product recommendation is deterministic.
* Parser remains non-authoritative.

All completed.

Unresolved issues:

* Planner still consumes `TurnAnalysis`.
* Response package still consumes planner-compatible legacy fields.
* Live OpenAI targeted validation was not run in Phase 2.
* Unsupported-channel and Captura external-action response constraints are deferred to Phase 3.

Exact next task:

* Implement Phase 3 only: Sales Policy Planner integration with the normalized contract, CTA/next-question compatibility, and response-package claim constraints.

## Phase 3: Sales Policy Planner Integration

Status: completed.

Depends on:

* Phase 2 normalized-turn contract and derivation layer.

Files changed:

* `src/movia_sales_agent/agent/planners.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/agent/response.py`
* `tests/test_agent_policy.py`
* `tests/test_response_context.py`
* `docs/implementation/PHASE_ANALYZER_V3_3_REPORT.md`
* `PLAN_ANALYZER_V3.md`

Implemented:

* Added `normalized_turn` to planner state and graph planner calls.
* Added planner-visible normalized fields:
  * `requested_product`
  * `recommended_product`
  * `selected_product`
  * `product_preference_mismatch`
  * `known_slots`
  * `missing_slots`
  * `action_requirement`.
* Changed planner order so:
  * post-purchase and objection handling remain highest priority;
  * explicit start can still direct close when allowed;
  * exact pricing/channel/process/comparison questions stay informational;
  * unknown action requirement routes to discovery;
  * product mismatch routes to `narrow_solution`;
  * evidence-backed available product fit routes to `recommend_solution`;
  * soft close still wins after recommendation has already been communicated.
* Enforced question CTA compatibility for `discovery_question`, `soft_question`, and `objection_question`.
* Added response-package sections:
  * `turn_signal_context`
  * `claim_constraints`.
* Added deterministic constraints:
  * only WhatsApp Business is available today;
  * Facebook and Instagram are upcoming/not available;
  * no MovIA product should be described as currently multichannel;
  * Captura may collect order information in WhatsApp but may not create/register/write orders in external systems;
  * external-action requests route toward Híbrido.
* Updated fallback responses so generic product recommendation no longer runs as a catch-all.

Migrations:

* None.

Tests:

* `.venv/bin/pytest tests/test_agent_policy.py tests/test_memory_v3.py tests/test_response_context.py tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py -q`
  * Result: 65 passed, 1 warning.
* `.venv/bin/pytest -q`
  * Result: 125 passed, 1 warning.

Acceptance:

* Analyzer only observes.
* Normalizer only derives.
* Planner only decides.
* Generator only writes.
* No automatic Captura recommendation without evidence.
* No unsupported channel claims in fallback or package constraints.
* No Captura external-action overpromises in fallback or package constraints.
* No null question key for question CTAs.
* Existing Atomic/Coherent datasets remain unchanged.

Unresolved issues:

* Live OpenAI targeted validation was not run in Phase 3.
* The response LLM is constrained by package/prompt; deterministic post-generation claim validation remains a later hardening option if Phase 4 live validation finds new wording failures.
* `TurnAnalysis` compatibility remains present for existing runtime consumers.

Exact next task:

* Implement Phase 4 only: targeted live validation for the most damaging Analyzer V3 cases without modifying gold datasets or starting a full replay.

## Phase 4: Targeted Live Validation

Status: completed.

Depends on:

* Phases 1-3 complete.

Files changed:

* `movia_validation_package/analyzer_v3_targeted_manifest.json`
* `src/movia_sales_agent/evaluation/analyzer_v3_targeted.py`
* `src/movia_sales_agent/evaluation/cli.py`
* `src/movia_sales_agent/analyzer/contract_v3.py`
* `src/movia_sales_agent/analyzer/normalizer.py`
* `src/movia_sales_agent/agent/planners.py`
* `docs/architecture/ANALYZER_CONTRACT_V3.json`
* `docs/evaluation/PARSER_SHADOW_COMPARISON.md`
* `docs/evaluation/ANALYZER_V3_TARGETED_COMPARISON.md`
* `tests/test_analyzer_targeted_v3.py`
* `tests/test_analyzer_contract_v3.py`
* `tests/test_analyzer_normalization_v3.py`
* `tests/test_agent_policy.py`
* `docs/implementation/PHASE_ANALYZER_V3_4_REPORT.md`
* `PLAN_ANALYZER_V3.md`

Artifacts:

* Final passed artifact: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`
* Source all-OpenAI live run: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260606T235650Z-1df8be/`
* Summary: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/summary.md`
* Gate summary: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/gate_summary.json`

Implemented:

* Added reference-only targeted manifest covering premature recommendation, external actions, unsupported Instagram/Facebook channel claims, explicit-start handling, false historical references, true historical references, sarcasm, and price-question cases.
* Added analyzer-only targeted replay that runs shadow parser, Analyzer V3, normalizer, derivation, and planner without generating responses.
* Added targeted live replay that runs the real agent with OpenAI analyzer calls, response generation, DB-backed runtime, and RAG when selected.
* Added previous-versus-new comparison using latest Atomic and Coherent OpenAI Phase 6 baselines.
* Added parser-shadow comparison report.
* Hardened strict Analyzer V3 schema generation by stripping JSON-schema defaults before OpenAI structured-output submission.
* Added OpenAI analyzer payload sanitizer for recoverable evidence-span shape issues so valid live observations do not fall back unnecessarily.
* Tightened prior-reference cue normalization and unsupported-channel planning.
* Fixed Captura external-action detector safe negations such as `sin registrar`.

Migrations:

* None.

Tests:

* `.venv/bin/pytest tests/test_analyzer_targeted_v3.py tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py tests/test_agent_policy.py -q`
  * Result: 66 passed, 1 warning.
* `.venv/bin/python -m py_compile src/movia_sales_agent/evaluation/analyzer_v3_targeted.py src/movia_sales_agent/analyzer/contract_v3.py`
  * Result: passed.
* `.venv/bin/pytest -q`
  * Result: 138 passed, 1 warning.

Acceptance:

* Hard failures are zero in targeted live validation: completed.
* Hallucinated turn numbers are zero: completed.
* Impossible normalized states are zero: completed.
* External-action critical misses are zero: completed.
* Captura external-action overpromises are zero: completed.
* Unsupported channel claims are zero: completed.
* False prior references are materially reduced: completed, 6 previous to 0 current.
* Explicit-start cases pass: completed.
* Full replay is recommended only if targeted gates pass: completed.

Unresolved issues:

* Token usage increased versus previous V3 because targeted records now use OpenAI analyzer calls instead of fallback analysis.
* Parser-shadow channel telemetry has high conflict counts and should remain observational until a later rule is explicitly justified.
* `TurnAnalysis` compatibility remains for existing runtime consumers.
* A duplicate post-fix live rerun hung after creating an empty artifact directory and was terminated; the final artifact uses the completed all-OpenAI live source records and corrected detector rescore.

Exact next task:

* Run the full Atomic and Coherent replay with the current Analyzer V3 implementation. Do not modify gold datasets, deploy, or start an adaptive hybrid flow before reviewing the full replay results.
