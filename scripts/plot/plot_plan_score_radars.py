#!/usr/bin/env python3
"""
Plot per-model radar charts from plan_scores*.csv files (publication-ready).

Each output figure corresponds to one model and shows multiple conditions
(LLM, Agent, Agent + Web, etc.) as radar lines.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.projections.polar import PolarAxes

DIMENSIONS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_parameterization",
    "scientific_rigor",
]

CONDITION_ORDER = [
    "LLM",
    "Agent",
    "Agent + Web",
    "Agent + GraphRAG",
    "Agent + Web + GraphRAG",
]

# Paul Tol (muted) inspired palette: colorblind-friendly + print-friendly
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
class RunStats:
    label: str
    model: str
    condition: str
    scores: Dict[str, float]


def set_publication_style() -> None:
    """A clean, journal-like matplotlib style without seaborn."""
    plt.rcParams.update({
        # Fonts
        "font.family": "DejaVu Sans",  # portable; swap to Arial/Helvetica if available
        "font.size": 9,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        # Lines
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        # Figure / save
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        # Grid
        "axes.grid": True,
        "grid.linewidth": 0.8,
        "grid.alpha": 0.35,
        # Legend
        "legend.frameon": False,
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot radar charts per model from plan_scores CSVs."
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        help="Optional list of run directories to include (e.g., results/agent_plans_phage_qwen).",
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
        "--eval-tag",
        nargs="+",
        help=(
            "Optional eval tag(s) to select plan_scores_<tag>.csv files "
            "(e.g., qwen deepseekv3). If omitted with --run-dirs, runs all "
            "tags found in every run dir."
        ),
    )
    parser.add_argument(
        "--labels", nargs="+", help="Optional labels matching --files order."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/plots/radars"),
        help="Output directory for radar plots.",
    )
    parser.add_argument(
        "--include-model",
        nargs="+",
        help="Optional list of model names to include (case-insensitive).",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Figure DPI for PNG.")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf"],
        help="Output formats, e.g. png pdf svg. Default: png pdf",
    )
    parser.add_argument(
        "--title-suffix",
        default="Plan Quality Radar",
        help="Suffix shown in the figure title.",
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


def _extract_tag(path: Path) -> Optional[str]:
    stem = path.stem.lower()
    for prefix in ("plan_scores_", "results_"):
        if stem.startswith(prefix):
            tag = stem[len(prefix) :].strip()
            return _strip_timestamp(tag) or None
    return None


def _strip_timestamp(tag: str) -> str:
    if not tag:
        return tag
    # Remove trailing _YYYYMMDD_HHMMSS if present
    return re.sub(r"_\d{8}_\d{6}$", "", tag)


def _extract_timestamp(path: Path) -> Optional[str]:
    match = re.search(r"_\d{8}_\d{6}\.csv$", path.name)
    if not match:
        return None
    return match.group(0).lstrip("_").replace(".csv", "")


def find_score_files_in_runs(
    run_dirs: Sequence[str], eval_tag: Optional[str]
) -> List[Path]:
    files: List[Path] = []
    tag = eval_tag.lower() if eval_tag else None
    for raw in run_dirs:
        root = Path(raw)
        if not root.exists():
            print(f"[WARN] Run dir not found: {root}")
            continue
        all_candidates = list(root.rglob("plan_scores*.csv"))
        if not all_candidates:
            print(f"[WARN] No plan_scores*.csv found under {root}")
            continue
        candidates = all_candidates
        if tag:
            candidates = [p for p in all_candidates if _extract_tag(p) == tag]
        if not candidates:
            if tag:
                available = sorted(
                    {t for t in (_extract_tag(p) for p in all_candidates) if t}
                )
                print(
                    f"[WARN] No files matched eval tag '{tag}' under {root}. "
                    f"Available tags: {available or 'none'}"
                )
            continue
        candidates = sorted(candidates)
        if len(candidates) > 1:
            # Prefer timestamped files; fallback to most recently modified
            ts_pattern = re.compile(r"_\d{8}_\d{6}\.csv$")
            ts_candidates = [p for p in candidates if ts_pattern.search(p.name)]
            if ts_candidates:
                chosen = max(
                    ts_candidates,
                    key=lambda p: _extract_timestamp(p) or "",
                )
                reason = "latest timestamped"
            else:
                chosen = max(candidates, key=lambda p: p.stat().st_mtime)
                reason = "latest modified"
            print(
                f"[INFO] Multiple score files under {root}; "
                f"using {reason} file: {chosen}"
            )
            files.append(chosen)
        else:
            chosen = candidates[0]
            print(f"[INFO] Using score file: {chosen}")
            files.append(chosen)
    return files


def collect_eval_tags(run_dirs: Sequence[str]) -> Dict[str, int]:
    tag_counts: Dict[str, int] = {}
    for raw in run_dirs:
        root = Path(raw)
        if not root.exists():
            continue
        for path in root.rglob("plan_scores*.csv"):
            tag = _extract_tag(path)
            if not tag:
                continue
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return tag_counts


def infer_label(path: Path) -> str:
    parent2 = path.parent.parent.name if path.parent.parent else ""
    return parent2 or path.stem


def detect_model(label: str) -> str:
    low = label.lower()
    if "deepseek" in low:
        return "DeepSeek-V3"
    if "qwen" in low:
        return "Qwen3-Max"
    if "glm" in low:
        return "GLM"
    if "gpt" in low:
        return "GPT"
    return "Unknown"


def detect_condition(label: str) -> str:
    low = label.lower()
    if "llm" in low:
        return "LLM"
    if "agent" in low:
        if "web" in low and ("rag" in low or "graph" in low):
            return "Agent + Web + GraphRAG"
        if "web" in low:
            return "Agent + Web"
        if "rag" in low or "graph" in low:
            return "Agent + GraphRAG"
        return "Agent"
    return label.strip()


def mean_scores(path: Path) -> Dict[str, float]:
    values: Dict[str, List[float]] = {dim: [] for dim in DIMENSIONS}
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            for dim in DIMENSIONS:
                try:
                    values[dim].append(float(row.get(dim, "nan")))
                except Exception:
                    continue
    scores: Dict[str, float] = {}
    for dim in DIMENSIONS:
        vals = [v for v in values[dim] if not math.isnan(v)]
        scores[dim] = sum(vals) / len(vals) if vals else 0.0
    return scores


def load_runs(paths: Sequence[Path], labels: Optional[Sequence[str]]) -> List[RunStats]:
    runs: List[RunStats] = []
    for idx, path in enumerate(paths):
        if not path.exists():
            continue
        label = labels[idx] if labels and idx < len(labels) else infer_label(path)
        runs.append(
            RunStats(
                label=label,
                model=detect_model(label),
                condition=detect_condition(label),
                scores=mean_scores(path),
            )
        )
    if not runs:
        raise RuntimeError("No score data loaded. Check file paths.")
    return runs


def metric_labels() -> List[str]:
    return [
        "Contextual\nCompleteness",
        "Accuracy",
        "Task\nGranularity",
        "Reproducibility",
        "Scientific\nRigor",
    ]


def sort_conditions(runs: List[RunStats]) -> List[RunStats]:
    order = {name: idx for idx, name in enumerate(CONDITION_ORDER)}
    return sorted(runs, key=lambda r: (order.get(r.condition, 99), r.condition))


def infer_score_max(runs: List[RunStats]) -> int:
    max_val = 0.0
    for run in runs:
        for dim in DIMENSIONS:
            max_val = max(max_val, run.scores.get(dim, 0.0))
    if max_val <= 0:
        return 5
    return max(5, int(math.ceil(max_val)))


def plot_model_radar(
    model: str,
    runs: List[RunStats],
    output_base: Path,
    dpi: int,
    formats: Sequence[str],
    title_suffix: str,
) -> None:
    runs = sort_conditions(runs)
    labels = metric_labels()
    score_max = infer_score_max(runs)
    tick_step = 1 if score_max <= 10 else 2

    angles = np.linspace(0, 2 * np.pi, len(DIMENSIONS), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7.2, 5.6), subplot_kw={"polar": True})

    # Scheme 1 (type narrowing): keep runtime behavior, satisfy Pylance.
    assert isinstance(ax, PolarAxes), f"Expected PolarAxes, got {type(ax)}"

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    for t in ax.get_xticklabels():
        t.set_fontweight("semibold")

    ax.set_ylim(1, score_max)
    ticks = list(range(1, score_max + 1, tick_step))
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(t) for t in ticks], fontsize=8)
    ax.set_rlabel_position(90)

    ax.grid(True)
    ax.spines["polar"].set_alpha(0.25)
    ax.spines["polar"].set_linewidth(0.9)

    handles = []
    for idx, run in enumerate(runs):
        values = [run.scores.get(dim, 0.0) for dim in DIMENSIONS]
        values += values[:1]
        color = PUB_PALETTE[idx % len(PUB_PALETTE)]

        h = ax.plot(
            angles,
            values,
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=3.6,
            markerfacecolor="white",
            markeredgewidth=1.2,
            label=run.condition,
            zorder=3,
        )[0]
        ax.fill(angles, values, color=color, alpha=0.08, zorder=2)
        handles.append(h)

    ax.set_title(
        f"{model} — {title_suffix}", fontsize=12, pad=18, fontweight="semibold"
    )

    legend = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.05),
        borderaxespad=0.0,
        fontsize=9,
        ncol=1,
        handlelength=2.4,
        labelspacing=0.6,
    )

    output_base.parent.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        fmt = fmt.lower().lstrip(".")
        out = output_base.with_suffix(f".{fmt}")
        save_kwargs = {}
        if fmt in ("png", "jpg", "jpeg", "tif", "tiff"):
            save_kwargs["dpi"] = dpi
        fig.savefig(out, bbox_extra_artists=(legend,), **save_kwargs)
        print(f"[OK] Saved {out}")

    plt.close(fig)


def main() -> None:
    set_publication_style()
    args = parse_args()

    def _resolve_paths(tag: Optional[str]) -> tuple[List[Path], Optional[List[str]]]:
        labels = args.labels
        if args.files:
            paths = [Path(p) for p in args.files]
            if tag:
                if labels:
                    pairs = [
                        (p, label)
                        for p, label in zip(paths, labels)
                        if tag in p.stem.lower()
                    ]
                    paths = [p for p, _ in pairs]
                    labels = [label for _, label in pairs]
                else:
                    paths = [p for p in paths if tag in p.stem.lower()]
        elif args.run_dirs:
            paths = find_score_files_in_runs(args.run_dirs, tag)
        else:
            paths = find_score_files(args.scores_dir)
            if tag:
                if labels:
                    pairs = [
                        (p, label)
                        for p, label in zip(paths, labels)
                        if tag in p.stem.lower()
                    ]
                    paths = [p for p, _ in pairs]
                    labels = [label for _, label in pairs]
                else:
                    paths = [p for p in paths if tag in p.stem.lower()]
        return paths, labels

    eval_tags: List[str] = []
    if args.eval_tag:
        eval_tags = [tag.lower() for tag in args.eval_tag]
    elif args.run_dirs:
        tag_counts = collect_eval_tags(args.run_dirs)
        if tag_counts:
            total_runs = len(args.run_dirs)
            eval_tags = [
                tag for tag, count in tag_counts.items() if count == total_runs
            ]
            eval_tags = sorted(eval_tags)
            if not eval_tags:
                eval_tags = sorted(tag_counts.keys())
                print(
                    "[WARN] No eval tag is shared across all run dirs; using union instead."
                )

    tags_to_run: Sequence[Optional[str]] = eval_tags if eval_tags else [None]

    for tag in tags_to_run:
        paths, labels = _resolve_paths(tag)
        if not paths:
            if tag:
                print(f"[WARN] No plan_scores files matched eval tag '{tag}'.")
                continue
            raise SystemExit("[ERR] No plan_scores files found.")

        if labels and len(labels) != len(paths):
            print("[WARN] --labels length does not match paths; ignoring labels.")
            labels = None

        runs = load_runs(paths, labels)

        include = [m.lower() for m in args.include_model] if args.include_model else None
        by_model: Dict[str, List[RunStats]] = {}
        for run in runs:
            if include and run.model.lower() not in include:
                continue
            by_model.setdefault(run.model, []).append(run)

        if not by_model:
            print("[WARN] No runs matched the selected models.")
            continue

        output_root = args.output_dir
        title_suffix = args.title_suffix
        if tag:
            output_root = output_root / f"eval_{tag}"
            title_suffix = f"{title_suffix} ({tag})"

        for model, model_runs in by_model.items():
            slug = model.lower().replace(" ", "_").replace("-", "_")
            output_base = output_root / f"radar_{slug}"
            plot_model_radar(
                model=model,
                runs=model_runs,
                output_base=output_base,
                dpi=args.dpi,
                formats=args.formats,
                title_suffix=title_suffix,
            )


if __name__ == "__main__":
    main()
