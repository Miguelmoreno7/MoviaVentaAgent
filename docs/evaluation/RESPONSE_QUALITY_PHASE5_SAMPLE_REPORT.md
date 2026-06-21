# Response Quality Phase 5 Sample Report

Date: 2026-06-05

## Scope

Phase 5 implemented response-quality evaluation but did not run the full scripted replay. Full integrated validation remains Phase 6.

## Implemented Evaluation Paths

- Deterministic response-quality judge for local/unit evaluation.
- Optional live LLM judge through `movia-eval run --llm-response-quality`.
- CLI skip switch through `movia-eval run --skip-response-quality`.
- Atomic sampling policy: turns `1`, `6`, and `12`.
- Coherent scripted policy: all turns.

## Metrics

Response-quality metrics are emitted under the `response_quality` category:

- `response_quality.overall`
- `response_quality.directness`
- `response_quality.relevance`
- `response_quality.factuality`
- `response_quality.personalization`
- `response_quality.persuasiveness`
- `response_quality.naturalness`
- `response_quality.non_repetition`
- `response_quality.next_step_quality`
- `response_quality.conciseness`
- `response_quality.tone`
- `response_quality.critical_defects`

## Critical Defect Visibility

Known-slot repetition appears as:

```text
response_quality.critical_defects -> asked_known_information
```

This is intentionally separate from trace mismatches and hard commercial failures.

## Phase Boundary

No deployment, production migration or full replay was performed in Phase 5.
