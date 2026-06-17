"""Push/fold Nash equilibrium solver for short-stack Texas Hold'em.

Game: N-handed, all-in-or-fold only, constant stacks (winnings withdrawn /
auto buy-in), so chip-EV == money-EV (no ICM). Default config: 8 BB stacks,
BB = 1.0, SB = 0.4.
"""

from .cards import HAND_CLASSES, hand_class_index, combo_count
from .config import GameConfig

__all__ = ["HAND_CLASSES", "hand_class_index", "combo_count", "GameConfig"]
