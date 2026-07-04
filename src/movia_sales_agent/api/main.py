from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse

from movia_sales_agent.agent.graph import MoviaSalesAgent
from movia_sales_agent.chatwoot.client import ChatwootClient, ChatwootSendError
from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.followup.scheduler import FollowUpScheduler
from movia_sales_agent.meta.conversions import MetaConversionsService
from movia_sales_agent.models.schemas import ChatRequest, ChatResponse
from movia_sales_agent.platform.observability import PlatformObservabilityService
from movia_sales_agent.platform.registry_sync import sync_from_settings
from movia_sales_agent.runtime.metadata import (
    compact_knowledge_plan,
    compact_lead_state,
    compact_response_metadata,
    compact_retrieval_metadata,
)
from movia_sales_agent.whatsapp.client import WhatsAppClient
from movia_sales_agent.whatsapp.queue import WhatsAppWorkerManager, should_send_entry_intent_buttons


FRONTEND_ROOT = PROJECT_ROOT / "frontend"
WEBHOOK_LOG_MAX_CHARS = 20000
logger = logging.getLogger(__name__)


class HealthAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return '"GET /health ' not in message and '"HEAD /health ' not in message


def install_health_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, HealthAccessLogFilter) for item in access_logger.filters):
        return
    access_logger.addFilter(HealthAccessLogFilter())


install_health_access_log_filter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.platform_registry_sync = await sync_platform_registry_on_startup(settings)
    agent = get_agent()
    manager: Optional[WhatsAppWorkerManager] = None
    if settings.webhook_queue_enabled:
        manager = WhatsAppWorkerManager(
            settings=settings,
            agent=agent,
            client=WhatsAppClient(settings),
        )
        await manager.start()
    scheduler: Optional[FollowUpScheduler] = None
    if settings.followup_enabled:
        scheduler = FollowUpScheduler(
            settings=settings,
            repository=agent.repository,
            whatsapp_client=WhatsAppClient(settings),
            chatwoot_client=ChatwootClient(settings, repository=agent.repository),
            observability=PlatformObservabilityService.from_settings(
                settings,
                memory=getattr(agent, "memory", None),
            ),
        )
        await scheduler.start()
    app.state.whatsapp_worker_manager = manager
    app.state.followup_scheduler = scheduler
    try:
        yield
    finally:
        if scheduler:
            await scheduler.stop()
        if manager:
            await manager.stop()


async def sync_platform_registry_on_startup(settings: Settings) -> Dict[str, Any]:
    if not settings.platform_registry_sync_on_startup:
        return {"enabled": False, "status": "disabled"}
    if not settings.platform_observability_enabled:
        return {"enabled": False, "status": "platform_observability_disabled"}
    try:
        result = await asyncio.to_thread(sync_from_settings, settings, dry_run=False)
        logger.info("Platform registry sync completed on startup: %s", result)
        return {"enabled": True, "status": "success", "result": result}
    except Exception as exc:
        logger.exception("Platform registry sync failed on startup")
        return {
            "enabled": True,
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


app = FastAPI(title="MovIA Sales Agent", version="0.1.0", lifespan=lifespan)


@lru_cache(maxsize=1)
def get_agent() -> MoviaSalesAgent:
    return MoviaSalesAgent(get_settings())


def get_whatsapp_client(settings: Settings = Depends(get_settings)) -> WhatsAppClient:
    return WhatsAppClient(settings)


def require_internal_api_key(
    settings: Settings = Depends(get_settings),
    x_movia_internal_api_key: Optional[str] = Header(default=None),
) -> None:
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if x_movia_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


def require_debug_ui(settings: Settings = Depends(get_settings)) -> None:
    if not settings.enable_debug_ui:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def get_worker_manager(request: Request) -> Optional[WhatsAppWorkerManager]:
    return getattr(request.app.state, "whatsapp_worker_manager", None)


def get_followup_scheduler(request: Request) -> Optional[FollowUpScheduler]:
    return getattr(request.app.state, "followup_scheduler", None)


@app.get("/")
def frontend(
    _debug: None = Depends(require_debug_ui),
    _auth: None = Depends(require_internal_api_key),
) -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "index.html")


