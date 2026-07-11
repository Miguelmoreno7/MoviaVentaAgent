from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from movia_sales_agent.agent.memory import build_structured_memory, next_question_for_missing_slot
from movia_sales_agent.agent.objections import active_objection_from_profile
from movia_sales_agent.agent.requirements import (
    active_external_action_count,
    derive_action_requirement,
    derive_product_fit,
    ensure_requirement_profile,
)
from movia_sales_agent.agent.rag_policy import build_rag_route
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    ConversationMode,
    CTAType,
    Intent,
    MacroAction,
    MicroAction,
    ObjectionFlowStep,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionStatus,
    ObjectionType,
    PlannerReasonCode,
    ProductFit,
    SalesStage,
    Topic,
)
from movia_sales_agent.models.schemas import KnowledgePlan, ObjectionOverlay, SalesPlan, TurnAnalysis


@dataclass(frozen=True)
class PlannerState:
    analysis: TurnAnalysis
    lead_profile: Dict[str, Any]
    normalized_turn: Dict[str, Any] = None
    current_stage: Optional[str] = None
    previous_stage: Optional[str] = None
    active_objection: Optional[Dict[str, Any]] = None
    last_macro_action: Optional[str] = None
    last_micro_action: Optional[str] = None
    last_cta: Optional[str] = None
    structured_memory: Dict[str, Any] = None
    action_requirement: str = ActionRequirement.UNKNOWN.value
    known_product_fit: str = ProductFit.UNKNOWN.value
    requirement_class: str = "unknown"
    requested_product: str = "none"
    recommended_product: Optional[str] = None
    confirmed_product: Optional[str] = None
    selected_product: Optional[str] = None
    product_preference_mismatch: bool = False
    scope_flags: List[str] = None
    active_external_action_count: Optional[int] = None
    known_slots: List[str] = None
    missing_slots: List[str] = None
    purchase_status: Dict[str, Any] = None
    message: str = ""


class SalesPolicyPlanner:
    def plan(
        self,
        analysis: TurnAnalysis,
        lead_profile: Dict[str, Any],
        *,
        current_stage: Optional[str] = None,
        previous_stage: Optional[str] = None,
        active_objection: Optional[Dict[str, Any]] = None,
        last_macro_action: Optional[str] = None,
        last_micro_action: Optional[str] = None,
        last_cta: Optional[str] = None,
        normalized_turn: Optional[Dict[str, Any]] = None,
        purchase_status: Optional[Dict[str, Any]] = None,
        message: str = "",
    ) -> SalesPlan:
        state = build_planner_state(
            analysis=analysis,
            lead_profile=lead_profile,
            current_stage=current_stage,
            previous_stage=previous_stage,
            active_objection=active_objection,
            last_macro_action=last_macro_action,
            last_micro_action=last_micro_action,
            last_cta=last_cta,
            normalized_turn=normalized_turn,
            purchase_status=purchase_status,
            message=message,
        )
        return self._plan_state(state)

    def _plan_state(self, state: PlannerState) -> SalesPlan:
        analysis = state.analysis
        if analysis.is_post_purchase:
            if not _post_purchase_handoff_allowed(state):
                return _finalize_plan(state, make_plan(
                    MacroAction.EXPLAIN_PROCESS,
                    MicroAction.EXPLAIN_HUMAN_HANDOFF,
                    "Explicar que el seguimiento personalizado se activa cuando el depósito queda confirmado.",
                    CTAType.NONE,
                    SalesStage.EDUCATING,
                    PlannerReasonCode.PROCESS_EXPLANATION_REQUESTED,
                ))
            return _finalize_plan(state, make_plan(
                MacroAction.HANDOFF_TO_MIGUEL,
                MicroAction.REDIRECT_POST_PURCHASE,
                "Enviar a soporte personalizado cuando el depósito o pago esté confirmado.",
                CTAType.REDIRECT_TO_MIGUEL,
                SalesStage.HANDOFF,
                PlannerReasonCode.POST_PURCHASE_HANDOFF,
            ))

        if _support_handoff_requested(state):
            return _finalize_plan(state, make_plan(
                MacroAction.HANDOFF_TO_MIGUEL,
                MicroAction.REDIRECT_EXISTING_CLIENT,
                "Redirigir a Miguel cuando el usuario ya es cliente o pide soporte humano.",
                CTAType.REDIRECT_TO_MIGUEL,
                SalesStage.HANDOFF,
                PlannerReasonCode.SUPPORT_HANDOFF,
            ))

        if _has_active_hard_objection(state) and _turn_resolves_active_objection(state):
            if not _should_process_current_intent_after_resolution(state):
                return _finalize_plan(state, make_plan(
                    MacroAction.HANDLE_OBJECTION,
                    MicroAction.CLOSE_OR_CONTINUE_OBJECTION,
                    "Cerrar semánticamente la objeción y retomar la etapa comercial previa.",
                    CTAType.SOFT_QUESTION,
                    _current_commercial_stage(state),
                    PlannerReasonCode.ACTIVE_OBJECTION_CONTINUATION,
                    objection_flow_step=ObjectionFlowStep.RESOLVED,
                ))

        if (
            _has_active_hard_objection(state)
            and not _turn_resolves_active_objection(state)
            and not _should_pause_active_objection(state)
        ):
            if _new_objection_replaces_active(state):
                return _finalize_plan(state, make_plan(
                    MacroAction.HANDLE_OBJECTION,
                    MicroAction.VALIDATE_AND_CLARIFY_OBJECTION,
                    "Atender la nueva objeción sin mezclarla con la anterior.",
                    CTAType.OBJECTION_QUESTION,
                    _current_commercial_stage(state),
                    PlannerReasonCode.NEW_HARD_OBJECTION
                    if analysis.objection_strength == ObjectionStrength.HARD.value
                    else PlannerReasonCode.NEW_SOFT_OBJECTION,
                    objection_flow_step=ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION,
                ))
            next_step = _semantic_active_objection_step(state)
            return _finalize_plan(state, make_plan(
                MacroAction.HANDLE_OBJECTION,
                _microaction_for_objection_step(next_step),
                _goal_for_objection_step(next_step),
                CTAType.OBJECTION_QUESTION,
                _current_commercial_stage(state),
                PlannerReasonCode.ACTIVE_OBJECTION_CONTINUATION,
                objection_flow_step=ObjectionFlowStep(next_step),
            ))

        if _has_new_hard_objection(analysis):
            return _finalize_plan(state, make_plan(
                MacroAction.HANDLE_OBJECTION,
                MicroAction.VALIDATE_AND_CLARIFY_OBJECTION,
                "Entender la objeción real antes de intentar avanzar.",
                CTAType.OBJECTION_QUESTION,
                _current_commercial_stage(state),
                PlannerReasonCode.NEW_HARD_OBJECTION,
                objection_flow_step=ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION,
            ))

        if analysis.explicit_start_intent and can_direct_close(state):
            return _finalize_plan(state, make_plan(
                MacroAction.DIRECT_CLOSE,
                MicroAction.SEND_APP_LINK_AND_DEPOSIT_STEP,
                "Guiar al inicio formal en la app con depósito del 50%.",
                CTAType.DIRECT_CLOSE,
                SalesStage.CLOSING,
                PlannerReasonCode.DIRECT_CLOSE_ALLOWED,
            ))

        if _is_first_touch_greeting(state):
            return _finalize_plan(state, make_plan(
                MacroAction.ANSWER_AND_ADVANCE,
                MicroAction.ANSWER_GENERAL_THEN_DISCOVER_NEED,
                "Dar una bienvenida breve y abrir una ruta suave antes de discovery comercial.",
                CTAType.SOFT_QUESTION,
                SalesStage.NEW,
                PlannerReasonCode.BUSINESS_TYPE_UNKNOWN,
                next_question="¿Vienes buscando información general o quieres cotizar algo específico?",
                next_question_key="entry_intent",
            ))

        unavailable_plan = _unavailable_product_plan(state)
        if unavailable_plan:
            return _finalize_plan(state, unavailable_plan)

        exact_plan = _exact_question_plan(state)
        if exact_plan:
            return _finalize_plan(state, exact_plan)

        unsupported_channel_plan = _unsupported_channel_plan(state)
        if unsupported_channel_plan:
            return _finalize_plan(state, unsupported_channel_plan)

        if _needs_risk_reversal(state):
            return _finalize_plan(state, make_plan(
                MacroAction.RISK_REVERSAL,
                _risk_reversal_microaction(state),
                "Reducir riesgo percibido con políticas y proceso oficial.",
                CTAType.SOFT_QUESTION,
                SalesStage.EDUCATING,
                PlannerReasonCode.POLICY_RISK_REVERSAL_REQUESTED,
            ))

        if Topic.PLATFORM_PROCESS.value in analysis.topics or Topic.ONBOARDING.value in analysis.topics:
            return _finalize_plan(state, make_plan(
                MacroAction.EXPLAIN_PROCESS,
                _process_microaction(analysis),
                "Resolver proceso y acercar al registro.",
                CTAType.EXPLAIN_NEXT_STEP,
                SalesStage.EDUCATING,
                PlannerReasonCode.PROCESS_EXPLANATION_REQUESTED,
            ))

        if Topic.COMPETITOR_COMPARISON.value in analysis.topics:
            return _finalize_plan(state, make_plan(
                MacroAction.COMPARE_ALTERNATIVE,
                _comparison_microaction(state),
                "Diferenciar MovIA contra la alternativa mencionada.",
                CTAType.DISCOVERY_QUESTION,
                SalesStage.COMPARING,
                PlannerReasonCode.COMPARISON_REQUESTED,
                next_question="¿Buscas solo responder preguntas o también necesitas acciones como agendar o registrar datos?",
                next_question_key="action_requirement",
            ))

        if _is_unknown_recovery(state):
            return _finalize_plan(state, make_plan(
                MacroAction.ANSWER_UNKNOWN_SAFELY,
                MicroAction.ASK_SINGLE_CLARIFYING_QUESTION,
                "Reconocer el límite y regresar a la necesidad de automatización.",
                CTAType.SOFT_QUESTION,
                SalesStage.UNKNOWN_RECOVERY,
                PlannerReasonCode.UNKNOWN_RECOVERY,
                next_question="¿Qué parte del flujo de atención quieres automatizar?",
                next_question_key="automation_need",
            ))

        if _must_discover_action_requirement(state):
            return _finalize_plan(state, _discovery_plan("action_requirement"))

        if analysis.skeptical_tone:
            return _finalize_plan(state, make_plan(
                MacroAction.PERSUADE_VALUE,
                MicroAction.LOGICAL_VALUE,
                "Explicar valor sin tratar el tono escéptico como una objeción dura.",
                CTAType.DISCOVERY_QUESTION,
                SalesStage.EDUCATING,
                PlannerReasonCode.SKEPTICAL_VALUE_NEEDED,
                next_question="¿Qué tipo de negocio tienes y qué te preocupa que el agente responda mal?",
                next_question_key="business_type",
            ))

        if _has_product_preference_mismatch(state):
            return _finalize_plan(state, make_plan(
                MacroAction.NARROW_SOLUTION,
                _narrow_microaction(state),
                "Aclarar la diferencia entre el producto pedido y el producto que cubre la necesidad.",
                CTAType.DISCOVERY_QUESTION,
                SalesStage.QUALIFIED,
                _narrow_reason_code(state),
                next_question="¿El agente solo debe responder/capturar datos o también hacer acciones como agendar, cotizar o registrar información?",
                next_question_key="action_requirement",
            ))

        recommendation_plan = _recommendation_plan(state)
        if recommendation_plan:
            return _finalize_plan(state, recommendation_plan)

        missing_key = _missing_core_discovery_key(state)
        if missing_key:
            return _finalize_plan(state, _discovery_plan(missing_key))

        if _can_soft_close(state):
            return _finalize_plan(state, make_plan(
                MacroAction.SOFT_CLOSE,
                MicroAction.ASK_PERMISSION_TO_SEND_LINK,
                "Avanzar con una invitación suave sin enviar link todavía.",
                CTAType.ASK_PERMISSION_TO_SEND_LINK,
                SalesStage.READY_TO_START,
                PlannerReasonCode.MEDIUM_HIGH_SIGNAL_SOFT_CLOSE,
            ))

        if _should_persuade_value(state):
            return _finalize_plan(state, make_plan(
                MacroAction.PERSUADE_VALUE,
                _persuasion_microaction(state),
                "Explicar el valor comercial antes de pedir avance.",
                CTAType.SOFT_QUESTION,
                SalesStage.EDUCATING,
                PlannerReasonCode.INDUSTRY_VALUE_NEEDED,
            ))

        return _finalize_plan(state, make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            _default_recommendation_microaction(state),
            "Recomendar el producto disponible más probable según la necesidad conocida.",
            CTAType.SOFT_CLOSE,
            SalesStage.SOLUTION_RECOMMENDED,
            PlannerReasonCode.DEFAULT_RECOMMENDATION,
        ))

