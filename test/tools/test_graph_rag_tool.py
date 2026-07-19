from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest

from app.config import get_graph_rag_settings, reset_graph_rag_settings_cache
from tool_box.cache import ToolCache
from tool_box.tools_impl import graph_rag as graph_module
from tool_box.tools_impl.graph_rag.service import (
    check_graph_rag_health,
    reset_graph_rag_service,
)


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_data: Any = None,
        *,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or ("" if json_data is None else str(json_data))

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self) -> Any:
        return self._json_data


class _FakeAsyncClient:
    def __init__(
        self,
        *,
        timeout: float,
        responses: List[Any],
        calls: List[Dict[str, Any]],
    ) -> None:
        self.timeout = timeout
        self._responses = responses
        self._calls = calls

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, **kwargs: Any) -> Any:
        self._calls.append({
            "method": "GET",
            "url": url,
            "kwargs": kwargs,
            "timeout": self.timeout,
        })
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, url: str, **kwargs: Any) -> Any:
        self._calls.append({
            "method": "POST",
            "url": url,
            "kwargs": kwargs,
            "timeout": self.timeout,
        })
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def _reset_graph_rag_env(monkeypatch):
    monkeypatch.delenv("MULTIRAG_BASE_URL", raising=False)
    monkeypatch.delenv("MULTIRAG_API_KEY", raising=False)
    monkeypatch.delenv("MULTIRAG_QUERY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MULTIRAG_HEALTH_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MULTIRAG_HEALTH_CACHE_TTL", raising=False)
    monkeypatch.delenv("GRAPH_RAG_CACHE_TTL", raising=False)
    monkeypatch.delenv("GRAPH_RAG_TOP_K", raising=False)
    monkeypatch.delenv("GRAPH_RAG_MAX_CHUNKS", raising=False)
    monkeypatch.delenv("GRAPH_RAG_MAX_REFERENCES", raising=False)
    reset_graph_rag_settings_cache()
    reset_graph_rag_service()
    yield
    reset_graph_rag_settings_cache()
    reset_graph_rag_service()


@pytest.fixture()
def isolated_graph_cache(monkeypatch):
    cache = ToolCache()

    async def _fake_get_memory_cache() -> ToolCache:
        return cache

    monkeypatch.setattr(graph_module, "get_memory_cache", _fake_get_memory_cache)
    return cache


def _patch_async_client(monkeypatch, responses: List[Any], calls: List[Dict[str, Any]]) -> None:
    def _factory(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        timeout = kwargs.get("timeout", 0.0)
        return _FakeAsyncClient(timeout=timeout, responses=responses, calls=calls)

    monkeypatch.setattr("tool_box.tools_impl.graph_rag.service.httpx.AsyncClient", _factory)


@pytest.mark.asyncio
async def test_graph_rag_handler_requires_query(isolated_graph_cache):
    result = await graph_module.graph_rag_handler(query="  ")
    assert result["success"] is False
    assert result["code"] == "missing_query"


@pytest.mark.asyncio
async def test_graph_rag_handler_rejects_invalid_mode(monkeypatch, isolated_graph_cache):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://example.com")
    monkeypatch.setenv("MULTIRAG_API_KEY", "secret")
    reset_graph_rag_settings_cache()

    result = await graph_module.graph_rag_handler(query="test", mode="bad-mode")
    assert result["success"] is False
    assert result["code"] == "invalid_mode"


@pytest.mark.asyncio
async def test_graph_rag_handler_requires_configuration(isolated_graph_cache):
    result = await graph_module.graph_rag_handler(query="test query")
    assert result["success"] is False
    assert result["code"] == "missing_config"


@pytest.mark.asyncio
async def test_graph_rag_handler_success_and_cache(monkeypatch, isolated_graph_cache):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        _FakeResponse(
            200,
            {
                "response": "回答：batch effect 的核心处理流程",
                "references": [
                    {
                        "reference_id": "1",
                        "file_path": "batch-effect.md",
                        "shard": "03",
                    }
                ],
                "metadata": {
                    "shards_total": 8,
                    "shards_ok": 8,
                    "query_mode": "mix",
                },
            },
        )
    ]
    _patch_async_client(monkeypatch, responses, calls)

    first = await graph_module.graph_rag_handler(query="batch effect")
    second = await graph_module.graph_rag_handler(query="batch effect")

    assert first["success"] is True
    assert first["result"]["backend"] == "lightrag_8_shard"
    assert first["result"]["mode"] == "mix"
    assert first["result"]["response"].startswith("回答")
    assert first["result"]["trace"]["references"][0]["shard"] == "03"
    assert first["result"]["trace"]["metadata"]["shards_ok"] == 8
    assert second["cache_hit"] is True
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "http://multirag.local/query"
    assert calls[0]["kwargs"]["json"] == {
        "query": "batch effect",
        "mode": "mix",
        "top_k": 2,
        "max_chunks": 24,
        "max_references": 32,
    }
    assert calls[0]["kwargs"]["headers"]["X-API-Key"] == "server-key"


