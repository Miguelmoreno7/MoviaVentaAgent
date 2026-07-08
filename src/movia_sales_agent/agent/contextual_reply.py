from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from movia_sales_agent.analyzer.contract_v3 import RequestedAgentAction, RequestedProduct
from movia_sales_agent.contracts.commercial import BuyingSignal, Intent, ProductFit
from movia_sales_agent.models.schemas import TurnAnalysis


AFFIRMATIVE_REPLIES = {
    "si",
    "si porfavor",
    "si por favor",
    "si gracias",
    "si claro",
    "claro",
    "dale",
    "va",
    "ok",
    "okay",
    "de acuerdo",
    "perfecto",
    "por favor",
    "porfavor",
}

ACTION_TYPE_CUES = [
    (RequestedAgentAction.SCHEDULE_APPOINTMENT.value, ["agendar", "agenda", "agende", "cita", "citas", "reservar"]),
    (RequestedAgentAction.GENERATE_QUOTE.value, ["cotizar", "cotice", "cotizacion", "cotización", "presupuesto"]),
    (RequestedAgentAction.WRITE_EXTERNAL_SYSTEM.value, ["registrar", "registre", "guardar", "base de datos", "sistema", "crm", "panel"]),
]


def apply_contextual_reply_resolution(
    *,
    analysis: TurnAnalysis,
    normalized_turn: Dict[str, Any],
    message: str,
    recent_messages: Sequence[Dict[str, Any]],
) -> Tuple[TurnAnalysis, Dict[str, Any]]:
    """Resolve tiny replies against the immediately previous assistant question.

    This is a deterministic runtime adapter. It does not change analyzer output or
    let older context compete with the V3.1 semantic fields.
    """
    normalized = dict(normalized_turn or {})
    resolved_analysis = analysis.model_copy(deep=True)
    previous_assistant = _last_assistant_message(recent_messages)
    previous_text = _message_content(previous_assistant)
    current_text = _normalize(message)
    previous_frame = _previous_frame(previous_text)
    resolution: Dict[str, Any] = {
        "applied": False,
        "previous_frame": previous_frame,
    }

    if not previous_text or not current_text:
        normalized["contextual_reply_resolution"] = resolution
        return resolved_analysis, normalized

    if _is_short_affirmative(current_text):
        if previous_frame == "link_start_cta":
            _resolve_start_intent(resolved_analysis, normalized, message, resolution)
        elif previous_frame == "requirement_actions":
            _resolve_action_requirements(normalized, message, current_text, previous_text, resolution)
        elif previous_frame == "product_confirmation":
            _resolve_product_confirmation(normalized, previous_text, resolution)
        elif previous_frame == "explain_more":
            _resolve_explain_more(normalized, resolution)
    elif previous_frame == "requirement_actions":
        _resolve_action_requirements(normalized, message, current_text, previous_text, resolution)

    normalized["contextual_reply_resolution"] = resolution
    if resolution.get("applied"):
        warnings = list(normalized.get("normalization_warnings") or [])
        warning = str(resolution.get("warning") or "")
        if warning and warning not in warnings:
            warnings.append(warning)
        normalized["normalization_warnings"] = warnings
    return resolved_analysis, normalized


def _resolve_start_intent(
    analysis: TurnAnalysis,
    normalized: Dict[str, Any],
    message: str,
    resolution: Dict[str, Any],
) -> None:
    analysis.primary_intent = Intent.EXPLICIT_START_REQUEST.value
    analysis.explicit_start_intent = True
    analysis.buying_signal = BuyingSignal.EXPLICIT_START.value
    analysis.confidence.start_intent = max(analysis.confidence.start_intent or 0.0, 0.85)
    normalized["explicit_start_intent"] = True
    resolution.update(
        {
            "applied": True,
            "resolution_type": "short_affirmative_to_start_intent",
            "evidence_span": message,
            "warning": "contextual_affirmative_resolved_to_start_intent",
        }
    )


def _resolve_action_requirements(
    normalized: Dict[str, Any],
    message: str,
    current_text: str,
    previous_text: str,
    resolution: Dict[str, Any],
) -> None:
    if _is_generic_affirmative_only(current_text) and not _mentions_both(current_text):
        return
    action_entries = _action_entries_from_text(message, current_text)
    if not action_entries and _mentions_both(current_text):
        action_entries = _action_entries_from_previous_frame(previous_text, message)
    if not action_entries:
        return
    normalized["contextual_requirement_actions"] = _dedupe_action_entries(
        [
            *list(normalized.get("contextual_requirement_actions") or []),
            *action_entries,
        ]
    )
    requested = list(normalized.get("requested_agent_actions") or [])
    for entry in action_entries:
        if entry["type"] not in requested:
            requested.append(entry["type"])
    normalized["requested_agent_actions"] = requested
    resolution.update(
        {
            "applied": True,
            "resolution_type": "requirement_frame_to_external_actions",
            "action_types": [entry["type"] for entry in action_entries],
            "evidence_span": message,
            "warning": "contextual_requirement_frame_promoted_actions",
        }
    )


def _resolve_product_confirmation(
    normalized: Dict[str, Any],
    previous_text: str,
    resolution: Dict[str, Any],
) -> None:
    product = _product_mentioned(previous_text)
    if not product:
        return
    normalized["selected_product"] = product
    normalized["requested_product"] = product
    if product in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}:
        normalized["recommended_product"] = product
    resolution.update(
        {
            "applied": True,
            "resolution_type": "short_affirmative_to_product_confirmation",
            "selected_product": product,
            "warning": "contextual_affirmative_resolved_to_product_confirmation",
        }
    )


