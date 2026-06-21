from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from openai import OpenAI

from movia_sales_agent.analyzer.contract_v3 import (
    ANALYZER_CONTRACT_VERSION,
    ANALYZER_V3_SCHEMA,
    AnalyzerTurnObservation,
    observation_to_turn_analysis,
    validate_analyzer_observation,
)
from movia_sales_agent.analyzer.normalizer import (
    NORMALIZED_TURN_CONTRACT_VERSION,
    normalize_analyzer_turn,
)
from movia_sales_agent.analyzer.shadow_parser import ShadowSignalParser
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import get_settings
from movia_sales_agent.services.openai_service import json_default, response_usage


ATOMIC_RUN = (
    PROJECT_ROOT
    / "artifacts"
    / "evaluations"
    / "requirement-v3-phase4-atomic-live"
    / "movia-eval-20260611T055355Z-a0d168"
    / "run.json"
)
COHERENT_RUN = (
    PROJECT_ROOT
    / "artifacts"
    / "evaluations"
    / "requirement-v3-phase4-coherent-live"
    / "movia-eval-20260611T060949Z-4fcc86"
    / "run.json"
)
DATASET_PATH = PROJECT_ROOT / "movia_validation_package" / "analyzer_model_benchmark_v1.json"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "analyzer-model-benchmark"
REPORT_PATH = PROJECT_ROOT / "docs" / "evaluation" / "ANALYZER_MODEL_BENCHMARK.md"

BASELINE_MODEL = "gpt-4.1-mini"
MODELS = [BASELINE_MODEL, "gpt-5-mini"]
REPETITIONS = 2

ANALYZER_PROMPT = (
    "Analiza un mensaje de preventa de MovIA y devuelve solo JSON válido bajo Analyzer Contract V3.1. "
    "Tu tarea es observar lenguaje, no tomar decisiones comerciales. "
    "No recomiendes producto, no elijas etapa, no elijas acción comercial, no decidas CTA y no generes next_question. "
    "No devuelvas has_objection, references_prior_message, explicit_start_intent, explicit_turn_number, "
    "action_requirement, known_product_fit, recommended_product, sales_stage, macro_action, micro_action, cta_type ni needs_rag. "
    "Distingue entre lo que la persona le pregunta al vendedor de MovIA ahora y lo que quiere que haga el agente después de comprarlo. "
    "observed_business_problems captura dolores operativos actuales observables en el mensaje. "
    "requested_agent_capabilities solo captura capacidades futuras pedidas explícitamente para el agente comprado. "
    "requested_agent_actions solo captura acciones externas futuras pedidas explícitamente para ese agente, como agendar, cotizar, registrar, leer o escribir en sistemas. "
    "No conviertas preguntas actuales de precio, proceso o venta al asesor en capacidades futuras del agente. "
    "requested_product solo identifica un producto mencionado por el usuario; nunca recomiendes uno. "
    "Una pregunta de precio no es una objeción; solo marca price_objection cuando haya resistencia a pagar. "
    "purchase_readiness.level=explicit_start solo si el usuario pide iniciar, contratar, pagar o recibir link. "
    "prior_reference.type no debe usar turnos numéricos; usa topic/entity/assistant commitment cuando haya evidencia. "
    "Cada evidence_span requerido debe ser una frase literal del mensaje actual."
)

