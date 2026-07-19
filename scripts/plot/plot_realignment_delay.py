#!/usr/bin/env python3
"""Visualize how many turns it takes to recover to 'aligned' after a misalignment."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import List, Tuple


def _collect_delays(run_dir: Path) -> Tuple[Counter[int], List[int], int]:
    counter: Counter[int] = Counter()
    raw_delays: List[int] = []
    unresolved = 0
    for path in run_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        turns = payload.get("turns") or []
        alignments = [
            (turn.get("index"), (turn.get("judge") or {}).get("alignment"))
            for turn in turns
        ]
        for idx, (_, alignment) in enumerate(alignments):
            if alignment != "misaligned":
                continue
            delay = None
            for offset, (_, next_alignment) in enumerate(
                alignments[idx + 1 :], start=1
            ):
                if next_alignment == "aligned":
                    delay = offset
                    break
                if next_alignment is None:
                    continue
            if delay is not None:
                counter[delay] += 1
                raw_delays.append(delay)
            else:
                unresolved += 1
    return counter, raw_delays, unresolved


def _collect_delays_from_matrix(csv_path: Path) -> Tuple[Counter[int], List[int], int]:
    """
    Given a misalignment matrix (rows=runs, cols=turns, 1=misaligned), compute delays:
    delay = first turn where misaligned (value 1) to the next turn with value 0.
    If no misalignment in a run -> ignore. If never recovered -> unresolved +1.
    """
    counter: Counter[int] = Counter()
    raw_delays: List[int] = []
    unresolved = 0
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        if len(header) < 2:
            return counter, raw_delays, unresolved
        turns = header[1:]
        for row in reader:
            if len(row) < 2:
                continue
            vals = []
            try:
                vals = [int(x) for x in row[1:]]
            except Exception:
                continue
            try:
                first = vals.index(1)
            except ValueError:
                continue  # no misalignment in this run
            # find first 0 after first 1
            recovery = None
            for i in range(first + 1, len(vals)):
                if vals[i] == 0:
                    recovery = i - first
                    break
            if recovery is not None:
                counter[recovery] += 1
                raw_delays.append(recovery)
            else:
                unresolved += 1
    return counter, raw_delays, unresolved


def _plot(
    counter: Counter[int],
    delays: List[int],
    *,
    output: Path,
    unresolved: int,
) -> Path:
    if not counter and unresolved == 0:
        raise ValueError("No delays to plot")
    try:
        import matplotlib.pyplot as plt  # type: ignore
        from matplotlib.ticker import MaxNLocator
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "[ERR] matplotlib is required for publication-quality plots. Install with: pip install matplotlib"
        ) from exc

    from nbt_style import PALETTE, set_nature_style, soften_axes

    set_nature_style()
    labels = sorted(counter.keys())
    counts = [counter[k] for k in labels]

    fig, ax = plt.subplots(figsize=(5.8, 3.2))
    ax.bar(
        labels,
        counts,
        color=PALETTE["hist"],
        edgecolor="white",
        linewidth=0.4,
        zorder=3,
    )
    ax.set_xlabel("Turns to realignment")
    ax.set_ylabel("Runs")
    ax.set_title("Recovery after misalignment")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color=PALETTE["grid"], linestyle="-", zorder=0)

    if delays:
        median_val = statistics.median(delays)
        ax.axvline(median_val, color=PALETTE["accent"], lw=1.0, ls="--")
        ax.text(
            median_val,
            ax.get_ylim()[1] * 0.95,
            f"median {median_val:.1f}",
            ha="center",
            va="top",
            fontsize=7,
            color=PALETTE["accent"],
        )

    if unresolved:
        ax.text(
            0.98,
            0.95,
            f"No recovery: {unresolved}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=7,
            color=PALETTE["muted"],
        )

    soften_axes(ax)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot recovery time after misalignment."
    )
    parser.add_argument("--run-dir", help="Directory with run JSON logs (action mode).")
    parser.add_argument(
        "--matrix",
        help="Misalignment matrix CSV (from plot_misalignment_distribution --matrix-output).",
    )
    parser.add_argument(
        "--output",
        default="experiments/misalignment_recovery.png",
        help="Output image path.",
    )
    args = parser.parse_args()

    counter: Counter[int]
    delays: List[int]
    unresolved: int

    if args.matrix:
        csv_path = Path(args.matrix)
        if not csv_path.exists():
            parser.error(f"Matrix CSV not found: {csv_path}")
        counter, delays, unresolved = _collect_delays_from_matrix(csv_path)
    else:
        run_dir = Path(args.run_dir or "experiments/run_logs")
        if not run_dir.exists():
            parser.error(f"Run directory not found: {run_dir}")
        counter, delays, unresolved = _collect_delays(run_dir)

    if not delays and unresolved == 0:
        print(
            "[WARN] No recoveries detected (either no misalignments or never realigned)."
        )
        return

    saved = _plot(counter, delays, output=Path(args.output), unresolved=unresolved)
    print(f"[INFO] Saved recovery distribution to {saved}")
    data_path = Path(args.output).with_suffix(".json")
    data_path.write_text(
        json.dumps({"delays": delays, "unresolved": unresolved}, indent=2),
        encoding="utf-8",
    )
    for delay in sorted(counter):
        print(f"Delay {delay:>2}: {counter[delay]} occurrences")
    if unresolved:
        print(f"No recovery: {unresolved} occurrences")


if __name__ == "__main__":
    main()
