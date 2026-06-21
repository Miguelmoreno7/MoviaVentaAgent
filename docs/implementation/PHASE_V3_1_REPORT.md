# Phase V3.1 Report: Evaluation System Redesign

Date: 2026-06-05  
Master reference: `PLAN_V3.md`  
Status: completed  
Scope: Phase 1 only

## Summary

Phase 1 separates MovIA validation into distinct evaluation suites so the existing 60-turn replay remains useful without pretending it is a causal sales conversation.

The atomic difficult-lead dataset is now explicitly marked as non-causal. Sales progression and full objection resolution remain visible as diagnostics there, but they no longer define the primary applicable score for that suite.

No agent runtime behavior, objection policy, memory logic, RAG logic, migrations, production data, adaptive simulation, or full expensive replay were changed or run.

## Completed Work

- Added V3 evaluation contract source:
  - `src/movia_sales_agent/evaluation/contracts_v3.py`
- Added suite metadata to the atomic 60-turn dataset:
  - `evaluation_contract_version = "3.0"`
  - `suite_type = "atomic_scripted"`
  - `causal_continuity = false`
  - `agent_contract_version = "2.0"`
  - `dataset_version = "v3.0-atomic-2026-06-05"`
  - `run_mode = "scripted_replay"`
- Added coherent scripted suite:
  - `movia_validation_package/movia_coherent_scripted_conversations.json`
  - 5 conversations
  - 41 total turns
  - each conversation has 8-15 causally coherent user turns
- Added adaptive hybrid predeploy interface only:
  - `movia_validation_package/movia_adaptive_hybrid_predeploy_interface.json`
  - `enabled = false`
  - `predeploy_only = true`
- Extended evaluation dataset models and validation summaries with V3 metadata.
- Added suite-aware validation:
  - atomic requires exactly 5 scenarios, 60 turns and 12 turns per scenario;
  - coherent requires at least 5 scenarios, 8-15 turns each and `causal_continuity=true`;
  - adaptive hybrid is not loadable as a scripted replay dataset in Phase 1.
- Added suite-aware score grouping and pass-policy filtering:
  - atomic excludes diagnostic progression/objection categories from the primary score;
  - coherent keeps progression and objection lifecycle authoritative.
- Updated Markdown reports to show:
  - evaluation contract;
  - suite type;
  - causal continuity;
  - dataset version;
  - run mode;
  - score groups;
  - diagnostic versus authoritative categories.
- Added V3 strategy document:
  - `docs/evaluation/EVALUATION_STRATEGY_V3.md`
- Added Phase 1 tests for:
  - atomic dataset metadata;
  - coherent dataset structural validation;
  - disabled adaptive hybrid interface;
  - atomic diagnostic progression score behavior;
  - updated report metadata and score groups.

## Files Changed

- `PLAN_V3.md`
- `docs/evaluation/EVALUATION_STRATEGY_V3.md`
- `docs/implementation/PHASE_V3_1_REPORT.md`
- `movia_validation_package/movia_difficult_lead_validation_scenarios.json`
- `movia_validation_package/movia_coherent_scripted_conversations.json`
- `movia_validation_package/movia_adaptive_hybrid_predeploy_interface.json`
- `src/movia_sales_agent/evaluation/contracts_v3.py`
- `src/movia_sales_agent/evaluation/models.py`
- `src/movia_sales_agent/evaluation/dataset.py`
- `src/movia_sales_agent/evaluation/runner.py`
- `src/movia_sales_agent/evaluation/scoring.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `tests/test_evaluation.py`

## Tests Run

```bash
.venv/bin/pytest tests/test_evaluation.py
```

Result:

```text
14 passed, 1 warning
```

```bash
.venv/bin/movia-eval validate-dataset
```

Result:

```text
valid=true
suite_type=atomic_scripted
causal_continuity=false
scenario_count=5
turn_count=60
unsupported_expected_fields=[]
unsupported_expected_sources=[]
```

```bash
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
```

Result:

```text
valid=true
suite_type=coherent_scripted
causal_continuity=true
scenario_count=5
turn_count=41
unsupported_expected_fields=[]
unsupported_expected_sources=[]
```

Warnings observed:

- `urllib3` LibreSSL/OpenSSL compatibility warning from the local Python environment.
- LangGraph pending deprecation warning from installed dependency.

## Guardrails Verified

- Original atomic user messages were preserved.
- Previous V1/V2 replay artifacts were not deleted or modified.
- No adaptive simulation was run.
- No full 60-turn replay was run.
- No production migrations were applied.
- No runtime agent behavior was modified.
- No RAG, memory, objection, prompt, or deployment behavior was changed.

## Repository Conflicts Or Constraints

- The remote DB still lacks local V2 stage/objection migrations from earlier phases; Phase 1 does not apply or require them.
- Existing V2 atomic replay artifacts remain methodologically valid only as atomic capability artifacts, not as coherent progression evidence.
- Response-quality judging remains unimplemented until Phase 5.
- Coherent scripted conversations are structurally valid but have not been replayed yet; replay is intentionally deferred.

## Acceptance Criteria

- Existing 60 messages classified as atomic capability tests: completed.
- Atomic dataset marked `suite_type=atomic_scripted` and `causal_continuity=false`: completed.
- Sales progression and objection resolution are diagnostic for atomic scripts: completed through suite-aware scoring.
- Five coherent scripted conversations exist and validate structurally: completed.
- Metric applicability is explicit: completed in `contracts_v3.py` and strategy docs.
- Reports distinguish capability/progression/memory/retrieval/response-quality groups: completed at the report schema level.
- Adaptive hybrid remains disabled: completed.

## Exact Next Task

Begin Phase 2 only: implement the parallel objection architecture where soft concerns are inline overlays, hard objections persist independently from `sales_stage`, and `objection_handling` stops freezing the primary commercial stage.