CASE_SPECS: List[Dict[str, Any]] = [
    {
        "case_id": "AMB-001-false-future-action-start-link",
        "category": "false_future_agent_action",
        "run": "coherent",
        "scenario": "MOVIA-COH-001",
        "turn": 6,
        "expected": {
            "primary_intent": "explicit_start_request",
            "purchase_readiness_level": "explicit_start",
            "requested_agent_actions_exclude": ["schedule_appointment"],
            "prior_reference_not_type": "none",
        },
        "critical_fields": ["primary_intent", "purchase_readiness", "requested_agent_actions"],
        "control": False,
    },
    {
        "case_id": "AMB-002-requirement-change-prices-only",
        "category": "requirement_change",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 9,
        "force_previous_requirement_profile": {
            "requirement_profile_version": "1.0",
            "observed_business_problems": [],
            "informational_capabilities": [],
            "sales_capabilities": [],
            "external_actions": [
                {
                    "type": "schedule_appointment",
                    "evidence_span": "quiero que agende citas tambien",
                    "strength": "explicit",
                    "active": True,
                    "source_turn": 8,
                }
            ],
            "declared_external_action_count": None,
            "requirement_class": "external_actions",
            "first_confirmed_turn": 8,
            "last_updated_turn": 8,
            "sources": {"external_actions": {"schedule_appointment": {"source_turn": 8, "active": True}}},
        },
        "expected": {
            "requested_agent_capabilities_include_any": ["provide_prices", "answer_customer_questions"],
            "requested_agent_actions_exclude": [
                "schedule_appointment",
                "generate_quote",
                "create_order",
                "read_external_system",
                "write_external_system",
                "update_external_record",
                "send_reminder",
                "follow_up_lead",
                "send_notification",
                "take_payment",
                "unknown_external_action",
            ],
            "contract_limitation": "Analyzer V3.1 cannot directly express replacement/removal of a prior requirement; downstream profile replacement is excluded from this benchmark score.",
        },
        "critical_fields": ["requested_agent_capabilities", "requested_agent_actions"],
        "control": False,
    },
    {
        "case_id": "AMB-003-active-objection-resolution",
        "category": "active_objection_resolution",
        "run": "coherent",
        "scenario": "MOVIA-COH-003",
        "turn": 6,
        "force_previous_active_objection": {
            "active": True,
            "resolved": False,
            "type": "price_objection",
            "strength": "hard",
            "status": "active",
            "current_step": "clarify_value",
        },
        "expected": {
            "objection_relation_allowed": ["resolved", "clarified", "continuation", "none"],
            "representational_limitation": "Analyzer V3.1 can emit objection relation only when it observes an objection candidate; softening/resolution without a new objection is partly representationally limited.",
        },
        "critical_fields": ["objection_relation"],
        "control": False,
    },
    {
        "case_id": "AMB-004-deposit-policy-reference",
        "category": "deposit_policy_reference",
        "run": "coherent",
        "scenario": "MOVIA-MEM-002",
        "turn": 5,
        "expected": {
            "prior_reference_not_type": "none",
            "topics_any": ["deposit", "policy", "refund_policy", "pricing"],
            "primary_intent_not": "unknown",
        },
        "critical_fields": ["prior_reference", "topics", "primary_intent"],
        "control": False,
    },
    {
        "case_id": "AMB-005-refund-deposit-policy",
        "category": "refund_deposit_policy",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 12,
        "expected": {
            "topics_any": ["refund_policy", "deposit", "pricing"],
            "primary_intent_not": "unknown",
            "not_only_pricing": True,
        },
        "critical_fields": ["primary_intent", "topics"],
        "control": False,
    },
    {
        "case_id": "AMB-006-no-prior-captura-price",
        "category": "no_invented_historical_reference",
        "run": "coherent",
        "scenario": "MOVIA-COH-001",
        "turn": 4,
        "expected": {
            "primary_intent": "pricing_question",
            "topics_any": ["pricing"],
            "prior_reference_type": "none",
            "requested_product": "movia_captura",
            "objection_type": "none",
        },
        "critical_fields": ["prior_reference", "primary_intent", "objection_type"],
        "control": True,
    },
    {
        "case_id": "AMB-007-no-prior-answers-only",
        "category": "answers_only_requirement",
        "run": "coherent",
        "scenario": "MOVIA-COH-001",
        "turn": 3,
        "expected": {
            "requested_agent_capabilities_include_all": ["answer_customer_questions", "capture_lead_data"],
            "requested_agent_actions_exclude": ["schedule_appointment", "generate_quote", "write_external_system"],
            "prior_reference_type": "none",
        },
        "critical_fields": ["requested_agent_capabilities", "requested_agent_actions", "prior_reference"],
        "control": True,
    },
    {
        "case_id": "AMB-008-current-process-question-not-capability",
        "category": "current_process_question",
        "run": "coherent",
        "scenario": "MOVIA-COH-001",
        "turn": 5,
        "expected": {
            "topics_any": ["onboarding", "platform_process", "pricing"],
            "requested_agent_capabilities_exclude": ["explain_business_process"],
            "requested_agent_actions_exclude": ["schedule_appointment"],
            "prior_reference_type": "none",
        },
        "critical_fields": ["requested_agent_capabilities", "requested_agent_actions", "prior_reference"],
        "control": True,
    },
    {
        "case_id": "AMB-009-explicit-schedule-request",
        "category": "explicit_external_action",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 8,
        "expected": {
            "requested_agent_actions_include_all": ["schedule_appointment"],
            "topics_any": ["product_scope", "integration", "whatsapp"],
            "purchase_readiness_not_level": "explicit_start",
        },
        "critical_fields": ["requested_agent_actions", "purchase_readiness"],
        "control": True,
    },
    {
        "case_id": "AMB-010-quote-and-system-write",
        "category": "explicit_external_action",
        "run": "coherent",
        "scenario": "MOVIA-COH-004",
        "turn": 5,
        "expected": {
            "requested_agent_actions_include_all": ["generate_quote", "write_external_system"],
            "requested_agent_actions_exclude": ["schedule_appointment"],
            "topics_any": ["integration", "product_scope"],
        },
        "critical_fields": ["requested_agent_actions"],
        "control": True,
    },
    {
        "case_id": "AMB-011-external-system-write-notify",
        "category": "explicit_external_action",
        "run": "coherent",
        "scenario": "MOVIA-COH-005",
        "turn": 3,
        "expected": {
            "requested_agent_actions_include_any": ["write_external_system", "send_notification"],
            "topics_any": ["integration", "product_scope"],
        },
        "critical_fields": ["requested_agent_actions"],
        "control": True,
    },
    {
        "case_id": "AMB-012-audio-capability-question",
        "category": "capability_question",
        "run": "atomic",
        "scenario": "MOVIA-VAL-004",
        "turn": 8,
        "expected": {
            "requested_agent_capabilities_include_all": ["understand_audio"],
            "requested_agent_actions_exclude": ["read_external_system", "write_external_system"],
            "prior_reference_not_type": "assistant_commitment_reference",
        },
        "critical_fields": ["requested_agent_capabilities", "requested_agent_actions"],
        "control": True,
    },
    {
        "case_id": "AMB-013-hibrido-price-question",
        "category": "product_pricing_question",
        "run": "coherent",
        "scenario": "MOVIA-COH-005",
        "turn": 5,
        "expected": {
            "primary_intent": "pricing_question",
            "topics_any": ["pricing"],
            "requested_product": "movia_hibrido",
            "objection_type": "none",
        },
        "critical_fields": ["primary_intent", "requested_product", "objection_type"],
        "control": True,
    },
    {
        "case_id": "AMB-014-true-price-objection",
        "category": "true_price_objection",
        "run": "coherent",
        "scenario": "MOVIA-COH-003",
        "turn": 3,
        "expected": {
            "objection_type": "price_objection",
            "objection_strength": "hard",
            "purchase_readiness_not_level": "explicit_start",
        },
        "critical_fields": ["objection_type", "objection_strength"],
        "control": True,
    },
    {
        "case_id": "AMB-015-trust-objection",
        "category": "true_trust_objection",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 6,
        "expected": {
            "objection_type_any": ["trust_objection", "fear_wrong_answers", "not_sure_if_needed"],
            "purchase_readiness_not_level": "explicit_start",
        },
        "critical_fields": ["objection_type"],
        "control": False,
    },
    {
        "case_id": "AMB-016-true-historical-reference",
        "category": "true_historical_reference",
        "run": "atomic",
        "scenario": "MOVIA-VAL-002",
        "turn": 7,
        "expected": {
            "prior_reference_not_type": "none",
            "topics_any": ["pricing"],
            "primary_intent": "pricing_question",
        },
        "critical_fields": ["prior_reference", "primary_intent"],
        "control": True,
    },
    {
        "case_id": "AMB-017-business-problem-no-capability",
        "category": "business_problem_without_requested_capability",
        "run": "coherent",
        "scenario": "MOVIA-COH-001",
        "turn": 2,
        "expected": {
            "observed_business_problems_include_any": ["slow_response", "repetitive_questions", "missed_leads"],
            "requested_agent_capabilities_exclude": ["provide_prices", "answer_customer_questions"],
            "requested_agent_actions_exclude": ["schedule_appointment", "generate_quote", "write_external_system"],
        },
        "critical_fields": ["observed_business_problems", "requested_agent_capabilities", "requested_agent_actions"],
        "control": False,
    },
    {
        "case_id": "AMB-018-explicit-start-no-future-action",
        "category": "explicit_start_without_future_action",
        "run": "coherent",
        "scenario": "MOVIA-MEM-001",
        "turn": 8,
        "expected": {
            "primary_intent": "explicit_start_request",
            "purchase_readiness_level": "explicit_start",
            "requested_agent_actions_exclude": ["schedule_appointment", "generate_quote", "write_external_system"],
        },
        "critical_fields": ["primary_intent", "purchase_readiness", "requested_agent_actions"],
        "control": True,
    },
    {
        "case_id": "AMB-019-two-external-actions",
        "category": "explicit_external_action",
        "run": "coherent",
        "scenario": "MOVIA-COH-005",
        "turn": 4,
        "expected": {
            "requested_agent_actions_include_all": ["write_external_system", "send_notification"],
            "declared_external_action_count": 2,
            "requested_agent_capabilities_exclude": ["handle_sales_objections"],
        },
        "critical_fields": ["requested_agent_actions", "declared_external_action_count"],
        "control": False,
    },
    {
        "case_id": "AMB-020-price-question-not-objection",
        "category": "price_question_not_objection",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 1,
        "expected": {
            "primary_intent": "pricing_question",
            "topics_any": ["pricing"],
            "objection_type": "none",
            "prior_reference_type": "none",
        },
        "critical_fields": ["primary_intent", "objection_type"],
        "control": True,
    },
    {
        "case_id": "AMB-021-free-trial-objection",
        "category": "free_trial_objection",
        "run": "atomic",
        "scenario": "MOVIA-VAL-005",
        "turn": 5,
        "expected": {
            "objection_type": "wants_free_trial",
            "purchase_readiness_not_level": "explicit_start",
        },
        "critical_fields": ["objection_type", "purchase_readiness"],
        "control": False,
    },
    {
        "case_id": "AMB-022-support-concern-not-start",
        "category": "support_policy_concern",
        "run": "atomic",
        "scenario": "MOVIA-VAL-003",
        "turn": 10,
        "expected": {
            "topics_any": ["support", "whatsapp"],
            "purchase_readiness_not_level": "explicit_start",
            "requested_agent_actions_exclude": ["schedule_appointment", "write_external_system"],
        },
        "critical_fields": ["purchase_readiness", "requested_agent_actions"],
        "control": False,
    },
    {
        "case_id": "AMB-023-current-price-not-capability",
        "category": "current_question_not_future_capability",
        "run": "atomic",
        "scenario": "MOVIA-VAL-001",
        "turn": 4,
        "expected": {
            "primary_intent": "pricing_question",
            "requested_agent_capabilities_exclude": ["provide_prices"],
            "objection_type": "none",
        },
        "critical_fields": ["primary_intent", "requested_agent_capabilities", "objection_type"],
        "control": True,
    },
    {
        "case_id": "AMB-024-policy-adjustments-concern",
        "category": "policy_question",
        "run": "atomic",
        "scenario": "MOVIA-VAL-003",
        "turn": 3,
        "expected": {
            "topics_any": ["support", "policy", "pricing"],
            "primary_intent_not": "unknown",
            "purchase_readiness_not_level": "explicit_start",
        },
        "critical_fields": ["primary_intent", "topics"],
        "control": False,
    },
    {
        "case_id": "AMB-025-ordinary-no-prior-problem-message",
        "category": "no_invented_historical_reference",
        "run": "atomic",
        "scenario": "MOVIA-VAL-001",
        "turn": 3,
        "expected": {
            "prior_reference_type": "none",
            "observed_business_problems_include_any": ["lead_drop_off", "high_message_volume", "missed_leads"],
            "requested_agent_capabilities_exclude": ["provide_prices"],
        },
        "critical_fields": ["prior_reference", "observed_business_problems", "requested_agent_capabilities"],
        "control": True,
    },
    {
        "case_id": "AMB-026-explicit-start-hibrido",
        "category": "explicit_start_without_future_action",
        "run": "coherent",
        "scenario": "MOVIA-COH-005",
        "turn": 8,
        "expected": {
            "primary_intent": "explicit_start_request",
            "purchase_readiness_level": "explicit_start",
            "requested_product": "movia_hibrido",
            "requested_agent_actions_exclude": ["schedule_appointment", "write_external_system"],
        },
        "critical_fields": ["primary_intent", "purchase_readiness", "requested_product", "requested_agent_actions"],
        "control": True,
    },
    {
        "case_id": "AMB-027-human-confirmation-capability",
        "category": "human_confirmation_requirement",
        "run": "coherent",
        "scenario": "MOVIA-COH-005",
        "turn": 7,
        "expected": {
            "requested_agent_capabilities_include_any": ["redirect_to_human", "answer_customer_questions"],
            "requested_agent_actions_exclude": ["write_external_system", "schedule_appointment"],
            "prior_reference_type": "none",
        },
        "critical_fields": ["requested_agent_capabilities", "requested_agent_actions"],
        "control": False,
    },
    {
        "case_id": "AMB-028-unavailable-channel-scope",
        "category": "scope_control",
        "run": "coherent",
        "scenario": "MOVIA-COH-004",
        "turn": 7,
        "expected": {
            "primary_intent": "explicit_start_request",
            "purchase_readiness_level": "explicit_start",
            "requested_agent_actions_exclude": ["schedule_appointment", "write_external_system"],
        },
        "critical_fields": ["primary_intent", "purchase_readiness", "requested_agent_actions"],
        "control": False,
    },
]

