"""
Graph RAG configuration.

The public tool name remains `graph_rag`, but the runtime backend is 8-shard LightRAG.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass(slots=True)
class GraphRAGSettings:
    """8-shard LightRAG-backed Graph RAG configuration."""

    base_url: str = ""
    api_key: str = ""
    query_timeout_seconds: float = 420.0
    health_timeout_seconds: float = 5.0
    health_cache_ttl: int = 60
    cache_ttl: int = 900
    top_k: int = 2
    max_chunks: int = 24
    max_references: int = 32


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _float_env(key: str, default: float) -> float:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(key: str, default: int) -> int:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_graph_rag_settings() -> GraphRAGSettings:
    """Read environment variables and return LightRAG settings."""

    return GraphRAGSettings(
        base_url=_env("MULTIRAG_BASE_URL", "") or "",
        api_key=_env("MULTIRAG_API_KEY", "") or "",
        query_timeout_seconds=max(_float_env("MULTIRAG_QUERY_TIMEOUT_SECONDS", 420.0), 1.0),
        health_timeout_seconds=max(_float_env("MULTIRAG_HEALTH_TIMEOUT_SECONDS", 5.0), 1.0),
        health_cache_ttl=max(_int_env("MULTIRAG_HEALTH_CACHE_TTL", 60), 0),
        cache_ttl=max(_int_env("GRAPH_RAG_CACHE_TTL", 900), 0),
        top_k=max(_int_env("GRAPH_RAG_TOP_K", 2), 1),
        max_chunks=max(_int_env("GRAPH_RAG_MAX_CHUNKS", 24), 1),
        max_references=max(_int_env("GRAPH_RAG_MAX_REFERENCES", 32), 1),
    )


def reset_graph_rag_settings_cache() -> None:
    """Clear cached Graph RAG settings (tests)."""

    get_graph_rag_settings.cache_clear()  # type: ignore[attr-defined]
