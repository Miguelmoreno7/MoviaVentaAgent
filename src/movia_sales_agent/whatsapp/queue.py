from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.chatwoot.client import (
    ChatwootClient,
    ChatwootConversation,
    ChatwootSendError,
)
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.meta.conversions import MetaConversionsService
from movia_sales_agent.platform.observability import (
    PlatformObservabilityService,
    batch_input_json,
    extract_total_tokens,
    response_output_json,
)
from movia_sales_agent.whatsapp.client import WhatsAppClient, WhatsAppMessage
from movia_sales_agent.whatsapp.interactive_policy import (
    InteractivePacket,
    resolve_interactive_packet,
)


logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 60 * 60 * 24 * 7
LEAD_LOCK_TTL_SECONDS = 120
STALE_BUFFER_MIN_SECONDS = 30


@dataclass(frozen=True)
class QueuedWhatsAppMessage:
    message_id: str
    from_number: str
    text: str
    channel: str = "whatsapp"
    ctwa_clid: Optional[str] = None
    referral: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None
    interactive_button_id: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)

    @property
    def lead_key(self) -> str:
        digest = hashlib.sha256(f"{self.channel}:{self.from_number}".encode("utf-8")).hexdigest()
        return digest


class WhatsAppQueue(Protocol):
    durable: bool

    async def enqueue(self, message: QueuedWhatsAppMessage) -> str:
        ...

    async def next_lead(self, timeout_seconds: int = 1) -> Optional[QueuedWhatsAppMessage]:
        ...

    async def collect_batch(
        self, lead: QueuedWhatsAppMessage, *, batch_window_seconds: float
    ) -> List[QueuedWhatsAppMessage]:
        ...

    async def acquire_lead_lock(self, lead: QueuedWhatsAppMessage) -> bool:
        ...

    async def release_lead_lock(self, lead: QueuedWhatsAppMessage) -> None:
        ...

    async def reschedule(self, lead: QueuedWhatsAppMessage) -> None:
        ...


