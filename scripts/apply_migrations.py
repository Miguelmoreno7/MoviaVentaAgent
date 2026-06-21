#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_ROOT = PROJECT_ROOT / "supabase" / "migrations"
FALLBACK_ENV = Path("/Users/miguelmoreno/developer/Movia/MoviaVentaAgente/.env")


def load_env() -> None:
    if (PROJECT_ROOT / ".env").exists():
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    elif FALLBACK_ENV.exists():
        load_dotenv(FALLBACK_ENV, override=False)


def main() -> int:
    load_env()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is missing; cannot apply migrations.", file=sys.stderr)
        return 1
    migration_files = sorted(MIGRATIONS_ROOT.glob("*.sql"))
    if not migration_files:
        print("No migrations found.")
        return 0
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            """
            create table if not exists public.movia_schema_migrations (
              version text primary key,
              applied_at timestamptz not null default now()
            )
            """
        )
        for path in migration_files:
            version = path.stem
            existing = conn.execute(
                "select 1 from public.movia_schema_migrations where version = %s",
                (version,),
            ).fetchone()
            if existing:
                print(f"skip {version}")
                continue
            print(f"apply {version}")
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "insert into public.movia_schema_migrations (version) values (%s)",
                (version,),
            )
    print("migrations complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

