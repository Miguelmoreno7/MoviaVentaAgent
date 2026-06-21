from __future__ import annotations

from enum import Enum
from typing import Dict, List, Type


COMMERCIAL_CONTRACT_VERSION = "2.0"


class CommercialEnum(str, Enum):
    @classmethod
    def values(cls) -> List[str]:
        return [item.value for item in cls]


class Intent(CommercialEnum):
    GREETING = "greeting"
    GENERAL_INFO = "general_info"
    PRICING_QUESTION = "pricing_question"
    CHEAPEST_PLAN_QUESTION = "cheapest_plan_question"
    PRODUCT_SCOPE_QUESTION = "product_scope_question"
    PRODUCT_RECOMMENDATION_QUESTION = "product_recommendation_question"
    PLATFORM_STEPS_QUESTION = "platform_steps_question"
    ONBOARDING_QUESTION = "onboarding_question"
    POLICY_QUESTION = "policy_question"
    CHANNEL_QUESTION = "channel_question"
    INTEGRATION_QUESTION = "integration_question"
    INDUSTRY_FIT_QUESTION = "industry_fit_question"
    COMPARISON_QUESTION = "comparison_question"
    EXPLICIT_START_REQUEST = "explicit_start_request"
    POST_PURCHASE_REQUEST = "post_purchase_request"
    SUPPORT_REQUEST = "support_request"
    UNKNOWN = "unknown"


class Topic(CommercialEnum):
    PRICING = "pricing"
    PRODUCT_SCOPE = "product_scope"
    PRODUCT_RECOMMENDATION = "product_recommendation"
    PLATFORM_PROCESS = "platform_process"
    ONBOARDING = "onboarding"
    DEPOSIT = "deposit"
    FINAL_PAYMENT = "final_payment"
    MONTHLY_PAYMENT = "monthly_payment"
    REFUND_POLICY = "refund_policy"
    SUPPORT = "support"
    TOKEN_USAGE = "token_usage"
    WHATSAPP = "whatsapp"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    INTEGRATION = "integration"
    BUSINESS_FIT = "business_fit"
    INDUSTRY_USE_CASE = "industry_use_case"
    COMPETITOR_COMPARISON = "competitor_comparison"
    HUMAN_HANDOFF = "human_handoff"
    DEMO = "demo"
    DOCUMENTS = "documents"
    CONVERSATION_EXAMPLES = "conversation_examples"
    CLIENT_REVIEW = "client_review"
    ACTIVATION = "activation"
    POST_PURCHASE = "post_purchase"
    UNKNOWN = "unknown"


class ObjectionType(CommercialEnum):
    NONE = "none"
    PRICE_OBJECTION = "price_objection"
    TRUST_OBJECTION = "trust_objection"
    FEAR_WRONG_ANSWERS = "fear_wrong_answers"
    ALREADY_HAVE_PERSON = "already_have_person"
    ALREADY_USE_WHATSAPP_BUSINESS = "already_use_whatsapp_business"
    NEED_TO_THINK = "need_to_think"
    WANTS_FREE_TRIAL = "wants_free_trial"
    COMPETITOR_COMPARISON = "competitor_comparison"
    NOT_SURE_IF_NEEDED = "not_sure_if_needed"
    SCOPE_OBJECTION = "scope_objection"
    CHANNEL_CONNECTION_CONCERN = "channel_connection_concern"
    SUPPORT_CONCERN = "support_concern"


class ObjectionStrength(CommercialEnum):
    NONE = "none"
    SOFT = "soft"
    HARD = "hard"


class ObjectionRelation(CommercialEnum):
    NONE = "none"
    NEW = "new"
    CONTINUATION = "continuation"
    REAFFIRMED = "reaffirmed"
    CLARIFIED = "clarified"
    RESOLVED = "resolved"
    UNRELATED = "unrelated"


class ObjectionStatus(CommercialEnum):
    NONE = "none"
    ACTIVE = "active"
    PAUSED = "paused"
    RESOLVED = "resolved"


