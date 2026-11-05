/**
 * Phase 2 · Source Clean one-action rail, driven without any media file.
 *
 * The page opens an extraction-only job through stubbed API routes: a real
 * Check report shape, a real Source Clean record shape and a tiny JPEG frame.
 * It proves the ingest-adjacent screen opens in source scope, auto-ticks only
 * high-confidence rows, scans/cleans/renders through one primary action, keeps
 * Before/After on the one frame and never asks analysis for a source job.
 *
 * Exit 0 passes, exit 2 means this host cannot run Playwright (skip).
 */

import process from "node:process";

const base = String(process.env.CLASSIC_BASE_URL || "").replace(/\/$/, "");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
if (!base) {
  console.error("SKIP: CLASSIC_BASE_URL is not set");
  process.exit(2);
}
if (!moduleUrl) {
  console.error("SKIP: PLAYWRIGHT_MODULE is not set");
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import(moduleUrl));
} catch (error) {
  console.error(`SKIP: Playwright cannot be imported: ${error?.message || error}`);
  process.exit(2);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function json(payload, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  };
}

// 1×1 JPEG. The UI only needs decodable pixels; the server route is stubbed.
const JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==";
const JPEG_BYTES = Buffer.from(JPEG_BASE64, "base64");
const JPEG_DATA = `data:image/jpeg;base64,${JPEG_BASE64}`;

const SOURCE = {
  name: "source.mp4",
  duration: 12,
  width: 1280,
  height: 720,
  fps: 30,
  has_audio: true,
  size: 2048,
};

const JOB = {
  id: "j1",
  created: 1,
  updated: 1,
  status: "source_ready",
  progress: 1,
  message: "Source ready",
  error: null,
  mode: "clean",
  source: SOURCE,
  options: {},
  analysis: null,
  renders: {},
  artifacts: {},
  artifact_ids: [],
  source_clean: {
    status: "idle",
    progress: 0,
    message: "No Source Clean render has run.",
  },
};

const SCAN = {
  status: "ready",
  complete: true,
  message: "",
  progress: 1,
  text: { confirmed: true, tracklets: 3, present: true },
  tracklets: [{ id: 1 }, { id: 2 }, { id: 3 }],
  clean_prefill: [
    {
      tracklet_id: "t1",
      kind: "subtitle",
      box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
      ranges: [{ start: 0.5, end: 4.0 }],
      action: "blur",
      enabled: true,
      confidence: 0.92,
    },
    {
      tracklet_id: "t2",
      kind: "handle_or_logo",
      box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
      ranges: [],
      action: "blur",
      enabled: true,
      confidence: 0.81,
    },
    {
      tracklet_id: "t3",
      kind: "screen_text",
      box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
      ranges: [{ start: 4.0, end: 8.0 }],
      action: "blur",
      enabled: true,
      confidence: 0.4,
    },
  ],
};

const FILL = {
  available: true,
  missing: [],
  files: [],
  engines: { lama: { id: "lama", ready: true, reason: "" } },
  default: "lama",
  preview: "lama",
  methods: ["blur", "crop", "lama"],
  note: "AI fill is ready with LaMa.",
};

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  console.error(`SKIP: Chromium did not launch: ${error?.message || error}`);
  process.exit(2);
}

