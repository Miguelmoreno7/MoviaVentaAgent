from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Set

from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.contracts.commercial import (
    COMMERCIAL_CONTRACT_VERSION,
    CTAType,
    MacroAction,
    MicroAction,
    ObjectionFlowStep,
    ObjectionType,
    SalesStage,
)
from movia_sales_agent.evaluation.contracts_v3 import (
    EVALUATION_CONTRACT_VERSION,
    RunMode,
    SuiteType,
)
from movia_sales_agent.evaluation.models import (
    AdaptiveHybridInterface,
    DatasetValidationSummary,
    ValidationDataset,
    ValidationScenario,
)


DEFAULT_DATASET_PATH = (
    PROJECT_ROOT
    / "movia_validation_package"
    / "movia_difficult_lead_validation_scenarios.json"
)
COHERENT_SCRIPTED_DATASET_PATH = (
    PROJECT_ROOT
    / "movia_validation_package"
    / "movia_coherent_scripted_conversations.json"
)
ADAPTIVE_HYBRID_INTERFACE_PATH = (
    PROJECT_ROOT
    / "movia_validation_package"
    / "movia_adaptive_hybrid_predeploy_interface.json"
)

SUPPORTED_EXPECTED_FIELDS: Set[str] = {
    "current_stage",
    "macro_action",
    "micro_action",
    "objection_type",
    "objection_flow_step",
    "expected_sources",
    "rag_used",
    "structured_used",
    "json_used",
    "final_cta_type",
}

CONTRACT_EXPECTED_FIELDS = {
    "current_stage": SalesStage,
    "macro_action": MacroAction,
    "micro_action": MicroAction,
    "objection_type": ObjectionType,
    "objection_flow_step": ObjectionFlowStep,
    "final_cta_type": CTAType,
}


def load_validation_dataset(path: Optional[Path] = None) -> ValidationDataset:
    dataset_path = path or DEFAULT_DATASET_PATH
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    return ValidationDataset.model_validate(raw)


def load_adaptive_hybrid_interface(
    path: Optional[Path] = None,
) -> AdaptiveHybridInterface:
    interface_path = path or ADAPTIVE_HYBRID_INTERFACE_PATH
    raw = json.loads(interface_path.read_text(encoding="utf-8"))
    return AdaptiveHybridInterface.model_validate(raw)


def validate_dataset(
    dataset: ValidationDataset,
    supported_expected_fields: Optional[Iterable[str]] = None,
    supported_sources: Optional[Iterable[str]] = None,
) -> DatasetValidationSummary:
    supported = set(supported_expected_fields or SUPPORTED_EXPECTED_FIELDS)
    source_supported = set(supported_sources) if supported_sources is not None else _default_source_capabilities()
    errors = []
    scenario_ids = [scenario.conversation_id for scenario in dataset.scenarios]
    turn_count = sum(len(scenario.turns) for scenario in dataset.scenarios)
    unsupported_expected_sources: Set[str] = set()

    if dataset.evaluation_contract_version != EVALUATION_CONTRACT_VERSION:
        errors.append(
            "Dataset evaluation_contract_version must be "
            f"{EVALUATION_CONTRACT_VERSION!r}; found "
            f"{dataset.evaluation_contract_version!r}."
        )

    if dataset.commercial_contract_version != COMMERCIAL_CONTRACT_VERSION:
        errors.append(
            "Dataset commercial_contract_version must be "
            f"{COMMERCIAL_CONTRACT_VERSION!r}; found {dataset.commercial_contract_version!r}."
        )
    if dataset.agent_contract_version != COMMERCIAL_CONTRACT_VERSION:
        errors.append(
            "Dataset agent_contract_version must be "
            f"{COMMERCIAL_CONTRACT_VERSION!r}; found {dataset.agent_contract_version!r}."
        )

    _validate_suite_metadata(dataset, errors)

    if len(set(scenario_ids)) != len(scenario_ids):
        errors.append("Scenario conversation_id values must be unique.")

    expected_fields = set()
    for scenario in dataset.scenarios:
        _validate_scenario_shape(dataset, scenario, errors)
        expected_ids = list(range(1, len(scenario.turns) + 1))
        actual_ids = [turn.turn_id for turn in scenario.turns]
        if actual_ids != expected_ids:
            errors.append(f"{scenario.conversation_id} turn_id values must be ordered from 1.")
        for turn in scenario.turns:
            expected_fields.update(turn.expected.keys())
            location = f"{scenario.conversation_id} turn {turn.turn_id}"
            if not turn.user.strip():
                errors.append(f"{location} has no user text.")
            if not turn.ideal_assistant.strip():
                errors.append(f"{location} has no ideal response.")
            for value_error in contract_value_errors(turn.expected):
                errors.append(f"{location}: {value_error}")
            _validate_bool_expected_values(turn.expected, location, errors)
            expected_sources = turn.expected.get("expected_sources")
            if expected_sources is None:
                continue
            if not isinstance(expected_sources, list) or not all(
                isinstance(source, str) for source in expected_sources
            ):
                errors.append(f"{location}: expected_sources must be a list of strings.")
                continue
            unsupported_expected_sources.update(
                source for source in expected_sources if source not in source_supported
            )

    unsupported_expected_fields = sorted(expected_fields - supported)
    for field in unsupported_expected_fields:
        errors.append(f"Unsupported expected field in dataset: {field}.")
    for source in sorted(unsupported_expected_sources):
        errors.append(f"Unsupported expected source in dataset: {source}.")

    return DatasetValidationSummary(
        valid=not errors,
        evaluation_contract_version=dataset.evaluation_contract_version,
        commercial_contract_version=dataset.commercial_contract_version,
        agent_contract_version=dataset.agent_contract_version,
        suite_type=dataset.suite_type,
        causal_continuity=dataset.causal_continuity,
        dataset_version=dataset.dataset_version,
        run_mode=dataset.run_mode,
        scenario_count=len(dataset.scenarios),
        turn_count=turn_count,
        scenario_ids=scenario_ids,
        unsupported_expected_fields=unsupported_expected_fields,
        unsupported_expected_sources=sorted(unsupported_expected_sources),
        errors=errors,
    )


