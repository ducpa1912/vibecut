/**
 * Phase 4 · stable Clean tick identities.
 *
 * Scan ticks are keyed by row identity, not array position. Adding a manual
 * box must not move a high tick, and manual choices must survive reload. A new
 * scan report clears old choices and re-ticks the high rows.
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

const JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==";
const JPEG_BYTES = Buffer.from(JPEG_BASE64, "base64");

const SOURCE = {
  name: "tick-source.mp4", duration: 12, width: 1280, height: 720,
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

function report(highConfidence) {
  return {
    status: "ready", complete: true, message: "", progress: 1,
    text: { confirmed: true, tracklets: 3, present: true },
    tracklets: [{ id: 1 }, { id: 2 }, { id: 3 }],
    clean_prefill: [
      {
        tracklet_id: "hello", kind: "subtitle",
        box: { x: 0.1, y: 0.6, w: 0.8, h: 0.12 },
        ranges: [{ start: 4, end: 5 }], action: "blur", enabled: true,
        confidence: highConfidence, text: "HELLO WORLD", text_key: "hello world",
      },
      {
        tracklet_id: "low", kind: "screen_text",
        box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
        ranges: [{ start: 3, end: 4 }], action: "blur", enabled: true,
        confidence: 0.4, text: "LOW ROW", text_key: "low row",
      },
      {
        tracklet_id: "outside", kind: "handle_or_logo",
        box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
        ranges: [{ start: 10, end: 12 }], action: "blur", enabled: true,
        confidence: 0.95, text: "OUTSIDE HIGH", text_key: "outside high",
      },
    ],
  };
}

const FILL = {
  available: true, missing: [], files: [],
  engines: { lama: { id: "lama", ready: true, reason: "" } },
  default: "lama", preview: "lama", methods: ["blur", "crop", "lama"],
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
  const errors = [];
  const pageErrors = [];
  let newReport = false;
  let cleanRows = [];

  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  await page.route(/\/api\/jobs\/j1$/, (route) => route.fulfill(json(JOB)));
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill(json(report(newReport ? 0.96 : 0.95)));
    }
    return route.fulfill(json(report(newReport ? 0.96 : 0.95)));
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
  await page.route(/\/api\/jobs\/j1\/history/, (route) => route.fulfill(json({ entries: [] })));
  await page.route(/\/api\/jobs\/j1\/audio\/moods/, (route) => route.fulfill(json({ moods: [] })));
  await page.route(/\/api\/audio\/engines$/, (route) =>
    route.fulfill(json({ voices: {}, music: {}, translation: [] })));
  await page.route(/\/api\/jobs\/j1\/mixer/, (route) =>
    route.fulfill(json({ ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [] })));
  await page.route(/\/api\/jobs\/j1\/usage/, (route) =>
    route.fulfill(json({ total_calls: 0, items: [] })));
  await page.route(/\/api\/jobs\/j1\/thumb\/0$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: JPEG_BYTES }));
  await page.route(/\/api\/classic\/jobs\/j1\/frame$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: { "X-VibeCut-Segment": "0", "X-VibeCut-Crop": "0,0,1,1", "X-VibeCut-Fill": "1" },
      body: JPEG_BYTES,
    }));

  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 3,
  null, { timeout: 30000 });

  const label = `${viewport.width}×${viewport.height}`;
  const rowFor = (text) => page.locator("#clean-found .clean-found-row", { hasText: text });
  const tickFor = (text) => rowFor(text).locator("[data-found-tick]");
  const checked = (text) => tickFor(text).isChecked();
  const rowCount = () => page.locator("#clean-found .clean-found-row").count();

  assert(await checked("HELLO WORLD"), `${label}: high row was not auto-ticked`);
  assert(!(await checked("LOW ROW")), `${label}: low row was auto-ticked`);
  assert(!(await checked("OUTSIDE HIGH")), `${label}: outside row was auto-ticked`);

  await tickFor("LOW ROW").check();
  await page.locator("#clean-draw").click();
  const canvas = await page.locator("#clean-canvas").boundingBox();
  await page.mouse.move(canvas.x + canvas.width * 0.2, canvas.y + canvas.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(canvas.x + canvas.width * 0.5, canvas.y + canvas.height * 0.45, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(() => document.querySelectorAll("#clean-found .clean-found-row").length === 4,
    null, { timeout: 10000 });
  assert(await checked("HELLO WORLD"), `${label}: high tick moved after adding a manual row`);
  assert(await checked("LOW ROW"), `${label}: low tick did not survive the manual row`);
  assert(await page.locator("#clean-found .clean-found-row").filter({ hasText: "Drawn box" })
    .locator("[data-found-tick]").count() === 0,
  `${label}: the manual row gained a scan checkbox`);

  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Clean 2 texts & render$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || ""),
  null, { timeout: 10000 });
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));

  await page.waitForTimeout(800);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll("#clean-found .clean-found-row").length === 4,
    null, { timeout: 30000 });
  assert(await checked("HELLO WORLD"), `${label}: high tick did not survive reload`);
  assert(await checked("LOW ROW"), `${label}: low tick did not survive reload`);
  assert(!(await checked("OUTSIDE HIGH")), `${label}: outside row was ticked after reload`);
  assert(await rowCount() === 4, `${label}: reload lost the manual row`);

  newReport = true;
  await page.locator("#clean-scan-start").click();
  await page.waitForFunction(() => {
    const row = [...document.querySelectorAll("#clean-found .clean-found-row")]
      .find((node) => node.textContent.includes("HELLO WORLD"));
    return row?.querySelector("[data-found-tick]")?.checked === true
      && [...document.querySelectorAll("#clean-found .clean-found-row")]
        .find((node) => node.textContent.includes("LOW ROW"))
        ?.querySelector("[data-found-tick]")?.checked === false;
  }, null, { timeout: 20000 });
  assert(!(await checked("LOW ROW")), `${label}: old low choice survived a new report`);
  assert(!(await checked("OUTSIDE HIGH")), `${label}: outside row was ticked by the new report`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(errors.length === 0, `${label}: console errors: ${errors.join(" | ")}`);

  await context.close();
  console.log(`ok cut-ticks ${label}`);
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
