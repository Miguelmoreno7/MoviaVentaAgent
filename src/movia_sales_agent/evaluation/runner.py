from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.config.knowledge import load_policies_seed, load_products_seed
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.evaluation.capabilities import source_capabilities
from movia_sales_agent.evaluation.dataset import (
    DEFAULT_DATASET_PATH,
    load_validation_dataset,
    validate_dataset,
)
from movia_sales_agent.evaluation.frameworks import DeepEvalEvaluator, RagasEvaluator
from movia_sales_agent.evaluation.models import (
    EvaluationRunResult,
    HardFailure,
    ScenarioEvaluationResult,
    TurnEvaluationResult,
    ValidationDataset,
    ValidationScenario,
)
from movia_sales_agent.evaluation.response_quality import ResponseQualityEvaluator
from movia_sales_agent.evaluation.scoring import (
    aggregate_scenario,
    category_scores,
    passes_policy,
    scenario_business_terms,
    score_groups,
    score_turn,
    weighted_score,
)


class EvaluationRunner:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        dataset_path: Optional[Path] = None,
        agent_factory: Optional[Callable[[], MoviaSalesAgent]] = None,
        enable_ragas: bool = True,
        enable_deepeval: bool = True,
        enable_response_quality: bool = True,
        enable_response_quality_llm: bool = False,
    ):
        self.settings = settings or get_settings()
        self.dataset_path = dataset_path or DEFAULT_DATASET_PATH
        self.dataset = load_validation_dataset(self.dataset_path)
        self.dataset_summary = validate_dataset(self.dataset)
        if not self.dataset_summary.valid:
            raise ValueError("Invalid validation dataset: " + "; ".join(self.dataset_summary.errors))
        self.agent_factory = agent_factory or (lambda: MoviaSalesAgent(self.settings))
        self.source_capabilities = source_capabilities()
        self.business_terms = scenario_business_terms(self.dataset.scenarios)
        self.ragas = RagasEvaluator(self.settings, enabled=enable_ragas)
        self.deepeval = DeepEvalEvaluator(self.settings, enabled=enable_deepeval)
        self.response_quality = ResponseQualityEvaluator(
            self.settings,
            enabled=enable_response_quality,
            use_llm_judge=enable_response_quality_llm,
        )

    def run(
        self,
        scenario_id: str = "all",
        repeat: int = 1,
        max_turns: Optional[int] = None,
        offline: bool = False,
    ) -> EvaluationRunResult:
        started = now_iso()
        run_id = make_run_id()
        scenarios = select_scenarios(self.dataset, scenario_id)
        scenario_results = []
        all_metrics = []
        agent_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        notes = []
        if offline:
            notes.append("Offline run: framework metrics are skipped and results are non-comparable.")
        if not self.ragas.enabled:
            notes.append(f"RAGAS skipped: {self.ragas.error}")
        if not self.deepeval.enabled:
            notes.append(f"DeepEval skipped: {self.deepeval.error}")
        if not self.response_quality.enabled:
            notes.append(f"Response quality skipped: {self.response_quality.error}")
        elif self.response_quality.error:
            notes.append(f"Response quality LLM judge skipped: {self.response_quality.error}")

        for repeat_index in range(1, max(1, repeat) + 1):
            for scenario in scenarios:
                result = self._run_scenario(
                    run_id=run_id,
                    scenario=scenario,
                    repeat_index=repeat_index,
                    max_turns=max_turns,
                )
                scenario_results.append(result)
                all_metrics.extend(
                    metric for turn in result.turns for metric in turn.metrics
                )
                all_metrics.extend(result.conversation_metrics)
                for turn in result.turns:
                    add_token_usage(agent_tokens, turn.token_usage)

        run_category_scores = category_scores(all_metrics)
        run_score_groups = score_groups(run_category_scores, self.dataset.suite_type)
        overall_score = weighted_score(run_category_scores, self.dataset.suite_type)
        hard_failures = [
            failure for result in scenario_results for failure in result.hard_failures
        ]
        complete_run = max_turns is None
        passed = (
            complete_run
            and not offline
            and all(result.passed for result in scenario_results)
            and passes_policy(
                overall_score,
                run_category_scores,
                hard_failures,
                suite_type=self.dataset.suite_type,
            )
        )
        if not complete_run:
            notes.append("Partial run: pass/fail is intentionally false.")

        return EvaluationRunResult(
            evaluation_contract_version=self.dataset.evaluation_contract_version,
            commercial_contract_version=self.dataset.commercial_contract_version,
            agent_contract_version=self.dataset.agent_contract_version,
            suite_type=self.dataset.suite_type,
            causal_continuity=self.dataset.causal_continuity,
            dataset_version=self.dataset.dataset_version,
            run_mode=self.dataset.run_mode,
            run_id=run_id,
            started_at=started,
            completed_at=now_iso(),
            dataset_path=str(self.dataset_path),
            dataset_summary=self.dataset_summary,
            scenario_results=scenario_results,
            category_scores=run_category_scores,
            score_groups=run_score_groups,
            overall_score=overall_score,
            agent_token_usage=agent_tokens,
            hard_failures=hard_failures,
            passed=passed,
            offline=offline,
            notes=notes,
        )

    def _run_scenario(
        self,
        run_id: str,
        scenario: ValidationScenario,
        repeat_index: int,
        max_turns: Optional[int],
    ) -> ScenarioEvaluationResult:
        agent = self.agent_factory()
        lead_external_id = f"{run_id}:{scenario.conversation_id}:r{repeat_index}"
        ground_truth = load_current_ground_truth(agent)
        result = ScenarioEvaluationResult(
            run_id=run_id,
            conversation_id=scenario.conversation_id,
            persona=scenario.persona,
            difficulty=scenario.difficulty,
            success_goal=scenario.success_goal,
            lead_external_id=lead_external_id,
        )
        user_history: List[str] = []
        turns = scenario.turns[:max_turns] if max_turns else scenario.turns
        for validation_turn in turns:
            started = perf_counter()
            try:
                response = agent.invoke(
                    validation_turn.user,
                    lead_external_id=lead_external_id,
                    channel="evaluation",
                    external_message_id=(
                        f"eval:{run_id}:{scenario.conversation_id}:"
                        f"r{repeat_index}:t{validation_turn.turn_id}"
                    ),
                )
                latency_ms = round((perf_counter() - started) * 1000, 2)
                metrics, failures = score_turn(
                    validation_turn=validation_turn,
                    response=response,
                    source_capabilities=self.source_capabilities,
                    ground_truth=ground_truth,
                    scenario=scenario,
                    user_history=user_history,
                    scenario_business_terms=self.business_terms,
                )
                turn_result = TurnEvaluationResult(
                    run_id=run_id,
                    conversation_id=scenario.conversation_id,
                    turn_id=validation_turn.turn_id,
                    user_input=validation_turn.user,
                    ideal_response=validation_turn.ideal_assistant,
                    agent_output=response.response,
                    response_messages=response.response_messages,
                    analysis=response.analysis.model_dump(),
                    lead_state=response.lead_state,
                    selected_action=response.selected_action,
                    knowledge_plan=response.knowledge_plan,
                    retrieved_sources=response.retrieved_sources,
                    response_metadata=response.response_metadata,
                    token_usage=response.token_usage,
                    latency_ms=latency_ms,
                    metrics=metrics,
                    hard_failures=failures,
                )
                turn_result.metrics.extend(self.ragas.evaluate_turn(turn_result))
                turn_result.metrics.extend(
                    self.response_quality.evaluate_turn(
                        turn=turn_result,
                        scenario=scenario,
                        previous_turns=result.turns,
                        ground_truth=ground_truth,
                        suite_type=self.dataset.suite_type,
                    )
                )
            except Exception as exc:
                latency_ms = round((perf_counter() - started) * 1000, 2)
                failure = HardFailure(
                    code="agent_error",
                    category="commercial_accuracy",
                    reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                    turn_id=validation_turn.turn_id,
                )
                turn_result = TurnEvaluationResult(
                    run_id=run_id,
                    conversation_id=scenario.conversation_id,
                    turn_id=validation_turn.turn_id,
                    user_input=validation_turn.user,
                    ideal_response=validation_turn.ideal_assistant,
                    agent_output="",
                    latency_ms=latency_ms,
                    hard_failures=[failure],
                    error=failure.reason,
                )
            result.turns.append(turn_result)
            user_history.append(validation_turn.user)

        result.conversation_metrics = self.deepeval.evaluate_scenario(
            scenario, result, ground_truth
        )
        return aggregate_scenario(result, suite_type=self.dataset.suite_type)


def load_current_ground_truth(agent: MoviaSalesAgent) -> Dict[str, object]:
    try:
        products = agent.repository.fetch_products()
    except Exception:
        products = load_products_seed()
    try:
        policies = agent.repository.fetch_policies()
    except Exception:
        policies = load_policies_seed()
    try:
        official_links = agent.repository.fetch_official_links()
    except Exception:
        official_links = [
            {
                "slug": "movia_app",
                "url": "https://app.moviatech.com.mx",
                "status": "official",
            }
        ]
    return {
        "products": products,
        "policies": policies,
        "official_links": official_links,
    }


def select_scenarios(dataset: ValidationDataset, scenario_id: str) -> List[ValidationScenario]:
    if scenario_id == "all":
        return list(dataset.scenarios)
    selected = [
        scenario for scenario in dataset.scenarios if scenario.conversation_id == scenario_id
    ]
    if not selected:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    return selected


def add_token_usage(total: Dict[str, int], usage: Dict[str, object]) -> None:
    usage_total = usage.get("total") if isinstance(usage, dict) else None
    if not isinstance(usage_total, dict):
        return
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        total[key] += int(usage_total.get(key) or 0)


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"movia-eval-{stamp}-{uuid4().hex[:6]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
