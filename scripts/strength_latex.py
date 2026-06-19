"""Generate a LaTeX (TikZ) document of the strength heatmaps — one page per
seat — reproducing web/charts/strength exactly: per-seat grayscale fill, the
Top-X% set outlined in black with black text, the rest greyed out, and each
cell labelled with hand / win% / odds.

Reads web/charts/strength/data.js, writes data/charts/strength/strength.tex
and compiles it with pdflatex.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA_JS = os.path.join(ROOT, "web", "charts", "strength", "data.js")
OUT_DIR = os.path.join(ROOT, "data", "charts", "strength")
TEX = os.path.join(OUT_DIR, "strength.tex")

# per-seat odds bar: a hand is "in" (outlined) if its odds to be best are this
# good or better. Loosens ~0.5:1 per seat toward the button.
PER_SEAT_ODDS = {"UTG": 3.5, "MP": 3.0, "CO": 2.5, "BTN": 2.0, "SB": 1.0}
OPP_PCTS = [10, 15, 20]   # opponent range widths for the equity-vs-range pages
S = 1.5                   # cell side, cm
RR = "AKQJT98765432"
COMBOS = lambda h: 6 if len(h) == 2 else (4 if h.endswith("s") else 12)


def load_probs():
    txt = open(DATA_JS).read()
    data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    return data["meta"]["seats"], data["bySeat"]


def odds_str(p):
    if p <= 0 or p >= 1:
        return ""
    return f"{(1 - p) / p:.1f}:1" if p < 0.5 else f"1:{p / (1 - p):.1f}"


def odds_str_int(p):                               # rounded to the nearest whole number
    if p <= 0 or p >= 1:
        return ""
    return f"{round((1 - p) / p)}:1" if p < 0.5 else f"1:{round(p / (1 - p))}"


# ---- compact range notation (port of the web compressor) ----
def _runs(asc):
    res, i = [], 0
    while i < len(asc):
        j = i
        while j + 1 < len(asc) and asc[j + 1] == asc[j] + 1:
            j += 1
        res.append((asc[i], asc[j]))
        i = j + 1
    return res


def compress(hands):
    s, out = set(hands), []
    pr = [i for i in range(13) if RR[i] + RR[i] in s]
    for a, b in _runs(pr):
        out.append(f"{RR[b]}{RR[b]}+" if a == 0 else
                   (f"{RR[a]}{RR[a]}" if a == b else f"{RR[b]}{RR[b]}-{RR[a]}{RR[a]}"))
    for suit in ("s", "o"):
        for h in range(13):
            ks = [k for k in range(h + 1, 13) if RR[h] + RR[k] + suit in s]
            for a, b in _runs(ks):
                out.append(f"{RR[h]}{RR[b]}{suit}+" if a == h + 1 else
                           (f"{RR[h]}{RR[a]}{suit}" if a == b
                            else f"{RR[h]}{RR[b]}{suit}-{RR[h]}{RR[a]}{suit}"))
    return ", ".join(out)


def select_by_odds(P, x):
    pmin = 1.0 / (x + 1.0)                     # win% needed for X:1 to be best
    sel = {h for h in P if P[h] >= pmin}
    combos = sum(COMBOS(h) for h in sel)
    return sel, combos


def cell_label(r, c):
    if r == c:
        return RR[r] + RR[r]
    return (RR[r] + RR[c] + "s") if r < c else (RR[c] + RR[r] + "o")


def seat_tikz(name, opp, P, odds_bar):
    lo = min(P.values()); hi = max(P.values())
    sel, combos = select_by_odds(P, odds_bar)
    lines = ["\\begin{tikzpicture}"]
    for r in range(13):
        for c in range(13):
            label = cell_label(r, c)
            p = P[label]
            norm = (p - lo) / (hi - lo) if hi > lo else 0.0
            bp = round(4 + 41 * norm)                       # black!bp!white (matches web grays)
            x0, y0 = c * S, -r * S
            cx, cy = x0 + S / 2, y0 - S / 2
            sel_hand = label in sel
            fav = (not sel_hand) and p > 0.5            # favourite but outside the range
            tc = "black" if sel_hand else ("black!78" if fav else "black!62")
            lines.append(f"\\fill[black!{bp}!white] ({x0:.3f},{y0:.3f}) rectangle ({x0 + S:.3f},{y0 - S:.3f});")
            lines.append(f"\\draw[black!18,line width=0.3pt] ({x0:.3f},{y0:.3f}) rectangle ({x0 + S:.3f},{y0 - S:.3f});")
            if sel_hand:
                lines.append(f"\\draw[black,line width=1.1pt] ({x0+0.02:.3f},{y0-0.02:.3f}) rectangle ({x0 + S-0.02:.3f},{y0 - S+0.02:.3f});")
            elif fav:
                lines.append(f"\\draw[black!55,line width=0.8pt] ({x0+0.02:.3f},{y0-0.02:.3f}) rectangle ({x0 + S-0.02:.3f},{y0 - S+0.02:.3f});")
            pct = f"{round(p * 100)}\\%"
            od = odds_str(p)
            node = (f"{{\\fontsize{{9.5}}{{10}}\\selectfont\\textbf{{{label}}}}}"
                    f"\\\\[1.5pt]{{\\fontsize{{7.5}}{{8}}\\selectfont {pct}}}"
                    f"\\\\[0.5pt]{{\\fontsize{{6.3}}{{6.8}}\\selectfont {od}}}")
            lines.append(f"\\node[align=center,inner sep=0pt,text={tc}] at ({cx:.3f},{cy:.3f}) {{{node}}};")
    lines.append("\\end{tikzpicture}")
    rng = compress(sel)
    pct_of = combos / 1326 * 100
    return name, opp, "\n".join(lines), rng, len(sel), combos, pct_of


def vsrange_pages(M, HC, W):
    """LaTeX pages: your heads-up equity vs an opponent on the top X% of hands."""
    ix = {h: i for i, h in enumerate(HC)}
    wsum = sum(W)
    opp_str = [sum(W[j] * M[i][j] for j in range(169)) / wsum for i in range(169)]
    order = sorted(range(169), key=lambda i: -opp_str[i])

    def opp_set(pct):
        target, s, combos = pct / 100 * 1326, [], 0
        for j in order:
            if combos >= target:
                break
            s.append(j); combos += W[j]
        return s, combos

    def equity_vs(hero, s):
        n = sum(W[j] * M[hero][j] for j in s)
        d = sum(W[j] for j in s)
        return n / d if d else 0.0

    out, vs_summary = [], []
    for pct in OPP_PCTS:
        oset, ocombos = opp_set(pct)
        eq = {h: equity_vs(ix[h], oset) for h in HC}
        lo, hi = min(eq.values()), max(eq.values())
        favs = [h for h in HC if eq[h] >= 0.5]
        fav_combos = sum(COMBOS(h) for h in favs)
        oset_labels = [HC[j] for j in oset]
        vs_summary.append((pct, ocombos, compress(oset_labels), fav_combos, compress(favs)))

        lines = ["\\begin{tikzpicture}"]
        for r in range(13):
            for c in range(13):
                label = cell_label(r, c)
                e = eq[label]
                norm = (e - lo) / (hi - lo) if hi > lo else 0.5
                bp = round(4 + 41 * norm)
                x0, y0 = c * S, -r * S
                cx, cy = x0 + S / 2, y0 - S / 2
                tc = "white" if norm > 0.62 else "black"
                lines.append(f"\\fill[black!{bp}!white] ({x0:.3f},{y0:.3f}) rectangle ({x0 + S:.3f},{y0 - S:.3f});")
                lines.append(f"\\draw[black!18,line width=0.3pt] ({x0:.3f},{y0:.3f}) rectangle ({x0 + S:.3f},{y0 - S:.3f});")
                if e >= 0.5:
                    lines.append(f"\\draw[black,line width=1.1pt] ({x0+0.02:.3f},{y0-0.02:.3f}) rectangle ({x0 + S-0.02:.3f},{y0 - S+0.02:.3f});")
                node = (f"{{\\fontsize{{9.5}}{{10}}\\selectfont\\textbf{{{label}}}}}"
                        f"\\\\[1.5pt]{{\\fontsize{{7.5}}{{8}}\\selectfont {round(e*100)}\\%}}"
                        f"\\\\[0.5pt]{{\\fontsize{{6.3}}{{6.8}}\\selectfont {odds_str_int(e)}}}")
                lines.append(f"\\node[align=center,inner sep=0pt,text={tc}] at ({cx:.3f},{cy:.3f}) {{{node}}};")
        lines.append("\\end{tikzpicture}")

        out += [
            r"\begin{center}",
            rf"{{\LARGE\bfseries Your Equity vs Opponent's Top {pct}\%}}\\[2pt]",
            r"{\normalsize Heads-up (you on SB) $\cdot$ your win\% and odds at showdown vs the range below}",
            r"\end{center}",
            r"\vspace{3pt}",
            r"\begin{center}", "\n".join(lines), r"\end{center}",
            r"\vspace{8pt}",
            r"{\large",
            rf"\textbf{{Opponent's range (top {pct}\%, {ocombos} combos)}}:\\[2pt]",
            rf"\texttt{{{compress(oset_labels)}}}\\[8pt]",
            rf"\textbf{{You're a favourite ($\geq$50\%) with}} ({len(favs)} classes, {fav_combos} combos, {fav_combos/1326*100:.1f}\%):\\[2pt]",
            rf"\texttt{{{compress(favs)}}}\par}}",
            r"\newpage",
        ]
    return out, vs_summary


def outs_table():
    """Outs -> chance of hitting at least one out on ANY remaining card:
    from the flop both the turn and river are still to come (2 cards), from the
    turn only the river is (1 card). 47 unseen on the flop, 46 on the turn."""
    def od(p):
        x = (1 - p) / p
        return f"{x:.1f}:1" if x < 10 else f"{round(x)}:1"

    lines = [
        r"\begin{center}{\LARGE\bfseries Outs to Equity \& Odds}\\[2pt]",
        r"{\normalsize chance to hit at least one out on any remaining card $\cdot$ \% and odds against}\end{center}",
        r"\vspace{12pt}",
        r"\renewcommand{\arraystretch}{1.4}",
        r"\begin{center}",
        r"\begin{tabular}{c cc cc}",
        r"\toprule",
        r"& \multicolumn{2}{c}{\textbf{On the flop}} & \multicolumn{2}{c}{\textbf{On the turn}}\\",
        r"& \multicolumn{2}{c}{\footnotesize turn \& river to come} & \multicolumn{2}{c}{\footnotesize river to come}\\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
        r"\textbf{Outs} & \textbf{\%} & \textbf{Odds} & \textbf{\%} & \textbf{Odds}\\",
        r"\midrule",
    ]
    for o in range(1, 21):
        p_flop = 1 - (47 - o) * (46 - o) / (47 * 46)   # by the river (2 cards)
        p_turn = o / 46                                # river only (1 card)
        lines.append(rf"{o} & {round(p_flop*100)} & {od(p_flop)} & {round(p_turn*100)} & {od(p_turn)}\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{center}"]
    lines += [
        r"\vspace{10pt}",
        r"{\footnotesize\textit{On the flop} assumes you see both the turn and river (e.g.\ all-in). "
        r"If you must pay again to see the river, a single next card is only about half of that.\par}",
    ]
    return lines


def main():
    from pushfold.cards import HAND_CLASSES, COMBO_WEIGHTS
    from pushfold.equity import load_or_build_hu_matrix

    seats, by_seat = load_probs()
    os.makedirs(OUT_DIR, exist_ok=True)

    doc = [
        r"\documentclass[10pt]{article}",
        r"\usepackage[margin=0.35in]{geometry}",
        r"\usepackage{tikz}\usepackage{xcolor}\usepackage{booktabs}",
        r"\usepackage[scaled=0.95]{helvet}\renewcommand{\familydefault}{\sfdefault}",
        r"\pagestyle{empty}\setlength{\parindent}{0pt}",
        r"\begin{document}",
    ]
    summaries = []
    for s in seats:
        name, opp = s["name"], s["opponents"]
        bar = PER_SEAT_ODDS[name]
        bs = f"{bar:g}"
        _, _, tikz, rng, nclass, combos, pct_of = seat_tikz(name, opp, by_seat[name], bar)
        summaries.append((name, opp, bs, rng, nclass, combos, pct_of))
        doc += [
            r"\begin{center}",
            rf"{{\LARGE\bfseries Strength Chart: {name}}}\\[2pt]",
            rf"{{\normalsize P(best at showdown) $\cdot$ 6-handed, folded to you $\cdot$ vs {opp} opponents $\cdot$ outlined: $\geq$ {bs}:1 to be best}}",
            r"\end{center}",
            r"\vspace{3pt}",
            r"\begin{center}",
            tikz,
            r"\end{center}",
            r"\vspace{8pt}",
            r"{\large",
            rf"\textbf{{Range ($\geq$ {bs}:1 to be best)}}: {nclass} classes, {combos} combos, {pct_of:.1f}\% of hands:\\[4pt]",
            rf"\texttt{{{rng}}}\par}}",
            r"\newpage",
        ]
    # ---- equity-vs-opponent-range pages ----
    M = load_or_build_hu_matrix(iters=10000)
    vs_pages, vs_summary = vsrange_pages(M, HAND_CLASSES, COMBO_WEIGHTS)
    doc += vs_pages

    # ---- final cheat-sheet page: every position's range in one table ----
    doc += [
        r"\begin{center}",
        r"{\LARGE\bfseries Playable Ranges by Position}\\[2pt]",
        r"{\normalsize 6-handed $\cdot$ folded to you $\cdot$ hands above each seat's odds-to-be-best bar}",
        r"\end{center}",
        r"\vspace{18pt}",
        r"\renewcommand{\arraystretch}{1.8}",
        r"\begin{center}",
        r"\begin{tabular}{l c c r p{0.56\textwidth}}",
        r"\toprule",
        r"\textbf{Pos} & \textbf{Opp} & \textbf{Bar} & \textbf{Hands} & \textbf{Playable range}\\",
        r"\midrule",
    ]
    for name, opp, bs, rng, nclass, combos, pct_of in summaries:
        doc.append(rf"\textbf{{{name}}} & {opp} & $\geq${bs}:1 & {pct_of:.1f}\% & \texttt{{{rng}}}\\")
    doc += [r"\bottomrule", r"\end{tabular}", r"\end{center}"]

    # ---- second table: hands you're a favourite with vs each opponent range ----
    doc += [
        r"\vspace{26pt}",
        r"\begin{center}{\large\bfseries Heads-up: Hands You're a Favourite With ($\geq$50\%) vs Opponent's Range}\end{center}",
        r"\vspace{10pt}",
        r"\begin{center}",
        r"\begin{tabular}{c c p{0.62\textwidth}}",
        r"\toprule",
        r"\textbf{Opponent} & \textbf{Hands} & \textbf{You're a favourite with}\\",
        r"\midrule",
    ]
    for pct, ocombos, opp_rng, fav_combos, fav_rng in vs_summary:
        doc.append(rf"top {pct}\% & {fav_combos/1326*100:.1f}\% & \texttt{{{fav_rng}}}\\")
    doc += [r"\bottomrule", r"\end{tabular}", r"\end{center}"]

    # ---- outs-to-equity reference page ----
    doc.append(r"\newpage")
    doc += outs_table()
    doc.append(r"\end{document}")

    with open(TEX, "w") as f:
        f.write("\n".join(doc))
    print(f"wrote {TEX}")

    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                        os.path.basename(TEX)], cwd=OUT_DIR,
                       capture_output=True, text=True)
    pdf = TEX.replace(".tex", ".pdf")
    if os.path.exists(pdf):
        print(f"compiled {pdf}")
    else:
        print("pdflatex FAILED:\n" + r.stdout[-1500:])
        sys.exit(1)


if __name__ == "__main__":
    main()
