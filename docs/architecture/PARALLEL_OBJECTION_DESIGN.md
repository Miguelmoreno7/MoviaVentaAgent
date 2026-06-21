# Parallel Objection Design

Date: 2026-06-05

## Purpose

Phase V3.2 replaces the old exclusive objection-stage behavior with a parallel overlay:

```text
commercial sales stage = where the lead is in the funnel
conversation mode = whether an objection overlay is active
active objection = persisted hard objection lifecycle
```

This keeps exact informational turns usable while preserving hard closing gates.

## State Model

Runtime lead state can now represent:

```json
{
  "current_stage": "educating",
  "conversation_mode": "handling_objection",
  "active_objection": {
    "active": true,
    "type": "price_objection",
    "strength": "hard",
    "status": "paused",
    "relation": "unrelated",
    "current_step": "thank_empathize_ask_open_question",
    "stage_before_objection": "educating"
  }
}
```

`objection_handling` remains in `SalesStage` only for migration compatibility. New planner output must not target it as the primary persisted stage.

## Routing Rules

Soft concerns:

- stay inline by default;
- set `SalesPlan.objection_overlay.inline=true`;
- do not create persistent `active_objection`;
- do not switch `conversation_mode` away from `normal`.

Hard objections:

- create or update `active_objection`;
- set `conversation_mode=handling_objection`;
- preserve the commercial `current_stage`;
- block `soft_close` and `direct_close` until resolved;
- allow exact questions to be answered by pausing the objection overlay.

Resolution:

- uses `TurnAnalysis.objection_relation=resolved`;
- marks `active_objection.status=resolved`;
- returns `conversation_mode=normal`;
- does not reset mature stages back to `new`.

## Planner Contract

The planner still emits one canonical `macro_action`, but now attaches an optional `objection_overlay`:

```json
{
  "macro_action": "explain_process",
  "target_stage": "educating",
  "objection_overlay": {
    "mode": "handling_objection",
    "status": "paused",
    "blocking_close": true,
    "response_instruction": "Responde primero la intencion actual..."
  }
}
```

The overlay can constrain CTA and tone, but it must not arbitrarily replace the primary turn action.

## Semantic Progression

Objection flow steps no longer advance only because another turn occurred.

- new hard objection -> `thank_empathize_ask_open_question`
- clarified blocker -> `clarify_value`
- value/business reason after clarification -> `tie_solution`
- proof/evidence request -> `provide_proof`
- acceptance -> `resolved`
- unrelated exact question -> pause and answer current intent

## Persistence

`active_objection` remains JSONB. Phase V3.2 adds local/evaluation migration:

```text
supabase/migrations/202606050001_parallel_objection_mode_v3.sql
```

The migration adds `movia_lead_profiles.conversation_mode` with values:

```text
normal
handling_objection
```

It is not applied to production in this phase.

## Non-Goals

- No LangGraph subgraph for objections.
- No new always-on LLM call.
- No production migration application.
- No full evaluation replay.
