#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec "$DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --loop asyncio
