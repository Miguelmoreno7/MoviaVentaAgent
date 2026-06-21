from __future__ import annotations

import glob
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.agent.memory import (
    build_structured_memory,
    memory_updates_for_profile,
    merge_lead_profile_memory,
)
from movia_sales_agent.agent.objections import ObjectionFlowService
from movia_sales_agent.agent.planners import SalesPolicyPlanner
from movia_sales_agent.agent.stages import SalesStageTransitionService
from movia_sales_agent.analyzer.contract_v3 import ANALYZER_CONTRACT_VERSION
from movia_sales_agent.analyzer.normalizer import (
    normalize_analyzer_turn,
    normalized_turn_to_analysis,
)
from movia_sales_agent.analyzer.shadow_parser import ShadowSignalParser
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    BuyingSignal,
    Intent,
    MacroAction,
    MicroAction,
    ObjectionType,
    ProductFit,
)
from movia_sales_agent.evaluation.dataset import load_validation_dataset
from movia_sales_agent.evaluation.models import ValidationDataset, ValidationScenario, ValidationTurn
from movia_sales_agent.services.openai_service import OpenAIService


DEFAULT_TARGETED_MANIFEST = (
    PROJECT_ROOT / "movia_validation_package" / "analyzer_v3_targeted_manifest.json"
)
DEFAULT_TARGETED_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "evaluations" / "analyzer-v3-targeted"
PARSER_SHADOW_REPORT = PROJECT_ROOT / "docs" / "evaluation" / "PARSER_SHADOW_COMPARISON.md"
COMPARISON_REPORT = PROJECT_ROOT / "docs" / "evaluation" / "ANALYZER_V3_TARGETED_COMPARISON.md"


class ScenarioRef(BaseModel):
    dataset: str
    scenario_id: str
    turn_ranges: List[List[int]]
    focus_turn_ids: List[int] = Field(default_factory=list)


class TargetedCase(BaseModel):
    case_id: str
    dataset: Optional[str] = None
    scenario_id: Optional[str] = None
    turn_ranges: List[List[int]] = Field(default_factory=list)
    focus_turn_ids: List[int] = Field(default_factory=list)
    scenario_refs: List[ScenarioRef] = Field(default_factory=list)
    checks: List[str] = Field(default_factory=list)


class TargetedManifest(BaseModel):
    manifest_version: str
    phase: str
    description: str
    datasets: Dict[str, str]
    cases: List[TargetedCase]
    previous_run_globs: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ResolvedTurn:
    case_id: str
    dataset_alias: str
    scenario: ValidationScenario
    turn: ValidationTurn
    focus: bool
    checks: Tuple[str, ...]


def load_targeted_manifest(path: Path = DEFAULT_TARGETED_MANIFEST) -> TargetedManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _ensure_manifest_has_no_embedded_dataset_content(raw)
    manifest = TargetedManifest.model_validate(raw)
    validate_targeted_manifest(manifest)
    return manifest


def validate_targeted_manifest(manifest: TargetedManifest) -> None:
    if not manifest.datasets:
        raise ValueError("Targeted manifest must define dataset aliases.")
    if not manifest.cases:
        raise ValueError("Targeted manifest must define at least one case.")
    datasets = _load_manifest_datasets(manifest)
    errors: List[str] = []
    for case in manifest.cases:
        refs = _case_refs(case)
        if not refs:
            errors.append(f"{case.case_id}: case must define a scenario reference.")
            continue
        if not case.checks:
            errors.append(f"{case.case_id}: case must define at least one check.")
        for ref in refs:
            if ref.dataset not in datasets:
                errors.append(f"{case.case_id}: unknown dataset alias {ref.dataset!r}.")
                continue
            scenario = _scenario_by_id(datasets[ref.dataset], ref.scenario_id)
            if not scenario:
                errors.append(f"{case.case_id}: scenario {ref.scenario_id!r} not found.")
                continue
            turn_ids = {turn.turn_id for turn in scenario.turns}
            for start, end in _iter_ranges(ref.turn_ranges):
                missing = [turn_id for turn_id in range(start, end + 1) if turn_id not in turn_ids]
                if missing:
                    errors.append(
                        f"{case.case_id}: {ref.scenario_id} missing turn ids {missing}."
                    )
            missing_focus = [turn_id for turn_id in ref.focus_turn_ids if turn_id not in turn_ids]
            if missing_focus:
                errors.append(
                    f"{case.case_id}: {ref.scenario_id} missing focus turn ids {missing_focus}."
                )
    if errors:
        raise ValueError("Invalid targeted manifest: " + "; ".join(errors))


def resolve_targeted_turns(manifest: TargetedManifest) -> List[ResolvedTurn]:
    datasets = _load_manifest_datasets(manifest)
    resolved: List[ResolvedTurn] = []
    for case in manifest.cases:
        for ref in _case_refs(case):
            scenario = _scenario_by_id(datasets[ref.dataset], ref.scenario_id)
            if not scenario:
                continue
            selected_turn_ids = set(_turn_ids_from_ranges(ref.turn_ranges))
            focus_ids = set(ref.focus_turn_ids)
            for turn in scenario.turns:
                if turn.turn_id not in selected_turn_ids:
                    continue
                resolved.append(
                    ResolvedTurn(
                        case_id=case.case_id,
                        dataset_alias=ref.dataset,
                        scenario=scenario,
                        turn=turn,
                        focus=turn.turn_id in focus_ids,
                        checks=tuple(case.checks),
                    )
                )
    return resolved


