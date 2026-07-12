from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.interaction_context import build_analyzer_interaction_context
from movia_sales_agent.agent.reply_frame import (
    REPLY_FRAME_ACTION_REQUIREMENT,
    REPLY_FRAME_LINK_START_CONFIRMATION,
    REPLY_FRAME_PLANNER_CONTEXT,
    resolve_reply_frame_with_usage,
)
from movia_sales_agent.agent.requirements import resolve_requirement_delta_with_usage
from movia_sales_agent.analyzer.contract_v3 import AnalyzerTurnObservation
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.services.openai_service import OpenAIService


DEFAULT_PRODUCTION_CONTRACT_DATASET = (
    PROJECT_ROOT
    / "movia_validation_package"
    / "movia_production_contract_regression_v1.json"
)
DEFAULT_PRODUCTION_CONTRACT_OUTPUT = (
    PROJECT_ROOT / "artifacts" / "evaluations" / "production-contract-v3-2"
)


def run_production_contract_regression(
    *,
    dataset_path: Path = DEFAULT_PRODUCTION_CONTRACT_DATASET,
    output_root: Path = DEFAULT_PRODUCTION_CONTRACT_OUTPUT,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    run_settings = _no_write_settings(settings or get_settings())
    run_id = _run_id()
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []

    for case in dataset.get("cases") or []:
        records.extend(_run_case(case, run_settings))

    failures = [failure for record in records for failure in record.get("failures") or []]
    fallbacks = [record for record in records if _record_has_fallback(record)]
    result = {
        "run_id": run_id,
        "dataset": str(dataset_path),
        "dataset_version": dataset.get("dataset_version"),
        "analyzer_contract_version": dataset.get("target_analyzer_contract_version"),
        "analysis_model": run_settings.analysis_model,
        "no_write_mode": True,
        "passed": not failures and not fallbacks,
        "case_count": len(dataset.get("cases") or []),
        "record_count": len(records),
        "failure_count": len(failures),
        "fallback_count": len(fallbacks),
        "failures": failures,
        "records": records,
        "baseline_failures": dataset.get("baseline_failures") or [],
    }
    (output_dir / "run.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(_summary(result), encoding="utf-8")
    return {**result, "output_dir": str(output_dir)}


def _run_case(case: Dict[str, Any], settings: Settings) -> List[Dict[str, Any]]:
    case_type = str(case.get("case_type") or "analyzer_turn")
    repeat = max(1, int(case.get("repeat") or 1))
    recent_messages = _recent_messages(case.get("recent_messages") or [])
    lead_profile = _lead_profile(case.get("initial_profile") or {})
    interaction_context = build_analyzer_interaction_context(
        lead_profile=lead_profile,
        recent_messages=recent_messages,
    )
    service = OpenAIService(settings)
    records: List[Dict[str, Any]] = []

    for repetition in range(1, repeat + 1):
        _analysis, usage, observation = service.analyze_turn_v3_with_usage(
            str(case.get("current_message") or ""),
            recent_messages,
            interaction_context=interaction_context,
        )
        reply_resolution = None
        reply_usage: Dict[str, Any] = {}
        frame = (interaction_context.get("previous_planner") or {}).copy()
        if frame and not frame.get("type"):
            frame["type"] = _frame_type(frame)
        if frame:
            reply_resolution, reply_usage = resolve_reply_frame_with_usage(
                service,
                frame=frame,
                message=str(case.get("current_message") or ""),
                observation=observation,
            )
        delta_resolution = None
        delta_usage: Dict[str, Any] = {}
        if case_type == "requirement_delta":
            delta_resolution, delta_usage = resolve_requirement_delta_with_usage(
                service,
                message=str(case.get("current_message") or ""),
                existing_profile=(lead_profile.get("profile_data") or {}).get(
                    "requirement_profile"
                )
                or {},
                analyzer_observation=observation.model_dump(),
                candidate_hint=True,
            )
        failures = _check_raw(
            case,
            observation,
            reply_resolution.model_dump() if reply_resolution else {},
            delta_resolution.model_dump() if delta_resolution else {},
        )
        records.append(
            {
                "case_id": case.get("id"),
                "mode": "raw",
                "repetition": repetition,
                "observation": observation.model_dump(),
                "reply_resolution": reply_resolution.model_dump()
                if reply_resolution
                else {},
                "requirement_delta_resolution": delta_resolution.model_dump()
                if delta_resolution
                else {},
                "failures": failures,
                "usage_calls": [
                    call
                    for call in [usage, reply_usage, delta_usage]
                    if call
                ],
            }
        )

    if _requires_stateful_replay(case):
        records.append(_run_stateful_case(case, settings, recent_messages, lead_profile))
    return records


def _run_stateful_case(
    case: Dict[str, Any],
    settings: Settings,
    recent_messages: List[Dict[str, Any]],
    lead_profile: Dict[str, Any],
) -> Dict[str, Any]:
    agent = MoviaSalesAgent(settings)
    external_id = f"contract-v3-2:{case.get('id')}"
    channel = "evaluation"
    lead = agent.repository.upsert_lead(channel, external_id)
    lead_id = str(lead.get("id") or "")
    agent.repository.update_lead_profile(
        lead_id,
        {
            key: value
            for key, value in lead_profile.items()
            if key in {"business_type", "main_channel", "pain", "urgency", "buying_signal", "profile_data"}
        },
        current_stage=lead_profile.get("current_stage"),
        active_objection=lead_profile.get("active_objection"),
        last_action=lead_profile.get("last_action"),
    )
    memory_key = f"{channel}:{external_id}"
    for message in recent_messages:
        agent.memory.add_recent(memory_key, message)

    response = agent.invoke(
        str(case.get("current_message") or ""),
        lead_external_id=external_id,
        channel=channel,
    )
    normalized = dict(response.response_metadata.get("normalized_turn") or {})
    failures = _check_stateful(case, response, normalized)
    return {
        "case_id": case.get("id"),
        "mode": "stateful",
        "repetition": 1,
        "observation": response.response_metadata.get("analyzer_observation") or {},
        "normalized_turn": normalized,
        "selected_action": response.selected_action,
        "knowledge_plan": response.knowledge_plan,
        "lead_state": response.lead_state,
        "response": response.response,
        "failures": failures,
        "usage_calls": list((response.token_usage or {}).get("calls") or []),
    }


def _check_raw(
    case: Dict[str, Any],
    observation: AnalyzerTurnObservation,
    reply_resolution: Dict[str, Any],
    delta_resolution: Dict[str, Any],
) -> List[Dict[str, Any]]:
    expected = dict(case.get("expected") or {})
    actual = observation.model_dump()
    failures: List[Dict[str, Any]] = []
    _expect_equal(failures, case, "primary_intent", actual.get("primary_intent"), expected)
    _expect_set(failures, case, "secondary_intents", actual.get("secondary_intents"), expected)
    _expect_set(
        failures,
        case,
        "requested_agent_actions",
        [item.get("type") for item in actual.get("requested_agent_actions") or []],
        expected,
    )
    _expect_set(
        failures,
        case,
        "requested_agent_capabilities",
        [item.get("type") for item in actual.get("requested_agent_capabilities") or []],
        expected,
    )
    if str(case.get("case_type") or "") != "requirement_delta":
        _expect_equal(
            failures,
            case,
            "requirement_update_intent",
            actual.get("requirement_update_intent"),
            expected,
        )
    _expect_equal(
        failures,
        case,
        "purchase_readiness",
        (actual.get("purchase_readiness") or {}).get("level"),
        expected,
    )
    if "explicit_start_intent" in expected:
        analyzer_start = (
            (actual.get("purchase_readiness") or {}).get("level") == "explicit_start"
        )
        frame_start = reply_resolution.get("reply_act") == "accept" and _frame_type(
            ((case.get("recent_messages") or [{}])[-1].get("planner_context") or {})
        ) == REPLY_FRAME_LINK_START_CONFIRMATION
        _expect_equal(
            failures,
            case,
            "explicit_start_intent",
            analyzer_start or frame_start,
            expected,
        )
    _expect_equal(
        failures,
        case,
        "objection_candidate",
        (actual.get("objection_candidate") or {}).get("type"),
        expected,
    )
    _expect_equal(
        failures,
        case,
        "active_objection_relation",
        (actual.get("active_objection_relation") or {}).get("relation"),
        expected,
    )
    _expect_product_references(failures, case, actual.get("product_references"), expected)
    _expect_equal(failures, case, "reply_act", reply_resolution.get("reply_act"), expected)
    if delta_resolution:
        _expect_equal(
            failures,
            case,
            "requirement_update_intent",
            delta_resolution.get("operation"),
            expected,
        )
    return failures


def _check_stateful(
    case: Dict[str, Any], response: Any, normalized: Dict[str, Any]
) -> List[Dict[str, Any]]:
    expected = dict(case.get("expected") or {})
    failures: List[Dict[str, Any]] = []
    profile_data = dict((response.lead_state or {}).get("profile_data") or {})
    requirement_profile = dict(profile_data.get("requirement_profile") or {})
    product_context = dict(profile_data.get("product_context") or {})
    reply_resolution = dict(normalized.get("reply_frame_resolution") or {})
    active_objection = dict((response.lead_state or {}).get("active_objection") or {})

    actuals = {
        "reply_act": reply_resolution.get("reply_act"),
        "action_requirement": normalized.get("action_requirement")
        or profile_data.get("action_requirement"),
        "requirement_class": requirement_profile.get("requirement_class"),
        "recommended_product": normalized.get("recommended_product")
        or profile_data.get("known_product_fit"),
        "selected_product": product_context.get("selected_product")
        or profile_data.get("selected_product"),
        "confirmed_product": product_context.get("confirmed_product")
        or profile_data.get("confirmed_product"),
        "active_product_context": product_context.get("active_product_context"),
        "explicit_start_intent": normalized.get("explicit_start_intent"),
        "primary_intent": response.analysis.primary_intent,
        "active_objection_after": active_objection.get("type")
        if active_objection.get("active")
        else "none",
    }
    for field in actuals:
        _expect_equal(failures, case, field, actuals[field], expected)

    for field in ("requested_agent_actions", "requested_agent_capabilities"):
        _expect_set(failures, case, field, normalized.get(field), expected)
    _expect_product_references(failures, case, normalized.get("product_references"), expected)

    active_actions = [
        item.get("type")
        for item in requirement_profile.get("external_actions") or []
        if item.get("active", True)
    ]
    inactive_actions = [
        item.get("type")
        for item in requirement_profile.get("external_actions") or []
        if not item.get("active", True)
    ]
    _expect_set(failures, case, "active_external_actions", active_actions, expected)
    _expect_set(failures, case, "inactive_external_actions", inactive_actions, expected)
    active_capabilities = [
        item.get("type")
        for item in requirement_profile.get("informational_capabilities") or []
        if item.get("active", True)
    ]
    _expect_set(
        failures,
        case,
        "active_informational_capabilities",
        active_capabilities,
        expected,
    )

    if response.selected_action.get("next_question_key") in set(
        expected.get("forbidden_next_question_keys") or []
    ):
        failures.append(
            _failure(
                case,
                "forbidden_next_question_key",
                response.selected_action.get("next_question_key"),
                expected.get("forbidden_next_question_keys"),
            )
        )
    if response.action in set(expected.get("forbidden_macro_actions") or []):
        failures.append(
            _failure(
                case,
                "forbidden_macro_action",
                response.action,
                expected.get("forbidden_macro_actions"),
            )
        )
    required_needs = set(expected.get("required_knowledge_needs") or [])
    if required_needs and not required_needs.issubset(
        set(response.knowledge_plan.get("knowledge_needs") or [])
    ):
        failures.append(
            _failure(
                case,
                "required_knowledge_needs",
                response.knowledge_plan.get("knowledge_needs") or [],
                sorted(required_needs),
            )
        )
    required_product_contexts = set(expected.get("required_product_contexts") or [])
    if required_product_contexts:
        actual_products = {
            str(item.get("product"))
            for item in normalized.get("product_references") or []
            if isinstance(item, dict) and item.get("product")
        }
        has_official_products = "postgres.products" in set(
            response.knowledge_plan.get("structured_sources") or []
        )
        if not required_product_contexts.issubset(actual_products) or not has_official_products:
            failures.append(
                _failure(
                    case,
                    "required_product_contexts",
                    {
                        "products": sorted(actual_products),
                        "official_products_loaded": has_official_products,
                    },
                    sorted(required_product_contexts),
                )
            )
    normalized_response = str(response.response or "").lower().replace(",", "")
    missing_facts = [
        fact
        for fact in expected.get("required_response_facts") or []
        if str(fact).lower().replace(",", "") not in normalized_response
    ]
    if missing_facts:
        failures.append(_failure(case, "required_response_facts", missing_facts, []))
    return failures


def _recent_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for message in messages:
        item = {"role": message.get("role"), "content": message.get("content")}
        planner_context = message.get("planner_context")
        if isinstance(planner_context, dict):
            frame = {**planner_context, "type": _frame_type(planner_context)}
            item["analysis"] = {"reply_frame": frame}
        result.append(item)
    return result


def _frame_type(frame: Dict[str, Any]) -> str:
    if frame.get("next_question_key") == "action_requirement" or frame.get(
        "micro_action"
    ) == "ask_action_requirement":
        return REPLY_FRAME_ACTION_REQUIREMENT
    if frame.get("next_question_key") == "link_start_confirmation" or frame.get(
        "cta_type"
    ) == "ask_permission_to_send_link":
        return REPLY_FRAME_LINK_START_CONFIRMATION
    return REPLY_FRAME_PLANNER_CONTEXT


def _requires_stateful_replay(case: Dict[str, Any]) -> bool:
    if str(case.get("case_type") or "") in {
        "stateful_turn",
        "planner_turn",
        "requirement_delta",
    }:
        return True
    state_fields = {
        "active_objection_after",
        "selected_product",
        "confirmed_product",
        "active_product_context",
        "required_product_contexts",
        "required_knowledge_needs",
        "required_response_facts",
        "active_external_actions",
        "inactive_external_actions",
        "active_informational_capabilities",
        "forbidden_macro_actions",
        "forbidden_next_question_keys",
    }
    return bool(state_fields & set((case.get("expected") or {}).keys()))


def _lead_profile(initial: Dict[str, Any]) -> Dict[str, Any]:
    profile = {
        "current_stage": initial.get("current_stage") or "new",
        "business_type": initial.get("business_type"),
        "main_channel": initial.get("main_channel"),
        "pain": initial.get("pain_or_goal") or initial.get("pain"),
        "active_objection": initial.get("active_objection") or {},
        "profile_data": {},
    }
    profile_data = {
        key: value
        for key, value in initial.items()
        if key
        not in {
            "current_stage",
            "business_type",
            "main_channel",
            "pain_or_goal",
            "pain",
            "active_objection",
        }
    }
    if profile_data.get("selected_product") or profile_data.get("confirmed_product"):
        profile_data["product_context"] = {
            **dict(profile_data.get("product_context") or {}),
            "selected_product": profile_data.get("selected_product"),
            "confirmed_product": profile_data.get("confirmed_product"),
            "active_product_context": profile_data.get("confirmed_product")
            or profile_data.get("selected_product"),
        }
    profile["profile_data"] = profile_data
    return profile


def _expect_equal(
    failures: List[Dict[str, Any]],
    case: Dict[str, Any],
    field: str,
    actual: Any,
    expected: Dict[str, Any],
) -> None:
    if field in expected and actual != expected[field]:
        failures.append(_failure(case, field, actual, expected[field]))


def _expect_set(
    failures: List[Dict[str, Any]],
    case: Dict[str, Any],
    field: str,
    actual: Any,
    expected: Dict[str, Any],
) -> None:
    if field not in expected:
        return
    if set(actual or []) != set(expected[field] or []):
        failures.append(_failure(case, field, actual or [], expected[field] or []))


def _expect_product_references(
    failures: List[Dict[str, Any]],
    case: Dict[str, Any],
    actual: Any,
    expected: Dict[str, Any],
) -> None:
    if "product_references" not in expected:
        return
    compact_actual = {
        (item.get("product"), item.get("reference_role"))
        for item in actual or []
        if isinstance(item, dict)
    }
    compact_expected = {
        (item.get("product"), item.get("reference_role"))
        for item in expected.get("product_references") or []
    }
    if compact_actual != compact_expected:
        failures.append(
            _failure(
                case,
                "product_references",
                sorted(compact_actual),
                sorted(compact_expected),
            )
        )


def _failure(case: Dict[str, Any], field: str, actual: Any, expected: Any) -> Dict[str, Any]:
    return {
        "case_id": case.get("id"),
        "field": field,
        "actual": actual,
        "expected": expected,
    }


def _no_write_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "database_url": None,
            "disable_database": True,
            "disable_openai": False,
            "redis_url": None,
            "debug_metadata": True,
            "followup_enabled": False,
            "platform_observability_enabled": False,
            "platform_registry_sync_on_startup": False,
            "meta_whatsapp_access_token": None,
            "meta_whatsapp_phone_number_id": None,
            "meta_capi_dataset_id": None,
            "chatwoot_url": None,
            "chatwoot_api_token": None,
            "chatwoot_account_id": None,
        }
    )


