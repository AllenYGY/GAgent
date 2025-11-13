#!/usr/bin/env python3
"""Run the simulated user mode from the command line."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

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
            print(f"Judge verdict     : {turn.judge.alignment} (conf={turn.judge.confidence})")
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

    settings = get_settings()
    default_goal = getattr(
        settings,
        "sim_default_goal",
        "Refine the currently bound plan to better achieve the user's objectives.",
    )
    goal = (args.goal or "").strip() or default_goal

    registry = SimulationRegistry(SimulationOrchestrator)
    config = SimulationRunConfig(
        session_id=args.session_id,
        plan_id=args.plan_id,
        improvement_goal=goal,
        max_turns=args.max_turns,
        auto_advance=not args.manual,
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
    print(f"Run id        : {state.run_id}")
    print(f"Status        : {state.status}")
    print(f"Turns         : {len(state.turns)} / {config.max_turns}")
    if state.error:
        print(f"Error         : {state.error}")
    print(f"Remaining     : {state.remaining_turns}")

    _print_turns(state, show_raw=args.show_raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute the simulated user mode loop.")
    parser.add_argument("--session-id", help="Chat session id to associate with the run.")
    parser.add_argument("--plan-id", type=int, help="Plan id to bind for context.")
    parser.add_argument("--goal", help="Improvement goal to guide the simulated user.")
    parser.add_argument("--max-turns", type=int, default=5, help="Maximum turns to run.")
    parser.add_argument("--manual", action="store_true", help="Run turn-by-turn with prompts instead of auto advancing.")
    parser.add_argument("--db-root", help="Override DB root path.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw JSON payloads returned by the agents.")
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
