# Platform Agent Registration And Observability Guide

This guide documents how to connect a Python/LangGraph agent to the MovIA platform registry and run observability tables. It is intended as the repeatable checklist for future client agents.

## 1. Required Platform Tables

The platform database must already include the registry and run tracking tables used by the platform service:

- `agents`
- `agent_versions`
- `runs`
- `run_events`

Do not create platform migrations inside each client agent unless the shared platform schema changes. Client agents should only register themselves and write run/event records.

## 2. Required Environment Variables

Every agent service needs these platform variables:

```text
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
MOVIA_PLATFORM_OBSERVABILITY_ENABLED=true
MOVIA_PLATFORM_AGENT_KEY=client_agent_key
MOVIA_PLATFORM_AGENT_VERSION=v1
MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS=30
MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=true
AGENTS_REGISTRY_PATH=platform_registry/agents.json
SYNC_TIMEOUT_SECONDS=20
```

If the agent also receives webhooks or sends WhatsApp/Chatwoot messages, add those variables separately.

Important deployment rule: every new runtime env var must be added in all three places:

- `Settings` or equivalent config object.
- `.env.example`.
- `docker-compose.yml` service `environment` passthrough.

Dokploy only passes variables into the container when the compose file maps them. After changing env vars, recreate/reload the service so cached settings are rebuilt.

## 3. Registry File

Create `platform_registry/agents.json` in the agent repository.

Example:

```json
{
  "agents": [
    {
      "key": "client_agent_key",
      "name": "Client Agent Name",
      "enabled": true,
      "default_version": "v1",
      "versions": [
        {
          "version": "v1",
          "entrypoint": "package.api.main:app",
          "status": "active",
          "config_json": {
            "feature": "whatsapp_agent",
            "webhook_path": "/webhooks/whatsapp",
            "health_path": "/health"
          }
        }
      ]
    }
  ]
}
```

Recommended conventions:

- `key`: lowercase snake case, stable forever.
- `name`: human-readable name shown in the platform.
- `enabled`: default platform switch for this agent.
- `default_version`: usually `v1`.
- `entrypoint`: FastAPI app import path.
- `config_json`: non-secret metadata that helps operators understand how the agent runs.

## 4. Registry Sync

The agent should run registry sync on startup when:

```text
MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=true
```

The startup sync should:

- Read `platform_registry/agents.json`.
- Upsert `agents`.
- Upsert `agent_versions`.
- Never crash the API if sync fails.
- Log the sync result.

For manual sync, expose or keep a CLI command such as:

```bash
movia-platform-sync sync
```

Dry-run mode is recommended for debugging:

```bash
movia-platform-sync sync --dry-run
```

## 5. Runtime Enabled Resolution

The platform enabled flag is authoritative. Before a worker runs the agent, resolve:

- `agent_key`
- requested/default version
- `enabled`
- `agent_id`
- `agent_version_id`

Use a short cache:

```text
MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS=30
```

Recommended behavior:

- If cache is fresh, do not call Supabase again.
- If refresh fails and stale cache exists, use stale cache briefly and log a warning.
- If refresh fails and no cache exists, fail closed: skip the run.
- If `enabled=false`, create/update a cancelled run if possible and do not execute the agent.

## 6. Run Lifecycle

For each inbound job or batch, create one platform run.

Recommended statuses:

```text
running
success
failed
cancelled
```

Minimum `runs` fields to populate:

- `agent_id`
- `agent_version_id`
- `status`
- `input_json`
- `output_json`
- `error_text`
- `total_tokens`
- `total_duration_ms`
- `requested_by`

`input_json` should be compact and safe:

```json
{
  "channel": "whatsapp",
  "from_number": "521...",
  "message_ids": ["wamid..."],
  "batch_count": 1
}
```

Do not store prompts, secrets, full RAG chunks, or private credentials in platform run payloads.

## 7. Recommended Run Events

Use compact lifecycle events instead of internal LangGraph node logs.

