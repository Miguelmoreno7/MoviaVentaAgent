# MovIA Knowledge Source Map

This document maps MovIA knowledge sources to the runtime surfaces that consume them. Use it before changing commercial facts, policies, product scope, RAG explanations, or sales behavior.

The knowledge package is intentionally not a Markdown-to-database importer. Markdown files can be authoring briefs or explanatory RAG material. Runtime truth lives in structured Postgres tables, loaded JSON config, code contracts, or ingested RAG chunks depending on the information type.

## Runtime Flows

| Flow | Source files | Runtime destination | Script or reload |
|---|---|---|---|
| Structured product and policy seed | `docs/movia_knowledge_source/config/products.seed.json`, `docs/movia_knowledge_source/config/policies.seed.json` | `movia_products`, `movia_product_features`, `movia_policies` | `python scripts/seed_database.py` |
| Structured reference seed | Hardcoded rows in `scripts/seed_database.py` with Markdown `source_path` provenance | `movia_channels`, `movia_integrations`, `movia_official_links`, `movia_project_statuses` | `python scripts/seed_database.py` |
| Runtime JSON config | `docs/movia_knowledge_source/config/*.json` | In-memory config bundle loaded by `load_config_bundle()` | Restart app or clear process cache |
| RAG content | `docs/movia_knowledge_source/rag_docs/**/*.md` | `movia_knowledge_documents`, `movia_knowledge_chunks` | `python scripts/ingest_rag.py` |
| Foundational Markdown | `docs/movia_knowledge_source/docs/*.md` | Human/Codex authoring source and provenance | Manually translate changes into the correct runtime source |
| Knowledge gaps | `docs/movia_knowledge_source/KNOWLEDGE_GAPS.md` | Human/Codex guardrail for uncertain or missing information | Do not seed or answer as official truth |

## Authority and Conflict Resolution

When the same fact appears in more than one place, use this order of authority. Lower-authority sources may explain or paraphrase higher-authority facts, but must not override them.

| Topic | Authoritative source | Conflict rule |
|---|---|---|
| Exact product facts | `movia_products` and `movia_product_features`, seeded from `config/products.seed.json` | RAG and foundational Markdown may explain product facts but cannot override structured product data |
| Product prices and availability | `movia_products`, seeded from `config/products.seed.json` | Any conflicting RAG, FAQ, or narrative copy must be updated or ignored |
| Product capabilities | `movia_products` and `movia_product_features`, seeded from `config/products.seed.json` | Use-case RAG must remain consistent with structured capabilities |
| Official links | `movia_official_links`, seeded by `scripts/seed_database.py` | `platform_steps.json` may reference the app link but must not define a conflicting URL |
| Platform steps | `config/platform_steps.json` | RAG may explain the process but cannot change ordered user-facing steps |
| Policies | `movia_policies`, seeded from `config/policies.seed.json` | FAQ RAG may paraphrase policy but cannot override deposit, refund, payment, support, or token/API rules |
| Channel and integration status | `movia_channels` and `movia_integrations`, seeded by `scripts/seed_database.py` | Product explanations and channel RAG must respect structured availability |
| Commercial behavior | Planner/code rules, commercial contracts, and deterministic policy code | Narrative wording in playbooks or Markdown cannot override runtime behavior when they conflict |
| Objection and CTA wording | JSON config such as `objection_playbook.json`, `cta_rules.json`, and `sales_actions.json` | Planner/code decides when behavior applies; JSON guides how the agent should express it |
| Unknown or uncertain information | `KNOWLEDGE_GAPS.md` | Gaps are not official truth and must not be answered as confirmed facts |

If a source conflict is discovered, update the lower-authority source or mark it stale. Do not average, merge, or let RAG resolve exact commercial facts.

## Source Directories

### `docs/movia_knowledge_source/config`

Machine-readable runtime and seed files. The app loads all `*.json` files in this directory into the config bundle. Some files are also used by seed scripts.