def run_targeted_validation(
    *,
    manifest_path: Path = DEFAULT_TARGETED_MANIFEST,
    output_root: Path = DEFAULT_TARGETED_OUTPUT_ROOT,
    mode: str = "both",
    settings: Optional[Settings] = None,
    offline: bool = False,
    previous_run_paths: Optional[Sequence[Path]] = None,
    write_docs: bool = True,
) -> Dict[str, Any]:
    manifest = load_targeted_manifest(manifest_path)
    settings = _offline_settings(settings or get_settings()) if offline else (settings or get_settings())
    run_id = make_targeted_run_id()
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_paths = list(previous_run_paths or default_previous_run_paths(manifest))

    analyzer_records: List[Dict[str, Any]] = []
    live_records: List[Dict[str, Any]] = []
    if mode in {"both", "analyzer-only"}:
        analyzer_records = run_analyzer_only_replay(
            manifest,
            settings=_analyzer_only_settings(settings),
            run_id=run_id,
        )
    if mode in {"both", "live-agent"}:
        live_records = run_live_agent_replay(
            manifest,
            settings=settings,
            run_id=run_id,
        )

    previous_records = load_previous_targeted_records(previous_paths, manifest)
    result = build_targeted_result(
        run_id=run_id,
        manifest_path=manifest_path,
        manifest=manifest,
        mode=mode,
        settings=settings,
        analyzer_records=analyzer_records,
        live_records=live_records,
        previous_records=previous_records,
        previous_run_paths=previous_paths,
        offline=offline,
    )
    write_targeted_artifacts(result, output_dir, write_docs=write_docs)
    return {**result, "output_dir": str(output_dir)}


def run_analyzer_only_replay(
    manifest: TargetedManifest,
    *,
    settings: Settings,
    run_id: str,
) -> List[Dict[str, Any]]:
    openai = OpenAIService(settings)
    shadow_parser = ShadowSignalParser()
    planner = SalesPolicyPlanner()
    stage_service = SalesStageTransitionService()
    objection_service = ObjectionFlowService()
    records: List[Dict[str, Any]] = []

    for case in manifest.cases:
        for ref in _case_refs(case):
            dataset = _load_manifest_datasets(manifest)[ref.dataset]
            scenario = _scenario_by_id(dataset, ref.scenario_id)
            if not scenario:
                continue
            selected_ids = set(_turn_ids_from_ranges(ref.turn_ranges))
            focus_ids = set(ref.focus_turn_ids)
            recent_messages: List[Dict[str, Any]] = []
            lead_profile: Dict[str, Any] = {
                "current_stage": "new",
                "conversation_mode": "normal",
                "previous_stage": None,
                "stage_before_objection": None,
                "active_objection": {},
                "last_action": None,
                "profile_data": {},
            }
            for turn in scenario.turns:
                if turn.turn_id not in selected_ids:
                    continue
                started = perf_counter()
                try:
                    shadow = shadow_parser.parse(turn.user)
                    analysis, usage, observation = openai.analyze_turn_v3_with_usage(
                        turn.user,
                        recent_messages,
                    )
                    normalized = normalize_analyzer_turn(
                        observation,
                        message=turn.user,
                        lead_profile=lead_profile,
                        shadow_parser=shadow.model_dump(),
                    )
                    analysis = normalized_turn_to_analysis(
                        observation,
                        normalized,
                        message=turn.user,
                    )
                    memory = build_structured_memory(analysis, lead_profile)
                    lead_profile = merge_lead_profile_memory(lead_profile, analysis, memory)
                    sales_plan = planner.plan(
                        analysis,
                        lead_profile,
                        current_stage=lead_profile.get("current_stage"),
                        previous_stage=lead_profile.get("previous_stage"),
                        active_objection=lead_profile.get("active_objection"),
                        last_macro_action=lead_profile.get("last_action"),
                        normalized_turn=normalized.model_dump(),
                        message=turn.user,
                    )
                    stage = stage_service.transition(
                        lead_profile=lead_profile,
                        analysis=analysis,
                        sales_plan=sales_plan,
                    )
                    active_objection = objection_service.transition(
                        lead_profile=lead_profile,
                        analysis=analysis,
                        sales_plan=sales_plan,
                        stage_transition=stage,
                        message=turn.user,
                    )
                    updates = memory_updates_for_profile(analysis, memory)
                    lead_profile = {
                        **lead_profile,
                        **{key: value for key, value in updates.items() if key != "profile_data"},
                        "profile_data": {
                            **dict(lead_profile.get("profile_data") or {}),
                            **dict(updates.get("profile_data") or {}),
                        },
                        "current_stage": stage.current_stage,
                        "previous_stage": stage.previous_stage,
                        "stage_before_objection": stage.stage_before_objection,
                        "conversation_mode": stage.conversation_mode,
                        "active_objection": active_objection.model_dump(),
                        "last_action": sales_plan.macro_action,
                    }
                    record = {
                        "run_id": run_id,
                        "mode": "analyzer_only",
                        "case_id": case.case_id,
                        "dataset": ref.dataset,
                        "scenario_id": scenario.conversation_id,
                        "turn_id": turn.turn_id,
                        "focus": turn.turn_id in focus_ids,
                        "checks": case.checks,
                        "user_input": turn.user,
                        "analysis": analysis.model_dump(),
                        "analyzer_observation": observation.model_dump(),
                        "shadow_parser": shadow.model_dump(),
                        "normalized_turn": normalized.model_dump(),
                        "selected_action": sales_plan.model_dump(),
                        "lead_state": _compact_lead_state(lead_profile),
                        "token_usage": {"calls": [usage], "total": _usage_total([usage])},
                        "latency_ms": round((perf_counter() - started) * 1000, 2),
                    }
                except Exception as exc:
                    record = _error_record(
                        run_id=run_id,
                        mode="analyzer_only",
                        case_id=case.case_id,
                        dataset=ref.dataset,
                        scenario_id=scenario.conversation_id,
                        turn=turn,
                        focus=turn.turn_id in focus_ids,
                        checks=case.checks,
                        started=started,
                        exc=exc,
                    )
                record["gate_violations"] = evaluate_gate_violations(record)
                records.append(record)
                recent_messages.append({"role": "user", "content": turn.user})
                recent_messages.append(
                    {
                        "role": "assistant",
                        "content": f"[analyzer-only skipped response: {record.get('selected_action', {}).get('macro_action', 'none')}]",
                    }
                )
    return records


