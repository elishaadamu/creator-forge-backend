#!/usr/bin/env bash
# Creator Forge — local dev launcher
# Starts FastAPI backend (port 8000) and Vite frontend (port 3001) together.
# Usage: ./start-dev.sh

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"

# ── Create venv if missing ────────────────────────────────────────────────────
if [ ! -f "$VENV/bin/python" ]; then
  echo "🐍 Creating Python virtual environment…"
  python3 -m venv "$VENV"
fi

# ── Install Python deps if needed ─────────────────────────────────────────────
echo "📦 Installing Python dependencies…"
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"

# ── Install Node deps if needed ───────────────────────────────────────────────
if [ ! -d "$ROOT/web/node_modules" ]; then
  echo "📦 Installing Node dependencies…"
  (cd "$ROOT/web" && npm install)
fi

# ── Start backend (background) ────────────────────────────────────────────────
echo ""
echo "🚀 Starting FastAPI backend on http://localhost:8000"
"$VENV/bin/uvicorn" app.main:app --reload --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!

sleep 2

# ── Start frontend ────────────────────────────────────────────────────────────
echo "🌐 Starting Vite frontend on http://localhost:3001"
echo ""
echo "  Creator Dashboard: http://localhost:3001"
echo "  Ops Pipeline:      http://localhost:3001/ops"
echo "  API Docs:          http://localhost:8000/docs"
echo ""
(cd "$ROOT/web" && npm run dev) &
FRONTEND_PID=$!

# ── Cleanup on Ctrl+C ─────────────────────────────────────────────────────────
trap "echo ''; echo '⏹  Stopping…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" INT TERM
wait
