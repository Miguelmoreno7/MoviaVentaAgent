from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.evaluation.contracts_v3 import SuiteType
from movia_sales_agent.evaluation.frameworks import ground_truth_summary
from movia_sales_agent.evaluation.models import (
    MetricResult,
    TurnEvaluationResult,
    ValidationScenario,
)


RESPONSE_QUALITY_DIMENSIONS = [
    "directness",
    "relevance",
    "factuality",
    "personalization",
    "persuasiveness",
    "naturalness",
    "non_repetition",
    "next_step_quality",
    "conciseness",
    "tone",
]

CRITICAL_RESPONSE_DEFECTS = [
    "did_not_answer_question",
    "asked_known_information",
    "unsupported_claim",
    "overpromised_scope",
    "premature_close",
    "irrelevant_context",
    "repetitive_question",
    "unnatural_or_defensive_tone",
    "poor_next_step",
]

RESPONSE_QUALITY_THRESHOLD = 0.75


class ResponseQualityDimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    evidence: str = Field(min_length=1, max_length=240)


class ResponseQualityJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension_scores: Dict[str, ResponseQualityDimensionScore]
    critical_defects: List[str] = Field(default_factory=list)
    overall_response_quality: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=320)

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimensions(
        cls, value: Dict[str, ResponseQualityDimensionScore]
    ) -> Dict[str, ResponseQualityDimensionScore]:
        expected = set(RESPONSE_QUALITY_DIMENSIONS)
        actual = set(value)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"Invalid response-quality dimensions. missing={missing} extra={extra}")
        return value

    @field_validator("critical_defects")
    @classmethod
    def validate_defects(cls, value: List[str]) -> List[str]:
        invalid = sorted(set(value) - set(CRITICAL_RESPONSE_DEFECTS))
        if invalid:
            raise ValueError(f"Invalid response-quality defects: {invalid}")
        return sorted(set(value), key=CRITICAL_RESPONSE_DEFECTS.index)


class ResponseQualityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: str
    recent_context: List[Dict[str, str]] = Field(default_factory=list)
    known_lead_facts: Dict[str, Any] = Field(default_factory=dict)
    official_facts_used: Dict[str, Any] = Field(default_factory=dict)
    selected_commercial_action: Dict[str, Any] = Field(default_factory=dict)
    response: str
    rubric: Dict[str, str]


class ResponseQualityEvaluator:
    def __init__(
        self,
        settings: Settings,
        *,
        enabled: bool = True,
        use_llm_judge: bool = False,
    ):
        self.settings = settings
        self.enabled = enabled
        self.use_llm_judge = bool(
            use_llm_judge and settings.openai_api_key and not settings.disable_openai
        )
        self.client: Optional[OpenAI] = None
        self.error: Optional[str] = None
        if not enabled:
            self.error = "Disabled by run configuration."
        elif use_llm_judge and not self.use_llm_judge:
            self.error = "LLM response-quality judge requires OpenAI credentials."
        elif self.use_llm_judge:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def evaluate_turn(
        self,
        *,
        turn: TurnEvaluationResult,
        scenario: ValidationScenario,
        previous_turns: Sequence[TurnEvaluationResult],
        ground_truth: Dict[str, Any],
        suite_type: str,
    ) -> List[MetricResult]:
        if not should_evaluate_response_quality(suite_type, scenario.conversation_id, turn.turn_id):
            return [
                MetricResult(
                    name="response_quality.overall",
                    category="response_quality",
                    status="skipped",
                    reason="This turn is outside the response-quality sampling policy.",
                    framework="response_quality",
                )
            ]
        if not self.enabled:
            return [
                MetricResult(
                    name="response_quality.overall",
                    category="response_quality",
                    status="skipped",
                    reason=self.error,
                    framework="response_quality",
                )
            ]

        quality_input = build_quality_input(turn, previous_turns, ground_truth)
        try:
            judgment = (
                self._judge_with_llm(quality_input, scenario)
                if self.use_llm_judge
                else judge_deterministically(quality_input, turn)
            )
        except Exception as exc:
            return [
                MetricResult(
                    name="response_quality.overall",
                    category="response_quality",
                    status="error",
                    reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                    framework="response_quality",
                )
            ]
        return metrics_from_judgment(judgment)

    def _judge_with_llm(
        self,
        quality_input: ResponseQualityInput,
        scenario: ValidationScenario,
    ) -> ResponseQualityJudgment:
        if not self.client:
            raise RuntimeError("OpenAI client is not configured.")
        prompt = (
            "Evaluate the visible WhatsApp response from a MovIA pre-sales agent. "
            "Use only the supplied rubric and facts. Return structured JSON only. "
            "Do not include hidden reasoning; evidence must be short and observable. "
            f"Scenario goal: {scenario.success_goal}"
        )
        response = self.client.responses.create(
            model=self.settings.eval_model,
            input=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": quality_input.model_dump_json(),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "movia_response_quality_judgment",
                    "schema": response_quality_json_schema(),
                    "strict": True,
                }
            },
        )
        return ResponseQualityJudgment.model_validate_json(response.output_text)


