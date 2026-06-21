from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.memory import (
    build_structured_memory,
    next_question_for_missing_slot,
    retrieve_conversation_memory,
)
from movia_sales_agent.agent.planners import SalesPolicyPlanner
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    CTAType,
    Intent,
    MacroAction,
    ProductFit,
    ReferenceType,
    Topic,
)
from movia_sales_agent.evaluation.capabilities import source_capabilities
from movia_sales_agent.evaluation.models import ValidationScenario, ValidationTurn
from movia_sales_agent.evaluation.scoring import score_turn
from movia_sales_agent.models.schemas import ChatResponse
from movia_sales_agent.models.schemas import TurnAnalysis
from movia_sales_agent.services.openai_service import heuristic_analysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def test_structured_memory_derives_product_fit_and_forbidden_questions():
    analysis = TurnAnalysis(
        lead_updates={
            "profile_data": {
                "requirement_profile": {
                    "requirement_profile_version": "1.0",
                    "observed_business_problems": [],
                    "informational_capabilities": [
                        {"type": "answer_customer_questions", "active": True}
                    ],
                    "sales_capabilities": [],
                    "external_actions": [],
                    "declared_external_action_count": None,
                    "requirement_class": "informational_only",
                    "first_confirmed_turn": 1,
                    "last_updated_turn": 1,
                    "sources": {},
                },
            }
        }
    )
    memory = build_structured_memory(
        analysis,
        {
            "business_type": "dental",
            "main_channel": "whatsapp",
            "pain": "missed_leads",
            "profile_data": {},
        },
    )

    assert memory["known_slots"]["action_requirement"] == ActionRequirement.ANSWERS_ONLY.value
    assert memory["known_slots"]["known_product_fit"] == ProductFit.MOVIA_CAPTURA.value
    assert memory["missing_slots"] == []
    assert set(memory["forbidden_question_keys"]) == {
        "business_type",
        "main_channel",
        "pain_or_goal",
        "action_requirement",
    }
    assert memory["requirement_class"] == "informational_only"


def test_requirement_profile_external_actions_prevent_reasking_action_requirement():
    requirement_profile = {
        "requirement_profile_version": "1.0",
        "observed_business_problems": [],
        "informational_capabilities": [],
        "sales_capabilities": [],
        "external_actions": [
            {"type": "generate_quote", "active": True},
            {"type": "write_external_system", "active": True},
        ],
        "declared_external_action_count": None,
        "requirement_class": "external_actions",
        "first_confirmed_turn": 1,
        "last_updated_turn": 1,
        "sources": {},
    }
    memory = build_structured_memory(
        TurnAnalysis(
            lead_updates={"profile_data": {"requirement_profile": requirement_profile}}
        ),
        {"profile_data": {}},
    )

    assert memory["known_slots"]["action_requirement"] == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    assert "action_requirement" not in memory["missing_slots"]
    assert "action_requirement" in memory["forbidden_question_keys"]

    stale_memory = {**memory, "missing_slots": ["action_requirement"]}
    assert next_question_for_missing_slot(stale_memory) == (None, None)


def test_question_ctas_have_question_key_or_are_downgraded_to_none():
    planner = SalesPolicyPlanner()
    known_profile = {
        "business_type": "dental",
        "main_channel": "whatsapp",
        "pain": "leads_disappear_after_price_question",
        "profile_data": {
            "action_requirement": ActionRequirement.ANSWERS_ONLY.value,
            "known_product_fit": ProductFit.MOVIA_CAPTURA.value,
        },
    }
    complete = planner.plan(
        TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]),
        known_profile,
        message="Cuanto cuesta Captura?",
    )
    incomplete = planner.plan(
        TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]),
        {},
        message="Cuanto cuesta?",
    )

    assert complete.cta_type == CTAType.NONE.value
    assert complete.next_question_key is None
    assert incomplete.cta_type == CTAType.SOFT_QUESTION.value
    assert incomplete.next_question_key == "business_type"


def test_turn4_regression_does_not_reask_known_slots():
    agent = MoviaSalesAgent(offline_settings())
    lead_id = "phase3-turn4"

    agent.invoke(
        "Hola, tengo una clinica dental y nos llegan muchos WhatsApps de anuncios.",
        lead_external_id=lead_id,
    )
    agent.invoke(
        "El problema es que preguntan precios y nadie contesta rapido.",
        lead_external_id=lead_id,
    )
    agent.invoke(
        "Solo quiero que responda dudas y capture datos del paciente.",
        lead_external_id=lead_id,
    )
    result = agent.invoke("Cuanto cuesta Captura?", lead_external_id=lead_id)

    lowered = result.response.lower()
    assert result.action == MacroAction.ANSWER_AND_ADVANCE.value
    assert "$4,900 MXN" in result.response
    assert "qué tipo de negocio" not in lowered
    assert "que tipo de negocio" not in lowered
    assert "por dónde te escriben" not in lowered
    assert "por donde te escriben" not in lowered
    assert "qué quieres mejorar" not in lowered
    assert "que quieres mejorar" not in lowered
    assert result.response_metadata["memory_validation"]["violations"] == []
    assert result.lead_state["profile_data"]["known_product_fit"] == ProductFit.MOVIA_CAPTURA.value


