import json

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.response import (
    BASE_SYSTEM_PROMPT,
    build_generation_context,
    response_package_token_estimates,
)
from movia_sales_agent.agent.planners import KnowledgePlanner, SalesPolicyPlanner
from movia_sales_agent.config.knowledge import load_config_bundle, load_policies_seed, load_products_seed
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import MacroAction, MicroAction, ProductFit
from movia_sales_agent.ingestion.chunker import estimate_tokens
from movia_sales_agent.services.openai_service import heuristic_analysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def test_generation_context_is_compact_symbolic_package():
    analysis = heuristic_analysis("Solo responder. ¿Cuánto cuesta?")
    sales_plan = SalesPolicyPlanner().plan(
        analysis,
        {
            "business_type": "dental",
            "main_channel": "whatsapp",
            "profile_data": {"action_requirement": "answers_only"},
        },
        message="Solo responder. ¿Cuánto cuesta?",
    )
    structured_context = {
        "products": load_products_seed(),
        "policies": load_policies_seed(),
    }
    json_context = load_config_bundle()

    compact = build_generation_context(
        analysis,
        sales_plan,
        structured_context,
        json_context,
        rag_context=[],
        recent_messages=[],
        lead_profile={"business_type": "dental", "main_channel": "whatsapp"},
    )

    assert set(compact) == {
        "commercial_instruction",
        "lead_context",
        "official_facts",
        "playbook_instruction",
        "turn_signal_context",
        "response_fulfillment_policy",
        "memory_context",
        "rag_context",
        "recent_messages",
        "claim_constraints",
        "response_requirements",
    }
    assert "structured_context" not in compact
    assert "json_context" not in compact
    assert compact["commercial_instruction"]["macro_action"] == MacroAction.ANSWER_AND_ADVANCE.value
    assert compact["official_facts"]["products"][0]["setup_price_mxn"] == 4900
    assert compact["playbook_instruction"]["cta"]["type"] == "soft_question"
    assert compact["claim_constraints"]["channels"]["available_now"] == ["whatsapp_business"]


def test_compact_context_is_smaller_than_legacy_context_shape():
    message = "Solo responder. ¿Cuánto cuesta?"
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    structured_context = {"products": load_products_seed(), "policies": load_policies_seed()}
    json_context = load_config_bundle()
    compact = build_generation_context(
        analysis,
        sales_plan,
        structured_context,
        json_context,
        rag_context=[],
        recent_messages=[],
    )
    legacy = {
        "analysis": analysis.model_dump(),
        "sales_plan": sales_plan.model_dump(),
        "structured_context": structured_context,
        "json_context": json_context,
        "rag_context": [],
        "recent_messages": [],
        "response_requirements": [
            "Contestar la duda explícita.",
            "Usar solo datos del contexto.",
            "Si hay precio estructurado y RAG de industria, combinar ambos en la respuesta.",
            "Redactar en formato WhatsApp: bloques breves, legibles y escaneables.",
            "Cerrar con una pregunta o CTA comercial suave salvo en handoff.",
            "No mencionar arquitectura interna.",
        ],
    }

    compact_tokens = response_package_token_estimates(
        compact, BASE_SYSTEM_PROMPT, message
    )["context_total_estimate"]
    legacy_tokens = estimate_tokens(json.dumps(legacy, ensure_ascii=False, default=str))

    assert compact_tokens < legacy_tokens * 0.65


def test_rag_context_is_bounded_and_deduplicated():
    analysis = heuristic_analysis("¿Esto es como ManyChat?")
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message="¿Esto es como ManyChat?")
    rag_context = [
        {
            "title": f"Doc {index}",
            "source_path": f"rag_docs/comparisons/doc_{index}.md",
            "content": "contenido largo " * 120,
            "metadata": {"topic": "comparisons", "comparison": "manychat", "extra": "drop"},
        }
        for index in range(5)
    ]
    compact = build_generation_context(
        analysis,
        sales_plan,
        {"products": load_products_seed()},
        load_config_bundle(),
        rag_context=rag_context,
        recent_messages=[],
    )

    assert len(compact["rag_context"]) == 3
    assert all(len(chunk["preview"]) <= 650 for chunk in compact["rag_context"])
    assert all("extra" not in chunk["metadata"] for chunk in compact["rag_context"])


def test_phase3_response_package_includes_signals_and_claim_constraints():
    message = "Necesito que cotice y registre pedidos en mi sistema."
    analysis = heuristic_analysis(message)
    normalized_turn = {
        "action_requirement": "external_actions_required",
        "requested_product": "none",
        "recommended_product": ProductFit.MOVIA_HIBRIDO.value,
        "requested_actions": ["generate_quote", "create_order", "write_external_system"],
        "known_slots": ["action_requirement"],
        "missing_slots": ["business_type", "main_channel", "pain_or_goal"],
    }
    sales_plan = SalesPolicyPlanner().plan(
        analysis,
        {},
        normalized_turn=normalized_turn,
        message=message,
    )
    compact = build_generation_context(
        analysis,
        sales_plan,
        {"products": load_products_seed()},
        load_config_bundle(),
        rag_context=[],
        recent_messages=[],
        normalized_turn=normalized_turn,
    )

    assert sales_plan.micro_action == MicroAction.RECOMMEND_MOVIA_HIBRIDO.value
    assert compact["commercial_instruction"]["micro_action"] == MicroAction.RECOMMEND_MOVIA_HIBRIDO.value
    assert compact["turn_signal_context"]["recommended_product"] == ProductFit.MOVIA_HIBRIDO.value
    assert compact["claim_constraints"]["external_action_routing"] == {
        "required_product": ProductFit.MOVIA_HIBRIDO.value,
        "forbidden_product": ProductFit.MOVIA_CAPTURA.value,
    }
    assert "párrafos cortos" in BASE_SYSTEM_PROMPT
    assert any("No describas ningún producto MovIA como multicanal" in item for item in compact["response_requirements"])


def test_response_metadata_includes_package_token_estimates():
    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke("¿Cuánto cuesta?", lead_external_id="phase6-token-metadata")

    estimates = result.response_metadata["response_package_token_estimates"]
    assert estimates["system_prompt"] > 0
    assert estimates["official_facts"] > 0
    assert estimates["claim_constraints"] > 0
    assert estimates["response_input_total_estimate"] < 1700
    response_call = next(
        call for call in result.token_usage["calls"] if call["operation"] == "response"
    )
    assert "response_package_estimates" in response_call["details"]


def test_fulfillment_policy_replaces_broad_question_in_context_only():
    message = "Pásame el link."
    analysis = heuristic_analysis(message)
    sales_plan = SalesPolicyPlanner().plan(analysis, {}, message=message)
    original_question = sales_plan.next_question
    compact = build_generation_context(
        analysis,
        sales_plan,
        {"official_links": [{"link_type": "app", "url": "https://app.moviatech.com.mx"}]},
        load_config_bundle(),
        rag_context=[],
        recent_messages=[],
        response_fulfillment_policy={
            "mandatory_fulfillments": ["official_app_link"],
            "next_question_policy": "replace_minimal",
            "minimal_question_key": "answer_or_actions",
            "preserve_commercial_plan": True,
            "preserve_commercial_stage": True,
        },
    )

    assert sales_plan.next_question == original_question
    assert compact["playbook_instruction"]["micro_action"]["next_question_key"] == "answer_or_actions"
    assert "¿solo necesitas que responda/capture información" in compact["playbook_instruction"]["micro_action"]["next_question"]
    assert any("Incluye el link oficial" in item for item in compact["response_requirements"])
