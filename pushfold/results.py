"""Turn a solved equilibrium into EV tables, decisions, and a saveable bundle."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from .cards import COMBO_WEIGHTS, HAND_CLASSES
from .config import GameConfig
from .solver import Evaluator, Strategy

_W = np.asarray(COMBO_WEIGHTS, dtype=np.float64)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")


@dataclass
class Results:
    cfg: GameConfig
    jam_ev: Dict[int, np.ndarray]        # seat -> (169,) EV of open-jamming
    jam_freq: Dict[int, np.ndarray]      # seat -> (169,) equilibrium jam prob
    call_ev: Dict[Tuple[int, int], np.ndarray]   # (seat, jammer) -> (169,)
    call_freq: Dict[Tuple[int, int], np.ndarray]

    # ----- derived convenience -------------------------------------------
    def jam_fold_ev(self, seat: int) -> float:
        return -self.cfg.posted(seat)

    def jam_decision(self, seat: int) -> np.ndarray:
        return self.jam_ev[seat] > self.jam_fold_ev(seat)

    def call_decision(self, seat: int, jammer: int) -> np.ndarray:
        return self.call_ev[(seat, jammer)] > -self.cfg.posted(seat)

    def range_pct(self, freqlike: np.ndarray) -> float:
        return 100.0 * float((freqlike * _W).sum() / _W.sum())

    # ----- persistence ----------------------------------------------------
    def save(self):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        key = self.cfg.key()
        arrays = {}
        for seat, v in self.jam_ev.items():
            arrays[f"jamev_{seat}"] = v
            arrays[f"jamfreq_{seat}"] = self.jam_freq[seat]
        for (seat, J), v in self.call_ev.items():
            arrays[f"callev_{seat}_{J}"] = v
            arrays[f"callfreq_{seat}_{J}"] = self.call_freq[(seat, J)]
        np.savez_compressed(os.path.join(RESULTS_DIR, key + ".npz"), **arrays)
        meta = {"n_players": self.cfg.n_players, "stack": self.cfg.stack,
                "sb": self.cfg.sb, "bb": self.cfg.bb,
                "positions": self.cfg.positions}
        with open(os.path.join(RESULTS_DIR, key + ".json"), "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, cfg: GameConfig) -> "Results":
        key = cfg.key()
        data = np.load(os.path.join(RESULTS_DIR, key + ".npz"))
        jam_ev, jam_freq, call_ev, call_freq = {}, {}, {}, {}
        for name in data.files:
            parts = name.split("_")
            if parts[0] == "jamev":
                jam_ev[int(parts[1])] = data[name]
            elif parts[0] == "jamfreq":
                jam_freq[int(parts[1])] = data[name]
            elif parts[0] == "callev":
                call_ev[(int(parts[1]), int(parts[2]))] = data[name]
            elif parts[0] == "callfreq":
                call_freq[(int(parts[1]), int(parts[2]))] = data[name]
        return cls(cfg, jam_ev, jam_freq, call_ev, call_freq)

    @classmethod
    def exists(cls, cfg: GameConfig) -> bool:
        return os.path.exists(os.path.join(RESULTS_DIR, cfg.key() + ".npz"))


def compute_results(cfg: GameConfig, M: np.ndarray, sigma: Strategy,
                    samples: int = 200000, seed: int = 99) -> Results:
    """High-sample EV evaluation of the final equilibrium strategy."""
    rng = np.random.default_rng(seed)
    ev = Evaluator(cfg, M, rng, samples=samples)
    n = cfg.n_players

    jam_ev = {p: ev.jam_ev(p, sigma) for p in range(n - 1)}
    jam_freq = {p: sigma.jam[p].copy() for p in range(n - 1)}
    call_ev, call_freq = {}, {}
    for q in range(1, n):
        for J in range(q):
            call_ev[(q, J)] = ev.call_ev(q, J, sigma)
            call_freq[(q, J)] = sigma.call[q][J].copy()
    return Results(cfg, jam_ev, jam_freq, call_ev, call_freq)
