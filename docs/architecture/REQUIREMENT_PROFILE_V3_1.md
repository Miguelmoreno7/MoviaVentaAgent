# Requirement Profile V3.1

Version: `1.0`

## Purpose

Phase 2 introduces a deterministic persisted requirement profile under:

```text
movia_lead_profiles.profile_data.requirement_profile
```

This profile separates:

- observed business problems;
- informational future-agent capabilities;
- sales future-agent capabilities;
- external future-agent actions;
- declared external-action count.

The current turn contributes a delta. It does not replace the full profile.

## Persistence Shape

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

Each persisted item stores:

- canonical `type`;
- literal `evidence_span`;
- `source_turn`;
- `strength`;
- `active`.

## Current-Turn Delta

The deterministic delta uses:

- `no_update`
- `merge`
- `explicit_correction`
- `explicit_removal`

Absence of a new requirement means `no_update`, not `unknown`.

## Deterministic Requirement Class

Derived from active persisted requirements only:

```text
sales + external_actions -> mixed_advanced
sales only -> sales_persuasion
external_actions only -> external_actions
informational only -> informational_only
otherwise -> unknown
```

Observed business problems never determine requirement class.

## Compatibility Mapping

Legacy planner/runtime compatibility fields are now derived only from the persisted profile:

- `informational_only` -> `action_requirement=answers_only`
- `external_actions` -> `action_requirement=external_actions_required`
- otherwise -> `action_requirement=unknown`

## Deterministic Product Fit

Current official policy mapping:

- `unknown` -> no recommendation
- `informational_only` -> `movia_captura`
- `external_actions` -> `movia_hibrido` when standard scope
- `sales_persuasion` -> `movia_ventas_unavailable`
- `mixed_advanced` -> `custom_review`

If the declared or active external-action count exceeds the standard limit, product fit becomes `custom_review`.

## Scope Flags

Phase 2 derives compact scope flags for planner and response-package use:

- `unsupported_scope`
- `custom_scope_review_required`
- `product_unavailable`
- `product_preference_mismatch`

## Direct-Close Gate

Direct close now requires:

- explicit start intent;
- confirmed or selected product;
- available compatible product fit;
- no unresolved scope flags that block closing.

## Source Of Truth

Runtime sources:

```text
src/movia_sales_agent/agent/requirements.py
src/movia_sales_agent/agent/memory.py
src/movia_sales_agent/agent/planners.py
```