def run_live_agent_replay(
    manifest: TargetedManifest,
    *,
    settings: Settings,
    run_id: str,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    datasets = _load_manifest_datasets(manifest)
    replay_plan = _unique_live_replay_plan(manifest)
    for dataset_name, scenario_id in replay_plan:
        dataset = datasets[dataset_name]
        scenario = _scenario_by_id(dataset, scenario_id)
        if not scenario:
            continue
        scenario_plan = replay_plan[(dataset_name, scenario_id)]
        selected_ids = set(scenario_plan)
        agent = MoviaSalesAgent(settings)
        lead_external_id = (
            f"analyzer-v3-targeted:{run_id}:live-agent:"
            f"{dataset_name}:{scenario.conversation_id}"
        )
        for turn in scenario.turns:
            if turn.turn_id not in selected_ids:
                continue
            turn_plan = scenario_plan[turn.turn_id]
            case_id = "+".join(sorted(turn_plan["case_ids"]))
            checks = sorted(turn_plan["checks"])
            gate_checks = sorted(turn_plan["focus_checks"])
            focus = bool(gate_checks)
            started = perf_counter()
            try:
                response = agent.invoke(
                    turn.user,
                    lead_external_id=lead_external_id,
                    channel="evaluation",
                    external_message_id=(
                        f"analyzer-v3-targeted:{run_id}:live-agent:"
                        f"{dataset_name}:{scenario.conversation_id}:t{turn.turn_id}"
                    ),
                )
                record = {
                    "run_id": run_id,
                    "mode": "live_agent",
                    "case_id": case_id,
                    "dataset": dataset_name,
                    "scenario_id": scenario.conversation_id,
                    "turn_id": turn.turn_id,
                    "focus": focus,
                    "checks": checks,
                    "gate_checks": gate_checks,
                    "user_input": turn.user,
                    "agent_output": response.response,
                    "response_messages": response.response_messages,
                    "analysis": response.analysis.model_dump(),
                    "normalized_turn": response.response_metadata.get("normalized_turn") or {},
                    "analyzer_observation": response.response_metadata.get("analyzer_observation") or {},
                    "shadow_parser": response.response_metadata.get("shadow_parser") or {},
                    "selected_action": response.selected_action,
                    "lead_state": response.lead_state,
                    "knowledge_plan": response.knowledge_plan,
                    "retrieved_sources": response.retrieved_sources,
                    "response_metadata": response.response_metadata,
                    "token_usage": response.token_usage,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                }
            except Exception as exc:
                record = _error_record(
                    run_id=run_id,
                    mode="live_agent",
                    case_id=case_id,
                    dataset=dataset_name,
                    scenario_id=scenario.conversation_id,
                    turn=turn,
                    focus=focus,
                    checks=checks,
                    started=started,
                    exc=exc,
                )
            record["gate_violations"] = evaluate_gate_violations(record)
            records.append(record)
    return records


def load_previous_targeted_records(
    previous_run_paths: Sequence[Path],
    manifest: TargetedManifest,
) -> List[Dict[str, Any]]:
    index = _focus_index(manifest)
    records: List[Dict[str, Any]] = []
    for path in previous_run_paths:
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        suite_alias = "coherent" if raw.get("suite_type") == "coherent_scripted" else "atomic"
        for scenario in raw.get("scenario_results") or []:
            scenario_id = scenario.get("conversation_id")
            for turn in scenario.get("turns") or []:
                turn_id = int(turn.get("turn_id") or 0)
                keys = index.get((suite_alias, scenario_id, turn_id), [])
                for case_id, checks in keys:
                    record = {
                        "run_id": raw.get("run_id"),
                        "mode": "previous_v3_live",
                        "source_run_path": str(path),
                        "case_id": case_id,
                        "dataset": suite_alias,
                        "scenario_id": scenario_id,
                        "turn_id": turn_id,
                        "focus": True,
                        "checks": checks,
                        "user_input": turn.get("user_input") or "",
                        "agent_output": turn.get("agent_output") or "",
                        "response_messages": turn.get("response_messages") or [],
                        "analysis": turn.get("analysis") or {},
                        "normalized_turn": (turn.get("response_metadata") or {}).get("normalized_turn") or {},
                        "selected_action": turn.get("selected_action") or {},
                        "lead_state": turn.get("lead_state") or {},
                        "response_metadata": turn.get("response_metadata") or {},
                        "token_usage": turn.get("token_usage") or {},
                        "latency_ms": turn.get("latency_ms") or 0,
                    }
                    record["gate_violations"] = evaluate_gate_violations(record)
                    records.append(record)
    return records


def _unique_live_replay_plan(
    manifest: TargetedManifest,
) -> Dict[Tuple[str, str], Dict[int, Dict[str, Any]]]:
    plan: Dict[Tuple[str, str], Dict[int, Dict[str, Any]]] = {}
    for case in manifest.cases:
        for ref in _case_refs(case):
            scenario_key = (ref.dataset, ref.scenario_id)
            scenario_plan = plan.setdefault(scenario_key, {})
            selected_ids = set(_turn_ids_from_ranges(ref.turn_ranges))
            focus_ids = set(ref.focus_turn_ids)
            for turn_id in selected_ids:
                turn_plan = scenario_plan.setdefault(
                    turn_id,
                    {"case_ids": set(), "checks": set(), "focus_checks": set()},
                )
                turn_plan["case_ids"].add(case.case_id)
                turn_plan["checks"].update(case.checks)
                if turn_id in focus_ids:
                    turn_plan["focus_checks"].update(case.checks)
    return plan


def build_targeted_result(
    *,
    run_id: str,
    manifest_path: Path,
    manifest: TargetedManifest,
    mode: str,
    settings: Settings,
    analyzer_records: List[Dict[str, Any]],
    live_records: List[Dict[str, Any]],
    previous_records: List[Dict[str, Any]],
    previous_run_paths: Sequence[Path],
    offline: bool,
) -> Dict[str, Any]:
    active_records = live_records if live_records else analyzer_records
    gate_summary = summarize_gates(active_records)
    analyzer_summary = summarize_records(analyzer_records)
    live_summary = summarize_records(live_records)
    previous_summary = summarize_gates(previous_records)
    comparison = previous_vs_new_comparison(previous_records, active_records)
    parser_shadow = parser_shadow_summary(analyzer_records or live_records)
    passed = targeted_gates_pass(gate_summary, previous_summary)
    return {
        "run_id": run_id,
        "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
        "manifest_path": str(manifest_path),
        "manifest_version": manifest.manifest_version,
        "mode": mode,
        "offline": offline,
        "analysis_model": settings.analysis_model,
        "response_model": settings.response_model,
        "started_at": run_id_timestamp(run_id),
        "completed_at": now_iso(),
        "previous_run_paths": [str(path) for path in previous_run_paths],
        "record_counts": {
            "analyzer_only": len(analyzer_records),
            "live_agent": len(live_records),
            "previous_v3_live": len(previous_records),
            "focus_turns": sum(1 for record in active_records if record.get("focus")),
        },
        "passed": passed,
        "terminal_status": (
            "TARGETED CONTRACT VALIDATION PASSED"
            if passed
            else "TARGETED CONTRACT VALIDATION FAILED"
        ),
        "gate_summary": gate_summary,
        "analyzer_summary": analyzer_summary,
        "live_summary": live_summary,
        "previous_summary": previous_summary,
        "comparison": comparison,
        "parser_shadow": parser_shadow,
        "full_replay_recommendation": (
            "Recommend full Atomic and Coherent replay."
            if passed and live_records
            else "Do not run full replay yet; resolve targeted blockers first."
        ),
        "manifest": manifest.model_dump(),
        "analyzer_records": analyzer_records,
        "live_records": live_records,
        "previous_records": previous_records,
    }


def write_targeted_artifacts(result: Dict[str, Any], output_dir: Path, *, write_docs: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "manifest_snapshot.json", result["manifest"])
    _write_json(output_dir / "analyzer_only_results.json", result["analyzer_records"])
    _write_json(output_dir / "targeted_live_results.json", result["live_records"])
    _write_json(output_dir / "previous_v3_results.json", result["previous_records"])
    _write_json(output_dir / "gate_summary.json", _strip_records(result))
    (output_dir / "summary.md").write_text(targeted_markdown_report(result), encoding="utf-8")
    if write_docs:
        PARSER_SHADOW_REPORT.parent.mkdir(parents=True, exist_ok=True)
        PARSER_SHADOW_REPORT.write_text(parser_shadow_markdown(result), encoding="utf-8")
        COMPARISON_REPORT.write_text(previous_comparison_markdown(result), encoding="utf-8")


def evaluate_gate_violations(record: Dict[str, Any]) -> List[Dict[str, str]]:
    if not record.get("focus"):
        return []
    checks = set(record.get("gate_checks") or record.get("checks") or [])
    analysis = record.get("analysis") or {}
    normalized = record.get("normalized_turn") or {}
    selected = record.get("selected_action") or {}
    output = str(record.get("agent_output") or "")
    violations: List[Dict[str, str]] = []
    if record.get("error"):
        violations.append(_violation("agent_error", "Agent returned an error."))

    if "impossible_objection_state" in checks or True:
        violations.extend(_impossible_state_violations(analysis, normalized))

    if "hallucinated_turn_number" in checks and analysis.get("explicit_turn_number"):
        violations.append(
            _violation("hallucinated_turn_number", "Analyzer emitted an explicit turn number.")
        )

    if "false_prior_reference" in checks and _has_prior_reference(analysis, normalized):
        violations.append(
            _violation("false_prior_reference", "Turn was marked as a prior reference.")
        )

    if "true_prior_reference_retained" in checks and not _has_prior_reference(analysis, normalized):
        violations.append(
            _violation("true_prior_reference_missed", "True prior reference was not detected.")
        )

    if "premature_captura_recommendation" in checks:
        action_requirement = _action_requirement(analysis, normalized)
        if action_requirement == ActionRequirement.UNKNOWN.value and _mentions_captura_recommendation(
            selected, output, analysis, normalized
        ):
            violations.append(
                _violation(
                    "premature_captura_recommendation",
                    "Captura was recommended before action requirement was known.",
                )
            )

    if "external_action_routing" in checks:
        action_requirement = _action_requirement(analysis, normalized)
        if action_requirement != ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value:
            violations.append(
                _violation("external_action_miss", "External action requirement was not detected.")
            )
        elif _routes_to_captura(selected, analysis, normalized):
            violations.append(
                _violation("external_action_miss", "External action routed to Captura.")
            )
        elif not _routes_to_hibrido_or_handoff(selected, analysis, normalized):
            violations.append(
                _violation("external_action_miss", "External action did not route to Híbrido or handoff.")
            )

    if "captura_external_action_overpromise" in checks and captura_external_overpromise(output):
        violations.append(
            _violation(
                "captura_external_action_overpromise",
                "Response overpromised Captura for external actions.",
            )
        )

    if (
        ("unsupported_channel_claim" in checks or "multichannel_claim" in checks)
        and unsupported_channel_claim(output)
    ):
        violations.append(
            _violation("unsupported_channel_claim", "Response implied unsupported channels are available.")
        )

    if "explicit_start_precision" in checks and not _explicit_start(analysis, normalized):
        violations.append(
            _violation("explicit_start_false_negative", "Explicit start intent was not detected.")
        )

    if "need_to_think_false_positive" in checks and analysis.get("objection_type") == ObjectionType.NEED_TO_THINK.value:
        violations.append(
            _violation("need_to_think_false_positive", "Explicit start was classified as need_to_think.")
        )

    if "sarcastic_soft_concern" in checks:
        if analysis.get("objection_strength") == "hard":
            violations.append(
                _violation("sarcastic_hard_objection", "Sarcastic opener became a hard objection.")
            )
        if (selected.get("objection_overlay") or {}).get("blocking_close"):
            violations.append(
                _violation("sarcastic_persistent_objection", "Sarcastic opener created a blocking objection.")
            )

    if "price_question_precision" in checks:
        if analysis.get("primary_intent") not in {
            Intent.PRICING_QUESTION.value,
            Intent.CHEAPEST_PLAN_QUESTION.value,
        } and "pricing" not in (analysis.get("topics") or []):
            violations.append(
                _violation("price_question_intent_miss", "Price question was not recognized.")
            )

    if "price_objection_false_positive" in checks and analysis.get("objection_type") == ObjectionType.PRICE_OBJECTION.value:
        violations.append(
            _violation("price_objection_false_positive", "Price question became a price objection.")
        )

    if "explicit_start_false_positive" in checks and _explicit_start(analysis, normalized):
        violations.append(
            _violation("explicit_start_false_positive", "Non-start turn became explicit start.")
        )

    return _dedupe_violations(violations)


def summarize_gates(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    focus = [record for record in records if record.get("focus")]
    violations = [
        violation
        for record in focus
        for violation in record.get("gate_violations") or []
    ]
    counts = Counter(violation["code"] for violation in violations)
    summary = {
        "focus_turns": len(focus),
        "hard_failures": len(violations),
        "impossible_states": sum(
            counts[code]
            for code in [
                "impossible_objection_state",
                "impossible_action_product_state",
                "impossible_unavailable_selected_product",
            ]
        ),
        "false_prior_references": counts["false_prior_reference"],
        "true_prior_reference_misses": counts["true_prior_reference_missed"],
        "hallucinated_turn_numbers": counts["hallucinated_turn_number"],
        "external_action_misses": counts["external_action_miss"],
        "premature_captura_recommendations": counts["premature_captura_recommendation"],
        "captura_external_action_overpromises": counts["captura_external_action_overpromise"],
        "unsupported_channel_claims": counts["unsupported_channel_claim"],
        "explicit_start_false_negatives": counts["explicit_start_false_negative"],
        "need_to_think_false_positives": counts["need_to_think_false_positive"],
        "objection_contradictions": counts["impossible_objection_state"],
        "violation_counts": dict(sorted(counts.items())),
        "violations": violations,
    }
    return summary


def summarize_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    token_totals = [_total_tokens(record.get("token_usage") or {}) for record in records]
    analyzer_tokens = [
        call.get("total_tokens", 0)
        for record in records
        for call in (record.get("token_usage") or {}).get("calls", [])
        if call.get("operation") == "analysis"
    ]
    response_tokens = [
        call.get("total_tokens", 0)
        for record in records
        for call in (record.get("token_usage") or {}).get("calls", [])
        if call.get("operation") == "response"
    ]
    latencies = [float(record.get("latency_ms") or 0) for record in records]
    return {
        "turns": len(records),
        "focus_turns": sum(1 for record in records if record.get("focus")),
        "avg_total_tokens_per_turn": _average(token_totals),
        "avg_analyzer_tokens_per_turn": _average(analyzer_tokens),
        "avg_response_tokens_per_turn": _average(response_tokens),
        "avg_latency_ms": _average(latencies),
        "errors": sum(1 for record in records if record.get("error")),
    }


def previous_vs_new_comparison(
    previous_records: Sequence[Dict[str, Any]],
    new_records: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Optional[float]]]:
    previous = summarize_gates(previous_records)
    new = summarize_gates(new_records)
    previous_perf = summarize_records(previous_records)
    new_perf = summarize_records(new_records)
    rows = {
        "Impossible states": ("impossible_states", previous, new),
        "False prior references": ("false_prior_references", previous, new),
        "Hallucinated turn numbers": ("hallucinated_turn_numbers", previous, new),
        "External action misses": ("external_action_misses", previous, new),
        "Premature Captura recommendations": ("premature_captura_recommendations", previous, new),
        "Explicit-start false negatives": ("explicit_start_false_negatives", previous, new),
        "Objection contradictions": ("objection_contradictions", previous, new),
        "Hard failures": ("hard_failures", previous, new),
        "Analyzer tokens per turn": ("avg_analyzer_tokens_per_turn", previous_perf, new_perf),
        "Analyzer latency": ("avg_latency_ms", previous_perf, new_perf),
        "Full agent tokens per turn": ("avg_total_tokens_per_turn", previous_perf, new_perf),
    }
    comparison: Dict[str, Dict[str, Optional[float]]] = {}
    for label, (key, previous_source, new_source) in rows.items():
        old_value = previous_source.get(key)
        new_value = new_source.get(key)
        delta = None
        if old_value is not None and new_value is not None:
            delta = float(new_value) - float(old_value)
        comparison[label] = {
            "previous_v3": old_value,
            "analyzer_v3": new_value,
            "delta": delta,
        }
    return comparison


def targeted_gates_pass(
    gate_summary: Dict[str, Any],
    previous_summary: Optional[Dict[str, Any]] = None,
) -> bool:
    required_zero = [
        "hard_failures",
        "hallucinated_turn_numbers",
        "impossible_states",
        "external_action_misses",
        "captura_external_action_overpromises",
        "unsupported_channel_claims",
        "explicit_start_false_negatives",
        "need_to_think_false_positives",
    ]
    if any(int(gate_summary.get(key) or 0) != 0 for key in required_zero):
        return False
    if previous_summary and previous_summary.get("focus_turns"):
        return int(gate_summary.get("false_prior_references") or 0) <= int(
            previous_summary.get("false_prior_references") or 0
        )
    return True


def parser_shadow_summary(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    categories = ["actions", "products", "purchase_cues", "prior_references", "channels"]
    summary: Dict[str, Any] = {}
    examples: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        category: {"parser_only": [], "llm_only": [], "agreement": []}
        for category in categories
    }
    for category in categories:
        counts = Counter()
        for record in records:
            telemetry = (
                (record.get("normalized_turn") or {}).get("parser_llm_telemetry") or {}
            ).get(category) or {}
            counts["agreement"] += len(telemetry.get("agreement") or [])
            counts["parser_only"] += len(telemetry.get("parser_only") or [])
            counts["llm_only"] += len(telemetry.get("llm_only") or [])
            counts["conflicts"] += 1 if telemetry.get("conflict") else 0
            for bucket in ["parser_only", "llm_only", "agreement"]:
                if telemetry.get(bucket) and len(examples[category][bucket]) < 5:
                    examples[category][bucket].append(
                        {
                            "case_id": record.get("case_id"),
                            "scenario_id": record.get("scenario_id"),
                            "turn_id": record.get("turn_id"),
                            "values": telemetry.get(bucket),
                        }
                    )
        summary[category] = dict(counts)
    return {
        "categories": summary,
        "examples": examples,
        "patterns_that_may_become_rules": [
            "High-agreement requested external actions such as quote/register/write-system.",
            "High-agreement channel mentions for WhatsApp/Facebook/Instagram availability checks.",
            "High-agreement explicit-start cues that contain link/start/pay language.",
        ],
        "patterns_that_must_remain_semantic": [
            "Soft sarcasm versus persistent hard objection.",
            "Prior references that depend on an assistant commitment.",
            "Scope reduction after a custom/handoff branch.",
        ],
    }


def default_previous_run_paths(manifest: TargetedManifest) -> List[Path]:
    paths: List[Path] = []
    for pattern in manifest.previous_run_globs:
        matches = sorted(
            (Path(path) for path in glob.glob(str(PROJECT_ROOT / pattern))),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
        )
        if matches:
            paths.append(matches[-1])
    return paths


def targeted_markdown_report(result: Dict[str, Any]) -> str:
    lines = [
        f"# Analyzer V3 Targeted Validation: {result['run_id']}",
        "",
        f"- **Status:** {result['terminal_status']}",
        f"- **Analyzer contract:** {result['analyzer_contract_version']}",
        f"- **Manifest:** {result['manifest_version']}",
        f"- **Mode:** {result['mode']}",
        f"- **Offline:** {str(result['offline']).lower()}",
        f"- **Analysis model:** {result['analysis_model']}",
        f"- **Response model:** {result['response_model']}",
        f"- **Live turns:** {result['record_counts']['live_agent']}",
        f"- **Analyzer-only turns:** {result['record_counts']['analyzer_only']}",
        f"- **Focus turns:** {result['record_counts']['focus_turns']}",
        "",
        "## Gates",
        "",
    ]
    lines.extend(_gate_table(result["gate_summary"]))
    lines.extend(["", "## Previous Vs Analyzer V3", ""])
    lines.extend(_comparison_table(result["comparison"]))
    if result["gate_summary"].get("violations"):
        lines.extend(["", "## Targeted Blockers", ""])
        for violation in result["gate_summary"]["violations"][:30]:
            lines.append(f"- `{violation['code']}`: {violation['reason']}")
    lines.extend(
        [
            "",
            "## Full Replay Decision",
            "",
            result["full_replay_recommendation"],
            "",
            result["terminal_status"],
            "",
        ]
    )
    return "\n".join(lines)


def parser_shadow_markdown(result: Dict[str, Any]) -> str:
    parser = result["parser_shadow"]
    lines = [
        "# Parser Shadow Comparison",
        "",
        f"- **Run:** {result['run_id']}",
        f"- **Analyzer contract:** {result['analyzer_contract_version']}",
        "",
        "| Category | Parser true positives | Parser false positives | Parser false negatives | Conflicts |",
        "|---|---:|---:|---:|---:|",
    ]
    for category, counts in parser["categories"].items():
        lines.append(
            f"| {category} | {counts.get('agreement', 0)} | "
            f"{counts.get('parser_only', 0)} | {counts.get('llm_only', 0)} | "
            f"{counts.get('conflicts', 0)} |"
        )
    lines.extend(["", "## LLM-Only Correct Detections", ""])
    for category, examples in parser["examples"].items():
        for example in examples.get("llm_only", [])[:3]:
            lines.append(
                f"- `{category}` {example['scenario_id']} turn {example['turn_id']}: "
                f"{example['values']}"
            )
    lines.extend(["", "## Patterns That May Later Become Deterministic Rules", ""])
    lines.extend(f"- {item}" for item in parser["patterns_that_may_become_rules"])
    lines.extend(["", "## Patterns That Must Remain Semantic", ""])
    lines.extend(f"- {item}" for item in parser["patterns_that_must_remain_semantic"])
    lines.append("")
    return "\n".join(lines)


def previous_comparison_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Analyzer V3 Targeted Comparison",
        "",
        f"- **Run:** {result['run_id']}",
        f"- **Status:** {result['terminal_status']}",
        "",
        "| Metric | Previous V3 | Analyzer V3 | Delta |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(_comparison_table(result["comparison"], include_header=False))
    lines.extend(["", "## Token And Latency Summary", ""])
    for label, summary in [
        ("Analyzer-only", result["analyzer_summary"]),
        ("Targeted live", result["live_summary"]),
        ("Previous V3", summarize_records(result["previous_records"])),
    ]:
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---:|")
        for key in [
            "turns",
            "focus_turns",
            "avg_analyzer_tokens_per_turn",
            "avg_response_tokens_per_turn",
            "avg_total_tokens_per_turn",
            "avg_latency_ms",
            "errors",
        ]:
            lines.append(f"| {key} | {_format_value(summary.get(key))} |")
        lines.append("")
    lines.append(result["terminal_status"])
    lines.append("")
    return "\n".join(lines)


def _ensure_manifest_has_no_embedded_dataset_content(raw: Dict[str, Any]) -> None:
    banned = {"user", "ideal_assistant", "expected"}

    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in banned:
                    raise ValueError(f"Targeted manifest embeds banned dataset field {path}.{key}.")
                walk(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    walk(raw)


def _load_manifest_datasets(manifest: TargetedManifest) -> Dict[str, ValidationDataset]:
    return {
        alias: load_validation_dataset(_project_path(path))
        for alias, path in manifest.datasets.items()
    }


def _project_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _case_refs(case: TargetedCase) -> List[ScenarioRef]:
    if case.scenario_refs:
        return case.scenario_refs
    if case.dataset and case.scenario_id:
        return [
            ScenarioRef(
                dataset=case.dataset,
                scenario_id=case.scenario_id,
                turn_ranges=case.turn_ranges,
                focus_turn_ids=case.focus_turn_ids,
            )
        ]
    return []


def _scenario_by_id(dataset: ValidationDataset, scenario_id: str) -> Optional[ValidationScenario]:
    return next((scenario for scenario in dataset.scenarios if scenario.conversation_id == scenario_id), None)


def _iter_ranges(ranges: Iterable[Sequence[int]]) -> Iterable[Tuple[int, int]]:
    for item in ranges:
        if len(item) != 2:
            raise ValueError(f"turn_ranges entries must be [start, end], got {item!r}")
        start, end = int(item[0]), int(item[1])
        if start <= 0 or end < start:
            raise ValueError(f"Invalid turn range {item!r}")
        yield start, end


def _turn_ids_from_ranges(ranges: Iterable[Sequence[int]]) -> List[int]:
    ids: List[int] = []
    for start, end in _iter_ranges(ranges):
        ids.extend(range(start, end + 1))
    return ids


def _focus_index(manifest: TargetedManifest) -> Dict[Tuple[str, str, int], List[Tuple[str, List[str]]]]:
    index: Dict[Tuple[str, str, int], List[Tuple[str, List[str]]]] = defaultdict(list)
    for case in manifest.cases:
        for ref in _case_refs(case):
            for turn_id in ref.focus_turn_ids:
                index[(ref.dataset, ref.scenario_id, turn_id)].append((case.case_id, case.checks))
    return index


def _offline_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "disable_openai": True,
            "disable_database": True,
            "openai_model": "offline",
        }
    )


