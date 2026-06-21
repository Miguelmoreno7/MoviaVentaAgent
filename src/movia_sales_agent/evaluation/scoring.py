from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from movia_sales_agent.agent.rag_policy import (
    MIN_RAG_SIMILARITY,
    comparison_target_from_text,
    industry_from_analysis,
)
from movia_sales_agent.contracts.commercial import MacroAction, ObjectionFlowStep, ProductFit, Topic
from movia_sales_agent.evaluation.capabilities import emitted_source_labels
from movia_sales_agent.evaluation.contracts_v3 import (
    CATEGORY_TO_SCORE_GROUP,
    ScoreGroup,
    SuiteType,
    authoritative_categories,
    category_is_authoritative,
    suite_primary_score_group,
)
from movia_sales_agent.evaluation.models import (
    HardFailure,
    MetricResult,
    ScenarioEvaluationResult,
    ValidationScenario,
    ValidationTurn,
)
from movia_sales_agent.models.schemas import ChatResponse


CATEGORY_WEIGHTS: Dict[str, float] = {
    "commercial_accuracy": 0.20,
    "policy_compliance": 0.20,
    "sales_progression": 0.15,
    "memory_consistency": 0.15,
    "scope_control": 0.10,
    "objection_handling": 0.10,
    "source_selection": 0.10,
    "response_quality": 0.15,
}

CATEGORY_THRESHOLDS: Dict[str, float] = {
    "commercial_accuracy": 0.85,
    "policy_compliance": 0.85,
    "memory_consistency": 0.80,
    "scope_control": 0.80,
    "sales_progression": 0.70,
    "objection_handling": 0.70,
    "source_selection": 0.70,
    "response_quality": 0.75,
}

EXPECTED_FIELD_MAP: Dict[str, Tuple[str, str]] = {
    "current_stage": ("sales_progression", "current_stage"),
    "macro_action": ("sales_progression", "macro_action"),
    "micro_action": ("sales_progression", "micro_action"),
    "final_cta_type": ("sales_progression", "final_cta_type"),
    "objection_type": ("objection_handling", "objection_type"),
    "objection_flow_step": ("objection_handling", "objection_flow_step"),
    "rag_used": ("source_selection", "rag_used"),
    "structured_used": ("source_selection", "structured_used"),
    "json_used": ("source_selection", "json_used"),
}

POLICY_TERMS = {
    "deposito",
    "pago",
    "reembolso",
    "mensualidad",
    "tokens",
    "soporte",
    "ajustes",
    "pague",
    "pagado",
}
SCOPE_TERMS = {
    "captura",
    "hibrido",
    "agendar",
    "agenda",
    "registrar",
    "cotizar",
    "ticket",
    "panel",
    "acciones",
    "facebook",
    "instagram",
}
COMMERCIAL_TERMS = {
    "cuesta",
    "precio",
    "plan",
    "movia",
    "captura",
    "hibrido",
    "ventas",
    "pro comercial",
    "link",
    "disponible",
}


def score_turn(
    validation_turn: ValidationTurn,
    response: ChatResponse,
    source_capabilities: Set[str],
    ground_truth: Dict[str, Any],
    scenario: ValidationScenario,
    user_history: Sequence[str],
    scenario_business_terms: Dict[str, Set[str]],
) -> Tuple[List[MetricResult], List[HardFailure]]:
    metrics = _score_expected_fields(validation_turn, response, source_capabilities)
    failures = detect_hard_failures(
        validation_turn=validation_turn,
        response=response,
        ground_truth=ground_truth,
        scenario=scenario,
        user_history=user_history,
        scenario_business_terms=scenario_business_terms,
    )
    metrics.extend(_hard_rule_metrics(validation_turn, response, failures))
    metrics.extend(_semantic_requirement_metrics(validation_turn, response, user_history))
    metrics.extend(_memory_metrics(validation_turn, response))
    metrics.extend(_rag_metrics(validation_turn, response))
    return metrics, failures


def _score_expected_fields(
    validation_turn: ValidationTurn,
    response: ChatResponse,
    source_capabilities: Set[str],
) -> List[MetricResult]:
    expected = validation_turn.expected
    actual = {
        "current_stage": response.lead_state.get("current_stage"),
        "macro_action": response.selected_action.get("macro_action"),
        "micro_action": response.selected_action.get("micro_action"),
        "final_cta_type": response.selected_action.get("cta_type"),
        "objection_type": response.analysis.objection_type,
        "objection_flow_step": response.selected_action.get("objection_flow_step"),
        "rag_used": bool(response.retrieved_sources),
        "structured_used": bool(response.knowledge_plan.get("structured_sources")),
        "json_used": bool(response.knowledge_plan.get("json_sources")),
    }
    metrics: List[MetricResult] = []
    for expected_field, expected_value in expected.items():
        if expected_field == "expected_sources":
            metrics.extend(
                _score_expected_sources(
                    expected_sources=expected_value or [],
                    response=response,
                    source_capabilities=source_capabilities,
                )
            )
            continue
        mapping = EXPECTED_FIELD_MAP.get(expected_field)
        if mapping is None:
            metrics.append(
                MetricResult(
                    name=f"expected.{expected_field}",
                    category="dataset_contract",
                    status="not_applicable",
                    expected=expected_value,
                    reason="The current agent does not emit a compatible field.",
                )
            )
            continue
        category, actual_field = mapping
        actual_value = actual[actual_field]
        score = 1.0 if actual_value == expected_value else 0.0
        metrics.append(
            MetricResult(
                name=f"trace.{expected_field}",
                category=category,
                status="passed" if score == 1.0 else "failed",
                score=score,
                threshold=1.0,
                expected=expected_value,
                actual=actual_value,
                reason="Soft trace agreement; differences do not create a hard failure.",
            )
        )
    return metrics


