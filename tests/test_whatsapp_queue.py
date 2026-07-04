import asyncio
import time
from types import SimpleNamespace

import pytest

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.whatsapp.client import WhatsAppMessage
from movia_sales_agent.whatsapp.queue import (
    InMemoryWhatsAppQueue,
    QueuedWhatsAppMessage,
    WhatsAppWorkerManager,
    build_queue,
)


class FakeAgent:
    def __init__(self, delay: float = 0.0, response_messages=None, selected_action=None):
        self.delay = delay
        self.response_messages = response_messages
        self.selected_action = selected_action or {}
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
            response_messages=self.response_messages or [f"respuesta para {lead_external_id}"],
            response_metadata={"response_source": "fake"},
            selected_action=self.selected_action,
            token_usage={"total": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
        )


class FakeClient:
    def __init__(self):
        self.sent = []
        self.interactive_buttons = []
        self.read_typing = []

    def send_text(self, to_number, text):
        self.sent.append({"to": to_number, "text": text})
        return {"mocked": True}

    def send_entry_intent_buttons(self, to_number):
        self.interactive_buttons.append({"to": to_number})
        return {"mocked": True, "interactive": True}

    def mark_messages_read_with_typing(self, message_ids):
        message_ids = list(message_ids)
        self.read_typing.append(message_ids)
        return {"attempted": len(message_ids), "succeeded": len(message_ids), "failed": 0}


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
        "CHATWOOT_URL": None,
        "CHATWOOT_API_TOKEN": None,
        "CHATWOOT_ACCOUNT_ID": None,
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
    assert client.read_typing == [["m1", "m2"]]
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_same_lead_messages_outside_batch_window_are_not_compacted():
    queue = InMemoryWhatsAppQueue()
    base = time.time()
    first = QueuedWhatsAppMessage(
        message_id="m1",
        from_number="lead-a",
        text="Hola",
        enqueued_at=base,
    )
    second = QueuedWhatsAppMessage(
        message_id="m2",
        from_number="lead-a",
        text="Sigo aquí",
        enqueued_at=base + 180,
    )

    assert await queue.enqueue(first) == "queued"
    assert await queue.enqueue(second) == "queued"
    lead = await queue.next_lead(timeout_seconds=1)
    assert lead is not None

    batch = await queue.collect_batch(lead, batch_window_seconds=20)
    assert [message.message_id for message in batch] == ["m1"]

    next_lead = await queue.next_lead(timeout_seconds=1)
    assert next_lead is not None
    next_batch = await queue.collect_batch(next_lead, batch_window_seconds=20)
    assert [message.message_id for message in next_batch] == ["m2"]


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


@pytest.mark.asyncio
async def test_worker_sends_agent_response_through_chatwoot_when_conversation_resolves():
    agent = FakeAgent()
    client = FakeClient()
    chatwoot = FakeChatwootClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: len(chatwoot.public_messages) == 1)
    finally:
        await manager.stop()

    assert client.sent == []
    assert chatwoot.resolved_numbers == ["lead-a"]
    assert chatwoot.public_messages[0]["conversation_id"] == 66
    assert chatwoot.public_messages[0]["messages"] == ["respuesta para lead-a"]


@pytest.mark.asyncio
async def test_worker_falls_back_to_whatsapp_and_private_note_when_chatwoot_public_send_fails():
    agent = FakeAgent()
    client = FakeClient()
    chatwoot = FakeChatwootClient(fail_public=True)
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: len(client.sent) == 1 and len(chatwoot.private_notes) == 1)
    finally:
        await manager.stop()

    assert client.sent == [{"to": "lead-a", "text": "respuesta para lead-a"}]
    assert "fallback sent" in chatwoot.private_notes[0]["content"]


@pytest.mark.asyncio
async def test_worker_does_not_whatsapp_fallback_after_partial_chatwoot_send():
    agent = FakeAgent(response_messages=["parte 1", "parte 2"])
    client = FakeClient()
    chatwoot = FakeChatwootClient(partial_public_failure=True)
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: len(agent.calls) == 1 and chatwoot.partial_attempted)
    finally:
        await manager.stop()

    assert client.sent == []
    assert chatwoot.private_notes == []


@pytest.mark.asyncio
async def test_worker_sends_entry_intent_as_whatsapp_interactive_buttons():
    agent = FakeAgent(selected_action={"next_question_key": "entry_intent"})
    client = FakeClient()
    chatwoot = FakeChatwootClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(WhatsAppMessage("m1", "lead-a", "Hola"))
        await wait_for(lambda: len(client.interactive_buttons) == 1)
    finally:
        await manager.stop()

    assert client.interactive_buttons == [{"to": "lead-a"}]
    assert client.sent == []
    assert chatwoot.public_messages == []
    assert "interactive button message" in chatwoot.private_notes[0]["content"]


