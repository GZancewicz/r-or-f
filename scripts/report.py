"""Print push/fold range summaries for all solved table sizes (sanity report)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pushfold.cards import COMBO_WEIGHTS                      # noqa: E402
from pushfold.config import GameConfig                        # noqa: E402
from pushfold.results import Results                          # noqa: E402

W = np.asarray(COMBO_WEIGHTS, dtype=float)


def pct(decision):
    return 100.0 * (decision.astype(float) * W).sum() / W.sum()


def main():
    for n in range(2, 7):
        cfg = GameConfig(n_players=n, stack=8.0, sb=0.4, bb=1.0)
        if not Results.exists(cfg):
            continue
        res = Results.load(cfg)
        print(f"\n=== {cfg.describe()} ===")
        print("  OPEN-JAM (folded to you):")
        for p in range(n - 1):
            print(f"    {cfg.positions[p]:>4}: {pct(res.jam_decision(p)):5.1f}%")
        print("  CALL vs a shove (caller <- shover):")
        for q in range(1, n):
            row = []
            for J in range(q):
                row.append(f"{cfg.positions[J]} {pct(res.call_decision(q, J)):4.1f}%")
            print(f"    {cfg.positions[q]:>4}: " + " | ".join(row))


if __name__ == "__main__":
    main()
