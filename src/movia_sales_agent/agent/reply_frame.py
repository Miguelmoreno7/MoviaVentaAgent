"""Turn-local semantic resolution for replies to planner-authored questions."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, model_validator

from movia_sales_agent.analyzer.contract_v3 import AnalyzerTurnObservation, evidence_span_in_message
from movia_sales_agent.contracts.commercial import CTAType, Intent, MicroAction
from movia_sales_agent.services.openai_service import empty_usage, response_usage


REPLY_FRAME_ACTION_REQUIREMENT = "action_requirement"
REPLY_FRAME_LINK_START_CONFIRMATION = "link_start_confirmation"
REPLY_FRAME_PLANNER_CONTEXT = "planner_context"

ReplyAct = Literal[
    "accept",
    "decline",
    "provide_answer",
    "ask_followup",
    "unrelated",
    "unclear",
]


class ReplyFrameSemanticResolution(BaseModel):
    """Private schema that only relates this reply to the prior planner turn."""

    model_config = ConfigDict(extra="forbid")

    reply_act: ReplyAct = "unclear"
    evidence_span: Optional[str] = None

    @model_validator(mode="after")
    def require_literal_evidence(self) -> "ReplyFrameSemanticResolution":
        if self.reply_act == "unclear":
            if self.evidence_span:
                raise ValueError("unclear reply act cannot include evidence")
            return self
        if not (self.evidence_span or "").strip():
            raise ValueError("contextual reply act requires evidence_span")
        return self


def reply_frame_for_sales_plan(
    sales_plan: Any,
    normalized_turn: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Serialize the planner decision that gives the next user reply its frame."""

    micro_action = _value(getattr(sales_plan, "micro_action", None))
    cta_type = _value(getattr(sales_plan, "cta_type", None))
    next_question = getattr(sales_plan, "next_question", None)
    next_question_key = getattr(sales_plan, "next_question_key", None)
    if not next_question and not next_question_key and cta_type == CTAType.NONE.value:
        return None

    if micro_action == MicroAction.ASK_ACTION_REQUIREMENT.value:
        frame_type = REPLY_FRAME_ACTION_REQUIREMENT
    elif (
        micro_action == MicroAction.ASK_PERMISSION_TO_SEND_LINK.value
        or cta_type == CTAType.ASK_PERMISSION_TO_SEND_LINK.value
    ):
        frame_type = REPLY_FRAME_LINK_START_CONFIRMATION
    else:
        frame_type = REPLY_FRAME_PLANNER_CONTEXT

    normalized = dict(normalized_turn or {})
    product_context = dict(normalized.get("product_context") or {})
    frame = {
        "type": frame_type,
        "macro_action": _value(getattr(sales_plan, "macro_action", None)),
        "micro_action": micro_action,
        "cta_type": cta_type,
        "next_question_key": next_question_key,
        "next_question": next_question,
        "target_product": normalized.get("selected_product")
        or normalized.get("recommended_product")
        or normalized.get("active_product_context")
        or product_context.get("active_product_context"),
    }
    return {key: value for key, value in frame.items() if value not in (None, "", {})}


