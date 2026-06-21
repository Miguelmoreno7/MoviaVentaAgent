# Phase Requirement Semantics V3.4 Report

Date: `2026-06-11`

Status: Phase 4 complete. Both required full live replays were executed exactly once.

## Freeze Metadata

- Code revision: no Git `HEAD` exists in this workspace; recorded as uncommitted workspace / no HEAD.
- Analyzer contract: `3.1`
- Normalized-turn contract: `3.1`
- Commercial contract: `2.0`
- Evaluation contract: `3.0`
- OpenAI enabled: yes
- Database mode: enabled
- Analyzer model: `gpt-4.1-mini`
- Response model: `gpt-4.1-mini`
- RAGAS: skipped by configuration
- DeepEval: skipped by configuration
- Retry count: `0` recorded
- Resume count: `0` recorded

No runtime code, evaluator code, prompts, gold expectations, or migrations were changed after the full replay began.

## Runs

### Atomic

- Run ID: `movia-eval-20260611T055355Z-a0d168`
- Artifact: `artifacts/evaluations/requirement-v3-phase4-atomic-live/movia-eval-20260611T055355Z-a0d168/run.json`
- Summary: `artifacts/evaluations/requirement-v3-phase4-atomic-live/movia-eval-20260611T055355Z-a0d168/summary.md`
- Suite: `atomic_scripted`
- Scenarios / turns: `5 / 60`
- Passed: `false`
- Overall score: `0.9548`
- Hard failures: `1`
- Duration: `943.98s`
- Fallback count: `0`
- Providers: analysis `openai`, response `openai`, embeddings `openai` or `none`
- Tokens: `282,865` total
- Avg tokens / turn: `4,714.417`
- Avg latency / turn: `15,501.76ms`

Hard failure:

- `cross_scenario_memory_leak`, `MOVIA-VAL-003` turn `2`: response referenced another scenario's business context: `garantias`.

### Coherent

- Run ID: `movia-eval-20260611T060949Z-4fcc86`
- Artifact: `artifacts/evaluations/requirement-v3-phase4-coherent-live/movia-eval-20260611T060949Z-4fcc86/run.json`
- Summary: `artifacts/evaluations/requirement-v3-phase4-coherent-live/movia-eval-20260611T060949Z-4fcc86/summary.md`
- Suite: `coherent_scripted`
- Scenarios / turns: `7 / 57`
- Passed: `false`
- Overall score: `0.8851`
- Hard failures: `1`
- Duration: `910.18s`
- Fallback count: `0`
- Providers: analysis `openai`, response `openai`, embeddings `openai` or `none`
- Tokens: `263,791` total
- Avg tokens / turn: `4,627.912`
- Avg latency / turn: `15,630.23ms`

Hard failure:

- `incorrect_deposit_percentage`, `MOVIA-COH-003` turn `6`: response states an unsupported deposit percentage: `100%`.

## Baseline Comparison

Comparison artifact:

```text
artifacts/evaluations/requirement-v3-phase4-comparison.json
```

Atomic baseline:

- Baseline: `artifacts/evaluations/phase6-atomic-db-openai/movia-eval-20260606T193317Z-bd6909/run.json`
- Overall: `0.9133 -> 0.9548` (`+0.0415`)
- Hard failures: `0 -> 1` (`+1`)
- Notable deltas:
  - memory consistency: `+0.2526`
  - objection handling: `+0.1000`
  - sales progression: `+0.1508`
  - response quality: `+0.0341`
  - source selection: `-0.0528`
  - scope control: `-0.0034`

Coherent baseline:

- Baseline: `artifacts/evaluations/phase6-coherent-db-openai/movia-eval-20260606T194627Z-44595c/run.json`
- Overall: `0.8267 -> 0.8851` (`+0.0584`)
- Hard failures: `2 -> 1` (`-1`)
- Notable deltas:
  - memory consistency: `+0.3415`
  - sales progression: `+0.2342`
  - scope control: `+0.0165`
  - commercial accuracy: `+0.0059`
  - policy compliance: `-0.0588`
  - source selection: `-0.0863`

Analyzer V3 targeted references:

