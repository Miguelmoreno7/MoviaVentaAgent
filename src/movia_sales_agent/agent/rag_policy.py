from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from movia_sales_agent.contracts.commercial import (
    MacroAction,
    ObjectionFlowStep,
    ObjectionType,
    Topic,
)
from movia_sales_agent.models.schemas import SalesPlan, TurnAnalysis


MIN_RAG_SIMILARITY = 0.58


@dataclass(frozen=True)
class RagRoute:
    queries: List[str] = field(default_factory=list)
    metadata_filter: Dict[str, Any] = field(default_factory=dict)
    routing_reason: str = "structured_or_json_only"

    @property
    def needs_rag(self) -> bool:
        return bool(self.queries)


def build_rag_route(
    analysis: TurnAnalysis,
    sales_plan: Optional[SalesPlan],
    message: str,
    *,
    active_objection: Optional[Dict[str, Any]] = None,
) -> RagRoute:
    """Deterministic policy for deciding whether vector context is needed."""
    comparison_target = comparison_target_from_text(message)
    industry = industry_from_analysis(analysis)

    macro_action = sales_plan.macro_action if sales_plan else None
    objection_flow_step = sales_plan.objection_flow_step if sales_plan else None

    if Topic.COMPETITOR_COMPARISON.value in analysis.topics or (
        macro_action == MacroAction.COMPARE_ALTERNATIVE.value
    ):
        filter_value: Dict[str, Any] = {"topic": "comparisons"}
        if comparison_target:
            filter_value["comparison"] = comparison_target
        return RagRoute(
            queries=[_query_with_route_terms(message, comparison_target or "comparacion")],
            metadata_filter=filter_value,
            routing_reason="comparison_target",
        )

    if any(
        topic in analysis.topics
        for topic in [Topic.INDUSTRY_USE_CASE.value, Topic.BUSINESS_FIT.value]
    ):
        if industry:
            return RagRoute(
                queries=[_query_with_route_terms(message, industry)],
                metadata_filter={"topic": "use_cases", "industry": industry},
                routing_reason="industry_use_case",
            )
        return RagRoute(
            queries=[message],
            metadata_filter={"topic": "overview"},
            routing_reason="business_fit_overview",
        )

    if objection_flow_step == ObjectionFlowStep.PROVIDE_PROOF.value:
        objection_type = _active_or_current_objection_type(analysis, active_objection)
        if objection_type == ObjectionType.COMPETITOR_COMPARISON.value:
            target = comparison_target or "manychat"
            return RagRoute(
                queries=[_query_with_route_terms(message, target)],
                metadata_filter={"topic": "comparisons", "comparison": target},
                routing_reason="objection_proof_comparison",
            )
        if industry:
            return RagRoute(
                queries=[_query_with_route_terms(message, industry)],
                metadata_filter={"topic": "use_cases", "industry": industry},
                routing_reason="objection_proof_industry",
            )
        return RagRoute(routing_reason="objection_proof_without_safe_filter")

    if macro_action == MacroAction.PERSUADE_VALUE.value and Topic.DEMO.value in analysis.topics:
        return RagRoute(
            queries=[message],
            metadata_filter={"topic": "overview"},
            routing_reason="open_explanatory_overview",
        )

    return RagRoute()


def industry_from_analysis(analysis: TurnAnalysis) -> Optional[str]:
    business_type = analysis.business_type or analysis.lead_updates.business_type
    if business_type == "dental":
        return "dental"
    if business_type == "restaurant":
        return "restaurants"
    if business_type == "real_estate":
        return "real_estate"
    return None


def comparison_target_from_text(message: str) -> Optional[str]:
    text = (message or "").lower()
    if "manychat" in text:
        return "manychat"
    if "recepcionista" in text:
        return "human_receptionist"
    if "whatsapp business" in text or "respuestas rápidas" in text or "respuestas rapidas" in text:
        return "basic_chatbot"
    if "chatbot" in text:
        return "basic_chatbot"
    return None


def _active_or_current_objection_type(
    analysis: TurnAnalysis,
    active_objection: Optional[Dict[str, Any]],
) -> str:
    if analysis.objection_type and analysis.objection_type != ObjectionType.NONE.value:
        return analysis.objection_type
    if active_objection and active_objection.get("type"):
        return str(active_objection.get("type"))
    return ObjectionType.NONE.value


def _query_with_route_terms(message: str, route_term: str) -> str:
    if route_term and route_term.lower() not in (message or "").lower():
        return f"{route_term} {message}".strip()
    return message
