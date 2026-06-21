# MovIA Validation Plan - Difficult Lead Scenarios

- **Agent:** MovIA Preventa
- **Channel:** WhatsApp
- **Date created:** 2026-06-04

## Objective

Validate the MovIA pre-sales conversational agent against difficult inbound leads coming from Facebook Ads into WhatsApp. The evaluation should measure commercial accuracy, policy compliance, source selection, objection handling, memory consistency, scope control, and the ability to move the sale forward without hallucinating.

## Recommended conversation length

- **target_user_turns:** 12-15 user turns
- **reasoning:** B2B sales cadence references commonly mention ~8-12 touchpoints and 8-15 for B2B deals. For WhatsApp inbound from Facebook Ads, use 10-15 user turns as a realistic stress-test window, not a guaranteed close requirement.
- **stress_test_target:** 12 user turns per scenario

## Evaluation framework recommendation

- **primary:** RAGAS for RAG + agent/multi-turn evaluation, especially when validating retrieval, faithfulness, and goal-oriented multi-turn success.
- **secondary:** DeepEval or LangSmith can be added later for CI-style pass/fail conversational metrics, trace-aware debugging, and regression tests.
- **note:** Because MovIA is hybrid (Postgres + JSON + RAG + LangGraph state), do not rely only on RAG metrics. Evaluate source selection, sales policy action, policy compliance, memory consistency, and response quality.

## MovIA ground truth

### Available products

| Slug | Name | Setup MXN | Monthly MXN | Delivery time | Status |
|---|---|---:|---:|---|---|
| movia_captura | MovIA Captura | 4900 | 450 | 3-5 dias habiles | available |
| movia_hibrido | MovIA Hibrido | 7500 | 550 | 5-10 dias habiles | available |

### Coming soon products

| Slug | Name | Setup MXN | Monthly MXN | Delivery time | Status |
|---|---|---:|---:|---|---|
| movia_ventas | Agente MovIA Ventas | 13500 | 1000 | aprox. 15 dias habiles | coming_soon |
| movia_pro_comercial | Agente MovIA Pro Comercial | 25000 | 2000 | aprox. 15 dias habiles | coming_soon |

- **official_channel:** WhatsApp
- **upcoming_channels:** Facebook, Instagram
- **app_url:** https://app.moviatech.com.mx
- **payment_policy:** 50% deposit to start; deposit is non-refundable; remaining payment after customer approves agent; monthly starts after approval; non-payment pauses agent.
- **support_policy:** After deposit, customer receives personalized support with Miguel. Pre-sales bot should redirect post-purchase questions to Miguel without verifying payment.

## Required debug fields

- `conversation_id`
- `turn_id`
- `intent`
- `topics`
- `current_stage`
- `macro_action`
- `micro_action`
- `objection_type`
- `objection_flow_step`
- `knowledge_plan.fetches`
- `sources_used`
- `rag_used`
- `structured_used`
- `json_used`
- `final_cta_type`
- `unsupported_claims`
- `token_usage`

## Global pass criteria

- Does not invent prices, channels, delivery times, integrations, or refund policy.
- Does not sell Facebook/Instagram as currently available.
- Does not sell MovIA Ventas or Pro Comercial as available unless user accepts future/waitlist framing.
- If the lead asks for actions, correctly differentiates Captura vs Hibrido.
- Handles objections with thank/empathize/open question before long persuasion.
- Uses Postgres for exact pricing/policies, JSON for process/playbooks, RAG for explanations/comparisons/use cases.
- Maintains memory across at least 12 user turns and can reference early information later.
- Every response answers the explicit question and advances one commercial micro-step.

## Custom metrics to track

- `commercial_accuracy`
- `policy_compliance`
- `sales_progression`
- `memory_consistency`
- `scope_control`
- `objection_methodology_compliance`
- `unsupported_claim_rate`

## RAGAS / evaluation mapping notes

**Recommended usage:** Use each conversation as a multi-turn test case. Run the actual MovIA agent turn by turn, capture outputs and debug trace, then score against expected_state and criteria.

### RAGAS metrics to consider
- AspectCritic for multi-turn success criteria
- AgentGoalAccuracy for goal completion where available
- ToolCallAccuracy or custom source_selection_accuracy for expected Postgres/JSON/RAG fetches
- Faithfulness and ResponseRelevancy for turns that use RAG
- ContextPrecision/ContextRecall for RAG retrieval turns

### Sample eval record shape

```json
{
  "conversation_id": "MOVIA-VAL-001",
  "turn_id": 5,
  "user_input": "Y por que no usar ManyChat?",
  "agent_output": "<actual output from MovIA agent>",
  "retrieved_contexts": [
    "<RAG chunks if any>"
  ],
  "debug_trace": {
    "macro_action": "compare_alternative",
    "micro_action": "compare_manychat",
    "sources_used": [
      "rag.comparisons.manychat"
    ]
  },
  "expected": {
    "macro_action": "compare_alternative",
    "must_not_claim": [
      "ManyChat is bad",
      "MovIA supports Instagram now"
    ]
  }
}
```

## Scenario index

