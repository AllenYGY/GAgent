#!/usr/bin/env python3
"""
Aggregate plan-quality score CSVs into paper-friendly summary tables.

This script is designed to align with the radar plotting workflow:
`scripts/plot/run_plot_eval_all.sh` + `scripts/plot/plot_plan_score_radars.py`.

Outputs (CSV):
1) selected_score_files.csv
2) plan_quality_file_level.csv
3) plan_quality_grouped.csv
4) plan_quality_gain_vs_llm.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple


DIMENSIONS = [
    "contextual_completeness",
    "accuracy",
    "task_granularity_atomicity",
    "reproducibility_execution",
    "scientific_rigor",
    "innovation_feasibility",
]

# Compatibility with older score exports.
METRIC_ALIASES = {
    "contextual_completeness": ["contextual_completeness"],
    "accuracy": ["accuracy"],
    "task_granularity_atomicity": ["task_granularity_atomicity"],
    "reproducibility_execution": [
        "reproducibility_execution",
        "reproducibility_parameterization",
    ],
    "scientific_rigor": ["scientific_rigor"],
    "innovation_feasibility": ["innovation_feasibility"],
}

CONDITION_ORDER = [
    "LLM",
    "Agent",
    "Agent + Web",
    "Agent + GraphRAG",
    "Agent + Web + GraphRAG",
]

PLAN_SCORE_RE = re.compile(r"^plan_scores_(?P<tag>.+?)(?:_(?P<ts>\d{8}_\d{6}))?\.csv$")
EVAL_TAG_RE = re.compile(r'--eval-tag\s+"([^"]+)"')
ROOT_RE = re.compile(r'^ROOT="([^"]+)"')


@dataclass(frozen=True)
class ScoreFile:
    path: Path
    run_dir: str
    evaluator_tag: str
    evaluator_model: str
    timestamp: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate plan-quality CSVs into summary tables."
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        help="Optional explicit run directories. If omitted, parse from --plot-script.",
    )
    parser.add_argument(
        "--plot-script",
        type=Path,
        default=Path("scripts/plot/run_plot_eval_all.sh"),
        help="Shell script used to parse default run_dirs and eval tags.",
    )
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=Path("results"),
        help="Fallback scan directory if --run-dirs and --plot-script parsing both fail.",
    )
    parser.add_argument(
        "--eval-tags",
        nargs="+",
        help="Optional evaluator tags (e.g., qwen_10pt deepseekv3_10pt).",
    )
    parser.add_argument(
        "--selection",
        choices=["latest", "all"],
        default="latest",
        help="How to handle multiple files per (run_dir, evaluator_tag).",
    )
    parser.add_argument(
        "--allow-partial-metrics",
        action="store_true",
        help="Allow files missing one or more canonical dimensions.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/analysis/plan_quality"),
        help="Directory for output CSV files.",
    )
    return parser.parse_args()


def parse_plot_script_run_dirs(path: Path) -> List[Path]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")

    root = path.resolve().parents[2]
    for line in text.splitlines():
        match = ROOT_RE.match(line.strip())
        if match:
            root = Path(match.group(1))
            break

    lines = text.splitlines()
    in_block = False
    run_dirs: List[Path] = []
    for raw in lines:
        line = raw.strip()
        if not in_block and line.startswith("run_dirs=("):
            in_block = True
            continue
        if in_block and line == ")":
            break
        if not in_block:
            continue

        match = re.search(r'["\']([^"\']+)["\']', line)
        if not match:
            continue
        value = match.group(1).replace("$ROOT", str(root))
        path_val = Path(value)
        if not path_val.is_absolute():
            path_val = root / path_val
        run_dirs.append(path_val)
    return run_dirs


def parse_plot_script_eval_tags(path: Path) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return sorted(set(EVAL_TAG_RE.findall(text)))


def parse_tag_and_timestamp(path: Path) -> Tuple[str, str]:
    match = PLAN_SCORE_RE.match(path.name)
    if not match:
        return "", ""
    tag = match.group("tag") or ""
    ts = match.group("ts") or ""
    return tag, ts


def normalize_model_name(raw: str) -> str:
    low = raw.lower()
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
    return raw


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
    return label


def infer_evaluator_model(evaluator_tag: str) -> str:
    base = evaluator_tag
    if "_10pt" in base:
        base = base.split("_10pt", 1)[0]
    return normalize_model_name(base)


def collect_candidates(run_dirs: Sequence[Path], eval_tags: Optional[set[str]]) -> List[ScoreFile]:
    candidates: List[ScoreFile] = []
    for run_dir in run_dirs:
        if not run_dir.exists():
            print(f"[WARN] Run dir not found: {run_dir}")
            continue
        for path in run_dir.rglob("plan_scores*.csv"):
            tag, ts = parse_tag_and_timestamp(path)
            if not tag:
                continue
            if eval_tags and tag not in eval_tags:
                continue
            candidates.append(
                ScoreFile(
                    path=path,
                    run_dir=run_dir.name,
                    evaluator_tag=tag,
                    evaluator_model=infer_evaluator_model(tag),
                    timestamp=ts,
                )
            )
    return candidates


def collect_candidates_from_root(scores_dir: Path, eval_tags: Optional[set[str]]) -> List[ScoreFile]:
    candidates: List[ScoreFile] = []
    if not scores_dir.exists():
        return candidates
    for path in scores_dir.rglob("plan_scores*.csv"):
        tag, ts = parse_tag_and_timestamp(path)
        if not tag:
            continue
        if eval_tags and tag not in eval_tags:
            continue
        run_dir = path.parent.parent.name if path.parent.parent else path.parent.name
        candidates.append(
            ScoreFile(
                path=path,
                run_dir=run_dir,
                evaluator_tag=tag,
                evaluator_model=infer_evaluator_model(tag),
                timestamp=ts,
            )
        )
    return candidates


def select_files(candidates: Sequence[ScoreFile], mode: str) -> List[ScoreFile]:
    if mode == "all":
        return sorted(candidates, key=lambda x: (x.run_dir, x.evaluator_tag, str(x.path)))

    grouped: DefaultDict[Tuple[str, str], List[ScoreFile]] = defaultdict(list)
    for c in candidates:
        grouped[(c.run_dir, c.evaluator_tag)].append(c)

    selected: List[ScoreFile] = []
    for key in sorted(grouped.keys()):
        group = grouped[key]
        group_sorted = sorted(
            group,
            key=lambda x: (
                x.timestamp or "",
                x.path.stat().st_mtime,
                str(x.path),
            ),
        )
        selected.append(group_sorted[-1])
    return selected


def safe_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def first_existing_metric(row: Dict[str, str], aliases: Iterable[str]) -> Optional[float]:
    for key in aliases:
        if key in row:
            value = safe_float(row.get(key))
            if value is not None:
                return value
    return None


def mean(values: Sequence[float]) -> float:
    return float(statistics.mean(values)) if values else float("nan")


def std(values: Sequence[float]) -> float:
    if len(values) <= 1:
        return 0.0 if values else float("nan")
    return float(statistics.stdev(values))


def fmt_num(value: float) -> str:
    if value != value:  # NaN check
        return ""
    return f"{value:.4f}"


def load_file_metrics(path: Path) -> Tuple[Dict[str, List[float]], List[float], List[str], int]:
    metric_values: Dict[str, List[float]] = {dim: [] for dim in DIMENSIONS}
    overall_values: List[float] = []
    missing_metrics = set(DIMENSIONS)
    row_count = 0

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_vals: List[float] = []
            has_any = False
            for dim in DIMENSIONS:
                value = first_existing_metric(row, METRIC_ALIASES[dim])
                if value is None:
                    continue
                metric_values[dim].append(value)
                row_vals.append(value)
                has_any = True
                if dim in missing_metrics:
                    missing_metrics.remove(dim)
            if has_any:
                row_count += 1
                overall_values.append(float(statistics.mean(row_vals)))
    return metric_values, overall_values, sorted(missing_metrics), row_count


def condition_sort_key(condition: str) -> Tuple[int, str]:
    order = {name: idx for idx, name in enumerate(CONDITION_ORDER)}
    return order.get(condition, 99), condition


def write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    eval_tags: Optional[set[str]] = set(args.eval_tags) if args.eval_tags else None

    run_dirs: List[Path] = [Path(p) for p in args.run_dirs] if args.run_dirs else []
    if not run_dirs:
        run_dirs = parse_plot_script_run_dirs(args.plot_script)
        if run_dirs:
            print(f"[INFO] Loaded {len(run_dirs)} run dirs from {args.plot_script}")
    if not eval_tags and args.plot_script.exists():
        script_tags = parse_plot_script_eval_tags(args.plot_script)
        if script_tags:
            eval_tags = set(script_tags)
            print(f"[INFO] Loaded eval tags from {args.plot_script}: {sorted(eval_tags)}")

    if run_dirs:
        candidates = collect_candidates(run_dirs, eval_tags)
    else:
        print("[WARN] Falling back to scanning scores-dir because run dirs are unavailable.")
        candidates = collect_candidates_from_root(args.scores_dir, eval_tags)

    if not candidates:
        raise SystemExit("[ERR] No matching plan_scores CSV files found.")

    selected = select_files(candidates, mode=args.selection)
    print(f"[INFO] Selected {len(selected)} files from {len(candidates)} candidates.")

    selected_rows: List[List[str]] = []
    selected_header = [
        "run_dir",
        "condition",
        "generator_model",
        "evaluator_tag",
        "evaluator_model",
        "timestamp",
        "file_path",
    ]

    file_rows: List[List[str]] = []
    file_header = [
        "run_dir",
        "condition",
        "generator_model",
        "evaluator_tag",
        "evaluator_model",
        "timestamp",
        "n_rows",
        "file_path",
    ]
    for dim in DIMENSIONS:
        file_header.append(f"{dim}_mean")
    file_header.append("overall_mean")
    for dim in DIMENSIONS:
        file_header.append(f"{dim}_std")
    file_header.append("overall_std")
    file_header.append("missing_metrics")

    grouped_values: DefaultDict[Tuple[str, str, str], Dict[str, List[float]]] = defaultdict(
        lambda: {**{dim: [] for dim in DIMENSIONS}, "overall": []}
    )
    grouped_files: DefaultDict[Tuple[str, str, str], int] = defaultdict(int)

    skipped_partial = 0
    for item in selected:
        run_dir = item.run_dir
        condition = detect_condition(run_dir)
        generator_model = normalize_model_name(run_dir)

        metric_values, overall_values, missing_metrics, n_rows = load_file_metrics(item.path)
        if not args.allow_partial_metrics and missing_metrics:
            skipped_partial += 1
            print(
                "[WARN] Skipping partial-metric file "
                f"(missing={missing_metrics}): {item.path}"
            )
            continue
        if n_rows == 0:
            print(f"[WARN] Skipping empty score file: {item.path}")
            continue

        selected_rows.append(
            [
                run_dir,
                condition,
                generator_model,
                item.evaluator_tag,
                item.evaluator_model,
                item.timestamp,
                str(item.path),
            ]
        )

        means = {dim: mean(metric_values[dim]) for dim in DIMENSIONS}
        stds = {dim: std(metric_values[dim]) for dim in DIMENSIONS}
        row: List[str] = [
            run_dir,
            condition,
            generator_model,
            item.evaluator_tag,
            item.evaluator_model,
            item.timestamp,
            str(n_rows),
            str(item.path),
        ]
        row.extend(fmt_num(means[dim]) for dim in DIMENSIONS)
        row.append(fmt_num(mean(overall_values)))
        row.extend(fmt_num(stds[dim]) for dim in DIMENSIONS)
        row.append(fmt_num(std(overall_values)))
        row.append(",".join(missing_metrics))
        file_rows.append(row)

        group_key = (item.evaluator_model, generator_model, condition)
        grouped_files[group_key] += 1
        for dim in DIMENSIONS:
            grouped_values[group_key][dim].extend(metric_values[dim])
        grouped_values[group_key]["overall"].extend(overall_values)

    if not file_rows:
        raise SystemExit("[ERR] No valid files left after filtering.")

    grouped_header = [
        "evaluator_model",
        "generator_model",
        "condition",
        "n_files",
        "n_rows",
    ]
    for dim in DIMENSIONS:
        grouped_header.append(f"{dim}_mean")
    grouped_header.append("overall_mean")
    for dim in DIMENSIONS:
        grouped_header.append(f"{dim}_std")
    grouped_header.append("overall_std")

    grouped_rows: List[List[str]] = []
    grouped_mean_map: Dict[Tuple[str, str, str], Dict[str, float]] = {}
    for key in sorted(
        grouped_values.keys(),
        key=lambda x: (x[0], x[1], condition_sort_key(x[2])),
    ):
        evaluator_model, generator_model, condition = key
        vals = grouped_values[key]
        n_rows = len(vals["overall"])
        means = {dim: mean(vals[dim]) for dim in DIMENSIONS}
        stds = {dim: std(vals[dim]) for dim in DIMENSIONS}
        overall_mean = mean(vals["overall"])
        overall_std = std(vals["overall"])

        grouped_mean_map[key] = {**means, "overall": overall_mean}

        row = [
            evaluator_model,
            generator_model,
            condition,
            str(grouped_files[key]),
            str(n_rows),
        ]
        row.extend(fmt_num(means[dim]) for dim in DIMENSIONS)
        row.append(fmt_num(overall_mean))
        row.extend(fmt_num(stds[dim]) for dim in DIMENSIONS)
        row.append(fmt_num(overall_std))
        grouped_rows.append(row)

    gain_header = [
        "evaluator_model",
        "generator_model",
        "condition",
        "overall_mean",
        "llm_overall_mean",
        "delta_overall_vs_llm",
    ]
    for dim in DIMENSIONS:
        gain_header.append(f"delta_{dim}_vs_llm")

    gain_rows: List[List[str]] = []
    pairs = sorted(
        {(k[0], k[1]) for k in grouped_mean_map},
        key=lambda x: (x[0], x[1]),
    )
    for evaluator_model, generator_model in pairs:
        llm_key = (evaluator_model, generator_model, "LLM")
        if llm_key not in grouped_mean_map:
            continue
        llm_scores = grouped_mean_map[llm_key]
        for condition in CONDITION_ORDER:
            key = (evaluator_model, generator_model, condition)
            if key not in grouped_mean_map or condition == "LLM":
                continue
            scores = grouped_mean_map[key]
            deltas = {
                dim: scores[dim] - llm_scores[dim]
                for dim in DIMENSIONS
            }
            gain_row = [
                evaluator_model,
                generator_model,
                condition,
                fmt_num(scores["overall"]),
                fmt_num(llm_scores["overall"]),
                fmt_num(scores["overall"] - llm_scores["overall"]),
            ]
            gain_row.extend(fmt_num(deltas[dim]) for dim in DIMENSIONS)
            gain_rows.append(gain_row)

    output_dir = args.output_dir
    write_csv(output_dir / "selected_score_files.csv", selected_header, selected_rows)
    write_csv(output_dir / "plan_quality_file_level.csv", file_header, file_rows)
    write_csv(output_dir / "plan_quality_grouped.csv", grouped_header, grouped_rows)
    write_csv(output_dir / "plan_quality_gain_vs_llm.csv", gain_header, gain_rows)

    print(f"[OK] Wrote CSVs to: {output_dir}")
    if skipped_partial:
        print(f"[INFO] Skipped partial-metric files: {skipped_partial}")


if __name__ == "__main__":
    main()
