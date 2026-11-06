#!/usr/bin/env node
/**
 * Real-use acceptance for Classic Clean.
 *
 * It drives the real server and a real video file. It does not start the
 * server, does not download a model, and does not stub any route or media.
 *
 *   Terminal 1: scripts/serve-classic.sh
 *   Terminal 2:
 *     CLASSIC_REAL_VIDEO="/absolute/path/video.mp4" \
 *       node scripts/classic-real-acceptance.mjs
 *
 * Optional:
 *   CLASSIC_URL=http://127.0.0.1:8796/
 *   CLASSIC_OUT_DIR=~/vibecut-lanes/real-acceptance/run-1
 *   CLASSIC_REAL_CUT=1        # also clean the cut after the source
 *   CLASSIC_HEADLESS=1        # hide the browser
 *   CLASSIC_VIEWPORT=1280x800
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const URL_BASE = (process.env.CLASSIC_URL || "http://127.0.0.1:8796/").replace(/\/?$/, "/");
const VIDEO = process.env.CLASSIC_REAL_VIDEO ? resolve(process.env.CLASSIC_REAL_VIDEO) : "";
const OUT = resolve(
  (process.env.CLASSIC_OUT_DIR || join(homedir(), "vibecut-lanes", "real-acceptance",
    new Date().toISOString().replace(/[:.]/g, "-"))).replace(/^~(?=\/)/, homedir()),
);
const WITH_CUT = process.env.CLASSIC_REAL_CUT === "1";
const HEADLESS = process.env.CLASSIC_HEADLESS === "1";
const [vpW, vpH] = (process.env.CLASSIC_VIEWPORT || "1440x900").split("x").map(Number);

function die(message, code = 1) {
  console.error(`\nFAIL: ${message}`);
  process.exit(code);
}

function playwrightModule() {
  if (process.env.PLAYWRIGHT_MODULE) return process.env.PLAYWRIGHT_MODULE;
  const local = join(ROOT, "node_modules", "playwright", "index.mjs");
  if (existsSync(local)) return local;
  const root = join(homedir(), ".npm", "_npx");
  if (!existsSync(root)) return "";
  const found = [];
  for (const entry of readdirSync(root)) {
    const module = join(root, entry, "node_modules", "playwright", "index.mjs");
    if (!existsSync(module)) continue;
    let version = "0.0.0";
    try {
      version = JSON.parse(readFileSync(join(dirname(module), "package.json"), "utf8")).version;
    } catch (_) { /* keep the sort stable */ }
    found.push({ module, version });
  }
  found.sort((a, b) => b.version.localeCompare(a.version, undefined, { numeric: true }));
  return found[0]?.module || "";
}

function probe(file) {
  try {
    const raw = execFileSync("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration,size:stream=codec_type,width,height,r_frame_rate",
      "-of", "json", file,
    ], { encoding: "utf8" });
    return JSON.parse(raw);
  } catch (error) {
    return { error: String(error.message || error) };
  }
}

async function waitFor(check, label, timeoutMs = 30 * 60 * 1000, everyMs = 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await check()) return true;
    await new Promise((resolve) => setTimeout(resolve, everyMs));
  }
  throw new Error(`${label} did not finish in ${Math.round(timeoutMs / 1000)}s`);
}

async function clickPrimary(page, runSelector, downloadSelector, label) {
  let clicked = false;
  let clickedConfirm = false;
  const started = Date.now();
  while (Date.now() - started < 60 * 60 * 1000) {
    if (await page.locator(downloadSelector).isVisible().catch(() => false)) return;
    const run = page.locator(runSelector);
    if (await run.isVisible().catch(() => false)) {
      const text = (await run.innerText().catch(() => "")).trim();
      const enabled = await run.isEnabled().catch(() => false);
      if (/review/i.test(text)) {
        throw new Error(
          `${label}: the scan found low-confidence text and stopped for review. `
          + `Inspect the rail, tick the rows you want, then click the primary. `
          + `Screenshot: ${join(OUT, `${label}-review.png`)}`,
        );
      }
      if (!enabled && /clean \d+ text/i.test(text)) {
        throw new Error(
          `${label}: review is required. Tick at least one row in the rail, then run the command again.`,
        );
      }
      if (/scan again|rescan/i.test(text)) {
        throw new Error(
          `${label}: the scan found no usable text rows. Use a clip with baked-in text.`,
        );
      }
      if (enabled && !/finding text|cleaning|rendering|preparing|estimating/i.test(text)) {
        const wantsConfirm = /clean \d+ text/i.test(text) || /render cut/i.test(text);
        if (!clicked || (wantsConfirm && !clickedConfirm)) {
          await run.click();
          clicked = true;
          clickedConfirm = clickedConfirm || wantsConfirm;
        }
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`${label}: no Download appeared within 60 minutes`);
}

async function saveDownload(page, selector, filename) {
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 5 * 60 * 1000 }),
    page.locator(selector).click(),
  ]);
  const path = join(OUT, filename);
  await download.saveAs(path);
  return path;
}

