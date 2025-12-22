#!/usr/bin/env python3
"""
Plot plan-quality scores as grouped bar charts.

Expected input CSV (e.g., produced by summarize_plan_scores.py):
  name,n,contextual_completeness,accuracy,task_granularity_atomicity,reproducibility_parameterization,scientific_rigor

We put metrics on the x-axis, and for each metric, plot one bar per model/run.
Legend is auto-prettified into four常见标签:
  - agent_deepseek_v3
  - agent_qwen_max
  - llm_deepseek_v3
  - llm_qwen_max

You can filter rows by substring (case-insensitive) to control which runs appear.

Examples:
  # qwen-max 评测相关（包含 name 中的 'qwen'）
  python scripts/plot_plan_score_bars.py \
    --input results/score_summary.csv \
    --filter qwen \
    --output results/score_bars_qwen.png

  # deepseek-v3 评测相关（包含 name 中的 'deepseekv3'）
  python scripts/plot_plan_score_bars.py \
    --input results/score_summary.csv \
    --filter deepseekv3 \
    --output results/score_bars_deepseekv3.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np

METRICS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_parameterization",
    "scientific_rigor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot plan-quality scores as grouped bar chart.")
    parser.add_argument("--input", type=Path, help="Summary CSV (name,n,<metrics...>). Ignored if --files is given.")
    parser.add_argument("--files", nargs="+", help="Optional: direct plan_scores*.csv files; bypass summary CSV.")
    parser.add_argument("--labels", nargs="+", help="Optional labels matching --files order.")
    parser.add_argument("--output", required=True, type=Path, help="Output image path (png/svg...).")
    parser.add_argument("--filter", help="Only plot rows whose 'name' contains this substring (case-insensitive).")
    parser.add_argument("--figsize", type=float, nargs=2, default=(10, 6), help="Figure size (w h).")
    parser.add_argument("--dpi", type=int, default=200, help="Figure DPI.")
    return parser.parse_args()


def prettify_label(name: str) -> str:
    low = name.lower()
    if "agent_plans_phage" in low:
        if "deepseekv3" in low:
            return "agent_deepseek_v3"
        if "qwen" in low:
            return "agent_qwen_max"
    if "llm_plans_phage" in low:
        if "deepseekv3" in low:
            return "llm_deepseek_v3"
        if "qwen" in low:
            return "llm_qwen_max"
    return name


def summarize_file(path: Path) -> List[float]:
    vals = {m: [] for m in METRICS}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for m in METRICS:
                try:
                    vals[m].append(float(row.get(m, "nan")))
                except Exception:
                    pass
    avgs = []
    for m in METRICS:
        arr = vals[m]
        arr = [x for x in arr if not np.isnan(x)]
        avgs.append(float("nan") if not arr else sum(arr) / len(arr))
    return avgs


def main() -> None:
    args = parse_args()
    # If explicit files provided, bypass summary CSV
    if args.files:
        paths = [Path(f) for f in args.files]
        labels = args.labels or []
        if labels and len(labels) != len(paths):
            raise SystemExit("[ERR] --labels length must match --files length.")
        if not labels:
            labels = []
            for p in paths:
                # infer label from parent (e.g., agent_plans_phage_qwen)
                parent2 = p.parent.parent.name if p.parent.parent else ""
                label = parent2 or p.stem
                labels.append(prettify_label(label))
        data = {}
        for lab, p in zip(labels, paths):
            if not p.exists():
                raise SystemExit(f"[ERR] File not found: {p}")
            data[lab] = summarize_file(p)
        unique_labels = list(data.keys())
    else:
        if not args.input or not args.input.exists():
            raise SystemExit("[ERR] --input is required if --files is not provided.")
        with args.input.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        if not rows:
            raise SystemExit(f"[ERR] No data rows in {args.input}")
        # Filter
        filt = (args.filter or "").lower().strip()
        filtered = []
        for row in rows:
            nm = row.get("name", "")
            if filt and filt not in nm.lower():
                continue
            filtered.append(row)
        if not filtered:
            raise SystemExit(f"[ERR] No rows left after filter '{args.filter}'")

        # Aggregate by label (average if重复label出现多次)
        agg = {}
        for row in filtered:
            lab = prettify_label(row.get("name", ""))
            if lab not in agg:
                agg[lab] = {m: [] for m in METRICS}
            for m in METRICS:
                try:
                    agg[lab][m].append(float(row.get(m, "nan")))
                except Exception:
                    agg[lab][m].append(float("nan"))

        unique_labels = list(agg.keys())
        # Compute mean per label/metric
        data = {}
        for lab in unique_labels:
            vals = []
            for m in METRICS:
                arr = agg[lab][m]
                arr = [x for x in arr if not np.isnan(x)]
                vals.append(float("nan") if not arr else sum(arr) / len(arr))
            data[lab] = vals

    x = np.arange(len(METRICS))
    width = 0.8 / max(1, len(unique_labels))  # total bar span within [0.2,0.8]

    plt.figure(figsize=tuple(args.figsize), dpi=args.dpi)
    for idx, lab in enumerate(unique_labels):
        offset = (idx - (len(unique_labels) - 1) / 2) * width
        bars = plt.bar(x + offset, data[lab], width, label=lab)
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                height + 0.03,
                f"{height:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=0,
            )

    plt.xticks(x, METRICS, rotation=30, ha="right")
    plt.ylabel("Score")
    plt.ylim(0, 5.1)
    plt.title("Plan quality scores (grouped bars)")
    plt.legend()
    plt.tight_layout()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.output)
    print(f"[OK] Saved {args.output}")


if __name__ == "__main__":
    main()
