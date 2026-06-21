from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.planners import make_plan
from movia_sales_agent.agent.stages import SalesStageTransitionService, normalize_stage
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ConversationMode,
    CTAType,
    MacroAction,
    MicroAction,
    ObjectionFlowStep,
    PlannerReasonCode,
    SalesStage,
)
from movia_sales_agent.models.schemas import TurnAnalysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def test_v1_stage_values_are_normalized_to_v2():
    assert normalize_stage("recommended") == (SalesStage.SOLUTION_RECOMMENDED.value, "recommended")
    assert normalize_stage("unknown") == (SalesStage.UNKNOWN_RECOVERY.value, "unknown")
    assert normalize_stage("objection_handling") == (SalesStage.NEW.value, "objection_handling")
    assert normalize_stage("made_up") == (SalesStage.UNKNOWN_RECOVERY.value, "made_up")


def test_stage_transition_uses_target_stage_not_macro_projection():
    plan = make_plan(
        MacroAction.ANSWER_AND_ADVANCE,
        MicroAction.ANSWER_PRICE_THEN_EXPLAIN_SCOPE,
        "Answer price while keeping the lead in education.",
        CTAType.SOFT_QUESTION,
        SalesStage.EDUCATING,
        PlannerReasonCode.PRICE_QUESTION_WITH_DISCOVERY_GAP,
    )

    transition = SalesStageTransitionService().transition(
        lead_profile={"current_stage": SalesStage.DISCOVERY.value},
        analysis=TurnAnalysis(),
        sales_plan=plan,
    )

    assert transition.current_stage == SalesStage.EDUCATING.value
    assert transition.previous_stage == SalesStage.DISCOVERY.value
    assert transition.current_stage != "qualified"
    assert transition.stage_changed is True


def test_objection_handling_is_not_persisted_as_primary_stage():
    plan = make_plan(
        MacroAction.HANDLE_OBJECTION,
        MicroAction.VALIDATE_AND_CLARIFY_OBJECTION,
        "Handle a hard objection.",
        CTAType.OBJECTION_QUESTION,
        SalesStage.OBJECTION_HANDLING,
        PlannerReasonCode.NEW_HARD_OBJECTION,
        objection_flow_step=ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION,
    )

    transition = SalesStageTransitionService().transition(
        lead_profile={"current_stage": SalesStage.SOLUTION_RECOMMENDED.value},
        analysis=TurnAnalysis(),
        sales_plan=plan,
    )

    assert transition.current_stage == SalesStage.SOLUTION_RECOMMENDED.value
    assert transition.previous_stage is None
    assert transition.stage_before_objection == SalesStage.SOLUTION_RECOMMENDED.value
    assert transition.conversation_mode == ConversationMode.HANDLING_OBJECTION.value


def test_invalid_transition_is_explicitly_normalized():
    plan = make_plan(
        MacroAction.SOFT_CLOSE,
        MicroAction.ASK_PERMISSION_TO_SEND_LINK,
        "Soft close too early.",
        CTAType.ASK_PERMISSION_TO_SEND_LINK,
        SalesStage.READY_TO_START,
        PlannerReasonCode.MEDIUM_HIGH_SIGNAL_SOFT_CLOSE,
    )

    transition = SalesStageTransitionService().transition(
        lead_profile={"current_stage": SalesStage.NEW.value},
        analysis=TurnAnalysis(),
        sales_plan=plan,
    )

    assert transition.current_stage == SalesStage.NEW.value
    assert transition.invalid_transition == "new->ready_to_start"
    assert transition.stage_changed is False


def test_offline_agent_persists_stage_between_turns():
    agent = MoviaSalesAgent(offline_settings())

    first = agent.invoke("¿Cuánto cuesta?", lead_external_id="stage-persist")
    second = agent.invoke("Se me hace caro", lead_external_id="stage-persist")

    assert first.action == MacroAction.ANSWER_AND_ADVANCE.value
    assert first.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert second.action == MacroAction.HANDLE_OBJECTION.value
    assert second.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert second.lead_state["conversation_mode"] == ConversationMode.HANDLING_OBJECTION.value
    assert second.lead_state["stage_before_objection"] == SalesStage.EDUCATING.value
