#!/usr/bin/env bash
# Print one lane's isolated environment. Nothing here is shared with another
# lane: each lane has its own port, data folder and media folder. The Voice Room
# keeps everything in this worktree's git-ignored data/ folder.
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
  voice)   port=8797; edition=voice; features="voice_room" ;;
  *)
    echo "usage: $0 classic|studio|voice" >&2
    exit 2
    ;;
esac

root="${VIBECUT_LANE_ROOT:-$HOME/vibecut-lanes}"
if [[ "$lane" == voice ]]; then
  worktree="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  data="${VIBECUT_LANE_ROOT:-$worktree}/data"
  printf 'export VIBECUT_EDITION=%s\n' "$edition"
  printf 'export VIBECUT_PORT=%s\n' "$port"
  printf 'export VIBECUT_DATA=%s\n' "$data"
  printf 'export VIBECUT_FEATURES=%s\n' "$features"
  printf 'export VIBECUT_LANE=%s\n' "$lane"
  printf 'export VIBECUT_LANE_MEDIA=%s\n' "$data/media"
  printf 'export VIBECUT_RECORDINGS=%s\n' "$data/recordings"
  exit 0
fi
printf 'export VIBECUT_EDITION=%s\n' "$edition"
printf 'export VIBECUT_PORT=%s\n' "$port"
printf 'export VIBECUT_DATA=%s\n' "$root/$lane"
printf 'export VIBECUT_FEATURES=%s\n' "$features"
printf 'export VIBECUT_LANE=%s\n' "$lane"
printf 'export VIBECUT_LANE_MEDIA=%s\n' "$root/media/$lane"
