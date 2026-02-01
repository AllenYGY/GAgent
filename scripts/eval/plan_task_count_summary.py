#!/usr/bin/env python3
"""
Summarize task counts (node counts) for plan_*.json directories.

Examples:
  python scripts/eval/plan_task_count_summary.py \
    results/agent_plans_phage_qwen/plans \
    results/agent_plans_phage_deepseek/plans \
    results/llm_plans_phage_qwen/parsed \
    results/llm_plans_phage_deepseek/parsed
"""

from __future__ import annotations

import argparse
import json
import math
import csv
from pathlib import Path
from typing import Tuple, List, Dict

import matplotlib.pyplot as plt

METRICS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_parameterization",
    "scientific_rigor",
]


def stats_for_dir(path: Path) -> Tuple[int, float, int, int]:
    counts = []
    for p in sorted(path.glob("plan_*.json")):
        try:
            raw = json.loads(p.read_text())
            counts.append(len(raw.get("nodes", {})))
        except Exception:
            continue
    if counts:
        return len(counts), sum(counts) / len(counts), min(counts), max(counts)
    return 0, 0.0, 0, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize plan task counts from plan_*.json directories.")
    parser.add_argument("dirs", nargs="+", help="Directories containing plan_*.json files.")
    parser.add_argument(
        "--score-files",
        nargs="+",
        help="Optional plan_scores*.csv files to find lowest scoring plans.",
    )
    args = parser.parse_args()

    print("dir,n,avg,min,max")
    for d in args.dirs:
        path = Path(d)
        if not path.exists() or not path.is_dir():
            print(f"{d},0,0,0,0")
            continue
        n, avg, mn, mx = stats_for_dir(path)
        print(f"{d},{n},{avg:.2f},{mn},{mx}")

    # Plot task count distribution if matplotlib is available
    try:
        import matplotlib  # noqa: F401
        plt.figure(figsize=(10, 6), dpi=200)
        for d in args.dirs:
            path = Path(d)
            if not path.exists() or not path.is_dir():
                continue
            counts = []
            for p in sorted(path.glob("plan_*.json")):
                try:
                    raw = json.loads(p.read_text())
                    counts.append(len(raw.get("nodes", {})))
                except Exception:
                    continue
            if counts:
                plt.hist(
                    counts,
                    bins=range(min(counts), max(counts) + 2),
                    alpha=0.5,
                    label=path.name,
                )
        if plt.gca().has_data():
            plt.xlabel("Task count per plan")
            plt.ylabel("Frequency")
            plt.title("Task count distribution")
            plt.legend()
            plt.tight_layout()
            out_path = Path("results/task_count_distribution.png")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(out_path)
            print(f"[INFO] Saved task count distribution to {out_path}")
        plt.close()
    except ModuleNotFoundError:
        pass

    if args.score_files:
        print("\nlowest_scores_per_metric:")
        best: Dict[str, tuple] = {m: (math.inf, None, None, None) for m in METRICS}  # score, title, plan_id, file
        for sf in args.score_files:
            p = Path(sf)
            if not p.exists():
                continue
            with p.open() as h:
                reader = csv.DictReader(h)
                for row in reader:
                    for m in METRICS:
                        try:
                            val = float(row[m])
                        except Exception:
                            continue
                        if val < best[m][0]:
                            best[m] = (val, row.get("title"), row.get("plan_id"), p.name)
        print("metric,score,plan_id,title,source_file")
        for m in METRICS:
            score, title, pid, fname = best[m]
            if math.isinf(score):
                continue
            print(f"{m},{score},{pid},{title},{fname}")


if __name__ == "__main__":
    main()
