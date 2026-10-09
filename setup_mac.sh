#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== Harvest Hand setup (Mac/Linux) ==="
command -v python3 >/dev/null || { echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo
echo "Setup done. Start the app with:  ./run_mac.sh"
