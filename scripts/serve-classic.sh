#!/usr/bin/env bash
# Start Classic on its own port and data folder, from this checkout only.
#
#   scripts/serve-classic.sh
#
# Port 8796, jobs and settings in ~/vibecut-lanes/classic, media, voices and
# music in this checkout's data/ folder. It needs nothing from another lane's
# checkout. A .venv in this checkout is used when there is one.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$(scripts/lane-env.sh classic)"
mkdir -p "$VIBECUT_LANE_MEDIA" "$VIBECUT_LANE_RECORDINGS" "$VIBECUT_VOICES_DIR" "$VIBECUT_MUSIC_DIR"
python=python3
if [[ -x .venv/bin/python ]]; then
  python=.venv/bin/python
fi
exec "$python" app.py
