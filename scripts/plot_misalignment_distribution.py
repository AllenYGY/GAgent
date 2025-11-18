#!/usr/bin/env python3
"""Plot the distribution of misaligned turns across simulation runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Tuple


def collect_misalignment_turns(run_dir: Path) -> Tuple[Counter[int], Counter[int]]:
    overall: Counter[int] = Counter()
    first_hits: Counter[int] = Counter()
    for path in sorted(run_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue
        issues = payload.get("alignment_issues", []) or []
        first_seen = False
        for issue in issues:
            turn_index = issue.get("turn_index")
            if not isinstance(turn_index, int):
                continue
            overall[turn_index] += 1
            if not first_seen:
                first_hits[turn_index] += 1
                first_seen = True
    return overall, first_hits


def _plot_svg(counter: Counter[int], *, output_path: Path, total_runs: int) -> None:
    turns = sorted(counter)
    counts = [counter[t] for t in turns]
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
        '<style>text { font-family: Arial, sans-serif; }</style>',
        f'<text x="{width/2}" y="30" text-anchor="middle" font-size="20">Misaligned turn distribution (runs={total_runs}, issues={sum(counts)})</text>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#111"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#111"/>',
    ]
    points = []
    for idx, turn in enumerate(turns):
        value = counts[idx]
        x = margin + idx * bar_width + bar_width / 2
        y = height - margin - value * scale
        points.append((x, y, turn, value))
    for (x1, y1, _, _), (x2, y2, _, _) in zip(points, points[1:]):
        lines.append(f'<path d="M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}" stroke="#3b82f6" stroke-width="2" fill="none" />')
    for x, y, turn, value in points:
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#3b82f6" />')
        lines.append(f'<text x="{x:.2f}" y="{height - margin + 20}" text-anchor="middle" font-size="12">{turn}</text>')
        lines.append(f'<text x="{x:.2f}" y="{y - 6:.2f}" text-anchor="middle" font-size="12">{value}</text>')
    lines.append(
        f'<text x="{width/2}" y="{height - 10}" text-anchor="middle" font-size="14">Turn index</text>'
    )
    lines.append(
        f'<text transform="rotate(-90 {15} {height/2})" x="15" y="{height/2}" text-anchor="middle" font-size="14">Misaligned occurrences</text>'
    )
    lines.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_distribution(counter: Counter[int], *, output_path: Path, total_runs: int) -> Path:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError:
        svg_path = output_path if output_path.suffix.lower() == ".svg" else output_path.with_suffix(".svg")
        _plot_svg(counter, output_path=svg_path, total_runs=total_runs)
        return svg_path

    turns: Iterable[int] = sorted(counter)
    counts = [counter[turn] for turn in turns]
    plt.figure(figsize=(10, 5))
    plt.plot(list(turns), counts, color="#3b82f6", marker="o")
    plt.fill_between(list(turns), counts, color="#3b82f6", alpha=0.15)
    plt.xlabel("Turn index")
    plt.ylabel("Misaligned occurrences")
    plt.title(f"Misaligned turn distribution (runs={total_runs}, issues={sum(counts)})")
    plt.xticks(sorted(counter))
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot misaligned turn distribution.")
    parser.add_argument("--run-dir", default="experiments/run_logs", help="Directory containing simulation run JSON files.")
    parser.add_argument("--output", default="experiments/misalignment_distribution.png", help="Output path (PNG/SVG). A second file with suffix '_first' is generated for first misalignments.")
    parser.add_argument("--first-only", action="store_true", help="Only plot the first misalignment per run.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        parser.error(f"Run directory not found: {run_dir}")

    overall, first_hits = collect_misalignment_turns(run_dir)
    total_runs = len(list(run_dir.glob("*.json")))
    if not overall:
        print("[WARN] No misaligned turns found in run logs.")
        return

    output_path = Path(args.output)
    if args.first_only:
        if not first_hits:
            print("[WARN] No first misalignment data available.")
            return
        saved = plot_distribution(first_hits, output_path=output_path, total_runs=total_runs)
        print(f"[INFO] Saved first-misalignment plot to {saved}")
        for turn in sorted(first_hits):
            print(f"Turn {turn:>2}: {first_hits[turn]} first misalignments")
        return

    saved_overall = plot_distribution(overall, output_path=output_path, total_runs=total_runs)
    print(f"[INFO] Saved distribution plot to {saved_overall}")
    for turn in sorted(overall):
        print(f"Turn {turn:>2}: {overall[turn]} misalignments")

    if first_hits:
        first_path = saved_overall.with_name(saved_overall.stem + "_first" + saved_overall.suffix)
        saved_first = plot_distribution(first_hits, output_path=first_path, total_runs=total_runs)
        print(f"[INFO] Saved first-misalignment plot to {saved_first}")
        for turn in sorted(first_hits):
            print(f"Turn {turn:>2}: {first_hits[turn]} first misalignments")


if __name__ == "__main__":
    main()
