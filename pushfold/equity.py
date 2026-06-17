"""Preflop all-in equity: cached 169x169 heads-up matrix + multiway Monte-Carlo.

The heads-up matrix M[i][j] = class i's equity vs class j averaged over suits,
combos (blockers) and all run-outs. Built once via Monte-Carlo and cached to
disk. Multiway pots (2+ callers) are evaluated live with a small board sample.
"""
from __future__ import annotations

import os
import random
from functools import lru_cache
from typing import List, Sequence, Tuple

import eval7
import numpy as np

from .cards import HAND_CLASSES, RANKS, class_combos

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_RANK_CHAR_TO_GRID = {r: i for i, r in enumerate(RANKS)}

FULL_DECK = [eval7.Card(r + s) for r in "23456789TJQKA" for s in "cdhs"]
Card = eval7.Card
Combo = Tuple[Card, Card]


# ---------------------------------------------------------------------------
# combo <-> class helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _combo_class_label(c1s: str, c2s: str) -> str:
    r1, s1 = c1s[0], c1s[1]
    r2, s2 = c2s[0], c2s[1]
    if _RANK_CHAR_TO_GRID[r1] > _RANK_CHAR_TO_GRID[r2]:
        r1, s1, r2, s2 = r2, s2, r1, s1   # high rank first
    if r1 == r2:
        return r1 + r2
    return f"{r1}{r2}{'s' if s1 == s2 else 'o'}"


# ---------------------------------------------------------------------------
# heads-up matrix
# ---------------------------------------------------------------------------
def hu_equity_pair(i: int, j: int, iters: int, rng: random.Random) -> float:
    """Monte-Carlo equity of class i vs class j (averaged over combos/boards)."""
    if i == j:
        return 0.5
    combos_i = class_combos(HAND_CLASSES[i])
    combos_j = class_combos(HAND_CLASSES[j])
    wins = 0.0
    n = 0
    while n < iters:
        ci = rng.choice(combos_i)
        cj = rng.choice(combos_j)
        if ci[0] == cj[0] or ci[0] == cj[1] or ci[1] == cj[0] or ci[1] == cj[1]:
            continue  # card conflict, resample
        used = {ci[0], ci[1], cj[0], cj[1]}
        board = rng.sample([c for c in FULL_DECK if c not in used], 5)
        hi = eval7.evaluate([ci[0], ci[1], *board])
        hj = eval7.evaluate([cj[0], cj[1], *board])
        if hi > hj:
            wins += 1.0
        elif hi == hj:
            wins += 0.5
        n += 1
    return wins / iters


def _row_block(args):
    """Worker: compute equities for hero classes in `idxs` vs all j>i."""
    idxs, iters, seed = args
    rng = random.Random(seed)
    out = {}
    for i in idxs:
        row = {}
        for j in range(i + 1, 169):
            row[j] = hu_equity_pair(i, j, iters, rng)
        out[i] = row
    return out


def build_hu_matrix(iters: int = 10000, processes: int | None = None) -> np.ndarray:
    """Build the full 169x169 HU equity matrix (parallel)."""
    import multiprocessing as mp

    if processes is None:
        processes = max(1, (os.cpu_count() or 2) - 1)
    all_idx = list(range(169))
    chunks = [all_idx[k::processes] for k in range(processes)]
    args = [(chunk, iters, 1234 + k) for k, chunk in enumerate(chunks)]

    M = np.full((169, 169), 0.5, dtype=np.float64)
    with mp.Pool(processes) as pool:
        for part in pool.imap_unordered(_row_block, args):
            for i, row in part.items():
                for j, eq in row.items():
                    M[i, j] = eq
                    M[j, i] = 1.0 - eq
    return M


def load_or_build_hu_matrix(iters: int = 10000, force: bool = False,
                            verbose: bool = True) -> np.ndarray:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"hu_equity_{iters}.npy")
    if os.path.exists(path) and not force:
        return np.load(path)
    if verbose:
        print(f"Building HU equity matrix ({iters} iters/pair)... one-time.")
    M = build_hu_matrix(iters)
    np.save(path, M)
    return M


# ---------------------------------------------------------------------------
# multiway equity (live, used only when 2+ players call)
# ---------------------------------------------------------------------------
def multiway_equity(hero: Combo, opps: Sequence[Combo], board_iters: int,
                    rng: random.Random) -> float:
    """Hero's pot share vs >=1 specific opponent hands, over random run-outs."""
    used = {hero[0], hero[1]}
    for o in opps:
        used.add(o[0]); used.add(o[1])
    deck = [c for c in FULL_DECK if c not in used]
    share = 0.0
    for _ in range(board_iters):
        board = rng.sample(deck, 5)
        hs = eval7.evaluate([hero[0], hero[1], *board])
        best = hs
        ties = 1
        beaten = False
        for o in opps:
            os_ = eval7.evaluate([o[0], o[1], *board])
            if os_ > hs:
                beaten = True
                break
            if os_ == hs:
                ties += 1
        if not beaten:
            share += 1.0 / ties
    return share / board_iters


def combo_class_index(c1: Card, c2: Card) -> int:
    from .cards import CLASS_INDEX
    return CLASS_INDEX[_combo_class_label(str(c1), str(c2))]
