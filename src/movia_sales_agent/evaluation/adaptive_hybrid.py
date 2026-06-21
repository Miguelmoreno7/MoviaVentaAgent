from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from movia_sales_agent.agent.graph import MoviaSalesAgent, merge_usage
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.contracts.commercial import MacroAction, ObjectionStrength
from movia_sales_agent.services.openai_service import json_default, response_usage


DEFAULT_ADAPTIVE_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "evaluations" / "adaptive-hybrid"
MAX_TURNS_PER_CONVERSATION = 10
SEEDS = [101, 202]


@dataclass(frozen=True)
class AdaptivePersona:
    persona_id: str
    persona: str
    hidden_goal: str
    hidden_constraints: List[str]
    starting_message: str
    likely_fit: str
    possible_outcomes: List[str]


PERSONAS: List[AdaptivePersona] = [
    AdaptivePersona(
        persona_id="AH-001-high-intent-dental",
        persona="High-intent dental clinic owner who needs WhatsApp answers and lead-data capture.",
        hidden_goal="Clarify price and process, then request the app link if the agent is clear.",
        hidden_constraints=[
            "Needs answers, lead-data capture and WhatsApp.",
            "Should only commit after understanding price and how to start.",
        ],
        starting_message="Tengo una clínica dental y quiero que respondan dudas por WhatsApp y capturen datos de pacientes.",
        likely_fit="movia_captura",
        possible_outcomes=["product_confirmed", "registration_intent"],
    ),
    AdaptivePersona(
        persona_id="AH-002-demo-first-barbershop",
        persona="Demo-first barbershop owner who is interested but does not want to purchase before testing.",
        hidden_goal="Ask about the 10-message demo, then request the application link to try the platform.",
        hidden_constraints=[
            "Demo interest is not purchase commitment.",
            "Must not accept a required deposit for demo.",
        ],
        starting_message="Tengo una barbería y me interesa, pero primero quiero probar un demo antes de pagar.",
        likely_fit="movia_captura",
        possible_outcomes=["demo_intent"],
    ),
    AdaptivePersona(
        persona_id="AH-003-price-sensitive-restaurant",
        persona="Price-sensitive restaurant owner with a real monthly-price objection.",
        hidden_goal="Understand value, may ask for the link before fully resolving the objection.",
        hidden_constraints=[
            "Has a genuine monthly-price objection.",
            "A link request does not mean the objection disappeared.",
        ],
        starting_message="Tengo un restaurante y me interesa automatizar WhatsApp, pero me preocupa la mensualidad.",
        likely_fit="movia_captura",
        possible_outcomes=["qualified_but_not_ready", "registration_intent", "conversation_stalled"],
    ),
    AdaptivePersona(
        persona_id="AH-004-unsupported-channel",
        persona="Lead who primarily requires Instagram or Facebook today.",
        hidden_goal="Pressure the agent to sell unsupported channels as active.",
        hidden_constraints=[
            "Needs Instagram or Facebook today more than WhatsApp.",
            "Should not buy if the agent is honest that those channels are not active.",
        ],
        starting_message="Yo necesito que el agente responda Instagram y Facebook desde hoy, no tanto WhatsApp.",
        likely_fit="not_current_fit",
        possible_outcomes=["not_current_fit", "future_interest"],
    ),
    AdaptivePersona(
        persona_id="AH-005-supplier-operations",
        persona="Supplier operations lead who needs quotes, tickets, order processing and external-system interaction.",
        hidden_goal="Find whether standard Híbrido fits or custom scope review is needed.",
        hidden_constraints=[
            "Needs multiple operational actions.",
            "Captura must not be accepted for external-system actions.",
        ],
        starting_message="Mis proveedores mandan tickets y fotos por WhatsApp; necesito cotizar y registrar pedidos en mi sistema.",
        likely_fit="movia_hibrido_or_custom_review",
        possible_outcomes=["product_confirmed", "handoff_requested", "qualified_but_not_ready"],
    ),
    AdaptivePersona(
        persona_id="AH-006-skeptical-indecisive",
        persona="Skeptical and indecisive lead who challenges credibility and may request the link only to review.",
        hidden_goal="Test whether the agent creates trust without forcing a close.",
        hidden_constraints=[
            "May ask unrelated questions or change topic.",
            "Requesting the link is only for review unless explicitly committing.",
        ],
        starting_message="Vi su anuncio, pero suena como otro bot más. ¿Por qué debería confiar en MovIA?",
        likely_fit="unknown",
        possible_outcomes=["qualified_but_not_ready", "conversation_stalled", "registration_intent"],
    ),
    AdaptivePersona(
        persona_id="AH-007-requirement-changing-memory",
        persona="Lead who changes requirements and later references prior facts.",
        hidden_goal="Start with external action, narrow to answers only, then reference price or deposit.",
        hidden_constraints=[
            "Latest valid replacement should control active requirements.",
            "Official facts remain authoritative; memory only supports context.",
        ],
        starting_message="Quiero que el agente agende citas por WhatsApp, aunque quizá después solo necesite que responda dudas.",
        likely_fit="movia_captura_after_replacement",
        possible_outcomes=["product_confirmed", "qualified_but_not_ready"],
    ),
]


class SimulatorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_message: Optional[str] = None
    should_stop: bool = False
    terminal_outcome: Optional[str] = None
    rationale: str = ""
    interest_level: float = Field(default=0.5, ge=0.0, le=1.0)
    objection_state: str = "none"


class ConversationJudgeScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_answering: float = Field(ge=0.0, le=1.0)
    commercial_progression: float = Field(ge=0.0, le=1.0)
    product_fit: float = Field(ge=0.0, le=1.0)
    objection_handling: float = Field(ge=0.0, le=1.0)
    memory_and_consistency: float = Field(ge=0.0, le=1.0)
    closing_timing: float = Field(ge=0.0, le=1.0)
    friction_control: float = Field(ge=0.0, le=1.0)
    response_quality: float = Field(ge=0.0, le=1.0)
    outcome_score: float = Field(ge=0.0, le=1.0)
    rationale: str


SIMULATOR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "next_message": {"type": ["string", "null"]},
        "should_stop": {"type": "boolean"},
        "terminal_outcome": {
            "type": ["string", "null"],
            "enum": [
                "registration_intent",
                "demo_intent",
                "product_confirmed",
                "qualified_but_not_ready",
                "not_current_fit",
                "explicit_rejection",
                "handoff_requested",
                "conversation_stalled",
                "max_turns_reached",
                None,
            ],
        },
        "rationale": {"type": "string"},
        "interest_level": {"type": "number", "minimum": 0, "maximum": 1},
        "objection_state": {"type": "string"},
    },
    "required": [
        "next_message",
        "should_stop",
        "terminal_outcome",
        "rationale",
        "interest_level",
        "objection_state",
    ],
}
JUDGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "question_answering": {"type": "number", "minimum": 0, "maximum": 1},
        "commercial_progression": {"type": "number", "minimum": 0, "maximum": 1},
        "product_fit": {"type": "number", "minimum": 0, "maximum": 1},
        "objection_handling": {"type": "number", "minimum": 0, "maximum": 1},
        "memory_and_consistency": {"type": "number", "minimum": 0, "maximum": 1},
        "closing_timing": {"type": "number", "minimum": 0, "maximum": 1},
        "friction_control": {"type": "number", "minimum": 0, "maximum": 1},
        "response_quality": {"type": "number", "minimum": 0, "maximum": 1},
        "outcome_score": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
    },
    "required": [
        "question_answering",
        "commercial_progression",
        "product_fit",
        "objection_handling",
        "memory_and_consistency",
        "closing_timing",
        "friction_control",
        "response_quality",
        "outcome_score",
        "rationale",
    ],
}


def run_adaptive_hybrid_pilot(
    *,
    output_root: Path = DEFAULT_ADAPTIVE_OUTPUT_ROOT,
    settings: Optional[Settings] = None,
    max_turns: int = MAX_TURNS_PER_CONVERSATION,
) -> Dict[str, Any]:
    settings = settings or get_settings()
    if not settings.openai_api_key or settings.disable_openai:
        raise RuntimeError("OPENAI_API_KEY is required and MOVIA_DISABLE_OPENAI must be false.")
    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    agent = MoviaSalesAgent(settings)
    run_id = _make_run_id()
    started_at = _now()
    conversations: List[Dict[str, Any]] = []
    usage = _empty_usage_totals()

    for persona in PERSONAS:
        for seed in SEEDS:
            conversation, conversation_usage = _run_conversation(
                run_id=run_id,
                persona=persona,
                seed=seed,
                max_turns=max_turns,
                agent=agent,
                client=client,
                settings=settings,
            )
            conversations.append(conversation)
            usage = _merge_usage_totals(usage, conversation_usage)

    completed_at = _now()
    gate_summary = _gate_summary(conversations)
    aggregate_scores = _aggregate_scores(conversations)
    passed = _passed(gate_summary, aggregate_scores)
    result = {
        "run_id": run_id,
        "suite_type": "adaptive_hybrid",
        "started_at": started_at,
        "completed_at": completed_at,
        "analysis_model": settings.analysis_model,
        "response_model": settings.response_model,
        "simulator_model": settings.eval_model,
        "judge_model": settings.eval_model,
        "persona_count": len(PERSONAS),
        "seed_count": len(SEEDS),
        "conversation_count": len(conversations),
        "max_turns_per_conversation": max_turns,
        "conversations": conversations,
        "gate_summary": gate_summary,
        "aggregate_scores": aggregate_scores,
        "cost_latency": _cost_latency(conversations, usage),
        "passed": passed,
        "final_status": "ADAPTIVE HYBRID PILOT PASSED" if passed else "ADAPTIVE HYBRID PILOT FAILED",
        "ready_for_limited_internal_pilot": bool(passed),
        "ready_for_external_leads": False,
    }
    output_dir = output_root / run_id
    _write_artifacts(result, output_dir)
    return {**result, "output_dir": str(output_dir)}


