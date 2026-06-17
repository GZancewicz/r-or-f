"""Game configuration: table size, stack depth, blinds, and position naming."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Non-blind seats named by their offset from the button.
_NAME_BY_OFFSET = {0: "BTN", 1: "CO", 2: "HJ", 3: "LJ", 4: "UTG", 5: "UTG1", 6: "UTG2"}


def positions_for(n_players: int) -> List[str]:
    """Position labels in preflop action order (index 0 acts first)."""
    if n_players < 2:
        raise ValueError("need at least 2 players")
    if n_players == 2:
        # Heads-up: the SB is the button and acts first preflop.
        return ["SB", "BB"]
    nonblind = [_NAME_BY_OFFSET[o] for o in range(n_players - 3, -1, -1)]
    return nonblind + ["SB", "BB"]


@dataclass(frozen=True)
class GameConfig:
    n_players: int = 4
    stack: float = 8.0        # effective stack in big blinds (auto buy-in resets here)
    sb: float = 0.4           # small blind in big blinds
    bb: float = 1.0           # big blind (the normalization unit)

    positions: List[str] = field(default_factory=list, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "positions", positions_for(self.n_players))

    @property
    def sb_index(self) -> int:
        return self.n_players - 2

    @property
    def bb_index(self) -> int:
        return self.n_players - 1

    def posted(self, seat: int) -> float:
        """Chips the seat has already posted before acting (blinds)."""
        if seat == self.sb_index:
            return self.sb
        if seat == self.bb_index:
            return self.bb
        return 0.0

    def key(self) -> str:
        return f"n{self.n_players}_S{self.stack:g}_sb{self.sb:g}_bb{self.bb:g}"

    def describe(self) -> str:
        return (f"{self.n_players}-handed | stack {self.stack:g}bb | "
                f"SB {self.sb:g} / BB {self.bb:g} | positions: "
                f"{', '.join(self.positions)}")