class ConversationMode(CommercialEnum):
    NORMAL = "normal"
    HANDLING_OBJECTION = "handling_objection"


class ReferenceType(CommercialEnum):
    NONE = "none"
    EXPLICIT_TURN = "explicit_turn"
    TEMPORAL_REFERENCE = "temporal_reference"
    TOPIC_REFERENCE = "topic_reference"
    ENTITY_REFERENCE = "entity_reference"
    ASSISTANT_COMMITMENT_REFERENCE = "assistant_commitment_reference"


class BuyingSignal(CommercialEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXPLICIT_START = "explicit_start"


class ActionRequirement(CommercialEnum):
    ANSWERS_ONLY = "answers_only"
    EXTERNAL_ACTIONS_REQUIRED = "external_actions_required"
    UNKNOWN = "unknown"


class ProductFit(CommercialEnum):
    UNKNOWN = "unknown"
    MOVIA_CAPTURA = "movia_captura"
    MOVIA_HIBRIDO = "movia_hibrido"
    MOVIA_VENTAS_UNAVAILABLE = "movia_ventas_unavailable"
    MOVIA_PRO_COMERCIAL_UNAVAILABLE = "movia_pro_comercial_unavailable"
    CUSTOM_REVIEW = "custom_review"


class SalesStage(CommercialEnum):
    NEW = "new"
    DISCOVERY = "discovery"
    EDUCATING = "educating"
    COMPARING = "comparing"
    # Deprecated as a primary persisted stage. Kept for migration compatibility only.
    OBJECTION_HANDLING = "objection_handling"
    QUALIFIED = "qualified"
    SOLUTION_RECOMMENDED = "solution_recommended"
    READY_TO_START = "ready_to_start"
    CLOSING = "closing"
    POST_PURCHASE = "post_purchase"
    HANDOFF = "handoff"
    UNKNOWN_RECOVERY = "unknown_recovery"


class MacroAction(CommercialEnum):
    ANSWER_AND_ADVANCE = "answer_and_advance"
    DISCOVER_NEED = "discover_need"
    NARROW_SOLUTION = "narrow_solution"
    RECOMMEND_SOLUTION = "recommend_solution"
    PERSUADE_VALUE = "persuade_value"
    HANDLE_OBJECTION = "handle_objection"
    RISK_REVERSAL = "risk_reversal"
    COMPARE_ALTERNATIVE = "compare_alternative"
    EXPLAIN_PROCESS = "explain_process"
    SOFT_CLOSE = "soft_close"
    DIRECT_CLOSE = "direct_close"
    HANDOFF_TO_MIGUEL = "handoff_to_miguel"
    ANSWER_UNKNOWN_SAFELY = "answer_unknown_safely"


class MicroAction(CommercialEnum):
    ANSWER_PRICE_THEN_EXPLAIN_SCOPE = "answer_price_then_explain_scope"
    ANSWER_SCOPE_THEN_DISCOVER_BUSINESS = "answer_scope_then_discover_business"
    ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL = "answer_channel_then_discover_main_channel"
    ANSWER_PROCESS_THEN_EXPLAIN_NEXT_STEP = "answer_process_then_explain_next_step"
    ANSWER_POLICY_THEN_REDUCE_RISK = "answer_policy_then_reduce_risk"
    ANSWER_GENERAL_THEN_DISCOVER_NEED = "answer_general_then_discover_need"
    ASK_BUSINESS_TYPE = "ask_business_type"
    ASK_MAIN_CHANNEL = "ask_main_channel"
    ASK_PAIN_OR_GOAL = "ask_pain_or_goal"
    ASK_MESSAGE_VOLUME = "ask_message_volume"
    ASK_ACTION_REQUIREMENT = "ask_action_requirement"
    ASK_CURRENT_PROCESS = "ask_current_process"
    DIFFERENTIATE_CAPTURA_VS_HIBRIDO = "differentiate_captura_vs_hibrido"
    DETERMINE_IF_EXTERNAL_ACTIONS_ARE_NEEDED = "determine_if_external_actions_are_needed"
    ROUTE_TO_AVAILABLE_PRODUCTS = "route_to_available_products"
    CLARIFY_ACTION_COUNT = "clarify_action_count"
    CLARIFY_OPERATIONAL_SCOPE = "clarify_operational_scope"
    RECOMMEND_MOVIA_CAPTURA = "recommend_movia_captura"
    RECOMMEND_MOVIA_HIBRIDO = "recommend_movia_hibrido"
    RECOMMEND_DEMO = "recommend_demo"
    EXPLAIN_VENTAS_NOT_AVAILABLE = "explain_ventas_not_available"
    EXPLAIN_PRO_COMERCIAL_NOT_AVAILABLE = "explain_pro_comercial_not_available"
    INDUSTRY_SPECIFIC_VALUE = "industry_specific_value"
    LOGICAL_VALUE = "logical_value"
    OPPORTUNITY_COST = "opportunity_cost"
    STATUS_QUO_COST = "status_quo_cost"
    RESPONSE_SPEED_VALUE = "response_speed_value"
    HUMAN_TEAM_SUPPORT_VALUE = "human_team_support_value"
    VALIDATE_AND_CLARIFY_OBJECTION = "validate_and_clarify_objection"
    CLARIFY_OBJECTION_VALUE = "clarify_objection_value"
    TIE_SOLUTION_TO_OBJECTION = "tie_solution_to_objection"
    PROVIDE_OBJECTION_PROOF = "provide_objection_proof"
    CLOSE_OR_CONTINUE_OBJECTION = "close_or_continue_objection"
    EXPLAIN_TESTING_BEFORE_RELEASE = "explain_testing_before_release"
    EXPLAIN_CLIENT_REVIEW = "explain_client_review"
    EXPLAIN_ADJUSTMENTS_BEFORE_APPROVAL = "explain_adjustments_before_approval"
    EXPLAIN_HUMAN_HANDOFF = "explain_human_handoff"
    EXPLAIN_OFFICIAL_META_CONNECTION = "explain_official_meta_connection"
    COMPARE_MANYCHAT = "compare_manychat"
    COMPARE_BASIC_CHATBOT = "compare_basic_chatbot"
    COMPARE_HUMAN_RECEPTIONIST = "compare_human_receptionist"
    COMPARE_WHATSAPP_BUSINESS_ONLY = "compare_whatsapp_business_only"
    COMPARE_CUSTOM_DEVELOPMENT = "compare_custom_development"
    EXPLAIN_APP_REGISTRATION = "explain_app_registration"
    EXPLAIN_CUSTOMER_WORKSPACE = "explain_customer_workspace"
    EXPLAIN_DEMO = "explain_demo"
    EXPLAIN_AGENT_CREATION = "explain_agent_creation"
    EXPLAIN_DEPOSIT = "explain_deposit"
    EXPLAIN_DOCUMENTS = "explain_documents"
    EXPLAIN_CONVERSATION_EXAMPLES = "explain_conversation_examples"
    EXPLAIN_WHATSAPP_INTEGRATION = "explain_whatsapp_integration"
    EXPLAIN_FINAL_PAYMENT = "explain_final_payment"
    EXPLAIN_ACTIVATION = "explain_activation"
    INVITE_TO_DEMO = "invite_to_demo"
    INVITE_TO_START = "invite_to_start"
    CONFIRM_SOLUTION_FIT = "confirm_solution_fit"
    ASK_PERMISSION_TO_SEND_LINK = "ask_permission_to_send_link"
    SEND_APP_LINK = "send_app_link"
    SEND_APP_LINK_AND_DEPOSIT_STEP = "send_app_link_and_deposit_step"
    EXPLAIN_IMMEDIATE_NEXT_STEP = "explain_immediate_next_step"
    REDIRECT_POST_PURCHASE = "redirect_post_purchase"
    REDIRECT_CONNECTION_ISSUE = "redirect_connection_issue"
    REDIRECT_CUSTOM_SCOPE = "redirect_custom_scope"
    REDIRECT_EXISTING_CLIENT = "redirect_existing_client"
    CLARIFY_SCOPE = "clarify_scope"
    ACKNOWLEDGE_LIMIT = "acknowledge_limit"
    RECOVER_TO_AUTOMATION_NEED = "recover_to_automation_need"
    ASK_SINGLE_CLARIFYING_QUESTION = "ask_single_clarifying_question"


class CTAType(CommercialEnum):
    NONE = "none"
    SOFT_QUESTION = "soft_question"
    DISCOVERY_QUESTION = "discovery_question"
    OBJECTION_QUESTION = "objection_question"
    EXPLAIN_NEXT_STEP = "explain_next_step"
    SOFT_CLOSE = "soft_close"
    ASK_PERMISSION_TO_SEND_LINK = "ask_permission_to_send_link"
    SEND_APP_LINK = "send_app_link"
    DIRECT_CLOSE = "direct_close"
    REDIRECT_TO_MIGUEL = "redirect_to_miguel"


class ObjectionFlowStep(CommercialEnum):
    NONE = "none"
    THANK_EMPATHIZE_ASK_OPEN_QUESTION = "thank_empathize_ask_open_question"
    CLARIFY_VALUE = "clarify_value"
    TIE_SOLUTION = "tie_solution"
    PROVIDE_PROOF = "provide_proof"
    CLOSE_OR_CONTINUE = "close_or_continue"
    RESOLVED = "resolved"


class PlannerReasonCode(CommercialEnum):
    POST_PURCHASE_HANDOFF = "POST_PURCHASE_HANDOFF"
    SUPPORT_HANDOFF = "SUPPORT_HANDOFF"
    ACTIVE_OBJECTION_CONTINUATION = "ACTIVE_OBJECTION_CONTINUATION"
    NEW_HARD_OBJECTION = "NEW_HARD_OBJECTION"
    NEW_SOFT_OBJECTION = "NEW_SOFT_OBJECTION"
    DIRECT_CLOSE_ALLOWED = "DIRECT_CLOSE_ALLOWED"
    PRICE_QUESTION_WITH_DISCOVERY_GAP = "PRICE_QUESTION_WITH_DISCOVERY_GAP"
    SCOPE_QUESTION_WITH_DISCOVERY_GAP = "SCOPE_QUESTION_WITH_DISCOVERY_GAP"
    CHANNEL_QUESTION_WITH_DISCOVERY_GAP = "CHANNEL_QUESTION_WITH_DISCOVERY_GAP"
    PROCESS_EXPLANATION_REQUESTED = "PROCESS_EXPLANATION_REQUESTED"
    POLICY_RISK_REVERSAL_REQUESTED = "POLICY_RISK_REVERSAL_REQUESTED"
    COMPARISON_REQUESTED = "COMPARISON_REQUESTED"
    UNKNOWN_RECOVERY = "UNKNOWN_RECOVERY"
    BUSINESS_TYPE_UNKNOWN = "BUSINESS_TYPE_UNKNOWN"
    MAIN_CHANNEL_UNKNOWN = "MAIN_CHANNEL_UNKNOWN"
    PAIN_OR_GOAL_UNKNOWN = "PAIN_OR_GOAL_UNKNOWN"
    ACTION_REQUIREMENT_UNKNOWN = "ACTION_REQUIREMENT_UNKNOWN"
    ANSWERS_ONLY_CAPTURA_FIT = "ANSWERS_ONLY_CAPTURA_FIT"
    EXTERNAL_ACTIONS_HIBRIDO_FIT = "EXTERNAL_ACTIONS_HIBRIDO_FIT"
    SALES_PRODUCT_UNAVAILABLE = "SALES_PRODUCT_UNAVAILABLE"
    PRO_PRODUCT_UNAVAILABLE = "PRO_PRODUCT_UNAVAILABLE"
    CUSTOM_SCOPE_REVIEW = "CUSTOM_SCOPE_REVIEW"
    SKEPTICAL_VALUE_NEEDED = "SKEPTICAL_VALUE_NEEDED"
    INDUSTRY_VALUE_NEEDED = "INDUSTRY_VALUE_NEEDED"
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    MEDIUM_HIGH_SIGNAL_SOFT_CLOSE = "MEDIUM_HIGH_SIGNAL_SOFT_CLOSE"
    DEFAULT_RECOMMENDATION = "DEFAULT_RECOMMENDATION"


CONTRACT_ENUMS: Dict[str, Type[CommercialEnum]] = {
    "intents": Intent,
    "topics": Topic,
    "objection_types": ObjectionType,
    "objection_strengths": ObjectionStrength,
    "objection_relations": ObjectionRelation,
    "objection_statuses": ObjectionStatus,
    "conversation_modes": ConversationMode,
    "reference_types": ReferenceType,
    "buying_signals": BuyingSignal,
    "action_requirements": ActionRequirement,
    "product_fits": ProductFit,
    "sales_stages": SalesStage,
    "macro_actions": MacroAction,
    "micro_actions": MicroAction,
    "cta_types": CTAType,
    "objection_flow_steps": ObjectionFlowStep,
    "planner_reason_codes": PlannerReasonCode,
}


MICROACTIONS_BY_MACRO: Dict[str, List[str]] = {
    MacroAction.ANSWER_AND_ADVANCE.value: [
        MicroAction.ANSWER_PRICE_THEN_EXPLAIN_SCOPE.value,
        MicroAction.ANSWER_SCOPE_THEN_DISCOVER_BUSINESS.value,
        MicroAction.ANSWER_CHANNEL_THEN_DISCOVER_MAIN_CHANNEL.value,
        MicroAction.ANSWER_PROCESS_THEN_EXPLAIN_NEXT_STEP.value,
        MicroAction.ANSWER_POLICY_THEN_REDUCE_RISK.value,
        MicroAction.ANSWER_GENERAL_THEN_DISCOVER_NEED.value,
    ],
    MacroAction.DISCOVER_NEED.value: [
        MicroAction.ASK_BUSINESS_TYPE.value,
        MicroAction.ASK_MAIN_CHANNEL.value,
        MicroAction.ASK_PAIN_OR_GOAL.value,
        MicroAction.ASK_MESSAGE_VOLUME.value,
        MicroAction.ASK_ACTION_REQUIREMENT.value,
        MicroAction.ASK_CURRENT_PROCESS.value,
    ],
    MacroAction.NARROW_SOLUTION.value: [
        MicroAction.DIFFERENTIATE_CAPTURA_VS_HIBRIDO.value,
        MicroAction.DETERMINE_IF_EXTERNAL_ACTIONS_ARE_NEEDED.value,
        MicroAction.ROUTE_TO_AVAILABLE_PRODUCTS.value,
        MicroAction.CLARIFY_ACTION_COUNT.value,
        MicroAction.CLARIFY_OPERATIONAL_SCOPE.value,
    ],
    MacroAction.RECOMMEND_SOLUTION.value: [
        MicroAction.RECOMMEND_MOVIA_CAPTURA.value,
        MicroAction.RECOMMEND_MOVIA_HIBRIDO.value,
        MicroAction.RECOMMEND_DEMO.value,
        MicroAction.EXPLAIN_VENTAS_NOT_AVAILABLE.value,
        MicroAction.EXPLAIN_PRO_COMERCIAL_NOT_AVAILABLE.value,
    ],
    MacroAction.PERSUADE_VALUE.value: [
        MicroAction.INDUSTRY_SPECIFIC_VALUE.value,
        MicroAction.LOGICAL_VALUE.value,
        MicroAction.OPPORTUNITY_COST.value,
        MicroAction.STATUS_QUO_COST.value,
        MicroAction.RESPONSE_SPEED_VALUE.value,
        MicroAction.HUMAN_TEAM_SUPPORT_VALUE.value,
    ],
    MacroAction.HANDLE_OBJECTION.value: [
        MicroAction.VALIDATE_AND_CLARIFY_OBJECTION.value,
        MicroAction.CLARIFY_OBJECTION_VALUE.value,
        MicroAction.TIE_SOLUTION_TO_OBJECTION.value,
        MicroAction.PROVIDE_OBJECTION_PROOF.value,
        MicroAction.CLOSE_OR_CONTINUE_OBJECTION.value,
    ],
    MacroAction.RISK_REVERSAL.value: [
        MicroAction.EXPLAIN_TESTING_BEFORE_RELEASE.value,
        MicroAction.EXPLAIN_CLIENT_REVIEW.value,
        MicroAction.EXPLAIN_ADJUSTMENTS_BEFORE_APPROVAL.value,
        MicroAction.EXPLAIN_HUMAN_HANDOFF.value,
        MicroAction.EXPLAIN_OFFICIAL_META_CONNECTION.value,
    ],
    MacroAction.COMPARE_ALTERNATIVE.value: [
        MicroAction.COMPARE_MANYCHAT.value,
        MicroAction.COMPARE_BASIC_CHATBOT.value,
        MicroAction.COMPARE_HUMAN_RECEPTIONIST.value,
        MicroAction.COMPARE_WHATSAPP_BUSINESS_ONLY.value,
        MicroAction.COMPARE_CUSTOM_DEVELOPMENT.value,
    ],
    MacroAction.EXPLAIN_PROCESS.value: [
        MicroAction.EXPLAIN_APP_REGISTRATION.value,
        MicroAction.EXPLAIN_CUSTOMER_WORKSPACE.value,
        MicroAction.EXPLAIN_DEMO.value,
        MicroAction.EXPLAIN_AGENT_CREATION.value,
        MicroAction.EXPLAIN_DEPOSIT.value,
        MicroAction.EXPLAIN_DOCUMENTS.value,
        MicroAction.EXPLAIN_CONVERSATION_EXAMPLES.value,
        MicroAction.EXPLAIN_WHATSAPP_INTEGRATION.value,
        MicroAction.EXPLAIN_CLIENT_REVIEW.value,
        MicroAction.EXPLAIN_FINAL_PAYMENT.value,
        MicroAction.EXPLAIN_ACTIVATION.value,
    ],
    MacroAction.SOFT_CLOSE.value: [
        MicroAction.INVITE_TO_DEMO.value,
        MicroAction.INVITE_TO_START.value,
        MicroAction.CONFIRM_SOLUTION_FIT.value,
        MicroAction.ASK_PERMISSION_TO_SEND_LINK.value,
    ],
    MacroAction.DIRECT_CLOSE.value: [
        MicroAction.SEND_APP_LINK.value,
        MicroAction.SEND_APP_LINK_AND_DEPOSIT_STEP.value,
        MicroAction.EXPLAIN_IMMEDIATE_NEXT_STEP.value,
    ],
    MacroAction.HANDOFF_TO_MIGUEL.value: [
        MicroAction.REDIRECT_POST_PURCHASE.value,
        MicroAction.REDIRECT_CONNECTION_ISSUE.value,
        MicroAction.REDIRECT_CUSTOM_SCOPE.value,
        MicroAction.REDIRECT_EXISTING_CLIENT.value,
    ],
    MacroAction.ANSWER_UNKNOWN_SAFELY.value: [
        MicroAction.CLARIFY_SCOPE.value,
        MicroAction.ACKNOWLEDGE_LIMIT.value,
        MicroAction.RECOVER_TO_AUTOMATION_NEED.value,
        MicroAction.ASK_SINGLE_CLARIFYING_QUESTION.value,
    ],
}


def enum_values(enum_cls: Type[CommercialEnum]) -> List[str]:
    return enum_cls.values()


def commercial_contract() -> Dict[str, object]:
    return {
        "commercial_contract_version": COMMERCIAL_CONTRACT_VERSION,
        "enums": {name: enum_cls.values() for name, enum_cls in CONTRACT_ENUMS.items()},
        "microactions_by_macro": MICROACTIONS_BY_MACRO,
    }


def json_schema_enum(enum_cls: Type[CommercialEnum]) -> Dict[str, object]:
    return {"type": "string", "enum": enum_cls.values()}
