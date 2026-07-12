import json

from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.evaluation.cli import build_parser
from movia_sales_agent.evaluation.production_contract_regression import (
    DEFAULT_PRODUCTION_CONTRACT_DATASET,
    _no_write_settings,
    _record_has_fallback,
    _requires_stateful_replay,
)


VULNERABILITY_AUDIT_DATASET = (
    PROJECT_ROOT
    / "movia_validation_package"
    / "movia_contract_v3_2_vulnerability_audit.json"
)


def test_frozen_production_contract_dataset_has_required_coverage():
    dataset = json.loads(DEFAULT_PRODUCTION_CONTRACT_DATASET.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    ids = {case["id"] for case in cases}

    assert dataset["target_analyzer_contract_version"] == "3.2"
    assert dataset["provenance"]["frozen_before_runtime_changes"] is True
    assert dataset["provenance"]["source_conversation_ids"] == [84, 85, 86, 89]
    assert {
        "PROD-84-ACTION-SELECTION",
        "PROD-85-LINK-ACCEPTANCE",
        "PROD-86-LINK-ACCEPTANCE",
        "PROD-89-ACTION-FRAME",
        "OBJECTION-ACTIVE-RESOLVED",
        "PRODUCT-COMPARISON",
        "REQUIREMENT-EXPLICIT-REMOVAL",
        "PLANNER-UNKNOWN-DOES-NOT-REOPEN-COMPLETE-PROFILE",
    }.issubset(ids)
    assert all(int(case.get("repeat") or 1) == 5 for case in cases if case.get("repeat"))
    serialized = json.dumps(dataset, ensure_ascii=False)
    assert "wa_id" not in serialized
    assert "lead_id" not in serialized


def test_production_contract_settings_are_strictly_no_write():
    settings = Settings(
        DATABASE_URL="postgresql://would-write",
        REDIS_URL="redis://would-write",
        OPENAI_API_KEY="test-key",
        META_WHATSAPP_ACCESS_TOKEN="whatsapp-token",
        META_WHATSAPP_PHONE_NUMBER_ID="phone-id",
        META_CAPI_DATASET_ID="dataset-id",
        CHATWOOT_URL="https://chatwoot.example",
        CHATWOOT_API_TOKEN="chatwoot-token",
        CHATWOOT_ACCOUNT_ID=2,
    )

    isolated = _no_write_settings(settings)

    assert isolated.disable_database is True
    assert isolated.database_url is None
    assert isolated.redis_url is None
    assert isolated.disable_openai is False
    assert isolated.followup_enabled is False
    assert isolated.platform_observability_enabled is False
    assert isolated.meta_whatsapp_access_token is None
    assert isolated.chatwoot_url is None
    assert isolated.chatwoot_api_token is None


def test_vulnerability_audit_covers_every_v3_2_hardening_dimension():
    dataset = json.loads(VULNERABILITY_AUDIT_DATASET.read_text(encoding="utf-8"))
    ids = {case["id"] for case in dataset["cases"]}

    assert dataset["target_analyzer_contract_version"] == "3.2"
    assert any("ACTOR" in case_id for case_id in ids)
    assert any("CONTEXT" in case_id for case_id in ids)
    assert any("REQUIREMENT" in case_id for case_id in ids)
    assert any("OBJECTION" in case_id for case_id in ids)
    assert any("PRODUCT" in case_id for case_id in ids)
    assert any("COMPLETE-PROFILE" in case_id for case_id in ids)


def test_stateful_expectations_run_once_after_raw_repetitions():
    assert _requires_stateful_replay(
        {
            "case_type": "analyzer_turn",
            "expected": {"active_objection_after": "none"},
        }
    )
    assert not _requires_stateful_replay(
        {"case_type": "analyzer_turn", "expected": {"primary_intent": "general_info"}}
    )


def test_fallback_detection_supports_raw_and_graph_usage_shapes():
    assert _record_has_fallback(
        {"usage_calls": [{"provider": "fallback", "operation": "analysis"}]}
    )
    assert _record_has_fallback(
        {
            "usage_calls": [
                {
                    "calls": [
                        {"provider": "openai"},
                        {"provider": "openai", "error": "timeout"},
                    ]
                }
            ]
        }
    )
    assert not _record_has_fallback(
        {"usage_calls": [{"provider": "not_applicable", "operation": "reply_frame"}]}
    )


def test_cli_exposes_production_contract_regression_command():
    args = build_parser().parse_args(["production-contract-regression"])

    assert args.dataset == (
        PROJECT_ROOT
        / "movia_validation_package"
        / "movia_production_contract_regression_v1.json"
    )
    assert args.command == "production-contract-regression"
