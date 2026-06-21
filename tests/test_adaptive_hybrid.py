from __future__ import annotations

from movia_sales_agent.evaluation.adaptive_hybrid import (
    PERSONAS,
    SEEDS,
    _deterministic_violations,
    _gate_summary,
)
from movia_sales_agent.evaluation.cli import build_parser


def test_adaptive_hybrid_cli_command_is_registered():
    args = build_parser().parse_args(["adaptive-hybrid-pilot", "--no-fail-exit"])

    assert args.command == "adaptive-hybrid-pilot"


def test_adaptive_hybrid_persona_seed_shape_matches_pilot_spec():
    assert len(PERSONAS) == 7
    assert SEEDS == [101, 202]
    assert len(PERSONAS) * len(SEEDS) == 14


def test_link_request_requires_link_and_official_source():
    persona = PERSONAS[0]
    turn = {
        "user_input": "Pásame el link.",
        "agent_response": "Claro, para orientarte primero dime qué quieres automatizar.",
        "analysis": {"explicit_start_intent": True},
        "normalized_turn": {},
        "selected_action": {"macro_action": "discover_need", "next_question_key": "automation_need"},
        "knowledge_plan": {"structured_sources": []},
        "response_metadata": {
            "response_source": "openai",
            "response_fulfillment_policy": {},
        },
        "response_source": "openai",
    }

    violations = _deterministic_violations(
        turn_record=turn,
        previous_turns=[],
        persona=persona,
    )

    assert any(item["code"] == "official_link_requested_not_delivered" for item in violations)
    assert _gate_summary([{"deterministic_violations": violations}])["hard_failures"] >= 1


def test_link_delivery_requires_official_links_source_when_policy_applies():
    persona = PERSONAS[0]
    turn = {
        "user_input": "Pásame el link.",
        "agent_response": "Claro, aquí está el link oficial: https://app.moviatech.com.mx. ¿Quieres que te guíe?",
        "analysis": {"explicit_start_intent": True},
        "normalized_turn": {},
        "selected_action": {"macro_action": "answer_and_advance", "next_question_key": "automation_need"},
        "knowledge_plan": {"structured_sources": []},
        "response_metadata": {
            "response_source": "openai",
            "response_fulfillment_policy": {
                "mandatory_fulfillments": ["official_app_link"],
                "next_question_policy": "replace_minimal",
            },
        },
        "response_source": "openai",
    }

    violations = _deterministic_violations(
        turn_record=turn,
        previous_turns=[],
        persona=persona,
    )

    assert any(item["code"] == "mandatory_source_not_loaded" for item in violations)
