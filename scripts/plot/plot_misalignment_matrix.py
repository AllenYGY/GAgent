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
    --link-mode both
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
        LinearSegmentedColormap,
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
        default="both",
        help="Link definition for circos-classic.",
    )
    parser.add_argument(
        "--min-link-count",
        type=int,
        default=2,
        help="Minimum aggregated count to render a link (circos-classic).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=220,
        help="Maximum number of links to render per link type (circos-classic).",
    )
    parser.add_argument(
        "--run-bins",
        type=int,
        default=20,
        help="Number of run bins for heatmap track (circos-classic).",
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
    soften_axes(ax)


def plot_dashboard(
    data: np.ndarray, turns: List[int], label: str, output_path: Path
) -> None:
    n_runs, n_turns = data.shape
    rate_per_turn = data.mean(axis=0)
    per_run_counts = data.sum(axis=1)
    overall_rate = float(data.mean())

    fig = plt.figure(figsize=(7.2, 4.6))
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

    ax_rate.plot(turns, rate_per_turn, color=PALETTE["rate"], lw=1.6)
    ax_rate.fill_between(turns, rate_per_turn, color=PALETTE["rate"], alpha=0.14)
    ax_rate.set_title("Misalignment rate")
    ax_rate.set_xlabel("Turn")
    ax_rate.set_ylabel("Rate")
    ax_rate.set_ylim(0, 1)
    ax_rate.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax_rate.yaxis.set_major_locator(MaxNLocator(5))
    ax_rate.grid(True, axis="y", color=PALETTE["grid"], alpha=0.6, linestyle="-")
    ax_rate.set_xticks([turns[i] for i in x_positions])

    ax_rate.axhline(overall_rate, color=PALETTE["accent"], lw=1.0, ls="--")
    ax_rate.annotate(
        f"Overall {overall_rate:.1%}",
        xy=(turns[-1], overall_rate),
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

    fig.suptitle(f"{label} misalignment overview", fontsize=10, y=0.98)
    fig.text(
        0.02,
        0.02,
        f"Runs: {n_runs}  |  Turns: {n_turns}  |  Overall rate: {overall_rate:.1%}",
        fontsize=7,
        color=PALETTE["muted"],
    )

    for ax in (ax_heat, ax_rate, ax_hist):
        _soften_spines(ax)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.9, bottom=0.12)
    fig.savefig(output_path)
    plt.close(fig)


def plot_circos(
    data: np.ndarray, turns: List[int], label: str, output_path: Path
) -> None:
    n_runs, n_turns = data.shape
    rate_per_turn = data.mean(axis=0)
    overall_rate = float(data.mean())

    fig = plt.figure(figsize=(6.2, 6.2))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_direction(-1)
    ax.set_theta_zero_location("N")

    theta_edges = np.linspace(0, 2 * np.pi, n_turns + 1)
    r_edges = np.linspace(0.18, 1.0, n_runs + 1)
    theta_centers = (theta_edges[:-1] + theta_edges[1:]) / 2

    cmap = ListedColormap([PALETTE["aligned"], PALETTE["misaligned"]])
    norm = BoundaryNorm([0, 0.5, 1.0], cmap.N)
    ax.pcolormesh(theta_edges, r_edges, data, cmap=cmap, norm=norm, shading="auto")

    # Outer track: misalignment rate by turn
    r_base = 1.03
    r_line = r_base + 0.18 * rate_per_turn
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
    ax.grid(False)

    legend_handles = [
        Patch(facecolor=PALETTE["misaligned"], label="Misaligned"),
        Patch(facecolor=PALETTE["aligned"], label="Aligned"),
        Patch(facecolor=PALETTE["rate"], label="Rate"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper right",
        bbox_to_anchor=(1.12, 1.1),
        frameon=False,
        fontsize=7,
        handlelength=1.0,
    )

    fig.text(
        0.5,
        0.04,
        f"{label} | Runs: {n_runs} | Turns: {n_turns} | Overall rate: {overall_rate:.1%}",
        ha="center",
        fontsize=7,
        color=PALETTE["muted"],
    )
    fig.text(
        0.5,
        0.015,
        "Heatmap: run x turn (red=misaligned). Outer line: misalignment rate by turn.",
        ha="center",
        fontsize=6,
        color=PALETTE["muted"],
    )
    fig.suptitle(f"{label} misalignment overview", fontsize=10, y=0.98)

    output_path.parent.mkdir(parents=True, exist_ok=True)
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


def _bin_runs(data: np.ndarray, bins: int) -> np.ndarray:
    n_runs = data.shape[0]
    bins = max(1, min(bins, n_runs))
    edges = np.linspace(0, n_runs, bins + 1, dtype=int)
    binned = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if hi <= lo:
            continue
        binned.append(data[lo:hi].mean(axis=0))
    return np.vstack(binned) if binned else data.mean(axis=0, keepdims=True)


def _filter_links(
    counts: Counter[Tuple[int, int]],
    *,
    min_count: int,
    max_links: int,
) -> List[Tuple[int, int, int]]:
    items = [
        (start, end, count)
        for (start, end), count in counts.items()
        if count >= min_count and start != end
    ]
    items.sort(key=lambda x: x[2], reverse=True)
    if max_links and len(items) > max_links:
        items = items[:max_links]
    return items


def _add_circos_track_legend(fig: plt.Figure, *, include_links: bool) -> None:
    ax = fig.add_axes([0.6, 0.02, 0.26, 0.26])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.05, 1.35)
    ax.set_ylim(-1.05, 1.05)

    center = (0.0, 0.0)
    start_angle = 120
    end_angle = 60

    tracks = [
        ("Axis (turn)", 0.82, 0.98, PALETTE["aligned"]),
        ("Misalignment rate", 0.66, 0.80, PALETTE["rate"]),
        ("First misalignment", 0.50, 0.64, PALETTE["misaligned"]),
        ("Run-binned heatmap", 0.34, 0.48, "#f2dcd8"),
    ]
    if include_links:
        tracks.append(("Links (blue/red)", 0.18, 0.32, "#e6edf5"))

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
            fontsize=10,
            color=PALETTE["muted"],
        )

    # Links are explained by label only; no line samples.


