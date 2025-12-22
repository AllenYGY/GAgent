#!/usr/bin/env python3
"""
Quickly summarize average plan-quality scores from one or more CSV files.

Each input CSV is expected to have columns:
plan_id,title,contextual_completeness,accuracy,task_granularity_atomicity,reproducibility_parameterization,scientific_rigor[,comments]

Usage:
  python scripts/summarize_plan_scores.py results/*/eval/plan_scores*.csv
  python scripts/summarize_plan_scores.py --output summary.csv path/to/a.csv path/to/b.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional

METRICS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_parameterization",
    "scientific_rigor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize average plan-quality scores."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more CSV files with plan scores.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output CSV file. If omitted, print to stdout.",
    )
    return parser.parse_args()


def summarize_file(path: Path) -> Dict[str, Optional[float]]:
    vals: Dict[str, List[float]] = {m: [] for m in METRICS}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for m in METRICS:
                try:
                    vals[m].append(float(row[m]))
                except Exception:
                    pass
    n = len(next(iter(vals.values()))) if vals[METRICS[0]] else 0
    avgs = {
        m: round(sum(vals[m]) / len(vals[m]), 3) if vals[m] else None for m in METRICS
    }
    avgs["n"] = n
    return avgs


def main() -> None:
    args = parse_args()
    rows: List[List[str]] = []
    header = ["name", "n"] + METRICS

    for input_path in args.inputs:
        path = Path(input_path)
        if not path.exists():
            continue
        avgs = summarize_file(path)
        # Use a more informative default name: parent-of-parent / stem
        parent2 = path.parent.parent.name if path.parent.parent else ""
        if parent2:
            name = f"{parent2}_{path.stem}"
        else:
            name = path.stem
        row = [name, str(avgs.get("n", 0))] + [str(avgs.get(m, "")) for m in METRICS]
        rows.append(row)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
    else:
        print(",".join(header))
        for row in rows:
            print(",".join(row))


if __name__ == "__main__":
    main()
