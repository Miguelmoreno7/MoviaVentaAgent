#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
FALLBACK_ENV = Path("/Users/miguelmoreno/developer/Movia/MoviaVentaAgente/.env")
sys.path.insert(0, str(SRC_ROOT))

from movia_sales_agent.config.knowledge import iter_rag_documents  # noqa: E402
from movia_sales_agent.config.settings import Settings  # noqa: E402
from movia_sales_agent.ingestion.chunker import build_document_records  # noqa: E402
from movia_sales_agent.services.openai_service import OpenAIService  # noqa: E402


def load_env() -> None:
    if (PROJECT_ROOT / ".env").exists():
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    elif FALLBACK_ENV.exists():
        load_dotenv(FALLBACK_ENV, override=False)


def vector_literal(values: List[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def upsert_document(conn, record: Dict[str, Any]) -> str:
    row = conn.execute(
        """
        insert into public.movia_knowledge_documents (
          source_path, title, source_type, content_hash, metadata, approved, last_ingested_at
        )
        values (%s, %s, %s, %s, %s::jsonb, true, now())
        on conflict (source_path) do update set
          title = excluded.title,
          source_type = excluded.source_type,
          content_hash = excluded.content_hash,
          metadata = excluded.metadata,
          approved = excluded.approved,
          last_ingested_at = now()
        returning id
        """,
        (
            record["source_path"],
            record["title"],
            record["source_type"],
            record["content_hash"],
            json.dumps(record["metadata"], ensure_ascii=False),
        ),
    ).fetchone()
    return str(row["id"])


def main() -> int:
    load_env()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is missing; cannot ingest RAG.", file=sys.stderr)
        return 1
    settings = Settings()
    openai_service = OpenAIService(settings)
    if not openai_service.enabled:
        print("OPENAI_API_KEY is missing; cannot create embeddings.", file=sys.stderr)
        return 1
    records = build_document_records(iter_rag_documents())
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        for record in records:
            document_id = upsert_document(conn, record)
            chunks = record["chunks"]
            embeddings = openai_service.embed([str(chunk["content"]) for chunk in chunks])
            conn.execute(
                "delete from public.movia_knowledge_chunks where document_id = %s",
                (document_id,),
            )
            for chunk, embedding in zip(chunks, embeddings):
                conn.execute(
                    """
                    insert into public.movia_knowledge_chunks (
                      document_id, chunk_index, content, token_estimate, metadata, embedding
                    )
                    values (%s, %s, %s, %s, %s::jsonb, %s::vector)
                    """,
                    (
                        document_id,
                        chunk["chunk_index"],
                        chunk["content"],
                        chunk["token_estimate"],
                        json.dumps(chunk["metadata"], ensure_ascii=False),
                        vector_literal(embedding),
                    ),
                )
            print(f"ingested {record['source_path']} ({len(chunks)} chunks)")
    print("rag ingestion complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

