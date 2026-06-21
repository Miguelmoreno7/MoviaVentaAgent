# Analyzer V3 Phase 4 Report

Status: TARGETED CONTRACT VALIDATION PASSED

Date: 2026-06-07

## Scope

Phase 4 implemented targeted live validation for the highest-risk Analyzer V3 cases without modifying Atomic/Coherent gold datasets and without running the full replay.

Implemented:

- Added reference-only targeted manifest: `movia_validation_package/analyzer_v3_targeted_manifest.json`.
- Added analyzer-only and live targeted validation harness.
- Added `movia-eval analyzer-v3-targeted`.
- Added parser-shadow comparison and previous-versus-new comparison reports.
- Hardened OpenAI analyzer schema handling so recoverable evidence-span issues are sanitized before runtime validation instead of causing fallback.
- Tightened prior-reference normalization, unsupported-channel planning, Captura external-action detector negation handling, and related regression tests.

## Final Artifacts

- Final passed artifact: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`
- Source live run: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260606T235650Z-1df8be/`
- Summary: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/summary.md`
- Gate summary: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/gate_summary.json`
- Parser-shadow report: `docs/evaluation/PARSER_SHADOW_COMPARISON.md`
- Previous-vs-new report: `docs/evaluation/ANALYZER_V3_TARGETED_COMPARISON.md`

The final artifact is a rescore of the completed all-OpenAI source run after fixing a safe-negation detector false positive. No model calls were rerun for the rescore.

## Gate Results

| Gate | Count |
|---|---:|
| hard_failures | 0 |
| impossible_states | 0 |
| false_prior_references | 0 |
| true_prior_reference_misses | 0 |
| hallucinated_turn_numbers | 0 |
| external_action_misses | 0 |
| premature_captura_recommendations | 0 |
| captura_external_action_overpromises | 0 |
| unsupported_channel_claims | 0 |
| explicit_start_false_negatives | 0 |
| need_to_think_false_positives | 0 |

## Provider And Token Check

- Analyzer-only records: 44 turns, 44 OpenAI analyzer calls, 0 call errors, 84,557 total tokens.
- Live records: 44 turns, 44 OpenAI analyzer calls, 44 OpenAI response calls, 12 OpenAI embedding calls, 0 call errors, 167,602 total tokens.
- Live average total tokens per turn: 3,809.14.
- Live average latency: 13,247.68 ms.

## Previous Vs New

- Hard failures: 18 -> 0.
- False prior references: 6 -> 0.
- Hallucinated turn numbers: 8 -> 0.
- External-action misses: 1 -> 0.
- Unsupported-channel claims: 1 -> 0.
- Captura external-action overpromises: 1 -> 0.

## Tests Run

- `.venv/bin/pytest tests/test_analyzer_targeted_v3.py tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py tests/test_agent_policy.py -q`
  - Result: 66 passed, 1 warning.
- `.venv/bin/python -m py_compile src/movia_sales_agent/evaluation/analyzer_v3_targeted.py src/movia_sales_agent/analyzer/contract_v3.py`
  - Result: passed.
- `.venv/bin/pytest -q`
  - Result: 138 passed, 1 warning.

## Notes And Risks

- A duplicate live rerun after the detector fix hung after creating an empty artifact directory and was terminated. The completed source run already had all analyzer and response calls from OpenAI with zero call errors.
- Analyzer and full-agent token usage increased versus the previous V3 baseline because the sanitizer prevented fallback and captured complete OpenAI usage.
- Parser-shadow telemetry still shows high channel conflicts; this is observational telemetry only and remains non-authoritative.
- `TurnAnalysis` compatibility remains for existing runtime consumers.

## Exact Next Task

Run the full Atomic and Coherent replay with the current Analyzer V3 implementation. Do not modify gold datasets, deploy, or start an adaptive hybrid flow before reviewing the full replay results.