def plot_circos_classic(
    data: np.ndarray,
    turns: List[int],
    label: str,
    output_path: Path,
    *,
    link_mode: str,
    min_link_count: int,
    max_links: int,
    run_bins: int,
) -> None:
    try:
        from pycirclize import Circos
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "[ERR] pycirclize is required for --style circos-classic. Install it with: pip install pycirclize"
        ) from exc

    n_runs, n_turns = data.shape
    sector_name = "Turns"
    circos = Circos(
        {sector_name: n_turns},
        start=-90,
        end=270,
        space=2,
        endspace=False,
    )
    sector = circos.sectors[0]

    x = np.arange(n_turns) + 0.5
    rate_per_turn = data.mean(axis=0)
    first_counts = np.zeros(n_turns, dtype=float)
    for row in data:
        for idx, val in enumerate(row):
            if val:
                first_counts[idx] += 1
                break

    axis_track = sector.add_track((94, 100))
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

    rate_track = sector.add_track((82, 92), r_pad_ratio=0.06)
    rate_track.axis(ec=PALETTE["grid"], lw=0.4)
    rate_track.line(
        x,
        rate_per_turn,
        vmin=0,
        vmax=1,
        color=PALETTE["rate"],
        lw=1.2,
    )
    rate_track.fill_between(
        x,
        rate_per_turn,
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

    bar_track = sector.add_track((68, 80), r_pad_ratio=0.08)
    bar_track.axis(ec=PALETTE["grid"], lw=0.4)
    bar_track.bar(
        x,
        first_counts,
        vmin=0,
        vmax=max(1, float(first_counts.max())),
        width=0.8,
        color=PALETTE["misaligned"],
        ec="white",
        lw=0.3,
    )
    bar_track.yticks(
        [0, float(first_counts.max())],
        labels=["0", f"{int(first_counts.max())}"],
        vmin=0,
        vmax=max(1, float(first_counts.max())),
        label_size=7,
        line_kws=dict(ec=PALETTE["grid"], lw=0.4),
        text_kws=dict(color=PALETTE["muted"]),
    )

    heat_track = sector.add_track((50, 66), r_pad_ratio=0.02)
    heat_track.axis(ec=PALETTE["grid"], lw=0.4)
    binned = _bin_runs(data, run_bins)
    cmap = LinearSegmentedColormap.from_list(
        "misalign",
        ["#ffffff", PALETTE["misaligned"]],
    )
    heat_track.heatmap(
        binned,
        vmin=0,
        vmax=1,
        cmap=cmap,
        rect_kws=dict(ec="white", lw=0.2),
    )

    def _interval(turn: int) -> Tuple[float, float]:
        start = max(0.0, float(turn - 1))
        end = min(float(n_turns), float(turn))
        return start, end

    if link_mode in ("first-recovery", "both"):
        counts, unresolved = _first_recovery_links(data)
        links = _filter_links(
            counts,
            min_count=min_link_count,
            max_links=max_links,
        )
        max_count = max((c for _, _, c in links), default=1)
        for start, end, count in links:
            alpha = 0.08 + 0.42 * (count / max_count)
            circos.link(
                (sector_name, *_interval(start)),
                (sector_name, *_interval(end)),
                color=to_rgba(PALETTE["rate"], alpha),
                ec="none",
                lw=0,
            )
        if unresolved:
            circos.text(
                f"No recovery: {unresolved}",
                r=46,
                deg=0,
                size=7,
                color=PALETTE["muted"],
                ha="left",
                va="center",
            )

    if link_mode in ("segments", "both"):
        seg_counts = _segment_links(data)
        links = _filter_links(
            seg_counts,
            min_count=min_link_count,
            max_links=max_links,
        )
        max_count = max((c for _, _, c in links), default=1)
        for start, end, count in links:
            alpha = 0.06 + 0.36 * (count / max_count)
            circos.link(
                (sector_name, *_interval(start)),
                (sector_name, *_interval(end)),
                color=to_rgba(PALETTE["misaligned"], alpha),
                ec="none",
                lw=0,
            )

    fig = circos.plotfig()
    w, h = fig.get_size_inches()
    fig.set_size_inches(w, h)
    fig.subplots_adjust(right=0.74)
    fig.suptitle(f"{label} misalignment overview", fontsize=20, y=0.9)
    fig.text(
        0.5,
        0.015,
        f"Runs: {n_runs} | Turns: {n_turns} | Overall rate: {rate_per_turn.mean():.1%}",
        ha="center",
        fontsize=15,
        fontweight="semibold",
        color=PALETTE["ink"],
    )
    _add_circos_track_legend(
        fig,
        include_links=link_mode in ("first-recovery", "segments", "both"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.set_constrained_layout(False)
    fig.set_tight_layout(False)
    fig.savefig(output_path, bbox_inches=None)
    plt.close(fig)


def plot_comparison(
    series: Iterable[Tuple[str, List[int], np.ndarray]], output_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    series_list = list(series)
    colors = series_colors(len(series_list))
    for (label, turns, rate), color in zip(series_list, colors):
        ax.plot(turns, rate, lw=1.6, label=label, color=color)
    ax.set_title("Misalignment rate comparison")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(True, axis="y", color=PALETTE["grid"], alpha=0.6, linestyle="-")
    ax.legend(frameon=False, fontsize=7, ncol=1)
    _soften_spines(ax)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    set_nature_style()

    inputs = [Path(p) for p in args.inputs]
    for path in inputs:
        if not path.exists():
            raise SystemExit(f"[ERR] File not found: {path}")

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
                run_bins=args.run_bins,
            )
        else:
            plot_circos(data, turns, label, output_path)
        dashboards.append((label, turns, data.mean(axis=0)))
        print(f"[INFO] Saved figure to {output_path}")

    if args.compare_output and len(dashboards) > 1:
        plot_comparison(dashboards, args.compare_output)
        print(f"[INFO] Saved comparison plot to {args.compare_output}")


if __name__ == "__main__":
    main()