class InMemoryWhatsAppQueue:
    durable = False

    def __init__(self) -> None:
        self._dedupe: set[str] = set()
        self._buffers: Dict[str, List[QueuedWhatsAppMessage]] = {}
        self._scheduled: set[str] = set()
        self._locks: set[str] = set()
        self._lead_queue: asyncio.Queue[QueuedWhatsAppMessage] = asyncio.Queue()
        self._mutex = asyncio.Lock()

    async def enqueue(self, message: QueuedWhatsAppMessage) -> str:
        async with self._mutex:
            if message.message_id in self._dedupe:
                return "duplicate"
            self._dedupe.add(message.message_id)
            self._buffers.setdefault(message.lead_key, []).append(message)
            if message.lead_key not in self._scheduled:
                self._scheduled.add(message.lead_key)
                await self._lead_queue.put(message)
        return "queued"

    async def next_lead(self, timeout_seconds: int = 1) -> Optional[QueuedWhatsAppMessage]:
        try:
            return await asyncio.wait_for(self._lead_queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None

    async def collect_batch(
        self, lead: QueuedWhatsAppMessage, *, batch_window_seconds: float
    ) -> List[QueuedWhatsAppMessage]:
        async with self._mutex:
            messages = self._buffers.pop(lead.lead_key, [])
            self._scheduled.discard(lead.lead_key)
            batch, remaining = split_batch_by_window(
                messages,
                batch_window_seconds=batch_window_seconds,
            )
            if remaining:
                self._buffers[lead.lead_key] = remaining
                self._scheduled.add(lead.lead_key)
                await self._lead_queue.put(remaining[0])
            return batch

    async def acquire_lead_lock(self, lead: QueuedWhatsAppMessage) -> bool:
        async with self._mutex:
            if lead.lead_key in self._locks:
                return False
            self._locks.add(lead.lead_key)
            return True

    async def release_lead_lock(self, lead: QueuedWhatsAppMessage) -> None:
        async with self._mutex:
            self._locks.discard(lead.lead_key)

    async def reschedule(self, lead: QueuedWhatsAppMessage) -> None:
        async with self._mutex:
            if lead.lead_key not in self._scheduled:
                self._scheduled.add(lead.lead_key)
                await self._lead_queue.put(lead)


class RedisWhatsAppQueue:
    durable = True

    def __init__(self, redis_url: str, *, stale_buffer_after_seconds: float = STALE_BUFFER_MIN_SECONDS):
        import redis

        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._stream = "movia:whatsapp:lead_jobs"
        self._group = "movia-agent"
        self._consumer = f"worker-{int(time.time() * 1000)}"
        self._stale_buffer_after_seconds = max(
            STALE_BUFFER_MIN_SECONDS,
            float(stale_buffer_after_seconds or STALE_BUFFER_MIN_SECONDS),
        )
        try:
            self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, message: QueuedWhatsAppMessage) -> str:
        return await asyncio.to_thread(self._enqueue_sync, message)

    def _enqueue_sync(self, message: QueuedWhatsAppMessage) -> str:
        dedupe_key = f"movia:whatsapp:message:{message.message_id}"
        if not self._redis.set(dedupe_key, "1", nx=True, ex=DEDUP_TTL_SECONDS):
            return "duplicate"
        lead_payload = {
            "message_id": message.message_id,
            "from_number": message.from_number,
            "text": message.text,
            "channel": message.channel,
            "ctwa_clid": message.ctwa_clid,
            "referral": message.referral or {},
            "timestamp": message.timestamp,
            "interactive_button_id": message.interactive_button_id,
            "enqueued_at": message.enqueued_at,
        }
        self._redis.rpush(
            f"movia:whatsapp:lead:{message.lead_key}:messages",
            json.dumps(lead_payload, ensure_ascii=False),
        )
        scheduled_key = f"movia:whatsapp:lead:{message.lead_key}:scheduled"
        if self._redis.set(scheduled_key, "1", nx=True, ex=LEAD_LOCK_TTL_SECONDS):
            self._redis.xadd(
                self._stream,
                {
                    "lead_key": message.lead_key,
                    "from_number": message.from_number,
                    "channel": message.channel,
                },
            )
        return "queued"

    async def next_lead(self, timeout_seconds: int = 1) -> Optional[QueuedWhatsAppMessage]:
        return await asyncio.to_thread(self._next_lead_sync, timeout_seconds)

    def _next_lead_sync(self, timeout_seconds: int) -> Optional[QueuedWhatsAppMessage]:
        rows = self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=1,
            block=max(1, timeout_seconds * 1000),
        )
        if not rows:
            self._reschedule_stale_buffers_sync()
            return None
        _stream_name, entries = rows[0]
        entry_id, fields = entries[0]
        self._redis.xack(self._stream, self._group, entry_id)
        return QueuedWhatsAppMessage(
            message_id=f"lead-job:{entry_id}",
            from_number=fields["from_number"],
            text="",
            channel=fields.get("channel") or "whatsapp",
        )

    def _reschedule_stale_buffers_sync(self) -> None:
        now = time.time()
        pattern = "movia:whatsapp:lead:*:messages"
        try:
            keys = list(self._redis.scan_iter(match=pattern, count=25))
        except Exception as exc:
            logger.warning("Redis stale WhatsApp buffer scan failed: %s", exc)
            return
        for messages_key in keys:
            try:
                if self._redis.llen(messages_key) <= 0:
                    continue
                lead_key = messages_key.removeprefix("movia:whatsapp:lead:").removesuffix(
                    ":messages"
                )
                if self._redis.exists(f"movia:whatsapp:lead:{lead_key}:lock"):
                    continue
                first_row = self._redis.lindex(messages_key, 0)
                if not first_row:
                    continue
                payload = json.loads(first_row)
                enqueued_at = payload_enqueued_at(payload, default=now)
                if now - enqueued_at < self._stale_buffer_after_seconds:
                    continue
                self._redis.set(
                    f"movia:whatsapp:lead:{lead_key}:scheduled",
                    "1",
                    ex=LEAD_LOCK_TTL_SECONDS,
                )
                self._redis.xadd(
                    self._stream,
                    {
                        "lead_key": lead_key,
                        "from_number": payload["from_number"],
                        "channel": payload.get("channel") or "whatsapp",
                    },
                )
                logger.warning(
                    "Rescheduled stale WhatsApp buffer for lead_key=%s age_seconds=%.1f",
                    lead_key,
                    now - enqueued_at,
                )
            except Exception as exc:
                logger.warning("Redis stale WhatsApp buffer recovery failed for %s: %s", messages_key, exc)

    async def collect_batch(
        self, lead: QueuedWhatsAppMessage, *, batch_window_seconds: float
    ) -> List[QueuedWhatsAppMessage]:
        return await asyncio.to_thread(
            self._collect_batch_sync,
            lead,
            batch_window_seconds,
        )

    def _collect_batch_sync(
        self, lead: QueuedWhatsAppMessage, batch_window_seconds: float
    ) -> List[QueuedWhatsAppMessage]:
        messages_key = f"movia:whatsapp:lead:{lead.lead_key}:messages"
        rows = self._redis.lrange(messages_key, 0, -1)
        self._redis.delete(messages_key)
        self._redis.delete(f"movia:whatsapp:lead:{lead.lead_key}:scheduled")
        messages = []
        for row in rows:
            payload = json.loads(row)
            messages.append(
                QueuedWhatsAppMessage(
                    message_id=payload["message_id"],
                    from_number=payload["from_number"],
                    text=payload["text"],
                    channel=payload.get("channel") or "whatsapp",
                    ctwa_clid=payload.get("ctwa_clid"),
                    referral=payload.get("referral") or {},
                    timestamp=payload.get("timestamp"),
                    interactive_button_id=payload.get("interactive_button_id"),
                    enqueued_at=payload_enqueued_at(payload, default=time.time()),
                )
            )
        batch, remaining = split_batch_by_window(
            messages,
            batch_window_seconds=batch_window_seconds,
        )
        if remaining:
            pipe = self._redis.pipeline()
            for message in remaining:
                pipe.rpush(
                    messages_key,
                    json.dumps(
                        {
                            "message_id": message.message_id,
                            "from_number": message.from_number,
                            "text": message.text,
                            "channel": message.channel,
                            "ctwa_clid": message.ctwa_clid,
                            "referral": message.referral or {},
                            "timestamp": message.timestamp,
                            "interactive_button_id": message.interactive_button_id,
                            "enqueued_at": message.enqueued_at,
                        },
                        ensure_ascii=False,
                    ),
                )
            pipe.set(
                f"movia:whatsapp:lead:{lead.lead_key}:scheduled",
                "1",
                ex=LEAD_LOCK_TTL_SECONDS,
            )
            pipe.xadd(
                self._stream,
                {
                    "lead_key": lead.lead_key,
                    "from_number": remaining[0].from_number,
                    "channel": remaining[0].channel,
                },
            )
            pipe.execute()
        return batch

    async def acquire_lead_lock(self, lead: QueuedWhatsAppMessage) -> bool:
        return await asyncio.to_thread(
            self._redis.set,
            f"movia:whatsapp:lead:{lead.lead_key}:lock",
            "1",
            nx=True,
            ex=LEAD_LOCK_TTL_SECONDS,
        )

    async def release_lead_lock(self, lead: QueuedWhatsAppMessage) -> None:
        await asyncio.to_thread(self._redis.delete, f"movia:whatsapp:lead:{lead.lead_key}:lock")

    async def reschedule(self, lead: QueuedWhatsAppMessage) -> None:
        await asyncio.to_thread(
            self._redis.xadd,
            self._stream,
            {
                "lead_key": lead.lead_key,
                "from_number": lead.from_number,
                "channel": lead.channel,
            },
        )