PRICING_USD_PER_1M = {
    # OpenAI API pricing page, checked 2026-06-15.
    # gpt-5.4-nano is retained for historical benchmark artifacts.
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5.4-nano": {"input": None, "output": None},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyzer-only model benchmark.")
    parser.add_argument("command", choices=["build-dataset", "run"])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--models", nargs="*", default=MODELS)
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    args = parser.parse_args()

    if args.command == "build-dataset":
        dataset = build_dataset()
        write_json(args.dataset, dataset)
        print(json.dumps({"dataset": str(args.dataset), "case_count": len(dataset["cases"])}, indent=2))
        return 0

    dataset = load_or_build_dataset(args.dataset)
    run_id = f"analyzer-model-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "benchmark_cases.json", dataset)
    result = run_benchmark(dataset, args.models, args.repetitions, output_dir)
    write_report(result, output_dir)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": str(output_dir),
                "recommendation": result["recommendation"],
                "models": list(result["field_scores"]["models"].keys()),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0


def build_dataset() -> Dict[str, Any]:
    runs = {"atomic": load_json(ATOMIC_RUN), "coherent": load_json(COHERENT_RUN)}
    cases = []
    for spec in CASE_SPECS:
        run = runs[spec["run"]]
        scenario, turn_index = find_turn(run, spec["scenario"], spec["turn"])
        turn = scenario["turns"][turn_index]
        previous_turn = scenario["turns"][turn_index - 1] if turn_index > 0 else None
        previous_lead_state = dict(previous_turn.get("lead_state") or {}) if previous_turn else {}
        previous_profile_data = dict(previous_lead_state.get("profile_data") or {})
        previous_requirement_profile = (
            spec.get("force_previous_requirement_profile")
            or previous_profile_data.get("requirement_profile")
            or {}
        )
        previous_active_objection = (
            spec.get("force_previous_active_objection")
            or previous_lead_state.get("active_objection")
            or {}
        )
        if previous_requirement_profile:
            previous_profile_data["requirement_profile"] = previous_requirement_profile
            previous_lead_state["profile_data"] = previous_profile_data
        if previous_active_objection:
            previous_lead_state["active_objection"] = previous_active_objection
        cases.append(
            {
                "case_id": spec["case_id"],
                "category": spec["category"],
                "user_message": turn["user_input"],
                "recent_messages": recent_messages_for_scenario(scenario, turn_index),
                "previous_lead_state": previous_lead_state,
                "previous_requirement_profile": previous_requirement_profile,
                "previous_active_objection": previous_active_objection,
                "expected_analyzer_fields": spec["expected"],
                "critical_fields": spec["critical_fields"],
                "control": bool(spec.get("control")),
                "source_run_id": run["run_id"],
                "source_scenario_id": scenario["conversation_id"],
                "source_turn_id": turn["turn_id"],
            }
        )
    return {
        "dataset_version": "analyzer-model-benchmark-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analyzer_contract_version": ANALYZER_CONTRACT_VERSION,
        "normalized_turn_contract_version": NORMALIZED_TURN_CONTRACT_VERSION,
        "source_runs": {"atomic": str(ATOMIC_RUN), "coherent": str(COHERENT_RUN)},
        "notes": [
            "Analyzer-only benchmark. Inputs exclude ideal responses, selected actions, final responses, and evaluator results.",
            "Recent messages are reconstructed from prior user/assistant turns in the source run artifacts.",
            "Requirement replacement is a known Analyzer V3.1 representational limitation and is not scored as downstream profile replacement.",
        ],
        "cases": cases,
    }


