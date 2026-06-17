//! Pure-std HTTP server for the push/fold engine.
//!   GET  /                -> serves the web/ UI (same origin, no CORS issues)
//!   GET  /<file>          -> static file from web/
//!   POST /api/simulate    -> live Monte-Carlo for the posted spot

mod model;
mod sim;

use model::Model;
use sim::{simulate, Rng};

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

const MODEL_PATH: &str = "engine/data/model.txt";
const WEB_DIR: &str = "web";
const ADDR: &str = "127.0.0.1:7878";

static SEED_CTR: AtomicU64 = AtomicU64::new(0);

fn main() {
    let model = match Model::load(MODEL_PATH) {
        Ok(m) => Arc::new(m),
        Err(e) => {
            eprintln!("failed to load {MODEL_PATH}: {e}\n(run from the repo root, after `python scripts/export_engine.py`)");
            std::process::exit(1);
        }
    };
    let listener = TcpListener::bind(ADDR).unwrap_or_else(|e| {
        eprintln!("cannot bind {ADDR}: {e}");
        std::process::exit(1);
    });
    println!("push/fold engine ready → open  http://{ADDR}/");
    for stream in listener.incoming() {
        if let Ok(s) = stream {
            let m = Arc::clone(&model);
            std::thread::spawn(move || { let _ = handle(s, m); });
        }
    }
}

fn handle(stream: TcpStream, model: Arc<Model>) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut req_line = String::new();
    if reader.read_line(&mut req_line)? == 0 { return Ok(()); }
    let mut parts = req_line.split_whitespace();
    let method = parts.next().unwrap_or("").to_string();
    let path = parts.next().unwrap_or("/").to_string();

    let mut content_length = 0usize;
    loop {
        let mut h = String::new();
        if reader.read_line(&mut h)? == 0 { break; }
        if h == "\r\n" || h == "\n" { break; }
        let low = h.to_ascii_lowercase();
        if let Some(v) = low.strip_prefix("content-length:") {
            content_length = v.trim().parse().unwrap_or(0);
        }
    }
    let mut body = vec![0u8; content_length];
    if content_length > 0 { reader.read_exact(&mut body)?; }
    let body = String::from_utf8_lossy(&body).to_string();

    let mut out = stream;
    if method == "OPTIONS" {
        return write_resp(&mut out, "204 No Content", "text/plain", b"", true);
    }
    if method == "POST" && path == "/api/simulate" {
        let json = handle_simulate(&model, &body);
        return write_resp(&mut out, "200 OK", "application/json", json.as_bytes(), true);
    }
    // static
    serve_static(&mut out, &path)
}

fn handle_simulate(model: &Model, body: &str) -> String {
    let n = json_int(body, "n").unwrap_or(4) as usize;
    let hero = json_int(body, "hero").unwrap_or(0) as usize;
    let samples = (json_int(body, "samples").unwrap_or(20000) as usize).clamp(1000, 200000);
    let cards = json_str_array(body, "cards");
    let acts = json_str_array(body, "acts");

    if cards.len() < 2 {
        return r#"{"ok":false,"error":"need two cards"}"#.into();
    }
    let hc = match model.class_of(&cards[0], &cards[1]) {
        Some(i) => i,
        None => return r#"{"ok":false,"error":"bad cards"}"#.into(),
    };
    let seed = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64
        ^ SEED_CTR.fetch_add(0x9E3779B9, Ordering::Relaxed);
    let mut rng = Rng(seed | 1);

    match simulate(model, n, hero, hc, &acts, samples, &mut rng) {
        Ok(o) => format!(
            r#"{{"ok":true,"ev":{:.3},"foldev":{:.3},"freq":{:.4},"foldpct":{:.1},"cp25":{:.3},"cmed":{:.3},"cp75":{:.3},"mode":"{}","samples":{}}}"#,
            o.ev, o.foldev, o.freq, o.foldpct, o.cp25, o.cmed, o.cp75, o.mode, o.samples
        ),
        Err(e) => format!(r#"{{"ok":false,"error":"{}"}}"#, e.replace('"', "'")),
    }
}

// ---- minimal JSON readers (fixed, trusted schema) ----
fn json_int(body: &str, key: &str) -> Option<i64> {
    let pat = format!("\"{key}\"");
    let i = body.find(&pat)?;
    let after = &body[i + pat.len()..];
    let c = after.find(':')?;
    let s: String = after[c + 1..].trim_start()
        .chars().take_while(|ch| ch.is_ascii_digit() || *ch == '-').collect();
    s.parse().ok()
}

fn json_str_array(body: &str, key: &str) -> Vec<String> {
    let pat = format!("\"{key}\"");
    let Some(i) = body.find(&pat) else { return vec![] };
    let after = &body[i + pat.len()..];
    let Some(lb) = after.find('[') else { return vec![] };
    let Some(rb) = after[lb..].find(']') else { return vec![] };
    after[lb + 1..lb + rb]
        .split(',')
        .map(|t| t.trim().trim_matches('"').to_string())
        .collect()
}

// ---- static files ----
fn serve_static(out: &mut TcpStream, path: &str) -> std::io::Result<()> {
    let rel = if path == "/" { "table.html" } else { path.trim_start_matches('/') };
    if rel.contains("..") {
        return write_resp(out, "403 Forbidden", "text/plain", b"no", false);
    }
    let full = format!("{WEB_DIR}/{rel}");
    match std::fs::read(&full) {
        Ok(bytes) => write_resp(out, "200 OK", content_type(rel), &bytes, false),
        Err(_) => write_resp(out, "404 Not Found", "text/plain", b"not found", false),
    }
}

fn content_type(name: &str) -> &'static str {
    if name.ends_with(".html") { "text/html; charset=utf-8" }
    else if name.ends_with(".css") { "text/css; charset=utf-8" }
    else if name.ends_with(".js") { "application/javascript; charset=utf-8" }
    else { "text/plain; charset=utf-8" }
}

fn write_resp(out: &mut TcpStream, status: &str, ctype: &str, body: &[u8], cors: bool) -> std::io::Result<()> {
    let cors_hdr = if cors {
        "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: Content-Type\r\nAccess-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
    } else { "" };
    let head = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {}\r\n{cors_hdr}Connection: close\r\n\r\n",
        body.len()
    );
    out.write_all(head.as_bytes())?;
    out.write_all(body)?;
    out.flush()
}
