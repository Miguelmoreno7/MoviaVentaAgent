# MOVIA SALES AGENT — VALIDATION, PARALLEL OBJECTIONS, MEMORY, RAG AND RESPONSE QUALITY PLAN

## Purpose

This is the master implementation plan for the next iteration of the MovIA conversational sales agent.

The work must be executed in six separate phases.

Do not implement all six phases in one run.

The six phases are:

1. Redesign the evaluation system.
2. Implement parallel objection handling.
3. Fix and evaluate conversational memory.
4. Audit and improve RAG routing and retrieval.
5. Add response-quality evaluation.
6. Run integrated validation and prepare adaptive hybrid predeployment testing.

The current agent already has strong results in:

* commercial accuracy;
* policy compliance;
* scope control;
* basic memory persistence;
* token reduction;
* prevention of premature direct closes;
* canonical commercial taxonomies.

Preserve those improvements.

The next work must focus on improving how the system is evaluated and on fixing specific behavioral weaknesses without converting the agent back into a prompt-heavy or LLM-controlled architecture.

---

# REQUIRED SOURCE DOCUMENTS

Before planning or changing code, inspect:

* `PLAN.md`
* `PLANV2.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
* `docs/audit/PARALLEL_OBJECTION_RUNTIME_AUDIT.md`
* all Phase 1–6 implementation reports from the previous iteration;
* the latest V1 vs V2 comparison;
* the latest 60-turn `run.json`;
* the current evaluation datasets;
* the current LangGraph runtime;
* current migrations;
* current unit and regression tests.

Treat the repository implementation as the source of truth for current behavior.

Treat this document as the target behavior.

---

# EXECUTION MODE

This document is the complete master specification.

For the first run:

1. Read the entire specification.
2. Inspect the repository.
3. Create or update a durable plan:

   * `PLAN_V3.md`
4. Include:

   * all six phases;
   * dependencies;
   * files expected to change;
   * migrations;
   * tests;
   * acceptance criteria;
   * risks;
   * unresolved decisions.
5. Verify whether this specification conflicts with the actual repository.
6. Implement **Phase 1 only**.
7. Run only Phase 1 tests.
8. Produce:

   * `docs/implementation/PHASE_V3_1_REPORT.md`
9. Update `PLAN_V3.md`.
10. Stop.

Do not begin Phase 2 in the first run.

For later runs, Miguel will explicitly request:

```text
Continue PLAN_V3.md and implement Phase N only.
Run the Phase N tests, update the plan, produce the phase report, and stop.
```

---

# GLOBAL ARCHITECTURAL PRINCIPLES

## LLM responsibilities

LLMs may:

* interpret natural language;
* extract canonical signals;
* formulate natural responses;
* judge response quality during evaluation;
* generate adaptive lead responses only during the final predeployment suite.

## Deterministic-code responsibilities

Code must decide:

* commercial stage;
* commercial action;
* objection persistence;
* whether an objection blocks closing;
* which question may be asked next;
* known and missing lead fields;
* source routing;
* whether RAG is necessary;
* allowed CTA;
* product availability;
* exact pricing and policies.

## Cost constraint

Do not add another always-on LLM call.

Any new LLM-based process must be:

* evaluation-only;
* conditional;
* or demonstrably cheaper than the work it replaces.

## Safety constraint

Never regress:

* exact prices;
* deposit percentage;
* refund policy;
* channel availability;
* available product status;
* Captura versus Híbrido scope;
* post-purchase handoff;
* memory isolation between leads.

---

# PHASE 1 — REDESIGN THE EVALUATION SYSTEM

## Objective

Separate evaluation according to what each test format can validly measure.

The current 60-turn scripted replay is valuable, but it is not a causally coherent sales conversation. Its next user message does not react to the agent's answer.

Therefore, it must not be used as the primary measurement of complete sales progression or complete objection resolution.

Do not run adaptive simulation in this phase.

---

## 1. Define three evaluation suites

### Suite A — Atomic Scripted Capability Replay

Use the existing five scenarios and 60 lead messages.

Purpose:

* deterministic regression;
* intent classification;
* commercial taxonomy;
* exact information retrieval;
* source routing;
* policy compliance;
* scope control;
* isolated memory usage;
* response to difficult inputs;
* prevention of invalid closing.

It must not heavily score:

* global funnel progression;
* full objection resolution;
* whether the lead became convinced;
* final conversion.

Rename or classify the current dataset as:

```text
suite_type = atomic_scripted
causal_continuity = false
```

Preserve the original messages.

Do not delete the previous artifacts.

### Suite B — Coherent Scripted Conversations

Create deterministic conversations where every user turn is causally coherent with the expected behavior of the previous agent turn.

Create at least five conversations:

1. Successful sale ending in app registration.
2. Interested lead ending in the 10-message demo.
3. Real blocking objection that is resolved.
4. Lead that should not be closed.
5. Lead whose needs reveal that MovIA Híbrido is required.

Each conversation should have approximately 8–15 lead turns.

These scripts should contain meaningful paths such as:

```text
discovery
→ qualification
→ recommendation
→ concern or objection
→ clarification
→ risk reduction
→ acceptance
→ soft close
→ explicit start
```

The expected next lead message must respond coherently to the expected prior agent behavior.

This suite can evaluate:

* sales progression;
* stage transitions;
* objection lifecycle;
* recommendation quality;
* soft close;
* direct close;
* conversation coherence.

Classify as:

```text
suite_type = coherent_scripted
causal_continuity = true
```

### Suite C — Adaptive Hybrid Predeploy

Define the schema and runner interface only.

Do not run it yet.

It will eventually contain:

1. deterministic regression;
2. adaptive lead simulation reacting to actual responses.

It can only run after Phases 2–5 pass their acceptance gates.

Classify as:

```text
suite_type = adaptive_hybrid
predeploy_only = true
```

---

## 2. Metric applicability

Add explicit suite-to-metric applicability.

Example:

| Metric                |         Atomic | Coherent | Adaptive |
| --------------------- | -------------: | -------: | -------: |
| Commercial accuracy   |           High |     High |     High |
| Policy compliance     |           High |     High |     High |
| Scope control         |           High |     High |     High |
| Intent/action routing |           High |     High |   Medium |
| Source selection      |           High |     High |   Medium |
| Memory persistence    |         Medium |     High |     High |
| Sales progression     | Low/diagnostic |     High |     High |
| Objection resolution  | Low/diagnostic |     High |     High |
| Conversion behavior   | Not applicable |   Medium |     High |
| Response quality      |        Sampled |     High |     High |

Do not calculate a misleading global score by applying invalid metrics to a suite.

---

## 3. Evaluation metadata

Every dataset and run must include:

```json
{
  "evaluation_contract_version": "3.0",
  "suite_type": "atomic_scripted",
  "causal_continuity": false,
  "agent_contract_version": "...",
  "dataset_version": "...",
  "run_mode": "..."
}
```

Fail early if incompatible versions are used.

---

## 4. Reporting

Produce separate reports:

* capability score;
* progression score;
* memory score;
* retrieval score;
* response-quality score;
* critical-rule failures.

Do not combine them into one score unless weights are explicitly documented.

Reports must distinguish:

* hard failures;
* deterministic rule failures;
* soft trace mismatches;
* judge failures;
* partial retrieval matches;
* skipped;
* not applicable.

---

## 5. Phase 1 deliverables

Create:

* `docs/evaluation/EVALUATION_STRATEGY_V3.md`
* `src/.../evaluation/contracts_v3.py` or the equivalent repository location
* updated atomic dataset metadata;
* coherent scripted dataset schema;
* five coherent scripted conversations;
* adaptive-hybrid interface/schema without execution;
* evaluator applicability matrix;
* Phase 1 tests;
* `docs/implementation/PHASE_V3_1_REPORT.md`

---

## 6. Phase 1 restrictions

* Do not change agent runtime behavior.
* Do not redesign objections yet.
* Do not change memory logic.
* Do not change RAG logic.
* Do not run adaptive simulation.
* Do not run a full expensive replay unless needed to verify the new evaluator schema.
* Preserve the original V2 replay artifacts.

---

## 7. Phase 1 acceptance criteria

* Existing 60 messages are classified as atomic capability tests.
* Sales progression and objection resolution are no longer treated as authoritative global metrics for non-causal scripts.
* Five coherent scripted conversations exist and validate structurally.
* Metric applicability is explicit.
* Reports distinguish capability from progression.
* Adaptive hybrid remains disabled.

---

# PHASE 2 — PARALLEL OBJECTION HANDLING

## Objective

Replace the current exclusive objection-stage architecture with a hybrid parallel architecture:

```text
soft concern
→ inline objection overlay
→ no persistent objection subdialogue

