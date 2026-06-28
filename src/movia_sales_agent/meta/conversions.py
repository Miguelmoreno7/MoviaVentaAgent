from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx

from movia_sales_agent.config.settings import Settings


logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v20.0"
EVENT_ORDER = ["LeadSubmitted", "ViewContent", "QualifiedLead", "InitiateCheckout"]


@dataclass(frozen=True)
class MetaConversionEvent:
    event_name: str
    event_id: str
    payload: Dict[str, Any]


class MetaConversionsClient:
    def __init__(self, settings: Settings, *, timeout_seconds: float = 5.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return self.settings.meta_capi_configured

    def send_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            return {"skipped": True, "reason": "meta_capi_not_configured"}
        url = (
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
            f"{self.settings.meta_capi_dataset_id}/events"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.meta_whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json={"data": [payload]})
            response.raise_for_status()
            return response.json()


class MetaConversionsService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Any,
        client: Optional[MetaConversionsClient] = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.client = client or MetaConversionsClient(settings)

    @property
    def configured(self) -> bool:
        return self.client.configured

    def record_attribution(
        self,
        *,
        lead_id: Optional[str],
        ctwa_clid: Optional[str],
        referral: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not lead_id or not ctwa_clid:
            return False
        try:
            return bool(
                self.repository.store_meta_ctwa_attribution(
                    lead_id,
                    ctwa_clid,
                    referral or {},
                )
            )
        except Exception as exc:
            logger.warning("Meta CTWA attribution store failed: %s", exc)
            return False

    def schedule_response_events(
        self,
        *,
        response: Any,
        latest_ctwa_clid: Optional[str] = None,
        latest_referral: Optional[Dict[str, Any]] = None,
    ) -> None:
        thread = threading.Thread(
            target=self._record_and_send_response_events,
            kwargs={
                "response": response,
                "latest_ctwa_clid": latest_ctwa_clid,
                "latest_referral": latest_referral or {},
            },
            daemon=True,
        )
        thread.start()

    def _record_and_send_response_events(
        self,
        *,
        response: Any,
        latest_ctwa_clid: Optional[str],
        latest_referral: Dict[str, Any],
    ) -> None:
        lead_id = getattr(response, "lead_id", None)
        if not lead_id:
            return
        if latest_ctwa_clid:
            self.record_attribution(
                lead_id=lead_id,
                ctwa_clid=latest_ctwa_clid,
                referral=latest_referral,
            )
        if not self.configured:
            return
        try:
            attribution = self.repository.get_meta_ctwa_attribution(lead_id)
        except Exception as exc:
            logger.warning("Meta CTWA attribution lookup failed: %s", exc)
            return
        ctwa_clid = attribution.get("ctwa_clid") or latest_ctwa_clid
        if not ctwa_clid:
            return
        for event in build_conversion_events(response, settings=self.settings, ctwa_clid=ctwa_clid):
            try:
                created = self.repository.create_meta_conversion_event(
                    lead_id=lead_id,
                    event_name=event.event_name,
                    event_id=event.event_id,
                    payload=event.payload,
                )
            except Exception as exc:
                logger.warning("Meta conversion event create failed event=%s: %s", event.event_name, exc)
                continue
            if not created:
                continue
            try:
                result = self.client.send_event(event.payload)
                self.repository.mark_meta_conversion_event_sent(
                    event_id=event.event_id,
                    response_json=result,
                )
            except Exception as exc:
                logger.warning("Meta CAPI event send failed event=%s: %s", event.event_name, exc)
                try:
                    self.repository.mark_meta_conversion_event_failed(
                        event_id=event.event_id,
                        error_text=f"{type(exc).__name__}: {str(exc)[:500]}",
                    )
                except Exception as mark_exc:
                    logger.warning("Meta CAPI failure mark failed: %s", mark_exc)


def build_conversion_events(
    response: Any,
    *,
    settings: Settings,
    ctwa_clid: str,
) -> List[MetaConversionEvent]:
    applicable = applicable_event_names(response)
    return [
        build_conversion_event(response, settings=settings, ctwa_clid=ctwa_clid, event_name=name)
        for name in EVENT_ORDER
        if name in applicable
    ]


def applicable_event_names(response: Any) -> List[str]:
    names = {"LeadSubmitted"}
    analysis = _as_dict(getattr(response, "analysis", {}))
    action = _as_dict(getattr(response, "selected_action", {}))
    knowledge = _as_dict(getattr(response, "knowledge_plan", {}))
    topics = set(_values(analysis.get("topics")))
    needs = set(_values(knowledge.get("knowledge_needs")))
    primary_intent = str(analysis.get("primary_intent") or "")
    buying_signal = str(analysis.get("buying_signal") or "")
    macro_action = str(action.get("macro_action") or getattr(response, "action", "") or "")
    micro_action = str(action.get("micro_action") or "")
    cta_type = str(action.get("cta_type") or "")
    target_stage = str(action.get("target_stage") or "")

    if (
        topics
        & {
            "pricing",
            "product_scope",
            "business_fit",
            "platform_process",
            "platform_steps_question",
            "comparison",
        }
        or needs
        & {
            "product_pricing",
            "product_capability",
            "product_fit",
            "platform_steps",
            "official_policy",
        }
        or primary_intent in {"ask_price", "ask_product_scope", "ask_platform_steps"}
    ):
        names.add("ViewContent")

    if (
        buying_signal in {"high", "explicit_start"}
        or target_stage in {"qualified", "solution_recommended", "ready_to_start", "closing"}
        or macro_action in {"recommend_solution", "soft_close", "direct_close"}
    ):
        names.add("QualifiedLead")

    if (
        bool(analysis.get("explicit_start_intent"))
        or macro_action == "direct_close"
        or cta_type in {"send_app_link", "direct_close"}
        or micro_action in {"send_app_link", "send_app_link_and_deposit_step"}
    ):
        names.add("InitiateCheckout")

    return [name for name in EVENT_ORDER if name in names]


def build_conversion_event(
    response: Any,
    *,
    settings: Settings,
    ctwa_clid: str,
    event_name: str,
) -> MetaConversionEvent:
    lead_id = str(getattr(response, "lead_id", "") or "unknown")
    event_id = deterministic_event_id(lead_id, event_name)
    payload = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": {
            "ctwa_clid": ctwa_clid,
            "whatsapp_business_account_id": settings.meta_whatsapp_business_account_id,
        },
        "custom_data": compact_custom_data(response),
    }
    return MetaConversionEvent(event_name=event_name, event_id=event_id, payload=payload)


def deterministic_event_id(lead_id: str, event_name: str) -> str:
    digest = hashlib.sha256(f"{lead_id}:{event_name}".encode("utf-8")).hexdigest()[:24]
    return f"movia:{event_name}:{digest}"


def compact_custom_data(response: Any) -> Dict[str, Any]:
    action = _as_dict(getattr(response, "selected_action", {}))
    analysis = _as_dict(getattr(response, "analysis", {}))
    lead_state = _as_dict(getattr(response, "lead_state", {}))
    return {
        "lead_id": getattr(response, "lead_id", None),
        "macro_action": action.get("macro_action") or getattr(response, "action", None),
        "micro_action": action.get("micro_action"),
        "cta_type": action.get("cta_type"),
        "target_stage": action.get("target_stage") or lead_state.get("current_stage"),
        "buying_signal": analysis.get("buying_signal"),
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _values(value: Any) -> Iterable[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []
