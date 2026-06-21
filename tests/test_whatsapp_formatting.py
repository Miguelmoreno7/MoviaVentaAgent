from movia_sales_agent.whatsapp.formatting import split_whatsapp_messages
from movia_sales_agent.whatsapp.client import WhatsAppClient
from movia_sales_agent.config.settings import Settings


def test_short_message_stays_single_part():
    parts = split_whatsapp_messages("Hola, puedo ayudarte con MovIA Captura.")

    assert parts == ["Hola, puedo ayudarte con MovIA Captura."]


def test_long_message_splits_on_readable_boundaries():
    text = (
        "MovIA Captura sirve para responder dudas frecuentes y capturar datos básicos. "
        "También ayuda a ordenar leads antes de pasarlos a una persona. "
        "MovIA Híbrido conviene cuando además necesitas acciones como agendar, cotizar o registrar información. "
    ) * 5

    parts = split_whatsapp_messages(text, soft_limit=220, hard_limit=320)

    assert len(parts) > 1
    assert all(len(part) <= 320 for part in parts)
    assert all(part.strip() == part for part in parts)


def test_short_intro_merges_with_following_message():
    text = (
        "Claro, te explico el proceso:\n\n"
        "Primero entras a la app, eliges el producto, llenas la información inicial "
        "y pagas el depósito para que MovIA pueda comenzar."
    )

    parts = split_whatsapp_messages(text, soft_limit=260, hard_limit=320)

    assert len(parts) == 1
    assert "Claro" in parts[0]
    assert "Primero" in parts[0]


def test_short_intro_can_merge_past_soft_limit_when_under_hard_limit():
    intro = "Claro, te explico el proceso para empezar con MovIA:"
    next_message = " ".join(["paso"] * 120)

    parts = split_whatsapp_messages(
        f"{intro}\n\n{next_message}",
        soft_limit=220,
        hard_limit=700,
    )

    assert len(parts) == 1
    assert parts[0].startswith("Claro")


def test_whatsapp_client_sends_split_messages_in_order_when_mocked():
    client = WhatsAppClient(
        Settings(
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            OPENAI_MODEL="offline",
            MOVIA_DISABLE_OPENAI=True,
            MOVIA_DISABLE_DATABASE=True,
        )
    )
    text = ("MovIA puede ayudarte a responder mejor en WhatsApp. " * 30).strip()

    result = client.send_text("5218180000000", text)

    assert result["split"] is True
    assert result["count"] > 1
    assert [message["index"] for message in result["messages"]] == list(range(result["count"]))
    assert all(message["result"]["mocked"] is True for message in result["messages"])


def test_whatsapp_client_parses_n8n_wrapped_body_payload():
    client = WhatsAppClient(
        Settings(
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            OPENAI_MODEL="offline",
            MOVIA_DISABLE_OPENAI=True,
            MOVIA_DISABLE_DATABASE=True,
        )
    )

    messages = client.parse_messages(
        [
            {
                "headers": {"content-type": "application/json"},
                "body": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"wa_id": "5218717876121"}],
                    "messages": [
                        {
                            "from": "5218717876121",
                            "id": "wamid.example",
                            "timestamp": "1782071897",
                            "text": {"body": "Hola!"},
                            "type": "text",
                        }
                    ],
                },
            }
        ]
    )

    assert len(messages) == 1
    assert messages[0].message_id == "wamid.example"
    assert messages[0].from_number == "5218717876121"
    assert messages[0].text == "Hola!"


def test_whatsapp_client_parses_direct_body_messages_payload():
    client = WhatsAppClient(
        Settings(
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            OPENAI_MODEL="offline",
            MOVIA_DISABLE_OPENAI=True,
            MOVIA_DISABLE_DATABASE=True,
        )
    )

    messages = client.parse_messages(
        {
            "body": {
                "messages": [
                    {
                        "from": "5218717876121",
                        "id": "wamid.direct",
                        "text": {"body": "Hola directo"},
                        "type": "text",
                    }
                ]
            }
        }
    )

    assert len(messages) == 1
    assert messages[0].message_id == "wamid.direct"
    assert messages[0].text == "Hola directo"