def _run_conversation(
    *,
    run_id: str,
    persona: AdaptivePersona,
    seed: int,
    max_turns: int,
    agent: MoviaSalesAgent,
    client: OpenAI,
    settings: Settings,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    conversation_id = f"{persona.persona_id}-seed-{seed}"
    external_user_id = f"adaptive-hybrid:{run_id}:{conversation_id}"
    turns: List[Dict[str, Any]] = []
    transcript: List[Dict[str, str]] = []
    usage = _empty_usage_totals()
    lead_message = persona.starting_message
    terminal_outcome: Optional[str] = None
    terminal_reason = ""
    stalled_count = 0
    previous_progress_key = ""
    started = perf_counter()

    for turn_number in range(1, max_turns + 1):
        transcript.append({"role": "lead", "content": lead_message})
        turn_started = perf_counter()
        try:
            response = agent.invoke(
                lead_message,
                lead_external_id=external_user_id,
                channel="evaluation",
                external_message_id=f"adaptive:{run_id}:{conversation_id}:t{turn_number}",
            )
            latency_ms = round((perf_counter() - turn_started) * 1000, 2)
            turn_record = _turn_record(
                turn_number=turn_number,
                user_input=lead_message,
                response=response,
                latency_ms=latency_ms,
            )
            turn_record["deterministic_violations"] = _deterministic_violations(
                turn_record=turn_record,
                previous_turns=turns,
                persona=persona,
            )
            turns.append(turn_record)
            transcript.append({"role": "agent", "content": response.response})
            usage = _merge_usage_totals(usage, {"agent": response.token_usage})
            hard_codes = [item["code"] for item in turn_record["deterministic_violations"] if item.get("hard")]
            if hard_codes:
                terminal_outcome = "conversation_stalled"
                terminal_reason = "hard_failure:" + ",".join(hard_codes)
                break
        except Exception as exc:
            latency_ms = round((perf_counter() - turn_started) * 1000, 2)
            turn_record = {
                "turn_id": turn_number,
                "user_input": lead_message,
                "agent_response": "",
                "latency_ms": latency_ms,
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                "deterministic_violations": [
                    {"code": "provider_error", "reason": str(exc)[:300], "hard": True}
                ],
            }
            turns.append(turn_record)
            terminal_outcome = "conversation_stalled"
            terminal_reason = "agent_error"
            break

        progress_key = _progress_key(turn_record)
        stalled_count = stalled_count + 1 if progress_key == previous_progress_key else 0
        previous_progress_key = progress_key
        deterministic_outcome = _deterministic_terminal_outcome(turns, persona)
        if deterministic_outcome:
            terminal_outcome, terminal_reason = deterministic_outcome
            break
        if stalled_count >= 2:
            terminal_outcome = "conversation_stalled"
            terminal_reason = "two_consecutive_turns_without_meaningful_progress"
            break

        sim_started = perf_counter()
        decision, sim_usage = _simulate_next_lead_turn(
            client=client,
            settings=settings,
            persona=persona,
            seed=seed,
            turn_number=turn_number,
            remaining_turns=max_turns - turn_number,
            transcript=transcript,
            last_turn=turns[-1],
        )
        usage = _merge_usage_totals(usage, {"simulator": sim_usage})
        turns[-1]["simulator_latency_ms"] = round((perf_counter() - sim_started) * 1000, 2)
        turns[-1]["simulator_decision"] = decision.model_dump()
        if decision.should_stop:
            terminal_outcome = decision.terminal_outcome or "conversation_stalled"
            terminal_reason = decision.rationale
            break
        if not decision.next_message:
            terminal_outcome = "conversation_stalled"
            terminal_reason = "simulator_returned_no_next_message"
            break
        lead_message = decision.next_message

    if terminal_outcome is None:
        terminal_outcome = "max_turns_reached"
        terminal_reason = "maximum turn budget reached"

    judge_started = perf_counter()
    judge, judge_usage = _judge_conversation(
        client=client,
        settings=settings,
        persona=persona,
        seed=seed,
        terminal_outcome=terminal_outcome,
        terminal_reason=terminal_reason,
        turns=turns,
        transcript=transcript,
    )
    usage = _merge_usage_totals(usage, {"judge": judge_usage})
    conversation = {
        "conversation_id": conversation_id,
        "persona_id": persona.persona_id,
        "persona": persona.persona,
        "seed": seed,
        "hidden_goal_summary": persona.hidden_goal,
        "hidden_constraints": persona.hidden_constraints,
        "likely_fit": persona.likely_fit,
        "possible_outcomes": persona.possible_outcomes,
        "terminal_outcome": terminal_outcome,
        "terminal_reason": terminal_reason,
        "turn_count": len(turns),
        "turns": turns,
        "transcript": transcript,
        "product_progression": _product_progression(turns),
        "objection_progression": _objection_progression(turns),
        "link_delivery_events": _link_delivery_events(turns),
        "response_fulfillment_policy_decisions": [
            (turn.get("response_metadata") or {}).get("response_fulfillment_policy") or {}
            for turn in turns
        ],
        "knowledge_sources": [
            {
                "turn_id": turn.get("turn_id"),
                "structured_sources": turn.get("knowledge_plan", {}).get("structured_sources") or [],
                "json_sources": turn.get("knowledge_plan", {}).get("json_sources") or [],
                "knowledge_needs": turn.get("knowledge_plan", {}).get("knowledge_needs") or [],
            }
            for turn in turns
        ],
        "judge_scores": judge.model_dump(),
        "deterministic_violations": [
            violation for turn in turns for violation in turn.get("deterministic_violations") or []
        ],
        "token_usage": usage,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "judge_latency_ms": round((perf_counter() - judge_started) * 1000, 2),
    }
    return conversation, usage


def _turn_record(*, turn_number: int, user_input: str, response: Any, latency_ms: float) -> Dict[str, Any]:
    metadata = response.response_metadata or {}
    return {
        "turn_id": turn_number,
        "user_input": user_input,
        "agent_response": response.response,
        "response_messages": response.response_messages,
        "analysis": response.analysis.model_dump(),
        "normalized_turn": metadata.get("normalized_turn") or {},
        "lead_state": response.lead_state,
        "selected_action": response.selected_action,
        "knowledge_plan": response.knowledge_plan,
        "retrieved_sources": response.retrieved_sources,
        "response_metadata": metadata,
        "response_source": metadata.get("response_source"),
        "token_usage": response.token_usage,
        "latency_ms": latency_ms,
    }


def _simulate_next_lead_turn(
    *,
    client: OpenAI,
    settings: Settings,
    persona: AdaptivePersona,
    seed: int,
    turn_number: int,
    remaining_turns: int,
    transcript: List[Dict[str, str]],
    last_turn: Dict[str, Any],
) -> Tuple[SimulatorDecision, Dict[str, Any]]:
    prompt = (
        "Eres un simulador de lead para evaluar un agente de preventa de MovIA. "
        "Reacciona naturalmente a la última respuesta real del agente. "
        "No ayudes al agente a pasar, no veas ni inventes criterios de evaluación, conserva las restricciones ocultas. "
        "Si la conversación ya llegó a un resultado natural, marca should_stop=true. "
        "Un link recibido no significa compra automáticamente. Responde en español mexicano y con un solo mensaje breve."
    )
    payload = {
        "persona": persona.persona,
        "hidden_goal": persona.hidden_goal,
        "hidden_constraints": persona.hidden_constraints,
        "likely_fit": persona.likely_fit,
        "possible_outcomes": persona.possible_outcomes,
        "seed": seed,
        "turn_number": turn_number,
        "remaining_turn_budget": remaining_turns,
        "last_agent_response": last_turn.get("agent_response"),
        "last_agent_action": last_turn.get("selected_action"),
        "last_normalized_state": last_turn.get("normalized_turn"),
        "link_delivery_events_so_far": _link_delivery_events([last_turn]),
        "transcript": transcript[-10:],
    }
    response = client.responses.create(
        model=settings.eval_model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=json_default)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "adaptive_hybrid_simulator_decision",
                "schema": SIMULATOR_SCHEMA,
                "strict": True,
            }
        },
    )
    usage = response_usage(response, "simulator", settings.eval_model, "openai")
    return SimulatorDecision.model_validate_json(response.output_text), usage


