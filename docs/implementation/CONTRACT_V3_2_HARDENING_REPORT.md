# MovIA Contract 3.2 Hardening Report

## Scope

Analyzer Contract 3.2 is implemented. Commercial Contract 2.0, the analyzer and
response models (`gpt-4.1-mini`), the 17 intent values, planner action enums,
and persisted database schema remain unchanged.

The implementation adds:

- ephemeral analyzer interaction context from existing planner and lead state;
- contextual reply-act resolution for planner-authored questions and CTAs;
- semantic requirement deltas for merge, replace, correction, and removal;
- independent active-objection relation observations;
- multiple product references with mention, question, comparison, preference,
  and commitment roles;
- one-way compatibility aliases for legacy runtime consumers;
- ontology and literal-evidence validation with field-local sanitization;
- deterministic contradiction handling when an `unrelated` or `resolved`
  relation duplicates the active objection as a new candidate;
- compact analyzer history, interaction context, and schema representation to
  keep the Atomic token budget within its acceptance threshold.

The legacy regex contextual resolver remains available for audit but no longer
mutates runtime state. No migration or production write was performed.

## Validation Data

The production-derived regression set is stored at:

- `movia_validation_package/movia_production_contract_regression_v1.json`

The bounded post-implementation vulnerability audit is stored at:

- `movia_validation_package/movia_contract_v3_2_vulnerability_audit.json`

One expectation was corrected before the final acceptance runs: the literal
text `Ya elegi Captura` represents a committed reference, not a mere mention.
The associated state assertion still requires a later Hibrido question to leave
Captura selected and confirmed.

## Final Gates

### Offline suite

- Result: `308 passed`
- Warning: one existing LangGraph pending-deprecation warning

### Production-derived contract regression

- Artifact: `artifacts/evaluations/production-contract-v3-2-final-acceptance/production-contract-v3-2-20260712T161059Z-672afd/`
- Cases: 22
- Records: 116
- Failures: 0
- Fallbacks: 0
- Provider errors: 0

### Vulnerability audit

- Artifact: `artifacts/evaluations/contract-v3-2-vulnerability-audit-acceptance/production-contract-v3-2-20260712T162212Z-722d56/`
- Cases: 17
- Records: 32
- Failures: 0
- Fallbacks: 0
- Provider errors: 0

### Atomic replay

- Artifact: `artifacts/evaluations/contract-v3-2-atomic-acceptance/movia-eval-20260712T162555Z-86a00d/`
- Turns: 60
- Primary applicable score: 0.9612
- Hard failures: 0
- Commercial accuracy: 1.0
- Policy compliance: 1.0
- Provider errors: 0
- Fallbacks: 0
- Total agent tokens: 331,365
- Average agent tokens per turn: 5,522.75
- Token gate: pass (`<= 5,600`)

The first behavior-clean V3.2 Atomic attempt averaged 5,995.90 tokens per turn.
Removing non-semantic schema titles and compacting duplicate prompt/context
content reduced the final average by 473.15 tokens per turn without changing
the accepted contract behavior.

## Outcome

All Contract 3.2 acceptance gates pass. Conversations derived from Chatwoot
84, 85, 86, and 89 no longer reopen answered discovery in the frozen
regression, active objections can be related independently from new objection
candidates, and cross-product questions no longer overwrite product
commitment state.