hard/blocking objection
→ persistent objection overlay
→ independent from sales_stage
```

Do not implement a LangGraph subgraph initially.

The current audit shows that the existing runtime already stores `sales_stage` and `active_objection` separately. The simpler and safer correction is to change policy semantics, not add graph complexity.

---

## 1. Core model

The lead state must be able to represent:

```json
{
  "sales_stage": "qualified",
  "conversation_mode": "handling_objection",
  "active_objection": {
    "type": "price_objection",
    "strength": "hard",
    "status": "active",
    "current_step": "clarify_value"
  }
}
```

The objection must not replace the sales stage.

---

## 2. SalesStage semantics

The runtime must stop using `objection_handling` as the persisted primary sales stage.

Canonical commercial stages should remain commercial-funnel concepts such as:

```text
new
discovery
educating
comparing
qualified
solution_recommended
ready_to_start
closing
post_purchase
handoff
unknown_recovery
```

If `objection_handling` remains in an enum for migration compatibility:

* mark it deprecated;
* do not target it for new turns;
* normalize existing records to `stage_before_objection`;
* fall back to `previous_stage`, then `discovery` or `educating` when no valid prior stage exists.

Document any contract-version change.

---

## 3. Conversation mode

Add a separate canonical field:

```text
conversation_mode:
- normal
- handling_objection
```

The mode may change without changing `sales_stage`.

---

## 4. Soft concerns

A soft concern must not automatically create persistent `active_objection`.

Examples:

```text
“Seguro es otro bot.”
“No me digas que venderá brackets solo.”
“¿Y eso sí sirve?”
```

Possible behavior:

```text
current user intent = product_scope_question
sales_stage = educating
macro_action = persuade_value or answer_and_advance
objection_overlay = acknowledge and reassure briefly
```

The response should answer the actual question while addressing the concern inline.

Persist a soft concern only when:

* it is repeated;
* it becomes explicit resistance;
* it blocks advancement;
* confidence and business rules classify it as materially unresolved.

---

## 5. Hard objections

Hard objections remain persistent.

Examples:

```text
“No pienso pagar eso.”
“Dame prueba gratis sin depósito o no me interesa.”
“No confío en conectar mi WhatsApp.”
“Hasta que no me demuestres que funciona no voy a avanzar.”
```

A hard objection:

* creates or updates `active_objection`;
* sets `conversation_mode=handling_objection`;
* may block `soft_close` or `direct_close`;
* does not prevent exact informational questions from being answered;
* does not erase the commercial sales stage.

---

## 6. Planner priority redesign

The current planner evaluates persisted objections before many current-turn intents.

Refactor into two decisions:

### Decision A — Primary turn action

Select based on:

* current user intent;
* current commercial stage;
* known lead information;
* explicit request;
* product fit;
* current message.

Examples:

```text
pricing question → answer_and_advance
comparison → compare_alternative
industry fit → persuade_value
missing action requirement → narrow_solution
```

### Decision B — Objection overlay and constraints

Independently determine:

* no overlay;
* inline soft concern;
* active hard objection continuation;
* pause;
* resolution;
* replacement;
* closing restriction.

The overlay can modify:

* tone;
* supporting point;
* proof requirement;
* CTA allowance.

It must not arbitrarily replace the selected primary action.

---

## 7. Objection relation signals

Extend canonical analysis with an enum such as:

```text
objection_relation:
- none
- new
- continuation
- reaffirmed
- clarified
- resolved
- unrelated
```

Add confidence.

Do not advance objection steps only because another turn occurred.

---

## 8. Semantic objection progression

Replace fixed turn-based progression.

Example logic:

```text
new hard objection
→ thank_empathize_ask_open_question

