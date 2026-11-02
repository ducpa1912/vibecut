#!/bin/zsh
# Double-click in Finder to record a Voice Room pass with Playwright.
# Start the Voice Room server first with "Voice Room Server.command".
# This opens VibeCut Voice. Finish with the floating button, close the browser,
# or press Ctrl-C; wait for "Saved ..." before closing anything.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
PORT=8797
if ! curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "The Voice Room is not running on port $PORT."
  echo "Start scripts/Voice Room Server.command first."
  read -r "?Press Return to close."
  exit 1
fi
export VOICE_PATH='/voices'
exec scripts/voice-record.sh
