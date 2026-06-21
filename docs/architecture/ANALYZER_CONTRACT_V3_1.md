# Analyzer Contract V3.1

Version: `3.1`

## Boundary

Analyzer Contract V3.1 keeps the analyzer focused on independent observations from the current user message.

The analyzer may observe:

- primary and secondary intent;
- explicit lead facts;
- `observed_business_problems`;
- `requested_agent_capabilities` for the future purchased agent only;
- `requested_agent_actions` for future external actions only;
- `declared_external_action_count` when the count is literally stated;
- explicitly requested product;
- objection candidate;
- purchase readiness;
- prior-conversation reference;
- post-purchase signal;
- literal evidence spans and confidence.

The analyzer must not decide:

- `action_requirement`;
- `known_product_fit`;
- `recommended_product`;
- sales stage;
- macro action;
- micro action;
- CTA;
- next question;
- RAG routing;
- closing permission.

## Semantic Split

V3.1 makes a three-way distinction:

- `observed_business_problems`: pain or operational friction happening now.
- `requested_agent_capabilities`: what the lead wants the future purchased agent to be able to do later.
- `requested_agent_actions`: what the lead wants that future agent to do in external workflows or systems.

Current questions to the MovIA salesperson do not count as future-agent capabilities or actions.

Examples:

- “La gente pregunta precio y luego desaparece” → business problem, not `provide_prices`.
- “Quiero que el agente dé precios automáticamente” → future-agent capability.
- “Agendamos manualmente” → business problem, not `schedule_appointment`.
- “Necesito que el agente agende citas” → future-agent action.

## Evidence Rules

Every semantic observation in V3.1 must be grounded in a literal span from the current message.

Runtime sanitization is field-local:

- invalid evidence is repaired when a smaller literal cue is available;
- otherwise that field is dropped;
- the rest of the analyzer payload remains usable;
- sanitization warnings remain visible in trace metadata.

Full-message evidence should not be retained when a smaller literal span is available.

## Compatibility Note

The current runtime still consumes legacy planner-compatible fields in downstream paths.

During Phase 1, any temporary compatibility adapter must be one-way:

- derived only from V3.1 semantics;
- business problems must never create `answers_only`;
- only explicit future-agent capabilities and actions may feed compatibility aliases;
- legacy and V3.1 semantics must not compete as peer inputs.

## Source Of Truth

Runtime source:

```text
src/movia_sales_agent/analyzer/contract_v3.py
```

Machine-readable summary:

```text
docs/architecture/ANALYZER_CONTRACT_V3_1.json
```
