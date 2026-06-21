# Phase V3.2 Report: Parallel Objection Handling

Date: 2026-06-05

## Summary

Phase V3.2 is complete. The agent now treats objections as a parallel overlay instead of using `objection_handling` as the primary persisted sales stage.

Soft concerns stay inline by default. Hard objections persist in `active_objection`, set `conversation_mode=handling_objection`, preserve the current commercial stage, and continue to block premature closing until semantic resolution.

## Files Changed

- `docs/architecture/PARALLEL_OBJECTION_DESIGN.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.md`
- `docs/architecture/COMMERCIAL_CONTRACT_V2.json`
- `src/movia_sales_agent/contracts/commercial.py`
- `src/movia_sales_agent/models/schemas.py`
- `src/movia_sales_agent/services/openai_service.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/objections.py`
- `src/movia_sales_agent/agent/stages.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/db/repository.py`
- `supabase/migrations/202606050001_parallel_objection_mode_v3.sql`
- `tests/test_stage_machine.py`
- `tests/test_objection_flow.py`
- `PLAN_V3.md`

## Contract Changes

- Added `ObjectionRelation`.
- Added `ObjectionStatus`.
- Added `ConversationMode`.
- Added `TurnAnalysis.objection_relation`.
- Added `AnalysisConfidence.objection_relation`.
- Added `SalesPlan.objection_overlay`.
- Added `StageTransition.conversation_mode`.
- Added `ActiveObjection.status`, `relation`, `paused_reason`, and `resolved_reason`.
- Marked `SalesStage.objection_handling` as deprecated for primary persisted stage use.

## Runtime Decisions

- Soft concerns no longer automatically create persistent `active_objection`.
- Hard objections persist independently from `current_stage`.
- Exact questions during a hard objection pause the objection overlay and answer the current intent.
- Semantic resolution can unblock direct close when the user both resolves the concern and explicitly asks to start.
- Unresolved hard objections still block direct close.
- No new always-on LLM call was added.

## Migration

Created local/evaluation migration only:

```text
supabase/migrations/202606050001_parallel_objection_mode_v3.sql
```

It adds `movia_lead_profiles.conversation_mode` and an index for `handling_objection`.

This migration was not applied to production.

## Tests Run

```bash
.venv/bin/python -m compileall src/movia_sales_agent
.venv/bin/pytest tests/test_commercial_contract.py tests/test_agent_policy.py tests/test_stage_machine.py tests/test_objection_flow.py tests/test_response_context.py tests/test_evaluation.py -q
.venv/bin/pytest -q
.venv/bin/movia-eval validate-dataset
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
```

Results:

- Compile check passed.
- `59 passed, 1 warning`.
- Full local pytest passed: `68 passed, 1 warning`.
- Atomic dataset validation passed: 5 scenarios, 60 turns.
- Coherent dataset validation passed: 5 scenarios, 41 turns.

Warnings:

- Existing environment warning: urllib3 reports LibreSSL instead of OpenSSL.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Soft concerns do not freeze the funnel: completed.
- Hard objections persist independently: completed.
- `sales_stage` no longer becomes `objection_handling`: completed.
- Current exact intent can be processed during active objection: completed.
- Hard unresolved objections still protect closing: completed.
- Objections resolve based on semantic evidence: completed.
- Resolution does not return a mature lead to `new`: completed.
- No new always-on LLM call: completed.

## Unresolved Issues

- The local/evaluation `conversation_mode` migration is not applied to production.
- Coherent-suite expected traces remain structurally valid but not replay-calibrated after Phase V3.2.
- Memory issues remain intentionally deferred to Phase V3.3.
- RAG retrieval issues remain intentionally deferred to Phase V3.4.

## Exact Next Task

Begin Phase V3.3 only: memory correction and memory evaluation, using `PLAN_V3.md` as the operational tracker.
