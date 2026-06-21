from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_ROOT = PROJECT_ROOT / "docs" / "movia_knowledge_source"
CONFIG_ROOT = KNOWLEDGE_ROOT / "config"
RAG_DOCS_ROOT = KNOWLEDGE_ROOT / "rag_docs"
MIGRATIONS_ROOT = PROJECT_ROOT / "supabase" / "migrations"

