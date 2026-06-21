from __future__ import annotations

from typing import Any, Dict, Optional

from movia_sales_agent.contracts.commercial import (
    MacroAction,
    ObjectionStrength,
    SalesStage,
)
from movia_sales_agent.models.schemas import SalesPlan, TurnAnalysis


NEXT_QUESTION_KEEP = "keep"
NEXT_QUESTION_REPLACE_MINIMAL = "replace_minimal"
NEXT_QUESTION_SUPPRESS = "suppress"

MINIMAL_QUESTIONS = {
    "answer_or_actions": "Para elegir bien dentro de la app: ¿solo necesitas que responda/capture información o también que haga acciones como agendar o cotizar?",
    "guide_app_options": "¿Quieres que te guíe con qué opciones seleccionar dentro de la app?",
    "none": None,
}

BROAD_DISCOVERY_KEYS = {
    "automation_need",
    "business_type",
    "main_channel",
    "pain_or_goal",
    "action_requirement",
}


def build_response_fulfillment_policy(
    *,
    analysis: TurnAnalysis,
    sales_plan: SalesPlan,
    normalized_turn: Dict[str, Any],
    active_objection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn-local response packaging policy. It never represents lead memory."""
    policy: Dict[str, Any] = {
        "mandatory_fulfillments": [],
        "next_question_policy": NEXT_QUESTION_KEEP,
        "minimal_question_key": "none",
        "preserve_commercial_plan": True,
        "preserve_commercial_stage": True,
    }
    if not _should_include_app_link(analysis, sales_plan, normalized_turn):
        return policy

    policy["mandatory_fulfillments"] = ["official_app_link"]
    minimal_key = _minimal_question_key(
        sales_plan=sales_plan,
        normalized_turn=normalized_turn,
        active_objection=active_objection,
    )
    if minimal_key == "none":
        policy["next_question_policy"] = NEXT_QUESTION_SUPPRESS
    elif _should_replace_question(sales_plan) or not sales_plan.next_question:
        policy["next_question_policy"] = NEXT_QUESTION_REPLACE_MINIMAL
    policy["minimal_question_key"] = minimal_key
    return policy


def minimal_question_for(policy: Dict[str, Any]) -> Optional[str]:
    return MINIMAL_QUESTIONS.get(str(policy.get("minimal_question_key") or "none"))


def _should_include_app_link(
    analysis: TurnAnalysis,
    sales_plan: SalesPlan,
    normalized_turn: Dict[str, Any],
) -> bool:
    if not analysis.explicit_start_intent:
        return False
    if analysis.is_post_purchase or sales_plan.target_stage == SalesStage.HANDOFF.value:
        return False
    if normalized_turn.get("product_unavailable") or normalized_turn.get("unsupported_scope"):
        return False
    return True


def _minimal_question_key(
    *,
    sales_plan: SalesPlan,
    normalized_turn: Dict[str, Any],
    active_objection: Optional[Dict[str, Any]],
) -> str:
    active = active_objection or {}
    if active.get("active") and active.get("strength") == ObjectionStrength.HARD.value:
        return "guide_app_options"
    if (
        normalized_turn.get("selected_product")
        or normalized_turn.get("confirmed_product")
        or sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value
    ):
        return "guide_app_options"
    if normalized_turn.get("active_product_context") in {"movia_captura", "movia_hibrido"}:
        return "guide_app_options"
    return "answer_or_actions"


def _should_replace_question(sales_plan: SalesPlan) -> bool:
    if not sales_plan.next_question:
        return False
    return str(sales_plan.next_question_key or "") in BROAD_DISCOVERY_KEYS