| Conversation ID | Persona | Difficulty | Success goal | Primary risks |
|---|---|---|---|---|
| MOVIA-VAL-001 | Lead sarcastico que desafia credibilidad | high | No caer en defensiva; explicar valor, precios oficiales y llevarlo a identificar canal/dolor; idealmente invitar a iniciar demo o registro. | sarcasm, trust objection, competitor comparison, pressure to overpromise |
| MOVIA-VAL-002 | Lead que cambia de tema para probar memoria y consistencia | high | Mantener contexto de barberia/WhatsApp, responder cambios de tema sin perder hilo y cerrar hacia MovIA Captura. | topic switching, memory consistency, scope drift, availability hallucination |
| MOVIA-VAL-003 | Lead que prueba politicas, reembolsos y soporte | very_high | Mantener politicas firmes: deposito 50%, no reembolso, mensualidad, soporte limitado, tokens incluidos con limite razonable. | refund hallucination, support overpromise, policy conflict, post-purchase confusion |
| MOVIA-VAL-004 | Lead que intenta meter acciones complejas en Captura | high | Detectar que requiere Hibrido, explicar que Captura no hace acciones y proteger alcance. | wrong product recommendation, underpricing, scope creep, API/action confusion |
| MOVIA-VAL-005 | Lead agresivo, bajo presupuesto, quiere prueba gratis y compara con hacerlo solo | very_high | Mantener tono calmado, no regalar, no prometer trial ilimitado, sugerir demo de 10 mensajes y cerrar a Captura si encaja. | price objection, free trial pressure, discount pressure, tone escalation, unsupported promises |

---

# Detailed scenarios

## MOVIA-VAL-001 - Lead sarcastico que desafia credibilidad

- **Difficulty:** high
- **Success goal:** No caer en defensiva; explicar valor, precios oficiales y llevarlo a identificar canal/dolor; idealmente invitar a iniciar demo o registro.
- **Primary risks:** sarcasm, trust objection, competitor comparison, pressure to overpromise

### Lead profile seed

```json
{
  "business_type": "clinica dental",
  "main_channel": null,
  "pain": "tarda en responder pacientes",
  "tone": "sarcastic/skeptical"
}
```

### Turn 1

**User message**

> Vi su anuncio. A ver, convenceme rapido: seguro es otro bot que contesta tonterias, no?

**Ideal assistant response**

> Entiendo la duda. MovIA no busca venderte un bot generico, sino un agente configurado con la informacion de tu negocio para responder leads por WhatsApp. Si tu objetivo es solo responder preguntas y filtrar interesados, normalmente empezamos con MovIA Captura. Para ubicarlo bien: que tipo de negocio tienes?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | discovery |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_scope_then_discover_business |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | rag.overview, json.sales_actions |

### Turn 2

**User message**

> Clinica dental. Pero no me digas que va a vender brackets solito.

**Ideal assistant response**

> No te diria eso. Para una clinica dental, el primer valor no es que 'venda brackets solo', sino que responda rapido dudas repetidas: horarios, tratamientos, precios aproximados si ustedes los proporcionan, requisitos y captura de datos del paciente. Eso ayuda a que recepcion no pierda leads cuando esta ocupada. Tus pacientes te escriben mas por WhatsApp directo o vienen de anuncios/redes?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | discovery |
| `macro_action` | persuade_value |
| `micro_action` | industry_specific_value |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | rag.use_cases.dental, json.cta_rules |

### Turn 3

**User message**

> De Facebook Ads a WhatsApp. La gente pregunta precio y luego desaparece.

**Ideal assistant response**

> Ese caso encaja muy bien con MovIA Captura si solo necesitas responder, filtrar y redirigir a humano. El agente puede contestar preguntas frecuentes, pedir datos basicos y dejar mas claro si el lead realmente esta interesado. Si ademas quieres que agende citas o mande recordatorios, ahi ya seria MovIA Hibrido. Hoy necesitas solo responder y filtrar, o tambien agendar?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | narrow_solution |
| `micro_action` | differentiate_captura_vs_hibrido |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features, rag.use_cases.dental |

### Turn 4

**User message**

> Solo responder. Cuanto cuesta el chiste?

**Ideal assistant response**

> Para ese caso, el plan disponible que mas encaja es MovIA Captura: $4,900 MXN de setup y $450 MXN mensuales. Se entrega normalmente en 3 a 5 dias habiles. Incluye respuestas con informacion de tu negocio, calificacion basica de leads y redireccion a humano; no agenda ni ejecuta acciones externas. Quieres que te explique como seria el proceso para iniciarlo?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_price_then_explain_scope |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_close |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 5

**User message**

> Y por que no usar ManyChat? Es mas conocido que ustedes.

**Ideal assistant response**

> Tiene sentido compararlo. ManyChat puede servir muy bien para flujos mas armados tipo menu o automatizaciones simples. MovIA busca algo mas personalizado para responder preguntas abiertas con la informacion de tu clinica y filtrar leads sin que tengas que construir todo tu flujo. Si lo que quieres es solo botones, ManyChat podria bastar; si quieres respuestas mas adaptadas a tu negocio, MovIA tiene mas sentido. Tus preguntas de pacientes son repetitivas o llegan muy variadas?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | comparing |
| `macro_action` | compare_alternative |
| `micro_action` | compare_manychat |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | rag.comparisons.manychat, json.sales_actions |

### Turn 6

**User message**

> Variadas. Unos preguntan limpieza, otros ortodoncia, otros urgencias. Pero si contesta mal me quema.

**Ideal assistant response**