| File | Contains | Runtime use | Update workflow |
|---|---|---|---|
| `products.seed.json` | Product catalog, availability, prices, delivery time, included meetings, includes, excludes, recommended-when rules | Seed source for product tables; offline fallback when DB is unavailable | Edit file, run `python scripts/seed_database.py`, run product/response tests |
| `policies.seed.json` | Deposit, final payment, refund, monthly billing, token/API policies | Seed source for policy table; offline fallback when DB is unavailable | Edit file, run `python scripts/seed_database.py`, run policy/response tests |
| `platform_steps.json` | MovIA app link and ordered platform/start/onboarding steps | Loaded as JSON context when `platform_steps` or `official_app_link` is needed | Edit file, restart app, run start/payment/link response tests |
| `objection_playbook.json` | Objection handling methodology and objection-specific response guidance | Loaded as full or single-objection JSON context by Knowledge Planner | Edit file, restart app, run objection-flow tests |
| `post_purchase_handoff.json` | Post-purchase handoff rule and handoff message | Loaded when planner selects Miguel/post-purchase handoff | Edit file, restart app, run post-purchase/handoff tests |
| `sales_actions.json` | Allowed commercial actions and response behavior guidance | Always loaded as base JSON context | Edit file, restart app, run agent policy tests |
| `cta_rules.json` | CTA/discovery/direct-close/soft-close guidance | Always loaded as base JSON context | Edit file, restart app, run CTA and direct-close tests |
| `tone_rules.json` | Spanish WhatsApp tone, style, and avoid-list | Always loaded as base JSON context | Edit file, restart app, run response-quality tests |
| `source_routing_rules.json` | Comparison/source routing rules for alternatives and competitors | Loaded for competitor/comparison topics | Edit file, restart app, run comparison tests |

### `docs/movia_knowledge_source/docs`

Foundational authoring documents. These files explain the original commercial truth used to design tables, configs, prompts, and RAG. The runtime does not parse them automatically.

Do not edit these original package Markdown files for routine knowledge changes. Preserve them as the initial authoring package. New or revised Markdown briefs should be added under `docs/knowledge_change_requests/`, then translated into the correct runtime source using this map.

| File | Contains | Current runtime relationship | When changing it |
|---|---|---|---|
| `00_market_check.md` | Market positioning and price reference context | Human/Codex source only | Translate changes into pricing/positioning copy or RAG only if they become approved MovIA claims |
| `01_products_and_pricing.md` | Product scope, prices, availability, descriptions, includes/excludes, recommended use | Source material for `products.seed.json` and product-related response constraints | Update product seed or product capability RAG if the change is official |
| `02_webapp_process.md` | App link, registration, workspace, demo/project creation, payment/start process, project statuses | Provenance for `movia_official_links` and `movia_project_statuses`; source material for `platform_steps.json` | Update platform steps, official links/reference seed, or RAG FAQ depending on whether the change is exact process or explanatory |
| `03_policies.md` | Deposit, final payment, approval, refund, monthly billing, API/token/support policies | Source material for `policies.seed.json` | Update policy seed when official policy changes |
| `04_channels_and_integrations.md` | Available/upcoming channels, WhatsApp Business requirements, official Meta integration | Provenance for channels/integrations reference seed | Update `scripts/seed_database.py` reference rows if exact channel/integration status changes; update RAG only for explanation |
| `05_use_cases_and_segmentation.md` | Product-fit segmentation, ideal use cases, and when to choose Captura vs Hibrido | Source material for product recommended-when rules and RAG use cases | Update product seed for exact recommendation criteria; update RAG use-case docs for narrative examples |
| `06_sales_actions.md` | Sales action definitions and allowed commercial behavior | Source material for sales action config and planner policy | Update `sales_actions.json` or planner tests/code if behavior changes |
| `07_objection_playbook.md` | Objection signals, response strategy, and recommended wording | Source material for `objection_playbook.json` | Update objection playbook config and objection tests |
| `08_industry_benefits.md` | Industry-specific pains, benefits, and persuasive examples | Source material for RAG use-case documents | Update matching `rag_docs/use_cases/*.md` and run RAG ingestion |
| `09_rag_knowledge_index.md` | Defines what belongs in RAG and what must stay structured | Governance source for knowledge architecture | Update only when the knowledge architecture changes |
| `10_codex_implementation_prompt.md` | Original implementation brief, database/table intent, config list, and restrictions | Historical implementation source | Update only if preserving a new master implementation brief |

### `docs/movia_knowledge_source/rag_docs`

Approved explanatory content for retrieval. These Markdown files are read, chunked, embedded, and stored in Postgres by `scripts/ingest_rag.py`.