def _analyzer_only_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"disable_database": True})


def _compact_lead_state(lead_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in lead_profile.items()
        if key
        in {
            "business_type",
            "main_channel",
            "pain",
            "urgency",
            "buying_signal",
            "current_stage",
            "previous_stage",
            "stage_before_objection",
            "conversation_mode",
            "active_objection",
            "last_action",
            "profile_data",
        }
    }


def _error_record(
    *,
    run_id: str,
    mode: str,
    case_id: str,
    dataset: str,
    scenario_id: str,
    turn: ValidationTurn,
    focus: bool,
    checks: Sequence[str],
    started: float,
    exc: Exception,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "case_id": case_id,
        "dataset": dataset,
        "scenario_id": scenario_id,
        "turn_id": turn.turn_id,
        "focus": focus,
        "checks": list(checks),
        "user_input": turn.user,
        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        "latency_ms": round((perf_counter() - started) * 1000, 2),
    }


def _impossible_state_violations(
    analysis: Dict[str, Any],
    normalized: Dict[str, Any],
) -> List[Dict[str, str]]:
    violations: List[Dict[str, str]] = []
    has_objection = bool(analysis.get("has_objection"))
    objection_type = analysis.get("objection_type") or ObjectionType.NONE.value
    objection_strength = analysis.get("objection_strength") or "none"
    if not has_objection and objection_type != ObjectionType.NONE.value:
        violations.append(
            _violation("impossible_objection_state", "objection_type set while has_objection=false.")
        )
    if objection_type == ObjectionType.NONE.value and objection_strength == "hard":
        violations.append(
            _violation("impossible_objection_state", "Hard objection strength with objection_type=none.")
        )
    if (
        normalized.get("action_requirement") == ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value
        and normalized.get("recommended_product") == ProductFit.MOVIA_CAPTURA.value
    ):
        violations.append(
            _violation("impossible_action_product_state", "External actions derived Captura.")
        )
    if normalized.get("selected_product") in {
        "movia_ventas",
        "movia_pro_comercial",
    }:
        violations.append(
            _violation("impossible_unavailable_selected_product", "Unavailable product was selected.")
        )
    return violations


