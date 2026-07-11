from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.analyzer.contract_v3 import (
    AgentActionObservation,
    AgentCapabilityObservation,
    AnalyzerExtractedFacts,
    AnalyzerReferenceType,
    AnalyzerTurnObservation,
    ObjectionCandidateObservation,
    PriorReferenceObservation,
    PurchaseReadinessObservation,
    RequestedProductObservation,
    legacy_analysis_to_observation,
)
from movia_sales_agent.analyzer.normalizer import (
    NORMALIZED_TURN_CONTRACT_VERSION,
    normalize_analyzer_turn,
    normalized_turn_to_analysis,
)
from movia_sales_agent.analyzer.shadow_parser import ShadowSignalParser
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    Intent,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionType,
    ProductFit,
)
from movia_sales_agent.services.openai_service import heuristic_analysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def normalize_message(message: str, lead_profile=None):
    observation = legacy_analysis_to_observation(heuristic_analysis(message), message)
    return normalize_analyzer_turn(
        observation,
        message=message,
        lead_profile=lead_profile or {},
        shadow_parser=ShadowSignalParser().parse(message).model_dump(),
    )


def test_price_question_derives_no_objection_no_start_unknown_requirement():
    normalized = normalize_message("¿Cuánto cuesta?")

    assert normalized.has_objection is False
    assert normalized.explicit_start_intent is False
    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value
    assert normalized.recommended_product is None


def test_answers_only_derives_captura_recommendation():
    normalized = normalize_message("Quiero que el agente responda dudas y capture datos.")

    assert set(normalized.requested_agent_capabilities) >= {
        "answer_customer_questions",
        "capture_lead_data",
    }
    assert set(normalized.requested_capabilities) >= {
        "answer_customer_questions",
        "capture_lead_data",
    }
    assert normalized.action_requirement == ActionRequirement.ANSWERS_ONLY.value
    assert normalized.recommended_product == ProductFit.MOVIA_CAPTURA.value
    assert "action_requirement" in normalized.known_slots


def test_external_actions_derive_hibrido_never_captura():
    normalized = normalize_message("Necesito que el agente cotice y registre pedidos en mi sistema.")

    assert set(normalized.requested_actions) >= {
        "generate_quote",
        "create_order",
        "write_external_system",
    }
    assert normalized.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    assert normalized.recommended_product == ProductFit.MOVIA_HIBRIDO.value
    assert normalized.recommended_product != ProductFit.MOVIA_CAPTURA.value


def test_business_problem_does_not_become_future_agent_capability():
    normalized = normalize_message("La gente pregunta precio y luego desaparece.")

    assert normalized.observed_business_problems
    assert normalized.requested_agent_capabilities == []
    assert normalized.requested_capabilities == []
    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value


def test_current_pricing_question_does_not_become_provide_prices():
    normalized = normalize_message("¿Cuánto cuesta?")

    assert "provide_prices" not in normalized.requested_agent_capabilities
    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value


def test_contract_valid_capability_passes_through_normalizer_without_cue_reclassification():
    message = "¿Cuánto cuesta?"
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRICING_QUESTION,
        requested_agent_capabilities=[
            AgentCapabilityObservation(type="provide_prices", evidence_span="Cuánto cuesta")
        ],
    )

    normalized = normalize_analyzer_turn(observation, message=message, shadow_parser={})

    assert "provide_prices" in normalized.requested_agent_capabilities
    assert normalized.action_requirement == ActionRequirement.ANSWERS_ONLY.value


def test_future_agent_pricing_request_becomes_provide_prices():
    normalized = normalize_message("Quiero que el agente dé precios automáticamente.")

    assert "provide_prices" in normalized.requested_agent_capabilities
    assert "provide_prices" in normalized.requested_capabilities
    assert normalized.action_requirement == ActionRequirement.ANSWERS_ONLY.value


def test_manual_scheduling_pain_does_not_become_schedule_appointment():
    normalized = normalize_message("Hoy agendamos manualmente y eso nos quita tiempo.")

    assert "manual_scheduling" in normalized.observed_business_problems
    assert "schedule_appointment" not in normalized.requested_agent_actions
    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value


def test_explicit_future_agent_scheduling_request_becomes_schedule_appointment():
    normalized = normalize_message("Necesito que el agente agende citas por WhatsApp.")

    assert "schedule_appointment" in normalized.requested_agent_actions
    assert normalized.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value


