from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.planners import SalesPolicyPlanner, build_planner_state, can_direct_close
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    CTAType,
    Intent,
    MacroAction,
    MicroAction,
    ObjectionFlowStep,
    ObjectionStrength,
    ObjectionType,
    PlannerReasonCode,
    ProductFit,
    SalesStage,
    Topic,
)
from movia_sales_agent.models.schemas import TurnAnalysis
from movia_sales_agent.services.openai_service import heuristic_analysis
from movia_sales_agent.services.purchase_status import (
    FixedPurchaseStatusService,
    PURCHASE_STATUS_DEPOSIT_CONFIRMED,
)


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def plan_for(analysis: TurnAnalysis, lead_profile=None, **kwargs):
    return SalesPolicyPlanner().plan(analysis, lead_profile or {}, **kwargs)


def profile(**profile_data):
    return {
        "business_type": "dental",
        "main_channel": "whatsapp",
        "pain": "missed_leads",
        "profile_data": profile_data,
    }


def test_post_purchase_routes_to_handoff():
    analysis = heuristic_analysis("Ya pagué, ¿qué sigue?")
    plan = plan_for(
        analysis,
        purchase_status={"status": PURCHASE_STATUS_DEPOSIT_CONFIRMED},
    )

    assert analysis.is_post_purchase is True
    assert analysis.primary_intent == Intent.POST_PURCHASE_REQUEST.value
    assert plan.macro_action == "handoff_to_miguel"
    assert plan.cta_type == "redirect_to_miguel"
    assert plan.target_stage == SalesStage.HANDOFF.value
    assert plan.reason_code == PlannerReasonCode.POST_PURCHASE_HANDOFF.value


def test_post_purchase_without_confirmed_deposit_uses_safe_gated_message():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke("Ya pagué, ¿qué sigue?", lead_external_id="post-purchase-not-checked")

    assert result.analysis.is_post_purchase is True
    assert result.action == MacroAction.EXPLAIN_PROCESS.value
    assert result.selected_action["micro_action"] == MicroAction.EXPLAIN_HUMAN_HANDOFF.value
    assert result.response_metadata["purchase_status"]["status"] == "not_checked"
    assert "Una vez que el depósito quede confirmado" in result.response
    assert "Mientras tanto" in result.response


def test_post_purchase_with_confirmed_deposit_routes_to_miguel():
    agent = MoviaSalesAgent(
        offline_settings(),
        purchase_status_service=FixedPurchaseStatusService(PURCHASE_STATUS_DEPOSIT_CONFIRMED),
    )
    result = agent.invoke("Ya pagué, ¿qué sigue?", lead_external_id="post-purchase-confirmed")

    assert result.analysis.is_post_purchase is True
    assert result.action == MacroAction.HANDOFF_TO_MIGUEL.value
    assert result.selected_action["reason_code"] == PlannerReasonCode.POST_PURCHASE_HANDOFF.value
    assert result.response_metadata["purchase_status"]["status"] == PURCHASE_STATUS_DEPOSIT_CONFIRMED


def test_price_objection_uses_objection_flow():
    analysis = heuristic_analysis("Se me hace caro")
    plan = plan_for(analysis)

    assert analysis.has_objection is True
    assert analysis.objection_type == ObjectionType.PRICE_OBJECTION.value
    assert analysis.objection_strength == ObjectionStrength.HARD.value
    assert plan.macro_action == "handle_objection"
    assert plan.objection_flow_step == ObjectionFlowStep.THANK_EMPATHIZE_ASK_OPEN_QUESTION.value
    assert plan.reason_code == PlannerReasonCode.NEW_HARD_OBJECTION.value


def test_cheapest_plan_question_is_not_price_objection():
    analysis = heuristic_analysis(
        "¿Cuál es el plan más barato y por qué me conviene para una clínica dental?"
    )
    plan = SalesPolicyPlanner().plan(analysis, {})

    assert analysis.has_objection is False
    assert analysis.primary_intent == Intent.CHEAPEST_PLAN_QUESTION.value
    assert Topic.PRICING.value in analysis.topics
    assert Topic.INDUSTRY_USE_CASE.value in analysis.topics
    assert plan.macro_action == MacroAction.ANSWER_AND_ADVANCE.value
    assert plan.micro_action == MicroAction.ANSWER_PRICE_THEN_EXPLAIN_SCOPE.value