class WhatsAppWorkerManager:
    def __init__(
        self,
        *,
        settings: Settings,
        agent: MoviaSalesAgent,
        client: WhatsAppClient,
        queue: Optional[WhatsAppQueue] = None,
        observability: Optional[PlatformObservabilityService] = None,
        chatwoot_client: Optional[ChatwootClient] = None,
        meta_conversions: Optional[MetaConversionsService] = None,
    ) -> None:
        self.settings = settings
        self.agent = agent
        self.client = client
        self.queue = queue or build_queue(settings)
        self.chatwoot_client = chatwoot_client or ChatwootClient(
            settings,
            repository=getattr(agent, "repository", None),
        )
        self.observability = observability or PlatformObservabilityService.from_settings(
            settings,
            memory=getattr(agent, "memory", None),
        )
        self.meta_conversions = meta_conversions or MetaConversionsService(
            settings=settings,
            repository=getattr(agent, "repository", None),
        )
        self._tasks: List[asyncio.Task] = []
        self._stopping = asyncio.Event()
        self._interactive_packet_counts: Dict[str, int] = {}

    @property
    def durable(self) -> bool:
        return self.queue.durable

    async def start(self) -> None:
        if self._tasks:
            await self.ensure_running()
            return
        self._stopping.clear()
        self._tasks = []
        self._spawn_missing_worker_tasks()

    async def stop(self) -> None:
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def ensure_running(self) -> None:
        if self._stopping.is_set():
            return
        alive_tasks = []
        for task in self._tasks:
            if task.done():
                try:
                    exc = task.exception()
                except asyncio.CancelledError:
                    exc = None
                if exc:
                    logger.error("WhatsApp worker task exited unexpectedly: %s", exc)
            else:
                alive_tasks.append(task)
        self._tasks = alive_tasks
        self._spawn_missing_worker_tasks()

    def worker_status(self) -> Dict[str, Any]:
        desired = self._desired_concurrency()
        alive = sum(1 for task in self._tasks if not task.done())
        done = sum(1 for task in self._tasks if task.done())
        return {
            "desired_concurrency": desired,
            "task_count": len(self._tasks),
            "alive_task_count": alive,
            "done_task_count": done,
            "running": alive >= desired,
            "durable": self.durable,
        }

    def _desired_concurrency(self) -> int:
        return max(1, int(self.settings.job_concurrency or 1))

    def _spawn_missing_worker_tasks(self) -> None:
        desired = self._desired_concurrency()
        missing = max(0, desired - len(self._tasks))
        if missing <= 0:
            return
        start_index = len(self._tasks)
        for offset in range(missing):
            index = start_index + offset
            self._tasks.append(
                asyncio.create_task(
                    self._worker_loop(index),
                    name=f"movia-whatsapp-worker-{index}",
                )
            )

    async def enqueue(self, message: WhatsAppMessage) -> str:
        await self.ensure_running()
        queued = QueuedWhatsAppMessage(
            message_id=message.message_id,
            from_number=message.from_number,
            text=message.text,
            ctwa_clid=message.ctwa_clid,
            referral=message.referral,
            timestamp=message.timestamp,
            interactive_button_id=message.interactive_button_id,
        )
        return await self.queue.enqueue(queued)

    async def _worker_loop(self, index: int) -> None:
        while not self._stopping.is_set():
            lead = await self.queue.next_lead(timeout_seconds=1)
            if lead is None:
                continue
            acquired = await self.queue.acquire_lead_lock(lead)
            if not acquired:
                await asyncio.sleep(0.5)
                await self.queue.reschedule(lead)
                continue
            try:
                self._record_queue_event(
                    "batch_window_started",
                    "Batch window started for WhatsApp lead.",
                    {"from_number": lead.from_number, "channel": lead.channel},
                )
                await asyncio.sleep(max(0.0, float(self.settings.lead_batch_window_seconds or 0.0)))
                batch = await self.queue.collect_batch(
                    lead,
                    batch_window_seconds=float(self.settings.lead_batch_window_seconds or 0.0),
                )
                if not batch:
                    continue
                await asyncio.to_thread(self._process_batch_sync, batch)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WhatsApp worker %s failed to process lead batch", index)
            finally:
                await self.queue.release_lead_lock(lead)

    def _process_batch_sync(self, batch: List[QueuedWhatsAppMessage]) -> None:
        first = batch[0]
        combined_text = combine_messages(batch)
        external_message_id = batch[0].message_id if len(batch) == 1 else "batch:" + batch[0].message_id
        input_json = batch_input_json(
            from_number=first.from_number,
            channel=first.channel,
            message_ids=[message.message_id for message in batch],
            batch_count=len(batch),
        )
        runtime = None
        run_id = None
        if self.observability:
            runtime, warning = self.observability.resolve_runtime()
            if warning and not runtime:
                logger.warning("Skipping agent run because platform runtime could not be resolved")
                return
            if runtime:
                run_id = self._safe_start_run(
                    runtime=runtime,
                    status="running" if runtime.enabled else "cancelled",
                    input_json=input_json,
                    requested_by=first.from_number,
                )
                self._add_run_event(
                    run_id,
                    "info",
                    "webhook_received",
                    "Webhook messages received by queue.",
                    {"message_ids": input_json["message_ids"]},
                )
                self._add_run_event(
                    run_id,
                    "info",
                    "message_queued",
                    "Messages queued for background processing.",
                    {"batch_count": len(batch)},
                )
                self._add_run_event(
                    run_id,
                    "info",
                    "batch_window_started",
                    "Batch window completed for WhatsApp lead.",
                    {
                        "batch_window_seconds": self.settings.lead_batch_window_seconds,
                        "batch_count": len(batch),
                    },
                )
                self._add_run_event(
                    run_id,
                    "info",
                    "platform_runtime_resolved",
                    "Platform runtime resolved.",
                    {
                        "agent_key": runtime.agent_key,
                        "version": runtime.version,
                        "enabled": runtime.enabled,
                    },
                )
                if not runtime.enabled:
                    self._add_run_event(
                        run_id,
                        "info",
                        "platform_disabled_skip",
                        "Agent execution skipped because platform disabled this agent.",
                        input_json,
                    )
                    return

        self._add_run_event(
            run_id,
            "info",
            "batch_compacted",
            "WhatsApp messages compacted into one agent input.",
            {"batch_count": len(batch), "message_ids": input_json["message_ids"]},
        )
        started_at = time.time()
        try:
            typing_result = self.client.mark_messages_read_with_typing(input_json["message_ids"])
            logger.info("whatsapp_typing_indicator_sent result=%s", typing_result)
            self._add_run_event(
                run_id,
                "info",
                "agent_started",
                "Agent execution started.",
                {"typing_indicator": typing_result},
            )
            response = self.agent.invoke(
                message=combined_text,
                lead_external_id=first.from_number,
                channel=first.channel,
                external_message_id=external_message_id,
            )
            logger.info(
                "movia_agent_turn_diagnostics=%s",
                json.dumps(
                    turn_diagnostics_payload(
                        run_id=run_id,
                        input_json=input_json,
                        response=response,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )
            self._add_run_event(
                run_id,
                "info",
                "agent_completed",
                "Agent execution completed.",
                {"action": response.action, "message_count": len(response.response_messages)},
            )
            self._add_run_event(run_id, "info", "whatsapp_send_started", "Outbound send started.", {})
            send_result = self._send_agent_response(
                first.from_number,
                response,
                batch=batch,
                force_entry_intent_buttons=should_send_campaign_entry_intent_buttons(
                    response,
                    batch,
                ),
            )
            self._schedule_meta_conversions(response, batch)
            self._add_run_event(
                run_id,
                "info",
                "whatsapp_send_completed",
                "Outbound send completed.",
                {
                    "message_count": len(response.response_messages),
                    "transport": send_result.get("transport"),
                    "fallback_used": send_result.get("fallback_used", False),
                },
            )
            duration_ms = int((time.time() - started_at) * 1000)
            output_json = response_output_json(response, debug_metadata=self.settings.debug_metadata)
            total_tokens = extract_total_tokens(response.token_usage)
            if self.observability:
                self._safe_update_run(
                    run_id=run_id,
                    status="success",
                    output_json=output_json,
                    total_tokens=total_tokens,
                    total_duration_ms=duration_ms,
                )
                self.observability.add_event_async(
                    run_id=run_id,
                    level="info",
                    event_type="run_completed",
                    message="Run completed successfully.",
                    payload_json={"duration_ms": duration_ms, "total_tokens": total_tokens},
                )
        except Exception as exc:
            duration_ms = int((time.time() - started_at) * 1000)
            if self.observability:
                self._safe_update_run(
                    run_id=run_id,
                    status="failed",
                    output_json=None,
                    total_duration_ms=duration_ms,
                    error_text=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
                self.observability.add_event_async(
                    run_id=run_id,
                    level="error",
                    event_type="run_failed",
                    message="Run failed.",
                    payload_json={"error": f"{type(exc).__name__}: {str(exc)[:500]}"},
                )
            raise

    def _schedule_meta_conversions(self, response: Any, batch: List[QueuedWhatsAppMessage]) -> None:
        if not self.meta_conversions:
            return
        latest = next((message for message in batch if message.ctwa_clid), None)
        try:
            self.meta_conversions.schedule_response_events(
                response=response,
                latest_ctwa_clid=latest.ctwa_clid if latest else None,
                latest_referral=latest.referral if latest else {},
            )
        except Exception as exc:
            logger.warning("Meta conversion scheduling failed: %s", exc)

    def _send_agent_response(
        self,
        to_number: str,
        response: Any,
        *,
        batch: Optional[List[QueuedWhatsAppMessage]] = None,
        force_entry_intent_buttons: bool = False,
    ) -> Dict[str, Any]:
        if force_entry_intent_buttons or should_send_entry_intent_buttons(response):
            self._interactive_packet_counts[to_number] = (
                self._interactive_packet_counts.get(to_number, 0) + 1
            )
            return self._send_entry_intent_buttons(to_number, response)
        packet = resolve_interactive_packet(
            response=response,
            batch=batch or [],
            sent_count=self._interactive_packet_counts.get(to_number, 0),
        )
        if packet:
            self._interactive_packet_counts[to_number] = (
                self._interactive_packet_counts.get(to_number, 0) + 1
            )
            return self._send_interactive_packet(to_number, response, packet)
        messages = list(response.response_messages or []) or [response.response]
        conversation: Optional[ChatwootConversation] = None
        if self.chatwoot_client.enabled:
            try:
                conversation = self.chatwoot_client.resolve_conversation_for_lead(
                    lead_id=getattr(response, "lead_id", None),
                    whatsapp_number=to_number,
                )
                if conversation:
                    result = self.chatwoot_client.send_public_messages(conversation, messages)
                    return {**result, "fallback_used": False}
                logger.warning("Chatwoot conversation not found; falling back to WhatsApp API")
            except ChatwootSendError as exc:
                if exc.sent_count > 0:
                    logger.warning(
                        "Chatwoot public outbound failed after %s accepted messages; "
                        "not falling back to WhatsApp to avoid duplicates: %s",
                        exc.sent_count,
                        exc.original,
                    )
                    return {
                        "transport": "chatwoot_partial",
                        "fallback_used": False,
                        "chatwoot_sent_count": exc.sent_count,
                        "error": str(exc.original),
                    }
                logger.warning(
                    "Chatwoot public outbound failed before any message was accepted; "
                    "falling back to WhatsApp API: %s",
                    exc.original,
                )
            except Exception as exc:
                logger.warning("Chatwoot public outbound failed; falling back to WhatsApp API: %s", exc)

        whatsapp_result = self.client.send_text(to_number, response.response)
        fallback_result: Dict[str, Any] = {
            "transport": "whatsapp",
            "fallback_used": bool(self.chatwoot_client.enabled),
            "whatsapp_result": whatsapp_result,
        }
        if conversation:
            note = (
                "MovIA fallback sent this response directly through WhatsApp API after "
                "Chatwoot public outbound failed:\n\n"
                f"{response.response}"
            )
            try:
                fallback_result["chatwoot_private_note"] = self.chatwoot_client.send_private_note(
                    conversation,
                    note,
                )
            except Exception as exc:
                logger.warning("Chatwoot fallback private note failed: %s", exc)
                fallback_result["chatwoot_private_note_error"] = str(exc)
        return fallback_result

    def _send_interactive_packet(
        self,
        to_number: str,
        response: Any,
        packet: InteractivePacket,
    ) -> Dict[str, Any]:
        result = self.client.send_interactive_reply_buttons(
            to_number,
            body=packet.body,
            buttons=packet.buttons,
        )
        send_result: Dict[str, Any] = {
            "transport": "whatsapp_interactive_buttons",
            "fallback_used": False,
            "interactive_packet_key": packet.key,
            "whatsapp_result": result,
        }
        if self.chatwoot_client.enabled:
            try:
                conversation = self.chatwoot_client.resolve_conversation_for_lead(
                    lead_id=getattr(response, "lead_id", None),
                    whatsapp_number=to_number,
                    attempts=1,
                    retry_delays=(0.0,),
                )
                if conversation:
                    send_result["chatwoot_private_note"] = self.chatwoot_client.send_private_note(
                        conversation,
                        (
                            "MovIA sent an early-funnel interactive button message directly "
                            "through WhatsApp Cloud API:\n\n"
                            f"{packet.body}"
                        ),
                    )
            except Exception as exc:
                logger.warning("Chatwoot interactive packet private note failed: %s", exc)
                send_result["chatwoot_private_note_error"] = str(exc)
        return send_result

    def _send_entry_intent_buttons(self, to_number: str, response: Any) -> Dict[str, Any]:
        result = self.client.send_entry_intent_buttons(to_number)
        send_result: Dict[str, Any] = {
            "transport": "whatsapp_interactive_buttons",
            "fallback_used": False,
            "whatsapp_result": result,
        }
        if self.chatwoot_client.enabled:
            try:
                conversation = self.chatwoot_client.resolve_conversation_for_lead(
                    lead_id=getattr(response, "lead_id", None),
                    whatsapp_number=to_number,
                    attempts=1,
                    retry_delays=(0.0,),
                )
                if conversation:
                    send_result["chatwoot_private_note"] = self.chatwoot_client.send_private_note(
                        conversation,
                        (
                            "MovIA sent the first-touch interactive button message directly "
                            "through WhatsApp Cloud API:\n\n"
                            f"{response.response}"
                        ),
                    )
            except Exception as exc:
                logger.warning("Chatwoot interactive button private note failed: %s", exc)
                send_result["chatwoot_private_note_error"] = str(exc)
        return send_result

    def _record_queue_event(self, event_type: str, message: str, payload: Dict[str, Any]) -> None:
        logger.info("%s: %s %s", event_type, message, payload)

    def _safe_start_run(
        self,
        *,
        runtime: Any,
        status: str,
        input_json: Dict[str, Any],
        requested_by: str,
    ) -> Optional[str]:
        if not self.observability:
            return None
        try:
            return self.observability.start_run_async(
                runtime=runtime,
                status=status,
                input_json=input_json,
                requested_by=requested_by,
            )
        except Exception as exc:
            logger.warning("Platform start_run failed: %s", exc)
            return None

    def _safe_update_run(
        self,
        *,
        run_id: Optional[str],
        status: str,
        output_json: Optional[Dict[str, Any]],
        total_tokens: Optional[int] = None,
        total_duration_ms: Optional[int] = None,
        error_text: Optional[str] = None,
    ) -> None:
        if not self.observability:
            return
        try:
            self.observability.update_run_async(
                run_id=run_id,
                status=status,
                output_json=output_json,
                total_tokens=total_tokens,
                total_duration_ms=total_duration_ms,
                error_text=error_text,
            )
        except Exception as exc:
            logger.warning("Platform update_run failed: %s", exc)

    def _add_run_event(
        self,
        run_id: Optional[str],
        level: str,
        event_type: str,
        message: str,
        payload_json: Dict[str, Any],
    ) -> None:
        if self.observability:
            try:
                self.observability.add_event_async(
                    run_id=run_id,
                    level=level,
                    event_type=event_type,
                    message=message,
                    payload_json=payload_json,
                )
            except Exception as exc:
                logger.warning("Platform add_event failed: %s", exc)


def build_queue(settings: Settings) -> WhatsAppQueue:
    if settings.webhook_queue_enabled and settings.redis_url:
        try:
            return RedisWhatsAppQueue(
                settings.redis_url,
                stale_buffer_after_seconds=float(settings.lead_batch_window_seconds or 0.0) + 10.0,
            )
        except Exception as exc:
            logger.warning("Redis WhatsApp queue unavailable; falling back to in-memory queue: %s", exc)
    return InMemoryWhatsAppQueue()


def combine_messages(messages: List[QueuedWhatsAppMessage]) -> str:
    if len(messages) == 1:
        return messages[0].text
    lines = []
    for index, message in enumerate(messages, start=1):
        lines.append(f"Mensaje {index}: {message.text}")
    return "\n".join(lines)


def split_batch_by_window(
    messages: List[QueuedWhatsAppMessage], *, batch_window_seconds: float
) -> tuple[List[QueuedWhatsAppMessage], List[QueuedWhatsAppMessage]]:
    if not messages:
        return [], []
    ordered = sorted(messages, key=lambda message: message.enqueued_at)
    first_enqueued_at = ordered[0].enqueued_at
    cutoff = first_enqueued_at + max(0.0, float(batch_window_seconds or 0.0)) + 0.25
    batch = [message for message in ordered if message.enqueued_at <= cutoff]
    remaining = [message for message in ordered if message.enqueued_at > cutoff]
    return batch, remaining


def payload_enqueued_at(payload: Dict[str, Any], *, default: float) -> float:
    for key in ("enqueued_at", "timestamp"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def should_send_entry_intent_buttons(response: Any) -> bool:
    selected_action = getattr(response, "selected_action", None) or {}
    return selected_action.get("next_question_key") == "entry_intent"


def should_send_campaign_entry_intent_buttons(
    response: Any,
    batch: List[QueuedWhatsAppMessage],
) -> bool:
    if not any(message.ctwa_clid for message in batch):
        return False
    if should_send_entry_intent_buttons(response):
        return True

    selected_action = getattr(response, "selected_action", None) or {}
    macro_action = str(selected_action.get("macro_action") or getattr(response, "action", "") or "")
    micro_action = str(selected_action.get("micro_action") or "")
    next_question_key = selected_action.get("next_question_key")

    if macro_action == "answer_unknown_safely":
        return True
    if macro_action != "answer_and_advance":
        return False
    if next_question_key == "entry_intent":
        return True

    specific_answer_micro_actions = {
        "answer_price_then_explain_scope",
        "answer_scope_then_discover_business",
        "answer_channel_then_discover_main_channel",
        "answer_process_then_explain_next_step",
        "answer_policy_then_reduce_risk",
    }
    if micro_action in specific_answer_micro_actions:
        return False

    commercial_specific_keys = {
        "objection_clarification",
        "answer_or_actions",
        "guide_app_options",
    }
    if next_question_key in commercial_specific_keys:
        return False

    return micro_action in {"", "answer_general_then_discover_need"} or next_question_key in {
        None,
        "business_type",
        "automation_need",
        "action_requirement",
    }


def turn_diagnostics_payload(
    *,
    run_id: Optional[str],
    input_json: Dict[str, Any],
    response: Any,
) -> Dict[str, Any]:
    analysis = _model_dump(getattr(response, "analysis", None))
    response_metadata = getattr(response, "response_metadata", None) or {}
    normalized_turn = response_metadata.get("normalized_turn") or {}
    analyzer_observation = response_metadata.get("analyzer_observation") or {}
    selected_action = getattr(response, "selected_action", None) or {}
    product_context = normalized_turn.get("product_context") or {}
    return {
        "run_id": run_id,
        "lead_id": getattr(response, "lead_id", None),
        "message_ids": input_json.get("message_ids") or [],
        "batch_count": input_json.get("batch_count"),
        "analysis": {
            "primary_intent": analysis.get("primary_intent"),
            "secondary_intents": analysis.get("secondary_intents") or [],
            "topics": analysis.get("topics") or [],
            "has_objection": analysis.get("has_objection"),
            "objection_type": analysis.get("objection_type"),
            "objection_strength": analysis.get("objection_strength"),
            "objection_relation": analysis.get("objection_relation"),
            "skeptical_tone": analysis.get("skeptical_tone"),
            "buying_signal": analysis.get("buying_signal"),
            "explicit_start_intent": analysis.get("explicit_start_intent"),
            "is_post_purchase": analysis.get("is_post_purchase"),
            "references_prior_message": analysis.get("references_prior_message"),
            "confidence": analysis.get("confidence") or {},
        },
        "analyzer_observation": {
            "objection_candidate": analyzer_observation.get("objection_candidate"),
            "requested_product": analyzer_observation.get("requested_product"),
            "purchase_readiness": analyzer_observation.get("purchase_readiness"),
            "observed_business_problems": analyzer_observation.get("observed_business_problems")
            or [],
            "requested_agent_capabilities": analyzer_observation.get(
                "requested_agent_capabilities"
            )
            or [],
            "requested_agent_actions": analyzer_observation.get("requested_agent_actions")
            or [],
        },
        "normalized_turn": {
            "normalized_objection": normalized_turn.get("normalized_objection"),
            "requested_product": normalized_turn.get("requested_product"),
            "requirement_class": normalized_turn.get("requirement_class"),
            "action_requirement": normalized_turn.get("action_requirement"),
            "active_product_context": normalized_turn.get("active_product_context")
            or product_context.get("active_product_context"),
            "selected_product": normalized_turn.get("selected_product")
            or product_context.get("selected_product"),
            "confirmed_product": normalized_turn.get("confirmed_product")
            or product_context.get("confirmed_product"),
            "scope_flags": normalized_turn.get("scope_flags") or [],
        },
        "selected_action": {
            "macro_action": selected_action.get("macro_action")
            or getattr(response, "action", None),
            "micro_action": selected_action.get("micro_action"),
            "reason_code": selected_action.get("reason_code"),
            "target_stage": selected_action.get("target_stage"),
            "cta_type": selected_action.get("cta_type"),
            "next_question_key": selected_action.get("next_question_key"),
            "objection_flow_step": selected_action.get("objection_flow_step"),
            "objection_overlay": selected_action.get("objection_overlay"),
        },
    }


def _model_dump(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}