@pytest.mark.asyncio
async def test_graph_rag_handler_does_not_cache_failures(monkeypatch, isolated_graph_cache):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        _FakeResponse(503, {"success": False, "error": "upstream unavailable"}),
        _FakeResponse(
            200,
            {
                "response": "ok",
                "references": [],
                "metadata": {"query_mode": "hybrid"},
            },
        ),
    ]
    _patch_async_client(monkeypatch, responses, calls)

    first = await graph_module.graph_rag_handler(query="batch effect", mode="hybrid")
    second = await graph_module.graph_rag_handler(query="batch effect", mode="hybrid")

    assert first["success"] is False
    assert first["code"] == "service_unavailable"
    assert second["success"] is True
    assert "cache_hit" not in second
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "payload", "expected_code"),
    [
        (401, {"success": False, "error": "bad key"}, "invalid_api_key"),
        (403, {"detail": "Invalid API Key"}, "invalid_api_key"),
        (422, {"detail": "invalid request"}, "request_error"),
        (413, {"success": False, "error": "too large"}, "request_too_large"),
        (429, {"success": False, "error": "slow down"}, "rate_limit"),
        (503, {"success": False, "error": "temporarily unavailable"}, "service_unavailable"),
    ],
)
async def test_graph_rag_handler_maps_http_errors(
    monkeypatch,
    isolated_graph_cache,
    status_code: int,
    payload: Dict[str, Any],
    expected_code: str,
):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [_FakeResponse(status_code, payload)]
    _patch_async_client(monkeypatch, responses, calls)

    result = await graph_module.graph_rag_handler(query="batch effect")
    assert result["success"] is False
    assert result["code"] == expected_code


@pytest.mark.asyncio
async def test_graph_rag_handler_maps_timeout(monkeypatch, isolated_graph_cache):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [httpx.TimeoutException("timeout")]
    _patch_async_client(monkeypatch, responses, calls)

    result = await graph_module.graph_rag_handler(query="batch effect")
    assert result["success"] is False
    assert result["code"] == "query_timeout"


@pytest.mark.asyncio
async def test_check_graph_rag_health_uses_get_without_api_key(monkeypatch):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        _FakeResponse(
            200,
            {
                "status": "healthy",
                "shards_total": 8,
                "shards_ok": 8,
                "shards": [],
            },
        )
    ]
    _patch_async_client(monkeypatch, responses, calls)

    health = await check_graph_rag_health(get_graph_rag_settings())
    assert health["success"] is True
    assert health["shards_total"] == 8
    assert health["shards_ok"] == 8
    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "http://multirag.local/health"
    assert "headers" not in calls[0]["kwargs"]


@pytest.mark.asyncio
async def test_check_graph_rag_health_is_cached(monkeypatch):
    monkeypatch.setenv("MULTIRAG_BASE_URL", "http://multirag.local")
    monkeypatch.setenv("MULTIRAG_API_KEY", "server-key")
    monkeypatch.setenv("MULTIRAG_HEALTH_CACHE_TTL", "60")
    reset_graph_rag_settings_cache()

    calls: List[Dict[str, Any]] = []
    responses: List[Any] = [
        _FakeResponse(200, {"status": "healthy", "shards_total": 8, "shards_ok": 8}),
    ]
    _patch_async_client(monkeypatch, responses, calls)

    settings = get_graph_rag_settings()
    first = await check_graph_rag_health(settings)
    second = await check_graph_rag_health(settings)

    assert first["success"] is True
    assert second["success"] is True
    assert len(calls) == 1
