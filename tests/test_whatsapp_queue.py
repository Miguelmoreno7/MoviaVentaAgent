import asyncio
import time
from types import SimpleNamespace

import pytest

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.whatsapp.client import WhatsAppMessage
from movia_sales_agent.whatsapp.queue import InMemoryWhatsAppQueue, WhatsAppWorkerManager, build_queue


class FakeAgent:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = []
        self.starts = []

    def invoke(self, *, message, lead_external_id, channel, external_message_id):
        self.starts.append((lead_external_id, time.monotonic()))
        if self.delay:
            time.sleep(self.delay)
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
            response=f"respuesta para {lead_external_id}",
            response_messages=[f"respuesta para {lead_external_id}"],
            response_metadata={"response_source": "fake"},
            token_usage={"total": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
        )


class FakeClient:
    def __init__(self):
        self.sent = []

    def send_text(self, to_number, text):
        self.sent.append({"to": to_number, "text": text})
        return {"mocked": True}


def queue_settings(**overrides):
    values = {
        "DATABASE_URL": None,
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "offline",
        "MOVIA_DISABLE_OPENAI": True,
        "MOVIA_DISABLE_DATABASE": True,
        "REDIS_URL": None,
        "MOVIA_WEBHOOK_QUEUE_ENABLED": True,
        "MOVIA_JOB_CONCURRENCY": 2,
        "MOVIA_LEAD_BATCH_WINDOW_SECONDS": 0.05,
        "MOVIA_PLATFORM_OBSERVABILITY_ENABLED": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_same_lead_messages_are_batched_into_one_agent_run():
    agent = FakeAgent()
    client = FakeClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
    )
    await manager.start()
    try:
        assert await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola")) == "queued"
        assert await manager.enqueue(WhatsAppMessage("m2", "lead-a", "Cuánto cuesta")) == "queued"
        await wait_for(lambda: len(agent.calls) == 1)
    finally:
        await manager.stop()

    assert "Mensaje 1: Hola" in agent.calls[0]["message"]
    assert "Mensaje 2: Cuánto cuesta" in agent.calls[0]["message"]
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_different_leads_can_run_concurrently():
    agent = FakeAgent(delay=0.2)
    client = FakeClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await manager.enqueue(WhatsAppMessage("m2", "lead-b", "Hola"))
        await wait_for(lambda: len(agent.calls) == 2, timeout=2)
    finally:
        await manager.stop()

    assert len(agent.starts) == 2
    assert abs(agent.starts[0][1] - agent.starts[1][1]) < 0.15


@pytest.mark.asyncio
async def test_duplicate_message_id_is_not_queued_twice():
    queue = InMemoryWhatsAppQueue()
    message = WhatsAppMessage("m1", "lead-a", "Hola")

    assert await queue.enqueue(to_queued(message)) == "queued"
    assert await queue.enqueue(to_queued(message)) == "duplicate"


def test_build_queue_falls_back_when_redis_is_unreachable():
    settings = queue_settings(REDIS_URL="redis://unreachable-redis-host:6379/0")

    queue = build_queue(settings)

    assert isinstance(queue, InMemoryWhatsAppQueue)
    assert queue.durable is False


def to_queued(message):
    from movia_sales_agent.whatsapp.queue import QueuedWhatsAppMessage

    return QueuedWhatsAppMessage(
        message_id=message.message_id,
        from_number=message.from_number,
        text=message.text,
    )


async def wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")
