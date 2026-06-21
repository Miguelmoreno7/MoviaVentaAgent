# Analyzer Model Benchmark

- **Run artifact:** `/Users/miguelmoreno/Documents/MoviaVentaAgente/artifacts/analyzer-model-benchmark/analyzer-model-benchmark-20260615T231210Z-373c13`
- **Dataset:** `movia_validation_package/analyzer_model_benchmark_v1.json`
- **Analyzer contract:** `3.1`
- **Normalized-turn contract:** `3.1`
- **Scope:** analyzer-only; no response generator, embeddings, RAG, RAGAS, DeepEval, judge, production DB writes, Atomic replay or Coherent replay.
- **Pricing source:** OpenAI API pricing page checked on 2026-06-15.

| Metric | gpt-4.1-mini | gpt-5-mini | Delta |
| --- | ---: | ---: | ---: |
| Weighted critical accuracy | 0.9968 | 0.9886 | -0.0082 |
| False requested actions | 0 | 0 | 0.0000 |
| Missed external actions | 0 | 2 | 2.0000 |
| Requirement observation accuracy | 0.5000 | 0.5000 | 0.0000 |
| Objection accuracy | 0.8333 | 0.8333 | 0.0000 |
| Prior-reference precision | 1.0000 | 1.0000 | 0.0000 |
| Intent/topic accuracy | 1.0000 | 0.9722 | -0.0278 |
| Raw contradictions | 0 | 0 | 0.0000 |
| Normalized contradictions | 0.1786 | 0 | -0.1786 |
| Stability | 0.8929 | 0.8214 | -0.0715 |
| Tokens per call | 2668.9820 | 3046.1250 | 377.1430 |
| Cost per call | 0.0014 | 0.0019 | 0.0005 |
| Average latency | 4662.9000 | 8608.9100 | 3946.0100 |

## Reliability

- gpt-4.1-mini schema validity: `0.8929`; provider errors: `0`; fallback count: `0`.
- gpt-5-mini schema validity: `0.6786`; provider errors: `0`; fallback count: `0`.

## Critical Errors

```json
{
  "gpt-4.1-mini": {
    "false_historical_reference": 1,
    "false_explicit_start": 1,
    "normalized:false_explicit_start": 1
  },
  "gpt-5-mini": {
    "missed_explicit_external_action": 2,
    "false_explicit_start": 1,
    "missed_explicit_start": 2,
    "normalized:missed_explicit_external_action": 2,
    "normalized:false_explicit_start": 1,
    "normalized:missed_explicit_start": 2
  }
}
```

## Stability

```json
{
  "gpt-4.1-mini": {
    "exact_output_agreement": 0.0,
    "critical_field_agreement": 0.8929,
    "enum_disagreement_count": 35,
    "evidence_span_disagreement_count": 24
  },
  "gpt-5-mini": {
    "exact_output_agreement": 0.0,
    "critical_field_agreement": 0.8214,
    "enum_disagreement_count": 48,
    "evidence_span_disagreement_count": 25
  }
}
```

## Contract Limitations

- Requirement replacement/removal is not directly expressible by Analyzer Contract V3.1. The benchmark scores only the current-turn observation and reports downstream replacement as out of scope.
- Active objection resolution can be partly representationally limited when the user softens an objection without stating a new objection candidate.

## Recommendation

KEEP GPT-4.1-MINI

Sources: [OpenAI API pricing](https://openai.com/api/pricing/).
