from __future__ import annotations

from movia_sales_agent.evaluation.phase4_supplementary import (
    evaluate_turn,
    says_cannot_understand_audio,
    states_non_refundable,
)


def test_soft_price_objection_does_not_require_persistent_active_objection():
    violations = evaluate_turn(
        {
            "scenario_id": "PHASE4-SUP-003",
            "turn_id": 1,
            "agent_response": "Entiendo, veámoslo contra el costo de perder mensajes.",
            "analysis": {
                "objection_type": "price_objection",
                "objection_strength": "soft",
            },
            "active_objection_after": {},
            "normalized_turn": {},
            "persisted_requirement_profile": {},
            "product_state": {},
            "selected_sales_action": {},
            "structured_sources": [],
            "json_sources": [],
            "knowledge_needs": [],
            "response_source": "openai",
        }
    )

    assert not any(item["code"] == "active_objection_resolution_failure" for item in violations)


def test_refund_gate_accepts_equivalent_non_refundable_wording():
    assert states_non_refundable("El depósito es no reembolsable.")
    assert states_non_refundable("$2,450 MXN, que no se regresan.")


def test_audio_gate_flags_negative_audio_claims():
    assert says_cannot_understand_audio("Actualmente Captura no interpreta audios.")
    assert says_cannot_understand_audio("Captura no entiende audios de clientes.")