def test_price_question_is_not_objection_or_start_intent():
    analysis = heuristic_analysis("¿Cuánto cuesta?")

    assert analysis.primary_intent == Intent.PRICING_QUESTION.value
    assert Topic.PRICING.value in analysis.topics
    assert analysis.has_objection is False
    assert analysis.objection_type == ObjectionType.NONE.value
    assert analysis.explicit_start_intent is False
    assert analysis.buying_signal == BuyingSignal.LOW.value


def test_sarcastic_opener_is_skeptical_tone_not_hard_objection():
    analysis = heuristic_analysis(
        "Vi su anuncio. A ver, convenceme rapido: seguro es otro bot que contesta tonterias, no?"
    )

    assert analysis.skeptical_tone is True
    assert analysis.has_objection is False
    assert analysis.objection_type == ObjectionType.NONE.value
    assert analysis.objection_strength == ObjectionStrength.SOFT.value
    assert analysis.explicit_start_intent is False


def test_free_trial_request_is_objection_not_explicit_start():
    analysis = heuristic_analysis("Dame prueba gratis sin deposito y si funciona pago.")
    plan = plan_for(analysis)

    assert analysis.has_objection is True
    assert analysis.objection_type == ObjectionType.WANTS_FREE_TRIAL.value
    assert analysis.explicit_start_intent is False
    assert plan.macro_action == "handle_objection"


def test_link_request_is_explicit_start_intent():
    analysis = heuristic_analysis("Pásame el link para empezar.")
    plan = plan_for(
        analysis,
        profile(
            known_product_fit=ProductFit.MOVIA_CAPTURA.value,
            confirmed_product=ProductFit.MOVIA_CAPTURA.value,
        ),
    )

    assert analysis.primary_intent == Intent.EXPLICIT_START_REQUEST.value
    assert analysis.explicit_start_intent is True
    assert analysis.buying_signal == BuyingSignal.EXPLICIT_START.value
    assert plan.macro_action == "direct_close"
    assert plan.reason_code == PlannerReasonCode.DIRECT_CLOSE_ALLOWED.value


