# Phase V3.5 Report: Response Quality Evaluation

Date: 2026-06-05

## Summary

Phase V3.5 is complete. The evaluator now measures visible response quality independently from trace correctness, RAG routing, memory checks and hard commercial-policy rules.

No runtime agent cost was added. The response-quality judge runs only inside evaluation. No production migration was created or applied. No full scripted replay was run.

## Files Changed

- `docs/evaluation/RESPONSE_QUALITY_RUBRIC.md`
- `docs/evaluation/RESPONSE_QUALITY_CALIBRATION.md`
- `docs/evaluation/RESPONSE_QUALITY_PHASE5_SAMPLE_REPORT.md`
- `docs/implementation/PHASE_V3_5_REPORT.md`
- `movia_validation_package/response_quality_calibration.json`
- `src/movia_sales_agent/evaluation/response_quality.py`
- `src/movia_sales_agent/evaluation/runner.py`
- `src/movia_sales_agent/evaluation/cli.py`
- `src/movia_sales_agent/evaluation/reporting.py`
- `src/movia_sales_agent/evaluation/scoring.py`
- `tests/test_response_quality_v3.py`
- `tests/test_evaluation.py`
- `PLAN_V3.md`

## Runtime Impact

None. The production LangGraph runtime does not call the response-quality judge.

## Evaluation Changes

Added response-quality dimensions:

- `directness`
- `relevance`
- `factuality`
- `personalization`
- `persuasiveness`
- `naturalness`
- `non_repetition`
- `next_step_quality`
- `conciseness`
- `tone`

Added critical response defects:

- `did_not_answer_question`
- `asked_known_information`
- `unsupported_claim`
- `overpromised_scope`
- `premature_close`
- `irrelevant_context`
- `repetitive_question`
- `unnatural_or_defensive_tone`
- `poor_next_step`

Added metrics:

- `response_quality.overall`
- `response_quality.<dimension>`
- `response_quality.critical_defects`

Added CLI switches:

```bash
movia-eval run --skip-response-quality
movia-eval run --llm-response-quality
```

Default behavior is deterministic response-quality evaluation. Live LLM judging is opt-in.
The opt-in live judge uses an explicit JSON schema that enumerates all rubric dimensions and allowed critical defects.

## Sampling Policy

- Coherent scripted conversations: all turns.
- Memory scenarios: all turns.
- RAG scenarios: all turns when present.
- Atomic scripted replay: turns `1`, `6`, and `12` per scenario.
- Adaptive hybrid: all turns in Phase 6 if deterministic gates pass.

## Calibration

Created `movia_validation_package/response_quality_calibration.json` with ten manually labeled examples:

- excellent;
- acceptable;
- weak;
- factually correct but commercially weak;
- persuasive but overly long;
- repetitive;
- wrong next question;
- unsupported claim;
- overpromised scope;
- unnatural or defensive tone.

Known-slot repetition is surfaced as `asked_known_information`.

## Tests Run

```bash
.venv/bin/pytest tests/test_response_quality_v3.py -q
.venv/bin/pytest tests/test_evaluation.py -q
.venv/bin/python -m compileall src/movia_sales_agent
.venv/bin/pytest tests/test_response_quality_v3.py tests/test_evaluation.py tests/test_memory_v3.py tests/test_rag_v3.py tests/test_response_context.py -q
.venv/bin/pytest -q
.venv/bin/movia-eval validate-dataset
.venv/bin/movia-eval validate-dataset --dataset movia_validation_package/movia_coherent_scripted_conversations.json
.venv/bin/movia-eval run --scenario MOVIA-VAL-001 --max-turns 1 --offline --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase5-smoke
```

Results:

- Response-quality tests: `6 passed, 1 warning`.
- Evaluation tests: `14 passed, 1 warning`.
- Compileall: passed.
- Targeted Phase 5 regression: `36 passed, 1 warning`.
- Full local pytest: `86 passed, 1 warning`.
- Atomic dataset validation passed: 5 scenarios, 60 turns.
- Coherent dataset validation passed: 7 scenarios, 57 turns.
- Offline one-turn CLI smoke emitted response-quality metrics and produced no hard failures.

Warnings:

- Existing urllib3 LibreSSL warning.
- Existing LangGraph pending deprecation warning.

## Acceptance

- Quality is evaluated independently from traces: completed.
- Rubric includes next-question quality: completed.
- Known-slot repetition is visible as a defect: completed.
- Judge outputs are structured and reproducible: completed.
- Calibration against human examples is documented: completed.
- No runtime cost is added: completed.

## Unresolved Issues

- Live LLM judge calibration was not run because Phase 5 keeps evaluation cost opt-in.
- Deterministic quality scoring is conservative and should be compared with live judge output during Phase 6 if budget is approved.
- The one-turn CLI smoke is not a full replay and is not deployment evidence.

## Exact Next Task

Begin Phase V3.6 only: integrated validation and hybrid predeploy preparation, using `PLAN_V3.md` as the operational tracker.