def test_contract_valid_action_passes_through_normalizer_without_cue_reclassification():
    message = "Ok, si eso queda claro, mándame el link para iniciar."
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.EXPLICIT_START_REQUEST,
        requested_agent_actions=[
            AgentActionObservation(
                type="schedule_appointment",
                evidence_span="mándame el link para iniciar",
            )
        ],
        purchase_readiness=PurchaseReadinessObservation(
            level=BuyingSignal.EXPLICIT_START,
            evidence_span="mándame el link para iniciar",
        ),
    )

    normalized = normalize_analyzer_turn(observation, message=message, shadow_parser={})

    assert normalized.requested_agent_actions == ["schedule_appointment"]
    assert normalized.action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value


def test_sales_closing_requirement_becomes_close_sale_without_compatibility_leak():
    normalized = normalize_message("Quiero que el agente cierre ventas por mí.")

    assert "close_sale" in normalized.requested_agent_capabilities
    assert normalized.requested_capabilities == []
    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value


def test_external_system_registration_request_yields_write_external_system():
    normalized = normalize_message("Necesito que el agente registre pedidos en mi sistema.")

    assert "write_external_system" in normalized.requested_agent_actions


def test_declared_external_action_count_requires_literal_count_evidence():
    normalized = normalize_message("Necesito como 3 acciones: cotizar, agendar y registrar.")

    assert normalized.declared_external_action_count == 3

    without_literal_count = normalize_message("Necesito varias acciones: cotizar, agendar y registrar.")
    assert without_literal_count.declared_external_action_count is None


def test_weak_inference_does_not_create_capability_or_action():
    normalized = normalize_message("Tal vez más adelante vemos si algo así podría ayudar.")

    assert normalized.requested_agent_capabilities == []
    assert normalized.requested_agent_actions == []


def test_explicit_start_derives_start_intent_without_need_to_think():
    message = "No quiero hablar con nadie, pásame el link y ya."
    normalized = normalize_message(message)
    analysis = normalized_turn_to_analysis(
        legacy_analysis_to_observation(heuristic_analysis(message), message),
        normalized,
        message=message,
    )

    assert normalized.explicit_start_intent is True
    assert analysis.explicit_start_intent is True
    assert analysis.objection_type != ObjectionType.NEED_TO_THINK.value


def test_false_historical_reference_before_pagar_is_removed():
    normalized = normalize_message("Antes de pagar quiero entender cómo empiezo.")

    assert normalized.has_prior_reference is False
    assert normalized.normalized_prior_reference["type"] == AnalyzerReferenceType.NONE.value


def test_direct_price_question_is_not_prior_reference_without_reference_cue():
    message = "Cuanto cuesta Captura?"
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRICING_QUESTION,
        requested_product=RequestedProductObservation(
            product="movia_captura",
            evidence_span="Captura",
        ),
        prior_reference=PriorReferenceObservation(
            type=AnalyzerReferenceType.TOPIC_REFERENCE,
            topic_hint="MovIA Captura product and pricing",
            evidence_span=message,
        ),
    )

    normalized = normalize_analyzer_turn(
        observation,
        message=message,
        shadow_parser={},
    )

    assert normalized.has_prior_reference is False
    assert normalized.normalized_prior_reference["type"] == AnalyzerReferenceType.NONE.value
    assert any(
        issue.contradiction_code == "false_prior_reference_without_reference_cue"
        for issue in normalized.contradictions
    )


def test_true_historical_reference_remains_detected():
    normalized = normalize_message("Como te dije antes, solo necesito respuestas.")

    assert normalized.has_prior_reference is True
    assert normalized.normalized_prior_reference["type"] != AnalyzerReferenceType.NONE.value


def test_true_historical_reference_with_topic_cue_remains_detected():
    message = "Lo de mis proveedores, era Captura o Hibrido?"
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRODUCT_RECOMMENDATION_QUESTION,
        prior_reference=PriorReferenceObservation(
            type=AnalyzerReferenceType.TOPIC_REFERENCE,
            topic_hint="proveedores",
            evidence_span="Lo de mis proveedores",
        ),
    )

    normalized = normalize_analyzer_turn(
        observation,
        message=message,
        shadow_parser={},
    )

    assert normalized.has_prior_reference is True
    assert normalized.normalized_prior_reference["type"] == AnalyzerReferenceType.TOPIC_REFERENCE.value


