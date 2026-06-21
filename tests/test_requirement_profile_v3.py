from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.commercial_state import resolve_product_context
from movia_sales_agent.agent.planners import build_planner_state, can_direct_close
from movia_sales_agent.agent.requirements import (
    REQUIREMENT_CLASS_EXTERNAL_ACTIONS,
    REQUIREMENT_CLASS_INFORMATIONAL_ONLY,
    REQUIREMENT_CLASS_SALES_PERSUASION,
    current_turn_requirement_delta,
    empty_requirement_profile,
    merge_requirement_profile,
)
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import BuyingSignal, Intent, MacroAction, PlannerReasonCode, ProductFit
from movia_sales_agent.models.schemas import TurnAnalysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def test_situation_only_persists_unknown_requirement_profile():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Tengo una clínica dental y recibimos muchos WhatsApps.",
        lead_external_id="req-v3-situation-only",
    )

    profile = result.lead_state["profile_data"]["requirement_profile"]
    assert profile["requirement_class"] == "unknown"
    assert result.selected_action["macro_action"] in {
        MacroAction.DISCOVER_NEED.value,
        MacroAction.ANSWER_AND_ADVANCE.value,
    }
    assert result.selected_action["next_question_key"]
    assert result.response_metadata["normalized_turn"]["recommended_product"] is None


def test_informational_request_maps_to_captura_profile():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Recibimos muchos mensajes y quiero que el agente responda dudas.",
        lead_external_id="req-v3-informational",
    )

    profile = result.lead_state["profile_data"]["requirement_profile"]
    assert profile["requirement_class"] == REQUIREMENT_CLASS_INFORMATIONAL_ONLY
    assert result.lead_state["profile_data"]["known_product_fit"] == ProductFit.MOVIA_CAPTURA.value


def test_sales_requirement_maps_to_ventas_conceptual_fit_unavailable():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Quiero que cierre ventas automáticamente.",
        lead_external_id="req-v3-sales",
    )

    profile = result.lead_state["profile_data"]["requirement_profile"]
    assert profile["requirement_class"] == REQUIREMENT_CLASS_SALES_PERSUASION
    assert result.lead_state["profile_data"]["known_product_fit"] == ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    assert result.selected_action["reason_code"] == PlannerReasonCode.SALES_PRODUCT_UNAVAILABLE.value


def test_external_actions_preserve_profile_and_declared_count_drives_custom_scope():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "req-v3-external-count"

    first = agent.invoke(
        "Necesito que cotice y registre pedidos en mi sistema.",
        lead_external_id=lead_id,
    )
    second = agent.invoke(
        "Son como cinco acciones.",
        lead_external_id=lead_id,
    )

    profile = second.lead_state["profile_data"]["requirement_profile"]
    actions = {item["type"] for item in profile["external_actions"] if item.get("active")}
    assert actions >= {"generate_quote", "create_order", "write_external_system"}
    assert profile["declared_external_action_count"]["value"] == 5
    assert profile["requirement_class"] == REQUIREMENT_CLASS_EXTERNAL_ACTIONS
    assert second.lead_state["profile_data"]["known_product_fit"] == ProductFit.CUSTOM_REVIEW.value
    assert "custom_scope_review_required" in second.response_metadata["normalized_turn"]["scope_flags"]
    assert first.response_metadata["normalized_turn"]["requirement_class"] == REQUIREMENT_CLASS_EXTERNAL_ACTIONS


def test_explicit_start_with_unresolved_custom_scope_does_not_direct_close():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "req-v3-mismatch-close"
    agent.invoke(
        "Necesito que cotice y registre pedidos en mi sistema.",
        lead_external_id=lead_id,
    )
    agent.invoke(
        "Son como cinco acciones.",
        lead_external_id=lead_id,
    )
    result = agent.invoke(
        "Pásame el link y ya.",
        lead_external_id=lead_id,
    )

    assert result.action != MacroAction.DIRECT_CLOSE.value
    assert result.selected_action["reason_code"] == PlannerReasonCode.CUSTOM_SCOPE_REVIEW.value


def test_explicit_requirement_replacement_deactivates_prior_external_actions():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "req-v3-replace"

    first = agent.invoke(
        "Necesito que el agente agende citas por WhatsApp.",
        lead_external_id=lead_id,
    )
    second = agent.invoke(
        "No, eso ya se fue caro. Entonces solo que responda precios.",
        lead_external_id=lead_id,
    )

    first_profile = first.lead_state["profile_data"]["requirement_profile"]
    second_profile = second.lead_state["profile_data"]["requirement_profile"]
    assert first_profile["requirement_class"] == REQUIREMENT_CLASS_EXTERNAL_ACTIONS
    assert second.response_metadata["normalized_turn"]["current_turn_requirement_delta"]["update_type"] == "replace"
    assert second_profile["requirement_class"] == REQUIREMENT_CLASS_INFORMATIONAL_ONLY
    assert "provide_prices" in {
        item["type"] for item in second_profile["informational_capabilities"] if item.get("active")
    }
    assert "schedule_appointment" not in {
        item["type"] for item in second_profile["external_actions"] if item.get("active")
    }
    assert second.lead_state["profile_data"]["known_product_fit"] == ProductFit.MOVIA_CAPTURA.value


