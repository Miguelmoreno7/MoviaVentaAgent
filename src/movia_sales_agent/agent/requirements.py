from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from movia_sales_agent.analyzer.contract_v3 import (
    INFORMATIONAL_AGENT_CAPABILITIES,
    SALES_AGENT_CAPABILITIES,
    RequirementUpdateIntent,
    RequestedAgentAction,
)
from movia_sales_agent.contracts.commercial import ActionRequirement, ProductFit


REQUIREMENT_PROFILE_VERSION = "1.0"
REQUIREMENT_CLASS_UNKNOWN = "unknown"
REQUIREMENT_CLASS_INFORMATIONAL_ONLY = "informational_only"
REQUIREMENT_CLASS_EXTERNAL_ACTIONS = "external_actions"
REQUIREMENT_CLASS_SALES_PERSUASION = "sales_persuasion"
REQUIREMENT_CLASS_MIXED_ADVANCED = "mixed_advanced"
STANDARD_HIBRIDO_ACTION_LIMIT = 2


def empty_requirement_profile() -> Dict[str, Any]:
    return {
        "requirement_profile_version": REQUIREMENT_PROFILE_VERSION,
        "observed_business_problems": [],
        "informational_capabilities": [],
        "sales_capabilities": [],
        "external_actions": [],
        "declared_external_action_count": None,
        "requirement_class": REQUIREMENT_CLASS_UNKNOWN,
        "first_confirmed_turn": None,
        "last_updated_turn": None,
        "sources": {},
    }


