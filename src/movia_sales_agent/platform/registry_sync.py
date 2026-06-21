from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from movia_sales_agent.config.paths import PROJECT_ROOT
from movia_sales_agent.config.settings import Settings, get_settings


DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "platform_registry" / "agents.json"


@dataclass(frozen=True)
class PlatformSyncConfig:
    supabase_url: str
    service_role_key: str
    registry_path: Path = DEFAULT_REGISTRY_PATH
    timeout_seconds: int = 20
    dry_run: bool = False


def sync_config_from_settings(
    settings: Optional[Settings] = None,
    *,
    dry_run: bool = False,
) -> PlatformSyncConfig:
    settings = settings or get_settings()
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise ValueError(f"Missing required settings: {', '.join(missing)}")
    return PlatformSyncConfig(
        supabase_url=str(settings.supabase_url),
        service_role_key=str(settings.supabase_service_role_key),
        registry_path=settings.agents_registry_path,
        timeout_seconds=settings.sync_timeout_seconds,
        dry_run=dry_run,
    )


class SupabaseRegistryClient:
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

    def _insert(self, table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        response = httpx.post(
            f"{self._base_url}/{table}",
            headers=self._headers,
            content=json.dumps(rows),
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _update(
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

    def ensure_agent(
        self,
        *,
        key: str,
        name: str,
        enabled: bool,
        default_version: Optional[str],
        dry_run: bool,
    ) -> tuple[str, str, bool]:
        rows = self._get(
            "agents",
            {
                "select": "id,key,name,enabled,default_version",
                "key": f"eq.{key}",
                "limit": "1",
            },
        )
        payload = {"name": name, "enabled": enabled, "default_version": default_version}
        if rows:
            agent_id = str(rows[0]["id"])
            if dry_run:
                return agent_id, "update(dry-run)", False
            self._update("agents", {"id": f"eq.{agent_id}"}, payload)
            return agent_id, "update", False
        if dry_run:
            return "<new-agent>", "insert(dry-run)", True
        inserted = self._insert("agents", [{"key": key, **payload}])
        if not inserted:
            raise RuntimeError(f"Insert returned no rows for agent key={key}")
        return str(inserted[0]["id"]), "insert", False

    def ensure_agent_version(
        self,
        *,
        agent_id: str,
        version: str,
        entrypoint: str,
        status: str,
        config_json: Dict[str, Any],
        dry_run: bool,
    ) -> str:
        rows = self._get(
            "agent_versions",
            {
                "select": "id,agent_id,version",
                "agent_id": f"eq.{agent_id}",
                "version": f"eq.{version}",
                "limit": "1",
            },
        )
        payload = {"entrypoint": entrypoint, "status": status, "config_json": config_json}
        if rows:
            version_id = str(rows[0]["id"])
            if dry_run:
                return "update(dry-run)"
            self._update("agent_versions", {"id": f"eq.{version_id}"}, payload)
            return "update"
        if dry_run:
            return "insert(dry-run)"
        self._insert("agent_versions", [{"agent_id": agent_id, "version": version, **payload}])
        return "insert"


def read_registry(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Registry file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry root must be a JSON object.")
    agents = data.get("agents")
    if not isinstance(agents, list):
        raise ValueError("Registry must include an 'agents' array.")
    return agents


def sync_registry(config: PlatformSyncConfig) -> Dict[str, Any]:
    agents = read_registry(config.registry_path)
    client = SupabaseRegistryClient(
        config.supabase_url,
        config.service_role_key,
        config.timeout_seconds,
    )
    agent_actions: List[Dict[str, str]] = []
    version_actions: List[Dict[str, str]] = []
    for agent in agents:
        key = str(agent.get("key") or "").strip()
        name = str(agent.get("name") or "").strip()
        enabled = bool(agent.get("enabled", True))
        default_version = (
            str(agent.get("default_version")).strip()
            if agent.get("default_version") not in {None, ""}
            else None
        )
        versions = agent.get("versions")
        if not key or not name:
            raise ValueError(f"Invalid agent entry in registry. key/name required: {agent}")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"Agent '{key}' must include at least one version entry.")
        agent_id, action, placeholder_id = client.ensure_agent(
            key=key,
            name=name,
            enabled=enabled,
            default_version=default_version,
            dry_run=config.dry_run,
        )
        agent_actions.append({"key": key, "action": action})
        for version_entry in versions:
            version = str(version_entry.get("version") or "").strip()
            entrypoint = str(version_entry.get("entrypoint") or "").strip()
            status = str(version_entry.get("status") or "active").strip()
            config_json = version_entry.get("config_json") or {}
            if not version or not entrypoint:
                raise ValueError(f"Agent '{key}' has invalid version entry: {version_entry}")
            if not isinstance(config_json, dict):
                raise ValueError(
                    f"Agent '{key}' version '{version}' has non-object config_json."
                )
            if placeholder_id and config.dry_run:
                version_action = "insert(dry-run)"
            else:
                version_action = client.ensure_agent_version(
                    agent_id=agent_id,
                    version=version,
                    entrypoint=entrypoint,
                    status=status,
                    config_json=config_json,
                    dry_run=config.dry_run,
                )
            version_actions.append(
                {"key": key, "version": version, "action": version_action}
            )
    return {
        "dry_run": config.dry_run,
        "registry_path": str(config.registry_path),
        "agents_processed": len(agent_actions),
        "versions_processed": len(version_actions),
        "agent_actions": agent_actions,
        "version_actions": version_actions,
    }


def sync_from_settings(settings: Optional[Settings] = None, *, dry_run: bool = False) -> Dict[str, Any]:
    return sync_registry(sync_config_from_settings(settings, dry_run=dry_run))
