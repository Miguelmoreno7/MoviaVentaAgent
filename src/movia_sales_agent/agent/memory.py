from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    ProductFit,
    ReferenceType,
    Topic,
)
from movia_sales_agent.agent.requirements import (
    active_external_action_count,
    build_requirement_summary,
    derive_action_requirement,
    derive_product_fit,
    ensure_requirement_profile,
)
from movia_sales_agent.models.schemas import TurnAnalysis


CORE_SLOT_KEYS = [
    "business_type",
    "main_channel",
    "pain_or_goal",
    "action_requirement",
    "known_product_fit",
]

QUESTION_KEY_TO_SLOT = {
    "business_type": "business_type",
    "main_channel": "main_channel",
    "pain_or_goal": "pain_or_goal",
    "action_requirement": "action_requirement",
}

QUESTION_TEXT_BY_KEY = {
    "business_type": "¿Qué tipo de negocio tienes?",
    "main_channel": "¿Por dónde te escriben más tus clientes: WhatsApp, Facebook o Instagram?",
    "pain_or_goal": "¿Qué quieres mejorar primero: responder más rápido, filtrar leads o registrar datos?",
    "action_requirement": "¿El agente solo debe responder/capturar datos o también hacer acciones como agendar, cotizar o registrar información?",
    "process_or_demo": "¿Quieres que te explique el proceso para iniciar o prefieres ver el demo?",
}


def build_structured_memory(analysis: TurnAnalysis, lead_profile: Dict[str, Any]) -> Dict[str, Any]:
    profile_data = {
        **dict(lead_profile.get("profile_data") or {}),
        **dict(analysis.lead_updates.profile_data or {}),
    }
    requirement_profile = ensure_requirement_profile(profile_data)
    requirement_class = requirement_profile.get("requirement_class")
    action_requirement = derive_action_requirement(requirement_class)
    if action_requirement == ActionRequirement.UNKNOWN.value:
        action_requirement = _valid_action_requirement(profile_data.get("action_requirement"))
    known_product_fit = _valid_product_fit(derive_product_fit(requirement_profile))
    if known_product_fit == ProductFit.UNKNOWN.value:
        fallback_fit = _valid_product_fit(profile_data.get("known_product_fit"))
        if fallback_fit != ProductFit.UNKNOWN.value:
            known_product_fit = fallback_fit
    if known_product_fit != ProductFit.UNKNOWN.value:
        profile_data["known_product_fit"] = known_product_fit
    if action_requirement != ActionRequirement.UNKNOWN.value:
        profile_data["action_requirement"] = action_requirement
    profile_data["requirement_profile"] = requirement_profile
    requirement_summary = build_requirement_summary(
        requirement_profile,
        requested_product=profile_data.get("requested_product"),
    )
    action_requirement_known = _action_requirement_is_known(
        action_requirement=action_requirement,
        requirement_class=requirement_class,
        requirement_profile=requirement_profile,
    )

    known_slots = _drop_empty(
        {
            "business_type": analysis.business_type
            or analysis.lead_updates.business_type
            or lead_profile.get("business_type"),
            "main_channel": analysis.main_channel
            or analysis.lead_updates.main_channel
            or lead_profile.get("main_channel"),
            "pain_or_goal": analysis.pain
            or analysis.lead_updates.pain
            or lead_profile.get("pain"),
            "action_requirement": action_requirement
            if action_requirement != ActionRequirement.UNKNOWN.value
            else None,
            "known_product_fit": known_product_fit
            if known_product_fit != ProductFit.UNKNOWN.value
            else None,
        }
    )
    missing_slots = [
        slot
        for slot in CORE_SLOT_KEYS
        if slot not in known_slots
        and not (slot == "action_requirement" and action_requirement_known)
    ]
    forbidden_question_keys = [
        key
        for key, slot in QUESTION_KEY_TO_SLOT.items()
        if slot in known_slots or (slot == "action_requirement" and action_requirement_known)
    ]
    derived_profile_data = dict(profile_data)
    if known_product_fit != ProductFit.UNKNOWN.value:
        derived_profile_data["known_product_fit"] = known_product_fit
    if action_requirement != ActionRequirement.UNKNOWN.value:
        derived_profile_data["action_requirement"] = action_requirement
    derived_profile_data["requirement_profile"] = requirement_profile

    return {
        "known_slots": known_slots,
        "missing_slots": missing_slots,
        "forbidden_question_keys": forbidden_question_keys,
        "derived_profile_data": derived_profile_data,
        "requirement_profile": requirement_profile,
        "requirement_class": requirement_class,
        "active_external_action_count": active_external_action_count(requirement_profile),
        "scope_flags": requirement_summary["scope_flags"],
        "confirmed_requirements": requirement_summary["confirmed_requirements"],
    }


