from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.db.repository import MoviaRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatwootConversation:
    account_id: int
    conversation_id: int


class ChatwootSendError(RuntimeError):
    def __init__(self, message: str, *, sent_count: int, original: Exception):
        super().__init__(message)
        self.sent_count = sent_count
        self.original = original


class ChatwootClient:
    def __init__(self, settings: Settings, repository: Optional[MoviaRepository] = None):
        self.settings = settings
        self.repository = repository
        self._account_id: Optional[int] = settings.chatwoot_account_id

    @property
    def enabled(self) -> bool:
        return self.settings.chatwoot_enabled

    def resolve_conversation_for_lead(
        self,
        *,
        lead_id: Optional[str],
        whatsapp_number: str,
        attempts: int = 3,
        retry_delays: Iterable[float] = (0.0, 1.0, 2.0),
    ) -> Optional[ChatwootConversation]:
        if not self.enabled:
            return None

        account_id = self._resolve_account_id()
        if not account_id:
            logger.warning("Chatwoot account id could not be resolved")
            return None

        stored = self._stored_conversation_id(lead_id)
        if stored:
            return ChatwootConversation(account_id=account_id, conversation_id=stored)

        delays = list(retry_delays)
        max_attempts = max(1, attempts)
        for index in range(max_attempts):
            if index < len(delays) and delays[index] > 0:
                time.sleep(delays[index])
            conversation_id = self._find_conversation_id(account_id, whatsapp_number)
            if conversation_id:
                self._store_conversation_id(lead_id, conversation_id)
                return ChatwootConversation(
                    account_id=account_id,
                    conversation_id=conversation_id,
                )
        return None

    def send_public_messages(
        self,
        conversation: ChatwootConversation,
        messages: Iterable[str],
    ) -> Dict[str, Any]:
        results = []
        for index, message in enumerate([part for part in messages if part]):
            try:
                result = self._send_message(
                    conversation.account_id,
                    conversation.conversation_id,
                    message,
                    private=False,
                )
            except Exception as exc:
                raise ChatwootSendError(
                    "Chatwoot public outbound failed",
                    sent_count=len(results),
                    original=exc,
                ) from exc
            results.append({"index": index, "result": result})
        return {
            "transport": "chatwoot",
            "conversation_id": conversation.conversation_id,
            "count": len(results),
            "messages": results,
        }

    def send_private_note(
        self,
        conversation: ChatwootConversation,
        content: str,
    ) -> Dict[str, Any]:
        result = self._send_message(
            conversation.account_id,
            conversation.conversation_id,
            content,
            private=True,
        )
        return {
            "transport": "chatwoot_private_note",
            "conversation_id": conversation.conversation_id,
            "result": result,
        }

    def _resolve_account_id(self) -> Optional[int]:
        if self._account_id:
            return self._account_id
        with self._http_client() as client:
            response = client.get("/api/v1/profile")
            response.raise_for_status()
            profile = response.json()
        account_id = profile.get("account_id") if isinstance(profile, dict) else None
        self._account_id = int(account_id) if account_id is not None else None
        return self._account_id

    def _stored_conversation_id(self, lead_id: Optional[str]) -> Optional[int]:
        if not self.repository or not lead_id:
            return None
        lead = self.repository.get_lead_profile(lead_id)
        if not lead:
            return None
        value = lead.get("chatwoot_conversation_id")
        return int(value) if value else None

    def _store_conversation_id(self, lead_id: Optional[str], conversation_id: int) -> None:
        if not self.repository:
            return
        try:
            self.repository.update_chatwoot_conversation_id(lead_id, conversation_id)
        except Exception as exc:
            logger.warning(
                "Chatwoot conversation id persistence failed lead_id=%s conversation_id=%s error=%s",
                lead_id,
                conversation_id,
                exc,
            )

    def _find_conversation_id(self, account_id: int, whatsapp_number: str) -> Optional[int]:
        contacts = self._find_contacts(account_id, whatsapp_number)
        for contact in contacts:
            contact_id = contact.get("id")
            if not contact_id:
                continue
            conversations = self._contact_conversations(account_id, int(contact_id))
            selected = select_conversation(conversations)
            if selected and selected.get("id"):
                return int(selected["id"])
        return None

    def _find_contacts(self, account_id: int, whatsapp_number: str) -> List[Dict[str, Any]]:
        terms = search_terms(whatsapp_number)
        contacts_by_id: Dict[int, Dict[str, Any]] = {}
        with self._http_client() as client:
            for term in terms:
                response = client.get(
                    f"/api/v1/accounts/{account_id}/contacts/search",
                    params={"q": term},
                )
                response.raise_for_status()
                data = response.json()
                payload = data.get("payload") if isinstance(data, dict) else data
                for contact in payload if isinstance(payload, list) else []:
                    if isinstance(contact, dict) and contact.get("id") is not None:
                        contacts_by_id[int(contact["id"])] = contact
        expected = set(terms)
        matched = [
            contact
            for contact in contacts_by_id.values()
            if contact_matches_terms(contact, expected)
        ]
        return matched or list(contacts_by_id.values())

    def _contact_conversations(self, account_id: int, contact_id: int) -> List[Dict[str, Any]]:
        with self._http_client() as client:
            response = client.get(
                f"/api/v1/accounts/{account_id}/contacts/{contact_id}/conversations"
            )
            response.raise_for_status()
            data = response.json()
        payload = data.get("payload") if isinstance(data, dict) else data
        return payload if isinstance(payload, list) else []

    def _send_message(
        self,
        account_id: int,
        conversation_id: int,
        content: str,
        *,
        private: bool,
    ) -> Dict[str, Any]:
        with self._http_client() as client:
            response = client.post(
                f"/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages",
                json={
                    "content": content,
                    "message_type": "outgoing",
                    "private": private,
                },
            )
            response.raise_for_status()
            return response.json()

    def _http_client(self) -> httpx.Client:
        if not self.settings.chatwoot_url or not self.settings.chatwoot_api_token:
            raise RuntimeError("Chatwoot is not configured")
        return httpx.Client(
            base_url=self.settings.chatwoot_url.rstrip("/"),
            timeout=20,
            headers={
                "api_access_token": self.settings.chatwoot_api_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return f"+{digits}" if digits else value


def search_terms(whatsapp_number: str) -> List[str]:
    terms = [normalize_phone(whatsapp_number), re.sub(r"\D+", "", whatsapp_number or "")]
    return [term for index, term in enumerate(terms) if term and term not in terms[:index]]


def contact_matches_terms(contact: Dict[str, Any], expected_terms: set[str]) -> bool:
    fields = {
        str(contact.get("phone_number") or ""),
        str(contact.get("identifier") or ""),
        str(contact.get("source_id") or ""),
    }
    for item in contact.get("contact_inboxes") or []:
        if isinstance(item, dict):
            fields.add(str(item.get("source_id") or ""))
    return bool(expected_terms.intersection(fields))


def select_conversation(conversations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    preferred_statuses = {"open", "pending", "snoozed"}
    ordered = sorted(
        conversations,
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    for conversation in ordered:
        if str(conversation.get("status") or "").lower() in preferred_statuses:
            return conversation
    return ordered[0] if ordered else None
