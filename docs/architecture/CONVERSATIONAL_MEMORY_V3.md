# Conversational Memory V3

Date: 2026-06-05

## Purpose

Phase V3.3 fixes memory usage without adding a large memory system. The main failure was not storage; the agent already had lead facts but could still ask for them again.

The V3 memory contract separates:

```text
structured lead memory
recent conversation evidence
response guardrails
evaluation metrics
```

## Structured Memory

The runtime computes known and missing slots deterministically:

```text
business_type
main_channel
pain_or_goal
action_requirement
known_product_fit
```

Product fit is derived in code:

```text
answers_only -> movia_captura
external_actions_required -> movia_hibrido
```

This prevents the planner from leaving `known_product_fit=unknown` when `action_requirement` already decides the fit.

## Question Contract

For `discovery_question` and `soft_question` CTAs:

```text
next_question_key must be non-null
```

If all safe discovery questions are already known, the planner downgrades the CTA to:

```text
cta_type = none
```

The response package also includes:

```json
{
  "memory_context": {
    "known_slots": {},
    "missing_slots": [],
    "forbidden_question_keys": []
  }
}
```

The generator must not ask a forbidden question.

## Response Guardrail

After response generation, the runtime validates whether the answer asks for known information again.

If it detects a violation, it corrects the final CTA deterministically without adding another LLM call.

Example replacement:

```text
Con lo que ya me compartiste, puedo avanzar sin volver a preguntarte esos datos.
¿Quieres que te explique el proceso para iniciar o prefieres ver el demo?
```

The correction is logged in:

```text
response_metadata.memory_validation
```

## Prior-Message Detection

`TurnAnalysis` now emits:

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
none
explicit_turn
temporal_reference
topic_reference
entity_reference
assistant_commitment_reference
```

## Conditional Retrieval

Conversation memory evidence is retrieved only when:

```text
references_prior_message = true
```

The first implementation uses the current lead's recent message buffer and returns up to three turn pairs:

```json
{
  "turn_id": 2,
  "user_message": "...",
  "assistant_message": "...",
  "relevance_reason": "assistant_commitment_reference"
}
```

It does not send the full conversation and does not run embeddings.

## Evaluation Metrics

Phase V3.3 adds deterministic memory metrics:

```text
memory.known_slot_repetition
memory.historical_reference_accuracy
memory.prior_commitment_consistency
memory.contextual_personalization
```

These use emitted agent fields only.

## Non-Goals

- No production migration.
- No semantic message embeddings.
- No full replay.
- No new always-on LLM call.
- No cross-lead shared memory.
