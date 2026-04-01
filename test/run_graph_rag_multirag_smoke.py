from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict

from dotenv import load_dotenv

from app.config import get_graph_rag_settings, reset_graph_rag_settings_cache
from tool_box.tools_impl.graph_rag import graph_rag_handler
from tool_box.tools_impl.graph_rag.service import check_graph_rag_health


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke test the MultiRAG-backed graph_rag integration.",
    )
    parser.add_argument(
        "--query",
        default="what is BACTERIOPHAGE",
        help="Query sent to graph_rag.",
    )
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=["hybrid", "local", "global", "naive"],
        help="MultiRAG mode.",
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Only call GET /api/health and skip the query request.",
    )
    parser.add_argument(
        "--force-health",
        action="store_true",
        help="Bypass cached health result.",
    )
    return parser


def _mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) < 8:
        return value[:2] + "..."
    return value[:4] + "..." + value[-4:]


def _print_json(title: str, payload: Dict[str, Any]) -> None:
    print(f"\n[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    load_dotenv()
    reset_graph_rag_settings_cache()
    settings = get_graph_rag_settings()

    config_summary = {
        "base_url": settings.base_url or "",
        "has_api_key": bool(settings.api_key),
        "api_key_preview": _mask_api_key(settings.api_key),
        "query_timeout_seconds": settings.query_timeout_seconds,
        "health_timeout_seconds": settings.health_timeout_seconds,
        "health_cache_ttl": settings.health_cache_ttl,
        "cache_ttl": settings.cache_ttl,
    }
    _print_json("config", config_summary)

    health = await check_graph_rag_health(settings, force=args.force_health)
    _print_json("health", health)

    if args.health_only:
        return 0 if health.get("success") else 1

    result = await graph_rag_handler(query=args.query, mode=args.mode)
    _print_json("graph_rag", result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main()))
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        raise SystemExit(130)