def _resolve_explain_more(normalized: Dict[str, Any], resolution: Dict[str, Any]) -> None:
    normalized["contextual_continuation"] = "explain_more"
    resolution.update(
        {
            "applied": True,
            "resolution_type": "short_affirmative_to_explain_more",
            "warning": "contextual_affirmative_resolved_to_explain_more",
        }
    )


def _last_assistant_message(recent_messages: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for message in reversed(list(recent_messages or [])):
        role = str(message.get("role") or message.get("sender") or "").lower()
        if role == "assistant":
            return message
    return None


def _message_content(message: Optional[Dict[str, Any]]) -> str:
    if not isinstance(message, dict):
        return ""
    return str(
        message.get("content")
        or message.get("message")
        or message.get("text")
        or message.get("body")
        or ""
    )


def _previous_frame(previous_text: str) -> str:
    text = _normalize(previous_text)
    if not text:
        return "none"
    if _looks_like_link_start_cta(text):
        return "link_start_cta"
    if _looks_like_requirement_action_question(text):
        return "requirement_actions"
    if _looks_like_explain_more_question(text):
        return "explain_more"
    if _looks_like_product_confirmation(text):
        return "product_confirmation"
    return "none"


def _looks_like_link_start_cta(text: str) -> bool:
    link_cues = ["link", "enlace", "liga", "app", "plataforma"]
    start_cues = ["empezar", "iniciar", "comenzar", "contratar", "crear tu agente", "crear el agente", "pase"]
    question_cues = ["quieres", "te paso", "te comparto", "pasarte", "mandarte", "envio", "envío"]
    return (
        any(cue in text for cue in link_cues)
        and any(cue in text for cue in [*start_cues, *question_cues])
        and any(cue in text for cue in question_cues + ["quieres empezar", "quieres iniciar"])
    )


def _looks_like_requirement_action_question(text: str) -> bool:
    response_side = any(cue in text for cue in ["solo responder", "solo responda", "responder/capturar", "responda dudas", "capture"])
    action_side = any(cue in text for cue in ["tambien", "también", "hacer acciones", "acciones como", "agendar", "cotizar", "registrar"])
    return response_side and action_side


def _looks_like_explain_more_question(text: str) -> bool:
    return any(
        cue in text
        for cue in [
            "quieres que te explique",
            "te explico mas",
            "te explico más",
            "explicarte mas",
            "explicarte más",
            "quieres mas informacion",
            "quieres más información",
        ]
    )


def _looks_like_product_confirmation(text: str) -> bool:
    return bool(_product_mentioned(text)) and any(
        cue in text for cue in ["quieres", "te conviene", "seria", "sería", "opcion", "opción", "ideal"]
    )


def _is_short_affirmative(text: str) -> bool:
    cleaned = _strip_punctuation(text).strip()
    if cleaned in AFFIRMATIVE_REPLIES:
        return True
    tokens = cleaned.split()
    return 0 < len(tokens) <= 3 and tokens[0] in {"si", "claro", "ok", "dale", "va"}


def _is_generic_affirmative_only(text: str) -> bool:
    cleaned = _strip_punctuation(text).strip()
    return cleaned in AFFIRMATIVE_REPLIES


def _mentions_both(text: str) -> bool:
    cleaned = _strip_punctuation(text)
    return any(phrase in cleaned for phrase in ["las dos", "ambas", "tambien acciones", "también acciones", "las 2"])


def _action_entries_from_text(original_message: str, normalized_text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for action_type, cues in ACTION_TYPE_CUES:
        span = _first_matching_span(original_message, normalized_text, cues)
        if span:
            entries.append(_action_entry(action_type, span))
    return _dedupe_action_entries(entries[:2])


def _action_entries_from_previous_frame(previous_text: str, current_message: str) -> List[Dict[str, Any]]:
    normalized_previous = _normalize(previous_text)
    entries = [
        _action_entry(action_type, current_message)
        for action_type, cues in ACTION_TYPE_CUES
        if any(_normalize(cue) in normalized_previous for cue in cues)
    ]
    return _dedupe_action_entries(entries[:2])


def _action_entry(action_type: str, evidence_span: str) -> Dict[str, Any]:
    return {
        "type": action_type,
        "evidence_span": evidence_span,
        "strength": "explicit",
        "source": "contextual_requirement_frame",
        "active": True,
    }


def _dedupe_action_entries(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        action_type = str(entry.get("type") or "")
        if not action_type or action_type in seen:
            continue
        seen.add(action_type)
        result.append(entry)
    return result


def _product_mentioned(text: str) -> Optional[str]:
    normalized = _normalize(text)
    if "captura" in normalized:
        return RequestedProduct.MOVIA_CAPTURA.value
    if "hibrido" in normalized or "híbrido" in normalized:
        return RequestedProduct.MOVIA_HIBRIDO.value
    return None


def _first_matching_span(original_message: str, normalized_message: str, cues: Iterable[str]) -> Optional[str]:
    for cue in cues:
        normalized_cue = _normalize(cue)
        if normalized_cue not in normalized_message:
            continue
        pattern = re.compile(re.escape(cue), re.IGNORECASE)
        match = pattern.search(original_message)
        if match:
            return match.group(0)
        return cue
    return None


def _strip_punctuation(text: str) -> str:
    return re.sub(r"[¿?¡!.,;:]+", " ", text).strip()


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents.lower()).strip()