def _score_expected_sources(
    expected_sources: Sequence[str],
    response: ChatResponse,
    source_capabilities: Set[str],
) -> List[MetricResult]:
    metrics: List[MetricResult] = []
    applicable = sorted(set(expected_sources) & source_capabilities)
    unsupported = sorted(set(expected_sources) - source_capabilities)
    for source in unsupported:
        metrics.append(
            MetricResult(
                name=f"source.{source}",
                category="source_selection",
                status="not_applicable",
                expected=True,
                reason="This logical source is not emitted by the current agent.",
            )
        )
    if not applicable:
        metrics.append(
            MetricResult(
                name="source.expected_recall",
                category="source_selection",
                status="not_applicable",
                expected=list(expected_sources),
                reason="None of the expected logical sources are current agent capabilities.",
            )
        )
        return metrics
    actual = emitted_source_labels(response.knowledge_plan, response.retrieved_sources)
    matched = sorted(set(applicable) & actual)
    score = len(matched) / len(applicable)
    metrics.append(
        MetricResult(
            name="source.expected_recall",
            category="source_selection",
            status="passed" if score == 1.0 else "failed",
            score=score,
            threshold=1.0,
            expected=applicable,
            actual=sorted(actual),
            reason="Only current agent source capabilities are included in the denominator.",
        )
    )
    return metrics


def detect_hard_failures(
    validation_turn: ValidationTurn,
    response: ChatResponse,
    ground_truth: Dict[str, Any],
    scenario: ValidationScenario,
    user_history: Sequence[str],
    scenario_business_terms: Dict[str, Set[str]],
) -> List[HardFailure]:
    failures: List[HardFailure] = []
    text = normalize_text(response.response)
    products = ground_truth.get("products") or []

    allowed_amounts = _allowed_currency_amounts(products)
    for amount in extract_currency_amounts(response.response):
        if amount not in allowed_amounts:
            failures.append(
                HardFailure(
                    code="unknown_price",
                    category="commercial_accuracy",
                    reason=f"Response contains unsupported currency amount ${amount:,.2f}.",
                    turn_id=validation_turn.turn_id,
                )
            )

    official_urls = {
        str(item.get("url")).rstrip("/")
        for item in ground_truth.get("official_links") or []
        if item.get("url")
    }
    for url in extract_urls(response.response):
        if official_urls and url.rstrip("/") not in official_urls:
            failures.append(
                HardFailure(
                    code="unofficial_link",
                    category="commercial_accuracy",
                    reason=f"Response contains a non-official link: {url}",
                    turn_id=validation_turn.turn_id,
                )
            )

    for channel in ("facebook", "instagram"):
        if _claims_channel_is_available(text, channel):
            failures.append(
                HardFailure(
                    code="future_channel_sold_as_available",
                    category="commercial_accuracy",
                    reason=f"Response presents {channel.title()} as currently available.",
                    turn_id=validation_turn.turn_id,
                )
            )

    for product in products:
        if product.get("status") == "available":
            continue
        product_name = normalize_text(str(product.get("name") or ""))
        if product_name and product_name in text and _claims_product_is_available(text, product_name):
            failures.append(
                HardFailure(
                    code="unavailable_product_sold_as_active",
                    category="commercial_accuracy",
                    reason=f"Response presents {product.get('name')} as currently available.",
                    turn_id=validation_turn.turn_id,
                )
            )

    if _claims_refund_is_available(text):
        failures.append(
            HardFailure(
                code="incorrect_refund_policy",
                category="policy_compliance",
                reason="Response claims or implies that the deposit can be refunded.",
                turn_id=validation_turn.turn_id,
            )
        )

    if "deposito" in text:
        for percentage in _deposit_percentages(response.response):
            if percentage != 50:
                failures.append(
                    HardFailure(
                        code="incorrect_deposit_percentage",
                        category="policy_compliance",
                        reason=f"Response states an unsupported deposit percentage: {percentage}%.",
                        turn_id=validation_turn.turn_id,
                    )
                )

    if (
        response.analysis.is_post_purchase
        and response.action != "handoff_to_miguel"
        and _post_purchase_handoff_required(response)
    ):
        failures.append(
            HardFailure(
                code="missing_post_purchase_handoff",
                category="policy_compliance",
                reason="A post-purchase turn was not routed to Miguel.",
                turn_id=validation_turn.turn_id,
            )
        )

    if _claims_captura_external_actions(text):
        failures.append(
            HardFailure(
                code="captura_scope_overpromise",
                category="scope_control",
                reason="Response claims MovIA Captura performs unsupported external actions.",
                turn_id=validation_turn.turn_id,
            )
        )

    history_text = normalize_text(" ".join(user_history) + " " + validation_turn.user)
    for conversation_id, terms in scenario_business_terms.items():
        if conversation_id == scenario.conversation_id:
            continue
        for term in terms:
            if _term_is_generic_business_word(term):
                continue
            if term and term in text and term not in history_text:
                failures.append(
                    HardFailure(
                        code="cross_scenario_memory_leak",
                        category="memory_consistency",
                        reason=f"Response referenced another scenario's business context: {term}.",
                        turn_id=validation_turn.turn_id,
                    )
                )
                break

    return dedupe_hard_failures(failures)


