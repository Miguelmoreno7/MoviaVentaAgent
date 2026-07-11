"""Turn-local semantic resolution for replies to planner-authored questions.

The commercial contract stays unchanged.  A reply frame is only metadata on an
assistant turn which tells a small, focused resolver what the planner asked on
that turn.  It never becomes lead state or a competing semantic contract.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from movia_sales_agent.analyzer.contract_v3 import (
    AgentActionObservation,
    AgentCapabilityObservation,
    AnalyzerTurnObservation,
    RequirementUpdateIntent,
    evidence_span_in_message,
)
from movia_sales_agent.contracts.commercial import CTAType, MicroAction
from movia_sales_agent.services.openai_service import empty_usage, response_usage


REPLY_FRAME_ACTION_REQUIREMENT = "action_requirement"
REPLY_FRAME_LINK_START_CONFIRMATION = "link_start_confirmation"


class ReplyFrameSemanticResolution(BaseModel):
    """Private resolver schema; values deliberately reuse Contract V3.1 enums."""

    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")

    requested_agent_capabilities: List[AgentCapabilityObservation] = Field(default_factory=list)
    requested_agent_actions: List[AgentActionObservation] = Field(default_factory=list)
    action_requirement_selection: Literal["unknown", "answers_only", "external_actions_required"] = "unknown"
    start_or_link_confirmed: bool = False
    confirmation_evidence_span: Optional[str] = None
    requirement_update_intent: RequirementUpdateIntent = RequirementUpdateIntent.NO_CHANGE


def reply_frame_for_sales_plan(sales_plan: Any) -> Optional[Dict[str, Any]]:
    """Serialize an intentionally small semantic frame with the assistant turn."""

    micro_action = _value(getattr(sales_plan, "micro_action", None))
    cta_type = _value(getattr(sales_plan, "cta_type", None))
    if micro_action == MicroAction.ASK_ACTION_REQUIREMENT.value:
        return {"type": REPLY_FRAME_ACTION_REQUIREMENT}
    if (
        micro_action == MicroAction.ASK_PERMISSION_TO_SEND_LINK.value
        or cta_type == CTAType.ASK_PERMISSION_TO_SEND_LINK.value
    ):
        product = None
        if micro_action == MicroAction.RECOMMEND_MOVIA_CAPTURA.value:
            product = "movia_captura"
        elif micro_action == MicroAction.RECOMMEND_MOVIA_HIBRIDO.value:
            product = "movia_hibrido"
        frame = {"type": REPLY_FRAME_LINK_START_CONFIRMATION}
        if product:
            frame["product"] = product
        return frame
    return None


def reply_frame_from_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read new frames, with a metadata-only compatibility path for old turns."""

    analysis = message.get("analysis") if isinstance(message, dict) else None
    if isinstance(analysis, dict) and isinstance(analysis.get("reply_frame"), dict):
        return dict(analysis["reply_frame"])
    metadata = message.get("retrieval_metadata") if isinstance(message, dict) else None
    response_metadata = (metadata or {}).get("response_metadata") if isinstance(metadata, dict) else {}
    micro_action = str((response_metadata or {}).get("micro_action") or "")
    cta_type = str((response_metadata or {}).get("cta_type") or "")
    if micro_action == MicroAction.ASK_ACTION_REQUIREMENT.value:
        return {"type": REPLY_FRAME_ACTION_REQUIREMENT, "source": "legacy_response_metadata"}
    if micro_action == MicroAction.ASK_PERMISSION_TO_SEND_LINK.value or cta_type == CTAType.ASK_PERMISSION_TO_SEND_LINK.value:
        return {"type": REPLY_FRAME_LINK_START_CONFIRMATION, "source": "legacy_response_metadata"}
    return None


