#!/usr/bin/env bash
# Start the Classic app with its own port/data defaults (classic_app.py).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec python3 classic_app.py
