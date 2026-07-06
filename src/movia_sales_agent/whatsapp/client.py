from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

import httpx

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.whatsapp.formatting import split_whatsapp_messages


logger = logging.getLogger(__name__)

ENTRY_INTENT_BUTTONS = [
    {"id": "entry_prices", "title": "Ver precios", "text": "Quiero ver precios"},
    {"id": "entry_choose_agent", "title": "Elegir agente", "text": "Ayúdame a elegir agente"},
    {"id": "entry_how_it_works", "title": "Cómo funciona", "text": "Quiero saber cómo funciona"},
]
ENTRY_INTENT_BODY = (
    "Hola! Soy el asistente de MovIA.\n\n"
    "Te ayudo a revisar si MovIA Captura o MovIA Híbrido tienen sentido para tu negocio.\n\n"
    "¿Qué te gustaría revisar primero?"
)
INTERACTIVE_REPLY_TEXT_BY_ID = {
    button["id"]: button["text"]
    for button in ENTRY_INTENT_BUTTONS
}


class WhatsAppMessage:
    def __init__(
        self,
        message_id: str,
        from_number: str,
        text: str,
        *,
        ctwa_clid: Optional[str] = None,
        referral: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ):
        self.message_id = message_id
        self.from_number = from_number
        self.text = text
        self.ctwa_clid = ctwa_clid
        self.referral = referral or {}
        self.timestamp = timestamp


class WhatsAppClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.whatsapp_enabled

    def parse_messages(self, payload: Any) -> List[WhatsAppMessage]:
        messages: List[WhatsAppMessage] = []
        for body in self._candidate_bodies(payload):
            messages.extend(self._parse_direct_messages(body))
            messages.extend(self._parse_meta_entry_messages(body))
        return messages

    def _candidate_bodies(self, payload: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    body = item.get("body")
                    if isinstance(body, dict):
                        yield body
                    yield item
            return
        if isinstance(payload, dict):
            body = payload.get("body")
            if isinstance(body, dict):
                yield body
            yield payload

    def _parse_direct_messages(self, body: Dict[str, Any]) -> List[WhatsAppMessage]:
        messages: List[WhatsAppMessage] = []
        for message in body.get("messages", []):
            parsed = self._parse_text_message(message, fallback_referral=body.get("referral"))
            if parsed:
                messages.append(parsed)
        return messages

    def _parse_meta_entry_messages(self, body: Dict[str, Any]) -> List[WhatsAppMessage]:
        messages: List[WhatsAppMessage] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    parsed = self._parse_text_message(message, fallback_referral=value.get("referral"))
                    if parsed:
                        messages.append(parsed)
        return messages

    def _parse_text_message(
        self,
        message: Any,
        *,
        fallback_referral: Any = None,
    ) -> WhatsAppMessage | None:
        if not isinstance(message, dict) or message.get("type") != "text":
            return self._parse_interactive_reply(message, fallback_referral=fallback_referral)
        text_payload = message.get("text") or {}
        text = text_payload.get("body") if isinstance(text_payload, dict) else None
        from_number = message.get("from")
        message_id = message.get("id")
        referral = compact_referral(message.get("referral") or fallback_referral)
        ctwa_clid = extract_ctwa_clid(message, referral)
        if text and from_number and message_id:
            return WhatsAppMessage(
                str(message_id),
                str(from_number),
                str(text),
                ctwa_clid=ctwa_clid,
                referral=referral,
                timestamp=str(message.get("timestamp")) if message.get("timestamp") else None,
            )
        return None

    def _parse_interactive_reply(
        self,
        message: Any,
        *,
        fallback_referral: Any = None,
    ) -> WhatsAppMessage | None:
        if not isinstance(message, dict) or message.get("type") != "interactive":
            return None
        interactive = message.get("interactive")
        if not isinstance(interactive, dict):
            return None
        button_reply = interactive.get("button_reply")
        if not isinstance(button_reply, dict):
            return None
        reply_id = str(button_reply.get("id") or "")
        title = str(button_reply.get("title") or "")
        text = INTERACTIVE_REPLY_TEXT_BY_ID.get(reply_id) or title
        from_number = message.get("from")
        message_id = message.get("id")
        referral = compact_referral(message.get("referral") or fallback_referral)
        ctwa_clid = extract_ctwa_clid(message, referral)
        if text and from_number and message_id:
            return WhatsAppMessage(
                str(message_id),
                str(from_number),
                text,
                ctwa_clid=ctwa_clid,
                referral=referral,
                timestamp=str(message.get("timestamp")) if message.get("timestamp") else None,
            )
        return None

    def send_text(self, to_number: str, text: str) -> Dict[str, Any]:
        messages = split_whatsapp_messages(text)
        if len(messages) <= 1:
            return self._send_single_text(to_number, messages[0] if messages else text)
        results = []
        for index, message in enumerate(messages):
            result = self._send_single_text(to_number, message)
            results.append({"index": index, "text": message, "result": result})
        return {"split": True, "count": len(results), "messages": results}

    def send_entry_intent_buttons(self, to_number: str) -> Dict[str, Any]:
        return self.send_interactive_reply_buttons(
            to_number,
            body=ENTRY_INTENT_BODY,
            buttons=ENTRY_INTENT_BUTTONS,
        )

    def send_interactive_reply_buttons(
        self,
        to_number: str,
        *,
        body: str,
        buttons: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        normalized_buttons = [
            {"type": "reply", "reply": {"id": button["id"], "title": button["title"]}}
            for button in buttons[:3]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": normalized_buttons},
            },
        }
        if not self.enabled:
            return {"mocked": True, "to": to_number, "payload": payload}
        url = (
            "https://graph.facebook.com/v20.0/"
            f"{self.settings.meta_whatsapp_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.meta_whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def mark_read_with_typing(self, message_id: str) -> Dict[str, Any]:
        return self._mark_read(message_id, include_typing=True)

    def mark_read(self, message_id: str) -> Dict[str, Any]:
        return self._mark_read(message_id, include_typing=False)

    def _mark_read(self, message_id: str, *, include_typing: bool) -> Dict[str, Any]:
        if not self.enabled:
            return {"mocked": True, "message_id": message_id, "typing_indicator": include_typing}
        url = (
            "https://graph.facebook.com/v20.0/"
            f"{self.settings.meta_whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        if include_typing:
            payload["typing_indicator"] = {"type": "text"}
        headers = {
            "Authorization": f"Bearer {self.settings.meta_whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=8) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def mark_messages_read(self, message_ids: Iterable[str]) -> Dict[str, Any]:
        attempted = 0
        succeeded = 0
        failed = 0
        for message_id in dict.fromkeys(message_ids):
            attempted += 1
            try:
                self.mark_read(message_id)
                succeeded += 1
            except Exception as exc:
                failed += 1
                logger.warning("WhatsApp mark-read failed message_id=%s error=%s", message_id, exc)
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed}

    def mark_messages_read_with_typing(self, message_ids: Iterable[str]) -> Dict[str, Any]:
        attempted = 0
        succeeded = 0
        failed = 0
        for message_id in dict.fromkeys(message_ids):
            attempted += 1
            try:
                self.mark_read_with_typing(message_id)
                succeeded += 1
            except Exception as exc:
                failed += 1
                logger.warning("WhatsApp read/typing indicator failed message_id=%s error=%s", message_id, exc)
        return {"attempted": attempted, "succeeded": succeeded, "failed": failed}

    def _send_single_text(self, to_number: str, text: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"mocked": True, "to": to_number, "text": text}
        url = (
            "https://graph.facebook.com/v20.0/"
            f"{self.settings.meta_whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.meta_whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()


def compact_referral(referral: Any) -> Dict[str, Any]:
    if not isinstance(referral, dict):
        return {}
    allowed = {
        "source_url",
        "source_id",
        "source_type",
        "headline",
        "body",
        "media_type",
        "image_url",
        "video_url",
        "thumbnail_url",
        "ctwa_clid",
        "ad_id",
        "adset_id",
        "campaign_id",
    }
    compact: Dict[str, Any] = {}
    for key in allowed:
        value = referral.get(key)
        if value is not None:
            compact[key] = value
    return compact


def extract_ctwa_clid(message: Dict[str, Any], referral: Dict[str, Any]) -> Optional[str]:
    candidates = [
        referral.get("ctwa_clid"),
        message.get("ctwa_clid"),
        (
            message.get("referral", {}).get("ctwa_clid")
            if isinstance(message.get("referral"), dict)
            else None
        ),
    ]
    for value in candidates:
        if value:
            return str(value)
    return None
