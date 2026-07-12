import json

import pytest
from pydantic import ValidationError

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.planners import SalesPolicyPlanner
from movia_sales_agent.analyzer.contract_v3 import (
    ANALYZER_CONTRACT_VERSION,
    ANALYZER_V3_SCHEMA,
    AnalyzerTurnObservation,
    ProductReferenceObservation,
    ProductReferenceRole,
    analyzer_contract_document,
    validate_analyzer_observation,
)
from movia_sales_agent.services.openai_service import (
    _apply_contextual_observation_invariants,
    _analyzer_schema_for_context,
    compact_analyzer_recent_messages,
)
from movia_sales_agent.analyzer.shadow_parser import ShadowSignalParser
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import Intent
from movia_sales_agent.services.openai_service import heuristic_analysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def minimal_payload():
    return {
        "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
        "primary_intent": "pricing_question",
        "secondary_intents": [],
        "extracted_facts": {
            "business_type": None,
            "main_channel": "whatsapp",
            "pain_or_goal": None,
            "urgency": None,
        },
        "observed_business_problems": [],
        "requested_agent_capabilities": [],
        "requested_agent_actions": [],
        "declared_external_action_count": None,
        "requirement_update_intent": "no_change",
        "product_references": [],
        "objection_candidate": {
            "type": "none",
            "strength": "none",
            "evidence_span": None,
        },
        "active_objection_relation": {"relation": "none", "evidence_span": None},
        "purchase_readiness": {"level": "medium", "evidence_span": None},
        "prior_reference": {"type": "none", "topic_hint": None, "evidence_span": None},
        "post_purchase_signal": {"detected": False, "evidence_span": None},
        "confidence": {
            "intent": 0.9,
            "facts": 0.9,
            "capabilities": 0.9,
            "actions": 0.9,
            "objection": 0.9,
            "purchase_readiness": 0.9,
            "prior_reference": 0.9,
            "post_purchase": 0.9,
            "requirement_update": 0.9,
        },
    }


def test_analyzer_history_keeps_last_six_text_turns_without_runtime_metadata():
    messages = [
        {
            "role": "assistant" if index % 2 else "user",
            "content": f"message-{index}",
            "retrieval_metadata": {"large": "diagnostic-state"},
            "analysis": {"reply_frame": {"next_question_key": "business_type"}},
        }
        for index in range(7)
    ]

    compact = compact_analyzer_recent_messages(messages)

    assert compact == [
        {
            "role": "assistant" if index % 2 else "user",
            "content": f"message-{index}",
        }
        for index in range(1, 7)
    ]


@pytest.mark.parametrize("field", ["has_objection", "known_product_fit", "explicit_turn_number"])
def test_analyzer_v3_rejects_legacy_dependent_fields(field):
    payload = minimal_payload()
    payload[field] = False

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_analyzer_v3_rejects_nested_known_product_fit():
    payload = minimal_payload()
    payload["extracted_facts"]["known_product_fit"] = "movia_captura"

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_analyzer_v3_2_rejects_legacy_requested_product_peer_field():
    payload = minimal_payload()
    payload["requested_product"] = {
        "product": "movia_captura",
        "evidence_span": "Captura",
    }

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_product_references_dedupe_by_contract_role_precedence():
    observation = AnalyzerTurnObservation(
        product_references=[
            ProductReferenceObservation(
                product="movia_captura",
                evidence_span="Captura",
                reference_role=ProductReferenceRole.MENTIONED,
            ),
            ProductReferenceObservation(
                product="movia_captura",
                evidence_span="Captura",
                reference_role=ProductReferenceRole.COMMITTED,
            ),
        ]
    )

    assert len(observation.product_references) == 1
    assert observation.product_references[0].reference_role == "committed"


def test_validator_drops_product_inferred_only_from_conversation_context():
    payload = minimal_payload()
    payload["product_references"] = [
        {
            "product": "movia_hibrido",
            "evidence_span": "esa parte",
            "reference_role": "question_subject",
        }
    ]
    payload["prior_reference"] = {
        "type": "implicit_prior_reference",
        "topic_hint": "explicación anterior",
        "evidence_span": "esa parte",
    }

    observation = validate_analyzer_observation(payload, "Explícame esa parte")

    assert observation.product_references == []
    assert observation.prior_reference.type == "implicit_prior_reference"


def test_objection_requires_evidence():
    payload = minimal_payload()
    payload["objection_candidate"] = {
        "type": "price_objection",
        "strength": "hard",
        "evidence_span": None,
    }

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_prior_reference_requires_evidence():
    payload = minimal_payload()
    payload["prior_reference"] = {
        "type": "topic_reference",
        "topic_hint": "proveedores",
        "evidence_span": None,
    }

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_explicit_start_requires_evidence():
    payload = minimal_payload()
    payload["purchase_readiness"] = {"level": "explicit_start", "evidence_span": None}

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_requested_actions_require_evidence():
    payload = minimal_payload()
    payload["requested_agent_actions"] = [{"type": "generate_quote", "evidence_span": ""}]

    with pytest.raises(ValidationError):
        AnalyzerTurnObservation.model_validate(payload)


