#!/bin/bash
# Double-click to set up (first time) and start Harvest Hand.
cd "$(dirname "$0")"
echo "=== Harvest Hand ==="
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/ then double-click this file again."
  open "https://www.python.org/downloads/"
  read -p "Press Enter to close."; exit 1
fi
echo "Using $($PY --version)"
if [ ! -x .venv/bin/python ]; then
  echo "First-time setup: installing packages (takes a minute)..."
  "$PY" -m venv .venv || { read -p "Couldn't create the environment. Press Enter to close."; exit 1; }
  .venv/bin/python -m pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt -q || { rm -rf .venv; read -p "Package install failed. Check your internet and try again. Press Enter to close."; exit 1; }
fi
[ -f .env ] || cp .env.example .env
if lsof -i :8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Something is already running on port 8000. Opening the app..."; open http://localhost:8000; exit 0
fi
IP=$(ipconfig getifaddr en0 2>/dev/null)
echo
echo "Harvest Hand is running:  http://localhost:8000"
[ -n "$IP" ] && echo "On your phone (same Wi-Fi): http://$IP:8000"
echo "Keep this window open. Press Ctrl+C or close it to stop."
( sleep 3; open http://localhost:8000 ) &
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
