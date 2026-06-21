import json
from pathlib import Path

import pytest

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.contracts.commercial import (
    ActionRequirement,
    MacroAction,
    MicroAction,
    ProductFit,
)
from movia_sales_agent.evaluation.analyzer_v3_targeted import (
    DEFAULT_TARGETED_MANIFEST,
    captura_external_overpromise,
    evaluate_gate_violations,
    load_targeted_manifest,
    resolve_targeted_turns,
    run_targeted_validation,
    unsupported_channel_claim,
)
from movia_sales_agent.evaluation.cli import build_parser


def offline_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


def test_targeted_manifest_is_reference_only_and_resolves_turns():
    raw = json.loads(DEFAULT_TARGETED_MANIFEST.read_text(encoding="utf-8"))
    serialized = json.dumps(raw)

    assert '"user"' not in serialized
    assert '"ideal_assistant"' not in serialized
    assert '"expected"' not in serialized

    manifest = load_targeted_manifest(DEFAULT_TARGETED_MANIFEST)
    turns = resolve_targeted_turns(manifest)
    focus = [turn for turn in turns if turn.focus]

    assert len(manifest.cases) == 8
    assert len(turns) >= 40
    assert len(focus) >= 25
    assert any(turn.case_id == "external_action_captura_hard_failure" for turn in focus)


def test_targeted_manifest_rejects_embedded_gold_fields(tmp_path: Path):
    payload = json.loads(DEFAULT_TARGETED_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][0]["user"] = "do not embed dataset messages"
    path = tmp_path / "bad_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="banned dataset field"):
        load_targeted_manifest(path)


def test_gate_checks_flag_external_action_captura_failure():
    record = {
        "focus": True,
        "checks": ["external_action_routing", "captura_external_action_overpromise"],
        "analysis": {
            "lead_updates": {
                "profile_data": {
                    "action_requirement": ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value,
                    "known_product_fit": ProductFit.MOVIA_CAPTURA.value,
                }
            }
        },
        "normalized_turn": {
            "action_requirement": ActionRequirement.EXTERNAL_ACTIONS_REQUIRED.value,
            "recommended_product": ProductFit.MOVIA_CAPTURA.value,
        },
        "selected_action": {
            "macro_action": MacroAction.RECOMMEND_SOLUTION.value,
            "micro_action": MicroAction.RECOMMEND_MOVIA_CAPTURA.value,
        },
        "agent_output": "MovIA Captura registra pedidos en tu sistema externo.",
    }

    violations = evaluate_gate_violations(record)
    codes = {violation["code"] for violation in violations}

    assert "impossible_action_product_state" in codes
    assert "external_action_miss" in codes
    assert "captura_external_action_overpromise" in codes


def test_channel_and_captura_claim_detectors_allow_safe_negations():
    assert unsupported_channel_claim("Facebook e Instagram ya están disponibles.")
    assert not unsupported_channel_claim(
        "Facebook e Instagram están en proceso; hoy solo WhatsApp Business está disponible."
    )
    assert not unsupported_channel_claim(
        "Hoy solo usar Instagram limita el alcance; por ahora WhatsApp Business es el canal disponible."
    )
    assert captura_external_overpromise("Captura registra pedidos en sistemas externos.")
    assert not captura_external_overpromise(
        "Captura puede recopilar información en WhatsApp, pero no registra pedidos en sistemas externos."
    )
    assert not captura_external_overpromise(
        "MovIA Captura funciona en WhatsApp, pero solo recopila información dentro del chat, sin registrar pedidos fuera."
    )


def test_offline_analyzer_only_targeted_run_writes_artifacts(tmp_path: Path):
    result = run_targeted_validation(
        manifest_path=DEFAULT_TARGETED_MANIFEST,
        output_root=tmp_path,
        mode="analyzer-only",
        settings=offline_settings(),
        offline=True,
        previous_run_paths=[],
        write_docs=False,
    )
    output = Path(result["output_dir"])

    assert result["mode"] == "analyzer-only"
    assert result["record_counts"]["analyzer_only"] >= 40
    assert result["gate_summary"]["hard_failures"] == 0
    assert (output / "analyzer_only_results.json").exists()
    assert (output / "summary.md").read_text(encoding="utf-8").endswith(
        "TARGETED CONTRACT VALIDATION PASSED\n"
    )


def test_cli_exposes_analyzer_v3_targeted_command():
    args = build_parser().parse_args(
        ["analyzer-v3-targeted", "--mode", "analyzer-only", "--offline"]
    )

    assert args.command == "analyzer-v3-targeted"
    assert args.mode == "analyzer-only"
    assert args.offline is True
