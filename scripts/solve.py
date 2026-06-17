"""Solve the push/fold equilibrium for one or more table sizes and cache results."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pushfold.config import GameConfig          # noqa: E402
from pushfold.equity import load_or_build_hu_matrix  # noqa: E402
from pushfold.results import compute_results    # noqa: E402
from pushfold.solver import solve               # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=str, default="4",
                    help="comma list or range, e.g. '4' or '2-6'")
    ap.add_argument("--stack", type=float, default=8.0)
    ap.add_argument("--sb", type=float, default=0.4)
    ap.add_argument("--bb", type=float, default=1.0)
    ap.add_argument("--iters", type=int, default=120, help="fictitious-play iterations")
    ap.add_argument("--samples", type=int, default=30000, help="MC deals per EV eval")
    ap.add_argument("--final-samples", type=int, default=300000)
    ap.add_argument("--matrix-iters", type=int, default=10000)
    args = ap.parse_args()

    if "-" in args.players:
        a, b = args.players.split("-")
        ns = list(range(int(a), int(b) + 1))
    else:
        ns = [int(x) for x in args.players.split(",")]

    M = load_or_build_hu_matrix(iters=args.matrix_iters)

    for n in ns:
        cfg = GameConfig(n_players=n, stack=args.stack, sb=args.sb, bb=args.bb)
        print(f"\n=== solving {cfg.describe()} ===")
        t = time.time()
        sigma = solve(cfg, M, iters=args.iters, samples=args.samples)
        res = compute_results(cfg, M, sigma, samples=args.final_samples)
        res.save()
        print(f"  solved & saved in {time.time() - t:.1f}s  -> data/results/{cfg.key()}.npz")
        # quick range summary
        for p in range(n - 1):
            print(f"    {cfg.positions[p]:>4} open-jam range: "
                  f"{res.range_pct(res.jam_freq[p]):5.1f}%")


if __name__ == "__main__":
    main()
