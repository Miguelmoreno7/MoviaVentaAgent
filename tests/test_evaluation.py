from pathlib import Path

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import COMMERCIAL_CONTRACT_VERSION, MacroAction
from movia_sales_agent.evaluation.capabilities import source_capabilities
from movia_sales_agent.evaluation.dataset import (
    COHERENT_SCRIPTED_DATASET_PATH,
    contract_value_errors,
    load_adaptive_hybrid_interface,
    load_validation_dataset,
    validate_dataset,
)
from movia_sales_agent.evaluation.contracts_v3 import (
    EVALUATION_CONTRACT_VERSION,
    SuiteType,
)
from movia_sales_agent.evaluation.models import MetricResult, ValidationTurn
from movia_sales_agent.evaluation.reporting import report_counters, write_reports
from movia_sales_agent.evaluation.runner import EvaluationRunner
from movia_sales_agent.evaluation.scoring import (
    category_scores,
    scenario_business_terms,
    score_turn,
    weighted_score,
)
from movia_sales_agent.models.schemas import ChatResponse, TurnAnalysis


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def make_response(
    text: str = "MovIA Captura cuesta $4,900 MXN y responde por WhatsApp.",
    action: str = "answer_and_advance",
    stage: str = "qualified",
    micro_action: str = "answer_price_then_explain_scope",
    cta_type: str = "soft_question",
    analysis: TurnAnalysis = None,
    structured_sources=None,
    json_sources=None,
    retrieved_sources=None,
    response_metadata=None,
) -> ChatResponse:
    return ChatResponse(
        action=action,
        response=text,
        response_messages=[text],
        analysis=analysis or TurnAnalysis(),
        lead_state={"current_stage": stage, "last_action": action},
        selected_action={
            "macro_action": action,
            "micro_action": micro_action,
            "commercial_goal": "advance",
            "cta_type": cta_type,
            "objection_flow_step": None,
        },
        knowledge_plan={
            "structured_sources": structured_sources or [],
            "json_sources": json_sources or [],
            "rag_queries": [],
            "needs_rag": bool(retrieved_sources),
        },
        retrieved_sources=retrieved_sources or [],
        response_metadata=response_metadata or {},
        token_usage={
            "total": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        },
    )


def current_ground_truth():
    return {
        "products": [
            {
                "name": "MovIA Captura",
                "status": "available",
                "setup_price_mxn": 4900,
                "monthly_price_mxn": 450,
            },
            {
                "name": "MovIA Híbrido",
                "status": "available",
                "setup_price_mxn": 7500,
                "monthly_price_mxn": 550,
            },
            {
                "name": "Agente MovIA Ventas",
                "status": "not_available",
                "setup_price_mxn": 13500,
                "monthly_price_mxn": 1000,
            },
        ],
        "policies": {},
        "official_links": [{"url": "https://app.moviatech.com.mx"}],
    }


def test_validation_dataset_has_five_scenarios_and_sixty_turns():
    dataset = load_validation_dataset()
    summary = validate_dataset(dataset)

    assert summary.valid is True
    assert dataset.evaluation_contract_version == EVALUATION_CONTRACT_VERSION
    assert dataset.suite_type == SuiteType.ATOMIC_SCRIPTED.value
    assert dataset.causal_continuity is False
    assert dataset.agent_contract_version == COMMERCIAL_CONTRACT_VERSION
    assert dataset.commercial_contract_version == COMMERCIAL_CONTRACT_VERSION
    assert summary.evaluation_contract_version == EVALUATION_CONTRACT_VERSION
    assert summary.commercial_contract_version == COMMERCIAL_CONTRACT_VERSION
    assert summary.suite_type == SuiteType.ATOMIC_SCRIPTED.value
    assert summary.causal_continuity is False
    assert summary.scenario_count == 5
    assert summary.turn_count == 60
    assert summary.unsupported_expected_fields == []
    assert summary.unsupported_expected_sources == []