lead clarifies blocker
→ clarify_value or tie_solution

lead asks for evidence
→ provide_proof

lead accepts explanation or explicitly moves forward
→ resolved

unrelated exact question
→ paused, answer current question

same objection reaffirmed
→ continue relevant step, do not restart

different objection
→ supersede or stack according to explicit policy
```

Do not advance merely from one index to the next.

---

## 9. Pausing and closing gates

A paused soft concern:

* must not block soft close;
* must not force `handle_objection`;
* must not freeze stage progression.

A paused unresolved hard objection:

* may allow exact answers and process explanations;
* still blocks direct close unless the user explicitly resolves or accepts it.

An explicit-start message may also be evidence that the prior soft concern is resolved.

---

## 10. Response-generation overlay

When the primary action is not `handle_objection`, the generator may receive:

```json
{
  "objection_overlay": {
    "mode": "inline",
    "type": "trust_objection",
    "instruction": "Acknowledge the concern briefly, then answer the current question.",
    "must_not_dominate_response": true
  }
}
```

For persistent hard objections, load only the relevant playbook entry.

Do not load the complete objection playbook.

---

## 11. Persistence

The current JSONB `active_objection` can support the first overlay version.

Add fields only if required:

```text
status
paused_reason
resolved_reason
last_related_turn
resolved_at
superseded_by
```

Create local migration only if necessary.

Do not apply production migrations.

---

## 12. Required regression cases

Test:

1. Sarcastic opener handled inline.
2. Brackets joke handled as scope clarification, not persistent objection.
3. Pain description advances discovery even if a soft concern happened earlier.
4. Exact price question answers price and progresses sales stage.
5. Hard free-trial objection persists and blocks direct close.
6. Paused hard objection allows an exact policy question.
7. Acceptance resolves an objection semantically.
8. New objection replaces or supersedes according to policy.
9. No fixed-step advancement without semantic evidence.
10. Objection resolution returns to the existing sales stage, not `new`.

---

## 13. Phase 2 deliverables

Create:

* `docs/architecture/PARALLEL_OBJECTION_DESIGN.md`
* contract changes;
* planner changes;
* stage changes;
* objection service changes;
* response-overlay changes;
* migration if required;
* unit and multi-turn tests;
* `docs/implementation/PHASE_V3_2_REPORT.md`

---

## 14. Phase 2 acceptance criteria

* Soft concerns do not freeze the funnel.
* Hard objections persist independently.
* `sales_stage` no longer becomes `objection_handling`.
* Current intent can be processed during an active objection.
* Hard unresolved objections still protect closing.
* Objections resolve based on semantic evidence.
* Resolution does not return a mature lead to `new`.
* No new always-on LLM call is introduced.

---

# PHASE 3 — MEMORY CORRECTION AND MEMORY EVALUATION

## Objective

Fix memory usage before adding more memory infrastructure.

The observed Turn 4 problem was not a storage failure.

The agent already had:

* business type;
* channel;
* pain;
* action requirement.

The failure was:

```text
incorrect missing-slot detection
+
null next_question_key
+
generator improvised a generic question
+
no guard against asking known information
```

Implement this phase in two parts.

---

## PHASE 3A — Fix structured-memory usage

### 1. Deterministic known/missing slots

Calculate in code:

```json
{
  "known_slots": [],
  "missing_slots": []
}
```

The LLM must not independently decide which persisted fields are missing.

Core slots:

```text
business_type
main_channel
pain_or_goal
action_requirement
known_product_fit
```

### 2. Product-fit derivation

At minimum:

```text
action_requirement = answers_only
→ known_product_fit = movia_captura

action_requirement = external_actions_required
→ known_product_fit = movia_hibrido
```

Do not leave product fit unknown when enough deterministic evidence exists.

### 3. Required next-question key

Any CTA that asks a question must provide a canonical `next_question_key`.

If:

```text
cta_type = discovery_question
or
cta_type = soft_question
```

then:

```text
next_question_key != null
```

If no valid next question exists:

```text
cta_type = none
```

Do not let the response generator invent a discovery question.

### 4. Forbidden questions

Add to the response package:

```json
{
  "known_slots": {},
  "forbidden_question_keys": []
}
```

Examples:

```text
business_type known
→ forbid ask_business_type

main_channel known
→ forbid ask_main_channel

pain known
→ forbid ask_pain