def _hard_rule_metrics(
    validation_turn: ValidationTurn,
    response: ChatResponse,
    failures: Sequence[HardFailure],
) -> List[MetricResult]:
    combined = normalize_text(validation_turn.user + " " + response.response)
    failure_categories = {failure.category for failure in failures}
    relevant = {
        "commercial_accuracy": any(term in combined for term in COMMERCIAL_TERMS),
        "policy_compliance": any(term in combined for term in POLICY_TERMS),
        "scope_control": any(term in combined for term in SCOPE_TERMS),
        "memory_consistency": validation_turn.turn_id > 1,
    }
    metrics = []
    for category, is_relevant in relevant.items():
        if not is_relevant:
            metrics.append(
                MetricResult(
                    name=f"rules.{category}",
                    category=category,
                    status="not_applicable",
                    reason="No deterministic rule for this category applies to the turn.",
                )
            )
            continue
        score = 0.0 if category in failure_categories else 1.0
        metrics.append(
            MetricResult(
                name=f"rules.{category}",
                category=category,
                status="passed" if score == 1.0 else "failed",
                score=score,
                threshold=1.0,
                reason="Deterministic validation against the current MovIA knowledge contract.",
            )
        )
    return metrics


def _semantic_requirement_metrics(
    validation_turn: ValidationTurn,
    response: ChatResponse,
    user_history: Sequence[str],
) -> List[MetricResult]:
    normalized = dict((response.response_metadata or {}).get("normalized_turn") or {})
    profile_data = dict(response.lead_state.get("profile_data") or {})
    requirement_profile = dict(profile_data.get("requirement_profile") or {})
    requirement_class = str(
        normalized.get("requirement_class")
        or requirement_profile.get("requirement_class")
        or "unknown"
    )
    scope_flags = set(normalized.get("scope_flags") or [])
    observed_problems = set(normalized.get("observed_business_problems") or [])
    requested_capabilities = set(normalized.get("requested_agent_capabilities") or [])
    requested_actions = set(normalized.get("requested_agent_actions") or [])
    active_profile_actions = set(_active_profile_types(requirement_profile.get("external_actions")))
    active_sales_caps = set(_active_profile_types(requirement_profile.get("sales_capabilities")))
    user_text = normalize_text(validation_turn.user)
    history_text = normalize_text(" ".join(user_history))
    response_text = normalize_text(response.response)
    selected = response.selected_action or {}

    checks = [
        _semantic_metric(
            "problem_capability_leakage",
            "scope_control",
            not (
                observed_problems
                and requested_capabilities
                and not _future_agent_requirement_context(user_text)
            ),
            {
                "observed_business_problems": sorted(observed_problems),
                "requested_agent_capabilities": sorted(requested_capabilities),
            },
            "Business problems must not become future-agent capabilities.",
        ),
        _semantic_metric(
            "current_question_future_capability_leakage",
            "scope_control",
            not (
                _current_salesperson_question(user_text)
                and requested_capabilities
                and not _future_agent_requirement_context(user_text)
            ),
            {
                "requested_agent_capabilities": sorted(requested_capabilities),
                "user": validation_turn.user,
            },
            "Current questions to MovIA must not become future-agent requirements.",
        ),
        _semantic_metric(
            "requirement_profile_reset",
            "memory_consistency",
            not _requirement_profile_reset(history_text, requirement_profile),
            {
                "history": list(user_history),
                "requirement_profile": requirement_profile,
            },
            "Persisted requirements must not disappear without explicit correction or removal.",
        ),
        _semantic_metric(
            "premature_product_recommendation",
            "sales_progression",
            not (
                requirement_class == "unknown"
                and (
                    selected.get("macro_action") == MacroAction.RECOMMEND_SOLUTION.value
                    or _mentions_product_recommendation(response_text)
                )
            ),
            {
                "requirement_class": requirement_class,
                "macro_action": selected.get("macro_action"),
                "response": response.response,
            },
            "Product recommendation requires a known requirement class.",
        ),
        _semantic_metric(
            "sales_capability_misrouted",
            "commercial_accuracy",
            not (
                active_sales_caps
                and (
                    profile_data.get("known_product_fit")
                    in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}
                    or selected.get("micro_action")
                    in {"recommend_movia_captura", "recommend_movia_hibrido"}
                )
            ),
            {
                "sales_capabilities": sorted(active_sales_caps),
                "known_product_fit": profile_data.get("known_product_fit"),
                "selected_action": selected,
            },
            "Sales capabilities must not route to Captura or Híbrido as informational needs.",
        ),
        _semantic_metric(
            "external_action_scope_miss",
            "scope_control",
            not _external_action_scope_miss(
                requested_actions=requested_actions,
                profile_actions=active_profile_actions,
                requirement_profile=requirement_profile,
                scope_flags=scope_flags,
                profile_data=profile_data,
            ),
            {
                "requested_agent_actions": sorted(requested_actions),
                "profile_external_actions": sorted(active_profile_actions),
                "declared_external_action_count": requirement_profile.get("declared_external_action_count"),
                "scope_flags": sorted(scope_flags),
                "known_product_fit": profile_data.get("known_product_fit"),
            },
            "External actions must be preserved, counted and scoped correctly.",
        ),
        _semantic_metric(
            "wrong_product_direct_close",
            "commercial_accuracy",
            not _wrong_product_direct_close(response),
            {
                "macro_action": selected.get("macro_action"),
                "cta_type": selected.get("cta_type"),
                "profile_data": profile_data,
                "scope_flags": sorted(scope_flags),
            },
            "Direct close requires confirmed or selected compatible product state.",
        ),
        _semantic_metric(
            "unsupported_standard_scope_claim",
            "scope_control",
            not (
                (
                    "custom_scope_review_required" in scope_flags
                    or profile_data.get("known_product_fit") == ProductFit.CUSTOM_REVIEW.value
                )
                and _claims_standard_hibrido_scope(response_text)
            ),
            {
                "scope_flags": sorted(scope_flags),
                "known_product_fit": profile_data.get("known_product_fit"),
                "response": response.response,
            },
            "Unsupported or custom scope must not be described as standard-package coverage.",
        ),
    ]
    return checks