def run_benchmark(
    dataset: Dict[str, Any],
    models: List[str],
    repetitions: int,
    output_dir: Path,
) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for the analyzer model benchmark.")
    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=1)
    raw_records = []
    normalized_records = []
    raw_path = output_dir / "raw_outputs.jsonl"
    normalized_path = output_dir / "normalized_outputs.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw_file, normalized_path.open("w", encoding="utf-8") as norm_file:
        for model in models:
            for case in dataset["cases"]:
                for repetition in range(1, repetitions + 1):
                    record, normalized = run_case(client, model, case, repetition)
                    raw_records.append(record)
                    normalized_records.append(normalized)
                    raw_file.write(json.dumps(record, ensure_ascii=False, default=json_default) + "\n")
                    raw_file.flush()
                    norm_file.write(json.dumps(normalized, ensure_ascii=False, default=json_default) + "\n")
                    norm_file.flush()

    field_scores = score_records(dataset["cases"], raw_records, normalized_records, models)
    cost_latency = cost_latency_summary(raw_records, models)
    recommendation = choose_recommendation(field_scores, cost_latency)
    result = {
        "dataset": dataset,
        "raw_records": raw_records,
        "normalized_records": normalized_records,
        "field_scores": field_scores,
        "cost_latency": cost_latency,
        "recommendation": recommendation,
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "field_scores.json", field_scores)
    write_json(output_dir / "cost_latency.json", cost_latency)
    return result


def run_case(client: OpenAI, model: str, case: Dict[str, Any], repetition: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    started = perf_counter()
    raw_payload: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None
    usage: Dict[str, Any] = empty_usage(model)
    error: Optional[str] = None
    retry_count = 0
    reasoning_used = False
    request_body = {
        "model": model,
        "input": [
            {"role": "system", "content": ANALYZER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": case["user_message"],
                        "recent_messages": case.get("recent_messages", [])[-6:],
                    },
                    ensure_ascii=False,
                    default=json_default,
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "movia_analyzer_observation_v3",
                "schema": ANALYZER_V3_SCHEMA,
                "strict": True,
            }
        },
    }
    if model.startswith("gpt-5"):
        request_body["reasoning"] = {"effort": "minimal"}
        reasoning_used = True
    try:
        try:
            response = client.responses.create(**request_body)
        except Exception as exc:
            if reasoning_used:
                retry_count += 1
                request_body.pop("reasoning", None)
                reasoning_used = False
                response = client.responses.create(**request_body)
            else:
                raise exc
        raw_text = response.output_text
        raw_payload = json.loads(raw_text)
        usage = response_usage(response, "analysis", model, "openai")
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    latency_ms = round((perf_counter() - started) * 1000, 2)
    raw_validation = validate_raw_payload(raw_payload)
    sanitized_observation, sanitized_error = validate_sanitized_payload(raw_payload, case["user_message"])
    raw_record = {
        "model": model,
        "case_id": case["case_id"],
        "category": case["category"],
        "repetition": repetition,
        "source_run_id": case["source_run_id"],
        "source_scenario_id": case["source_scenario_id"],
        "source_turn_id": case["source_turn_id"],
        "provider": "openai" if raw_payload is not None else "error",
        "fallback": False,
        "error": error,
        "retry_count": retry_count,
        "reasoning_requested": model.startswith("gpt-5"),
        "reasoning_used": reasoning_used,
        "latency_ms": latency_ms,
        "usage": usage,
        "raw_text": raw_text,
        "raw_payload": raw_payload,
        "raw_schema_valid": raw_validation["valid"],
        "raw_schema_error": raw_validation["error"],
        "sanitized_valid": sanitized_observation is not None,
        "sanitized_error": sanitized_error,
        "raw_scores": score_output(case, raw_payload, sanitized_observation, normalized=None),
    }
    normalized_record = normalize_record(case, model, repetition, raw_payload, sanitized_observation)
    return raw_record, normalized_record


def normalize_record(
    case: Dict[str, Any],
    model: str,
    repetition: int,
    raw_payload: Optional[Dict[str, Any]],
    observation: Optional[AnalyzerTurnObservation],
) -> Dict[str, Any]:
    normalized_payload = None
    analysis_payload = None
    error = None
    if observation is not None:
        try:
            shadow = ShadowSignalParser().parse(case["user_message"]).model_dump()
            normalized = normalize_analyzer_turn(
                observation,
                message=case["user_message"],
                lead_profile=case.get("previous_lead_state") or {},
                shadow_parser=shadow,
            )
            analysis = observation_to_turn_analysis(observation, case["user_message"])
            normalized_payload = normalized.model_dump()
            analysis_payload = analysis.model_dump()
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:500]}"
    else:
        error = "sanitized observation unavailable"
    return {
        "model": model,
        "case_id": case["case_id"],
        "category": case["category"],
        "repetition": repetition,
        "normalized_valid": normalized_payload is not None,
        "normalization_error": error,
        "normalized_turn": normalized_payload,
        "analysis": analysis_payload,
        "normalized_scores": score_output(case, raw_payload, None, normalized_payload, analysis_payload),
    }


