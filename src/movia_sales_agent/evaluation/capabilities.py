from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from movia_sales_agent.config.knowledge import iter_rag_documents, load_config_bundle
from movia_sales_agent.config.paths import RAG_DOCS_ROOT
from movia_sales_agent.contracts.commercial import ObjectionType


STRUCTURED_SOURCE_CAPABILITIES: Set[str] = {
    "postgres.products",
    "postgres.policies",
    "postgres.official_links",
}


def source_capabilities() -> Set[str]:
    capabilities = set(STRUCTURED_SOURCE_CAPABILITIES)
    capabilities.update(f"json.{name}" for name in load_config_bundle())
    capabilities.update(
        f"json.objection_playbook:{objection_type}"
        for objection_type in ObjectionType.values()
        if objection_type != ObjectionType.NONE.value
    )
    capabilities.update(rag_label_for_path(path) for path in iter_rag_documents())
    return capabilities


def emitted_source_labels(
    knowledge_plan: Dict[str, Any],
    retrieved_sources: List[Dict[str, Any]],
) -> Set[str]:
    labels = set(knowledge_plan.get("structured_sources") or [])
    labels.update(f"json.{name}" for name in knowledge_plan.get("json_sources") or [])
    for source in retrieved_sources:
        source_path = source.get("source_path")
        if source_path:
            labels.add(rag_label_for_path(Path(str(source_path))))
    return labels


def rag_label_for_path(path: Path) -> str:
    parts = _rag_relative_parts(path)
    if not parts:
        return "rag.unknown"
    stem = Path(parts[-1]).stem
    topic = parts[0]
    if topic == "overview":
        return "rag.overview"
    return ".".join(["rag", topic, stem])


def _rag_relative_parts(path: Path) -> List[str]:
    normalized = str(path).replace("\\", "/")
    marker = "rag_docs/"
    if marker in normalized:
        return normalized.split(marker, 1)[1].split("/")
    try:
        return list(path.relative_to(RAG_DOCS_ROOT).parts)
    except ValueError:
        return list(path.parts)
