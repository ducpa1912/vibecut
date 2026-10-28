/**
 * The Voice Room page (`/voices`) in Chromium.
 *
 * Starts from one ready video in a scratch data folder, served by
 * `voice_room_server.py` with the clip search and upload cleaning faked.
 * Finds clean clips, plays one, clones from a picked clip, renames and
 * deletes the clone, and clones an uploaded recording.
 *
 * Exit 0 passes, exit 2 means the host cannot run Playwright (skip), any
 * other exit fails. The Python wrapper owns the server and its cleanup.
 */

import { readFile } from "node:fs/promises";
import process from "node:process";

const base = String(process.env.VR_BASE_URL || "").replace(/\/$/, "");
const jobId = String(process.env.VR_JOB_ID || "");
const upload = String(process.env.VR_UPLOAD || "");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
const screenshot = process.env.VR_SCREENSHOT || "";

function skip(message) {
  console.error(`SKIP: ${message}`);
  process.exit(2);
}

if (!base) skip("VR_BASE_URL is not set");
if (!moduleUrl) skip("PLAYWRIGHT_MODULE is not set");

let chromium;
try {
  ({ chromium } = await import(moduleUrl));
} catch (error) {
  skip(`Playwright cannot be imported: ${error?.message || error}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

let browser;
try {
  browser = await chromium.launch({ headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

const pageErrors = [];
const report = {};
let page;
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("dialog", (dialog) => { void dialog.accept(); });

  await page.goto(`${base}/voices`, { waitUntil: "domcontentloaded" });
  const finder = page.locator('[data-panel="clip-finder"]');
  const mine = page.locator('[data-panel="your-voices"]');
  await finder.locator('select[aria-label="Video"]').waitFor({ state: "visible", timeout: 30000 });
  report.stylesheets = await page.evaluate(
    () => [...document.styleSheets].map((sheet) => sheet.href || "").filter(Boolean),
  );

  // Find the clean clips for the video.
  await finder.locator('select[aria-label="Video"]').selectOption(jobId);
  await finder.getByRole("button", { name: "Find clean clips" }).click();
  await finder.locator("[data-clip]").first().waitFor({ state: "visible", timeout: 30000 });
  report.clips = await finder.locator("[data-clip]").count();
  assert(report.clips === 3, `expected 3 clips, saw ${report.clips}`);

  // Play a clip: its button turns into Stop while it plays.
  const second = finder.locator('[data-clip="2"]');
  await second.getByRole("button", { name: "Play clip 2" }).click();
  await second.getByRole("button", { name: "Stop clip 2" }).waitFor({ timeout: 10000 });
  await second.getByRole("button", { name: "Stop clip 2" }).click();

  // Pick it, confirm consent, clone.
  await second.getByRole("button", { name: "Use this clip" }).click();
  const cloneButton = finder.getByRole("button", { name: "Clone this clip" });
  assert(await cloneButton.isDisabled(), "Clone is enabled before consent");
  await finder.locator("#vr-consent-video").check();
  await cloneButton.click();
  const row = mine.locator("[data-voice]").first();
  await row.waitFor({ state: "visible", timeout: 30000 });
  report.cloned = (await row.locator("strong").textContent()) || "";
  assert(/voice/i.test(report.cloned), `unexpected clone name ${report.cloned}`);
  report.notice = (await page.locator(".vr-notice").textContent()) || "";
  assert(report.notice.includes("clip 2"), `notice does not name the clip: ${report.notice}`);

  // Rename it.
  await row.getByRole("button", { name: /^Rename / }).click();
  const input = mine.locator("[data-voice] input").first();
  await input.fill("Founder test voice");
  await input.press("Enter");
  await mine.getByText("Founder test voice").waitFor({ timeout: 10000 });

  // Clone an uploaded recording.
  const panel = page.locator('[data-panel="my-voice"]');
  await panel.locator('input[type="file"]').setInputFiles({
    name: "me.wav", mimeType: "audio/wav", buffer: await readFile(upload),
  });
  await panel.locator("#st-voice-consent-me").check();
  await panel.getByRole("button", { name: "Clone my voice" }).click();
  await page.waitForFunction(
    () => document.querySelectorAll('[data-panel="your-voices"] [data-voice]').length === 2,
    null, { timeout: 30000 },
  );

  // Delete the renamed clone.
  const renamed = mine.locator("[data-voice]", { hasText: "Founder test voice" });
  await renamed.getByRole("button", { name: /^Delete / }).click();
  await page.waitForFunction(
    () => !document.querySelector('[data-panel="your-voices"]')?.textContent?.includes("Founder test voice"),
    null, { timeout: 15000 },
  );
  report.left = await mine.locator("[data-voice]").count();
  assert(report.left === 1, `expected 1 clone left, saw ${report.left}`);

  assert(pageErrors.length === 0, `page errors: ${pageErrors.join(" | ")}`);
  console.log(JSON.stringify(report));
} catch (error) {
  if (screenshot) {
    try {
      await page?.screenshot({ path: screenshot, fullPage: true });
    } catch (_) {
      // The screenshot is diagnostic only.
    }
  }
  console.error(error?.stack || String(error));
  process.exitCode = 1;
} finally {
  await browser.close();
}