def _has_prior_reference(analysis: Dict[str, Any], normalized: Dict[str, Any]) -> bool:
    return bool(
        normalized.get("has_prior_reference")
        or analysis.get("references_prior_message")
        or (normalized.get("normalized_prior_reference") or {}).get("type") not in {None, "", "none"}
    )


def _explicit_start(analysis: Dict[str, Any], normalized: Dict[str, Any]) -> bool:
    return bool(
        normalized.get("explicit_start_intent")
        or analysis.get("explicit_start_intent")
        or analysis.get("buying_signal") == BuyingSignal.EXPLICIT_START.value
    )


def _action_requirement(analysis: Dict[str, Any], normalized: Dict[str, Any]) -> str:
    profile_data = ((analysis.get("lead_updates") or {}).get("profile_data") or {})
    normalized_requirement = normalized.get("action_requirement")
    if normalized_requirement == ActionRequirement.UNKNOWN.value:
        normalized_requirement = None
    return str(
        normalized_requirement
        or (normalized.get("known_slot_values") or {}).get("action_requirement")
        or profile_data.get("action_requirement")
        or ActionRequirement.UNKNOWN.value
    )


def _recommended_product(analysis: Dict[str, Any], normalized: Dict[str, Any]) -> str:
    profile_data = ((analysis.get("lead_updates") or {}).get("profile_data") or {})
    return str(
        normalized.get("recommended_product")
        or profile_data.get("known_product_fit")
        or ProductFit.UNKNOWN.value
    )


