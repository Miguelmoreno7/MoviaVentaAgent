# Response Quality Calibration V3

Date: 2026-06-05

Calibration dataset:

`movia_validation_package/response_quality_calibration.json`

## Coverage

The calibration set contains ten manually labeled examples:

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

## Human Labels

Human labels use `human_overall` from 0.0 to 1.0 and explicit critical defect flags.

The initial deterministic judge is expected to agree on critical defects before it agrees perfectly on nuanced quality gradients. That is intentional: Phase 5 prioritizes catching deployment-relevant response defects without adding runtime cost.

## Known Disagreements To Watch

- Persuasive but overly long responses may score acceptable on value while weak on conciseness.
- Factually correct responses can still be commercially weak when they fail to handle an objection or ask the wrong next question.
- Personalization should not be penalized when no useful lead context is known.
- Atomic scripted turns are sampled because the user's next message does not react to the actual answer.

## Sampling Policy

- Coherent scripted suite: all turns.
- Memory scenarios: all turns because they are part of coherent scripts.
- RAG scenarios: all turns when present.
- Atomic scripted suite: sampled turns `1`, `6`, and `12` per scenario.
- Adaptive hybrid: all turns after deterministic gates pass in Phase 6.

## Phase 5 Status

This calibration documents the rubric and deterministic judge behavior. Live LLM judge calibration remains opt-in through the evaluation runner and should be run only when credentials and budget are intentionally configured.
