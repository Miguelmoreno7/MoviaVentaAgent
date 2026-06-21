from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.evaluation.models import TurnEvaluationResult
from movia_sales_agent.evaluation.response_quality import (
    CRITICAL_RESPONSE_DEFECTS,
    RESPONSE_QUALITY_DIMENSIONS,
    ResponseQualityDimensionScore,
    ResponseQualityJudgment,
    build_quality_input,
    judge_deterministically,
    response_quality_json_schema,
)
from movia_sales_agent.evaluation.runner import EvaluationRunner
from movia_sales_agent.models.schemas import ChatResponse, TurnAnalysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def make_turn(
    *,
    user: str = "Cuanto cuesta?",
    response: str = "MovIA Captura cuesta $4,900 MXN. ¿Que flujo quieres automatizar?",
    action: str = "answer_and_advance",
    cta_type: str = "soft_question",
    analysis=None,
    lead_state=None,
) -> TurnEvaluationResult:
    return TurnEvaluationResult(
        run_id="rq-test",
        conversation_id="MOVIA-VAL-001",
        turn_id=1,
        user_input=user,
        ideal_response="Respuesta",
        agent_output=response,
        response_messages=[response],
        analysis=analysis or {"topics": ["pricing"], "explicit_start_intent": False},
        lead_state=lead_state or {},
        selected_action={
            "macro_action": action,
            "micro_action": "answer_price_then_explain_scope",
            "commercial_goal": "advance",
            "cta_type": cta_type,
            "objection_flow_step": "none",
        },
        knowledge_plan={"structured_sources": ["postgres.products"]},
    )


def test_response_quality_schema_requires_all_dimensions_and_known_defects():
    judgment = ResponseQualityJudgment(
        dimension_scores={
            dimension: ResponseQualityDimensionScore(score=4, evidence="ok")
            for dimension in RESPONSE_QUALITY_DIMENSIONS
        },
        critical_defects=["poor_next_step"],
        overall_response_quality=0.72,
        summary="Structured and reproducible.",
    )

    assert judgment.critical_defects == ["poor_next_step"]
    assert set(judgment.dimension_scores) == set(RESPONSE_QUALITY_DIMENSIONS)
    schema = response_quality_json_schema()
    assert set(schema["properties"]["dimension_scores"]["required"]) == set(
        RESPONSE_QUALITY_DIMENSIONS
    )

    with pytest.raises(ValidationError):
        ResponseQualityJudgment(
            dimension_scores={
                RESPONSE_QUALITY_DIMENSIONS[0]: ResponseQualityDimensionScore(
                    score=4,
                    evidence="missing the rest",
                )
            },
            critical_defects=["made_up_defect"],
            overall_response_quality=0.5,
            summary="invalid",
        )


def test_deterministic_quality_flags_known_slot_repetition():
    turn = make_turn(
        user="Tengo una clinica dental y me escriben por WhatsApp.",
        response="Perfecto. ¿Que tipo de negocio tienes?",
        lead_state={"business_type": "dental", "main_channel": "whatsapp"},
    )
    quality_input = build_quality_input(turn, [], {"products": [], "official_links": []})

    judgment = judge_deterministically(quality_input, turn)

    assert "asked_known_information" in judgment.critical_defects
    assert judgment.dimension_scores["non_repetition"].score == 1
    assert judgment.overall_response_quality < 0.75


def test_deterministic_quality_accepts_direct_price_answer():
    turn = make_turn()
    quality_input = build_quality_input(turn, [], {"products": [], "official_links": []})

    judgment = judge_deterministically(quality_input, turn)

    assert judgment.critical_defects == []
    assert judgment.dimension_scores["directness"].score >= 4
    assert judgment.overall_response_quality >= 0.75


def test_deterministic_quality_flags_premature_direct_close():
    turn = make_turn(
        user="Cuanto cuesta?",
        response="Empieza en app.moviatech.com.mx.",
        action="direct_close",
        cta_type="direct_close",
        analysis={"topics": ["pricing"], "explicit_start_intent": False},
    )
    quality_input = build_quality_input(turn, [], {"products": [], "official_links": []})

    judgment = judge_deterministically(quality_input, turn)

    assert "premature_close" in judgment.critical_defects
    assert judgment.overall_response_quality < 0.75


class FakeAgent:
    def invoke(self, message, lead_external_id, channel, external_message_id):
        response = "MovIA Captura cuesta $4,900 MXN. ¿Que flujo quieres automatizar?"
        return ChatResponse(
            action="answer_and_advance",
            response=response,
            response_messages=[response],
            analysis=TurnAnalysis.model_validate(
                {
                    "primary_intent": "pricing_question",
                    "topics": ["pricing"],
                    "explicit_start_intent": False,
                }
            ),
            lead_state={"current_stage": "educating", "last_action": "answer_and_advance"},
            selected_action={
                "macro_action": "answer_and_advance",
                "micro_action": "answer_price_then_explain_scope",
                "commercial_goal": "advance",
                "cta_type": "soft_question",
                "objection_flow_step": "none",
                "target_stage": "educating",
                "reason_code": "price_question_with_discovery_gap",
            },
            knowledge_plan={
                "structured_sources": ["postgres.products"],
                "json_sources": [],
                "rag_queries": [],
                "needs_rag": False,
            },
            retrieved_sources=[],
        )


def test_runner_attaches_response_quality_metrics_and_can_skip():
    runner = EvaluationRunner(
        settings=offline_settings(),
        agent_factory=lambda: FakeAgent(),
        enable_ragas=False,
        enable_deepeval=False,
        enable_response_quality=True,
    )
    result = runner.run(scenario_id="MOVIA-VAL-001", max_turns=1, offline=True)

    metric_names = {metric.name for metric in result.scenario_results[0].turns[0].metrics}
    assert "response_quality.overall" in metric_names
    assert "response_quality.critical_defects" in metric_names

    skipped_runner = EvaluationRunner(
        settings=offline_settings(),
        agent_factory=lambda: FakeAgent(),
        enable_ragas=False,
        enable_deepeval=False,
        enable_response_quality=False,
    )
    skipped = skipped_runner.run(scenario_id="MOVIA-VAL-001", max_turns=1, offline=True)
    quality = [
        metric
        for metric in skipped.scenario_results[0].turns[0].metrics
        if metric.name == "response_quality.overall"
    ]
    assert quality and quality[0].status == "skipped"


def test_response_quality_calibration_dataset_has_required_examples():
    path = Path("movia_validation_package/response_quality_calibration.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    labels = {example["label"] for example in payload["examples"]}

    assert len(payload["examples"]) >= 10
    assert set(payload["rubric_dimensions"]) == set(RESPONSE_QUALITY_DIMENSIONS)
    assert set(payload["critical_defects"]) == set(CRITICAL_RESPONSE_DEFECTS)
    assert {
        "excellent",
        "acceptable",
        "weak",
        "repetitive",
        "wrong_next_question",
    } <= labels