def test_all_macroactions_are_reachable_with_valid_input_states():
    scenarios = {
        MacroAction.ANSWER_AND_ADVANCE.value: (TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]), {}),
        MacroAction.DISCOVER_NEED.value: (TurnAnalysis(primary_intent=Intent.GREETING), {}),
        MacroAction.NARROW_SOLUTION.value: (
            TurnAnalysis(
                primary_intent=Intent.PRODUCT_SCOPE_QUESTION,
                topics=[Topic.PRODUCT_SCOPE],
                lead_updates={"profile_data": {"action_requirement": ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value}},
            ),
            profile(),
            {
                "normalized_turn": {
                    "action_requirement": ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value,
                    "requested_product": "movia_captura",
                    "recommended_product": ProductFit.MOVIA_HIBRIDO.value,
                    "product_preference_mismatch": True,
                    "known_slots": ["action_requirement"],
                    "missing_slots": ["business_type", "main_channel", "pain_or_goal"],
                }
            },
        ),
        MacroAction.RECOMMEND_SOLUTION.value: (
            TurnAnalysis(primary_intent=Intent.PRODUCT_RECOMMENDATION_QUESTION),
            profile(
                action_requirement=ActionRequirement.ANSWERS_ONLY.value,
                known_product_fit=ProductFit.MOVIA_CAPTURA.value,
            ),
        ),
        MacroAction.PERSUADE_VALUE.value: (
            TurnAnalysis(primary_intent=Intent.GENERAL_INFO, skeptical_tone=True, objection_strength=ObjectionStrength.SOFT),
            {},
        ),
        MacroAction.HANDLE_OBJECTION.value: (
            TurnAnalysis(
                primary_intent=Intent.GENERAL_INFO,
                has_objection=True,
                objection_type=ObjectionType.PRICE_OBJECTION,
                objection_strength=ObjectionStrength.HARD,
            ),
            {},
        ),
        MacroAction.RISK_REVERSAL.value: (
            TurnAnalysis(primary_intent=Intent.POLICY_QUESTION, topics=[Topic.REFUND_POLICY]),
            profile(action_requirement=ActionRequirement.ANSWERS_ONLY.value),
        ),
        MacroAction.COMPARE_ALTERNATIVE.value: (
            TurnAnalysis(primary_intent=Intent.COMPARISON_QUESTION, topics=[Topic.COMPETITOR_COMPARISON]),
            profile(),
        ),
        MacroAction.EXPLAIN_PROCESS.value: (
            TurnAnalysis(primary_intent=Intent.PLATFORM_STEPS_QUESTION, topics=[Topic.PLATFORM_PROCESS]),
            profile(),
        ),
        MacroAction.SOFT_CLOSE.value: (
            TurnAnalysis(primary_intent=Intent.GENERAL_INFO, buying_signal=BuyingSignal.HIGH),
            {
                **profile(
                    action_requirement=ActionRequirement.ANSWERS_ONLY.value,
                    known_product_fit=ProductFit.MOVIA_CAPTURA.value,
                ),
                "current_stage": SalesStage.SOLUTION_RECOMMENDED.value,
                "last_action": MacroAction.RECOMMEND_SOLUTION.value,
            },
        ),
        MacroAction.DIRECT_CLOSE.value: (
            TurnAnalysis(
                primary_intent=Intent.EXPLICIT_START_REQUEST,
                explicit_start_intent=True,
                buying_signal=BuyingSignal.EXPLICIT_START,
            ),
            profile(
                known_product_fit=ProductFit.MOVIA_CAPTURA.value,
                confirmed_product=ProductFit.MOVIA_CAPTURA.value,
            ),
        ),
        MacroAction.HANDOFF_TO_MIGUEL.value: (
            TurnAnalysis(primary_intent=Intent.POST_PURCHASE_REQUEST, is_post_purchase=True),
            {},
            {"purchase_status": {"status": PURCHASE_STATUS_DEPOSIT_CONFIRMED}},
        ),
        MacroAction.ANSWER_UNKNOWN_SAFELY.value: (
            TurnAnalysis(primary_intent=Intent.UNKNOWN, topics=[Topic.UNKNOWN]),
            profile(),
        ),
    }

    reached = {}
    for expected_action, scenario in scenarios.items():
        analysis, lead_profile, *extra = scenario
        kwargs = extra[0] if extra else {}
        plan = plan_for(
            analysis,
            lead_profile,
            message="ManyChat" if expected_action == MacroAction.COMPARE_ALTERNATIVE.value else "",
            **kwargs,
        )
        reached[expected_action] = plan.macro_action
        assert plan.macro_action == expected_action
        assert plan.reason_code
        assert plan.target_stage

    assert set(reached) == set(MacroAction.values())


def test_can_direct_close_requires_explicit_start_and_no_unresolved_hard_objection():
    price_state = build_planner_state(
        analysis=TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]),
        lead_profile=profile(known_product_fit=ProductFit.MOVIA_CAPTURA.value),
    )
    pain_state = build_planner_state(
        analysis=TurnAnalysis(primary_intent=Intent.PRODUCT_RECOMMENDATION_QUESTION, pain="missed_leads"),
        lead_profile=profile(known_product_fit=ProductFit.MOVIA_CAPTURA.value),
    )
    feature_state = build_planner_state(
        analysis=TurnAnalysis(primary_intent=Intent.PRODUCT_SCOPE_QUESTION, topics=[Topic.PRODUCT_SCOPE]),
        lead_profile=profile(known_product_fit=ProductFit.MOVIA_HIBRIDO.value),
    )
    hard_objection_state = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.EXPLICIT_START_REQUEST,
            explicit_start_intent=True,
            has_objection=True,
            objection_type=ObjectionType.WANTS_FREE_TRIAL,
            objection_strength=ObjectionStrength.HARD,
        ),
        lead_profile=profile(known_product_fit=ProductFit.MOVIA_CAPTURA.value),
    )
    valid_state = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.EXPLICIT_START_REQUEST,
            explicit_start_intent=True,
            buying_signal=BuyingSignal.EXPLICIT_START,
        ),
        lead_profile=profile(
            known_product_fit=ProductFit.MOVIA_CAPTURA.value,
            confirmed_product=ProductFit.MOVIA_CAPTURA.value,
        ),
    )

    assert can_direct_close(price_state) is False
    assert can_direct_close(pain_state) is False
    assert can_direct_close(feature_state) is False
    assert can_direct_close(hard_objection_state) is False
    assert can_direct_close(valid_state) is True


