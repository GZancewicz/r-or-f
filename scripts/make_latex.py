"""Generate the printable LaTeX shove/call sheet for the 4-handed game.

Page 1 (portrait): open-shove ranges, columns CO/BTN/SB/BB. Each cell is that
seat's full threshold; pairs row + rules separate Pairs / suited / offsuit.
Page 2 (landscape): all calling ranges combined -- position groups
(CO placeholder, BTN, SB, BB) with a sub-column per shover.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pushfold.cards import HAND_CLASSES, COMBO_WEIGHTS  # noqa: E402
from pushfold.config import GameConfig                  # noqa: E402
from pushfold.results import Results                     # noqa: E402

RV = {r: v for v, r in enumerate("23456789TJQKA", 2)}
CH = lambda v: "23456789TJQKA"[v - 2]
W = np.asarray(COMBO_WEIGHTS, float)
CFG = GameConfig(4, 8.0, 0.4, 1.0)


def pct(decision):
    return 100 * (decision.astype(float) * W).sum() / W.sum()


def _runs(vals):
    out, s, p = [], None, None
    for v in sorted(set(vals)):
        if s is None:
            s = p = v
        elif v == p + 1:
            p = v
        else:
            out.append((s, p))
            s = p = v
    if s is not None:
        out.append((s, p))
    return out


def compress(colset, high, suit):
    hs = [h for h in colset if len(h) == 3 and h[0] == high and h[2] == suit]
    if not hs:
        return None
    maxk = RV[high] - 1
    parts = []
    for lo, hi in _runs(RV[h[1]] for h in hs):
        if hi == maxk and lo != hi:
            parts.append(f"{high}{CH(lo)}{suit}+")
        elif lo == hi:
            parts.append(f"{high}{CH(lo)}{suit}")
        else:
            parts.append(f"{high}{CH(hi)}{suit}--{high}{CH(lo)}{suit}")
    return " ".join(parts)


def compress_pairs(colset):
    ps = [h for h in colset if len(h) == 2]
    if not ps:
        return None
    parts = []
    for lo, hi in _runs(RV[h[0]] for h in ps):
        if hi == 14 and lo != hi:
            parts.append(f"{CH(lo)}{CH(lo)}+")
        elif lo == hi:
            parts.append(f"{CH(lo)}{CH(lo)}")
        else:
            parts.append(f"{CH(hi)}{CH(hi)}--{CH(lo)}{CH(lo)}")
    return " ".join(parts)


ROW_FNS = ([("Pairs", compress_pairs)]
           + [(f"{h}Xs", (lambda cs, h=h: compress(cs, h, "s"))) for h in "AKQJT98765"]
           + [(f"{h}Xo", (lambda cs, h=h: compress(cs, h, "o"))) for h in "AKQJT987"])


def _group(label):
    return 0 if label == "Pairs" else (1 if label.endswith("Xs") else 2)


def render_body(rows):
    """Join rows, inserting a \\midrule between Pairs / suited / offsuit blocks."""
    out, prev = [], None
    for lab, cells in rows:
        g = _group(lab)
        if prev is not None and g != prev:
            out.append(r"\midrule")
        out.append(lab + " & " + " & ".join(cells) + r"\\")
        prev = g
    return "\n".join(out)


# ---------------------------------------------------------------------------
# open table (one column per seat, full thresholds)
# ---------------------------------------------------------------------------
def open_table(colsets, headers, include_pairs):
    rows = []
    for label, fn in ROW_FNS:
        if label == "Pairs" and not include_pairs:
            continue
        cells = [fn(cs) for cs in colsets]
        if any(c is not None for c in cells):
            rows.append((label, ["--" if c is None else c for c in cells]))
    spec = "R" + " c" * len(headers)
    head = " & ".join(["\\textbf{Row}"] + headers)
    return (f"\\begin{{tabular}}{{{spec}}}\n\\toprule\n{head}\\\\\n"
            f"\\midrule\n{render_body(rows)}\n\\bottomrule\n\\end{{tabular}}")


# ---------------------------------------------------------------------------
# combined calling table (position groups, sub-column per shover)
# ---------------------------------------------------------------------------
def combined_call_table(groups):
    """groups: list of (caller_label, [(sub_label, cumulative_set), ...])."""
    rows = []
    for label, fn in ROW_FNS:
        cells, has_any = [], False
        for _, subs in groups:
            if not subs:                       # CO placeholder
                cells.append("--")
                continue
            prev = None
            for _, cs in subs:
                cur = fn(cs)
                if cur is not None:
                    has_any = True
                cells.append(cur if cur != prev else None)
                prev = cur
        if has_any:
            rows.append((label, ["--" if c is None else c for c in cells]))

    # vertical rule between each seat group (and after the Row label)
    spec = "R" + "".join("|" + "c" * max(1, len(s)) for _, s in groups)
    h1, h2, cmids, col = ["\\textbf{Row}"], [""], [], 2
    ng = len(groups)
    for gi, (cl, subs) in enumerate(groups):
        n = max(1, len(subs))
        align = "c|" if gi < ng - 1 else "c"     # right rule on every group but the last
        h1.append(f"\\multicolumn{{{n}}}{{{align}}}{{\\textbf{{{cl}}}}}")
        cmids.append(f"\\cmidrule(lr){{{col}-{col + n - 1}}}")
        col += n
        if not subs:
            h2.append("{\\footnotesize n/a}")
        else:
            h2.extend(f"{{\\footnotesize {sl}}}" for sl, _ in subs)
    return ("\\begin{tabular}{" + spec + "}\n\\toprule\n"
            + " & ".join(h1) + "\\\\\n" + "".join(cmids) + "\n"
            + " & ".join(h2) + "\\\\\n\\midrule\n"
            + render_body(rows) + "\n\\bottomrule\n\\end{tabular}")


def build():
    res = Results.load(CFG)
    pos = CFG.positions
    inset = lambda d: set(h for i, h in enumerate(HAND_CLASSES) if d[i])

    co = inset(res.jam_decision(0))
    btn = inset(res.jam_decision(1)) | co
    sb = inset(res.jam_decision(2)) | btn
    cum = {0: co, 1: btn, 2: sb, 3: set()}
    open_cols, open_hdr = [], []
    for s in (3, 2, 1, 0):                        # BB, SB, BTN, CO -- match calling chart
        open_cols.append(cum[s])
        if s == 3:
            open_hdr.append(r"\textbf{BB} (walk)")
        else:
            open_hdr.append(f"\\textbf{{{pos[s]}+}} ({pct(res.jam_decision(s)):.0f}\\%)")
    open_tbl = open_table(open_cols, open_hdr, include_pairs=True)

    groups = []
    for q in range(4):                          # CO(placeholder), BTN, SB, BB
        subs, cum = [], set()
        for J in range(q):
            cum = cum | inset(res.call_decision(q, J))     # nest: wider vs looser shover
            subs.append((f"vs {pos[J]} ({pct(res.call_decision(q, J)):.0f}\\%)", set(cum)))
        groups.append((pos[q], subs))
    return open_tbl, combined_call_table(groups[::-1])     # display BB, SB, BTN, CO


HEAD = r"""\documentclass[11pt]{article}
\usepackage[margin=0.6in]{geometry}
\usepackage{booktabs}\usepackage{array}\usepackage{enumitem}\usepackage{pdflscape}
\setlist{nosep,leftmargin=1.4em}
\renewcommand{\arraystretch}{1.25}
\pagestyle{empty}
\newcolumntype{R}{>{\bfseries}c}
\begin{document}
"""

OPEN_PAGE = r"""\begin{center}
{\LARGE\bfseries Open-Shove Chart}\\[2pt]
{\large 4-handed \;$\cdot$\; 8\,bb \;$\cdot$\; SB 0.4 / BB 1.0 \;$\cdot$\; all-in or fold \;$\cdot$\; Nash}
\end{center}
\noindent\textbf{Use this ONLY when it is folded to you.}\\[-2pt]
\begin{center}OPEN_TBL\end{center}
\noindent\textbf{How to read:} each column is that seat's full open-shove threshold
(``Q4s+'' = all suited queens down to Q4s); ``--'' = no hands of that type. The \textbf{BB}
column is all dashes because the BB never open-shoves --- if it folds to the BB it's a walk
(you already win). Ranges nest CO $\subseteq$ BTN $\subseteq$ SB.
\par\vspace{4pt}
\noindent\textbf{If anyone has already shoved, DO NOT use this page} --- use the Calling chart.
Calling your open range vs a shove costs $\approx$20\,bb/100.
\par\vspace{6pt}
\noindent\textbf{\large Notes}\par\nobreak\vspace{2pt}
\begin{itemize}
\item \textbf{The SB+ column is mostly blind defense} ($\approx$0.3\,bb/100, almost all of it recovering the 0.4 you'd forfeit by folding). The valuable part is \textbf{the offsuit kings (K2o+)}; the low suited tail (84s, 74s, 63s, 53s\dots) is a rounding error -- skip it if simplifying.
\item \textbf{Break-even hands wobble:} single-hand cells sit near 0\,EV and can flip with tiny changes -- don't sweat the exact edge.
\item \textbf{Button range is a safe SB default:} every BTN hand is also a +EV SB shove, so ``BTN range in the SB'' never misfires -- it just leaves $\approx$0.3\,bb/100 of the fringe behind.
\item \textbf{Constant 8\,bb stacks} (auto buy-in / winnings withdrawn) $\Rightarrow$ chip-EV $=$ money-EV, no ICM.
\end{itemize}
"""

CALL_PAGE = r"""\begin{landscape}
\begin{center}
{\LARGE\bfseries Calling Chart --- all seats}\\[2pt]
{\large facing an all-in shove \;$\cdot$\; 4-handed \;$\cdot$\; 8\,bb \;$\cdot$\; Nash}
\end{center}
\noindent\textbf{Use this ONLY when someone has already moved all-in} in front of you.
Top groups are \emph{your} seat; sub-columns are the shover's seat (tightest shover first).
Within a group ``--'' = same as the column to its left --- you call \emph{wider} vs a looser
shover. (CO acts first, so it never faces a shove.)
\par\vspace{6pt}
\begin{center}\large CALL_TBL\end{center}
\par\vspace{8pt}
\noindent\fbox{\parbox{0.96\linewidth}{%
\textbf{Facing 2+ all-ins (over-call):} the table is for \emph{one} shover. If someone has
already \emph{called} the all-in ahead of you, call only premiums --- about
\textbf{66+, ATs+, KTs+, AK, AQ} ($\approx$half as wide). You must beat \emph{two} strong
ranges, and a cold-caller is never bluffing. Tighten more if an early/tight seat called; stay
a touch wider if both players in were late (BTN/SB). With all three all-in, tighten again to
$\approx$TT+ / AQ+ / AK. (Only the SB and BB can ever face this; the BTN faces at most one.)}}
\end{landscape}
"""


def main():
    open_tbl, call_tbl = build()
    body = OPEN_PAGE.replace("OPEN_TBL", open_tbl)
    body += CALL_PAGE.replace("CALL_TBL", call_tbl)
    tex = HEAD + body + "\\end{document}\n"
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "charts")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "shove_chart.tex")
    with open(path, "w") as f:
        f.write(tex)
    print(os.path.abspath(path))


if __name__ == "__main__":
    main()
