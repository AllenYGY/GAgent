#!/usr/bin/env python3
"""
Plot per-metric vertical violin plots from plan_scores*.csv files.

Each metric is plotted in its own figure with one violin per run/model.

Publication-style adjustments:
- Violin only (NO boxplot overlay)
- NO scatter/dots on top
- Optional median line (on by default; can disable with --no-median)
- Auto y axis for integer scores (defaults to 1..5, expands for 10pt)
- Stronger, colorblind-friendly palette
- Default export: PNG only
- Pylance-friendly typing for matplotlib violinplot return types
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection, PolyCollection

DIMENSIONS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_execution",
    "scientific_rigor",
    "innovation_feasibility",
]

# Colorblind- and print-friendly palette (Paul Tol-like)
PUB_PALETTE = [
    "#4477AA",  # blue
    "#228833",  # green
    "#CCBB44",  # yellow/olive
    "#EE6677",  # red/pink
    "#AA3377",  # purple
    "#66CCEE",  # cyan
    "#BBBBBB",  # gray fallback
]


@dataclass(frozen=True)
class MetricSeries:
    pretty_labels: List[str]
    series: List[List[float]]


def set_publication_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "axes.grid": True,
        "grid.linewidth": 0.8,
        "grid.alpha": 0.22,
        "legend.frameon": False,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot per-metric violin plots from plan_scores CSVs."
    )
    parser.add_argument(
        "--files", nargs="+", help="plan_scores*.csv files (preferred)."
    )
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=Path("results"),
        help="Directory to scan for plan_scores*.csv if --files is not provided.",
    )
    parser.add_argument(
        "--labels", nargs="+", help="Optional labels matching --files order."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/plots/violins"),
        help="Output directory for violin plots.",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        choices=DIMENSIONS,
        help="Optional subset of metrics to plot.",
    )

    # Export (user requested no PDF)
    parser.add_argument("--dpi", type=int, default=300, help="Figure DPI for PNG.")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png"],
        help="Output formats (e.g., png svg). Default: png",
    )

    # Visual controls
    parser.add_argument(
        "--rotate-x",
        type=float,
        default=20.0,
        help="X tick label rotation angle (degrees).",
    )
    parser.add_argument(
        "--no-median",
        action="store_true",
        help="Disable median line inside violins.",
    )
    return parser.parse_args()


def find_score_files(scores_dir: Path) -> List[Path]:
    if not scores_dir.exists():
        raise FileNotFoundError(f"Scores directory not found: {scores_dir}")
    patterns = ["plan_scores*.csv", "results*.csv"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(scores_dir.rglob(pat))
    files = sorted(set(files))
    if not files:
        raise FileNotFoundError(
            f"No plan_scores*.csv or results*.csv files found under {scores_dir}."
        )
    return files


def infer_label(path: Path) -> str:
    parent2 = path.parent.parent.name if path.parent.parent else ""
    return parent2 or path.stem


def load_scores(
    paths: List[Path], labels: Optional[List[str]]
) -> Dict[str, Dict[str, List[float]]]:
    data: Dict[str, Dict[str, List[float]]] = {}
    for idx, path in enumerate(paths):
        if not path.exists():
            continue
        label = labels[idx] if labels and idx < len(labels) else infer_label(path)
        values: Dict[str, List[float]] = {dim: [] for dim in DIMENSIONS}
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for dim in DIMENSIONS:
                    try:
                        v = float(row.get(dim, "nan"))
                        if not math.isnan(v):
                            values[dim].append(v)
                    except Exception:
                        continue
        data[label] = values

    if not data:
        raise RuntimeError("No score data loaded. Check file paths.")
    return data


def prettify_label(label: str) -> str:
    low = label.lower()
    model = None
    if "deepseek" in low:
        model = "DeepSeek-V3"
    elif "qwen" in low:
        model = "Qwen3-Max"
    elif "gemini" in low:
        model = "Gemini-3-Pro"
    elif "grok" in low:
        model = "Grok-4"
    elif "gpt52" in low or "gpt-5.2" in low or "gpt5" in low:
        model = "GPT-5.2-Chat"
    elif "glm" in low:
        model = "GLM"
    elif "gpt" in low:
        model = "GPT"

    if "agent" in low:
        if "web" in low and ("rag" in low or "graph" in low):
            base = "Agent + Web + GraphRAG"
        elif "web" in low:
            base = "Agent + Web"
        elif "rag" in low or "graph" in low:
            base = "Agent + GraphRAG"
        else:
            base = "Agent"
    elif "llm" in low:
        base = "LLM"
    else:
        base = label.strip()

    if model and base:
        return f"{base} ({model})"
    return base or label.strip()


def collect_metric_series(
    metric: str, data: Dict[str, Dict[str, List[float]]]
) -> MetricSeries:
    pretty_labels: List[str] = []
    series: List[List[float]] = []
    for label, values in data.items():
        vals = values.get(metric, [])
        if not vals:
            continue
        pretty_labels.append(prettify_label(label))
        series.append(vals)
    return MetricSeries(pretty_labels=pretty_labels, series=series)


def metric_title(metric: str) -> str:
    return metric.replace("_", " ").title()


def choose_colors(n: int) -> List[str]:
    return [PUB_PALETTE[i % len(PUB_PALETTE)] for i in range(n)]


def infer_score_max(series: Sequence[Sequence[float]]) -> int:
    max_val = 0.0
    for vals in series:
        if not vals:
            continue
        max_val = max(max_val, max(vals))
    if max_val <= 0:
        return 5
    return max(5, int(math.ceil(max_val)))


def plot_metric_violin(
    metric: str,
    data: Dict[str, Dict[str, List[float]]],
    output_base: Path,
    dpi: int,
    formats: Sequence[str],
    rotate_x: float,
    show_median: bool,
) -> None:
    ms = collect_metric_series(metric, data)
    if not ms.series:
        print(f"[WARN] No values for metric {metric}; skipping.")
        return

    n = len(ms.series)
    max_label_len = max((len(s) for s in ms.pretty_labels), default=10)

    # Sizing: compact but readable
    fig_w = max(7.2, min(12.0, 0.92 * n + 4.8))
    fig_h = max(4.6, min(6.6, 4.6 + max(0, (max_label_len - 18)) * 0.03))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    positions = np.arange(1, n + 1)
    colors = choose_colors(n)

    vp = ax.violinplot(
        dataset=ms.series,
        positions=positions,
        widths=0.86,
        showmeans=False,
        showmedians=show_median,
        showextrema=False,
    )

    # Pylance-friendly cast: vp["bodies"] can be typed weirdly in stubs
    bodies = cast(Iterable[PolyCollection], vp["bodies"])
    for i, body in enumerate(bodies):
        c = colors[i % len(colors)]
        body.set_facecolor(c)
        body.set_edgecolor(c)
        body.set_alpha(0.78)  # <- 比之前更“实”，不会太淡
        body.set_linewidth(1.6)
        body.set_zorder(2)

    # Style median line (not a dot). Keep subtle, not pure black.
    if show_median and "cmedians" in vp:
        med = cast(LineCollection, vp["cmedians"])
        med.set_color("#374151")  # dark gray
        med.set_linewidth(1.8)
        med.set_alpha(0.9)
        med.set_zorder(3)

    # Axis: integer score range (auto-detect 5pt vs 10pt)
    score_max = infer_score_max(ms.series)
    ax.set_ylim(0.5, score_max + 0.5)
    ax.set_yticks(list(range(1, score_max + 1)))
    ax.set_ylabel("Score")

    ax.set_xlim(0.4, n + 0.6)
    ax.set_xticks(positions)
    ax.set_xticklabels(ms.pretty_labels, rotation=rotate_x, ha="right")

    # Grid: y only
    ax.grid(axis="y", linestyle="-", linewidth=0.8, alpha=0.22)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)

    # Clean spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    title = metric_title(metric)
    ax.set_title(f"{title} — Violin Distribution", pad=10, fontweight="semibold")

    # Save (PNG only by default)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        fmt = fmt.lower().lstrip(".")
        out = output_base.with_suffix(f".{fmt}")
        save_kwargs = {}
        if fmt in ("png", "jpg", "jpeg", "tif", "tiff"):
            save_kwargs["dpi"] = dpi
        fig.savefig(out, **save_kwargs)
        print(f"[OK] Saved {out}")

    plt.close(fig)


def main() -> None:
    set_publication_style()
    args = parse_args()

    if args.files:
        paths = [Path(p) for p in args.files]
    else:
        paths = find_score_files(args.scores_dir)

    if args.labels and len(args.labels) != len(paths):
        raise SystemExit("[ERR] --labels length must match --files length.")

    data = load_scores(paths, args.labels)
    metrics = args.metrics or DIMENSIONS

    for metric in metrics:
        output_base = args.output_dir / f"violin_{metric}"
        plot_metric_violin(
            metric=metric,
            data=data,
            output_base=output_base,
            dpi=args.dpi,
            formats=args.formats,
            rotate_x=args.rotate_x,
            show_median=(not args.no_median),
        )


if __name__ == "__main__":
    main()