def should_evaluate_response_quality(suite_type: str, conversation_id: str, turn_id: int) -> bool:
    if suite_type in {SuiteType.COHERENT_SCRIPTED.value, SuiteType.ADAPTIVE_HYBRID.value}:
        return True
    if conversation_id.startswith("MOVIA-MEM-") or conversation_id.startswith("MOVIA-RAG-"):
        return True
    if suite_type == SuiteType.ATOMIC_SCRIPTED.value:
        return turn_id in {1, 6, 12}
    return False


def build_quality_input(
    turn: TurnEvaluationResult,
    previous_turns: Sequence[TurnEvaluationResult],
    ground_truth: Dict[str, Any],
) -> ResponseQualityInput:
    recent_context = []
    for previous in previous_turns[-3:]:
        recent_context.append({"role": "user", "content": previous.user_input})
        recent_context.append({"role": "assistant", "content": previous.agent_output[:700]})
    return ResponseQualityInput(
        user_message=turn.user_input,
        recent_context=recent_context,
        known_lead_facts=_known_lead_facts(turn.lead_state),
        official_facts_used={
            "structured_sources": turn.knowledge_plan.get("structured_sources") or [],
            "json_sources": turn.knowledge_plan.get("json_sources") or [],
            "retrieved_sources": [
                {
                    "title": source.get("title"),
                    "source_path": source.get("source_path"),
                    "metadata": source.get("metadata") or {},
                }
                for source in turn.retrieved_sources
            ],
            "ground_truth_summary": ground_truth_summary(ground_truth),
        },
        selected_commercial_action=turn.selected_action,
        response=turn.agent_output,
        rubric=response_quality_rubric(),
    )


def response_quality_rubric() -> Dict[str, str]:
    return {
        "directness": "Answers the user's actual question before adding context.",
        "relevance": "Avoids unrelated explanations and keeps to the current sales need.",
        "factuality": "Uses only official facts for prices, policies, links, channels and scope.",
        "personalization": "Uses known lead context when it would improve the answer.",
        "persuasiveness": "Explains commercial value without pressure or invention.",
        "naturalness": "Sounds appropriate for a WhatsApp sales chat.",
        "non_repetition": "Avoids repeating questions or asking for known information.",
        "next_step_quality": "Ends with the best single question or CTA for the selected action.",
        "conciseness": "Is complete enough without becoming unnecessarily long.",
        "tone": "Stays calm, consultative and non-defensive.",
    }


def judge_deterministically(
    quality_input: ResponseQualityInput,
    turn: TurnEvaluationResult,
) -> ResponseQualityJudgment:
    response = quality_input.response or ""
    text = normalize_text(response)
    user_text = normalize_text(quality_input.user_message)
    defects = deterministic_defects(quality_input, turn)

    scores = {
        "directness": _score_directness(user_text, text, defects),
        "relevance": _score_relevance(user_text, text, defects),
        "factuality": 2 if any(item in defects for item in ["unsupported_claim", "overpromised_scope"]) else 5,
        "personalization": _score_personalization(quality_input, text),
        "persuasiveness": _score_persuasiveness(text, defects),
        "naturalness": _score_naturalness(response, text, defects),
        "non_repetition": 1 if any(item in defects for item in ["asked_known_information", "repetitive_question"]) else 5,
        "next_step_quality": 2 if "poor_next_step" in defects else 5,
        "conciseness": _score_conciseness(response),
        "tone": 2 if "unnatural_or_defensive_tone" in defects else 5,
    }
    dimension_scores = {
        dimension: ResponseQualityDimensionScore(
            score=score,
            evidence=_evidence_for_dimension(dimension, score, defects),
        )
        for dimension, score in scores.items()
    }
    overall = round(sum(scores.values()) / (len(scores) * 5), 4)
    if defects:
        overall = min(overall, 0.72 if len(defects) == 1 else 0.60)
    return ResponseQualityJudgment(
        dimension_scores=dimension_scores,
        critical_defects=defects,
        overall_response_quality=overall,
        summary="Deterministic response-quality evaluation from visible answer, action and lead state.",
    )


