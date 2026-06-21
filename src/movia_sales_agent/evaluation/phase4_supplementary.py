from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.contracts.commercial import MacroAction, ObjectionStrength, ObjectionType


DEFAULT_SUPPLEMENTARY_MANIFEST = (
    PROJECT_ROOT / "movia_validation_package" / "movia_phase4_supplementary_manifest.json"
)
DEFAULT_SUPPLEMENTARY_OUTPUT_ROOT = (
    PROJECT_ROOT / "artifacts" / "evaluations" / "phase4-supplementary-live"
)


class SupplementaryTurn(BaseModel):
    turn_id: int
    user: str


class SupplementaryScenario(BaseModel):
    conversation_id: str
    title: str
    turns: List[SupplementaryTurn]


class SupplementaryDataset(BaseModel):
    dataset_version: str
    description: str
    scenarios: List[SupplementaryScenario]


class SupplementaryManifest(BaseModel):
    manifest_version: str
    phase: str
    description: str
    dataset: str
    expected_turns: int
    required_mode: Dict[str, Any] = Field(default_factory=dict)
    gates: List[str] = Field(default_factory=list)


def run_phase4_supplementary_live(
    *,
    manifest_path: Path = DEFAULT_SUPPLEMENTARY_MANIFEST,
    output_root: Path = DEFAULT_SUPPLEMENTARY_OUTPUT_ROOT,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    manifest = load_manifest(manifest_path)
    dataset = load_dataset(_resolve_path(manifest.dataset))
    validate_dataset_shape(dataset, manifest)

    settings = settings or get_settings()
    run_id = make_run_id()
    started_at = now_iso()
    records: List[Dict[str, Any]] = []

    for scenario in dataset.scenarios:
        agent = MoviaSalesAgent(settings)
        lead_external_id = f"{run_id}:{scenario.conversation_id}"
        active_before: Dict[str, Any] = {}
        for turn in scenario.turns:
            started = perf_counter()
            try:
                response = agent.invoke(
                    turn.user,
                    lead_external_id=lead_external_id,
                    channel="evaluation",
                    external_message_id=f"phase4-supp:{run_id}:{scenario.conversation_id}:t{turn.turn_id}",
                )
                latency_ms = round((perf_counter() - started) * 1000, 2)
                record = build_turn_record(
                    run_id=run_id,
                    scenario=scenario,
                    turn=turn,
                    response=response,
                    active_objection_before=active_before,
                    latency_ms=latency_ms,
                )
                active_before = dict(record.get("active_objection_after") or {})
            except Exception as exc:
                latency_ms = round((perf_counter() - started) * 1000, 2)
                record = error_record(
                    run_id=run_id,
                    scenario=scenario,
                    turn=turn,
                    active_objection_before=active_before,
                    latency_ms=latency_ms,
                    exc=exc,
                )
            record["gate_violations"] = evaluate_turn(record)
            records.append(record)

    gate_summary = summarize_gates(records)
    passed = gate_summary["hard_failures"] == 0
    result = {
        "run_id": run_id,
        "manifest_version": manifest.manifest_version,
        "manifest_path": str(manifest_path),
        "dataset_path": str(_resolve_path(manifest.dataset)),
        "dataset_version": dataset.dataset_version,
        "status": (
            "SUPPLEMENTARY LIVE VALIDATION PASSED"
            if passed
            else "SUPPLEMENTARY LIVE VALIDATION FAILED"
        ),
        "passed": passed,
        "started_at": started_at,
        "completed_at": now_iso(),
        "analysis_model": settings.analysis_model,
        "response_model": settings.response_model,
        "openai_enabled": bool(settings.openai_api_key and not settings.disable_openai),
        "database_enabled": not settings.disable_database,
        "turn_count": len(records),
        "scenario_count": len(dataset.scenarios),
        "gate_summary": gate_summary,
        "records": records,
        "recommendation": (
            "Ready for one full Coherent replay."
            if passed
            else "Not ready for one full Coherent replay; inspect supplementary blockers first."
        ),
    }
    output_dir = output_root / run_id
    write_artifacts(result, output_dir)
    return {**result, "output_dir": str(output_dir)}


def build_turn_record(
    *,
    run_id: str,
    scenario: SupplementaryScenario,
    turn: SupplementaryTurn,
    response: Any,
    active_objection_before: Dict[str, Any],
    latency_ms: float,
) -> Dict[str, Any]:
    metadata = response.response_metadata or {}
    normalized = metadata.get("normalized_turn") or {}
    lead_state = response.lead_state or {}
    profile_data = lead_state.get("profile_data") or {}
    requirement_profile = profile_data.get("requirement_profile") or {}
    selected_action = response.selected_action or {}
    knowledge_plan = response.knowledge_plan or {}
    active_after = lead_state.get("active_objection") or {}
    return {
        "run_id": run_id,
        "scenario_id": scenario.conversation_id,
        "scenario_title": scenario.title,
        "turn_id": turn.turn_id,
        "user_input": turn.user,
        "agent_response": response.response,
        "response_messages": response.response_messages,
        "analyzer_observation": metadata.get("analyzer_observation") or {},
        "analysis": response.analysis.model_dump(),
        "normalized_turn": normalized,
        "current_turn_requirement_delta": normalized.get("current_turn_requirement_delta") or {},
        "persisted_requirement_profile": requirement_profile,
        "active_objection_before": active_objection_before,
        "active_objection_after": active_after,
        "selected_sales_action": selected_action,
        "product_state": {
            "requested_product": normalized.get("requested_product"),
            "referenced_product": normalized.get("referenced_product"),
            "active_product_context": normalized.get("active_product_context")
            or (profile_data.get("product_context") or {}).get("active_product_context"),
            "recommended_product": normalized.get("recommended_product"),
            "confirmed_product": normalized.get("confirmed_product") or profile_data.get("confirmed_product"),
            "selected_product": normalized.get("selected_product") or profile_data.get("selected_product"),
            "known_product_fit": profile_data.get("known_product_fit"),
        },
        "knowledge_needs": knowledge_plan.get("knowledge_needs") or [],
        "structured_sources": knowledge_plan.get("structured_sources") or [],
        "json_sources": knowledge_plan.get("json_sources") or [],
        "retrieved_sources": response.retrieved_sources,
        "response_metadata": metadata,
        "response_source": metadata.get("response_source"),
        "token_usage": response.token_usage,
        "latency_ms": latency_ms,
        "error": None,
    }


def error_record(
    *,
    run_id: str,
    scenario: SupplementaryScenario,
    turn: SupplementaryTurn,
    active_objection_before: Dict[str, Any],
    latency_ms: float,
    exc: Exception,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario_id": scenario.conversation_id,
        "scenario_title": scenario.title,
        "turn_id": turn.turn_id,
        "user_input": turn.user,
        "agent_response": "",
        "response_messages": [],
        "analyzer_observation": {},
        "analysis": {},
        "normalized_turn": {},
        "current_turn_requirement_delta": {},
        "persisted_requirement_profile": {},
        "active_objection_before": active_objection_before,
        "active_objection_after": {},
        "selected_sales_action": {},
        "product_state": {},
        "knowledge_needs": [],
        "structured_sources": [],
        "json_sources": [],
        "retrieved_sources": [],
        "response_metadata": {},
        "response_source": None,
        "token_usage": {},
        "latency_ms": latency_ms,
        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
    }


def evaluate_turn(record: Dict[str, Any]) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    scenario = record["scenario_id"]
    turn_id = record["turn_id"]
    text = normalize(record.get("agent_response") or "")
    normalized = record.get("normalized_turn") or {}
    requirement_profile = record.get("persisted_requirement_profile") or {}
    product_state = record.get("product_state") or {}
    action = record.get("selected_sales_action") or {}
    sources = set(record.get("structured_sources") or [])
    json_sources = set(record.get("json_sources") or [])
    needs = set(record.get("knowledge_needs") or [])
    active_after = record.get("active_objection_after") or {}

    if record.get("error"):
        violations.append(v("provider_error", record["error"]))
        return violations
    if record.get("response_source") != "openai":
        violations.append(v("fallback", "Response source was not OpenAI."))

    if scenario == "PHASE4-SUP-001":
        if turn_id == 1:
            active_actions = active_types(requirement_profile.get("external_actions"))
            if "schedule_appointment" not in set(normalized.get("requested_agent_actions") or active_actions):
                violations.append(v("requirement_replacement_failure", "schedule_appointment was not detected on turn 1."))
            if requirement_profile.get("requirement_class") != "external_actions":
                violations.append(v("requirement_replacement_failure", "Turn 1 did not persist external_actions requirement class."))
            if product_state.get("recommended_product") != "movia_hibrido":
                violations.append(v("wrong_product_after_replacement", "Turn 1 did not recommend MovIA Híbrido."))
        elif turn_id == 2:
            delta = record.get("current_turn_requirement_delta") or {}
            if delta.get("update_type") != "replace":
                violations.append(v("requirement_replacement_failure", "Explicit scope narrowing did not produce replace update."))
            if "provide_prices" not in set(normalized.get("requested_agent_capabilities") or []) and "provide_prices" not in active_types(requirement_profile.get("informational_capabilities")):
                violations.append(v("requirement_replacement_failure", "provide_prices was not active after replacement."))
            if "schedule_appointment" in active_types(requirement_profile.get("external_actions")):
                violations.append(v("requirement_replacement_failure", "schedule_appointment remained active after replacement."))
            if requirement_profile.get("requirement_class") != "informational_only":
                violations.append(v("requirement_replacement_failure", "Requirement class was not informational_only after replacement."))
            if product_state.get("recommended_product") != "movia_captura":
                violations.append(v("wrong_product_after_replacement", "Replacement did not recommend MovIA Captura."))
        elif turn_id == 3:
            if "schedule_appointment" in active_types(requirement_profile.get("external_actions")):
                violations.append(v("requirement_replacement_failure", "schedule_appointment returned active on follow-up."))
            if requirement_profile.get("requirement_class") != "informational_only":
                violations.append(v("requirement_profile_reset_failure", "Requirement profile did not remain informational_only."))
            if product_state.get("recommended_product") != "movia_captura":
                violations.append(v("wrong_product_after_replacement", "Follow-up did not preserve Captura recommendation."))

    if scenario == "PHASE4-SUP-002":
        if product_state.get("requested_product") != "movia_captura":
            violations.append(v("product_capability_routing_miss", "Captura reference was not detected."))
        if product_state.get("selected_product"):
            violations.append(v("premature_selected_product_assignment", "Captura was selected from a capability question."))
        if "product_capabilities" not in needs or "postgres.products" not in sources:
            violations.append(v("product_capability_routing_miss", "Product capability context was not loaded."))
        if says_cannot_understand_audio(text) or not confirms_audio(text):
            violations.append(v("audio_capability_factual_error", "Response did not confirm Captura audio support."))

    if scenario == "PHASE4-SUP-003":
        if turn_id == 1:
            analysis = record.get("analysis") or {}
            if analysis.get("objection_type") != ObjectionType.PRICE_OBJECTION.value:
                violations.append(v("active_objection_resolution_failure", "Price objection was not detected."))
            if analysis.get("objection_strength") == ObjectionStrength.HARD.value and not active_after.get("active"):
                violations.append(v("active_objection_resolution_failure", "Active objection was not created."))
        elif turn_id == 3:
            if normalized.get("objection_relation") != "resolved":
                violations.append(v("active_objection_resolution_failure", "Acceptance did not resolve the active objection relation."))
            if active_after.get("active") and not active_after.get("resolved"):
                violations.append(v("resolved_objection_remains_blocking", "Resolved objection remained active and blocking."))
            if (action.get("macro_action") == MacroAction.HANDLE_OBJECTION.value) or "preocupa" in text:
                violations.append(v("active_objection_resolution_failure", "Agent continued the objection flow after acceptance."))

    if scenario == "PHASE4-SUP-004":
        if turn_id == 1:
            if "postgres.products" not in sources:
                violations.append(v("product_capability_routing_miss", "Price turn did not load products."))
            if product_state.get("selected_product"):
                violations.append(v("premature_selected_product_assignment", "Híbrido price question selected the product."))
            if not contains_amount(text, 7500) or not contains_amount(text, 550):
                violations.append(v("deposit_setup_composition_error", "Híbrido price response missed setup or monthly price."))
        elif turn_id == 2:
            if not {"product_pricing", "official_policy", "platform_steps"} <= needs:
                violations.append(v("required_policy_source_miss", "Start-payment turn missed pricing, policy, or platform needs."))
            if "postgres.products" not in sources or "postgres.policies" not in sources or "platform_steps" not in json_sources:
                violations.append(v("required_policy_source_miss", "Start-payment turn missed products, policies, or platform steps source."))
            if deposit_composition_error(text):
                violations.append(v("deposit_setup_composition_error", "Deposit/setup composition was incorrect."))
        elif turn_id == 3:
            if "postgres.policies" not in sources:
                violations.append(v("required_policy_source_miss", "Refund turn missed policies source."))
            if not states_non_refundable(text):
                violations.append(v("refund_policy_error", "Refund answer did not state the deposit is non-refundable."))
            if claims_refundable(text):
                violations.append(v("refund_policy_error", "Refund answer implied the deposit is refundable."))

    if scenario == "PHASE4-SUP-005":
        if turn_id == 1:
            if product_state.get("requested_product") != "movia_captura":
                violations.append(v("premature_selected_product_assignment", "Captura price reference was not tracked as requested_product."))
            if product_state.get("selected_product"):
                violations.append(v("premature_selected_product_assignment", "Captura was selected during price question."))
            if action.get("macro_action") == MacroAction.DIRECT_CLOSE.value:
                violations.append(v("premature_selected_product_assignment", "Price question triggered direct close."))
            if not contains_amount(text, 4900) or not contains_amount(text, 450):
                violations.append(v("deposit_setup_composition_error", "Captura price response missed setup or monthly price."))
        elif turn_id == 2:
            analysis = record.get("analysis") or {}
            if not analysis.get("explicit_start_intent"):
                violations.append(v("explicit_product_commitment_miss", "Explicit commitment did not set start intent."))
            if product_state.get("selected_product") != "movia_captura" and product_state.get("confirmed_product") != "movia_captura":
                violations.append(v("explicit_product_commitment_miss", "Captura was not selected or confirmed after explicit commitment."))
            if action.get("macro_action") == MacroAction.DIRECT_CLOSE.value and product_state.get("selected_product") not in {None, "movia_captura"}:
                violations.append(v("wrong_product_direct_close", "Direct close used a product other than Captura."))
            if "app.moviatech.com.mx" not in text:
                violations.append(v("explicit_product_commitment_miss", "Official application link was not provided."))

    return dedupe_violations(violations)


def summarize_gates(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    violations = [violation for record in records for violation in record.get("gate_violations") or []]
    counts = Counter(violation["code"] for violation in violations)
    gate_counts = {
        "hard_failures": len(violations),
        "provider_errors": counts["provider_error"],
        "fallbacks": counts["fallback"],
        "requirement_replacement_failures": counts["requirement_replacement_failure"],
        "requirement_profile_reset_failures": counts["requirement_profile_reset_failure"],
        "wrong_product_after_replacement": counts["wrong_product_after_replacement"],
        "audio_capability_factual_errors": counts["audio_capability_factual_error"],
        "product_capability_routing_misses": counts["product_capability_routing_miss"],
        "active_objection_resolution_failures": counts["active_objection_resolution_failure"],
        "resolved_objection_remains_blocking": counts["resolved_objection_remains_blocking"],
        "deposit_setup_composition_errors": counts["deposit_setup_composition_error"],
        "refund_policy_errors": counts["refund_policy_error"],
        "required_policy_source_misses": counts["required_policy_source_miss"],
        "premature_selected_product_assignments": counts["premature_selected_product_assignment"],
        "explicit_product_commitment_misses": counts["explicit_product_commitment_miss"],
        "wrong_product_direct_closes": counts["wrong_product_direct_close"],
    }
    return {
        **gate_counts,
        "violation_counts": dict(sorted(counts.items())),
        "violations": violations,
    }


def write_artifacts(result: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "gate_summary.json").write_text(
        json.dumps(result["gate_summary"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(summary_markdown(result), encoding="utf-8")
    (output_dir / "conversation_transcript.md").write_text(transcript_markdown(result), encoding="utf-8")


def summary_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# Phase 4 Supplementary Live Validation: {result['run_id']}",
        "",
        f"- **Status:** {result['status']}",
        f"- **Analyzer model:** {result['analysis_model']}",
        f"- **Response model:** {result['response_model']}",
        f"- **Turns:** {result['turn_count']}",
        f"- **Scenarios:** {result['scenario_count']}",
        f"- **Recommendation:** {result['recommendation']}",
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
    violations = result["gate_summary"].get("violations") or []
    if violations:
        lines.extend(["", "## Violations", ""])
        for violation in violations:
            lines.append(f"- `{violation['code']}`: {violation['reason']}")
    lines.extend(["", result["status"]])
    return "\n".join(lines)


def transcript_markdown(result: Dict[str, Any]) -> str:
    lines = [f"# Supplementary Transcript: {result['run_id']}", ""]
    current = None
    for record in result["records"]:
        if record["scenario_id"] != current:
            current = record["scenario_id"]
            lines.extend(["", f"## {current}: {record['scenario_title']}", ""])
        lines.extend(
            [
                f"### Turn {record['turn_id']}",
                "",
                f"**User:** {record['user_input']}",
                "",
                f"**Assistant:** {record['agent_response']}",
                "",
                f"**Action:** `{(record.get('selected_sales_action') or {}).get('macro_action')}`",
                f"**Knowledge needs:** `{', '.join(record.get('knowledge_needs') or [])}`",
                f"**Structured sources:** `{', '.join(record.get('structured_sources') or [])}`",
                f"**JSON sources:** `{', '.join(record.get('json_sources') or [])}`",
                f"**Product state:** `{json.dumps(record.get('product_state') or {}, ensure_ascii=False)}`",
                f"**Active objection before:** `{json.dumps(record.get('active_objection_before') or {}, ensure_ascii=False)}`",
                f"**Active objection after:** `{json.dumps(record.get('active_objection_after') or {}, ensure_ascii=False)}`",
                f"**Requirement delta:** `{json.dumps(record.get('current_turn_requirement_delta') or {}, ensure_ascii=False)}`",
                f"**Persisted requirement profile:** `{json.dumps(record.get('persisted_requirement_profile') or {}, ensure_ascii=False)}`",
                f"**Latency ms:** `{record.get('latency_ms')}`",
                f"**Token usage:** `{json.dumps(record.get('token_usage') or {}, ensure_ascii=False)}`",
                f"**Gate violations:** `{json.dumps(record.get('gate_violations') or [], ensure_ascii=False)}`",
                "",
            ]
        )
    return "\n".join(lines)


def load_manifest(path: Path) -> SupplementaryManifest:
    return SupplementaryManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_dataset(path: Path) -> SupplementaryDataset:
    return SupplementaryDataset.model_validate_json(path.read_text(encoding="utf-8"))


def validate_dataset_shape(dataset: SupplementaryDataset, manifest: SupplementaryManifest) -> None:
    turn_count = sum(len(scenario.turns) for scenario in dataset.scenarios)
    if len(dataset.scenarios) != 5:
        raise ValueError(f"Expected 5 supplementary scenarios, got {len(dataset.scenarios)}.")
    if turn_count != manifest.expected_turns:
        raise ValueError(f"Expected {manifest.expected_turns} supplementary turns, got {turn_count}.")


def active_types(entries: Any) -> List[str]:
    return [
        str(entry.get("type"))
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("type") and entry.get("active", True)
    ]


def contains_amount(text: str, amount: int) -> bool:
    compact = re.sub(r"[^\d]", "", text)
    return str(amount) in compact


def confirms_audio(text: str) -> bool:
    return "audio" in text and any(word in text for word in ["puede", "si", "entiend", "interpret", "proces"])


def says_cannot_understand_audio(text: str) -> bool:
    return "audio" in text and any(
        phrase in text
        for phrase in [
            "no puede entender audio",
            "no puede entender audios",
            "no entiende audio",
            "no entiende audios",
            "no puede interpretar audio",
            "no puede interpretar audios",
            "no interpreta audio",
            "no interpreta audios",
            "no procesa audio",
            "no procesa audios",
            "captura no puede",
        ]
    )


def deposit_composition_error(text: str) -> bool:
    additive = (
        contains_amount(text, 7500)
        and "50%" in text
        and any(phrase in text for phrase in ["mas 50", "más 50", "adicional", "aparte"])
    )
    deposit_is_total = contains_amount(text, 7500) and any(
        phrase in text
        for phrase in [
            "deposito de 7500",
            "depósito de 7500",
            "7500 de deposito",
            "7500 de depósito",
        ]
    )
    missing_policy = "50%" not in text and "mitad" not in text
    return additive or deposit_is_total or missing_policy


def states_non_refundable(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "no hay reembolso",
            "no es reembolsable",
            "no reembolsable",
            "no se reembolsa",
            "sin reembolso",
            "no podemos reembols",
            "no se regresa",
            "no se regresan",
            "no se devuelve",
            "no se devuelven",
        ]
    )


def claims_refundable(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "si hay reembolso",
            "es reembolsable",
            "se puede reembolsar",
            "te devolvemos",
        ]
    ) and not states_non_refundable(text)


def v(code: str, reason: str) -> Dict[str, str]:
    return {"code": code, "reason": reason}


def dedupe_violations(violations: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for violation in violations:
        key = (violation["code"], violation["reason"])
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(violation))
    return result


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_marks.lower()


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def make_run_id() -> str:
    return f"phase4-supp-live-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
