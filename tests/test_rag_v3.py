from __future__ import annotations

from typing import Any, Dict, List, Optional

from movia_sales_agent.agent.planners import KnowledgePlanner, SalesPolicyPlanner
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    Intent,
    MacroAction,
    PlannerReasonCode,
    SalesStage,
    Topic,
)
from movia_sales_agent.evaluation.capabilities import source_capabilities
from movia_sales_agent.evaluation.models import ValidationTurn
from movia_sales_agent.evaluation.scoring import score_turn
from movia_sales_agent.memory.store import MemoryStore
from movia_sales_agent.models.schemas import ChatResponse, TurnAnalysis
from movia_sales_agent.services.openai_service import heuristic_analysis
from movia_sales_agent.services.rag import RagService, filter_relevant_contexts


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def knowledge_for(message: str, analysis: TurnAnalysis, lead_profile: Optional[Dict[str, Any]] = None):
    sales_plan = SalesPolicyPlanner().plan(
        analysis,
        lead_profile or {},
        message=message,
    )
    return KnowledgePlanner().plan(analysis, sales_plan, message)


def test_exact_price_policy_and_platform_questions_do_not_use_rag():
    cases = [
        (
            "¿Cuánto cuesta?",
            TurnAnalysis(primary_intent=Intent.PRICING_QUESTION, topics=[Topic.PRICING]),
        ),
        (
            "¿Hay reembolso?",
            TurnAnalysis(primary_intent=Intent.POLICY_QUESTION, topics=[Topic.REFUND_POLICY]),
        ),
        (
            "¿Cómo lleno la información en la página?",
            TurnAnalysis(primary_intent=Intent.PLATFORM_STEPS_QUESTION, topics=[Topic.PLATFORM_PROCESS]),
        ),
    ]

    for message, analysis in cases:
        knowledge_plan = knowledge_for(message, analysis)

        assert knowledge_plan.needs_rag is False
        assert knowledge_plan.rag_queries == []
        assert knowledge_plan.rag_metadata_filter == {}


def test_prior_reference_to_deposit_loads_memory_need_and_official_policy():
    message = "Tú dijiste que el depósito era 50%, ¿verdad?"
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        normalized_turn={"has_prior_reference": True},
    )

    assert "conversation_memory" in knowledge_plan.knowledge_needs
    assert "official_policy" in knowledge_plan.knowledge_needs
    assert "postgres.policies" in knowledge_plan.structured_sources


def test_audio_capability_question_loads_product_capabilities():
    message = "¿El agente puede entender audios de mis clientes?"
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        normalized_turn={"requested_agent_capabilities": ["understand_audio"]},
    )

    assert "product_capabilities" in knowledge_plan.knowledge_needs
    assert "postgres.products" in knowledge_plan.structured_sources


def test_multi_product_comparison_loads_official_product_facts_for_both_references():
    message = "¿Captura puede agendar o para eso necesito Híbrido?"
    analysis = TurnAnalysis(primary_intent=Intent.COMPARISON_QUESTION)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        normalized_turn={
            "product_references": [
                {"product": "movia_captura", "reference_role": "question_subject"},
                {
                    "product": "movia_hibrido",
                    "reference_role": "comparison_alternative",
                },
            ]
        },
    )

    assert "product_comparison" in knowledge_plan.knowledge_needs
    assert "product_capabilities" in knowledge_plan.knowledge_needs
    assert "postgres.products" in knowledge_plan.structured_sources


def test_direct_close_loads_products_policies_and_platform_steps_additively():
    message = "Quiero empezar con MovIA Captura, pásame el link."
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(
        analysis,
        {
            "profile_data": {
                "known_product_fit": "movia_captura",
                "selected_product": "movia_captura",
            }
        },
        message=message,
    )
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        normalized_turn={"selected_product": "movia_captura"},
    )

    assert "product_pricing" in knowledge_plan.knowledge_needs
    assert "official_policy" in knowledge_plan.knowledge_needs
    assert "platform_steps" in knowledge_plan.knowledge_needs
    assert "postgres.products" in knowledge_plan.structured_sources
    assert "postgres.policies" in knowledge_plan.structured_sources
    assert "platform_steps" in knowledge_plan.json_sources


def test_fulfillment_official_app_link_loads_official_links():
    message = "Pásame el link."
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        response_fulfillment_policy={
            "mandatory_fulfillments": ["official_app_link"],
            "next_question_policy": "replace_minimal",
            "minimal_question_key": "answer_or_actions",
        },
    )

    assert "official_app_link" in knowledge_plan.knowledge_needs
    assert "postgres.official_links" in knowledge_plan.structured_sources
    assert "platform_steps" in knowledge_plan.json_sources


def test_start_payment_followup_with_active_product_loads_pricing_policy_and_platform():
    message = "¿Y cuánto tengo que pagar para empezar?"
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(
        analysis,
        {
            "profile_data": {
                "product_context": {"active_product_context": "movia_hibrido"}
            }
        },
        message=message,
    )
    knowledge_plan = KnowledgePlanner().plan(
        analysis,
        sales_plan,
        message,
        normalized_turn={"active_product_context": "movia_hibrido"},
        lead_profile={
            "profile_data": {
                "product_context": {"active_product_context": "movia_hibrido"}
            }
        },
    )

    assert "product_pricing" in knowledge_plan.knowledge_needs
    assert "official_policy" in knowledge_plan.knowledge_needs
    assert "platform_steps" in knowledge_plan.knowledge_needs
    assert "postgres.products" in knowledge_plan.structured_sources
    assert "postgres.policies" in knowledge_plan.structured_sources
    assert "platform_steps" in knowledge_plan.json_sources