> Esa preocupacion es valida. Por eso el agente se construye con tu informacion y se prueba antes de activarlo. Tu ves escenarios de prueba y puedes aprobarlo o pedir ajustes antes del pago final. La idea no es soltarlo sin revision, sino validar que responda como esperas. Que informacion tendrias lista para entrenarlo: catalogo, precios, tratamientos o preguntas frecuentes?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | risk_reversal |
| `micro_action` | explain_testing_before_release |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.platform_steps, postgres.policies, rag.use_cases.dental |

### Turn 7

**User message**

> Tengo PDF con tratamientos y precios. Pero no quiero que prometa diagnosticos.

**Ideal assistant response**

> Perfecto, eso se puede controlar. El agente puede usar tu PDF para informar sobre tratamientos y precios, pero se le puede indicar que no diagnostique ni prometa resultados medicos, y que redirija a valoracion cuando aplique. Ese tipo de regla es justo lo que nos conviene dejar claro en el intake y en ejemplos de conversacion. Quieres que te diga que tendrias que subir en la plataforma?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_policy_then_reduce_risk |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.platform_steps, rag.use_cases.dental |

### Turn 8

**User message**

> A ver, y si un paciente manda una foto de su diente?

**Ideal assistant response**

> MovIA Captura puede entender imagenes cuando aplique, pero para una clinica dental debe usarse con cuidado: puede reconocer que el paciente envio una imagen y pedir datos o redirigir a valoracion, no diagnosticar. Para salud, lo correcto seria que el agente guie y capture informacion, no que sustituya criterio profesional. Te serviria mas que pida nombre, telefono, molestia y disponibilidad para valoracion?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | risk_reversal |
| `micro_action` | explain_safe_image_handling |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.product_features, rag.use_cases.dental |

### Turn 9

**User message**

> Mmm. Me sigue sonando a que luego va a fallar y nadie responde.

**Ideal assistant response**

> Gracias por decirlo directo. La duda real aqui parece ser confianza y soporte. MovIA incluye mantenimiento mensual para mantener el agente activo y ajustes dentro del alcance, como actualizar informacion o mejorar respuestas. Despues del deposito tambien tienes seguimiento personalizado con Miguel. Que te preocuparia mas: que falle tecnicamente o que conteste algo fuera de tono?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | trust_empathize_ask_open_question |
| `objection_type` | trust_objection |
| `objection_flow_step` | thank_empathize_ask_open_question |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.policies |

### Turn 10

**User message**

> Que conteste fuera de tono. Mi recepcionista es amable, no robotica.

**Ideal assistant response**

> Eso es totalmente ajustable. En los ejemplos de conversacion puedes mostrar como quieres que responda: amable, breve, formal o cercano. Nosotros usamos esos ejemplos para probar el comportamiento antes de activarlo. Si tu objetivo es conservar un tono humano pero responder rapido, Captura sigue siendo buena opcion. Quieres empezar con un demo o prefieres ir directo al registro del agente?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | solution_recommended |
| `macro_action` | soft_close |
| `micro_action` | soft_invite_to_start |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_close |
| `expected_sources` | json.platform_steps, json.cta_rules |

### Turn 11

**User message**

> Dame el link, pero no prometo nada.

**Ideal assistant response**

> Claro. Puedes iniciar en https://app.moviatech.com.mx. Entras, te registras, eliges customer/cliente y despues Crear agente. Para tu caso seleccionaria MovIA Captura. Ahi podras dejar objetivo, informacion de tu clinica, documentos PDF y ejemplos de conversacion. El deposito es del 50% para empezar el proyecto.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | direct_close |
| `micro_action` | send_app_link |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | send_app_link |
| `expected_sources` | postgres.official_links, json.platform_steps, postgres.policies |

### Turn 12

**User message**

> Ok, si desde el mensaje 2 te dije clinica dental, no me vuelvas a preguntar eso despues.

**Ideal assistant response**

> Correcto, lo tengo presente: es para una clinica dental y el caso viene de Facebook Ads a WhatsApp. Por eso la recomendacion sigue siendo MovIA Captura si solo necesitas responder y filtrar leads. En el registro, lo mas importante sera subir el PDF de tratamientos/precios y ejemplos de tono para que el agente responda como tu recepcionista.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | answer_and_advance |
| `micro_action` | memory_reference_and_next_step |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | explain_next_step |
| `expected_sources` | memory.lead_profile, json.platform_steps |

---

## MOVIA-VAL-002 - Lead que cambia de tema para probar memoria y consistencia

- **Difficulty:** high
- **Success goal:** Mantener contexto de barberia/WhatsApp, responder cambios de tema sin perder hilo y cerrar hacia MovIA Captura.
- **Primary risks:** topic switching, memory consistency, scope drift, availability hallucination

### Lead profile seed

```json
{
  "business_type": "barberia",
  "main_channel": "WhatsApp",
  "pain": "mensajes despues de horario",
  "tone": "distracted/testing"
}
```

### Turn 1

**User message**

> Tengo una barberia y me llegan mensajes despues de las 9 pm por WhatsApp.

**Ideal assistant response**

> Para una barberia, ese caso encaja muy bien con MovIA Captura si el objetivo es responder dudas fuera de horario, precios, ubicacion, horarios y filtrar interesados. Si quieres que tambien agende citas, entonces seria MovIA Hibrido. Hoy solo quieres responder o tambien agendar?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | discovery |
| `macro_action` | narrow_solution |
| `micro_action` | differentiate_captura_vs_hibrido |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, rag.use_cases.beauty_barbershop |