def build_planner_state(
    *,
    analysis: TurnAnalysis,
    lead_profile: Dict[str, Any],
    normalized_turn: Optional[Dict[str, Any]] = None,
    current_stage: Optional[str] = None,
    previous_stage: Optional[str] = None,
    active_objection: Optional[Dict[str, Any]] = None,
    last_macro_action: Optional[str] = None,
    last_micro_action: Optional[str] = None,
    last_cta: Optional[str] = None,
    purchase_status: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> PlannerState:
    normalized_turn = normalized_turn or {}
    profile_data = _merged_profile_data(analysis, lead_profile)
    structured_memory = build_structured_memory(analysis, lead_profile)
    known_slots = structured_memory.get("known_slots") or {}
    stored_active_objection = lead_profile.get("active_objection") or profile_data.get("active_objection")
    action_requirement = _planner_action_requirement(normalized_turn, known_slots, profile_data)
    known_product_fit = _planner_product_fit(normalized_turn, known_slots, profile_data)
    requirement_profile = ensure_requirement_profile(profile_data)
    requirement_class = str(
        normalized_turn.get("requirement_class")
        or structured_memory.get("requirement_class")
        or requirement_profile.get("requirement_class")
        or "unknown"
    )
    effective_known_slots = _effective_known_slots(
        normalized_turn=normalized_turn,
        structured_known_slots=known_slots,
        action_requirement=action_requirement,
        requirement_class=requirement_class,
    )
    return PlannerState(
        analysis=analysis,
        lead_profile=lead_profile,
        normalized_turn=normalized_turn,
        current_stage=current_stage or lead_profile.get("current_stage"),
        previous_stage=previous_stage or lead_profile.get("previous_stage"),
        active_objection=active_objection or stored_active_objection,
        last_macro_action=last_macro_action or lead_profile.get("last_action"),
        last_micro_action=last_micro_action or profile_data.get("last_micro_action"),
        last_cta=last_cta or profile_data.get("last_cta"),
        structured_memory=structured_memory,
        action_requirement=action_requirement,
        known_product_fit=known_product_fit,
        requirement_class=requirement_class,
        requested_product=str(normalized_turn.get("requested_product") or "none"),
        recommended_product=_enum_or_default(
            normalized_turn.get("recommended_product"),
            ProductFit.values(),
            None,
        ),
        confirmed_product=str(
            normalized_turn.get("confirmed_product")
            or profile_data.get("confirmed_product")
            or ""
        )
        or None,
        selected_product=str(
            normalized_turn.get("selected_product")
            or profile_data.get("selected_product")
            or ""
        ),
        product_preference_mismatch=bool(normalized_turn.get("product_preference_mismatch")),
        scope_flags=list(
            normalized_turn.get("scope_flags")
            or structured_memory.get("scope_flags")
            or []
        ),
        active_external_action_count=(
            normalized_turn.get("declared_external_action_count")
            or structured_memory.get("active_external_action_count")
            or active_external_action_count(requirement_profile)
        ),
        known_slots=sorted(effective_known_slots),
        missing_slots=_effective_missing_slots(
            normalized_turn=normalized_turn,
            structured_memory=structured_memory,
            effective_known_slots=effective_known_slots,
        ),
        purchase_status=dict(purchase_status or {}),
        message=message,
    )


def can_direct_close(state: PlannerState) -> bool:
    if not state.analysis.explicit_start_intent:
        return False
    if state.analysis.is_post_purchase:
        return False
    committed_product = state.confirmed_product or state.selected_product
    if not committed_product:
        return False
    if committed_product not in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}:
        return False
    if state.known_product_fit not in {
        ProductFit.UNKNOWN.value,
        ProductFit.MOVIA_CAPTURA.value,
        ProductFit.MOVIA_HIBRIDO.value,
    }:
        return False
    if state.known_product_fit in {
        ProductFit.MOVIA_CAPTURA.value,
        ProductFit.MOVIA_HIBRIDO.value,
    } and state.known_product_fit != committed_product:
        return False
    if state.scope_flags and any(
        flag in set(state.scope_flags)
        for flag in ["unsupported_scope", "custom_scope_review_required", "product_preference_mismatch"]
    ):
        return False
    if (_has_active_hard_objection(state) and not _turn_resolves_active_objection(state)) or _has_new_hard_objection(state.analysis):
        return False
    return True


