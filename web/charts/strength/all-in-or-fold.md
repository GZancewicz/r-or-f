# All-In or Fold — Game Rules

* **Up to 4 players**
* **$2.00 buy-in** per player
* Blinds: **SB $0.10**, **BB $0.25** → stacks are **8 bb** effective (SB = 0.4 bb)
* Only two actions: **ALL-IN** or **FOLD** — no other bet sizes
* **Bankrolls trued up to $2.00 after each round** → stacks reset every hand,
  chip-EV equals money-EV, no ICM

## Player stats (shown in the app for each player)

| Stat | Meaning |
|------|---------|
| **All-in** | Number of times the player went ALL-IN when they had the option |
| **Fold** | Number of times the player FOLDED when they had the option |
| **FTA** | *Fold To All-in* — how often the player folds when one or more players have already gone all-in |
| **ATS** | *Attempt To Steal* — how often the player goes all-in from any position other than BB when nobody has shoved yet (blind-steal frequency) |

## How the "All-in or Fold" page uses these stats

* The **first shove** ahead of you is a steal → that player is put on their **top ATS%** of hands.
* A shove **over an earlier all-in** is a call/reshove → **top (100 − FTA)%** of hands.
* A player still **to act behind you** is assumed to **fold with probability FTA**;
  when they don't fold, they call with their **top (100 − FTA)%** of hands.
* The raw **All-in %** is a blend of these two situations — every decision is either
  "no shove yet" (ATS) or "facing a shove" (100 − FTA) — so ATS and FTA together
  already carry all of its information.
* The range card shows **P(win at showdown given you get called)** — averaged over
  every fold/call combination of the players behind you that produces a showdown,
  using precomputed heads-up equities. The everyone-folds case is deliberately
  **excluded**: with fold equity included, nearly any hand "wins" more than half
  the time and the chart stops discriminating.
