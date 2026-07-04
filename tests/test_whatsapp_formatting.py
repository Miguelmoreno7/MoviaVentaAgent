from movia_sales_agent.whatsapp.formatting import split_whatsapp_messages
from movia_sales_agent.whatsapp.client import WhatsAppClient
from movia_sales_agent.config.settings import Settings


def mocked_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        META_WHATSAPP_ACCESS_TOKEN=None,
        META_WHATSAPP_PHONE_NUMBER_ID=None,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )


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
    client = WhatsAppClient(mocked_settings())
    text = ("MovIA puede ayudarte a responder mejor en WhatsApp. " * 30).strip()

    result = client.send_text("5218180000000", text)

    assert result["split"] is True
    assert result["count"] > 1
    assert [message["index"] for message in result["messages"]] == list(range(result["count"]))
    assert all(message["result"]["mocked"] is True for message in result["messages"])


def test_whatsapp_client_parses_n8n_wrapped_body_payload():
    client = WhatsAppClient(mocked_settings())

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
    client = WhatsAppClient(mocked_settings())

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


def test_whatsapp_client_parses_interactive_button_reply_as_text():
    client = WhatsAppClient(mocked_settings())

    messages = client.parse_messages(
        {
            "messages": [
                {
                    "from": "5218717876121",
                    "id": "wamid.button",
                    "timestamp": "1782071899",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "entry_prices", "title": "Ver precios"},
                    },
                }
            ]
        }
    )

    assert len(messages) == 1
    assert messages[0].message_id == "wamid.button"
    assert messages[0].text == "Quiero ver precios"


def test_whatsapp_client_sends_entry_intent_interactive_buttons_mocked():
    client = WhatsAppClient(mocked_settings())

    result = client.send_entry_intent_buttons("5218180000000")

    assert result["mocked"] is True
    payload = result["payload"]
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "button"
    assert payload["interactive"]["body"]["text"].startswith("¡Hola! Soy el asistente de MovIA.")
    buttons = payload["interactive"]["action"]["buttons"]
    assert [button["reply"]["title"] for button in buttons] == [
        "Ver precios",
        "Elegir agente",
        "Cómo funciona",
    ]


def test_whatsapp_client_marks_read_with_typing_mocked_without_meta_credentials():
    client = WhatsAppClient(mocked_settings())

    result = client.mark_messages_read_with_typing(["wamid.1", "wamid.1", "wamid.2"])

    assert result == {"attempted": 2, "succeeded": 2, "failed": 0}


def test_whatsapp_client_marks_read_payload_without_typing(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True}

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return FakeResponse()

    import movia_sales_agent.whatsapp.client as whatsapp_client

    monkeypatch.setattr(whatsapp_client.httpx, "Client", FakeHttpClient)
    client = WhatsAppClient(
        Settings(
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            OPENAI_MODEL="offline",
            MOVIA_DISABLE_OPENAI=True,
            MOVIA_DISABLE_DATABASE=True,
            META_WHATSAPP_ACCESS_TOKEN="token",
            META_WHATSAPP_PHONE_NUMBER_ID="phone-id",
        )
    )

    result = client.mark_read("wamid.1")

    assert result == {"success": True}
    assert calls[0]["url"] == "https://graph.facebook.com/v20.0/phone-id/messages"
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.1",
    }


def test_whatsapp_client_marks_read_with_typing_payload(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True}

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return FakeResponse()

    import movia_sales_agent.whatsapp.client as whatsapp_client

    monkeypatch.setattr(whatsapp_client.httpx, "Client", FakeHttpClient)
    client = WhatsAppClient(
        Settings(
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            OPENAI_MODEL="offline",
            MOVIA_DISABLE_OPENAI=True,
            MOVIA_DISABLE_DATABASE=True,
            META_WHATSAPP_ACCESS_TOKEN="token",
            META_WHATSAPP_PHONE_NUMBER_ID="phone-id",
        )
    )

    result = client.mark_read_with_typing("wamid.1")

    assert result == {"success": True}
    assert calls[0]["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.1",
        "typing_indicator": {"type": "text"},
    }
