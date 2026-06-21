# Phase 6 OpenAI Replay Report

Date: 2026-06-06

## Summary

The OpenAI Responses API did not block during the retry.

I first ran a direct `responses.create` smoke with a watchdog:

- Text response call: completed in `2.48s`.
- JSON-schema response call: completed in `2.23s`.
- Model: `gpt-4.1-mini`.

Then I ran a real two-turn MovIA evaluation smoke with OpenAI enabled:

- Run ID: `movia-eval-20260606T193215Z-de601a`
- Total tokens: `2,389`
- OpenAI calls were recorded in the artifact.

After those checks passed, I ran the full Phase 6 atomic and coherent suites with OpenAI enabled for the agent. RAGAS and DeepEval remained skipped, so token totals below are agent-call tokens only.

## Atomic DB OpenAI Run

Command:

```bash
.venv/bin/movia-eval run --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-atomic-db-openai
```

Result:

- Run ID: `movia-eval-20260606T193317Z-bd6909`
- Overall score: `0.9133`
- Passed: `false`
- Hard failures: `0`

Token usage:

| Operation | Calls | Input Tokens | Output Tokens | Total Tokens |
|---|---:|---:|---:|---:|
| analysis | 60 | 92,123 | 13,510 | 105,633 |
| embedding | 9 | 189 | 0 | 189 |
| response | 60 | 84,161 | 6,264 | 90,425 |
| total | 129 | 176,473 | 19,774 | 196,247 |

Category scores:

| Category | Score |
|---|---:|
| sales_progression | 0.3125 |
| objection_handling | 0.6917 |
| source_selection | 0.8863 |
| commercial_accuracy | 1.0000 |
| policy_compliance | 1.0000 |
| memory_consistency | 0.6474 |
| response_quality | 0.9082 |
| scope_control | 1.0000 |

Artifacts:

- `artifacts/evaluations/phase6-atomic-db-openai/movia-eval-20260606T193317Z-bd6909/run.json`
- `artifacts/evaluations/phase6-atomic-db-openai/movia-eval-20260606T193317Z-bd6909/summary.md`

## Coherent DB OpenAI Run

Command:

```bash
.venv/bin/movia-eval run --dataset movia_validation_package/movia_coherent_scripted_conversations.json --scenario all --skip-ragas --skip-deepeval --no-fail-exit --output-root artifacts/evaluations/phase6-coherent-db-openai
```

Result:

- Run ID: `movia-eval-20260606T194627Z-44595c`
- Overall score: `0.8267`
- Passed: `false`
- Hard failures: `2`

Token usage:

| Operation | Calls | Input Tokens | Output Tokens | Total Tokens |
|---|---:|---:|---:|---:|
| analysis | 57 | 84,118 | 13,181 | 97,299 |
| embedding | 11 | 155 | 0 | 155 |
| response | 57 | 70,681 | 5,731 | 76,412 |
| total | 125 | 154,954 | 18,912 | 173,866 |

Category scores:

| Category | Score |
|---|---:|
| sales_progression | 0.3377 |
| objection_handling | 0.8246 |
| source_selection | 0.8852 |
| commercial_accuracy | 0.9821 |
| policy_compliance | 1.0000 |
| scope_control | 0.9800 |
| memory_consistency | 0.6096 |
| response_quality | 0.9550 |

Hard failures:

| Conversation | Turn | User Input | Failure |
|---|---:|---|---|
| `MOVIA-COH-004` | 2 | `Entonces hoy no me sirve si solo uso Instagram.` | `future_channel_sold_as_available`: response presents Instagram as currently available. |
| `MOVIA-COH-004` | 5 | `Necesito que cotice y registre pedidos en mi sistema.` | `captura_scope_overpromise`: response claims MovIA Captura performs unsupported external actions. |

Artifacts:

- `artifacts/evaluations/phase6-coherent-db-openai/movia-eval-20260606T194627Z-44595c/run.json`
- `artifacts/evaluations/phase6-coherent-db-openai/movia-eval-20260606T194627Z-44595c/summary.md`

## Combined Token Usage

| Suite | Input Tokens | Output Tokens | Total Tokens |
|---|---:|---:|---:|
| atomic | 176,473 | 19,774 | 196,247 |
| coherent | 154,954 | 18,912 | 173,866 |
| total | 331,427 | 38,686 | 370,113 |

## Conclusion

The earlier block was not reproduced. The direct OpenAI smoke, two-turn MovIA smoke, full atomic replay, and full coherent replay all completed with OpenAI enabled.

No fallback implementation was added in this pass.

The deployment recommendation remains:

```text
NOT READY
```

Reasons:

- Coherent OpenAI replay produced 2 hard failures.
- Sales progression remains below gate.
- Memory consistency remains below gate.
- The agent overclaimed Instagram availability and Captura external-action scope in `MOVIA-COH-004`.

