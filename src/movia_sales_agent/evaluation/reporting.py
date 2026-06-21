from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.evaluation.models import (
    EvaluationRunResult,
    MetricResult,
    ScenarioEvaluationResult,
)
from movia_sales_agent.evaluation.contracts_v3 import (
    category_applicability,
    category_is_authoritative,
)
from movia_sales_agent.evaluation.scoring import CATEGORY_THRESHOLDS


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "evaluations"
OVERALL_THRESHOLD = 0.80


def write_reports(
    result: EvaluationRunResult,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    run_root = output_root / result.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run.json").write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    with (run_root / "turns.jsonl").open("w", encoding="utf-8") as file:
        for scenario in result.scenario_results:
            for turn in scenario.turns:
                file.write(turn.model_dump_json() + "\n")
    (run_root / "summary.md").write_text(markdown_report(result), encoding="utf-8")
    return run_root


def markdown_report(result: EvaluationRunResult) -> str:
    counters = report_counters(result)
    token_summary = report_token_summary(result)
    lines = [
        f"# MovIA Validation Report: {result.run_id}",
        "",
        f"- **Status:** {'PASS' if result.passed else 'FAIL'}",
        f"- **Evaluation contract:** {result.evaluation_contract_version}",
        f"- **Commercial contract:** {result.commercial_contract_version}",
        f"- **Dataset commercial contract:** {result.dataset_summary.commercial_contract_version}",
        f"- **Suite type:** {result.suite_type}",
        f"- **Causal continuity:** {str(result.causal_continuity).lower()}",
        f"- **Dataset version:** {result.dataset_version}",
        f"- **Run mode:** {result.run_mode}",
        f"- **Primary applicable score:** {format_score(result.overall_score)}",
        f"- **Scenarios:** {len(result.scenario_results)}",
        f"- **Turns:** {sum(len(item.turns) for item in result.scenario_results)}",
        f"- **Agent tokens:** {result.agent_token_usage.get('total_tokens', 0):,}",
        f"- **Hard failures:** {len(result.hard_failures)}",
        f"- **Started:** {result.started_at}",
        f"- **Completed:** {result.completed_at}",
        "",
        "## Pass Policy",
        "",
        "Only authoritative categories for this suite affect pass/fail. "
        "Diagnostic categories remain visible but do not enter the primary score.",
        "",
        "| Requirement | Applicability | Threshold | Actual | Status |",
        "|---|---|---:|---:|---|",
        f"| Primary applicable score | authoritative | {OVERALL_THRESHOLD:.3f} | "
        f"{format_score(result.overall_score)} | {threshold_status(result.overall_score, OVERALL_THRESHOLD)} |",
    ]
    for category, threshold in sorted(CATEGORY_THRESHOLDS.items()):
        actual = result.category_scores.get(category)
        applicability = category_applicability(category, result.suite_type)
        if not category_is_authoritative(category, result.suite_type):
            lines.append(
                f"| {category} | {applicability} | n/a | {format_score(actual)} | DIAGNOSTIC |"
            )
            continue
        lines.append(
            f"| {category} | {applicability} | {threshold:.3f} | {format_score(actual)} | "
            f"{threshold_status(actual, threshold)} |"
        )

    if result.score_groups:
        lines.extend(
            [
                "",
                "## Score Groups",
                "",
                "| Group | Score |",
                "|---|---:|",
            ]
        )
        for group, score in sorted(result.score_groups.items()):
            lines.append(f"| {group} | {format_score(score)} |")

    lines.extend(
        [
            "",
            "## Failure Inventory",
            "",
            "| Bucket | Count |",
            "|---|---:|",
        ]
    )
    for name, count in counters.items():
        lines.append(f"| {name} | {count} |")

    lines.extend(
        [
            "",
            "## Token Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Avg total agent tokens / turn | {format_score(token_summary.get('avg_total_tokens_per_turn'))} |",
            f"| Avg actual response input tokens / turn | {format_score(token_summary.get('avg_response_input_tokens'))} |",
            f"| Avg estimated response input tokens / turn | {format_score(token_summary.get('avg_estimated_response_input_tokens'))} |",
        ]
    )
    section_averages = token_summary.get("section_averages") or {}
    if section_averages:
        lines.extend(
            [
                "",
                "### Response Package Section Estimates",
                "",
                "| Section | Avg estimated tokens |",
                "|---|---:|",
            ]
        )
        for section, value in sorted(section_averages.items()):
            lines.append(f"| {section} | {format_score(value)} |")

    root_causes = root_cause_counts(result)
    if root_causes:
        lines.extend(
            [
                "",
                "## Root Causes",
                "",
                "| Cause | Count |",
                "|---|---:|",
            ]
        )
        for cause, count in root_causes.most_common():
            lines.append(f"| `{escape_cell(cause)}` | {count} |")

    lines.extend(
        [
            "",
            "## Category Scores",
            "",
            "| Category | Score |",
            "|---|---:|",
        ]
    )
    for category, score in sorted(result.category_scores.items()):
        lines.append(f"| {category} | {score:.3f} |")

    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| Scenario | Persona | Score | Status | Hard failures |",
            "|---|---|---:|---|---:|",
        ]
    )
    for scenario in result.scenario_results:
        lines.append(
            f"| {scenario.conversation_id} | {escape_cell(scenario.persona)} | "
            f"{format_score(scenario.overall_score)} | "
            f"{'PASS' if scenario.passed else 'FAIL'} | {len(scenario.hard_failures)} |"
        )

    if result.hard_failures:
        lines.extend(["", "## Hard Failures", ""])
        for failure in result.hard_failures:
            turn = f" turn {failure.turn_id}" if failure.turn_id else ""
            lines.append(
                f"- `{failure.code}` ({failure.category}){turn}: {failure.reason}"
            )

    if result.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in result.notes)

    for scenario in result.scenario_results:
        lines.extend(scenario_markdown(scenario))
    lines.append("")
    return "\n".join(lines)


