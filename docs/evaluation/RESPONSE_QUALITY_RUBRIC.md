# Response Quality Rubric V3

Date: 2026-06-05

## Purpose

Response quality measures whether the visible WhatsApp answer is useful, natural, persuasive and well directed.

It is separate from:

- trace agreement;
- source routing;
- hard commercial-policy rules;
- sales-stage correctness.

## Scoring

Each dimension is scored from 1 to 5.

| Score | Meaning |
|---:|---|
| 5 | Strong, clear and appropriate. |
| 4 | Good with minor limitations. |
| 3 | Acceptable but noticeably weak. |
| 2 | Poor; likely hurts the interaction. |
| 1 | Fails the dimension. |

The normalized overall quality score is the average dimension score divided by 5, capped downward when critical defects are present.

## Dimensions

### Directness

The answer responds to the user's actual question before adding context.

### Relevance

The answer avoids unrelated explanations and stays focused on the current commercial need.

### Factuality

The answer uses only official MovIA facts for prices, policies, links, channel availability and product scope.

### Personalization

The answer uses known lead context when useful, such as business type, channel, pain, action requirement or product fit.

### Persuasiveness

The answer explains value without pressure, exaggeration or invented proof.

### Naturalness

The answer sounds appropriate for WhatsApp: concise, conversational and easy to scan.

### Non-Repetition

The answer avoids repeating itself or asking again for known information.

### Next-Step Quality

The final question or CTA matches the selected commercial action and is the best logical next move.

### Conciseness

The answer is complete enough without unnecessary length.

### Tone

The answer is calm, consultative and non-defensive.

## Critical Defects

Critical defects are flagged separately:

- `did_not_answer_question`
- `asked_known_information`
- `unsupported_claim`
- `overpromised_scope`
- `premature_close`
- `irrelevant_context`
- `repetitive_question`
- `unnatural_or_defensive_tone`
- `poor_next_step`

Known-slot repetition is always visible through `asked_known_information`.

## Judge Input

The response-quality judge receives:

- user message;
- recent context;
- known lead facts;
- official facts used;
- selected commercial action;
- visible response;
- this rubric.

It must not receive or return hidden reasoning.

## Judge Output

The canonical output is:

- dimension scores with short evidence;
- critical defect flags;
- overall response quality;
- short summary.

Runtime agent execution does not call this judge. It is evaluation-only.
