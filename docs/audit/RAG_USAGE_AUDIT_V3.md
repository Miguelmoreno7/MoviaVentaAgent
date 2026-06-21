# RAG Usage Audit V3

Date: 2026-06-05

## Scope

This audit covers Phase V3.4 runtime RAG behavior. It focuses on when the agent should retrieve vector context, which filters it should use, and whether weak context is excluded before response generation.

No production database migration was applied. No full scripted replay was run.

## Current RAG Surfaces

Runtime RAG is controlled by:

- `KnowledgePlanner.plan(...)`
- `build_rag_route(...)`
- `RagService.retrieve_with_usage(...)`
- `_compact_rag_context(...)`
- deterministic evaluation metrics in `evaluation/scoring.py`

Structured commercial facts remain outside RAG:

- prices
- payment terms
- refund policy
- official links
- channel availability
- product availability
- platform/onboarding steps

## Routing Audit

| User message | Primary intent | Routing reason | Query | Metadata filter | Result |
|---|---|---|---|---|---|
| `¿Cuánto cuesta?` | `pricing_question` | `structured_or_json_only` | none | `{}` | No RAG. Uses structured products. |
| `¿Cuál es el plan más barato y por qué me conviene para una clínica dental?` | `cheapest_plan_question` | `industry_use_case` | user message | `{"topic":"use_cases","industry":"dental"}` | Retrieves `rag_docs/use_cases/dental.md`. |
| `¿Esto es como ManyChat?` | `comparison_question` | `comparison_target` | user message | `{"topic":"comparisons","comparison":"manychat"}` | Retrieves `rag_docs/comparisons/manychat.md`. |

## Issues Found

Before Phase V3.4, the retrieval service retried an unfiltered vector search when a filtered search returned no rows. That could inject unrelated chunks, such as future channel documentation, into a turn that requested a specific industry or comparison context.

Before Phase V3.4, the planner emitted only `rag_queries`; it did not expose the deterministic route reason or metadata filter in the knowledge plan. This made source-label matching possible, but not route-quality scoring.

Before Phase V3.4, low-similarity chunks could survive retrieval if the backend returned them. This made "some context" possible even when "no context" was safer.

## Phase V3.4 Corrections

- Added deterministic route decisions in `src/movia_sales_agent/agent/rag_policy.py`.
- Added `rag_metadata_filter` and `rag_routing_reason` to `KnowledgePlan`.
- Removed unfiltered fallback after filtered retrieval returns no rows.
- Added a minimum similarity policy: `MIN_RAG_SIMILARITY = 0.58`.
- Limited retained RAG context to at most three chunks.
- Added local fallback metadata filtering and normalized keyword scoring.
- Added canonical ingestion metadata aliases:
  - `comparison_target`
  - `product`
- Preserved existing metadata keys:
  - `comparison`
  - `product_explanation`

## Remaining Risks

- Existing remote RAG rows may not include new alias metadata until ingestion is rerun.
- The current deterministic groundedness metric uses visible metadata terms and is intentionally conservative.
- No RAGAS judge was added in this phase; judge-based RAG quality remains conditional/evaluation-only.
