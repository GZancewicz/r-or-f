//! Live Monte-Carlo of a push/fold spot — a faithful port of the Python
//! Evaluator: sample opponents' actions/classes from the equilibrium ranges,
//! settle the all-in by the heads-up equity matrix (independent-equity for
//! multiway), and return EV, fold-out%, and the when-called percentile spread.

use crate::model::{Model, Table, NCLASS, STACK};

/// splitmix64 — tiny deterministic RNG, seeded per request.
pub struct Rng(pub u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / ((1u64 << 53) as f64)
    }
}

/// (P(player enters this range), cumulative conditional class distribution).
struct Cum { freq: f64, cum: Vec<f64> }

fn cumdist(model: &Model, prob: &[f64]) -> Cum {
    let mut mass = vec![0.0f64; NCLASS];
    let mut total = 0.0;
    let mut wsum = 0.0;
    for i in 0..NCLASS {
        mass[i] = model.weights[i] * prob[i];
        total += mass[i];
        wsum += model.weights[i];
    }
    if total <= 0.0 {
        return Cum { freq: 0.0, cum: vec![] };
    }
    let mut cum = vec![0.0f64; NCLASS];
    let mut acc = 0.0;
    for i in 0..NCLASS {
        acc += mass[i] / total;
        cum[i] = acc;
    }
    Cum { freq: total / wsum, cum }
}

fn sample_class(cum: &[f64], u: f64) -> usize {
    // searchsorted right, clipped
    match cum.binary_search_by(|x| x.partial_cmp(&u).unwrap()) {
        Ok(i) => (i + 1).min(NCLASS - 1),
        Err(i) => i.min(NCLASS - 1),
    }
}

fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() { return 0.0; }
    if sorted.len() == 1 { return sorted[0]; }
    let rank = p / 100.0 * ((sorted.len() - 1) as f64);
    let lo = rank.floor() as usize;
    let hi = rank.ceil() as usize;
    if lo == hi { sorted[lo] } else { sorted[lo] + (rank - lo as f64) * (sorted[hi] - sorted[lo]) }
}

pub struct SimOut {
    pub ev: f64,
    pub foldev: f64,        // EV of folding (= -posted) — the verdict threshold
    pub freq: f64,          // hero's equilibrium probability of the action
    pub foldpct: f64,
    pub cp25: f64,
    pub cmed: f64,
    pub cp75: f64,
    pub mode: &'static str,
    pub samples: usize,
}

/// hero_in = hero seat. opp_seats = seats (besides hero) that may be all-in.
/// `jammer` (seat, its range cum) is Some for a call spot (always in).
fn aggregate(
    model: &Model, t: &Table, hero_in: usize, hc: usize,
    opp_seats: &[usize], opp_cums: &[Cum],
    jammer: Option<(usize, &Cum)>,
    samples: usize, rng: &mut Rng,
) -> (f64, f64, f64, f64, f64) {
    let sb_i = t.n - 2;
    let bb_i = t.n - 1;
    let mut outcomes = Vec::with_capacity(samples);
    let mut called = Vec::with_capacity(samples);
    let mut foldouts = 0usize;

    for _ in 0..samples {
        // which opponents are all-in, and their classes
        let mut in_mask = vec![false; opp_seats.len()];
        let mut classes: Vec<usize> = Vec::with_capacity(opp_seats.len() + 1);
        for (r, cum) in opp_cums.iter().enumerate() {
            if cum.freq > 0.0 && rng.unit() < cum.freq {
                in_mask[r] = true;
                classes.push(sample_class(&cum.cum, rng.unit()));
            }
        }
        let mut jammer_seat = usize::MAX;
        if let Some((js, jc)) = jammer {
            jammer_seat = js;
            classes.push(sample_class(&jc.cum, rng.unit()));
        }
        let n_others = classes.len();

        // pot = stack per all-in player + forfeited (dead) blinds
        let mut pot = STACK * (n_others as f64 + 1.0);
        for &(b, amt) in &[(sb_i, t.posted[sb_i]), (bb_i, t.posted[bb_i])] {
            if b == hero_in || b == jammer_seat { continue; }       // blind already all-in
            if let Some(r) = opp_seats.iter().position(|&s| s == b) {
                if !in_mask[r] { pot += amt; }                       // that blind folded
            } else if jammer.is_some() && b < jammer_seat {
                pot += amt;                                          // folded before the jammer
            }
        }

        // hero's result this trial
        let out = if n_others == 0 {
            pot - STACK
        } else if n_others == 1 {
            model.equity(hc, classes[0]) * pot - STACK
        } else {
            let mut eqv = 1.0;
            for &c in &classes { eqv *= model.equity(hc, c); }
            eqv * pot - STACK
        };
        outcomes.push(out);
        if n_others == 0 { foldouts += 1; } else { called.push(out); }
    }

    let ev = outcomes.iter().sum::<f64>() / samples as f64;
    let foldpct = 100.0 * foldouts as f64 / samples as f64;
    called.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let (cp25, cmed, cp75) = if called.is_empty() {
        (ev, ev, ev)
    } else {
        (percentile(&called, 25.0), percentile(&called, 50.0), percentile(&called, 75.0))
    };
    (ev, foldpct, cp25, cmed, cp75)
}

