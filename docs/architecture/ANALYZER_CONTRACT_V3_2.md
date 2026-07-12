# Analyzer Contract V3.2

Version: `3.2`

## Boundary

Analyzer Contract V3.2 observes independent linguistic facts from the current user message. The analyzer receives recent messages and a compact, turn-local `interaction_context`, but it does not choose product fit, sales stage, planner action, CTA, knowledge routing, or closing permission.

The interaction context contains only existing runtime facts:

- the immediately previous planner action, CTA, question key, actual question, and target product;
- current requirement summary, product context, and active objection;
- an explicit actor boundary: the current interlocutor is the MovIA salesperson,
  while future requirement fields target only the purchased agent.

It is not persisted as lead state and does not introduce an actor-target output.

## Semantic Split

- `observed_business_problems` describes current operational pain.
- `requested_agent_capabilities` describes capabilities explicitly requested for the future purchased agent.
- `requested_agent_actions` describes future actions in workflows or external systems.
- Current requests to the MovIA salesperson, including prices, app links, checkout help, or calls, must not become future-agent requirements.

When requirement observations are present, `requirement_update_intent` must be
`merge` or `replace`; `no_change` cannot carry requirement observations.

The existing intent taxonomy remains unchanged: one primary intent plus zero or more secondary intents.

## Product References

`product_references` contains every product literally referenced in the current message. Each entry contains `product`, `evidence_span`, and one role:

- `question_subject`
- `comparison_alternative`
- `preferred`
- `committed`
- `mentioned`

A mention, question, comparison, or preference is not a selection. Only explicit compatible commitment may become selected product. The legacy singular `requested_product` is derived downstream only when one unambiguous product exists.

Product evidence must literally name that product in the current message.
Conversation context may identify the active product, but it cannot manufacture a
product reference for a deictic phrase such as "esa parte".

## Objection Relation

`objection_candidate` represents only a new or continuing objection expressed in the current message. It contains type, strength, and literal evidence.

`active_objection_relation` independently relates the current message to an already active objection:

- `none`
- `resolved`
- `clarified`
- `reaffirmed`
- `continuation`
- `unrelated`

This relation may be present when `objection_candidate.type=none`. A new objection relation is derived by code and is not emitted in this field.

When an active objection exists, `none` is not a usable runtime relation. A
missing relation falls back conservatively to `unrelated`, which preserves the
blocker and never clears it by inference.

## Evidence And Compatibility

Every semantic observation requires literal current-message evidence. Action
evidence must also support the selected action ontology value. Invalid evidence
is repaired or dropped field-locally without discarding the rest of a usable
payload.

Compatibility is one-way from V3.2 into temporary normalized aliases. Legacy singular product and objection-relation fields are not accepted as peer analyzer inputs.

## Source Of Truth

Runtime source:

```text
src/movia_sales_agent/analyzer/contract_v3.py
```

Machine-readable summary:

```text
docs/architecture/ANALYZER_CONTRACT_V3_2.json
```
