# Phase V3.6 Report: Integrated Validation And Hybrid Predeploy

Date: 2026-06-06

## Summary

Phase V3.6 is complete.

Miguel approved using the configured production Supabase database for this test run. Required migrations were applied, seeds were refreshed, RAG documents were ingested, DB-mode deterministic validation suites were run, Phase 6 gates were evaluated, and deployment recommendation was documented.

Final recommendation:

```text
NOT READY
```

Reason: coherent scripted conversation gates failed. The later OpenAI-enabled replay also produced hard failures in `MOVIA-COH-004`. Adaptive hybrid was not run.

## Files Changed

- `docs/evaluation/PHASE6_DB_PERSISTENCE_REPORT.md`
- `docs/evaluation/PHASE6_GATE_REPORT.md`
- `docs/evaluation/PHASE6_OPENAI_REPLAY_REPORT.md`
- `docs/evaluation/V2_VS_V3_COMPARISON.md`
- `docs/implementation/PHASE_V3_6_REPORT.md`
- `src/movia_sales_agent/evaluation/phase6.py`
- `tests/test_phase6.py`
- `supabase/migrations/202606040001_stage_machine_v2.sql`
- `PLAN_V3.md`

## Database Actions

Applied migrations:

```bash
.venv/bin/python scripts/apply_migrations.py
```

Applied:

- `202606040001_stage_machine_v2`
- `202606040002_active_objection_v2`
- `202606050001_parallel_objection_mode_v3`

Already applied:

- `202606030001_init_movia_sales_agent`

The first migration attempt failed because `202606040001_stage_machine_v2` updated legacy stage values before dropping the old stage check constraint. The transaction rolled back. I patched the migration order, reran tests, and then applied successfully.

Seed and RAG refresh:

```bash
.venv/bin/python scripts/seed_database.py
.venv/bin/python scripts/ingest_rag.py
```

RAG ingestion refreshed 13 documents and 13 chunks.

## Validation Runs

Live DB smoke:

```bash
.venv/bin/movia-eval run --scenario MOVIA-VAL-001 --max-turns 1 --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-db-smoke
```

Result:

- Run ID: `movia-eval-20260606T063901Z-d60d50`
- Overall: `0.9766`
- Hard failures: `0`

Live full atomic DB run:

- Started, then interrupted.
- Reason: the process blocked inside `OpenAI responses.create()` during `analyze_turn`.
- No final run artifact was produced for this interrupted full live run.

Atomic DB deterministic run:

```bash
MOVIA_DISABLE_OPENAI=true .venv/bin/movia-eval run --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-atomic-db-deterministic
```

Result:

- Run ID: `movia-eval-20260606T064839Z-e61463`
- Overall: `0.9626`
- Hard failures: `0`
- Phase 6 atomic gates: passed.

Coherent DB deterministic run:

```bash
MOVIA_DISABLE_OPENAI=true .venv/bin/movia-eval run --dataset movia_validation_package/movia_coherent_scripted_conversations.json --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-coherent-db-deterministic
```

Result:

- Run ID: `movia-eval-20260606T065555Z-7b83ad`
- Overall: `0.8454`
- Hard failures: `0`
- Phase 6 coherent gates: failed.

OpenAI retry after the deterministic baseline:

- Direct `responses.create` text smoke completed in `2.48s`.
- Direct `responses.create` JSON-schema smoke completed in `2.23s`.
- Two-turn MovIA OpenAI smoke completed with `2,389` total tokens.

Atomic DB OpenAI run:

```bash
.venv/bin/movia-eval run --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-atomic-db-openai
```

Result:

- Run ID: `movia-eval-20260606T193317Z-bd6909`
- Overall: `0.9133`
- Hard failures: `0`
- Total tokens: `196,247`

Coherent DB OpenAI run:

```bash
.venv/bin/movia-eval run --dataset movia_validation_package/movia_coherent_scripted_conversations.json --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-coherent-db-openai
```

Result:

- Run ID: `movia-eval-20260606T194627Z-44595c`
- Overall: `0.8267`
- Hard failures: `2`
- Total tokens: `173,866`

Combined OpenAI agent tokens:

- Input tokens: `331,427`
- Output tokens: `38,686`
- Total tokens: `370,113`

## Gate Results

Database:

- Ready: yes.
- Missing migrations: none.
- Missing columns: none.

Atomic gates:

- Hard failures: pass.
- Commercial accuracy: pass.
- Policy compliance: pass.
- Scope control: pass.
- Memory consistency: pass.
- Source selection: pass.
- Response quality: pass.
- Known-slot critical repetitions: pass.
- Premature direct closes: pass.
- Irrelevant RAG injection: pass.

Coherent gates:

- Hard failures: pass.
- Commercial accuracy: pass.
- Policy compliance: pass.
- Scope control: pass.
- Memory consistency: pass.
- Source selection: pass.
- Response quality: pass.
- Sales progression: fail, `0.2895` vs `0.700`.
- Known-slot critical repetitions: fail, `4` vs `0`.
- Premature direct closes: pass.
- Irrelevant RAG injection: pass.

## Persistence Evidence

See:

- `docs/evaluation/PHASE6_DB_PERSISTENCE_REPORT.md`

Key evidence:

- Atomic run persisted 5 evaluation leads and 120 messages.
- Coherent run persisted 7 evaluation leads and 114 messages.
- Assistant messages persisted retrieval metadata.
- Stage columns persisted.
- Active objection state persisted.
- Historical memory evidence passed on atomic and coherent turns.

## Tests Run

```bash
.venv/bin/pytest tests/test_phase6.py -q
.venv/bin/python -m compileall src/movia_sales_agent/evaluation
.venv/bin/pytest -q
.venv/bin/movia-eval validate-dataset
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
```

Results:

- Phase 6 tests: `4 passed, 1 warning`.
- Full local pytest: `90 passed, 1 warning`.
- Atomic dataset validation passed: 5 scenarios, 60 turns.
- Coherent dataset validation passed: 7 scenarios, 57 turns.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Deployment Recommendation

```text
NOT READY
```

Do not run adaptive hybrid yet. Do not pilot or deploy.

## Unresolved Issues

- Coherent sales progression remains below gate.
- Known-slot critical repetitions still occur in coherent/memory scenarios.
- The earlier live OpenAI block was not reproduced during the retry, but application-level OpenAI request timeout/retry handling is still recommended before repeated long validation runs.
- RAGAS and DeepEval were skipped to control cost and because deterministic Phase 6 gates already failed.
- Coherent OpenAI replay produced two hard failures in `MOVIA-COH-004`: Instagram presented as currently available, and Captura overclaimed as performing unsupported external actions.

## Exact Next Task

Fix coherent progression and known-slot repetition issues before rerunning Phase 6 gates.