@pytest.mark.asyncio
async def test_worker_sends_ctwa_first_touch_as_whatsapp_interactive_buttons():
    agent = FakeAgent(
        selected_action={
            "macro_action": "answer_and_advance",
            "micro_action": "answer_general_then_discover_need",
            "next_question_key": "business_type",
        }
    )
    client = FakeClient()
    chatwoot = FakeChatwootClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(
            WhatsAppMessage(
                "m1",
                "lead-a",
                "Hola, quiero más información",
                ctwa_clid="ctwa-123",
                referral={"campaign_id": "camp-1"},
            )
        )
        await wait_for(lambda: len(client.interactive_buttons) == 1)
    finally:
        await manager.stop()

    assert client.interactive_buttons == [{"to": "lead-a"}]
    assert client.sent == []
    assert chatwoot.public_messages == []


@pytest.mark.asyncio
async def test_worker_does_not_force_ctwa_buttons_for_specific_pricing_turn():
    agent = FakeAgent(
        selected_action={
            "macro_action": "answer_and_advance",
            "micro_action": "answer_price_then_explain_scope",
            "next_question_key": "business_type",
        }
    )
    client = FakeClient()
    chatwoot = FakeChatwootClient()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        chatwoot_client=chatwoot,
    )
    await manager.start()
    try:
        await manager.enqueue(
            WhatsAppMessage(
                "m1",
                "lead-a",
                "Hola, quiero más información",
                ctwa_clid="ctwa-123",
                referral={"campaign_id": "camp-1"},
            )
        )
        await manager.enqueue(WhatsAppMessage("m2", "lead-a", "¿Cuánto cuesta?"))
        await wait_for(lambda: len(chatwoot.public_messages) == 1)
    finally:
        await manager.stop()

    assert client.interactive_buttons == []
    assert chatwoot.public_messages[0]["messages"] == ["respuesta para lead-a"]


@pytest.mark.asyncio
async def test_worker_schedules_meta_conversions_with_batch_ctwa_metadata():
    agent = FakeAgent()
    client = FakeClient()
    meta = FakeMetaConversions()
    manager = WhatsAppWorkerManager(
        settings=queue_settings(MOVIA_LEAD_BATCH_WINDOW_SECONDS=0),
        agent=agent,
        client=client,
        queue=InMemoryWhatsAppQueue(),
        meta_conversions=meta,
    )
    await manager.start()
    try:
        await manager.enqueue(
            WhatsAppMessage(
                "m1",
                "lead-a",
                "Hola",
                ctwa_clid="ctwa-123",
                referral={"campaign_id": "camp-1"},
            )
        )
        await wait_for(lambda: len(meta.scheduled) == 1)
    finally:
        await manager.stop()

    assert meta.scheduled[0]["latest_ctwa_clid"] == "ctwa-123"
    assert meta.scheduled[0]["latest_referral"] == {"campaign_id": "camp-1"}


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


class FakeChatwootClient:
    enabled = True

    def __init__(self, fail_public=False, partial_public_failure=False):
        self.fail_public = fail_public
        self.partial_public_failure = partial_public_failure
        self.partial_attempted = False
        self.resolved_numbers = []
        self.public_messages = []
        self.private_notes = []

    def resolve_conversation_for_lead(self, *, lead_id, whatsapp_number, **_kwargs):
        self.resolved_numbers.append(whatsapp_number)
        from movia_sales_agent.chatwoot.client import ChatwootConversation

        return ChatwootConversation(account_id=2, conversation_id=66)

    def send_public_messages(self, conversation, messages):
        if self.fail_public:
            raise RuntimeError("chatwoot failed")
        messages = list(messages)
        if self.partial_public_failure:
            self.partial_attempted = True
            from movia_sales_agent.chatwoot.client import ChatwootSendError

            raise ChatwootSendError(
                "partial chatwoot failure",
                sent_count=1,
                original=RuntimeError("second part failed"),
            )
        self.public_messages.append(
            {"conversation_id": conversation.conversation_id, "messages": messages}
        )
        return {
            "transport": "chatwoot",
            "conversation_id": conversation.conversation_id,
            "count": len(messages),
        }

    def send_private_note(self, conversation, content):
        self.private_notes.append(
            {"conversation_id": conversation.conversation_id, "content": content}
        )
        return {"transport": "chatwoot_private_note"}


class FakeMetaConversions:
    def __init__(self):
        self.scheduled = []

    def schedule_response_events(self, *, response, latest_ctwa_clid=None, latest_referral=None):
        self.scheduled.append(
            {
                "response": response,
                "latest_ctwa_clid": latest_ctwa_clid,
                "latest_referral": latest_referral,
            }
        )
