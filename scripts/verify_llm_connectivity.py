#!/usr/bin/env python
"""
LLM connectivity verifier.

Features:
- Iterate through all configured providers (except Perplexity by default) and
  run a lightweight chat prompt to confirm each can respond.
- Optionally restrict to a comma-separated provider list or override the prompt
  via CLI flags / environment variables.
- Run deeper plan-level smoke tests (plan decomposer + executor) using the
  default provider when --run-plan-tests is passed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

# Allow running the script from any working directory by ensuring repository root is on sys.path.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from app.database import init_db
from app.llm import PROVIDER_CONFIGS, LLMClient
from app.repository.plan_repository import PlanRepository
from app.services.llm.llm_service import LLMService
from app.services.plans.plan_decomposer import PlanDecomposer
from app.services.plans.plan_executor import ExecutionConfig, PlanExecutor

DEFAULT_PROVIDER_SEQUENCE = [
    provider
    for provider in (
        "glm",
        "qwen",
        "doubao",
        "moonshot",
        "deepseek",
        "grok",
        "gemini",
        "perplexity",  # supported but skipped by default
    )
    if provider in PROVIDER_CONFIGS
]


def _first_env_value(names: Optional[Sequence[str] | str]) -> Optional[str]:
    if not names:
        return None
    if isinstance(names, str):
        names = [names]
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value:
            return value
    return None


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify LLM connectivity.")
    parser.add_argument(
        "--providers",
        type=str,
        help="Comma-separated provider list (default: all configured except Perplexity).",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="Override test prompt (defaults to LLM_SMOKE_PROMPT or a generic request).",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Force a model name for chat tests (applied to every provider).",
    )
    parser.add_argument(
        "--plan-id",
        type=int,
        default=0,
        help="Existing plan ID for decomposer/executor tests (default: auto-create).",
    )
    parser.add_argument(
        "--run-plan-tests",
        action="store_true",
        help="Also run plan decomposer/executor smoke tests (disabled by default).",
    )
    return parser.parse_args()


def provider_has_credentials(provider: str) -> bool:
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        return False
    env_name = config.get("api_key_env")
    return bool(_first_env_value(env_name))


def resolve_provider_targets(arg_value: Optional[str]) -> List[str]:
    if arg_value:
        raw = [item.strip().lower() for item in arg_value.split(",")]
        return [provider for provider in raw if provider]
    providers: List[str] = []
    for provider in DEFAULT_PROVIDER_SEQUENCE:
        if provider == "perplexity":
            continue  # skip unless explicitly requested
        if not provider_has_credentials(provider):
            continue
        providers.append(provider)
    return providers


def smoke_chat(
    provider: str,
    service: LLMService,
    prompt: str,
    *,
    model: Optional[str] = None,
) -> None:
    _print_header(f"LLMService.chat [{provider}]")
    kwargs = {"model": model} if model else {}
    response = service.chat(prompt, **kwargs)
    snippet = response[:200]
    ellipsis = "..." if len(response) > 200 else ""
    print(f"Response snippet: {snippet}{ellipsis}\n")


def smoke_plan_decomposer(plan_id: int, prompt: str) -> None:
    _print_header("PlanDecomposerLLMService.generate")
    try:
        repo = PlanRepository()
        tree = repo.get_plan_tree(plan_id)
        roots = tree.root_node_ids()
        if not roots:
            raise RuntimeError("Plan has no root nodes to decompose.")
        target = roots[0]
        decomposer = PlanDecomposer(repo=repo)
        result = decomposer.decompose_node(plan_id, target, expand_depth=1)
        print(
            "Created tasks:",
            [node.id for node in result.created_tasks],
            "Stopped:",
            result.stopped_reason,
        )
    except Exception as exc:  # pragma: no cover - manual inspection
        print(f"[WARN] Decomposer run failed: {exc}")


_db_initialised = False


def smoke_plan_executor(plan_id: int) -> None:
    _print_header("PlanExecutor.execute_plan")
    repo = PlanRepository()
    executor = PlanExecutor(repo=repo)
    config = ExecutionConfig.from_settings(
        executor._settings
    )  # use configured defaults
    try:
        summary = executor.execute_plan(plan_id, config=config)
        print(
            "Executed tasks:",
            summary.executed_task_ids,
            "Failed:",
            summary.failed_task_ids,
            "Skipped:",
            summary.skipped_task_ids,
        )
    except Exception as exc:  # pragma: no cover - manual inspection
        print(f"[ERROR] PlanExecutor failed: {exc}")
        raise


def ensure_demo_plan(plan_root: Path) -> int:
    """Create a minimal plan if none exists."""
    global _db_initialised
    if not _db_initialised:
        os.environ.setdefault("DB_ROOT", str(plan_root))
        plan_root.mkdir(parents=True, exist_ok=True)
        init_db()
        _db_initialised = True

    # Always create a fresh plan so we exercise the full create-plan pipeline.
    repo = PlanRepository()
    plan = repo.create_plan("LLM Smoke Test Plan")
    print(f"[INFO] Created plan #{plan.id}")
    root = repo.create_task(
        plan.id, name="Draft summary", instruction="Summarise the prompt."
    )
    repo.create_task(plan.id, name="Review summary", parent_id=root.id)
    return plan.id


def run_provider_chat_checks(
    providers: Iterable[str],
    prompt: str,
    model_override: Optional[str],
    api_key_override: Optional[str] = None,
) -> None:
    successes = 0
    for provider in providers:
        print(f"[INFO] Testing provider '{provider}'.")
        if not api_key_override and not provider_has_credentials(provider):
            print(
                f"[WARN] Skipping provider '{provider}' because no API key is configured in environment."
            )
            continue
        try:
            client = LLMClient(provider=provider, model=model_override)
        except Exception as exc:
            print(f"[WARN] Skipping provider '{provider}': {exc}")
            continue
        print(f"[INFO] Provider '{provider}' will use model '{client.model}'.")
        service = LLMService(client)
        try:
            smoke_chat(provider, service, prompt, model=model_override)
            successes += 1
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[ERROR] Provider '{provider}' chat failed: {exc}")
    if successes == 0:
        raise RuntimeError("No provider chat test succeeded.")


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()
    prompt = args.prompt or os.getenv(
        "LLM_SMOKE_PROMPT",
        "Summarize the solar system in one short paragraph.",
    )
    model_override = args.model or os.getenv("LLM_SMOKE_MODEL")
    providers = resolve_provider_targets(args.providers)
    if not providers:
        raise SystemExit("No providers specified or discovered for connectivity test.")

    run_provider_chat_checks(providers, prompt, model_override)

    if not args.run_plan_tests:
        print(
            "[INFO] Plan decomposer/executor tests disabled (pass --run-plan-tests to enable)."
        )
        return

    plan_id = args.plan_id or int(os.getenv("LLM_SMOKE_PLAN_ID", "0"))
    if plan_id <= 0:
        plan_root = Path(os.getenv("DB_ROOT", "data/demo_db"))
        plan_id = ensure_demo_plan(plan_root)

    smoke_plan_decomposer(plan_id, prompt)
    smoke_plan_executor(plan_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - manual smoke run
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
