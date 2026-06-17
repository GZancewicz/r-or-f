# Push/Fold Nash Advisor (`r-or-f`)

GTO **shove-or-fold** advice and **expected winnings** for short-stack Texas
Hold'em, for the specific game you described:

* **N players** (2–6, selectable — "some seats may be empty")
* **All-in or fold only**
* **8 bb effective stacks**, **BB = 1.0**, **SB = 0.4** (everything normalized to bb)
* **Auto buy-in / winnings withdrawn** → stacks reset to 8 bb every hand, so
  chip-EV equals money-EV and there is **no ICM**. EV is just expected net big
  blinds per hand.

For every position and every one of the 169 starting hands it tells you whether
to **shove or fold** and your **expected winnings (bb)**, assuming all opponents
play the same Nash-equilibrium strategy.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) build the heads-up equity matrix (one-time, ~2 min, cached to data/)
python scripts/build_matrix.py

# 2) solve the equilibria you want (cached to data/results/)
python scripts/solve.py --players 2-6

# 3) launch the app
streamlit run app.py
```

(The repo already ships with solved results in `data/`, so step 3 works
immediately. Steps 1–2 only re-run if you change the game or want fresh solves.)

## What the app shows

* **🎯 Should I shove?** — pick your cards, position, and whether it's folded to
  you or you're facing a shove. Big **SHOVE / FOLD** verdict plus EV(action),
  EV(fold), and the gain over folding.
* **📈 Open-jam ranges** — the 13×13 grid of open-shoving decisions for each
  position (folded to you), colored by EV.
* **📞 Calling ranges** — your call/fold grid versus a shove from any earlier
  position.
* **ℹ️ Model** — the assumptions below.

Grid layout: rows = higher card, columns = lower card; upper-right triangle =
suited, lower-left = offsuit, diagonal = pairs. Green = +EV to act, red = fold.
Hover a cell for exact EVs.

## How it works

1. **Equity** — a 169×169 heads-up all-in equity matrix is precomputed by
   Monte-Carlo (10k run-outs per matchup) and cached. Validated against known
   matchups (AA vs KK ≈ 82%, AKo vs QQ ≈ 43%, …).
2. **Equilibrium** — found by **fictitious play** (iterated best response). Each
   player's EV at every decision is estimated by a vectorized forward
   Monte-Carlo simulation of the hand given the opponents' current strategies,
   which naturally captures fold equity, multiway over-calls, and dead blinds.
3. **Results** — the converged strategy is re-evaluated at high sample count to
   produce the EV tables and push/fold decisions, then cached.

## Modeling assumptions / limitations

* Equal stacks ⇒ after the first all-in everyone else can only call or fold
  (no re-raising); every player acts at most once.
* **Calling ranges are conditioned on the shover's position** (the standard
  "calling range vs a shove from seat X" model). The simulation still accounts
  for additional callers and multiway equities; it does not separately solve
  squeeze/over-call tightening.
* **Heads-up** all-in equities are exact (MC matrix). **Multiway** pots (2+
  callers — a minority at 8 bb) use an independent-equity approximation.
* Opponent hand-classes are sampled at the 169-class level; card-removal is
  modeled in the heads-up equities but approximated in the forward simulation.
  These are standard class-level simplifications; thresholds are accurate to a
  fraction of a hand class.

These are practical approximations, not a commercial-grade ICM solver — but the
ranges reproduce known short-stack Nash charts (e.g. heads-up button shoves
~60% at 8 bb; later positions shove wider; you call wider versus wider shovers).

## Table view (standalone, no server)

A zero-dependency poker-table UI seated **you at the bottom, one villain left,
one across, one right** — just double-click `web/table.html` (works over
`file://`). Pick your position and two cards; click an earlier player to mark
them all-in. It shows a big **SHOVE / CALL / FOLD** verdict with EV(action),
EV(fold), and the gain, read straight from the solved 4-handed Nash strategy.

Regenerate its data after re-solving:

```bash
python scripts/export_web.py   # writes web/data.js from data/results/n4_*.npz
```

## Layout

```
pushfold/      cards, config, equity, solver, results, grid
scripts/       build_matrix.py, solve.py, export_web.py
data/          cached equity matrix + solved results
app.py         Streamlit UI
web/           standalone 4-seat table UI (table.html/.css/.js + data.js)
```
