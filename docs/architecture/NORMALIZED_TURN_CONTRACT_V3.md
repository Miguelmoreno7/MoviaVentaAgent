# Normalized Turn Contract V3

Version: `3.0`

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
- `requested_product`
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

Requested product, recommended product and selected product remain separate. Unavailable products are never selected.

## Evidence Validation

Required evidence spans are rechecked against the current user message. Invalid evidence is normalized away and recorded as a contradiction.

Examples:

- invalid objection evidence → `invalid_objection_evidence`
- invalid prior-reference evidence → `invalid_prior_reference_evidence`
- explicit start without valid evidence → `explicit_start_without_valid_evidence`
- unavailable requested product → `unavailable_product_not_selected`

## Parser Telemetry

Shadow parser candidates are compared with analyzer observations.

Each category records:

- `agreement`
- `parser_only`
- `llm_only`
- `conflict`

The parser remains non-authoritative. Parser-only values do not change `action_requirement`, product recommendation, selected product, planner behavior or memory updates.

## Phase 2 Compatibility

The current planner still consumes `TurnAnalysis`. Phase 2 converts the normalized turn into planner-compatible `TurnAnalysis` after normalization.

Phase 3 should adapt the Sales Policy Planner to consume the normalized contract directly.

