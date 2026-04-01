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

  # Circos-style overview (one panel per input)
  python scripts/plot/plot_misalignment_matrix.py \
    --inputs experiments/simulation_agent_misalignment_matrix_qwen.csv \
    --output-dir experiments/plots \
    --style circos

  # Circos-classic (multi-track + links, requires pycirclize)
  python scripts/plot/plot_misalignment_matrix.py \
    --inputs experiments/simulation_agent_misalignment_matrix_qwen.csv \
    --output-dir experiments/plots \
    --style circos-classic \
    --link-mode first-recovery
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Tuple

try:
    import matplotlib.pyplot as plt
    from matplotlib.colors import (
        BoundaryNorm,
        ListedColormap,
        to_rgba,
    )
    from matplotlib.patches import Patch, Wedge
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

from nbt_style import (
    PALETTE,
    add_panel_label,
    series_colors,
    set_nature_style,
    soften_axes,
)


def set_times_new_roman_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [
                "Times New Roman",
                "Times",
                "Nimbus Roman",
                "Nimbus Roman No9 L",
                "DejaVu Serif",
            ],
            "mathtext.fontset": "stix",
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
        "--style",
        choices=["dashboard", "circos", "circos-classic"],
        default="dashboard",
        help="Visualization style for per-file outputs.",
    )
    parser.add_argument(
        "--link-mode",
        choices=["first-recovery", "segments", "both", "none"],
        default="first-recovery",
        help="Deprecated compatibility flag; circos-classic now renders ring summaries instead of links.",
    )
    parser.add_argument(
        "--min-link-count",
        type=int,
        default=2,
        help="Deprecated compatibility flag retained for older commands.",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=32,
        help="Deprecated compatibility flag retained for older commands.",
    )
    parser.add_argument(
        "--link-bins",
        "--run-bins",
        dest="link_bins",
        type=int,
        default=10,
        help="Number of turn bins used to aggregate recovery links (circos-classic).",
    )
    parser.add_argument(
        "--compare-output",
        type=Path,
        help="Optional output path for a multi-file comparison plot.",
    )
    parser.add_argument(
        "--compare-legend-position",
        choices=["right", "bottom"],
        default="right",
        help="Legend placement for the comparison plot.",
    )
    return parser.parse_args()


def label_from_path(path: Path) -> str:
    name = path.stem
    name = name.replace("simulation_", "")
    name = name.replace("_misalignment_matrix", "")
    normalized = name.replace("-", "_").lower()

    if normalized == "agent_qwen":
        return "PhageAgent"

    if normalized.startswith("llm_"):
        model_name = normalized[len("llm_") :]
        model_overrides = {
            "deepseekv3": "DeepSeekV3",
            "deepseek_v3": "DeepSeekV3",
            "deepseek": "DeepSeek",
            "qwen": "Qwen3-Max",
            "qwen3max": "Qwen3-Max",
            "qwen3_max": "Qwen3-Max",
            "grok": "grok-4-1-fast-reasoning",
            "grok_4_1_fast_reasoning": "grok-4-1-fast-reasoning",
            "gemini": "gemini-3-flash-preview",
            "gemini_3_flash_preview": "gemini-3-flash-preview",
            "gpt52chat": "GPT-5.2-Chat",
            "gpt_5_2_chat": "GPT-5.2-Chat",
            "gpt53chat": "GPT-5.3-Chat",
            "gpt_5_3_chat": "GPT-5.3-Chat",
        }
        if model_name in model_overrides:
            return model_overrides[model_name]
        parts = [part for part in model_name.split("_") if part]
        return " ".join(part.capitalize() for part in parts) if parts else path.stem

    parts = [part for part in normalized.split("_") if part]
    return " ".join(part.capitalize() for part in parts) if parts else path.stem


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
    soften_axes(ax)


