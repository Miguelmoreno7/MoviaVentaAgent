from __future__ import annotations

from typing import Any, Dict, List


def compact_retrieval_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "structured_sources": metadata.get("structured_sources") or [],
        "json_sources": metadata.get("json_sources") or [],
        "rag_chunk_count": metadata.get("rag_chunk_count") or 0,
        "conversation_memory_lookup": metadata.get("conversation_memory_lookup"),
    }


def compact_lead_state(lead_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "current_stage": lead_state.get("current_stage"),
        "previous_stage": lead_state.get("previous_stage"),
        "conversation_mode": lead_state.get("conversation_mode"),
        "last_action": lead_state.get("last_action"),
    }


def compact_knowledge_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "knowledge_needs": plan.get("knowledge_needs") or [],
        "structured_sources": plan.get("structured_sources") or [],
        "json_sources": plan.get("json_sources") or [],
        "needs_rag": bool(plan.get("needs_rag")),
    }


def compact_response_metadata(
    metadata: Dict[str, Any],
    *,
    action: str,
    selected_action: Dict[str, Any],
    knowledge_plan: Dict[str, Any],
    token_usage: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "response_source": metadata.get("response_source"),
        "action": action,
        "macro_action": selected_action.get("macro_action"),
        "micro_action": selected_action.get("micro_action"),
        "reason_code": selected_action.get("reason_code"),
        "message_count": metadata.get("message_count"),
        "structured_context_keys": metadata.get("structured_context_keys") or [],
        "json_context_keys": metadata.get("json_context_keys") or [],
        "knowledge_needs": knowledge_plan.get("knowledge_needs") or [],
        "token_total": (token_usage.get("total") or {}).get("total_tokens", 0),
        "fallback": metadata.get("response_source") == "fallback",
        "memory_validation": {
            "corrected": (metadata.get("memory_validation") or {}).get("corrected", False),
            "violation_count": len((metadata.get("memory_validation") or {}).get("violations") or []),
        },
    }


def compact_token_usage(token_usage: Dict[str, Any]) -> Dict[str, Any]:
    return {"total": token_usage.get("total") or {}}


def compact_retrieved_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "title": source.get("title"),
            "source_path": source.get("source_path"),
            "similarity": source.get("similarity"),
        }
        for source in sources or []
    ]
