from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple

from movia_sales_agent.agent.objections import active_objection_from_profile
from movia_sales_agent.contracts.commercial import (
    ConversationMode,
    MacroAction,
    ObjectionFlowStep,
    ObjectionStatus,
    ObjectionStrength,
    SalesStage,
)
from movia_sales_agent.models.schemas import SalesPlan, StageTransition, TurnAnalysis


V1_STAGE_MAP: Dict[str, str] = {
    "recommended": SalesStage.SOLUTION_RECOMMENDED.value,
    "unknown": SalesStage.UNKNOWN_RECOVERY.value,
}


ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    SalesStage.NEW.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.QUALIFIED.value,
        SalesStage.COMPARING.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.DISCOVERY.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.QUALIFIED.value,
        SalesStage.COMPARING.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.EDUCATING.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.QUALIFIED.value,
        SalesStage.COMPARING.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.READY_TO_START.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.COMPARING.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.COMPARING.value,
        SalesStage.QUALIFIED.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.READY_TO_START.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.QUALIFIED.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.COMPARING.value,
        SalesStage.QUALIFIED.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.READY_TO_START.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.SOLUTION_RECOMMENDED.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.COMPARING.value,
        SalesStage.SOLUTION_RECOMMENDED.value,
        SalesStage.READY_TO_START.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.READY_TO_START.value: {
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
        SalesStage.READY_TO_START.value,
        SalesStage.CLOSING.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.CLOSING.value: {
        SalesStage.CLOSING.value,
        SalesStage.POST_PURCHASE.value,
        SalesStage.HANDOFF.value,
        SalesStage.UNKNOWN_RECOVERY.value,
    },
    SalesStage.POST_PURCHASE.value: {
        SalesStage.POST_PURCHASE.value,
        SalesStage.HANDOFF.value,
    },
    SalesStage.HANDOFF.value: {
        SalesStage.HANDOFF.value,
    },
    SalesStage.UNKNOWN_RECOVERY.value: {
        SalesStage.UNKNOWN_RECOVERY.value,
        SalesStage.DISCOVERY.value,
        SalesStage.EDUCATING.value,
    },
}


class SalesStageTransitionService:
    def transition(
        self,
        *,
        lead_profile: Dict[str, Any],
        analysis: TurnAnalysis,
        sales_plan: SalesPlan,
    ) -> StageTransition:
        previous_stage, _previous_normalized = normalize_optional_stage(lead_profile.get("previous_stage"))
        stage_before_objection, _objection_normalized = normalize_optional_stage(
            lead_profile.get("stage_before_objection")
        )
        current_stage, normalized_from = normalize_stage(
            lead_profile.get("current_stage"), default=SalesStage.NEW.value
        )
        if lead_profile.get("current_stage") == SalesStage.OBJECTION_HANDLING.value:
            current_stage = stage_before_objection or previous_stage or SalesStage.DISCOVERY.value
            normalized_from = SalesStage.OBJECTION_HANDLING.value
        target_stage = sales_plan.target_stage
        if target_stage == SalesStage.OBJECTION_HANDLING.value:
            target_stage = stage_before_objection or previous_stage or current_stage or SalesStage.DISCOVERY.value

        allowed = is_transition_allowed(current_stage, target_stage, sales_plan)
        next_stage = target_stage if allowed else current_stage
        invalid_transition = None if allowed else f"{current_stage}->{target_stage}"

        if (
            sales_plan.macro_action == MacroAction.HANDLE_OBJECTION.value
            and sales_plan.objection_flow_step
            not in {ObjectionFlowStep.RESOLVED.value, ObjectionFlowStep.CLOSE_OR_CONTINUE.value}
            and not stage_before_objection
        ):
            stage_before_objection = current_stage

        if next_stage != current_stage:
            previous_stage = current_stage

        reason = sales_plan.commercial_goal
        if invalid_transition:
            reason = f"Invalid transition normalized to {current_stage}: {sales_plan.commercial_goal}"

        return StageTransition(
            current_stage=next_stage,
            previous_stage=previous_stage,
            stage_before_objection=stage_before_objection,
            conversation_mode=_conversation_mode(lead_profile, sales_plan),
            stage_reason_code=sales_plan.reason_code,
            stage_reason=reason,
            stage_changed=next_stage != current_stage,
            normalized_from=normalized_from,
            invalid_transition=invalid_transition,
        )


def is_transition_allowed(current_stage: str, target_stage: str, sales_plan: SalesPlan) -> bool:
    if current_stage == target_stage:
        return True
    if target_stage == SalesStage.OBJECTION_HANDLING.value:
        return False
    if current_stage == SalesStage.OBJECTION_HANDLING.value:
        return False
    if target_stage == SalesStage.CLOSING.value:
        return sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value
    if target_stage == SalesStage.HANDOFF.value:
        return sales_plan.macro_action == MacroAction.HANDOFF_TO_MIGUEL.value
    return target_stage in ALLOWED_TRANSITIONS.get(current_stage, set())


def normalize_stage(value: Any, default: str = SalesStage.NEW.value) -> Tuple[str, Optional[str]]:
    if value == SalesStage.OBJECTION_HANDLING.value:
        return default, SalesStage.OBJECTION_HANDLING.value
    if value in SalesStage.values():
        return str(value), None
    if value in V1_STAGE_MAP:
        return V1_STAGE_MAP[str(value)], str(value)
    if value in (None, ""):
        return default, None
    return SalesStage.UNKNOWN_RECOVERY.value, str(value)


def normalize_optional_stage(value: Any) -> Tuple[Optional[str], Optional[str]]:
    if value in (None, ""):
        return None, None
    stage, normalized_from = normalize_stage(value)
    return stage, normalized_from


def _conversation_mode(lead_profile: Dict[str, Any], sales_plan: SalesPlan) -> str:
    overlay = sales_plan.objection_overlay
    if overlay:
        if overlay.status == ObjectionStatus.RESOLVED.value:
            return ConversationMode.NORMAL.value
        if overlay.mode == ConversationMode.HANDLING_OBJECTION.value:
            return ConversationMode.HANDLING_OBJECTION.value
    if sales_plan.macro_action == MacroAction.HANDLE_OBJECTION.value and sales_plan.objection_flow_step not in {
        ObjectionFlowStep.RESOLVED.value,
        ObjectionFlowStep.CLOSE_OR_CONTINUE.value,
    }:
        return ConversationMode.HANDLING_OBJECTION.value
    active = active_objection_from_profile(lead_profile)
    if active.active and not active.resolved and active.strength == ObjectionStrength.HARD.value:
        return ConversationMode.HANDLING_OBJECTION.value
    return ConversationMode.NORMAL.value
