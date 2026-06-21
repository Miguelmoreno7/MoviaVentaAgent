from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import psycopg
from psycopg.rows import dict_row

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.evaluation.models import EvaluationRunResult


REQUIRED_PHASE6_MIGRATIONS = [
    "202606030001_init_movia_sales_agent",
    "202606040001_stage_machine_v2",
    "202606040002_active_objection_v2",
    "202606050001_parallel_objection_mode_v3",
]

REQUIRED_PHASE6_COLUMNS = [
    "previous_stage",
    "stage_before_objection",
    "stage_reason_code",
    "stage_reason",
    "stage_entered_at",
    "stage_updated_at",
    "active_objection",
    "conversation_mode",
]

PHASE6_GATE_THRESHOLDS = {
    "commercial_accuracy": 0.95,
    "policy_compliance": 0.95,
    "scope_control": 0.95,
    "memory_consistency": 0.80,
    "source_selection": 0.70,
    "response_quality": 0.75,
    "sales_progression": 0.70,
    "objection_handling": 0.70,
}


def load_run_result(path: Path) -> EvaluationRunResult:
    return EvaluationRunResult.model_validate_json(path.read_text(encoding="utf-8"))


def database_phase6_status(settings: Settings) -> Dict[str, Any]:
    if not settings.database_url:
        return {
            "status": "blocked",
            "database_url_present": False,
            "ready": False,
            "missing_migrations": REQUIRED_PHASE6_MIGRATIONS,
            "missing_columns": REQUIRED_PHASE6_COLUMNS,
        }

    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        applied = {
            row["version"]
            for row in conn.execute(
                """
                select version
                from public.movia_schema_migrations
                """
            ).fetchall()
        }
        columns = {
            row["column_name"]
            for row in conn.execute(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = 'movia_lead_profiles'
                """
            ).fetchall()
        }
        counts = {
            row["table_name"]: int(row["count"])
            for row in conn.execute(
                """
                select 'movia_products' as table_name, count(*) from public.movia_products
                union all select 'movia_policies', count(*) from public.movia_policies
                union all select 'movia_lead_profiles', count(*) from public.movia_lead_profiles
                union all select 'movia_conversation_messages', count(*) from public.movia_conversation_messages
                union all select 'movia_knowledge_documents', count(*) from public.movia_knowledge_documents
                union all select 'movia_knowledge_chunks', count(*) from public.movia_knowledge_chunks
                """
            ).fetchall()
        }

    missing_migrations = [
        migration for migration in REQUIRED_PHASE6_MIGRATIONS if migration not in applied
    ]
    missing_columns = [column for column in REQUIRED_PHASE6_COLUMNS if column not in columns]
    ready = not missing_migrations and not missing_columns
    return {
        "status": "ready" if ready else "blocked",
        "database_url_present": True,
        "ready": ready,
        "applied_migrations": sorted(applied),
        "missing_migrations": missing_migrations,
        "required_columns_present": sorted(set(REQUIRED_PHASE6_COLUMNS) & columns),
        "missing_columns": missing_columns,
        "table_counts": counts,
    }


def evaluate_phase6_gates(
    result: EvaluationRunResult,
    *,
    require_progression: bool,
) -> Dict[str, Any]:
    gates = []
    gates.append(_gate("hard_failures_zero", len(result.hard_failures) == 0, 0, len(result.hard_failures)))
    for category, threshold in PHASE6_GATE_THRESHOLDS.items():
        if category in {"sales_progression", "objection_handling"} and not require_progression:
            gates.append(
                {
                    "name": f"{category}_minimum",
                    "status": "diagnostic",
                    "threshold": threshold,
                    "actual": result.category_scores.get(category),
                }
            )
            continue
        actual = result.category_scores.get(category)
        gates.append(
            _gate(
                f"{category}_minimum",
                actual is not None and actual >= threshold,
                threshold,
                actual,
            )
        )

    critical_defects = _critical_response_defects(result)
    known_slot_repetitions = critical_defects.count("asked_known_information")
    premature_closes = critical_defects.count("premature_close") + _hard_failure_count(
        result, "premature_direct_close"
    )
    irrelevant_rag = critical_defects.count("irrelevant_context") + _failed_metric_count(
        result, "rag.context_relevance"
    )
    gates.extend(
        [
            _gate("known_slot_critical_repetitions_zero", known_slot_repetitions == 0, 0, known_slot_repetitions),
            _gate("premature_direct_closes_zero", premature_closes == 0, 0, premature_closes),
            _gate("irrelevant_rag_injection_zero", irrelevant_rag == 0, 0, irrelevant_rag),
        ]
    )
    passed = all(gate["status"] in {"pass", "diagnostic"} for gate in gates)
    return {
        "run_id": result.run_id,
        "suite_type": result.suite_type,
        "passed": passed,
        "gates": gates,
    }


def combined_phase6_recommendation(
    *,
    database_status: Dict[str, Any],
    gate_reports: Iterable[Dict[str, Any]],
    adaptive_hybrid_ran: bool = False,
    adaptive_hybrid_passed: bool = False,
) -> Dict[str, str]:
    reports = list(gate_reports)
    if not database_status.get("ready"):
        return {
            "recommendation": "NOT READY",
            "reason": "Database persistence prerequisites are not satisfied.",
        }
    failed = [report for report in reports if not report.get("passed")]
    if failed:
        return {
            "recommendation": "NOT READY",
            "reason": "One or more deterministic validation suites failed Phase 6 gates.",
        }
    if not adaptive_hybrid_ran:
        return {
            "recommendation": "READY FOR PREDEPLOY HYBRID ONLY",
            "reason": "Deterministic gates passed, but adaptive hybrid has not been run.",
        }
    if adaptive_hybrid_passed:
        return {
            "recommendation": "READY FOR LIMITED PILOT",
            "reason": "Deterministic and adaptive predeploy gates passed.",
        }
    return {
        "recommendation": "NOT READY",
        "reason": "Adaptive hybrid predeploy did not pass.",
    }


def markdown_phase6_gate_report(
    *,
    database_status: Dict[str, Any],
    gate_reports: List[Dict[str, Any]],
    recommendation: Dict[str, str],
) -> str:
    lines = [
        "# Phase 6 Gate Report",
        "",
        f"- **Database status:** {database_status.get('status')}",
        f"- **Recommendation:** {recommendation['recommendation']}",
        f"- **Reason:** {recommendation['reason']}",
        "",
        "## Database",
        "",
        "| Check | Value |",
        "|---|---|",
        f"| Ready | {database_status.get('ready')} |",
        f"| Missing migrations | {', '.join(database_status.get('missing_migrations') or []) or 'none'} |",
        f"| Missing columns | {', '.join(database_status.get('missing_columns') or []) or 'none'} |",
    ]
    counts = database_status.get("table_counts") or {}
    for table_name, count in sorted(counts.items()):
        lines.append(f"| {table_name} rows | {count} |")

    for report in gate_reports:
        lines.extend(
            [
                "",
                f"## {report['suite_type']} `{report['run_id']}`",
                "",
                "| Gate | Threshold | Actual | Status |",
                "|---|---:|---:|---|",
            ]
        )
        for gate in report["gates"]:
            lines.append(
                f"| {gate['name']} | {_format(gate.get('threshold'))} | "
                f"{_format(gate.get('actual'))} | {gate['status']} |"
            )
    lines.append("")
    return "\n".join(lines)


def _gate(name: str, passed: bool, threshold: Any, actual: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "threshold": threshold,
        "actual": actual,
    }


def _critical_response_defects(result: EvaluationRunResult) -> List[str]:
    defects: List[str] = []
    for scenario in result.scenario_results:
        for turn in scenario.turns:
            for metric in turn.metrics:
                if metric.name != "response_quality.critical_defects":
                    continue
                defects.extend(list(metric.actual or []))
    return defects


def _hard_failure_count(result: EvaluationRunResult, code: str) -> int:
    return sum(failure.code == code for failure in result.hard_failures)


def _failed_metric_count(result: EvaluationRunResult, name: str) -> int:
    return sum(
        metric.name == name and metric.status == "failed"
        for scenario in result.scenario_results
        for turn in scenario.turns
        for metric in turn.metrics
    )


def _format(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