def test_evidence_must_exist_in_current_message():
    payload = minimal_payload()
    payload["requested_agent_actions"] = [{"type": "generate_quote", "evidence_span": "que cotice"}]

    observation = validate_analyzer_observation(payload, "Solo quiero que responda dudas.")

    assert observation.requested_agent_actions == []


def test_validator_drops_action_whose_literal_span_does_not_support_its_ontology():
    payload = minimal_payload()
    payload["requirement_update_intent"] = "merge"
    payload["requested_agent_actions"] = [
        {
            "type": "generate_quote",
            "evidence_span": "que el agente cotice a mis clientes",
        },
        {
            "type": "take_payment",
            "evidence_span": "que el agente cotice a mis clientes; mándame el link",
        },
    ]

    observation = validate_analyzer_observation(
        payload,
        "Quiero que el agente cotice a mis clientes; mándame el link",
    )

    assert [item.type for item in observation.requested_agent_actions] == ["generate_quote"]


def test_validator_preserves_conjugated_payment_action_evidence():
    payload = minimal_payload()
    payload["requirement_update_intent"] = "merge"
    payload["requested_agent_actions"] = [
        {
            "type": "take_payment",
            "evidence_span": "cobre anticipos a mis clientes",
        }
    ]

    observation = validate_analyzer_observation(
        payload,
        "Necesito que el agente cobre anticipos a mis clientes",
    )

    assert [item.type for item in observation.requested_agent_actions] == ["take_payment"]


def test_validator_drops_capabilities_not_supported_by_their_literal_evidence():
    payload = minimal_payload()
    payload["requirement_update_intent"] = "merge"
    payload["requested_agent_capabilities"] = [
        {
            "type": "provide_catalog_information",
            "evidence_span": "cotice los paquetes",
        },
        {
            "type": "handle_sales_objections",
            "evidence_span": "cotice los paquetes",
        },
        {
            "type": "answer_customer_questions",
            "evidence_span": "responda dudas",
        },
    ]

    observation = validate_analyzer_observation(
        payload,
        "Quiero que cotice los paquetes y responda dudas",
    )

    assert [item.type for item in observation.requested_agent_capabilities] == [
        "answer_customer_questions"
    ]


def test_validator_sanitizes_none_objection_evidence_from_openai_payload():
    payload = minimal_payload()
    payload["objection_candidate"] = {
        "type": "none",
        "strength": "soft",
        "evidence_span": "cuando nadie contesta",
    }

    observation = validate_analyzer_observation(payload, "Cuando nadie contesta perdemos leads.")

    assert observation.objection_candidate.type == "none"
    assert observation.objection_candidate.strength == "none"
    assert observation.objection_candidate.evidence_span is None


def test_validator_drops_malformed_candidate_without_losing_active_relation():
    payload = minimal_payload()
    payload["objection_candidate"] = {
        "type": "price_objection",
        "strength": "none",
        "evidence_span": "ya me hace sentido",
    }
    payload["active_objection_relation"] = {
        "relation": "resolved",
        "evidence_span": "ya me hace sentido",
    }

    observation = validate_analyzer_observation(
        payload,
        "Bueno, con ese ahorro ya me hace sentido",
    )

    assert observation.objection_candidate.type == "none"
    assert observation.objection_candidate.strength == "none"
    assert observation.active_objection_relation.relation == "resolved"


def test_validator_drops_nonliteral_prior_reference_without_cue():
    payload = minimal_payload()
    payload["prior_reference"] = {
        "type": "topic_reference",
        "topic_hint": "precio",
        "evidence_span": "la parte anterior",
    }

    observation = validate_analyzer_observation(payload, "Cuanto cuesta Captura?")

    assert observation.prior_reference.type == "none"
    assert observation.prior_reference.topic_hint is None


def test_validator_repairs_prior_reference_evidence_with_literal_cue():
    payload = minimal_payload()
    payload["prior_reference"] = {
        "type": "topic_reference",
        "topic_hint": "proveedores",
        "evidence_span": "la parte anterior",
    }

    observation = validate_analyzer_observation(payload, "Lo de mis proveedores, cual era?")

    assert observation.prior_reference.type == "topic_reference"
    assert observation.prior_reference.evidence_span == "lo de"


def test_validator_repairs_contract_version_from_openai_payload():
    payload = minimal_payload()
    payload["analyzer_contract_version"] = "3"

    observation = validate_analyzer_observation(payload, "Cuanto cuesta?")

    assert observation.analyzer_contract_version == ANALYZER_CONTRACT_VERSION


def test_valid_evidence_accepts_accents_case_and_punctuation():
    payload = minimal_payload()
    payload["purchase_readiness"] = {
        "level": "explicit_start",
        "evidence_span": "pasame el link",
    }

    observation = validate_analyzer_observation(payload, "Pásame el link, porfa.")

    assert observation.purchase_readiness.level == "explicit_start"


