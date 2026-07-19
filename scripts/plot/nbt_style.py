from __future__ import annotations

from itertools import cycle, islice
from typing import List

PALETTE = {
    "ink": "#1f2933",
    "muted": "#6b7280",
    "grid": "#d8dee4",
    "aligned": "#f3f4f6",
    "misaligned": "#c95c54",
    "rate": "#2f5d9b",
    "hist": "#3d8c7a",
    "accent": "#b08968",
    "background": "#ffffff",
}

COLOR_CYCLE = [
    "#2f5d9b",
    "#3d8c7a",
    "#c95c54",
    "#b08968",
    "#6b7280",
]


def set_nature_style() -> None:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "axes.titlepad": 6,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.linewidth": 0.6,
            "axes.edgecolor": PALETTE["ink"],
            "axes.labelcolor": PALETTE["ink"],
            "text.color": PALETTE["ink"],
            "xtick.color": PALETTE["muted"],
            "ytick.color": PALETTE["muted"],
            "figure.facecolor": PALETTE["background"],
            "axes.facecolor": PALETTE["background"],
            "savefig.facecolor": PALETTE["background"],
            "legend.frameon": False,
            "legend.fontsize": 7,
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.5,
            "grid.alpha": 0.7,
            "figure.dpi": 300,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def soften_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(PALETTE["muted"])
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(axis="both", length=3, width=0.6, color=PALETTE["muted"])


def add_panel_label(ax, label: str, *, x: float = -0.08, y: float = 1.02) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        fontweight="bold",
        color=PALETTE["ink"],
    )


def series_colors(count: int) -> List[str]:
    return list(islice(cycle(COLOR_CYCLE), max(1, count)))