def plot_dashboard(
    data: np.ndarray, turns: List[int], label: str, output_path: Path
) -> None:
    n_runs, n_turns = data.shape
    alignment_rate_per_turn = 1.0 - data.mean(axis=0)
    per_run_counts = data.sum(axis=1)
    overall_alignment_rate = float(alignment_rate_per_turn.mean())

    fig = plt.figure(figsize=(8.6, 5.4))
    gs = fig.add_gridspec(
        nrows=2,
        ncols=2,
        width_ratios=[3.4, 1.6],
        height_ratios=[2.2, 1.3],
        wspace=0.3,
        hspace=0.35,
    )

    ax_heat = fig.add_subplot(gs[:, 0])
    ax_rate = fig.add_subplot(gs[0, 1])
    ax_hist = fig.add_subplot(gs[1, 1])

    cmap = ListedColormap([PALETTE["aligned"], PALETTE["misaligned"]])
    norm = BoundaryNorm([0, 0.5, 1.0], cmap.N)
    ax_heat.imshow(data, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm)
    ax_heat.set_title("Misalignment by run and turn")
    ax_heat.set_xlabel("Turn")
    ax_heat.set_ylabel("Run index")

    x_positions = _tick_positions(n_turns)
    y_positions = _tick_positions(n_runs)
    ax_heat.set_xticks(x_positions)
    ax_heat.set_xticklabels([str(turns[i]) for i in x_positions])
    ax_heat.set_yticks(y_positions)
    ax_heat.set_yticklabels([str(i + 1) for i in y_positions])
    ax_heat.tick_params(axis="both", length=2, width=0.6, color=PALETTE["muted"])

    legend_handles = [
        Patch(facecolor=PALETTE["misaligned"], label="Misaligned"),
        Patch(facecolor=PALETTE["aligned"], label="Aligned"),
    ]
    ax_heat.legend(
        handles=legend_handles,
        loc="upper right",
        frameon=False,
        fontsize=7,
        handlelength=0.9,
        borderpad=0.2,
    )

    ax_rate.scatter(
        turns,
        alignment_rate_per_turn,
        facecolors="white",
        edgecolors=PALETTE["rate"],
        s=13,
        alpha=0.95,
        linewidths=0.7,
        zorder=4,
    )
    ax_rate.set_title("Turn-wise Alignment Score")
    ax_rate.set_xlabel("Turn")
    ax_rate.set_ylabel("Alignment rate")
    ax_rate.set_ylim(0, 1)
    ax_rate.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax_rate.yaxis.set_major_locator(MaxNLocator(5))
    ax_rate.grid(True, axis="y", color=PALETTE["grid"], alpha=0.6, linestyle="-")
    ax_rate.set_xticks([turns[i] for i in x_positions])

    ax_rate.axhline(
        overall_alignment_rate, color=PALETTE["accent"], lw=1.0, ls="--"
    )
    ax_rate.annotate(
        f"Overall {overall_alignment_rate:.1%}",
        xy=(turns[-1], overall_alignment_rate),
        xytext=(6, 6),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=7,
        color=PALETTE["accent"],
    )

    bins = np.arange(0, n_turns + 2) - 0.5
    ax_hist.hist(
        per_run_counts,
        bins=bins,
        color=PALETTE["hist"],
        edgecolor="white",
        linewidth=0.4,
    )
    ax_hist.set_title("Misaligned turns per run")
    ax_hist.set_xlabel("Count")
    ax_hist.set_ylabel("Runs")
    ax_hist.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax_hist.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax_hist.grid(True, axis="y", color=PALETTE["grid"], alpha=0.6, linestyle="-")
    ax_hist.set_xlim(-0.5, n_turns + 0.5)

    median = float(np.median(per_run_counts))
    ax_hist.axvline(median, color=PALETTE["accent"], lw=1.0, ls="--")
    ymax = ax_hist.get_ylim()[1]
    ax_hist.text(
        median,
        ymax * 0.95,
        f"median {median:.0f}",
        ha="center",
        va="top",
        fontsize=7,
        color=PALETTE["accent"],
    )

    add_panel_label(ax_heat, "a")
    add_panel_label(ax_rate, "b")
    add_panel_label(ax_hist, "c")

    for ax in (ax_heat, ax_rate, ax_hist):
        _soften_spines(ax)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.11)
    fig.savefig(output_path)
    plt.close(fig)