def make_plan(
    macro_action: MacroAction,
    micro_action: MicroAction,
    commercial_goal: str,
    cta_type: CTAType,
    target_stage: SalesStage,
    reason_code: PlannerReasonCode,
    *,
    next_question: Optional[str] = None,
    next_question_key: Optional[str] = None,
    objection_flow_step: ObjectionFlowStep = ObjectionFlowStep.NONE,
) -> SalesPlan:
    return SalesPlan(
        macro_action=macro_action,
        micro_action=micro_action,
        commercial_goal=commercial_goal,
        next_question=next_question,
        next_question_key=next_question_key,
        cta_type=cta_type,
        objection_flow_step=objection_flow_step,
        target_stage=target_stage,
        reason_code=reason_code,
    )


def _finalize_plan(state: PlannerState, plan: SalesPlan) -> SalesPlan:
    overlay = _objection_overlay_for_plan(state, plan)
    updates: Dict[str, Any] = {}
    if overlay:
        updates["objection_overlay"] = overlay
    question_updates = _question_contract_updates(state, plan)
    updates.update(question_updates)
    return plan.model_copy(update=updates) if updates else plan


def _question_contract_updates(state: PlannerState, plan: SalesPlan) -> Dict[str, Any]:
    if plan.cta_type not in {
        CTAType.DISCOVERY_QUESTION.value,
        CTAType.SOFT_QUESTION.value,
        CTAType.OBJECTION_QUESTION.value,
    }:
        return {}
    if plan.cta_type == CTAType.OBJECTION_QUESTION.value and not plan.next_question_key:
        return {
            "next_question": "¿Qué es lo que más te preocupa de ese punto?",
            "next_question_key": "objection_clarification",
        }
    if plan.next_question_key:
        if plan.next_question_key in set((state.structured_memory or {}).get("forbidden_question_keys") or []):
            question, key = next_question_for_missing_slot(state.structured_memory or {})
            if key:
                return {"next_question": question, "next_question_key": key}
            return {
                "cta_type": CTAType.NONE.value,
                "next_question": None,
                "next_question_key": None,
            }
        return {}
    question, key = next_question_for_missing_slot(state.structured_memory or {})
    if key:
        return {"next_question": question, "next_question_key": key}
    return {
        "cta_type": CTAType.NONE.value,
        "next_question": None,
        "next_question_key": None,
    }


def _support_handoff_requested(state: PlannerState) -> bool:
    analysis = state.analysis
    if analysis.primary_intent != Intent.SUPPORT_REQUEST.value:
        return False
    profile_data = _merged_profile_data(analysis, state.lead_profile)
    return bool(profile_data.get("existing_client")) or state.current_stage in {
        SalesStage.POST_PURCHASE.value,
        SalesStage.HANDOFF.value,
        "post_purchase",
        "handoff",
    }


def _has_active_objection(state: PlannerState) -> bool:
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    return active.active and not active.resolved


def _has_active_hard_objection(state: PlannerState) -> bool:
    if not _has_active_objection(state):
        return False
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    return active.strength == ObjectionStrength.HARD.value


def _should_pause_active_objection(state: PlannerState) -> bool:
    analysis = state.analysis
    if analysis.has_objection or analysis.explicit_start_intent:
        return False
    if analysis.objection_relation == ObjectionRelation.RESOLVED.value:
        return False
    return analysis.primary_intent in {
        Intent.PRICING_QUESTION.value,
        Intent.CHEAPEST_PLAN_QUESTION.value,
        Intent.PRODUCT_SCOPE_QUESTION.value,
        Intent.PLATFORM_STEPS_QUESTION.value,
        Intent.ONBOARDING_QUESTION.value,
        Intent.POLICY_QUESTION.value,
        Intent.CHANNEL_QUESTION.value,
        Intent.INTEGRATION_QUESTION.value,
        Intent.COMPARISON_QUESTION.value,
    }


def _turn_resolves_active_objection(state: PlannerState) -> bool:
    analysis = state.analysis
    if not _has_active_hard_objection(state):
        return False
    if analysis.has_objection:
        return False
    return analysis.objection_relation == ObjectionRelation.RESOLVED.value


def _should_process_current_intent_after_resolution(state: PlannerState) -> bool:
    analysis = state.analysis
    return analysis.explicit_start_intent or analysis.primary_intent in {
        Intent.PRICING_QUESTION.value,
        Intent.CHEAPEST_PLAN_QUESTION.value,
        Intent.PRODUCT_SCOPE_QUESTION.value,
        Intent.PRODUCT_RECOMMENDATION_QUESTION.value,
        Intent.PLATFORM_STEPS_QUESTION.value,
        Intent.ONBOARDING_QUESTION.value,
        Intent.POLICY_QUESTION.value,
        Intent.CHANNEL_QUESTION.value,
        Intent.INTEGRATION_QUESTION.value,
        Intent.COMPARISON_QUESTION.value,
        Intent.INDUSTRY_FIT_QUESTION.value,
    }


def _new_objection_replaces_active(state: PlannerState) -> bool:
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    analysis = state.analysis
    return (
        active.active
        and analysis.has_objection
        and analysis.objection_type != ObjectionType.NONE.value
        and analysis.objection_type != active.type
    )


