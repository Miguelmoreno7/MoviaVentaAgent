from __future__ import annotations

from typing import Any, Dict, List, Optional

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.evaluation.models import (
    MetricResult,
    ScenarioEvaluationResult,
    TurnEvaluationResult,
    ValidationScenario,
)
from movia_sales_agent.evaluation.scoring import CATEGORY_THRESHOLDS


class RagasEvaluator:
    def __init__(self, settings: Settings, enabled: bool = True):
        self.settings = settings
        self.enabled = False
        self.metrics: List[Any] = []
        self.error: Optional[str] = None
        if not enabled:
            self.error = "Disabled by run configuration."
            return
        if not settings.openai_api_key or settings.disable_openai:
            self.error = "RAGAS requires OpenAI credentials and an enabled OpenAI client."
            return
        self.enabled = True
        try:
            from openai import AsyncOpenAI
            from ragas.embeddings import OpenAIEmbeddings
            from ragas.llms import llm_factory
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextPrecisionWithReference,
                ContextRecall,
                ContextRelevance,
                Faithfulness,
            )

            client = AsyncOpenAI(api_key=settings.openai_api_key)
            llm = llm_factory(settings.eval_model, client=client)
            embeddings = OpenAIEmbeddings(client, model=settings.openai_embedding_model)
            self.metrics = [
                Faithfulness(llm),
                AnswerRelevancy(llm, embeddings),
                ContextRelevance(llm),
                ContextPrecisionWithReference(llm),
                ContextRecall(llm),
            ]
        except Exception as exc:
            self.enabled = False
            self.error = f"{type(exc).__name__}: {str(exc)[:300]}"

    def evaluate_turn(self, turn: TurnEvaluationResult) -> List[MetricResult]:
        if not turn.retrieved_sources:
            return [
                MetricResult(
                    name="ragas.rag_quality",
                    category="source_selection",
                    status="skipped",
                    reason="The agent did not retrieve RAG context for this turn.",
                    framework="ragas",
                )
            ]
        if not self.enabled:
            return [
                MetricResult(
                    name="ragas.rag_quality",
                    category="source_selection",
                    status="skipped",
                    reason=self.error,
                    framework="ragas",
                )
            ]

        retrieved_contexts = [
            str(source.get("preview") or "")
            for source in turn.retrieved_sources
            if source.get("preview")
        ]
        results = []
        for metric in self.metrics:
            name = str(getattr(metric, "name", metric.__class__.__name__))
            kwargs: Dict[str, Any] = {
                "user_input": turn.user_input,
                "response": turn.agent_output,
                "retrieved_contexts": retrieved_contexts,
                "reference": turn.ideal_response,
            }
            try:
                signature = metric.ascore.__signature__ if hasattr(metric.ascore, "__signature__") else None
                if signature is None:
                    import inspect

                    signature = inspect.signature(metric.ascore)
                accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
                value = metric.score(**accepted)
                score = _numeric_score(getattr(value, "value", value))
                reason = getattr(value, "reason", None)
                results.append(
                    MetricResult(
                        name=f"ragas.{name}",
                        category="source_selection",
                        status="passed" if score >= 0.70 else "failed",
                        score=score,
                        threshold=0.70,
                        reason=reason,
                        framework="ragas",
                    )
                )
            except Exception as exc:
                results.append(
                    MetricResult(
                        name=f"ragas.{name}",
                        category="source_selection",
                        status="error",
                        reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                        framework="ragas",
                    )
                )
        return results


class DeepEvalEvaluator:
    def __init__(self, settings: Settings, enabled: bool = True):
        self.settings = settings
        self.enabled = False
        self.error: Optional[str] = None
        if not enabled:
            self.error = "Disabled by run configuration."
            return
        if not settings.openai_api_key or settings.disable_openai:
            self.error = "DeepEval requires OpenAI credentials and an enabled OpenAI client."
            return
        self.enabled = True
        try:
            import deepeval  # noqa: F401
        except Exception as exc:
            self.enabled = False
            self.error = f"{type(exc).__name__}: {str(exc)[:300]}"

    def evaluate_scenario(
        self,
        scenario: ValidationScenario,
        result: ScenarioEvaluationResult,
        ground_truth: Dict[str, Any],
    ) -> List[MetricResult]:
        if not self.enabled:
            return [
                MetricResult(
                    name="deepeval.conversation_quality",
                    category="sales_progression",
                    status="skipped",
                    reason=self.error,
                    framework="deepeval",
                )
            ]
        try:
            from deepeval.metrics import (
                ConversationCompletenessMetric,
                KnowledgeRetentionMetric,
                RoleAdherenceMetric,
                TopicAdherenceMetric,
                TurnRelevancyMetric,
            )
            from deepeval.test_case import ConversationalTestCase, Turn

            turns = []
            for turn in result.turns:
                turns.append(Turn(role="user", content=turn.user_input))
                retrieval_context = [
                    str(source.get("preview") or "")
                    for source in turn.retrieved_sources
                    if source.get("preview")
                ]
                turns.append(
                    Turn(
                        role="assistant",
                        content=turn.agent_output,
                        retrieval_context=retrieval_context or None,
                    )
                )
            test_case = ConversationalTestCase(
                name=scenario.conversation_id,
                turns=turns,
                scenario=scenario.persona,
                expected_outcome=scenario.success_goal,
                chatbot_role="MovIA pre-sales agent for WhatsApp",
                context=[ground_truth_summary(ground_truth)],
            )
            model = self.settings.eval_model
            specs = [
                (
                    ConversationCompletenessMetric(
                        threshold=0.70, model=model, async_mode=False
                    ),
                    "sales_progression",
                    "conversation_completeness",
                ),
                (
                    TurnRelevancyMetric(threshold=0.70, model=model, async_mode=False),
                    "sales_progression",
                    "turn_relevancy",
                ),
                (
                    KnowledgeRetentionMetric(threshold=0.80, model=model, async_mode=False),
                    "memory_consistency",
                    "knowledge_retention",
                ),
                (
                    RoleAdherenceMetric(threshold=0.80, model=model, async_mode=False),
                    "scope_control",
                    "role_adherence",
                ),
                (
                    TopicAdherenceMetric(
                        relevant_topics=[
                            "MovIA products",
                            "pre-sales discovery",
                            "pricing and policies",
                            "WhatsApp automation",
                            "product scope and onboarding",
                        ],
                        threshold=0.80,
                        model=model,
                        async_mode=False,
                    ),
                    "scope_control",
                    "topic_adherence",
                ),
            ]
            specs.extend(_custom_deepeval_specs(model, scenario, ground_truth))
            return [_measure_deepeval(metric, category, name, test_case) for metric, category, name in specs]
        except Exception as exc:
            return [
                MetricResult(
                    name="deepeval.conversation_quality",
                    category="sales_progression",
                    status="error",
                    reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                    framework="deepeval",
                )
            ]


