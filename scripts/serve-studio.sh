#!/usr/bin/env bash
# Start the Studio app with its own port/data defaults (studio_app.py).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec python3 studio_app.py
