#!/usr/bin/env bash
# The founder records a test run of this lane with real files. Start the lane
# with scripts/serve.sh first. Recordings go to ~/vibecut-lanes/recordings/
# <lane>/<date-time>/ and stay on this Mac, outside the repo, because they hold
# frames and media from the founder's videos.
#
#   scripts/record.sh        # press Ctrl-C here, or close the app tab, to save
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
lane_vars=$(scripts/lane-env.sh) || exit 1
eval "$lane_vars"

if ! curl -sf "http://127.0.0.1:$VIBECUT_PORT/api/health" >/dev/null 2>&1; then
  echo "Lane $VIBECUT_LANE is not on http://127.0.0.1:$VIBECUT_PORT. Run scripts/serve.sh first." >&2
  exit 1
fi
page="http://127.0.0.1:$VIBECUT_PORT/"
if [[ "$VIBECUT_LANE" == "voice" ]]; then
  page="${page}voices"
fi

out="$VIBECUT_LANE_RECORDINGS/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$out"

pw_pkg=$(find "$HOME/.npm/_npx" -path '*/node_modules/playwright/package.json' -print 2>/dev/null | sort | tail -1)
if [[ -z "$pw_pkg" ]]; then
  echo "Playwright is not in the npx cache. Run: npx playwright --version" >&2
  exit 1
fi
NODE_PATH=$(dirname "$(dirname "$pw_pkg")")
export NODE_PATH RECORD_OUT="$out" RECORD_URL="$page"

echo "Recording lane $VIBECUT_LANE into $out"
echo "Do the flow in the browser. Then press Ctrl-C here, or close the app tab."
echo "It saves a piece every five minutes. Leave the 'Keep this tab open' tab, and wait for 'Saved …'."
node scripts/record-session.cjs
