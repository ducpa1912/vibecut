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
echo "Wait until this terminal prints 'Saved …' before closing anything else."
node <<'NODE'
const { chromium } = require("playwright");

const out = process.env.RECORD_OUT;
const url = process.env.RECORD_URL;

(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ["--start-maximized", "--keep-alive-for-test"],
  });
  const context = await browser.newContext({
    viewport: null,
    recordHar: { path: `${out}/network.har`, content: "embed" },
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = await context.newPage();
  await page.goto(url);
  console.log("Browser open. Do the flow, then press Ctrl-C in this terminal.");

  let saving = false;
  async function save() {
    if (saving) return;
    saving = true;
    console.log("Saving trace and session…");
    try {
      await context.tracing.stop({ path: `${out}/trace.zip` });
    } catch (error) {
      console.error(`Trace was not saved: ${error.message}`);
    }
    try {
      await context.storageState({ path: `${out}/storage.json` });
    } catch (error) {
      console.error(`Storage was not saved: ${error.message}`);
    }
    try { await context.close(); } catch (_) { /* already closed */ }
    try { await browser.close(); } catch (_) { /* already closed */ }
    console.log(`Saved ${out}`);
    process.exit(0);
  }

  process.on("SIGINT", save);
  process.on("SIGTERM", save);
  page.on("close", () => {
    console.log("Page closed. Saving the trace…");
    void save();
  });
  await new Promise(() => {});
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
NODE
