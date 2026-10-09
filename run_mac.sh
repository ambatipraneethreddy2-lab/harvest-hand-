#!/bin/bash
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run ./setup_mac.sh first."; exit 1; }
source .venv/bin/activate
echo "Harvest Hand is running at http://localhost:8000   (press Ctrl+C to stop)"
( sleep 2; open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null ) &
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