def _semantic_active_objection_step(state: PlannerState) -> str:
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    relation = state.analysis.objection_relation
    text = state.message.lower()

    if relation == ObjectionRelation.RESOLVED.value:
        return ObjectionFlowStep.RESOLVED.value
    if _contains_any_text(text, ["demuestr", "muéstrame", "muestrame", "prueba", "evidencia", "caso real"]):
        return ObjectionFlowStep.PROVIDE_PROOF.value
    if relation == ObjectionRelation.CLARIFIED.value:
        if active.current_step in {
            ObjectionFlowStep.NONE.value,
            ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value,
        }:
            return ObjectionFlowStep.CLARIFY_VALUE.value
        return ObjectionFlowStep.TIE_SOLUTION.value
    if relation in {ObjectionRelation.CONTINUATION.value, ObjectionRelation.REAFFIRMED.value}:
        if active.current_step in {
            ObjectionFlowStep.NONE.value,
            ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value,
        }:
            return ObjectionFlowStep.CLARIFY_VALUE.value
        return active.current_step
    if _contains_any_text(text, ["recuperar tiempo", "ahorrar tiempo", "equipo", "seguimiento", "vale la pena"]):
        return ObjectionFlowStep.TIE_SOLUTION.value
    if active.current_step == ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value:
        return ObjectionFlowStep.CLARIFY_VALUE.value
    if active.current_step in {ObjectionFlowStep.NONE.value, ObjectionFlowStep.RESOLVED.value}:
        return ObjectionFlowStep.CLARIFY_VALUE.value
    return active.current_step


def _microaction_for_objection_step(step: str) -> MicroAction:
    return {
        ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value: MicroAction.VALIDATE_AND_CLARIFY_OBJECTION,
        ObjectionFlowStep.CLARIFY_VALUE.value: MicroAction.CLARIFY_OBJECTION_VALUE,
        ObjectionFlowStep.TIE_SOLUTION.value: MicroAction.TIE_SOLUTION_TO_OBJECTION,
        ObjectionFlowStep.PROVIDE_PROOF.value: MicroAction.PROVIDE_OBJECTION_PROOF,
        ObjectionFlowStep.CLOSE_OR_CONTINUE.value: MicroAction.CLOSE_OR_CONTINUE_OBJECTION,
        ObjectionFlowStep.RESOLVED.value: MicroAction.CLOSE_OR_CONTINUE_OBJECTION,
    }.get(step, MicroAction.CLARIFY_OBJECTION_VALUE)


def _goal_for_objection_step(step: str) -> str:
    return {
        ObjectionFlowStep.CLARIFY_VALUE.value: "Clarificar si el bloqueo es valor, confianza, alcance o timing.",
        ObjectionFlowStep.TIE_SOLUTION.value: "Conectar la capacidad correcta de MovIA con la objeción real.",
        ObjectionFlowStep.PROVIDE_PROOF.value: "Dar evidencia segura sin inventar testimonios ni resultados.",
        ObjectionFlowStep.CLOSE_OR_CONTINUE.value: "Cerrar la objeción o decidir si conviene seguir descubriendo.",
    }.get(step, "Continuar la objeción activa sin reiniciar la conversación.")


def _target_stage_for_objection_step(state: PlannerState, step: str) -> SalesStage:
    return _current_commercial_stage(state)


def _current_commercial_stage(state: PlannerState) -> SalesStage:
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    candidate = (
        active.stage_before_objection
        or state.current_stage
        or state.previous_stage
        or SalesStage.DISCOVERY.value
    )
    if candidate == SalesStage.OBJECTION_HANDLING.value:
        candidate = state.previous_stage or active.stage_before_objection or SalesStage.DISCOVERY.value
    return _stage_enum(candidate)


def _stage_enum(value: Any) -> SalesStage:
    if value == SalesStage.OBJECTION_HANDLING.value:
        return SalesStage.DISCOVERY
    if value in SalesStage.values():
        return SalesStage(str(value))
    return SalesStage.DISCOVERY


def _has_new_hard_objection(analysis: TurnAnalysis) -> bool:
    return (
        analysis.has_objection
        and analysis.objection_type != ObjectionType.NONE.value
        and analysis.objection_strength == ObjectionStrength.HARD.value
    )


def _has_new_soft_objection(analysis: TurnAnalysis) -> bool:
    return (
        analysis.has_objection
        and analysis.objection_type != ObjectionType.NONE.value
        and analysis.objection_strength != ObjectionStrength.HARD.value
    )


def _objection_overlay_for_plan(state: PlannerState, plan: SalesPlan) -> Optional[ObjectionOverlay]:
    active = active_objection_from_profile({"active_objection": state.active_objection or {}})
    analysis = state.analysis

    if _has_new_hard_objection(analysis):
        return ObjectionOverlay(
            mode=ConversationMode.HANDLING_OBJECTION,
            relation=ObjectionRelation.NEW,
            type=analysis.objection_type,
            strength=analysis.objection_strength,
            status=ObjectionStatus.ACTIVE,
            current_step=plan.objection_flow_step,
            blocking_close=True,
            response_instruction="Atiendan la objeción como bloqueo real sin cambiar la etapa comercial principal.",
        )

    if active.active and not active.resolved and active.strength == ObjectionStrength.HARD.value:
        if plan.objection_flow_step == ObjectionFlowStep.RESOLVED.value or _turn_resolves_active_objection(state):
            return ObjectionOverlay(
                mode=ConversationMode.NORMAL,
                relation=ObjectionRelation.RESOLVED,
                type=active.type,
                strength=active.strength,
                status=ObjectionStatus.RESOLVED,
                current_step=ObjectionFlowStep.RESOLVED,
                blocking_close=False,
                response_instruction="Cierra la preocupación brevemente y retoma la conversación comercial sin reiniciar etapa.",
            )
        if plan.macro_action == MacroAction.HANDLE_OBJECTION.value:
            return ObjectionOverlay(
                mode=ConversationMode.HANDLING_OBJECTION,
                relation=_overlay_relation(analysis, ObjectionRelation.CONTINUATION.value),
                type=active.type,
                strength=active.strength,
                status=ObjectionStatus.ACTIVE,
                current_step=plan.objection_flow_step or active.current_step,
                blocking_close=True,
                response_instruction="La objeción dura sigue abierta; no cierres venta hasta resolverla.",
            )
        return ObjectionOverlay(
            mode=ConversationMode.HANDLING_OBJECTION,
            relation=_overlay_relation(analysis, ObjectionRelation.UNRELATED.value),
            type=active.type,
            strength=active.strength,
            status=ObjectionStatus.PAUSED,
            current_step=active.current_step,
            inline=True,
            blocking_close=True,
            response_instruction="Responde primero la intención actual y menciona de forma breve que la preocupación queda pendiente.",
        )

    if _has_new_soft_objection(analysis):
        return ObjectionOverlay(
            mode=ConversationMode.NORMAL,
            relation=ObjectionRelation.NEW,
            type=analysis.objection_type,
            strength=analysis.objection_strength,
            status=ObjectionStatus.NONE,
            inline=True,
            blocking_close=False,
            response_instruction="Reconoce la preocupación en una frase y sigue con la acción principal del turno.",
        )

    if analysis.skeptical_tone:
        return ObjectionOverlay(
            mode=ConversationMode.NORMAL,
            relation=ObjectionRelation.NONE,
            type=ObjectionType.NONE,
            strength=ObjectionStrength.SOFT,
            status=ObjectionStatus.NONE,
            inline=True,
            blocking_close=False,
            response_instruction="Baja la fricción del tono escéptico sin tratarlo como objeción persistente.",
        )

    return None


def _overlay_relation(analysis: TurnAnalysis, default: str) -> str:
    if analysis.objection_relation and analysis.objection_relation != ObjectionRelation.NONE.value:
        return analysis.objection_relation
    return default