def test_coherent_scripted_dataset_validates_structurally():
    dataset = load_validation_dataset(COHERENT_SCRIPTED_DATASET_PATH)
    summary = validate_dataset(dataset)

    assert summary.valid is True
    assert summary.evaluation_contract_version == EVALUATION_CONTRACT_VERSION
    assert summary.suite_type == SuiteType.COHERENT_SCRIPTED.value
    assert summary.causal_continuity is True
    assert summary.scenario_count == 7
    assert all(8 <= len(scenario.turns) <= 15 for scenario in dataset.scenarios)
    assert summary.unsupported_expected_fields == []
    assert summary.unsupported_expected_sources == []


def test_adaptive_hybrid_interface_is_defined_but_disabled():
    interface = load_adaptive_hybrid_interface()

    assert interface.evaluation_contract_version == EVALUATION_CONTRACT_VERSION
    assert interface.suite_type == SuiteType.ADAPTIVE_HYBRID.value
    assert interface.predeploy_only is True
    assert interface.enabled is False
    assert interface.lead_specs


def test_dataset_validation_rejects_unreachable_gold_expectations():
    dataset = load_validation_dataset().model_copy(deep=True)
    dataset.evaluation_contract_version = "2.0"
    dataset.commercial_contract_version = "1.0"
    dataset.scenarios[0].turns[0].expected["macro_action"] = "made_up_action"
    dataset.scenarios[0].turns[0].expected["expected_sources"].append(
        "postgres.product_actions"
    )
    dataset.scenarios[0].turns[0].expected["unsupported_trace"] = "anything"

    summary = validate_dataset(dataset)

    assert summary.valid is False
    assert "unsupported_trace" in summary.unsupported_expected_fields
    assert "postgres.product_actions" in summary.unsupported_expected_sources
    assert any("evaluation_contract_version" in error for error in summary.errors)
    assert any("commercial_contract_version" in error for error in summary.errors)
    assert any("macro_action='made_up_action'" in error for error in summary.errors)
    assert any("Unsupported expected source" in error for error in summary.errors)


def test_contract_value_helper_validates_v2_values_without_mutating_gold_dataset():
    assert contract_value_errors(
        {
            "macro_action": MacroAction.ANSWER_AND_ADVANCE.value,
            "micro_action": "answer_price_then_explain_scope",
            "final_cta_type": "soft_question",
            "objection_type": "none",
            "objection_flow_step": "none",
            "current_stage": "discovery",
        }
    ) == []
    assert contract_value_errors({"macro_action": "made_up_action"})


def test_unsupported_expected_fields_and_sources_are_not_applicable():
    dataset = load_validation_dataset()
    scenario = dataset.scenarios[0]
    validation_turn = ValidationTurn(
        turn_id=1,
        user="Cuanto cuesta?",
        ideal_assistant="Respuesta",
        expected={
            "macro_action": "answer_and_advance",
            "unsupported_trace": "anything",
            "expected_sources": ["postgres.products", "postgres.product_actions"],
        },
    )
    response = make_response(structured_sources=["postgres.products"])

    metrics, failures = score_turn(
        validation_turn=validation_turn,
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=scenario,
        user_history=[],
        scenario_business_terms=scenario_business_terms(dataset.scenarios),
    )

    assert not failures
    unsupported = {metric.name: metric.status for metric in metrics}
    assert unsupported["expected.unsupported_trace"] == "not_applicable"
    assert unsupported["source.postgres.product_actions"] == "not_applicable"
    source_recall = next(metric for metric in metrics if metric.name == "source.expected_recall")
    assert source_recall.score == 1.0


def test_deposit_hard_rule_ignores_confidence_percentage():
    response = make_response(
        text="Sí, 100% seguro. El depósito para iniciar es del 50%.",
    )

    _, failures = score_turn(
        validation_turn=ValidationTurn(turn_id=1, user="¿El depósito es 50%?", ideal_assistant="", expected={}),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=type("Scenario", (), {"conversation_id": "deposit"})(),
        user_history=[],
        scenario_business_terms={},
    )

    assert "incorrect_deposit_percentage" not in {failure.code for failure in failures}


def test_generic_warranty_word_is_not_cross_scenario_memory_leak():
    response = make_response(text="También puede ayudarte a ordenar tickets, fotos y garantías.")

    _, failures = score_turn(
        validation_turn=ValidationTurn(turn_id=1, user="Tengo proveedores con tickets y garantías.", ideal_assistant="", expected={}),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=type("Scenario", (), {"conversation_id": "current"})(),
        user_history=[],
        scenario_business_terms={"other": {"garantias"}, "current": set()},
    )

    assert "cross_scenario_memory_leak" not in {failure.code for failure in failures}