def ensure_requirement_profile(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    profile = dict(profile_data.get("requirement_profile") or {})
    merged = {
        **empty_requirement_profile(),
        **profile,
    }
    for key in [
        "observed_business_problems",
        "informational_capabilities",
        "sales_capabilities",
        "external_actions",
    ]:
        merged[key] = list(merged.get(key) or [])
    declared = merged.get("declared_external_action_count")
    if declared and not isinstance(declared, dict):
        merged["declared_external_action_count"] = None
    merged["requirement_class"] = derive_requirement_class(merged)
    merged["sources"] = _derive_sources(merged)
    return merged


def current_turn_requirement_delta(
    *,
    normalized_turn: Dict[str, Any],
    analyzer_observation: Dict[str, Any],
    message: str,
    existing_profile: Dict[str, Any],
) -> Dict[str, Any]:
    existing_profile = ensure_requirement_profile({"requirement_profile": existing_profile})
    problems = _entries_from_observation(
        analyzer_observation.get("observed_business_problems"),
        normalized_turn.get("observed_business_problems") or [],
        strength_key="observation_strength",
    )
    capabilities = _entries_from_observation(
        analyzer_observation.get("requested_agent_capabilities"),
        normalized_turn.get("requested_agent_capabilities") or [],
        strength_key="requirement_strength",
    )
    actions = _entries_from_observation(
        analyzer_observation.get("requested_agent_actions"),
        normalized_turn.get("requested_agent_actions") or [],
        strength_key="requirement_strength",
    )
    actions = _dedupe_entries(
        [
            *actions,
            *_contextual_action_entries(normalized_turn.get("contextual_requirement_actions")),
        ]
    )
    informational = [
        entry for entry in capabilities if entry["type"] in INFORMATIONAL_AGENT_CAPABILITIES
    ]
    sales = [entry for entry in capabilities if entry["type"] in SALES_AGENT_CAPABILITIES]
    removals = _detect_explicit_removals(existing_profile, message)
    declared_count = _declared_count_payload(
        analyzer_observation.get("declared_external_action_count"),
        normalized_turn.get("declared_external_action_count"),
    )
    has_additions = any([problems, informational, sales, actions, declared_count])
    has_removals = any(removals.values())
    has_scope_narrowing = _has_scope_narrowing_replacement(
        message=message,
        new_entries=[*informational, *sales, *actions],
        existing_profile=existing_profile,
    )
    analyzer_update_intent = str(
        analyzer_observation.get("requirement_update_intent")
        or normalized_turn.get("requirement_update_intent")
        or RequirementUpdateIntent.NO_CHANGE.value
    )
    update_type = "no_update"
    if analyzer_update_intent == RequirementUpdateIntent.REPLACE.value and has_additions:
        update_type = "replace"
    elif has_additions and has_scope_narrowing:
        update_type = "replace"
    elif analyzer_update_intent == RequirementUpdateIntent.MERGE.value and has_additions:
        update_type = "merge"
    elif has_additions and has_removals:
        update_type = "explicit_correction"
    elif has_removals:
        update_type = "explicit_removal"
    elif has_additions:
        update_type = "merge"
    return {
        "update_type": update_type,
        "analyzer_update_intent": analyzer_update_intent,
        "new_observed_problems": problems,
        "new_informational_capabilities": informational,
        "new_sales_capabilities": sales,
        "new_external_actions": actions,
        "removed_informational_capabilities": removals["informational_capabilities"],
        "removed_sales_capabilities": removals["sales_capabilities"],
        "removed_external_actions": removals["external_actions"],
        "declared_external_action_count": declared_count,
    }


def merge_requirement_profile(
    existing_profile: Dict[str, Any],
    delta: Dict[str, Any],
    *,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    profile = ensure_requirement_profile({"requirement_profile": existing_profile})
    effective_turn = turn_number or int(profile.get("last_updated_turn") or 0) + 1
    if delta.get("update_type") == "replace":
        _deactivate_all(profile["informational_capabilities"], effective_turn)
        _deactivate_all(profile["sales_capabilities"], effective_turn)
        _deactivate_all(profile["external_actions"], effective_turn)
        if delta.get("declared_external_action_count") is None and profile.get("declared_external_action_count"):
            profile["declared_external_action_count"]["active"] = False
            profile["declared_external_action_count"]["last_removed_turn"] = effective_turn
    _merge_items(profile["observed_business_problems"], delta.get("new_observed_problems") or [], effective_turn)
    _merge_items(profile["informational_capabilities"], delta.get("new_informational_capabilities") or [], effective_turn)
    _merge_items(profile["sales_capabilities"], delta.get("new_sales_capabilities") or [], effective_turn)
    _merge_items(profile["external_actions"], delta.get("new_external_actions") or [], effective_turn)
    _deactivate_items(
        profile["informational_capabilities"],
        delta.get("removed_informational_capabilities") or [],
        effective_turn,
    )
    _deactivate_items(
        profile["sales_capabilities"],
        delta.get("removed_sales_capabilities") or [],
        effective_turn,
    )
    _deactivate_items(
        profile["external_actions"],
        delta.get("removed_external_actions") or [],
        effective_turn,
    )
    declared_count = delta.get("declared_external_action_count")
    if declared_count:
        profile["declared_external_action_count"] = {
            **declared_count,
            "source_turn": effective_turn,
            "active": True,
        }
    if delta.get("update_type") != "no_update":
        profile["last_updated_turn"] = effective_turn
    profile["requirement_class"] = derive_requirement_class(profile)
    if (
        profile["requirement_class"] != REQUIREMENT_CLASS_UNKNOWN
        and not profile.get("first_confirmed_turn")
    ):
        profile["first_confirmed_turn"] = profile.get("last_updated_turn") or effective_turn
    profile["sources"] = _derive_sources(profile)
    return profile


def derive_requirement_class(profile: Dict[str, Any]) -> str:
    informational = _active_types(profile.get("informational_capabilities"))
    sales = _active_types(profile.get("sales_capabilities"))
    external = _active_types(profile.get("external_actions"))
    if sales and external:
        return REQUIREMENT_CLASS_MIXED_ADVANCED
    if sales:
        return REQUIREMENT_CLASS_SALES_PERSUASION
    if external:
        return REQUIREMENT_CLASS_EXTERNAL_ACTIONS
    if informational:
        return REQUIREMENT_CLASS_INFORMATIONAL_ONLY
    return REQUIREMENT_CLASS_UNKNOWN


def derive_action_requirement(requirement_class: str) -> str:
    if requirement_class == REQUIREMENT_CLASS_INFORMATIONAL_ONLY:
        return ActionRequirement.ANSWERS_ONLY.value
    if requirement_class == REQUIREMENT_CLASS_EXTERNAL_ACTIONS:
        return ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    return ActionRequirement.UNKNOWN.value


def derive_product_fit(profile: Dict[str, Any]) -> str:
    requirement_class = profile.get("requirement_class") or derive_requirement_class(profile)
    action_count = active_external_action_count(profile)
    if requirement_class == REQUIREMENT_CLASS_INFORMATIONAL_ONLY:
        return ProductFit.MOVIA_CAPTURA.value
    if requirement_class == REQUIREMENT_CLASS_EXTERNAL_ACTIONS:
        if action_count and action_count > STANDARD_HIBRIDO_ACTION_LIMIT:
            return ProductFit.CUSTOM_REVIEW.value
        return ProductFit.MOVIA_HIBRIDO.value
    if requirement_class == REQUIREMENT_CLASS_SALES_PERSUASION:
        return ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    if requirement_class == REQUIREMENT_CLASS_MIXED_ADVANCED:
        return ProductFit.CUSTOM_REVIEW.value
    return ProductFit.UNKNOWN.value


def active_external_action_count(profile: Dict[str, Any]) -> Optional[int]:
    declared = profile.get("declared_external_action_count") or {}
    if declared.get("active") and isinstance(declared.get("value"), int):
        return int(declared["value"])
    # A list of action examples establishes external-action fit, but does not
    # establish that every named action is a committed paid scope.  Only a
    # literal declared count can move Híbrido past its two-action limit.
    return None


def derive_scope_flags(profile: Dict[str, Any], requested_product: Optional[str] = None) -> List[str]:
    flags: List[str] = []
    fit = derive_product_fit(profile)
    requirement_class = profile.get("requirement_class") or derive_requirement_class(profile)
    if fit == ProductFit.CUSTOM_REVIEW.value:
        _append_unique(flags, "unsupported_scope")
        _append_unique(flags, "custom_scope_review_required")
    if requested_product in {"movia_ventas", "movia_pro_comercial"}:
        _append_unique(flags, "product_unavailable")
    if requested_product == "movia_captura" and requirement_class in {
        REQUIREMENT_CLASS_EXTERNAL_ACTIONS,
        REQUIREMENT_CLASS_MIXED_ADVANCED,
    }:
        _append_unique(flags, "product_preference_mismatch")
    if requested_product == "movia_hibrido" and requirement_class == REQUIREMENT_CLASS_INFORMATIONAL_ONLY:
        _append_unique(flags, "product_preference_mismatch")
    return flags


def build_requirement_summary(
    profile: Dict[str, Any], *, requested_product: Optional[str] = None
) -> Dict[str, Any]:
    profile = ensure_requirement_profile({"requirement_profile": profile})
    fit = derive_product_fit(profile)
    return {
        "observed_problems": sorted(_active_types(profile.get("observed_business_problems"))),
        "confirmed_requirements": {
            "informational_capabilities": sorted(
                _active_types(profile.get("informational_capabilities"))
            ),
            "sales_capabilities": sorted(_active_types(profile.get("sales_capabilities"))),
            "external_actions": sorted(_active_types(profile.get("external_actions"))),
        },
        "declared_external_action_count": active_external_action_count(profile),
        "requirement_class": profile.get("requirement_class") or derive_requirement_class(profile),
        "recommended_product": fit if fit != ProductFit.UNKNOWN.value else None,
        "scope_flags": derive_scope_flags(profile, requested_product=requested_product),
    }


def _entries_from_observation(
    observation_list: Any,
    allowed_types: Iterable[str],
    *,
    strength_key: str,
) -> List[Dict[str, Any]]:
    allowed = set(str(value) for value in allowed_types)
    result: List[Dict[str, Any]] = []
    for item in observation_list or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type not in allowed:
            continue
        result.append(
            {
                "type": item_type,
                "evidence_span": item.get("evidence_span"),
                "strength": item.get(strength_key) or "explicit",
                "active": True,
            }
        )
    return _dedupe_entries(result)


def _contextual_action_entries(raw_entries: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    valid_actions = set(RequestedAgentAction.values()) - {
        RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION.value
    }
    for item in raw_entries or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type not in valid_actions:
            continue
        evidence_span = str(item.get("evidence_span") or "").strip()
        if not evidence_span:
            continue
        result.append(
            {
                "type": item_type,
                "evidence_span": evidence_span,
                "strength": item.get("strength") or "explicit",
                "source": item.get("source") or "contextual_requirement_frame",
                "active": True,
            }
        )
    return _dedupe_entries(result)


def _declared_count_payload(
    raw_payload: Any, normalized_value: Any
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return None
    value = raw_payload.get("value")
    if value != normalized_value or not isinstance(value, int):
        return None
    evidence_span = raw_payload.get("evidence_span")
    if not evidence_span:
        return None
    return {"value": value, "evidence_span": evidence_span}


def _merge_items(existing: List[Dict[str, Any]], new_items: List[Dict[str, Any]], turn_number: int) -> None:
    for item in new_items:
        item_type = item["type"]
        current = next((entry for entry in existing if entry.get("type") == item_type), None)
        payload = {
            **item,
            "source_turn": turn_number,
            "active": True,
        }
        if current:
            current.update(payload)
        else:
            existing.append(payload)


def _deactivate_items(existing: List[Dict[str, Any]], removed_types: List[str], turn_number: int) -> None:
    for item_type in removed_types:
        current = next((entry for entry in existing if entry.get("type") == item_type), None)
        if current:
            current["active"] = False
            current["last_removed_turn"] = turn_number


def _deactivate_all(existing: List[Dict[str, Any]], turn_number: int) -> None:
    for current in existing:
        if current.get("active", True):
            current["active"] = False
            current["last_removed_turn"] = turn_number


def _derive_sources(profile: Dict[str, Any]) -> Dict[str, Any]:
    sources: Dict[str, Any] = {}
    for key in [
        "observed_business_problems",
        "informational_capabilities",
        "sales_capabilities",
        "external_actions",
    ]:
        category_sources = {}
        for item in profile.get(key) or []:
            category_sources[item.get("type")] = {
                "source_turn": item.get("source_turn"),
                "active": item.get("active", True),
            }
        sources[key] = category_sources
    if profile.get("declared_external_action_count"):
        sources["declared_external_action_count"] = {
            "source_turn": profile["declared_external_action_count"].get("source_turn"),
            "active": profile["declared_external_action_count"].get("active", True),
        }
    return sources


def _dedupe_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        key = entry.get("type")
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _active_types(entries: Optional[Iterable[Dict[str, Any]]]) -> List[str]:
    return [
        str(entry.get("type"))
        for entry in entries or []
        if entry.get("type") and entry.get("active", True)
    ]


def _detect_explicit_removals(profile: Dict[str, Any], message: str) -> Dict[str, List[str]]:
    normalized = _normalize(message)
    if not _contains_removal_signal(normalized):
        return {
            "informational_capabilities": [],
            "sales_capabilities": [],
            "external_actions": [],
        }
    return {
        "informational_capabilities": [
            item_type
            for item_type in _active_types(profile.get("informational_capabilities"))
            if _message_mentions_type(normalized, item_type)
        ],
        "sales_capabilities": [
            item_type
            for item_type in _active_types(profile.get("sales_capabilities"))
            if _message_mentions_type(normalized, item_type)
        ],
        "external_actions": [
            item_type
            for item_type in _active_types(profile.get("external_actions"))
            if _message_mentions_type(normalized, item_type)
        ],
    }


def _has_scope_narrowing_replacement(
    *,
    message: str,
    new_entries: List[Dict[str, Any]],
    existing_profile: Dict[str, Any],
) -> bool:
    if not new_entries or not _has_active_requirement(existing_profile):
        return False
    evidence_text = " ".join(
        str(entry.get("evidence_span") or "") for entry in new_entries if entry.get("evidence_span")
    )
    combined = _normalize(f"{message} {evidence_text}")
    if not combined:
        return False
    return any(
        phrase in combined
        for phrase in [
            "mejor solo",
            "mejor solamente",
            "mejor unicamente",
            "mejor únicamente",
            "solo que",
            "solamente que",
            "unicamente que",
            "únicamente que",
            "nada mas que",
            "nada más que",
            "solo necesito que",
            "solamente necesito que",
            "unicamente necesito que",
            "únicamente necesito que",
        ]
    )


def _has_active_requirement(profile: Dict[str, Any]) -> bool:
    return any(
        _active_types(profile.get(key))
        for key in [
            "informational_capabilities",
            "sales_capabilities",
            "external_actions",
        ]
    )


def _contains_removal_signal(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in [
            "ya no necesito",
            "ya no quiero",
            "en realidad ya no",
            "quitale",
            "quitar",
            "sin ",
        ]
    )


def _message_mentions_type(normalized: str, item_type: str) -> bool:
    cues = _type_cues().get(item_type, [])
    return any(cue in normalized for cue in cues)


def _type_cues() -> Dict[str, List[str]]:
    return {
        "answer_customer_questions": ["responder", "dudas", "preguntas"],
        "provide_prices": ["precios", "precio"],
        "capture_lead_data": ["capturar datos", "capturar", "leads"],
        "close_sale": ["cerrar ventas", "cierre ventas", "venda por mi", "venda por mí"],
        "schedule_appointment": ["agendar", "agenda", "citas", "cita"],
        "generate_quote": ["cotizar", "cotice", "cotizacion", "cotización"],
        "create_order": ["pedido", "pedidos", "orden"],
        "write_external_system": ["sistema", "panel", "crm"],
        "send_reminder": ["recordatorio", "recordar"],
        "follow_up_lead": ["seguimiento", "follow up"],
    }


def _normalize(value: str) -> str:
    lowered = str(value or "").lower()
    lowered = re.sub(r"[^\w\s%]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", lowered).strip()


def _append_unique(values: List[str], value: str) -> None:
    if value not in values:
        values.append(value)
