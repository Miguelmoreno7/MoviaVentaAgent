from types import SimpleNamespace

from movia_sales_agent.whatsapp.interactive_policy import resolve_interactive_packet


class Message:
    def __init__(self, text="button text", interactive_button_id=None):
        self.text = text
        self.interactive_button_id = interactive_button_id


def response(**overrides):
    base = {
        "action": "answer_and_advance",
        "selected_action": {
            "macro_action": "answer_and_advance",
            "micro_action": "answer_general_then_discover_need",
            "target_stage": "new",
        },
        "lead_state": {"current_stage": "new", "profile_data": {}},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_entry_prices_low_context_sends_price_qualification_not_prices():
    packet = resolve_interactive_packet(
        response=response(),
        batch=[Message(interactive_button_id="entry_prices")],
    )

    assert packet
    assert packet.key == "price_qualification"
    assert "$4,900" not in packet.body
    assert "$7,500" not in packet.body
    assert [button["title"] for button in packet.buttons] == [
        "Responder dudas",
        "Hacer acciones",
        "No sé todavía",
    ]


def test_need_answers_sends_captura_price_context():
    packet = resolve_interactive_packet(
        response=response(),
        batch=[Message(interactive_button_id="need_answers")],
    )

    assert packet
    assert packet.key == "captura_price_context"
    assert "MovIA Captura" in packet.body
    assert "$4,900 MXN" in packet.body
    assert "MovIA Ventas" not in packet.body
    assert "Pro Comercial" not in packet.body


def test_need_actions_sends_hibrido_price_context():
    packet = resolve_interactive_packet(
        response=response(),
        batch=[Message(interactive_button_id="need_actions")],
    )

    assert packet
    assert packet.key == "hibrido_price_context"
    assert "MovIA Híbrido" in packet.body
    assert "$7,500 MXN" in packet.body


def test_meaningful_free_text_bypasses_interactive_packet():
    packet = resolve_interactive_packet(
        response=response(),
        batch=[
            Message(interactive_button_id="entry_prices"),
            Message(text="Tengo una clínica dental y quiero agendar citas"),
        ],
    )

    assert packet is None


def test_exit_guards_bypass_interactive_packet():
    direct_close = response(
        action="direct_close",
        selected_action={"macro_action": "direct_close", "target_stage": "closing"},
    )
    objection = response(
        selected_action={"macro_action": "handle_objection", "target_stage": "objection_handling"},
        lead_state={"active_objection": {"active": True, "status": "active"}},
    )
    post_purchase = response(
        selected_action={"macro_action": "handoff_to_miguel", "target_stage": "post_purchase"},
    )
    custom_scope = response(
        selected_action={
            "macro_action": "handoff_to_miguel",
            "micro_action": "redirect_custom_scope",
            "reason_code": "CUSTOM_SCOPE_REVIEW",
        },
    )

    for guarded in [direct_close, objection, post_purchase, custom_scope]:
        packet = resolve_interactive_packet(
            response=guarded,
            batch=[Message(interactive_button_id="entry_prices")],
        )
        assert packet is None


def test_product_context_bypasses_generic_price_qualification():
    packet = resolve_interactive_packet(
        response=response(
            lead_state={
                "profile_data": {
                    "product_context": {
                        "active_product_context": "movia_captura",
                    }
                }
            }
        ),
        batch=[Message(interactive_button_id="entry_prices")],
    )

    assert packet is None


def test_max_interactive_packet_count_is_respected():
    packet = resolve_interactive_packet(
        response=response(),
        batch=[Message(interactive_button_id="entry_prices")],
        sent_count=3,
    )

    assert packet is None
