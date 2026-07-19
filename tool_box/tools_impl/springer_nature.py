"""
Springer Nature API tool implementation.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Optional

from app.config import get_springer_settings

from springernature_api_client.exceptions import (
    APIRequestError,
    InvalidAPIKeyError,
    RateLimitExceededError,
)
from springernature_api_client.meta import MetaAPI
from springernature_api_client.openaccess import OpenAccessAPI

logger = logging.getLogger(__name__)

_SUPPORTED_APIS = {"meta", "openaccess"}
_SORT_PATTERN = re.compile(r"(?:^|\s)sort:[^\s)]+", re.IGNORECASE)
_FIELD_PATTERN = re.compile(r"\b[\w-]+:(\"[^\"]+\"|\([^)]+\)|[^\s)]+)")
_NEAR_PATTERN = re.compile(r"\bNEAR/\d+\b", re.IGNORECASE)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_api(api: Optional[str]) -> str:
    api_name = (api or "meta").strip().lower()
    if api_name not in _SUPPORTED_APIS:
        raise ValueError(f"Unsupported api: {api_name}")
    return api_name


def _resolve_api_key(api_name: str, api_key: Optional[str]) -> str:
    settings = get_springer_settings()
    selected_key = (api_key or "").strip() or None

    if not selected_key:
        if api_name == "meta":
            selected_key = settings.meta_api_key
        elif api_name == "openaccess":
            selected_key = settings.openaccess_api_key
        else:
            raise ValueError(f"Unsupported api: {api_name}")

    if not selected_key:
        if api_name == "meta":
            raise ValueError("Missing SPRINGER_META_API_KEY")
        raise ValueError("Missing SPRINGER_OPENACCESS_API_KEY")

    return selected_key


def _strip_sort_clause(query: str) -> str:
    stripped = _SORT_PATTERN.sub("", query)
    return " ".join(stripped.split())


def _basic_sanitize_query(query: str) -> str:
    stripped = _SORT_PATTERN.sub("", query)
    stripped = _NEAR_PATTERN.sub(" ", stripped)
    return " ".join(stripped.split())


def _strip_field_constraints(query: str) -> str:
    def _field_repl(match: re.Match[str]) -> str:
        return match.group(1)

    simplified = _FIELD_PATTERN.sub(_field_repl, query)
    simplified = simplified.replace("|", " ")
    simplified = " ".join(simplified.split())
    return simplified


def _run_search(
    api_name: str,
    api_key: str,
    query: str,
    p: int,
    s: int,
    fetch_all: bool,
    is_premium: bool,
) -> Any:
    if api_name == "meta":
        client = MetaAPI(api_key=api_key)
    elif api_name == "openaccess":
        client = OpenAccessAPI(api_key=api_key)
    else:
        raise ValueError(f"Unsupported api: {api_name}")

    return client.search(q=query, p=p, s=s, fetch_all=fetch_all, is_premium=is_premium)


async def springer_nature_handler(
    api: str = "meta",
    q: str = "",
    p: int = 10,
    s: int = 1,
    fetch_all: bool = False,
    is_premium: bool = False,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        api_name = _normalize_api(api)
    except ValueError as exc:
        return {
            "api": (api or "").strip().lower() or "unknown",
            "success": False,
            "error": str(exc),
            "code": "invalid_request",
        }
    query = (q or "").strip()
    if not query:
        return {
            "api": api_name,
            "success": False,
            "error": "Query cannot be empty",
            "code": "missing_query",
        }

    p_value = max(1, _coerce_int(p, 10))
    s_value = max(1, _coerce_int(s, 1))
    fetch_all_value = bool(fetch_all)
    is_premium_value = False
    try:
        selected_key = _resolve_api_key(api_name, api_key)

        async def _execute(selected_api: str, selected_query: str) -> Any:
            return await asyncio.to_thread(
                _run_search,
                selected_api,
                selected_key,
                selected_query,
                p_value,
                s_value,
                fetch_all_value,
                is_premium_value,
            )

        original_query = query
        current_query = _basic_sanitize_query(query)
        if not current_query:
            return {
                "api": api_name,
                "success": False,
                "error": "Query cannot be empty after basic-plan normalization",
                "code": "missing_query",
            }
        fallback_reasons: list[str] = []
        if current_query != original_query:
            fallback_reasons.append("basic_plan_simplified")
        attempted_field_strip = False

        while True:
            try:
                data = await _execute(api_name, current_query)
                break
            except APIRequestError as exc:
                if (
                    not is_premium_value
                    and not attempted_field_strip
                    and "403" in str(exc)
                ):
                    simplified_query = _strip_field_constraints(current_query)
                    if simplified_query and simplified_query != current_query:
                        logger.warning(
                            "Springer Nature request forbidden; retrying with field constraints removed."
                        )
                        current_query = simplified_query
                        attempted_field_strip = True
                        if "field_constraints_removed" not in fallback_reasons:
                            fallback_reasons.append("field_constraints_removed")
                        continue
                raise

        records = data.get("records", []) if isinstance(data, dict) else []
        result: Dict[str, Any] = {
            "api": api_name,
            "query": current_query,
            "success": True,
            "records": records,
            "record_count": len(records),
        }
        if fallback_reasons:
            result["fallback_reason"] = ",".join(fallback_reasons)
            if current_query != original_query:
                result["original_query"] = original_query
        return result

    except InvalidAPIKeyError as exc:
        logger.warning("Invalid Springer Nature API key: %s", exc)
        return {
            "api": api_name,
            "query": query,
            "success": False,
            "error": str(exc),
            "code": "invalid_api_key",
        }
    except RateLimitExceededError as exc:
        logger.warning("Springer Nature rate limit exceeded: %s", exc)
        return {
            "api": api_name,
            "query": query,
            "success": False,
            "error": str(exc),
            "code": "rate_limit",
        }
    except APIRequestError as exc:
        logger.warning("Springer Nature request failed: %s", exc)
        return {
            "api": api_name,
            "query": query,
            "success": False,
            "error": str(exc),
            "code": "request_error",
        }
    except ValueError as exc:
        return {
            "api": api_name,
            "query": query,
            "success": False,
            "error": str(exc),
            "code": "invalid_request",
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected Springer Nature failure")
        return {
            "api": api_name,
            "query": query,
            "success": False,
            "error": str(exc),
            "code": "unexpected_error",
        }


springer_nature_tool = {
    "name": "springer_nature",
    "description": "Search Springer Nature Meta or Open Access APIs.",
    "category": "information_retrieval",
    "parameters_schema": {
        "type": "object",
        "properties": {
            "api": {
                "type": "string",
                "description": "API to query",
                "enum": ["meta", "openaccess"],
                "default": "meta",
            },
            "q": {
                "type": "string",
                "description": "Query string (Springer Nature query syntax)",
            },
            "p": {
                "type": "integer",
                "description": "Results per page",
                "default": 10,
                "minimum": 1,
            },
            "s": {
                "type": "integer",
                "description": "Start position",
                "default": 1,
                "minimum": 1,
            },
            "fetch_all": {
                "type": "boolean",
                "description": "Fetch all pages",
                "default": False,
            },
            "is_premium": {
                "type": "boolean",
                "description": "Premium plan flag",
                "default": False,
            },
            "api_key": {
                "type": "string",
                "description": "Optional API key override",
            },
        },
        "required": ["q"],
    },
    "handler": springer_nature_handler,
    "tags": ["springer", "search", "meta", "openaccess"],
    "examples": [
        "keyword:\"cancer\" year:2023",
        "doi:10.1007/s00125-023-05915-9",
        "orgname:\"University of Calgary\"",
    ],
}

__all__ = ["springer_nature_tool", "springer_nature_handler"]