def _judge_conversation(
    *,
    client: OpenAI,
    settings: Settings,
    persona: AdaptivePersona,
    seed: int,
    terminal_outcome: str,
    terminal_reason: str,
    turns: List[Dict[str, Any]],
    transcript: List[Dict[str, str]],
) -> Tuple[ConversationJudgeScores, Dict[str, Any]]:
    prompt = (
        "Eres juez de una evaluación Adaptive Hybrid de un agente de preventa de MovIA. "
        "Califica de 0 a 1. Una no-venta correcta puede tener alta progresión. "
        "No penalices diferencias exactas de stage/macro/micro/CTA si la conversación fue comercialmente correcta. "
        "Distingue link_delivered, closing_started y purchase_commitment."
    )
    payload = {
        "persona": persona.persona,
        "hidden_goal": persona.hidden_goal,
        "hidden_constraints": persona.hidden_constraints,
        "seed": seed,
        "terminal_outcome": terminal_outcome,
        "terminal_reason": terminal_reason,
        "transcript": transcript,
        "key_normalized_state_changes": [
            {
                "turn_id": turn.get("turn_id"),
                "normalized_turn": turn.get("normalized_turn"),
                "selected_action": turn.get("selected_action"),
                "violations": turn.get("deterministic_violations"),
            }
            for turn in turns
        ],
        "product_recommendations": _product_progression(turns),
        "objection_timeline": _objection_progression(turns),
        "link_delivery_events": _link_delivery_events(turns),
    }
    response = client.responses.create(
        model=settings.eval_model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=json_default)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "adaptive_hybrid_conversation_judge",
                "schema": JUDGE_SCHEMA,
                "strict": True,
            }
        },
    )
    usage = response_usage(response, "judge", settings.eval_model, "openai")
    return ConversationJudgeScores.model_validate_json(response.output_text), usage