action requirement known
→ forbid ask_action_requirement
```

### 5. Post-generation validator

Detect whether the response asks for already-known information.

On violation:

* regenerate once with explicit correction; or
* replace the CTA with a deterministic next question.

Log the violation.

### 6. Turn 4 regression

Given:

```text
business_type = dental
main_channel = whatsapp
pain known
action_requirement = answers_only
```

When:

```text
“¿Cuánto cuesta?”
```

Then:

* answer Captura price;
* do not ask business type;
* do not ask main channel;
* do not ask pain;
* optionally ask whether the lead wants the process or demo.

---

## PHASE 3B — Historical conversational memory

Implement conditional prior-message retrieval.

### Detection fields

Extend analysis with:

```text
references_prior_message
reference_type
reference_query
referenced_topics
explicit_turn_number
reference_confidence
```

Reference types:

```text
explicit_turn
temporal_reference
topic_reference
entity_reference
assistant_commitment_reference
```

### Retrieval hierarchy

Use:

1. Structured lead memory.
2. Recent Redis/in-memory buffer.
3. Postgres full-text or metadata search.
4. Semantic message retrieval only as fallback.

Do not use embeddings when a structured field already answers the reference.

### Retrieval output

Return only 1–3 relevant turn pairs:

```json
{
  "conversation_memory_evidence": [
    {
      "turn_id": 2,
      "user_message": "...",
      "assistant_message": "...",
      "relevance_reason": "..."
    }
  ]
}
```

Do not send the entire conversation.

### Message metadata

Store or derive:

```text
turn_number
topics
entities
facts_extracted
created_at
```

Do not store hidden chain-of-thought.

---

## Memory metrics

Add:

### `known_slot_repetition`

Did the agent ask again for known structured information?

### `historical_reference_accuracy`

Did the agent correctly resolve a reference to an earlier message?

### `prior_commitment_consistency`

Did the agent contradict something it previously told the lead?

### `contextual_personalization`

Did it use known relevant lead information appropriately?

---

## Memory scenarios

Create at least two dedicated coherent scenarios.

### Scenario A — Structured slots

Reveal business type, channel, pain and action needs across early turns.

Later ensure:

* they are not asked again;
* they are used in product recommendation;
* next questions advance to new information.

### Scenario B — Historical reference

Include:

```text
“¿Cuál era el plan que me recomendaste?”
“Lo de mis proveedores, ¿era Captura o Híbrido?”
“Como te dije al inicio, no necesito agenda.”
“Tú dijiste que el depósito era 50%, ¿verdad?”
```

Validate retrieval and consistency.

---

## Phase 3 deliverables

Create:

* structured-memory correction;
* prior-reference detector;
* conditional memory retriever;
* four metrics;
* two coherent memory scenarios;
* tests;
* `docs/architecture/CONVERSATIONAL_MEMORY_V3.md`
* `docs/implementation/PHASE_V3_3_REPORT.md`

---

## Phase 3 acceptance criteria

* Turn 4 regression passes.
* Known slots are never casually re-requested.
* Question CTAs cannot have a null question key.
* Historical retrieval runs only when needed.
* Prior references return relevant evidence.
* No cross-lead contamination.
* No large unconditional token increase.

---

# PHASE 4 — RAG AUDIT AND ROUTING IMPROVEMENT

## Objective

Measure and improve:

1. whether RAG was needed;
2. whether the correct collection/topic was selected;
3. whether retrieved chunks were relevant;
4. whether the response used them correctly.

Matching expected source labels is not enough.

---

## 1. Audit latest RAG turns

For every turn that used RAG, record:

```text
user message
primary intent
routing reason
retrieval query
metadata filters
retrieved documents
similarity
context relevance
whether RAG was needed
whether response used context
```

Produce:

* `docs/audit/RAG_USAGE_AUDIT_V3.md`

---

## 2. Deterministic RAG policy

Implement explicit rules:

```text
price → structured DB, no RAG
policy → structured DB, no RAG
platform steps → JSON, no RAG
onboarding → JSON/DB, no RAG
product availability → DB, no RAG
industry use case → RAG with industry filter
comparison → RAG with comparison target filter
open explanatory question → RAG
provide proof → conditional RAG
```

---

## 3. Metadata filtering

Use canonical metadata such as:

```text
topic
industry
channel
product
comparison_target
funnel_stage
approved
version
```

A dental question should prefer:

```text
use_cases.dental
product_explanations.movia_captura
```

not unrelated Facebook/Instagram documents.

---

## 4. Relevance threshold

Define a minimum relevance policy.

When results are weak:

```text
no context is better than wrong context
```

Do not inject irrelevant chunks solely because retrieval returned something.

---

## 5. Context limits

Use:

* top 1–3 chunks;
* deduplication;
* metadata filters;
* token budget;
* structured facts overriding RAG.

---

## 6. RAG metrics

Add:

### `retrieval_necessity`

Was RAG appropriate for this turn?

### `routing_accuracy`

Was the right topic/industry/comparison collection selected?

### `context_relevance`

Were the retrieved chunks relevant to the question?

### `answer_groundedness`

Did the answer faithfully use the retrieved context?

Use deterministic checks where possible.

Use RAGAS or a judge only on actual RAG turns.

---

## 7. Phase 4 deliverables

Create:

* RAG usage audit;
* routing-policy document;
* corrected knowledge planner;
* metadata-filter logic;
* relevance threshold;
* RAG metrics;
* RAG-specific evaluation cases;
* `docs/implementation/PHASE_V3_4_REPORT.md`

---

## 8. Phase 4 acceptance criteria

* Exact factual questions do not trigger unnecessary RAG.
* Industry questions use appropriate industry documents.
* Irrelevant low-score chunks are rejected.
* RAG metrics evaluate semantic quality, not only source names.
* No commercial fact is overridden by RAG.
* Average context does not grow significantly.

---

# PHASE 5 — RESPONSE QUALITY EVALUATION

## Objective

Evaluate whether the visible response is genuinely useful, persuasive, natural and well directed.

Trace correctness and response quality must remain separate.

---

## 1. Response-quality rubric

Score each applicable dimension from 1–5:

```text
directness
relevance
factuality
personalization
persuasiveness
naturalness
non_repetition
next_step_quality
conciseness
tone
```

Definitions must be explicit.

### Directness

Did the response answer the actual question?

### Relevance

Did it avoid unrelated explanations?

### Factuality

Did it remain grounded in official context?

### Personalization

Did it use known lead context where useful?

### Persuasiveness

Did it explain value without pressure or invention?

### Naturalness

Does it sound appropriate for WhatsApp?

### Non-repetition

Did it avoid asking or explaining the same thing unnecessarily?

### Next-step quality

Was the final question or CTA the best logical next move?

### Conciseness

Was it sufficiently complete without unnecessary length?

### Tone

Was it calm, consultative and appropriate for the lead?

---

## 2. Judge design

Implement a structured evaluation judge.

The judge must receive:

* user message;
* relevant recent context;
* known lead facts;
* official facts used;
* selected commercial action;
* response;
* rubric.

Do not give it hidden chain-of-thought.

Return canonical JSON with:

```text
dimension scores
short evidence
critical defect flags
overall response quality
```

Use an evaluation model only during selected evaluation suites.

Do not add it to runtime.

---

## 3. Calibration

Create at least 10 manually reviewed examples:

* excellent;
* acceptable;
* weak;
* factually correct but commercially weak;
* persuasive but overly long;
* repetitive;
* wrong next question.

Compare judge scores to human labels.

Document disagreements.

---

## 4. Where to run the judge

Run response-quality evaluation on:

* all coherent scripted conversations;
* memory scenarios;
* RAG scenarios;
* a sampled subset of atomic replay;
* future adaptive hybrid runs.

Do not require an expensive judge for every small unit test.

---

## 5. Critical response defects

Flag separately:

```text
did_not_answer_question
asked_known_information
unsupported_claim
overpromised_scope
premature_close
irrelevant_context
repetitive_question
unnatural_or_defensive_tone
poor_next_step
```

---

## 6. Phase 5 deliverables

Create:

* `docs/evaluation/RESPONSE_QUALITY_RUBRIC.md`
* judge schema;
* judge runner;
* calibration dataset;
* sampled atomic evaluation;
* coherent-conversation quality report;
* `docs/implementation/PHASE_V3_5_REPORT.md`

---

## 7. Phase 5 acceptance criteria

* Quality is evaluated independently from traces.
* The rubric includes next-question quality.
* Known-slot repetition is visible as a defect.
* Judge outputs are structured and reproducible.
* Calibration against human examples is documented.
* No runtime cost is added.

---

# PHASE 6 — INTEGRATED VALIDATION AND HYBRID PREDEPLOY

## Objective

Run the complete validation system only after Phases 1–5 are stable.

---

## 1. Evaluation database

Use a safe evaluation Postgres/Supabase environment.

Apply required local/evaluation migrations:

* stage-machine migration;
* active-objection migration;
* any V3 migration;
* memory-related migration if needed.

Do not apply production migrations.

Report:

```text
persistence mode
migration status
read-after-write verification
active-objection persistence
sales-stage persistence
historical-message retrieval
```

---

## 2. Run deterministic suites

Run:

1. Atomic scripted replay.
2. Coherent scripted conversations.
3. Memory scenarios.
4. RAG routing/relevance scenarios.
5. Response-quality judge.
6. Unit and regression tests.

Do not run adaptive hybrid if critical deterministic gates fail.

---

## 3. Deterministic gates

Minimum requirements:

```text
hard failures = 0
commercial accuracy >= 0.95
policy compliance >= 0.95
scope control >= 0.95
known-slot critical repetitions = 0
historical reference suite passes
premature direct closes = 0
irrelevant RAG injection below agreed threshold
coherent sales progression >= agreed threshold
coherent objection resolution >= agreed threshold
response quality >= agreed threshold
```

Atomic sales progression should remain diagnostic, not a deployment gate.

---

## 4. Adaptive Hybrid Predeploy

Only if deterministic gates pass:

Run Hybrid Suite:

1. fixed regression replay;
2. adaptive simulated leads reacting to actual agent responses.

Use the five difficult personas plus:

* one normal high-intent lead;
* one qualified lead who should close;
* one lead who should not close.

Record:

```text
conversation outcome
sales-stage path
objection path
memory references
sources used
response quality
token cost
latency
judge disagreements
```

Run enough seeds to detect variance, but keep cost controlled.

---

## 5. Before/after report

Create:

* `docs/evaluation/V2_VS_V3_COMPARISON.md`

Include:

```text
capability metrics
coherent progression
objection resolution
memory metrics
RAG metrics
response quality
tokens
latency
action distribution
stage distribution
objection distribution
CTA distribution
critical defects
```

Do not compare invalid V2 atomic progression directly with V3 coherent progression without labeling the methodological difference.

---

## 6. Deployment recommendation

End with one of:

```text
NOT READY
READY FOR LIMITED PILOT
READY FOR PREDEPLOY HYBRID ONLY
READY FOR CONTROLLED PRODUCTION
```

Give explicit reasons.

Do not deploy automatically.

---

## 7. Phase 6 deliverables

Create:

* all deterministic run artifacts;
* DB-mode persistence report;
* adaptive hybrid artifacts if gates pass;
* V2 vs V3 comparison;
* deployment recommendation;
* unresolved issues;
* `docs/implementation/PHASE_V3_6_REPORT.md`

---

# GLOBAL TEST REQUIREMENTS

Throughout all phases:

* preserve previous artifacts;
* add regression tests before fixing known bugs;
* never weaken critical hard-failure rules;
* distinguish evaluator defects from runtime defects;
* document all contract changes;
* keep source routing observable;
* preserve token instrumentation;
* do not invent business claims;
* do not expose unavailable products as available;
* do not add hidden LLM reasoning to persistence;
* do not use production data for testing.

---

# FINAL TARGET ARCHITECTURE

```text
load memory
→ analyze current turn
→ update structured lead facts
→ detect prior-message reference
→ retrieve conversation evidence conditionally
→ choose primary commercial action
→ apply objection overlay and closing constraints
→ resolve independent sales-stage transition
→ select structured / JSON / RAG sources
→ build compact response package
→ generate natural response
→ validate known-slot and critical-rule compliance
→ persist messages, stage, objection and metadata
```

The final agent must treat:

```text
sales_stage
```

and:

```text
active_objection
```

as related but independent dimensions.

The final evaluator must treat:

```text
capability correctness
conversation progression
response quality
```

as separate concepts.

---

# OPERATIONAL EXECUTION TRACKER

Last updated: 2026-06-06  
Current status: Phase 6 completed; deterministic DB validation finished with recommendation `NOT READY`.

## Current Decisions

* `PLAN_V3.md` remains the master implementation plan for the six V3 phases.
* Phase 1 changes evaluator contracts, datasets, scoring applicability and reports only.
* The existing 60-turn difficult-lead dataset is now `atomic_scripted` and non-causal.
* Coherent scripted conversations are a separate suite and are the correct place to score sales progression and objection lifecycle.
* Adaptive hybrid is schema/interface-only until Phases 2-5 pass deterministic gates.
* Objections now run as a parallel overlay: hard objections persist, soft concerns stay inline by default.
* `conversation_mode` carries active objection context; `current_stage` remains the commercial funnel stage.
* Structured lead memory is deterministic; known slots create forbidden question keys.
* Prior-message retrieval is conditional and uses compact current-lead evidence only.
* RAG routing is deterministic; exact facts stay structured, industry/comparison routes use metadata filters, and weak chunks are rejected.
* Response-quality judging is evaluation-only; deterministic by default and live LLM-based only when explicitly requested.
* Previous V2 replay artifacts are preserved and not rewritten.
* Miguel explicitly approved using the configured production Supabase database for Phase 6 testing.
* Required V2/V3 migrations, seed refresh and RAG ingestion were applied to that configured database for Phase 6.
* Adaptive hybrid was not run because deterministic coherent gates failed.
* No deployment or production pilot was performed.

## Current Repository Conflicts

* The configured remote database now has the V2 stage, active-objection and V3 conversation-mode migrations applied.
* The configured production database now contains evaluation rows under `channel='evaluation'`, tagged by run ID and `external_user_id like 'movia-eval-%'`.
* Existing V2 final replay score remains useful as atomic capability evidence, but not as authoritative sales progression evidence.
* Remote RAG rows were refreshed during Phase 6 ingestion, but only 13 source docs / 13 chunks currently exist.
* An initial live full-suite DB replay blocked inside `OpenAI responses.create()` and was interrupted; deterministic DB replay with `MOVIA_DISABLE_OPENAI=true` was used for the first completed Phase 6 baseline.
* A later OpenAI retry completed direct Responses API smoke, two-turn agent smoke, full atomic replay, and full coherent replay.
* Coherent scripted gates failed on sales progression, memory consistency, known-slot repetitions, and live OpenAI hard failures, so adaptive hybrid remains blocked.

## Phase 1: Redesign The Evaluation System

Status: completed.

Depends on:

* Existing V2 evaluator and datasets.
* `docs/evaluation/V1_VS_V2_COMPARISON.md`.
* `docs/audit/PARALLEL_OBJECTION_RUNTIME_AUDIT.md`.
* Commercial Contract V2.

Files changed:

* `docs/evaluation/EVALUATION_STRATEGY_V3.md`
* `docs/implementation/PHASE_V3_1_REPORT.md`
* `movia_validation_package/movia_difficult_lead_validation_scenarios.json`
* `movia_validation_package/movia_coherent_scripted_conversations.json`
* `movia_validation_package/movia_adaptive_hybrid_predeploy_interface.json`
* `src/movia_sales_agent/evaluation/contracts_v3.py`
* `src/movia_sales_agent/evaluation/models.py`
* `src/movia_sales_agent/evaluation/dataset.py`
* `src/movia_sales_agent/evaluation/runner.py`
* `src/movia_sales_agent/evaluation/scoring.py`
* `src/movia_sales_agent/evaluation/reporting.py`
* `tests/test_evaluation.py`
* `PLAN_V3.md`

Migrations:

* None.

Tests:

* `.venv/bin/pytest tests/test_evaluation.py`
  * Result: 14 passed.
* `.venv/bin/movia-eval validate-dataset`
  * Result: valid atomic suite, 5 scenarios, 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`
  * Result: valid coherent suite, 5 scenarios, 41 turns.

