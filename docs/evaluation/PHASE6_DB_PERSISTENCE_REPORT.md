# Phase 6 DB Persistence Report

Date: 2026-06-06

## Database Target

The configured `DATABASE_URL` points to the Supabase pooler host:

```text
aws-0-us-east-2.pooler.supabase.com
```

Miguel explicitly approved using this production database for this test run.

## Migration Status

Applied migrations:

- `202606030001_init_movia_sales_agent`
- `202606040001_stage_machine_v2`
- `202606040002_active_objection_v2`
- `202606050001_parallel_objection_mode_v3`

Required Phase 6 lead-profile columns are present:

- `previous_stage`
- `stage_before_objection`
- `stage_reason_code`
- `stage_reason`
- `stage_entered_at`
- `stage_updated_at`
- `active_objection`
- `conversation_mode`

## Migration Note

The first attempt to apply `202606040001_stage_machine_v2` failed because the migration tried to normalize `current_stage='recommended'` to `solution_recommended` before dropping the old stage check constraint.

The transaction rolled back and did not record the migration. The migration file was patched to drop the old constraint before updating legacy stage values, then all migrations applied successfully.

Legacy stage impact:

- 12 existing lead rows moved from `recommended` to `solution_recommended`.

## Seed And RAG Ingestion

Completed:

```bash
.venv/bin/python scripts/seed_database.py
.venv/bin/python scripts/ingest_rag.py
```

RAG ingestion refreshed 13 documents and 13 chunks.

Current table counts after Phase 6 deterministic runs:

| Table | Rows |
|---|---:|
| `movia_products` | 4 |
| `movia_policies` | 5 |
| `movia_lead_profiles` | 48 |
| `movia_conversation_messages` | 494 |
| `movia_knowledge_documents` | 13 |
| `movia_knowledge_chunks` | 13 |

## Read-After-Write Verification

Atomic DB deterministic run:

- Run ID: `movia-eval-20260606T064839Z-e61463`
- Leads persisted: 5
- Messages persisted: 120
- User messages: 60
- Assistant messages: 60
- Assistant messages with retrieval metadata: 60
- Leads with `stage_updated_at`: 5
- Leads with non-empty `active_objection`: 5
- Leads in `handling_objection` mode: 1

Coherent DB deterministic run:

- Run ID: `movia-eval-20260606T065555Z-7b83ad`
- Leads persisted: 7
- Messages persisted: 114
- User messages: 57
- Assistant messages: 57
- Assistant messages with retrieval metadata: 57
- Leads with `stage_updated_at`: 7
- Leads with non-empty `active_objection`: 7
- Leads in `handling_objection` mode: 1

## Persistence Evidence

Sales-stage persistence is working: evaluation leads persisted `current_stage`, `previous_stage`, `stage_reason_code`, and `stage_updated_at`.

Active-objection persistence is working: `MOVIA-COH-003` persisted a hard `price_objection` with `conversation_mode='handling_objection'`, `current_step='clarify_value'`, and accumulated evidence.

Historical-message retrieval is working at the metric level:

- Atomic suite: `memory.historical_reference_accuracy` passed on 2 turns.
- Coherent suite: `memory.historical_reference_accuracy` passed on 3 turns.

## Production Caution

This test wrote evaluation leads and messages into the production database under `channel='evaluation'`. They are tagged by run ID and can be filtered by `external_user_id like 'movia-eval-%'`.