/// Run a spot. `acts[i]` is "fold"|"allin"|"" for seat i (only seats before hero matter).
pub fn simulate(
    model: &Model, n: usize, hero: usize, hc: usize, acts: &[String],
    samples: usize, rng: &mut Rng,
) -> Result<SimOut, String> {
    let t = model.tables.get(&n).ok_or("unknown table size")?;
    // every seat before hero must be specified
    for i in 0..hero {
        let a = acts.get(i).map(|s| s.as_str()).unwrap_or("");
        if a != "fold" && a != "allin" {
            return Err(format!("seat {i} not specified"));
        }
    }
    let allin: Vec<usize> = (0..hero)
        .filter(|&i| acts.get(i).map(|s| s == "allin").unwrap_or(false))
        .collect();

    let foldev = -t.posted[hero];

    if allin.is_empty() {
        if hero == n - 1 {
            return Ok(SimOut { ev: t.posted[hero], foldev: 0.0, freq: 1.0, foldpct: 100.0,
                               cp25: 0.0, cmed: 0.0, cp75: 0.0, mode: "walk", samples });
        }
        // open shove from `hero`; players behind may call vs jammer = hero
        let later: Vec<usize> = ((hero + 1)..n).collect();
        let cums: Vec<Cum> = later.iter()
            .map(|&q| cumdist(model, t.call.get(&(q, hero)).map(|v| v.as_slice()).unwrap_or(&[])))
            .collect();
        let (ev, fp, c25, c50, c75) = aggregate(model, t, hero, hc, &later, &cums, None, samples, rng);
        let freq = t.jam.get(&hero).and_then(|v| v.get(hc)).copied().unwrap_or(0.0);
        return Ok(SimOut { ev, foldev, freq, foldpct: fp, cp25: c25, cmed: c50, cp75: c75, mode: "shove", samples });
    }

    // facing a shove: jammer = earliest all-in seat; hero calls
    let j = allin[0];
    let jam_range = t.jam.get(&j).ok_or("no jam range for jammer seat")?;
    let jc = cumdist(model, jam_range);
    let opp_seats: Vec<usize> = ((j + 1)..n).filter(|&s| s != hero).collect();
    let cums: Vec<Cum> = opp_seats.iter()
        .map(|&s| cumdist(model, t.call.get(&(s, j)).map(|v| v.as_slice()).unwrap_or(&[])))
        .collect();
    let (ev, fp, c25, c50, c75) = aggregate(model, t, hero, hc, &opp_seats, &cums, Some((j, &jc)), samples, rng);
    let freq = t.call.get(&(hero, j)).and_then(|v| v.get(hc)).copied().unwrap_or(0.0);
    Ok(SimOut { ev, foldev, freq, foldpct: fp, cp25: c25, cmed: c50, cp75: c75, mode: "call", samples })
}
