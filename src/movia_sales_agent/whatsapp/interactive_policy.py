from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol


MAX_EARLY_FUNNEL_INTERACTIVE_PACKETS = 3


class InteractiveMessage(Protocol):
    text: str
    interactive_button_id: Optional[str]


@dataclass(frozen=True)
class InteractivePacket:
    key: str
    body: str
    buttons: List[Dict[str, str]]


PRICE_QUALIFICATION_PACKET = InteractivePacket(
    key="price_qualification",
    body=(
        "Sí, te puedo orientar con precios.\n\n"
        "MovIA tiene opciones según lo que necesites que haga el agente: desde atención básica "
        "en WhatsApp hasta flujos con acciones como agendar, cotizar o registrar información.\n\n"
        "Para darte el precio correcto, ¿qué necesitas que haga?"
    ),
    buttons=[
        {"id": "need_answers", "title": "Responder dudas"},
        {"id": "need_actions", "title": "Hacer acciones"},
        {"id": "need_unsure", "title": "No sé todavía"},
    ],
)

NEED_SEGMENTATION_PACKET = InteractivePacket(
    key="need_segmentation",
    body=(
        "Para orientarte rápido:\n\n"
        "¿Necesitas que el agente solo responda y capture datos, o también que haga acciones "
        "como agendar, cotizar o registrar información?"
    ),
    buttons=[
        {"id": "need_answers", "title": "Solo responde"},
        {"id": "need_actions", "title": "Hace acciones"},
        {"id": "need_unsure", "title": "No estoy seguro"},
    ],
)

HOW_IT_WORKS_PACKET = InteractivePacket(
    key="how_it_works",
    body=(
        "Funciona así:\n\n"
        "1. Creas tu agente en la app.\n"
        "2. Cargas la información de tu negocio.\n"
        "3. Revisas el demo y se ajusta antes de activarlo.\n\n"
        "La idea es que el agente responda por WhatsApp con la información correcta de tu negocio."
    ),
    buttons=[
        {"id": "entry_prices", "title": "Ver precios"},
        {"id": "entry_choose_agent", "title": "Elegir agente"},
        {"id": "start_now", "title": "Quiero empezar"},
    ],
)

CAPTURA_PRICE_CONTEXT_PACKET = InteractivePacket(
    key="captura_price_context",
    body=(
        "Entonces probablemente MovIA Captura es la mejor primera opción.\n\n"
        "Sirve para responder preguntas, capturar datos y filtrar interesados por WhatsApp.\n\n"
        "El setup empieza en $4,900 MXN y la mensualidad es de $500 MXN."
    ),
    buttons=[
        {"id": "start_now", "title": "Quiero empezar"},
        {"id": "entry_how_it_works", "title": "Cómo funciona"},
        {"id": "ask_question", "title": "Tengo duda"},
    ],
)

HIBRIDO_PRICE_CONTEXT_PACKET = InteractivePacket(
    key="hibrido_price_context",
    body=(
        "Entonces suena más cercano a MovIA Híbrido.\n\n"
        "Además de responder, puede manejar hasta 2 acciones operativas acordadas, como agendar, "
        "cotizar o registrar información.\n\n"
        "El setup empieza en $7,500 MXN y la mensualidad es de $500 MXN."
    ),
    buttons=[
        {"id": "start_now", "title": "Quiero empezar"},
        {"id": "review_scope", "title": "Revisar alcance"},
        {"id": "ask_question", "title": "Tengo duda"},
    ],
)


BUTTON_PACKET_BY_ID = {
    "entry_prices": PRICE_QUALIFICATION_PACKET,
    "entry_choose_agent": NEED_SEGMENTATION_PACKET,
    "entry_how_it_works": HOW_IT_WORKS_PACKET,
    "need_unsure": NEED_SEGMENTATION_PACKET,
    "need_answers": CAPTURA_PRICE_CONTEXT_PACKET,
    "need_actions": HIBRIDO_PRICE_CONTEXT_PACKET,
}