def deterministic_defects(
    quality_input: ResponseQualityInput,
    turn: TurnEvaluationResult,
) -> List[str]:
    response = quality_input.response or ""
    text = normalize_text(response)
    user_text = normalize_text(quality_input.user_message)
    defects: List[str] = []

    if not response.strip() or _score_directness(user_text, text, []) <= 2:
        defects.append("did_not_answer_question")
    if _asks_known_information(text, quality_input.known_lead_facts):
        defects.append("asked_known_information")
    if _has_unsupported_claim(text):
        defects.append("unsupported_claim")
    if _overpromises_scope(text):
        defects.append("overpromised_scope")
    if (
        turn.selected_action.get("macro_action") == "direct_close"
        and not bool((turn.analysis or {}).get("explicit_start_intent"))
    ):
        defects.append("premature_close")
    if _irrelevant_context(user_text, text, turn):
        defects.append("irrelevant_context")
    if _repeats_question(response):
        defects.append("repetitive_question")
    if _bad_tone(text):
        defects.append("unnatural_or_defensive_tone")
    if _poor_next_step(response, turn):
        defects.append("poor_next_step")
    return [defect for defect in CRITICAL_RESPONSE_DEFECTS if defect in defects]


def metrics_from_judgment(judgment: ResponseQualityJudgment) -> List[MetricResult]:
    metrics = [
        MetricResult(
            name="response_quality.overall",
            category="response_quality",
            status="passed"
            if judgment.overall_response_quality >= RESPONSE_QUALITY_THRESHOLD
            else "failed",
            score=judgment.overall_response_quality,
            threshold=RESPONSE_QUALITY_THRESHOLD,
            actual=judgment.model_dump(),
            reason=judgment.summary,
            framework="response_quality",
        )
    ]
    for dimension, score in judgment.dimension_scores.items():
        normalized = round(score.score / 5, 4)
        metrics.append(
            MetricResult(
                name=f"response_quality.{dimension}",
                category="response_quality",
                status="passed" if score.score >= 3 else "failed",
                score=normalized,
                threshold=0.60,
                actual=score.model_dump(),
                reason=score.evidence,
                framework="response_quality",
            )
        )
    metrics.append(
        MetricResult(
            name="response_quality.critical_defects",
            category="response_quality",
            status="passed" if not judgment.critical_defects else "failed",
            score=1.0 if not judgment.critical_defects else 0.0,
            threshold=1.0,
            expected=[],
            actual=judgment.critical_defects,
            reason="Critical response defects are tracked separately from trace agreement.",
            framework="response_quality",
        )
    )
    return metrics


def _known_lead_facts(lead_state: Dict[str, Any]) -> Dict[str, Any]:
    profile_data = dict(lead_state.get("profile_data") or {})
    return {
        key: value
        for key, value in {
            "business_type": lead_state.get("business_type"),
            "main_channel": lead_state.get("main_channel"),
            "pain_or_goal": lead_state.get("pain"),
            "action_requirement": profile_data.get("action_requirement"),
            "known_product_fit": profile_data.get("known_product_fit"),
        }.items()
        if value not in (None, "", [], {}, "unknown")
    }


def _score_directness(user_text: str, response_text: str, defects: Sequence[str]) -> int:
    if "did_not_answer_question" in defects or not response_text:
        return 1
    question_terms = {
        "price": ["cuanto", "cuesta", "precio", "barato"],
        "link": ["link", "empezar", "iniciar", "contratar"],
        "refund": ["reembolso"],
        "platform": ["pagina", "registro", "app", "llenar"],
        "comparison": ["manychat", "chatbot", "recepcionista"],
    }
    expected_terms = {
        "price": ["$", "cuesta", "captura", "hibrido"],
        "link": ["app.moviatech", "link", "iniciar", "deposito"],
        "refund": ["no hay reembolso", "no se reembolsa", "deposito"],
        "platform": ["app", "registro", "informacion", "deposito"],
        "comparison": ["manychat", "diferencia", "movia"],
    }
    for key, triggers in question_terms.items():
        if any(term in user_text for term in triggers):
            return 5 if any(term in response_text for term in expected_terms[key]) else 2
    return 4


def _score_relevance(user_text: str, response_text: str, defects: Sequence[str]) -> int:
    if "irrelevant_context" in defects:
        return 2
    if len(response_text) > 1800:
        return 3
    if user_text and any(term in response_text for term in _content_terms(user_text)):
        return 5
    return 4


def _score_personalization(quality_input: ResponseQualityInput, response_text: str) -> int:
    facts = quality_input.known_lead_facts
    if not facts:
        return 5
    useful_terms = [
        normalize_text(str(value))
        for key, value in facts.items()
        if key in {"business_type", "pain_or_goal", "known_product_fit"}
    ]
    if any(term and term in response_text for term in useful_terms):
        return 5
    if any(term in normalize_text(quality_input.user_message) for term in ["conviene", "recomi", "plan"]):
        return 3
    return 4


