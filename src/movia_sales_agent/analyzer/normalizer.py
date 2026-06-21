from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

from movia_sales_agent.analyzer.contract_v3 import (
    AnalyzerReferenceType,
    AnalyzerTurnObservation,
    INFORMATIONAL_AGENT_CAPABILITIES,
    RequestedAgentAction,
    RequirementUpdateIntent,
    RequestedProduct,
    evidence_span_in_message,
    observation_to_turn_analysis,
)
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionType,
    ProductFit,
    ReferenceType,
)
from movia_sales_agent.models.schemas import TurnAnalysis


NORMALIZED_TURN_CONTRACT_VERSION = "3.1"
CORE_COMMERCIAL_SLOTS = ["business_type", "main_channel", "pain_or_goal", "action_requirement"]
AVAILABLE_PRODUCTS = {RequestedProduct.MOVIA_CAPTURA.value, RequestedProduct.MOVIA_HIBRIDO.value}
UNAVAILABLE_PRODUCTS = {
    RequestedProduct.MOVIA_VENTAS.value,
    RequestedProduct.MOVIA_PRO_COMERCIAL.value,
}


class NormalizationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_code: str
    original_values: Dict[str, Any] = Field(default_factory=dict)
    normalized_values: Dict[str, Any] = Field(default_factory=dict)


class ParserLLMComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreement: List[str] = Field(default_factory=list)
    parser_only: List[str] = Field(default_factory=list)
    llm_only: List[str] = Field(default_factory=list)
    conflict: bool = False


class ParserLLMTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_problems: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    requested_capabilities: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    requested_actions: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    products: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    purchase_cues: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    prior_references: ParserLLMComparison = Field(default_factory=ParserLLMComparison)
    channels: ParserLLMComparison = Field(default_factory=ParserLLMComparison)