def test_skipped_and_not_applicable_metrics_do_not_change_denominator():
    scores = category_scores(
        [
            MetricResult(
                name="one",
                category="commercial_accuracy",
                status="passed",
                score=1.0,
            ),
            MetricResult(
                name="skip",
                category="commercial_accuracy",
                status="skipped",
                score=0.0,
            ),
            MetricResult(
                name="na",
                category="commercial_accuracy",
                status="not_applicable",
                score=0.0,
            ),
        ]
    )

    assert scores["commercial_accuracy"] == 1.0


def test_atomic_scripted_progression_is_diagnostic_not_primary_score():
    scores = {
        "commercial_accuracy": 1.0,
        "policy_compliance": 1.0,
        "scope_control": 1.0,
        "sales_progression": 0.0,
        "objection_handling": 0.0,
    }

    assert weighted_score(scores, SuiteType.ATOMIC_SCRIPTED.value) == 1.0
    assert weighted_score(scores, SuiteType.COHERENT_SCRIPTED.value) < 1.0


def test_official_link_with_sentence_punctuation_is_allowed():
    dataset = load_validation_dataset()
    scenario = dataset.scenarios[0]
    response = make_response(text="Empieza en https://app.moviatech.com.mx.")

    _metrics, failures = score_turn(
        validation_turn=ValidationTurn(
            turn_id=1,
            user="Dame el link",
            ideal_assistant="Link",
            expected={},
        ),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=scenario,
        user_history=[],
        scenario_business_terms=scenario_business_terms(dataset.scenarios),
    )

    assert not failures


def test_hard_failures_detect_unsupported_commercial_and_policy_claims():
    dataset = load_validation_dataset()
    scenario = dataset.scenarios[4]
    validation_turn = ValidationTurn(
        turn_id=1,
        user="Puedo pedir reembolso y usar Instagram?",
        ideal_assistant="No.",
        expected={},
    )
    response = make_response(
        text=(
            "Si hay reembolso. Instagram ya funciona. "
            "MovIA Captura puede agendar. Cuesta $9,999 MXN."
        )
    )

    _metrics, failures = score_turn(
        validation_turn=validation_turn,
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=scenario,
        user_history=[],
        scenario_business_terms=scenario_business_terms(dataset.scenarios),
    )
    codes = {failure.code for failure in failures}

    assert "unknown_price" in codes
    assert "incorrect_refund_policy" in codes
    assert "future_channel_sold_as_available" in codes
    assert "captura_scope_overpromise" in codes


def test_post_purchase_without_handoff_is_a_hard_failure():
    dataset = load_validation_dataset()
    scenario = dataset.scenarios[2]
    response = make_response(
        text="Te ayudo por aqui.",
        analysis=TurnAnalysis(is_post_purchase=True),
    )

    _metrics, failures = score_turn(
        validation_turn=ValidationTurn(
            turn_id=12,
            user="Ya pague, que sigue?",
            ideal_assistant="Miguel te ayuda.",
            expected={},
        ),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=scenario,
        user_history=[],
        scenario_business_terms=scenario_business_terms(dataset.scenarios),
    )

    assert {failure.code for failure in failures} == {"missing_post_purchase_handoff"}


def test_post_purchase_gated_response_without_confirmed_deposit_is_not_hard_failure():
    dataset = load_validation_dataset()
    scenario = dataset.scenarios[2]
    response = make_response(
        text=(
            "Una vez que el depósito quede confirmado en la plataforma, tendrás acceso al "
            "seguimiento personalizado. Mientras tanto, puedo ayudarte por aquí con cualquier duda del proceso."
        ),
        action=MacroAction.EXPLAIN_PROCESS.value,
        micro_action="explain_human_handoff",
        analysis=TurnAnalysis(is_post_purchase=True),
        response_metadata={"purchase_status": {"status": "not_checked"}},
    )

    _metrics, failures = score_turn(
        validation_turn=ValidationTurn(
            turn_id=12,
            user="Ya pague, que sigue?",
            ideal_assistant="Miguel te ayuda.",
            expected={},
        ),
        response=response,
        source_capabilities=source_capabilities(),
        ground_truth=current_ground_truth(),
        scenario=scenario,
        user_history=[],
        scenario_business_terms=scenario_business_terms(dataset.scenarios),
    )

    assert "missing_post_purchase_handoff" not in {failure.code for failure in failures}


