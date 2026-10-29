#!/usr/bin/env bash
# Print one lane's isolated environment. Nothing here is shared with another
# lane: each lane has its own port, data folder and media folder.
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
  voice)   port=8797; edition=classic; features="voice_room"; folder=voice; media=voiceroom ;;
  *)
    echo "usage: $0 classic|studio|voice" >&2
    exit 2
    ;;
esac

root="${VIBECUT_LANE_ROOT:-$HOME/vibecut-lanes}"
printf 'export VIBECUT_EDITION=%s\n' "$edition"
printf 'export VIBECUT_PORT=%s\n' "$port"
printf 'export VIBECUT_DATA=%s\n' "$root/${folder:-$lane}"
printf 'export VIBECUT_FEATURES=%s\n' "$features"
printf 'export VIBECUT_LANE=%s\n' "$lane"
printf 'export VIBECUT_LANE_MEDIA=%s\n' "$root/media/${media:-$lane}"
