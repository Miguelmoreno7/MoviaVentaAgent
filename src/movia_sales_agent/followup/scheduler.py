from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from movia_sales_agent.chatwoot.client import (
    ChatwootClient,
    ChatwootConversation,
    ChatwootSendError,
)
from movia_sales_agent.config.settings import Settings
from movia_sales_agent.db.repository import MoviaRepository
from movia_sales_agent.platform.observability import PlatformObservabilityService
from movia_sales_agent.whatsapp.client import WhatsAppClient


logger = logging.getLogger(__name__)

CLOSE_OR_LINK_ACTIONS = {"direct_close", "soft_close"}
PRODUCT_LABELS = {
    "movia_captura": "MovIA Captura",
    "movia_hibrido": "MovIA Híbrido",
}


class FollowUpScheduler:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: MoviaRepository,
        whatsapp_client: WhatsAppClient,
        chatwoot_client: Optional[ChatwootClient] = None,
        observability: Optional[PlatformObservabilityService] = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.whatsapp_client = whatsapp_client
        self.chatwoot_client = chatwoot_client or ChatwootClient(settings, repository=repository)
        self.observability = observability
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    @property
    def running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        if self._task or not self.settings.followup_enabled:
            return
        if not self.repository.enabled:
            logger.warning("Follow-up scheduler disabled: database is not configured")
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="movia-followup-scheduler")

    async def stop(self) -> None:
        self._stopping.set()
        if not self._task:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self) -> None:
        interval = max(10.0, float(self.settings.followup_scan_interval_seconds or 300.0))
        while not self._stopping.is_set():
            try:
                await asyncio.to_thread(self.scan_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Follow-up scheduler scan failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def scan_once(self) -> int:
        if not self.settings.followup_enabled or not self.repository.enabled:
            return 0
        if not self._platform_allows_followups():
            logger.info("followup_skipped_platform_disabled")
            return 0
        logger.info("followup_scan_started")
        candidates = self.repository.find_followup_candidates(
            delay_hours=self.settings.followup_delay_hours,
            window_safety_minutes=self.settings.followup_window_safety_minutes,
            max_attempts=self.settings.followup_max_attempts,
        )
        sent = 0
        for candidate in candidates:
            if self._process_candidate(candidate):
                sent += 1
        return sent

    def _platform_allows_followups(self) -> bool:
        if not self.observability:
            return True
        runtime, warning = self.observability.resolve_runtime()
        if warning and not runtime:
            logger.warning("followup_platform_runtime_unavailable warning=%s", warning)
            return False
        if runtime and not runtime.enabled:
            return False
        return True

    def _process_candidate(self, candidate: Dict[str, Any]) -> bool:
        message_text = build_followup_message(candidate)
        attempt = self.repository.claim_followup_attempt(
            lead_id=str(candidate["lead_id"]),
            trigger_user_message_id=str(candidate["trigger_user_message_id"]),
            message_text=message_text,
            max_attempts=self.settings.followup_max_attempts,
        )
        if not attempt:
            return False
        attempt_id = str(attempt["id"])
        logger.info(
            "followup_candidate_claimed lead_id=%s attempt_id=%s",
            candidate["lead_id"],
            attempt_id,
        )
        if not self.repository.is_followup_still_valid(
            lead_id=str(candidate["lead_id"]),
            trigger_user_message_id=str(candidate["trigger_user_message_id"]),
            delay_hours=self.settings.followup_delay_hours,
            window_safety_minutes=self.settings.followup_window_safety_minutes,
        ):
            self.repository.mark_followup_skipped(
                attempt_id=attempt_id,
                reason="followup_skipped_window_expired_or_answered",
            )
            logger.info("followup_skipped_window_expired lead_id=%s", candidate["lead_id"])
            return False
        try:
            send_result = self._send_followup(candidate, message_text)
            self.repository.save_message(
                str(candidate["lead_id"]),
                "assistant",
                message_text,
                external_message_id=f"followup:{attempt_id}",
                retrieval_metadata={
                    "response_metadata": {
                        "response_source": "followup_scheduler",
                        "action": "followup_nudge",
                    },
                    "followup": {
                        "attempt_id": attempt_id,
                        "trigger_user_message_id": str(candidate["trigger_user_message_id"]),
                    },
                },
            )
            self.repository.mark_followup_sent(attempt_id=attempt_id, send_result=send_result)
            logger.info("followup_sent lead_id=%s attempt_id=%s", candidate["lead_id"], attempt_id)
            return True
        except Exception as exc:
            self.repository.mark_followup_failed(
                attempt_id=attempt_id,
                error_text=f"{type(exc).__name__}: {str(exc)[:500]}",
            )
            logger.warning("followup_failed lead_id=%s error=%s", candidate["lead_id"], exc)
            return False

    def _send_followup(self, candidate: Dict[str, Any], message_text: str) -> Dict[str, Any]:
        conversation: Optional[ChatwootConversation] = None
        to_number = str(candidate["external_user_id"])
        if self.chatwoot_client.enabled:
            try:
                conversation = self.chatwoot_client.resolve_conversation_for_lead(
                    lead_id=str(candidate["lead_id"]),
                    whatsapp_number=to_number,
                )
                if conversation:
                    result = self.chatwoot_client.send_public_messages(conversation, [message_text])
                    return {**result, "fallback_used": False}
                logger.warning("Chatwoot conversation not found for follow-up; falling back to WhatsApp")
            except ChatwootSendError as exc:
                if exc.sent_count > 0:
                    logger.warning(
                        "Chatwoot follow-up failed after %s accepted messages; avoiding WhatsApp fallback: %s",
                        exc.sent_count,
                        exc.original,
                    )
                    return {
                        "transport": "chatwoot_partial",
                        "fallback_used": False,
                        "chatwoot_sent_count": exc.sent_count,
                        "error": str(exc.original),
                    }
                logger.warning("Chatwoot follow-up failed before send; falling back: %s", exc.original)
            except Exception as exc:
                logger.warning("Chatwoot follow-up failed; falling back to WhatsApp: %s", exc)

        whatsapp_result = self.whatsapp_client.send_text(to_number, message_text)
        result: Dict[str, Any] = {
            "transport": "whatsapp",
            "fallback_used": bool(self.chatwoot_client.enabled),
            "whatsapp_result": whatsapp_result,
        }
        if conversation:
            try:
                result["chatwoot_private_note"] = self.chatwoot_client.send_private_note(
                    conversation,
                    (
                        "MovIA fallback sent this follow-up directly through WhatsApp API after "
                        "Chatwoot public outbound failed:\n\n"
                        f"{message_text}"
                    ),
                )
            except Exception as exc:
                logger.warning("Chatwoot follow-up fallback private note failed: %s", exc)
                result["chatwoot_private_note_error"] = str(exc)
        return result


def build_followup_message(candidate: Dict[str, Any]) -> str:
    product = product_label(candidate)
    close_or_link = str(candidate.get("last_action") or "") in CLOSE_OR_LINK_ACTIONS
    if close_or_link and product:
        return (
            f"Te doy seguimiento por aquí sobre {product}.\n\n"
            "¿Pudiste abrir el link o quieres que te guíe con la opción correcta para empezar?"
        )
    if close_or_link:
        return (
            "Te doy seguimiento por aquí.\n\n"
            "¿Pudiste abrir el link o quieres que te guíe con la opción correcta para empezar?"
        )
    if product:
        return (
            f"Te doy seguimiento por aquí sobre {product}.\n\n"
            "¿Quieres que retomemos la cotización o prefieres que te ayude a confirmar si es la opción correcta para tu negocio?"
        )
    return (
        "Te doy seguimiento por aquí.\n\n"
        "¿Quieres que retomemos la cotización o prefieres que te ayude a elegir la opción correcta para tu negocio?"
    )


def product_label(candidate: Dict[str, Any]) -> Optional[str]:
    profile_data = candidate.get("profile_data") if isinstance(candidate.get("profile_data"), dict) else {}
    product_context = (
        profile_data.get("product_context") if isinstance(profile_data.get("product_context"), dict) else {}
    )
    product = (
        product_context.get("confirmed_product")
        or product_context.get("selected_product")
        or product_context.get("active_product_context")
        or profile_data.get("confirmed_product")
        or profile_data.get("selected_product")
    )
    return PRODUCT_LABELS.get(str(product or ""))