Acceptance criteria:

* Existing 60 messages classified as atomic capability tests: completed.
* Atomic dataset has `suite_type=atomic_scripted` and `causal_continuity=false`: completed.
* Sales progression and objection resolution are diagnostic for atomic scripts: completed.
* Five coherent scripted conversations exist and validate structurally: completed.
* Metric applicability is explicit: completed.
* Reports distinguish score groups: completed.
* Adaptive hybrid remains disabled: completed.

Risks:

* Coherent expected traces are structurally valid but not yet replay-proven.
* Response-quality scoring remains absent until Phase 5.
* Atomic reports may look numerically different because the primary score now excludes low-diagnostic categories.

Unresolved decisions:

* Exact coherent-suite pass thresholds remain for later calibration.
* Adaptive hybrid seed counts and cost caps remain for Phase 6.

Exact next task:

* Completed. Current next task is tracked under Phase 2.

## Phase 2: Parallel Objection Handling

Status: completed.

Depends on:

* Phase 1 suite separation.
* `docs/audit/PARALLEL_OBJECTION_RUNTIME_AUDIT.md`.

Files changed:

* `docs/architecture/PARALLEL_OBJECTION_DESIGN.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
* `src/movia_sales_agent/contracts/commercial.py`
* `src/movia_sales_agent/models/schemas.py`
* `src/movia_sales_agent/services/openai_service.py`
* `src/movia_sales_agent/agent/planners.py`
* `src/movia_sales_agent/agent/objections.py`
* `src/movia_sales_agent/agent/stages.py`
* `src/movia_sales_agent/agent/response.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/db/repository.py`
* `supabase/migrations/202606050001_parallel_objection_mode_v3.sql`
* `tests/test_stage_machine.py`
* `tests/test_objection_flow.py`
* `docs/implementation/PHASE_V3_2_REPORT.md`
* `PLAN_V3.md`

Migrations:

* Created `supabase/migrations/202606050001_parallel_objection_mode_v3.sql`.
* Local/evaluation only; production migration was not applied.

Tests and acceptance:

* `.venv/bin/python -m compileall src/movia_sales_agent`: passed.
* `.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py -q`: 59 passed, 1 warning.
* `.venv/bin/pytest -q`: 68 passed, 1 warning.
* `.venv/bin/movia-eval validate-dataset`: passed, atomic 5 scenarios / 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`: passed, coherent 5 scenarios / 41 turns.
* Soft concerns do not create persistent blocking objections by default: completed.
* Hard objections persist independently from primary sales stage: completed.
* `sales_stage` no longer becomes or remains frozen as `objection_handling`: completed.
* Current exact intent can be answered during active objections: completed.
* Hard unresolved objections still block direct close: completed.
* Semantic evidence, not fixed turn count, resolves objections: completed.
* No new always-on LLM call: completed.

