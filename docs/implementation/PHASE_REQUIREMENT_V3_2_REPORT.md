# Phase Requirement Semantics V3.2 Report

Date: `2026-06-10`

Status: Phase 2 complete.

## Scope Completed

Phase 2 only:

- added a deterministic requirement-profile service;
- persisted requirement state under `profile_data.requirement_profile`;
- introduced current-turn requirement deltas with merge/no-update handling;
- derived `requirement_class`, compatibility `action_requirement`, deterministic product fit, and scope flags from the persisted profile;
- integrated planner gating for direct close, custom scope, unavailable products, and persisted requirement fit;
- updated response-package context with compact requirement summary and scope metadata;
- tightened the offline heuristic path so future-agent requirements need future-agent wording;
- added/update Phase 2 tests.

No migrations were added or applied.
No Atomic, Coherent, targeted live, or Adaptive Hybrid runs were executed.

## Files Changed

- `src/movia_sales_agent/agent/requirements.py`
- `src/movia_sales_agent/agent/memory.py`
- `src/movia_sales_agent/agent/planners.py`
- `src/movia_sales_agent/agent/graph.py`
- `src/movia_sales_agent/agent/response.py`
- `src/movia_sales_agent/services/openai_service.py`
- `tests/test_requirement_profile_v3.py`
- `tests/test_memory_v3.py`
- `tests/test_agent_policy.py`
- `tests/test_response_context.py`
- `docs/architecture/REQUIREMENT_PROFILE_V3_1.md`
- `PLAN_REQUIREMENT_SEMANTICS_V3_1.md`

## Behavioral Decisions Locked In

- Missing new requirements no longer erase persisted requirements.
- Business problems stay separate from requirement class.
- More than two active external actions moves fit to `custom_review`.
- Sales capabilities never derive Captura.
- Direct close now requires confirmed or selected compatible product state, not just explicit-start language.
- Legacy `action_requirement` and `known_product_fit` remain derived compatibility outputs only.

## Tests Run

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_requirement_profile_v3.py tests/test_memory_v3.py tests/test_agent_policy.py tests/test_response_context.py -q
```

Result:

- `44 passed`
- `1 warning` from `urllib3` / LibreSSL in the local environment

## Unresolved Issues

- `confirmed_product` still depends on persisted profile state or explicit selected-product compatibility; later phases may want a stronger deterministic confirmation transition.
- The evaluator and replay tooling have not yet been updated to score the new persisted requirement-profile outputs end to end.
- Existing compatibility aliases are still present in planner/memory/response payloads and should remain until Phase 3 regression work confirms they are safe to narrow further.

## Exact Next Task

Phase 3 only:

- align offline regression coverage and evaluator contracts with the persisted requirement profile;
- run offline regression and smoke-level compatibility checks only;
- prepare the live-smoke boundary without running the full Atomic or Coherent replay.
