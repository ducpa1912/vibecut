#!/usr/bin/env bash
# Print one lane's isolated environment. Each lane has its own port, data folder
# and media. Python, packages and models stay shared on the machine for
# development (founder's decision, see docs/classic/shared-runtime.md).
#
#   eval "$(scripts/lane-env.sh classic)"
#   python3 app.py
#
# Ports: Classic 8796, Studio 8795, Voice Room 8797. Port 8787 is the founder's
# server and must never be used by a lane.
set -euo pipefail

lane=${1:-}
case "$lane" in
  classic) port=8796; edition=classic; features="" ;;
  studio)  port=8795; edition=studio;  features="" ;;
  voice)   port=8797; edition=all;     features="voice_room" ;;
  *)
    echo "usage: $0 classic|studio|voice" >&2
    exit 2
    ;;
esac

root="${VIBECUT_LANE_ROOT:-$HOME/vibecut-lanes}"
printf 'export VIBECUT_EDITION=%s\n' "$edition"
printf 'export VIBECUT_PORT=%s\n' "$port"
printf 'export VIBECUT_DATA=%s\n' "$root/$lane"
printf 'export VIBECUT_FEATURES=%s\n' "$features"
printf 'export VIBECUT_LANE=%s\n' "$lane"
# Classic's optional model packs stay in its own folder, not the shared
# Application Support one. Whisper and Python packages are still machine-level;
# see docs/classic/shared-runtime.md.
#
# Classic's own files live in this checkout, under the gitignored data/ folder:
# test videos in data/media, recordings in data/recordings, cloned voices in
# data/voices and the music library in data/music. This copy of the script only
# speaks for Classic, so it prints these paths for Classic alone.
if [[ "$lane" == "classic" ]]; then
  checkout="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  printf 'export VIBECUT_PACKS_DIR=%s\n' "$root/$lane/packs"
  printf 'export VIBECUT_LANE_MEDIA=%s\n' "$checkout/data/media"
  printf 'export VIBECUT_LANE_RECORDINGS=%s\n' "$checkout/data/recordings"
  printf 'export VIBECUT_VOICES_DIR=%s\n' "$checkout/data/voices"
  printf 'export VIBECUT_MUSIC_DIR=%s\n' "$checkout/data/music"
  # AI fill models are shared on the machine, one read-only copy for development.
  printf 'export VIBECUT_FILL_MODELS=%s\n' "$HOME/.cache/vibecut/models/fill"
fi