def resolve_interactive_packet(
    *,
    response: Any,
    batch: Iterable[InteractiveMessage],
    sent_count: int = 0,
) -> Optional[InteractivePacket]:
    messages = list(batch)
    if sent_count >= MAX_EARLY_FUNNEL_INTERACTIVE_PACKETS:
        return None
    button_id = _single_known_button_id(messages)
    if not button_id:
        return None
    packet = BUTTON_PACKET_BY_ID.get(button_id)
    if not packet:
        return None
    if _has_exit_guard(response):
        return None
    if button_id == "entry_prices" and _has_product_context(response):
        return None
    return packet


def _single_known_button_id(messages: List[InteractiveMessage]) -> Optional[str]:
    if not messages:
        return None
    button_ids = [message.interactive_button_id for message in messages if message.interactive_button_id]
    if len(button_ids) != len(messages):
        return None
    if len(set(button_ids)) != 1:
        return None
    button_id = button_ids[0]
    return button_id if button_id in BUTTON_PACKET_BY_ID else None


def _has_exit_guard(response: Any) -> bool:
    selected_action = getattr(response, "selected_action", None) or {}
    lead_state = getattr(response, "lead_state", None) or {}
    macro_action = str(selected_action.get("macro_action") or getattr(response, "action", "") or "")
    micro_action = str(selected_action.get("micro_action") or "")
    reason_code = str(selected_action.get("reason_code") or "")
    target_stage = str(selected_action.get("target_stage") or lead_state.get("current_stage") or "")

    if macro_action in {
        "direct_close",
        "handle_objection",
        "handoff_to_miguel",
        "soft_close",
    }:
        return True
    if target_stage in {"closing", "post_purchase", "handoff", "objection_handling"}:
        return True
    if micro_action in {"redirect_custom_scope", "send_app_link", "send_app_link_and_deposit_step"}:
        return True
    if reason_code in {"CUSTOM_SCOPE_REVIEW", "DIRECT_CLOSE_ALLOWED", "POST_PURCHASE_HANDOFF"}:
        return True
    if _active_objection(lead_state.get("active_objection")):
        return True
    if _has_committed_product(lead_state):
        return True
    if _has_custom_scope(lead_state):
        return True
    return False


def _active_objection(active_objection: Any) -> bool:
    if not isinstance(active_objection, dict):
        return False
    if active_objection.get("active") is True:
        return True
    return str(active_objection.get("status") or "") == "active"


def _has_committed_product(lead_state: Dict[str, Any]) -> bool:
    profile_data = lead_state.get("profile_data") if isinstance(lead_state, dict) else {}
    profile_data = profile_data if isinstance(profile_data, dict) else {}
    product_context = profile_data.get("product_context")
    product_context = product_context if isinstance(product_context, dict) else {}
    return bool(
        lead_state.get("selected_product")
        or lead_state.get("confirmed_product")
        or profile_data.get("selected_product")
        or profile_data.get("confirmed_product")
        or product_context.get("selected_product")
        or product_context.get("confirmed_product")
    )


def _has_product_context(response: Any) -> bool:
    lead_state = getattr(response, "lead_state", None) or {}
    profile_data = lead_state.get("profile_data") if isinstance(lead_state, dict) else {}
    profile_data = profile_data if isinstance(profile_data, dict) else {}
    product_context = profile_data.get("product_context")
    product_context = product_context if isinstance(product_context, dict) else {}
    return bool(
        product_context.get("active_product_context")
        or product_context.get("referenced_product")
        or profile_data.get("active_product_context")
        or profile_data.get("referenced_product")
    )


def _has_custom_scope(lead_state: Dict[str, Any]) -> bool:
    profile_data = lead_state.get("profile_data") if isinstance(lead_state, dict) else {}
    profile_data = profile_data if isinstance(profile_data, dict) else {}
    scope_flags = set(profile_data.get("scope_flags") or lead_state.get("scope_flags") or [])
    return "custom_scope_review_required" in scope_flags or "unsupported_scope" in scope_flags