### Turn 2

**User message**

> Solo responder por ahora. Luego vemos agenda.

**Ideal assistant response**

> Entonces empezaria con MovIA Captura. Te ayuda a contestar preguntas repetidas y capturar datos del interesado sin ejecutar acciones externas. Si despues quieres agendar, se puede evaluar pasar a Hibrido. Cuantas preguntas al dia recibes mas o menos por WhatsApp?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | recommend_solution |
| `micro_action` | recommend_movia_captura |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 3

**User message**

> Unas 20. Oye y ustedes hacen paginas web?

**Ideal assistant response**

> Podemos hablarlo aparte, pero el enfoque principal de MovIA aqui son agentes por WhatsApp. Para tu barberia, lo importante seria que el agente responda a esos 20 mensajes diarios y no se pierdan cuando ya cerraste. Regresando al agente: que suelen preguntar mas, precios, horarios o ubicacion?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | unknown_recovery |
| `macro_action` | answer_unknown_safely |
| `micro_action` | return_to_automation_need |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.sales_actions, rag.overview |

### Turn 4

**User message**

> Precios y horarios. Pero tambien me preguntan si hay promo de corte y barba.

**Ideal assistant response**

> Perfecto. Eso se puede cargar como informacion del negocio para que el agente responda precios, horarios y promociones vigentes. Si la promocion cambia, tambien se puede actualizar dentro del soporte mensual. Esto sigue siendo Captura porque solo responde y filtra. Tienes esos precios en PDF o en algun documento?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_scope_then_route_product |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.product_features, postgres.policies, json.platform_steps |

### Turn 5

**User message**

> No, los tengo en una imagen del menu pegada en la pared.

**Ideal assistant response**

> Tambien puede servir como referencia inicial si se interpreta la imagen, pero para construirlo bien conviene pasar precios y promociones a PDF o texto claro. Asi reducimos errores. En la app podras subir PDF y agregar notas del negocio. Quieres que te explique los pasos?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | explain_process |
| `micro_action` | explain_pdf_documents |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.platform_steps |

### Turn 6

**User message**

> Cambiando de tema, Facebook e Instagram ya funcionan?

**Ideal assistant response**

> Actualmente el canal disponible oficialmente es WhatsApp. Facebook e Instagram estan en camino, pero no te los venderia como disponibles todavia. Para tu caso, como ya dijiste que los mensajes llegan por WhatsApp, podemos arrancar por ahi sin problema.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_channel_then_keep_context |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.channels, memory.lead_profile |

### Turn 7

**User message**

> Ok, cuanto era el plan que me recomendaste?

**Ideal assistant response**

> Para tu barberia te recomende MovIA Captura. Cuesta $4,900 MXN de setup y $450 MXN mensuales, con entrega estimada de 3 a 5 dias habiles. Aplica porque por ahora solo quieres responder y filtrar mensajes, no agendar automaticamente.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_price_with_memory |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, memory.lead_profile |

### Turn 8

**User message**

> Y si manana quiero que agende, no me vas a querer cobrar todo otra vez?

**Ideal assistant response**

> Si el alcance cambia a agendar, ya no seria Captura; tendriamos que evaluar pasarlo a Hibrido porque ahi el agente ejecuta acciones. No te diria que es 'todo otra vez', pero si seria una cotizacion o ajuste de alcance segun lo que se necesite conectar. Para iniciar barato y validar, Captura puede ser el primer paso.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | scope_empathize_clarify |
| `objection_type` | scope_objection |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.products, postgres.product_actions |

### Turn 9

**User message**

> Entonces mejor dame Hibrido de una vez, pero al precio de Captura.

**Ideal assistant response**

> Entiendo por que lo pedirias, pero no seria correcto ofrecer Hibrido al precio de Captura porque Hibrido ya incluye acciones y posible integracion con procesos externos. Captura responde y filtra; Hibrido puede ejecutar hasta 2 acciones. Si tu prioridad hoy es costo, arrancaria con Captura y dejaria agenda para una segunda etapa.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | price_scope_reframe |
| `objection_type` | price_objection |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.products, postgres.product_features |

### Turn 10

**User message**

> A ver si entendiste: que negocio tengo?

**Ideal assistant response**

> Tienes una barberia. Me comentaste que recibes unos 20 mensajes diarios por WhatsApp despues de horario, principalmente sobre precios, horarios y promociones como corte y barba.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | answer_and_advance |
| `micro_action` | memory_reference_and_next_step |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | memory.lead_profile, memory.conversation_summary |

### Turn 11

**User message**

> Bien. Mandame donde empiezo.

**Ideal assistant response**

> Puedes empezar en https://app.moviatech.com.mx. Te registras, eliges customer/cliente y seleccionas Crear agente. Para tu caso, elige MovIA Captura si quieres responder y filtrar por WhatsApp sin agenda automatica. Recuerda que para iniciar se paga el 50% de deposito.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | direct_close |
| `micro_action` | send_app_link |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | send_app_link |
| `expected_sources` | postgres.official_links, json.platform_steps, postgres.policies |

### Turn 12

**User message**

> Y el demo ese de 10 mensajes me sirve antes?

**Ideal assistant response**

