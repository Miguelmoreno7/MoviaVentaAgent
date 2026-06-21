import pytest

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ConversationMode,
    MacroAction,
    ObjectionFlowStep,
    ObjectionStrength,
    ObjectionType,
    SalesStage,
)


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


@pytest.mark.parametrize(
    ("message", "expected_type"),
    [
        ("Se me hace caro.", ObjectionType.PRICE_OBJECTION.value),
        ("No confio, siento que va a fallar.", ObjectionType.TRUST_OBJECTION.value),
        ("Me preocupa que responda mal y me queme con clientes.", ObjectionType.FEAR_WRONG_ANSWERS.value),
        ("Dame prueba gratis sin deposito y si funciona pago.", ObjectionType.WANTS_FREE_TRIAL.value),
    ],
)
def test_hard_objection_types_persist_and_progress_without_repeating_first_step(message, expected_type):
    agent = MoviaSalesAgent(offline_settings())
    lead_id = f"objection-{expected_type}"

    agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    first = agent.invoke(message, lead_external_id=lead_id)
    second = agent.invoke("Lo que me preocupa es si realmente vale la pena.", lead_external_id=lead_id)

    assert first.action == MacroAction.HANDLE_OBJECTION.value
    assert first.analysis.objection_type == expected_type
    assert first.analysis.objection_strength == ObjectionStrength.HARD.value
    assert first.selected_action["objection_flow_step"] == (
        ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value
    )
    assert first.lead_state["active_objection"]["type"] == expected_type
    assert first.lead_state["active_objection"]["active"] is True
    assert first.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert first.lead_state["conversation_mode"] == ConversationMode.HANDLING_OBJECTION.value
    assert first.action != MacroAction.DIRECT_CLOSE.value

    assert second.action == MacroAction.HANDLE_OBJECTION.value
    assert second.selected_action["objection_flow_step"] == ObjectionFlowStep.CLARIFY_VALUE.value
    assert second.selected_action["objection_flow_step"] != first.selected_action["objection_flow_step"]
    assert second.lead_state["active_objection"]["type"] == expected_type
    assert second.lead_state["active_objection"]["current_step"] == ObjectionFlowStep.CLARIFY_VALUE.value
    assert second.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert second.action != MacroAction.DIRECT_CLOSE.value


@pytest.mark.parametrize(
    ("message", "expected_type", "expected_action"),
    [
        ("Ya tengo una persona que responde WhatsApp.", ObjectionType.ALREADY_HAVE_PERSON.value, MacroAction.ANSWER_AND_ADVANCE.value),
        (
            "Ya uso WhatsApp Business gratis con respuestas rápidas.",
            ObjectionType.ALREADY_USE_WHATSAPP_BUSINESS.value,
            MacroAction.COMPARE_ALTERNATIVE.value,
        ),
        ("Lo tengo que pensar.", ObjectionType.NEED_TO_THINK.value, MacroAction.ANSWER_UNKNOWN_SAFELY.value),
        ("ManyChat es mejor y ya lo uso.", ObjectionType.COMPETITOR_COMPARISON.value, MacroAction.COMPARE_ALTERNATIVE.value),
        ("Me preocupa el soporte por WhatsApp personal.", ObjectionType.SUPPORT_CONCERN.value, MacroAction.RISK_REVERSAL.value),
    ],
)
def test_soft_objections_stay_inline_without_persistent_active_objection(message, expected_type, expected_action):
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(message, lead_external_id=f"soft-{expected_type}")

    assert result.analysis.objection_type == expected_type
    assert result.analysis.objection_strength == ObjectionStrength.SOFT.value
    assert result.action == expected_action
    assert result.lead_state["active_objection"]["active"] is False
    assert result.lead_state["conversation_mode"] == ConversationMode.NORMAL.value
    assert result.selected_action["objection_overlay"]["inline"] is True
    assert result.selected_action["objection_overlay"]["blocking_close"] is False


