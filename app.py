"""Push/Fold Nash Advisor -- Streamlit UI.

For an N-handed, all-in-or-fold game with constant stacks (auto buy-in, winnings
withdrawn => no ICM), shows GTO push/fold decisions and expected winnings (bb)
for every starting hand, in every position, assuming all players play the Nash
equilibrium.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from pushfold.cards import HAND_CLASSES, RANKS, hand_class_index, combo_count
from pushfold.config import GameConfig
from pushfold.equity import load_or_build_hu_matrix
from pushfold.grid import AXIS, label_grid, to_grid
from pushfold.results import Results, compute_results
from pushfold.solver import solve

st.set_page_config(page_title="Push/Fold Nash Advisor", layout="wide")

STACK, SB, BB = 8.0, 0.4, 1.0          # fixed game (auto buy-in to 8bb)
LABELS = label_grid()


# ---------------------------------------------------------------------------
# data loading / solving (cached)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading equity matrix...")
def get_matrix():
    return load_or_build_hu_matrix(iters=10000)


@st.cache_resource(show_spinner=False)
def get_results(n: int) -> Results | None:
    cfg = GameConfig(n_players=n, stack=STACK, sb=SB, bb=BB)
    if Results.exists(cfg):
        return Results.load(cfg)
    return None


def solve_now(n: int) -> Results:
    cfg = GameConfig(n_players=n, stack=STACK, sb=SB, bb=BB)
    M = get_matrix()
    with st.spinner(f"Solving {n}-handed equilibrium (~1 min, one-time)..."):
        sigma = solve(cfg, M, iters=120, samples=30000, verbose=False)
        res = compute_results(cfg, M, sigma, samples=300000)
        res.save()
    get_results.clear()
    return res


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------
def grid_figure(vec_ev, vec_freq, fold_ev, action="Jam", show_numbers=False):
    g_adv = to_grid(vec_ev - fold_ev)        # advantage of acting vs folding
    g_ev = to_grid(vec_ev)
    g_freq = to_grid(vec_freq) if vec_freq is not None else np.full((13, 13), np.nan)

    text = np.empty((13, 13), dtype=object)
    hover = np.empty((13, 13), dtype=object)
    for r in range(13):
        for c in range(13):
            lab = LABELS[r, c]
            if show_numbers and not np.isnan(g_ev[r, c]):
                text[r, c] = f"{g_ev[r, c]:+.2f}"
            else:
                text[r, c] = lab
            if np.isnan(g_ev[r, c]):
                hover[r, c] = ""
            else:
                hover[r, c] = (f"<b>{lab}</b><br>"
                               f"EV {action.lower()}: {g_ev[r,c]:+.3f} bb<br>"
                               f"EV fold: {fold_ev:+.3f} bb<br>"
                               f"GTO {action.lower()} freq: {100*g_freq[r,c]:.0f}%")
    # diverging scale centered at 0: green = +advantage (act), red = fold
    amax = max(0.05, np.nanmax(np.abs(g_adv)))
    fig = go.Figure(go.Heatmap(
        z=g_adv, x=AXIS, y=AXIS, zmid=0, zmin=-amax, zmax=amax,
        colorscale=[[0, "#b2182b"], [0.5, "#f7f7c8"], [1, "#1a9850"]],
        text=text, texttemplate="%{text}", textfont={"size": 11},
        customdata=hover, hovertemplate="%{customdata}<extra></extra>",
        showscale=True, colorbar={"title": f"EV({action})-EV(fold)"}))
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis=dict(autorange="reversed", title="high card"),
                      xaxis=dict(side="top", title="low card"))
    return fig


# ---------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("♠ Push/Fold Nash")
n_players = st.sidebar.select_slider("Players at the table (occupied seats)",
                                     options=[2, 3, 4, 5, 6], value=4)
st.sidebar.markdown(
    f"**Stack:** {STACK:g} bb &nbsp; **BB:** {BB:g} &nbsp; **SB:** {SB:g}  \n"
    "All-in or fold • auto buy-in (constant stack) • **no ICM**")

cfg = GameConfig(n_players=n_players, stack=STACK, sb=SB, bb=BB)
st.sidebar.caption("Seats (action order): " + " → ".join(cfg.positions))

res = get_results(n_players)
if res is None:
    st.sidebar.warning(f"No solved equilibrium cached for {n_players} players.")
    if st.sidebar.button(f"Solve {n_players}-handed now"):
        res = solve_now(n_players)
    else:
        st.title("Push/Fold Nash Advisor")
        st.info(f"The {n_players}-handed equilibrium isn't solved yet. "
                "Click **Solve now** in the sidebar (one-time, ~1 minute), or "
                "precompute with `python scripts/solve.py --players 2-6`.")
        st.stop()

show_numbers = st.sidebar.checkbox("Show EV numbers in grids", value=False)

POS = cfg.positions

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
st.title("Push/Fold Nash Advisor")
st.caption(cfg.describe() + "  •  EV = expected net bb per hand, GTO opponents.")

tab_help, tab_jam, tab_call, tab_about = st.tabs(
    ["🎯 Should I shove?", "📈 Open-jam ranges", "📞 Calling ranges", "ℹ️ Model"])

# ---- decision helper ------------------------------------------------------
with tab_help:
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        r1 = st.selectbox("Card 1 rank", list(RANKS), index=0, key="r1")
        r2 = st.selectbox("Card 2 rank", list(RANKS), index=1, key="r2")
        if r1 == r2:
            hand = r1 + r2
        else:
            suited = st.radio("Suits", ["Suited", "Offsuit"], horizontal=True)
            hand = f"{r1}{r2}{'s' if suited == 'Suited' else 'o'}"
        st.markdown(f"### Hand: `{hand}`")
        hidx = hand_class_index(hand)
    with c2:
        scenario = st.radio("Situation", ["Folded to me (open)", "Facing a shove"])
        my_pos_options = (POS[:-1] if scenario.startswith("Folded")
                          else POS[1:])
        my_pos = st.selectbox("My position", my_pos_options)
        my_idx = POS.index(my_pos)
        jammer_idx = None
        if scenario == "Facing a shove":
            jammer_opts = POS[:my_idx]
            jammer = st.selectbox("Shover's position", jammer_opts)
            jammer_idx = POS.index(jammer)
    with c3:
        if scenario.startswith("Folded"):
            ev_act = float(res.jam_ev[my_idx][hidx])
            fold_ev = res.jam_fold_ev(my_idx)
            act_name = "SHOVE"
        else:
            ev_act = float(res.call_ev[(my_idx, jammer_idx)][hidx])
            fold_ev = -cfg.posted(my_idx)
            act_name = "CALL"
        do_it = ev_act > fold_ev
        verdict = act_name if do_it else "FOLD"
        color = "#1a9850" if do_it else "#b2182b"
        st.markdown(
            f"<div style='background:{color};padding:18px;border-radius:10px;"
            f"text-align:center;color:white;'>"
            f"<div style='font-size:42px;font-weight:800'>{verdict}</div></div>",
            unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric(f"EV {act_name.lower()}", f"{ev_act:+.3f} bb")
        m2.metric("EV fold", f"{fold_ev:+.3f} bb")
        m3.metric("Gain vs fold", f"{ev_act - fold_ev:+.3f} bb")
        st.caption("Positive 'gain vs fold' ⇒ the aggressive line is +EV. "
                   "EV is net big blinds for this hand, opponents playing GTO.")

# ---- open-jam ranges ------------------------------------------------------
with tab_jam:
    st.subheader("Open-jam ranges (folded to you)")
    st.caption("Green = shoving is +EV vs folding. Hover any cell for EVs.")
    openers = POS[:-1]
    cols = st.columns(min(3, len(openers)))
    for i, pos in enumerate(openers):
        idx = POS.index(pos)
        pct = res.range_pct(res.jam_decision(idx).astype(float))
        with cols[i % len(cols)]:
            st.markdown(f"**{pos}** — shove **{pct:.0f}%** of hands")
            st.plotly_chart(
                grid_figure(res.jam_ev[idx], res.jam_freq[idx],
                            res.jam_fold_ev(idx), "Jam", show_numbers),
                width='stretch', key=f"jam_{idx}")

# ---- calling ranges -------------------------------------------------------
with tab_call:
    st.subheader("Calling ranges (facing an all-in shove)")
    cc1, cc2 = st.columns(2)
    caller = cc1.selectbox("Your position", POS[1:], key="callpos")
    cidx = POS.index(caller)
    jammer = cc2.selectbox("Shover's position", POS[:cidx], key="jammerpos")
    jidx = POS.index(jammer)
    vec = res.call_ev[(cidx, jidx)]
    fold_ev = -cfg.posted(cidx)
    pct = res.range_pct((vec > fold_ev).astype(float))
    st.markdown(f"**{caller}** calling a shove from **{jammer}** — "
                f"call **{pct:.0f}%** of hands  (fold EV {fold_ev:+.2f} bb)")
    st.plotly_chart(
        grid_figure(vec, res.call_freq[(cidx, jidx)], fold_ev, "Call", show_numbers),
        width='stretch', key=f"call_{cidx}_{jidx}")

# ---- about ----------------------------------------------------------------
with tab_about:
    st.markdown(f"""
### Model & assumptions
* **Game:** {n_players}-handed Texas Hold'em, **all-in or fold only**, equal
  **{STACK:g} bb** stacks. BB = {BB:g}, SB = {SB:g}.
* **Auto buy-in / withdrawal:** stacks reset to {STACK:g} bb every hand, so
  chip-EV equals money-EV — **no ICM**. EV is net big blinds per hand.
* **Equilibrium:** Nash, found by fictitious play (iterated best response). All
  opponents are assumed to play this same GTO strategy.
* **Equity:** heads-up all-in equities use an exact Monte-Carlo matrix
  (10k run-outs/matchup). Multiway pots (2+ callers) use an independent-equity
  approximation — a small minority of pots at this depth.
* **Calling ranges** are conditioned on the shover's position. Card-removal is
  modelled in heads-up equities; opponent hand-classes are sampled at the
  169-class level in the forward simulation.

**Reading the grids:** rows = higher card, columns = lower card; upper-right
triangle = suited, lower-left = offsuit, diagonal = pairs. Green cells are
+EV to shove/call; red are folds.
""")