def test_explicit_start_with_unavailable_product_does_not_direct_close():
    analysis = TurnAnalysis(primary_intent=Intent.EXPLICIT_START_REQUEST, explicit_start_intent=True)
    plan = plan_for(
        analysis,
        profile(known_product_fit=ProductFit.MOVIA_VENTAS_UNAVAILABLE.value),
    )

    assert plan.macro_action == MacroAction.RECOMMEND_SOLUTION.value
    assert plan.micro_action == MicroAction.EXPLAIN_VENTAS_NOT_AVAILABLE.value
    assert plan.reason_code == PlannerReasonCode.SALES_PRODUCT_UNAVAILABLE.value


def test_active_objection_continuation_does_not_reset_to_first_response():
    plan = plan_for(
        TurnAnalysis(primary_intent=Intent.GENERAL_INFO),
        profile(),
        active_objection={"type": ObjectionType.PRICE_OBJECTION.value, "strength": ObjectionStrength.HARD.value},
    )

    assert plan.macro_action == MacroAction.HANDLE_OBJECTION.value
    assert plan.micro_action == MicroAction.CLARIFY_OBJECTION_VALUE.value
    assert plan.objection_flow_step == ObjectionFlowStep.CLARIFY_VALUE.value
    assert plan.reason_code == PlannerReasonCode.ACTIVE_OBJECTION_CONTINUATION.value


def test_sarcastic_opener_routes_to_persuade_value_without_direct_close():
    analysis = heuristic_analysis("Vi su anuncio. Seguro es otro bot que contesta tonterias.")
    plan = plan_for(analysis)

    assert analysis.skeptical_tone is True
    assert analysis.has_objection is False
    assert plan.macro_action == MacroAction.PERSUADE_VALUE.value
    assert plan.reason_code == PlannerReasonCode.SKEPTICAL_VALUE_NEEDED.value


def test_pain_description_does_not_become_price_question_or_direct_close():
    analysis = heuristic_analysis("De Facebook Ads a WhatsApp. La gente pregunta precio y luego desaparece.")
    plan = plan_for(analysis)

    assert analysis.explicit_start_intent is False
    assert analysis.primary_intent != Intent.PRICING_QUESTION.value
    assert plan.macro_action == MacroAction.DISCOVER_NEED.value
    assert plan.reason_code == PlannerReasonCode.ACTION_REQUIREMENT_UNKNOWN.value
    assert plan.next_question_key == "action_requirement"


def test_price_question_routes_to_answer_and_advance_not_direct_close():
    analysis = heuristic_analysis("Solo responder. ¿Cuánto cuesta?")
    plan = plan_for(analysis)

    assert analysis.explicit_start_intent is False
    assert plan.macro_action == MacroAction.ANSWER_AND_ADVANCE.value
    assert plan.cta_type == CTAType.SOFT_QUESTION.value


def test_supplier_workflow_routes_to_hibrido_narrowing_not_direct_close():
    analysis = heuristic_analysis("Tengo proveedores que mandan ticket, foto y datos de garantía.")
    plan = plan_for(analysis, profile(), message="Tengo proveedores que mandan ticket, foto y datos de garantía.")

    assert analysis.explicit_start_intent is False
    assert plan.macro_action == MacroAction.ANSWER_AND_ADVANCE.value
    assert plan.micro_action == MicroAction.ANSWER_SCOPE_THEN_DISCOVER_BUSINESS.value
    assert plan.reason_code == PlannerReasonCode.SCOPE_QUESTION_WITH_DISCOVERY_GAP.value


def test_manychat_comparison_routes_to_compare_alternative():
    analysis = heuristic_analysis("¿Esto es como ManyChat?")
    plan = plan_for(analysis, profile(), message="¿Esto es como ManyChat?")

    assert analysis.primary_intent == Intent.COMPARISON_QUESTION.value
    assert analysis.objection_type != ObjectionType.TRUST_OBJECTION.value
    assert plan.macro_action == MacroAction.COMPARE_ALTERNATIVE.value
    assert plan.micro_action == MicroAction.COMPARE_MANYCHAT.value


