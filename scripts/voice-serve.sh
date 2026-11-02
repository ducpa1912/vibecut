#!/usr/bin/env bash
# Start the Voice Room lane on its own port and data folder.
#
#   scripts/voice-serve.sh    # Ctrl-C stops it
#
# Port 8797, data ~/vibecut-lanes/voice, media ~/vibecut-lanes/media/voiceroom.
# Never port 8787 and never the founder's data.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
eval "$(scripts/lane-env.sh voice)"

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "voice-room" ]]; then
  echo "This starts the Voice Room lane only; this checkout is on '$(git rev-parse --abbrev-ref HEAD)'." >&2
  exit 1
fi
if lsof -nP -iTCP:"$VIBECUT_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $VIBECUT_PORT is already in use:" >&2
  lsof -nP -iTCP:"$VIBECUT_PORT" -sTCP:LISTEN >&2
  echo "Stop that process first. Do not use another lane's port." >&2
  exit 1
fi

mkdir -p "$VIBECUT_DATA" "$VIBECUT_DATA/logs"
log="$VIBECUT_DATA/logs/server.log"
pidfile="$VIBECUT_DATA/server.pid"
echo "VibeCut Voice: http://127.0.0.1:$VIBECUT_PORT/"
echo "Data:       $VIBECUT_DATA"
echo "Media:      $VIBECUT_LANE_MEDIA"
echo "Log:        $log"

# Finder's Terminal does not activate the project venv, so use it when present.
python_bin="${VIBECUT_PYTHON:-$PWD/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3)"
fi

VIBECUT_PORT="$VIBECUT_PORT" \
VIBECUT_DATA="$VIBECUT_DATA" \
VIBECUT_EDITION="$VIBECUT_EDITION" \
VIBECUT_FEATURES="$VIBECUT_FEATURES" \
  "$python_bin" app.py >>"$log" 2>&1 &
pid=$!
echo "$pid" >"$pidfile"
cleanup() {
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -f "$pidfile"
}
trap cleanup INT TERM EXIT
wait "$pid"