def _semantic_metric(
    name: str,
    category: str,
    passed: bool,
    actual: Dict[str, Any],
    reason: str,
) -> MetricResult:
    return MetricResult(
        name=f"semantic.{name}",
        category=category,
        status="passed" if passed else "failed",
        score=1.0 if passed else 0.0,
        threshold=1.0,
        actual=actual,
        reason=reason,
        framework="deterministic",
    )


def _memory_metrics(
    validation_turn: ValidationTurn,
    response: ChatResponse,
) -> List[MetricResult]:
    metrics: List[MetricResult] = []
    known_slots = _known_slots_from_response(response)
    violations = list(
        (response.response_metadata.get("memory_validation") or {}).get("violations") or []
    )
    if not violations:
        violations = _known_slot_repetition_violations(response.response, known_slots)
    if known_slots:
        metrics.append(
            MetricResult(
                name="memory.known_slot_repetition",
                category="memory_consistency",
                status="passed" if not violations else "failed",
                score=1.0 if not violations else 0.0,
                threshold=1.0,
                expected="Do not ask again for known structured slots.",
                actual=violations,
                reason="Checks response text and response-memory validator output for repeated known-slot questions.",
            )
        )
    else:
        metrics.append(
            MetricResult(
                name="memory.known_slot_repetition",
                category="memory_consistency",
                status="not_applicable",
                reason="No known structured slots were emitted for this turn.",
            )
        )

    if response.analysis.references_prior_message:
        evidence = response.retrieval_metadata.get("conversation_memory_evidence") or []
        metrics.append(
            MetricResult(
                name="memory.historical_reference_accuracy",
                category="memory_consistency",
                status="passed" if evidence else "failed",
                score=1.0 if evidence else 0.0,
                threshold=1.0,
                expected="Relevant prior-turn evidence is retrieved when the user references earlier context.",
                actual=evidence,
            )
        )
        text = normalize_text(response.response)
        consistent = bool(evidence) and "no recuerdo" not in text and "no tengo contexto" not in text
        metrics.append(
            MetricResult(
                name="memory.prior_commitment_consistency",
                category="memory_consistency",
                status="passed" if consistent else "failed",
                score=1.0 if consistent else 0.0,
                threshold=1.0,
                expected="Response should use prior evidence without contradicting it.",
                actual=response.response,
            )
        )
    else:
        metrics.extend(
            [
                MetricResult(
                    name="memory.historical_reference_accuracy",
                    category="memory_consistency",
                    status="not_applicable",
                    reason="The turn does not reference prior conversation.",
                ),
                MetricResult(
                    name="memory.prior_commitment_consistency",
                    category="memory_consistency",
                    status="not_applicable",
                    reason="The turn does not reference prior conversation.",
                ),
            ]
        )

    personalization_applies = bool(known_slots) and any(
        term in normalize_text(validation_turn.user)
        for term in ["precio", "cuesta", "plan", "recomend", "conviene", "agente"]
    )
    if personalization_applies:
        text = normalize_text(response.response)
        expected_terms = {
            normalize_text(str(value))
            for value in known_slots.values()
            if str(value) not in {"answers_only", "external_actions_required"}
        }
        expected_terms.update(["captura", "hibrido", "híbrido"])
        used_context = any(term and term in text for term in expected_terms)
        metrics.append(
            MetricResult(
                name="memory.contextual_personalization",
                category="memory_consistency",
                status="passed" if used_context else "failed",
                score=1.0 if used_context else 0.0,
                threshold=1.0,
                expected=sorted(expected_terms),
                actual=response.response,
                reason="Checks whether relevant known lead context is reflected when the turn asks for product guidance.",
            )
        )
    else:
        metrics.append(
            MetricResult(
                name="memory.contextual_personalization",
                category="memory_consistency",
                status="not_applicable",
                reason="No product-guidance turn with known lead context.",
            )
        )
    return metrics