def plot_circos(
    data: np.ndarray, turns: List[int], label: str, output_path: Path
) -> None:
    n_runs, n_turns = data.shape
    alignment_rate_per_turn = 1.0 - data.mean(axis=0)
    overall_alignment_rate = float(alignment_rate_per_turn.mean())

    fig = plt.figure(figsize=(8.6, 8.6))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_direction(-1)
    ax.set_theta_zero_location("N")

    theta_edges = np.linspace(0, 2 * np.pi, n_turns + 1)
    # Reduce the inner hole so the circular heatmap occupies more of the figure.
    r_edges = np.linspace(0.08, 1.0, n_runs + 1)
    theta_centers = (theta_edges[:-1] + theta_edges[1:]) / 2

    cmap = ListedColormap([PALETTE["aligned"], PALETTE["misaligned"]])
    norm = BoundaryNorm([0, 0.5, 1.0], cmap.N)
    ax.pcolormesh(theta_edges, r_edges, data, cmap=cmap, norm=norm, shading="auto")

    # Outer track: alignment rate by turn
    r_base = 1.02
    r_line = r_base + 0.16 * alignment_rate_per_turn
    ax.plot(theta_centers, r_line, color=PALETTE["rate"], lw=1.3)
    ax.fill_between(
        theta_centers,
        r_base,
        r_line,
        color=PALETTE["rate"],
        alpha=0.12,
        linewidth=0,
    )

    # Ticks: sparse, turn-labeled
    tick_positions = _tick_positions(n_turns, approx=8)
    ax.set_xticks([theta_centers[i] for i in tick_positions])
    ax.set_xticklabels([str(turns[i]) for i in tick_positions], fontsize=7)
    ax.set_yticks([])
    ax.set_ylim(0.0, 1.2)
    ax.grid(False)
    ax.set_position([0.06, 0.12, 0.78, 0.78])

    fig.text(
        0.5,
        0.015,
        "Heatmap: run x turn (red=misaligned). Outer line: alignment rate by turn.",
        ha="center",
        fontsize=7,
        color=PALETTE["muted"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.96, bottom=0.09)
    fig.savefig(output_path)
    plt.close(fig)


def _first_recovery_links(data: np.ndarray) -> Tuple[Counter[Tuple[int, int]], int]:
    counts: Counter[Tuple[int, int]] = Counter()
    unresolved = 0
    for row in data:
        first_idx = None
        for idx, val in enumerate(row):
            if val:
                first_idx = idx
                break
        if first_idx is None:
            continue
        recovery_idx = None
        for idx in range(first_idx + 1, len(row)):
            if row[idx] == 0:
                recovery_idx = idx
                break
        if recovery_idx is None:
            unresolved += 1
            continue
        counts[(first_idx + 1, recovery_idx + 1)] += 1
    return counts, unresolved


def _segment_links(data: np.ndarray) -> Counter[Tuple[int, int]]:
    counts: Counter[Tuple[int, int]] = Counter()
    for row in data:
        start = None
        for idx, val in enumerate(row):
            if val and start is None:
                start = idx
            if start is not None and (not val or idx == len(row) - 1):
                end = idx if val else idx - 1
                if end >= start:
                    counts[(start + 1, end + 1)] += 1
                start = None
    return counts


def _first_recovery_counts_by_bin(
    data: np.ndarray,
    edges: np.ndarray,
) -> Tuple[np.ndarray, int]:
    counts = np.zeros(len(edges) - 1, dtype=float)
    unresolved = 0
    for row in data:
        first_idx = None
        for idx, val in enumerate(row):
            if val:
                first_idx = idx
                break
        if first_idx is None:
            continue
        recovery_idx = None
        for idx in range(first_idx + 1, len(row)):
            if row[idx] == 0:
                recovery_idx = idx
                break
        if recovery_idx is None:
            unresolved += 1
            continue
        counts[_turn_to_bin(recovery_idx + 1, edges)] += 1
    return counts, unresolved


def _segment_duration_by_bin(
    data: np.ndarray,
    edges: np.ndarray,
) -> np.ndarray:
    duration_sum = np.zeros(len(edges) - 1, dtype=float)
    duration_count = np.zeros(len(edges) - 1, dtype=float)

    for row in data:
        start = None
        for idx, val in enumerate(row):
            if val and start is None:
                start = idx
            if start is not None and (not val or idx == len(row) - 1):
                end = idx if val else idx - 1
                if end >= start:
                    duration = end - start + 1
                    bin_idx = _turn_to_bin(start + 1, edges)
                    duration_sum[bin_idx] += duration
                    duration_count[bin_idx] += 1
                start = None

    out = np.zeros(len(edges) - 1, dtype=float)
    mask = duration_count > 0
    out[mask] = duration_sum[mask] / duration_count[mask]
    return out


def _turn_bin_edges(n_turns: int, bins: int) -> np.ndarray:
    bins = max(1, min(bins, n_turns))
    return np.linspace(0, n_turns, bins + 1, dtype=int)


def _turn_to_bin(turn: int, edges: np.ndarray) -> int:
    zero_based_turn = max(0, turn - 1)
    return int(np.searchsorted(edges, zero_based_turn, side="right") - 1)


def _draw_fan_legend(
    ax: plt.Axes,
    tracks: List[Tuple[str, float, float, str]],
    *,
    start_angle: float = 122.5,
    end_angle: float = 57.5,
    font_size: float = 7.5,
    font_weight: str = "normal",
) -> None:
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.02, 1.62)
    ax.set_ylim(0.0, 1.02)

    center = (0.0, 0.0)
    anchor_x = (
        max(r_outer for _, _, r_outer, _ in tracks) * np.cos(np.deg2rad(end_angle))
        + 0.12
    )

    for label, r_inner, r_outer, color in tracks:
        wedge = Wedge(
            center,
            r_outer,
            end_angle,
            start_angle,
            width=r_outer - r_inner,
            facecolor=color,
            edgecolor=PALETTE["grid"],
            linewidth=0.5,
        )
        ax.add_patch(wedge)
        r_mid = (r_inner + r_outer) / 2
        angle = (start_angle + end_angle) / 2
        x = r_mid * np.cos(np.deg2rad(angle))
        y = r_mid * np.sin(np.deg2rad(angle))
        ax.text(
            anchor_x,
            y,
            label,
            ha="left",
            va="center",
            fontsize=font_size,
            fontweight=font_weight,
            color=PALETTE["muted"],
        )


