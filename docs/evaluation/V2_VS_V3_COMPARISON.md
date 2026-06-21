# V2 vs V3 Comparison

Date: 2026-06-06

## Methodology Warning

Do not compare V2 atomic progression directly with V3 coherent progression as if they measured the same thing.

V2 final replay used the original 60-turn difficult-lead scripted replay as a broad score. V3 separates:

- atomic capability replay;
- coherent scripted conversation progression;
- memory metrics;
- RAG routing/relevance metrics;
- response quality;
- deployment gates.

## Compared Runs

| Label | Run ID | Mode | Notes |
|---|---|---|---|
| V2 final replay | `movia-eval-20260605T060417Z-bef7a2` | live OpenAI, DB disabled | No hard failures; old result schema. |
| V3 atomic DB deterministic | `movia-eval-20260606T064839Z-e61463` | DB enabled, OpenAI disabled | Production DB migrated and persisted evaluation rows. |
| V3 coherent DB deterministic | `movia-eval-20260606T065555Z-7b83ad` | DB enabled, OpenAI disabled | Coherent progression gate run. |

## Score Comparison

| Category | V2 Final Atomic | V3 Atomic DB | V3 Coherent DB |
|---|---:|---:|---:|
| Overall | 0.8505 | 0.9626 | 0.8454 |
| Hard failures | 0 | 0 | 0 |
| Commercial accuracy | 1.000 | 1.000 | 1.000 |
| Policy compliance | 1.000 | 1.000 | 1.000 |
| Scope control | 1.000 | 1.000 | 1.000 |
| Memory consistency | 1.000 | 0.905 | 0.872 |
| Source selection | 0.8858 | 0.9754 | 0.8297 |
| Sales progression | 0.4125 | 0.8583 diagnostic | 0.2895 authoritative |
| Objection handling | 0.5000 | 0.9667 diagnostic | 0.8158 authoritative |
| Response quality | n/a | 0.8866 | 0.8894 |

## Token Comparison

| Run | Agent Tokens |
|---|---:|
| V2 final replay | 162,770 |
| V3 atomic DB deterministic | 0 |
| V3 coherent DB deterministic | 0 |

The V3 Phase 6 deterministic DB runs used `MOVIA_DISABLE_OPENAI=true`, so token totals are not comparable with V2 live OpenAI runs.

## Improvements

- Production DB schema now supports stage persistence, active objection state and conversation mode.
- Atomic capability gates pass with no hard failures.
- Exact commercial facts remain stable: pricing, policies, product availability and scope all passed.
- RAG routing/relevance is now measured separately from generic source matching.
- Response-quality scoring exists and surfaces visible defects.
- Historical-memory metrics have passing evidence in both atomic and coherent runs.

## Regressions Or Open Issues

- Coherent sales progression is below gate: `0.2895` vs required `0.700`.
- Coherent known-slot critical repetitions failed: 4 `asked_known_information` response-quality defects.
- Coherent trace alignment remains weak across macro action, micro action, stage and CTA expectations.
- The live OpenAI full atomic DB run was interrupted because an `OpenAI responses.create()` call blocked during analysis. A one-turn live DB smoke succeeded before that interruption.

## Recommendation

```text
NOT READY
```

V3 is materially stronger as an evaluation architecture and DB-persistence implementation, but the coherent conversation gates failed. The next work should fix coherent sales progression and known-slot repetition before adaptive hybrid or pilot deployment.
