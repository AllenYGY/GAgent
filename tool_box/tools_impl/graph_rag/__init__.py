"""
Graph RAG tool backed by the 8-shard LightRAG gateway.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import get_graph_rag_settings
from tool_box.cache import get_memory_cache

from .exceptions import GraphRAGError
from .service import ALLOWED_GRAPH_RAG_MODES, query_graph_rag

logger = logging.getLogger(__name__)


def _normalize_mode(raw: Any) -> str:
    mode = str(raw or "mix").strip().lower()
    if mode not in ALLOWED_GRAPH_RAG_MODES:
        raise GraphRAGError(
            f"Unsupported graph_rag mode: {mode}",
            code="invalid_mode",
        )
    return mode


async def graph_rag_handler(
    *,
    query: str,
    mode: str = "mix",
) -> Dict[str, Any]:
    query_text = (query or "").strip()
    if not query_text:
        return {
            "query": query,
            "success": False,
            "error": "Graph RAG requires a non-empty query.",
            "code": "missing_query",
        }

    try:
        normalized_mode = _normalize_mode(mode)
    except GraphRAGError as exc:
        return {
            "query": query_text,
            "success": False,
            "error": exc.message,
            "code": exc.code,
        }

    settings = get_graph_rag_settings()
    params = {
        "query": query_text,
        "mode": normalized_mode,
        "top_k": settings.top_k,
        "max_chunks": settings.max_chunks,
        "max_references": settings.max_references,
    }

    cache = await get_memory_cache()
    cached = await cache.get("graph_rag", params)
    if cached:
        return dict(cached, cache_hit=True)

    try:
        result = await query_graph_rag(
            settings=settings,
            query=query_text,
            mode=normalized_mode,
        )
    except GraphRAGError as exc:
        logger.warning("Graph RAG execution failed: %s", exc.message)
        return {
            "query": query_text,
            "success": False,
            "error": exc.message,
            "code": exc.code,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected Graph RAG failure")
        return {
            "query": query_text,
            "success": False,
            "error": str(exc),
            "code": "unexpected_error",
        }

    payload = {
        "query": query_text,
        "success": True,
        "result": result,
    }
    await cache.set("graph_rag", params, payload, ttl=settings.cache_ttl)
    return payload


graph_rag_tool = {
    "name": "graph_rag",
    "description": "Query the 8-shard LightRAG backend and return the final answer plus trace data.",
    "category": "knowledge_graph",
    "parameters_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "User query for LightRAG.",
            },
            "mode": {
                "type": "string",
                "enum": list(ALLOWED_GRAPH_RAG_MODES),
                "default": "mix",
                "description": "LightRAG retrieval mode.",
            },
        },
        "required": ["query"],
    },
    "handler": graph_rag_handler,
    "tags": ["knowledge", "graph", "rag", "lightrag"],
    "examples": [
        "噬菌体和水产养殖有什么关系",
        "what is BACTERIOPHAGE",
    ],
}

__all__ = ["graph_rag_tool", "graph_rag_handler"]