Recommended event types:

```text
webhook_received
message_queued
batch_window_started
batch_compacted
platform_runtime_resolved
platform_disabled_skip
agent_started
agent_completed
outbound_send_started
outbound_send_completed
observability_write_failed
run_failed
run_completed
```

For WhatsApp agents, outbound payload can include:

```json
{
  "transport": "chatwoot",
  "fallback_used": false,
  "message_count": 1
}
```

Keep events best-effort. Event write failures must never block agent execution or customer delivery.

## 8. Token Tracking

Every agent response should expose token usage in a machine-readable shape.

Recommended summary:

```json
{
  "total": {
    "input_tokens": 1234,
    "output_tokens": 456,
    "total_tokens": 1690
  }
}
```

Persist `runs.total_tokens` from that response. Store per-call details only when debug metadata is enabled.

## 9. Health Endpoint

`GET /health` should stay public and non-sensitive.

Recommended fields:

```json
{
  "status": "ok",
  "queue_enabled": true,
  "queue_durable": true,
  "platform_observability_enabled": true,
  "platform_registry_sync_status": "success",
  "platform_agent_key": "client_agent_key",
  "platform_runtime_cache_seconds": 30
}
```

Use booleans for integration configuration when helpful, never secrets:

```json
{
  "whatsapp_enabled": true,
  "chatwoot_enabled": true
}
```

## 10. Production Logging

Platform observability is not a replacement for service logs. Keep compact stdout logs for debugging deployments:

```text
webhook_received parsed_messages=1
webhook_enqueue status=queued message_id=...
batch_window_started lead=...
agent_started lead=...
agent_completed action=...
outbound_started lead=...
outbound_completed transport=chatwoot fallback=false
```

Do not log message text, prompts, user private details, API tokens, or full diagnostics by default.

## 11. Docker Compose Checklist

For every env var used by the service, add an explicit passthrough:

```yaml
services:
  client_agent:
    environment:
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY}
      MOVIA_PLATFORM_OBSERVABILITY_ENABLED: ${MOVIA_PLATFORM_OBSERVABILITY_ENABLED:-true}
      MOVIA_PLATFORM_AGENT_KEY: ${MOVIA_PLATFORM_AGENT_KEY:-client_agent_key}
      MOVIA_PLATFORM_AGENT_VERSION: ${MOVIA_PLATFORM_AGENT_VERSION:-v1}
      MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS: ${MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS:-30}
      MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP: ${MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP:-true}
      AGENTS_REGISTRY_PATH: ${AGENTS_REGISTRY_PATH:-platform_registry/agents.json}
      SYNC_TIMEOUT_SECONDS: ${SYNC_TIMEOUT_SECONDS:-20}
```

If using Chatwoot:

```yaml
      CHATWOOT_URL: ${CHATWOOT_URL}
      CHATWOOT_API_TOKEN: ${CHATWOOT_API_TOKEN}
      CHATWOOT_ACCOUNT_ID: ${CHATWOOT_ACCOUNT_ID}
```

If using WhatsApp Cloud API directly:

```yaml
      META_WHATSAPP_ACCESS_TOKEN: ${META_WHATSAPP_ACCESS_TOKEN}
      META_WHATSAPP_PHONE_NUMBER_ID: ${META_WHATSAPP_PHONE_NUMBER_ID}
```

If using Redis queues:

```yaml
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
```

## 12. Acceptance Checklist

Before calling an agent platform-ready:

- `platform_registry/agents.json` exists and validates.
- Startup registry sync succeeds or logs a clear warning.
- `/health` reports platform observability state.
- The platform can toggle the agent with `agents.enabled`.
- Disabled state skips agent execution.
- A successful run creates one `runs` row.
- Run events appear in order.
- Token totals are persisted.
- Event write failures do not block the agent.
- All env vars are present in `.env.example` and `docker-compose.yml`.
- Dokploy service has been recreated after env changes.