def test_objection_flow_advances_to_resolution_and_returns_to_previous_stage():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "objection-resolution"

    first_context = agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    first = agent.invoke("Se me hace caro.", lead_external_id=lead_id)
    clarify = agent.invoke("El pago inicial es lo que más me pesa.", lead_external_id=lead_id)
    tie = agent.invoke("Quiero recuperar tiempo con mi equipo.", lead_external_id=lead_id)
    proof = agent.invoke("Muéstrame una prueba segura de que no inventan.", lead_external_id=lead_id)
    close = agent.invoke("Ok, eso tiene sentido.", lead_external_id=lead_id)

    assert first_context.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert first.selected_action["objection_flow_step"] == (
        ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value
    )
    assert clarify.selected_action["objection_flow_step"] == ObjectionFlowStep.CLARIFY_VALUE.value
    assert tie.selected_action["objection_flow_step"] == ObjectionFlowStep.TIE_SOLUTION.value
    assert proof.selected_action["objection_flow_step"] == ObjectionFlowStep.PROVIDE_PROOF.value
    assert close.selected_action["objection_flow_step"] == ObjectionFlowStep.RESOLVED.value
    assert close.lead_state["active_objection"]["resolved"] is True
    assert close.lead_state["active_objection"]["active"] is False
    assert close.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert close.lead_state["conversation_mode"] == ConversationMode.NORMAL.value
    assert close.action != MacroAction.DIRECT_CLOSE.value


def test_active_objection_can_resolve_without_new_objection_candidate():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "objection-resolve-no-new-candidate"

    agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    agent.invoke("Se me hace caro.", lead_external_id=lead_id)
    result = agent.invoke("Ok, con eso ya no es tanto problema.", lead_external_id=lead_id)

    assert result.analysis.has_objection is False
    assert result.analysis.objection_relation == "resolved"
    assert result.lead_state["active_objection"]["active"] is False
    assert result.lead_state["active_objection"]["status"] == "resolved"


def test_objection_can_pause_for_topic_change_and_resume_later():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "objection-pause"

    agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    objection = agent.invoke("Se me hace caro.", lead_external_id=lead_id)
    process = agent.invoke("¿Cómo lleno la información en la página?", lead_external_id=lead_id)
    resumed = agent.invoke("Volviendo a eso, el pago inicial es lo que me pesa.", lead_external_id=lead_id)

    assert objection.selected_action["objection_flow_step"] == (
        ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value
    )
    assert process.action == MacroAction.EXPLAIN_PROCESS.value
    assert process.lead_state["current_stage"] == SalesStage.EDUCATING.value
    assert process.lead_state["conversation_mode"] == ConversationMode.HANDLING_OBJECTION.value
    assert process.lead_state["active_objection"]["active"] is True
    assert process.lead_state["active_objection"]["paused"] is True
    assert resumed.action == MacroAction.HANDLE_OBJECTION.value
    assert resumed.selected_action["objection_flow_step"] == ObjectionFlowStep.CLARIFY_VALUE.value


def test_explicit_start_during_unresolved_hard_objection_does_not_direct_close():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "objection-no-close"

    agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    agent.invoke("Dame prueba gratis sin deposito y si funciona pago.", lead_external_id=lead_id)
    result = agent.invoke("Bueno pásame el link para empezar.", lead_external_id=lead_id)

    assert result.action == MacroAction.HANDLE_OBJECTION.value
    assert result.action != MacroAction.DIRECT_CLOSE.value
    assert result.lead_state["active_objection"]["active"] is True
    assert result.lead_state["current_stage"] != SalesStage.OBJECTION_HANDLING.value


def test_explicit_start_after_semantic_resolution_can_direct_close():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "objection-resolved-close"

    agent.invoke("Necesito que responda WhatsApp y capture datos de clientes.", lead_external_id=lead_id)
    agent.invoke("¿Cuánto cuesta?", lead_external_id=lead_id)
    agent.invoke("Se me hace caro.", lead_external_id=lead_id)
    result = agent.invoke(
        "Ok, eso tiene sentido, pásame el link para empezar con MovIA Captura.",
        lead_external_id=lead_id,
    )

    assert result.action == MacroAction.DIRECT_CLOSE.value
    assert result.lead_state["active_objection"]["active"] is False
    assert result.lead_state["active_objection"]["status"] == "resolved"
    assert result.lead_state["conversation_mode"] == ConversationMode.NORMAL.value
