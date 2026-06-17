"""Export the equity matrix + solved equilibrium ranges into a flat text file
the Rust engine reads (engine/data/model.txt). Pure line-based format so the
engine can parse it with the std library only (no JSON dependency).

Format (one record per line, first token is the tag):
  HANDS   <169 class labels>
  WEIGHTS <169 combo counts>
  EQ <row> <169 equities>            # heredo M[row, :] = equity of class `row` vs each
  TABLE <n>
  POS <comma-separated positions>
  POSTED <n blind amounts, by seat>
  JAM <seat> <169 freqs>
  CALL <q> <J> <169 freqs>
"""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
RESULTS_DIR = os.path.join(ROOT, "data", "results")
OUT = os.path.join(ROOT, "engine", "data", "model.txt")
PLAYER_COUNTS = [2, 3, 4]


def main():
    import json
    from pushfold.cards import HAND_CLASSES, COMBO_WEIGHTS
    from pushfold.config import GameConfig
    from pushfold.equity import load_or_build_hu_matrix
    from pushfold.results import Results

    M = load_or_build_hu_matrix(iters=10000)          # (169,169) hero-vs-opp equity
    assert M.shape == (169, 169)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lines = []
    lines.append("HANDS " + " ".join(HAND_CLASSES))
    lines.append("WEIGHTS " + " ".join(str(w) for w in COMBO_WEIGHTS))
    for i in range(169):
        lines.append(f"EQ {i} " + " ".join(f"{x:.6f}" for x in M[i]))

    for n in PLAYER_COUNTS:
        key = f"n{n}_S8_sb0.4_bb1"
        meta = json.load(open(os.path.join(RESULTS_DIR, key + ".json")))
        cfg = GameConfig(n_players=n, stack=meta["stack"], sb=meta["sb"], bb=meta["bb"])
        res = Results.load(cfg)
        posted = [cfg.posted(p) for p in range(n)]

        lines.append(f"TABLE {n}")
        lines.append("POS " + ",".join(meta["positions"]))
        lines.append("POSTED " + " ".join(f"{x:g}" for x in posted))
        for p in range(n - 1):
            lines.append(f"JAM {p} " + " ".join(f"{x:.5f}" for x in res.jam_freq[p]))
        for q in range(1, n):
            for J in range(q):
                if (q, J) in res.call_freq:
                    lines.append(f"CALL {q} {J} " +
                                 " ".join(f"{x:.5f}" for x in res.call_freq[(q, J)]))

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