def _mentions_captura_recommendation(
    selected: Dict[str, Any],
    output: str,
    analysis: Dict[str, Any],
    normalized: Dict[str, Any],
) -> bool:
    return (
        selected.get("micro_action") == MicroAction.RECOMMEND_MOVIA_CAPTURA.value
        or _recommended_product(analysis, normalized) == ProductFit.MOVIA_CAPTURA.value
        or bool(re.search(r"(te conviene|recomiendo|recomendaria|recomendaría).{0,60}captura", output.lower()))
    )


def _routes_to_captura(
    selected: Dict[str, Any],
    analysis: Dict[str, Any],
    normalized: Dict[str, Any],
) -> bool:
    return (
        selected.get("micro_action") == MicroAction.RECOMMEND_MOVIA_CAPTURA.value
        or _recommended_product(analysis, normalized) == ProductFit.MOVIA_CAPTURA.value
    )


def _routes_to_hibrido_or_handoff(
    selected: Dict[str, Any],
    analysis: Dict[str, Any],
    normalized: Dict[str, Any],
) -> bool:
    return (
        selected.get("micro_action")
        in {
            MicroAction.RECOMMEND_MOVIA_HIBRIDO.value,
            MicroAction.DIFFERENTIATE_CAPTURA_VS_HIBRIDO.value,
            MicroAction.DETERMINE_IF_EXTERNAL_ACTIONS_ARE_NEEDED.value,
            MicroAction.REDIRECT_CUSTOM_SCOPE.value,
        }
        or selected.get("macro_action") == MacroAction.HANDOFF_TO_MIGUEL.value
        or _recommended_product(analysis, normalized) == ProductFit.MOVIA_HIBRIDO.value
    )