def _deterministic_violations(
    *, turn_record: Dict[str, Any], previous_turns: Sequence[Dict[str, Any]], persona: AdaptivePersona
) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    text = _normalize(turn_record.get("agent_response") or "")
    user_text = _normalize(turn_record.get("user_input") or "")
    action = turn_record.get("selected_action") or {}
    normalized = turn_record.get("normalized_turn") or {}
    metadata = turn_record.get("response_metadata") or {}
    policy = metadata.get("response_fulfillment_policy") or {}
    knowledge = turn_record.get("knowledge_plan") or {}

    if turn_record.get("response_source") != "openai":
        violations.append(_violation("provider_fallback", "Response source was not OpenAI.", True))
    if _claims_unsupported_channel_available(text):
        violations.append(_violation("unsupported_channel_claim", "Facebook/Instagram presented as available today.", True))
    if _captura_promised_external_actions(text):
        violations.append(_violation("captura_promised_external_actions", "Captura was described as performing external actions.", True))
    if _commercial_fact_error(text):
        violations.append(_violation("commercial_fact_error", "Detected likely incorrect official price or payment fact.", True))
    if _demo_requires_deposit(text, user_text):
        violations.append(_violation("demo_deposit_error", "Demo was described as requiring deposit.", True))
    link_requested = bool(turn_record.get("analysis", {}).get("explicit_start_intent"))
    link_delivered = _official_link_delivered(text)
    if link_requested and not link_delivered and not normalized.get("product_unavailable") and not normalized.get("unsupported_scope"):
        violations.append(_violation("official_link_requested_not_delivered", "User requested link but official app link was not delivered.", True))
    if link_requested and link_delivered:
        if not _link_before_continuation(turn_record.get("agent_response") or ""):
            violations.append(_violation("link_not_fulfilled_first", "Link was not fulfilled before continuation.", False))
        if _question_count(turn_record.get("agent_response") or "") > 1:
            violations.append(_violation("too_many_continuation_questions", "More than one continuation question after link.", False))
        if _asked_broad_discovery_after_link(turn_record):
            violations.append(_violation("broad_discovery_after_link", "Broad discovery was asked after delivering link.", False))
        if "official_app_link" not in set(policy.get("mandatory_fulfillments") or []):
            violations.append(_violation("response_fulfillment_policy_missing", "Link request did not activate official_app_link fulfillment.", False))
        if "postgres.official_links" not in set(knowledge.get("structured_sources") or []):
            violations.append(_violation("mandatory_source_not_loaded", "Official links source was not loaded for link fulfillment.", True))
    if _wrong_product_direct_close(turn_record):
        violations.append(_violation("wrong_product_direct_close", "Direct close used unsafe or unavailable product.", True))
    if _recommendation_repeated_after_acceptance(turn_record, previous_turns):
        violations.append(_violation("recommendation_repeated_after_acceptance", "Product recommendation repeated after explicit product acceptance.", False))
    if _repeated_known_slot_question(turn_record, previous_turns):
        violations.append(_violation("repeated_known_slot_question", "Agent repeated a known-slot question.", False))
    if persona.persona_id == "AH-004-unsupported-channel" and action.get("macro_action") == MacroAction.DIRECT_CLOSE.value:
        violations.append(_violation("scope_overpromise", "Unsupported-channel persona was moved to direct close.", True))
    return violations


def _deterministic_terminal_outcome(
    turns: Sequence[Dict[str, Any]], persona: AdaptivePersona
) -> Optional[Tuple[str, str]]:
    last = turns[-1]
    text = _normalize(last.get("agent_response") or "")
    user_text = _normalize(last.get("user_input") or "")
    action = last.get("selected_action") or {}
    normalized = last.get("normalized_turn") or {}
    hard = [v for v in last.get("deterministic_violations") or [] if v.get("hard")]
    if hard:
        return ("conversation_stalled", "hard_failure")
    if "no me interesa" in user_text or "lo dejo" in user_text:
        return ("explicit_rejection", "lead explicitly rejected")
    if "miguel" in text and action.get("macro_action") == MacroAction.HANDOFF_TO_MIGUEL.value:
        return ("handoff_requested", "agent routed to Miguel")
    if persona.persona_id == "AH-004-unsupported-channel" and any(
        phrase in text for phrase in ["instagram", "facebook"]
    ) and any(phrase in text for phrase in ["proceso", "no esta disponible", "no están disponibles", "whatsapp"]):
        return ("not_current_fit", "unsupported channel limitation explained")
    if "demo" in user_text and _official_link_delivered(text):
        return ("demo_intent", "lead chose demo path and received link")
    if normalized.get("selected_product") and _official_link_delivered(text):
        return ("registration_intent", "selected product and registration link delivered")
    return None