@app.get("/frontend/{asset_path:path}")
def frontend_asset(
    asset_path: str,
    _debug: None = Depends(require_debug_ui),
    _auth: None = Depends(require_internal_api_key),
) -> FileResponse:
    path = (FRONTEND_ROOT / asset_path).resolve()
    if FRONTEND_ROOT.resolve() not in path.parents and path != FRONTEND_ROOT.resolve():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(path)


@app.get("/health")
def health(
    settings: Settings = Depends(get_settings),
    manager: Optional[WhatsAppWorkerManager] = Depends(get_worker_manager),
    scheduler: Optional[FollowUpScheduler] = Depends(get_followup_scheduler),
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "database_configured": bool(settings.database_url and not settings.disable_database),
        "openai_configured": bool(settings.openai_api_key and not settings.disable_openai),
        "redis_configured": bool(settings.redis_url),
        "queue_enabled": settings.webhook_queue_enabled,
        "queue_durable": bool(manager and manager.durable),
        "job_concurrency": settings.job_concurrency,
        "lead_batch_window_seconds": settings.lead_batch_window_seconds,
        "followup_enabled": settings.followup_enabled,
        "followup_scheduler_running": bool(scheduler and scheduler.running),
        "followup_delay_hours": settings.followup_delay_hours,
        "followup_scan_interval_seconds": settings.followup_scan_interval_seconds,
        "platform_observability_enabled": settings.platform_observability_enabled,
        "platform_registry_sync_on_startup": settings.platform_registry_sync_on_startup,
        "platform_registry_sync_status": getattr(
            getattr(app, "state", None),
            "platform_registry_sync",
            {"status": "not_started"},
        ).get("status"),
        "platform_agent_key": settings.platform_agent_key,
        "platform_runtime_cache_seconds": settings.platform_runtime_cache_seconds,
        "debug_ui_enabled": settings.enable_debug_ui,
        "debug_metadata_enabled": settings.debug_metadata,
        "whatsapp_enabled": settings.whatsapp_enabled,
        "meta_whatsapp_business_account_configured": bool(
            settings.meta_whatsapp_business_account_id
        ),
        "meta_capi_dataset_configured": bool(settings.meta_capi_dataset_id),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    _auth: None = Depends(require_internal_api_key),
    settings: Settings = Depends(get_settings),
    agent: MoviaSalesAgent = Depends(get_agent),
) -> ChatResponse:
    response = agent.invoke(
        message=payload.message,
        lead_external_id=payload.lead_external_id,
        channel=payload.channel,
        external_message_id=payload.external_message_id,
    )
    return response if settings.debug_metadata else compact_chat_response(response)


@app.post("/webhooks/whatsapp")
async def receive_whatsapp(
    request: Request,
    settings: Settings = Depends(get_settings),
    agent: MoviaSalesAgent = Depends(get_agent),
    client: WhatsAppClient = Depends(get_whatsapp_client),
    manager: Optional[WhatsAppWorkerManager] = Depends(get_worker_manager),
) -> Dict[str, Any]:
    payload = await request.json()
    inbound_messages = client.parse_messages(payload)
    summaries = summarize_webhook_messages(payload)
    print_webhook_diagnostics(payload, summaries=summaries, parsed_count=len(inbound_messages))
    logger.info("whatsapp_webhook_payload raw=%s", json_for_log(payload))
    logger.info(
        "whatsapp_webhook_received parsed_messages=%s raw_messages=%s summaries=%s",
        len(inbound_messages),
        len(summaries),
        json_for_log(summaries),
    )
    results = []
    if settings.webhook_queue_enabled:
        if manager is None:
            manager = WhatsAppWorkerManager(settings=settings, agent=agent, client=client)
            request.app.state.whatsapp_worker_manager = manager
            await manager.start()
        for inbound in inbound_messages:
            enqueue_status = await manager.enqueue(inbound)
            read_result = mark_inbound_read(client, inbound.message_id)
            logger.info(
                "whatsapp_webhook_enqueue message_id=%s status=%s read_status=%s",
                inbound.message_id,
                enqueue_status,
                read_result.get("status"),
            )
            results.append(
                {
                    "message_id": inbound.message_id,
                    "status": enqueue_status,
                    "read_status": read_result.get("status"),
                }
            )
        return {"status": "accepted", "queued": len(results), "results": results}

    for inbound in inbound_messages:
        if agent.repository.message_exists(inbound.message_id):
            read_result = mark_inbound_read(client, inbound.message_id)
            results.append(
                {
                    "message_id": inbound.message_id,
                    "status": "duplicate",
                    "read_status": read_result.get("status"),
                }
            )
            continue
        mark_inbound_read(client, inbound.message_id)
        response = await run_agent_and_send(agent, client, inbound, settings)
        results.append(
            {
                "message_id": inbound.message_id,
                "status": "processed",
                "action": response.action,
                "message_count": len(response.response_messages),
            }
        )
    return {"status": "ok", "processed": len(results), "results": results}


