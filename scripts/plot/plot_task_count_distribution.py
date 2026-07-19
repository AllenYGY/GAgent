#!/usr/bin/env python3
"""
Plot distribution of task counts across plan_*.json directories.

Example:
  python scripts/plot/plot_task_count_distribution.py \
    --dirs results/agent_plans_phage_qwen/plans results/agent_plans_phage_deepseek/plans \
    --labels agent_qwen_max agent_deepseek_v3 \
    --output results/task_count_distribution.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt


def load_counts(dir_path: Path) -> List[int]:
    counts = []
    for p in sorted(dir_path.glob("plan_*.json")):
        try:
            raw = json.loads(p.read_text())
            counts.append(len(raw.get("nodes", {})))
        except Exception:
            continue
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot task count distribution for plan_*.json directories.")
    parser.add_argument("--dirs", nargs="+", required=True, help="Directories containing plan_*.json files.")
    parser.add_argument("--labels", nargs="+", help="Optional labels matching --dirs order.")
    parser.add_argument("--output", required=True, type=Path, help="Output image path (png/svg...).")
    parser.add_argument("--figsize", type=float, nargs=2, default=(10, 6), help="Figure size (w h).")
    parser.add_argument("--dpi", type=int, default=200, help="Figure DPI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dirs = [Path(d) for d in args.dirs]
    labels = args.labels or []
    if labels and len(labels) != len(dirs):
        raise SystemExit("[ERR] --labels length must match --dirs length.")
    if not labels:
        labels = [d.name for d in dirs]

    plt.figure(figsize=tuple(args.figsize), dpi=args.dpi)
    for idx, (dir_path, label) in enumerate(zip(dirs, labels)):
        if not dir_path.exists():
            print(f"[WARN] Directory not found: {dir_path}")
            continue
        counts = load_counts(dir_path)
        if not counts:
            print(f"[WARN] No plan_*.json in {dir_path}")
            continue
        plt.hist(counts, bins=range(min(counts), max(counts) + 2), alpha=0.5, label=label)

    plt.xlabel("Task count per plan")
    plt.ylabel("Frequency")
    plt.title("Task count distribution")
    plt.legend()
    plt.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.output)
    print(f"[OK] Saved {args.output}")


if __name__ == "__main__":
    main()