class NormalizedTurn(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    normalized_turn_contract_version: str = NORMALIZED_TURN_CONTRACT_VERSION
    has_objection: bool = False
    has_prior_reference: bool = False
    explicit_start_intent: bool = False
    is_post_purchase: bool = False
    action_requirement: ActionRequirement = ActionRequirement.UNKNOWN
    requested_product: RequestedProduct = RequestedProduct.NONE
    recommended_product: Optional[ProductFit] = None
    selected_product: Optional[RequestedProduct] = None
    product_preference_mismatch: bool = False
    observed_business_problems: List[str] = Field(default_factory=list)
    requested_agent_capabilities: List[str] = Field(default_factory=list)
    requested_agent_actions: List[str] = Field(default_factory=list)
    declared_external_action_count: Optional[int] = None
    requirement_update_intent: RequirementUpdateIntent = RequirementUpdateIntent.NO_CHANGE
    requested_capabilities: List[str] = Field(default_factory=list)
    requested_actions: List[str] = Field(default_factory=list)
    known_slots: List[str] = Field(default_factory=list)
    known_slot_values: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    normalized_objection: Dict[str, Any] = Field(default_factory=dict)
    objection_relation: ObjectionRelation = ObjectionRelation.NONE
    normalized_prior_reference: Dict[str, Any] = Field(default_factory=dict)
    contradictions: List[NormalizationIssue] = Field(default_factory=list)
    normalization_warnings: List[str] = Field(default_factory=list)
    parser_llm_telemetry: ParserLLMTelemetry = Field(default_factory=ParserLLMTelemetry)


def normalize_analyzer_turn(
    observation: AnalyzerTurnObservation | Dict[str, Any],
    *,
    message: str,
    lead_profile: Optional[Dict[str, Any]] = None,
    shadow_parser: Optional[Dict[str, Any]] = None,
) -> NormalizedTurn:
    if not isinstance(observation, AnalyzerTurnObservation):
        observation = AnalyzerTurnObservation.model_validate(observation)
    lead_profile = lead_profile or {}

    contradictions: List[NormalizationIssue] = []
    warnings: List[str] = []

    valid_actions = [
        action
        for action in observation.requested_agent_actions
        if _valid_future_agent_action(action, message)
    ]
    invalid_actions = [
        action
        for action in observation.requested_agent_actions
        if not _valid_future_agent_action(action, message)
    ]
    for action in invalid_actions:
        contradictions.append(
            _issue(
                "invalid_requested_action_semantics",
                {"type": action.type, "evidence_span": action.evidence_span},
                {"dropped": True},
            )
        )

    valid_capabilities = [
        capability
        for capability in observation.requested_agent_capabilities
        if _valid_future_agent_capability(capability, message)
    ]
    invalid_capabilities = [
        capability
        for capability in observation.requested_agent_capabilities
        if not _valid_future_agent_capability(capability, message)
    ]
    if invalid_capabilities:
        warnings.append("requested_agent_capabilities_without_valid_future_agent_semantics")
        for capability in invalid_capabilities:
            contradictions.append(
                _issue(
                    "invalid_requested_capability_semantics",
                    {"type": capability.type, "evidence_span": capability.evidence_span},
                    {"dropped": True},
                )
            )
    informational_capabilities = [
        capability
        for capability in valid_capabilities
        if capability.type in INFORMATIONAL_AGENT_CAPABILITIES
    ]
    valid_business_problems = [
        problem
        for problem in observation.observed_business_problems
        if problem.evidence_span and _valid_evidence(problem.evidence_span, message)
    ]

    normalized_objection = _normalize_objection(observation, message, contradictions)
    objection_relation = _derive_objection_relation(message, normalized_objection)
    normalized_prior = _normalize_prior_reference(observation, message, contradictions)
    explicit_start = _derive_explicit_start(observation, message, contradictions)
    is_post_purchase = _derive_post_purchase(observation, message, contradictions)
    action_requirement = _derive_action_requirement(valid_actions, informational_capabilities)
    requested_product = _normalize_requested_product(observation, message, contradictions)
    recommended_product = _derive_recommended_product(action_requirement)
    selected_product = _derive_selected_product(
        requested_product,
        recommended_product,
        explicit_start,
        observation.purchase_readiness.evidence_span,
        message,
        contradictions,
    )
    product_preference_mismatch = _derive_product_preference_mismatch(
        requested_product, recommended_product
    )

    if valid_actions and action_requirement == ActionRequirement.ANSWERS_ONLY.value:
        contradictions.append(
            _issue(
                "requested_action_with_answers_only_requirement",
                {"requested_actions": [action.type for action in valid_actions]},
                {"action_requirement": ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value},
            )
        )
        action_requirement = ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        recommended_product = ProductFit.MOVIA_HIBRIDO.value

    if action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value and recommended_product == ProductFit.MOVIA_CAPTURA.value:
        contradictions.append(
            _issue(
                "external_actions_cannot_recommend_captura",
                {"action_requirement": action_requirement, "recommended_product": recommended_product},
                {"recommended_product": ProductFit.MOVIA_HIBRIDO.value},
            )
        )
        recommended_product = ProductFit.MOVIA_HIBRIDO.value

    known_values = _known_slot_values(
        observation=observation,
        lead_profile=lead_profile,
        action_requirement=action_requirement,
    )
    known_slots = [slot for slot in CORE_COMMERCIAL_SLOTS if known_values.get(slot)]
    missing_slots = [slot for slot in CORE_COMMERCIAL_SLOTS if slot not in known_slots]

    telemetry = compare_parser_to_llm(
        shadow_parser or {},
        observation,
        valid_actions=valid_actions,
        valid_capabilities=valid_capabilities,
        valid_business_problems=valid_business_problems,
    )

    return NormalizedTurn(
        has_objection=normalized_objection["type"] != ObjectionType.NONE.value,
        has_prior_reference=normalized_prior["type"] != AnalyzerReferenceType.NONE.value,
        explicit_start_intent=explicit_start,
        is_post_purchase=is_post_purchase,
        action_requirement=action_requirement,
        requested_product=requested_product,
        recommended_product=recommended_product,
        selected_product=selected_product,
        product_preference_mismatch=product_preference_mismatch,
        observed_business_problems=[problem.type for problem in valid_business_problems],
        requested_agent_capabilities=[capability.type for capability in valid_capabilities],
        requested_agent_actions=[action.type for action in valid_actions],
        declared_external_action_count=(
            observation.declared_external_action_count.value
            if observation.declared_external_action_count
            and _valid_evidence(observation.declared_external_action_count.evidence_span, message)
            else None
        ),
        requirement_update_intent=observation.requirement_update_intent,
        requested_capabilities=[capability.type for capability in informational_capabilities],
        requested_actions=[action.type for action in valid_actions],
        known_slots=known_slots,
        known_slot_values={key: value for key, value in known_values.items() if value},
        missing_slots=missing_slots,
        normalized_objection=normalized_objection,
        objection_relation=objection_relation,
        normalized_prior_reference=normalized_prior,
        contradictions=contradictions,
        normalization_warnings=warnings,
        parser_llm_telemetry=telemetry,
    )


def normalized_turn_to_analysis(
    observation: AnalyzerTurnObservation | Dict[str, Any],
    normalized: NormalizedTurn,
    *,
    message: str,
) -> TurnAnalysis:
    if not isinstance(observation, AnalyzerTurnObservation):
        observation = AnalyzerTurnObservation.model_validate(observation)
    analysis = observation_to_turn_analysis(observation, message)

    objection = normalized.normalized_objection
    prior = normalized.normalized_prior_reference
    analysis.has_objection = normalized.has_objection
    analysis.objection_type = objection.get("type") or ObjectionType.NONE.value
    analysis.objection_strength = objection.get("strength") or ObjectionStrength.NONE.value
    analysis.objection_relation = normalized.objection_relation
    analysis.references_prior_message = normalized.has_prior_reference
    analysis.reference_type = _legacy_reference_type(prior.get("type"))
    analysis.reference_query = (prior.get("topic_hint") or prior.get("evidence_span")) if normalized.has_prior_reference else None
    if not normalized.has_prior_reference:
        analysis.referenced_topics = []
    analysis.explicit_turn_number = None
    analysis.explicit_start_intent = normalized.explicit_start_intent
    analysis.is_post_purchase = normalized.is_post_purchase
    if normalized.explicit_start_intent:
        analysis.buying_signal = BuyingSignal.EXPLICIT_START.value
    elif analysis.buying_signal == BuyingSignal.EXPLICIT_START.value:
        analysis.buying_signal = BuyingSignal.NONE.value

    known_values = normalized.known_slot_values
    analysis.business_type = known_values.get("business_type") or analysis.business_type
    analysis.main_channel = known_values.get("main_channel") or analysis.main_channel
    analysis.pain = known_values.get("pain_or_goal") or analysis.pain
    analysis.lead_updates.business_type = analysis.business_type
    analysis.lead_updates.main_channel = analysis.main_channel
    analysis.lead_updates.pain = analysis.pain
    profile_data = dict(analysis.lead_updates.profile_data or {})
    if normalized.action_requirement != ActionRequirement.UNKNOWN.value:
        profile_data["action_requirement"] = normalized.action_requirement
    else:
        profile_data.pop("action_requirement", None)
    if normalized.recommended_product:
        profile_data["known_product_fit"] = normalized.recommended_product
    elif normalized.requested_product == RequestedProduct.MOVIA_VENTAS.value:
        profile_data["known_product_fit"] = ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    elif normalized.requested_product == RequestedProduct.MOVIA_PRO_COMERCIAL.value:
        profile_data["known_product_fit"] = ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value
    else:
        profile_data.pop("known_product_fit", None)
    analysis.lead_updates.profile_data = profile_data
    return analysis


def compare_parser_to_llm(
    shadow_parser: Dict[str, Any],
    observation: AnalyzerTurnObservation,
    *,
    valid_actions: Optional[Sequence[Any]] = None,
    valid_capabilities: Optional[Sequence[Any]] = None,
    valid_business_problems: Optional[Sequence[Any]] = None,
) -> ParserLLMTelemetry:
    action_types = {
        action.type
        for action in (
            valid_actions if valid_actions is not None else observation.requested_agent_actions
        )
    }
    capability_types = {
        capability.type
        for capability in (
            valid_capabilities if valid_capabilities is not None else observation.requested_agent_capabilities
        )
    }
    problem_types = {
        problem.type
        for problem in (
            valid_business_problems
            if valid_business_problems is not None
            else observation.observed_business_problems
        )
    }
    product_types = {
        observation.requested_product.product
        if observation.requested_product.product != RequestedProduct.NONE.value
        else None
    } - {None}
    purchase_types = {
        observation.purchase_readiness.level
        if observation.purchase_readiness.level != BuyingSignal.NONE.value
        else None
    } - {None}
    prior_types = {
        observation.prior_reference.type
        if observation.prior_reference.type != AnalyzerReferenceType.NONE.value
        else None
    } - {None}
    channel_types = {
        observation.extracted_facts.main_channel
        if observation.extracted_facts.main_channel
        else None
    } - {None}
    return ParserLLMTelemetry(
        observed_problems=_compare_sets(
            _candidate_types(shadow_parser, "observed_problem_candidates"),
            problem_types,
        ),
        requested_capabilities=_compare_sets(
            _candidate_types(shadow_parser, "requested_capability_candidates"),
            capability_types,
        ),
        requested_actions=_compare_sets(
            _candidate_types(shadow_parser, "requested_action_candidates")
            or _candidate_types(shadow_parser, "action_candidates"),
            action_types,
        ),
        products=_compare_sets(_candidate_types(shadow_parser, "product_candidates"), product_types),
        purchase_cues=_compare_sets(_candidate_types(shadow_parser, "purchase_cue_candidates"), purchase_types),
        prior_references=_compare_sets(_candidate_types(shadow_parser, "prior_reference_candidates"), prior_types),
        channels=_compare_sets(set(shadow_parser.get("channel_candidates") or []), channel_types),
    )


def _normalize_objection(
    observation: AnalyzerTurnObservation,
    message: str,
    contradictions: List[NormalizationIssue],
) -> Dict[str, Any]:
    objection = observation.objection_candidate
    if objection.type == ObjectionType.NONE.value:
        if objection.strength != ObjectionStrength.NONE.value or objection.relation != ObjectionRelation.NONE.value or objection.evidence_span:
            contradictions.append(
                _issue(
                    "normalized_empty_objection",
                    objection.model_dump(),
                    {
                        "type": ObjectionType.NONE.value,
                        "strength": ObjectionStrength.NONE.value,
                        "relation": ObjectionRelation.NONE.value,
                        "evidence_span": None,
                    },
                )
            )
        return {
            "type": ObjectionType.NONE.value,
            "strength": ObjectionStrength.NONE.value,
            "relation": ObjectionRelation.NONE.value,
            "evidence_span": None,
        }
    if not _valid_evidence(objection.evidence_span, message):
        contradictions.append(
            _issue(
                "invalid_objection_evidence",
                objection.model_dump(),
                {
                    "type": ObjectionType.NONE.value,
                    "strength": ObjectionStrength.NONE.value,
                    "relation": ObjectionRelation.NONE.value,
                    "evidence_span": None,
                },
            )
        )
        return {
            "type": ObjectionType.NONE.value,
            "strength": ObjectionStrength.NONE.value,
            "relation": ObjectionRelation.NONE.value,
            "evidence_span": None,
        }
    return objection.model_dump()


def _normalize_prior_reference(
    observation: AnalyzerTurnObservation,
    message: str,
    contradictions: List[NormalizationIssue],
) -> Dict[str, Any]:
    prior = observation.prior_reference
    if prior.type == AnalyzerReferenceType.NONE.value:
        return {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None}
    if _false_prior_reference_phrase(prior.evidence_span or message):
        contradictions.append(
            _issue(
                "false_prior_reference_phrase",
                prior.model_dump(),
                {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None},
            )
        )
        return {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None}
    if _current_message_lacks_prior_reference_cue(message):
        contradictions.append(
            _issue(
                "false_prior_reference_without_reference_cue",
                prior.model_dump(),
                {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None},
            )
        )
        return {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None}
    if not _valid_evidence(prior.evidence_span, message):
        contradictions.append(
            _issue(
                "invalid_prior_reference_evidence",
                prior.model_dump(),
                {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None},
            )
        )
        return {"type": AnalyzerReferenceType.NONE.value, "topic_hint": None, "evidence_span": None}
    return prior.model_dump()


def _derive_objection_relation(message: str, normalized_objection: Dict[str, Any]) -> str:
    if normalized_objection.get("type") != ObjectionType.NONE.value:
        return normalized_objection.get("relation") or ObjectionRelation.NEW.value
    text = _simple_normalize(message)
    if _contains_any(
        text,
        [
            "ok eso tiene sentido",
            "eso tiene sentido",
            "queda claro",
            "me queda claro",
            "ya entendi",
            "me sirve",
            "suena bien",
            "me convenciste",
            "perfecto",
            "ya no es tanto problema",
            "no es tanto problema",
            "con eso ya no es tanto problema",
            "ya no me preocupa",
            "con eso me quedo tranquilo",
        ],
    ):
        return ObjectionRelation.RESOLVED.value
    if _contains_any(
        text,
        [
            "lo que me preocupa",
            "lo que me pesa",
            "mi duda es",
            "mi bloqueo",
            "pago inicial",
            "vale la pena",
            "recuperar tiempo",
            "ahorrar tiempo",
        ],
    ):
        return ObjectionRelation.CLARIFIED.value
    if _contains_any(text, ["demuestr", "muestrame", "prueba", "evidencia", "caso real"]):
        return ObjectionRelation.CONTINUATION.value
    return ObjectionRelation.NONE.value


def _derive_explicit_start(
    observation: AnalyzerTurnObservation,
    message: str,
    contradictions: List[NormalizationIssue],
) -> bool:
    readiness = observation.purchase_readiness
    if readiness.level != BuyingSignal.EXPLICIT_START.value:
        return False
    if _valid_evidence(readiness.evidence_span, message):
        return True
    contradictions.append(
        _issue(
            "explicit_start_without_valid_evidence",
            readiness.model_dump(),
            {"explicit_start_intent": False},
        )
    )
    return False


def _derive_post_purchase(
    observation: AnalyzerTurnObservation,
    message: str,
    contradictions: List[NormalizationIssue],
) -> bool:
    signal = observation.post_purchase_signal
    if not signal.detected:
        return False
    if _valid_evidence(signal.evidence_span, message):
        return True
    contradictions.append(
        _issue(
            "post_purchase_without_valid_evidence",
            signal.model_dump(),
            {"is_post_purchase": False},
        )
    )
    return False


def _derive_action_requirement(valid_actions: Sequence[Any], valid_capabilities: Sequence[Any]) -> str:
    if valid_actions:
        return ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
    if valid_capabilities:
        return ActionRequirement.ANSWERS_ONLY.value
    return ActionRequirement.UNKNOWN.value


def _normalize_requested_product(
    observation: AnalyzerTurnObservation,
    message: str,
    contradictions: List[NormalizationIssue],
) -> str:
    requested = observation.requested_product
    if requested.product == RequestedProduct.NONE.value:
        return RequestedProduct.NONE.value
    if not _valid_evidence(requested.evidence_span, message):
        contradictions.append(
            _issue(
                "invalid_requested_product_evidence",
                requested.model_dump(),
                {"requested_product": RequestedProduct.NONE.value},
            )
        )
        return RequestedProduct.NONE.value
    return requested.product


def _derive_recommended_product(action_requirement: str) -> Optional[str]:
    if action_requirement == ActionRequirement.ANSWERS_ONLY.value:
        return ProductFit.MOVIA_CAPTURA.value
    if action_requirement == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
        return ProductFit.MOVIA_HIBRIDO.value
    return None


def _derive_selected_product(
    requested_product: str,
    recommended_product: Optional[str],
    explicit_start: bool,
    purchase_evidence: Optional[str],
    message: str,
    contradictions: List[NormalizationIssue],
) -> Optional[str]:
    if requested_product in UNAVAILABLE_PRODUCTS:
        contradictions.append(
            _issue(
                "unavailable_product_not_selected",
                {"requested_product": requested_product},
                {"selected_product": None},
            )
        )
        return None
    if requested_product not in AVAILABLE_PRODUCTS:
        return None
    if recommended_product and requested_product != recommended_product:
        return None
    if not explicit_start:
        return None
    if not _product_selection_commitment(requested_product, purchase_evidence, message):
        return None
    return requested_product


def _derive_product_preference_mismatch(
    requested_product: str,
    recommended_product: Optional[str],
) -> bool:
    return (
        requested_product not in {None, RequestedProduct.NONE.value, RequestedProduct.UNKNOWN_PRODUCT.value}
        and recommended_product is not None
        and requested_product != recommended_product
    )


def _known_slot_values(
    *,
    observation: AnalyzerTurnObservation,
    lead_profile: Dict[str, Any],
    action_requirement: str,
) -> Dict[str, Any]:
    facts = observation.extracted_facts
    return {
        "business_type": facts.business_type or lead_profile.get("business_type"),
        "main_channel": facts.main_channel or lead_profile.get("main_channel"),
        "pain_or_goal": facts.pain_or_goal or lead_profile.get("pain"),
        "action_requirement": action_requirement
        if action_requirement != ActionRequirement.UNKNOWN.value
        else (lead_profile.get("profile_data") or {}).get("action_requirement"),
    }


def _compare_sets(parser_values: Set[str], llm_values: Set[str]) -> ParserLLMComparison:
    agreement = sorted(parser_values & llm_values)
    parser_only = sorted(parser_values - llm_values)
    llm_only = sorted(llm_values - parser_values)
    return ParserLLMComparison(
        agreement=agreement,
        parser_only=parser_only,
        llm_only=llm_only,
        conflict=bool(parser_only or llm_only),
    )


def _candidate_types(shadow_parser: Dict[str, Any], key: str) -> Set[str]:
    return {
        str(candidate.get("type"))
        for candidate in shadow_parser.get(key) or []
        if candidate.get("type")
    }


def _valid_evidence(evidence_span: Optional[str], message: str) -> bool:
    return bool(evidence_span and evidence_span_in_message(evidence_span, message))


def _valid_future_agent_action(action: Any, message: str) -> bool:
    if not _valid_evidence(action.evidence_span, message):
        return False
    action_type = str(action.type)
    evidence = _simple_normalize(str(action.evidence_span or ""))
    text = _simple_normalize(message)
    if not _has_future_agent_context(text):
        return False
    ontology_cues = _action_ontology_cues().get(action_type, [])
    if ontology_cues and not any(cue in evidence or cue in text for cue in ontology_cues):
        return False
    if action_type == RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION.value:
        return _contains_any(text, ["sistema", "crm", "panel", "base", "extern", "erp"])
    return True


def _valid_future_agent_capability(capability: Any, message: str) -> bool:
    if not _valid_evidence(capability.evidence_span, message):
        return False
    capability_type = str(capability.type)
    evidence = _simple_normalize(str(capability.evidence_span or ""))
    text = _simple_normalize(message)
    if not _has_future_agent_context(text):
        return False
    ontology_cues = _capability_ontology_cues().get(capability_type, [])
    if ontology_cues and not any(cue in evidence or cue in text for cue in ontology_cues):
        return False
    return True


def _has_future_agent_context(text: str) -> bool:
    product_context_terms = [
        "movia captura",
        "movia hibrido",
        "movia híbrido",
        "captura",
        "hibrido",
        "híbrido",
    ]
    if _contains_any(text, product_context_terms) and _contains_any(
        text, [" para ", " puede ", " podria ", "podria ", " podría ", "podría "]
    ):
        return True
    return _contains_any(
        text,
        [
            "que el agente",
            "quiero que",
            "necesito que",
            "busco que",
            "quiero que el agente",
            "necesito que el agente",
            "busco que el agente",
            "mi agente",
            "el bot",
            "que movia",
            "quiero movia para",
            "necesito un agente",
            "cuando lo compre",
            "despues de comprar",
            "despues de contratar",
            "para mis clientes",
            "solo que",
            "solamente que",
            "entonces solo",
            "mejor solo",
            "por ahora solo",
        ],
    )


def _action_ontology_cues() -> Dict[str, List[str]]:
    return {
        RequestedAgentAction.SCHEDULE_APPOINTMENT.value: ["agend", "cita", "reserv"],
        RequestedAgentAction.GENERATE_QUOTE.value: ["cotiz", "cotic", "quote", "presupuest"],
        RequestedAgentAction.CREATE_ORDER.value: ["pedido", "orden", "crear orden"],
        RequestedAgentAction.READ_EXTERNAL_SYSTEM.value: ["leer", "consult", "sistema", "crm", "panel", "base"],
        RequestedAgentAction.WRITE_EXTERNAL_SYSTEM.value: ["registr", "escrib", "guardar", "sistema", "crm", "panel", "base"],
        RequestedAgentAction.UPDATE_EXTERNAL_RECORD.value: ["actualiz", "modific", "sistema", "crm", "panel", "base"],
        RequestedAgentAction.SEND_REMINDER.value: ["recordatorio", "recordar"],
        RequestedAgentAction.FOLLOW_UP_LEAD.value: ["seguimiento", "follow up"],
        RequestedAgentAction.SEND_NOTIFICATION.value: ["notific", "avis"],
        RequestedAgentAction.TAKE_PAYMENT.value: ["cobr", "pago", "tarjeta"],
        RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION.value: ["sistema", "crm", "panel", "base", "extern", "erp"],
    }


def _capability_ontology_cues() -> Dict[str, List[str]]:
    return {
        "answer_customer_questions": ["respond", "contest", "duda", "pregunta"],
        "provide_prices": ["precio", "precios", "cotizacion", "cotización"],
        "provide_catalog_information": ["catalog", "producto", "servicio"],
        "capture_lead_data": ["captur", "datos", "lead"],
        "qualify_leads": ["calific", "filtr", "lead"],
        "redirect_to_human": ["humano", "persona", "asesor"],
        "understand_audio": ["audio", "audios", "voz"],
        "understand_images": ["imagen", "imagenes", "foto", "fotos"],
        "explain_business_process": ["explic", "proceso", "funciona"],
        "collect_order_information": ["pedido", "orden", "datos"],
        "persuade_leads": ["persuad", "convenc"],
        "handle_sales_objections": ["objecion", "objeciones"],
        "recommend_products_commercially": ["recomend", "producto"],
        "close_sale": ["cerrar venta", "cierre venta", "venda", "venta"],
    }


def _product_selection_commitment(
    requested_product: str,
    purchase_evidence: Optional[str],
    message: str,
) -> bool:
    text = _simple_normalize(" ".join([message, purchase_evidence or ""]))
    product_cues = {
        RequestedProduct.MOVIA_CAPTURA.value: ["captura"],
        RequestedProduct.MOVIA_HIBRIDO.value: ["hibrido", "híbrido"],
    }.get(requested_product, [])
    if not any(cue in text for cue in product_cues):
        return False
    return _contains_any(
        text,
        [
            "empezar con",
            "iniciar con",
            "contratar",
            "lo quiero",
            "quiero empezar",
            "quiero iniciar",
            "pagar",
            "pasame el link",
            "pásame el link",
        ],
    )


def _false_prior_reference_phrase(value: str) -> bool:
    normalized = _simple_normalize(value)
    return any(
        phrase in normalized
        for phrase in [
            "antes de pagar",
            "antes de contratar",
            "antes de empezar",
            "antes de iniciar",
        ]
    )


def _current_message_lacks_prior_reference_cue(value: str) -> bool:
    normalized = _simple_normalize(value)
    cues = [
        "lo de",
        "lo que",
        "eso que",
        "eso del",
        "esa parte",
        "antes dijiste",
        "dijiste",
        "te dije",
        "como te dije",
        "me dijiste",
        "tu dijiste",
        "mencionaste",
        "recomendaste",
        "me recomend",
        "era captura",
        "era hibrido",
        "era híbrido",
        "cual era",
        "cuál era",
        "retom",
        "veníamos",
        "veniamos",
        "habíamos",
        "habiamos",
        "el plan que",
        "del que hablamos",
    ]
    return not any(cue in normalized for cue in cues)


def _legacy_reference_type(reference_type: Optional[str]) -> str:
    mapping = {
        AnalyzerReferenceType.NONE.value: ReferenceType.NONE.value,
        AnalyzerReferenceType.IMPLICIT_PRIOR_REFERENCE.value: ReferenceType.TEMPORAL_REFERENCE.value,
        AnalyzerReferenceType.TOPIC_REFERENCE.value: ReferenceType.TOPIC_REFERENCE.value,
        AnalyzerReferenceType.ENTITY_REFERENCE.value: ReferenceType.ENTITY_REFERENCE.value,
        AnalyzerReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value: ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value,
    }
    return mapping.get(reference_type or AnalyzerReferenceType.NONE.value, ReferenceType.NONE.value)


def _issue(code: str, original: Dict[str, Any], normalized: Dict[str, Any]) -> NormalizationIssue:
    return NormalizationIssue(
        contradiction_code=code,
        original_values=original,
        normalized_values=normalized,
    )


def _simple_normalize(value: str) -> str:
    value = value.lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)
