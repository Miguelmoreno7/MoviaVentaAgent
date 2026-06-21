# 10 - Prompt base para Codex

Estamos construyendo el agente vendedor conversacional de MovIA usando LangGraph.

## Objetivo principal

Crear primero la arquitectura de conocimiento y luego construir un skeleton local del agente para probar en localhost.

No queremos un agente autónomo que decida todo libremente.

Queremos un agente conversacional de preventa con:

1. Fuentes controladas.
2. Bajo costo de tokens.
3. Alta precisión comercial.
4. Persuasión hacia venta.
5. Separación clara entre datos exactos, reglas, RAG y memoria.

## Arquitectura conceptual

User Message
→ load_memory
→ analyze_turn
→ update_lead_state
→ sales_policy_planner
→ knowledge_planner
→ fetch_structured_data / fetch_json_playbooks / fetch_rag_context
→ merge_context
→ generate_response
→ save_memory

## Regla central

El LLM no decide libremente la venta.

El LLM interpreta lenguaje natural y genera respuestas.

La lógica del sistema decide:

- Acción comercial.
- Fuentes de conocimiento.
- Ruta de ejecución.
- Cuándo usar RAG.
- Cuándo consultar Postgres.
- Cuándo usar JSON.
- Cuándo redirigir a Miguel.

## analyze_turn

Debe usar LLM barato con salida JSON.

Debe extraer:

- intent
- topics
- has_objection
- objection_type
- business_type
- main_channel
- pain
- urgency
- buying_signal
- wants_to_start
- is_post_purchase
- lead_updates

## sales_policy_planner

Debe ser principalmente lógico.

Debe recibir:

- analysis
- lead_profile
- last_action
- current_stage

Debe decidir:

- macro_action
- micro_action
- commercial_goal
- next_question
- cta_type
- objection_flow_step

## Acciones comerciales permitidas

- answer_and_advance
- discover_need
- narrow_solution
- recommend_solution
- persuade_value
- handle_objection
- risk_reversal
- compare_alternative
- explain_process
- soft_close
- direct_close
- handoff_to_miguel
- answer_unknown_safely

## Reglas de prioridad

1. Si is_post_purchase = true → handoff_to_miguel.
2. Si wants_to_start = true → direct_close.
3. Si has_objection = true → handle_objection.
4. Si faltan datos mínimos → discover_need o answer_and_discover.
5. Si hay suficiente contexto → recommend_solution.
6. Si buying_signal es alto → soft_close.
7. Si no encaja → answer_unknown_safely.

## knowledge_planner

Debe soportar múltiples fuentes.

Ejemplo:

Usuario:
“¿Cuál es el plan más barato y por qué me conviene para mi clínica dental?”

Debe generar:

- Structured fetch: cheapest active plan desde Postgres.
- RAG fetch: beneficios/caso de uso dental.
- JSON fetch: sales_action answer_and_advance o recommend_solution.

## Source rules

- Datos exactos → Postgres/Supabase.
- Pasos, reglas y playbooks → JSON.
- Explicaciones, beneficios, casos de uso y comparaciones → RAG.
- Datos del lead → Postgres.
- Mensajes recientes/cache/debounce → Redis.
- Reglas universales → prompt base.

## Fuentes de conocimiento

Crear o proponer tablas:

- movia_products
- movia_product_features
- movia_channels
- movia_integrations
- movia_official_links
- movia_policies
- movia_project_statuses
- movia_lead_profiles
- movia_conversation_summaries
- movia_conversation_messages
- movia_knowledge_documents
- movia_knowledge_chunks

## JSON en repo

Crear:

- config/sales_actions.json
- config/objection_playbook.json
- config/source_routing_rules.json
- config/platform_steps.json
- config/onboarding_steps.json
- config/post_purchase_handoff.json
- config/cta_rules.json
- config/tone_rules.json

## RAG docs

Usar los documentos dentro de rag_docs/.

Los documentos deben partirse en chunks pequeños con metadata útil.

## Redis

Usar Redis para:

- recent message buffer
- lead-level debounce
- temporary retrieval cache
- ephemeral graph session cache

No usar Redis como única memoria persistente.

## Prompt base

Debe incluir:

- Eres el agente de preventa de MovIA.
- Tu objetivo es informar, recomendar y avanzar la venta.
- Responde solo con información oficial recibida en contexto.
- No inventes precios, tiempos, links, features o políticas.
- Si falta información, pregunta o responde con límites.
- Cada respuesta debe contestar la duda y avanzar una micro-etapa comercial.
- No atiendas post-compra compleja; redirige a Miguel.
- No menciones detalles técnicos internos salvo que el usuario pregunte explícitamente.

## Skeleton local de LangGraph

Crear nodos:

- load_memory
- analyze_turn
- update_lead_state
- sales_policy_planner
- knowledge_planner
- fetch_structured_data
- fetch_json_playbooks
- fetch_rag_context
- merge_context
- generate_response
- save_memory

Debe correr localmente para pruebas.

## Casos de prueba iniciales

1. “¿Cuánto cuesta?”
2. “¿Cuál es el plan más barato y por qué me conviene para una clínica dental?”
3. “Se me hace caro.”
4. “Ya tengo alguien que responde WhatsApp.”
5. “¿Cómo lleno la información en la página?”
6. “Quiero empezar.”
7. “Ya pagué, ¿qué sigue?”
8. “¿Esto es como ManyChat?”
9. “Tengo proveedores que me mandan tickets y fotos, ¿qué agente necesito?”

## Restricciones

- No construir una implementación one-shot gigante sin plan.
- Primero inspeccionar el repo.
- Primero crear plan técnico con archivos, tablas y migraciones propuestas.
- No modificar producción.
- No inventar datos faltantes.
- Crear KNOWLEDGE_GAPS.md con información faltante.
- Crear seeds solo con datos confirmados.
- Todo dato dudoso debe marcarse como draft o placeholder.
