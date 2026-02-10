#!/usr/bin/env python3
"""
Grouped bar charts by category.

Inputs:
  --category-csv: CSV with at least columns `category` and `title` (e.g., data/phage_plans.csv).
  --files: one or more plan_scores*.csv (with columns title,contextual_completeness,accuracy,task_granularity_atomicity,reproducibility_execution,scientific_rigor,innovation_feasibility,...).
  --labels: optional labels matching --files order (otherwise inferred).

Output:
  One image per category written to --output-dir, filename: <slugified_category>.png

Example:
  python scripts/plot/plot_plan_score_bars_by_category.py \
    --category-csv data/phage_plans.csv \
    --files \
      results/agent_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/agent_plans_phage_deepseek/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_qwen/eval/plan_scores_qwen.csv \
      results/llm_plans_phage_deepseek/eval/plan_scores_qwen.csv \
    --labels agent_qwen_max agent_deepseek_v3 llm_qwen_max llm_deepseek_v3 \
    --output-dir results/score_bars_by_category_qwen
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np

METRICS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_execution",
    "scientific_rigor",
    "innovation_feasibility",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot plan scores by category (grouped bars per metric).")
    parser.add_argument("--category-csv", required=True, type=Path, help="CSV with columns category,title.")
    parser.add_argument("--files", nargs="+", required=True, help="plan_scores*.csv files to compare.")
    parser.add_argument("--labels", nargs="+", help="Optional labels matching --files order.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to save plots.")
    parser.add_argument("--figsize", type=float, nargs=2, default=(10, 6), help="Figure size (w h).")
    parser.add_argument("--dpi", type=int, default=200, help="Figure DPI.")
    return parser.parse_args()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def load_category_map(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cat = (row.get("category") or "").strip()
            title = (row.get("title") or "").strip()
            if not cat or not title:
                continue
            mapping[title] = cat
    return mapping


def summarize_file(path: Path, title_to_cat: Dict[str, str]) -> Dict[str, List[float]]:
    per_cat = defaultdict(lambda: {m: [] for m in METRICS})
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("title") or "").strip()
            cat = title_to_cat.get(title)
            if not cat:
                continue
            for m in METRICS:
                try:
                    per_cat[cat][m].append(float(row.get(m, "nan")))
                except Exception:
                    pass
    # average per category
    result = {}
    for cat, metrics_vals in per_cat.items():
        vals = []
        for m in METRICS:
            arr = metrics_vals[m]
            arr = [x for x in arr if not np.isnan(x)]
            vals.append(float("nan") if not arr else sum(arr) / len(arr))
        result[cat] = vals
    return result


def main() -> None:
    args = parse_args()
    title_to_cat = load_category_map(args.category_csv)
    if not title_to_cat:
        raise SystemExit(f"[ERR] No category/title pairs found in {args.category_csv}")

    paths = [Path(f) for f in args.files]
    labels = args.labels or []
    if labels and len(labels) != len(paths):
        raise SystemExit("[ERR] --labels length must match --files length.")
    if not labels:
        labels = [p.stem for p in paths]

    # Collect per-file summaries (category -> metric list)
    per_file = []
    all_categories = set()
    for lab, p in zip(labels, paths):
        if not p.exists():
            raise SystemExit(f"[ERR] File not found: {p}")
        cat_avgs = summarize_file(p, title_to_cat)
        per_file.append((lab, cat_avgs))
        all_categories.update(cat_avgs.keys())

    if not all_categories:
        raise SystemExit("[ERR] No categories matched between scores and category CSV.")

    # Determine scale from all values
    all_vals: List[float] = []
    for _, cat_avgs in per_file:
        for vals in cat_avgs.values():
            all_vals.extend([v for v in vals if not np.isnan(v)])
    score_max = max(5, int(math.ceil(max(all_vals)))) if all_vals else 5

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for cat in sorted(all_categories):
        plt.figure(figsize=tuple(args.figsize), dpi=args.dpi)
        x = np.arange(len(METRICS))
        width = 0.8 / max(1, len(per_file))
        for idx, (lab, cat_avgs) in enumerate(per_file):
            vals = cat_avgs.get(cat, [float("nan")] * len(METRICS))
            offset = (idx - (len(per_file) - 1) / 2) * width
            plt.bar(x + offset, vals, width, label=lab)
        plt.xticks(x, METRICS, rotation=30, ha="right")
        plt.ylabel("Score")
        plt.ylim(0, score_max + 0.5)
        plt.title(f"Plan quality by category: {cat}")
        plt.legend()
        plt.tight_layout()
        out_path = args.output_dir / f"{slugify(cat)}.png"
        plt.savefig(out_path)
        plt.close()
        print(f"[OK] Saved {out_path}")


if __name__ == "__main__":
    main()
