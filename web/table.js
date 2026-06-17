/* Push/Fold GTO table UI — every number comes live from the Rust engine
   (POST /api/simulate). No precomputed data; the page is served by the engine. */
(function () {
  "use strict";

  // table structure only (positions); all GTO numbers come from the engine
  const POSITIONS = {
    2: ["SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["CO", "BTN", "SB", "BB"],
  };
  const SAMPLES = 60000;

  const RANKS = "AKQJT98765432".split("");
  const RVAL = Object.fromEntries(RANKS.map((r, i) => [r, i]));
  const SUITS = [
    { v: "s", sym: "♠", red: false },
    { v: "h", sym: "♥", red: true },
    { v: "d", sym: "♦", red: true },
    { v: "c", sym: "♣", red: false },
  ];
  const SUIT_SYM = Object.fromEntries(SUITS.map((s) => [s.v, s]));

  const LAYOUT = {
    1: [{ t: 12, l: 50, who: "across" }],
    2: [{ t: 18, l: 18, who: "to your left" }, { t: 18, l: 82, who: "to your right" }],
    3: [{ t: 46, l: 11, who: "to your left" }, { t: 12, l: 50, who: "across" },
        { t: 46, l: 89, who: "to your right" }],
  };

  // -------- state --------
  const state = { nPlayers: 4, heroPos: 0, cards: [], actions: {} };
  const POS = () => POSITIONS[state.nPlayers];
  const btnIdx = () => { const i = POS().indexOf("BTN"); return i >= 0 ? i : 0; };

  // default: it's folded to you — every earlier seat folds. Flip a seat to
  // All-in only when that player actually shoves into you.
  function foldedToMe() {
    const a = {};
    for (let i = 0; i < state.heroPos; i++) a[i] = "fold";
    return a;
  }
  function setPlayers(n) {
    state.nPlayers = n;
    state.heroPos = btnIdx();
    state.actions = foldedToMe();
  }

  function handLabel(c0, c1) {
    if (!c0 || !c1) return null;
    if (c0.r === c1.r && c0.s === c1.s) return null;
    if (c0.r === c1.r) return c0.r + c1.r;
    let hi = c0, lo = c1;
    if (RVAL[c1.r] < RVAL[c0.r]) { hi = c1; lo = c0; }
    return hi.r + lo.r + (c0.s === c1.s ? "s" : "o");
  }

  // -------- seats --------
  function villains() {
    const n = state.nPlayers;
    return LAYOUT[n - 1].map((slot, k) => ({ seat: (state.heroPos + k + 1) % n, slot }));
  }
  const earlierSeats = () => Array.from({ length: state.heroPos }, (_, i) => i);
  const unspecified = () => earlierSeats().filter((i) => !state.actions[i]);
  const allinSeats = () =>
    earlierSeats().filter((i) => state.actions[i] === "allin").sort((a, b) => a - b);

  function dealerCorner(seat, slot) {
    if (seat === state.heroPos) return "hero";
    if (slot.l < 35) return "left";
    if (slot.l > 65) return "right";
    return "top";
  }
  const dealerDisk = (seat, slot) =>
    seat === btnIdx() ? `<div class="dealer-btn d-${dealerCorner(seat, slot)}">B</div>` : "";

  // -------- which scenario are we in (no numbers — those come from the engine) --------
  function preflight() {
    const h = state.heroPos, n = state.nPlayers;
    if (unspecified().length) return { kind: "unspecified", n: unspecified().length };
    if (state.cards.length < 2) return { kind: "incomplete" };
    const lbl = handLabel(state.cards[0], state.cards[1]);
    if (!lbl) return { kind: "invalid" };
    const allin = allinSeats();
    if (allin.length === 0) {
      if (h === n - 1) return { kind: "walk" };
      return { kind: "ready", mode: "shove", lbl };
    }
    return { kind: "ready", mode: "call", lbl, vs: POS()[allin[0]], multi: allin.length > 1 };
  }

  // -------- rendering --------
  const $ = (id) => document.getElementById(id);

  function cardHTML(c, empty) {
    if (empty) return '<div class="pcard empty">?</div>';
    const s = SUIT_SYM[c.s];
    return `<div class="pcard pick ${s.red ? "red" : ""}" data-r="${c.r}" data-s="${c.s}" title="click to remove">
      <span class="r">${c.r}</span><span class="s">${s.sym}</span></div>`;
  }
  const badge = (t, cls) => `<span class="badge ${cls}">${t}</span>`;

  function seatHTML(seat, slot) {
    const head = `${dealerDisk(seat, slot)}
      <div class="pos">${POS()[seat]}</div><div class="who">${slot.who}</div>`;
    if (seat >= state.heroPos) return head + badge("TO ACT", "toact");
    const a = state.actions[seat];
    return head + `<div class="act-btns">
      <button class="abtn fold ${a === "fold" ? "on" : ""}"  data-seat="${seat}" data-act="fold">Fold</button>
      <button class="abtn allin ${a === "allin" ? "on" : ""}" data-seat="${seat}" data-act="allin">All-in</button>
    </div>`;
  }

  function render() {
    $("playerSeg").innerHTML = [4, 3, 2].map(
      (n) => `<button data-n="${n}" class="${n === state.nPlayers ? "active" : ""}">${n}</button>`
    ).join("");

    $("villains").innerHTML = villains().map(({ seat, slot }) =>
      `<div class="seat seat-villain ${state.actions[seat] === "allin" ? "is-shover" : ""}
            ${state.actions[seat] === "fold" ? "is-folded" : ""}"
            style="top:${slot.t}%;left:${slot.l}%">${seatHTML(seat, slot)}</div>`
    ).join("");

    $("seat-hero").classList.add("is-hero");
    $("seat-hero").innerHTML =
      `${dealerDisk(state.heroPos, { l: 50 })}<div class="pos">${POS()[state.heroPos]}</div>
       <div class="who">YOU</div>
       <div class="hero-cards">
         ${cardHTML(state.cards[0], !state.cards[0])}${cardHTML(state.cards[1], !state.cards[1])}
       </div>`;

    renderBoard();
    $("deckCount").textContent = `${state.cards.length} / 2`;

    const n = state.nPlayers, allin = allinSeats();
    $("feltLabel").textContent =
      unspecified().length ? "Set the action for the players before you"
      : allin.length ? `${POS()[allin[0]]} is all-in — folds to you${allin.length > 1 ? ` (+${allin.length - 1} more)` : ""}`
      : state.heroPos === n - 1 ? "Folded to you — a walk"
      : "Folded to you";

    updateVerdict();
  }

  function evChip(k, val, big) {
    const cls = val > 0 ? "pos" : val < 0 ? "neg" : "";
    const sign = val > 0 ? "+" : "";
    return `<div class="ev-chip ${big ? "big" : ""}"><div class="k">${k}</div>
            <div class="v ${cls}">${sign}${val.toFixed(2)}</div></div>`;
  }
  const plainChip = (k, txt) =>
    `<div class="ev-chip"><div class="k">${k}</div><div class="v plain">${txt}</div></div>`;

  // -------- verdict: placeholder synchronously, then live numbers from the engine --------
  let statTimer = null, reqToken = 0;

  function updateVerdict() {
    const a = $("verdictAction"), d = $("verdictDetail"), row = $("evRow");
    a.className = "verdict-action";
    const pf = preflight();

    if (pf.kind === "unspecified") {
      a.classList.add("none"); a.textContent = "—";
      d.innerHTML = `<span class="warn">⚠ Mark Fold or All-in for the ${pf.n} player${pf.n > 1 ? "s" : ""} before you to see your stats.</span>`;
      row.innerHTML = ""; clearTimeout(statTimer); reqToken++; return;
    }
    if (pf.kind === "incomplete") {
      a.classList.add("none"); a.textContent = "—";
      d.textContent = `Click ${2 - state.cards.length} more card${state.cards.length === 1 ? "" : "s"} on the left.`;
      row.innerHTML = ""; clearTimeout(statTimer); reqToken++; return;
    }
    if (pf.kind === "invalid") {
      a.classList.add("none"); a.textContent = "—";
      d.textContent = "Pick two different cards."; row.innerHTML = ""; clearTimeout(statTimer); reqToken++; return;
    }
    if (pf.kind === "walk") {
      a.classList.add("none"); a.textContent = "WALK";
      d.textContent = "Everyone folded to your big blind — you win the blinds. No decision.";
      row.innerHTML = ""; clearTimeout(statTimer); reqToken++; return;
    }

    // ready → ask the engine (debounced; show a computing state immediately)
    a.classList.add("none"); a.textContent = "…";
    d.innerHTML = `<span class="muted">simulating ${SAMPLES.toLocaleString()} hands…</span>`;
    clearTimeout(statTimer);
    statTimer = setTimeout(() => fetchStats(pf), 110);
  }

  function fetchStats(pf) {
    const n = state.nPlayers, hero = state.heroPos;
    const acts = Array.from({ length: n }, (_, i) => (i < hero ? (state.actions[i] || "") : ""));
    const cards = state.cards.map((c) => c.r + c.s);
    const my = ++reqToken;
    fetch("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, hero, cards, acts, samples: SAMPLES }),
    })
      .then((r) => r.json())
      .then((res) => { if (my === reqToken) renderStats(pf, res); })
      .catch(() => { if (my === reqToken) renderNoEngine(); });
  }

  function renderNoEngine() {
    const a = $("verdictAction"), d = $("verdictDetail"), row = $("evRow");
    a.className = "verdict-action none"; a.textContent = "⚠";
    d.innerHTML = `<span class="warn">No engine. Run <code>./run.sh</code> and open <code>http://127.0.0.1:7878/</code></span>`;
    row.innerHTML = "";
  }

  function renderStats(pf, res) {
    const a = $("verdictAction"), d = $("verdictDetail"), row = $("evRow");
    a.className = "verdict-action";
    if (!res || !res.ok) { renderNoEngine(); return; }

    const kind = res.ev > res.foldev ? pf.mode : "fold";   // shove/call vs fold
    const action = pf.mode === "shove" ? "SHOVE" : "CALL";
    a.classList.add(kind);
    a.textContent = kind === "fold" ? "FOLD" : action;

    const freqPct = Math.round(res.freq * 100);
    const mixed = res.freq > 0.08 && res.freq < 0.92;
    const ctx = pf.vs ? `facing ${pf.vs}'s shove` : `open from ${POS()[state.heroPos]}`;
    let line;
    if (kind === "fold") {
      line = `${pf.lbl} · ${ctx}. Fold — ${action.toLowerCase()}ing averages ${res.ev >= 0 ? "+" : ""}${res.ev.toFixed(2)} bb (worse than folding).`;
    } else {
      line = `${pf.lbl} · ${ctx}. GTO ${action.toLowerCase()}s this `
           + (mixed ? `<b>${freqPct}%</b> of the time (mixed).` : `(pure).`);
    }
    if (pf.multi) line += ` <span class="warn">multiple all-ins — approx. vs the first shover.</span>`;
    d.innerHTML = line;

    if (pf.mode === "shove") {
      const unc = Math.round(res.foldpct), called = 100 - unc;
      row.innerHTML =
        `<div class="ev-main">
           ${evChip("EV of shove", res.ev, true)}
           ${plainChip("Wins uncontested", `${unc}%`)}
         </div>
         <div class="ev-called">
           <span class="cl-label">When called (${called}% of the time):</span>
           <div class="cl-chips">
             ${evChip("25th", res.cp25)}${evChip("Median", res.cmed)}${evChip("75th", res.cp75)}
           </div>
         </div>`;
    } else {
      row.innerHTML =
        `<div class="ev-main">${evChip("EV of call", res.ev, true)}</div>
         <div class="ev-called">
           <span class="cl-label">At showdown:</span>
           <div class="cl-chips">
             ${evChip("25th", res.cp25)}${evChip("Median", res.cmed)}${evChip("75th", res.cp75)}
           </div>
         </div>`;
    }
  }

  // -------- 52-card board --------
  function renderBoard() {
    let html = "";
    for (const r of RANKS) {
      for (const s of SUITS) {
        const order = state.cards.findIndex((c) => c.r === r && c.s === s.v) + 1;
        html += `<div class="dcard ${s.red ? "red" : ""} ${order ? "sel" : ""}"
                   data-r="${r}" data-s="${s.v}" ${order ? `data-order="${order}"` : ""}>
                   <span class="r">${r}</span><span class="s">${s.sym}</span></div>`;
      }
    }
    $("cardBoard").innerHTML = html;
  }

  function toggleCard(r, s) {
    const i = state.cards.findIndex((c) => c.r === r && c.s === s);
    if (i >= 0) state.cards.splice(i, 1);
    else { if (state.cards.length >= 2) state.cards.shift(); state.cards.push({ r, s }); }
    render();
  }

  // -------- events --------
  function wire() {
    $("playerSeg").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      setPlayers(+b.dataset.n); render();
    });

    $("rotateBtn").addEventListener("click", () => {
      const n = state.nPlayers;
      state.heroPos = (state.heroPos + n - 1) % n;
      state.actions = foldedToMe();
      render();
    });

    $("villains").addEventListener("click", (e) => {
      const btn = e.target.closest(".abtn"); if (!btn) return;
      const seat = +btn.dataset.seat;
      state.actions[seat] = state.actions[seat] === btn.dataset.act ? undefined : btn.dataset.act;
      render();
    });

    $("seat-hero").addEventListener("click", (e) => {
      const p = e.target.closest(".pcard.pick"); if (!p) return;
      const i = state.cards.findIndex((c) => c.r === p.dataset.r && c.s === p.dataset.s);
      if (i >= 0) { state.cards.splice(i, 1); render(); }
    });

    $("resetBtn").addEventListener("click", () => { state.actions = foldedToMe(); render(); });

    $("cardBoard").addEventListener("click", (e) => {
      const c = e.target.closest(".dcard"); if (!c) return;
      toggleCard(c.dataset.r, c.dataset.s);
    });

    $("clearCards").addEventListener("click", () => { state.cards = []; render(); });
  }

  setPlayers(4);
  wire();
  render();
})();