def _custom_deepeval_specs(
    model: str,
    scenario: ValidationScenario,
    ground_truth: Dict[str, Any],
) -> List[Any]:
    from deepeval.metrics import ConversationalGEval

    facts = ground_truth_summary(ground_truth)
    criteria = {
        "commercial_accuracy": (
            "Judge the commercial claims the assistant actually makes. They must remain accurate "
            "and avoid unsupported claims. Do not penalize the assistant for facts that were not "
            f"relevant to the user's questions. Official facts: {facts}"
        ),
        "policy_compliance": (
            "Judge payment, refund, monthly billing, support, and post-purchase statements only "
            "when those topics occur. Do not require unrelated policy explanations. Any policy "
            f"statement that is made must comply with these official facts: {facts}"
        ),
        "sales_progression": (
            "Judge whether each answer addresses the explicit question and advances one useful "
            "commercial micro-step appropriate to the conversation so far. Do not require every "
            f"goal element in every turn. Scenario goal: {scenario.success_goal}"
        ),
        "scope_control": (
            "Judge product and channel scope claims when they occur. The assistant must avoid "
            "overpromising and stay within the official facts, but should not be penalized for "
            f"omitting unrelated scope details. Official facts: {facts}"
        ),
        "objection_handling": (
            "Judge whether the assistant handles objections calmly, acknowledges the concern, "
            "asks useful open questions, and avoids defensive or high-pressure persuasion."
        ),
    }
    specs = []
    for category, criterion in criteria.items():
        threshold = CATEGORY_THRESHOLDS[category]
        specs.append(
            (
                ConversationalGEval(
                    name=category,
                    criteria=criterion,
                    threshold=threshold,
                    model=model,
                    async_mode=False,
                ),
                category,
                category,
            )
        )
    return specs


def _measure_deepeval(metric: Any, category: str, name: str, test_case: Any) -> MetricResult:
    try:
        metric.measure(test_case)
        score = _numeric_score(metric.score)
        threshold = float(getattr(metric, "threshold", CATEGORY_THRESHOLDS.get(category, 0.70)))
        return MetricResult(
            name=f"deepeval.{name}",
            category=category,
            status="passed" if score >= threshold else "failed",
            score=score,
            threshold=threshold,
            reason=getattr(metric, "reason", None),
            framework="deepeval",
        )
    except Exception as exc:
        return MetricResult(
            name=f"deepeval.{name}",
            category=category,
            status="error",
            reason=f"{type(exc).__name__}: {str(exc)[:300]}",
            framework="deepeval",
        )


def ground_truth_summary(ground_truth: Dict[str, Any]) -> str:
    products = []
    for product in ground_truth.get("products") or []:
        products.append(
            f"{product.get('name')}: status={product.get('status')}, "
            f"setup={product.get('setup_price_mxn')} MXN, "
            f"monthly={product.get('monthly_price_mxn')} MXN"
        )
    policies = []
    for slug, policy in (ground_truth.get("policies") or {}).items():
        policies.append(f"{slug}: {policy.get('content') or policy.get('description') or policy}")
    links = [str(item.get("url")) for item in ground_truth.get("official_links") or []]
    return (
        "Products: "
        + "; ".join(products)
        + ". Policies: "
        + "; ".join(policies)
        + ". Available channel: WhatsApp Business. Facebook and Instagram are not currently "
        + "available. Official links: "
        + ", ".join(links)
        + "."
    )


def _numeric_score(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return max(0.0, min(1.0, float(value)))
