from movia_sales_agent.agent.contextual_reply import apply_contextual_reply_resolution
from movia_sales_agent.agent.planners import build_planner_state
from movia_sales_agent.agent.requirements import (
    REQUIREMENT_CLASS_EXTERNAL_ACTIONS,
    current_turn_requirement_delta,
    empty_requirement_profile,
    merge_requirement_profile,
)
from movia_sales_agent.contracts.commercial import BuyingSignal, Intent, ProductFit, Topic
from movia_sales_agent.models.schemas import TurnAnalysis


def test_short_affirmative_after_link_cta_sets_start_intent():
    analysis, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        normalized_turn={"explicit_start_intent": False, "normalization_warnings": []},
        message="Sí porfavor",
        recent_messages=[
            {"role": "assistant", "content": "¿Quieres que te pase el link para empezar?"}
        ],
    )

    assert analysis.primary_intent == Intent.EXPLICIT_START_REQUEST.value
    assert analysis.explicit_start_intent is True
    assert analysis.buying_signal == BuyingSignal.EXPLICIT_START.value
    assert normalized["explicit_start_intent"] is True
    assert normalized["contextual_reply_resolution"]["resolution_type"] == (
        "short_affirmative_to_start_intent"
    )


def test_short_affirmative_after_explain_more_cta_is_not_start_intent():
    analysis, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        normalized_turn={"explicit_start_intent": False, "normalization_warnings": []},
        message="sí",
        recent_messages=[
            {
                "role": "assistant",
                "content": "¿Quieres que te explique más cómo funcionaría en tu clínica?",
            }
        ],
    )

    assert analysis.explicit_start_intent is False
    assert normalized["contextual_continuation"] == "explain_more"
    assert normalized["contextual_reply_resolution"]["resolution_type"] == (
        "short_affirmative_to_explain_more"
    )


def test_requirement_frame_las_dos_promotes_external_actions():
    _, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        normalized_turn={"requested_agent_actions": [], "normalization_warnings": []},
        message="Las dos",
        recent_messages=[
            {
                "role": "assistant",
                "content": (
                    "¿El agente solo debe responder/capturar datos o también hacer acciones "
                    "como agendar, cotizar o registrar información?"
                ),
            }
        ],
    )

    delta = current_turn_requirement_delta(
        normalized_turn=normalized,
        analyzer_observation={"requested_agent_actions": [], "requirement_update_intent": "no_change"},
        message="Las dos",
        existing_profile=empty_requirement_profile(),
    )
    profile = merge_requirement_profile(empty_requirement_profile(), delta, turn_number=1)

    assert profile["requirement_class"] == REQUIREMENT_CLASS_EXTERNAL_ACTIONS
    assert {entry["type"] for entry in profile["external_actions"] if entry.get("active")}


def test_action_like_pain_without_requirement_frame_is_not_promoted():
    _, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        normalized_turn={"requested_agent_actions": [], "normalization_warnings": []},
        message="Me cuesta agendar citas rápido",
        recent_messages=[
            {"role": "assistant", "content": "¿Qué parte de tu atención quieres mejorar primero?"}
        ],
    )

    delta = current_turn_requirement_delta(
        normalized_turn=normalized,
        analyzer_observation={"requested_agent_actions": [], "requirement_update_intent": "no_change"},
        message="Me cuesta agendar citas rápido",
        existing_profile=empty_requirement_profile(),
    )

    assert delta["update_type"] == "no_update"
    assert delta["new_external_actions"] == []


def test_action_terms_after_requirement_frame_persist_hibrido_fit():
    _, normalized = apply_contextual_reply_resolution(
        analysis=TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        normalized_turn={"requested_agent_actions": [], "normalization_warnings": []},
        message="Agendar, cotizar o registrar información",
        recent_messages=[
            {
                "role": "assistant",
                "content": (
                    "¿El agente solo debe responder/capturar datos o también hacer acciones "
                    "como agendar, cotizar o registrar información?"
                ),
            }
        ],
    )

    delta = current_turn_requirement_delta(
        normalized_turn=normalized,
        analyzer_observation={"requested_agent_actions": [], "requirement_update_intent": "no_change"},
        message="Agendar, cotizar o registrar información",
        existing_profile=empty_requirement_profile(),
    )
    profile = merge_requirement_profile(empty_requirement_profile(), delta, turn_number=1)

    assert profile["requirement_class"] == REQUIREMENT_CLASS_EXTERNAL_ACTIONS
    assert len([entry for entry in profile["external_actions"] if entry.get("active")]) <= 2


def test_hibrido_context_suppresses_repeated_action_requirement_discovery():
    state = build_planner_state(
        analysis=TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]),
        lead_profile={
            "business_type": "clínica dental",
            "main_channel": "whatsapp",
            "pain": "quiere automatizar citas",
            "profile_data": {},
        },
        normalized_turn={
            "active_product_context": ProductFit.MOVIA_HIBRIDO.value,
            "product_context": {"active_product_context": ProductFit.MOVIA_HIBRIDO.value},
            "missing_slots": ["action_requirement"],
        },
    )

    assert "action_requirement" in state.known_slots
    assert "action_requirement" not in state.missing_slots