> Si, el demo te puede servir para entender como se configura un agente y probar hasta 10 mensajes. Solo ten en cuenta que es una prueba, no el agente final de tu barberia. Si despues te convence, creas el agente y completas la informacion real del negocio.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | explain_process |
| `micro_action` | explain_demo_10_messages |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.platform_steps |

---

## MOVIA-VAL-003 - Lead que prueba politicas, reembolsos y soporte

- **Difficulty:** very_high
- **Success goal:** Mantener politicas firmes: deposito 50%, no reembolso, mensualidad, soporte limitado, tokens incluidos con limite razonable.
- **Primary risks:** refund hallucination, support overpromise, policy conflict, post-purchase confusion

### Lead profile seed

```json
{
  "business_type": "fumigacion",
  "main_channel": "WhatsApp",
  "pain": "cotizaciones y dudas repetidas",
  "tone": "legalistic/distrustful"
}
```

### Turn 1

**User message**

> Tengo un negocio de fumigacion. Antes de hablar, quiero saber si me devuelven el dinero si no me gusta.

**Ideal assistant response**

> Te lo digo claro: el deposito no es reembolsable. MovIA trabaja con un deposito del 50% para iniciar, y despues se hacen pruebas y revision para que puedas aprobar o pedir ajustes antes del pago final. Si quieres, te explico primero como se reduce el riesgo antes de pagar el restante.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | refund_policy_clear_then_risk_reversal |
| `objection_type` | trust_objection |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies, json.objection_playbook |

### Turn 2

**User message**

> Eso suena mal. O sea pago y si no sirve ya perdi.

**Ideal assistant response**

> Entiendo como puede sonar. La razon es que el deposito activa trabajo personalizado: revisar tu informacion, construir el agente y probarlo. Lo que si hacemos para protegerte es que antes del pago final ves escenarios de prueba y puedes pedir ajustes. El objetivo es que apruebes cuando el agente ya responde conforme a lo solicitado.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | empathize_tie_solution |
| `objection_type` | trust_objection |
| `objection_flow_step` | tie_solution |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies, json.platform_steps |

### Turn 3

**User message**

> Y cuantos ajustes incluye? No quiero que luego todo me lo cobren.

**Ideal assistant response**

> Dentro del alcance del agente, los ajustes de informacion y comportamiento se contemplan: por ejemplo actualizar respuestas, precios, servicios o forma de contestar. Lo que si se cotiza aparte son features nuevas o cambiar el tipo de agente, como pasar de solo responder a agendar o conectar sistemas externos.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_policy_then_reduce_risk |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies, postgres.product_features |

### Turn 4

**User message**

> Entonces si quiero que cotice fumigacion por metros cuadrados, entra o no?

**Ideal assistant response**

> Depende de la complejidad. Si solo responde rangos o explica el proceso, podria ser Captura. Si debe calcular una cotizacion con reglas, registrar datos o ejecutar una accion, seria MovIA Hibrido. Para fumigacion, si quieres que pida metros, tipo de plaga y zona para generar una cotizacion simple, probablemente hablamos de Hibrido.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | narrow_solution |
| `micro_action` | detect_if_actions_are_needed |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions, rag.use_cases.home_services |

### Turn 5

**User message**

> Cuanto cuesta ese entonces?

**Ideal assistant response**

> MovIA Hibrido cuesta $7,500 MXN de setup y $550 MXN mensuales. Incluye todo lo de Captura y hasta 2 acciones acordadas, como cotizar de forma simple o registrar solicitudes, siempre que el alcance quede bien definido.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_price_then_explain_scope |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 6

**User message**

> Y si no pago la mensualidad un mes?

**Ideal assistant response**

> Si no se paga la mensualidad, el agente se pausa. Cuando se regulariza el pago, puede volver a activarse. La mensualidad cubre mantenimiento, infraestructura, recursos computacionales y ajustes dentro del alcance.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_policy_then_reduce_risk |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies |

### Turn 7

**User message**

> Y si me escribe mucha gente? Me van a cobrar tokens escondidos?

**Ideal assistant response**

> El uso de tokens/API viene incluido en la mensualidad hasta un limite razonable. Si el uso se vuelve muy alto, MovIA te avisaria antes de ajustar o cobrar algo adicional. No deberia manejarse como cargo escondido. Aun falta definir publicamente un limite exacto, asi que no te inventaria una cifra.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_policy_with_draft_limit |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies |

### Turn 8

**User message**

> No me gusta eso de limite razonable. Suena ambiguo.

**Ideal assistant response**

> Tienes razon en pedir claridad. Hoy la politica confirmada es que el uso normal esta incluido y que, si hubiera consumo extraordinario, se te avisaria antes de cualquier ajuste. No tenemos una cifra publica cerrada para darte en este momento, por eso prefiero no inventarla. Si tu volumen es alto, conviene revisarlo con Miguel antes de contratar.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | policy_ambiguity_acknowledge |
| `objection_type` | trust_objection |
| `objection_flow_step` | ask_open_question |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.policies |

### Turn 9

**User message**

> Y llamadas? Quiero que el bot llame al cliente.

**Ideal assistant response**

> Por ahora no incluimos llamadas. MovIA puede responder, guiar, calificar y en Hibrido ejecutar acciones acordadas como agendar o registrar informacion, pero llamadas no forman parte del alcance. Si tu proceso requiere llamada, lo correcto seria que el agente capture datos y redirija a humano.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_scope_then_route_product |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.product_features, postgres.products |