def test_heuristic_detects_prior_message_reference_fields():
    analysis = heuristic_analysis("Cual era el plan que me recomendaste?")

    assert analysis.references_prior_message is True
    assert analysis.reference_type == ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value
    assert analysis.reference_query
    assert Topic.PRODUCT_RECOMMENDATION.value in analysis.referenced_topics
    assert analysis.reference_confidence >= 0.8


def test_prior_memory_retrieval_is_conditional_and_relevant():
    no_reference = heuristic_analysis("Cuanto cuesta?")
    reference = heuristic_analysis("Lo de mis proveedores, era Captura o Hibrido?")
    recent = [
        {"role": "user", "content": "Tengo proveedores que mandan ticket, foto y datos de garantia."},
        {"role": "assistant", "content": "Para ese flujo conviene MovIA Híbrido."},
        {"role": "user", "content": "Cuanto cuesta?"},
        {"role": "assistant", "content": "Híbrido cuesta $7,500 MXN de setup."},
    ]

    assert retrieve_conversation_memory(no_reference, recent) == []
    evidence = retrieve_conversation_memory(reference, recent)

    assert evidence
    assert evidence[0]["turn_id"] == 1
    assert "proveedores" in evidence[0]["user_message"].lower()
    assert "Híbrido" in evidence[0]["assistant_message"]


def test_offline_agent_resolves_prior_reference_without_cross_lead_leakage():
    agent = MoviaSalesAgent(offline_settings())
    lead_a = "phase3-memory-a"
    lead_b = "phase3-memory-b"

    agent.invoke(
        "Quiero que el agente cotice y registre pedidos de mis proveedores en mi sistema.",
        lead_external_id=lead_a,
    )
    reference_a = agent.invoke(
        "Lo de mis proveedores, era Captura o Hibrido?",
        lead_external_id=lead_a,
    )
    reference_b = agent.invoke(
        "Lo de mis proveedores, era Captura o Hibrido?",
        lead_external_id=lead_b,
    )

    assert reference_a.analysis.references_prior_message is True
    assert reference_a.retrieval_metadata["conversation_memory_lookup"] == "used"
    assert reference_a.retrieval_metadata["conversation_memory_evidence"]
    assert "Híbrido" in reference_a.response
    assert reference_b.retrieval_metadata["conversation_memory_lookup"] == "used"
    assert reference_b.retrieval_metadata["conversation_memory_evidence"] == []


def test_memory_metrics_are_emitted_for_reference_turns():
    analysis = TurnAnalysis(
        references_prior_message=True,
        reference_type=ReferenceType.ASSISTANT_COMMITMENT_REFERENCE,
        reference_query="Cual era el plan que me recomendaste?",
        referenced_topics=[Topic.PRODUCT_RECOMMENDATION],
        reference_confidence=0.9,
    )
    response = ChatResponse(
        action=MacroAction.RECOMMEND_SOLUTION.value,
        response="El plan que veníamos perfilando era MovIA Captura.",
        response_messages=["El plan que veníamos perfilando era MovIA Captura."],
        analysis=analysis,
        lead_state={
            "business_type": "dental",
            "main_channel": "whatsapp",
            "pain": "missed_leads",
            "profile_data": {
                "action_requirement": ActionRequirement.ANSWERS_ONLY.value,
                "known_product_fit": ProductFit.MOVIA_CAPTURA.value,
            },
        },
        selected_action={
            "macro_action": MacroAction.RECOMMEND_SOLUTION.value,
            "micro_action": "recommend_movia_captura",
            "cta_type": "none",
            "objection_flow_step": "none",
        },
        retrieval_metadata={
            "conversation_memory_evidence": [
                {
                    "turn_id": 2,
                    "user_message": "Solo quiero responder dudas.",
                    "assistant_message": "Te conviene MovIA Captura.",
                    "relevance_reason": "assistant_commitment_reference",
                }
            ]
        },
        response_metadata={"memory_validation": {"violations": [], "corrected": False}},
    )

    metrics, failures = score_turn(
        validation_turn=ValidationTurn(
            turn_id=4,
            user="Cual era el plan que me recomendaste?",
            ideal_assistant="Captura.",
            expected={},
        ),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth={"products": [], "official_links": []},
        scenario=ValidationScenario(
            conversation_id="MOVIA-MEM-TEST",
            persona="memory test",
            difficulty="medium",
            success_goal="memory",
        ),
        user_history=["Solo quiero responder dudas."],
        scenario_business_terms={},
    )

    assert not failures
    scores = {metric.name: metric.score for metric in metrics if metric.name.startswith("memory.")}
    assert scores["memory.known_slot_repetition"] == 1.0
    assert scores["memory.historical_reference_accuracy"] == 1.0
    assert scores["memory.prior_commitment_consistency"] == 1.0
    assert scores["memory.contextual_personalization"] == 1.0
