# MovIA Validation Package - Difficult Lead Scenarios

Este paquete contiene 5 conversaciones de validación para el agente vendedor de MovIA. Cada conversación tiene 12 turnos de usuario, respuesta ideal, expected state, macro_action, micro_action, fuentes esperadas y criterios de evaluación.

## Recomendación de longitud

Usar 12 turnos de usuario por escenario. Es suficiente para probar discovery, objeciones, memoria, consistencia, comparación, cierre y límites de alcance.

## Archivos

- `movia_difficult_lead_validation_scenarios.json`: dataset completo.
- `movia_validation_plan.pdf`: guía ejecutiva y metodología.

## Uso sugerido

1. Correr cada escenario turno por turno contra el agente real.
2. Guardar `debug_trace` por turno.
3. Comparar macro_action/micro_action/fuentes contra el JSON.
4. Usar RAGAS para RAG/multi-turn/aspect criteria y agregar métricas custom para ventas/políticas.
