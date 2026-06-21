import time
from types import SimpleNamespace

import httpx
import pytest

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.platform.observability import (
    AgentRuntimeInfo,
    PlatformObservabilityService,
    PlatformRuntimeResolver,
    extract_total_tokens,
)
from movia_sales_agent.platform.registry_sync import PlatformSyncConfig, read_registry, sync_registry
from movia_sales_agent.whatsapp.client import WhatsAppMessage
from movia_sales_agent.whatsapp.queue import InMemoryWhatsAppQueue, WhatsAppWorkerManager


def platform_settings(**overrides):
    values = {
        "DATABASE_URL": None,
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "offline",
        "MOVIA_DISABLE_OPENAI": True,
        "MOVIA_DISABLE_DATABASE": True,
        "REDIS_URL": None,
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "MOVIA_PLATFORM_OBSERVABILITY_ENABLED": True,
        "MOVIA_PLATFORM_AGENT_KEY": "movia_sales_agent",
        "MOVIA_PLATFORM_AGENT_VERSION": "v1",
        "MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS": 30,
        "MOVIA_WEBHOOK_QUEUE_ENABLED": True,
        "MOVIA_JOB_CONCURRENCY": 1,
        "MOVIA_LEAD_BATCH_WINDOW_SECONDS": 0,
    }
    values.update(overrides)
    return Settings(**values)


class FakePlatformClient:
    def __init__(self, runtime=None):
        self.runtime = runtime or AgentRuntimeInfo(
            agent_id="agent-1",
            agent_key="movia_sales_agent",
            enabled=True,
            version="v1",
            agent_version_id="version-1",
        )
        self.resolve_calls = 0
        self.fail_resolve = False
        self.created = []
        self.events = []
        self.updates = []
        self.fail_events = False
        self.fail_updates = False

    def resolve_agent_runtime(self, *, agent_key, requested_version=None):
        self.resolve_calls += 1
        if self.fail_resolve:
            raise RuntimeError("platform unavailable")
        return self.runtime

    def create_run(self, **kwargs):
        self.created.append(kwargs)
        return kwargs.get("run_id") or "run-1"

    def add_event(self, **kwargs):
        if self.fail_events:
            raise RuntimeError("event write failed")
        self.events.append(kwargs)

    def update_run(self, **kwargs):
        if self.fail_updates:
            raise RuntimeError("update failed")
        self.updates.append(kwargs)


def conflict_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/run_events")
    response = httpx.Response(
        409,
        request=request,
        json={"code": "23503", "message": "insert or update violates foreign key"},
    )
    return httpx.HTTPStatusError(
        "Client error '409 Conflict' for url 'https://example.supabase.co/rest/v1/run_events'",
        request=request,
        response=response,
    )


class ConflictThenSuccessPlatformClient(FakePlatformClient):
    def __init__(self, conflicts: int):
        super().__init__()
        self.conflicts = conflicts
        self.event_attempts = 0

    def add_event(self, **kwargs):
        self.event_attempts += 1
        if self.event_attempts <= self.conflicts:
            raise conflict_error()
        self.events.append(kwargs)


class FakeAgent:
    def __init__(self):
        self.calls = []

    def invoke(self, *, message, lead_external_id, channel, external_message_id):
        self.calls.append(
            {
                "message": message,
                "lead_external_id": lead_external_id,
                "channel": channel,
                "external_message_id": external_message_id,
            }
        )
        return SimpleNamespace(
            action="answer_and_advance",
            response="Respuesta",
            response_messages=["Respuesta"],
            response_metadata={"response_source": "fake"},
            token_usage={"total": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}},
        )


class FakeWhatsAppClient:
    def __init__(self):
        self.sent = []

    def send_text(self, to_number, text):
        self.sent.append({"to": to_number, "text": text})
        return {"mocked": True}


def test_registry_json_shape_matches_platform_contract():
    agents = read_registry(platform_settings().agents_registry_path)

    assert agents[0]["key"] == "movia_sales_agent"
    assert agents[0]["default_version"] == "v1"
    assert agents[0]["versions"][0]["entrypoint"] == "movia_sales_agent.api.main:app"
    assert agents[0]["versions"][0]["config_json"]["webhook_path"] == "/webhooks/whatsapp"


