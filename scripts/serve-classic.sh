#!/usr/bin/env bash
# Start Classic on its own port and data folder, from this checkout only.
#
#   scripts/serve-classic.sh
#
# Port 8796, data in ~/vibecut-lanes/classic. It needs nothing from another
# lane's checkout. A .venv in this checkout is used when there is one.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$(scripts/lane-env.sh classic)"
python=python3
if [[ -x .venv/bin/python ]]; then
  python=.venv/bin/python
fi
exec "$python" app.py
