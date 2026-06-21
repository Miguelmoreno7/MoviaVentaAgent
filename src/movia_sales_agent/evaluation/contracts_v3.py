from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, List, Optional


EVALUATION_CONTRACT_VERSION = "3.0"


class EvaluationEnum(str, Enum):
    @classmethod
    def values(cls) -> List[str]:
        return [item.value for item in cls]


class SuiteType(EvaluationEnum):
    ATOMIC_SCRIPTED = "atomic_scripted"
    COHERENT_SCRIPTED = "coherent_scripted"
    ADAPTIVE_HYBRID = "adaptive_hybrid"


class RunMode(EvaluationEnum):
    SCRIPTED_REPLAY = "scripted_replay"
    ADAPTIVE_HYBRID = "adaptive_hybrid"
    STRUCTURAL_VALIDATION = "structural_validation"


class MetricApplicability(EvaluationEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW_DIAGNOSTIC = "low_diagnostic"
    SAMPLED = "sampled"
    NOT_APPLICABLE = "not_applicable"


class ScoreGroup(EvaluationEnum):
    CAPABILITY = "capability"
    PROGRESSION = "progression"
    MEMORY = "memory"
    RETRIEVAL = "retrieval"
    RESPONSE_QUALITY = "response_quality"
    CRITICAL_RULES = "critical_rules"


METRIC_APPLICABILITY: Dict[str, Dict[str, str]] = {
    "commercial_accuracy": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "policy_compliance": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "scope_control": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "intent_action_routing": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.MEDIUM.value,
    },
    "source_selection": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.MEDIUM.value,
    },
    "memory_consistency": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.MEDIUM.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "sales_progression": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.LOW_DIAGNOSTIC.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "objection_resolution": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.LOW_DIAGNOSTIC.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "conversion_behavior": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.NOT_APPLICABLE.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.MEDIUM.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
    "response_quality": {
        SuiteType.ATOMIC_SCRIPTED.value: MetricApplicability.SAMPLED.value,
        SuiteType.COHERENT_SCRIPTED.value: MetricApplicability.HIGH.value,
        SuiteType.ADAPTIVE_HYBRID.value: MetricApplicability.HIGH.value,
    },
}


CATEGORY_TO_SCORE_GROUP: Dict[str, str] = {
    "commercial_accuracy": ScoreGroup.CAPABILITY.value,
    "policy_compliance": ScoreGroup.CAPABILITY.value,
    "scope_control": ScoreGroup.CAPABILITY.value,
    "sales_progression": ScoreGroup.PROGRESSION.value,
    "objection_handling": ScoreGroup.PROGRESSION.value,
    "memory_consistency": ScoreGroup.MEMORY.value,
    "source_selection": ScoreGroup.RETRIEVAL.value,
    "response_quality": ScoreGroup.RESPONSE_QUALITY.value,
}


CATEGORY_TO_APPLICABILITY_METRIC: Dict[str, str] = {
    "commercial_accuracy": "commercial_accuracy",
    "policy_compliance": "policy_compliance",
    "scope_control": "scope_control",
    "sales_progression": "sales_progression",
    "objection_handling": "objection_resolution",
    "memory_consistency": "memory_consistency",
    "source_selection": "source_selection",
    "response_quality": "response_quality",
}


PRIMARY_SCORE_GROUP_BY_SUITE: Dict[str, str] = {
    SuiteType.ATOMIC_SCRIPTED.value: ScoreGroup.CAPABILITY.value,
    SuiteType.COHERENT_SCRIPTED.value: ScoreGroup.PROGRESSION.value,
    SuiteType.ADAPTIVE_HYBRID.value: ScoreGroup.PROGRESSION.value,
}


AUTHORITATIVE_APPLICABILITY = {
    MetricApplicability.HIGH.value,
    MetricApplicability.MEDIUM.value,
    MetricApplicability.SAMPLED.value,
}


def metric_applicability(metric_name: str, suite_type: str) -> str:
    return METRIC_APPLICABILITY.get(metric_name, {}).get(
        suite_type,
        MetricApplicability.NOT_APPLICABLE.value,
    )


def category_applicability(category: str, suite_type: str) -> str:
    metric_name = CATEGORY_TO_APPLICABILITY_METRIC.get(category, category)
    return metric_applicability(metric_name, suite_type)


def category_is_authoritative(category: str, suite_type: str) -> bool:
    return category_applicability(category, suite_type) in AUTHORITATIVE_APPLICABILITY


def authoritative_categories(categories: Iterable[str], suite_type: str) -> List[str]:
    return [
        category
        for category in categories
        if category_is_authoritative(category, suite_type)
    ]


def suite_primary_score_group(suite_type: str) -> Optional[str]:
    return PRIMARY_SCORE_GROUP_BY_SUITE.get(suite_type)