def _gate_summary(conversations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    violations = [v for c in conversations for v in c.get("deterministic_violations") or []]
    hard = [v for v in violations if v.get("hard")]
    counts: Dict[str, int] = {}
    for violation in violations:
        counts[violation["code"]] = counts.get(violation["code"], 0) + 1
    return {
        "hard_failures": len(hard),
        "provider_fallbacks": counts.get("provider_fallback", 0),
        "commercial_fact_errors": counts.get("commercial_fact_error", 0),
        "policy_errors": counts.get("policy_error", 0) + counts.get("demo_deposit_error", 0),
        "scope_overpromises": counts.get("scope_overpromise", 0),
        "unsupported_channel_claims": counts.get("unsupported_channel_claim", 0),
        "wrong_product_direct_closes": counts.get("wrong_product_direct_close", 0),
        "captura_promised_external_actions": counts.get("captura_promised_external_actions", 0),
        "official_link_requested_not_delivered": counts.get("official_link_requested_not_delivered", 0),
        "demo_described_as_requiring_deposit": counts.get("demo_deposit_error", 0),
        "violation_counts": counts,
        "violations": violations,
    }


def _aggregate_scores(conversations: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    dimensions = [
        "question_answering",
        "commercial_progression",
        "product_fit",
        "objection_handling",
        "memory_and_consistency",
        "closing_timing",
        "friction_control",
        "response_quality",
        "outcome_score",
    ]
    result = {}
    for dimension in dimensions:
        values = [float((c.get("judge_scores") or {}).get(dimension) or 0.0) for c in conversations]
        result[dimension] = round(sum(values) / len(values), 4) if values else 0.0
    return result


def _passed(gates: Dict[str, Any], scores: Dict[str, float]) -> bool:
    if gates.get("hard_failures", 0) > 0:
        return False
    hard_gate_keys = [
        "provider_fallbacks",
        "commercial_fact_errors",
        "policy_errors",
        "scope_overpromises",
        "unsupported_channel_claims",
        "wrong_product_direct_closes",
        "captura_promised_external_actions",
        "official_link_requested_not_delivered",
        "demo_described_as_requiring_deposit",
    ]
    if any(gates.get(key, 0) > 0 for key in hard_gate_keys):
        return False
    return (
        scores.get("outcome_score", 0.0) >= 0.75
        and scores.get("response_quality", 0.0) >= 0.80
        and scores.get("commercial_progression", 0.0) >= 0.70
        and scores.get("closing_timing", 0.0) >= 0.75
        and scores.get("friction_control", 0.0) >= 0.80
    )


def _write_artifacts(result: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "run.json", _without_output_dir(result))
    _write_json(output_dir / "conversation_scores.json", _conversation_scores(result))
    _write_json(output_dir / "cost_latency.json", result["cost_latency"])
    (output_dir / "summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    (output_dir / "conversations.md").write_text(_conversations_markdown(result), encoding="utf-8")


def _summary_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# MovIA Adaptive Hybrid Pilot: {result['run_id']}",
        "",
        f"- **Status:** {result['final_status']}",
        f"- **Conversations:** {result['conversation_count']}",
        f"- **Max turns:** {result['max_turns_per_conversation']}",
        f"- **Analyzer model:** {result['analysis_model']}",
        f"- **Response model:** {result['response_model']}",
        f"- **Simulator/Judge model:** {result['judge_model']}",
        f"- **ready_for_limited_internal_pilot:** `{str(result['ready_for_limited_internal_pilot']).lower()}`",
        f"- **ready_for_external_leads:** `{str(result['ready_for_external_leads']).lower()}`",
        "",
        "## Gates",
        "",
        "| Gate | Count |",
        "|---|---:|",
    ]
    for key, value in result["gate_summary"].items():
        if key in {"violations", "violation_counts"}:
            continue
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Aggregate Scores", "", "| Dimension | Score |", "|---|---:|"])
    for key, value in result["aggregate_scores"].items():
        lines.append(f"| {key} | {value:.3f} |")
    lines.extend(["", "## Cost And Latency", "", "```json", json.dumps(result["cost_latency"], indent=2, ensure_ascii=False), "```"])
    lines.extend(["", result["final_status"]])
    return "\n".join(lines)


def _conversations_markdown(result: Dict[str, Any]) -> str:
    lines = [f"# Adaptive Hybrid Conversations: {result['run_id']}", ""]
    for conversation in result["conversations"]:
        lines.extend(
            [
                f"## {conversation['conversation_id']}",
                "",
                f"- **Persona:** {conversation['persona']}",
                f"- **Seed:** {conversation['seed']}",
                f"- **Hidden goal:** {conversation['hidden_goal_summary']}",
                f"- **Terminal outcome:** `{conversation['terminal_outcome']}`",
                f"- **Turn count:** {conversation['turn_count']}",
                f"- **Judge scores:** `{json.dumps(conversation['judge_scores'], ensure_ascii=False)}`",
                f"- **Violations:** `{json.dumps(conversation['deterministic_violations'], ensure_ascii=False)}`",
                "",
            ]
        )
        for message in conversation["transcript"]:
            label = "Lead" if message["role"] == "lead" else "Agent"
            lines.extend([f"**{label}:** {message['content']}", ""])
    return "\n".join(lines)


def _cost_latency(conversations: Sequence[Dict[str, Any]], usage: Dict[str, Any]) -> Dict[str, Any]:
    total_turns = sum(int(c.get("turn_count") or 0) for c in conversations)
    total_latency = sum(float(c.get("latency_ms") or 0.0) for c in conversations)
    return {
        "agent_tokens": _usage_total(usage.get("agent")),
        "simulator_tokens": _usage_total(usage.get("simulator")),
        "judge_tokens": _usage_total(usage.get("judge")),
        "embedding_tokens": _operation_tokens(usage.get("agent"), "embedding"),
        "total_tokens": sum(_usage_total(usage.get(key)) for key in ["agent", "simulator", "judge"]),
        "estimated_cost_usd": None,
        "pricing_note": "Cost estimate not computed; token usage is recorded for external pricing calculation.",
        "conversation_count": len(conversations),
        "turn_count": total_turns,
        "average_latency_ms_per_conversation": round(total_latency / len(conversations), 2) if conversations else 0.0,
        "average_latency_ms_per_turn": round(total_latency / total_turns, 2) if total_turns else 0.0,
        "retry_count": 0,
    }


def _conversation_scores(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "conversation_id": c["conversation_id"],
            "persona_id": c["persona_id"],
            "seed": c["seed"],
            "terminal_outcome": c["terminal_outcome"],
            "turn_count": c["turn_count"],
            "judge_scores": c["judge_scores"],
            "deterministic_violations": c["deterministic_violations"],
        }
        for c in result["conversations"]
    ]


def _without_output_dir(result: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in result.items() if key != "output_dir"}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")


def _empty_usage_totals() -> Dict[str, Any]:
    return {"agent": {}, "simulator": {}, "judge": {}}


def _merge_usage_totals(existing: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = {key: dict(existing.get(key) or {}) for key in ["agent", "simulator", "judge"]}
    for bucket, usage in update.items():
        if not usage:
            continue
        if usage.get("calls"):
            for call in usage.get("calls") or []:
                merged[bucket] = merge_usage(merged.get(bucket, {}), call)
        else:
            merged[bucket] = merge_usage(merged.get(bucket, {}), usage)
    return merged


def _usage_total(usage: Optional[Dict[str, Any]]) -> int:
    return int(((usage or {}).get("total") or {}).get("total_tokens") or 0)


def _operation_tokens(usage: Optional[Dict[str, Any]], operation: str) -> int:
    return sum(
        int(call.get("total_tokens") or 0)
        for call in (usage or {}).get("calls") or []
        if call.get("operation") == operation
    )


def _product_progression(turns: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "turn_id": turn.get("turn_id"),
            "requested_product": (turn.get("normalized_turn") or {}).get("requested_product"),
            "active_product_context": (turn.get("normalized_turn") or {}).get("active_product_context"),
            "selected_product": (turn.get("normalized_turn") or {}).get("selected_product"),
            "recommended_product": (turn.get("normalized_turn") or {}).get("recommended_product"),
            "macro_action": (turn.get("selected_action") or {}).get("macro_action"),
            "micro_action": (turn.get("selected_action") or {}).get("micro_action"),
        }
        for turn in turns
    ]


def _objection_progression(turns: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "turn_id": turn.get("turn_id"),
            "objection_type": (turn.get("analysis") or {}).get("objection_type"),
            "objection_strength": (turn.get("analysis") or {}).get("objection_strength"),
            "objection_relation": (turn.get("analysis") or {}).get("objection_relation"),
            "active_objection": (turn.get("lead_state") or {}).get("active_objection"),
        }
        for turn in turns
    ]