def mark_inbound_read(client: WhatsAppClient, message_id: str) -> Dict[str, Any]:
    try:
        result = client.mark_read(message_id)
        logger.info("whatsapp_webhook_mark_read message_id=%s status=success", message_id)
        return {"status": "success", "result": result}
    except Exception as exc:
        logger.warning("whatsapp_webhook_mark_read message_id=%s status=failed error=%s", message_id, exc)
        return {"status": "failed", "error": str(exc)}


async def run_agent_and_send(
    agent: MoviaSalesAgent,
    client: WhatsAppClient,
    inbound: Any,
    settings: Settings,
) -> ChatResponse:
    import asyncio

    def _run() -> ChatResponse:
        response = agent.invoke(
            message=inbound.text,
            lead_external_id=inbound.from_number,
            channel="whatsapp",
            external_message_id=inbound.message_id,
        )
        chatwoot = ChatwootClient(settings, repository=getattr(agent, "repository", None))
        conversation = None
        if should_send_entry_intent_buttons(response):
            client.send_entry_intent_buttons(inbound.from_number)
            schedule_meta_conversions(settings, agent, inbound, response)
            return response
        if chatwoot.enabled:
            try:
                conversation = chatwoot.resolve_conversation_for_lead(
                    lead_id=response.lead_id,
                    whatsapp_number=inbound.from_number,
                )
                if conversation:
                    chatwoot.send_public_messages(
                        conversation,
                        list(response.response_messages or []) or [response.response],
                    )
                    schedule_meta_conversions(settings, agent, inbound, response)
                    return response
            except ChatwootSendError as exc:
                if exc.sent_count > 0:
                    logger.warning(
                        "Chatwoot outbound failed after %s accepted messages in direct webhook path; "
                        "not falling back to WhatsApp to avoid duplicates: %s",
                        exc.sent_count,
                        exc.original,
                    )
                    schedule_meta_conversions(settings, agent, inbound, response)
                    return response
                logger.warning(
                    "Chatwoot outbound failed before accepting a message in direct webhook path: %s",
                    exc.original,
                )
            except Exception as exc:
                logger.warning("Chatwoot outbound failed in direct webhook path: %s", exc)
        client.send_text(inbound.from_number, response.response)
        if conversation:
            try:
                chatwoot.send_private_note(
                    conversation,
                    (
                        "MovIA fallback sent this response directly through WhatsApp API after "
                        "Chatwoot public outbound failed:\n\n"
                        f"{response.response}"
                    ),
                )
            except Exception as exc:
                logger.warning("Chatwoot fallback private note failed in direct webhook path: %s", exc)
        schedule_meta_conversions(settings, agent, inbound, response)
        return response

    return await asyncio.to_thread(_run)


