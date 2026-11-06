/**
 * C0 · the Classic result screen as one frame.
 *
 * From 1000px up the result screen is a frame: compact top bar, then preview /
 * timeline / settings side by side, each scrolling on its own, the page never.
 * This spec proves that at 1280×720 and 1024×680 with a real fixture job, then
 * drives the scan card through idle → running → cancelled → ready.
 *
 * The shared Check route is stubbed here on purpose: a real 0.5 fps text pass
 * takes minutes and is covered by the Python route tests, so this spec only
 * holds the card to its own states. Exit 0 passes, exit 2 means the host cannot
 * run Playwright (skip), anything else fails.
 */

import process from "node:process";

const base = String(process.env.CLASSIC_BASE_URL || "").replace(/\/$/, "");
const jobId = String(process.env.CLASSIC_JOB_ID || "j1");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
const shotDir = process.env.CLASSIC_SHOT_DIR || "";

function skip(message) {
  console.error(`SKIP: ${message}`);
  process.exit(2);
}

if (!base) skip("CLASSIC_BASE_URL is not set");
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

function scanEnvelope(status, progress) {
  return {
    status,
    complete: false,
    message: status === "running" ? "Reading frames" : "",
    progress,
    text: { confirmed: false, tracklets: 0, present: false },
    tracklets: [],
    error: null,
  };
}

const READY_REPORT = {
  status: "ready",
  complete: true,
  message: "",
  progress: 1,
  text: { confirmed: true, tracklets: 2, present: true },
  tracklets: [{ id: 1 }, { id: 2 }],
  error: null,
};

function json(payload, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  };
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

const frames = [
  { width: 1280, height: 720 },
  { width: 1024, height: 680 },
];

async function frameMetrics(page) {
  return page.evaluate(() => {
    const panes = ["preview", "timeline", "settings"].map((name) => {
      const node = document.querySelector(`.editor-pane-${name}`);
      if (!node) return { name, missing: true };
      const box = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        name,
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        right: box.right,
        bottom: box.bottom,
        overflowY: style.overflowY,
        scrolls: node.scrollHeight > node.clientHeight + 1,
      };
    });
    const view = document.querySelector("#result-view");
    const viewBox = view ? view.getBoundingClientRect() : null;
    return {
      panes,
      viewBottom: viewBox ? viewBox.bottom : 0,
      scrollY: window.scrollY,
      innerHeight: window.innerHeight,
      innerWidth: window.innerWidth,
      docScrollHeight: document.documentElement.scrollHeight,
      bodyScrollHeight: document.body.scrollHeight,
      framed: document.body.classList.contains("editor-frame"),
      bodyOverflow: getComputedStyle(document.body).overflowY,
    };
  });
}

async function run(viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  // Stubbed Check: idle → running → cancelled, then ready on the third POST.
  let scan = "idle";
  let progress = 0.2;
  await page.route(/\/api\/jobs\/[^/]+\/check$/, async (route) => {
    if (route.request().method() === "POST") {
      if (scan === "ready") return route.fulfill(json(READY_REPORT));
      scan = "running";
      progress = 0.15;
      return route.fulfill(json(scanEnvelope("running", progress), 202));
    }
    if (scan === "idle") {
      return route.fulfill(json({
        status: "idle",
        report: null,
        complete: false,
        progress: 0,
        message: "No Check report yet for this cut.",
        text: { confirmed: false, present: false, tracklets: 0 },
        tracklets: [],
        clean_prefill: [],
      }));
    }
    if (scan === "cancelled") {
      return route.fulfill(json(scanEnvelope("cancelled", 1), 202));
    }
    if (scan === "ready") return route.fulfill(json(READY_REPORT));
    progress = Math.min(0.9, progress + 0.2);
    return route.fulfill(json(scanEnvelope("running", progress), 202));
  });
  await page.route(/\/api\/jobs\/[^/]+\/check\/cancel$/, async (route) => {
    scan = "cancelled";
    await route.fulfill(json({ ok: true, cancelled: true, status: "cancelled" }));
  });

  await page.goto(`${base}/#job=${jobId}`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator(".editor-pane-settings").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(600);

  const label = `${viewport.width}×${viewport.height}`;
  const metrics = await frameMetrics(page);
  assert(metrics.framed, `${label}: the result screen is not framed`);
  assert(metrics.bodyOverflow === "hidden", `${label}: body still scrolls`);
  assert(
    metrics.docScrollHeight <= metrics.innerHeight + 1,
    `${label}: the page scrolls (${metrics.docScrollHeight} > ${metrics.innerHeight})`,
  );
  assert(metrics.scrollY === 0, `${label}: the page is scrolled to ${metrics.scrollY}`);

  const [preview, timeline, settings] = metrics.panes;
  for (const pane of metrics.panes) {
    assert(!pane.missing, `${label}: the ${pane.name} pane is gone`);
    assert(pane.width > 200 && pane.height > 200, `${label}: ${pane.name} pane is ${pane.width}×${pane.height}`);
    assert(pane.bottom <= metrics.innerHeight + 1 || pane.scrolls,
      `${label}: ${pane.name} runs past the frame`);
    assert(pane.overflowY === "auto" || pane.overflowY === "scroll",
      `${label}: ${pane.name} does not scroll on its own (${pane.overflowY})`);
  }
  assert(preview.right <= timeline.x + 1,
    `${label}: preview and timeline overlap (${preview.right} > ${timeline.x})`);
  assert(timeline.right <= settings.x + 1,
    `${label}: timeline and settings overlap (${timeline.right} > ${settings.x})`);
  assert(metrics.panes.some((pane) => pane.scrolls),
    `${label}: nothing scrolls inside the panes, so the frame hides content`);

  // The video and the scan card must be visible together, which is the whole
  // point of the frame: the reason you scan is the picture in the preview.
  const live = await page.evaluate(() => {
    const node = (selector) => document.querySelector(selector);
    const visible = (element) => Boolean(element) && element.offsetParent !== null;
    const preview = node(".editor-pane-preview").getBoundingClientRect();
    const settings = node(".editor-pane-settings").getBoundingClientRect();
    const scan = node("#clean-scan").getBoundingClientRect();
    return {
      previewVisible: visible(node(".hook-panel")) || visible(node("#player-wrap")),
      scanInSettings: scan.x >= settings.x - 1 && scan.right <= settings.right + 1,
      scanVisible: visible(node("#clean-scan")),
      scanBottom: scan.bottom,
      previewBottom: preview.bottom,
      settingsBottom: settings.bottom,
    };
  });
  assert(live.previewVisible, `${label}: the preview column shows nothing`);
  assert(live.scanInSettings, `${label}: the scan card is not in the settings column`);
  assert(live.scanVisible, `${label}: the scan card is not visible`);

  // Idle → running.
  const status = page.locator("#clean-scan-status");
  assert(
    (await status.textContent()).includes("Not scanned yet"),
    `${label}: idle scan card does not say it has not run`,
  );
  await page.locator("#clean-scan-start").click();
  await page.waitForFunction(() => {
    const text = document.querySelector("#clean-scan-status")?.textContent || "";
    return /Scanning for text on screen/.test(text);
  }, null, { timeout: 15000 });
  assert(await page.locator("#clean-scan-cancel").isVisible(),
    `${label}: the running scan offers no Cancel`);
  assert(await page.locator("#clean-scan-start").isHidden(),
    `${label}: the running scan still offers Start`);

  // Running → cancelled.
  await page.locator("#clean-scan-cancel").click();
  await page.waitForFunction(() => {
    const text = document.querySelector("#clean-scan-status")?.textContent || "";
    return /Scan cancelled/.test(text);
  }, null, { timeout: 15000 });
  assert((await status.textContent()).includes("Scan cancelled"),
    `${label}: a cancelled scan does not say it was cancelled`);

  // Cancelled → ready, on a deliberate second start.
  scan = "ready";
  await page.locator("#clean-scan-start").click();
  await page.waitForFunction(() => {
    const text = document.querySelector("#clean-scan-status")?.textContent || "";
    return /Text on screen: 2 regions/.test(text);
  }, null, { timeout: 15000 });
  assert((await page.locator("#clean-scan-start").textContent()).trim() === "Scan again",
    `${label}: a finished scan does not offer Scan again`);

  // Focusing the scan button must not move the page under the frame.
  await page.evaluate(() => {
    document.querySelector("#clean-scan-start").focus();
    document.querySelector("#audio-panel").scrollIntoView({ block: "start" });
  });
  await page.waitForTimeout(300);
  const after = await frameMetrics(page);
  assert(after.scrollY === 0, `${label}: the page moved to ${after.scrollY} while focusing Edit`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);

  if (shotDir) {
    const { mkdir } = await import("node:fs/promises");
    await mkdir(shotDir, { recursive: true }).catch(() => {});
    await page.screenshot({ path: `${shotDir}/classic-frame-${label}.png` });
  }
  await context.close();
  console.log(`ok ${label}`);
}

try {
  for (const viewport of frames) await run(viewport);
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
