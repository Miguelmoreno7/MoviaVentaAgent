from fastapi.testclient import TestClient
import pytest

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.api.main import (
    app,
    get_agent,
    get_settings,
    get_whatsapp_client,
    sync_platform_registry_on_startup,
)
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.whatsapp.client import WhatsAppClient


class RecordingWhatsAppClient(WhatsAppClient):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.read_calls = []

    def mark_read(self, message_id: str):
        self.read_calls.append(message_id)
        return {"mocked": True, "message_id": message_id, "typing_indicator": False}


def make_test_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        MOVIA_INTERNAL_API_KEY="test-key",
        MOVIA_ENABLE_DEBUG_UI=True,
        MOVIA_DEBUG_METADATA=True,
        MOVIA_WEBHOOK_QUEUE_ENABLED=False,
        MOVIA_LEAD_BATCH_WINDOW_SECONDS=0,
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=False,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )


def test_health_and_chat_endpoint():
    settings = make_test_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    frontend = client.get("/")
    assert frontend.status_code == 401

    frontend = client.get("/", headers={"x-movia-internal-api-key": "test-key"})
    assert frontend.status_code == 200
    assert "MovIA Agent Tester" in frontend.text

    response = client.post(
        "/chat",
        json={"lead_external_id": "api-1", "message": "Quiero empezar"},
        headers={"x-movia-internal-api-key": "test-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "answer_unknown_safely"
    assert "app.moviatech.com.mx" in body["response"]
    assert body["response_messages"]
    assert body["selected_action"]["macro_action"] == "answer_unknown_safely"
    assert body["lead_state"]["last_action"] == "answer_unknown_safely"
    assert "total" in body["token_usage"]
    app.dependency_overrides.clear()


def test_chat_endpoint_requires_internal_api_key():
    settings = make_test_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    client = TestClient(app)

    response = client.post(
        "/chat",
        json={"lead_external_id": "api-auth", "message": "Hola"},
    )

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_debug_ui_can_be_disabled():
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        MOVIA_INTERNAL_API_KEY="test-key",
        MOVIA_ENABLE_DEBUG_UI=False,
        MOVIA_WEBHOOK_QUEUE_ENABLED=False,
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=False,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    frontend = client.get("/", headers={"x-movia-internal-api-key": "test-key"})

    assert frontend.status_code == 404
    app.dependency_overrides.clear()


def test_chat_compacts_metadata_when_debug_metadata_is_disabled():
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        MOVIA_INTERNAL_API_KEY="test-key",
        MOVIA_DEBUG_METADATA=False,
        MOVIA_WEBHOOK_QUEUE_ENABLED=False,
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=False,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    client = TestClient(app)

    response = client.post(
        "/chat",
        json={"lead_external_id": "api-compact", "message": "¿Cuánto cuesta?"},
        headers={"x-movia-internal-api-key": "test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "analyzer_observation" not in body["response_metadata"]
    assert "normalized_turn" not in body["response_metadata"]
    assert "token_total" in body["response_metadata"]
    assert body["retrieved_sources"] == []
    app.dependency_overrides.clear()


def test_whatsapp_dispatcher_post_mock_receive_without_queue():
    settings = make_test_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    client = TestClient(app)

    inbound = client.post(
        "/webhooks/whatsapp",
        json={
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "5218180000000",
                                        "type": "text",
                                        "text": {"body": "¿Cuánto cuesta?"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        },
    )
    assert inbound.status_code == 200
    body = inbound.json()
    assert body["processed"] == 1
    assert body["results"][0]["status"] == "processed"
    app.dependency_overrides.clear()


def test_whatsapp_webhook_fast_ack_queues_messages():
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        MOVIA_INTERNAL_API_KEY="test-key",
        MOVIA_WEBHOOK_QUEUE_ENABLED=True,
        MOVIA_LEAD_BATCH_WINDOW_SECONDS=0,
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=False,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    whatsapp = RecordingWhatsAppClient(settings)
    app.dependency_overrides[get_whatsapp_client] = lambda: whatsapp
    client = TestClient(app)

    inbound_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.queued.1",
                                    "from": "5218180000000",
                                    "type": "text",
                                    "text": {"body": "¿Cuánto cuesta?"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    first = client.post("/webhooks/whatsapp", json=inbound_payload)
    second = client.post("/webhooks/whatsapp", json=inbound_payload)

    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    assert first.json()["results"][0]["status"] == "queued"
    assert first.json()["results"][0]["read_status"] == "success"
    assert second.json()["results"][0]["status"] == "duplicate"
    assert second.json()["results"][0]["read_status"] == "success"
    assert whatsapp.read_calls == ["wamid.queued.1", "wamid.queued.1"]
    app.dependency_overrides.clear()


def test_whatsapp_webhook_accepts_n8n_wrapped_body_payload():
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        MOVIA_INTERNAL_API_KEY="test-key",
        MOVIA_WEBHOOK_QUEUE_ENABLED=True,
        MOVIA_LEAD_BATCH_WINDOW_SECONDS=0,
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=False,
        CHATWOOT_URL=None,
        CHATWOOT_API_TOKEN=None,
        CHATWOOT_ACCOUNT_ID=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_agent] = lambda: MoviaSalesAgent(settings)
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp",
        json=[
            {
                "headers": {"content-type": "application/json"},
                "body": {
                    "messaging_product": "whatsapp",
                    "messages": [
                        {
                            "from": "5218717876121",
                            "id": "wamid.n8n.1",
                            "timestamp": "1782071897",
                            "text": {"body": "Hola!"},
                            "type": "text",
                        }
                    ],
                },
            }
        ],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["queued"] == 1
    assert response.json()["results"][0]["status"] == "queued"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_platform_registry_sync_runs_on_startup_when_enabled(monkeypatch):
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-role",
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=True,
        MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=True,
    )
    calls = []

    def fake_sync_from_settings(received_settings, *, dry_run=False):
        calls.append({"settings": received_settings, "dry_run": dry_run})
        return {"agents_processed": 1, "versions_processed": 1}

    import movia_sales_agent.api.main as api_main

    monkeypatch.setattr(api_main, "sync_from_settings", fake_sync_from_settings)

    result = await sync_platform_registry_on_startup(settings)

    assert result["status"] == "success"
    assert calls == [{"settings": settings, "dry_run": False}]


@pytest.mark.asyncio
async def test_platform_registry_sync_startup_failure_does_not_crash(monkeypatch):
    settings = Settings(
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
        REDIS_URL=None,
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-role",
        MOVIA_PLATFORM_OBSERVABILITY_ENABLED=True,
        MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=True,
    )

    def fake_sync_from_settings(_settings, *, dry_run=False):
        raise RuntimeError("platform unavailable")

    import movia_sales_agent.api.main as api_main

    monkeypatch.setattr(api_main, "sync_from_settings", fake_sync_from_settings)

    result = await sync_platform_registry_on_startup(settings)

    assert result["status"] == "failed"
    assert "platform unavailable" in result["error"]