def test_invalid_objection_evidence_is_normalized_to_none():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.GENERAL_INFO,
        objection_candidate=ObjectionCandidateObservation(
            type=ObjectionType.PRICE_OBJECTION,
            strength=ObjectionStrength.HARD,
            relation=ObjectionRelation.NEW,
            evidence_span="se me hace caro",
        ),
    )

    normalized = normalize_analyzer_turn(
        observation,
        message="¿Cuánto cuesta?",
        shadow_parser={},
    )

    assert normalized.has_objection is False
    assert normalized.normalized_objection["type"] == ObjectionType.NONE.value
    assert any(issue.contradiction_code == "invalid_objection_evidence" for issue in normalized.contradictions)


def test_invalid_explicit_start_evidence_is_not_start_intent():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRICING_QUESTION,
        purchase_readiness=PurchaseReadinessObservation(
            level=BuyingSignal.EXPLICIT_START,
            evidence_span="pásame el link",
        ),
    )

    normalized = normalize_analyzer_turn(
        observation,
        message="¿Cuánto cuesta?",
        shadow_parser={},
    )

    assert normalized.explicit_start_intent is False
    assert any(
        issue.contradiction_code == "explicit_start_without_valid_evidence"
        for issue in normalized.contradictions
    )


def test_product_preference_mismatch_keeps_requested_recommended_selected_separate():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRODUCT_SCOPE_QUESTION,
        extracted_facts=AnalyzerExtractedFacts(main_channel="whatsapp"),
        requested_product=RequestedProductObservation(
            product="movia_hibrido",
            evidence_span="Híbrido",
        ),
        requested_agent_capabilities=[
            AgentCapabilityObservation(
                type="answer_customer_questions",
                evidence_span="solo que responda dudas",
            )
        ],
    )

    normalized = normalize_analyzer_turn(
        observation,
        message="Quiero el Híbrido, pero solo que responda dudas por WhatsApp.",
        shadow_parser={},
    )

    assert normalized.requested_product == "movia_hibrido"
    assert normalized.recommended_product == ProductFit.MOVIA_CAPTURA.value
    assert normalized.selected_product is None
    assert normalized.product_preference_mismatch is True


def test_unavailable_requested_product_is_not_selected():
    observation = AnalyzerTurnObservation(
        primary_intent=Intent.PRODUCT_SCOPE_QUESTION,
        requested_product=RequestedProductObservation(
            product="movia_ventas",
            evidence_span="MovIA Ventas",
        ),
    )

    normalized = normalize_analyzer_turn(
        observation,
        message="Quiero MovIA Ventas.",
        shadow_parser={},
    )

    assert normalized.requested_product == "movia_ventas"
    assert normalized.selected_product is None
    assert any(
        issue.contradiction_code == "unavailable_product_not_selected"
        for issue in normalized.contradictions
    )


def test_product_reference_does_not_imply_selection():
    normalized = normalize_message("¿Cuánto cuesta Captura?")

    assert normalized.requested_product == "movia_captura"
    assert normalized.selected_product is None


def test_parser_only_action_does_not_override_llm_observation():
    message = "Necesito que cotice."
    observation = AnalyzerTurnObservation(primary_intent=Intent.PRODUCT_SCOPE_QUESTION)
    parser = ShadowSignalParser().parse(message).model_dump()

    normalized = normalize_analyzer_turn(
        observation,
        message=message,
        shadow_parser=parser,
    )

    assert normalized.action_requirement == ActionRequirement.UNKNOWN.value
    assert normalized.recommended_product is None
    assert normalized.parser_llm_telemetry.requested_actions.parser_only == ["generate_quote"]
    assert normalized.parser_llm_telemetry.requested_actions.conflict is True


def test_parser_llm_agreement_is_recorded_when_both_detect_action():
    normalized = normalize_message("Necesito que cotice.")

    assert "generate_quote" in normalized.parser_llm_telemetry.requested_actions.agreement


def test_graph_exposes_normalized_turn_and_uses_it_for_memory():
    result = MoviaSalesAgent(offline_settings()).invoke(
        "Necesito que cotice y registre pedidos en mi sistema.",
        lead_external_id="analyzer-normalized-graph",
    )

    normalized = result.response_metadata["normalized_turn"]
    assert normalized["normalized_turn_contract_version"] == NORMALIZED_TURN_CONTRACT_VERSION
    assert normalized["action_requirement"] == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    assert normalized["recommended_product"] == ProductFit.MOVIA_HIBRIDO.value
    assert result.analysis.lead_updates.profile_data["known_product_fit"] == ProductFit.MOVIA_HIBRIDO.value
    assert result.response_metadata["parser_llm_telemetry"]["requested_actions"]["agreement"]