def _unavailable_product_plan(state: PlannerState) -> Optional[SalesPlan]:
    if state.known_product_fit == ProductFit.MOVIA_VENTAS_UNAVAILABLE.value:
        return make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            MicroAction.EXPLAIN_VENTAS_NOT_AVAILABLE,
            "Redirigir a MovIA Captura o MovIA Híbrido sin abrir productos no activos.",
            CTAType.SOFT_QUESTION,
            SalesStage.EDUCATING,
            PlannerReasonCode.SALES_PRODUCT_UNAVAILABLE,
        )
    if state.known_product_fit == ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value:
        return make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            MicroAction.EXPLAIN_PRO_COMERCIAL_NOT_AVAILABLE,
            "Redirigir a MovIA Captura o MovIA Híbrido, o a revisión humana si el alcance es personalizado.",
            CTAType.SOFT_QUESTION,
            SalesStage.EDUCATING,
            PlannerReasonCode.PRO_PRODUCT_UNAVAILABLE,
        )
    if state.known_product_fit == ProductFit.CUSTOM_REVIEW.value:
        return make_plan(
            MacroAction.HANDOFF_TO_MIGUEL,
            MicroAction.REDIRECT_CUSTOM_SCOPE,
            "Redirigir un alcance personalizado para revisión humana.",
            CTAType.REDIRECT_TO_MIGUEL,
            SalesStage.HANDOFF,
            PlannerReasonCode.CUSTOM_SCOPE_REVIEW,
        )
    return None


def _exact_question_plan(state: PlannerState) -> Optional[SalesPlan]:
    analysis = state.analysis
    if analysis.primary_intent in {
        Intent.PRICING_QUESTION.value,
        Intent.CHEAPEST_PLAN_QUESTION.value,
    }:
        missing_key = _missing_core_discovery_key(state)
        return make_plan(
            MacroAction.ANSWER_AND_ADVANCE,
            MicroAction.ANSWER_PRICE_THEN_EXPLAIN_SCOPE,
            "Responder precio exacto y avanzar una pregunta de descubrimiento si falta contexto.",
            CTAType.SOFT_QUESTION,
            SalesStage.EDUCATING,
            PlannerReasonCode.PRICE_QUESTION_WITH_DISCOVERY_GAP,
            next_question=_question_for_key(missing_key),
            next_question_key=missing_key,
        )
    if analysis.primary_intent == Intent.CHANNEL_QUESTION.value:
        missing_key = _missing_core_discovery_key(state)
        return make_plan(
            MacroAction.ANSWER_AND_ADVANCE,
            MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL,
            "Responder disponibilidad de canal y avanzar descubrimiento.",
            CTAType.SOFT_QUESTION,
            SalesStage.EDUCATING,
            PlannerReasonCode.CHANNEL_QUESTION_WITH_DISCOVERY_GAP,
            next_question=_question_for_key(missing_key),
            next_question_key=missing_key,
        )
    if (
        analysis.primary_intent == Intent.PRODUCT_SCOPE_QUESTION.value
        and state.action_requirement != ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    ):
        missing_key = _missing_core_discovery_key(state)
        return make_plan(
            MacroAction.ANSWER_AND_ADVANCE,
            MicroAction.ANSWER_SCOPE_THEN_DISCOVER_BUSINESS,
            "Responder alcance exacto sin vender acciones no soportadas.",
            CTAType.SOFT_QUESTION,
            SalesStage.EDUCATING,
            PlannerReasonCode.SCOPE_QUESTION_WITH_DISCOVERY_GAP,
            next_question=_question_for_key(missing_key),
            next_question_key=missing_key,
        )
    return None


def _unsupported_channel_plan(state: PlannerState) -> Optional[SalesPlan]:
    if not _unsupported_channel_requested_without_whatsapp(state):
        return None
    missing_key = _missing_core_discovery_key(state)
    return make_plan(
        MacroAction.ANSWER_AND_ADVANCE,
        MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL,
        "Aclarar que hoy solo WhatsApp Business está disponible y no vender canales próximos como activos.",
        CTAType.SOFT_QUESTION,
        SalesStage.EDUCATING,
        PlannerReasonCode.CHANNEL_QUESTION_WITH_DISCOVERY_GAP,
        next_question=_question_for_key(missing_key),
        next_question_key=missing_key,
    )


def _unsupported_channel_requested_without_whatsapp(state: PlannerState) -> bool:
    values = [
        state.analysis.main_channel,
        state.analysis.lead_updates.main_channel,
        (state.normalized_turn or {}).get("known_slot_values", {}).get("main_channel"),
        state.message,
    ]
    text = " ".join(str(value or "") for value in values).lower()
    if "whatsapp" in text:
        return False
    return "instagram" in text or "facebook" in text


def _needs_risk_reversal(state: PlannerState) -> bool:
    topics = state.analysis.topics
    return any(
        topic in topics
        for topic in [
            Topic.REFUND_POLICY.value,
            Topic.CLIENT_REVIEW.value,
            Topic.SUPPORT.value,
            Topic.DEPOSIT.value,
            Topic.FINAL_PAYMENT.value,
        ]
    )


def _risk_reversal_microaction(state: PlannerState) -> MicroAction:
    topics = state.analysis.topics
    if Topic.CLIENT_REVIEW.value in topics:
        return MicroAction.EXPLAIN_CLIENT_REVIEW
    if Topic.SUPPORT.value in topics:
        return MicroAction.EXPLAIN_HUMAN_HANDOFF
    if Topic.WHATSAPP.value in topics or Topic.INTEGRATION.value in topics:
        return MicroAction.EXPLAIN_OFFICIAL_META_CONNECTION
    return MicroAction.EXPLAIN_TESTING_BEFORE_RELEASE


def _process_microaction(analysis: TurnAnalysis) -> MicroAction:
    if Topic.DOCUMENTS.value in analysis.topics:
        return MicroAction.EXPLAIN_DOCUMENTS
    if Topic.CONVERSATION_EXAMPLES.value in analysis.topics:
        return MicroAction.EXPLAIN_CONVERSATION_EXAMPLES
    if Topic.CLIENT_REVIEW.value in analysis.topics:
        return MicroAction.EXPLAIN_CLIENT_REVIEW
    if Topic.ACTIVATION.value in analysis.topics:
        return MicroAction.EXPLAIN_ACTIVATION
    if Topic.DEPOSIT.value in analysis.topics:
        return MicroAction.EXPLAIN_DEPOSIT
    return MicroAction.EXPLAIN_APP_REGISTRATION


def _comparison_microaction(state: PlannerState) -> MicroAction:
    text = state.message.lower()
    if "whatsapp business" in text:
        return MicroAction.COMPARE_WHATSAPP_BUSINESS_ONLY
    if "recepcionista" in text:
        return MicroAction.COMPARE_HUMAN_RECEPTIONIST
    if "desarrollo" in text or "custom" in text:
        return MicroAction.COMPARE_CUSTOM_DEVELOPMENT
    if "chatbot" in text and "manychat" not in text:
        return MicroAction.COMPARE_BASIC_CHATBOT
    return MicroAction.COMPARE_MANYCHAT


def _is_unknown_recovery(state: PlannerState) -> bool:
    analysis = state.analysis
    if analysis.skeptical_tone:
        return False
    return analysis.primary_intent == Intent.UNKNOWN.value or (
        Topic.UNKNOWN.value in analysis.topics and len(analysis.topics) == 1
    )


def _should_narrow_solution(state: PlannerState) -> bool:
    return _has_product_preference_mismatch(state)


def _narrow_microaction(state: PlannerState) -> MicroAction:
    if _has_product_preference_mismatch(state):
        return MicroAction.DIFFERENTIATE_CAPTURA_VS_HIBRIDO
    if state.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
        return MicroAction.DETERMINE_IF_EXTERNAL_ACTIONS_ARE_NEEDED
    return MicroAction.DIFFERENTIATE_CAPTURA_VS_HIBRIDO