def score_records(
    cases: List[Dict[str, Any]],
    raw_records: List[Dict[str, Any]],
    normalized_records: List[Dict[str, Any]],
    models: List[str],
) -> Dict[str, Any]:
    cases_by_id = {case["case_id"]: case for case in cases}
    normalized_by_key = {
        (record["model"], record["case_id"], record["repetition"]): record
        for record in normalized_records
    }
    by_model: Dict[str, Dict[str, Any]] = {}
    for model in models:
        model_raw = [record for record in raw_records if record["model"] == model]
        model_norm = [record for record in normalized_records if record["model"] == model]
        raw_score_lists = [record["raw_scores"] for record in model_raw]
        norm_score_lists = [record["normalized_scores"] for record in model_norm]
        critical_errors = Counter()
        for scores in raw_score_lists:
            critical_errors.update(scores.get("critical_errors", []))
        for scores in norm_score_lists:
            critical_errors.update(f"normalized:{err}" for err in scores.get("critical_errors", []))
        stability = stability_summary(model, cases, raw_records, normalized_by_key)
        by_model[model] = {
            "calls": len(model_raw),
            "schema_validity": ratio(record.get("raw_schema_valid") for record in model_raw),
            "provider_errors": sum(1 for record in model_raw if record.get("provider") != "openai"),
            "fallback_count": sum(1 for record in model_raw if record.get("fallback")),
            "raw": aggregate_score_dicts(raw_score_lists),
            "normalized": aggregate_score_dicts(norm_score_lists),
            "critical_errors": dict(critical_errors),
            "weighted_critical_accuracy": weighted_critical_accuracy(raw_score_lists, norm_score_lists),
            "controls": control_summary(model_raw, model_norm, cases_by_id),
            "stability": stability,
        }
    return {
        "models": by_model,
        "case_count": len(cases),
        "repetitions": REPETITIONS,
        "critical_error_weights": critical_error_weights(),
    }