| File | Contains | Runtime use | Update workflow |
|---|---|---|---|
| `overview/movia_overview.md` | General explanation of MovIA | RAG context for broad questions | Edit, run `python scripts/ingest_rag.py`, run RAG retrieval tests |
| `use_cases/dental.md` | Dental/clinic use case | RAG context for dental leads | Edit, run RAG ingestion, run dental scenario tests |
| `use_cases/real_estate.md` | Real estate use case | RAG context for real estate leads | Edit, run RAG ingestion, run relevant use-case tests |
| `use_cases/restaurants.md` | Restaurant/food use case | RAG context for restaurant leads | Edit, run RAG ingestion, run relevant use-case tests |
| `use_cases/general_services.md` | General services and trades use case | RAG context for general service leads | Edit, run RAG ingestion, run relevant use-case tests |
| `comparisons/manychat.md` | MovIA vs ManyChat | RAG context for competitor/comparison questions | Edit, run RAG ingestion, run comparison tests |
| `comparisons/basic_chatbot.md` | MovIA vs basic chatbot | RAG context for chatbot comparison questions | Edit, run RAG ingestion, run comparison tests |
| `comparisons/human_receptionist.md` | MovIA vs human receptionist | RAG context for human/team comparison questions | Edit, run RAG ingestion, run comparison tests |
| `faqs/pre_purchase_faq.md` | Open pre-purchase FAQ explanations | RAG context for broad pre-purchase questions | Edit, run RAG ingestion, run FAQ tests |
| `product_explanations/whatsapp_agent.md` | WhatsApp agent explanation | RAG context for WhatsApp-agent questions | Edit, run RAG ingestion, run channel/product tests |
| `product_explanations/facebook_agent.md` | Facebook agent explanation | RAG context; must respect channel availability | Edit, run RAG ingestion, run unavailable-channel tests |
| `product_explanations/instagram_agent.md` | Instagram agent explanation | RAG context; must respect channel availability | Edit, run RAG ingestion, run unavailable-channel tests |
| `product_explanations/multichannel_agent.md` | Multichannel explanation | RAG context; must respect product/channel availability | Edit, run RAG ingestion, run channel scope tests |

### Other Knowledge Files

| File | Contains | Runtime use | Update workflow |
|---|---|---|---|
| `README.md` | Package intent and recommended reading order | Human/Codex onboarding only | Update when package structure changes |
| `KNOWLEDGE_GAPS.md` | Unknown, missing, or uncertain information | Guardrail only; not ingested as official truth | Move an item out only after it becomes official in a structured or RAG source |

### `docs/knowledge_change_requests`

New Markdown briefs for knowledge changes should live here. These files are not read by the runtime. They are input for Codex/human review before updating structured seed data, runtime JSON config, RAG Markdown, or code.

Recommended naming:

```text
docs/knowledge_change_requests/YYYY-MM-topic-name.md
```

Recommended sections:

```md
# Topic

## Change Summary

## Official Truth

## Examples Of Good Answers

## Must Not Say

## Affected Areas
```

## Runtime Consumers

| Consumer | Reads | Notes |
|---|---|---|
| `src/movia_sales_agent/config/knowledge.py` | `config/*.json`, `rag_docs/**/*.md` paths | Does not read `docs/*.md` |
| `scripts/seed_database.py` | Product/policy seed loaders plus hardcoded reference rows | Uses some `docs/*.md` paths only as provenance strings |
| `scripts/ingest_rag.py` | `rag_docs/**/*.md` through `iter_rag_documents()` | Writes documents/chunks/embeddings to Postgres |
| `src/movia_sales_agent/agent/graph.py` | Knowledge plan sources | Fetches structured DB data, JSON config, then RAG context |
| `src/movia_sales_agent/agent/planners.py` | Analyzer/planner state | Chooses `postgres.products`, `postgres.policies`, `postgres.official_links`, JSON config, and RAG routes |
| `src/movia_sales_agent/db/repository.py` | Postgres tables with seed fallback | Supplies products, policies, links, and platform context to the agent |

Verified against code on 2026-06-17:

- `src/movia_sales_agent/config/knowledge.py` reads `CONFIG_ROOT.glob("*.json")` and `RAG_DOCS_ROOT.rglob("*.md")`.
- `scripts/seed_database.py` loads product and policy seeds, then inserts hardcoded reference rows with Markdown `source_path` provenance.
- `scripts/ingest_rag.py` builds records from `iter_rag_documents()` and writes knowledge documents/chunks.
- `src/movia_sales_agent/agent/graph.py` fetches structured DB context, JSON config context, and RAG context from the selected knowledge plan.
- `src/movia_sales_agent/db/repository.py` fetches products, policies, and official/platform context from Postgres, with seed fallback for products and policies.

## Change Routing

Use this table to decide where a future knowledge change belongs.

