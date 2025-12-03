#!/usr/bin/env python3
"""Run the simulated user mode from the command line."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import init_db
from app.services.agents.simulation import (
    SimulationOrchestrator,
    SimulationRegistry,
    SimulationRunConfig,
    SimulationRunState,
)
from app.services.foundation.settings import get_settings
from app.repository.plan_repository import PlanRepository


def _print_heading(title: str) -> None:
    print(f"\n=== {title} ===")


def _print_turns(state: SimulationRunState, *, show_raw: bool) -> None:
    if not state.turns:
        print("(no turns recorded)")
        return
    for turn in state.turns:
        _print_heading(f"Turn {turn.index}")
        print(f"Goal              : {turn.goal or '(none)'}")
        print(f"Simulated user    : {turn.simulated_user.message}")
        if turn.simulated_user.desired_action:
            action = turn.simulated_user.desired_action
            print(f"Desired ACTION    : {action.kind}/{action.name} -> {action.parameters}")
        else:
            print("Desired ACTION    : (none)")
        print(f"Chat reply        : {turn.chat_agent.reply}")
        if turn.chat_agent.actions:
            for idx, action in enumerate(turn.chat_agent.actions, start=1):
                print(f"  Chat ACTION[{idx}] : {action.kind}/{action.name} -> {action.parameters}")
        else:
            print("  Chat ACTIONS    : (none)")
        if turn.judge:
            verdict = turn.judge.alignment
            score_repr = f" score={turn.judge.score}" if turn.judge.score is not None else ""
            print(
                f"Judge verdict     : {verdict}{score_repr} (conf={turn.judge.confidence})"
            )
            print(f"Judge explanation : {turn.judge.explanation}")
        else:
            print("Judge verdict     : (pending)")
        if show_raw:
            print("Raw simulated user payload:")
            print(turn.simulated_user.raw_response)
            print("Raw chat payload:")
            print(turn.chat_agent.raw_response)
            if turn.judge:
                print("Raw judge payload:")
                print(turn.judge.raw_response)


async def _run(args: argparse.Namespace) -> None:
    if args.db_root:
        os.environ["DB_ROOT"] = args.db_root
    init_db()

    repo = PlanRepository()
    try:
        plan_summary = repo.get_plan_summary(args.plan_id)
    except Exception as exc:
        print(f"[ERROR] Failed to load plan #{args.plan_id}: {exc}", file=sys.stderr)
        return
    else:
        print(
            f"[INFO] Running simulation against plan #{plan_summary.id}: {plan_summary.title}"
        )

    settings = get_settings()
    default_goal = getattr(
        settings,
        "sim_default_goal",
        "Refine the currently bound plan to better achieve the user's objectives.",
    )
    goal = (args.goal or "").strip() or default_goal

    registry = SimulationRegistry(SimulationOrchestrator)
    session_id = args.session_id or f"sim-{uuid4().hex}"
    max_turns = max(args.max_turns, 1)
    config = SimulationRunConfig(
        session_id=session_id,
        plan_id=args.plan_id,
        improvement_goal=goal,
        max_turns=max_turns,
        auto_advance=not args.manual,
        max_actions_per_turn=args.max_actions_per_turn,
        enable_execute_actions=args.enable_execute,
        allow_web_search=not args.disable_web_search,
        allow_rerun_task=not args.disable_rerun_task,
        allow_graph_rag=not args.disable_graph_rag,
        allow_show_tasks=False,  # default keep disabled unless explicitly enabled later
        stop_on_misalignment=not args.no_stop_on_misalignment,
    )
    state = await registry.create_run(config)

    if args.manual:
        for _ in range(config.max_turns):
            state = await registry.advance_run(state.run_id)
            if state.status in {"finished", "error", "cancelled"}:
                break
            proceed = input("Advance to next turn? [Y/n]: ").strip().lower()
            if proceed not in {"", "y", "yes"}:
                await registry.cancel_run(state.run_id)
                break
    else:
        state = await registry.auto_run(state.run_id)

    state = await registry.get_run(state.run_id) or state

    _print_heading("Simulation Summary")
    run_log_path = ROOT_DIR / "data" / "simulation_runs" / f"{state.run_id}.json"
    session_log_path = ROOT_DIR / "data" / "simulation_sessions" / f"{state.config.session_id}.json"
    print(f"Run id        : {state.run_id}")
    print(f"Session id    : {state.config.session_id}")
    print(f"Status        : {state.status}")
    print(f"Turns         : {len(state.turns)} / {config.max_turns}")
    if state.error:
        print(f"Error         : {state.error}")
    print(f"Remaining     : {state.remaining_turns}")
    print(f"Action limit  : {state.config.max_actions_per_turn} per turn")
    print(
        f"Execute plan  : {'enabled' if state.config.enable_execute_actions else 'disabled'}"
    )
    print(f"Run JSON      : {run_log_path}")
    print(f"Session log   : {session_log_path}")

    if state.alignment_issues:
        print("Misaligned turns:")
        for issue in state.alignment_issues:
            status = "delivered" if issue.delivered else "pending"
            print(f"  - Turn {issue.turn_index} ({status}): {issue.reason}")
    else:
        print("Misaligned turns: (none)")

    _print_turns(state, show_raw=args.show_raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute the simulated user mode loop.")
    parser.add_argument("--session-id", help="Chat session id to associate with the run.")
    parser.add_argument("--plan-id", type=int, required=True, help="Plan id to bind for context.")
    parser.add_argument("--goal", help="Improvement goal to guide the simulated user.")
    parser.add_argument("--max-turns", type=int, default=20, help="Maximum turns to run (default 20, capped at 20).")
    parser.add_argument(
        "--max-actions-per-turn",
        type=int,
        choices=[1, 2],
        default=2,
        help="Limit both agents to output at most this many ACTIONS per turn (1 or 2).",
    )
    parser.add_argument(
        "--no-stop-on-misalignment",
        action="store_true",
        help="Do not stop early when misaligned; always run until max_turns or error.",
    )
    parser.add_argument(
        "--enable-execute",
        action="store_true",
        help="Allow execute_plan actions during this simulation run.",
    )
    parser.add_argument("--manual", action="store_true", help="Run turn-by-turn with prompts instead of auto advancing.")
    parser.add_argument("--db-root", help="Override DB root path.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw JSON payloads returned by the agents.")
    parser.add_argument("--disable-web-search", action="store_true", help="Disable web_search action for this simulation run.")
    parser.add_argument("--disable-rerun-task", action="store_true", help="Disable rerun_task action for this simulation run.")
    parser.add_argument("--disable-graph-rag", action="store_true", help="Disable graph_rag action for this simulation run.")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[INFO] Simulation interrupted by user.")


if __name__ == "__main__":
    main()
