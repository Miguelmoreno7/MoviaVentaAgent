from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ValidationError

from movia_sales_agent.contracts.commercial import (
    MacroAction,
    ObjectionFlowStep,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionStatus,
    ObjectionType,
    SalesStage,
)
from movia_sales_agent.models.schemas import (
    ActiveObjection,
    SalesPlan,
    StageTransition,
    TurnAnalysis,
)


FLOW_ORDER = [
    ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value,
    ObjectionFlowStep.CLARIFY_VALUE.value,
    ObjectionFlowStep.TIE_SOLUTION.value,
    ObjectionFlowStep.PROVIDE_PROOF.value,
    ObjectionFlowStep.CLOSE_OR_CONTINUE.value,
]


class ObjectionFlowService:
    def transition(
        self,
        *,
        lead_profile: Dict[str, Any],
        analysis: TurnAnalysis,
        sales_plan: SalesPlan,
        stage_transition: StageTransition,
        message: str,
    ) -> ActiveObjection:
        current = active_objection_from_profile(lead_profile)
        next_turn = max(current.last_updated_turn + 1, 1)

        if _resolves_current_objection(current, analysis, sales_plan):
            current.current_step = ObjectionFlowStep.RESOLVED.value
            current.last_updated_turn = next_turn
            current.paused = False
            current.paused_reason = None
            current.resolved = True
            current.active = False
            current.status = ObjectionStatus.RESOLVED.value
            current.relation = ObjectionRelation.RESOLVED.value
            current.resolved_reason = "semantic_resolution"
            current.evidence = _append_evidence(current.evidence, message)
            return current

        if sales_plan.macro_action != MacroAction.HANDLE_OBJECTION.value:
            if current.active and not current.resolved:
                if current.strength != ObjectionStrength.HARD.value:
                    current.active = False
                    current.resolved = True
                    current.status = ObjectionStatus.RESOLVED.value
                    current.relation = ObjectionRelation.RESOLVED.value
                    current.resolved_reason = "soft_concern_handled_inline"
                    current.evidence = _append_evidence(current.evidence, message)
                    return current
                current.paused = True
                current.paused_reason = "current_intent_answered"
                current.status = ObjectionStatus.PAUSED.value
                current.relation = _relation_or_default(analysis, ObjectionRelation.UNRELATED.value)
                current.last_updated_turn = next_turn
                current.evidence = _append_evidence(current.evidence, message)
                return current
            return ActiveObjection()

        if _starts_or_replaces_objection(current, analysis, sales_plan):
            return ActiveObjection(
                active=True,
                type=analysis.objection_type,
                strength=analysis.objection_strength,
                status=ObjectionStatus.ACTIVE.value,
                relation=ObjectionRelation.NEW.value,
                current_step=sales_plan.objection_flow_step,
                started_turn=next_turn,
                last_updated_turn=next_turn,
                stage_before_objection=stage_transition.stage_before_objection
                or stage_transition.previous_stage
                or SalesStage.DISCOVERY.value,
                evidence=message,
                resolved=False,
                paused=False,
            )

        if current.active and not current.resolved:
            resolved = sales_plan.objection_flow_step in {
                ObjectionFlowStep.CLOSE_OR_CONTINUE.value,
                ObjectionFlowStep.RESOLVED.value,
            }
            current.current_step = sales_plan.objection_flow_step
            current.last_updated_turn = next_turn
            current.paused = False
            current.paused_reason = None
            current.resolved = resolved
            current.active = not resolved
            current.status = (
                ObjectionStatus.RESOLVED.value if resolved else ObjectionStatus.ACTIVE.value
            )
            current.relation = _relation_or_default(analysis, ObjectionRelation.CONTINUATION.value)
            if resolved:
                current.resolved_reason = "objection_flow_completed"
                current.relation = ObjectionRelation.RESOLVED.value
            current.evidence = _append_evidence(current.evidence, message)
            return current

        return ActiveObjection()


def active_objection_from_profile(lead_profile: Dict[str, Any]) -> ActiveObjection:
    payload = lead_profile.get("active_objection") or {}
    if not payload:
        payload = (lead_profile.get("profile_data") or {}).get("active_objection") or {}
    if not isinstance(payload, dict):
        return ActiveObjection()
    if "active" not in payload and payload.get("type") not in (None, "", ObjectionType.NONE.value):
        payload = {**payload, "active": True, "resolved": False}
    if "current_step" not in payload and payload.get("active"):
        payload = {**payload, "current_step": ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value}
    if "status" not in payload:
        if payload.get("resolved"):
            status = ObjectionStatus.RESOLVED.value
        elif payload.get("paused"):
            status = ObjectionStatus.PAUSED.value
        elif payload.get("active"):
            status = ObjectionStatus.ACTIVE.value
        else:
            status = ObjectionStatus.NONE.value
        payload = {**payload, "status": status}
    if "relation" not in payload:
        payload = {**payload, "relation": ObjectionRelation.NONE.value}
    try:
        return ActiveObjection.model_validate(payload)
    except ValidationError:
        return ActiveObjection()


def is_active_objection(payload: Optional[Dict[str, Any]]) -> bool:
    objection = active_objection_from_profile({"active_objection": payload or {}})
    return objection.active and not objection.resolved


def next_objection_step(active_objection: Dict[str, Any]) -> str:
    current = active_objection_from_profile({"active_objection": active_objection}).current_step
    if current in (ObjectionFlowStep.NONE.value, ObjectionFlowStep.RESOLVED.value):
        return ObjectionFlowStep.CLARIFY_VALUE.value
    try:
        index = FLOW_ORDER.index(current)
    except ValueError:
        return ObjectionFlowStep.CLARIFY_VALUE.value
    return FLOW_ORDER[min(index + 1, len(FLOW_ORDER) - 1)]


def _starts_or_replaces_objection(
    current: ActiveObjection, analysis: TurnAnalysis, sales_plan: SalesPlan
) -> bool:
    if not analysis.has_objection or analysis.objection_type == ObjectionType.NONE.value:
        return False
    if analysis.objection_strength != ObjectionStrength.HARD.value:
        return False
    if not current.active or current.resolved:
        return True
    if analysis.objection_type != current.type:
        return True
    return sales_plan.objection_flow_step == ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value


def is_unresolved_hard_objection(active_objection: Optional[Dict[str, Any]]) -> bool:
    objection = active_objection_from_profile({"active_objection": active_objection or {}})
    return (
        objection.active
        and not objection.resolved
        and objection.strength == ObjectionStrength.HARD.value
    )


def _resolves_current_objection(
    current: ActiveObjection, analysis: TurnAnalysis, sales_plan: SalesPlan
) -> bool:
    if not current.active or current.resolved:
        return False
    if analysis.has_objection and analysis.objection_type != ObjectionType.NONE.value:
        return False
    if analysis.objection_relation != ObjectionRelation.RESOLVED.value:
        return False
    return sales_plan.macro_action != MacroAction.HANDLE_OBJECTION.value or sales_plan.objection_flow_step in {
        ObjectionFlowStep.RESOLVED.value,
        ObjectionFlowStep.CLOSE_OR_CONTINUE.value,
    }


def _relation_or_default(analysis: TurnAnalysis, default: str) -> str:
    if analysis.objection_relation and analysis.objection_relation != ObjectionRelation.NONE.value:
        return analysis.objection_relation
    return default


def _append_evidence(existing: Optional[str], message: str) -> Optional[str]:
    if not message:
        return existing
    if message in (existing or ""):
        return existing
    return f"{existing or ''} | {message}".strip(" |")
