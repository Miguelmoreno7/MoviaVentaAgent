from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from numbers import Number
from threading import Lock, Thread
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from movia_sales_agent.config.settings import Settings
from movia_sales_agent.memory.store import MemoryStore
from movia_sales_agent.models.schemas import ChatResponse


logger = logging.getLogger(__name__)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, Number):
        return int(value)
    return None


def extract_total_tokens(payload: Any) -> Optional[int]:
    candidates: List[int] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            total_tokens = coerce_int(value.get("total_tokens"))
            if total_tokens is not None and total_tokens >= 0:
                candidates.append(total_tokens)
            prompt_tokens = coerce_int(value.get("prompt_tokens"))
            completion_tokens = coerce_int(value.get("completion_tokens"))
            input_tokens = coerce_int(value.get("input_tokens"))
            output_tokens = coerce_int(value.get("output_tokens"))
            if prompt_tokens is not None and completion_tokens is not None:
                candidates.append(prompt_tokens + completion_tokens)
            if input_tokens is not None and output_tokens is not None:
                candidates.append(input_tokens + output_tokens)
            for nested in value.values():
                collect(nested)
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload)
    return max(candidates) if candidates else None


@dataclass(frozen=True)
class AgentRuntimeInfo:
    agent_id: str
    agent_key: str
    enabled: bool
    version: str
    agent_version_id: str

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "AgentRuntimeInfo":
        return cls(
            agent_id=str(payload["agent_id"]),
            agent_key=str(payload["agent_key"]),
            enabled=bool(payload["enabled"]),
            version=str(payload["version"]),
            agent_version_id=str(payload["agent_version_id"]),
        )


@dataclass
class CachedRuntime:
    runtime: AgentRuntimeInfo
    fetched_at: float
    expires_at: float
    stale_until: float

    def to_payload(self) -> Dict[str, Any]:
        return {
            "runtime": asdict(self.runtime),
            "fetched_at": self.fetched_at,
            "expires_at": self.expires_at,
            "stale_until": self.stale_until,
        }

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "CachedRuntime":
        return cls(
            runtime=AgentRuntimeInfo.from_payload(payload["runtime"]),
            fetched_at=float(payload["fetched_at"]),
            expires_at=float(payload["expires_at"]),
            stale_until=float(payload["stale_until"]),
        )


