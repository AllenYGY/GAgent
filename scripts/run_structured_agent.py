#!/usr/bin/env python3
"""Exercise StructuredChatAgent against a real LLM.

This helper sends a single user prompt through StructuredChatAgent so you can
verify that the upstream model returns schema-compliant JSON and that the agent
creates/decomposes plans as expected.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config.decomposer_config import get_decomposer_settings
from app.config.executor_config import get_executor_settings
from app.database import init_db
from app.repository.plan_repository import PlanRepository
from app.services.plans.plan_decomposer import PlanDecomposer
from app.services.plans.plan_executor import PlanExecutor
from app.services.plans.plan_session import PlanSession
from app.routers.chat_routes import StructuredChatAgent


def _parse_json_arg(value: Optional[str], *, expected_type: type, label: str):
    if not value:
        return None
    try:
        obj = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERROR] Failed to parse {label} JSON: {exc}") from exc
    if not isinstance(obj, expected_type):
        raise SystemExit(f"[ERROR] {label} must be a {expected_type.__name__}")
    return obj


def _print_heading(title: str) -> None:
    print(f"\n=== {title} ===")


async def _run(args: argparse.Namespace) -> None:
    if args.db_root:
        os.environ["DB_ROOT"] = args.db_root
    init_db()

    repo = PlanRepository()
    session = PlanSession(repo=repo, plan_id=args.plan_id)
    if args.plan_id is not None:
        try:
            session.bind(args.plan_id)
        except ValueError as exc:
            raise SystemExit(f"[ERROR] Failed to bind plan {args.plan_id}: {exc}") from exc

    decomposer_settings = get_decomposer_settings()
    plan_decomposer: Optional[PlanDecomposer] = None
    if decomposer_settings.model:
        plan_decomposer = PlanDecomposer(repo=repo, settings=decomposer_settings)
    else:
        print("[WARN] PlanDecomposer disabled (DECOMP_MODEL not set). Auto decomposition will be skipped.")

    executor_settings = get_executor_settings()
    plan_executor: Optional[PlanExecutor] = None
    if executor_settings.model:
        plan_executor = PlanExecutor(repo=repo, settings=executor_settings)
    else:
        print("[WARN] PlanExecutor disabled (PLAN_EXECUTOR_MODEL not set). execute_plan / rerun_task actions will fail.")

    agent = StructuredChatAgent(
        plan_session=session,
        plan_decomposer=plan_decomposer,
        plan_executor=plan_executor,
        session_id=args.session_id,
        conversation_id=args.conversation_id,
        history=args.history,
        extra_context=args.context or {},
    )

    _print_heading("Sending prompt to StructuredChatAgent")
    print(f"User prompt: {args.prompt}")
    result = await agent.handle(args.prompt)

    _print_heading("LLM Reply")
    print(result.reply)

    _print_heading("Agent Steps")
    if not result.steps:
        print("(no actions executed)")
    for idx, step in enumerate(result.steps, start=1):
        print(f"[{idx}] {step.action.kind}/{step.action.name} -> success={step.success}")
        if step.message:
            print(f"    message: {step.message}")
        if step.details:
            print(f"    details: {json.dumps(step.details, ensure_ascii=False, indent=2)}")

    _print_heading("Summary")
    print(f"Result success     : {result.success}")
    print(f"Bound plan id      : {result.bound_plan_id}")
    print(f"Plan persisted     : {result.plan_persisted}")
    if result.suggestions:
        print(f"Suggestions        : {result.suggestions}")
    if result.errors:
        print(f"Errors             : {result.errors}")

    plan_to_show = result.bound_plan_id or args.plan_id
    if plan_to_show:
        try:
            tree = repo.get_plan_tree(plan_to_show)
        except ValueError as exc:
            print(f"[WARN] Unable to load plan tree #{plan_to_show}: {exc}")
        else:
            _print_heading(f"Plan #{plan_to_show} Outline")
            outline = tree.to_outline(max_depth=args.max_depth, max_nodes=args.max_nodes)
            print(outline)
            if args.dump_nodes:
                _print_heading("Plan Nodes (truncated)")
                for node in tree.iter_nodes():
                    payload = {
                        "id": node.id,
                        "name": node.name,
                        "parent_id": node.parent_id,
                        "instruction": node.instruction,
                        "status": node.status,
                        "dependencies": node.dependencies,
                        "context_combined": node.context_combined,
                    }
                    print(json.dumps(payload, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a prompt through StructuredChatAgent and observe the executed actions.",
    )
    parser.add_argument("prompt", help="User prompt to send to the agent.")
    parser.add_argument("--session-id", help="Optional session identifier.")
    parser.add_argument("--conversation-id", type=int, help="Optional conversation id.")
    parser.add_argument("--plan-id", type=int, help="Bind to an existing plan before sending the prompt.")
    parser.add_argument("--context", help="JSON object string passed as extra_context.")
    parser.add_argument("--history", help="JSON array string for prior chat history items.")
    parser.add_argument("--db-root", help="Override DB root path (useful for sandboxes).")
    parser.add_argument("--max-depth", type=int, default=4, help="Max depth when printing plan outline.")
    parser.add_argument("--max-nodes", type=int, default=60, help="Max nodes when printing plan outline.")
    parser.add_argument("--dump-nodes", action="store_true", help="Dump node summaries after outline.")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.context = _parse_json_arg(args.context, expected_type=dict, label="context")
    args.history = _parse_json_arg(args.history, expected_type=list, label="history")

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[INFO] Aborted by user.", file=sys.stderr)


if __name__ == "__main__":
    main()
