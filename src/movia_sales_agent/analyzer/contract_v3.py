from __future__ import annotations

import copy
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    Intent,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionType,
    ProductFit,
    ReferenceType,
    Topic,
)
from movia_sales_agent.models.schemas import AnalysisConfidence, LeadUpdates, TurnAnalysis


ANALYZER_CONTRACT_VERSION = "3.2"


class AnalyzerEnum(str, Enum):
    @classmethod
    def values(cls) -> List[str]:
        return [item.value for item in cls]


class SemanticStrength(AnalyzerEnum):
    EXPLICIT = "explicit"
    UNAMBIGUOUS_IMPLICIT = "unambiguous_implicit"


class RequirementUpdateIntent(AnalyzerEnum):
    NO_CHANGE = "no_change"
    MERGE = "merge"
    REPLACE = "replace"


class ObservedBusinessProblem(AnalyzerEnum):
    HIGH_MESSAGE_VOLUME = "high_message_volume"
    SLOW_RESPONSE = "slow_response"
    LEAD_DROP_OFF = "lead_drop_off"
    REPETITIVE_QUESTIONS = "repetitive_questions"
    MANUAL_DATA_CAPTURE = "manual_data_capture"
    MANUAL_FOLLOW_UP = "manual_follow_up"
    MISSED_LEADS = "missed_leads"
    DISORGANIZED_INFORMATION = "disorganized_information"
    MANUAL_QUOTING = "manual_quoting"
    MANUAL_SCHEDULING = "manual_scheduling"
    MANUAL_ORDER_PROCESSING = "manual_order_processing"
    SUPPORT_BOTTLENECK = "support_bottleneck"
    UNKNOWN_BUSINESS_PROBLEM = "unknown_business_problem"


class RequestedAgentCapability(AnalyzerEnum):
    ANSWER_CUSTOMER_QUESTIONS = "answer_customer_questions"
    PROVIDE_PRICES = "provide_prices"
    PROVIDE_CATALOG_INFORMATION = "provide_catalog_information"
    CAPTURE_LEAD_DATA = "capture_lead_data"
    QUALIFY_LEADS = "qualify_leads"
    REDIRECT_TO_HUMAN = "redirect_to_human"
    UNDERSTAND_AUDIO = "understand_audio"
    UNDERSTAND_IMAGES = "understand_images"
    EXPLAIN_BUSINESS_PROCESS = "explain_business_process"
    COLLECT_ORDER_INFORMATION = "collect_order_information"
    PERSUADE_LEADS = "persuade_leads"
    HANDLE_SALES_OBJECTIONS = "handle_sales_objections"
    RECOMMEND_PRODUCTS_COMMERCIALLY = "recommend_products_commercially"
    CLOSE_SALE = "close_sale"


class RequestedAgentAction(AnalyzerEnum):
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    GENERATE_QUOTE = "generate_quote"
    CREATE_ORDER = "create_order"
    READ_EXTERNAL_SYSTEM = "read_external_system"
    WRITE_EXTERNAL_SYSTEM = "write_external_system"
    UPDATE_EXTERNAL_RECORD = "update_external_record"
    SEND_REMINDER = "send_reminder"
    FOLLOW_UP_LEAD = "follow_up_lead"
    SEND_NOTIFICATION = "send_notification"
    TAKE_PAYMENT = "take_payment"
    UNKNOWN_EXTERNAL_ACTION = "unknown_external_action"


INFORMATIONAL_AGENT_CAPABILITIES = {
    RequestedAgentCapability.ANSWER_CUSTOMER_QUESTIONS.value,
    RequestedAgentCapability.PROVIDE_PRICES.value,
    RequestedAgentCapability.PROVIDE_CATALOG_INFORMATION.value,
    RequestedAgentCapability.CAPTURE_LEAD_DATA.value,
    RequestedAgentCapability.QUALIFY_LEADS.value,
    RequestedAgentCapability.REDIRECT_TO_HUMAN.value,
    RequestedAgentCapability.UNDERSTAND_AUDIO.value,
    RequestedAgentCapability.UNDERSTAND_IMAGES.value,
    RequestedAgentCapability.EXPLAIN_BUSINESS_PROCESS.value,
    RequestedAgentCapability.COLLECT_ORDER_INFORMATION.value,
}

SALES_AGENT_CAPABILITIES = {
    RequestedAgentCapability.PERSUADE_LEADS.value,
    RequestedAgentCapability.HANDLE_SALES_OBJECTIONS.value,
    RequestedAgentCapability.RECOMMEND_PRODUCTS_COMMERCIALLY.value,
    RequestedAgentCapability.CLOSE_SALE.value,
}


class RequestedProduct(AnalyzerEnum):
    NONE = "none"
    MOVIA_CAPTURA = "movia_captura"
    MOVIA_HIBRIDO = "movia_hibrido"
    MOVIA_VENTAS = "movia_ventas"
    MOVIA_PRO_COMERCIAL = "movia_pro_comercial"
    UNKNOWN_PRODUCT = "unknown_product"


class ProductReferenceRole(AnalyzerEnum):
    QUESTION_SUBJECT = "question_subject"
    COMPARISON_ALTERNATIVE = "comparison_alternative"
    PREFERRED = "preferred"
    COMMITTED = "committed"
    MENTIONED = "mentioned"


class AnalyzerActiveObjectionRelation(AnalyzerEnum):
    NONE = "none"
    RESOLVED = "resolved"
    CLARIFIED = "clarified"
    REAFFIRMED = "reaffirmed"
    CONTINUATION = "continuation"
    UNRELATED = "unrelated"


class AnalyzerReferenceType(AnalyzerEnum):
    NONE = "none"
    IMPLICIT_PRIOR_REFERENCE = "implicit_prior_reference"
    TOPIC_REFERENCE = "topic_reference"
    ENTITY_REFERENCE = "entity_reference"
    ASSISTANT_COMMITMENT_REFERENCE = "assistant_commitment_reference"


class AnalyzerExtractedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_type: Optional[str] = None
    main_channel: Optional[str] = None
    pain_or_goal: Optional[str] = None
    urgency: Optional[str] = None


class BusinessProblemObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: ObservedBusinessProblem
    evidence_span: str
    observation_strength: SemanticStrength = SemanticStrength.EXPLICIT

    @model_validator(mode="after")
    def require_evidence(self) -> "BusinessProblemObservation":
        if not (self.evidence_span or "").strip():
            raise ValueError("observed business problems require evidence_span")
        return self


class AgentCapabilityObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: RequestedAgentCapability
    evidence_span: str
    requirement_strength: SemanticStrength = SemanticStrength.EXPLICIT

    @model_validator(mode="after")
    def require_evidence(self) -> "AgentCapabilityObservation":
        if not (self.evidence_span or "").strip():
            raise ValueError("requested agent capabilities require evidence_span")
        return self


class AgentActionObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: RequestedAgentAction
    evidence_span: str
    requirement_strength: SemanticStrength = SemanticStrength.EXPLICIT

    @model_validator(mode="after")
    def require_evidence(self) -> "AgentActionObservation":
        if not self.evidence_span.strip():
            raise ValueError("requested agent actions require evidence_span")
        return self


class DeclaredExternalActionCountObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    value: int = Field(ge=1, le=99)
    evidence_span: str

    @model_validator(mode="after")
    def require_evidence(self) -> "DeclaredExternalActionCountObservation":
        if not (self.evidence_span or "").strip():
            raise ValueError("declared external action count requires evidence_span")
        return self


class ProductReferenceObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    product: RequestedProduct
    evidence_span: str
    reference_role: ProductReferenceRole = ProductReferenceRole.MENTIONED

    @model_validator(mode="after")
    def require_product_evidence(self) -> "ProductReferenceObservation":
        if self.product == RequestedProduct.NONE.value:
            raise ValueError("product references cannot use none")
        if not (self.evidence_span or "").strip():
            raise ValueError("product reference requires evidence_span")
        return self


class ObjectionCandidateObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: ObjectionType = ObjectionType.NONE
    strength: ObjectionStrength = ObjectionStrength.NONE
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def validate_objection_shape(self) -> "ObjectionCandidateObservation":
        if self.type == ObjectionType.NONE.value:
            if self.strength != ObjectionStrength.NONE.value:
                raise ValueError("none objection must have none strength")
            if self.evidence_span:
                raise ValueError("none objection cannot include evidence_span")
            return self
        if not (self.evidence_span or "").strip():
            raise ValueError("objection candidate requires evidence_span")
        if self.strength == ObjectionStrength.NONE.value:
            raise ValueError("objection candidate requires non-none strength")
        return self


class ActiveObjectionRelationObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    relation: AnalyzerActiveObjectionRelation = AnalyzerActiveObjectionRelation.NONE
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def validate_relation_shape(self) -> "ActiveObjectionRelationObservation":
        if self.relation == AnalyzerActiveObjectionRelation.NONE.value:
            if self.evidence_span:
                raise ValueError("none active-objection relation cannot include evidence_span")
            return self
        if not (self.evidence_span or "").strip():
            raise ValueError("active-objection relation requires evidence_span")
        return self


class PurchaseReadinessObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    level: BuyingSignal = BuyingSignal.NONE
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def require_readiness_evidence(self) -> "PurchaseReadinessObservation":
        if self.level in {BuyingSignal.HIGH.value, BuyingSignal.EXPLICIT_START.value} and not (
            self.evidence_span or ""
        ).strip():
            raise ValueError("high or explicit purchase readiness requires evidence_span")
        return self


class PriorReferenceObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    type: AnalyzerReferenceType = AnalyzerReferenceType.NONE
    topic_hint: Optional[str] = None
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def require_prior_reference_evidence(self) -> "PriorReferenceObservation":
        if self.type != AnalyzerReferenceType.NONE.value and not (self.evidence_span or "").strip():
            raise ValueError("prior reference requires evidence_span")
        return self


class PostPurchaseSignalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected: bool = False
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def require_post_purchase_evidence(self) -> "PostPurchaseSignalObservation":
        if self.detected and not (self.evidence_span or "").strip():
            raise ValueError("post-purchase signal requires evidence_span")
        return self


class AnalyzerObservationConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: float = Field(default=0.0, ge=0.0, le=1.0)
    facts: float = Field(default=0.0, ge=0.0, le=1.0)
    capabilities: float = Field(default=0.0, ge=0.0, le=1.0)
    actions: float = Field(default=0.0, ge=0.0, le=1.0)
    objection: float = Field(default=0.0, ge=0.0, le=1.0)
    purchase_readiness: float = Field(default=0.0, ge=0.0, le=1.0)
    prior_reference: float = Field(default=0.0, ge=0.0, le=1.0)
    post_purchase: float = Field(default=0.0, ge=0.0, le=1.0)
    requirement_update: float = Field(default=0.0, ge=0.0, le=1.0)