def test_registry_sync_dry_run_uses_expected_actions(monkeypatch, tmp_path):
    registry = tmp_path / "agents.json"
    registry.write_text(
        """
        {
          "agents": [
            {
              "key": "movia_sales_agent",
              "name": "MovIA Sales Agent",
              "enabled": true,
              "default_version": "v1",
              "versions": [
                {
                  "version": "v1",
                  "entrypoint": "movia_sales_agent.api.main:app",
                  "status": "active",
                  "config_json": {}
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    class FakeRegistryClient:
        def __init__(self, *args, **kwargs):
            pass

        def ensure_agent(self, **kwargs):
            assert kwargs["dry_run"] is True
            return "<new-agent>", "insert(dry-run)", True

        def ensure_agent_version(self, **kwargs):
            raise AssertionError("new dry-run agent should not need a real version id")

    import movia_sales_agent.platform.registry_sync as registry_sync

    monkeypatch.setattr(registry_sync, "SupabaseRegistryClient", FakeRegistryClient)
    result = sync_registry(
        PlatformSyncConfig(
            supabase_url="https://example.supabase.co",
            service_role_key="service-role",
            registry_path=registry,
            dry_run=True,
        )
    )

    assert result["agent_actions"][0]["action"] == "insert(dry-run)"
    assert result["version_actions"][0]["action"] == "insert(dry-run)"


def test_runtime_resolution_is_cached_within_ttl():
    client = FakePlatformClient()
    resolver = PlatformRuntimeResolver(
        settings=platform_settings(),
        client=client,
        memory=None,
    )

    first, refreshed_first, warning_first = resolver.resolve()
    second, refreshed_second, warning_second = resolver.resolve()

    assert first == second
    assert refreshed_first is True
    assert refreshed_second is False
    assert warning_first is None
    assert warning_second is None
    assert client.resolve_calls == 1


def test_runtime_resolution_uses_stale_cache_when_refresh_fails():
    client = FakePlatformClient()
    resolver = PlatformRuntimeResolver(
        settings=platform_settings(MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS=1),
        client=client,
        memory=None,
    )
    runtime, _, _ = resolver.resolve()
    cached = next(iter(resolver._cache.values()))
    cached.expires_at = time.time() - 1
    client.fail_resolve = True

    stale_runtime, refreshed, warning = resolver.resolve()

    assert stale_runtime == runtime
    assert refreshed is False
    assert "platform unavailable" in warning


def test_runtime_resolution_fails_closed_without_cache():
    client = FakePlatformClient()
    client.fail_resolve = True
    resolver = PlatformRuntimeResolver(
        settings=platform_settings(),
        client=client,
        memory=None,
    )

    runtime, refreshed, warning = resolver.resolve()

    assert runtime is None
    assert refreshed is False
    assert "platform unavailable" in warning


@pytest.mark.asyncio
async def test_disabled_platform_agent_skips_execution_and_send():
    runtime = AgentRuntimeInfo(
        agent_id="agent-1",
        agent_key="movia_sales_agent",
        enabled=False,
        version="v1",
        agent_version_id="version-1",
    )
    client = FakePlatformClient(runtime=runtime)
    service = PlatformObservabilityService(
        settings=platform_settings(),
        client=client,
        resolver=PlatformRuntimeResolver(settings=platform_settings(), client=client),
    )
    agent = FakeAgent()
    whatsapp = FakeWhatsAppClient()
    manager = WhatsAppWorkerManager(
        settings=platform_settings(),
        agent=agent,
        client=whatsapp,
        queue=InMemoryWhatsAppQueue(),
        observability=service,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: client.created)
    finally:
        await manager.stop()

    assert agent.calls == []
    assert whatsapp.sent == []
    assert client.created[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_observability_write_failures_do_not_block_agent_or_send():
    client = FakePlatformClient()
    client.fail_events = True
    client.fail_updates = True
    service = PlatformObservabilityService(
        settings=platform_settings(),
        client=client,
        resolver=PlatformRuntimeResolver(settings=platform_settings(), client=client),
    )
    agent = FakeAgent()
    whatsapp = FakeWhatsAppClient()
    manager = WhatsAppWorkerManager(
        settings=platform_settings(),
        agent=agent,
        client=whatsapp,
        queue=InMemoryWhatsAppQueue(),
        observability=service,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: len(agent.calls) == 1 and len(whatsapp.sent) == 1)
    finally:
        await manager.stop()

    assert len(agent.calls) == 1
    assert len(whatsapp.sent) == 1


def test_extract_total_tokens_from_nested_chat_response_usage():
    payload = {
        "calls": [
            {"operation": "analysis", "input_tokens": 100, "output_tokens": 30},
            {"operation": "response", "total_tokens": 450},
        ],
        "total": {"input_tokens": 300, "output_tokens": 200, "total_tokens": 500},
    }

    assert extract_total_tokens(payload) == 500


def test_event_write_retries_transient_conflict(monkeypatch):
    client = ConflictThenSuccessPlatformClient(conflicts=2)
    service = PlatformObservabilityService(
        settings=platform_settings(),
        client=client,
        resolver=PlatformRuntimeResolver(settings=platform_settings(), client=client),
    )
    import movia_sales_agent.platform.observability as observability

    monkeypatch.setattr(observability.time, "sleep", lambda _seconds: None)

    service._add_event_best_effort(
        run_id="run-1",
        level="info",
        event_type="agent_started",
        message="Agent started.",
        payload_json={},
    )

    assert client.event_attempts == 3
    assert client.events[0]["event_type"] == "agent_started"


def test_event_write_stops_after_repeated_conflicts(monkeypatch):
    client = ConflictThenSuccessPlatformClient(conflicts=10)
    service = PlatformObservabilityService(
        settings=platform_settings(),
        client=client,
        resolver=PlatformRuntimeResolver(settings=platform_settings(), client=client),
    )
    import movia_sales_agent.platform.observability as observability

    monkeypatch.setattr(observability.time, "sleep", lambda _seconds: None)

    service._add_event_best_effort(
        run_id="run-1",
        level="info",
        event_type="agent_started",
        message="Agent started.",
        payload_json={},
    )

    assert client.event_attempts == 4
    assert client.events == []


async def wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await __import__("asyncio").sleep(0.01)
    raise AssertionError("condition was not met before timeout")
