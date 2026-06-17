#!/usr/bin/env bash
# Build (if needed) and launch the push/fold engine + web UI.
# Open http://127.0.0.1:7878/ in your browser.
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.cargo/bin:$PATH"

# regenerate engine model data if missing
[ -f engine/data/model.txt ] || .venv/bin/python scripts/export_engine.py

# build the server if the binary is missing or sources changed
( cd engine && cargo build --release )

exec ./engine/target/release/server
