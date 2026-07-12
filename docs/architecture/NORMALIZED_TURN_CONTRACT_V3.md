# Normalized Turn Contract V3

Version: `3.2`

## Purpose

The normalized turn contract is the deterministic layer between Analyzer Contract V3 and the existing commercial runtime.

Analyzer V3 observes language. The normalizer derives logically dependent commercial interpretation.

```text
analyze_turn
→ normalize_and_derive_turn
→ update_lead_state
```

## Source Of Truth

Runtime source:

```text
src/movia_sales_agent/analyzer/normalizer.py
```

## Derived Fields

The normalizer derives:

- `has_objection`
- `has_prior_reference`
- `explicit_start_intent`
- `is_post_purchase`
- `action_requirement`
- `product_references`
- transitional singular `requested_product`, derived only when one product is unambiguous
- `recommended_product`
- `selected_product`
- `product_preference_mismatch`
- `known_slots`
- `missing_slots`
- normalized objection evidence
- normalized prior-reference evidence
- parser/LLM telemetry
- contradictions and normalization warnings

## Key Rules

Action requirement:

```text
valid requested_actions → external_actions_required
valid requested_capabilities → answers_only
otherwise → unknown
```

Product recommendation:

```text
answers_only → movia_captura
external_actions_required → movia_hibrido
unknown → null
```

Product references, recommended product and selected product remain separate. A
mention, comparison, or question never selects a product. Only an explicit,
compatible `committed` reference may update selection. Unavailable products are
never selected.

Active-objection relation is normalized independently from a new objection
candidate. This allows a turn to resolve, clarify, reaffirm, continue, or remain
unrelated to an existing objection without inventing another objection.
If the analyzer omits the relation while an objection is active and no new
candidate exists, normalization records a contradiction and conservatively uses
`unrelated`; it does not clear the objection.

## Evidence Validation

Required evidence spans are rechecked against the current user message. Invalid evidence is normalized away and recorded as a contradiction.

Examples:

- invalid objection evidence → `invalid_objection_evidence`
- invalid prior-reference evidence → `invalid_prior_reference_evidence`
- explicit start without valid evidence → `explicit_start_without_valid_evidence`
- unavailable requested product → `unavailable_product_not_selected`
- missing relation with active objection → `missing_active_objection_relation_defaults_unrelated`

## Parser Telemetry

Shadow parser candidates are compared with analyzer observations.

Each category records:

- `agreement`
- `parser_only`
- `llm_only`
- `conflict`

The parser remains non-authoritative. Parser-only values do not change `action_requirement`, product recommendation, selected product, planner behavior or memory updates.

## Compatibility

The current planner still consumes `TurnAnalysis`. The normalized contract
provides one-way aliases for legacy consumers. V3.2 semantic fields remain the
source of truth and legacy aliases cannot compete with them.
