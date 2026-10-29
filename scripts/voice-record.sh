#!/usr/bin/env bash
# Record the founder's real Voice Room flow, with a Playwright trace.
#
#   scripts/voice-record.sh
#
# Start scripts/voice-serve.sh first. The browser opens on
# http://127.0.0.1:8797/voices. Click the real flow, then press the floating
# "Finish recording" button. The trace is saved under
# ~/vibecut-lanes/recordings/voiceroom/<date-time>/trace.zip.
#
# The trace stays on this Mac and out of the repo. Do not close the browser
# window before pressing Finish recording; Playwright cannot save a trace after
# the browser is gone.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
eval "$(scripts/lane-env.sh voice)"

if ! curl -fsS "http://127.0.0.1:$VIBECUT_PORT/api/health" >/dev/null 2>&1; then
  echo "The Voice Room is not running on port $VIBECUT_PORT. Run scripts/voice-serve.sh first." >&2
  exit 1
fi

module="${PLAYWRIGHT_MODULE:-}"
if [[ -z "$module" ]]; then
  module=$(for pkg in "$HOME"/.npm/_npx/*/node_modules/playwright/package.json; do
    [[ -f "$pkg" ]] || continue
    version=$(node -p "require('$pkg').version" 2>/dev/null || true)
    [[ -n "$version" ]] && printf '%s\t%s\n' "$version" "${pkg%/package.json}/index.mjs"
  done | sort -V | tail -1 | cut -f2-)
fi
if [[ -z "$module" || ! -f "$module" ]]; then
  echo "Playwright is not installed. Install it with 'npx playwright install chromium'." >&2
  exit 1
fi

out="${VIBECUT_RECORDINGS:-$HOME/vibecut-lanes/recordings/voiceroom}/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$out"
echo "Recording Voice Room into $out"
echo "Press the floating 'Finish recording' button when the flow is finished."

VOICE_TRACE_DIR="$out" VOICE_URL="http://127.0.0.1:$VIBECUT_PORT/voices" \
VOICE_PLAYWRIGHT_MODULE="file://$module" \
node --input-type=module - <<'NODE'
import fs from "node:fs";
import path from "node:path";

const out = process.env.VOICE_TRACE_DIR;
const url = process.env.VOICE_URL;
const moduleUrl = process.env.VOICE_PLAYWRIGHT_MODULE;
const { chromium } = await import(moduleUrl);
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

await page.exposeFunction("__voiceTraceDone", () => stop("finish button"));
await page.evaluate(() => {
  const button = document.createElement("button");
  button.textContent = "Finish recording";
  button.setAttribute("data-voice-trace-finish", "1");
  Object.assign(button.style, {
    position: "fixed", right: "18px", top: "18px", zIndex: "2147483647",
    padding: "12px 18px", border: "0", borderRadius: "999px",
    background: "#f97316", color: "#111", font: "600 15px system-ui, sans-serif",
    boxShadow: "0 8px 24px rgba(0,0,0,.35)", cursor: "pointer",
  });
  button.addEventListener("click", () => window.__voiceTraceDone());
  document.body.append(button);
});

process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop("SIGTERM"));
await new Promise(() => {});
NODE
