#!/usr/bin/env python3
"""
Plot radar charts per generator model after averaging scores across evaluators.

For each run directory (e.g. agent_plans_phage_gemini), the script:
1. selects the latest score file for each evaluator tag,
2. computes per-dimension means inside each score file,
3. averages those dimension means across evaluators,
4. plots one radar per generator model with conditions as separate lines.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.projections.polar import PolarAxes

DIMENSIONS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_execution",
    "scientific_rigor",
    "innovation_feasibility",
]

CONDITION_ORDER = [
    "LLM",
    "Agent",
    "Agent + Web",
    "Agent + GraphRAG",
    "Agent + Web + GraphRAG",
]

PUB_PALETTE = [
    "#4477AA",
    "#228833",
    "#CCBB44",
    "#EE6677",
    "#AA3377",
    "#66CCEE",
    "#BBBBBB",
]


@dataclass(frozen=True)
class AveragedRunStats:
    label: str
    model: str
    condition: str
    scores: Dict[str, float]
    eval_tags: tuple[str, ...]


def set_publication_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "axes.grid": True,
        "grid.linewidth": 0.8,
        "grid.alpha": 0.35,
        "legend.frameon": False,
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot radar charts after averaging plan scores across evaluators."
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Run directories, e.g. results/agent_plans_phage_gemini.",
    )
    parser.add_argument(
        "--eval-tag",
        nargs="+",
        help=(
            "Optional evaluator tags to average across, e.g. qwen_10pt deepseekv3_10pt "
            "gemini_10pt gpt52chat_10pt. If omitted, the script uses the tag intersection "
            "shared by all run dirs."
        ),
    )
    parser.add_argument(
        "--include-model",
        nargs="+",
        help="Optional list of generator model names to include (case-insensitive).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/plots_eval_all_models/score_radars_mean_eval"),
        help="Output directory for averaged radar plots.",
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
        default="Mean Across Evaluators",
        help="Suffix shown in the figure title.",
    )
    return parser.parse_args()


def _strip_timestamp(tag: str) -> str:
    return re.sub(r"_\d{8}_\d{6}$", "", tag)


def _extract_tag(path: Path) -> Optional[str]:
    match = re.match(r"plan_scores_(.+?)(?:_\d{8}_\d{6})?\.csv$", path.name.lower())
    if not match:
        return None
    return _strip_timestamp(match.group(1))


def _extract_timestamp(path: Path) -> str:
    match = re.search(r"_(\d{8}_\d{6})\.csv$", path.name)
    return match.group(1) if match else ""


def infer_label(path: Path) -> str:
    return path.name


def detect_model(label: str) -> str:
    low = label.lower()
    if "deepseek" in low:
        return "DeepSeek-V3"
    if "qwen" in low:
        return "Qwen3-Max"
    if "gemini" in low:
        return "Gemini-3-Pro"
    if "grok" in low:
        return "Grok-4"
    if "gpt52" in low or "gpt-5.2" in low or "gpt5" in low:
        return "GPT-5.2-Chat"
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


def metric_labels() -> List[str]:
    return [
        "Contextual\nCompleteness",
        "Accuracy",
        "Task\nGranularity",
        "Reproducibility\n& Execution",
        "Scientific\nRigor",
        "Innovation\n& Feasibility",
    ]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


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


def average_score_dicts(score_dicts: Sequence[Dict[str, float]]) -> Dict[str, float]:
    avg: Dict[str, float] = {}
    for dim in DIMENSIONS:
        vals = [scores.get(dim, 0.0) for scores in score_dicts]
        avg[dim] = sum(vals) / len(vals) if vals else 0.0
    return avg


def collect_eval_files(run_dir: Path) -> Dict[str, Path]:
    files: Dict[str, List[Path]] = {}
    for path in run_dir.rglob("plan_scores*.csv"):
        tag = _extract_tag(path)
        if not tag:
            continue
        files.setdefault(tag, []).append(path)
    chosen: Dict[str, Path] = {}
    for tag, candidates in files.items():
        if len(candidates) == 1:
            chosen[tag] = candidates[0]
            continue
        timestamped = [p for p in candidates if _extract_timestamp(p)]
        if timestamped:
            chosen[tag] = max(timestamped, key=_extract_timestamp)
        else:
            chosen[tag] = max(candidates, key=lambda p: p.stat().st_mtime)
    return chosen


def choose_eval_tags(
    per_run: Dict[Path, Dict[str, Path]],
    requested_tags: Optional[Sequence[str]],
) -> List[str]:
    if requested_tags:
        return [tag.lower() for tag in requested_tags]
    tag_sets = [set(tag_map.keys()) for tag_map in per_run.values() if tag_map]
    if not tag_sets:
        return []
    shared = set.intersection(*tag_sets)
    if shared:
        return sorted(shared)
    union = sorted(set().union(*tag_sets))
    print(
        "[WARN] No evaluator tag is shared across all run dirs; using the union instead."
    )
    return union


def build_runs(
    run_dirs: Sequence[str],
    eval_tags: Sequence[str],
) -> List[AveragedRunStats]:
    per_run: Dict[Path, Dict[str, Path]] = {}
    for raw in run_dirs:
        root = Path(raw)
        if not root.exists():
            print(f"[WARN] Run dir not found: {root}")
            continue
        tag_map = collect_eval_files(root)
        if not tag_map:
            print(f"[WARN] No plan_scores*.csv found under {root}")
            continue
        per_run[root] = tag_map

    selected_tags = choose_eval_tags(per_run, eval_tags)
    if not selected_tags:
        raise RuntimeError("No evaluator tags available for averaging.")

    print(f"[INFO] Evaluator tags used for averaging: {selected_tags}")

    runs: List[AveragedRunStats] = []
    for root, tag_map in per_run.items():
        score_dicts: List[Dict[str, float]] = []
        used_tags: List[str] = []
        missing_tags: List[str] = []
        for tag in selected_tags:
            path = tag_map.get(tag)
            if not path:
                missing_tags.append(tag)
                continue
            score_dicts.append(mean_scores(path))
            used_tags.append(tag)
        if not score_dicts:
            print(f"[WARN] Skipping {root}; none of the selected evaluator tags were found.")
            continue
        if missing_tags:
            print(f"[WARN] {root} missing evaluator tags: {missing_tags}")
        label = infer_label(root)
        runs.append(
            AveragedRunStats(
                label=label,
                model=detect_model(label),
                condition=detect_condition(label),
                scores=average_score_dicts(score_dicts),
                eval_tags=tuple(used_tags),
            )
        )
    if not runs:
        raise RuntimeError("No averaged score data loaded. Check run directories.")
    return runs


def sort_conditions(runs: Iterable[AveragedRunStats]) -> List[AveragedRunStats]:
    order = {name: idx for idx, name in enumerate(CONDITION_ORDER)}
    return sorted(runs, key=lambda r: (order.get(r.condition, 99), r.condition))


def infer_score_max(runs: Sequence[AveragedRunStats]) -> int:
    max_val = 0.0
    for run in runs:
        for dim in DIMENSIONS:
            max_val = max(max_val, run.scores.get(dim, 0.0))
    if max_val <= 0:
        return 5
    return max(5, int(math.ceil(max_val)))


def write_summary_csv(output_dir: Path, runs: Sequence[AveragedRunStats]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "mean_across_evaluators_summary.csv"
    fieldnames = [
        "label",
        "model",
        "condition",
        "num_evaluators",
        "evaluator_tags",
        *DIMENSIONS,
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            row = {
                "label": run.label,
                "model": run.model,
                "condition": run.condition,
                "num_evaluators": len(run.eval_tags),
                "evaluator_tags": ",".join(run.eval_tags),
            }
            row.update({dim: f"{run.scores.get(dim, 0.0):.4f}" for dim in DIMENSIONS})
            writer.writerow(row)
    print(f"[OK] Saved {summary_path}")


def plot_model_radar(
    model: str,
    runs: Sequence[AveragedRunStats],
    output_base: Path,
    dpi: int,
    formats: Sequence[str],
    title_suffix: str,
) -> None:
    ordered_runs = sort_conditions(runs)
    labels = metric_labels()
    score_max = infer_score_max(ordered_runs)
    tick_step = 1 if score_max <= 10 else 2
    eval_tags = sorted({tag for run in ordered_runs for tag in run.eval_tags})

    angles = np.linspace(0, 2 * np.pi, len(DIMENSIONS), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7.4, 5.8), subplot_kw={"polar": True})
    assert isinstance(ax, PolarAxes), f"Expected PolarAxes, got {type(ax)}"

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    for tick in ax.get_xticklabels():
        tick.set_fontweight("semibold")

    ax.set_ylim(1, score_max)
    ticks = list(range(1, score_max + 1, tick_step))
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(tick) for tick in ticks], fontsize=8)
    ax.set_rlabel_position(90)
    ax.grid(True)
    ax.spines["polar"].set_alpha(0.25)
    ax.spines["polar"].set_linewidth(0.9)

    handles = []
    for idx, run in enumerate(ordered_runs):
        values = [run.scores.get(dim, 0.0) for dim in DIMENSIONS]
        values += values[:1]
        color = PUB_PALETTE[idx % len(PUB_PALETTE)]
        handle = ax.plot(
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
        handles.append(handle)

    ax.set_title(
        f"{model} — {title_suffix}",
        fontsize=12,
        pad=18,
        fontweight="semibold",
    )
    fig.text(
        0.5,
        0.02,
        f"Averaged evaluators: {', '.join(eval_tags)}",
        ha="center",
        va="bottom",
        fontsize=8,
        color="#5B6573",
    )

    legend = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.05),
        borderaxespad=0.0,
        fontsize=9,
        handlelength=2.4,
        labelspacing=0.6,
    )

    output_base.parent.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        ext = fmt.lower().lstrip(".")
        out = output_base.with_suffix(f".{ext}")
        save_kwargs = {}
        if ext in ("png", "jpg", "jpeg", "tif", "tiff"):
            save_kwargs["dpi"] = dpi
        fig.savefig(out, bbox_extra_artists=(legend,), **save_kwargs)
        print(f"[OK] Saved {out}")
    plt.close(fig)


def main() -> None:
    set_publication_style()
    args = parse_args()

    runs = build_runs(args.run_dirs, args.eval_tag)
    include = [name.lower() for name in args.include_model] if args.include_model else None

    write_summary_csv(args.output_dir, runs)

    by_model: Dict[str, List[AveragedRunStats]] = {}
    for run in runs:
        if include and run.model.lower() not in include:
            continue
        by_model.setdefault(run.model, []).append(run)

    if not by_model:
        raise SystemExit("[ERR] No runs matched the selected models.")

    for model, model_runs in sorted(by_model.items()):
        output_base = args.output_dir / f"radar_mean_eval_{slugify(model)}"
        plot_model_radar(
            model=model,
            runs=model_runs,
            output_base=output_base,
            dpi=args.dpi,
            formats=args.formats,
            title_suffix=args.title_suffix,
        )


if __name__ == "__main__":
    main()
