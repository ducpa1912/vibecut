#!/usr/bin/env bash
# Start this checkout's lane on its own port, data folder and build switches
# (scripts/lane-env.sh). Studio 8795, Classic 8796, Voice Room 8797.
#
#   scripts/serve.sh    # from the lane's worktree; Ctrl-C stops it
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
lane_vars=$(scripts/lane-env.sh) || exit 1
eval "$lane_vars"

if lsof -nP -iTCP:"$VIBECUT_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $VIBECUT_PORT is already in use:" >&2
  lsof -nP -iTCP:"$VIBECUT_PORT" -sTCP:LISTEN >&2
  echo "Stop that server first. Never start this lane on another port." >&2
  exit 1
fi

# One-time move: lanes used to keep their data in <worktree>/data. Move it to
# the lane folder when that folder is still empty, so keys and jobs carry over.
# This runs only here, with the lane's server stopped.
legacy="$PWD/data"
if [[ -d "$legacy" && -n "$(ls -A "$legacy" 2>/dev/null)" ]] \
  && [[ ! -d "$VIBECUT_DATA" || -z "$(ls -A "$VIBECUT_DATA" 2>/dev/null)" ]]; then
  echo "Moving this lane's data from $legacy to $VIBECUT_DATA (one time)."
  mkdir -p "$(dirname "$VIBECUT_DATA")"
  rmdir "$VIBECUT_DATA" 2>/dev/null || true
  mv "$legacy" "$VIBECUT_DATA"
elif [[ -d "$legacy" && -n "$(ls -A "$legacy" 2>/dev/null)" ]]; then
  echo "Note: $legacy still holds old data. This lane uses $VIBECUT_DATA." >&2
fi

mkdir -p "$VIBECUT_DATA/logs"
log="$VIBECUT_DATA/logs/server.log"
echo "Lane $VIBECUT_LANE on http://127.0.0.1:$VIBECUT_PORT"
echo "Data:  $VIBECUT_DATA"
echo "Media: $VIBECUT_LANE_MEDIA"
echo "Log:   $log"
python3 app.py 2>&1 | tee -a "$log"
