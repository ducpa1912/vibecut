#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
fi

if ! "$PY" -c "import fastapi, uvicorn, numpy, PIL, multipart" >/dev/null 2>&1; then
  echo "Installing Python dependencies…"
  "$PY" -m pip install -r requirements.txt
fi

exec "$PY" app.py