def _narrow_reason_code(state: PlannerState) -> PlannerReasonCode:
    if state.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
        return PlannerReasonCode.EXTERNAL_ACTIONS_HIBRIDO_FIT
    if state.action_requirement == ActionRequirement.ANSWERS_ONLY.value:
        return PlannerReasonCode.ANSWERS_ONLY_CAPTURA_FIT
    return PlannerReasonCode.ACTION_REQUIREMENT_UNKNOWN


def _missing_core_discovery_key(state: PlannerState) -> Optional[str]:
    known_slots = (state.structured_memory or {}).get("known_slots") or {}
    if "business_type" not in known_slots and not _known_business_type(state):
        return "business_type"
    if "main_channel" not in known_slots and not _known_main_channel(state):
        return "main_channel"
    if "pain_or_goal" not in known_slots and not _known_pain(state):
        return "pain_or_goal"
    if not _known_action_requirement(state):
        return "action_requirement"
    return None


def _is_first_touch_greeting(state: PlannerState) -> bool:
    if state.analysis.primary_intent != Intent.GREETING.value:
        return False
    if state.last_macro_action:
        return False
    meaningful_topics = [topic for topic in state.analysis.topics if topic != Topic.UNKNOWN.value]
    if meaningful_topics:
        return False
    current_stage = state.current_stage or state.lead_profile.get("current_stage")
    if current_stage and current_stage not in {SalesStage.NEW.value, SalesStage.UNKNOWN_RECOVERY.value}:
        return False
    if _has_meaningful_active_objection(state.active_objection):
        return False
    known_slots = (state.structured_memory or {}).get("known_slots") or {}
    if known_slots:
        return False
    profile_data = state.lead_profile.get("profile_data") or {}
    if profile_data.get("action_requirement") or profile_data.get("known_product_fit"):
        return False
    if _has_non_empty_requirement_profile(profile_data.get("requirement_profile")):
        return False
    if _has_non_empty_product_context(profile_data.get("product_context")):
        return False
    return True


def _has_meaningful_active_objection(active_objection: Any) -> bool:
    if not isinstance(active_objection, dict):
        return False
    return bool(
        active_objection.get("active")
        or active_objection.get("paused")
        or active_objection.get("status") in {ObjectionStatus.ACTIVE.value, ObjectionStatus.PAUSED.value}
    )


def _has_non_empty_requirement_profile(requirement_profile: Any) -> bool:
    if not isinstance(requirement_profile, dict):
        return False
    if requirement_profile.get("requirement_class") not in {None, "", "unknown"}:
        return True
    if requirement_profile.get("declared_external_action_count") is not None:
        return True
    for key in (
        "observed_business_problems",
        "informational_capabilities",
        "sales_capabilities",
        "external_actions",
    ):
        if requirement_profile.get(key):
            return True
    return False


def _has_non_empty_product_context(product_context: Any) -> bool:
    if not isinstance(product_context, dict):
        return False
    return any(
        product_context.get(key)
        for key in (
            "referenced_product",
            "active_product_context",
            "selected_product",
            "confirmed_product",
        )
    )


def _discovery_plan(missing_key: str) -> SalesPlan:
    microaction_by_key = {
        "business_type": MicroAction.ASK_BUSINESS_TYPE,
        "main_channel": MicroAction.ASK_MAIN_CHANNEL,
        "pain_or_goal": MicroAction.ASK_PAIN_OR_GOAL,
        "action_requirement": MicroAction.ASK_ACTION_REQUIREMENT,
    }
    reason_by_key = {
        "business_type": PlannerReasonCode.BUSINESS_TYPE_UNKNOWN,
        "main_channel": PlannerReasonCode.MAIN_CHANNEL_UNKNOWN,
        "pain_or_goal": PlannerReasonCode.PAIN_OR_GOAL_UNKNOWN,
        "action_requirement": PlannerReasonCode.ACTION_REQUIREMENT_UNKNOWN,
    }
    return make_plan(
        MacroAction.DISCOVER_NEED,
        microaction_by_key[missing_key],
        "Obtener el siguiente dato mínimo de descubrimiento.",
        CTAType.DISCOVERY_QUESTION,
        SalesStage.DISCOVERY,
        reason_by_key[missing_key],
        next_question=_question_for_key(missing_key),
        next_question_key=missing_key,
    )


def _recommendation_plan(state: PlannerState) -> Optional[SalesPlan]:
    if _recommendation_already_communicated(state):
        return None
    product_fit = _recommendable_product_fit(state)
    if product_fit == ProductFit.MOVIA_CAPTURA.value:
        return make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            MicroAction.RECOMMEND_MOVIA_CAPTURA,
            "Recomendar Captura para responder, capturar y filtrar leads.",
            CTAType.ASK_PERMISSION_TO_SEND_LINK,
            SalesStage.SOLUTION_RECOMMENDED,
            PlannerReasonCode.ANSWERS_ONLY_CAPTURA_FIT,
        )
    if product_fit == ProductFit.MOVIA_HIBRIDO.value and not _should_narrow_solution(state):
        return make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            MicroAction.RECOMMEND_MOVIA_HIBRIDO,
            "Recomendar Híbrido cuando se requieren acciones externas simples.",
            CTAType.ASK_PERMISSION_TO_SEND_LINK,
            SalesStage.SOLUTION_RECOMMENDED,
            PlannerReasonCode.EXTERNAL_ACTIONS_HIBRIDO_FIT,
        )
    if (
        state.analysis.primary_intent == Intent.PRODUCT_RECOMMENDATION_QUESTION.value
        and state.action_requirement != ActionRequirement.UNKNOWN.value
    ):
        return make_plan(
            MacroAction.RECOMMEND_SOLUTION,
            _default_recommendation_microaction(state),
            "Responder una solicitud directa de recomendación con producto disponible.",
            CTAType.SOFT_CLOSE,
            SalesStage.SOLUTION_RECOMMENDED,
            PlannerReasonCode.RECOMMENDATION_READY,
        )
    return None


def _recommendation_already_communicated(state: PlannerState) -> bool:
    return (
        state.last_macro_action == MacroAction.RECOMMEND_SOLUTION.value
        or state.current_stage in {SalesStage.SOLUTION_RECOMMENDED.value, "recommended"}
    )


def _should_persuade_value(state: PlannerState) -> bool:
    topics = state.analysis.topics
    return any(topic in topics for topic in [Topic.BUSINESS_FIT.value, Topic.INDUSTRY_USE_CASE.value, Topic.DEMO.value])


def _persuasion_microaction(state: PlannerState) -> MicroAction:
    if state.analysis.business_type or _known_business_type(state):
        return MicroAction.INDUSTRY_SPECIFIC_VALUE
    if _known_pain(state):
        return MicroAction.OPPORTUNITY_COST
    return MicroAction.LOGICAL_VALUE


def _can_soft_close(state: PlannerState) -> bool:
    return (
        state.analysis.buying_signal in {BuyingSignal.MEDIUM.value, BuyingSignal.HIGH.value}
        and state.known_product_fit in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}
        and (
            state.last_macro_action == MacroAction.RECOMMEND_SOLUTION.value
            or state.current_stage in {SalesStage.SOLUTION_RECOMMENDED.value, "recommended"}
        )
        and not _has_active_hard_objection(state)
        and not _has_new_hard_objection(state.analysis)
        and not state.analysis.has_objection
    )


def _default_recommendation_microaction(state: PlannerState) -> MicroAction:
    if state.known_product_fit == ProductFit.MOVIA_HIBRIDO.value:
        return MicroAction.RECOMMEND_MOVIA_HIBRIDO
    if state.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
        return MicroAction.RECOMMEND_MOVIA_HIBRIDO
    return MicroAction.RECOMMEND_MOVIA_CAPTURA


