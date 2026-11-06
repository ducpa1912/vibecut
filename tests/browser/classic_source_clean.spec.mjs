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

// A ready cut for the same source. The source record below is what the real
// server would have saved under the full-source clip.
const CUT_CLIP = {
  scene: 0, role: "hook", start: 2, end: 9, dur: 7,
  why: "Hook: a strong opening.", mid: 5.5,
  crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const CUT_SCENE = {
  id: 0, start: 2, end: 9, dur: 7, mid: 5.5, hook: 70, score: 70,
  deep: true, visual_score: 70, motion_score: 70, audio_score: 70,
  text_score: 0, ocr: "", speech: "", tags: [], face: false,
  crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const PLAN = {
  target: 30, clips: [CUT_CLIP], total: 7, clip_count: 1,
  hook_scene: 0, auto: true, note: "One clip", source_duration: 12,
  hook_why: "Opening", payoff_why: "Ending",
  reasoning: {
    hook: { headline: "Opening" },
    payoff: { headline: "Ending" },
  },
};
const READY_JOB = {
  ...JOB,
  status: "ready",
  progress: 1,
  message: "Ready",
  analysis: {
    scene_count: 1, hook_scene: 0, deep_count: 1, elapsed: 1.2,
    engine: {}, scenes: [CUT_SCENE],
    plans: { "15": PLAN, "30": PLAN, "60": PLAN },
  },
};
const SOURCE_CLIP = { scene: 0, start: 0, end: 12, dur: 12, role: "source" };

// Deterministic already-mapped cut rows for the carry stub. Mapping itself is
// covered by tests/test_classic_clean_carry.py; this stub only drives the UI.
const CARRY_ROWS = [
  {
    id: "cl01", method: "blur",
    box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
    ranges: [{ start: 2, end: 6 }],
    label: "Burned-in subtitle", kind: "subtitle", source: "scan",
    tracklet_id: "t1", text_key: "same words", hidden: false,
    opacity: 1, radius: 24, z: 0, color: "#0b0d12",
  },
  {
    id: "cl02", method: "blur",
    box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
    ranges: [{ start: 0, end: 7 }],
    label: "Handle or logo", kind: "handle_or_logo", source: "scan",
    tracklet_id: "t2", text_key: "mark", hidden: false,
    opacity: 1, radius: 24, z: 1, color: "#0b0d12",
  },
];

// Only the identity token is mirrored here, so the stub can apply the same
// delete/restore rule the backend uses. The source->cut mapping is not mirrored.
function identityToken(layer) {
  const tracklet = String(layer?.tracklet_id || "").trim();
  if (tracklet) return JSON.stringify(["tracklet", tracklet]);
  const box = layer?.box || {};
  const rect = ["x", "y", "w", "h"].map((axis) => (
    Math.round((Number(box[axis]) || 0) * 10000) / 10000
  ));
  return JSON.stringify(["text_key", String(layer?.text_key || ""), rect]);
}


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
  let analysisStarted = false;
  let analysisPolls = 0;
  let analysisDone = false;
  let cutSeeded = false;
  let cutRows = [];
  let sourceRows = [];
  let durableDeleted = new Set();
  let terminalStatus = "";
  let terminalError = "";
  let immediateReady = false;
  let slowSourceSave = false;
  let textOrder = [];
  const cutPuts = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.route(/\/api\/jobs\/j1$/, (route) => {
    if (!analysisStarted) return route.fulfill(json(JOB));
    if (immediateReady) return route.fulfill(json(READY_JOB));
    if (terminalStatus) {
      return route.fulfill(json({
        ...JOB,
        status: terminalStatus,
        error: terminalError || null,
        message: terminalStatus === "cancelled" ? "Cancelled" : "Stopped",
      }));
    }
    if (!analysisDone) {
      analysisPolls += 1;
      if (analysisPolls < 2) {
        return route.fulfill(json({
          ...JOB,
          status: "reading",
          progress: 0.4,
          message: "Reading the video",
        }));
      }
      analysisDone = true;
    }
    return route.fulfill(json(READY_JOB));
  });
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => route.fulfill(json(SCAN)));
  await page.route(/\/api\/jobs\/j1\/analyze$/, (route) => {
    analysisCalls.push(route.request().method());
    analysisStarted = true;
    const status = immediateReady ? "ready" : "queued";
    return route.fulfill(json({ ok: true, id: "j1", status, started: true }, 202));
  });
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(FILL)));
  await page.route(/\/api\/jobs\/j1\/history/, (route) =>
    route.fulfill(json({ entries: [] })));
  await page.route(/\/api\/jobs\/j1\/audio\/moods/, (route) =>
    route.fulfill(json({ moods: [] })));
  await page.route(/\/api\/jobs\/j1\/mixer/, (route) =>
    route.fulfill(json({
      ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [],
    })));
  await page.route(/\/api\/jobs\/j1\/thumb\/0$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: JPEG_BYTES }));
  await page.route(/\/api\/classic\/jobs\/j1\/frame$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: { "X-VibeCut-Width": "608", "X-VibeCut-Height": "1080" },
      body: JPEG_BYTES,
    }));

  await page.route(/\/api\/classic\/jobs\/j1\/text$/, async (route) => {
    let body = {};
    try { body = JSON.parse(route.request().postData() || "{}"); } catch (_) { /* empty */ }
    const clips = Array.isArray(body.clips) ? body.clips : [];
    const isSource = clips.length === 1 && clips[0]?.role === "source";
    if (route.request().method() === "PUT") {
      if (isSource) {
        textOrder.push("source-put-start");
        if (slowSourceSave) await new Promise((resolve) => setTimeout(resolve, 120));
        sourceRows = Array.isArray(body.clean) ? body.clean : [];
        textOrder.push("source-put-done");
      } else {
        const incoming = Array.isArray(body.clean) ? body.clean : [];
        const previous = cutRows;
        for (const id of Array.isArray(body.source_clean_deleted)
          ? body.source_clean_deleted : []) {
          const row = previous.find((item) => item.id === id)
            || incoming.find((item) => item.id === id);
          if (row) durableDeleted.add(identityToken(row));
        }
        if (body.source_clean_restore === true) {
          for (const row of incoming) durableDeleted.delete(identityToken(row));
          cutRows = incoming;
        } else {
          cutRows = incoming.filter((row) => !durableDeleted.has(identityToken(row)));
        }
        cutSeeded = true;
        cutPuts.push({
          clean: cutRows.map((row) => row.id),
          deleted: Array.isArray(body.source_clean_deleted)
            ? body.source_clean_deleted : [],
          restore: body.source_clean_restore === true,
        });
      }
      return route.fulfill(json({
        cut: {
          overlays: [], effects: [], clean: isSource ? sourceRows : cutRows,
          source_clean_seeded: !isSource,
          source_clean_deleted: [...durableDeleted],
        },
        aspects: ["9:16", "4:5"],
      }));
    }
    if (isSource) {
      textOrder.push("source-lookup");
      return route.fulfill(json({
        cut: { overlays: [], effects: [], clean: sourceRows, source_clean_seeded: false },
        aspects: ["9:16", "4:5"],
        source_clean_added: 0,
        source_clean_note: "",
      }));
    }
    textOrder.push("cut-lookup-start");
    let added = 0;
    if (!cutSeeded) {
      cutRows = CARRY_ROWS.map((row) => JSON.parse(JSON.stringify(row)));
      cutSeeded = true;
      added = cutRows.length;
    }
    return route.fulfill(json({
      cut: {
        overlays: [], effects: [], clean: cutRows,
        source_clean_seeded: true,
        source_clean_deleted: [...durableDeleted],
      },
      aspects: ["9:16", "4:5"],
      source_clean_added: added,
      source_clean_note: "",
    }));
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
    legacyScan: document.querySelector("#text-scan") === null,
    scanBlock: getComputedStyle(document.querySelector("#clean-scan")).display,
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
  assert(head.legacyScan, `${label}: the removed scan card is still in the page`);
  assert(head.scanBlock === "none", `${label}: the scan block still shows in source mode`);
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
  await page.locator('[data-found-index="1"] [data-found-tick]').focus();
  await page.keyboard.press("Space");
  const keyboardTick = await page.evaluate(() => ({
    checked: document.querySelector('[data-found-index="1"] [data-found-tick]')?.checked === true,
    focus: document.activeElement?.dataset?.foundTick || "",
  }));
  assert(keyboardTick.checked, `${label}: Space did not toggle the checkbox`);
  assert(Boolean(keyboardTick.focus), `${label}: focus moved to ${keyboardTick.focus || "nothing"}`);
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
  const expectedRows = CARRY_ROWS.length;
  // The handoff polls the job and opens the cut itself; it must not send the
  // founder to Recent cuts or leave them on the source screen.
  await page.waitForFunction((count) =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === count,
  expectedRows, { timeout: 30000 });
  assert(analysisPolls >= 2, `${label}: the handoff did not poll the job`);
  assert(await page.evaluate(() => location.hash) === "#job=j1",
    `${label}: the cut URL hash changed`);
  const seeded = await page.evaluate(() => ({
    rows: document.querySelectorAll("#clean-layers .clean-row").length,
    status: document.querySelector("#clean-status").textContent || "",
  }));
  assert(seeded.rows === expectedRows, `${label}: the cut has ${seeded.rows} rows`);
  assert(/Source Clean layers added/.test(seeded.status),
    `${label}: the seeded note is ${seeded.status}`);

  // Editing a cut row saves only the cut. The source lookup still returns the
  // original source-space rows.
  const readSourceRows = () => page.evaluate(async (clip) => {
    const response = await fetch("/api/classic/jobs/j1/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips: [clip] }),
    });
    return (await response.json()).cut.clean;
  }, SOURCE_CLIP);
  const sourceBefore = await readSourceRows();
  const saved = page.waitForRequest((request) =>
    /\/api\/classic\/jobs\/j1\/text$/.test(request.url())
      && request.method() === "PUT");
  await page.locator('[data-clean-eye="cl01"]').click();
  await saved;
  const sourceAfter = await readSourceRows();
  assert(JSON.stringify(sourceAfter) === JSON.stringify(sourceBefore),
    `${label}: editing the cut changed the source clean record`);

  // Reload the cut. The marker stops a second copy, so the rows stay few.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction((count) =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === count,
  expectedRows, { timeout: 30000 });
  const reloaded = await page.evaluate(() => ({
    rows: document.querySelectorAll("#clean-layers .clean-row").length,
    status: document.querySelector("#clean-status").textContent || "",
    off: document.querySelectorAll("#clean-layers .clean-row.is-off").length,
  }));
  assert(reloaded.rows === expectedRows,
    `${label}: reload duplicated the source rows (${reloaded.rows})`);
  assert(!/Source Clean layers added/.test(reloaded.status),
    `${label}: the seeded note appeared again on reload (${reloaded.status})`);
  assert(reloaded.off === 1, `${label}: the edited row did not stay excluded`);
  const hiddenCheck = await page.evaluate(() => {
    const node = document.querySelector(
      '#clean-found input[data-found-tick][disabled]',
    );
    return node ? node.getAttribute("aria-label") || "" : "";
  });
  assert(/^Excluded:/.test(hiddenCheck),
    `${label}: a hidden carried row says ${hiddenCheck || "nothing"}`);

  // Delete a carried row, make a normal edit (no restore), then undo both.
  // The undo of the delete must send the explicit restore flag and survive a
  // reload. The normal edit must never send it.
  await page.locator('[data-clean-delete="cl01"]').click();
  await page.waitForTimeout(500);
  assert(cutPuts.at(-1)?.deleted.includes("cl01")
    && cutPuts.at(-1)?.restore === false,
  `${label}: the delete PUT is ${JSON.stringify(cutPuts.at(-1))}`);

  await page.locator('[data-clean-eye="cl02"]').click();
  await page.waitForTimeout(500);
  assert(cutPuts.at(-1)?.restore === false,
    `${label}: a normal edit sent the restore flag`);

  await page.locator("#clean-undo").click();
  await page.waitForTimeout(500);
  assert(cutPuts.at(-1)?.restore === false,
    `${label}: undoing a normal edit sent the restore flag`);
  await page.locator("#clean-undo").click();
  await page.waitForTimeout(500);
  assert(cutPuts.at(-1)?.restore === true
    && cutPuts.at(-1)?.clean.includes("cl01"),
  `${label}: undoing a delete did not restore (${JSON.stringify(cutPuts.at(-1))})`);

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction((count) =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === count,
  expectedRows, { timeout: 30000 });
  const restored = await page.evaluate(() => ({
    ids: [...document.querySelectorAll("#clean-layers .clean-row")]
      .map((node) => node.dataset.cleanRow),
  }));
  assert(restored.ids.includes("cl01"),
    `${label}: the undone row did not survive reload (${restored.ids})`);

  // Durable across a reload: delete, reload, then re-add the same text. The
  // browser only knows the delete token from the cut lookup payload.
  await page.locator('[data-clean-delete="cl01"]').click();
  await page.waitForTimeout(500);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === 1,
  null, { timeout: 30000 });
  await page.locator('[data-found-index="0"] [data-found-tick]').check();
  await page.locator("[data-found-apply]").click();
  await page.waitForTimeout(500);
  assert(cutPuts.at(-1)?.restore === true,
    `${label}: a reloaded re-add sent restore=false (${JSON.stringify(cutPuts.at(-1))})`);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === 2,
  null, { timeout: 30000 });
  const readded = await page.evaluate(() => ({
    labels: [...document.querySelectorAll("#clean-layers .clean-row-label")]
      .map((node) => node.textContent),
  }));
  assert(readded.labels.some((text) => /subtitle/i.test(text)),
    `${label}: the re-added row did not survive reload (${readded.labels})`);

  // A stale tab has the old row but no local delete. It must send no restore
  // flag, and the stub (like the server) keeps it deleted.
  const oldClean = await page.evaluate(async (clip) => {
    const response = await fetch("/api/classic/jobs/j1/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips: [clip] }),
    });
    return (await response.json()).cut.clean;
  }, CUT_CLIP);
  const target = oldClean.find((row) => row.tracklet_id === "t1");
  assert(target, `${label}: the re-added row has no t1 identity`);
  await page.locator(`[data-clean-delete="${target.id}"]`).click();
  await page.waitForTimeout(500);
  await page.evaluate(async ({ clip, clean }) => {
    await fetch("/api/classic/jobs/j1/text", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips: [clip], clean, overlays: [], effects: [] }),
    });
  }, { clip: CUT_CLIP, clean: oldClean });
  assert(cutPuts.at(-1)?.restore === false,
    `${label}: a stale tab sent the restore flag`);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() =>
    !document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-layers .clean-row").length === 1,
  null, { timeout: 30000 });
  const stale = await page.evaluate(() => ({
    labels: [...document.querySelectorAll("#clean-layers .clean-row-label")]
      .map((node) => node.textContent),
  }));
  assert(!stale.labels.some((text) => /subtitle/i.test(text)),
    `${label}: the stale tab restored a deleted row (${stale.labels})`);

  async function backToSource(status = "", error = "") {
    terminalStatus = status;
    terminalError = error;
    analysisStarted = false;
    analysisDone = false;
    immediateReady = false;
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() =>
      document.body.classList.contains("source-mode")
        && !document.querySelector("#source-clean-result-actions").hidden,
    null, { timeout: 30000 });
  }

  // Every terminal status stops the poll and gives the button back.
  for (const [status, copy] of [
    ["cancelled", "Analysis was cancelled."],
    ["interrupted", "Analysis was interrupted."],
  ]) {
    await backToSource(status, `${status} by the operator`);
    if (status === "cancelled") {
      const cleaned = await page.evaluate(() => {
        const node = document.querySelector(
          '#clean-found input[data-found-tick][disabled]',
        );
        return node ? {
          disabled: node.disabled,
          label: node.getAttribute("aria-label") || "",
        } : null;
      });
      assert(cleaned && cleaned.disabled && /Already cleaned/.test(cleaned.label),
        `${label}: an applied found row is still an active checkbox`);
    }
    await page.locator("#source-clean-reel").click();
    await page.waitForFunction(() =>
      /Retry analysis/.test(document.querySelector("#source-clean-reel").textContent || "")
        && !document.querySelector("#source-clean-reel").disabled,
    null, { timeout: 15000 });
    const stopped = await page.evaluate(() => ({
      output: document.querySelector("#source-clean-output").textContent || "",
      title: document.querySelector("#source-clean-reel").title || "",
    }));
    assert(stopped.output.includes(copy),
      `${label}: ${status} note is ${stopped.output}`);
    assert(!stopped.output.includes(`${status} by the operator`),
      `${label}: ${status} detail leaked into the note`);
    assert(stopped.title === "",
      `${label}: ${status} detail leaked into the visible title`);
  }

  // A failure says a plain sentence; the raw engine/path detail stays out of
  // the note and in the title. It must not leave the poll running.
  await backToSource("failed", "/Users/founder/secret/model.onnx missing");
  await page.locator("#source-clean-reel").click();
  await page.waitForFunction(() =>
    /Retry analysis/.test(document.querySelector("#source-clean-reel").textContent || "")
      && !document.querySelector("#source-clean-reel").disabled,
  null, { timeout: 15000 });
  const failed = await page.evaluate(() => ({
    output: document.querySelector("#source-clean-output").textContent || "",
    title: document.querySelector("#source-clean-reel").title || "",
  }));
  assert(failed.output.includes("Analysis stopped before it could build the cut."),
    `${label}: failure note is ${failed.output}`);
  assert(!failed.output.includes("/Users/founder"),
    `${label}: failure note leaked the raw error (${failed.output})`);
  assert(failed.title === "",
    `${label}: the raw error leaked into the visible title`);

  // Leaving source mode with a save in flight must finish that source PUT
  // before the cut lookup runs.
  await backToSource();
  analysisStarted = false;
  analysisDone = false;
  terminalStatus = "";
  terminalError = "";
  immediateReady = true;
  slowSourceSave = true;
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-layers .clean-row").length > 0,
  null, { timeout: 15000 });
  textOrder = [];
  assert(await page.locator("#clean-layers [data-clean-eye]").count() > 0,
    `${label}: no source Clean row to edit`);
  await page.evaluate(() => {
    document.querySelector("#clean-layers [data-clean-eye]")?.click();
    document.querySelector("#source-clean-reel").click();
  });
  await page.waitForFunction(() =>
    !document.body.classList.contains("source-mode"),
  null, { timeout: 30000 });
  const putDone = textOrder.indexOf("source-put-done");
  const cutStart = textOrder.indexOf("cut-lookup-start");
  assert(putDone >= 0, `${label}: the pending source save never ran`);
  assert(cutStart > putDone,
    `${label}: the cut lookup ran before the source save (${textOrder.join(" | ")})`);

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
