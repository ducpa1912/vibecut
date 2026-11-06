/**
 * Phase 4 · empty confirmed Check report.
 *
 * A ready, confirmed report with no found text must offer Render cut and render
 * on the first click — from reload, from an Edit scan, and with a manual layer.
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
  return { status, contentType: "application/json", body: JSON.stringify(payload) };
}

const JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==";
const JPEG_BYTES = Buffer.from(JPEG_BASE64, "base64");

const SOURCE = {
  name: "empty-source.mp4", duration: 12, width: 1280, height: 720,
  fps: 30, has_audio: true, size: 4096,
};
const CLIP = {
  scene: 0, role: "hook", start: 2, end: 9, dur: 7,
  why: "Hook", mid: 5.5, crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const SCENE = {
  id: 0, start: 2, end: 9, dur: 7, mid: 5.5, hook: 70, score: 70,
  deep: true, visual_score: 70, motion_score: 70, audio_score: 70,
  text_score: 0, ocr: "", speech: "", tags: [], face: false,
  crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const PLAN = {
  target: 30, clips: [CLIP], total: 7, clip_count: 1, hook_scene: 0,
  auto: true, note: "One clip", source_duration: 12,
  hook_why: "Opening", payoff_why: "Ending",
  reasoning: { hook: { headline: "Opening" }, payoff: { headline: "Ending" } },
};
const JOB = {
  id: "j1", created: 1, updated: 1, status: "ready", progress: 1,
  message: "Ready", error: null, mode: "reel", source: SOURCE,
  options: {}, renders: {}, artifacts: {}, artifact_ids: [],
  analysis: {
    scene_count: 1, hook_scene: 0, deep_count: 1, elapsed: 1.2,
    engine: {}, scenes: [SCENE],
    plans: { "15": PLAN, "30": PLAN, "60": PLAN },
  },
};
const EMPTY_REPORT = {
  status: "ready", complete: true, message: "", progress: 1,
  text: { confirmed: true, tracklets: 0, present: false },
  tracklets: [], clean_prefill: [],
};
const FILL = {
  available: true, missing: [], files: [],
  engines: { lama: { id: "lama", ready: true, reason: "" } },
  default: "lama", preview: "lama", methods: ["blur", "crop", "lama"],
  note: "AI fill is ready with LaMa.",
};
const MANUAL_LAYER = {
  id: "manual1", method: "blur",
  box: { x: 0.2, y: 0.3, w: 0.4, h: 0.2 },
  ranges: [{ start: 2.5, end: 4 }],
  label: "Drawn box", kind: "manual", source: "manual",
  color: "#0b0d12", opacity: 1, radius: 24, hidden: false,
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
  const errors = [];
  const pageErrors = [];
  const renderBodies = [];
  let mode = "ready";
  let cleanRows = [];
  let renderRecord = null;
  let renderSeq = 0;
  let statusPolls = 0;

  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  await page.route(/\/api\/jobs\/j1$/, (route) => route.fulfill(json({
    ...JOB,
    renders: renderRecord ? { [renderRecord.record_key]: renderRecord } : {},
  })));
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => {
    if (route.request().method() === "POST") return route.fulfill(json(EMPTY_REPORT));
    if (mode === "idle") {
      return route.fulfill(json({
        status: "idle", report: null, complete: false, progress: 0,
        message: "No Check report yet for this cut.",
        text: { confirmed: false, present: false, tracklets: 0 },
        tracklets: [], clean_prefill: [],
      }));
    }
    return route.fulfill(json(EMPTY_REPORT));
  });
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(FILL)));
  await page.route(/\/api\/classic\/jobs\/j1\/text$/, async (route) => {
    let body = {};
    try { body = JSON.parse(route.request().postData() || "{}"); } catch (_) { /* empty */ }
    if (route.request().method() === "PUT") {
      cleanRows = (Array.isArray(body.clean) ? body.clean : []).map((row) => ({
        ...row,
        color: row.color || "#0b0d12",
        opacity: row.opacity ?? 1,
        radius: row.radius ?? 24,
      }));
    }
    return route.fulfill(json({
      cut: { overlays: [], effects: [], clean: cleanRows },
      aspects: ["9:16", "4:5"],
      source_clean_added: 0, source_clean_note: "",
    }));
  });
  await page.route(/\/api\/jobs\/j1\/render$/, (route) => {
    let body = {};
    try { body = JSON.parse(route.request().postData() || "{}"); } catch (_) { /* empty */ }
    renderBodies.push(body);
    renderSeq += 1;
    statusPolls = 0;
    const target = Number(body.target) || 30;
    renderRecord = {
      key: String(target), record_key: String(target), target, quality: "final",
      aspect: "9:16", captions: false, audio_sig: "", hook: 0,
      status: "queued", progress: 0, message: "Queued",
      width: 1080, height: 1920, duration: 7, clip_count: 1, size: 2048,
      updated: renderSeq, url: `/api/jobs/j1/media/reel_${renderSeq}.mp4`,
    };
    return route.fulfill(json({ render: renderRecord }));
  });
  await page.route(/\/api\/jobs\/j1\/status$/, (route) => {
    statusPolls += 1;
    if (renderRecord) {
      renderRecord = statusPolls < 3
        ? { ...renderRecord, status: "rendering", progress: 0.5, message: "Rendering cut" }
        : { ...renderRecord, status: "ready", progress: 1, message: "Ready", updated: renderRecord.updated + 1 };
    }
    return route.fulfill(json({
      renders: renderRecord ? { [renderRecord.record_key]: renderRecord } : {},
    }));
  });
  await page.route(/\/api\/jobs\/j1\/history/, (route) => route.fulfill(json({ entries: [] })));
  await page.route(/\/api\/jobs\/j1\/audio\/moods/, (route) => route.fulfill(json({ moods: [] })));
  await page.route(/\/api\/audio\/engines$/, (route) =>
    route.fulfill(json({ voices: {}, music: {}, translation: [] })));
  await page.route(/\/api\/jobs\/j1\/mixer/, (route) =>
    route.fulfill(json({ ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [] })));
  await page.route(/\/api\/jobs\/j1\/usage/, (route) =>
    route.fulfill(json({ total_calls: 0, items: [] })));
  await page.route(/\/api\/jobs\/j1\/media\//, (route) =>
    route.fulfill({ status: 200, contentType: "video/mp4", body: Buffer.alloc(64, 1) }));
  await page.route(/\/api\/jobs\/j1\/thumb\/0$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: JPEG_BYTES }));
  await page.route(/\/api\/classic\/jobs\/j1\/frame$/, (route) =>
    route.fulfill({
      status: 200, contentType: "image/jpeg",
      headers: { "X-VibeCut-Segment": "0", "X-VibeCut-Crop": "0,0,1,1", "X-VibeCut-Fill": "1" },
      body: JPEG_BYTES,
    }));

  const label = `${viewport.width}×${viewport.height}`;

  async function openAndRender() {
    await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
    await page.locator("#result-mode-clean").click();
    await page.waitForFunction(() =>
      /^Render cut$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
        && !document.querySelector("#cut-clean-run").hidden,
    null, { timeout: 10000 });
    const before = renderBodies.length;
    await page.locator("#cut-clean-run").click();
    await page.waitForFunction(() =>
      !document.querySelector("#cut-clean-result-actions").hidden
        && /Clean cut ready/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
    null, { timeout: 30000 });
    const ready = await page.evaluate(() => ({
      summary: document.querySelector("#cut-clean-summary")?.textContent || "",
      href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
      hidden: document.querySelector("#cut-clean-download")?.hidden,
    }));
    assert(/Clean cut ready/.test(ready.summary), `${label}: empty ready summary is ${ready.summary}`);
    assert(!ready.hidden && /media\/reel_/.test(ready.href),
      `${label}: empty ready Download is missing`);
    assert(renderBodies.length === before + 1,
      `${label}: Render cut did not issue exactly one render`);
  }

  // 1. Reload a job with a ready empty confirmed report.
  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await openAndRender();

  // Empty + no layers: Clean again renders a plain cut instead of returning.
  const firstAgain = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST",
  { timeout: 30000 });
  await page.locator("#cut-clean-again").click();
  await firstAgain;
  await page.waitForFunction(() =>
    /media\/reel_2\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && /Clean cut ready/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
  null, { timeout: 30000 });
  const noLayerNote = await page.locator("#clean-status").textContent();
  assert(/Rendering the cut without Clean boxes/.test(noLayerNote || ""),
    `${label}: empty no-layer Clean again has no honest note (${noLayerNote})`);

  // 2. Scan from Edit, then switch Clean on the empty result.
  mode = "idle";
  cleanRows = [];
  renderRecord = null;
  renderSeq = 0;
  statusPolls = 0;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#clean-scan-start").click();
  await page.waitForFunction(() =>
    /Text on screen: 0 regions/.test(document.querySelector("#clean-scan-status")?.textContent || ""),
  null, { timeout: 20000 });
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Render cut$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || ""),
  null, { timeout: 10000 });
  const beforeScanRender = renderBodies.length;
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  assert(renderBodies.length === beforeScanRender + 1,
    `${label}: the Edit-scan empty result did not render in one click`);

  // 3. Zero found rows plus a manual layer still renders from the first click.
  mode = "ready";
  cleanRows = [MANUAL_LAYER];
  renderRecord = null;
  renderSeq = 0;
  statusPolls = 0;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-layers .clean-row").length === 1,
  null, { timeout: 20000 });
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Render cut$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || ""),
  null, { timeout: 10000 });
  const beforeManualRender = renderBodies.length;
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  assert(renderBodies.length === beforeManualRender + 1,
    `${label}: manual + empty did not render in one click`);
  assert(renderBodies.at(-1).edit?.clean?.length === 1,
    `${label}: the manual layer did not ride the render`);

  // A layer change after an empty ready render is stale, not "no text found".
  await page.locator("#clean-layers [data-clean-method=\"fill\"]").first().click();
  await page.waitForFunction(() =>
    /Changed since this render/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
  null, { timeout: 20000 });
  const staleEmpty = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    download: document.querySelector("#cut-clean-download")?.textContent || "",
    className: document.querySelector("#cut-clean-download")?.className || "",
    hidden: document.querySelector("#cut-clean-download")?.hidden,
  }));
  assert(!/No baked-in text found/.test(staleEmpty.summary),
    `${label}: stale empty summary is false (${staleEmpty.summary})`);
  assert(!staleEmpty.hidden && /older/i.test(staleEmpty.download)
    && staleEmpty.className.includes("ghost"),
  `${label}: stale empty Download is not marked older`);

  // Empty + existing layer: the stale primary reuses the layer and makes a
  // second ready render.
  const layerAgain = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST",
  { timeout: 30000 });
  await page.locator("#cut-clean-run").click();
  await layerAgain;
  await page.waitForFunction(() =>
    /media\/reel_2\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && /Clean cut ready/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
  null, { timeout: 30000 });

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(errors.length === 0, `${label}: console errors: ${errors.join(" | ")}`);
  await context.close();
  console.log(`ok cut-empty ${label}`);
}

try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }]) {
    await run(viewport);
  }
} catch (error) {
  console.error(error?.stack || error?.message || error);
  process.exit(1);
} finally {
  await browser.close();
}