def _score_persuasiveness(response_text: str, defects: Sequence[str]) -> int:
    if "unsupported_claim" in defects or "overpromised_scope" in defects:
        return 2
    value_terms = ["ahorrar", "rapido", "rápido", "orden", "leads", "valor", "seguimiento", "responder"]
    return 5 if any(normalize_text(term) in response_text for term in value_terms) else 3


def _score_naturalness(response: str, response_text: str, defects: Sequence[str]) -> int:
    if "unnatural_or_defensive_tone" in defects:
        return 2
    if len(response) > 1200:
        return 3
    if response.count("\n") >= 1 or len(response) <= 700:
        return 5
    return 4


def _score_conciseness(response: str) -> int:
    length = len(response or "")
    if length == 0:
        return 1
    if length <= 900:
        return 5
    if length <= 1300:
        return 3
    return 2


def _evidence_for_dimension(dimension: str, score: int, defects: Sequence[str]) -> str:
    if score >= 4:
        return f"{dimension} is acceptable based on visible response and selected action."
    if defects:
        return f"{dimension} is reduced because of defects: {', '.join(defects)}."
    return f"{dimension} is weak according to deterministic response-quality checks."


def _asks_known_information(response_text: str, facts: Dict[str, Any]) -> bool:
    patterns = {
        "business_type": ["que tipo de negocio", "tipo de negocio tienes"],
        "main_channel": ["por donde te escriben", "canal principal"],
        "pain_or_goal": ["que quieres mejorar", "que parte de tu atencion"],
        "action_requirement": ["solo debe responder", "tambien hacer acciones", "agendar, cotizar o registrar"],
    }
    return any(
        key in facts and any(pattern in response_text for pattern in key_patterns)
        for key, key_patterns in patterns.items()
    )


def _has_unsupported_claim(response_text: str) -> bool:
    unsupported_patterns = [
        "si hay reembolso",
        "te devolvemos el deposito",
        "instagram ya funciona",
        "facebook ya funciona",
        "instagram esta disponible",
        "facebook esta disponible",
    ]
    return any(pattern in response_text for pattern in unsupported_patterns)


def _overpromises_scope(response_text: str) -> bool:
    return "captura" in response_text and any(
        pattern in response_text
        for pattern in [
            "captura puede agendar",
            "captura agenda",
            "captura puede cotizar",
            "captura registra tickets",
            "captura ejecuta acciones",
        ]
    )


def _irrelevant_context(user_text: str, response_text: str, turn: TurnEvaluationResult) -> bool:
    if any(term in user_text for term in ["facebook", "instagram"]):
        return False
    topics = set((turn.analysis or {}).get("topics") or [])
    if topics & {"facebook", "instagram", "channel_question", "integration"}:
        return False
    return any(term in response_text for term in ["facebook", "instagram"]) and "no disponible" not in response_text


def _repeats_question(response: str) -> bool:
    questions = re.findall(r"[^?]+\?", response or "")
    normalized = [normalize_text(question).strip() for question in questions]
    return len(normalized) != len(set(normalized))


def _bad_tone(response_text: str) -> bool:
    return any(
        phrase in response_text
        for phrase in [
            "obviamente",
            "como ya te dije",
            "si no quieres",
            "no entiendes",
            "te conviene si o si",
        ]
    )


def _poor_next_step(response: str, turn: TurnEvaluationResult) -> bool:
    cta_type = str(turn.selected_action.get("cta_type") or "")
    if cta_type in {"soft_question", "discovery_question", "objection_question"} and "?" not in response:
        return True
    if cta_type in {"direct_close", "send_app_link"}:
        return "app.moviatech" not in normalize_text(response)
    return False


def _content_terms(value: str) -> List[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9]+", normalize_text(value))
        if len(term) >= 5
    ]


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def response_quality_json_schema() -> Dict[str, Any]:
    dimension_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5},
            "evidence": {"type": "string", "minLength": 1, "maxLength": 240},
        },
        "required": ["score", "evidence"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dimension_scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    dimension: dimension_schema for dimension in RESPONSE_QUALITY_DIMENSIONS
                },
                "required": RESPONSE_QUALITY_DIMENSIONS,
            },
            "critical_defects": {
                "type": "array",
                "items": {"type": "string", "enum": CRITICAL_RESPONSE_DEFECTS},
            },
            "overall_response_quality": {"type": "number", "minimum": 0, "maximum": 1},
            "summary": {"type": "string", "minLength": 1, "maxLength": 320},
        },
        "required": [
            "dimension_scores",
            "critical_defects",
            "overall_response_quality",
            "summary",
        ],
    }