- Source run: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260606T235650Z-1df8be/`
- Passed rescore: `artifacts/evaluations/analyzer-v3-targeted/analyzer-v3-targeted-20260607T003000Z-rescore/`
- Passed rescore status: targeted contract validation passed with `0` hard failures.

## Contract Safety

Atomic:

- hard failures: `1`
- impossible states: no explicit impossible-state hard failure emitted
- false prior references: no explicit false-prior hard failure emitted
- hallucinated turn numbers: no explicit hard failure emitted
- contradictions: no explicit hard failure emitted
- fallbacks: `0`

Coherent:

- hard failures: `1`
- impossible states: no explicit impossible-state hard failure emitted
- false prior references: no explicit false-prior hard failure emitted
- hallucinated turn numbers: no explicit hard failure emitted
- contradictions: no explicit hard failure emitted
- fallbacks: `0`

## Requirement Semantics

Atomic semantic failures:

- `semantic.requirement_profile_reset`: `12`
- `semantic.current_question_future_capability_leakage`: `1`
- problem-capability leakage: `0`
- external-action misses: `0`
- sales-capability misroutes: `0`
- premature recommendations: `0`
- unsupported standard-scope claims: `0`
- wrong-product closes: `0`

Coherent semantic failures:

- `semantic.requirement_profile_reset`: `3`
- `semantic.wrong_product_direct_close`: `2`
- `semantic.problem_capability_leakage`: `1`
- current-question capability leakage: `0`
- external-action misses: `0`
- sales-capability misroutes: `0`
- premature recommendations: `0`
- unsupported standard-scope claims: `0`

## Commercial Performance

Atomic:

- sales progression score: `0.4633`
- objection handling score: `0.7917`
- direct closes: `2`
- non-closes: `58`
- recommend-solution turns: `7`
- objection-detected turns: `10`
- macro distribution: answer/advance `24`, discover `13`, unknown-safe `8`, recommend `7`, direct close `2`
- CTA distribution: soft question `22`, discovery question `15`, none `12`, soft close `7`, direct close `2`

Coherent:

- sales progression score: `0.5719`
- objection handling score: `0.8158`
- direct closes: `4`
- wrong-product direct-close metric failures: `2`
- non-closes: `53`
- recommend-solution turns: `12`
- objection-detected turns: `1`
- macro distribution: recommend `12`, discover `10`, handoff `9`, answer/advance `6`, handle objection `6`, direct close `4`
- CTA distribution: soft question `11`, discovery question `10`, redirect to Miguel `9`, soft close `8`, objection question `6`, direct close `4`

## Memory

Atomic:

- memory consistency score: `0.9000`
- `memory.known_slot_repetition`: `6`
- hard failure: `cross_scenario_memory_leak` on `MOVIA-VAL-003` turn `2`

Coherent:

- memory consistency score: `0.9511`
- `memory.known_slot_repetition`: `6`
- no memory hard failure emitted

## Sources And RAG

Atomic:

- source selection score: `0.8335`
- embedding calls: `60` total, `27` via OpenAI and `33` provider `none`
- retrieved-source count emitted in turn payloads: `0`
- `rag.context_relevance` failures: `27`
- `source.expected_recall` failures: `24`

Coherent:

- source selection score: `0.7989`
- embedding calls: `57` total, `26` via OpenAI and `31` provider `none`
- retrieved-source count emitted in turn payloads: `0`
- `rag.context_relevance` failures: `26`
- `source.expected_recall` failures: `21`

## Response Quality

Atomic:

- response quality score: `0.9423`
- response-quality failures: overall `1`, relevance `1`, critical defects `1`

Coherent:

- response quality score: `0.9499`
- response-quality failures: overall `3`, critical defects `3`, directness `2`, non-repetition `1`

## Performance

Atomic:

- analyzer tokens / turn: `2,789.55`
- response tokens / turn: `1,917.533`
- embedding tokens / turn: `7.333`
- total tokens / turn: `4,714.417`
- average latency / turn: `15,501.76ms`
- p50 latency / turn: `14,797.08ms`
- max latency / turn: `24,714.85ms`
- DB/retrieval latency: not separately emitted in run artifact

Coherent:

- analyzer tokens / turn: `2,710.351`
- response tokens / turn: `1,911.175`
- embedding tokens / turn: `6.386`
- total tokens / turn: `4,627.912`
- average latency / turn: `15,630.23ms`
- p50 latency / turn: `15,497.99ms`
- max latency / turn: `27,054.17ms`
- DB/retrieval latency: not separately emitted in run artifact

## Interpretation

Both full live suites improved overall score against their pinned baselines, but neither passed because each emitted one hard failure. Per Phase 4 rules, no automatic development loop was started and no rerun was executed.

The most important next review items are:

- Atomic `cross_scenario_memory_leak` detection on a refund/support-policy turn that mentioned `garantías`.
- Coherent unsupported `100%` wording on a deposit-confidence turn.
- Requirement-profile reset metrics in both suites.
- Coherent wrong-product direct-close metric failures.
- Source/RAG degradation versus baseline and zero retrieved sources in emitted turn payloads.

## Exact Next Task

Phase 5 only, if the user approves:

- analyze the preserved Phase 4 artifacts;
- decide which failures are true defects versus evaluator calibration issues;
- design a bounded fix plan without rerunning the full live suites automatically.
