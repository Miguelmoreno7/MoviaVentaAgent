from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Iterable, List

from movia_sales_agent.config.paths import RAG_DOCS_ROOT


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def document_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def metadata_for_path(path: Path) -> Dict[str, object]:
    relative = path.relative_to(RAG_DOCS_ROOT)
    parts = relative.parts
    topic = parts[0] if parts else "general"
    metadata: Dict[str, object] = {
        "topic": topic,
        "channel": "whatsapp",
        "funnel_stage": "pre_purchase",
        "source_type": "rag",
        "approved": True,
        "version": "v1",
        "last_updated": "2026-06-02",
    }
    stem = path.stem
    if topic == "use_cases":
        metadata["industry"] = stem
    elif topic == "comparisons":
        metadata["comparison"] = stem
        metadata["comparison_target"] = stem
    elif topic == "product_explanations":
        metadata["product_explanation"] = stem
        metadata["product"] = stem
    elif topic == "faqs":
        metadata["faq"] = stem
    return metadata


def split_markdown(content: str, max_chars: int = 1200, overlap_chars: int = 120) -> List[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    chunks: List[str] = []
    current = ""
    for block in blocks:
        next_value = f"{current}\n\n{block}".strip() if current else block
        if len(next_value) <= max_chars:
            current = next_value
            continue
        if current:
            chunks.append(current)
        if len(block) <= max_chars:
            current = block
            continue
        for start in range(0, len(block), max_chars - overlap_chars):
            piece = block[start : start + max_chars].strip()
            if piece:
                chunks.append(piece)
        current = ""
    if current:
        chunks.append(current)
    return chunks


def build_document_records(paths: Iterable[Path]) -> List[Dict[str, object]]:
    records = []
    for path in paths:
        content = path.read_text(encoding="utf-8")
        metadata = metadata_for_path(path)
        chunks = [
            {
                "chunk_index": index,
                "content": chunk,
                "token_estimate": estimate_tokens(chunk),
                "metadata": {**metadata, "chunk_index": index},
            }
            for index, chunk in enumerate(split_markdown(content))
        ]
        records.append(
            {
                "path": path,
                "source_path": str(path.relative_to(RAG_DOCS_ROOT.parents[0])),
                "title": document_title(content, path.stem.replace("_", " ").title()),
                "source_type": "rag",
                "content_hash": content_hash(content),
                "metadata": metadata,
                "chunks": chunks,
            }
        )
    return records
