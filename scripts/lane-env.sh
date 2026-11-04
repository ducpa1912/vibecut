#!/usr/bin/env bash
# Print one lane's isolated environment. Nothing here is shared with another
# lane: each lane has its own port, data, media and recordings folder, all
# under ~/vibecut-lanes (set VIBECUT_LANE_ROOT to move it).
#
#   eval "$(scripts/lane-env.sh classic)"   # or studio, voice
#   eval "$(scripts/lane-env.sh)"           # the lane of this checkout's branch
#   python3 app.py
#
# Ports: Studio 8795, Classic 8796, Voice Room 8797. Port 8787 is the founder's
# own app and is never a lane's. Studio and Classic are separate products; the
# app entrypoints carry their own defaults, while this helper remains for the
# legacy lane workflow.
set -euo pipefail

lane=${1:-}
if [[ -z "$lane" ]]; then
  case "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)" in
    studio|studio-*|vibecut-studio-*) lane=studio ;;
    classic|classic-*) lane=classic ;;
    voice-room|voice-room-*) lane=voice ;;
    *)
      echo "This checkout's branch is not a lane. Name one: classic, studio or voice." >&2
      exit 2
      ;;
  esac
fi
case "$lane" in
  studio)  port=8795; edition=studio;  features="voice_room"; folder=studio;  media=studio ;;
  classic) port=8796; edition=classic; features="";           folder=classic; media=classic ;;
  voice|voice-room)
           port=8797; edition=classic; features="voice_room"; folder=voice;   media=voiceroom; lane=voice ;;
  *)
    echo "'$lane' is not a lane. Lanes: classic, studio, voice." >&2
    exit 2
    ;;
esac

root="${VIBECUT_LANE_ROOT:-$HOME/vibecut-lanes}"
printf 'export VIBECUT_EDITION=%s\n' "$edition"
printf 'export VIBECUT_PORT=%s\n' "$port"
printf 'export VIBECUT_DATA=%s\n' "$root/$folder"
printf 'export VIBECUT_FEATURES=%s\n' "$features"
printf 'export VIBECUT_LANE=%s\n' "$lane"
printf 'export VIBECUT_LANE_MEDIA=%s\n' "$root/media/$media"
printf 'export VIBECUT_LANE_RECORDINGS=%s\n' "$root/recordings/$media"