### Turn 10

**User message**

> Ok, pero despues de pagar quiero tu WhatsApp personal desde el dia uno.

**Ideal assistant response**

> Despues del deposito recibes seguimiento personalizado con Miguel para el proyecto. Antes del deposito, este canal te puede orientar en preventa y proceso. El deposito es justo lo que activa el trabajo personalizado y el seguimiento directo.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_support_policy |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies, json.post_purchase_handoff |

### Turn 11

**User message**

> Mandame link. Pero si no me gusta voy a reclamar.

**Ideal assistant response**

> Te paso el link: https://app.moviatech.com.mx. Solo para dejarlo claro antes de avanzar: el deposito del 50% no es reembolsable, pero antes del pago final veras pruebas del agente y podras pedir ajustes dentro del alcance. Para tu caso de fumigacion con posible cotizacion, revisaria MovIA Hibrido.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | direct_close |
| `micro_action` | send_app_link_with_policy_reminder |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | send_app_link |
| `expected_sources` | postgres.official_links, postgres.policies, postgres.products |

### Turn 12

**User message**

> Si ya pague despues te escribo por aqui?

**Ideal assistant response**

> Si ya realizaste el deposito o ya estas en proceso, Miguel te dara seguimiento personalizado. Este agente puede orientarte, pero los temas especificos del proyecto se revisan directamente con Miguel para evitar confusiones.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | post_purchase |
| `macro_action` | handoff_to_miguel |
| `micro_action` | post_purchase_to_miguel |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | redirect_to_miguel |
| `expected_sources` | json.post_purchase_handoff, postgres.policies |

---

## MOVIA-VAL-004 - Lead que intenta meter acciones complejas en Captura

- **Difficulty:** high
- **Success goal:** Detectar que requiere Hibrido, explicar que Captura no hace acciones y proteger alcance.
- **Primary risks:** wrong product recommendation, underpricing, scope creep, API/action confusion

### Lead profile seed

```json
{
  "business_type": "proveedores / garantias",
  "main_channel": "WhatsApp",
  "pain": "proveedores mandan tickets, fotos y datos",
  "tone": "practical but scope-pushing"
}
```

### Turn 1

**User message**

> Tengo proveedores que mandan ticket de compra, foto del detalle y datos de garantia por WhatsApp. Quiero automatizar eso.

**Ideal assistant response**

> Ese caso suena mas a MovIA Hibrido que a Captura, porque no solo quieres responder dudas: quieres procesar informacion, posiblemente registrar datos y seguir un flujo. Captura sirve para responder y filtrar; Hibrido permite hasta 2 acciones acordadas. Que acciones exactas quieres que haga con esos tickets y fotos?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | discovery |
| `macro_action` | narrow_solution |
| `micro_action` | detect_if_actions_are_needed |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions, rag.use_cases.suppliers_operations |

### Turn 2

**User message**

> Que revise el ticket, extraiga datos y los suba a mi panel.

**Ideal assistant response**

> Eso ya implica una accion externa: extraer datos y subirlos a un panel. Por alcance, no seria MovIA Captura. Tendriamos que evaluarlo como Hibrido, siempre que sea posible conectarnos al panel o definir una forma segura de registrar la informacion.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | recommend_solution |
| `micro_action` | recommend_movia_hibrido |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions |

### Turn 3

**User message**

> Pero solo son dos cosas, ticket y foto. Cobrame Captura.

**Ideal assistant response**

> Entiendo la idea, pero la diferencia no es la cantidad de archivos, sino que el agente tendria que ejecutar una accion: subir o registrar datos en un sistema. Captura puede entender y responder; Hibrido puede ejecutar hasta 2 acciones acordadas. Para no prometer algo incorrecto, lo pondria como Hibrido.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | scope_reframe_actions_vs_info |
| `objection_type` | scope_objection |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.product_features |

### Turn 4

**User message**

> Cuanto seria Hibrido?

**Ideal assistant response**

> MovIA Hibrido cuesta $7,500 MXN de setup y $550 MXN mensuales. La entrega estimada es de 5 a 10 dias habiles, dependiendo de que tan clara este la accion y la conexion necesaria. Incluye hasta 2 acciones acordadas.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_price_then_explain_scope |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions |

### Turn 5

**User message**

> Y si mi panel no tiene API?

**Ideal assistant response**

> Si tu panel no tiene API, hay que revisar alternativas. Puede que no sea viable automatizarlo directo o que se necesite otro mecanismo. No te prometeria integracion sin revisar el sistema. En ese caso, Hibrido requiere evaluacion tecnica antes de cerrar alcance.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | risk_reversal |
| `micro_action` | avoid_unconfirmed_integration |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.product_features, json.sales_actions |

### Turn 6

**User message**

> Bueno, entonces que solo responda a proveedores y me mande resumen.

**Ideal assistant response**

> Si solo responde a proveedores, pide datos y te redirige o resume informacion sin subirla al panel, eso podria acercarse mas a Captura. La clave es: Captura no ejecuta acciones externas. Si el resultado es solo respuesta, captura y redireccion humana, podria funcionar. Quieres que el humano sea quien registre el dato final?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | narrow_solution |
| `macro_action` | narrow_solution |
| `micro_action` | differentiate_captura_vs_hibrido |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 7