def _question_for_key(key: Optional[str]) -> Optional[str]:
    questions = {
        "business_type": "¿Qué tipo de negocio tienes?",
        "main_channel": "¿Por dónde te escriben más tus clientes: WhatsApp, Facebook o Instagram?",
        "pain_or_goal": "¿Qué quieres mejorar primero: responder más rápido, filtrar leads o registrar datos?",
        "action_requirement": "¿El agente solo debe responder/capturar datos o también hacer acciones como agendar, cotizar o registrar información?",
        "process_or_demo": "¿Quieres que te explique el proceso para iniciar o prefieres ver el demo?",
    }
    return questions.get(key or "")


def _known_business_type(state: PlannerState) -> Optional[str]:
    return state.analysis.business_type or state.lead_profile.get("business_type")


def _known_main_channel(state: PlannerState) -> Optional[str]:
    return state.analysis.main_channel or state.lead_profile.get("main_channel")


def _known_pain(state: PlannerState) -> Optional[str]:
    return state.analysis.pain or state.lead_profile.get("pain")


def _merged_profile_data(analysis: TurnAnalysis, lead_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **dict(lead_profile.get("profile_data") or {}),
        **dict(analysis.lead_updates.profile_data or {}),
    }


def _planner_action_requirement(
    normalized_turn: Dict[str, Any],
    known_slots: Dict[str, Any],
    profile_data: Dict[str, Any],
) -> str:
    requirement_profile = ensure_requirement_profile(profile_data)
    profile_requirement = derive_action_requirement(requirement_profile.get("requirement_class"))
    if profile_requirement == ActionRequirement.UNKNOWN.value:
        profile_requirement = None
    normalized_requirement = normalized_turn.get("action_requirement")
    if normalized_requirement == ActionRequirement.UNKNOWN.value:
        normalized_requirement = None
    return _enum_or_default(
        normalized_requirement
        or known_slots.get("action_requirement")
        or profile_requirement
        or profile_data.get("action_requirement"),
        ActionRequirement.values(),
        ActionRequirement.UNKNOWN.value,
    )


def _planner_product_fit(
    normalized_turn: Dict[str, Any],
    known_slots: Dict[str, Any],
    profile_data: Dict[str, Any],
) -> str:
    requirement_profile = ensure_requirement_profile(profile_data)
    requested = str(normalized_turn.get("requested_product") or "")
    if requested == "movia_ventas":
        return ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    if requested == "movia_pro_comercial":
        return ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value

    normalized_fit = _enum_or_default(
        normalized_turn.get("recommended_product"),
        ProductFit.values(),
        None,
    )
    if normalized_fit == ProductFit.UNKNOWN.value:
        normalized_fit = None
    if normalized_fit:
        return normalized_fit
    profile_fit = derive_product_fit(requirement_profile)
    if profile_fit == ProductFit.UNKNOWN.value:
        profile_fit = None
    product_context = dict(normalized_turn.get("product_context") or profile_data.get("product_context") or {})
    committed_product = _enum_or_default(
        normalized_turn.get("confirmed_product")
        or normalized_turn.get("selected_product")
        or product_context.get("confirmed_product")
        or product_context.get("selected_product")
        or profile_data.get("confirmed_product")
        or profile_data.get("selected_product"),
        [ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value],
        None,
    )

    return _enum_or_default(
        known_slots.get("known_product_fit")
        or profile_fit
        or committed_product
        or profile_data.get("known_product_fit"),
        ProductFit.values(),
        ProductFit.UNKNOWN.value,
    )


def _effective_known_slots(
    *,
    normalized_turn: Dict[str, Any],
    structured_known_slots: Dict[str, Any],
    action_requirement: str,
    requirement_class: str,
) -> set:
    known = set(structured_known_slots.keys())
    known.update(str(slot) for slot in normalized_turn.get("known_slots") or [])
    if (
        action_requirement != ActionRequirement.UNKNOWN.value
        or str(requirement_class or "unknown") != "unknown"
        or _active_product_context(normalized_turn) == ProductFit.MOVIA_HIBRIDO.value
    ):
        known.add("action_requirement")
    return known


def _effective_missing_slots(
    *,
    normalized_turn: Dict[str, Any],
    structured_memory: Dict[str, Any],
    effective_known_slots: set,
) -> List[str]:
    ordered = ["business_type", "main_channel", "pain_or_goal", "action_requirement"]
    raw_missing = list(
        normalized_turn.get("missing_slots")
        or structured_memory.get("missing_slots")
        or ordered
    )
    return [
        slot
        for slot in ordered
        if slot in raw_missing and slot not in effective_known_slots
    ]


def _known_action_requirement(state: PlannerState) -> bool:
    if state.action_requirement != ActionRequirement.UNKNOWN.value:
        return True
    if str(state.requirement_class or "unknown") != "unknown":
        return True
    if state.known_product_fit == ProductFit.MOVIA_HIBRIDO.value:
        return True
    if _active_product_context(state.normalized_turn or {}) == ProductFit.MOVIA_HIBRIDO.value:
        return True
    memory_profile = ensure_requirement_profile(
        {"requirement_profile": (state.structured_memory or {}).get("requirement_profile") or {}}
    )
    return str(memory_profile.get("requirement_class") or "unknown") != "unknown"


def _active_product_context(normalized_turn: Dict[str, Any]) -> Optional[str]:
    product_context = dict(normalized_turn.get("product_context") or {})
    product = str(
        normalized_turn.get("active_product_context")
        or product_context.get("active_product_context")
        or ""
    )
    if product in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}:
        return product
    return None


def _post_purchase_handoff_allowed(state: PlannerState) -> bool:
    return str((state.purchase_status or {}).get("status") or "") in {
        "deposit_confirmed",
        "paid_in_full",
    }


def _must_discover_action_requirement(state: PlannerState) -> bool:
    if _known_action_requirement(state):
        return False
    if state.analysis.primary_intent in {
        Intent.PRODUCT_RECOMMENDATION_QUESTION.value,
        Intent.PRODUCT_SCOPE_QUESTION.value,
    }:
        return True
    if _known_pain(state) and (
        _known_business_type(state)
        or _known_main_channel(state)
        or state.current_stage in {SalesStage.DISCOVERY.value, SalesStage.EDUCATING.value}
    ):
        return True
    return False


def _has_product_preference_mismatch(state: PlannerState) -> bool:
    if state.product_preference_mismatch:
        return True
    requested = state.requested_product
    if requested == "movia_captura" and state.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
        return True
    if requested == "movia_hibrido" and state.action_requirement == ActionRequirement.ANSWERS_ONLY.value:
        return True
    return False


def _recommendable_product_fit(state: PlannerState) -> str:
    if _has_product_preference_mismatch(state):
        return ProductFit.UNKNOWN.value
    if state.recommended_product in {
        ProductFit.MOVIA_CAPTURA.value,
        ProductFit.MOVIA_HIBRIDO.value,
    }:
        return state.recommended_product
    if state.known_product_fit in {
        ProductFit.MOVIA_CAPTURA.value,
        ProductFit.MOVIA_HIBRIDO.value,
    }:
        return state.known_product_fit
    return ProductFit.UNKNOWN.value


def _enum_or_default(value: Any, allowed: List[str], default: str) -> str:
    if value in allowed:
        return str(value)
    return default


def _contains_any_text(text: str, needles: List[str]) -> bool:
    return any(needle in text for needle in needles)


