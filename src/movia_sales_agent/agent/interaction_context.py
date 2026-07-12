from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from movia_sales_agent.agent.reply_frame import reply_frame_from_message
from movia_sales_agent.agent.requirements import build_requirement_summary, ensure_requirement_profile


def build_analyzer_interaction_context(
    *,
    lead_profile: Optional[Dict[str, Any]],
    recent_messages: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build compact, turn-local context from already persisted runtime facts."""

    profile = dict(lead_profile or {})
    profile_data = dict(profile.get("profile_data") or {})
    requirement_profile = ensure_requirement_profile(profile_data)
    product_context = dict(profile_data.get("product_context") or {})
    previous = _latest_assistant_message(recent_messages)
    previous_planner = _previous_planner_context(previous)

    return {
        "current_interlocutor": "movia_salesperson",
        "future_requirement_target": "purchased_agent",
        "previous_planner": previous_planner,
        "commercial_state": {
            "current_stage": profile.get("current_stage"),
            "requirement_summary": _compact_requirement_summary(
                build_requirement_summary(
                    requirement_profile,
                    requested_product=product_context.get("active_product_context"),
                )
            ),
            "active_objection": _compact_active_objection(profile.get("active_objection")),
            "active_product_context": product_context.get("active_product_context"),
            "selected_product": product_context.get("selected_product")
            or profile_data.get("selected_product"),
            "confirmed_product": product_context.get("confirmed_product")
            or profile_data.get("confirmed_product"),
        },
    }


def _compact_requirement_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    confirmed = {
        key: value
        for key, value in dict(summary.get("confirmed_requirements") or {}).items()
        if value
    }
    compact = {
        "observed_problems": summary.get("observed_problems") or None,
        "confirmed_requirements": confirmed or None,
        "declared_external_action_count": summary.get("declared_external_action_count"),
        "requirement_class": (
            summary.get("requirement_class")
            if summary.get("requirement_class") not in {None, "unknown"}
            else None
        ),
        "recommended_product": summary.get("recommended_product"),
        "scope_flags": summary.get("scope_flags") or None,
    }
    return {key: value for key, value in compact.items() if value is not None}


def _latest_assistant_message(
    recent_messages: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for message in reversed(list(recent_messages or [])):
        if str(message.get("role") or "").lower() == "assistant":
            return message
    return None


def _previous_planner_context(message: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not message:
        return {}
    frame = reply_frame_from_message(message) or {}
    metadata = message.get("retrieval_metadata") if isinstance(message, dict) else None
    response_metadata = (
        (metadata or {}).get("response_metadata") if isinstance(metadata, dict) else {}
    ) or {}
    context = {
        "macro_action": frame.get("macro_action") or response_metadata.get("macro_action"),
        "micro_action": frame.get("micro_action") or response_metadata.get("micro_action"),
        "cta_type": frame.get("cta_type") or response_metadata.get("cta_type"),
        "next_question_key": frame.get("next_question_key")
        or response_metadata.get("next_question_key"),
        "next_question": frame.get("next_question")
        or response_metadata.get("next_question")
        or message.get("content"),
        "target_product": frame.get("target_product")
        or frame.get("product")
        or response_metadata.get("active_product_context")
        or response_metadata.get("selected_product"),
        "reply_frame_type": frame.get("type"),
    }
    return {key: value for key, value in context.items() if value not in (None, "", {})}


def _compact_active_objection(value: Any) -> Dict[str, Any]:
    active = dict(value or {})
    if not active.get("active"):
        return {}
    return {
        key: active.get(key)
        for key in ("type", "strength", "status", "current_step", "evidence")
        if active.get(key) not in (None, "", "none")
    }