**User message**

> Si, que el humano lo registre. El bot solo ordena la info.

**Ideal assistant response**

> Entonces Captura podria ser suficiente: responderia, pediria ticket/foto/datos necesarios y redirigiria a humano con la informacion ordenada. No subiria datos al panel ni ejecutaria acciones. Captura cuesta $4,900 MXN de setup y $450 MXN mensuales.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | solution_recommended |
| `macro_action` | recommend_solution |
| `micro_action` | recommend_movia_captura |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 8

**User message**

> Ahi si. Y puede leer audio?

**Ideal assistant response**

> Si, MovIA Captura puede entender audio cuando aplique, ademas de texto e imagenes. Para tu caso, convendria definir que datos debe extraer o pedir al proveedor para que el resumen llegue ordenado al humano.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_feature_then_discover_data_fields |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.product_features |

### Turn 9

**User message**

> Que pida numero de ticket, fecha, proveedor y foto.

**Ideal assistant response**

> Perfecto. Ese es un flujo de captura claro: numero de ticket, fecha, proveedor y foto. Mientras el agente solo recopile y redirija a humano, sigue dentro de Captura. Si despues quieres que lo suba automaticamente al panel, ahi se moveria a Hibrido.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | recommend_solution |
| `micro_action` | confirm_captura_scope |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | memory.lead_profile, postgres.product_features |

### Turn 10

**User message**

> Ok, cuanto pago para empezar?

**Ideal assistant response**

> Para MovIA Captura, el setup es de $4,900 MXN. Para iniciar se paga el 50% de deposito, es decir $2,450 MXN. El resto se paga cuando apruebes el agente despues de la revision. La mensualidad es de $450 MXN y empieza cuando apruebas el agente.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_deposit_amount |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.policies |

### Turn 11

**User message**

> Va, mandame link.

**Ideal assistant response**

> Claro: https://app.moviatech.com.mx. Registrate, elige customer/cliente y selecciona Crear agente. En tu caso elegiria MovIA Captura y describiria que el agente debe recopilar numero de ticket, fecha, proveedor y foto, y redirigir a humano sin subir datos al panel.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | direct_close |
| `micro_action` | send_app_link_with_context |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | send_app_link |
| `expected_sources` | postgres.official_links, json.platform_steps, memory.lead_profile |

### Turn 12

**User message**

> Si luego quiero que suba datos al panel, que pasa?

**Ideal assistant response**

> Eso ya seria una accion externa y tendria que evaluarse como MovIA Hibrido o como ajuste de alcance. Lo importante es que Captura te puede ayudar a ordenar y redirigir; Hibrido seria para automatizar acciones como registrar en tu panel.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | answer_and_advance |
| `micro_action` | scope_future_upgrade |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions |

---

## MOVIA-VAL-005 - Lead agresivo, bajo presupuesto, quiere prueba gratis y compara con hacerlo solo

- **Difficulty:** very_high
- **Success goal:** Mantener tono calmado, no regalar, no prometer trial ilimitado, sugerir demo de 10 mensajes y cerrar a Captura si encaja.
- **Primary risks:** price objection, free trial pressure, discount pressure, tone escalation, unsupported promises

### Lead profile seed

```json
{
  "business_type": "estetica",
  "main_channel": "WhatsApp",
  "pain": "responder precios y disponibilidad",
  "tone": "aggressive/budget-sensitive"
}
```

### Turn 1

**User message**

> Cuanto cuesta? No tengo tiempo para rollos.

**Ideal assistant response**

> Claro. El plan disponible mas economico es MovIA Captura: $4,900 MXN de setup y $450 MXN mensuales. Sirve para responder dudas, calificar leads y redirigir a humano por WhatsApp, sin ejecutar acciones como agendar. Para decirte si te conviene: que tipo de negocio tienes?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | discovery |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_price_then_discover_business |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_features |

### Turn 2

**User message**

> Estetica. Y se me hace caro para un bot.

**Ideal assistant response**

> Te entiendo, gracias por decirlo directo. Para ubicarlo bien: se te hace caro por el pago inicial o porque todavia no ves claro cuanto te puede ahorrar en tiempo o leads perdidos?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | price_validate_ask_open_question |
| `objection_type` | price_objection |
| `objection_flow_step` | thank_empathize_ask_open_question |
| `rag_used` | False |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook |

### Turn 3

**User message**

> Por las dos. Yo puedo poner respuestas rapidas en WhatsApp gratis.

**Ideal assistant response**

> Si solo necesitas respuestas manuales guardadas, WhatsApp Business puede ayudarte. La diferencia es que MovIA responde automaticamente, usa la informacion de tu negocio, captura datos y filtra interesados cuando no puedes contestar. Para una estetica, eso ayuda si te preguntan precios, horarios, servicios o disponibilidad mientras estas atendiendo. Cuantos mensajes al dia recibes mas o menos?

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | comparing |
| `macro_action` | compare_alternative |
| `micro_action` | compare_whatsapp_business_only |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | False |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | rag.comparisons.whatsapp_business_only, rag.use_cases.beauty_barbershop |

### Turn 4

**User message**

> Unos 30, pero muchos solo preguntan precio y no compran.

**Ideal assistant response**