def test_shadow_parser_detects_candidates_but_does_not_modify_analysis():
    message = "Necesito que cotice y registre pedidos en mi sistema."
    parser_result = ShadowSignalParser().parse(message)

    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(message, lead_external_id="analyzer-shadow-no-override")

    assert {candidate["type"] for candidate in result.response_metadata["shadow_parser"]["action_candidates"]} >= {
        "generate_quote",
        "create_order",
            "write_external_system",
        }
    assert result.response_metadata["normalized_turn"]["requested_actions"] == [
        "generate_quote",
        "create_order",
        "write_external_system",
    ]
    assert result.analysis.lead_updates.profile_data["action_requirement"] == "external_actions_required"
    assert parser_result.shadow_parser_may_override is False
    assert result.response_metadata["shadow_parser"]["shadow_parser_may_override"] is False


def test_shadow_parser_never_changes_planner_behavior():
    message = "Solo quiero que responda dudas y capture datos."
    expected_analysis = heuristic_analysis(message)
    expected_plan = SalesPolicyPlanner().plan(expected_analysis, {}, message=message)

    agent = MoviaSalesAgent(offline_settings())
    result = agent.invoke(message, lead_external_id="analyzer-shadow-planner")

    assert result.selected_action["macro_action"] == expected_plan.macro_action
    assert result.selected_action["micro_action"] == expected_plan.micro_action


def test_parser_trace_and_analyzer_observation_are_observable():
    result = MoviaSalesAgent(offline_settings()).invoke(
        "Pásame el link para empezar.",
        lead_external_id="analyzer-trace",
    )

    assert result.response_metadata["analyzer_contract_version"] == ANALYZER_CONTRACT_VERSION
    assert result.response_metadata["analyzer_observation"]["analyzer_contract_version"] == ANALYZER_CONTRACT_VERSION
    assert result.response_metadata["analyzer_observation"]["primary_intent"] == Intent.EXPLICIT_START_REQUEST.value
    assert result.response_metadata["shadow_parser"]["purchase_cue_candidates"]


def test_contract_json_matches_runtime_source():
    contract_path = PROJECT_ROOT / "docs" / "architecture" / "ANALYZER_CONTRACT_V3_2.json"
    documented = json.loads(contract_path.read_text())

    assert documented == analyzer_contract_document()


def test_analyzer_schema_does_not_expose_banned_fields():
    schema = AnalyzerTurnObservation.model_json_schema()
    schema_text = json.dumps(schema)
    banned = analyzer_contract_document()["banned_llm_fields"]

    for field in banned:
        assert f'"{field}"' not in schema_text


def test_strict_analyzer_schema_does_not_attach_keywords_to_refs():
    def visit(node):
        if isinstance(node, dict):
            if "$ref" in node:
                assert set(node) == {"$ref"}
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(ANALYZER_V3_SCHEMA)


def test_strict_analyzer_schema_omits_nonsemantic_titles():
    def visit(node):
        if isinstance(node, dict):
            assert "title" not in node
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(ANALYZER_V3_SCHEMA)


def test_active_objection_context_excludes_only_none_relation_from_request_schema():
    request_schema = _analyzer_schema_for_context(
        {"commercial_state": {"active_objection": {"type": "price_objection"}}}
    )

    request_values = request_schema["$defs"]["AnalyzerActiveObjectionRelation"]["enum"]
    contract_values = ANALYZER_V3_SCHEMA["$defs"]["AnalyzerActiveObjectionRelation"]["enum"]
    assert "none" not in request_values
    assert "unrelated" in request_values
    assert "none" in contract_values


def test_unrelated_relation_clears_only_duplicate_active_objection_candidate():
    observation = AnalyzerTurnObservation(
        objection_candidate={
            "type": "price_objection",
            "strength": "hard",
            "evidence_span": "cuánto tarda",
        },
        active_objection_relation={
            "relation": "unrelated",
            "evidence_span": "cuánto tarda",
        },
    )

    repairs = _apply_contextual_observation_invariants(
        observation,
        {"commercial_state": {"active_objection": {"type": "price_objection"}}},
    )

    assert observation.objection_candidate.type == "none"
    assert repairs == ["duplicate_active_objection_candidate_cleared_for_relation"]


def test_unrelated_relation_preserves_a_different_new_objection_type():
    observation = AnalyzerTurnObservation(
        objection_candidate={
            "type": "trust_objection",
            "strength": "hard",
            "evidence_span": "no confío",
        },
        active_objection_relation={
            "relation": "unrelated",
            "evidence_span": "no confío",
        },
    )

    repairs = _apply_contextual_observation_invariants(
        observation,
        {"commercial_state": {"active_objection": {"type": "price_objection"}}},
    )

    assert observation.objection_candidate.type == "trust_objection"
    assert repairs == []


def test_explicit_start_intent_label_requires_explicit_purchase_readiness():
    observation = AnalyzerTurnObservation(
        primary_intent="explicit_start_request",
        requested_agent_actions=[
            {"type": "generate_quote", "evidence_span": "cotice"}
        ],
        purchase_readiness={"level": "none", "evidence_span": None},
    )

    assert observation.primary_intent == "product_scope_question"