class FakeAgent:
    def __init__(self, calls):
        self.calls = calls

    def invoke(self, message, lead_external_id, channel, external_message_id):
        self.calls.append(
            {
                "message": message,
                "lead_external_id": lead_external_id,
                "channel": channel,
                "external_message_id": external_message_id,
            }
        )
        return make_response()


def test_runner_uses_isolated_tagged_leads_and_writes_reports(tmp_path: Path):
    calls = []
    runner = EvaluationRunner(
        settings=offline_settings(),
        agent_factory=lambda: FakeAgent(calls),
        enable_ragas=False,
        enable_deepeval=False,
        enable_response_quality=False,
    )

    result = runner.run(scenario_id="all", max_turns=1, offline=True)
    output = write_reports(result, tmp_path)

    lead_ids = {call["lead_external_id"] for call in calls}
    assert len(calls) == 5
    assert len(lead_ids) == 5
    assert {call["channel"] for call in calls} == {"evaluation"}
    assert all(call["external_message_id"].startswith("eval:") for call in calls)
    assert (output / "run.json").exists()
    assert (output / "turns.jsonl").exists()
    assert (output / "summary.md").exists()
    summary = (output / "summary.md").read_text(encoding="utf-8")
    assert "MovIA Validation Report" in summary
    assert "## Pass Policy" in summary
    assert "## Score Groups" in summary
    assert "**Evaluation contract:** 3.0" in summary
    assert "**Suite type:** atomic_scripted" in summary
    assert "## Failure Inventory" in summary
    assert "soft_trace_mismatches" in summary
    assert f"**Commercial contract:** {COMMERCIAL_CONTRACT_VERSION}" in summary


def test_runner_accepts_mocked_framework_metrics():
    calls = []
    runner = EvaluationRunner(
        settings=offline_settings(),
        agent_factory=lambda: FakeAgent(calls),
        enable_ragas=False,
        enable_deepeval=False,
        enable_response_quality=False,
    )
    runner.ragas.enabled = True
    runner.ragas.evaluate_turn = lambda _turn: [
        MetricResult(
            name="ragas.mock",
            category="source_selection",
            status="passed",
            score=1.0,
            framework="ragas",
        )
    ]
    runner.deepeval.enabled = True
    runner.deepeval.evaluate_scenario = lambda _scenario, _result, _ground_truth: [
        MetricResult(
            name="deepeval.mock",
            category="memory_consistency",
            status="passed",
            score=1.0,
            framework="deepeval",
        )
    ]

    result = runner.run(scenario_id="MOVIA-VAL-001", max_turns=1, offline=True)

    assert result.commercial_contract_version == COMMERCIAL_CONTRACT_VERSION
    assert any(
        metric.name == "ragas.mock"
        for metric in result.scenario_results[0].turns[0].metrics
    )
    assert result.scenario_results[0].conversation_metrics[0].name == "deepeval.mock"


def test_report_counters_separate_failure_buckets():
    calls = []
    runner = EvaluationRunner(
        settings=offline_settings(),
        agent_factory=lambda: FakeAgent(calls),
        enable_ragas=False,
        enable_deepeval=False,
        enable_response_quality=False,
    )
    runner.ragas.enabled = True
    runner.ragas.evaluate_turn = lambda _turn: [
        MetricResult(
            name="ragas.bad",
            category="source_selection",
            status="failed",
            score=0.0,
            framework="ragas",
        )
    ]

    result = runner.run(scenario_id="MOVIA-VAL-001", max_turns=1, offline=True)
    result.scenario_results[0].turns[0].metrics.append(
        MetricResult(
            name="skip.example",
            category="source_selection",
            status="skipped",
            framework="deterministic",
        )
    )

    counters = report_counters(result)

    assert counters["hard_failures"] == 0
    assert counters["soft_trace_mismatches"] > 0
    assert counters["judge_failures"] == 1
    assert counters["skipped_metrics"] >= 1
    assert counters["not_applicable_metrics"] >= 1