def latest_reply_frame(recent_messages: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for message in reversed(list(recent_messages or [])):
        if str(message.get("role") or "").lower() == "assistant":
            return reply_frame_from_message(message)
    return None


def merge_reply_frame_observation(
    observation: AnalyzerTurnObservation,
    resolution: ReplyFrameSemanticResolution,
    message: str,
) -> AnalyzerTurnObservation:
    """Union only literal, Contract-valid observations into the analyzer output."""

    actions = _union_observations(
        observation.requested_agent_actions,
        resolution.requested_agent_actions,
        message,
    )
    capabilities = _union_observations(
        observation.requested_agent_capabilities,
        resolution.requested_agent_capabilities,
        message,
    )
    intent = observation.requirement_update_intent
    if resolution.requirement_update_intent != RequirementUpdateIntent.NO_CHANGE.value:
        intent = resolution.requirement_update_intent
    return observation.model_copy(
        update={
            "requested_agent_actions": actions,
            "requested_agent_capabilities": capabilities,
            "requirement_update_intent": intent,
        }
    )


def _union_observations(existing: List[Any], additions: List[Any], message: str) -> List[Any]:
    merged = list(existing)
    # One canonical ontology action/capability is enough for a turn.  The main
    # analyzer and focused resolver can legitimately cite different literal
    # spans for the same value, which must not duplicate a requirement.
    seen = {_value(item.type) for item in merged}
    for item in additions:
        if not evidence_span_in_message(item.evidence_span, message):
            continue
        key = _value(item.type)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def resolve_reply_frame_with_usage(
    openai_service: Any,
    *,
    frame: Dict[str, Any],
    message: str,
) -> Tuple[Optional[ReplyFrameSemanticResolution], Dict[str, Any]]:
    """Call the focused semantic resolver only for a planner-authored frame."""

    if not getattr(openai_service, "enabled", False):
        return None, empty_usage("reply_frame", openai_service.settings.analysis_model, "disabled")
    frame_type = str(frame.get("type") or "")
    if frame_type not in {REPLY_FRAME_ACTION_REQUIREMENT, REPLY_FRAME_LINK_START_CONFIRMATION}:
        return None, empty_usage("reply_frame", openai_service.settings.analysis_model, "not_applicable")

    prompt = _resolver_prompt(frame_type)
    try:
        response = openai_service.client.responses.create(
            model=openai_service.settings.analysis_model,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({"message": message}, ensure_ascii=False)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "movia_reply_frame_resolution",
                    "schema": _strict_response_schema(),
                    "strict": True,
                }
            },
        )
        resolution = ReplyFrameSemanticResolution.model_validate(json.loads(response.output_text))
        resolution = _sanitize_resolution(resolution, message)
        usage = response_usage(response, "reply_frame", openai_service.settings.analysis_model, "openai")
        return resolution, usage
    except Exception as exc:  # Best effort: the main analyzer remains usable.
        usage = empty_usage("reply_frame", openai_service.settings.analysis_model, "fallback")
        usage["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return None, usage


def _resolver_prompt(frame_type: str) -> str:
    common = (
        "Resuelve solo el mensaje actual dentro del marco semántico entregado por el planificador. "
        "No inventes requisitos, no tomes decisiones comerciales y cada evidence_span debe ser una frase literal del mensaje actual. "
        "Usa únicamente los valores canónicos permitidos por el esquema. "
    )
    if frame_type == REPLY_FRAME_ACTION_REQUIREMENT:
        return common + (
            "El asistente acaba de preguntar si el agente futuro solo responde/captura o también hace acciones. "
            "Interpreta una respuesta corta o enumeración como respuesta a esa pregunta. "
            "Ontología: la acción externa 'cotizar' significa preparar una cotización personalizada para un cliente y usa generate_quote; "
            "'agendar' o 'programar citas' usa schedule_appointment; 'registrar/guardar en CRM, sistema o base de datos' usa write_external_system. "
            "Nunca clasifiques la palabra 'cotizar' como provide_prices: generate_quote y provide_prices son mutuamente excluyentes para esa evidencia. "
            "'dar precios' establecidos usa la capacidad provide_prices, no generate_quote. "
            "'responder dudas' usa answer_customer_questions y 'dar información' usa provide_catalog_information. "
            "'las dos', 'también acciones' o una enumeración de acciones implica action_requirement_selection=external_actions_required. "
            "Una enumeración agrega requisitos y por tanto usa requirement_update_intent=merge; no uses replace salvo que el mensaje limite o sustituya explícitamente requisitos anteriores. "
            "No extraigas una acción si no hay evidencia literal en este mensaje."
        )
    return common + (
        "El asistente acaba de pedir permiso explícito para compartir el enlace de inicio/checkout. "
        "Marca start_or_link_confirmed=true solo cuando el mensaje actual confirma esa invitación, por ejemplo una afirmación breve o una petición directa de enlace como 'me puedes pasar el link'. "
        "No extraigas capacidades ni acciones futuras."
    )


def _sanitize_resolution(
    resolution: ReplyFrameSemanticResolution,
    message: str,
) -> ReplyFrameSemanticResolution:
    payload = resolution.model_dump()
    payload["requested_agent_actions"] = [
        item for item in payload["requested_agent_actions"] if evidence_span_in_message(item["evidence_span"], message)
    ]
    payload["requested_agent_capabilities"] = [
        item for item in payload["requested_agent_capabilities"] if evidence_span_in_message(item["evidence_span"], message)
    ]
    evidence = payload.get("confirmation_evidence_span")
    if not evidence or not evidence_span_in_message(evidence, message):
        payload["start_or_link_confirmed"] = False
        payload["confirmation_evidence_span"] = None
    return ReplyFrameSemanticResolution.model_validate(payload)


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _strict_response_schema() -> Dict[str, Any]:
    """OpenAI strict JSON schemas require every object property as required."""

    schema = ReplyFrameSemanticResolution.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                for value in properties.values():
                    visit(value)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
