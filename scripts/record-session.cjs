// The recording behind scripts/record.sh. It saves the trace in pieces, so closing
// the browser or a long session loses at most the last piece.
const { chromium } = require("playwright");
const path = require("path");

const PIECE_MS = 5 * 60 * 1000;

function piecePath(out, index) {
  return path.join(out, `trace-${String(index).padStart(3, "0")}.zip`);
}

async function record({ out, url, headless = false, pieceMs = PIECE_MS }) {
  const browser = await chromium.launch({
    headless,
    args: ["--start-maximized"],
  });
  const context = await browser.newContext({
    viewport: null,
    // No bodies: a video session would hold every byte in memory. The trace has them.
    recordHar: { path: path.join(out, "network.har"), content: "omit" },
  });
  // Closing the app's last tab would shut the browser before the save can run.
  const keeper = await context.newPage();
  await keeper.setContent("<title>Keep this tab open</title><p>The recording needs this tab until it says Saved.</p>");
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await context.tracing.startChunk();
  const page = await context.newPage();
  await page.goto(url);

  let piece = 0;
  let saving = false;
  let finish;
  const done = new Promise((resolve) => { finish = resolve; });

  async function savePiece() {
    piece += 1;
    await context.tracing.stopChunk({ path: piecePath(out, piece) });
  }

  const timer = setInterval(async () => {
    if (saving) return;
    saving = true;
    try {
      await savePiece();
      await context.tracing.startChunk();
      console.log(`Saved piece ${piece}.`);
    } catch (error) {
      console.error(`Piece ${piece} was not saved: ${error.message}`);
    }
    saving = false;
  }, pieceMs);

  async function save() {
    clearInterval(timer);
    while (saving) await new Promise((resolve) => setTimeout(resolve, 100));
    saving = true;
    console.log("Saving trace and session…");
    try {
      await savePiece();
    } catch (error) {
      console.error(`The last piece was not saved: ${error.message}`);
    }
    try {
      await context.storageState({ path: path.join(out, "storage.json") });
    } catch (error) {
      console.error(`Storage was not saved: ${error.message}`);
    }
    try { await context.close(); } catch (_) { /* already closed */ }
    try { await browser.close(); } catch (_) { /* already closed */ }
    console.log(`Saved ${out}`);
    finish(piece);
  }

  page.on("close", () => {
    console.log("Page closed. Saving the trace…");
    void save();
  });
  browser.on("disconnected", () => {
    if (saving) return;
    saving = true;
    clearInterval(timer);
    console.error(`The browser closed first. Pieces 1 to ${piece} are saved in ${out}`);
    finish(piece);
  });
  return { browser, context, page, save, done };
}

module.exports = { record };

if (require.main === module) {
  record({ out: process.env.RECORD_OUT, url: process.env.RECORD_URL })
    .then(async ({ save, done }) => {
      console.log("Browser open. Do the flow, then press Ctrl-C in this terminal, or close the app tab.");
      process.on("SIGINT", () => { void save(); });
      process.on("SIGTERM", () => { void save(); });
      await done;
      process.exit(0);
    })
    .catch((error) => {
      console.error(error);
      process.exit(1);
    });
}
