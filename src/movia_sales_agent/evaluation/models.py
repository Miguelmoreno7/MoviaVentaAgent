from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from movia_sales_agent.contracts.commercial import COMMERCIAL_CONTRACT_VERSION
from movia_sales_agent.evaluation.contracts_v3 import EVALUATION_CONTRACT_VERSION


MetricStatus = Literal["passed", "failed", "skipped", "not_applicable", "error"]


class ValidationTurn(BaseModel):
    turn_id: int
    user: str
    ideal_assistant: str
    expected: Dict[str, Any] = Field(default_factory=dict)


class ValidationScenario(BaseModel):
    conversation_id: str
    persona: str
    difficulty: str
    success_goal: str
    primary_risks: List[str] = Field(default_factory=list)
    lead_profile_seed: Dict[str, Any] = Field(default_factory=dict)
    turns: List[ValidationTurn] = Field(default_factory=list)


class ValidationDataset(BaseModel):
    evaluation_contract_version: str
    suite_type: str
    causal_continuity: bool
    agent_contract_version: str
    dataset_version: str
    run_mode: str
    commercial_contract_version: str
    agent_name: str
    channel: str
    date_created: str
    debug_fields_required: List[str] = Field(default_factory=list)
    global_pass_criteria: List[str] = Field(default_factory=list)
    movia_ground_truth: Dict[str, Any] = Field(default_factory=dict)
    scenarios: List[ValidationScenario] = Field(default_factory=list)


class DatasetValidationSummary(BaseModel):
    valid: bool
    evaluation_contract_version: str
    commercial_contract_version: str
    agent_contract_version: str
    suite_type: str
    causal_continuity: bool
    dataset_version: str
    run_mode: str
    scenario_count: int
    turn_count: int
    scenario_ids: List[str]
    unsupported_expected_fields: List[str] = Field(default_factory=list)
    unsupported_expected_sources: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class MetricResult(BaseModel):
    name: str
    category: str
    status: MetricStatus
    score: Optional[float] = None
    threshold: Optional[float] = None
    expected: Any = None
    actual: Any = None
    reason: Optional[str] = None
    framework: str = "deterministic"


class HardFailure(BaseModel):
    code: str
    category: str
    reason: str
    turn_id: Optional[int] = None


class TurnEvaluationResult(BaseModel):
    commercial_contract_version: str = COMMERCIAL_CONTRACT_VERSION
    run_id: str
    conversation_id: str
    turn_id: int
    user_input: str
    ideal_response: str
    agent_output: str
    response_messages: List[str] = Field(default_factory=list)
    analysis: Dict[str, Any] = Field(default_factory=dict)
    lead_state: Dict[str, Any] = Field(default_factory=dict)
    selected_action: Dict[str, Any] = Field(default_factory=dict)
    knowledge_plan: Dict[str, Any] = Field(default_factory=dict)
    retrieved_sources: List[Dict[str, Any]] = Field(default_factory=list)
    response_metadata: Dict[str, Any] = Field(default_factory=dict)
    token_usage: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0
    metrics: List[MetricResult] = Field(default_factory=list)
    hard_failures: List[HardFailure] = Field(default_factory=list)
    error: Optional[str] = None


class ScenarioEvaluationResult(BaseModel):
    run_id: str
    conversation_id: str
    persona: str
    difficulty: str
    success_goal: str
    lead_external_id: str
    turns: List[TurnEvaluationResult] = Field(default_factory=list)
    conversation_metrics: List[MetricResult] = Field(default_factory=list)
    hard_failures: List[HardFailure] = Field(default_factory=list)
    category_scores: Dict[str, float] = Field(default_factory=dict)
    score_groups: Dict[str, Optional[float]] = Field(default_factory=dict)
    overall_score: Optional[float] = None
    passed: bool = False


class EvaluationRunResult(BaseModel):
    evaluation_contract_version: str = EVALUATION_CONTRACT_VERSION
    commercial_contract_version: str = COMMERCIAL_CONTRACT_VERSION
    agent_contract_version: str = COMMERCIAL_CONTRACT_VERSION
    suite_type: str
    causal_continuity: bool
    dataset_version: str
    run_mode: str
    run_id: str
    started_at: str
    completed_at: str
    dataset_path: str
    dataset_summary: DatasetValidationSummary
    scenario_results: List[ScenarioEvaluationResult] = Field(default_factory=list)
    category_scores: Dict[str, float] = Field(default_factory=dict)
    score_groups: Dict[str, Optional[float]] = Field(default_factory=dict)
    overall_score: Optional[float] = None
    agent_token_usage: Dict[str, int] = Field(default_factory=dict)
    hard_failures: List[HardFailure] = Field(default_factory=list)
    passed: bool = False
    offline: bool = False
    notes: List[str] = Field(default_factory=list)


class AdaptiveHybridLeadSpec(BaseModel):
    persona_id: str
    persona: str
    objective: str
    constraints: List[str] = Field(default_factory=list)


class AdaptiveHybridInterface(BaseModel):
    evaluation_contract_version: str
    suite_type: str
    predeploy_only: bool = True
    enabled: bool = False
    run_mode: str
    activation_gate: str
    fixed_regression_suite: str
    lead_specs: List[AdaptiveHybridLeadSpec] = Field(default_factory=list)
