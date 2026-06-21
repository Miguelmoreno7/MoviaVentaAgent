# RAG Routing Policy V3

Date: 2026-06-05

## Principle

Structured facts override RAG. RAG is used only when the user asks for explanatory context that is better answered from approved narrative documents.

## Structured Or JSON Only

These routes must not trigger RAG by themselves:

- price questions
- payment policy questions
- refund policy questions
- product availability questions
- channel availability questions
- integration questions
- platform registration steps
- onboarding/document steps
- exact Captura versus Híbrido scope facts

Authoritative sources:

- `postgres.products`
- `postgres.policies`
- `postgres.official_links`
- JSON config/playbooks

## RAG Routes

| Route | Trigger | Metadata filter | Notes |
|---|---|---|---|
| Industry use case | `industry_use_case` or `business_fit` topic | `{"topic":"use_cases","industry":"..."}` | Use for dental, restaurant, real estate use-case explanation. |
| Comparison | `competitor_comparison` topic or `compare_alternative` action | `{"topic":"comparisons","comparison":"..."}` | Use for ManyChat, basic chatbot, human receptionist, custom development comparisons. |
| Open explanatory overview | demo-oriented value explanation | `{"topic":"overview"}` | Use only for broad explanatory turns without exact structured facts. |
| Proof during objection | active proof step with safe industry/comparison target | industry or comparison filter | Skip RAG if no safe filter exists. |

## Metadata Contract

Approved RAG chunks should expose:

- `topic`
- `industry`
- `channel`
- `product`
- `comparison_target`
- `funnel_stage`
- `approved`
- `version`

Current compatibility keys remain supported:

- `comparison`
- `product_explanation`
- `faq`
- `source_type`

## Relevance Policy

Retrieval keeps at most three chunks.

Chunks with numeric `similarity < 0.58` are rejected.

Filtered retrieval does not fall back to unfiltered retrieval. If no filtered chunk is strong enough, the agent receives no RAG context for that turn.

## Evaluation Metrics

Deterministic RAG metrics are emitted under `source_selection`:

- `rag.retrieval_necessity`
- `rag.routing_accuracy`
- `rag.context_relevance`
- `rag.answer_groundedness`

Skipped and not-applicable metrics do not affect denominators.