| Change type | Edit first | Also consider | Verification |
|---|---|---|---|
| Product price, setup fee, monthly fee, delivery time | `config/products.seed.json` | `docs/01_products_and_pricing.md` as authoring record | Run seed, product tests, price scenario |
| Product availability or product status | `config/products.seed.json` | RAG docs that mention availability | Run seed, unavailable-product tests |
| Product capabilities, includes, excludes, recommended fit | `config/products.seed.json` | `rag_docs/use_cases/*.md`, `rag_docs/product_explanations/*.md` for explanation | Run seed, product capability tests, RAG ingestion if RAG changed |
| Deposit, refund, final payment, monthly billing, API/token policy | `config/policies.seed.json` | `rag_docs/faqs/pre_purchase_faq.md` for plain-language explanation | Run seed, policy tests, RAG ingestion if RAG changed |
| Official app link | `scripts/seed_database.py` reference row and `config/platform_steps.json` | `docs/02_webapp_process.md` as authoring record | Run seed, restart app, link tests |
| Exact app/start/onboarding steps | `config/platform_steps.json` | `scripts/seed_database.py` if project statuses or official link changed | Restart app, run start/process tests |
| Project status names or lifecycle | `scripts/seed_database.py` reference rows | `config/platform_steps.json` if user-facing steps changed | Run seed, lifecycle tests |
| Channel availability or integration status | `scripts/seed_database.py` reference rows | RAG channel explanation docs | Run seed, channel tests, RAG ingestion if RAG changed |
| Objection strategy or recommended objection wording | `config/objection_playbook.json` | `docs/07_objection_playbook.md` as authoring record | Restart app, objection tests |
| Sales behavior, CTA shape, direct-close guidance | `config/sales_actions.json`, `config/cta_rules.json` | Planner code/tests if deterministic behavior changes | Restart app, policy/planner tests |
| Tone, style, forbidden wording | `config/tone_rules.json` | Response-quality evaluator if rules become testable | Restart app, response-quality tests |
| Competitor/comparison explanation | `rag_docs/comparisons/*.md` | `config/source_routing_rules.json` if routing itself changes | Run RAG ingestion, comparison tests |
| Industry narrative, use-case examples, persuasive benefits | `rag_docs/use_cases/*.md` | Product seed only if exact capability/fit facts change | Run RAG ingestion, use-case tests |
| Unknown or unapproved fact | `KNOWLEDGE_GAPS.md` | No runtime source until approved | Ensure agent does not answer it as official |
| New Markdown change brief | `docs/knowledge_change_requests/*.md` | The runtime destination selected after classification | Classify claims, then follow the workflow for the actual destination |

## Update Workflows

### Structured Postgres Seed Change

Use for exact commercial facts: products, prices, policies, official links, channels, integrations, and statuses.

1. Identify the authoritative runtime source using this map.
2. Edit the seed/config/code source that populates the table.
3. Run:

```bash
python scripts/seed_database.py
```

4. Run focused tests for the changed fact.
5. If the app is already running, restart it when JSON config also changed.

### JSON Runtime Config Change

Use for playbooks, platform steps, CTAs, tone, source routing, and post-purchase handoff content.

1. Edit the relevant `docs/movia_knowledge_source/config/*.json` file.
2. Restart the app or test process so `load_config_bundle()` reloads.
3. Run focused planner/response tests.
4. Do not run RAG ingestion unless a `rag_docs` file also changed.

### RAG Markdown Change

Use for explanations, comparisons, examples, FAQs, and industry narratives that do not need exact deterministic answers.

1. Edit only the relevant `docs/movia_knowledge_source/rag_docs/**/*.md` file.
2. Run:

```bash
python scripts/ingest_rag.py
```

3. Run focused retrieval and response tests.
4. Do not place prices, refund rules, official links, exact product scope, or exact platform steps only in RAG.

### Foundational Markdown Change

Use when receiving a new authoring brief or revising broad documentation. Do not edit the original package files in `docs/movia_knowledge_source/docs/*.md` for routine changes. Add a new change brief under `docs/knowledge_change_requests/` and treat it as the authoring input.

1. Add or read the change brief in `docs/knowledge_change_requests/`.
2. Classify each claim:
   - exact structured fact;
   - runtime behavior/playbook rule;
   - explanatory RAG content;
   - unsupported or uncertain gap.
3. Resolve conflicts using the authority table above.
4. Update the corresponding runtime source from this map.
5. Preserve provenance by referencing the change brief in notes, tests, commit messages, or future source maps where useful.
6. Run the workflow for the actual runtime source that changed.

## Guardrails

- Do not rely on RAG for exact prices, refund rules, payment percentages, official links, product availability, or exact product scope.
- Do not treat `docs/*.md` edits as live runtime changes until the appropriate seed/config/RAG source is updated.
- Do not edit the original `docs/movia_knowledge_source/docs/*.md` package files for ordinary knowledge updates; create a new Markdown brief under `docs/knowledge_change_requests/`.
- Do not let lower-authority sources override structured Postgres facts, deterministic code behavior, or official runtime config.
- Do not ingest `KNOWLEDGE_GAPS.md` as official knowledge.
- Do not sell unavailable products or upcoming channels as active.
- Prefer the smallest source change that matches the information type.
- When a single authoring brief contains multiple fact types, split the implementation across structured seed, JSON config, and RAG rather than forcing everything into one destination.
