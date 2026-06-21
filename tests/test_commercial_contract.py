import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from movia_sales_agent.contracts.commercial import (
    COMMERCIAL_CONTRACT_VERSION,
    CONTRACT_ENUMS,
    MacroAction,
    PlannerReasonCode,
    SalesStage,
    commercial_contract,
)
from movia_sales_agent.models.schemas import SalesPlan, TurnAnalysis


CONTRACT_JSON_PATH = Path("docs/architecture/COMMERCIAL_CONTRACT_V2.json")


def test_contract_json_matches_python_source_of_truth():
    checked_in = json.loads(CONTRACT_JSON_PATH.read_text(encoding="utf-8"))

    assert checked_in == commercial_contract()
    assert checked_in["commercial_contract_version"] == COMMERCIAL_CONTRACT_VERSION


def test_contract_enums_have_no_duplicate_values():
    for enum_name, enum_cls in CONTRACT_ENUMS.items():
        values = enum_cls.values()
        assert len(values) == len(set(values)), enum_name


def test_turn_analysis_rejects_unknown_taxonomy_values():
    invalid_payloads = [
        {"primary_intent": "pre_purchase"},
        {"topics": ["pricing_question"]},
        {"objection_type": "general_objection"},
        {"objection_strength": "medium"},
        {"buying_signal": "ready_to_buy"},
        {"intent": "pricing_question"},
        {"wants_to_start": True},
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            TurnAnalysis(**payload)


def test_sales_plan_rejects_unknown_commercial_values():
    valid = {
        "macro_action": MacroAction.ANSWER_AND_ADVANCE.value,
        "micro_action": "answer_price_then_explain_scope",
        "commercial_goal": "Answer price and advance one step.",
        "cta_type": "soft_question",
        "objection_flow_step": "none",
        "target_stage": SalesStage.EDUCATING.value,
        "reason_code": PlannerReasonCode.PRICE_QUESTION_WITH_DISCOVERY_GAP.value,
    }
    invalid_payloads = [
        {**valid, "macro_action": "answer"},
        {**valid, "micro_action": "answer_price"},
        {**valid, "cta_type": "send_everything"},
        {**valid, "objection_flow_step": "first_response"},
        {**valid, "target_stage": "recommended"},
        {**valid, "reason_code": "PRICE_QUESTION"},
    ]

    assert SalesPlan(**valid).macro_action == MacroAction.ANSWER_AND_ADVANCE.value
    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            SalesPlan(**payload)
