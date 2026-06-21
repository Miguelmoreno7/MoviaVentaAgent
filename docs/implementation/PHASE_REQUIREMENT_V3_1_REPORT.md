# Phase Requirement Semantics V3.1 Report

Date: `2026-06-10`

Status: Phase 1 complete.

## Scope Completed

Phase 1 only:

- adjusted `MOVIA_3_1.md` with the agreed defaults and pinned baselines;
- bumped analyzer contract runtime from `3.0` to `3.1`;
- added `observed_business_problems`;
- made future-agent semantics explicit with `requested_agent_capabilities` and `requested_agent_actions`;
- added `declared_external_action_count`;
- updated analyzer prompt, sanitizer behavior, shadow telemetry, normalizer bridge, and response trace output;
- generated V3.1 contract docs and JSON;
- updated offline tests to the new boundary.

No Phase 2 work was started.
No DB migration was added or applied.
No live evaluation was run.

## Files Changed

- `MOVIA_3_1.md`
- `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`
- `src/movia_sales_agent/analyzer/contract_v3.py`
- `src/movia_sales_agent/analyzer/normalizer.py`
- `src/movia_sales_agent/analyzer/shadow_parser.py`
- `src/movia_sales_agent/services/openai_service.py`
- `src/movia_sales_agent/agent/response.py`
- `tests/test_analyzer_contract_v3.py`
- `tests/test_analyzer_normalization_v3.py`
- `tests/test_agent_policy.py`
- `docs/architecture/ANALYZER_CONTRACT_V3_1.md`
- `docs/architecture/ANALYZER_CONTRACT_V3_1.json`

## Behavioral Decisions Locked In

- Business pain is tracked separately from future-agent requirements.
- Current salesperson questions do not become future-agent capabilities or actions.
- Only explicit future-agent capabilities and actions feed the temporary compatibility bridge.
- Business problems never create `answers_only`.
- Invalid evidence is repaired or dropped field-locally instead of forcing full analyzer fallback.

## Tests Run

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_analyzer_contract_v3.py tests/test_analyzer_normalization_v3.py tests/test_agent_policy.py -q
```

Result:

- `69 passed`
- `1 warning` from `urllib3` / LibreSSL in the local environment

## Unresolved Issues

- Downstream planner and memory still consume compatibility aliases rather than a persisted V3.1 requirement profile.
- Supplier/workflow pain without explicit future-agent wording now stays in discovery. If later phases want deterministic product-fit inference from pain-only evidence, that should be added deliberately outside the analyzer semantic contract.

## Exact Next Task

Phase 2 only:

- persist `requirement_profile` under `movia_lead_profiles.profile_data.requirement_profile`;
- adapt planner-facing state to read that persisted structure deterministically;
- keep the one-way V3.1-to-legacy compatibility bridge until Phase 2 is complete.
