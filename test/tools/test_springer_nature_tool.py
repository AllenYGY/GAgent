from __future__ import annotations

import pytest

from app.config import reset_springer_settings_cache
from tool_box.tools_impl import springer_nature as springer


@pytest.fixture(autouse=True)
def _reset_springer_env(monkeypatch):
    monkeypatch.delenv("SPRINGER_META_API_KEY", raising=False)
    monkeypatch.delenv("SPRINGER_OPENACCESS_API_KEY", raising=False)
    reset_springer_settings_cache()
    yield
    reset_springer_settings_cache()


@pytest.mark.asyncio
async def test_springer_nature_handler_requires_query():
    result = await springer.springer_nature_handler(api="meta", q="  ")
    assert result["success"] is False
    assert result["code"] == "missing_query"


@pytest.mark.asyncio
async def test_springer_nature_handler_invalid_api():
    result = await springer.springer_nature_handler(api="tdm", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "invalid_request"
    assert "Unsupported api" in result["error"]


@pytest.mark.asyncio
async def test_springer_nature_handler_metadata_unsupported():
    result = await springer.springer_nature_handler(api="metadata", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "invalid_request"
    assert "Unsupported api" in result["error"]


@pytest.mark.asyncio
async def test_springer_nature_handler_missing_api_key():
    result = await springer.springer_nature_handler(api="meta", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "invalid_request"
    assert "SPRINGER_META_API_KEY" in result["error"]


@pytest.mark.asyncio
async def test_springer_nature_handler_success(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()
    captured = {}

    def fake_run_search(api_name, api_key, query, p, s, fetch_all, is_premium):
        captured["api_name"] = api_name
        captured["api_key"] = api_key
        captured["query"] = query
        captured["p"] = p
        captured["s"] = s
        captured["fetch_all"] = fetch_all
        captured["is_premium"] = is_premium
        return {"records": [{"title": "One"}, {"title": "Two"}]}

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(
        api="meta",
        q="keyword:test",
        p="5",
        s="2",
        fetch_all=True,
        is_premium=True,
    )
    assert result["success"] is True
    assert result["record_count"] == 2
    assert captured["api_name"] == "meta"
    assert captured["api_key"] == "meta-key"
    assert captured["query"] == "keyword:test"
    assert captured["p"] == 5
    assert captured["s"] == 2
    assert captured["fetch_all"] is True
    assert captured["is_premium"] is False


@pytest.mark.asyncio
async def test_springer_nature_handler_openaccess_override_key(monkeypatch):
    captured = {}

    def fake_run_search(api_name, api_key, query, p, s, fetch_all, is_premium):
        captured["api_name"] = api_name
        captured["api_key"] = api_key
        return {"records": []}

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(
        api="openaccess",
        q="doi:10.1000/xyz123",
        api_key="override-key",
    )
    assert result["success"] is True
    assert result["record_count"] == 0
    assert captured["api_name"] == "openaccess"
    assert captured["api_key"] == "override-key"


@pytest.mark.asyncio
async def test_springer_nature_handler_basic_sanitizes_query(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()
    calls = []

    def fake_run_search(api_name, api_key, query, p, s, fetch_all, is_premium):
        calls.append(query)
        return {"records": [{"title": "Fallback"}]}

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(
        api="meta", q="batch effect AND correction sort:date"
    )
    assert result["success"] is True
    assert result["fallback_reason"] == "basic_plan_simplified"
    assert result["original_query"] == "batch effect AND correction sort:date"
    assert result["query"] == "batch effect AND correction"
    assert calls == ["batch effect AND correction"]


@pytest.mark.asyncio
async def test_springer_nature_handler_field_constraint_fallback(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()
    calls = []

    def fake_run_search(api_name, api_key, query, p, s, fetch_all, is_premium):
        calls.append(query)
        if "subject:" in query:
            raise springer.APIRequestError("403 Client Error: Forbidden")
        return {"records": [{"title": "Fallback"}]}

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    query = 'subject:"Bioinformatics" AND ("batch effect" OR "batch correction")'
    result = await springer.springer_nature_handler(api="meta", q=query)
    assert result["success"] is True
    assert result["fallback_reason"] == "field_constraints_removed"
    assert result["original_query"] == query
    assert result["query"] == '"Bioinformatics" AND ("batch effect" OR "batch correction")'
    assert calls == [
        query,
        '"Bioinformatics" AND ("batch effect" OR "batch correction")',
    ]


@pytest.mark.asyncio
async def test_springer_nature_handler_invalid_api_key(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()

    def fake_run_search(*_args, **_kwargs):
        raise springer.InvalidAPIKeyError("bad key")

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(api="meta", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_springer_nature_handler_rate_limit(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()

    def fake_run_search(*_args, **_kwargs):
        raise springer.RateLimitExceededError("rate limit")

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(api="meta", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "rate_limit"


@pytest.mark.asyncio
async def test_springer_nature_handler_request_error(monkeypatch):
    monkeypatch.setenv("SPRINGER_META_API_KEY", "meta-key")
    reset_springer_settings_cache()

    def fake_run_search(*_args, **_kwargs):
        raise springer.APIRequestError("request failed")

    monkeypatch.setattr(springer, "_run_search", fake_run_search)

    result = await springer.springer_nature_handler(api="meta", q="keyword:test")
    assert result["success"] is False
    assert result["code"] == "request_error"
