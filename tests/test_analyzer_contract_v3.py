import json

import pytest
from pydantic import ValidationError

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.planners import SalesPolicyPlanner
from movia_sales_agent.analyzer.contract_v3 import (
    ANALYZER_CONTRACT_VERSION,
    AnalyzerTurnObservation,
    analyzer_contract_document,
    validate_analyzer_observation,
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
        "requested_product": {"product": "none", "evidence_span": None},
        "objection_candidate": {
            "type": "none",
            "strength": "none",
            "relation": "none",
            "evidence_span": None,
        },
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
        },
    }


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


def test_objection_requires_evidence():
    payload = minimal_payload()
    payload["objection_candidate"] = {
        "type": "price_objection",
        "strength": "hard",
        "relation": "new",
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


def test_validator_sanitizes_none_objection_evidence_from_openai_payload():
    payload = minimal_payload()
    payload["objection_candidate"] = {
        "type": "none",
        "strength": "soft",
        "relation": "new",
        "evidence_span": "cuando nadie contesta",
    }

    observation = validate_analyzer_observation(payload, "Cuando nadie contesta perdemos leads.")

    assert observation.objection_candidate.type == "none"
    assert observation.objection_candidate.strength == "none"
    assert observation.objection_candidate.evidence_span is None


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
    contract_path = PROJECT_ROOT / "docs" / "architecture" / "ANALYZER_CONTRACT_V3_1.json"
    documented = json.loads(contract_path.read_text())

    assert documented == analyzer_contract_document()


def test_analyzer_schema_does_not_expose_banned_fields():
    schema = AnalyzerTurnObservation.model_json_schema()
    schema_text = json.dumps(schema)
    banned = analyzer_contract_document()["banned_llm_fields"]

    for field in banned:
        assert f'"{field}"' not in schema_text
