from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from movia_sales_agent.agent.rag_policy import MIN_RAG_SIMILARITY
from movia_sales_agent.config.knowledge import iter_rag_documents
from movia_sales_agent.db.repository import MoviaRepository
from movia_sales_agent.ingestion.chunker import build_document_records
from movia_sales_agent.memory.store import MemoryStore
from movia_sales_agent.services.openai_service import OpenAIService


class RagService:
    def __init__(
        self,
        repository: MoviaRepository,
        openai_service: OpenAIService,
        memory: MemoryStore,
    ):
        self.repository = repository
        self.openai_service = openai_service
        self.memory = memory

    def retrieve(self, queries: List[str], match_count: int = 3) -> List[Dict[str, Any]]:
        contexts, _usage = self.retrieve_with_usage(queries, match_count)
        return contexts

    def retrieve_with_usage(
        self,
        queries: List[str],
        match_count: int = 3,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not queries:
            return [], {
                "operation": "embedding",
                "model": self.openai_service.settings.openai_embedding_model,
                "provider": "none",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        filter_key = str(sorted((metadata_filter or {}).items()))
        cache_key = (
            "rag:"
            + "|".join(queries).lower()
            + ":"
            + filter_key
            + f":min={MIN_RAG_SIMILARITY}"
        )
        cached = self.memory.get_cache(cache_key)
        if cached is not None:
            return cached, {
                "operation": "embedding",
                "model": self.openai_service.settings.openai_embedding_model,
                "provider": "cache",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        contexts: List[Dict[str, Any]] = []
        usage: Dict[str, Any]
        if self.repository.enabled and self.openai_service.enabled:
            embeddings, usage = self.openai_service.embed_with_usage(queries)
            seen = set()
            for embedding in embeddings:
                rows = self.repository.match_knowledge(
                    embedding, match_count=match_count, metadata_filter=metadata_filter
                )
                for row in rows:
                    if row["id"] in seen:
                        continue
                    seen.add(row["id"])
                    contexts.append(row)
        else:
            contexts = self._local_keyword_search(queries, match_count, metadata_filter)
            usage = {
                "operation": "embedding",
                "model": self.openai_service.settings.openai_embedding_model,
                "provider": "fallback",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        contexts = filter_relevant_contexts(contexts)
        self.memory.set_cache(cache_key, contexts, ttl_seconds=300)
        return contexts, usage

    def _local_keyword_search(
        self,
        queries: List[str],
        match_count: int,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        records = build_document_records(iter_rag_documents())
        words = {
            word
            for query in queries
            for word in _tokenize(query)
            if len(word) > 3
        }
        scored: List[Dict[str, Any]] = []
        for record in records:
            for chunk in record["chunks"]:
                metadata = chunk["metadata"]
                if metadata_filter and not _metadata_matches(metadata, metadata_filter):
                    continue
                content = str(chunk["content"])
                searchable = _normalize_text(f"{record['title']} {content}")
                score = sum(searchable.count(word) for word in words)
                if score:
                    scored.append(
                        {
                            "id": f"{record['source_path']}:{chunk['chunk_index']}",
                            "document_id": str(record["source_path"]),
                            "source_path": str(record["source_path"]),
                            "title": record["title"],
                            "content": content,
                            "metadata": metadata,
                            "similarity": min(0.95, 0.5 + score / 20),
                        }
                    )
        return sorted(scored, key=lambda item: item["similarity"], reverse=True)[:match_count]


def filter_relevant_contexts(
    contexts: List[Dict[str, Any]],
    min_similarity: float = MIN_RAG_SIMILARITY,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    seen = set()
    for context in contexts or []:
        similarity = context.get("similarity")
        if isinstance(similarity, (int, float)) and float(similarity) < min_similarity:
            continue
        key = (
            context.get("id"),
            context.get("source_path"),
            str(context.get("content") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        filtered.append(context)
    return filtered[:3]


def _metadata_matches(metadata: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in (expected or {}).items())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9_]+", _normalize_text(text))


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
