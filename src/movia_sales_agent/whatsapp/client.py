from __future__ import annotations

from typing import Any, Dict, List

import httpx

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.whatsapp.formatting import split_whatsapp_messages


class WhatsAppMessage:
    def __init__(self, message_id: str, from_number: str, text: str):
        self.message_id = message_id
        self.from_number = from_number
        self.text = text


class WhatsAppClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.whatsapp_enabled

    def parse_messages(self, payload: Dict[str, Any]) -> List[WhatsAppMessage]:
        messages: List[WhatsAppMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    text = (message.get("text") or {}).get("body")
                    from_number = message.get("from")
                    message_id = message.get("id")
                    if text and from_number and message_id:
                        messages.append(WhatsAppMessage(message_id, from_number, text))
        return messages

    def send_text(self, to_number: str, text: str) -> Dict[str, Any]:
        messages = split_whatsapp_messages(text)
        if len(messages) <= 1:
            return self._send_single_text(to_number, messages[0] if messages else text)
        results = []
        for index, message in enumerate(messages):
            result = self._send_single_text(to_number, message)
            results.append({"index": index, "text": message, "result": result})
        return {"split": True, "count": len(results), "messages": results}

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
