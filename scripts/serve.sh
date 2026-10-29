#!/usr/bin/env bash
# Start this lane's server on its own port, with its own data folder and build
# switches. Studio 8795, Classic 8796, Voice Room 8797 (docs/branching.md).
#
#   scripts/serve.sh    # from the lane's worktree; Ctrl-C stops it
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source scripts/lane.sh
lane_env "$(git rev-parse --abbrev-ref HEAD)"

if lsof -nP -iTCP:"$LANE_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $LANE_PORT is already in use:" >&2
  lsof -nP -iTCP:"$LANE_PORT" -sTCP:LISTEN >&2
  echo "Stop that server first. Never start this lane on another port." >&2
  exit 1
fi

mkdir -p "$LANE_DATA" "$LANE_NOTES"
echo "Lane $LANE on http://127.0.0.1:$LANE_PORT (data: $LANE_DATA)"
echo "Log: $LANE_NOTES/server.log"
VIBECUT_PORT="$LANE_PORT" \
VIBECUT_DATA="$LANE_DATA" \
VIBECUT_EDITION="$LANE_EDITION" \
VIBECUT_FEATURES="$LANE_FEATURES" \
  python3 app.py 2>&1 | tee -a "$LANE_NOTES/server.log"