def captura_external_overpromise(output: str) -> bool:
    text = _normalize_text(output)
    if "captura" not in text:
        return False
    external_phrases = [
        "registre pedidos",
        "registra pedidos",
        "registrar pedidos",
        "crea pedidos",
        "crear pedidos",
        "escribe datos",
        "suba a mi panel",
        "sistema externo",
        "registre en una hoja",
    ]
    if not any(phrase in text for phrase in external_phrases):
        return False
    safe_negations = [
        "no registra",
        "no puede registrar",
        "sin registrar",
        "sin registrar pedidos",
        "no crea",
        "no puede crear",
        "sin crear",
        "no escribe",
        "no puede escribir",
        "sin escribir",
        "solo recopila",
        "solo recopilar",
        "solo recoge",
        "pero no registra",
        "pero no puede",
    ]
    return not any(phrase in text for phrase in safe_negations)


def unsupported_channel_claim(output: str) -> bool:
    text = _normalize_text(output)
    if "multicanal" in text and not re.search(r"no.{0,30}multicanal", text):
        return True
    for channel in ["facebook", "instagram"]:
        for match in re.finditer(channel, text):
            window = text[match.start() : match.start() + 120]
            positive = any(
                word in window
                for word in ["disponible", "disponibles", "funciona", "funcionan", "activo", "activos", "listo", "listos"]
            )
            safe = any(
                word in window
                for word in [
                    "no ",
                    "aun no",
                    "aún no",
                    "todavia no",
                    "todavía no",
                    "proceso",
                    "upcoming",
                    "futuro",
                    "limita",
                    "limitado",
                    "limitada",
                    "solo whatsapp",
                    "por ahora whatsapp",
                    "whatsapp business es el canal disponible",
                ]
            )
            if positive and not safe:
                return True
    return False


