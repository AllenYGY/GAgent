#!/usr/bin/env python3
"""
High-quality visualisations for multi-model plan evaluations.

Reads every `plan_scores*.csv` inside `results/` (or a custom directory),
infers the provider/model from the filename, merges them into a single
DataFrame, and produces publication-friendly heatmaps:

1. `dimension_provider_heatmap.png`
   Mean score per (provider × dimension) so you can compare models quickly.
2. `plan_dimension_heatmap_<provider>.png`
   For each provider, a plan vs dimension heatmap using the top-N plans
   by average score (defaults to 20). Helpful for spotting weak spots.
3. `plan_provider_heatmap.png`
   Average score per (plan × provider) to visualise consistency across models.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DIMENSIONS = [
    "relevance",
    "completeness",
    "accuracy",
    "clarity",
    "coherence",
    "scientific_rigor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot plan score heatmaps.")
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing plan_scores*.csv files (default: results/).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/plots"),
        help="Directory to store generated PNGs (default: results/plots).",
    )
    parser.add_argument(
        "--top-plans",
        type=int,
        default=20,
        help="Max number of plans per provider heatmap (default: 20).",
    )
    parser.add_argument(
        "--plan-order",
        choices=["mean", "median", "max"],
        default="mean",
        help="Metric for ranking plans before truncation (default: mean).",
    )
    parser.add_argument(
        "--include-provider",
        type=str,
        nargs="*",
        help="Optional whitelist of providers to plot (default: all discovered).",
    )
    return parser.parse_args()


def find_score_files(scores_dir: Path) -> List[Path]:
    if not scores_dir.exists():
        raise FileNotFoundError(f"Scores directory not found: {scores_dir}")
    files = sorted(scores_dir.glob("plan_scores*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No plan_scores*.csv files found under {scores_dir}. "
            "Run eval_plan_quality.py first."
        )
    return files


def infer_provider_from_name(path: Path) -> str:
    stem = path.stem  # e.g. plan_scores_qwen
    match = re.match(r"plan_scores(?:[_\-](.+))?", stem)
    if match:
        suffix = match.group(1)
        if suffix:
            return suffix.strip().lower()
    return "default"


def load_all_scores(scores_dir: Path, include: Optional[List[str]]) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []
    for csv_path in find_score_files(scores_dir):
        provider = infer_provider_from_name(csv_path)
        if include and provider not in include:
            continue
        df = pd.read_csv(csv_path)
        missing = [dim for dim in DIMENSIONS if dim not in df.columns]
        if missing:
            print(
                f"[WARN] Skipping {csv_path} because it lacks columns: {missing}"
            )
            continue
        df["provider"] = provider
        df["source_file"] = csv_path.name
        rows.append(df)

    if not rows:
        raise RuntimeError("No valid score files matched the selection criteria.")

    combined = pd.concat(rows, ignore_index=True)
    combined["average_score"] = combined[DIMENSIONS].mean(axis=1)
    return combined


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_provider_dimension_heatmap(df: pd.DataFrame, output: Path) -> None:
    pivot = df.groupby("provider")[DIMENSIONS].mean().sort_index()
    fig, ax = plt.subplots(figsize=(1.4 * len(DIMENSIONS), 0.6 * len(pivot)))
    im = ax.imshow(pivot.values, cmap="viridis", vmin=1, vmax=5, aspect="auto")
    ax.set_xticks(range(len(DIMENSIONS)))
    ax.set_xticklabels(
        [dim.replace("_", "\n").title() for dim in DIMENSIONS], rotation=0, fontsize=10
    )
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels([provider.upper() for provider in pivot.index], fontsize=11)
    ax.set_title("Average Score per Dimension by Provider", fontsize=14)
    for (i, j), value in np.ndenumerate(pivot.values):
        ax.text(
            j,
            i,
            f"{value:.2f}",
            ha="center",
            va="center",
            color="white" if value >= 3.5 else "black",
            fontsize=9,
        )
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.set_label("Score (1–5)")
    plt.tight_layout()
    plt.savefig(output, dpi=220)
    plt.close(fig)


def _rank_plans(df: pd.DataFrame, plan_order: str) -> pd.Series:
    if plan_order == "median":
        return df.groupby("plan_id")["average_score"].median()
    if plan_order == "max":
        return df.groupby("plan_id")["average_score"].max()
    return df.groupby("plan_id")["average_score"].mean()


def plot_plan_dimension_heatmaps_per_provider(
    df: pd.DataFrame,
    output_dir: Path,
    top_plans: int,
    plan_order: str,
) -> None:
    grouped = df.groupby("provider")
    for provider, chunk in grouped:
        ranking = _rank_plans(chunk, plan_order).sort_values(ascending=False)
        top_ids = ranking.head(top_plans).index
        filtered = chunk[chunk["plan_id"].isin(top_ids)]
        if filtered.empty:
            continue
        pivot = filtered.groupby("plan_id")[DIMENSIONS].mean().loc[top_ids]
        fig, ax = plt.subplots(figsize=(1.4 * len(DIMENSIONS), 0.35 * len(pivot) + 1))
        im = ax.imshow(pivot.values, cmap="magma", vmin=1, vmax=5, aspect="auto")
        ax.set_xticks(range(len(DIMENSIONS)))
        ax.set_xticklabels(
            [dim.replace("_", "\n").title() for dim in DIMENSIONS], fontsize=10
        )
        ax.set_yticks(range(len(pivot)))
        ax.set_yticklabels([f"Plan {pid}" for pid in pivot.index], fontsize=9)
        ax.set_title(
            f"Plan vs Dimension Heatmap – {provider.upper()} (Top {len(pivot)})",
            fontsize=14,
        )
        cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
        cbar.set_label("Score (1–5)")
        plt.tight_layout()
        target = output_dir / f"plan_dimension_heatmap_{provider}.png"
        plt.savefig(target, dpi=220)
        plt.close(fig)


def plot_plan_provider_heatmap(df: pd.DataFrame, output: Path, top_plans: int, plan_order: str) -> None:
    ranking = _rank_plans(df, plan_order).sort_values(ascending=False)
    top_ids = ranking.head(top_plans).index
    filtered = df[df["plan_id"].isin(top_ids)]
    pivot = filtered.pivot_table(
        index="plan_id",
        columns="provider",
        values="average_score",
        aggfunc="mean",
    ).loc[top_ids]
    if pivot.empty:
        print("[WARN] Combined plan-provider heatmap has no data.")
        return
    pivot = pivot[sorted(pivot.columns)]
    providers = list(pivot.columns)
    fig, ax = plt.subplots(figsize=(0.9 * len(providers) + 2, 0.4 * len(pivot) + 1))
    im = ax.imshow(pivot.values, cmap="plasma", vmin=1, vmax=5, aspect="auto")
    ax.set_xticks(range(len(providers)))
    ax.set_xticklabels([p.upper() for p in providers], fontsize=10)
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels([f"Plan {pid}" for pid in pivot.index], fontsize=9)
    ax.set_title("Average Plan Score per Provider", fontsize=14)
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.set_label("Score (1–5)")
    plt.tight_layout()
    plt.savefig(output, dpi=220)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    include = [name.lower() for name in args.include_provider] if args.include_provider else None
    df = load_all_scores(args.scores_dir, include)
    ensure_output_dir(args.output_dir)

    plot_provider_dimension_heatmap(df, args.output_dir / "dimension_provider_heatmap.png")
    plot_plan_dimension_heatmaps_per_provider(
        df,
        args.output_dir,
        top_plans=args.top_plans,
        plan_order=args.plan_order,
    )
    plot_plan_provider_heatmap(
        df,
        args.output_dir / "plan_provider_heatmap.png",
        top_plans=args.top_plans,
        plan_order=args.plan_order,
    )
    print(f"[INFO] Saved heatmaps to {args.output_dir}")


if __name__ == "__main__":
    main()
