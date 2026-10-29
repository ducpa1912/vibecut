#!/usr/bin/env bash
# Record the founder's real Voice Room flow, with a Playwright trace.
#
#   scripts/voice-record.sh
#
# Start scripts/voice-serve.sh first. The browser opens on
# http://127.0.0.1:8797/voices. Click the real flow. When you are done, close
# the browser or press Ctrl-C here; the trace is saved under
# ~/vibecut-lanes/recordings/voiceroom/<date-time>/trace.zip.
#
# The trace stays on this Mac and out of the repo.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
eval "$(scripts/lane-env.sh voice)"

if ! curl -fsS "http://127.0.0.1:$VIBECUT_PORT/api/health" >/dev/null 2>&1; then
  echo "The Voice Room is not running on port $VIBECUT_PORT. Run scripts/voice-serve.sh first." >&2
  exit 1
fi

out="${VIBECUT_RECORDINGS:-$HOME/vibecut-lanes/recordings/voiceroom}/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$out"
echo "Recording Voice Room into $out"
echo "Close the browser when the flow is finished."

VOICE_TRACE_DIR="$out" VOICE_URL="http://127.0.0.1:$VIBECUT_PORT/voices" \
node --input-type=module - <<'NODE'
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const out = process.env.VOICE_TRACE_DIR;
const url = process.env.VOICE_URL;
const trace = path.join(out, "trace.zip");
const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
const page = await context.newPage();
await page.goto(url, { waitUntil: "domcontentloaded" });
fs.writeFileSync(path.join(out, "flow.txt"), `URL: ${url}\nStarted: ${new Date().toISOString()}\n`);

let stopping = false;
async function stop(reason) {
  if (stopping) return;
  stopping = true;
  try {
    await context.tracing.stop({ path: trace });
    console.log(`Saved ${trace}`);
  } catch (error) {
    console.error(`Could not save the trace: ${error?.message || error}`);
  }
  try { await browser.close(); } catch (_) {}
  fs.appendFileSync(path.join(out, "flow.txt"), `Stopped: ${new Date().toISOString()} (${reason})\n`);
  process.exit(0);
}

browser.on("disconnected", () => stop("browser closed"));
process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop("SIGTERM"));
await new Promise(() => {});
NODE
