# Parser Shadow Comparison

- **Run:** analyzer-v3-targeted-20260616T014111Z-d07702
- **Analyzer contract:** 3.1

| Category | Parser true positives | Parser false positives | Parser false negatives | Conflicts |
|---|---:|---:|---:|---:|
| actions | 0 | 0 | 0 | 0 |
| products | 5 | 3 | 4 | 7 |
| purchase_cues | 1 | 0 | 0 | 0 |
| prior_references | 2 | 1 | 10 | 10 |
| channels | 0 | 7 | 20 | 20 |

## LLM-Only Correct Detections

- `products` MOVIA-COH-004 turn 5: ['unknown_product']
- `products` MOVIA-COH-004 turn 7: ['unknown_product']
- `products` MOVIA-MEM-002 turn 5: ['unknown_product']
- `prior_references` MOVIA-COH-001 turn 3: ['topic_reference']
- `prior_references` MOVIA-COH-001 turn 4: ['topic_reference']
- `prior_references` MOVIA-COH-001 turn 5: ['topic_reference']
- `channels` MOVIA-COH-001 turn 1: ['WhatsApp']
- `channels` MOVIA-COH-001 turn 2: ['WhatsApps de anuncios']
- `channels` MOVIA-COH-001 turn 3: ['WhatsApp']

## Patterns That May Later Become Deterministic Rules

- High-agreement requested external actions such as quote/register/write-system.
- High-agreement channel mentions for WhatsApp/Facebook/Instagram availability checks.
- High-agreement explicit-start cues that contain link/start/pay language.

## Patterns That Must Remain Semantic

- Soft sarcasm versus persistent hard objection.
- Prior references that depend on an assistant commitment.
- Scope reduction after a custom/handoff branch.