def _rag_metrics(
    validation_turn: ValidationTurn,
    response: ChatResponse,
) -> List[MetricResult]:
    route = _expected_rag_route(validation_turn, response)
    planned = bool(response.knowledge_plan.get("rag_queries"))
    retrieved = bool(response.retrieved_sources)
    metrics: List[MetricResult] = []

    expected_needed = route.get("needs_rag")
    if expected_needed is None:
        metrics.append(
            MetricResult(
                name="rag.retrieval_necessity",
                category="source_selection",
                status="not_applicable",
                actual=planned,
                reason="This turn does not have a deterministic RAG necessity rule.",
            )
        )
    else:
        score = 1.0 if planned == expected_needed else 0.0
        metrics.append(
            MetricResult(
                name="rag.retrieval_necessity",
                category="source_selection",
                status="passed" if score == 1.0 else "failed",
                score=score,
                threshold=1.0,
                expected=expected_needed,
                actual=planned,
                reason="Checks whether RAG was planned only when deterministic policy says it is useful.",
            )
        )

    expected_filter = dict(route.get("metadata_filter") or {})
    actual_filter = dict(
        response.knowledge_plan.get("rag_metadata_filter")
        or response.retrieval_metadata.get("rag_metadata_filter")
        or {}
    )
    if not planned:
        metrics.append(
            MetricResult(
                name="rag.routing_accuracy",
                category="source_selection",
                status="not_applicable",
                expected=expected_filter,
                actual=actual_filter,
                reason="No RAG route was planned for this turn.",
            )
        )
    elif expected_filter:
        route_ok = _metadata_filter_contains(actual_filter, expected_filter)
        metrics.append(
            MetricResult(
                name="rag.routing_accuracy",
                category="source_selection",
                status="passed" if route_ok else "failed",
                score=1.0 if route_ok else 0.0,
                threshold=1.0,
                expected=expected_filter,
                actual=actual_filter,
                reason="Checks whether the planner selected the expected topic, industry, or comparison filter.",
            )
        )
    else:
        metrics.append(
            MetricResult(
                name="rag.routing_accuracy",
                category="source_selection",
                status="not_applicable",
                actual=actual_filter,
                reason="The expected RAG route has no deterministic metadata filter.",
            )
        )

    if expected_needed is True and not retrieved:
        metrics.append(
            MetricResult(
                name="rag.context_relevance",
                category="source_selection",
                status="failed",
                score=0.0,
                threshold=1.0,
                expected=expected_filter or "relevant RAG context",
                actual=[],
                reason="The turn needed RAG but no relevant chunk survived retrieval.",
            )
        )
    elif retrieved:
        relevant_count = sum(
            1
            for source in response.retrieved_sources
            if _source_relevant(source, expected_filter)
        )
        score = relevant_count / len(response.retrieved_sources)
        metrics.append(
            MetricResult(
                name="rag.context_relevance",
                category="source_selection",
                status="passed" if score == 1.0 else "failed",
                score=round(score, 4),
                threshold=1.0,
                expected=expected_filter or f"similarity >= {MIN_RAG_SIMILARITY}",
                actual=[
                    {
                        "source_path": source.get("source_path"),
                        "similarity": source.get("similarity"),
                        "metadata": source.get("metadata") or {},
                    }
                    for source in response.retrieved_sources
                ],
                reason="Checks retrieved chunk metadata and minimum relevance threshold.",
            )
        )
    else:
        metrics.append(
            MetricResult(
                name="rag.context_relevance",
                category="source_selection",
                status="not_applicable",
                reason="No RAG context was retrieved.",
            )
        )

    if not retrieved:
        metrics.append(
            MetricResult(
                name="rag.answer_groundedness",
                category="source_selection",
                status="not_applicable",
                reason="No RAG context was retrieved.",
            )
        )
        return metrics

    grounding_terms = _grounding_terms(response.retrieved_sources, expected_filter)
    if not grounding_terms:
        metrics.append(
            MetricResult(
                name="rag.answer_groundedness",
                category="source_selection",
                status="not_applicable",
                reason="No deterministic grounding term could be extracted from retrieved context.",
            )
        )
        return metrics

    text = normalize_text(response.response)
    grounded = any(term and term in text for term in grounding_terms)
    metrics.append(
        MetricResult(
            name="rag.answer_groundedness",
            category="source_selection",
            status="passed" if grounded else "failed",
            score=1.0 if grounded else 0.0,
            threshold=1.0,
            expected=sorted(grounding_terms),
            actual=response.response,
            reason="Checks whether the answer visibly used the selected RAG context.",
        )
    )
    return metrics


def _expected_rag_route(
    validation_turn: ValidationTurn,
    response: ChatResponse,
) -> Dict[str, Any]:
    analysis = response.analysis
    topics = set(analysis.topics)
    macro_action = response.selected_action.get("macro_action")
    objection_step = response.selected_action.get("objection_flow_step")

    if Topic.COMPETITOR_COMPARISON.value in topics or macro_action == MacroAction.COMPARE_ALTERNATIVE.value:
        target = comparison_target_from_text(validation_turn.user)
        metadata_filter = {"topic": "comparisons"}
        if target:
            metadata_filter["comparison"] = target
        return {"needs_rag": True, "metadata_filter": metadata_filter}

    if Topic.INDUSTRY_USE_CASE.value in topics or Topic.BUSINESS_FIT.value in topics:
        industry = industry_from_analysis(analysis)
        if industry:
            return {
                "needs_rag": True,
                "metadata_filter": {"topic": "use_cases", "industry": industry},
            }
        return {"needs_rag": True, "metadata_filter": {"topic": "overview"}}

    if objection_step == ObjectionFlowStep.PROVIDE_PROOF.value:
        industry = industry_from_analysis(analysis)
        if industry:
            return {
                "needs_rag": True,
                "metadata_filter": {"topic": "use_cases", "industry": industry},
            }
        target = comparison_target_from_text(validation_turn.user)
        if target:
            return {
                "needs_rag": True,
                "metadata_filter": {"topic": "comparisons", "comparison": target},
            }
        return {"needs_rag": False, "metadata_filter": {}}

    structured_only_topics = {
        Topic.PRICING.value,
        Topic.PRODUCT_SCOPE.value,
        Topic.PLATFORM_PROCESS.value,
        Topic.ONBOARDING.value,
        Topic.DEPOSIT.value,
        Topic.FINAL_PAYMENT.value,
        Topic.MONTHLY_PAYMENT.value,
        Topic.REFUND_POLICY.value,
        Topic.SUPPORT.value,
        Topic.TOKEN_USAGE.value,
        Topic.WHATSAPP.value,
        Topic.FACEBOOK.value,
        Topic.INSTAGRAM.value,
        Topic.INTEGRATION.value,
    }
    if topics & structured_only_topics:
        return {"needs_rag": False, "metadata_filter": {}}

    return {"needs_rag": None, "metadata_filter": {}}