def _add_circos_track_legend(
    fig: plt.Figure,
    *,
    box: Tuple[float, float, float, float] = (0.84, 0.07, 0.14, 0.14),
) -> None:
    ax = fig.add_axes(box)

    tracks = [
        ("Axis (turn)", 0.82, 0.98, PALETTE["aligned"]),
        ("Turn-wise Alignment Score", 0.64, 0.80, PALETTE["rate"]),
        ("First misalignment", 0.48, 0.62, PALETTE["misaligned"]),
        ("Recovery Frequency", 0.32, 0.46, PALETTE["hist"]),
        ("Mean Segment Duration", 0.16, 0.30, PALETTE["accent"]),
    ]
    _draw_fan_legend(ax, tracks)


def save_circos_legend(output_path: Path) -> None:
    fig = plt.figure(figsize=(2.8, 1.45))
    ax = fig.add_axes((0.02, 0.08, 0.96, 0.84))
    tracks = [
        ("Aligned", 0.68, 0.84, PALETTE["aligned"]),
        ("Misaligned", 0.48, 0.64, PALETTE["misaligned"]),
        ("Alignment Rate", 0.28, 0.44, PALETTE["rate"]),
    ]
    _draw_fan_legend(ax, tracks, font_size=7.2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def save_circos_classic_legend(output_path: Path) -> None:
    fig = plt.figure(figsize=(3.25, 1.75))
    _add_circos_track_legend(
        fig,
        box=(0.02, 0.06, 0.96, 0.88),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_circos_classic(
    data: np.ndarray,
    turns: List[int],
    label: str,
    output_path: Path,
    *,
    link_mode: str,
    min_link_count: int,
    max_links: int,
    link_bins: int,
) -> None:
    try:
        from pycirclize import Circos
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "[ERR] pycirclize is required for --style circos-classic. Install it with: pip install pycirclize"
        ) from exc

    n_runs, n_turns = data.shape
    sector_name = "Turns"
    bin_edges = _turn_bin_edges(n_turns, link_bins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    bin_widths = np.maximum(0.9, 0.82 * (bin_edges[1:] - bin_edges[:-1]))
    circos = Circos(
        {sector_name: n_turns},
        start=-90,
        end=270,
        space=2,
        endspace=False,
    )
    sector = circos.sectors[0]

    x = np.arange(n_turns) + 0.5
    alignment_rate_per_turn = 1.0 - data.mean(axis=0)
    first_counts = np.zeros(n_turns, dtype=float)
    for row in data:
        for idx, val in enumerate(row):
            if val:
                first_counts[idx] += 1
                break
    recovery_counts, unresolved = _first_recovery_counts_by_bin(data, bin_edges)
    segment_duration = _segment_duration_by_bin(data, bin_edges)

    axis_track = sector.add_track((96, 100))
    axis_track.axis(fc=PALETTE["aligned"], ec=PALETTE["grid"], lw=0.6)
    step = max(5, int(round(n_turns / 8)))
    tick_idx = list(range(0, n_turns, step))
    tick_positions = [i + 0.5 for i in tick_idx]
    tick_labels = [str(turns[i]) for i in tick_idx]
    axis_track.xticks(
        tick_positions,
        labels=tick_labels,
        label_orientation="vertical",
        label_size=7,
        line_kws=dict(ec=PALETTE["muted"], lw=0.5),
        text_kws=dict(color=PALETTE["muted"]),
    )

    rate_track = sector.add_track((81, 94), r_pad_ratio=0.05)
    rate_track.axis(ec=PALETTE["grid"], lw=0.4)
    rate_track.line(
        x,
        alignment_rate_per_turn,
        vmin=0,
        vmax=1,
        color=PALETTE["rate"],
        lw=1.2,
    )
    rate_track.fill_between(
        x,
        alignment_rate_per_turn,
        y2=0,
        vmin=0,
        vmax=1,
        fc=to_rgba(PALETTE["rate"], 0.12),
        ec="none",
    )
    rate_track.yticks(
        [0, 0.5, 1.0],
        labels=["0", "50", "100"],
        vmin=0,
        vmax=1,
        label_size=7,
        line_kws=dict(ec=PALETTE["grid"], lw=0.4),
        text_kws=dict(color=PALETTE["muted"]),
    )

    first_track = sector.add_track((68, 79), r_pad_ratio=0.05)
    first_track.axis(ec=PALETTE["grid"], lw=0.4)
    first_track.bar(
        x,
        first_counts,
        vmin=0,
        vmax=max(1, float(first_counts.max())),
        width=0.8,
        color=PALETTE["misaligned"],
        ec="white",
        lw=0.3,
    )
    first_track.yticks(
        [0, float(first_counts.max())],
        labels=["0", f"{int(first_counts.max())}"],
        vmin=0,
        vmax=max(1, float(first_counts.max())),
        label_size=6.5,
        line_kws=dict(ec=PALETTE["grid"], lw=0.4),
        text_kws=dict(color=PALETTE["muted"]),
    )

    recovery_track = sector.add_track((50, 66), r_pad_ratio=0.05)
    recovery_track.axis(ec=PALETTE["grid"], lw=0.4)
    recovery_track.bar(
        bin_centers,
        recovery_counts,
        vmin=0,
        vmax=max(1, float(recovery_counts.max())),
        width=bin_widths,
        color=PALETTE["hist"],
        ec="white",
        lw=0.3,
    )
    recovery_track.yticks(
        [0, float(recovery_counts.max())] if recovery_counts.max() > 0 else [0, 1],
        labels=["0", f"{int(recovery_counts.max())}"] if recovery_counts.max() > 0 else ["0", "1"],
        vmin=0,
        vmax=max(1, float(recovery_counts.max())),
        label_size=6.2,
        line_kws=dict(ec=PALETTE["grid"], lw=0.35),
        text_kws=dict(color=PALETTE["muted"]),
    )

    duration_track = sector.add_track((32, 48), r_pad_ratio=0.05)
    duration_track.axis(ec=PALETTE["grid"], lw=0.4)
    duration_track.bar(
        bin_centers,
        segment_duration,
        vmin=0,
        vmax=max(1, float(segment_duration.max())),
        width=bin_widths,
        color=PALETTE["accent"],
        ec="white",
        lw=0.3,
    )
    duration_track.yticks(
        [0, float(segment_duration.max())] if segment_duration.max() > 0 else [0, 1],
        labels=[ "0", f"{segment_duration.max():.1f}" ] if segment_duration.max() > 0 else ["0", "1"],
        vmin=0,
        vmax=max(1, float(segment_duration.max())),
        label_size=6.2,
        line_kws=dict(ec=PALETTE["grid"], lw=0.35),
        text_kws=dict(color=PALETTE["muted"]),
    )

    if unresolved:
        circos.text(
            f"No recovery: {unresolved}",
            r=22,
            deg=215,
            size=6.2,
            color=PALETTE["muted"],
            ha="left",
            va="center",
        )

    fig = circos.plotfig()
    w, h = fig.get_size_inches()
    fig.set_size_inches(w * 1.18, h * 1.18)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.96, bottom=0.03)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.set_constrained_layout(False)
    fig.set_tight_layout(False)
    fig.savefig(output_path)
    plt.close(fig)


def plot_comparison(
    series: Iterable[Tuple[str, List[int], np.ndarray]],
    output_path: Path,
    *,
    legend_position: str = "right",
) -> None:
    with plt.rc_context(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Helvetica",
                "Arial",
                "Nimbus Sans",
                "DejaVu Sans",
            ],
            "mathtext.fontset": "dejavusans",
        }
    ):
        fig, ax = plt.subplots(figsize=(8.8, 4.8))
        series_list = list(series)
        colors = series_colors(len(series_list))
        offsets = np.linspace(-0.18, 0.18, len(series_list)) if series_list else []
        max_turn = max((max(turns) for _, turns, _ in series_list), default=1)

        for (label, turns, rate), color, offset in zip(series_list, colors, offsets):
            x = np.asarray(turns, dtype=float)
            y = np.asarray(rate, dtype=float)
            x_offset = x + offset
            ax.plot(
                x,
                y,
                lw=0.85,
                alpha=0.55,
                color=color,
                label=label,
                zorder=2,
            )
            ax.scatter(
                x_offset,
                y,
                s=9,
                alpha=0.95,
                facecolors="white",
                edgecolors=color,
                linewidths=0.8,
                zorder=3,
            )

        ax.set_title("Turn-wise Alignment Score")
        ax.set_xlabel("Turn")
        ax.set_ylabel("Alignment rate")
        ax.set_ylim(0, 1)
        ax.set_xlim(0.5, max_turn + 0.6)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.grid(True, axis="y", color=PALETTE["grid"], alpha=0.6, linestyle="-")
        _soften_spines(ax)
        if legend_position == "bottom":
            ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, -0.11),
                ncol=max(1, len(series_list)),
                frameon=False,
                fontsize=8,
                handlelength=2.0,
                labelspacing=0.6,
                columnspacing=1.0,
                borderaxespad=0.0,
            )
        else:
            ax.legend(
                loc="center left",
                bbox_to_anchor=(1.01, 0.5),
                ncol=1,
                frameon=False,
                fontsize=8,
                handlelength=2.0,
                labelspacing=0.6,
                borderaxespad=0.0,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if legend_position == "bottom":
            fig.tight_layout(rect=(0, 0.03, 1, 1), pad=1.2)
        else:
            fig.tight_layout(rect=(0, 0, 0.84, 1), pad=1.2)
        fig.savefig(output_path)
        plt.close(fig)


def main() -> None:
    args = parse_args()
    set_nature_style()
    set_times_new_roman_style()

    inputs = [Path(p) for p in args.inputs]
    for path in inputs:
        if not path.exists():
            raise SystemExit(f"[ERR] File not found: {path}")

    legend_output: Path | None = None
    if args.style == "circos":
        legend_output = args.output_dir / "legend_circos.png"
        save_circos_legend(legend_output)
        print(f"[INFO] Saved legend to {legend_output}")
    elif args.style == "circos-classic":
        legend_output = args.output_dir / "legend_circos_classic.png"
        save_circos_classic_legend(legend_output)
        print(f"[INFO] Saved legend to {legend_output}")

    dashboards: List[Tuple[str, List[int], np.ndarray]] = []
    for path in inputs:
        data, turns = load_matrix(path)
        label = label_from_path(path)
        if args.style == "dashboard":
            suffix = "overview"
        elif args.style == "circos":
            suffix = "circos"
        else:
            suffix = "circos_classic"
        output_path = args.output_dir / f"{path.stem}_{suffix}.png"
        if args.style == "dashboard":
            plot_dashboard(data, turns, label, output_path)
        elif args.style == "circos-classic":
            plot_circos_classic(
                data,
                turns,
                label,
                output_path,
                link_mode=args.link_mode,
                min_link_count=args.min_link_count,
                max_links=args.max_links,
                link_bins=args.link_bins,
            )
        else:
            plot_circos(data, turns, label, output_path)
        dashboards.append((label, turns, 1.0 - data.mean(axis=0)))
        print(f"[INFO] Saved figure to {output_path}")

    if args.compare_output and len(dashboards) > 1:
        plot_comparison(
            dashboards,
            args.compare_output,
            legend_position=args.compare_legend_position,
        )
        print(f"[INFO] Saved comparison plot to {args.compare_output}")


if __name__ == "__main__":
    main()