class KnowledgePlanner:
    def plan(
        self,
        analysis: TurnAnalysis,
        sales_plan: SalesPlan,
        message: str,
        active_objection: Optional[Dict[str, Any]] = None,
        normalized_turn: Optional[Dict[str, Any]] = None,
        lead_profile: Optional[Dict[str, Any]] = None,
        response_fulfillment_policy: Optional[Dict[str, Any]] = None,
    ) -> KnowledgePlan:
        normalized_turn = normalized_turn or {}
        lead_profile = lead_profile or {}
        response_fulfillment_policy = response_fulfillment_policy or {}
        knowledge_needs = _knowledge_needs(
            analysis,
            sales_plan,
            message,
            normalized_turn=normalized_turn,
            lead_profile=lead_profile,
            active_objection=active_objection,
            response_fulfillment_policy=response_fulfillment_policy,
        )
        structured_sources: List[str] = []
        json_sources: List[str] = ["tone_rules", "cta_rules", "sales_actions"]

        if "product_pricing" in knowledge_needs:
            structured_sources.append("postgres.products")
        if "platform_steps" in knowledge_needs:
            json_sources.append("platform_steps")
            structured_sources.append("postgres.official_links")
        if "official_app_link" in knowledge_needs:
            structured_sources.append("postgres.official_links")
            json_sources.append("platform_steps")
        if sales_plan.macro_action == MacroAction.HANDLE_OBJECTION.value:
            objection_type = _objection_type_for_context(analysis, active_objection)
            if objection_type:
                json_sources.append(f"objection_playbook:{objection_type}")
            structured_sources.append("postgres.products")
            structured_sources.append("postgres.policies")
        elif sales_plan.objection_overlay and sales_plan.objection_overlay.type != ObjectionType.NONE.value:
            json_sources.append(f"objection_playbook:{sales_plan.objection_overlay.type}")
        if sales_plan.macro_action == MacroAction.HANDOFF_TO_MIGUEL.value:
            json_sources.append("post_purchase_handoff")
        if sales_plan.macro_action == MacroAction.RISK_REVERSAL.value:
            structured_sources.append("postgres.policies")
            json_sources.append("platform_steps")
        if "product_fit" in knowledge_needs or "product_capabilities" in knowledge_needs:
            structured_sources.append("postgres.products")
        if Topic.COMPETITOR_COMPARISON.value in analysis.topics or sales_plan.macro_action == MacroAction.COMPARE_ALTERNATIVE.value:
            json_sources.append("source_routing_rules")
        if "official_policy" in knowledge_needs:
            structured_sources.append("postgres.policies")
        if not structured_sources and sales_plan.macro_action in {
            MacroAction.ANSWER_AND_ADVANCE.value,
            MacroAction.RECOMMEND_SOLUTION.value,
            MacroAction.NARROW_SOLUTION.value,
            MacroAction.PERSUADE_VALUE.value,
            MacroAction.SOFT_CLOSE.value,
        }:
            structured_sources.append("postgres.products")

        rag_route = build_rag_route(
            analysis,
            sales_plan,
            message,
            active_objection=active_objection,
        )
        return KnowledgePlan(
            knowledge_needs=dedupe(knowledge_needs),
            structured_sources=dedupe(structured_sources),
            json_sources=dedupe(json_sources),
            rag_queries=dedupe(rag_route.queries),
            rag_metadata_filter=rag_route.metadata_filter,
            rag_routing_reason=rag_route.routing_reason,
            needs_rag=rag_route.needs_rag,
        )


def _knowledge_needs(
    analysis: TurnAnalysis,
    sales_plan: SalesPlan,
    message: str,
    *,
    normalized_turn: Dict[str, Any],
    lead_profile: Dict[str, Any],
    active_objection: Optional[Dict[str, Any]],
    response_fulfillment_policy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    needs: List[str] = []
    text = _normalize_text(message)
    topics = set(analysis.topics or [])
    profile_data = dict(lead_profile.get("profile_data") or {})
    response_fulfillment_policy = response_fulfillment_policy or {}
    mandatory_fulfillments = set(response_fulfillment_policy.get("mandatory_fulfillments") or [])
    product_context = dict(
        normalized_turn.get("product_context") or profile_data.get("product_context") or {}
    )
    active_product_context = str(
        normalized_turn.get("active_product_context")
        or product_context.get("active_product_context")
        or ""
    )
    start_payment_cues = [
        "pagar para empezar",
        "pagar para iniciar",
        "pago para empezar",
        "pago para iniciar",
        "pago inicial",
        "deposito",
        "depositar",
        "anticipo",
        "arrancar",
    ]
    start_process_cues = ["empezar", "iniciar", "arrancar", "contratar", "link", "app", "pagina", "registro"]

    if Topic.PRICING.value in topics or _contains_any_text(
        text, ["cuanto cuesta", "cuesta", "precio", "precios", "mensualidad", "setup"]
    ) or _contains_any_text(text, start_payment_cues) or sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value:
        needs.append("product_pricing")
    if _contains_any_text(
        text,
        [
            "deposito",
            "50%",
            "pago inicial",
            "pagar para empezar",
            "pagar para iniciar",
            "pago para empezar",
            "pago para iniciar",
            "anticipo",
            "pago final",
            "reembolso",
            "mensualidad",
            "tokens",
            "soporte",
        ],
    ) or sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value or any(
        topic in topics
        for topic in [
            Topic.DEPOSIT.value,
            Topic.FINAL_PAYMENT.value,
            Topic.MONTHLY_PAYMENT.value,
            Topic.REFUND_POLICY.value,
            Topic.SUPPORT.value,
            Topic.TOKEN_USAGE.value,
        ]
        ):
        needs.append("official_policy")
    if (
        Topic.PLATFORM_PROCESS.value in topics
        or Topic.ONBOARDING.value in topics
        or sales_plan.macro_action in {MacroAction.EXPLAIN_PROCESS.value, MacroAction.DIRECT_CLOSE.value}
        or _contains_any_text(text, start_process_cues)
    ):
        needs.append("platform_steps")
    if "official_app_link" in mandatory_fulfillments:
        needs.append("official_app_link")
        needs.append("platform_steps")
    if active_product_context in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value} and (
        _contains_any_text(text, start_payment_cues)
        or Topic.PRICING.value in topics
        or sales_plan.macro_action == MacroAction.DIRECT_CLOSE.value
    ):
        needs.append("product_pricing")
    if any(topic in topics for topic in [Topic.INDUSTRY_USE_CASE.value, Topic.BUSINESS_FIT.value]):
        needs.append("product_fit")
    capability_terms = {
        "understand_audio",
        "understand_images",
        "answer_customer_questions",
        "provide_catalog_information",
        "capture_lead_data",
        "collect_order_information",
    }
    if (
        capability_terms & set(normalized_turn.get("requested_agent_capabilities") or [])
        or normalized_turn.get("requested_product") not in (None, "", "none")
        or _contains_any_text(text, ["audio", "audios", "imagen", "imagenes", "foto", "catalogo", "catalogo"])
    ):
        needs.append("product_capabilities")
    if analysis.references_prior_message:
        needs.append("conversation_memory")
    if sales_plan.macro_action == MacroAction.HANDLE_OBJECTION.value or (
        active_objection and active_objection.get("type") not in (None, "", ObjectionType.NONE.value)
    ):
        needs.append("objection_context")
    if profile_data.get("known_product_fit") or (profile_data.get("requirement_profile") or {}).get("requirement_class"):
        needs.append("product_fit")
    return dedupe(needs)


def dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_text(value: str) -> str:
    lowered = str(value or "").lower()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u"}
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    return lowered


def _contains_any_text(text: str, needles: List[str]) -> bool:
    return any(needle in text for needle in needles)


def _objection_type_for_context(
    analysis: TurnAnalysis, active_objection: Optional[Dict[str, Any]]
) -> Optional[str]:
    if analysis.objection_type and analysis.objection_type != ObjectionType.NONE.value:
        return analysis.objection_type
    if active_objection and active_objection.get("type") != ObjectionType.NONE.value:
        return str(active_objection.get("type"))
    return None