def _metadata_filter_contains(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _source_relevant(source: Dict[str, Any], expected_filter: Dict[str, Any]) -> bool:
    similarity = source.get("similarity")
    if isinstance(similarity, (int, float)) and float(similarity) < MIN_RAG_SIMILARITY:
        return False
    metadata = dict(source.get("metadata") or {})
    if expected_filter and not _metadata_filter_contains(metadata, expected_filter):
        return False
    return True


def _grounding_terms(
    retrieved_sources: Sequence[Dict[str, Any]],
    expected_filter: Dict[str, Any],
) -> Set[str]:
    terms = {
        normalize_text(str(value))
        for key, value in expected_filter.items()
        if key in {"industry", "comparison", "comparison_target", "product"}
    }
    for source in retrieved_sources:
        metadata = source.get("metadata") or {}
        for key in ("industry", "comparison", "comparison_target", "product"):
            if metadata.get(key):
                terms.add(normalize_text(str(metadata[key])))
    return {term for term in terms if term}


def aggregate_scenario(
    scenario_result: ScenarioEvaluationResult,
    suite_type: str = SuiteType.ATOMIC_SCRIPTED.value,
) -> ScenarioEvaluationResult:
    all_metrics = [
        metric
        for turn in scenario_result.turns
        for metric in turn.metrics
    ] + list(scenario_result.conversation_metrics)
    scenario_result.hard_failures = dedupe_hard_failures(
        [failure for turn in scenario_result.turns for failure in turn.hard_failures]
        + list(scenario_result.hard_failures)
    )
    scenario_result.category_scores = category_scores(all_metrics)
    scenario_result.score_groups = score_groups(scenario_result.category_scores, suite_type)
    scenario_result.overall_score = weighted_score(scenario_result.category_scores, suite_type)
    scenario_result.passed = passes_policy(
        scenario_result.overall_score,
        scenario_result.category_scores,
        scenario_result.hard_failures,
        suite_type=suite_type,
    )
    return scenario_result


def category_scores(metrics: Iterable[MetricResult]) -> Dict[str, float]:
    values: Dict[str, List[float]] = defaultdict(list)
    for metric in metrics:
        if metric.status not in {"passed", "failed"} or metric.score is None:
            continue
        if metric.category not in CATEGORY_WEIGHTS:
            continue
        values[metric.category].append(float(metric.score))
    return {
        category: round(sum(scores) / len(scores), 4)
        for category, scores in values.items()
        if scores
    }


def weighted_score(
    scores: Dict[str, float],
    suite_type: str = SuiteType.ATOMIC_SCRIPTED.value,
) -> Optional[float]:
    applicable_categories = authoritative_categories(scores, suite_type)
    applicable_weight = sum(CATEGORY_WEIGHTS[category] for category in applicable_categories)
    if not applicable_weight:
        return None
    total = sum(
        scores[category] * CATEGORY_WEIGHTS[category]
        for category in applicable_categories
    )
    return round(total / applicable_weight, 4)


def passes_policy(
    overall_score: Optional[float],
    scores: Dict[str, float],
    hard_failures: Sequence[HardFailure],
    suite_type: str = SuiteType.ATOMIC_SCRIPTED.value,
) -> bool:
    if hard_failures or overall_score is None or overall_score < 0.80:
        return False
    return all(
        score >= CATEGORY_THRESHOLDS.get(category, 0.70)
        for category, score in scores.items()
        if category_is_authoritative(category, suite_type)
    )


def score_groups(
    scores: Dict[str, float],
    suite_type: str = SuiteType.ATOMIC_SCRIPTED.value,
) -> Dict[str, Optional[float]]:
    grouped: Dict[str, List[float]] = {
        group.value: []
        for group in ScoreGroup
        if group != ScoreGroup.CRITICAL_RULES
    }
    for category, score in scores.items():
        if not category_is_authoritative(category, suite_type):
            continue
        group = CATEGORY_TO_SCORE_GROUP.get(category)
        if not group:
            continue
        grouped.setdefault(group, []).append(float(score))
    result: Dict[str, Optional[float]] = {
        group: round(sum(values) / len(values), 4) if values else None
        for group, values in grouped.items()
    }
    primary_group = suite_primary_score_group(suite_type)
    if primary_group and result.get(primary_group) is not None:
        result["primary"] = result[primary_group]
    else:
        result["primary"] = weighted_score(scores, suite_type)
    return result


def scenario_business_terms(scenarios: Sequence[ValidationScenario]) -> Dict[str, Set[str]]:
    terms: Dict[str, Set[str]] = {}
    for scenario in scenarios:
        business_type = normalize_text(str(scenario.lead_profile_seed.get("business_type") or ""))
        candidates = {
            item.strip()
            for item in re.split(r"[/,]", business_type)
            if len(item.strip()) >= 5
        }
        terms[scenario.conversation_id] = candidates
    return terms


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def extract_currency_amounts(value: str) -> List[float]:
    amounts = []
    for match in re.finditer(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", value or ""):
        amounts.append(float(match.group(1).replace(",", "")))
    return amounts


def extract_percentages(value: str) -> List[int]:
    return [int(match) for match in re.findall(r"\b([0-9]{1,3})\s*%", value or "")]


def extract_urls(value: str) -> List[str]:
    return [
        match.rstrip(".,;:!?")
        for match in re.findall(r"https?://[^\s)\]}>,]+", value or "")
    ]


def _allowed_currency_amounts(products: Sequence[Dict[str, Any]]) -> Set[float]:
    amounts: Set[float] = set()
    for product in products:
        for key in ("setup_price_mxn", "monthly_price_mxn"):
            value = product.get(key)
            if value is None:
                continue
            numeric = float(value)
            amounts.add(numeric)
            if key == "setup_price_mxn":
                amounts.add(numeric * 0.5)
    return amounts


def _claims_channel_is_available(text: str, channel: str) -> bool:
    patterns = [
        rf"{channel}\s+(ya\s+)?(esta\s+)?disponible",
        rf"{channel}\s+ya\s+funciona",
        rf"(conectar|conectamos|usar|usamos)\s+{channel}\s+(ahora|hoy|ya)",
    ]
    return any(re.search(pattern, text) for pattern in patterns) and not any(
        phrase in text
        for phrase in [
            f"{channel} no esta disponible",
            f"{channel} aun no",
            f"{channel} esta en proceso",
        ]
    )


def _claims_product_is_available(text: str, product_name: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            f"{product_name} esta disponible",
            f"te recomiendo {product_name}",
            f"puedes contratar {product_name}",
            f"puedes iniciar con {product_name}",
        ]
    ) and not any(word in text for word in ["no disponible", "futuro", "proximamente"])


def _claims_refund_is_available(text: str) -> bool:
    positive = [
        "el deposito es reembolsable",
        "si hay reembolso",
        "te devolvemos el deposito",
        "devolvemos el deposito",
        "puedes pedir reembolso",
    ]
    return any(phrase in text for phrase in positive)


def _deposit_percentages(text: str) -> List[int]:
    normalized = normalize_text(text)
    percentages: List[int] = []
    for match in re.finditer(r"(\d{1,3})\s*%", normalized):
        before = normalized[max(0, match.start() - 70):match.start()]
        after = normalized[match.end():min(len(normalized), match.end() + 24)]
        if any(term in before for term in ["deposito", "pago inicial", "anticipo"]) or any(
            phrase in after for phrase in ["de deposito", "del deposito", "de pago inicial", "del pago inicial", "de anticipo"]
        ):
            percentages.append(int(match.group(1)))
    return percentages


def _term_is_generic_business_word(term: str) -> bool:
    return normalize_text(term) in {
        "garantia",
        "garantias",
        "proveedor",
        "proveedores",
        "ticket",
        "tickets",
        "foto",
        "fotos",
        "precio",
        "precios",
        "whatsapp",
        "cliente",
        "clientes",
    }


def _claims_captura_external_actions(text: str) -> bool:
    if "captura" not in text:
        return False
    positive_patterns = [
        r"captura\s+(puede\s+)?agendar",
        r"captura\s+(puede\s+)?cotizar",
        r"captura\s+(puede\s+)?registrar",
        r"captura\s+(puede\s+)?subir\s+datos",
        r"captura\s+(puede\s+)?enviar\s+recordatorios",
        r"captura\s+ejecuta\s+acciones",
    ]
    return any(re.search(pattern, text) for pattern in positive_patterns) and not any(
        phrase in text
        for phrase in [
            "captura no",
            "captura solo",
            "captura se limita",
        ]
    )


def _known_slots_from_response(response: ChatResponse) -> Dict[str, Any]:
    profile_data = dict(response.lead_state.get("profile_data") or {})
    known = {
        "business_type": response.lead_state.get("business_type"),
        "main_channel": response.lead_state.get("main_channel"),
        "pain_or_goal": response.lead_state.get("pain"),
        "action_requirement": profile_data.get("action_requirement"),
        "known_product_fit": profile_data.get("known_product_fit"),
    }
    return {
        key: value
        for key, value in known.items()
        if value not in (None, "", "unknown", [], {})
    }


def _active_profile_types(entries: Any) -> List[str]:
    return [
        str(entry.get("type"))
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("type") and entry.get("active", True)
    ]


def _future_agent_requirement_context(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "quiero que",
            "necesito que",
            "busco que",
            "que el agente",
            "mi agente",
            "quiero movia",
            "quiero captura",
            "quiero hibrido",
            "quiero híbrido",
            "lo quiero para",
            "necesito un agente",
        ]
    )


