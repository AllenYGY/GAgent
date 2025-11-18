#!/usr/bin/env python3
"""Visualize how many turns it takes to recover to 'aligned' after a misalignment."""

from __future__ import annotations

import argparse
import json
import math
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
            for offset, (_, next_alignment) in enumerate(alignments[idx + 1 :], start=1):
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


def _plot_svg(counter: Counter[int], *, output_path: Path) -> None:
    total = sum(counter.values())
    if total == 0:
        return
    width, height = 500, 500
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text { font-family: Arial, sans-serif; }</style>',
        '<text x="250" y="30" text-anchor="middle" font-size="20">Recovery delays</text>',
    ]
    cx, cy, r = width / 2, height / 2 + 10, 160
    start_angle = 0.0
    for delay, count in sorted(counter.items()):
        proportion = count / total
        sweep = proportion * 360.0
        end_angle = start_angle + sweep
        large_arc = 1 if sweep > 180 else 0
        x1 = cx + r * math.cos(math.radians(start_angle))
        y1 = cy + r * math.sin(math.radians(start_angle))
        x2 = cx + r * math.cos(math.radians(end_angle))
        y2 = cy + r * math.sin(math.radians(end_angle))
        path = "M{:.2f},{:.2f} L{:.2f},{:.2f} A{r},{r} 0 {la} 1 {x2:.2f},{y2:.2f} Z".format(
            cx,
            cy,
            x1,
            y1,
            la=large_arc,
            x2=x2,
            y2=y2,
            r=r,
        )
        lines.append(
            f'<path d="{path}" fill="#10b981" fill-opacity="{0.5 + 0.5 * proportion}" stroke="#ffffff" stroke-width="1" />'
        )
        mid_angle = start_angle + sweep / 2
        lx = cx + (r + 20) * math.cos(math.radians(mid_angle))
        ly = cy + (r + 20) * math.sin(math.radians(mid_angle))
        lines.append(
            f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" font-size="12">{delay} ({count})</text>'
        )
        start_angle = end_angle
    lines.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _plot(counter: Counter[int], *, output: Path) -> Path:
    if not counter:
        raise ValueError("No delays to plot")
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError:
        svg_path = output.with_suffix(".svg")
        _plot_svg(counter, output_path=svg_path)
        return svg_path
    labels = list(counter.keys())
    sizes = [counter[k] for k in labels]
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=[f"{label}" for label in labels], autopct="%1.1f%%")
    plt.title("Turns to recover after misalignment")
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output)
    plt.close()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot recovery time after misalignment.")
    parser.add_argument("--run-dir", default="experiments/run_logs", help="Directory with run JSON logs.")
    parser.add_argument("--output", default="experiments/misalignment_recovery.png", help="Output image path.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        parser.error(f"Run directory not found: {run_dir}")

    counter, delays, unresolved = _collect_delays(run_dir)
    if not delays and unresolved == 0:
        print("[WARN] No recoveries detected (either no misalignments or never realigned).")
        return

    saved = _plot(counter, output=Path(args.output))
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