def memory_updates_for_profile(analysis: TurnAnalysis, memory: Dict[str, Any]) -> Dict[str, Any]:
    updates = analysis.lead_updates.model_dump(exclude_none=True)
    profile_data = {
        **dict(updates.get("profile_data") or {}),
        **dict(memory.get("derived_profile_data") or {}),
    }
    if profile_data:
        updates["profile_data"] = profile_data
    return updates


def merge_lead_profile_memory(
    lead_profile: Dict[str, Any],
    analysis: TurnAnalysis,
    memory: Dict[str, Any],
) -> Dict[str, Any]:
    known = dict(memory.get("known_slots") or {})
    merged = dict(lead_profile)
    if known.get("business_type"):
        merged["business_type"] = known["business_type"]
    if known.get("main_channel"):
        merged["main_channel"] = known["main_channel"]
    if known.get("pain_or_goal"):
        merged["pain"] = known["pain_or_goal"]
    merged["profile_data"] = {
        **dict(lead_profile.get("profile_data") or {}),
        **dict(analysis.lead_updates.profile_data or {}),
        **dict(memory.get("derived_profile_data") or {}),
    }
    return merged


def next_question_for_missing_slot(memory: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    for key in ["business_type", "main_channel", "pain_or_goal", "action_requirement"]:
        if key in memory.get("missing_slots", []):
            if key == "action_requirement" and _memory_has_action_requirement(memory):
                continue
            return QUESTION_TEXT_BY_KEY[key], key
    return None, None


def retrieve_conversation_memory(
    analysis: TurnAnalysis,
    recent_messages: Sequence[Dict[str, Any]],
    *,
    max_pairs: int = 3,
) -> List[Dict[str, Any]]:
    if not analysis.references_prior_message:
        return []
    pairs = _turn_pairs(recent_messages)
    if not pairs:
        return []
    if analysis.explicit_turn_number:
        pair = next((item for item in pairs if item["turn_id"] == analysis.explicit_turn_number), None)
        return [_evidence(pair, "explicit_turn")] if pair else []

    query_terms = _reference_terms(analysis)
    ranked = []
    for pair in pairs:
        combined = f"{pair.get('user_message', '')} {pair.get('assistant_message', '')}".lower()
        score = sum(1 for term in query_terms if term and term in combined)
        if _contains_any(combined, ["captura", "hibrido", "híbrido", "deposito", "depósito"]):
            score += 1
        if score:
            ranked.append((score, pair))
    ranked.sort(key=lambda item: (-item[0], item[1]["turn_id"]))
    return [
        _evidence(pair, _reason_for_reference(analysis))
        for _score, pair in ranked[:max_pairs]
    ]


def sanitize_response_memory(
    response: str,
    context: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    memory = context.get("memory_context") or {}
    known_slots = dict(memory.get("known_slots") or {})
    forbidden = set(memory.get("forbidden_question_keys") or [])
    violations = [
        key
        for key in sorted(forbidden)
        if _response_asks_for_key(response, key)
    ]
    if not violations:
        return response, {"violations": [], "corrected": False}

    safe_response = _remove_forbidden_question_block(response, violations).strip()
    if not safe_response:
        safe_response = "Con lo que ya me compartiste, puedo avanzar sin volver a preguntarte esos datos."
    safe_response = safe_response.rstrip()
    if safe_response and safe_response[-1] not in ".!?":
        safe_response += "."
    safe_response += " " + QUESTION_TEXT_BY_KEY["process_or_demo"]
    return safe_response, {
        "violations": violations,
        "corrected": True,
        "known_slots_used": known_slots,
    }


def fallback_reference_response(
    analysis: TurnAnalysis,
    evidence: Sequence[Dict[str, Any]],
) -> Optional[str]:
    if not analysis.references_prior_message:
        return None
    query = (analysis.reference_query or "").lower()
    combined = " ".join(
        f"{item.get('user_message', '')} {item.get('assistant_message', '')}"
        for item in evidence
    ).lower()
    if "deposit" in query or "depósito" in query or "deposito" in query:
        return "Sí: el depósito oficial para iniciar es del 50%. Después se revisa y se completa el proceso según el flujo de la app."
    if "proveedor" in query or "ticket" in query or "foto" in query:
        return "Lo de proveedores, tickets y fotos corresponde mejor a MovIA Híbrido, porque requiere acciones además de responder."
    for item in evidence:
        assistant_message = str(item.get("assistant_message") or "").lower()
        if _contains_any(assistant_message, ["te conviene más movia captura", "te conviene mas movia captura", "recomendar captura"]):
            return "El plan que veníamos perfilando era MovIA Captura."
        if _contains_any(assistant_message, ["te conviene más movia híbrido", "te conviene mas movia hibrido", "recomendar hibrido", "recomendar híbrido"]):
            return "El plan que veníamos perfilando era MovIA Híbrido."
    if "captura" in combined and not ("hibrido" in combined or "híbrido" in combined):
        return "El plan que veníamos perfilando era MovIA Captura."
    if "hibrido" in combined or "híbrido" in combined:
        return "El plan que veníamos perfilando era MovIA Híbrido."
    if evidence:
        return "Sí, tengo presente lo anterior. Retomo esa información para no volver a preguntarte lo mismo."
    return None


def _valid_action_requirement(value: Any) -> str:
    if value in {
        ActionRequirement.ANSWERS_ONLY.value,
        ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value,
    }:
        return str(value)
    return ActionRequirement.UNKNOWN.value


def _action_requirement_is_known(
    *,
    action_requirement: Any,
    requirement_class: Any,
    requirement_profile: Dict[str, Any],
) -> bool:
    if _valid_action_requirement(action_requirement) != ActionRequirement.UNKNOWN.value:
        return True
    profile = ensure_requirement_profile({"requirement_profile": requirement_profile})
    if (profile.get("requirement_class") or "unknown") != "unknown":
        return True
    return bool(active_external_action_count(profile)) or str(requirement_class or "unknown") != "unknown"


def _memory_has_action_requirement(memory: Dict[str, Any]) -> bool:
    known_slots = dict(memory.get("known_slots") or {})
    if _valid_action_requirement(known_slots.get("action_requirement")) != ActionRequirement.UNKNOWN.value:
        return True
    if _valid_action_requirement(
        (memory.get("derived_profile_data") or {}).get("action_requirement")
    ) != ActionRequirement.UNKNOWN.value:
        return True
    return _action_requirement_is_known(
        action_requirement=(memory.get("derived_profile_data") or {}).get("action_requirement"),
        requirement_class=memory.get("requirement_class"),
        requirement_profile=memory.get("requirement_profile") or {},
    )


def _valid_product_fit(value: Any) -> str:
    if value in ProductFit.values():
        return str(value)
    return ProductFit.UNKNOWN.value


def _drop_empty(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value not in (None, "", [], {})
    }


def _turn_pairs(recent_messages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    pending_user: Optional[str] = None
    turn_id = 0
    for message in recent_messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if role == "user":
            pending_user = content
            continue
        if role == "assistant" and pending_user:
            turn_id += 1
            pairs.append(
                {
                    "turn_id": turn_id,
                    "user_message": pending_user,
                    "assistant_message": content,
                }
            )
            pending_user = None
    return pairs


def _evidence(pair: Optional[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    if not pair:
        return {}
    return {
        "turn_id": pair["turn_id"],
        "user_message": pair.get("user_message", ""),
        "assistant_message": pair.get("assistant_message", ""),
        "relevance_reason": reason,
    }


def _reference_terms(analysis: TurnAnalysis) -> List[str]:
    raw_terms = str(analysis.reference_query or "").lower().replace("_", " ").split()
    terms = [term for term in raw_terms if len(term) >= 5]
    for topic in analysis.referenced_topics:
        terms.extend(str(topic).replace("_", " ").split())
    return list(dict.fromkeys(terms))


def _reason_for_reference(analysis: TurnAnalysis) -> str:
    if analysis.reference_type == ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value:
        return "assistant_commitment_reference"
    if analysis.reference_type == ReferenceType.TOPIC_REFERENCE.value:
        return "topic_reference"
    if analysis.reference_type == ReferenceType.TEMPORAL_REFERENCE.value:
        return "temporal_reference"
    return "prior_reference"


def _response_asks_for_key(response: str, key: str) -> bool:
    text = response.lower()
    patterns = {
        "business_type": ["qué tipo de negocio", "que tipo de negocio", "tipo de negocio tienes"],
        "main_channel": ["por dónde te escriben", "por donde te escriben", "canal principal"],
        "pain_or_goal": ["qué quieres mejorar", "que quieres mejorar", "qué parte de tu atención", "que parte de tu atencion"],
        "action_requirement": ["solo debe responder", "también hacer acciones", "tambien hacer acciones", "agendar, cotizar o registrar"],
    }
    return any(pattern in text for pattern in patterns.get(key, [])) and "?" in text


def _remove_forbidden_question_block(response: str, violations: Sequence[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", response.strip())
    keep = [
        sentence
        for sentence in sentences
        if not any(_response_asks_for_key(sentence, key) for key in violations)
    ]
    return " ".join(keep)


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)
