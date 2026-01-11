#!/usr/bin/env python3
"""
Plot the distribution of misaligned turns across simulation runs.
Optimized for publication-quality figures suitable for top-tier scientific journals.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Tuple

# Ensure matplotlib is available for professional plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    from cycler import cycler
except ModuleNotFoundError:
    print(
        "[ERROR] matplotlib is required for generating publication-quality plots.\n"
        "Please install it via: pip install matplotlib"
    )
    sys.exit(1)


def set_publication_style():
    """
    Sets global matplotlib rcParams for a professional, publication-ready aesthetic.
    Focuses on serif fonts, clean layouts, and high readability.
    """
    plt.rcParams.update({
        # Use serif fonts to match typical journal body text (e.g., Times New Roman)
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif", "serif"],
        "font.size": 10,
        # Increase readability for labels and titles
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        # Heavier axes lines for definition
        "axes.linewidth": 0.8,
        # Cleaner legend
        "legend.frameon": False,
        "legend.fontsize": 9,
        # Professional color palette (muted slate blue instead of harsh default blue)
        "axes.prop_cycle": cycler(color=["#4E79A7", "#F28E2B", "#E15759", "#76B7B2"]),
        # High DPI for raster output by default
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
    })


def collect_misalignment_turns(
    run_dir: Path,
) -> Tuple[Counter[int], Counter[int], int, int, int, Dict[str, set]]:
    """Collects misalignment data from individual JSON run logs."""
    overall: Counter[int] = Counter()
    first_hits: Counter[int] = Counter()
    max_turn_seen = 0
    total_runs = 0
    runs_with_issue = 0
    run_turns: Dict[str, set] = {}
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
        run_key = (
            payload.get("run_id")
            or config.get("session_id")
            or config.get("plan_id")
            or path.stem
        )
        run_turns.setdefault(str(run_key), set())
        if issues:
            runs_with_issue += 1
        first_seen = False
        for issue in issues:
            turn_index = issue.get("turn_index")
            if not isinstance(turn_index, int):
                continue
            run_turns[str(run_key)].add(turn_index)
            overall[turn_index] += 1
            if not first_seen:
                first_hits[turn_index] += 1
                first_seen = True
            max_turn_seen = max(max_turn_seen, turn_index)
    return overall, first_hits, max_turn_seen, total_runs, runs_with_issue, run_turns


def collect_from_results_csv(
    csv_path: Path,
) -> Tuple[Counter[int], Counter[int], int, int, int, Dict[str, set]]:
    """Collects misalignment counts from an aggregated results.csv file."""
    overall: Counter[int] = Counter()
    first_hits: Counter[int] = Counter()
    max_turn_seen = 0
    runs_with_issue = 0
    runs_seen = set()
    first_seen_by_run = {}
    run_turns: Dict[str, set] = {}

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
            run_turns.setdefault(str(run), set())
            max_turn_seen = max(max_turn_seen, turn)
            if alignment == "misaligned":
                run_turns[str(run)].add(turn)
                overall[turn] += 1
                if run not in first_seen_by_run:
                    first_hits[turn] += 1
                    first_seen_by_run[run] = True

    total_runs = len(runs_seen)
    runs_with_issue = len(first_seen_by_run)
    return overall, first_hits, max_turn_seen, total_runs, runs_with_issue, run_turns


def plot_distribution(
    counter: Counter[int],
    *,
    output_path: Path,
    total_runs: int,
    max_turns: int,
    title_suffix: str = "",
) -> Path:
    """
    Generates a publication-quality bar chart of misalignment distribution using matplotlib.
    """
    # Ensure style settings are applied
    set_publication_style()

    turns: Iterable[int] = range(1, max_turns + 1)
    counts = [counter.get(turn, 0) for turn in turns]
    labels = [str(t) for t in turns]
    x_pos = list(range(len(labels)))

    # Use fixed standard figure dimensions (e.g., ~7 inches wide for double-column fit)
    # instead of dynamic sizing, to ensure consistency across publications.
    fig, ax = plt.subplots(figsize=(7.0, 3.5))

    # Plot bars using the defined color cycle (Slate Blue)
    # zorder=3 ensures bars are on top of the grid.
    bars = ax.bar(x_pos, counts, width=0.75, align="center", zorder=3)

    # Add count labels on top of bars if they aren't too crowded
    if len(x_pos) < 30:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(
                    f"{height}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 2),  # 2 points vertical offset
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    # Remove top and right spines for a cleaner, more modern look
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Configure grid
    # Only show horizontal grid lines, make them thin, gray, and placed behind bars (zorder=0).
    ax.yaxis.grid(
        True, linestyle="--", which="major", color="grey", alpha=0.4, zorder=0
    )
    ax.xaxis.grid(False)

    # Axis Labels and Title
    ax.set_xlabel("Turn Index (t)", labelpad=8)
    ax.set_ylabel("Frequency of Misalignment", labelpad=8)

    # Concise title with essential N-numbers
    total_issues = sum(counts)
    issue_type = (
        "First Misalignments"
        if "first" in title_suffix.lower()
        else "Total Misalignments"
    )
    ax.set_title(
        f"Distribution of {issue_type}\n(N={total_runs} Runs, Total Issues={total_issues})",
        pad=15,
    )

    # X-axis Ticks Configuration
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)

    # If too many ticks, prevent overlap by rotating or sparsifying
    if len(labels) > 20:
        plt.xticks(rotation=45, ha="right")
        # Optional: Show only every nth label if extremely crowded
        # n = len(labels) // 20 or 1
        # for i, label in enumerate(ax.xaxis.get_ticklabels()):
        #     if i % n != 0: label.set_visible(False)

    # Ensure integer ticks on Y-axis for counts
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    #  layout adjustments are handled by savefig.bbox = 'tight' in rcParams
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Recommend PDF for vector graphics in publications, fall back to high-DPI PNG
    save_kwargs = {}
    if output_path.suffix.lower() == ".pdf":
        save_kwargs = {"format": "pdf"}

    plt.savefig(output_path, **save_kwargs)
    plt.close(fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot misaligned turn distribution (Publication Quality)."
    )
    parser.add_argument(
        "--run-dir",
        default="experiments/run_logs",
        help="Directory containing simulation run JSON files, or a results.csv path.",
    )
    parser.add_argument(
        "--output",
        default="experiments/misalignment_distribution.pdf",  # Changed default to PDF for quality
        help="Output path (PDF/PNG/SVG). A second file with suffix '_first' is generated for first misalignments. PDF recommended for publications.",
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
    parser.add_argument(
        "--matrix-output",
        type=Path,
        help="Optional CSV to write run x turn misalignment matrix (1=misaligned, 0=else).",
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
        print(f"[INFO] Loading data from CSV: {csv_path}")
        overall, first_hits, max_turn_seen, total_runs, runs_with_issue, run_turns = (
            collect_from_results_csv(csv_path)
        )
    else:
        print(f"[INFO] Loading data from JSON logs in: {run_dir}")
        overall, first_hits, max_turn_seen, total_runs, runs_with_issue, run_turns = (
            collect_misalignment_turns(run_dir)
        )
    if total_runs == 0:
        print("[WARN] No run data found.")
        return
    if not overall:
        print("[WARN] No misaligned turns found in data.")

    max_turns = args.max_turns or max(max_turn_seen, max(overall) if overall else 0)
    if max_turns <= 0:
        max_turns = 1

    # Matrix output logic (unchanged)
    if args.matrix_output:
        out_path = Path(args.matrix_output)
        header = ["run"] + [str(t) for t in range(1, max_turns + 1)]

        def _sort_key(x: str):
            try:
                return int(x)
            except Exception:
                return x

        runs_sorted = sorted(run_turns.keys(), key=_sort_key)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for run_id in runs_sorted:
                turns = run_turns.get(run_id, set())
                row = [run_id] + [
                    1 if t in turns else 0 for t in range(1, max_turns + 1)
                ]
                writer.writerow(row)
        print(f"[INFO] Saved misalignment matrix to {out_path}")

    output_path = Path(args.output)

    # Plotting logic
    if args.first_only:
        if not first_hits:
            print("[WARN] No first misalignment data available to plot.")
            return
        saved = plot_distribution(
            first_hits,
            output_path=output_path,
            total_runs=total_runs,
            max_turns=max_turns,
            title_suffix="(First Only)",
        )
        print(f"[INFO] Saved first-misalignment plot to {saved}")
        return

    if overall:
        saved_overall = plot_distribution(
            overall,
            output_path=output_path,
            total_runs=total_runs,
            max_turns=max_turns,
            title_suffix="(Overall)",
        )
        print(f"[INFO] Saved overall distribution plot to {saved_overall}")

    if first_hits:
        # Generate the '_first' filename while preserving extension
        first_path = output_path.with_name(
            f"{output_path.stem}_first{output_path.suffix}"
        )
        saved_first = plot_distribution(
            first_hits,
            output_path=first_path,
            total_runs=total_runs,
            max_turns=max_turns,
            title_suffix="(First Only)",
        )
        print(f"[INFO] Saved first-misalignment plot to {saved_first}")


if __name__ == "__main__":
    main()
