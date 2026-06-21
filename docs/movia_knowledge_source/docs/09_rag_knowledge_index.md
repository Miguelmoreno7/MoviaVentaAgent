# 09 - Índice de conocimiento RAG

Este documento define qué contenido debe convertirse en documentos RAG y qué contenido debe permanecer fuera de RAG.

## Qué SÍ va en RAG

El RAG debe contener información explicativa, contextual y persuasiva.

Ejemplos:

- Qué es MovIA.
- Qué es un agente de IA para WhatsApp.
- Beneficios de automatizar atención.
- Casos de uso por industria.
- Comparaciones contra ManyChat.
- Comparaciones contra chatbot básico.
- Comparaciones contra humanos/recepcionistas.
- Preguntas frecuentes abiertas.
- Cuándo elegir Captura vs Híbrido.
- Ejemplos de conversaciones.
- Beneficios de responder rápido.
- Cómo preparar documentos para el agente.

## Qué NO va en RAG

No debe depender de RAG:

- Precios.
- Tiempos de entrega.
- Links oficiales.
- Políticas de pago.
- Estados del proyecto.
- Features exactos.
- Qué incluye o no incluye cada paquete.
- Pasos exactos de plataforma.
- Reglas de objeción.
- Acciones comerciales permitidas.

Eso debe ir en Postgres o JSON.

## Metadata recomendada para chunks

Cada chunk debe tener metadata:

```json
{
  "topic": "use_case",
  "industry": "dental",
  "channel": "whatsapp",
  "funnel_stage": "pre_purchase",
  "source_type": "rag",
  "approved": true,
  "version": "v1",
  "last_updated": "2026-06-02"
}
```

## Documentos RAG iniciales

- rag_docs/overview/movia_overview.md
- rag_docs/use_cases/dental.md
- rag_docs/use_cases/real_estate.md
- rag_docs/use_cases/restaurants.md
- rag_docs/use_cases/general_services.md
- rag_docs/comparisons/manychat.md
- rag_docs/comparisons/basic_chatbot.md
- rag_docs/comparisons/human_receptionist.md
- rag_docs/faqs/pre_purchase_faq.md
- rag_docs/product_explanations/whatsapp_agent.md
- rag_docs/product_explanations/instagram_agent.md
- rag_docs/product_explanations/facebook_agent.md
- rag_docs/product_explanations/multichannel_agent.md