def score_output(
    case: Dict[str, Any],
    raw_payload: Optional[Dict[str, Any]],
    observation: Optional[AnalyzerTurnObservation],
    normalized: Optional[Dict[str, Any]] = None,
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    expected = case.get("expected_analyzer_fields") or {}
    values = extract_values(raw_payload, observation, normalized, analysis)
    checks = []
    critical_errors: List[str] = []

    def add(name: str, passed: bool, critical_code: Optional[str] = None) -> None:
        checks.append({"name": name, "passed": bool(passed)})
        if not passed and critical_code:
            critical_errors.append(critical_code)

    if "primary_intent" in expected:
        add(
            "primary_intent",
            values["primary_intent"] == expected["primary_intent"],
            "missed_explicit_start" if expected["primary_intent"] == "explicit_start_request" else None,
        )
    if "primary_intent_not" in expected:
        add(
            "primary_intent_not",
            values["primary_intent"] != expected["primary_intent_not"],
            "policy_question_classified_unknown" if expected["primary_intent_not"] == "unknown" else None,
        )
    if "topics_any" in expected:
        add(
            "topics_any",
            bool(set(values["topics"]).intersection(expected["topics_any"])),
            "policy_question_classified_unknown" if {"refund_policy", "deposit", "policy"}.intersection(expected["topics_any"]) else None,
        )
    if expected.get("not_only_pricing"):
        add("not_only_pricing", set(values["topics"]) != {"pricing"}, "policy_question_classified_unknown")
    if "purchase_readiness_level" in expected:
        add(
            "purchase_readiness_level",
            values["purchase_readiness_level"] == expected["purchase_readiness_level"],
            "missed_explicit_start" if expected["purchase_readiness_level"] == "explicit_start" else None,
        )
    if "purchase_readiness_not_level" in expected:
        add(
            "purchase_readiness_not_level",
            values["purchase_readiness_level"] != expected["purchase_readiness_not_level"],
            "false_explicit_start" if expected["purchase_readiness_not_level"] == "explicit_start" else None,
        )
    if "requested_agent_actions_include_all" in expected:
        missing = set(expected["requested_agent_actions_include_all"]) - set(values["requested_agent_actions"])
        add("requested_agent_actions_include_all", not missing, "missed_explicit_external_action")
    if "requested_agent_actions_include_any" in expected:
        add(
            "requested_agent_actions_include_any",
            bool(set(values["requested_agent_actions"]).intersection(expected["requested_agent_actions_include_any"])),
            "missed_explicit_external_action",
        )
    if "requested_agent_actions_exclude" in expected:
        invented = set(values["requested_agent_actions"]).intersection(expected["requested_agent_actions_exclude"])
        add("requested_agent_actions_exclude", not invented, "invented_external_action")
    if "requested_agent_capabilities_include_all" in expected:
        add(
            "requested_agent_capabilities_include_all",
            set(expected["requested_agent_capabilities_include_all"]).issubset(values["requested_agent_capabilities"]),
        )
    if "requested_agent_capabilities_include_any" in expected:
        add(
            "requested_agent_capabilities_include_any",
            bool(set(values["requested_agent_capabilities"]).intersection(expected["requested_agent_capabilities_include_any"])),
        )
    if "requested_agent_capabilities_exclude" in expected:
        add(
            "requested_agent_capabilities_exclude",
            not set(values["requested_agent_capabilities"]).intersection(expected["requested_agent_capabilities_exclude"]),
        )
    if "observed_business_problems_include_any" in expected:
        add(
            "observed_business_problems_include_any",
            bool(set(values["observed_business_problems"]).intersection(expected["observed_business_problems_include_any"])),
        )
    if "prior_reference_type" in expected:
        add(
            "prior_reference_type",
            values["prior_reference_type"] == expected["prior_reference_type"],
            "false_historical_reference" if expected["prior_reference_type"] == "none" else "missed_true_historical_reference",
        )
    if "prior_reference_not_type" in expected:
        add(
            "prior_reference_not_type",
            values["prior_reference_type"] != expected["prior_reference_not_type"],
            "missed_true_historical_reference" if expected["prior_reference_not_type"] == "none" else None,
        )
    if "requested_product" in expected:
        add("requested_product", values["requested_product"] == expected["requested_product"])
    if "objection_type" in expected:
        code = None
        if expected["objection_type"] == "none" and values["objection_type"] == "price_objection":
            code = "price_question_classified_price_objection"
        add("objection_type", values["objection_type"] == expected["objection_type"], code)
    if "objection_type_any" in expected:
        add("objection_type_any", values["objection_type"] in expected["objection_type_any"])
    if "objection_strength" in expected:
        add("objection_strength", values["objection_strength"] == expected["objection_strength"])
    if "objection_relation_allowed" in expected:
        # No critical penalty when the case documents a representation limitation.
        add("objection_relation_allowed", values["objection_relation"] in expected["objection_relation_allowed"])
    if "declared_external_action_count" in expected:
        add("declared_external_action_count", values["declared_external_action_count"] == expected["declared_external_action_count"])

    evidence_validity = evidence_spans_valid(raw_payload, case["user_message"])
    add("evidence_span_validity", evidence_validity)
    contradiction_count = len(values.get("contradictions") or [])
    return {
        "values": values,
        "checks": checks,
        "accuracy": ratio(check["passed"] for check in checks),
        "critical_errors": critical_errors,
        "contradiction_count": contradiction_count,
        "evidence_span_validity": evidence_validity,
    }


def extract_values(
    raw_payload: Optional[Dict[str, Any]],
    observation: Optional[AnalyzerTurnObservation],
    normalized: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if normalized:
        norm_objection = normalized.get("normalized_objection") or {}
        norm_prior = normalized.get("normalized_prior_reference") or {}
        return {
            "primary_intent": (analysis or {}).get("primary_intent"),
            "topics": (analysis or {}).get("topics") or [],
            "purchase_readiness_level": "explicit_start" if normalized.get("explicit_start_intent") else ((analysis or {}).get("buying_signal") or "none"),
            "requested_agent_actions": normalized.get("requested_agent_actions") or [],
            "requested_agent_capabilities": normalized.get("requested_agent_capabilities") or [],
            "observed_business_problems": normalized.get("observed_business_problems") or [],
            "prior_reference_type": norm_prior.get("type") or "none",
            "requested_product": normalized.get("requested_product") or "none",
            "objection_type": norm_objection.get("type") or "none",
            "objection_strength": norm_objection.get("strength") or "none",
            "objection_relation": normalized.get("objection_relation") or norm_objection.get("relation") or "none",
            "declared_external_action_count": normalized.get("declared_external_action_count"),
            "contradictions": normalized.get("contradictions") or [],
        }
    payload = observation.model_dump() if observation is not None else (raw_payload or {})
    try:
        analysis_payload = observation_to_turn_analysis(observation, "").model_dump() if observation is not None else {}
    except Exception:
        analysis_payload = {}
    return {
        "primary_intent": payload.get("primary_intent"),
        "topics": analysis_payload.get("topics") or [],
        "purchase_readiness_level": (payload.get("purchase_readiness") or {}).get("level") or "none",
        "requested_agent_actions": [item.get("type") for item in payload.get("requested_agent_actions") or [] if isinstance(item, dict)],
        "requested_agent_capabilities": [item.get("type") for item in payload.get("requested_agent_capabilities") or [] if isinstance(item, dict)],
        "observed_business_problems": [item.get("type") for item in payload.get("observed_business_problems") or [] if isinstance(item, dict)],
        "prior_reference_type": (payload.get("prior_reference") or {}).get("type") or "none",
        "requested_product": (payload.get("requested_product") or {}).get("product") or "none",
        "objection_type": (payload.get("objection_candidate") or {}).get("type") or "none",
        "objection_strength": (payload.get("objection_candidate") or {}).get("strength") or "none",
        "objection_relation": (payload.get("objection_candidate") or {}).get("relation") or "none",
        "declared_external_action_count": (payload.get("declared_external_action_count") or {}).get("value")
        if isinstance(payload.get("declared_external_action_count"), dict)
        else None,
        "contradictions": [],
    }


def aggregate_score_dicts(scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    checks = defaultdict(list)
    critical_errors = Counter()
    contradiction_counts = []
    evidence_valid = []
    for score in scores:
        for check in score.get("checks") or []:
            checks[check["name"]].append(bool(check["passed"]))
        critical_errors.update(score.get("critical_errors") or [])
        contradiction_counts.append(score.get("contradiction_count") or 0)
        evidence_valid.append(bool(score.get("evidence_span_validity")))
    return {
        "overall_accuracy": ratio(value for values in checks.values() for value in values),
        "field_accuracy": {name: ratio(values) for name, values in sorted(checks.items())},
        "critical_error_count": sum(critical_errors.values()),
        "critical_errors": dict(critical_errors),
        "avg_contradictions": round(statistics.mean(contradiction_counts), 4) if contradiction_counts else 0,
        "evidence_span_validity": ratio(evidence_valid),
    }


def weighted_critical_accuracy(raw_scores: List[Dict[str, Any]], norm_scores: List[Dict[str, Any]]) -> float:
    weights = critical_error_weights()
    total_possible = 0
    total_penalty = 0
    for score in raw_scores + norm_scores:
        total_possible += sum(weights.values())
        for error in score.get("critical_errors") or []:
            total_penalty += weights.get(error.replace("normalized:", ""), 1)
    if not total_possible:
        return 1.0
    return max(0.0, round(1.0 - (total_penalty / total_possible), 4))


def critical_error_weights() -> Dict[str, int]:
    return {
        "invented_external_action": 5,
        "missed_explicit_external_action": 5,
        "false_explicit_start": 5,
        "missed_explicit_start": 5,
        "false_historical_reference": 4,
        "missed_true_historical_reference": 4,
        "price_question_classified_price_objection": 4,
        "policy_question_classified_unknown": 4,
        "active_objection_resolution_missed": 3,
    }


def stability_summary(
    model: str,
    cases: List[Dict[str, Any]],
    raw_records: List[Dict[str, Any]],
    normalized_by_key: Dict[Tuple[str, str, int], Dict[str, Any]],
) -> Dict[str, Any]:
    raw_by_key = {(record["model"], record["case_id"], record["repetition"]): record for record in raw_records}
    exact = []
    critical = []
    enum_disagreements = 0
    evidence_disagreements = 0
    for case in cases:
        r1 = raw_by_key.get((model, case["case_id"], 1))
        r2 = raw_by_key.get((model, case["case_id"], 2))
        n1 = normalized_by_key.get((model, case["case_id"], 1))
        n2 = normalized_by_key.get((model, case["case_id"], 2))
        if not r1 or not r2:
            continue
        exact.append(canonical_json(r1.get("raw_payload")) == canonical_json(r2.get("raw_payload")))
        critical.append(critical_signature(n1, case) == critical_signature(n2, case))
        enum_disagreements += enum_disagreement_count(r1.get("raw_payload"), r2.get("raw_payload"))
        evidence_disagreements += evidence_disagreement_count(r1.get("raw_payload"), r2.get("raw_payload"))
    return {
        "exact_output_agreement": ratio(exact),
        "critical_field_agreement": ratio(critical),
        "enum_disagreement_count": enum_disagreements,
        "evidence_span_disagreement_count": evidence_disagreements,
    }


def cost_latency_summary(raw_records: List[Dict[str, Any]], models: List[str]) -> Dict[str, Any]:
    result = {}
    for model in models:
        records = [record for record in raw_records if record["model"] == model]
        latencies = [record["latency_ms"] for record in records if isinstance(record.get("latency_ms"), (int, float))]
        totals = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
        retries = 0
        fallbacks = 0
        for record in records:
            usage = record.get("usage") or {}
            retries += int(record.get("retry_count") or 0)
            fallbacks += 1 if record.get("fallback") else 0
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                totals[key] += int(usage.get(key) or 0)
            details = usage.get("details") or {}
            output_details = details.get("output_tokens_details") or {}
            totals["reasoning_tokens"] += int(output_details.get("reasoning_tokens") or 0)
        cost = estimate_cost(model, totals)
        result[model] = {
            "calls": len(records),
            **totals,
            "tokens_per_call": round(totals["total_tokens"] / len(records), 3) if records else 0,
            "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
            "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
            "p95_latency_ms": percentile(latencies, 95) if latencies else None,
            "estimated_api_cost_usd": cost,
            "estimated_cost_per_call_usd": round(cost / len(records), 8) if cost is not None and records else None,
            "retry_count": retries,
            "fallback_count": fallbacks,
            "pricing_source": "https://openai.com/api/pricing/",
            "pricing_note": "gpt-5.4-nano was not listed on the public pricing page when checked." if model == "gpt-5.4-nano" else None,
        }
    return result


def choose_recommendation(field_scores: Dict[str, Any], cost_latency: Dict[str, Any]) -> str:
    baseline_model, challenger_model = comparison_models(field_scores["models"])
    baseline = field_scores["models"].get(baseline_model)
    challenger = field_scores["models"].get(challenger_model)
    if not baseline or not challenger:
        return "INCONCLUSIVE — CONTRACT/LABEL LIMITATION"
    if (
        challenger["provider_errors"]
        or challenger["fallback_count"]
        or challenger["schema_validity"] < baseline["schema_validity"]
    ):
        return "KEEP GPT-4.1-MINI"
    if challenger["weighted_critical_accuracy"] <= baseline["weighted_critical_accuracy"]:
        return "KEEP GPT-4.1-MINI"
    if challenger["controls"]["accuracy"] + 0.02 < baseline["controls"]["accuracy"]:
        return "KEEP GPT-4.1-MINI"
    if (
        challenger["stability"]["critical_field_agreement"]
        < baseline["stability"]["critical_field_agreement"]
    ):
        return "KEEP GPT-4.1-MINI"
    return f"ADOPT {challenger_model.upper()} FOR ANALYZER"


def comparison_models(models: Dict[str, Any]) -> Tuple[str, str]:
    baseline = BASELINE_MODEL if BASELINE_MODEL in models else sorted(models)[0]
    challengers = [model for model in models if model != baseline]
    challenger = challengers[0] if challengers else baseline
    return baseline, challenger


def write_report(result: Dict[str, Any], output_dir: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fs = result["field_scores"]["models"]
    cl = result["cost_latency"]
    baseline_model, challenger_model = comparison_models(fs)
    mini = fs.get(baseline_model, {})
    challenger = fs.get(challenger_model, {})

    def metric_row(label: str, mini_value: Any, nano_value: Any) -> str:
        delta = ""
        if isinstance(mini_value, (int, float)) and isinstance(nano_value, (int, float)):
            delta = f"{round(nano_value - mini_value, 4):.4f}"
        return f"| {label} | {fmt(mini_value)} | {fmt(nano_value)} | {delta} |"

    rows = [
        metric_row("Weighted critical accuracy", mini.get("weighted_critical_accuracy"), challenger.get("weighted_critical_accuracy")),
        metric_row("False requested actions", mini.get("critical_errors", {}).get("invented_external_action", 0), challenger.get("critical_errors", {}).get("invented_external_action", 0)),
        metric_row("Missed external actions", mini.get("critical_errors", {}).get("missed_explicit_external_action", 0), challenger.get("critical_errors", {}).get("missed_explicit_external_action", 0)),
        metric_row("Requirement observation accuracy", mini.get("normalized", {}).get("field_accuracy", {}).get("requested_agent_capabilities_include_any"), challenger.get("normalized", {}).get("field_accuracy", {}).get("requested_agent_capabilities_include_any")),
        metric_row("Objection accuracy", mini.get("normalized", {}).get("field_accuracy", {}).get("objection_type"), challenger.get("normalized", {}).get("field_accuracy", {}).get("objection_type")),
        metric_row("Prior-reference precision", mini.get("normalized", {}).get("field_accuracy", {}).get("prior_reference_type"), challenger.get("normalized", {}).get("field_accuracy", {}).get("prior_reference_type")),
        metric_row("Intent/topic accuracy", average_present([mini.get("normalized", {}).get("field_accuracy", {}).get("primary_intent"), mini.get("normalized", {}).get("field_accuracy", {}).get("topics_any")]), average_present([challenger.get("normalized", {}).get("field_accuracy", {}).get("primary_intent"), challenger.get("normalized", {}).get("field_accuracy", {}).get("topics_any")])),
        metric_row("Raw contradictions", mini.get("raw", {}).get("avg_contradictions"), challenger.get("raw", {}).get("avg_contradictions")),
        metric_row("Normalized contradictions", mini.get("normalized", {}).get("avg_contradictions"), challenger.get("normalized", {}).get("avg_contradictions")),
        metric_row("Stability", mini.get("stability", {}).get("critical_field_agreement"), challenger.get("stability", {}).get("critical_field_agreement")),
        metric_row("Tokens per call", cl.get(baseline_model, {}).get("tokens_per_call"), cl.get(challenger_model, {}).get("tokens_per_call")),
        metric_row("Cost per call", cl.get(baseline_model, {}).get("estimated_cost_per_call_usd"), cl.get(challenger_model, {}).get("estimated_cost_per_call_usd")),
        metric_row("Average latency", cl.get(baseline_model, {}).get("average_latency_ms"), cl.get(challenger_model, {}).get("average_latency_ms")),
    ]
    lines = [
        "# Analyzer Model Benchmark",
        "",
        f"- **Run artifact:** `{output_dir}`",
        f"- **Dataset:** `movia_validation_package/analyzer_model_benchmark_v1.json`",
        f"- **Analyzer contract:** `{ANALYZER_CONTRACT_VERSION}`",
        f"- **Normalized-turn contract:** `{NORMALIZED_TURN_CONTRACT_VERSION}`",
        "- **Scope:** analyzer-only; no response generator, embeddings, RAG, RAGAS, DeepEval, judge, production DB writes, Atomic replay or Coherent replay.",
        "- **Pricing source:** OpenAI API pricing page checked on 2026-06-15.",
        "",
        f"| Metric | {baseline_model} | {challenger_model} | Delta |",
        "| --- | ---: | ---: | ---: |",
        *rows,
        "",
        "## Reliability",
        "",
        f"- {baseline_model} schema validity: `{fmt(mini.get('schema_validity'))}`; provider errors: `{mini.get('provider_errors')}`; fallback count: `{mini.get('fallback_count')}`.",
        f"- {challenger_model} schema validity: `{fmt(challenger.get('schema_validity'))}`; provider errors: `{challenger.get('provider_errors')}`; fallback count: `{challenger.get('fallback_count')}`.",
        "",
        "## Critical Errors",
        "",
        "```json",
        json.dumps({model: data.get("critical_errors", {}) for model, data in fs.items()}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Stability",
        "",
        "```json",
        json.dumps({model: data.get("stability", {}) for model, data in fs.items()}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Contract Limitations",
        "",
        "- Requirement replacement/removal is not directly expressible by Analyzer Contract V3.1. The benchmark scores only the current-turn observation and reports downstream replacement as out of scope.",
        "- Active objection resolution can be partly representationally limited when the user softens an objection without stating a new objection candidate.",
        "",
        "## Recommendation",
        "",
        result["recommendation"],
        "",
        "Sources: [OpenAI API pricing](https://openai.com/api/pricing/).",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def recent_messages_for_scenario(scenario: Dict[str, Any], turn_index: int) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    for prior in scenario["turns"][:turn_index]:
        messages.append({"role": "user", "content": prior["user_input"]})
        if prior.get("agent_output"):
            messages.append({"role": "assistant", "content": prior["agent_output"]})
    return messages[-8:]


def find_turn(run: Dict[str, Any], scenario_id: str, turn_id: int) -> Tuple[Dict[str, Any], int]:
    for scenario in run["scenario_results"]:
        if scenario["conversation_id"] != scenario_id:
            continue
        for index, turn in enumerate(scenario["turns"]):
            if int(turn["turn_id"]) == int(turn_id):
                return scenario, index
    raise KeyError(f"Turn not found: {scenario_id} turn {turn_id}")


def validate_raw_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {"valid": False, "error": "no payload"}
    try:
        AnalyzerTurnObservation.model_validate(payload)
        return {"valid": True, "error": None}
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}


def validate_sanitized_payload(
    payload: Optional[Dict[str, Any]], message: str
) -> Tuple[Optional[AnalyzerTurnObservation], Optional[str]]:
    if payload is None:
        return None, "no payload"
    try:
        return validate_analyzer_observation(payload, message), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:500]}"


def evidence_spans_valid(payload: Optional[Dict[str, Any]], message: str) -> bool:
    if payload is None:
        return False
    text = normalize_for_evidence(message)
    spans = collect_evidence_spans(payload)
    return all(normalize_for_evidence(span) in text for span in spans if span)


def collect_evidence_spans(value: Any) -> List[str]:
    spans: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_span" and isinstance(child, str):
                spans.append(child)
            else:
                spans.extend(collect_evidence_spans(child))
    elif isinstance(value, list):
        for child in value:
            spans.extend(collect_evidence_spans(child))
    return spans


def normalize_for_evidence(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def control_summary(
    raw_records: List[Dict[str, Any]],
    normalized_records: List[Dict[str, Any]],
    cases_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    control_norm = [
        record
        for record in normalized_records
        if cases_by_id.get(record["case_id"], {}).get("control")
    ]
    values = [record.get("normalized_scores", {}).get("accuracy") for record in control_norm]
    return {"cases": len({record["case_id"] for record in control_norm}), "accuracy": ratio(v for v in values if v is not None)}


def critical_signature(record: Optional[Dict[str, Any]], case: Dict[str, Any]) -> Any:
    if not record:
        return None
    scores = record.get("normalized_scores") or {}
    values = scores.get("values") or {}
    keys = set(case.get("critical_fields") or [])
    mapped = {}
    if "primary_intent" in keys:
        mapped["primary_intent"] = values.get("primary_intent")
    if "purchase_readiness" in keys:
        mapped["purchase_readiness_level"] = values.get("purchase_readiness_level")
    if "requested_agent_actions" in keys:
        mapped["requested_agent_actions"] = sorted(values.get("requested_agent_actions") or [])
    if "requested_agent_capabilities" in keys:
        mapped["requested_agent_capabilities"] = sorted(values.get("requested_agent_capabilities") or [])
    if "prior_reference" in keys:
        mapped["prior_reference_type"] = values.get("prior_reference_type")
    if "objection_type" in keys:
        mapped["objection_type"] = values.get("objection_type")
    if "objection_relation" in keys:
        mapped["objection_relation"] = values.get("objection_relation")
    if "requested_product" in keys:
        mapped["requested_product"] = values.get("requested_product")
    return mapped


def enum_disagreement_count(first: Optional[Dict[str, Any]], second: Optional[Dict[str, Any]]) -> int:
    if not first or not second:
        return 1
    keys = [
        ("primary_intent",),
        ("purchase_readiness", "level"),
        ("prior_reference", "type"),
        ("objection_candidate", "type"),
        ("objection_candidate", "relation"),
        ("requested_product", "product"),
    ]
    count = 0
    for path in keys:
        if nested_get(first, path) != nested_get(second, path):
            count += 1
    for list_key in ("requested_agent_actions", "requested_agent_capabilities", "observed_business_problems"):
        if sorted(item.get("type") for item in first.get(list_key) or []) != sorted(
            item.get("type") for item in second.get(list_key) or []
        ):
            count += 1
    return count


def evidence_disagreement_count(first: Optional[Dict[str, Any]], second: Optional[Dict[str, Any]]) -> int:
    if not first or not second:
        return 1
    return 0 if sorted(collect_evidence_spans(first)) == sorted(collect_evidence_spans(second)) else 1


def nested_get(value: Dict[str, Any], path: Iterable[str]) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def estimate_cost(model: str, totals: Dict[str, int]) -> Optional[float]:
    rates = PRICING_USD_PER_1M.get(model) or {}
    input_rate = rates.get("input")
    output_rate = rates.get("output")
    if input_rate is None or output_rate is None:
        return None
    return round((totals["input_tokens"] / 1_000_000 * input_rate) + (totals["output_tokens"] / 1_000_000 * output_rate), 8)


def empty_usage(model: str) -> Dict[str, Any]:
    return {
        "operation": "analysis",
        "model": model,
        "provider": "error",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def ratio(values: Iterable[Any]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(1 for value in items if value) / len(items), 4)


def percentile(values: List[float], percentile_value: int) -> Optional[float]:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, round((percentile_value / 100) * (len(sorted_values) - 1)))
    return round(sorted_values[index], 2)


def average_present(values: Iterable[Optional[float]]) -> Optional[float]:
    present = [value for value in values if isinstance(value, (int, float))]
    if not present:
        return None
    return round(statistics.mean(present), 4)


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=json_default)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")


def load_or_build_dataset(path: Path) -> Dict[str, Any]:
    if path.exists():
        return load_json(path)
    dataset = build_dataset()
    write_json(path, dataset)
    return dataset


if __name__ == "__main__":
    raise SystemExit(main())
