//! Loads engine/data/model.txt: the 169x169 heads-up equity matrix and the
//! solved Nash jam/call ranges per table size. Pure std parsing (line-based).

use std::collections::HashMap;
use std::fs;

pub const NCLASS: usize = 169;
pub const STACK: f64 = 8.0;

pub struct Table {
    pub n: usize,
    pub positions: Vec<String>,
    pub posted: Vec<f64>,                       // blinds posted per seat
    pub jam: HashMap<usize, Vec<f64>>,          // seat -> 169 jam freqs
    pub call: HashMap<(usize, usize), Vec<f64>>, // (caller q, jammer J) -> 169 freqs
}

pub struct Model {
    pub hands: Vec<String>,
    pub hand_ix: HashMap<String, usize>,
    pub weights: Vec<f64>,                      // combo counts per class
    pub eq: Vec<f64>,                           // row-major 169x169: eq[i*169+j]
    pub tables: HashMap<usize, Table>,
}

impl Model {
    pub fn equity(&self, hero: usize, opp: usize) -> f64 {
        self.eq[hero * NCLASS + opp]
    }

    pub fn load(path: &str) -> Result<Model, String> {
        let text = fs::read_to_string(path).map_err(|e| format!("read {path}: {e}"))?;
        let mut hands: Vec<String> = Vec::new();
        let mut weights: Vec<f64> = Vec::new();
        let mut eq = vec![0.0f64; NCLASS * NCLASS];
        let mut tables: HashMap<usize, Table> = HashMap::new();
        let mut cur: usize = 0; // current table n being parsed

        for line in text.lines() {
            let mut it = line.split_whitespace();
            let tag = match it.next() {
                Some(t) => t,
                None => continue,
            };
            match tag {
                "HANDS" => hands = it.map(|s| s.to_string()).collect(),
                "WEIGHTS" => weights = it.map(|s| s.parse().unwrap()).collect(),
                "EQ" => {
                    let row: usize = it.next().unwrap().parse().unwrap();
                    for (j, tok) in it.enumerate() {
                        eq[row * NCLASS + j] = tok.parse().unwrap();
                    }
                }
                "TABLE" => {
                    cur = it.next().unwrap().parse().unwrap();
                    tables.insert(cur, Table {
                        n: cur, positions: vec![], posted: vec![],
                        jam: HashMap::new(), call: HashMap::new(),
                    });
                }
                "POS" => {
                    let t = tables.get_mut(&cur).unwrap();
                    t.positions = it.next().unwrap().split(',').map(|s| s.to_string()).collect();
                }
                "POSTED" => {
                    let t = tables.get_mut(&cur).unwrap();
                    t.posted = it.map(|s| s.parse().unwrap()).collect();
                }
                "JAM" => {
                    let seat: usize = it.next().unwrap().parse().unwrap();
                    let v: Vec<f64> = it.map(|s| s.parse().unwrap()).collect();
                    tables.get_mut(&cur).unwrap().jam.insert(seat, v);
                }
                "CALL" => {
                    let q: usize = it.next().unwrap().parse().unwrap();
                    let j: usize = it.next().unwrap().parse().unwrap();
                    let v: Vec<f64> = it.map(|s| s.parse().unwrap()).collect();
                    tables.get_mut(&cur).unwrap().call.insert((q, j), v);
                }
                _ => {}
            }
        }

        if hands.len() != NCLASS || weights.len() != NCLASS {
            return Err("model.txt missing HANDS/WEIGHTS".into());
        }
        let hand_ix = hands.iter().cloned().enumerate().map(|(i, h)| (h, i)).collect();
        Ok(Model { hands, hand_ix, weights, eq, tables })
    }

    /// Map two concrete cards ("As","Kh") to a 169-class index.
    pub fn class_of(&self, c0: &str, c1: &str) -> Option<usize> {
        const ORDER: &str = "AKQJT98765432";
        let rv = |c: char| ORDER.find(c);
        let (r0, s0) = (c0.chars().next()?, c0.chars().nth(1)?);
        let (r1, s1) = (c1.chars().next()?, c1.chars().nth(1)?);
        let label = if r0 == r1 {
            format!("{r0}{r1}")
        } else {
            let (hi, lo) = if rv(r0)? < rv(r1)? { (r0, r1) } else { (r1, r0) };
            let suited = if s0 == s1 { "s" } else { "o" };
            format!("{hi}{lo}{suited}")
        };
        self.hand_ix.get(&label).copied()
    }
}
