#!/usr/bin/env python3
"""
Compare consecutive plan outline snapshots for a given simulation run and show what changed each turn.

Plan outline snapshots are stored as `<run_id>_turn_##_plan_outline.txt` inside a logs directory
(`experiments/experiments-12/run_logs` by default). This script diffs each consecutive turn so you can
see exactly what lines were added/removed in the plan outline over time.

Example:
    python scripts/plan_outline_diff.py --run-id 09b2adf9a714487281f74be92cd252f5 \\
        --logs-dir experiments/experiments-12/run_logs --context 2
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path
from typing import Iterable, List, Tuple


Snapshot = Tuple[int, List[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show diffs between consecutive plan outline snapshots for a simulation run."
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Simulation run id prefix used in filenames (e.g., 09b2adf9a714487281f74be92cd252f5).",
    )
    parser.add_argument(
        "--logs-dir",
        default="experiments/experiments-12/run_logs",
        help="Directory containing <run_id>_turn_##_plan_outline.txt files.",
    )
    parser.add_argument(
        "--start",
        type=int,
        help="First turn number to include (inclusive).",
    )
    parser.add_argument(
        "--end",
        type=int,
        help="Last turn number to include (inclusive).",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=3,
        help="Number of context lines for unified diffs.",
    )
    parser.add_argument(
        "--show-equal",
        action="store_true",
        help="Also print turns with no diff.",
    )
    return parser.parse_args()


def load_snapshots(run_id: str, logs_dir: Path, start: int | None, end: int | None) -> List[Snapshot]:
    pattern = f"{run_id}_turn_*_plan_outline.txt"
    snapshots: List[Snapshot] = []
    for path in sorted(logs_dir.glob(pattern)):
        try:
            turn_part = path.name.split("_turn_")[1]
            turn_str = turn_part.split("_", 1)[0]
            turn = int(turn_str)
        except (IndexError, ValueError):
            continue

        if start is not None and turn < start:
            continue
        if end is not None and turn > end:
            continue

        snapshots.append((turn, path.read_text(encoding="utf-8").splitlines()))

    snapshots.sort(key=lambda pair: pair[0])
    return snapshots


def iter_diffs(run_id: str, snapshots: List[Snapshot], context: int) -> Iterable[Tuple[int, int, List[str]]]:
    for (turn_a, lines_a), (turn_b, lines_b) in zip(snapshots, snapshots[1:]):
        diff = list(
            difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=f"{run_id}_turn_{turn_a}",
                tofile=f"{run_id}_turn_{turn_b}",
                n=context,
                lineterm="",
            )
        )
        yield turn_a, turn_b, diff


def main() -> None:
    args = parse_args()
    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_dir():
        raise SystemExit(f"Logs dir not found: {logs_dir}")

    snapshots = load_snapshots(args.run_id, logs_dir, args.start, args.end)
    if len(snapshots) < 2:
        raise SystemExit("Need at least two snapshots to diff.")

    for turn_a, turn_b, diff in iter_diffs(args.run_id, snapshots, args.context):
        print(f"\n=== Turn {turn_a} -> {turn_b} ===")
        if diff:
            for line in diff:
                print(line)
        elif args.show_equal:
            print("(no changes)")


if __name__ == "__main__":
    main()