def schedule_meta_conversions(
    settings: Settings,
    agent: MoviaSalesAgent,
    inbound: Any,
    response: ChatResponse,
) -> None:
    try:
        MetaConversionsService(
            settings=settings,
            repository=getattr(agent, "repository", None),
        ).schedule_response_events(
            response=response,
            latest_ctwa_clid=getattr(inbound, "ctwa_clid", None),
            latest_referral=getattr(inbound, "referral", {}) or {},
        )
    except Exception as exc:
        logger.warning("Meta conversion scheduling failed in direct webhook path: %s", exc)


def json_for_log(payload: Any, *, max_chars: int = WEBHOOK_LOG_MAX_CHARS) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        text = str(payload)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"...[truncated {len(text) - max_chars} chars]"


def print_webhook_diagnostics(
    payload: Any,
    *,
    summaries: list[Dict[str, Any]],
    parsed_count: int,
) -> None:
    print(f"whatsapp_webhook_payload raw={json_for_log(payload)}", flush=True)
    print(
        "whatsapp_webhook_received "
        f"parsed_messages={parsed_count} "
        f"raw_messages={len(summaries)} "
        f"summaries={json_for_log(summaries)}",
        flush=True,
    )


def summarize_webhook_messages(payload: Any) -> list[Dict[str, Any]]:
    summaries = []
    for body_index, body in enumerate(candidate_webhook_bodies(payload)):
        source = f"body[{body_index}]"
        summaries.extend(
            summarize_message(message, source=f"{source}.messages")
            for message in body.get("messages", [])
            if isinstance(message, dict)
        )
        for entry_index, entry in enumerate(body.get("entry", [])):
            if not isinstance(entry, dict):
                continue
            for change_index, change in enumerate(entry.get("changes", [])):
                if not isinstance(change, dict):
                    continue
                value = change.get("value") if isinstance(change.get("value"), dict) else {}
                messages = value.get("messages", []) if isinstance(value, dict) else []
                summaries.extend(
                    summarize_message(
                        message,
                        source=f"{source}.entry[{entry_index}].changes[{change_index}].value.messages",
                    )
                    for message in messages
                    if isinstance(message, dict)
                )
    return summaries


def candidate_webhook_bodies(payload: Any) -> list[Dict[str, Any]]:
    bodies: list[Dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            body = item.get("body")
            if isinstance(body, dict):
                bodies.append(body)
            bodies.append(item)
        return bodies
    if isinstance(payload, dict):
        body = payload.get("body")
        if isinstance(body, dict):
            bodies.append(body)
        bodies.append(payload)
    return bodies


def summarize_message(message: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    text_payload = message.get("text") if isinstance(message.get("text"), dict) else {}
    referral = message.get("referral") if isinstance(message.get("referral"), dict) else {}
    summary: Dict[str, Any] = {
        "source": source,
        "id": message.get("id"),
        "from": message.get("from"),
        "type": message.get("type"),
        "timestamp": message.get("timestamp"),
    }
    if text_payload:
        summary["text_body"] = text_payload.get("body")
    if referral:
        summary["referral_keys"] = sorted(referral.keys())
        if referral.get("ctwa_clid"):
            summary["ctwa_clid"] = referral.get("ctwa_clid")
    if isinstance(message.get("button"), dict):
        summary["button"] = message.get("button")
    if isinstance(message.get("interactive"), dict):
        interactive = message["interactive"]
        summary["interactive_type"] = interactive.get("type")
    if message.get("type") != "text":
        summary["parsed_by_agent"] = False
    return summary


def compact_chat_response(response: ChatResponse) -> ChatResponse:
    return response.model_copy(
        update={
            "retrieval_metadata": compact_retrieval_metadata(response.retrieval_metadata),
            "lead_state": compact_lead_state(response.lead_state),
            "knowledge_plan": compact_knowledge_plan(response.knowledge_plan),
            "retrieved_sources": [],
            "response_metadata": compact_response_metadata(
                response.response_metadata,
                action=response.action,
                selected_action=response.selected_action,
                knowledge_plan=response.knowledge_plan,
                token_usage=response.token_usage,
            ),
        }
    )


def run() -> None:
    uvicorn.run("movia_sales_agent.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