def _current_salesperson_question(text: str) -> bool:
    return "?" in text or any(
        phrase in text
        for phrase in [
            "cuanto cuesta",
            "cuánto cuesta",
            "precio",
            "plan mas barato",
            "plan más barato",
            "como empiezo",
            "cómo empiezo",
            "como lleno",
            "cómo lleno",
        ]
    )


def _requirement_profile_reset(history_text: str, requirement_profile: Dict[str, Any]) -> bool:
    if _contains_removal_signal(history_text):
        return False
    if _history_mentions_external_requirement(history_text) and not _active_profile_types(
        requirement_profile.get("external_actions")
    ):
        return True
    if _history_mentions_informational_requirement(history_text) and not _active_profile_types(
        requirement_profile.get("informational_capabilities")
    ):
        return True
    if _history_mentions_sales_requirement(history_text) and not _active_profile_types(
        requirement_profile.get("sales_capabilities")
    ):
        return True
    return False


def _history_mentions_external_requirement(text: str) -> bool:
    return _future_agent_requirement_context(text) and any(
        phrase in text
        for phrase in ["agend", "cotiz", "registr", "sistema", "pedido", "recordatorio"]
    )


def _history_mentions_informational_requirement(text: str) -> bool:
    return _future_agent_requirement_context(text) and any(
        phrase in text
        for phrase in ["responda", "responder", "contestar", "precios", "capture datos"]
    )


