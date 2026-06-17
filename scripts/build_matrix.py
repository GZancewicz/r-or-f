"""Build & cache the 169x169 heads-up preflop equity matrix (one-time)."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pushfold.equity import load_or_build_hu_matrix  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=10000,
                    help="Monte-Carlo iterations per matchup")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    t = time.time()
    M = load_or_build_hu_matrix(iters=args.iters, force=args.force)
    print(f"matrix shape {M.shape} ready in {time.time() - t:.1f}s")


if __name__ == "__main__":
    main()