def _link_delivery_events(turns: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events = []
    for turn in turns:
        requested = bool((turn.get("analysis") or {}).get("explicit_start_intent"))
        delivered = _official_link_delivered(_normalize(turn.get("agent_response") or ""))
        if requested or delivered:
            events.append(
                {
                    "turn_id": turn.get("turn_id"),
                    "link_requested": requested,
                    "link_delivered": delivered,
                    "macro_action": (turn.get("selected_action") or {}).get("macro_action"),
                    "fulfillment_policy": (turn.get("response_metadata") or {}).get("response_fulfillment_policy") or {},
                }
            )
    return events


def _progress_key(turn: Dict[str, Any]) -> str:
    normalized = turn.get("normalized_turn") or {}
    action = turn.get("selected_action") or {}
    return "|".join(
        str(value or "")
        for value in [
            normalized.get("requirement_class"),
            normalized.get("selected_product"),
            normalized.get("recommended_product"),
            action.get("macro_action"),
            action.get("reason_code"),
        ]
    )


def _official_link_delivered(text: str) -> bool:
    return "app.moviatech.com.mx" in text


def _link_before_continuation(response: str) -> bool:
    link_index = response.find("app.moviatech.com.mx")
    question_index = response.find("?")
    return link_index >= 0 and (question_index < 0 or link_index < question_index)


def _question_count(response: str) -> int:
    return max(response.count("?"), response.count("¿"))


def _asked_broad_discovery_after_link(turn: Dict[str, Any]) -> bool:
    if not _official_link_delivered(_normalize(turn.get("agent_response") or "")):
        return False
    policy = ((turn.get("response_metadata") or {}).get("response_fulfillment_policy") or {})
    if policy.get("next_question_policy") == "replace_minimal":
        return False
    key = (turn.get("selected_action") or {}).get("next_question_key")
    return key in {"automation_need", "business_type", "main_channel", "pain_or_goal", "action_requirement"}


def _wrong_product_direct_close(turn: Dict[str, Any]) -> bool:
    action = turn.get("selected_action") or {}
    normalized = turn.get("normalized_turn") or {}
    if action.get("macro_action") != MacroAction.DIRECT_CLOSE.value:
        return False
    product = normalized.get("selected_product") or normalized.get("confirmed_product")
    return product not in {"movia_captura", "movia_hibrido"} or bool(
        normalized.get("unsupported_scope") or normalized.get("custom_scope_review_required")
    )


def _recommendation_repeated_after_acceptance(turn: Dict[str, Any], previous_turns: Sequence[Dict[str, Any]]) -> bool:
    if (turn.get("selected_action") or {}).get("macro_action") != MacroAction.RECOMMEND_SOLUTION.value:
        return False
    return any((prev.get("normalized_turn") or {}).get("selected_product") for prev in previous_turns)


def _repeated_known_slot_question(turn: Dict[str, Any], previous_turns: Sequence[Dict[str, Any]]) -> bool:
    key = (turn.get("selected_action") or {}).get("next_question_key")
    if not key:
        return False
    for previous in previous_turns:
        known = set((previous.get("normalized_turn") or {}).get("known_slots") or [])
        if key in known:
            return True
    return False


def _claims_unsupported_channel_available(text: str) -> bool:
    if not any(channel in text for channel in ["instagram", "facebook"]):
        return False
    available_claims = ["disponible", "listo", "activo", "ya podemos", "desde hoy"]
    limitation_terms = ["proceso", "no esta", "no estan", "no está", "no están", "whatsapp"]
    return any(term in text for term in available_claims) and not any(term in text for term in limitation_terms)


def _captura_promised_external_actions(text: str) -> bool:
    if "captura" not in text:
        return False
    action_terms = ["registrar pedidos", "sistema externo", "escribir en", "agenda citas", "agendar citas", "cotizar automaticamente"]
    negators = ["no registra", "no puede", "no agenda", "no escribe", "hibrido"]
    return any(term in text for term in action_terms) and not any(term in text for term in negators)


def _commercial_fact_error(text: str) -> bool:
    wrong_price_patterns = [
        r"captura[^.]{0,80}\$?\s*7[,\.]?500",
        r"h[ií]brido[^.]{0,80}\$?\s*4[,\.]?900",
        r"mensualidad[^.]{0,50}captura[^.]{0,50}\$?\s*550",
        r"mensualidad[^.]{0,50}h[ií]brido[^.]{0,50}\$?\s*450",
    ]
    if any(re.search(pattern, text) for pattern in wrong_price_patterns):
        return True
    if "deposito" in text or "depósito" in text:
        if "100%" in text and "seguro" not in text:
            return True
    return False


def _demo_requires_deposit(text: str, user_text: str) -> bool:
    return "demo" in user_text and "deposit" in text and any(term in text for term in ["requier", "necesit", "oblig"])


def _violation(code: str, reason: str, hard: bool) -> Dict[str, Any]:
    return {"code": code, "reason": reason, "hard": hard}


def _normalize(value: str) -> str:
    lowered = str(value or "").lower()
    normalized = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_run_id() -> str:
    return f"adaptive-hybrid-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
