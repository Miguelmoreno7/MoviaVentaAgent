# MovIA Sales Agent Knowledge Package

Fecha de creación: 2026-06-02

Este paquete contiene documentos `.md` y archivos `.json` para que Codex pueda construir la base de conocimiento y arquitectura inicial del agente vendedor conversacional de MovIA.

## Objetivo

Separar la información de MovIA según su tipo de uso:

- **Postgres/Supabase:** datos exactos como productos, precios, features, políticas, links y estados.
- **JSON:** reglas, playbooks, acciones comerciales, objeciones, pasos de plataforma y routing de fuentes.
- **RAG:** explicaciones, beneficios, casos de uso, comparaciones y FAQs abiertas.
- **Redis:** memoria temporal, debounce, mensajes recientes y cache.
- **Prompt base:** reglas universales del agente.

## Orden sugerido para Codex

1. Leer `docs/00_market_check.md`.
2. Leer `docs/01_products_and_pricing.md`.
3. Leer `docs/02_webapp_process.md`.
4. Leer `docs/03_policies.md`.
5. Leer `docs/04_channels_and_integrations.md`.
6. Leer `docs/05_use_cases_and_segmentation.md`.
7. Leer `docs/06_sales_actions.md`.
8. Leer `docs/07_objection_playbook.md`.
9. Leer `docs/08_industry_benefits.md`.
10. Leer `docs/09_rag_knowledge_index.md`.
11. Leer `docs/10_codex_implementation_prompt.md`.
12. Usar `config/*.json` como base de reglas y seeds.
13. Usar `rag_docs/**/*.md` como fuente inicial para chunks/embeddings.

## Nota importante

Los productos **MovIA Ventas** y **MovIA Pro Comercial** están marcados como **aún no disponibles**. Codex no debe venderlos como disponibles. Puede usarlos como producto futuro o waitlist.