def test_industry_question_routes_to_relevant_industry_rag():
    message = "¿Por qué me conviene para una clínica dental?"
    analysis = heuristic_analysis(message)
    knowledge_plan = knowledge_for(message, analysis)

    assert knowledge_plan.needs_rag is True
    assert knowledge_plan.rag_metadata_filter == {"topic": "use_cases", "industry": "dental"}
    assert "dental" in knowledge_plan.rag_queries[0].lower()
    assert "postgres.products" in knowledge_plan.structured_sources


def test_comparison_question_routes_to_comparison_target_rag():
    message = "¿Esto es como ManyChat?"
    analysis = heuristic_analysis(message)
    knowledge_plan = knowledge_for(message, analysis)

    assert knowledge_plan.needs_rag is True
    assert knowledge_plan.rag_metadata_filter == {"topic": "comparisons", "comparison": "manychat"}
    assert knowledge_plan.rag_routing_reason == "comparison_target"


def test_rag_service_rejects_low_similarity_chunks_and_keeps_filtered_search_filtered():
    class FakeRepository:
        enabled = True

        def __init__(self):
            self.calls: List[Optional[Dict[str, Any]]] = []

        def match_knowledge(self, _embedding, match_count=3, metadata_filter=None):
            self.calls.append(metadata_filter)
            if metadata_filter:
                return []
            return [
                {
                    "id": "unfiltered",
                    "source_path": "rag_docs/product_explanations/facebook_agent.md",
                    "title": "Facebook",
                    "content": "Irrelevant future channel context.",
                    "metadata": {"topic": "product_explanations"},
                    "similarity": 0.95,
                }
            ]

    class FakeOpenAI:
        enabled = True
        settings = offline_settings()

        def embed_with_usage(self, _queries):
            return [[0.1, 0.2]], {
                "operation": "embedding",
                "model": "fake",
                "provider": "fake",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

    repository = FakeRepository()
    service = RagService(repository, FakeOpenAI(), MemoryStore(offline_settings()))

    contexts, _usage = service.retrieve_with_usage(
        ["dental"],
        metadata_filter={"topic": "use_cases", "industry": "dental"},
    )

    assert contexts == []
    assert repository.calls == [{"topic": "use_cases", "industry": "dental"}]
    assert filter_relevant_contexts(
        [
            {
                "id": "low",
                "source_path": "rag_docs/use_cases/dental.md",
                "metadata": {"topic": "use_cases", "industry": "dental"},
                "similarity": 0.20,
            }
        ]
    ) == []


def test_rag_metrics_score_necessity_routing_relevance_and_grounding():
    analysis = heuristic_analysis("¿Por qué me conviene para una clínica dental?")
    response = ChatResponse(
        action=MacroAction.PERSUADE_VALUE.value,
        response="Para una clínica dental, MovIA ayuda a responder rápido y ordenar prospectos.",
        response_messages=["Para una clínica dental, MovIA ayuda a responder rápido y ordenar prospectos."],
        analysis=analysis,
        lead_state={"current_stage": SalesStage.EDUCATING.value},
        selected_action={
            "macro_action": MacroAction.PERSUADE_VALUE.value,
            "micro_action": "industry_specific_value",
            "commercial_goal": "explain value",
            "cta_type": "soft_question",
            "objection_flow_step": "none",
            "target_stage": SalesStage.EDUCATING.value,
            "reason_code": PlannerReasonCode.INDUSTRY_VALUE_NEEDED.value,
        },
        knowledge_plan={
            "structured_sources": ["postgres.products"],
            "json_sources": [],
            "rag_queries": ["dental ¿Por qué me conviene?"],
            "rag_metadata_filter": {"topic": "use_cases", "industry": "dental"},
            "rag_routing_reason": "industry_use_case",
            "needs_rag": True,
        },
        retrieved_sources=[
            {
                "title": "Caso de uso: clínicas dentales",
                "source_path": "rag_docs/use_cases/dental.md",
                "similarity": 0.82,
                "metadata": {"topic": "use_cases", "industry": "dental"},
                "preview": "Las clínicas dentales reciben preguntas repetidas.",
            }
        ],
    )

    metrics, failures = score_turn(
        validation_turn=ValidationTurn(
            turn_id=1,
            user="¿Por qué me conviene para una clínica dental?",
            ideal_assistant="Respuesta",
            expected={},
        ),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth={"products": [], "official_links": []},
        scenario=type("Scenario", (), {"conversation_id": "rag"})(),
        user_history=[],
        scenario_business_terms={},
    )

    assert not failures
    by_name = {metric.name: metric for metric in metrics}
    assert by_name["rag.retrieval_necessity"].score == 1.0
    assert by_name["rag.routing_accuracy"].score == 1.0
    assert by_name["rag.context_relevance"].score == 1.0
    assert by_name["rag.answer_groundedness"].score == 1.0