def _run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"production-contract-v3-2-{stamp}-{uuid4().hex[:6]}"


def _summary(result: Dict[str, Any]) -> str:
    status = "PASS" if result.get("passed") else "FAIL"
    lines = [
        f"# Production Contract V3.2 Regression: {result['run_id']}",
        "",
        f"- **Status:** {status}",
        f"- **Dataset:** `{result.get('dataset_version')}`",
        f"- **Analyzer contract:** `{result.get('analyzer_contract_version')}`",
        f"- **Model:** `{result.get('analysis_model')}`",
        f"- **Cases:** {result.get('case_count')}",
        f"- **Records:** {result.get('record_count')}",
        f"- **Failures:** {result.get('failure_count')}",
        f"- **Fallbacks:** {result.get('fallback_count')}",
        "- **Production writes:** disabled",
    ]
    if result.get("failures"):
        lines.extend(["", "## Failures", ""])
        for failure in result["failures"]:
            lines.append(
                f"- `{failure['case_id']}` `{failure['field']}`: actual={failure['actual']!r}, expected={failure['expected']!r}"
            )
    return "\n".join(lines) + "\n"


def _record_has_fallback(record: Dict[str, Any]) -> bool:
    for call in record.get("usage_calls") or []:
        nested = call.get("calls") if isinstance(call, dict) else None
        candidates = nested if isinstance(nested, list) else [call]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("provider") == "fallback" or candidate.get("error"):
                return True
    return False
