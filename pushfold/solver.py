"""Nash push/fold equilibrium via fictitious play (iterated best response).

Model & assumptions (documented honestly):
  * All-in-or-fold only; equal stacks => after the first jam, everyone else can
    only call or fold (no re-raising). Every player acts at most once.
  * Constant stacks each hand (winnings withdrawn / auto buy-in) => chip-EV ==
    money-EV, no ICM. EV is net BB won/lost per hand.
  * Strategies:
      - jam[p][hand]            : P(open-jam | folded to seat p)   (first-in)
      - call[q][J][hand]        : P(call | facing a jam from seat J)
    Calling ranges are conditioned on the JAMMER'S POSITION only (not on how
    many others already called). This is the standard "calling range vs a shove
    from seat X" model and makes every player's action independent, which lets
    us evaluate EVs by vectorized Monte-Carlo over the deal.
  * Equity: heads-up pots use the exact precomputed MC matrix. Multiway pots
    (2+ callers) use an independent-equity approximation (product of pairwise
    win probs) -- these pots are a small minority at these stack depths.
  * Card-removal between players is modelled in the heads-up equity matrix
    (blocker-averaged) but ignored when sampling opponents' classes in the
    forward simulation (class-level approximation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .cards import COMBO_WEIGHTS, HAND_CLASSES
from .config import GameConfig

NCLASS = 169
_W = np.asarray(COMBO_WEIGHTS, dtype=np.float64)
_PRIOR = _W / _W.sum()                 # P(a uniform random hand is class c)


# ---------------------------------------------------------------------------
# strategy container
# ---------------------------------------------------------------------------
@dataclass
class Strategy:
    cfg: GameConfig
    jam: Dict[int, np.ndarray] = field(default_factory=dict)
    call: Dict[int, Dict[int, np.ndarray]] = field(default_factory=dict)

    @classmethod
    def zeros(cls, cfg: GameConfig) -> "Strategy":
        n = cfg.n_players
        jam = {p: np.zeros(NCLASS) for p in range(n - 1)}      # 0..n-2 can open
        call = {q: {J: np.zeros(NCLASS) for J in range(q)} for q in range(1, n)}
        return cls(cfg, jam, call)

    def copy(self) -> "Strategy":
        return Strategy(self.cfg,
                        {p: v.copy() for p, v in self.jam.items()},
                        {q: {J: a.copy() for J, a in d.items()}
                         for q, d in self.call.items()})


def _cumdist(prob_weighted: np.ndarray):
    """Return (callfreq, cumulative-conditional-dist) for a weighted prob vec."""
    mass = _W * prob_weighted                 # combo-weighted reach of each class
    total = mass.sum()
    freq = total / _W.sum()                   # P(hand is in this range)
    if total <= 0:
        return 0.0, None
    return float(freq), np.cumsum(mass / total)


def _sample(cum, u):
    return np.searchsorted(cum, u, side="right").clip(max=NCLASS - 1)


# ---------------------------------------------------------------------------
# EV evaluation (vectorized Monte-Carlo over the deal)
# ---------------------------------------------------------------------------
class Evaluator:
    def __init__(self, cfg: GameConfig, M: np.ndarray, rng: np.random.Generator,
                 samples: int = 30000):
        self.cfg = cfg
        self.M = M
        self.rng = rng
        self.S = samples
        self.stack = cfg.stack

    # ---- jam EV: seat p is first-in and open-jams; integrate downstream -----
    def jam_ev(self, p: int, sigma: Strategy) -> np.ndarray:
        cfg, S, M, stack = self.cfg, self.S, self.M, self.stack
        later = list(range(p + 1, cfg.n_players))

        call_mask = np.zeros((len(later), S), dtype=bool)
        call_cls = np.zeros((len(later), S), dtype=np.int64)
        for r, q in enumerate(later):
            freq, cum = _cumdist(sigma.call[q][p])
            if cum is None:
                continue
            u = self.rng.random(S)
            called = u < freq
            call_mask[r] = called
            call_cls[r] = _sample(cum, self.rng.random(S))

        return self._aggregate(call_mask, call_cls, later, hero_in=p,
                               always_in_class=None)

    # ---- call EV: seat q faces a jam from seat J ----------------------------
    def call_ev(self, q: int, J: int, sigma: Strategy) -> np.ndarray:
        cfg, S = self.cfg, self.S
        # other live players besides hero q: jammer J (always in) + any seat
        # between J and q that cold-calls + any seat behind q that overcalls.
        other_seats = [s for s in range(J + 1, cfg.n_players) if s != q]
        call_mask = np.zeros((len(other_seats), S), dtype=bool)
        call_cls = np.zeros((len(other_seats), S), dtype=np.int64)
        for r, s in enumerate(other_seats):
            freq, cum = _cumdist(sigma.call[s][J])
            if cum is None:
                continue
            call_mask[r] = self.rng.random(S) < freq
            call_cls[r] = _sample(cum, self.rng.random(S))

        # jammer's revealed class
        jfreq, jcum = _cumdist(sigma.jam[J])
        if jcum is None:
            return np.full(NCLASS, -self.cfg.posted(q))   # jammer never jams
        jammer_cls = _sample(jcum, self.rng.random(S))

        return self._aggregate(call_mask, call_cls, other_seats, hero_in=q,
                               always_in_class=(J, jammer_cls))

    # ---- per-sample outcomes (NCLASS, S) for an open jam by seat p ----------
    def jam_outcomes(self, p: int, sigma: "Strategy") -> np.ndarray:
        cfg, S = self.cfg, self.S
        later = list(range(p + 1, cfg.n_players))
        call_mask = np.zeros((len(later), S), dtype=bool)
        call_cls = np.zeros((len(later), S), dtype=np.int64)
        for r, q in enumerate(later):
            freq, cum = _cumdist(sigma.call[q][p])
            if cum is None:
                continue
            call_mask[r] = self.rng.random(S) < freq
            call_cls[r] = _sample(cum, self.rng.random(S))
        return self._aggregate(call_mask, call_cls, later, hero_in=p,
                               always_in_class=None, per_sample=True)

    # ---- per-sample outcomes (NCLASS, S) for calling a jam from seat J ------
    def call_outcomes(self, q: int, J: int, sigma: "Strategy") -> np.ndarray:
        cfg, S = self.cfg, self.S
        other_seats = [s for s in range(J + 1, cfg.n_players) if s != q]
        call_mask = np.zeros((len(other_seats), S), dtype=bool)
        call_cls = np.zeros((len(other_seats), S), dtype=np.int64)
        for r, s in enumerate(other_seats):
            freq, cum = _cumdist(sigma.call[s][J])
            if cum is None:
                continue
            call_mask[r] = self.rng.random(S) < freq
            call_cls[r] = _sample(cum, self.rng.random(S))
        jfreq, jcum = _cumdist(sigma.jam[J])
        if jcum is None:
            return np.full((NCLASS, S), -self.cfg.posted(q))
        jammer_cls = _sample(jcum, self.rng.random(S))
        return self._aggregate(call_mask, call_cls, other_seats, hero_in=q,
                               always_in_class=(J, jammer_cls), per_sample=True)

    # ---- shared aggregation -------------------------------------------------
    def _aggregate(self, call_mask, call_cls, opp_seats, hero_in,
                   always_in_class, per_sample=False):
        cfg, S, M, stack = self.cfg, self.S, self.M, self.stack
        n_opp = call_mask.shape[0] if call_mask.size else 0

        # who is all-in (besides hero) per scenario
        in_mask = call_mask.copy() if n_opp else np.zeros((0, S), bool)
        n_others = in_mask.sum(0) if n_opp else np.zeros(S, dtype=int)

        # jammer (for call_ev) is always in
        jammer_seat = None
        if always_in_class is not None:
            jammer_seat, jammer_cls = always_in_class
            n_others = n_others + 1

        # ---- pot per scenario: 8 each for all-in players + forfeited blinds --
        n_allin = n_others + 1                       # + hero
        pot = stack * n_allin.astype(np.float64)
        for b, amt in ((cfg.sb_index, cfg.sb), (cfg.bb_index, cfg.bb)):
            if b == hero_in or b == jammer_seat:
                continue                              # blind is all-in (hero/jammer)
            if b in opp_seats:
                r = opp_seats.index(b)
                pot += amt * (~in_mask[r])            # forfeited if that seat folded
            elif always_in_class is not None and b > 0:
                # in call_ev, seats before jammer J folded -> forfeit their blind
                if b < jammer_seat:
                    pot += amt
            # in jam_ev, blinds before p don't exist (blinds act last)

        # ---- per-sample outcomes (NCLASS, S): EV of hero's hand each trial ---
        if per_sample:
            out = np.zeros((NCLASS, S))
            m0 = n_others == 0
            if m0.any():
                out[:, m0] = (pot[m0] - stack)[None, :]
            m1 = n_others == 1
            if m1.any():
                idx = np.where(m1)[0]
                cls1 = np.empty(len(idx), dtype=np.int64)
                filled = np.zeros(len(idx), dtype=bool)
                if n_opp:
                    sub_mask = in_mask[:, idx]
                    which = sub_mask.argmax(0)
                    has_caller = sub_mask.any(0)
                    cls1[has_caller] = call_cls[which[has_caller], idx[has_caller]]
                    filled |= has_caller
                if always_in_class is not None:
                    cls1[~filled] = jammer_cls[idx[~filled]]
                out[:, idx] = M[:, cls1] * pot[idx][None, :] - stack
            for s in np.where(n_others >= 2)[0]:
                cls_list = []
                if always_in_class is not None:
                    cls_list.append(int(jammer_cls[s]))
                if n_opp:
                    cls_list.extend(int(call_cls[r, s])
                                    for r in np.where(in_mask[:, s])[0])
                eqv = np.ones(NCLASS)
                for c in cls_list:
                    eqv *= M[:, c]
                out[:, s] = eqv * pot[s] - stack
            return out, n_others          # n_others: # callers at showdown per trial

        # ---- bucket by number of opponents at showdown ----------------------
        ev = np.zeros(NCLASS)

        # 0 others -> hero wins whole pot
        m0 = n_others == 0
        if m0.any():
            ev += (pot[m0] - stack).sum()             # same for every hero hand

        # exactly 1 other
        m1 = n_others == 1
        if m1.any():
            # gather that one opponent's class per scenario
            cls1 = np.empty(m1.sum(), dtype=np.int64)
            pot1 = pot[m1]
            if always_in_class is not None and n_opp == 0:
                cls1[:] = jammer_cls[m1]
            else:
                idx = np.where(m1)[0]
                # opponent could be the jammer or a single caller
                filled = np.zeros(len(idx), dtype=bool)
                if n_opp:
                    sub_mask = in_mask[:, idx]            # (n_opp, k)
                    which = sub_mask.argmax(0)            # first/only caller row
                    has_caller = sub_mask.any(0)
                    cls1[has_caller] = call_cls[which[has_caller], idx[has_caller]]
                    filled |= has_caller
                if always_in_class is not None:
                    cls1[~filled] = jammer_cls[idx[~filled]]
            w = np.zeros(NCLASS)
            np.add.at(w, cls1, pot1)
            ev += M.dot(w) - stack * m1.sum()

        # 2+ others -> multiway (independent-equity approximation)
        mm = n_others >= 2
        if mm.any():
            idx = np.where(mm)[0]
            for s in idx:
                cls_list = []
                if always_in_class is not None:
                    cls_list.append(int(jammer_cls[s]))
                if n_opp:
                    rows = np.where(in_mask[:, s])[0]
                    cls_list.extend(int(call_cls[r, s]) for r in rows)
                eqv = np.ones(NCLASS)
                for c in cls_list:
                    eqv *= M[:, c]
                ev += eqv * pot[s] - stack
        return ev / S


# ---------------------------------------------------------------------------
# fictitious play
# ---------------------------------------------------------------------------
def solve(cfg: GameConfig, M: np.ndarray, iters: int = 80,
          samples: int = 30000, seed: int = 7, verbose: bool = True):
    rng = np.random.default_rng(seed)
    ev = Evaluator(cfg, M, rng, samples=samples)
    sigma = Strategy.zeros(cfg)
    n = cfg.n_players

    for t in range(iters):
        br = Strategy.zeros(cfg)
        # jam best responses (seats 0..n-2 can be first-in)
        for p in range(n - 1):
            fold_ev = -cfg.posted(p)
            br.jam[p] = (ev.jam_ev(p, sigma) > fold_ev).astype(np.float64)
        # call best responses
        for q in range(1, n):
            fold_ev = -cfg.posted(q)
            for J in range(q):
                br.call[q][J] = (ev.call_ev(q, J, sigma) > fold_ev).astype(np.float64)

        # fictitious-play average update: sigma <- sigma + (br - sigma)/(t+2)
        w = 1.0 / (t + 2)
        delta = 0.0
        for p in range(n - 1):
            new = sigma.jam[p] + w * (br.jam[p] - sigma.jam[p])
            delta = max(delta, np.abs(new - sigma.jam[p]).max())
            sigma.jam[p] = new
        for q in range(1, n):
            for J in range(q):
                new = sigma.call[q][J] + w * (br.call[q][J] - sigma.call[q][J])
                sigma.call[q][J] = new
        if verbose and (t % 10 == 0 or t == iters - 1):
            print(f"  iter {t:3d}  max-jam-step {delta:.4f}")
    return sigma
