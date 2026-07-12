from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from movia_sales_agent.contracts.commercial import (
    COMMERCIAL_CONTRACT_VERSION,
    BuyingSignal,
    CTAType,
    ConversationMode,
    Intent,
    MacroAction,
    MicroAction,
    ObjectionFlowStep,
    ObjectionRelation,
    ObjectionStrength,
    ObjectionStatus,
    ObjectionType,
    PlannerReasonCode,
    ReferenceType,
    SalesStage,
    Topic,
)


class LeadUpdates(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    business_type: Optional[str] = None
    main_channel: Optional[str] = None
    pain: Optional[str] = None
    urgency: Optional[str] = None
    buying_signal: Optional[BuyingSignal] = None
    profile_data: Dict[str, Any] = Field(default_factory=dict)


class AnalysisConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: float = Field(default=0.0, ge=0.0, le=1.0)
    objection: float = Field(default=0.0, ge=0.0, le=1.0)
    objection_relation: float = Field(default=0.0, ge=0.0, le=1.0)
    prior_reference: float = Field(default=0.0, ge=0.0, le=1.0)
    start_intent: float = Field(default=0.0, ge=0.0, le=1.0)


class TurnAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    primary_intent: Intent = Intent.UNKNOWN
    secondary_intents: List[Intent] = Field(default_factory=list)
    topics: List[Topic] = Field(default_factory=list)
    skeptical_tone: bool = False
    has_objection: bool = False
    objection_type: ObjectionType = ObjectionType.NONE
    objection_strength: ObjectionStrength = ObjectionStrength.NONE
    objection_relation: ObjectionRelation = ObjectionRelation.NONE
    business_type: Optional[str] = None
    main_channel: Optional[str] = None
    pain: Optional[str] = None
    urgency: Optional[str] = None
    buying_signal: BuyingSignal = BuyingSignal.NONE
    explicit_start_intent: bool = False
    is_post_purchase: bool = False
    references_prior_message: bool = False
    reference_type: ReferenceType = ReferenceType.NONE
    reference_query: Optional[str] = None
    referenced_topics: List[Topic] = Field(default_factory=list)
    explicit_turn_number: Optional[int] = Field(default=None, ge=1)
    reference_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: AnalysisConfidence = Field(default_factory=AnalysisConfidence)
    lead_updates: LeadUpdates = Field(default_factory=LeadUpdates)


class ObjectionOverlay(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    mode: ConversationMode = ConversationMode.NORMAL
    relation: ObjectionRelation = ObjectionRelation.NONE
    type: ObjectionType = ObjectionType.NONE
    strength: ObjectionStrength = ObjectionStrength.NONE
    status: ObjectionStatus = ObjectionStatus.NONE
    current_step: ObjectionFlowStep = ObjectionFlowStep.NONE
    inline: bool = False
    blocking_close: bool = False
    response_instruction: Optional[str] = None


class SalesPlan(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    macro_action: MacroAction
    micro_action: MicroAction
    commercial_goal: str
    next_question: Optional[str] = None
    next_question_key: Optional[str] = None
    cta_type: CTAType = CTAType.NONE
    objection_flow_step: ObjectionFlowStep = ObjectionFlowStep.NONE
    target_stage: SalesStage
    reason_code: PlannerReasonCode
    objection_overlay: Optional[ObjectionOverlay] = None


class KnowledgePlan(BaseModel):
    knowledge_needs: List[str] = Field(default_factory=list)
    structured_sources: List[str] = Field(default_factory=list)
    json_sources: List[str] = Field(default_factory=list)
    rag_queries: List[str] = Field(default_factory=list)
    rag_metadata_filter: Dict[str, Any] = Field(default_factory=dict)
    rag_routing_reason: str = "structured_or_json_only"
    needs_rag: bool = False


class StageTransition(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    current_stage: SalesStage
    previous_stage: Optional[SalesStage] = None
    stage_before_objection: Optional[SalesStage] = None
    conversation_mode: ConversationMode = ConversationMode.NORMAL
    stage_reason_code: PlannerReasonCode
    stage_reason: str
    stage_changed: bool = False
    normalized_from: Optional[str] = None
    invalid_transition: Optional[str] = None


class ActiveObjection(BaseModel):
    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    active: bool = False
    type: ObjectionType = ObjectionType.NONE
    strength: ObjectionStrength = ObjectionStrength.NONE
    status: ObjectionStatus = ObjectionStatus.NONE
    relation: ObjectionRelation = ObjectionRelation.NONE
    current_step: ObjectionFlowStep = ObjectionFlowStep.NONE
    started_turn: int = Field(default=0, ge=0)
    last_updated_turn: int = Field(default=0, ge=0)
    stage_before_objection: Optional[SalesStage] = None
    evidence: Optional[str] = None
    resolved: bool = False
    paused: bool = False
    paused_reason: Optional[str] = None
    resolved_reason: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    lead_external_id: str = "local"
    channel: str = "local"
    external_message_id: Optional[str] = None


class ChatResponse(BaseModel):
    commercial_contract_version: str = COMMERCIAL_CONTRACT_VERSION
    lead_id: Optional[str] = None
    action: str
    response: str
    response_messages: List[str] = Field(default_factory=list)
    analysis: TurnAnalysis
    retrieval_metadata: Dict[str, Any] = Field(default_factory=dict)
    lead_state: Dict[str, Any] = Field(default_factory=dict)
    selected_action: Dict[str, Any] = Field(default_factory=dict)
    knowledge_plan: Dict[str, Any] = Field(default_factory=dict)
    retrieved_sources: List[Dict[str, Any]] = Field(default_factory=list)
    response_metadata: Dict[str, Any] = Field(default_factory=dict)
    token_usage: Dict[str, Any] = Field(default_factory=dict)


class AgentState(TypedDict, total=False):
    message: str
    channel: str
    external_user_id: str
    external_message_id: Optional[str]
    lead_id: Optional[str]
    lead_profile: Dict[str, Any]
    recent_messages: List[Dict[str, Any]]
    interaction_context: Dict[str, Any]
    structured_memory: Dict[str, Any]
    conversation_memory_evidence: List[Dict[str, Any]]
    shadow_parser: Dict[str, Any]
    analyzer_observation: Dict[str, Any]
    reply_frame: Dict[str, Any]
    reply_frame_resolution: Dict[str, Any]
    normalized_turn: Dict[str, Any]
    requirement_delta_resolution: Dict[str, Any]
    purchase_status: Dict[str, Any]
    analysis: TurnAnalysis
    sales_plan: SalesPlan
    stage_transition: StageTransition
    active_objection: ActiveObjection
    response_fulfillment_policy: Dict[str, Any]
    knowledge_plan: KnowledgePlan
    structured_context: Dict[str, Any]
    json_context: Dict[str, Any]
    rag_context: List[Dict[str, Any]]
    merged_context: Dict[str, Any]
    response: str
    response_messages: List[str]
    retrieval_metadata: Dict[str, Any]
    response_metadata: Dict[str, Any]
    token_usage: Dict[str, Any]
