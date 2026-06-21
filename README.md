# MovIA Sales Agent

Python implementation of MovIA's conversational pre-sales agent using LangGraph,
Supabase/Postgres, pgvector RAG, OpenAI, optional Redis memory, and a WhatsApp
webhook endpoint intended to receive messages from the existing dispatcher.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

Fill `.env` with Supabase and OpenAI credentials. Redis and Meta WhatsApp
send credentials are optional for local testing. This service only exposes the
dispatcher-facing `POST /webhooks/whatsapp` receiver.

## Database

```bash
python scripts/apply_migrations.py
python scripts/seed_database.py
python scripts/ingest_rag.py
```

## Local API

```bash
uvicorn movia_sales_agent.api.main:app --reload
```

Manual chat endpoint:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "content-type: application/json" \
  -H "x-movia-internal-api-key: $MOVIA_INTERNAL_API_KEY" \
  -d '{"lead_external_id":"local-1","message":"¿Cuánto cuesta?"}'
```

The local tester UI and `/chat` are protected by `MOVIA_INTERNAL_API_KEY`.
Set `MOVIA_ENABLE_DEBUG_UI=true` to expose `/` and `/frontend/*` for manual
testing. Keep it false in production.

## Redis

Redis is optional locally. Without `REDIS_URL`, the app uses in-memory buffers.

To test with local Redis:

```bash
docker compose -f docker-compose.redis.yml up -d
```

Use this in `.env` when running the API on your machine:

```bash
REDIS_URL=redis://localhost:6379/0
```

If the API runs in Docker on the same compose network as the `redis` service,
use the service name instead of `localhost`:

```bash
REDIS_URL=redis://redis:6379/0
```

In Dokploy, if Redis is deployed as a service in the same project/network, use
the internal Redis service hostname, for example:

```bash
REDIS_URL=redis://redis:6379/0
```

If Dokploy gives you a managed/external Redis URL, paste that exact value. Use
`rediss://...` when the provider requires TLS.

## Production webhook runtime

The WhatsApp webhook is fast-ack by default. `POST /webhooks/whatsapp` parses
inbound messages, enqueues them, and returns without waiting for OpenAI,
Postgres, or Meta outbound sends. Background workers process queued batches.

Recommended production values:

```bash
MOVIA_WEBHOOK_QUEUE_ENABLED=true
MOVIA_JOB_CONCURRENCY=4
MOVIA_LEAD_BATCH_WINDOW_SECONDS=15
MOVIA_DEBUG_METADATA=false
MOVIA_ENABLE_DEBUG_UI=false
MOVIA_INTERNAL_API_KEY=<strong-internal-token>
MOVIA_PLATFORM_OBSERVABILITY_ENABLED=true
MOVIA_PLATFORM_AGENT_KEY=movia_sales_agent
MOVIA_PLATFORM_AGENT_VERSION=v1
MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS=30
MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=true
AGENTS_REGISTRY_PATH=platform_registry/agents.json
SYNC_TIMEOUT_SECONDS=20
```

Messages from the same lead inside the batch window are combined into one agent
run. Different leads can run concurrently up to `MOVIA_JOB_CONCURRENCY`.

## Platform registry and observability

The service can register itself in the MovIA platform tables and report compact
run observability for WhatsApp worker batches. Platform observability uses the
same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as the rest of the app.

By default, `MOVIA_PLATFORM_REGISTRY_SYNC_ON_STARTUP=true` runs the registry
sync once during API startup. This is intended for Dokploy deployments where
you only click Deploy and do not have a separate shell step. Startup sync is
best-effort: if it fails, the API still starts and `/health` reports
`platform_registry_sync_status=failed`.

Dry-run registry sync:

```bash
movia-platform-sync --dry-run
```

Apply registry sync:

```bash
movia-platform-sync
```

The platform `agents.enabled` flag is authoritative. Runtime metadata is cached
for `MOVIA_PLATFORM_RUNTIME_CACHE_SECONDS` to avoid one Supabase lookup per
message burst. Run/event writes are best-effort and should not block successful
agent execution or WhatsApp delivery.

## Model validation

Install the optional evaluation dependencies:

```bash
python -m pip install -e ".[dev,eval]"
```

Validate the five-scenario dataset:

```bash
movia-eval validate-dataset
```

Run one scenario or the complete 60-turn scripted suite:

```bash
movia-eval run --scenario MOVIA-VAL-001
movia-eval run --scenario all
```

The runner uses unique leads under `channel=evaluation`, scores only fields and
sources the current agent can emit, and excludes unsupported expectations from
score denominators. It uses RAGAS only when RAG context was retrieved and uses
DeepEval for conversation-level metrics.

Reports are written to `artifacts/evaluations/<run-id>/`:

- `summary.md`: concise human-readable results.
- `run.json`: complete machine-readable run.
- `turns.jsonl`: one record per evaluated user turn.

Useful local and CI options:

```bash
# Exercise the complete harness without OpenAI or database calls.
movia-eval run --offline --scenario all --no-fail-exit

# Replay the real agent without judge-model calls.
movia-eval run --scenario all --skip-ragas --skip-deepeval --no-fail-exit
```

Set `OPENAI_EVAL_MODEL` to use a separate judge model. When omitted, evaluation
uses `OPENAI_MODEL`.