Risks:

* The local/evaluation conversation-mode migration has not been applied to production.
* Coherent scripted expectations are not replay-calibrated after Phase 2.

Exact next task:

* Completed. Current next task is tracked under Phase 3.

## Phase 3: Memory Correction And Memory Evaluation

Status: completed.

Depends on:

* Phase 2 objection/stage semantics.
* Phase 1 coherent suite framework.

Files changed:

* `docs/architecture/CONVERSATIONAL_MEMORY_V3.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
* `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
* `docs/implementation/PHASE_V3_3_REPORT.md`
* `movia_validation_package/movia_coherent_scripted_conversations.json`
* `src/movia_sales_agent/contracts/commercial.py`
* `src/movia_sales_agent/models/schemas.py`
* `src/movia_sales_agent/services/openai_service.py`
* `src/movia_sales_agent/agent/memory.py`
* `src/movia_sales_agent/agent/planners.py`
* `src/movia_sales_agent/agent/response.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/evaluation/scoring.py`
* `tests/test_memory_v3.py`
* `tests/test_response_context.py`
* `tests/test_evaluation.py`
* `PLAN_V3.md`

Migrations:

* None.

Tests and acceptance:

* `.venv/bin/python -m compileall src/movia_sales_agent`: passed.
* `.venv/bin/pytest tests/test_memory_v3.py -q`: 7 passed, 1 warning.
* `.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py tests/test_memory_v3.py -q`: 66 passed, 1 warning.
* `.venv/bin/pytest -q`: 75 passed, 1 warning.
* `.venv/bin/movia-eval validate-dataset`: passed, atomic 5 scenarios / 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`: passed, coherent 7 scenarios / 57 turns.
* Known slots are never casually re-requested: completed.
* Discovery/soft-question CTAs cannot have null `next_question_key`: completed.
* Product fit derives from action requirement when deterministic: completed.
* Prior-message retrieval runs conditionally: completed.
* Prior references return relevant evidence: completed.
* No cross-lead contamination: completed.

Risks:

* Prior-message retrieval currently uses recent message pairs only; Postgres full-text and semantic fallback are deferred.
* Memory scenarios are structurally valid but not replay-calibrated.

Exact next task:

* Completed. Current next task is tracked under Phase 4.

## Phase 4: RAG Audit And Routing Improvement

Status: completed.

Depends on:

* Phase 1 retrieval metric separation.
* Phase 3 memory context boundaries.

Files changed:

* `docs/audit/RAG_USAGE_AUDIT_V3.md`
* `docs/architecture/RAG_ROUTING_POLICY_V3.md`
* `docs/implementation/PHASE_V3_4_REPORT.md`
* `src/movia_sales_agent/agent/rag_policy.py`
* `src/movia_sales_agent/agent/planners.py`
* `src/movia_sales_agent/agent/graph.py`
* `src/movia_sales_agent/agent/response.py`
* `src/movia_sales_agent/models/schemas.py`
* `src/movia_sales_agent/services/rag.py`
* `src/movia_sales_agent/ingestion/chunker.py`
* `src/movia_sales_agent/evaluation/scoring.py`
* `tests/test_rag_v3.py`
* `PLAN_V3.md`

Migrations:

* None.

Tests and acceptance:

* `.venv/bin/pytest tests/test_rag_v3.py -q`: 5 passed, 1 warning.
* `.venv/bin/python -m compileall src/movia_sales_agent`: passed.
* `.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py tests/test_memory_v3.py tests/test_rag_v3.py -q`: 71 passed, 1 warning.
* `.venv/bin/pytest -q`: 80 passed, 1 warning.
* `.venv/bin/movia-eval validate-dataset`: passed, atomic 5 scenarios / 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`: passed, coherent 7 scenarios / 57 turns.
* Exact price/policy/platform questions do not trigger unnecessary RAG: completed.
* Industry questions use relevant industry documents: completed.
* Comparison questions use relevant comparison documents: completed.
* Irrelevant low-score chunks are rejected: completed.
* RAG metrics evaluate necessity, routing, relevance and groundedness: completed.
* No commercial fact is overridden by RAG: completed.
* Average context does not grow significantly: completed.