def _validate_suite_metadata(dataset: ValidationDataset, errors: list[str]) -> None:
    if dataset.suite_type not in SuiteType.values():
        errors.append(
            f"Unsupported suite_type {dataset.suite_type!r}; expected one of "
            f"{', '.join(SuiteType.values())}."
        )
        return
    if dataset.run_mode not in RunMode.values():
        errors.append(
            f"Unsupported run_mode {dataset.run_mode!r}; expected one of "
            f"{', '.join(RunMode.values())}."
        )
    if dataset.suite_type == SuiteType.ATOMIC_SCRIPTED.value:
        if dataset.causal_continuity is not False:
            errors.append("atomic_scripted datasets must set causal_continuity=false.")
        if dataset.run_mode != RunMode.SCRIPTED_REPLAY.value:
            errors.append("atomic_scripted datasets must use run_mode='scripted_replay'.")
        if len(dataset.scenarios) != 5:
            errors.append(f"Expected 5 atomic scenarios, found {len(dataset.scenarios)}.")
        turn_count = sum(len(scenario.turns) for scenario in dataset.scenarios)
        if turn_count != 60:
            errors.append(f"Expected 60 total atomic turns, found {turn_count}.")
    elif dataset.suite_type == SuiteType.COHERENT_SCRIPTED.value:
        if dataset.causal_continuity is not True:
            errors.append("coherent_scripted datasets must set causal_continuity=true.")
        if dataset.run_mode != RunMode.SCRIPTED_REPLAY.value:
            errors.append("coherent_scripted datasets must use run_mode='scripted_replay'.")
        if len(dataset.scenarios) < 5:
            errors.append(
                f"Expected at least 5 coherent scenarios, found {len(dataset.scenarios)}."
            )
    elif dataset.suite_type == SuiteType.ADAPTIVE_HYBRID.value:
        errors.append(
            "adaptive_hybrid uses the predeploy interface schema and cannot be loaded as "
            "a scripted ValidationDataset in Phase 1."
        )


def _validate_scenario_shape(
    dataset: ValidationDataset,
    scenario: ValidationScenario,
    errors: list[str],
) -> None:
    turn_count = len(scenario.turns)
    if dataset.suite_type == SuiteType.ATOMIC_SCRIPTED.value and turn_count != 12:
        errors.append(
            f"{scenario.conversation_id} must contain 12 atomic turns; found {turn_count}."
        )
    if dataset.suite_type == SuiteType.COHERENT_SCRIPTED.value and not 8 <= turn_count <= 15:
        errors.append(
            f"{scenario.conversation_id} must contain 8-15 coherent turns; found {turn_count}."
        )


def contract_value_errors(expected: dict) -> list[str]:
    errors = []
    for field, enum_cls in CONTRACT_EXPECTED_FIELDS.items():
        if field not in expected:
            continue
        value = expected.get(field)
        if value in (None, "") and field in {"objection_type", "objection_flow_step"}:
            value = "none"
        if value not in enum_cls.values():
            errors.append(
                f"{field}={value!r} is not in Commercial Contract V2 "
                f"({', '.join(enum_cls.values())})."
            )
    return errors


def _validate_bool_expected_values(expected: dict, location: str, errors: list[str]) -> None:
    for field in ("rag_used", "structured_used", "json_used"):
        if field in expected and not isinstance(expected.get(field), bool):
            errors.append(f"{location}: {field} must be true or false.")


def _default_source_capabilities() -> Set[str]:
    from movia_sales_agent.evaluation.capabilities import source_capabilities

    return source_capabilities()
