#!/bin/bash
set -e

echo "Setting up Instagram Competitor Dashboard..."

cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "Starting backend on http://localhost:5050"
echo "Open frontend: file://$(dirname "$(realpath "$0")")/frontend/index.html"
echo ""
echo "Press Ctrl+C to stop."

python app.py
