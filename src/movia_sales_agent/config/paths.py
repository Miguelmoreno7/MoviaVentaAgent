from __future__ import annotations

from pathlib import Path


def resolve_project_root() -> Path:
    """Resolve repo/app root for editable installs and Docker package installs."""
    package_root = Path(__file__).resolve().parents[3]
    cwd = Path.cwd().resolve()
    markers = (
        "platform_registry/agents.json",
        "docs/movia_knowledge_source",
        "pyproject.toml",
    )
    for candidate in (cwd, package_root):
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return package_root


PROJECT_ROOT = resolve_project_root()
KNOWLEDGE_ROOT = PROJECT_ROOT / "docs" / "movia_knowledge_source"
CONFIG_ROOT = KNOWLEDGE_ROOT / "config"
RAG_DOCS_ROOT = KNOWLEDGE_ROOT / "rag_docs"
MIGRATIONS_ROOT = PROJECT_ROOT / "supabase" / "migrations"
