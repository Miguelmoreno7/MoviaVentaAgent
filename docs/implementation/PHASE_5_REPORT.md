# Phase 5 Report: Evaluator Alignment

Date: 2026-06-04  
Master reference: `PLANV2.md`  
Operational plan: `PLAN.md`

## Summary

Phase 5 aligns the validation harness and gold scenario expectations to the MovIA V2 commercial contract. The evaluator now fails early when the dataset contract version, expected enum values, expected fields, or expected source labels cannot be supported by the current runtime.

The 60 scripted user turns and difficult lead personas were preserved. Only expected trace/source metadata and V2 dataset metadata were aligned. No full 60-turn evaluation replay, production migration, deployment, or production data change was performed.

## Completed Work

- Added `commercial_contract_version` to validation dataset models and validation summaries.
- Made `validate_dataset(...)` enforce:
  - `commercial_contract_version == "2.0"`;
  - V2 enum values for stages, actions, objections, objection-flow steps, and CTA types;
  - supported expected fields only;
  - supported observable source labels only;
  - boolean types for `rag_used`, `structured_used`, and `json_used`.
- Added exact dynamic source capabilities for V2 objection playbooks, for example `json.objection_playbook:price_objection`.
- Aligned `movia_validation_package/movia_difficult_lead_validation_scenarios.json` expected values to deterministic V2 runtime traces:
  - `current_stage`
  - `macro_action`
  - `micro_action`
  - `objection_type`
  - `objection_flow_step`
  - `expected_sources`
  - `rag_used`
  - `structured_used`
  - `json_used`
  - `final_cta_type`
- Updated dataset debug metadata from V1 `intent` to V2 `primary_intent` and `secondary_intents`.
- Expanded Markdown reporting with:
  - contract version summary;
  - pass-policy thresholds;
  - failure inventory buckets;
  - root-cause grouping.
- Preserved deterministic hard-failure scoring rules.

## Files Changed

- `src/movia_sales_agent/evaluation/models.py`
- `src/movia_sales_agent/evaluation/dataset.py`
- `src/movia_sales_agent/evaluation/capabilities.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `movia_validation_package/movia_difficult_lead_validation_scenarios.json`
- `tests/test_evaluation.py`
- `PLAN.md`
- `docs/implementation/PHASE_5_REPORT.md`

## Migration

None.

## Tests Run

```bash
.venv/bin/pytest tests/test_evaluation.py tests/test_commercial_contract.py tests/test_agent_policy.py
```

Result: 34 passed.

```bash
.venv/bin/movia-eval validate-dataset
```

Result: valid dataset, 5 scenarios, 60 turns, `commercial_contract_version="2.0"`, no unsupported expected fields, no unsupported expected sources.

```bash
.venv/bin/pytest tests
```

Result: 60 passed.

Warnings observed:

- `urllib3` LibreSSL/OpenSSL compatibility warning.
- LangGraph pending deprecation warning for default serializer settings.

## Guardrails Verified

- Full 60-turn evaluation replay was not run.
- The gold dataset user messages, personas, risks, and ideal responses were not changed.
- No production migrations were applied.
- No deployment or production data change was performed.
- Phase 6 was not started.

## Deferred Issues

- The aligned gold dataset has not yet been validated by a full live replay.
- DeepEval and RAGAS live judge behavior remains deferred until final replay.
- Token/context compaction remains Phase 6.
- The Phase 3 and Phase 4 migrations still exist locally but have not been applied to production.

## Exact Next Task

Begin Phase 6 by measuring current token/context usage on targeted smoke turns, then reduce response context/package size without changing commercial behavior or hard-failure rules.