async function run(viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  const analysisCalls = [];
  const renderBodies = [];
  let fillPreviewCalls = 0;
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.route(/\/api\/jobs\/j1$/, (route) => route.fulfill(json(JOB)));
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => route.fulfill(json(SCAN)));
  await page.route(/\/api\/jobs\/j1\/analyze$/, (route) => {
    analysisCalls.push(route.request().method());
    return route.fulfill(json({ ok: true, id: "j1", status: "queued", started: true }, 202));
  });
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(FILL)));

  await page.route(/\/api\/classic\/jobs\/j1\/text$/, (route) => {
    const cut = { overlays: [], effects: [], clean: [] };
    return route.fulfill(json({ cut, aspects: ["9:16", "4:5"] }));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/fill\/estimate$/, (route) =>
    route.fulfill(json({ method: "lama", estimate_seconds: 90, seconds: 90, measured: true })));
  await page.route(/\/api\/classic\/jobs\/j1\/fill\/preview$/, (route) => {
    fillPreviewCalls += 1;
    return route.fulfill(json({
      before: JPEG_DATA,
      after: JPEG_DATA,
      width: 1280,
      height: 720,
      time: 1,
      method: "lama",
      render_method: "lama",
      scope: "source",
    }));
  });

  await page.route(/\/api\/classic\/jobs\/j1\/frame\/source$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: {
        "X-VibeCut-Width": "1280",
        "X-VibeCut-Height": "720",
        "X-VibeCut-Fill": "1",
      },
      body: JPEG_BYTES,
    }));

  let statusReads = 0;
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source$/, (route) => {
    statusReads += 1;
    if (statusReads === 1) {
      return route.fulfill(json({
        status: "idle", progress: 0, message: "No Source Clean render has run.",
      }));
    }
    if (statusReads === 2) {
      return route.fulfill(json({
        status: "running",
        progress: 0.4,
        message: "Cleaning text with AI fill",
      }));
    }
    return route.fulfill(json({
      status: "ready",
      progress: 1,
      message: "Clean video ready · 1280×720 · 12.0s",
      path: "/tmp/out.mp4",
      url: "/api/classic/jobs/j1/clean/source/media?v=abc",
      width: 1280,
      height: 720,
      duration: 12,
      method: "lama",
      cached: false,
    }));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source\/render$/, (route) => {
    try { renderBodies.push(JSON.parse(route.request().postData() || "{}")); } catch (_) { renderBodies.push({}); }
    return route.fulfill(json({
      status: "queued",
      progress: 0,
      message: "Queued for Clean",
    }, 202));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source\/media/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "video/mp4",
      headers: { "content-length": "2048" },
      body: Buffer.alloc(2048, 1),
    }));

  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#clean-stage").waitFor({ state: "visible", timeout: 30000 });

  const label = `${viewport.width}×${viewport.height}`;
  await page.waitForFunction(() =>
    document.body.classList.contains("source-mode")
      && !document.querySelector("#source-clean-head").hidden
      && /Clean 2 texts/.test(document.querySelector("#source-clean-run").textContent || ""),
  null, { timeout: 20000 });
  await page.waitForFunction(() => {
    const img = document.querySelector("#clean-frame");
    return Boolean(img && (img.getAttribute("src") || "").startsWith("blob:") && img.naturalWidth > 0);
  }, null, { timeout: 30000 });

  const head = await page.evaluate(() => ({
    name: document.querySelector("#source-clean-name").textContent,
    meta: document.querySelector("#source-clean-meta").textContent,
    eyebrow: document.querySelector("#result-eyebrow").textContent,
    back: !document.querySelector("#source-back").hidden,
    actions: getComputedStyle(document.querySelector(".result-actions")).display,
    scan: getComputedStyle(document.querySelector("#text-scan")).display,
    cleanThis: getComputedStyle(document.querySelector("#clean-empty-scan-this")).display,
    rows: document.querySelectorAll("#clean-found .clean-found-row").length,
    ticks: document.querySelectorAll("#clean-found [data-found-tick]:checked").length,
    review: Boolean(document.querySelector("[data-found-review]")),
    frame: document.querySelector("#clean-frame").getAttribute("src") || "",
    ratio: document.querySelector("#clean-canvas").style.aspectRatio,
    emptyCopy: document.querySelector("#clean-empty p").textContent,
  }));
  assert(head.name === "source.mp4", `${label}: source name is ${head.name}`);
  assert(/12\.0s/.test(head.meta) && /360 frames/.test(head.meta) && /LaMa/.test(head.meta),
    `${label}: source header is ${head.meta}`);
  assert(/source/.test(head.eyebrow), `${label}: eyebrow is ${head.eyebrow}`);
  assert(head.back, `${label}: back action is hidden`);
  assert(head.actions === "none", `${label}: result actions still show`);
  assert(head.scan === "none", `${label}: the scan card still shows`);
  assert(head.cleanThis === "none", `${label}: Scan this moment still shows`);
  assert(head.rows === 3, `${label}: ${head.rows} rows`);
  assert(head.ticks === 2, `${label}: ${head.ticks} auto ticks`);
  assert(head.review, `${label}: no Review N more path`);
  assert(/Text was found/.test(head.emptyCopy),
    `${label}: the empty copy is ${head.emptyCopy}`);
  assert(head.ratio === "1280 / 720", `${label}: frame aspect is ${head.ratio}`);
  assert(head.frame.startsWith("blob:"), `${label}: the source frame is not an image`);

  await page.locator("#source-clean-run").click();
  await page.locator("#source-clean-result").waitFor({ state: "visible", timeout: 30000 });
  const result = await page.evaluate(() => ({
    output: document.querySelector("#source-clean-output").textContent,
    href: document.querySelector("#source-clean-download").getAttribute("href") || "",
    download: document.querySelector("#source-clean-download").getAttribute("download") || "",
    reel: document.querySelector("#source-clean-reel").textContent,
    actionHidden: document.querySelector("#source-clean-action").hidden,
    actionsHidden: document.querySelector("#source-clean-result-actions").hidden,
    removeTicked: Boolean(document.querySelector("[data-found-apply]")),
  }));
  assert(/1280×720/.test(result.output) && /12\.0s/.test(result.output),
    `${label}: result output is ${result.output}`);
  assert(/clean\/source\/media/.test(result.href), `${label}: download is ${result.href}`);
  assert(result.download === "source-clean.mp4", `${label}: download name is ${result.download}`);
  assert(!result.actionHidden && !result.actionsHidden,
    `${label}: the sticky result bar is hidden`);
  assert(!result.removeTicked, `${label}: source mode still shows Remove ticked`);
  const boxes = {};
  for (const selector of ["#source-clean-download", "#source-clean-reel", "#source-clean-again"]) {
    boxes[selector] = await page.locator(selector).boundingBox();
    assert(boxes[selector], `${label}: ${selector} has no box`);
    assert(boxes[selector].y + boxes[selector].height <= viewport.height,
      `${label}: ${selector} is below the fold at y=${boxes[selector].y}`);
  }
  const layerMeta = await page.evaluate(() =>
    [...document.querySelectorAll("#clean-layers .clean-row-meta")].map((node) => node.textContent));
  assert(layerMeta.some((text) => /whole video/.test(text)),
    `${label}: no source layer says whole video (${layerMeta.join(" | ")})`);
  assert(!layerMeta.some((text) => /whole cut/.test(text)),
    `${label}: a source layer still says whole cut`);
  assert(renderBodies.length === 1 && renderBodies[0].clean.length === 2,
    `${label}: the first render carried ${renderBodies[0]?.clean?.length} boxes`);

  await page.locator('[data-found-index="0"]').dblclick();
  await page.locator("#clean-detail").waitFor({ state: "visible", timeout: 10000 });
  const detailText = await page.locator("#clean-detail").textContent();
  assert(/92% confidence/.test(detailText), `${label}: the detail strip is ${detailText}`);

  // Tick change after the first clean: the next render must carry the new row,
  // not reuse the first set just because a render already happened. Space on a
  // focused checkbox must keep its native toggle and focus after the repaint.
  await page.locator('[data-found-index="1"] [data-found-tick="1"]').focus();
  await page.keyboard.press("Space");
  const keyboardTick = await page.evaluate(() => ({
    checked: document.querySelector('[data-found-index="1"] [data-found-tick="1"]')?.checked === true,
    focus: document.activeElement?.dataset?.foundTick || "",
  }));
  assert(keyboardTick.checked, `${label}: Space did not toggle the checkbox`);
  assert(keyboardTick.focus === "1", `${label}: focus moved to ${keyboardTick.focus || "nothing"}`);
  const nextRender = page.waitForRequest((request) =>
    /\/clean\/source\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#source-clean-again").click();
  const nextBody = JSON.parse((await nextRender).postData() || "{}");
  assert(nextBody.clean.length === 3,
    `${label}: the ticked row was not applied (${nextBody.clean.length} boxes)`);
  await page.waitForFunction(() => document.querySelector("#source-clean-result")?.hidden === false,
    null, { timeout: 30000 });
  assert(renderBodies.length === 2, `${label}: Clean again made ${renderBodies.length} renders`);

  const before = await page.locator("#clean-frame").getAttribute("src");
  await page.locator("#clean-preview-after").click();
  await page.waitForFunction((previous) => {
    const src = document.querySelector("#clean-frame").getAttribute("src") || "";
    return src !== previous && src.startsWith("data:image/jpeg");
  }, before, { timeout: 20000 });
  const note = await page.locator("#clean-fill-note").textContent();
  assert(/AI fill/.test(note), `${label}: the filled frame note is ${note}`);
  assert(fillPreviewCalls >= 1, `${label}: After did not use the fill preview`);
  await page.locator("#clean-preview-before").click();
  await page.waitForFunction(() => {
    const src = document.querySelector("#clean-frame").getAttribute("src") || "";
    return src.startsWith("blob:");
  }, null, { timeout: 20000 });

  await page.locator("#source-clean-reel").click();
  assert(analysisCalls.length === 1, `${label}: Make a reel did not call analyze`);
  await page.waitForFunction(() =>
    /Analysis started/.test(document.querySelector("#source-clean-output").textContent || ""),
  null, { timeout: 10000 });
  const startedNote = await page.locator("#source-clean-output").textContent();
  assert(/Analysis started\. Open the cut from Recent cuts when it finishes\./.test(startedNote),
    `${label}: the result note is ${startedNote}`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(consoleErrors.length === 0, `${label}: console errors: ${consoleErrors.join(" | ")}`);
  await context.close();
  console.log(`ok source-clean ${label}`);
}

try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }]) {
    await run(viewport);
  }
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
