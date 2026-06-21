from __future__ import annotations

from movia_sales_agent.evaluation.models import (
    DatasetValidationSummary,
    EvaluationRunResult,
    HardFailure,
    MetricResult,
    ScenarioEvaluationResult,
    TurnEvaluationResult,
)
from movia_sales_agent.evaluation.phase6 import (
    REQUIRED_PHASE6_COLUMNS,
    REQUIRED_PHASE6_MIGRATIONS,
    combined_phase6_recommendation,
    evaluate_phase6_gates,
    markdown_phase6_gate_report,
)


def make_summary() -> DatasetValidationSummary:
    return DatasetValidationSummary(
        valid=True,
        evaluation_contract_version="3.0",
        commercial_contract_version="2.0",
        agent_contract_version="2.0",
        suite_type="coherent_scripted",
        causal_continuity=True,
        dataset_version="test",
        run_mode="scripted_replay",
        scenario_count=1,
        turn_count=1,
        scenario_ids=["S1"],
    )


def make_run(**scores) -> EvaluationRunResult:
    turn = TurnEvaluationResult(
        run_id="run",
        conversation_id="S1",
        turn_id=1,
        user_input="user",
        ideal_response="ideal",
        agent_output="answer",
        metrics=[
            MetricResult(
                name="response_quality.critical_defects",
                category="response_quality",
                status="passed",
                score=1.0,
                actual=[],
            )
        ],
    )
    scenario = ScenarioEvaluationResult(
        run_id="run",
        conversation_id="S1",
        persona="persona",
        difficulty="test",
        success_goal="goal",
        lead_external_id="lead",
        turns=[turn],
        passed=True,
    )
    default_scores = {
        "commercial_accuracy": 1.0,
        "policy_compliance": 1.0,
        "scope_control": 1.0,
        "memory_consistency": 1.0,
        "source_selection": 1.0,
        "response_quality": 1.0,
        "sales_progression": 0.8,
        "objection_handling": 0.8,
    }
    default_scores.update(scores)
    return EvaluationRunResult(
        suite_type="coherent_scripted",
        causal_continuity=True,
        dataset_version="test",
        run_mode="scripted_replay",
        run_id="run",
        started_at="now",
        completed_at="now",
        dataset_path="dataset.json",
        dataset_summary=make_summary(),
        scenario_results=[scenario],
        category_scores=default_scores,
        overall_score=0.9,
        passed=True,
    )


def test_phase6_gates_pass_with_required_scores():
    report = evaluate_phase6_gates(make_run(), require_progression=True)

    assert report["passed"] is True
    assert all(gate["status"] == "pass" for gate in report["gates"])


def test_phase6_gates_fail_on_hard_failures_and_quality_defects():
    run = make_run(response_quality=0.5)
    run.hard_failures = [
        HardFailure(code="unknown_price", category="commercial_accuracy", reason="bad")
    ]
    run.scenario_results[0].turns[0].metrics[0].actual = ["asked_known_information"]
    run.scenario_results[0].turns[0].metrics[0].status = "failed"

    report = evaluate_phase6_gates(run, require_progression=True)
    failed = {gate["name"] for gate in report["gates"] if gate["status"] == "fail"}

    assert report["passed"] is False
    assert "hard_failures_zero" in failed
    assert "response_quality_minimum" in failed
    assert "known_slot_critical_repetitions_zero" in failed


def test_phase6_recommendation_requires_db_and_adaptive_hybrid():
    ready_db = {
        "ready": True,
        "missing_migrations": [],
        "missing_columns": [],
        "table_counts": {},
    }
    blocked_db = {
        "ready": False,
        "missing_migrations": REQUIRED_PHASE6_MIGRATIONS,
        "missing_columns": REQUIRED_PHASE6_COLUMNS,
        "table_counts": {},
    }
    passing = {"passed": True, "suite_type": "atomic_scripted", "run_id": "run", "gates": []}

    assert combined_phase6_recommendation(
        database_status=blocked_db,
        gate_reports=[passing],
    )["recommendation"] == "NOT READY"
    assert combined_phase6_recommendation(
        database_status=ready_db,
        gate_reports=[passing],
    )["recommendation"] == "READY FOR PREDEPLOY HYBRID ONLY"
    assert combined_phase6_recommendation(
        database_status=ready_db,
        gate_reports=[passing],
        adaptive_hybrid_ran=True,
        adaptive_hybrid_passed=True,
    )["recommendation"] == "READY FOR LIMITED PILOT"


def test_phase6_markdown_report_includes_database_and_gates():
    db = {
        "status": "ready",
        "ready": True,
        "missing_migrations": [],
        "missing_columns": [],
        "table_counts": {"movia_products": 4},
    }
    gate_report = {
        "suite_type": "atomic_scripted",
        "run_id": "run",
        "gates": [{"name": "hard_failures_zero", "threshold": 0, "actual": 0, "status": "pass"}],
    }
    markdown = markdown_phase6_gate_report(
        database_status=db,
        gate_reports=[gate_report],
        recommendation={"recommendation": "READY FOR PREDEPLOY HYBRID ONLY", "reason": "ok"},
    )

    assert "# Phase 6 Gate Report" in markdown
    assert "movia_products rows" in markdown
    assert "hard_failures_zero" in markdown