def test_phase3_first_business_message_does_not_auto_recommend_captura():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Hola, tengo una clínica dental y quiero automatizar WhatsApp.",
        lead_external_id="phase3-no-auto-captura",
    )

    assert result.action != MacroAction.RECOMMEND_SOLUTION.value
    assert result.selected_action["target_stage"] != SalesStage.SOLUTION_RECOMMENDED.value
    assert "te conviene más MovIA Captura" not in result.response


def test_phase3_discovery_happens_when_action_requirement_is_unknown():
    analysis = heuristic_analysis(
        "Tengo una clínica dental, por WhatsApp preguntan precio y luego desaparecen."
    )
    plan = plan_for(analysis)

    assert plan.macro_action == MacroAction.DISCOVER_NEED.value
    assert plan.micro_action == MicroAction.ASK_ACTION_REQUIREMENT.value
    assert plan.next_question_key == "action_requirement"


def test_planner_missing_slots_respect_requirement_profile_source_of_truth():
    requirement_profile = {
        "requirement_profile_version": "1.0",
        "observed_business_problems": [],
        "informational_capabilities": [],
        "sales_capabilities": [],
        "external_actions": [{"type": "write_external_system", "active": True}],
        "declared_external_action_count": None,
        "requirement_class": "external_actions",
        "first_confirmed_turn": 1,
        "last_updated_turn": 1,
        "sources": {},
    }
    state = build_planner_state(
        analysis=TurnAnalysis(
            primary_intent=Intent.PRODUCT_SCOPE_QUESTION,
            topics=[Topic.PRODUCT_SCOPE],
            lead_updates={"profile_data": {"requirement_profile": requirement_profile}},
        ),
        lead_profile={},
        normalized_turn={
            "action_requirement": ActionRequirement.UNKNOWN.value,
            "requirement_class": "external_actions",
            "known_slots": [],
            "missing_slots": ["action_requirement"],
        },
    )
    plan = SalesPolicyPlanner()._plan_state(state)

    assert state.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    assert "action_requirement" in state.known_slots
    assert "action_requirement" not in state.missing_slots
    assert plan.next_question_key != "action_requirement"


def test_phase3_captura_is_not_recommended_for_external_actions():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Quiero MovIA Captura para cotizar y registrar pedidos en mi sistema.",
        lead_external_id="phase3-captura-external-actions",
    )

    assert result.action == MacroAction.HANDOFF_TO_MIGUEL.value
    assert result.selected_action["micro_action"] == MicroAction.REDIRECT_CUSTOM_SCOPE.value
    assert result.selected_action["reason_code"] == PlannerReasonCode.CUSTOM_SCOPE_REVIEW.value
    assert "te conviene más MovIA Captura" not in result.response


def test_demo_question_separates_demo_from_paid_project_deposit():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "¿Puedo probar un demo antes de pagar?",
        lead_external_id="demo-vs-paid-project",
    )

    assert result.action == MacroAction.EXPLAIN_PROCESS.value
    response = result.response.lower()
    assert "no requiere depósito" in response
    assert "no inicia trabajo personalizado" in response
    assert "50%" in result.response


def test_hibrido_external_system_scope_requires_technical_review_not_denial():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "¿MovIA Híbrido puede registrar proveedores en mi sistema contable?",
        lead_external_id="hibrido-external-system-review",
    )

    assert result.action == MacroAction.RECOMMEND_SOLUTION.value
    assert "MovIA Híbrido" in result.response
    assert "revisión técnica" in result.response
    assert "no se garantiza compatibilidad" in result.response
    assert "no puede" not in result.response.lower()


def test_phase3_explicit_start_language_is_not_need_to_think():
    analysis = heuristic_analysis("Ya estoy listo, pásame el link para empezar.")
    plan = plan_for(
        analysis,
        profile(
            known_product_fit=ProductFit.MOVIA_CAPTURA.value,
            confirmed_product=ProductFit.MOVIA_CAPTURA.value,
        ),
    )

    assert analysis.explicit_start_intent is True
    assert analysis.objection_type != ObjectionType.NEED_TO_THINK.value
    assert plan.macro_action == MacroAction.DIRECT_CLOSE.value