class PlatformRunClient:
    def __init__(self, supabase_url: str, service_role_key: str, timeout_seconds: int):
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._timeout = timeout_seconds
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        response = httpx.get(
            f"{self._base_url}/{table}",
            headers=self._headers,
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _post(self, table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        response = httpx.post(
            f"{self._base_url}/{table}",
            headers=self._headers,
            content=json.dumps(rows),
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _patch(
        self,
        table: str,
        filters: Dict[str, str],
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        response = httpx.patch(
            f"{self._base_url}/{table}",
            headers=self._headers,
            params=filters,
            content=json.dumps(payload),
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def resolve_agent_runtime(
        self,
        *,
        agent_key: str,
        requested_version: Optional[str] = None,
    ) -> AgentRuntimeInfo:
        rows = self._get(
            "agents",
            {
                "select": "id,key,enabled,default_version",
                "key": f"eq.{agent_key}",
                "limit": "1",
            },
        )
        if not rows:
            raise RuntimeError(f"Agent key not found in platform registry: {agent_key}")
        agent = rows[0]
        agent_id = str(agent.get("id") or "").strip()
        default_version = str(agent.get("default_version") or "").strip() or None
        version = (requested_version or default_version or "").strip()
        enabled = bool(agent.get("enabled"))
        version_rows: List[Dict[str, Any]] = []
        if version:
            version_rows = self._get(
                "agent_versions",
                {
                    "select": "id,version,status",
                    "agent_id": f"eq.{agent_id}",
                    "version": f"eq.{version}",
                    "limit": "1",
                },
            )
        if not version_rows:
            version_rows = self._get(
                "agent_versions",
                {
                    "select": "id,version,status",
                    "agent_id": f"eq.{agent_id}",
                    "status": "eq.active",
                    "order": "created_at.desc",
                    "limit": "1",
                },
            )
        if not version_rows:
            raise RuntimeError(f"No agent_versions row found for agent key: {agent_key}")
        version_row = version_rows[0]
        resolved_version = str(version_row.get("version") or "").strip()
        agent_version_id = str(version_row.get("id") or "").strip()
        if not resolved_version or not agent_version_id or not agent_id:
            raise RuntimeError(f"Incomplete version metadata for agent key: {agent_key}")
        return AgentRuntimeInfo(
            agent_id=agent_id,
            agent_key=agent_key,
            enabled=enabled,
            version=resolved_version,
            agent_version_id=agent_version_id,
        )

    def create_run(
        self,
        *,
        run_id: Optional[str] = None,
        runtime: AgentRuntimeInfo,
        status: str,
        input_json: Dict[str, Any],
        requested_by: str,
    ) -> str:
        run_id = run_id or str(uuid4())
        now_ts = iso_now()
        payload: Dict[str, Any] = {
            "id": run_id,
            "agent_id": runtime.agent_id,
            "agent_version_id": runtime.agent_version_id,
            "status": status,
            "input_json": input_json,
            "requested_by": requested_by,
            "created_at": now_ts,
        }
        if status == "running":
            payload["started_at"] = now_ts
        if status in {"success", "failed", "cancelled"}:
            payload["finished_at"] = now_ts
        self._post("runs", [payload])
        return run_id

    def add_event(
        self,
        *,
        run_id: str,
        level: str,
        event_type: str,
        message: str,
        payload_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._post(
            "run_events",
            [
                {
                    "run_id": run_id,
                    "ts": iso_now(),
                    "level": level,
                    "event_type": event_type,
                    "message": message,
                    "payload_json": payload_json or {},
                }
            ],
        )

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        output_json: Optional[Dict[str, Any]],
        total_tokens: Optional[int] = None,
        total_duration_ms: Optional[int] = None,
        error_text: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "status": status,
            "output_json": output_json,
            "finished_at": iso_now(),
        }
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        if total_duration_ms is not None:
            payload["total_duration_ms"] = total_duration_ms
        if error_text:
            payload["error_text"] = error_text
        self._patch("runs", {"id": f"eq.{run_id}"}, payload)


class PlatformRuntimeResolver:
    def __init__(
        self,
        *,
        settings: Settings,
        client: PlatformRunClient,
        memory: Optional[MemoryStore] = None,
    ):
        self.settings = settings
        self.client = client
        self.memory = memory
        self._lock = Lock()
        self._cache: Dict[str, CachedRuntime] = {}

    def resolve(self) -> tuple[Optional[AgentRuntimeInfo], bool, Optional[str]]:
        cache_key = self._cache_key()
        now = time.time()
        cached = self._get_cached(cache_key)
        if cached and cached.expires_at >= now:
            return cached.runtime, False, None
        try:
            runtime = self.client.resolve_agent_runtime(
                agent_key=self.settings.platform_agent_key,
                requested_version=self.settings.platform_agent_version,
            )
            self._set_cached(cache_key, runtime, now)
            return runtime, True, None
        except Exception as exc:
            if cached and cached.stale_until >= now:
                return cached.runtime, False, f"{type(exc).__name__}: {str(exc)[:200]}"
            return None, False, f"{type(exc).__name__}: {str(exc)[:200]}"

    def _cache_key(self) -> str:
        version = self.settings.platform_agent_version or "default"
        return f"movia:platform:runtime:{self.settings.platform_agent_key}:{version}"

    def _get_cached(self, cache_key: str) -> Optional[CachedRuntime]:
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        if self.memory:
            payload = self.memory.get_cache(cache_key)
            if isinstance(payload, dict):
                try:
                    cached = CachedRuntime.from_payload(payload)
                except Exception:
                    return None
                with self._lock:
                    self._cache[cache_key] = cached
                return cached
        return None

    def _set_cached(self, cache_key: str, runtime: AgentRuntimeInfo, now: float) -> None:
        ttl = max(1, int(self.settings.platform_runtime_cache_seconds or 30))
        cached = CachedRuntime(
            runtime=runtime,
            fetched_at=now,
            expires_at=now + ttl,
            stale_until=now + ttl + max(30, ttl * 2),
        )
        with self._lock:
            self._cache[cache_key] = cached
        if self.memory:
            self.memory.set_cache(cache_key, cached.to_payload(), ttl_seconds=ttl)


class PlatformObservabilityService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: PlatformRunClient,
        resolver: PlatformRuntimeResolver,
    ):
        self.settings = settings
        self.client = client
        self.resolver = resolver

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        memory: Optional[MemoryStore] = None,
    ) -> Optional["PlatformObservabilityService"]:
        if not settings.platform_observability_enabled:
            return None
        if not settings.supabase_url or not settings.supabase_service_role_key:
            logger.warning("Platform observability disabled: missing Supabase settings")
            return None
        client = PlatformRunClient(
            settings.supabase_url,
            settings.supabase_service_role_key,
            settings.sync_timeout_seconds,
        )
        resolver = PlatformRuntimeResolver(settings=settings, client=client, memory=memory)
        return cls(settings=settings, client=client, resolver=resolver)

    def resolve_runtime(self) -> tuple[Optional[AgentRuntimeInfo], Optional[str]]:
        runtime, refreshed, warning = self.resolver.resolve()
        if warning:
            logger.warning("Platform runtime resolution warning: %s", warning)
        if runtime and refreshed:
            logger.info("Platform runtime resolved for %s@%s", runtime.agent_key, runtime.version)
        return runtime, warning

    def start_run_async(
        self,
        *,
        runtime: AgentRuntimeInfo,
        status: str,
        input_json: Dict[str, Any],
        requested_by: str,
    ) -> str:
        run_id = str(uuid4())
        Thread(
            target=self._create_run_best_effort,
            kwargs={
                "run_id": run_id,
                "runtime": runtime,
                "status": status,
                "input_json": input_json,
                "requested_by": requested_by,
            },
            daemon=True,
        ).start()
        return run_id

    def add_event_async(
        self,
        *,
        run_id: Optional[str],
        level: str,
        event_type: str,
        message: str,
        payload_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not run_id:
            return
        Thread(
            target=self._add_event_best_effort,
            kwargs={
                "run_id": run_id,
                "level": level,
                "event_type": event_type,
                "message": message,
                "payload_json": payload_json,
            },
            daemon=True,
        ).start()

    def update_run_async(
        self,
        *,
        run_id: Optional[str],
        status: str,
        output_json: Optional[Dict[str, Any]],
        total_tokens: Optional[int] = None,
        total_duration_ms: Optional[int] = None,
        error_text: Optional[str] = None,
    ) -> None:
        if not run_id:
            return
        Thread(
            target=self._update_run_best_effort,
            kwargs={
                "run_id": run_id,
                "status": status,
                "output_json": output_json,
                "total_tokens": total_tokens,
                "total_duration_ms": total_duration_ms,
                "error_text": error_text,
            },
            daemon=True,
        ).start()

    def _add_event_best_effort(self, **kwargs: Any) -> None:
        try:
            self.client.add_event(**kwargs)
        except Exception as exc:
            logger.warning("Platform run event write failed: %s", exc)

    def _create_run_best_effort(self, **kwargs: Any) -> None:
        try:
            self.client.create_run(**kwargs)
        except Exception as exc:
            logger.warning("Platform run create failed: %s", exc)

    def _update_run_best_effort(self, **kwargs: Any) -> None:
        try:
            self.client.update_run(**kwargs)
        except Exception as exc:
            logger.warning("Platform run update failed: %s", exc)


def batch_input_json(
    *,
    from_number: str,
    channel: str,
    message_ids: List[str],
    batch_count: int,
) -> Dict[str, Any]:
    return {
        "channel": channel,
        "from_number": from_number,
        "message_ids": message_ids,
        "batch_count": batch_count,
    }


def response_output_json(response: ChatResponse, *, debug_metadata: bool) -> Dict[str, Any]:
    total = (response.token_usage.get("total") or {}) if response.token_usage else {}
    output: Dict[str, Any] = {
        "action": response.action,
        "message_count": len(response.response_messages),
        "response_source": response.response_metadata.get("response_source"),
        "token_usage": {
            "total_tokens": total.get("total_tokens", 0),
            "input_tokens": total.get("input_tokens", 0),
            "output_tokens": total.get("output_tokens", 0),
        },
    }
    if debug_metadata:
        output["token_usage"]["calls"] = response.token_usage.get("calls") or []
    return output