def test_scope_narrowing_replaces_even_when_analyzer_marks_merge():
    existing = merge_requirement_profile(
        empty_requirement_profile(),
        {
            "update_type": "merge",
            "new_observed_problems": [],
            "new_informational_capabilities": [],
            "new_sales_capabilities": [],
            "new_external_actions": [
                {
                    "type": "schedule_appointment",
                    "evidence_span": "también agende citas",
                    "strength": "explicit",
                    "active": True,
                }
            ],
            "removed_informational_capabilities": [],
            "removed_sales_capabilities": [],
            "removed_external_actions": [],
            "declared_external_action_count": None,
        },
        turn_number=1,
    )

    delta = current_turn_requirement_delta(
        normalized_turn={
            "requested_agent_capabilities": ["provide_prices"],
            "requested_agent_actions": [],
            "requirement_update_intent": "merge",
        },
        analyzer_observation={
            "requested_agent_capabilities": [
                {
                    "type": "provide_prices",
                    "evidence_span": "Entonces mejor solo que responda precios.",
                    "requirement_strength": "explicit",
                }
            ],
            "requested_agent_actions": [],
            "requirement_update_intent": "merge",
        },
        message="No, eso ya se fue muy caro. Entonces mejor solo que responda precios.",
        existing_profile=existing,
    )
    updated = merge_requirement_profile(existing, delta, turn_number=2)

    assert delta["update_type"] == "replace"
    assert updated["requirement_class"] == REQUIREMENT_CLASS_INFORMATIONAL_ONLY
    assert "schedule_appointment" not in {
        item["type"] for item in updated["external_actions"] if item.get("active")
    }


def test_scope_narrowing_does_not_replace_without_future_requirement_addition():
    existing = merge_requirement_profile(
        empty_requirement_profile(),
        {
            "update_type": "merge",
            "new_observed_problems": [],
            "new_informational_capabilities": [],
            "new_sales_capabilities": [],
            "new_external_actions": [
                {
                    "type": "schedule_appointment",
                    "evidence_span": "agende citas",
                    "strength": "explicit",
                    "active": True,
                }
            ],
            "removed_informational_capabilities": [],
            "removed_sales_capabilities": [],
            "removed_external_actions": [],
            "declared_external_action_count": None,
        },
        turn_number=1,
    )

    delta = current_turn_requirement_delta(
        normalized_turn={
            "requested_agent_capabilities": [],
            "requested_agent_actions": [],
            "requirement_update_intent": "no_change",
        },
        analyzer_observation={
            "requested_agent_capabilities": [],
            "requested_agent_actions": [],
            "requirement_update_intent": "no_change",
        },
        message="Solo quiero saber cuánto cuesta.",
        existing_profile=existing,
    )

    assert delta["update_type"] == "no_update"


def test_direct_close_requires_confirmed_or_selected_product_under_phase2_gate():
    state_without_confirmation = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.EXPLICIT_START_REQUEST,
            explicit_start_intent=True,
            buying_signal=BuyingSignal.EXPLICIT_START,
        ),
        lead_profile={"profile_data": {"known_product_fit": ProductFit.MOVIA_HIBRIDO.value}},
    )
    state_with_confirmation = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.EXPLICIT_START_REQUEST,
            explicit_start_intent=True,
            buying_signal=BuyingSignal.EXPLICIT_START,
        ),
        lead_profile={
            "profile_data": {
                "known_product_fit": ProductFit.MOVIA_HIBRIDO.value,
                "confirmed_product": ProductFit.MOVIA_HIBRIDO.value,
            }
        },
    )

    assert can_direct_close(state_without_confirmation) is False
    assert can_direct_close(state_with_confirmation) is True


def test_product_reference_updates_active_context_without_selecting_product():
    context = resolve_product_context(
        profile_data={},
        normalized_turn={"requested_product": ProductFit.MOVIA_HIBRIDO.value},
        turn_number=1,
    )

    assert context["referenced_product"] == ProductFit.MOVIA_HIBRIDO.value
    assert context["active_product_context"] == ProductFit.MOVIA_HIBRIDO.value
    assert context["selected_product"] is None


def test_product_commitment_selects_product_without_requiring_requirement_class():
    state = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.EXPLICIT_START_REQUEST,
            explicit_start_intent=True,
            buying_signal=BuyingSignal.EXPLICIT_START,
        ),
        lead_profile={"profile_data": {}},
        normalized_turn={"selected_product": ProductFit.MOVIA_CAPTURA.value},
    )

    assert state.known_product_fit == ProductFit.MOVIA_CAPTURA.value
    assert can_direct_close(state) is True


def test_response_fulfillment_policy_is_turn_ephemeral():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke("Pásame el link.", lead_external_id="req-v3-ephemeral-link")

    assert result.response_metadata["response_fulfillment_policy"]["mandatory_fulfillments"] == [
        "official_app_link"
    ]
    profile_data = result.lead_state["profile_data"]
    assert "response_fulfillment_policy" not in profile_data
    assert "mandatory_fulfillments" not in profile_data
    assert "response_fulfillment_policy" not in profile_data.get("requirement_profile", {})
    assert "response_fulfillment_policy" not in profile_data.get("product_context", {})
