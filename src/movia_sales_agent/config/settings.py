from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from movia_sales_agent.config.paths import PROJECT_ROOT


def load_environment() -> None:
    local_env = PROJECT_ROOT / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    openai_analysis_model: Optional[str] = Field(default=None, alias="OPENAI_ANALYSIS_MODEL")
    openai_response_model: Optional[str] = Field(default=None, alias="OPENAI_RESPONSE_MODEL")
    openai_eval_model: Optional[str] = Field(default=None, alias="OPENAI_EVAL_MODEL")
    openai_timeout_seconds: float = Field(default=60.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    openai_embedding_dimensions: int = Field(
        default=1536, alias="OPENAI_EMBEDDING_DIMENSIONS"
    )
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    internal_api_key: Optional[str] = Field(default=None, alias="MOVIA_INTERNAL_API_KEY")
    enable_debug_ui: bool = Field(default=False, alias="MOVIA_ENABLE_DEBUG_UI")
    debug_metadata: bool = Field(default=False, alias="MOVIA_DEBUG_METADATA")
    webhook_queue_enabled: bool = Field(default=True, alias="MOVIA_WEBHOOK_QUEUE_ENABLED")
    job_concurrency: int = Field(default=4, alias="MOVIA_JOB_CONCURRENCY")
    lead_batch_window_seconds: float = Field(default=15.0, alias="MOVIA_LEAD_BATCH_WINDOW_SECONDS")
    platform_observability_enabled: bool = Field(
        default=True, alias="MOVIA_PLATFORM_OBSERVABILITY_ENABLED"
    )
    platform_agent_key: str = Field(default="movia_sales_agent", alias="MOVIA_PLATFORM_AGENT_KEY")
    platform_agent_version: Optional[str] = Field(default="v1", alias="MOVIA_PLATFORM_AGENT_VERSION")
    platform_runtime_cache_seconds: int = Field(
        default=30, alias="MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS"
    )
    platform_registry_sync_on_startup: bool = Field(
        default=True, alias="MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP"
    )
    agents_registry_path_value: str = Field(
        default="platform_registry/agents.json", alias="AGENTS_REGISTRY_PATH"
    )
    sync_timeout_seconds: int = Field(default=20, alias="SYNC_TIMEOUT_SECONDS")
    meta_whatsapp_access_token: Optional[str] = Field(
        default=None, alias="META_WHATSAPP_ACCESS_TOKEN"
    )
    meta_whatsapp_phone_number_id: Optional[str] = Field(
        default=None, alias="META_WHATSAPP_PHONE_NUMBER_ID"
    )
    chatwoot_url: Optional[str] = Field(default=None, alias="CHATWOOT_URL")
    chatwoot_api_token: Optional[str] = Field(default=None, alias="CHATWOOT_API_TOKEN")
    chatwoot_account_id: Optional[int] = Field(default=None, alias="CHATWOOT_ACCOUNT_ID")
    disable_openai: bool = Field(default=False, alias="MOVIA_DISABLE_OPENAI")
    disable_database: bool = Field(default=False, alias="MOVIA_DISABLE_DATABASE")

    @property
    def analysis_model(self) -> str:
        return self.openai_analysis_model or self.openai_model

    @property
    def response_model(self) -> str:
        return self.openai_response_model or self.openai_model

    @property
    def eval_model(self) -> str:
        return self.openai_eval_model or self.openai_model

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.meta_whatsapp_access_token and self.meta_whatsapp_phone_number_id)

    @property
    def chatwoot_enabled(self) -> bool:
        return bool(self.chatwoot_url and self.chatwoot_api_token)

    @property
    def agents_registry_path(self) -> Path:
        path = Path(self.agents_registry_path_value)
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_environment()
    return Settings()