def reply_frame_from_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read new frames with a metadata-only path for historical assistant turns."""

    analysis = message.get("analysis") if isinstance(message, dict) else None
    if isinstance(analysis, dict) and isinstance(analysis.get("reply_frame"), dict):
        return dict(analysis["reply_frame"])
    metadata = message.get("retrieval_metadata") if isinstance(message, dict) else None
    response_metadata = (metadata or {}).get("response_metadata") if isinstance(metadata, dict) else {}
    if not isinstance(response_metadata, dict):
        return None
    micro_action = str(response_metadata.get("micro_action") or "")
    cta_type = str(response_metadata.get("cta_type") or "")
    next_question_key = response_metadata.get("next_question_key")
    next_question = response_metadata.get("next_question") or message.get("content")
    if micro_action == MicroAction.ASK_ACTION_REQUIREMENT.value:
        frame_type = REPLY_FRAME_ACTION_REQUIREMENT
    elif (
        micro_action == MicroAction.ASK_PERMISSION_TO_SEND_LINK.value
        or cta_type == CTAType.ASK_PERMISSION_TO_SEND_LINK.value
    ):
        frame_type = REPLY_FRAME_LINK_START_CONFIRMATION
    elif next_question_key or next_question:
        frame_type = REPLY_FRAME_PLANNER_CONTEXT
    else:
        return None
    frame = {
        "type": frame_type,
        "macro_action": response_metadata.get("macro_action"),
        "micro_action": micro_action,
        "cta_type": cta_type,
        "next_question_key": next_question_key,
        "next_question": next_question,
        "target_product": response_metadata.get("selected_product")
        or response_metadata.get("active_product_context"),
        "source": "legacy_response_metadata",
    }
    return {key: value for key, value in frame.items() if value not in (None, "", {})}


def latest_reply_frame(recent_messages: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for message in reversed(list(recent_messages or [])):
        if str(message.get("role") or "").lower() == "assistant":
            return reply_frame_from_message(message)
    return None


def should_resolve_reply_frame(
    frame: Dict[str, Any], observation: AnalyzerTurnObservation
) -> bool:
    frame_type = str(frame.get("type") or "")
    if frame_type in {REPLY_FRAME_ACTION_REQUIREMENT, REPLY_FRAME_LINK_START_CONFIRMATION}:
        return True
    return _semantically_sparse(observation)


def merge_reply_frame_observation(
    observation: AnalyzerTurnObservation,
    resolution: ReplyFrameSemanticResolution,
    message: str,
) -> AnalyzerTurnObservation:
    """Compatibility no-op: contextual acts no longer compete with analyzer facts."""

    del resolution, message
    return observation


def resolve_reply_frame_with_usage(
    openai_service: Any,
    *,
    frame: Dict[str, Any],
    message: str,
    observation: Optional[AnalyzerTurnObservation] = None,
) -> Tuple[Optional[ReplyFrameSemanticResolution], Dict[str, Any]]:
    if not getattr(openai_service, "enabled", False):
        return None, empty_usage("reply_frame", openai_service.settings.analysis_model, "disabled")
    if observation is not None and not should_resolve_reply_frame(frame, observation):
        return None, empty_usage("reply_frame", openai_service.settings.analysis_model, "not_applicable")

    try:
        response = openai_service.client.responses.create(
            model=openai_service.settings.analysis_model,
            temperature=0,
            input=[
                {"role": "system", "content": _resolver_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"current_message": message, "previous_planner": frame},
                        ensure_ascii=False,
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "movia_contextual_reply_resolution",
                    "schema": _strict_response_schema(),
                    "strict": True,
                }
            },
        )
        resolution = ReplyFrameSemanticResolution.model_validate(json.loads(response.output_text))
        resolution = _sanitize_resolution(resolution, message)
        return resolution, response_usage(
            response, "reply_frame", openai_service.settings.analysis_model, "openai"
        )
    except Exception as exc:
        usage = empty_usage("reply_frame", openai_service.settings.analysis_model, "fallback")
        usage["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return None, usage


def _resolver_prompt() -> str:
    return (
        "Clasifica únicamente cómo responde current_message a previous_planner. "
        "No extraigas requisitos, productos, objeciones ni intención comercial. "
        "Usa accept únicamente para una aceptación afirmativa de permiso, propuesta o CTA; "
        "una enumeración o dato solicitado por una pregunta es provide_answer, no accept. "
        "Usa decline cuando rechaza la propuesta o CTA, incluso si después hace otra pregunta; "
        "provide_answer cuando entrega el dato solicitado; ask_followup solo cuando pide ampliar o aclarar sin aceptar ni rechazar; "
        "unrelated cuando cambia de tema; unclear cuando la relación no se puede determinar. "
        "En mensajes compuestos, una aceptación o rechazo explícito de la CTA previa tiene prioridad sobre la pregunta adicional; el analizador principal procesa esa pregunta. "
        "Ejemplos: una lista como 'cotizar, responder, dar información' después de una pregunta de requisitos es provide_answer; "
        "'todavía no, ¿el depósito es reembolsable?' después de ofrecer un link es decline. "
        "Cada respuesta distinta de unclear requiere evidence_span literal de current_message."
    )


def _sanitize_resolution(
    resolution: ReplyFrameSemanticResolution, message: str
) -> ReplyFrameSemanticResolution:
    if resolution.reply_act == "unclear":
        return ReplyFrameSemanticResolution()
    if not resolution.evidence_span or not evidence_span_in_message(
        resolution.evidence_span, message
    ):
        return ReplyFrameSemanticResolution()
    return resolution


def _semantically_sparse(observation: AnalyzerTurnObservation) -> bool:
    facts = observation.extracted_facts
    has_independent_semantics = any(
        [
            observation.observed_business_problems,
            observation.requested_agent_capabilities,
            observation.requested_agent_actions,
            observation.product_references,
            observation.objection_candidate.type != "none",
            observation.purchase_readiness.level not in {"none", "low"},
            facts.business_type,
            facts.main_channel,
            facts.pain_or_goal,
        ]
    )
    if has_independent_semantics:
        return False
    if observation.prior_reference.type != "none":
        return True
    return observation.primary_intent in {
        Intent.GENERAL_INFO.value,
        Intent.UNKNOWN.value,
        Intent.GREETING.value,
    }


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _strict_response_schema() -> Dict[str, Any]:
    schema = ReplyFrameSemanticResolution.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