> Justo ahi puede aportar: no todos van a comprar, pero el agente puede responder rapido, pedir datos basicos y ayudarte a separar curiosos de interesados reales. Asi tu equipo no pierde tanto tiempo repitiendo lo mismo. Si no necesitas agenda automatica, Captura seria el punto de entrada.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | persuade_value |
| `micro_action` | opportunity_cost |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | rag.use_cases.beauty_barbershop, postgres.products |

### Turn 5

**User message**

> Dame prueba gratis sin deposito y si funciona pago.

**Ideal assistant response**

> No manejamos desarrollo personalizado sin deposito. Lo que si existe es crear un demo limitado de 10 mensajes para que entiendas como funciona la configuracion. Para construir un agente con tu informacion real, el inicio requiere el deposito del 50%.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | free_trial_boundary_with_demo |
| `objection_type` | wants_free_trial |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, json.platform_steps, postgres.policies |

### Turn 6

**User message**

> Entonces no confias en tu producto.

**Ideal assistant response**

> Si confiamos, pero tambien cuidamos el tiempo de configuracion personalizada. Crear un agente real implica revisar informacion, cargar datos, probar respuestas y ajustar. Por eso el demo sirve para conocer la idea, y el deposito activa el trabajo personalizado.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | trust_empathize_tie_solution |
| `objection_type` | trust_objection |
| `objection_flow_step` | tie_solution |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | json.objection_playbook, postgres.policies |

### Turn 7

**User message**

> Y si te paso mi Instagram?

**Ideal assistant response**

> Actualmente el canal disponible oficialmente es WhatsApp. Instagram esta en camino, pero no te lo venderia como disponible todavia. Si tus clientas terminan escribiendo por WhatsApp, podemos arrancar ahi.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_channel_availability |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.channels |

### Turn 8

**User message**

> Ok, WhatsApp. Pero quiero que agende citas tambien.

**Ideal assistant response**

> Si quieres que agende citas, ya no seria Captura. Eso entra en MovIA Hibrido porque implica una accion. Hibrido cuesta $7,500 MXN de setup y $550 MXN mensuales, e incluye hasta 2 acciones acordadas, como agendar o mandar recordatorios.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | qualified |
| `macro_action` | narrow_solution |
| `micro_action` | recommend_movia_hibrido_due_to_scheduling |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, postgres.product_actions |

### Turn 9

**User message**

> No, eso ya se fue caro. Entonces solo que responda precios.

**Ideal assistant response**

> Perfecto, entonces volvemos a MovIA Captura. Para tu estetica responderia precios, servicios, horarios y preguntas frecuentes, y puede pedir datos para que una persona cierre la cita. Setup $4,900 MXN, mensualidad $450 MXN.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | solution_recommended |
| `macro_action` | recommend_solution |
| `micro_action` | recommend_movia_captura |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | True |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.products, rag.use_cases.beauty_barbershop |

### Turn 10

**User message**

> Que pasa si en un mes cambio precios?

**Ideal assistant response**

> Eso entra dentro de ajustes de informacion. La mensualidad contempla mantenimiento y actualizaciones dentro del alcance, como cambiar precios, respuestas o informacion del negocio. No seria una feature nueva mientras siga siendo el mismo agente de respuesta.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | educating |
| `macro_action` | answer_and_advance |
| `micro_action` | answer_support_policy |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies |

### Turn 11

**User message**

> Ok. Me convenciste a medias. Donde veo eso?

**Ideal assistant response**

> Puedes verlo e iniciar en https://app.moviatech.com.mx. Registrate, elige customer/cliente y puedes crear un demo de 10 mensajes o crear directamente el agente. Para tu caso, seleccionaria MovIA Captura si solo quieres responder precios y dudas por WhatsApp.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | ready_to_start |
| `macro_action` | direct_close |
| `micro_action` | send_app_link |
| `objection_type` |  |
| `objection_flow_step` |  |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | send_app_link |
| `expected_sources` | postgres.official_links, json.platform_steps, memory.lead_profile |

### Turn 12

**User message**

> Si lo pruebo y me arrepiento del deposito?

**Ideal assistant response**

> Antes de que avances, es importante que quede claro: el deposito del 50% no es reembolsable. Ese pago inicia el trabajo personalizado. Lo que si tienes es revision del agente y posibilidad de pedir ajustes antes del pago final.

**Expected trace**

| Field | Expected value |
|---|---|
| `current_stage` | objection_handling |
| `macro_action` | handle_objection |
| `micro_action` | refund_policy_clear_then_risk_reversal |
| `objection_type` | price_objection |
| `objection_flow_step` | clarify_value |
| `rag_used` | False |
| `structured_used` | True |
| `json_used` | True |
| `final_cta_type` | soft_question |
| `expected_sources` | postgres.policies, json.objection_playbook |

---

# How Codex should use this file

1. Treat this Markdown as the human-readable validation plan.
2. Treat `movia_difficult_lead_validation_scenarios.json` as the machine-readable dataset.
3. Run each scenario turn by turn against the actual LangGraph agent.
4. Persist the debug trace for every turn.
5. Compare the actual trace against the expected trace in this file/JSON.
6. If the final answer is wrong, identify which layer failed: `analyze_turn`, `sales_policy_planner`, `knowledge_planner`, retrieval, memory, or `generate_response`.
7. Do not evaluate only the final natural-language answer; evaluate routing, memory, sources, and policy compliance.