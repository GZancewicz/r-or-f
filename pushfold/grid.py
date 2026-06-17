"""Helpers to lay out a 169-vector onto the standard 13x13 hand grid."""
from __future__ import annotations

import numpy as np

from .cards import HAND_CLASSES, RANKS, grid_position


def to_grid(vec169: np.ndarray) -> np.ndarray:
    """Map a length-169 vector to a 13x13 grid (row 0 = A at top)."""
    g = np.full((13, 13), np.nan)
    for idx, label in enumerate(HAND_CLASSES):
        r, c = grid_position(label)
        g[r, c] = vec169[idx]
    return g


def label_grid() -> np.ndarray:
    g = np.empty((13, 13), dtype=object)
    for label in HAND_CLASSES:
        r, c = grid_position(label)
        g[r, c] = label
    return g


AXIS = list(RANKS)   # ['A','K',...,'2']
