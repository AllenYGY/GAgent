#!/usr/bin/env python3
"""
Visualize misalignment matrices (run x turn) with a heatmap and summary panels.

Example:
  python scripts/plot/plot_misalignment_matrix.py \
    --inputs experiments/simulation_agent_misalignment_matrix_qwen.csv \
             experiments/simulation_LLM_misalignment_matrix_deepseekv3.csv \
             experiments/simulation_LLM_misalignment_matrix_qwen.csv \
    --output-dir experiments/plots \
    --compare-output experiments/plots/misalignment_rate_compare.png
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

try:
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator, PercentFormatter
except ModuleNotFoundError as exc:
    raise SystemExit(
        "[ERR] matplotlib is required. Install it with: pip install matplotlib"
    ) from exc

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError as exc:
    raise SystemExit(
        "[ERR] numpy and pandas are required. Install them with: pip install numpy pandas"
    ) from exc

PALETTE = {
    "aligned": "#f3f4f6",
    "misaligned": "#e4572e",
    "line": "#264653",
    "hist": "#2a9d8f",
    "accent": "#e9c46a",
    "grid": "#b8b8b8",
    "text": "#2b2b2b",
}


def set_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.edgecolor": PALETTE["text"],
            "axes.linewidth": 0.8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot misalignment matrix CSVs.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="One or more misalignment matrix CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/plots"),
        help="Directory to store per-file dashboards.",
    )
    parser.add_argument(
        "--compare-output",
        type=Path,
        help="Optional output path for a multi-file comparison plot.",
    )
    return parser.parse_args()


def label_from_path(path: Path) -> str:
    name = path.stem
    name = name.replace("simulation_", "")
    name = name.replace("_misalignment_matrix", "")
    parts = name.replace("-", "_").split("_")
    labels = []
    for part in parts:
        low = part.lower()
        if low == "llm":
            labels.append("LLM")
        elif low == "agent":
            labels.append("Agent")
        elif low == "qwen":
            labels.append("Qwen")
        elif low.startswith("deepseek"):
            labels.append("DeepSeekV3" if "v3" in low else "DeepSeek")
        else:
            labels.append(part.capitalize() if part else part)
    return " ".join(labels) if labels else path.stem


def load_matrix(path: Path) -> Tuple[np.ndarray, List[int]]:
    df = pd.read_csv(path)
    if df.shape[1] < 2:
        raise ValueError(f"Expected at least 2 columns in {path}")
    raw = df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy()
    raw = np.nan_to_num(raw, nan=0.0)
    data = (raw > 0).astype(int)
    turns: List[int] = []
    for col in df.columns[1:]:
        try:
            turns.append(int(col))
        except Exception:
            turns.append(len(turns) + 1)
    return data, turns


def _tick_positions(count: int, approx: int = 10) -> List[int]:
    step = max(1, count // approx)
    return list(range(0, count, step))


def _soften_spines(ax: plt.Axes) -> None:
    for spine in ax.spines.values():
        spine.set_alpha(0.35)


def plot_dashboard(data: np.ndarray, turns: List[int], label: str, output_path: Path) -> None:
    n_runs, n_turns = data.shape
    rate_per_turn = data.mean(axis=0)
    per_run_counts = data.sum(axis=1)
    overall_rate = float(data.mean())

    fig = plt.figure(figsize=(12, 6))
    gs = fig.add_gridspec(
        nrows=2,
        ncols=2,
        width_ratios=[3.4, 1.6],
        height_ratios=[2.0, 1.2],
        wspace=0.28,
        hspace=0.35,
    )

    ax_heat = fig.add_subplot(gs[:, 0])
    ax_rate = fig.add_subplot(gs[0, 1])
    ax_hist = fig.add_subplot(gs[1, 1])

    cmap = ListedColormap([PALETTE["aligned"], PALETTE["misaligned"]])
    norm = BoundaryNorm([0, 0.5, 1.0], cmap.N)
    ax_heat.imshow(data, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm)
    ax_heat.set_title("Misalignment map")
    ax_heat.set_xlabel("Turn")
    ax_heat.set_ylabel("Run index")

    x_positions = _tick_positions(n_turns)
    y_positions = _tick_positions(n_runs)
    ax_heat.set_xticks(x_positions)
    ax_heat.set_xticklabels([str(turns[i]) for i in x_positions])
    ax_heat.set_yticks(y_positions)
    ax_heat.set_yticklabels([str(i + 1) for i in y_positions])
    ax_heat.tick_params(axis="both", length=0)

    legend_handles = [
        Patch(facecolor=PALETTE["misaligned"], label="Misaligned"),
        Patch(facecolor=PALETTE["aligned"], label="Aligned"),
    ]
    ax_heat.legend(handles=legend_handles, loc="upper right", frameon=False, fontsize=8)

    ax_rate.plot(turns, rate_per_turn, color=PALETTE["line"], lw=2)
    ax_rate.fill_between(turns, rate_per_turn, color=PALETTE["line"], alpha=0.18)
    ax_rate.set_title("Misalignment rate by turn")
    ax_rate.set_xlabel("Turn")
    ax_rate.set_ylabel("Rate")
    ax_rate.set_ylim(0, 1)
    ax_rate.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax_rate.yaxis.set_major_locator(MaxNLocator(5))
    ax_rate.grid(True, axis="y", color=PALETTE["grid"], alpha=0.4, linestyle="-")
    ax_rate.set_xticks([turns[i] for i in x_positions])

    ax_rate.axhline(overall_rate, color=PALETTE["accent"], lw=1.2, ls="--")
    ax_rate.annotate(
        f"Overall {overall_rate:.1%}",
        xy=(turns[-1], overall_rate),
        xytext=(6, 6),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=8,
        color=PALETTE["accent"],
    )

    bins = np.arange(0, n_turns + 2) - 0.5
    ax_hist.hist(per_run_counts, bins=bins, color=PALETTE["hist"], edgecolor="white")
    ax_hist.set_title("Misaligned turns per run")
    ax_hist.set_xlabel("Count")
    ax_hist.set_ylabel("Runs")
    ax_hist.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax_hist.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax_hist.grid(True, axis="y", color=PALETTE["grid"], alpha=0.35, linestyle="-")
    ax_hist.set_xlim(-0.5, n_turns + 0.5)

    median = float(np.median(per_run_counts))
    ax_hist.axvline(median, color=PALETTE["accent"], lw=1.2)
    ymax = ax_hist.get_ylim()[1]
    ax_hist.text(
        median,
        ymax * 0.95,
        f"median {median:.0f}",
        ha="center",
        va="top",
        fontsize=8,
        color=PALETTE["accent"],
    )

    fig.suptitle(f"{label} misalignment overview", fontsize=13, y=0.98)
    fig.text(
        0.02,
        0.02,
        f"Runs: {n_runs}  |  Turns: {n_turns}  |  Overall rate: {overall_rate:.1%}",
        fontsize=8,
        color=PALETTE["text"],
    )

    for ax in (ax_heat, ax_rate, ax_hist):
        _soften_spines(ax)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.92, bottom=0.1)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_comparison(
    series: Iterable[Tuple[str, List[int], np.ndarray]], output_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    for label, turns, rate in series:
        ax.plot(turns, rate, lw=2, label=label)
    ax.set_title("Misalignment rate comparison")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(True, axis="y", color=PALETTE["grid"], alpha=0.4, linestyle="-")
    ax.legend(frameon=False, fontsize=9)
    _soften_spines(ax)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    set_style()

    inputs = [Path(p) for p in args.inputs]
    for path in inputs:
        if not path.exists():
            raise SystemExit(f"[ERR] File not found: {path}")

    dashboards: List[Tuple[str, List[int], np.ndarray]] = []
    for path in inputs:
        data, turns = load_matrix(path)
        label = label_from_path(path)
        output_path = args.output_dir / f"{path.stem}_overview.png"
        plot_dashboard(data, turns, label, output_path)
        dashboards.append((label, turns, data.mean(axis=0)))
        print(f"[INFO] Saved dashboard to {output_path}")

    if args.compare_output and len(dashboards) > 1:
        plot_comparison(dashboards, args.compare_output)
        print(f"[INFO] Saved comparison plot to {args.compare_output}")


if __name__ == "__main__":
    main()
