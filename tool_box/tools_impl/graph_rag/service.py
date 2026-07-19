from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.config import GraphRAGSettings

from .exceptions import GraphRAGError

logger = logging.getLogger(__name__)

ALLOWED_GRAPH_RAG_MODES = ("mix", "local", "global", "hybrid", "naive", "bypass")


@dataclass(slots=True)
class _HealthState:
    payload: Dict[str, Any]
    timestamp: float


_HEALTH_STATE: Optional[_HealthState] = None
_HEALTH_LOCK = asyncio.Lock()


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _validate_settings(settings: GraphRAGSettings) -> None:
    if not settings.base_url or not settings.api_key:
        raise GraphRAGError(
            "Missing LightRAG configuration: set MULTIRAG_BASE_URL and MULTIRAG_API_KEY.",
            code="missing_config",
        )


def _health_cache_valid(settings: GraphRAGSettings) -> bool:
    if _HEALTH_STATE is None:
        return False
    return (time.time() - _HEALTH_STATE.timestamp) <= settings.health_cache_ttl


def _map_query_status(status_code: int, message: str) -> GraphRAGError:
    if status_code in {401, 403}:
        return GraphRAGError(message, code="invalid_api_key")
    if status_code == 413:
        return GraphRAGError(message, code="request_too_large")
    if status_code == 429:
        return GraphRAGError(message, code="rate_limit")
    if status_code >= 500:
        return GraphRAGError(message, code="service_unavailable")
    return GraphRAGError(message, code="request_error")


def _extract_error_text(response: httpx.Response, payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    text = response.text.strip()
    if text:
        return text
    return f"HTTP {response.status_code}"


async def _parse_json_response(response: httpx.Response) -> Any:
    content = response.content
    if not content:
        return {}
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise GraphRAGError(
            f"Invalid LightRAG JSON response: {exc}",
            code="request_error",
        ) from exc


async def check_graph_rag_health(
    settings: GraphRAGSettings,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    global _HEALTH_STATE

    configured = bool(settings.base_url and settings.api_key)
    base_payload: Dict[str, Any] = {
        "configured": configured,
        "base_url": settings.base_url,
        "has_api_key": bool(settings.api_key),
        "success": False,
    }

    if not settings.base_url:
        return {
            **base_payload,
            "error": "Missing MULTIRAG_BASE_URL",
            "code": "missing_config",
        }

    async with _HEALTH_LOCK:
        if not force and _health_cache_valid(settings):
            return dict(_HEALTH_STATE.payload)  # type: ignore[union-attr]

        url = f"{_normalize_base_url(settings.base_url)}/health"
        try:
            async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
                response = await client.get(url)
            payload = await _parse_json_response(response)
            success = response.status_code == 200 and isinstance(payload, dict)
            result = {
                **base_payload,
                "success": success,
                "status_code": response.status_code,
            }
            if isinstance(payload, dict):
                result.update(payload)
            if not success and "error" not in result:
                result["error"] = _extract_error_text(response, payload)
                result["code"] = "service_unavailable"
        except httpx.TimeoutException:
            result = {
                **base_payload,
                "error": "LightRAG health check timed out.",
                "code": "query_timeout",
            }
        except httpx.HTTPError as exc:
            result = {
                **base_payload,
                "error": f"LightRAG health check failed: {exc}",
                "code": "service_unavailable",
            }
        except GraphRAGError as exc:
            result = {
                **base_payload,
                "error": exc.message,
                "code": exc.code,
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("LightRAG health check failed unexpectedly: %s", exc)
            result = {
                **base_payload,
                "error": str(exc),
                "code": "unexpected_error",
            }

        _HEALTH_STATE = _HealthState(payload=result, timestamp=time.time())
        return dict(result)


async def query_graph_rag(
    *,
    settings: GraphRAGSettings,
    query: str,
    mode: str,
) -> Dict[str, Any]:
    _validate_settings(settings)

    url = f"{_normalize_base_url(settings.base_url)}/query"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": settings.api_key,
    }
    payload = {
        "query": query,
        "mode": mode,
        "top_k": settings.top_k,
        "max_chunks": settings.max_chunks,
        "max_references": settings.max_references,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.query_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
        data = await _parse_json_response(response)
    except httpx.TimeoutException as exc:
        raise GraphRAGError(
            "LightRAG query timed out.",
            code="query_timeout",
        ) from exc
    except httpx.HTTPError as exc:
        raise GraphRAGError(
            f"LightRAG request failed: {exc}",
            code="service_unavailable",
        ) from exc

    if response.status_code >= 400:
        message = _extract_error_text(response, data)
        raise _map_query_status(response.status_code, message)

    if not isinstance(data, dict):
        raise GraphRAGError(
            "Invalid LightRAG response payload.",
            code="request_error",
        )

    response_text = data.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        raise GraphRAGError(
            "LightRAG query returned an empty response.",
            code="request_error",
        )

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    references = data.get("references") if isinstance(data.get("references"), list) else []

    return {
        "backend": "lightrag_8_shard",
        "mode": str(metadata.get("query_mode") or mode),
        "response": response_text.strip(),
        "trace": {
            "references": references,
            "metadata": metadata,
        },
    }


def reset_graph_rag_service() -> None:
    global _HEALTH_STATE
    _HEALTH_STATE = None