Risks:

* Existing remote RAG rows may need re-ingestion before they include the new `comparison_target` and `product` alias metadata.
* Deterministic groundedness remains conservative and does not replace future optional RAGAS/judge evaluation.

Exact next task:

* Completed. Current next task is tracked under Phase 5.

## Phase 5: Response Quality Evaluation

Status: completed.

Depends on:

* Stable Phase 1 evaluation contracts.
* Phase 2-4 runtime fixes.

Files changed:

* `docs/evaluation/RESPONSE_QUALITY_RUBRIC.md`
* `docs/evaluation/RESPONSE_QUALITY_CALIBRATION.md`
* `docs/evaluation/RESPONSE_QUALITY_PHASE5_SAMPLE_REPORT.md`
* `docs/implementation/PHASE_V3_5_REPORT.md`
* `movia_validation_package/response_quality_calibration.json`
* `src/movia_sales_agent/evaluation/response_quality.py`
* `src/movia_sales_agent/evaluation/runner.py`
* `src/movia_sales_agent/evaluation/cli.py`
* `src/movia_sales_agent/evaluation/reporting.py`
* `src/movia_sales_agent/evaluation/scoring.py`
* `tests/test_response_quality_v3.py`
* `tests/test_evaluation.py`
* `PLAN_V3.md`

Migrations:

* None.

Tests and acceptance:

* `.venv/bin/pytest tests/test_response_quality_v3.py -q`: 6 passed, 1 warning.
* `.venv/bin/pytest tests/test_evaluation.py -q`: 14 passed, 1 warning.
* `.venv/bin/python -m compileall src/movia_sales_agent`: passed.
* `.venv/bin/pytest tests/test_response_quality_v3.py tests/test_evaluation.py tests/test_memory_v3.py tests/test_rag_v3.py tests/test_response_context.py -q`: 36 passed, 1 warning.
* `.venv/bin/pytest -q`: 86 passed, 1 warning.
* `.venv/bin/movia-eval validate-dataset`: passed, atomic 5 scenarios / 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`: passed, coherent 7 scenarios / 57 turns.
* `.venv/bin/movia-eval run --scenario MOVIA-VAL-001 --max-turns 1 --offline --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase5-smoke`: passed command execution and emitted response-quality metrics.
* Quality scores are separate from trace correctness: completed.
* Rubric includes next-question quality: completed.
* Known-slot repetition is visible as a critical response defect: completed.
* Judge outputs are structured and reproducible: completed.
* Calibration against human examples is documented: completed.
* No runtime cost is added: completed.

Risks:

* Live LLM response-quality judge calibration was not run because it is intentionally opt-in.
* Deterministic quality scoring should be compared with live judge output during Phase 6 if budget is approved.
* The one-turn CLI smoke is not a full replay or deployment signal.

Exact next task:

* Begin Phase 6 only: integrated validation and hybrid predeploy preparation.

## Phase 6: Integrated Validation And Hybrid Predeploy

Status: completed.

Depends on:

* Phases 1-5 complete.
* Safe evaluation DB available for persistence checks.
* Explicit user approval to use the configured production database for this test run.

Files changed:

* `src/movia_sales_agent/evaluation/phase6.py`
* `tests/test_phase6.py`
* `supabase/migrations/202606040001_stage_machine_v2.sql`
* `docs/evaluation/PHASE6_DB_PERSISTENCE_REPORT.md`
* `docs/evaluation/PHASE6_GATE_REPORT.md`
* `docs/evaluation/PHASE6_OPENAI_REPLAY_REPORT.md`
* `docs/evaluation/V2_VS_V3_COMPARISON.md`
* `docs/implementation/PHASE_V3_6_REPORT.md`
* `PLAN_V3.md`
* `artifacts/evaluations/phase6-db-smoke/`
* `artifacts/evaluations/phase6-atomic-db-deterministic/`
* `artifacts/evaluations/phase6-coherent-db-deterministic/`
* `artifacts/evaluations/phase6-openai-smoke/`
* `artifacts/evaluations/phase6-atomic-db-openai/`
* `artifacts/evaluations/phase6-coherent-db-openai/`

Migrations:

* Applied to the configured Supabase database after explicit user approval:
  * `202606040001_stage_machine_v2`
  * `202606040002_active_objection_v2`
  * `202606050001_parallel_objection_mode_v3`
* `202606030001_init_movia_sales_agent` was already applied.
* Patched `202606040001_stage_machine_v2` to drop the old stage check constraint before normalizing legacy `recommended` values to `solution_recommended`.
* Refreshed structured seeds with `scripts/seed_database.py`.
* Refreshed RAG rows with `scripts/ingest_rag.py`.

Tests and acceptance:

* `.venv/bin/python scripts/apply_migrations.py`: completed after migration-order patch.
* `.venv/bin/python scripts/seed_database.py`: completed.
* `.venv/bin/python scripts/ingest_rag.py`: completed, 13 docs / 13 chunks.
* `.venv/bin/pytest tests/test_phase6.py -q`: 4 passed, 1 warning.
* `.venv/bin/python -m compileall src/movia_sales_agent/evaluation`: passed.
* `.venv/bin/pytest -q`: 90 passed, 1 warning.
* `.venv/bin/movia-eval validate-dataset`: passed, atomic 5 scenarios / 60 turns.
* `.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json`: passed, coherent 7 scenarios / 57 turns.
* DB smoke run completed:
  * Run ID: `movia-eval-20260606T063901Z-d60d50`
  * Overall: `0.9766`
  * Hard failures: `0`
* Live full atomic DB run was interrupted because OpenAI blocked inside `responses.create`; no final artifact was produced for that interrupted run.
* Atomic DB deterministic run completed:
  * Run ID: `movia-eval-20260606T064839Z-e61463`
  * Overall: `0.9626`
  * Hard failures: `0`
  * Phase 6 gates: passed.
* Coherent DB deterministic run completed:
  * Run ID: `movia-eval-20260606T065555Z-7b83ad`
  * Overall: `0.8454`
  * Hard failures: `0`
  * Phase 6 gates: failed.
* Direct OpenAI `responses.create` smoke completed:
  * Text call: `2.48s`
  * JSON-schema call: `2.23s`
* Two-turn MovIA OpenAI smoke completed:
  * Run ID: `movia-eval-20260606T193215Z-de601a`
  * Total tokens: `2,389`
* Atomic DB OpenAI run completed:
  * Run ID: `movia-eval-20260606T193317Z-bd6909`
  * Overall: `0.9133`
  * Hard failures: `0`
  * Total tokens: `196,247`
* Coherent DB OpenAI run completed:
  * Run ID: `movia-eval-20260606T194627Z-44595c`
  * Overall: `0.8267`
  * Hard failures: `2`
  * Total tokens: `173,866`
* Combined OpenAI agent tokens:
  * Input tokens: `331,427`
  * Output tokens: `38,686`
  * Total tokens: `370,113`
* Atomic progression remained diagnostic: completed.
* Coherent progression and objection resolution were authoritative: completed.
* Adaptive hybrid was not run because deterministic coherent gates failed: completed.
* Final recommendation: `NOT READY`.

Unresolved issues:

* Coherent sales progression failed: `0.2895` vs `0.700`.
* Known-slot critical repetitions failed: `4` vs `0`.
* Coherent response defects remain: `poor_next_step`, `did_not_answer_question`, and `asked_known_information`.
* Long live validation runs completed on retry, but OpenAI request timeout/retry handling is still recommended.
* Coherent OpenAI replay hard failures:
  * `MOVIA-COH-004`, turn 2: Instagram presented as currently available.
  * `MOVIA-COH-004`, turn 5: Captura overclaimed as performing unsupported external actions.
* RAGAS and DeepEval remain skipped because deterministic gates already failed and cost control was preferred.

Exact next task:

* Fix coherent progression and known-slot repetition issues, then rerun deterministic Phase 6 gates before attempting adaptive hybrid or any pilot.
