#!/usr/bin/env python3
"""Plot the distribution of misaligned turns across simulation runs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Tuple


def collect_misalignment_turns(
    run_dir: Path,
) -> Tuple[Counter[int], Counter[int], int, int, int]:
    overall: Counter[int] = Counter()
    first_hits: Counter[int] = Counter()
    max_turn_seen = 0
    total_runs = 0
    runs_with_issue = 0
    for path in sorted(run_dir.glob("*.json")):
        total_runs += 1
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue
        config = payload.get("config") or {}
        mt = config.get("max_turns")
        if isinstance(mt, int):
            max_turn_seen = max(max_turn_seen, mt)
        issues = payload.get("alignment_issues", []) or []
        if issues:
            runs_with_issue += 1
        first_seen = False
        for issue in issues:
            turn_index = issue.get("turn_index")
            if not isinstance(turn_index, int):
                continue
            overall[turn_index] += 1
            if not first_seen:
                first_hits[turn_index] += 1
                first_seen = True
            max_turn_seen = max(max_turn_seen, turn_index)
    return overall, first_hits, max_turn_seen, total_runs, runs_with_issue


def collect_from_results_csv(
    csv_path: Path,
) -> Tuple[Counter[int], Counter[int], int, int, int]:
    """Collect misalignment counts from a results.csv produced by full_plan mode.

    Expected columns: run, turn, alignment (aligned|misaligned|unclear).
    Counts misaligned entries; unclear is ignored for the histogram.
    """
    overall: Counter[int] = Counter()
    first_hits: Counter[int] = Counter()
    max_turn_seen = 0
    runs_with_issue = 0
    runs_seen = set()
    first_seen_by_run = {}

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                run = int(row.get("run", 0))
                turn = int(float(row.get("turn", 0)))
            except Exception:
                continue
            alignment = (row.get("alignment") or "").strip().lower()
            runs_seen.add(run)
            max_turn_seen = max(max_turn_seen, turn)
            if alignment == "misaligned":
                overall[turn] += 1
                if run not in first_seen_by_run:
                    first_hits[turn] += 1
                    first_seen_by_run[run] = True

    total_runs = len(runs_seen)
    runs_with_issue = len(first_seen_by_run)
    return overall, first_hits, max_turn_seen, total_runs, runs_with_issue


def _plot_svg(
    counter: Counter[int],
    *,
    output_path: Path,
    total_runs: int,
    turns_range: Iterable[int],
    no_issue_runs: int,
) -> None:
    turns = list(turns_range)
    labels = [str(t) for t in turns] + [f">={turns[-1]}"]
    counts = [counter.get(t, 0) for t in turns] + [no_issue_runs]
    max_count = max(counts)
    width, height = 900, 500
    margin = 60
    chart_width = width - 2 * margin
    chart_height = height - 2 * margin
    bar_width = chart_width / max(len(turns), 1)
    scale = chart_height / max_count if max_count else 1

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        "<style>text { font-family: Arial, sans-serif; }</style>",
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-size="20">Misaligned turn distribution (runs={total_runs}, issues={sum(counts)})</text>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#111"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#111"/>',
    ]
    bars = []
    for idx, label in enumerate(labels):
        value = counts[idx]
        x = margin + idx * bar_width
        y = height - margin - value * scale
        bars.append((x, y, label, value))
    for x, y, label, value in bars:
        lines.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width * 0.8:.2f}" height="{value * scale:.2f}" fill="#3b82f6" opacity="0.9" />'
        )
        lines.append(
            f'<text x="{x + (bar_width * 0.4):.2f}" y="{height - margin + 20}" text-anchor="middle" font-size="12">{label}</text>'
        )
        lines.append(
            f'<text x="{x + (bar_width * 0.4):.2f}" y="{y - 6:.2f}" text-anchor="middle" font-size="12">{value}</text>'
        )
    lines.append(
        f'<text x="{width / 2}" y="{height - 10}" text-anchor="middle" font-size="14">Turn index</text>'
    )
    lines.append(
        f'<text transform="rotate(-90 {15} {height / 2})" x="15" y="{height / 2}" text-anchor="middle" font-size="14">Misaligned occurrences</text>'
    )
    lines.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_distribution(
    counter: Counter[int],
    *,
    output_path: Path,
    total_runs: int,
    max_turns: int,
    no_issue_runs: int,
) -> Path:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError:
        svg_path = (
            output_path
            if output_path.suffix.lower() == ".svg"
            else output_path.with_suffix(".svg")
        )
        turns_range = range(1, max_turns + 1)
        _plot_svg(
            counter,
            output_path=svg_path,
            total_runs=total_runs,
            turns_range=turns_range,
            no_issue_runs=no_issue_runs,
        )
        return svg_path

    turns: Iterable[int] = range(1, max_turns + 1)
    counts = [counter.get(turn, 0) for turn in turns] + [no_issue_runs]
    labels = [str(t) for t in turns] + [f">={max_turns}"]
    x = list(range(len(labels)))
    plt.figure(figsize=(max(20, len(labels) * 0.3), 5))
    width = min(
        0.6, 25 / max(1, len(labels))
    )  # auto-adjust bar width to reduce overlap
    plt.bar(x, counts, color="#3b82f6", alpha=0.9, width=width)
    plt.xlabel("Turn index (>=max_turns = runs with zero misalignment)")
    plt.ylabel("Misaligned occurrences")
    plt.title(f"Misaligned turn distribution (runs={total_runs}, issues={sum(counts)})")
    plt.xticks(x, labels)
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot misaligned turn distribution.")
    parser.add_argument(
        "--run-dir",
        default="experiments/run_logs",
        help="Directory containing simulation run JSON files, or a results.csv path.",
    )
    parser.add_argument(
        "--output",
        default="experiments/misalignment_distribution.png",
        help="Output path (PNG/SVG). A second file with suffix '_first' is generated for first misalignments.",
    )
    parser.add_argument(
        "--first-only",
        action="store_true",
        help="Only plot the first misalignment per run.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        help="Optional cap for turn axis; if omitted, uses max_turns from runs or observed turns.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        parser.error(f"Run directory/file not found: {run_dir}")

    # Decide source: CSV (full_plan results) or JSON run logs (action mode)
    use_csv = False
    csv_path = run_dir
    if run_dir.is_dir():
        candidate = run_dir / "results.csv"
        if candidate.exists():
            use_csv = True
            csv_path = candidate
    elif run_dir.suffix.lower() == ".csv":
        use_csv = True

    if use_csv:
        overall, first_hits, max_turn_seen, total_runs, runs_with_issue = (
            collect_from_results_csv(csv_path)
        )
    else:
        overall, first_hits, max_turn_seen, total_runs, runs_with_issue = (
            collect_misalignment_turns(run_dir)
        )
    if total_runs == 0:
        print("[WARN] No run logs found.")
        return
    if not overall:
        print("[WARN] No misaligned turns found in run logs.")
    max_turns = args.max_turns or max(max_turn_seen, max(overall) if overall else 0)
    if max_turns <= 0:
        max_turns = 1
    no_issue_runs = total_runs - runs_with_issue

    output_path = Path(args.output)
    if args.first_only:
        if not first_hits:
            print("[WARN] No first misalignment data available.")
            return
        saved = plot_distribution(
            first_hits,
            output_path=output_path,
            total_runs=total_runs,
            max_turns=max_turns,
            no_issue_runs=no_issue_runs,
        )
        print(f"[INFO] Saved first-misalignment plot to {saved}")
        for turn in sorted(first_hits):
            print(f"Turn {turn:>2}: {first_hits[turn]} first misalignments")
        return

    saved_overall = plot_distribution(
        overall,
        output_path=output_path,
        total_runs=total_runs,
        max_turns=max_turns,
        no_issue_runs=no_issue_runs,
    )
    print(f"[INFO] Saved distribution plot to {saved_overall}")
    for turn in sorted(overall):
        print(f"Turn {turn:>2}: {overall[turn]} misalignments")

    if first_hits:
        first_path = saved_overall.with_name(
            saved_overall.stem + "_first" + saved_overall.suffix
        )
        saved_first = plot_distribution(
            first_hits,
            output_path=first_path,
            total_runs=total_runs,
            max_turns=max_turns,
            no_issue_runs=no_issue_runs,
        )
        print(f"[INFO] Saved first-misalignment plot to {saved_first}")
        for turn in sorted(first_hits):
            print(f"Turn {turn:>2}: {first_hits[turn]} first misalignments")


if __name__ == "__main__":
    main()