def _normalize_text(value: str) -> str:
    text = value.lower()
    for source, target in {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }.items():
        text = text.replace(source, target)
    return text


def _violation(code: str, reason: str) -> Dict[str, str]:
    return {"code": code, "reason": reason}


def _dedupe_violations(violations: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped = []
    for violation in violations:
        key = (violation["code"], violation["reason"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(violation))
    return deduped


def _usage_total(usages: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for usage in usages:
        for key in total:
            total[key] += int(usage.get(key) or 0)
    return total


def _total_tokens(token_usage: Dict[str, Any]) -> int:
    if "total" in token_usage:
        return int((token_usage.get("total") or {}).get("total_tokens") or 0)
    return sum(int(call.get("total_tokens") or 0) for call in token_usage.get("calls") or [])


def _average(values: Sequence[float]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 2)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _strip_records(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"manifest", "analyzer_records", "live_records", "previous_records"}
    }


def _gate_table(summary: Dict[str, Any]) -> List[str]:
    lines = ["| Gate | Count |", "|---|---:|"]
    for key in [
        "hard_failures",
        "impossible_states",
        "false_prior_references",
        "true_prior_reference_misses",
        "hallucinated_turn_numbers",
        "external_action_misses",
        "premature_captura_recommendations",
        "captura_external_action_overpromises",
        "unsupported_channel_claims",
        "explicit_start_false_negatives",
        "need_to_think_false_positives",
    ]:
        lines.append(f"| {key} | {summary.get(key, 0)} |")
    return lines


def _comparison_table(
    comparison: Dict[str, Dict[str, Optional[float]]],
    *,
    include_header: bool = True,
) -> List[str]:
    lines = []
    if include_header:
        lines.extend(["| Metric | Previous V3 | Analyzer V3 | Delta |", "|---|---:|---:|---:|"])
    for metric, values in comparison.items():
        lines.append(
            f"| {metric} | {_format_value(values.get('previous_v3'))} | "
            f"{_format_value(values.get('analyzer_v3'))} | {_format_value(values.get('delta'))} |"
        )
    return lines


def _format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def make_targeted_run_id() -> str:
    return f"analyzer-v3-targeted-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"


def run_id_timestamp(run_id: str) -> str:
    parts = run_id.split("-")
    for part in parts:
        if len(part) == 16 and part.endswith("Z"):
            return part
    return now_iso()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
