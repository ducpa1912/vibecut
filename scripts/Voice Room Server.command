#!/bin/zsh
# Double-click in Finder to start the Voice Room server.
# The Terminal window stays open; press Ctrl-C or close it to stop.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
exec scripts/voice-serve.sh