async function main() {
  if (!VIDEO) die("Set CLASSIC_REAL_VIDEO to the real video path.", 2);
  if (!existsSync(VIDEO)) die(`Video not found: ${VIDEO}`, 2);
  const modulePath = playwrightModule();
  if (!modulePath) {
    die("Playwright not found. Run: npx -y playwright@1.65.0 install chromium", 2);
  }
  mkdirSync(OUT, { recursive: true });

  let health;
  try {
    const response = await fetch(new URL("api/health", URL_BASE));
    health = response.ok ? await response.json() : null;
  } catch (_) {
    health = null;
  }
  if (!health) {
    die(
      `Classic is not running at ${URL_BASE}. Start it in another terminal with `
      + "scripts/serve-classic.sh, then paste this command again.",
      2,
    );
  }

  const { chromium } = await import(pathToFileURL(modulePath).href);
  const browser = await chromium.launch({ headless: HEADLESS, slowMo: HEADLESS ? 0 : 60 });
  const context = await browser.newContext({
    viewport: { width: vpW || 1440, height: vpH || 900 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error.message || error)));

  const report = {
    started: new Date().toISOString(),
    url: URL_BASE,
    video: VIDEO,
    health: {
      edition: health.edition || "",
      vision: Boolean(health.capabilities?.vision),
      fill: health.capabilities?.fill ?? null,
    },
    steps: [],
  };
  const step = (name, extra = {}) => {
    report.steps.push({ name, at: new Date().toISOString(), ...extra });
    console.log(`- ${name}`);
  };

  try {
    await page.goto(URL_BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.locator("#file-input").waitFor({ state: "attached", timeout: 30000 });
    await page.locator("#file-input").setInputFiles(VIDEO);
    await page.locator("#clean-video").waitFor({ state: "visible", timeout: 30000 });
    await waitFor(
      () => page.locator("#clean-video").isEnabled(),
      "Clean video enable",
      30000,
    );
    step("video selected");
    await page.locator("#clean-video").click();
    await page.locator("#source-clean-run").waitFor({ state: "visible", timeout: 10 * 60 * 1000 });
    step("Source Clean opened");
    await page.screenshot({ path: join(OUT, "01-source-clean.png"), fullPage: false });

    await clickPrimary(page, "#source-clean-run", "#source-clean-download", "source");
    step("source clean ready");
    await page.screenshot({ path: join(OUT, "02-source-ready.png"), fullPage: false });
    const sourceFile = await saveDownload(page, "#source-clean-download", "source-clean.mp4");
    step("source clean downloaded", { file: sourceFile });
    report.source = { file: sourceFile, probe: probe(sourceFile) };

    if (WITH_CUT) {
      await page.locator("#source-clean-reel").click();
      await page.locator("#result-mode-clean").waitFor({ state: "visible", timeout: 30 * 60 * 1000 });
      await page.locator("#result-mode-clean").click();
      step("cut Clean opened");
      await page.screenshot({ path: join(OUT, "03-cut-clean.png"), fullPage: false });
      await clickPrimary(page, "#cut-clean-run", "#cut-clean-download", "cut");
      step("cut clean ready");
      await page.screenshot({ path: join(OUT, "04-cut-ready.png"), fullPage: false });
      const cutFile = await saveDownload(page, "#cut-clean-download", "cut-clean.mp4");
      step("cut clean downloaded", { file: cutFile });
      report.cut = { file: cutFile, probe: probe(cutFile) };
    }

    report.pageErrors = pageErrors;
    report.finished = new Date().toISOString();
    writeFileSync(join(OUT, "report.json"), JSON.stringify(report, null, 2));
    console.log(`\nPASS: real acceptance flow completed.\nOutput: ${OUT}`);
  } catch (error) {
    report.pageErrors = pageErrors;
    report.error = String(error.message || error);
    writeFileSync(join(OUT, "report.json"), JSON.stringify(report, null, 2));
    await page.screenshot({ path: join(OUT, "failure.png"), fullPage: false }).catch(() => {});
    console.error(`\nFAIL: ${error.message}`);
    console.error(`Report: ${join(OUT, "report.json")}`);
    process.exitCode = 1;
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`FAIL: ${error.stack || error.message || error}`);
  process.exit(1);
});
