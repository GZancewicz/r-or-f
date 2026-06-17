"""Starting-hand classes (169) and their combinatorics.

A "hand class" is one of the 169 canonical preflop hands, e.g. "AA", "AKs",
"AKo". We index them 0..168 in a fixed order and provide:
  - the list of concrete 2-card combos for each class (as eval7 Cards),
  - combo counts / weights (pair=6, suited=4, offsuit=12),
  - a 13x13 grid layout (pairs on diagonal, suited upper-right, offsuit
    lower-left) for plotting.
"""
from __future__ import annotations

import itertools
from functools import lru_cache

import eval7

RANKS = "AKQJT98765432"          # high -> low, used for the 13x13 grid order
RANK_VALUE = {r: i for i, r in enumerate(RANKS)}
SUITS = "cdhs"


def _build_classes():
    classes = []
    for i, hi in enumerate(RANKS):
        for j, lo in enumerate(RANKS):
            if i == j:
                classes.append(hi + lo)          # pair, e.g. "AA"
            elif i < j:
                classes.append(hi + lo + "s")     # suited (upper-right)
            else:
                classes.append(lo + hi + "o")     # offsuit (lower-left)
    # de-dup while preserving a canonical ordering
    seen, ordered = set(), []
    for c in classes:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


HAND_CLASSES = _build_classes()                    # 169 entries
assert len(HAND_CLASSES) == 169, len(HAND_CLASSES)
CLASS_INDEX = {c: i for i, c in enumerate(HAND_CLASSES)}


def hand_class_index(label: str) -> int:
    return CLASS_INDEX[normalize_class(label)]


def normalize_class(label: str) -> str:
    """Normalize user input like 'kqs', 'AKo', 'TT' to canonical class label."""
    label = label.strip()
    if len(label) == 2:                            # pair
        a, b = label[0].upper(), label[1].upper()
        return a + b
    r1, r2, suit = label[0].upper(), label[1].upper(), label[2].lower()
    # order high rank first
    if RANK_VALUE[r1] > RANK_VALUE[r2]:
        r1, r2 = r2, r1
    return f"{r1}{r2}{suit}"


def combo_count(label: str) -> int:
    label = normalize_class(label)
    if len(label) == 2:
        return 6
    return 4 if label.endswith("s") else 12


@lru_cache(maxsize=None)
def class_combos(label: str):
    """All concrete combos for a class as tuples of eval7.Card."""
    label = normalize_class(label)
    combos = []
    if len(label) == 2:                            # pair
        r = label[0]
        for s1, s2 in itertools.combinations(SUITS, 2):
            combos.append((eval7.Card(r + s1), eval7.Card(r + s2)))
    elif label.endswith("s"):                      # suited
        r1, r2 = label[0], label[1]
        for s in SUITS:
            combos.append((eval7.Card(r1 + s), eval7.Card(r2 + s)))
    else:                                          # offsuit
        r1, r2 = label[0], label[1]
        for s1 in SUITS:
            for s2 in SUITS:
                if s1 != s2:
                    combos.append((eval7.Card(r1 + s1), eval7.Card(r2 + s2)))
    return tuple(combos)


# Weight of each class in a uniform random deal (combos / 1326), as a vector.
COMBO_WEIGHTS = [combo_count(c) for c in HAND_CLASSES]            # sums to 1326
TOTAL_COMBOS = sum(COMBO_WEIGHTS)                                 # 1326


def grid_position(label: str):
    """Return (row, col) in the 13x13 grid for plotting (row 0 = A at top)."""
    label = normalize_class(label)
    if len(label) == 2:
        i = RANK_VALUE[label[0]]
        return i, i
    r1, r2 = label[0], label[1]
    i, j = RANK_VALUE[r1], RANK_VALUE[r2]
    if label.endswith("s"):
        return min(i, j), max(i, j)        # suited -> upper right
    return max(i, j), min(i, j)            # offsuit -> lower left