def scenario_markdown(scenario: ScenarioEvaluationResult) -> List[str]:
    lines = [
        "",
        f"## {scenario.conversation_id}",
        "",
        f"**Goal:** {scenario.success_goal}",
        "",
        "| Turn | Stage | Macro action | Applicable score | Failed metrics | Hard failures |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for turn in scenario.turns:
        applicable = [
            metric.score
            for metric in turn.metrics
            if metric.status in {"passed", "failed"} and metric.score is not None
        ]
        score = sum(applicable) / len(applicable) if applicable else None
        failed = sum(metric.status == "failed" for metric in turn.metrics)
        lines.append(
            f"| {turn.turn_id} | {escape_cell(str(turn.lead_state.get('current_stage') or ''))} | "
            f"{escape_cell(str(turn.selected_action.get('macro_action') or ''))} | "
            f"{format_score(score)} | {failed} | {len(turn.hard_failures)} |"
        )

    failed_metrics = [
        (turn.turn_id, metric)
        for turn in scenario.turns
        for metric in turn.metrics
        if metric.status == "failed"
    ] + [
        (None, metric)
        for metric in scenario.conversation_metrics
        if metric.status == "failed"
    ]
    if failed_metrics:
        counts = Counter(metric.name for _turn_id, metric in failed_metrics)
        lines.extend(
            [
                "",
                "### Failed Metric Counts",
                "",
                "| Metric | Count |",
                "|---|---:|",
            ]
        )
        for name, count in counts.most_common():
            lines.append(f"| `{name}` | {count} |")
        lines.extend(["", "### Failure Samples", ""])
        sample_limit = 10
        for turn_id, metric in failed_metrics[:sample_limit]:
            location = f"Turn {turn_id}: " if turn_id else "Conversation: "
            detail = metric.reason or (
                f"expected={compact(metric.expected)} actual={compact(metric.actual)}"
            )
            lines.append(
                f"- {location}`{metric.name}` = {format_score(metric.score)}. {detail}"
            )
        if len(failed_metrics) > sample_limit:
            lines.append(
                f"- {len(failed_metrics) - sample_limit} additional failures are available in "
                "`run.json` and `turns.jsonl`."
            )
    return lines


def all_metrics(result: EvaluationRunResult) -> List[MetricResult]:
    metrics = []
    for scenario in result.scenario_results:
        for turn in scenario.turns:
            metrics.extend(turn.metrics)
        metrics.extend(scenario.conversation_metrics)
    return metrics


def report_counters(result: EvaluationRunResult) -> Dict[str, int]:
    metrics = all_metrics(result)
    return {
        "hard_failures": len(result.hard_failures),
        "rule_failures": sum(
            metric.status == "failed" and metric.name.startswith("rules.")
            for metric in metrics
        ),
        "soft_trace_mismatches": sum(
            metric.status == "failed" and metric.name.startswith("trace.")
            for metric in metrics
        ),
        "partial_source_matches": sum(
            metric.name == "source.expected_recall"
            and metric.status == "failed"
            and metric.score is not None
            and 0.0 < float(metric.score) < 1.0
            for metric in metrics
        ),
        "judge_failures": sum(
            metric.framework in {"ragas", "deepeval", "response_quality"}
            and metric.status in {"failed", "error"}
            for metric in metrics
        ),
        "response_quality_defects": sum(
            metric.name == "response_quality.critical_defects"
            and metric.status == "failed"
            for metric in metrics
        ),
        "skipped_metrics": sum(metric.status == "skipped" for metric in metrics),
        "not_applicable_metrics": sum(metric.status == "not_applicable" for metric in metrics),
    }


def report_token_summary(result: EvaluationRunResult) -> Dict[str, object]:
    turns = [
        turn
        for scenario in result.scenario_results
        for turn in scenario.turns
    ]
    turn_count = len(turns)
    total_tokens = int(result.agent_token_usage.get("total_tokens") or 0)
    response_inputs = []
    estimated_response_inputs = []
    section_values: Dict[str, List[int]] = {}
    for turn in turns:
        for call in (turn.token_usage or {}).get("calls") or []:
            if call.get("operation") == "response":
                response_inputs.append(int(call.get("input_tokens") or 0))
        estimates = (turn.response_metadata or {}).get("response_package_token_estimates") or {}
        if estimates.get("response_input_total_estimate") is not None:
            estimated_response_inputs.append(int(estimates["response_input_total_estimate"]))
        for section in [
            "system_prompt",
            "commercial_instruction",
            "lead_context",
            "official_facts",
            "playbook",
            "rag_context",
            "recent_messages",
        ]:
            if estimates.get(section) is not None:
                section_values.setdefault(section, []).append(int(estimates[section]))
    return {
        "avg_total_tokens_per_turn": total_tokens / turn_count if turn_count else None,
        "avg_response_input_tokens": _average(response_inputs),
        "avg_estimated_response_input_tokens": _average(estimated_response_inputs),
        "section_averages": {
            section: _average(values)
            for section, values in section_values.items()
            if values
        },
    }


def root_cause_counts(result: EvaluationRunResult) -> Counter:
    causes = Counter()
    for failure in result.hard_failures:
        causes[f"hard_failure.{failure.code}"] += 1
    for metric in all_metrics(result):
        if metric.status not in {"failed", "error"}:
            continue
        if metric.name.startswith("rules."):
            causes[f"rule_failure.{metric.category}"] += 1
        elif metric.name.startswith("trace."):
            causes[f"trace_mismatch.{metric.name.removeprefix('trace.')}"] += 1
        elif metric.name == "source.expected_recall":
            causes["source_selection.expected_recall"] += 1
        elif metric.framework in {"ragas", "deepeval", "response_quality"}:
            causes[f"judge.{metric.framework}.{metric.name}"] += 1
        else:
            causes[f"metric.{metric.name}"] += 1
    return causes


def threshold_status(value: object, threshold: float) -> str:
    if value is None:
        return "n/a"
    return "PASS" if float(value) >= threshold else "FAIL"


def _average(values: List[int]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def format_score(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def compact(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 180 else text[:177] + "..."


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