def _history_mentions_sales_requirement(text: str) -> bool:
    return _future_agent_requirement_context(text) and any(
        phrase in text
        for phrase in ["cierre ventas", "cerrar ventas", "venda por mi", "venda por mí"]
    )


def _contains_removal_signal(text: str) -> bool:
    return any(
        phrase in text
        for phrase in ["ya no necesito", "ya no quiero", "en realidad ya no", "quitar", "quitale"]
    )


def _mentions_product_recommendation(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "te conviene movia captura",
            "te conviene mas movia captura",
            "te conviene más movia captura",
            "te conviene movia hibrido",
            "te conviene mas movia hibrido",
            "te conviene más movia hibrido",
            "recomiendo movia captura",
            "recomiendo movia hibrido",
        ]
    )


def _external_action_scope_miss(
    *,
    requested_actions: Set[str],
    profile_actions: Set[str],
    requirement_profile: Dict[str, Any],
    scope_flags: Set[str],
    profile_data: Dict[str, Any],
) -> bool:
    if requested_actions and not requested_actions.issubset(profile_actions):
        return True
    declared = requirement_profile.get("declared_external_action_count") or {}
    declared_count = declared.get("value") if declared.get("active", True) else None
    if isinstance(declared_count, int) and declared_count > 2:
        return not (
            "custom_scope_review_required" in scope_flags
            or profile_data.get("known_product_fit") == ProductFit.CUSTOM_REVIEW.value
        )
    return False


def _wrong_product_direct_close(response: ChatResponse) -> bool:
    selected = response.selected_action or {}
    if selected.get("macro_action") != MacroAction.DIRECT_CLOSE.value:
        return False
    profile_data = dict(response.lead_state.get("profile_data") or {})
    normalized = dict((response.response_metadata or {}).get("normalized_turn") or {})
    product = profile_data.get("confirmed_product") or profile_data.get("selected_product")
    if product not in {ProductFit.MOVIA_CAPTURA.value, ProductFit.MOVIA_HIBRIDO.value}:
        return True
    if profile_data.get("known_product_fit") not in {
        ProductFit.MOVIA_CAPTURA.value,
        ProductFit.MOVIA_HIBRIDO.value,
    }:
        return True
    if any(
        flag in set(normalized.get("scope_flags") or [])
        for flag in ["unsupported_scope", "custom_scope_review_required", "product_preference_mismatch"]
    ):
        return True
    return product != profile_data.get("known_product_fit")


def _claims_standard_hibrido_scope(text: str) -> bool:
    if "hibrido" not in text and "híbrido" not in text:
        return False
    if any(phrase in text for phrase in ["revisión", "revision", "miguel", "alcance personalizado", "custom"]):
        return False
    return any(
        phrase in text
        for phrase in [
            "te conviene movia hibrido",
            "te conviene más movia hibrido",
            "te conviene mas movia hibrido",
            "hibrido cubre",
            "híbrido cubre",
            "con hibrido puedes",
            "con híbrido puedes",
        ]
    )


def _known_slot_repetition_violations(response_text: str, known_slots: Dict[str, Any]) -> List[str]:
    text = normalize_text(response_text)
    if "?" not in text:
        return []
    patterns = {
        "business_type": ["que tipo de negocio", "tipo de negocio tienes"],
        "main_channel": ["por donde te escriben", "canal principal"],
        "pain_or_goal": ["que quieres mejorar", "que parte de tu atencion"],
        "action_requirement": ["solo debe responder", "tambien hacer acciones", "agendar, cotizar o registrar"],
    }
    violations = []
    for slot, slot_patterns in patterns.items():
        if slot not in known_slots:
            continue
        if any(pattern in text for pattern in slot_patterns):
            violations.append(slot)
    return violations


def _post_purchase_handoff_required(response: ChatResponse) -> bool:
    metadata = response.response_metadata or {}
    if "purchase_status" not in metadata:
        return True
    status = str((metadata.get("purchase_status") or {}).get("status") or "")
    return status in {"deposit_confirmed", "paid_in_full"}


def dedupe_hard_failures(failures: Sequence[HardFailure]) -> List[HardFailure]:
    seen = set()
    result = []
    for failure in failures:
        key = (failure.code, failure.turn_id, failure.reason)
        if key in seen:
            continue
        seen.add(key)
        result.append(failure)
    return result
