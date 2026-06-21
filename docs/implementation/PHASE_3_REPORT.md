# Phase 3 Report: Persistent Sales-Stage Machine

Date: 2026-06-04  
Master reference: `PLANV2.md`  
Operational plan: `PLAN.md`

## Summary

Phase 3 adds a persistent sales-stage machine for MovIA Sales Agent V2. The agent no longer derives `current_stage` from the current macroaction through a hard-coded action map. Instead, planner `target_stage` is resolved by `SalesStageTransitionService` against persisted lead stage state, controlled transition rules, and objection-stage preservation rules.

No production migrations, deployments, or full validation replay were run.

## Completed Work

- Added `StageTransition` runtime model with:
  - `current_stage`
  - `previous_stage`
  - `stage_before_objection`
  - `stage_reason_code`
  - `stage_reason`
  - `stage_changed`
  - `normalized_from`
  - `invalid_transition`
- Added `SalesStageTransitionService`.
- Added V1-to-V2 stage normalization:
  - `recommended -> solution_recommended`
  - `unknown -> unknown_recovery`
- Implemented controlled stage transitions, including:
  - normal progression from discovery/education/qualification to recommendation
  - explicit direct close into `closing`
  - post-purchase handoff into `handoff`
  - objection entry into `objection_handling`
  - invalid transition normalization instead of silent jumps
- Preserved `previous_stage` and `stage_before_objection` when entering objection handling.
- Added a `stage_transition` LangGraph node between policy planning and knowledge planning.
- Removed the old `_stage_for_action(...)` projection from the response path.
- Updated repository persistence for DB mode and local/offline fallback.
- Added an in-memory lead profile store for disabled-DB local testing so stage can persist between turns.
- Added local-only migration:
  - `supabase/migrations/202606040001_stage_machine_v2.sql`
- Updated architecture docs and `PLAN.md`.

## Files Changed

- `src/movia_sales_agent/agent/stages.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/db/repository.py`
- `src/movia_sales_agent/models/schemas.py`
- `tests/test_stage_machine.py`
- `supabase/migrations/202606040001_stage_machine_v2.sql`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `PLAN.md`
- `docs/implementation/PHASE_3_REPORT.md`

## Migration

Created but did not apply:

```text
supabase/migrations/202606040001_stage_machine_v2.sql
```

The migration:

- Adds `previous_stage`, `stage_before_objection`, `stage_reason_code`, `stage_reason`, `stage_entered_at`, and `stage_updated_at`.
- Maps old compact stages to V2 where needed.
- Replaces the old stage check constraint with the full Contract V2 stage vocabulary.
- Adds constraints for nullable previous-stage fields.
- Adds an index on `(current_stage, stage_updated_at desc)`.
- Documents rollback mapping in SQL comments.

## Tests Run

```bash
.venv/bin/pytest tests/test_stage_machine.py tests/test_agent_policy.py tests/test_api.py tests/test_evaluation.py
```

Result: 35 passed.

```bash
.venv/bin/pytest tests
```

Result: 46 passed.

Warnings observed:

- `urllib3` LibreSSL/OpenSSL compatibility warning.
- LangGraph pending deprecation warning for default serializer settings.

## Guardrails Verified

- Full 60-turn evaluation was not run.
- Gold validation dataset was not modified.
- Migration was created locally but not applied.
- No deployment or production data change was performed.
- Phase 4 was not started.

## Deferred Issues

- Active objection state is still not persistent. Phase 3 preserves `stage_before_objection`, but Phase 4 must persist the full active-objection object and advance objection-flow steps.
- The migration has not been applied to any production database.
- Full validation replay remains deferred until all phases are complete.
- Evaluation gold label alignment remains Phase 5.

## Exact Next Task

Begin Phase 4 by persisting active objection state, advancing `objection_flow_step` across turns, and preventing unresolved hard objections from resetting or prematurely routing to close.