def test_phase3_unavailable_channels_are_not_presented_as_available():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Quiero Facebook e Instagram también, está disponible?",
        lead_external_id="phase3-channel-constraints",
    )
    lowered = result.response.lower()

    assert result.selected_action["micro_action"] == MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL.value
    assert "whatsapp business" in lowered
    assert "facebook e instagram están en proceso" in lowered
    assert "multicanal" not in lowered
    assert result.response_metadata["claim_constraints"]["channels"]["upcoming_not_available"] == [
        "facebook",
        "instagram",
    ]


def test_phase4_unsupported_channel_request_answers_channel_before_product_recommendation():
    analysis = TurnAnalysis(
        primary_intent=Intent.PRODUCT_RECOMMENDATION_QUESTION,
        topics=[Topic.PRODUCT_RECOMMENDATION, Topic.PRODUCT_SCOPE],
        main_channel="Instagram DMs y Facebook",
        lead_updates={
            "main_channel": "Instagram DMs y Facebook",
            "pain": "venda solo",
            "profile_data": {"action_requirement": ActionRequirement.ANSWERS_ONLY.value},
        },
    )
    plan = plan_for(
        analysis,
        {},
        normalized_turn={
            "action_requirement": ActionRequirement.ANSWERS_ONLY.value,
            "recommended_product": ProductFit.MOVIA_CAPTURA.value,
            "known_slot_values": {
                "main_channel": "Instagram DMs y Facebook",
                "pain_or_goal": "venda solo",
                "action_requirement": ActionRequirement.ANSWERS_ONLY.value,
            },
        },
        message="Quiero un agente para Instagram DMs y Facebook que venda solo.",
    )

    assert plan.macro_action == MacroAction.ANSWER_AND_ADVANCE.value
    assert plan.micro_action == MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL.value
    assert plan.target_stage == SalesStage.EDUCATING.value


def test_phase3_question_ctas_always_have_question_key():
    planner = SalesPolicyPlanner()
    scenarios = [
        planner.plan(TurnAnalysis(primary_intent=Intent.GREETING), {}),
        planner.plan(TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]), {}),
        planner.plan(
            TurnAnalysis(
                has_objection=True,
                objection_type=ObjectionType.PRICE_OBJECTION,
                objection_strength=ObjectionStrength.HARD,
            ),
            {},
        ),
    ]

    for plan in scenarios:
        if plan.cta_type in {
            CTAType.DISCOVERY_QUESTION.value,
            CTAType.SOFT_QUESTION.value,
            CTAType.OBJECTION_QUESTION.value,
        }:
            assert plan.next_question_key
            assert plan.next_question


def test_agent_answers_pricing_offline():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke("¿Cuánto cuesta?", lead_external_id="test-pricing")

    assert result.action == "answer_and_advance"
    assert "MovIA Captura" in result.response
    assert "$4,900 MXN" in result.response
    assert result.selected_action["reason_code"] == PlannerReasonCode.PRICE_QUESTION_WITH_DISCOVERY_GAP.value


def test_agent_recommends_hibrido_for_tickets_and_photos():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "Tengo proveedores que me mandan tickets y fotos, ¿qué agente necesito?",
        lead_external_id="test-hibrido",
    )

    assert "MovIA Híbrido" not in result.response
    assert result.action == "answer_and_advance"
    assert result.selected_action["micro_action"] == MicroAction.ANSWER_SCOPE_THEN_DISCOVER_BUSINESS.value
    assert result.selected_action["reason_code"] == PlannerReasonCode.SCOPE_QUESTION_WITH_DISCOVERY_GAP.value


def test_agent_combines_pricing_and_dental_rag_offline():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(
        "¿Cuál es el plan más barato y por qué me conviene para una clínica dental?",
        lead_external_id="test-dental",
    )

    assert result.action == "answer_and_advance"
    assert "MovIA Captura" in result.response
    assert "clínica dental" in result.response
    assert result.retrieval_metadata["rag_chunk_count"] >= 1