class AnalyzerTurnObservation(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    analyzer_contract_version: str = ANALYZER_CONTRACT_VERSION
    primary_intent: Intent = Intent.UNKNOWN
    secondary_intents: List[Intent] = Field(default_factory=list)
    extracted_facts: AnalyzerExtractedFacts = Field(default_factory=AnalyzerExtractedFacts)
    observed_business_problems: List[BusinessProblemObservation] = Field(default_factory=list)
    requested_agent_capabilities: List[AgentCapabilityObservation] = Field(default_factory=list)
    requested_agent_actions: List[AgentActionObservation] = Field(default_factory=list)
    declared_external_action_count: Optional[DeclaredExternalActionCountObservation] = None
    requirement_update_intent: RequirementUpdateIntent = RequirementUpdateIntent.NO_CHANGE
    product_references: List[ProductReferenceObservation] = Field(default_factory=list)
    objection_candidate: ObjectionCandidateObservation = Field(default_factory=ObjectionCandidateObservation)
    active_objection_relation: ActiveObjectionRelationObservation = Field(
        default_factory=ActiveObjectionRelationObservation
    )
    purchase_readiness: PurchaseReadinessObservation = Field(default_factory=PurchaseReadinessObservation)
    prior_reference: PriorReferenceObservation = Field(default_factory=PriorReferenceObservation)
    post_purchase_signal: PostPurchaseSignalObservation = Field(default_factory=PostPurchaseSignalObservation)
    confidence: AnalyzerObservationConfidence = Field(default_factory=AnalyzerObservationConfidence)

    @model_validator(mode="after")
    def validate_version(self) -> "AnalyzerTurnObservation":
        if self.analyzer_contract_version != ANALYZER_CONTRACT_VERSION:
            raise ValueError(f"analyzer_contract_version must be {ANALYZER_CONTRACT_VERSION}")
        if self.product_references:
            deduped = _dedupe_product_references(
                [reference.model_dump() for reference in self.product_references]
            )
            self.product_references = [
                ProductReferenceObservation.model_validate(reference)
                for reference in deduped
            ]
            roles = {reference.reference_role for reference in self.product_references}
            if (
                len(self.product_references) > 1
                and ProductReferenceRole.QUESTION_SUBJECT.value in roles
                and ProductReferenceRole.COMPARISON_ALTERNATIVE.value in roles
                and self.primary_intent == Intent.PRODUCT_SCOPE_QUESTION.value
            ):
                self.primary_intent = Intent.COMPARISON_QUESTION.value
        if (
            self.primary_intent == Intent.EXPLICIT_START_REQUEST.value
            and self.purchase_readiness.level != BuyingSignal.EXPLICIT_START.value
        ):
            self.primary_intent = (
                Intent.PRODUCT_SCOPE_QUESTION.value
                if self.requested_agent_actions or self.requested_agent_capabilities
                else Intent.GENERAL_INFO.value
            )
        if self.requirement_update_intent == RequirementUpdateIntent.NO_CHANGE.value:
            self.requested_agent_actions = []
            self.requested_agent_capabilities = []
            self.declared_external_action_count = None
        return self


def analyzer_json_schema() -> Dict[str, Any]:
    schema = AnalyzerTurnObservation.model_json_schema()
    _strip_json_schema_defaults(schema)
    _strip_json_schema_titles(schema)
    _require_all_object_properties(schema)
    return schema

def validate_analyzer_observation(payload: Dict[str, Any], message: str) -> AnalyzerTurnObservation:
    observation = AnalyzerTurnObservation.model_validate(
        sanitize_analyzer_observation_payload(payload, message)
    )
    missing = [
        path
        for path, evidence in _evidence_paths(observation)
        if evidence and not evidence_span_in_message(evidence, message)
    ]
    if missing:
        raise ValueError(f"evidence_span not found in message: {', '.join(missing)}")
    return observation


def sanitize_analyzer_observation_payload(payload: Dict[str, Any], message: str) -> Dict[str, Any]:
    """Repair recoverable OpenAI payload shape issues before strict validation."""

    cleaned = copy.deepcopy(payload)
    cleaned["analyzer_contract_version"] = ANALYZER_CONTRACT_VERSION

    business_problems = cleaned.get("observed_business_problems")
    if isinstance(business_problems, list):
        cleaned["observed_business_problems"] = _sanitize_business_problems_payload(
            business_problems, message
        )

    capabilities = cleaned.get("requested_agent_capabilities")
    if isinstance(capabilities, list):
        cleaned["requested_agent_capabilities"] = _sanitize_requested_capabilities_payload(
            capabilities, message
        )

    actions = cleaned.get("requested_agent_actions")
    if isinstance(actions, list):
        cleaned["requested_agent_actions"] = _sanitize_requested_actions_payload(actions, message)

    declared_count = cleaned.get("declared_external_action_count")
    if isinstance(declared_count, dict):
        cleaned["declared_external_action_count"] = _sanitize_declared_action_count_payload(
            declared_count, message
        )

    product_references = cleaned.get("product_references")
    if isinstance(product_references, list):
        cleaned["product_references"] = _sanitize_product_references_payload(
            product_references, message
        )

    objection = cleaned.get("objection_candidate")
    if isinstance(objection, dict):
        _sanitize_objection_payload(objection, message)

    active_relation = cleaned.get("active_objection_relation")
    if isinstance(active_relation, dict):
        _sanitize_active_objection_relation_payload(active_relation, message)

    readiness = cleaned.get("purchase_readiness")
    if isinstance(readiness, dict):
        _sanitize_purchase_readiness_payload(readiness, message)

    prior = cleaned.get("prior_reference")
    if isinstance(prior, dict):
        _sanitize_prior_reference_payload(prior, message)

    post_purchase = cleaned.get("post_purchase_signal")
    if isinstance(post_purchase, dict):
        _sanitize_post_purchase_payload(post_purchase, message)

    return cleaned


def evidence_span_in_message(evidence_span: str, message: str) -> bool:
    evidence = _normalize_for_evidence(evidence_span)
    text = _normalize_for_evidence(message)
    return bool(evidence) and evidence in text


def legacy_requested_product(observation: AnalyzerTurnObservation) -> str:
    """Return the transitional singular alias only for one unambiguous product."""

    products = _dedupe([str(item.product) for item in observation.product_references])
    return products[0] if len(products) == 1 else RequestedProduct.NONE.value


def observation_to_turn_analysis(observation: AnalyzerTurnObservation, message: str) -> TurnAnalysis:
    facts = observation.extracted_facts
    objection = observation.objection_candidate
    readiness = observation.purchase_readiness
    prior = observation.prior_reference
    post_purchase = observation.post_purchase_signal

    topics = _topics_from_observation(observation)
    profile_data = _temporary_profile_aliases(observation)
    lead_updates = LeadUpdates(
        business_type=facts.business_type,
        main_channel=facts.main_channel,
        pain=facts.pain_or_goal,
        urgency=facts.urgency,
        buying_signal=None if readiness.level == BuyingSignal.NONE.value else readiness.level,
        profile_data=profile_data,
    )
    return TurnAnalysis(
        primary_intent=observation.primary_intent,
        secondary_intents=observation.secondary_intents,
        topics=topics,
        skeptical_tone=False,
        has_objection=objection.type != ObjectionType.NONE.value,
        objection_type=objection.type,
        objection_strength=objection.strength,
        objection_relation=_legacy_objection_relation(observation),
        business_type=facts.business_type,
        main_channel=facts.main_channel,
        pain=facts.pain_or_goal,
        urgency=facts.urgency,
        buying_signal=readiness.level,
        explicit_start_intent=readiness.level == BuyingSignal.EXPLICIT_START.value,
        is_post_purchase=post_purchase.detected,
        references_prior_message=prior.type != AnalyzerReferenceType.NONE.value,
        reference_type=_legacy_reference_type(prior.type),
        reference_query=prior.topic_hint or prior.evidence_span,
        referenced_topics=_reference_topics(prior, topics),
        explicit_turn_number=None,
        reference_confidence=observation.confidence.prior_reference,
        confidence=AnalysisConfidence(
            intent=observation.confidence.intent,
            objection=observation.confidence.objection,
            objection_relation=observation.confidence.objection,
            prior_reference=observation.confidence.prior_reference,
            start_intent=observation.confidence.purchase_readiness,
        ),
        lead_updates=lead_updates,
    )


def legacy_analysis_to_observation(analysis: TurnAnalysis, message: str) -> AnalyzerTurnObservation:
    objection_evidence = message if analysis.has_objection else None
    prior_evidence = message if analysis.references_prior_message else None
    post_purchase_evidence = message if analysis.is_post_purchase else None
    requested_actions = _actions_from_legacy_profile_data(analysis, message)
    requested_capabilities = _capabilities_from_legacy_profile_data(analysis, message)
    declared_action_count = _declared_external_action_count_from_message(message)
    objection_type = analysis.objection_type if analysis.has_objection else ObjectionType.NONE.value
    objection_strength = (
        analysis.objection_strength if analysis.has_objection else ObjectionStrength.NONE.value
    )
    active_relation = (
        analysis.objection_relation
        if analysis.objection_relation
        in {
            ObjectionRelation.RESOLVED.value,
            ObjectionRelation.CLARIFIED.value,
            ObjectionRelation.REAFFIRMED.value,
            ObjectionRelation.CONTINUATION.value,
            ObjectionRelation.UNRELATED.value,
        }
        else ObjectionRelation.NONE.value
    )
    return AnalyzerTurnObservation(
        primary_intent=analysis.primary_intent,
        secondary_intents=analysis.secondary_intents,
        extracted_facts=AnalyzerExtractedFacts(
            business_type=analysis.business_type,
            main_channel=analysis.main_channel,
            pain_or_goal=analysis.pain,
            urgency=analysis.urgency,
        ),
        observed_business_problems=_observed_business_problems_from_legacy_analysis(analysis, message),
        requested_agent_capabilities=requested_capabilities,
        requested_agent_actions=requested_actions,
        declared_external_action_count=declared_action_count,
        requirement_update_intent=_requirement_update_intent_from_legacy_analysis(
            analysis,
            message,
            requested_capabilities,
            requested_actions,
            declared_action_count,
        ),
        product_references=_product_references_from_message(message),
        objection_candidate=ObjectionCandidateObservation(
            type=objection_type,
            strength=objection_strength,
            evidence_span=objection_evidence,
        ),
        active_objection_relation=ActiveObjectionRelationObservation(
            relation=active_relation,
            evidence_span=message if active_relation != ObjectionRelation.NONE.value else None,
        ),
        purchase_readiness=PurchaseReadinessObservation(
            level=analysis.buying_signal,
            evidence_span=message
            if analysis.buying_signal in {BuyingSignal.HIGH.value, BuyingSignal.EXPLICIT_START.value}
            else None,
        ),
        prior_reference=PriorReferenceObservation(
            type=_analyzer_reference_type(analysis.reference_type) if analysis.references_prior_message else AnalyzerReferenceType.NONE.value,
            topic_hint=analysis.reference_query,
            evidence_span=prior_evidence,
        ),
        post_purchase_signal=PostPurchaseSignalObservation(
            detected=analysis.is_post_purchase,
            evidence_span=post_purchase_evidence,
        ),
        confidence=AnalyzerObservationConfidence(
            intent=analysis.confidence.intent,
            facts=0.75,
            capabilities=0.75,
            actions=0.75,
            objection=analysis.confidence.objection,
            purchase_readiness=analysis.confidence.start_intent,
            prior_reference=analysis.confidence.prior_reference,
            post_purchase=0.95 if analysis.is_post_purchase else 0.75,
            requirement_update=0.65,
        ),
    )


def analyzer_contract_document() -> Dict[str, Any]:
    return {
        "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
        "source_of_truth": "src/movia_sales_agent/analyzer/contract_v3.py",
        "responsibility": "LLM observes independent linguistic facts only; code derives dependent commercial fields.",
        "enums": {
            "observed_business_problems": ObservedBusinessProblem.values(),
            "semantic_strength": SemanticStrength.values(),
            "requested_agent_capabilities": RequestedAgentCapability.values(),
            "requested_agent_actions": RequestedAgentAction.values(),
            "requirement_update_intents": RequirementUpdateIntent.values(),
            "requested_products": RequestedProduct.values(),
            "product_reference_roles": ProductReferenceRole.values(),
            "prior_reference_types": AnalyzerReferenceType.values(),
            "purchase_readiness": BuyingSignal.values(),
            "objection_types": ObjectionType.values(),
            "objection_strengths": ObjectionStrength.values(),
            "active_objection_relations": AnalyzerActiveObjectionRelation.values(),
            "intents": Intent.values(),
        },
        "semantic_fields": [
            "observed_business_problems",
            "requested_agent_capabilities",
            "requested_agent_actions",
            "declared_external_action_count",
            "requirement_update_intent",
        ],
        "banned_llm_fields": [
            "has_objection",
            "references_prior_message",
            "explicit_turn_number",
            "explicit_start_intent",
            "action_requirement",
            "known_product_fit",
            "recommended_product",
            "sales_stage",
            "macro_action",
            "micro_action",
            "cta_type",
            "next_question",
            "next_question_key",
            "needs_rag",
        ],
        "shadow_parser": {
            "shadow_parser_may_observe": True,
            "shadow_parser_may_override": False,
            "shadow_parser_may_choose_product": False,
            "shadow_parser_may_choose_action": False,
        },
    }


def _evidence_paths(observation: AnalyzerTurnObservation) -> Iterable[Tuple[str, Optional[str]]]:
    for index, problem in enumerate(observation.observed_business_problems):
        yield f"observed_business_problems[{index}].evidence_span", problem.evidence_span
    for index, capability in enumerate(observation.requested_agent_capabilities):
        yield f"requested_agent_capabilities[{index}].evidence_span", capability.evidence_span
    for index, action in enumerate(observation.requested_agent_actions):
        yield f"requested_agent_actions[{index}].evidence_span", action.evidence_span
    if observation.declared_external_action_count:
        yield "declared_external_action_count.evidence_span", observation.declared_external_action_count.evidence_span
    for index, product in enumerate(observation.product_references):
        yield f"product_references[{index}].evidence_span", product.evidence_span
    if observation.objection_candidate.type != ObjectionType.NONE.value:
        yield "objection_candidate.evidence_span", observation.objection_candidate.evidence_span
    if observation.active_objection_relation.relation != AnalyzerActiveObjectionRelation.NONE.value:
        yield "active_objection_relation.evidence_span", observation.active_objection_relation.evidence_span
    if observation.purchase_readiness.level in {BuyingSignal.HIGH.value, BuyingSignal.EXPLICIT_START.value}:
        yield "purchase_readiness.evidence_span", observation.purchase_readiness.evidence_span
    if observation.prior_reference.type != AnalyzerReferenceType.NONE.value:
        yield "prior_reference.evidence_span", observation.prior_reference.evidence_span
    if observation.post_purchase_signal.detected:
        yield "post_purchase_signal.evidence_span", observation.post_purchase_signal.evidence_span


def _sanitize_product_references_payload(
    references: List[Any], message: str
) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        product = reference.get("product")
        role = reference.get("reference_role")
        if product not in RequestedProduct.values() or product == RequestedProduct.NONE.value:
            continue
        if role not in ProductReferenceRole.values():
            continue
        item = dict(reference)
        repaired = _product_reference_from_message(message, product, role)
        if not repaired:
            continue
        item["evidence_span"] = repaired.evidence_span
        sanitized.append(item)
    return _dedupe_product_references(sanitized)


def _sanitize_active_objection_relation_payload(payload: Dict[str, Any], message: str) -> None:
    relation = payload.get("relation") or AnalyzerActiveObjectionRelation.NONE.value
    if relation not in AnalyzerActiveObjectionRelation.values():
        payload["relation"] = AnalyzerActiveObjectionRelation.NONE.value
        payload["evidence_span"] = None
        return
    if relation == AnalyzerActiveObjectionRelation.NONE.value:
        payload["evidence_span"] = None
        return
    if not evidence_span_in_message(str(payload.get("evidence_span") or ""), message):
        payload["relation"] = AnalyzerActiveObjectionRelation.NONE.value
        payload["evidence_span"] = None


def _sanitize_business_problems_payload(
    problems: List[Any], message: str
) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for problem in problems:
        if not isinstance(problem, dict):
            continue
        problem_type = problem.get("type")
        if problem_type not in ObservedBusinessProblem.values():
            continue
        evidence_span = str(problem.get("evidence_span") or "")
        if evidence_span_in_message(evidence_span, message):
            sanitized.append(dict(problem))
            continue
        repaired = _first_matching_evidence(message, _business_problem_evidence_cues(problem_type))
        if repaired:
            repaired_problem = dict(problem)
            repaired_problem["evidence_span"] = repaired
            sanitized.append(repaired_problem)
    return sanitized


def _sanitize_requested_capabilities_payload(
    capabilities: List[Any], message: str
) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        capability_type = capability.get("type")
        if capability_type not in RequestedAgentCapability.values():
            continue
        evidence_span = str(capability.get("evidence_span") or "")
        if evidence_span_in_message(evidence_span, message):
            ontology_evidence = _first_matching_evidence(
                evidence_span, _capability_evidence_cues(capability_type)
            )
            if not ontology_evidence:
                continue
            if _is_full_message_span(evidence_span, message):
                repaired_capability = dict(capability)
                repaired_capability["evidence_span"] = ontology_evidence
                sanitized.append(repaired_capability)
                continue
            sanitized.append(dict(capability))
            continue
        repaired = _first_matching_evidence(message, _capability_evidence_cues(capability_type))
        if repaired:
            repaired_capability = dict(capability)
            repaired_capability["evidence_span"] = repaired
            sanitized.append(repaired_capability)
    return sanitized


def _sanitize_objection_payload(payload: Dict[str, Any], message: str) -> None:
    objection_type = payload.get("type") or ObjectionType.NONE.value
    if objection_type == ObjectionType.NONE.value:
        payload["strength"] = ObjectionStrength.NONE.value
        payload.pop("relation", None)
        payload["evidence_span"] = None
        return
    strength = payload.get("strength") or ObjectionStrength.NONE.value
    if (
        objection_type not in ObjectionType.values()
        or strength not in ObjectionStrength.values()
        or strength == ObjectionStrength.NONE.value
    ):
        payload["type"] = ObjectionType.NONE.value
        payload["strength"] = ObjectionStrength.NONE.value
        payload.pop("relation", None)
        payload["evidence_span"] = None
        return
    if evidence_span_in_message(str(payload.get("evidence_span") or ""), message):
        return
    repaired = _first_matching_evidence(message, _objection_evidence_cues(objection_type))
    if repaired:
        payload["evidence_span"] = repaired
        return
    payload["type"] = ObjectionType.NONE.value
    payload["strength"] = ObjectionStrength.NONE.value
    payload.pop("relation", None)
    payload["evidence_span"] = None


def _sanitize_purchase_readiness_payload(payload: Dict[str, Any], message: str) -> None:
    level = payload.get("level") or BuyingSignal.NONE.value
    if level not in {BuyingSignal.HIGH.value, BuyingSignal.EXPLICIT_START.value}:
        return
    if evidence_span_in_message(str(payload.get("evidence_span") or ""), message):
        return
    repaired = _first_matching_evidence(message, _purchase_readiness_cues(level))
    if repaired:
        payload["evidence_span"] = repaired
        return
    payload["level"] = BuyingSignal.NONE.value
    payload["evidence_span"] = None


def _sanitize_prior_reference_payload(payload: Dict[str, Any], message: str) -> None:
    reference_type = payload.get("type") or AnalyzerReferenceType.NONE.value
    if reference_type == AnalyzerReferenceType.NONE.value:
        payload["topic_hint"] = None
        payload["evidence_span"] = None
        return
    if evidence_span_in_message(str(payload.get("evidence_span") or ""), message):
        return
    repaired = _first_matching_evidence(message, _prior_reference_cues())
    if repaired:
        payload["evidence_span"] = repaired
        return
    payload["type"] = AnalyzerReferenceType.NONE.value
    payload["topic_hint"] = None
    payload["evidence_span"] = None


def _sanitize_post_purchase_payload(payload: Dict[str, Any], message: str) -> None:
    if not payload.get("detected"):
        payload["evidence_span"] = None
        return
    if evidence_span_in_message(str(payload.get("evidence_span") or ""), message):
        return
    repaired = _first_matching_evidence(
        message,
        ["ya pague", "ya pagué", "pague", "pagué", "ya hice el pago", "ya pagado"],
    )
    if repaired:
        payload["evidence_span"] = repaired
        return
    payload["detected"] = False
    payload["evidence_span"] = None


def _sanitize_declared_action_count_payload(
    payload: Dict[str, Any], message: str
) -> Optional[Dict[str, Any]]:
    value = payload.get("value")
    if not isinstance(value, int) or value < 1:
        return None
    evidence_span = str(payload.get("evidence_span") or "")
    if evidence_span_in_message(evidence_span, message):
        return payload
    repaired = _first_matching_evidence(message, _declared_action_count_cues(value))
    if repaired:
        payload["evidence_span"] = repaired
        return payload
    return None


def _sanitize_requested_actions_payload(actions: List[Any], message: str) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type not in RequestedAgentAction.values():
            continue
        evidence_span = str(action.get("evidence_span") or "")
        if evidence_span_in_message(evidence_span, message):
            ontology_evidence = _first_matching_evidence(
                evidence_span, _action_evidence_cues(action_type)
            )
            if not ontology_evidence:
                continue
            if _is_full_message_span(evidence_span, message):
                repaired_action = dict(action)
                repaired_action["evidence_span"] = ontology_evidence
                sanitized.append(repaired_action)
                continue
            sanitized.append(dict(action))
            continue
        repaired = _first_matching_evidence(message, _action_evidence_cues(action_type))
        if repaired:
            repaired_action = dict(action)
            repaired_action["evidence_span"] = repaired
            sanitized.append(repaired_action)
    return sanitized


def _action_evidence_cues(action_type: str) -> List[str]:
    cues = {
        RequestedAgentAction.SCHEDULE_APPOINTMENT.value: ["agendar", "agenda", "cita", "reservar"],
        RequestedAgentAction.GENERATE_QUOTE.value: ["cotice", "cotizar", "cotización", "cotizacion", "quote"],
        RequestedAgentAction.CREATE_ORDER.value: ["registrar", "registre", "pedido", "pedidos", "orden"],
        RequestedAgentAction.READ_EXTERNAL_SYSTEM.value: ["leer", "consultar", "sistema", "panel", "crm"],
        RequestedAgentAction.WRITE_EXTERNAL_SYSTEM.value: ["escribir", "registrar", "sistema", "panel", "crm"],
        RequestedAgentAction.UPDATE_EXTERNAL_RECORD.value: ["actualizar", "modificar", "sistema", "panel", "crm"],
        RequestedAgentAction.SEND_REMINDER.value: ["recordatorio", "recordar"],
        RequestedAgentAction.FOLLOW_UP_LEAD.value: ["seguimiento", "dar seguimiento"],
        RequestedAgentAction.SEND_NOTIFICATION.value: ["notificar", "notificación", "notificacion", "avisar"],
        RequestedAgentAction.TAKE_PAYMENT.value: [
            "cobrar",
            "cobre",
            "cobro",
            "cobros",
            "pago",
            "pagos",
            "pagar",
            "tarjeta",
            "anticipo",
            "anticipos",
        ],
        RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION.value: ["sistema", "panel", "crm", "base", "externo"],
    }
    return cues.get(action_type, [])


def _business_problem_evidence_cues(problem_type: str) -> List[str]:
    cues = {
        ObservedBusinessProblem.HIGH_MESSAGE_VOLUME.value: ["muchos mensajes", "muchos whatsapps", "muchos whatsapp"],
        ObservedBusinessProblem.SLOW_RESPONSE.value: ["nadie contesta rápido", "nadie contesta rapido", "no responden rápido", "no responden rapido"],
        ObservedBusinessProblem.LEAD_DROP_OFF.value: ["se pierden leads", "pierdo leads", "se enfria", "se enfría"],
        ObservedBusinessProblem.REPETITIVE_QUESTIONS.value: ["preguntan", "siempre preguntan", "mismas preguntas"],
        ObservedBusinessProblem.MANUAL_DATA_CAPTURE.value: ["registramos manualmente", "capturamos manualmente", "anotamos manualmente"],
        ObservedBusinessProblem.MANUAL_FOLLOW_UP.value: ["seguimiento manual", "dar seguimiento manual"],
        ObservedBusinessProblem.MISSED_LEADS.value: ["se nos van", "perdemos leads", "nadie contesta"],
        ObservedBusinessProblem.DISORGANIZED_INFORMATION.value: ["todo está desordenado", "información desordenada", "informacion desordenada"],
        ObservedBusinessProblem.MANUAL_QUOTING.value: ["cotizamos manualmente", "hacer cotizaciones manuales"],
        ObservedBusinessProblem.MANUAL_SCHEDULING.value: ["agenda todo manualmente", "agendamos manualmente"],
        ObservedBusinessProblem.MANUAL_ORDER_PROCESSING.value: ["registramos pedidos manualmente", "pedidos manualmente"],
        ObservedBusinessProblem.SUPPORT_BOTTLENECK.value: ["se satura soporte", "cuello de botella de soporte", "soporte se satura"],
        ObservedBusinessProblem.UNKNOWN_BUSINESS_PROBLEM.value: ["problema", "situación", "situacion"],
    }
    return cues.get(problem_type, [])


def _capability_evidence_cues(capability_type: str) -> List[str]:
    cues = {
        RequestedAgentCapability.ANSWER_CUSTOMER_QUESTIONS.value: [
            "responder",
            "responda",
            "contestar",
            "dudas",
            "preguntas",
        ],
        RequestedAgentCapability.PROVIDE_PRICES.value: [
            "dé precios",
            "de precios",
            "dar precios",
            "diga precios",
            "les diga precios",
        ],
        RequestedAgentCapability.PROVIDE_CATALOG_INFORMATION.value: [
            "dar información",
            "dar informacion",
            "información de productos",
            "informacion de productos",
            "explique catálogo",
            "explique catalogo",
            "catálogo",
            "catalogo",
        ],
        RequestedAgentCapability.CAPTURE_LEAD_DATA.value: [
            "capture datos",
            "capturar datos",
            "guardar datos",
            "tomar datos",
            "capture leads",
            "capturar leads",
        ],
        RequestedAgentCapability.QUALIFY_LEADS.value: ["califique leads", "filtre leads", "calificar leads"],
        RequestedAgentCapability.REDIRECT_TO_HUMAN.value: ["pase con una persona", "redirija a humano", "mande a humano"],
        RequestedAgentCapability.UNDERSTAND_AUDIO.value: ["escuche audios", "entienda audios", "audio"],
        RequestedAgentCapability.UNDERSTAND_IMAGES.value: ["entienda imágenes", "entienda imagenes", "imágenes", "imagenes"],
        RequestedAgentCapability.EXPLAIN_BUSINESS_PROCESS.value: ["explique el proceso", "explique cómo funciona", "explique como funciona"],
        RequestedAgentCapability.COLLECT_ORDER_INFORMATION.value: ["tome datos del pedido", "recoja información del pedido", "recoja informacion del pedido"],
        RequestedAgentCapability.PERSUADE_LEADS.value: ["persuada clientes", "convenza clientes", "convencer leads"],
        RequestedAgentCapability.HANDLE_SALES_OBJECTIONS.value: ["maneje objeciones", "resuelva objeciones", "responder objeciones"],
        RequestedAgentCapability.RECOMMEND_PRODUCTS_COMMERCIALLY.value: ["recomiende productos", "recomendar productos"],
        RequestedAgentCapability.CLOSE_SALE.value: ["cierre ventas", "cerrar ventas", "venda por mí", "venda por mi"],
    }
    return cues.get(capability_type, [])


def _declared_action_count_cues(count: int) -> List[str]:
    word = _count_to_spanish_word(count)
    cues = [str(count), f"{count} acciones", f"son {count} acciones", f"como {count} acciones"]
    if word:
        cues.extend([word, f"{word} acciones", f"son {word} acciones", f"como {word} acciones"])
    return cues


def _objection_evidence_cues(objection_type: str) -> List[str]:
    cues = {
        ObjectionType.PRICE_OBJECTION.value: ["caro", "precio", "cuesta", "presupuesto", "pagar"],
        ObjectionType.TRUST_OBJECTION.value: ["confío", "confio", "seguro", "dudo", "prueba"],
        ObjectionType.FEAR_WRONG_ANSWERS.value: ["responda mal", "equivoque", "incorrecto"],
        ObjectionType.ALREADY_HAVE_PERSON.value: ["ya tengo", "alguien", "persona", "equipo"],
        ObjectionType.ALREADY_USE_WHATSAPP_BUSINESS.value: ["whatsapp business", "ya uso whatsapp"],
        ObjectionType.NEED_TO_THINK.value: ["pensarlo", "revisarlo", "lo veo", "luego"],
        ObjectionType.WANTS_FREE_TRIAL.value: ["prueba gratis", "gratis", "trial"],
        ObjectionType.COMPETITOR_COMPARISON.value: ["manychat", "competidor", "otro"],
        ObjectionType.NOT_SURE_IF_NEEDED.value: ["sirve", "funciona", "para mi", "para mí"],
        ObjectionType.SCOPE_OBJECTION.value: ["puede hacer", "alcance", "incluye"],
        ObjectionType.CHANNEL_CONNECTION_CONCERN.value: ["instagram", "facebook", "canal", "conectar"],
        ObjectionType.SUPPORT_CONCERN.value: ["soporte", "ayuda", "acompañan", "acompanan"],
    }
    return cues.get(objection_type, [])


def _purchase_readiness_cues(level: str) -> List[str]:
    if level == BuyingSignal.EXPLICIT_START.value:
        return [
            "pásame el link",
            "pasame el link",
            "quiero empezar",
            "quiero iniciar",
            "quiero contratar",
            "quiero pagar",
            "donde pago",
            "dónde pago",
            "vamos a empezar",
            "link",
        ]
    return ["me interesa", "suena bien", "quiero", "vamos", "me sirve"]


def _prior_reference_cues() -> List[str]:
    return [
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


def _first_matching_evidence(message: str, cues: List[str]) -> Optional[str]:
    for cue in cues:
        if evidence_span_in_message(cue, message):
            return cue
    return None


def _normalize_for_evidence(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^\w\s%]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _require_all_object_properties(node: Any) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties.keys())
        for value in node.values():
            _require_all_object_properties(value)
    elif isinstance(node, list):
        for item in node:
            _require_all_object_properties(item)


def _strip_json_schema_defaults(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("default", None)
        for value in node.values():
            _strip_json_schema_defaults(value)
    elif isinstance(node, list):
        for item in node:
            _strip_json_schema_defaults(item)


def _strip_json_schema_titles(node: Any) -> None:
    """Drop descriptive Pydantic titles that do not constrain structured output."""

    if isinstance(node, dict):
        node.pop("title", None)
        for value in node.values():
            _strip_json_schema_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_json_schema_titles(item)


ANALYZER_V3_SCHEMA = analyzer_json_schema()


def _topics_from_observation(observation: AnalyzerTurnObservation) -> List[str]:
    topics: List[str] = []
    intent_topic_map = {
        Intent.PRICING_QUESTION.value: Topic.PRICING.value,
        Intent.CHEAPEST_PLAN_QUESTION.value: Topic.PRICING.value,
        Intent.PRODUCT_SCOPE_QUESTION.value: Topic.PRODUCT_SCOPE.value,
        Intent.PRODUCT_RECOMMENDATION_QUESTION.value: Topic.PRODUCT_RECOMMENDATION.value,
        Intent.PLATFORM_STEPS_QUESTION.value: Topic.PLATFORM_PROCESS.value,
        Intent.ONBOARDING_QUESTION.value: Topic.ONBOARDING.value,
        Intent.POLICY_QUESTION.value: Topic.REFUND_POLICY.value,
        Intent.CHANNEL_QUESTION.value: Topic.WHATSAPP.value,
        Intent.INTEGRATION_QUESTION.value: Topic.INTEGRATION.value,
        Intent.INDUSTRY_FIT_QUESTION.value: Topic.INDUSTRY_USE_CASE.value,
        Intent.COMPARISON_QUESTION.value: Topic.COMPETITOR_COMPARISON.value,
        Intent.POST_PURCHASE_REQUEST.value: Topic.POST_PURCHASE.value,
    }
    for intent in [observation.primary_intent, *observation.secondary_intents]:
        topic = intent_topic_map.get(str(intent))
        if topic:
            _append_unique(topics, topic)
    for capability in observation.requested_agent_capabilities:
        if capability.type == RequestedAgentCapability.PROVIDE_PRICES.value:
            _append_unique(topics, Topic.PRICING.value)
        if capability.type in {
            RequestedAgentCapability.CAPTURE_LEAD_DATA.value,
            RequestedAgentCapability.PROVIDE_CATALOG_INFORMATION.value,
            RequestedAgentCapability.COLLECT_ORDER_INFORMATION.value,
        }:
            _append_unique(topics, Topic.PRODUCT_SCOPE.value)
        if capability.type == RequestedAgentCapability.EXPLAIN_BUSINESS_PROCESS.value:
            _append_unique(topics, Topic.PLATFORM_PROCESS.value)
    if observation.requested_agent_actions:
        _append_unique(topics, Topic.PRODUCT_SCOPE.value)
        _append_unique(topics, Topic.INTEGRATION.value)
    channel = (observation.extracted_facts.main_channel or "").lower()
    if channel == "whatsapp":
        _append_unique(topics, Topic.WHATSAPP.value)
    elif channel == "facebook":
        _append_unique(topics, Topic.FACEBOOK.value)
    elif channel == "instagram":
        _append_unique(topics, Topic.INSTAGRAM.value)
    if observation.extracted_facts.business_type:
        _append_unique(topics, Topic.BUSINESS_FIT.value)
    return topics or [Topic.UNKNOWN.value]


def _temporary_profile_aliases(observation: AnalyzerTurnObservation) -> Dict[str, Any]:
    # Phase 1 compatibility: existing planner still consumes profile_data aliases.
    profile_data: Dict[str, Any] = {}
    if observation.requested_agent_actions:
        profile_data["action_requirement"] = ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        profile_data["known_product_fit"] = ProductFit.MOVIA_HIBRIDO.value
    elif any(
        capability.type in INFORMATIONAL_AGENT_CAPABILITIES
        for capability in observation.requested_agent_capabilities
    ):
        profile_data["action_requirement"] = ActionRequirement.ANSWERS_ONLY.value
        profile_data["known_product_fit"] = ProductFit.MOVIA_CAPTURA.value
    requested_product = legacy_requested_product(observation)
    if requested_product == RequestedProduct.MOVIA_VENTAS.value:
        profile_data["known_product_fit"] = ProductFit.MOVIA_VENTAS_UNAVAILABLE.value
    elif requested_product == RequestedProduct.MOVIA_PRO_COMERCIAL.value:
        profile_data["known_product_fit"] = ProductFit.MOVIA_PRO_COMERCIAL_UNAVAILABLE.value
    return profile_data


def _legacy_objection_relation(observation: AnalyzerTurnObservation) -> str:
    relation = str(observation.active_objection_relation.relation)
    if relation != AnalyzerActiveObjectionRelation.NONE.value:
        return relation
    if observation.objection_candidate.type != ObjectionType.NONE.value:
        return ObjectionRelation.NEW.value
    return ObjectionRelation.NONE.value


def _requirement_update_intent_from_legacy_analysis(
    analysis: TurnAnalysis,
    message: str,
    requested_capabilities: List[AgentCapabilityObservation],
    requested_actions: List[AgentActionObservation],
    declared_action_count: Optional[DeclaredExternalActionCountObservation],
) -> str:
    if not requested_capabilities and not requested_actions and not declared_action_count:
        return RequirementUpdateIntent.NO_CHANGE.value
    text = _normalize_for_evidence(message)
    if any(
        cue in text
        for cue in [
            "solo que",
            "solamente que",
            "entonces solo",
            "mejor solo",
            "por ahora solo",
            "ya no",
            "en vez de",
            "cambiarlo a",
            "cambiemos a",
        ]
    ):
        return RequirementUpdateIntent.REPLACE.value
    if analysis.references_prior_message and any(
        cue in text for cue in ["no", "eso ya", "mejor", "entonces"]
    ):
        return RequirementUpdateIntent.REPLACE.value
    return RequirementUpdateIntent.MERGE.value


def _legacy_reference_type(reference_type: str) -> str:
    mapping = {
        AnalyzerReferenceType.NONE.value: ReferenceType.NONE.value,
        AnalyzerReferenceType.IMPLICIT_PRIOR_REFERENCE.value: ReferenceType.TEMPORAL_REFERENCE.value,
        AnalyzerReferenceType.TOPIC_REFERENCE.value: ReferenceType.TOPIC_REFERENCE.value,
        AnalyzerReferenceType.ENTITY_REFERENCE.value: ReferenceType.ENTITY_REFERENCE.value,
        AnalyzerReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value: ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value,
    }
    return mapping.get(reference_type, ReferenceType.NONE.value)


def _analyzer_reference_type(reference_type: str) -> str:
    mapping = {
        ReferenceType.NONE.value: AnalyzerReferenceType.NONE.value,
        ReferenceType.EXPLICIT_TURN.value: AnalyzerReferenceType.IMPLICIT_PRIOR_REFERENCE.value,
        ReferenceType.TEMPORAL_REFERENCE.value: AnalyzerReferenceType.IMPLICIT_PRIOR_REFERENCE.value,
        ReferenceType.TOPIC_REFERENCE.value: AnalyzerReferenceType.TOPIC_REFERENCE.value,
        ReferenceType.ENTITY_REFERENCE.value: AnalyzerReferenceType.ENTITY_REFERENCE.value,
        ReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value: AnalyzerReferenceType.ASSISTANT_COMMITMENT_REFERENCE.value,
    }
    return mapping.get(reference_type, AnalyzerReferenceType.NONE.value)


def _reference_topics(prior: PriorReferenceObservation, fallback_topics: List[str]) -> List[str]:
    hint = (prior.topic_hint or "").lower()
    topics: List[str] = []
    if "proveedor" in hint or "ticket" in hint or "foto" in hint:
        topics.append(Topic.PRODUCT_SCOPE.value)
    if "deposit" in hint or "50%" in hint:
        topics.extend([Topic.DEPOSIT.value, Topic.PLATFORM_PROCESS.value])
    if "precio" in hint or "cuesta" in hint:
        topics.append(Topic.PRICING.value)
    return _dedupe(topics or fallback_topics)


def _actions_from_legacy_profile_data(
    analysis: TurnAnalysis, message: str
) -> List[AgentActionObservation]:
    if not (
        analysis.lead_updates.profile_data.get("action_requirement")
        == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        or _has_future_agent_request_context(message)
    ):
        return []
    if not _has_future_agent_request_context(message):
        return []
    text = _normalize_for_evidence(message)
    actions: List[AgentActionObservation] = []
    if "agend" in text and _explicit_action_requested(message, ["agendar", "agende", "agenda", "cita", "citas", "reservar"]):
        actions.append(AgentActionObservation(type=RequestedAgentAction.SCHEDULE_APPOINTMENT, evidence_span=_best_span(message, ["agendar", "agende", "agenda"])))
    if ("cotiz" in text or "cotic" in text) and _explicit_action_requested(message, ["cotice", "cotizar", "cotización", "cotizacion", "quote"]):
        actions.append(AgentActionObservation(type=RequestedAgentAction.GENERATE_QUOTE, evidence_span=_best_span(message, ["cotice", "cotizar", "cotización", "cotizacion"])))
    if ("registr" in text or "pedido" in text) and _explicit_action_requested(message, ["registrar", "registre", "pedido", "pedidos", "orden"]):
        actions.append(AgentActionObservation(type=RequestedAgentAction.CREATE_ORDER, evidence_span=_best_span(message, ["registre pedidos", "registrar", "pedidos"])))
    if ("sistema" in text or "panel" in text) and _explicit_action_requested(message, ["sistema", "panel", "crm", "base de datos"]):
        actions.append(AgentActionObservation(type=RequestedAgentAction.WRITE_EXTERNAL_SYSTEM, evidence_span=_best_span(message, ["sistema", "panel"])))
    if actions:
        return actions
    if _contains_any_normalized(message, ["sistema", "panel", "crm"]) and _has_future_agent_request_context(message):
        return [AgentActionObservation(type=RequestedAgentAction.UNKNOWN_EXTERNAL_ACTION, evidence_span=message)]
    return []


def _capabilities_from_legacy_profile_data(
    analysis: TurnAnalysis, message: str
) -> List[AgentCapabilityObservation]:
    if not _has_future_agent_request_context(message):
        return []
    capabilities: List[AgentCapabilityObservation] = []
    if _explicit_capability_requested(message, ["responder", "contestar", "dudas", "preguntas"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.ANSWER_CUSTOMER_QUESTIONS,
                evidence_span=message,
            )
        )
    if _explicit_capability_requested(message, ["capturar", "capture", "datos", "leads"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.CAPTURE_LEAD_DATA,
                evidence_span=message,
            )
        )
    if _explicit_capability_requested(message, ["dar precios", "de precios", "responda precios", "responder precios", "precios automáticamente", "precios automaticos", "les diga precios"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.PROVIDE_PRICES,
                evidence_span=message,
            )
        )
    if _explicit_capability_requested(message, ["explique el proceso", "explique como funciona", "explique cómo funciona"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.EXPLAIN_BUSINESS_PROCESS,
                evidence_span=message,
            )
        )
    if _explicit_capability_requested(message, ["cierre ventas", "cerrar ventas", "venda por mi", "venda por mí"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.CLOSE_SALE,
                evidence_span=message,
            )
        )
    if _explicit_capability_requested(message, ["maneje objeciones", "resuelva objeciones", "responda objeciones"]):
        capabilities.append(
            AgentCapabilityObservation(
                type=RequestedAgentCapability.HANDLE_SALES_OBJECTIONS,
                evidence_span=message,
            )
        )
    return capabilities


def _observed_business_problems_from_legacy_analysis(
    analysis: TurnAnalysis, message: str
) -> List[BusinessProblemObservation]:
    problem_map = [
        (ObservedBusinessProblem.LEAD_DROP_OFF.value, ["desaparece", "desaparecen", "pierdo leads", "se pierden leads", "se enfria", "se enfría"]),
        (ObservedBusinessProblem.SLOW_RESPONSE.value, ["no responde", "no responden", "nadie contesta", "nadie responde"]),
        (ObservedBusinessProblem.MANUAL_SCHEDULING.value, ["agendamos manualmente", "agenda todo manualmente"]),
        (ObservedBusinessProblem.MANUAL_ORDER_PROCESSING.value, ["registramos pedidos manualmente", "pedidos manualmente"]),
        (ObservedBusinessProblem.MANUAL_DATA_CAPTURE.value, ["capturamos manualmente", "registramos manualmente", "anotamos manualmente"]),
        (ObservedBusinessProblem.REPETITIVE_QUESTIONS.value, ["mismas preguntas", "siempre preguntan", "preguntan precio"]),
    ]
    observations: List[BusinessProblemObservation] = []
    for problem_type, cues in problem_map:
        span = _best_span_if_present(message, cues)
        if span:
            observations.append(
                BusinessProblemObservation(
                    type=problem_type,
                    evidence_span=span,
                    observation_strength=SemanticStrength.UNAMBIGUOUS_IMPLICIT,
                )
            )
    return observations


def _declared_external_action_count_from_message(
    message: str,
) -> Optional[DeclaredExternalActionCountObservation]:
    parsed = _extract_declared_action_count(message)
    if not parsed:
        return None
    count, evidence_span = parsed
    return DeclaredExternalActionCountObservation(value=count, evidence_span=evidence_span)


def _extract_declared_action_count(message: str) -> Optional[Tuple[int, str]]:
    normalized = _normalize_for_evidence(message)
    digit_match = re.search(r"\b(\d{1,2})\b(?:\s+acciones?)?", normalized)
    if digit_match:
        value = int(digit_match.group(1))
        if value >= 1:
            span = _substring_by_normalized_slice(message, digit_match.start(1), digit_match.end(0))
            if span:
                return value, span
    word_map = {
        "una": 1,
        "uno": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
    }
    for word, value in word_map.items():
        match = re.search(rf"\b{re.escape(word)}\b(?:\s+acciones?)?", normalized)
        if not match:
            continue
        span = _substring_by_normalized_slice(message, match.start(0), match.end(0))
        if span:
            return value, span
    return None


def _count_to_spanish_word(value: int) -> Optional[str]:
    mapping = {
        1: "una",
        2: "dos",
        3: "tres",
        4: "cuatro",
        5: "cinco",
        6: "seis",
        7: "siete",
        8: "ocho",
        9: "nueve",
        10: "diez",
    }
    return mapping.get(value)


def _substring_by_normalized_slice(message: str, start: int, end: int) -> Optional[str]:
    normalized_chars: List[str] = []
    source_indexes: List[int] = []
    for index, char in enumerate(message):
        normalized = _normalize_for_evidence(char)
        if not normalized:
            continue
        for normalized_char in normalized:
            normalized_chars.append(normalized_char)
            source_indexes.append(index)
    if not source_indexes or start >= len(source_indexes):
        return None
    source_start = source_indexes[start]
    source_end = source_indexes[min(end - 1, len(source_indexes) - 1)] + 1
    return message[source_start:source_end].strip(" ¿?.,;:!¡")


def _best_span_if_present(message: str, needles: List[str]) -> Optional[str]:
    text = _normalize_for_evidence(message)
    for needle in needles:
        if _normalize_for_evidence(needle) in text:
            return _best_span(message, [needle])
    return None


def _has_future_agent_request_context(message: str) -> bool:
    text = _normalize_for_evidence(message)
    product_context_terms = [
        "movia captura",
        "movia hibrido",
        "movia híbrido",
        "captura",
        "hibrido",
        "híbrido",
    ]
    if any(term in text for term in product_context_terms) and any(
        cue in text for cue in [" para ", " puede ", " podria ", " podría "]
    ):
        return True
    return _contains_any_normalized(
        message,
        [
            "quiero que",
            "necesito que",
            "busco que",
            "que el agente",
            "que movia",
            "que haga",
            "que pueda",
            "para que",
            "quiero movia",
            "quiero captura",
            "quiero hibrido",
            "quiero híbrido",
            "quiero el agente",
            "necesito el agente",
            "lo quiero para",
            "me gustaria que",
            "me gustaría que",
            "ocupo que",
            "necesito un agente que",
            "solo que",
            "solamente que",
            "entonces solo",
            "mejor solo",
            "por ahora solo",
        ],
    )


def _explicit_capability_requested(message: str, cues: List[str]) -> bool:
    return _has_future_agent_request_context(message) and _contains_any_normalized(message, cues)


def _explicit_action_requested(message: str, cues: List[str]) -> bool:
    return _has_future_agent_request_context(message) and _contains_any_normalized(message, cues)


def _product_references_from_message(message: str) -> List[ProductReferenceObservation]:
    text = _normalize_for_evidence(message)
    matches: List[Tuple[str, List[str]]] = [
        (RequestedProduct.MOVIA_CAPTURA.value, ["Captura", "captura"]),
        (RequestedProduct.MOVIA_HIBRIDO.value, ["Híbrido", "hibrido", "híbrido"]),
        (RequestedProduct.MOVIA_VENTAS.value, ["Ventas", "ventas"]),
        (RequestedProduct.MOVIA_PRO_COMERCIAL.value, ["Pro Comercial", "pro comercial"]),
    ]
    found = [(product, cues) for product, cues in matches if any(_normalize_for_evidence(cue) in text for cue in cues)]
    if not found:
        return []
    committed = _contains_any_normalized(
        message,
        [
            "me quedo con",
            "quiero contratar",
            "elijo",
            "vamos con",
            "quiero empezar con",
            "empezar con",
            "iniciar con",
        ],
    )
    preferred = _contains_any_normalized(message, ["prefiero", "me conviene", "me interesa más"])
    comparison = len(found) > 1 or _contains_any_normalized(message, ["compar", " vs ", "o necesito"])
    references: List[ProductReferenceObservation] = []
    for index, (product, cues) in enumerate(found):
        role = ProductReferenceRole.MENTIONED.value
        if committed and index == len(found) - 1:
            role = ProductReferenceRole.COMMITTED.value
        elif preferred and index == len(found) - 1:
            role = ProductReferenceRole.PREFERRED.value
        elif comparison:
            role = (
                ProductReferenceRole.QUESTION_SUBJECT.value
                if index == 0
                else ProductReferenceRole.COMPARISON_ALTERNATIVE.value
            )
        else:
            role = ProductReferenceRole.QUESTION_SUBJECT.value
        references.append(
            ProductReferenceObservation(
                product=product,
                evidence_span=_best_span(message, cues),
                reference_role=role,
            )
        )
    return references


def _product_reference_from_message(
    message: str, product: str, role: str
) -> Optional[ProductReferenceObservation]:
    for reference in _product_references_from_message(message):
        if reference.product == product:
            return reference.model_copy(update={"reference_role": role})
    return None


def _dedupe_product_references(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    precedence = {
        ProductReferenceRole.MENTIONED.value: 0,
        ProductReferenceRole.COMPARISON_ALTERNATIVE.value: 1,
        ProductReferenceRole.QUESTION_SUBJECT.value: 2,
        ProductReferenceRole.PREFERRED.value: 3,
        ProductReferenceRole.COMMITTED.value: 4,
    }
    by_product: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for reference in references:
        product = str(reference.get("product") or "")
        if product not in by_product:
            by_product[product] = reference
            order.append(product)
            continue
        current = by_product[product]
        if precedence.get(str(reference.get("reference_role")), -1) > precedence.get(
            str(current.get("reference_role")), -1
        ):
            by_product[product] = reference
    return [by_product[product] for product in order]


def _contains_any_normalized(message: str, needles: List[str]) -> bool:
    text = _normalize_for_evidence(message)
    return any(_normalize_for_evidence(needle) in text for needle in needles)


def _is_full_message_span(evidence_span: str, message: str) -> bool:
    return _normalize_for_evidence(evidence_span) == _normalize_for_evidence(message)


def _best_span(message: str, needles: List[str]) -> str:
    text = _normalize_for_evidence(message)
    for needle in needles:
        if _normalize_for_evidence(needle) in text:
            return needle
    return message


def _append_unique(values: List[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
