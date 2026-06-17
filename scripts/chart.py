"""Render a tiered open-shove push/fold chart (13x13) for a table size.

Each cell is colored by the EARLIEST position you can profitably open-jam the
hand from (later positions shove everything an earlier position does, plus
more). Saves a PNG to data/charts/.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib                                   # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.patches import Patch                # noqa: E402

from pushfold.cards import HAND_CLASSES, RANKS, grid_position, COMBO_WEIGHTS  # noqa: E402
from pushfold.config import GameConfig              # noqa: E402
from pushfold.results import Results                # noqa: E402

W = np.asarray(COMBO_WEIGHTS, float)


def render(n=4, out=None):
    cfg = GameConfig(n_players=n, stack=8.0, sb=0.4, bb=1.0)
    res = Results.load(cfg)
    openers = cfg.positions[:-1]                    # all but BB
    decs = [res.jam_decision(p) for p in range(len(openers))]

    # tier per hand = earliest opener index that shoves it (len => fold)
    tier = np.full(169, len(openers), dtype=int)
    for p in range(len(openers) - 1, -1, -1):       # later->earlier so earliest wins
        tier[decs[p]] = p

    # colors: earliest opener darkest, fold light grey
    palette = ["#1a7a3a", "#3fa45a", "#8ed08f", "#cdeccd", "#bfe0ff", "#dff0ff"]
    fold_color = "#ececec"
    pct = [100 * (d.astype(float) * W).sum() / W.sum() for d in decs]

    fig, ax = plt.subplots(figsize=(9.2, 9.6))
    for idx, label in enumerate(HAND_CLASSES):
        r, c = grid_position(label)
        t = tier[idx]
        color = fold_color if t == len(openers) else palette[t]
        txtcol = "white" if (t < 2) else "#173"
        if t == len(openers):
            txtcol = "#999"
        ax.add_patch(plt.Rectangle((c, 12 - r), 1, 1, facecolor=color,
                                   edgecolor="white", lw=1.2))
        ax.text(c + 0.5, 12 - r + 0.5, label, ha="center", va="center",
                fontsize=8.5, color=txtcol,
                fontweight="bold" if t < len(openers) else "normal")

    ax.set_xlim(0, 13); ax.set_ylim(0, 13); ax.set_aspect("equal")
    ax.set_xticks(np.arange(13) + 0.5); ax.set_xticklabels(list(RANKS), fontsize=9)
    ax.set_yticks(np.arange(13) + 0.5); ax.set_yticklabels(list(RANKS)[::-1], fontsize=9)
    ax.xaxis.tick_top(); ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)

    legend = [Patch(facecolor=palette[p], label=f"{openers[p]}+   (shove {pct[p]:.0f}%)")
              for p in range(len(openers))]
    legend.append(Patch(facecolor=fold_color, label="fold (all positions)"))
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.04),
              ncol=len(legend), frameon=False, fontsize=9)

    ax.set_title(f"{n}-handed · 8 bb · all-in/fold · open-shove ranges\n"
                 "color = earliest position you can profitably shove from "
                 "(upper-right = suited, lower-left = offsuit)",
                 fontsize=11)
    plt.tight_layout()

    out = out or os.path.join(os.path.dirname(__file__), "..", "data", "charts",
                              f"pushchart_n{n}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved {os.path.abspath(out)}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    render(args.players, args.out)
