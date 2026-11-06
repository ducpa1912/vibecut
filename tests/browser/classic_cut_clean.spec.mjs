/**
 * Phase 4 · Cut Clean focus mode, driven without real media.
 *
 * One ready cut on stubbed routes. The spec proves Edit | Clean hides the Edit
 * columns without dropping their state, one scan entry feeds one primary
 * action, high-confidence rows inside the cut tick by default, outside rows do
 * not move, Before sends no Clean layers, After sends them, and the finished
 * render reuses the normal render record for Download.
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

const JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==";
const JPEG_BYTES = Buffer.from(JPEG_BASE64, "base64");
const JPEG_DATA = `data:image/jpeg;base64,${JPEG_BASE64}`;

const SOURCE = {
  name: "cut-source.mp4",
  duration: 12,
  width: 1280,
  height: 720,
  fps: 30,
  has_audio: true,
  size: 4096,
};

const CLIP = {
  scene: 0, role: "hook", start: 2, end: 9, dur: 7,
  why: "Hook: a strong opening.", mid: 5.5,
  crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const SCENE = {
  id: 0, start: 2, end: 9, dur: 7, mid: 5.5, hook: 70, score: 70,
  deep: true, visual_score: 70, motion_score: 70, audio_score: 70,
  text_score: 0, ocr: "", speech: "", tags: [], face: false,
  crop: { cx: 0.5, cy: 0.5 }, crop_mode: "center",
};
const PLAN = {
  target: 30, clips: [CLIP], total: 7, clip_count: 1,
  hook_scene: 0, auto: true, note: "One clip", source_duration: 12,
  hook_why: "Opening", payoff_why: "Ending",
  reasoning: { hook: { headline: "Opening" }, payoff: { headline: "Ending" } },
};

const READY_JOB = {
  id: "j1", created: 1, updated: 1, status: "ready", progress: 1,
  message: "Ready", error: null, mode: "reel", source: SOURCE,
  options: {}, renders: {}, artifacts: {}, artifact_ids: [],
  analysis: {
    scene_count: 1, hook_scene: 0, deep_count: 1, elapsed: 1.2,
    engine: {},
    scenes: [SCENE],
    plans: { "15": { ...PLAN, target: 15 }, "30": PLAN, "60": { ...PLAN, target: 60 } },
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
      tracklet_id: "t1", kind: "subtitle",
      box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
      ranges: [{ start: 3, end: 5 }],
      action: "blur", enabled: true, confidence: 0.92,
      text: "inside words", text_key: "inside words",
    },
    {
      tracklet_id: "t2", kind: "screen_text",
      box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
      ranges: [{ start: 6, end: 7.5 }],
      action: "blur", enabled: true, confidence: 0.4,
      text: "low row", text_key: "low row",
    },
    {
      tracklet_id: "t3", kind: "handle_or_logo",
      box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
      ranges: [{ start: 10, end: 12 }],
      action: "blur", enabled: true, confidence: 0.88,
      text: "outside words", text_key: "outside words",
    },
  ],
};

const PLAN15 = {
  ...PLAN,
  target: 15,
  clips: [{ ...CLIP, end: 5, dur: 3 }],
  total: 3,
  clip_count: 1,
};

const TARGET_JOB = {
  ...READY_JOB,
  analysis: {
    ...READY_JOB.analysis,
    plans: { "15": PLAN15, "30": PLAN, "60": PLAN },
  },
};

const TARGET_SCAN = {
  status: "ready",
  complete: true,
  message: "",
  progress: 1,
  text: { confirmed: true, tracklets: 3, present: true },
  tracklets: [{ id: 1 }, { id: 2 }, { id: 3 }],
  clean_prefill: [
    {
      tracklet_id: "hello", kind: "subtitle",
      box: { x: 0.1, y: 0.6, w: 0.8, h: 0.12 },
      ranges: [{ start: 4, end: 5 }], action: "blur", enabled: true,
      confidence: 0.95, text: "HELLO WORLD", text_key: "hello world",
    },
    {
      tracklet_id: "low", kind: "screen_text",
      box: { x: 0.2, y: 0.2, w: 0.4, h: 0.1 },
      ranges: [{ start: 3, end: 4 }], action: "blur", enabled: true,
      confidence: 0.4, text: "low row", text_key: "low row",
    },
    {
      tracklet_id: "outside", kind: "handle_or_logo",
      box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
      ranges: [{ start: 10, end: 12 }], action: "blur", enabled: true,
      confidence: 0.95, text: "outside high", text_key: "outside high",
    },
  ],
};
const FILL = {
  available: true,
  missing: [],
  files: [],
  engines: {
    lama: { id: "lama", ready: true, reason: "" },
    migan: { id: "migan", ready: false, reason: "AI fill with MI-GAN is missing migan_traced.pt." },
    telea: { id: "telea", ready: true, reason: "" },
    ns: { id: "ns", ready: false, reason: "AI fill with NS needs the cv2 package on this Mac." },
  },
  render_options: {
    gpu: { lama: { ready: true, reason: "" }, migan: { ready: false, reason: "needs migan_traced.pt" } },
    follow: { ready: true, reason: "" },
  },
  default: "lama",
  preview: "lama",
  methods: ["blur", "crop", "lama"],
  note: "AI fill is ready with LaMa.",
};

const LONG_FILL = {
  available: false,
  missing: ["lama"],
  files: [],
  engines: {
    lama: {
      id: "lama",
      ready: false,
      reason: "models/ai-fill/lama/lama_fp32.onnx is missing from this install (very long nested model pack path for wrapping).",
    },
  },
  default: "lama",
  preview: "lama",
  methods: ["blur", "crop"],
  note: "AI fill is not ready: /Users/founder/Library/Application Support/VibeCut/models/ai-fill/lama/lama_fp32.onnx is missing from this install.",
};

// Same rows as SCAN, all high-confidence. The drawn-layer review fixture uses
// this so a manual layer cannot be mistaken for an applied scan layer.
const HIGH_SCAN = {
  ...SCAN,
  clean_prefill: SCAN.clean_prefill.map((row) => ({ ...row, confidence: 0.9 })),
};

// Four high-confidence rows inside the cut and one unticked low row. This is
// the big-picture B1 fixture.
const B1_SCAN = {
  status: "ready",
  complete: true,
  message: "",
  progress: 1,
  text: { confirmed: true, tracklets: 5, present: true },
  tracklets: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }],
  clean_prefill: [
    ["b1", "subtitle", 2.5, 3.5, 0.95, "high one"],
    ["b2", "subtitle", 3.5, 4.5, 0.95, "high two"],
    ["b3", "subtitle", 4.5, 5.5, 0.95, "high three"],
    ["b4", "subtitle", 5.5, 6.5, 0.95, "high four"],
    ["b5", "subtitle", 6.5, 7.5, 0.40, "low five"],
  ].map(([id, kind, start, end, confidence, text], index) => ({
    tracklet_id: id,
    kind,
    box: { x: 0.1, y: 0.2 + index * 0.1, w: 0.7, h: 0.08 },
    ranges: [{ start, end }],
    action: "blur",
    enabled: true,
    confidence,
    text,
    text_key: text,
  })),
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
  const textPuts = [];
  const renderBodies = [];
  const frameBodies = [];
  const fillPreviewBodies = [];
  const scanStatuses = [];

  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  let scanStarted = false;
  let scanPolls = 0;
  let cleanRows = [];
  let renderRecord = null;
  let statusPolls = 0;
  let renderSeq = 0;
  let cancelRequests = 0;
  let allHighScan = false;
  let b1Scan = false;
  let targetScan = false;
  let fillUnavailable = false;
  let releaseFill;
  const fillGate = new Promise((resolve) => { releaseFill = resolve; });

  // This spec drives the one-click flow. Review first has its own tests.
  await page.route(/\/api\/settings$/, (route) => route.fulfill(json({
    settings: { classic_clean: { flow: "one_click" } },
  })));
  await page.route(/\/api\/jobs\/j1$/, (route) => route.fulfill(json({
    ...(targetScan ? TARGET_JOB : READY_JOB),
    renders: renderRecord ? { [renderRecord.record_key]: renderRecord } : {},
  })));
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => {
    if (route.request().method() === "POST") {
      scanStarted = true;
      scanPolls = 0;
      scanStatuses.push("posted");
      return route.fulfill(json({
        status: "queued", complete: false, progress: 0,
        message: "Scan queued", text: { confirmed: false, tracklets: 0 },
        tracklets: [], clean_prefill: [],
      }, 202));
    }
    scanStatuses.push("get");
    if (!scanStarted) {
      return route.fulfill(json({
        status: "idle", report: null, complete: false, progress: 0,
        message: "No Check report yet.", text: { confirmed: false, tracklets: 0 },
        tracklets: [], clean_prefill: [],
      }));
    }
    scanPolls += 1;
    if (scanPolls === 1) {
      return route.fulfill(json({
        status: "running", complete: false, progress: 0.45,
        message: "Reading frames", text: { confirmed: false, tracklets: 0 },
        tracklets: [], clean_prefill: [],
      }));
    }
    return route.fulfill(json(
      targetScan
        ? TARGET_SCAN
        : (b1Scan ? B1_SCAN : (allHighScan ? HIGH_SCAN : SCAN)),
    ));
  });
  await page.route(/\/api\/jobs\/j1\/check\/cancel$/, (route) =>
    route.fulfill(json({ status: "cancelled", message: "Cancelled" })));
  await page.route(/\/api\/classic\/fill$/, async (route) => {
    await fillGate;
    return route.fulfill(json(fillUnavailable ? LONG_FILL : FILL));
  });
  await page.route(/\/api\/jobs\/j1\/history/, (route) =>
    route.fulfill(json({ entries: [] })));
  await page.route(/\/api\/jobs\/j1\/audio\/moods/, (route) =>
    route.fulfill(json({ moods: [] })));
  await page.route(/\/api\/audio\/engines$/, (route) =>
    route.fulfill(json({ voices: {}, music: {}, translation: [] })));
  await page.route(/\/api\/jobs\/j1\/mixer/, (route) =>
    route.fulfill(json({
      ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [],
    })));
  await page.route(/\/api\/jobs\/j1\/thumb\/0$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: JPEG_BYTES }));
  await page.route(/\/api\/classic\/jobs\/j1\/text$/, async (route) => {
    let body = {};
    try { body = JSON.parse(route.request().postData() || "{}"); } catch (_) { /* empty */ }
    if (route.request().method() === "PUT") {
      textPuts.push(body);
      // Mirror routes_classic.normalize_classic_clean: the server fills the
      // Clean defaults before it saves the row.
      cleanRows = (Array.isArray(body.clean) ? body.clean : []).map((row) => ({
        ...row,
        color: row.color || "#0b0d12",
        opacity: row.opacity ?? 1,
        radius: row.radius ?? 24,
      }));
      return route.fulfill(json({
        cut: { overlays: [], effects: [], clean: cleanRows },
        aspects: ["9:16", "4:5"],
      }));
    }
    return route.fulfill(json({
      cut: { overlays: [], effects: [], clean: cleanRows },
      aspects: ["9:16", "4:5"],
      source_clean_added: 0,
      source_clean_note: "",
    }));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/frame$/, (route) => {
    try { frameBodies.push(JSON.parse(route.request().postData() || "{}")); } catch (_) { frameBodies.push({}); }
    return route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: {
        "X-VibeCut-Segment": "0",
        "X-VibeCut-Crop": "0,0,1,1",
        "X-VibeCut-Fill": "1",
      },
      body: JPEG_BYTES,
    });
  });
  await page.route(/\/api\/classic\/jobs\/j1\/fill\/preview$/, (route) => {
    try { fillPreviewBodies.push(JSON.parse(route.request().postData() || "{}")); } catch (_) { fillPreviewBodies.push({}); }
    return route.fulfill(json({
      before: JPEG_DATA, after: JPEG_DATA, width: 608, height: 1080,
      time: 1, method: "lama", render_method: "lama", scope: "cut",
    }));
  });
  await page.route(/\/api\/jobs\/j1\/render$/, (route) => {
    let body = {};
    try { body = JSON.parse(route.request().postData() || "{}"); } catch (_) { /* empty */ }
    renderBodies.push(body);
    renderSeq += 1;
    statusPolls = 0;
    const target = Number(body.target) || 15;
    renderRecord = {
      key: String(target), record_key: String(target), target, quality: "final", aspect: "9:16",
      captions: false, audio_sig: "", hook: 0, status: "queued", progress: 0,
      message: "Queued", width: 1080, height: 1920, duration: 7, clip_count: 1,
      size: 2048, updated: renderSeq,
      url: `/api/jobs/j1/media/reel_15_${renderSeq}.mp4`,
    };
    return route.fulfill(json({ render: renderRecord }));
  });
  await page.route(/\/api\/jobs\/j1\/render\/.*\/cancel/, (route) => {
    cancelRequests += 1;
    if (renderRecord) {
      renderRecord = {
        ...renderRecord,
        status: "cancelled",
        progress: 1,
        message: "Cancelled",
        updated: renderSeq + 0.5,
      };
    }
    return route.fulfill(json({ ok: true, cancelled: true, render: renderRecord }));
  });
  await page.route(/\/api\/jobs\/j1\/status$/, (route) => {
    statusPolls += 1;
    if (renderRecord && renderRecord.status !== "cancelled") {
      if (statusPolls < 3) {
        renderRecord = { ...renderRecord, status: "rendering", progress: 0.55, message: "Rendering cut" };
      } else {
        renderRecord = { ...renderRecord, status: "ready", progress: 1, message: "Ready", updated: renderRecord.updated + 1 };
      }
    }
    return route.fulfill(json({
      renders: renderRecord ? { [renderRecord.record_key]: renderRecord } : {},
    }));
  });
  await page.route(/\/api\/jobs\/j1\/usage/, (route) =>
    route.fulfill(json({ total_calls: 0, items: [] })));
  await page.route(/\/api\/jobs\/j1\/media\//, (route) =>
    route.fulfill({ status: 200, contentType: "video/mp4", body: Buffer.alloc(64, 1) }));

  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.body.classList.contains("editor-frame")
      && !document.body.classList.contains("source-mode")
      && !document.body.classList.contains("cut-clean-mode"),
  null, { timeout: 20000 });

  const label = `${viewport.width}×${viewport.height}`;

  // Default Edit, and every Edit feature is still present.
  const edit = await page.evaluate(() => ({
    pressed: document.querySelector("#result-mode-edit")?.getAttribute("aria-pressed"),
    timeline: getComputedStyle(document.querySelector(".editor-pane-timeline")).display,
    hook: getComputedStyle(document.querySelector(".hook-panel")).display,
    audio: getComputedStyle(document.querySelector("#audio-panel")).display,
    legacyScan: document.querySelector("#text-scan"),
    scanStarts: document.querySelectorAll("#clean-scan-start").length,
    editHidden: document.querySelector("#result-mode").hidden,
  }));
  assert(edit.pressed === "true", `${label}: Edit is not pressed by default`);
  assert(edit.timeline !== "none" && edit.hook !== "none" && edit.audio !== "none",
    `${label}: an Edit column is missing by default`);
  assert(edit.legacyScan === null, `${label}: the removed scan card is still present`);
  assert(edit.scanStarts === 1, `${label}: ${edit.scanStarts} scan entries remain`);
  assert(!edit.editHidden, `${label}: the mode switch is hidden on a cut`);

  const smallEditText = await page.evaluate(() => {
    const roots = [
      document.querySelector(".editor-pane-preview"),
      document.querySelector(".editor-pane-timeline"),
      document.querySelector(".editor-pane-settings"),
    ].filter(Boolean);
    const found = [];
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const text = (node.nodeValue || "").trim();
        const element = node.parentElement;
        if (text && element && element.getClientRects().length) {
          const style = getComputedStyle(element);
          const size = Number.parseFloat(style.fontSize);
          if (style.visibility !== "hidden" && style.display !== "none" && size < 11) {
            found.push(`${element.tagName}.${element.className || ""} ${size}px ${text.slice(0, 30)}`);
          }
        }
        node = walker.nextNode();
      }
    }
    return found;
  });
  assert(smallEditText.length === 0,
    `${label}: Edit text below 11px: ${smallEditText.join(" | ")}`);

  // Settings scroll and focus survive Clean -> Edit.
  await page.evaluate(() => {
    const pane = document.querySelector(".editor-pane-settings");
    pane.scrollTop = 600;
    document.querySelector('#target-tabs [data-target="15"]')?.focus();
  });
  const beforeMode = await page.evaluate(() => ({
    scroll: document.querySelector(".editor-pane-settings").scrollTop,
    focused: document.activeElement?.matches?.('#target-tabs [data-target="15"]'),
  }));
  assert(beforeMode.scroll > 0 && beforeMode.focused,
    `${label}: could not set the Edit scroll/focus fixture`);
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"));
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
  const afterMode = await page.evaluate(() => ({
    scroll: document.querySelector(".editor-pane-settings").scrollTop,
    focused: document.activeElement?.matches?.('#target-tabs [data-target="15"]'),
  }));
  assert(afterMode.scroll === beforeMode.scroll,
    `${label}: settings scroll changed (${beforeMode.scroll} -> ${afterMode.scroll})`);
  assert(afterMode.focused, `${label}: focus did not return to the 15s tab`);

  // Change Edit state, then prove Clean restores it.
  await page.locator('#target-tabs [data-target="15"]').click();
  await page.waitForFunction(() =>
    document.querySelector('#target-tabs [data-target="15"]')?.classList.contains("active"),
  null, { timeout: 10000 });

  const overflow = await page.evaluate(() => {
    const button = document.querySelector("#job-menu-open");
    button.click();
    const menu = document.querySelector("#job-menu");
    return {
      open: !menu.hidden,
      expanded: button.getAttribute("aria-expanded"),
      cleanCopy: document.querySelector("#clean-job")?.textContent.trim(),
      profile: Boolean(menu.querySelector("#clean-profile")),
      topClean: [...document.querySelectorAll(".result-actions > button")]
        .filter((node) => node.textContent.trim() === "Clean").length,
    };
  });
  assert(overflow.open && overflow.expanded === "true",
    `${label}: the job overflow did not open`);
  assert(overflow.cleanCopy === "Clean work files…",
    `${label}: overflow clean copy is ${overflow.cleanCopy}`);
  assert(overflow.profile, `${label}: the overflow lost the clean profile`);
  assert(overflow.topClean === 0, `${label}: a top-level Clean button remains`);
  await page.keyboard.press("Escape");
  assert(await page.evaluate(() => document.querySelector("#job-menu").hidden),
    `${label}: Escape did not close the job overflow`);

  // Edit -> Clean, one click.
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"),
    null, { timeout: 10000 });
  const clean = await page.evaluate(() => ({
    pressed: document.querySelector("#result-mode-clean")?.getAttribute("aria-pressed"),
    timeline: getComputedStyle(document.querySelector(".editor-pane-timeline")).display,
    hook: getComputedStyle(document.querySelector(".hook-panel")).display,
    player: getComputedStyle(document.querySelector("#player-wrap")).display,
    ready: getComputedStyle(document.querySelector("#result-ready")).display,
    audio: getComputedStyle(document.querySelector("#audio-panel")).display,
    cleanPanel: getComputedStyle(document.querySelector("#clean-panel")).display,
    head: document.querySelector("#cut-clean-name")?.textContent,
    meta: document.querySelector("#cut-clean-meta")?.textContent,
    primary: document.querySelector("#cut-clean-run")?.textContent.trim(),
    primaryVisible: !document.querySelector("#cut-clean-run").hidden,
    primaries: [...document.querySelectorAll(".primary")]
      .filter((node) => node.offsetParent !== null).length,
  }));
  assert(clean.pressed === "true", `${label}: Clean is not pressed`);
  assert(clean.timeline === "none", `${label}: Smart Cut/moments still show in Clean`);
  assert(clean.hook === "none" && clean.player === "none",
    `${label}: the Edit preview still shows in Clean`);
  assert(clean.ready === "none", `${label}: a second Download row still shows`);
  assert(clean.audio === "none", `${label}: the audio panel still shows in Clean`);
  assert(clean.cleanPanel !== "none", `${label}: the Clean rail is hidden`);
  assert(clean.head === "15s clean cut", `${label}: the rail header is ${clean.head}`);
  assert(/7\.0s/.test(clean.meta) && /210 frames/.test(clean.meta),
    `${label}: the rail meta is ${clean.meta}`);
  assert(clean.primary === "Find text & clean",
    `${label}: the first primary action is ${clean.primary}`);
  assert(clean.primaryVisible && clean.primaries === 1,
    `${label}: ${clean.primaries} primary actions show in Clean`);
  const sticky = await page.locator("#cut-clean-run").boundingBox();
  assert(sticky && sticky.y + sticky.height <= viewport.height,
    `${label}: the sticky Clean action sits below the fold at y=${sticky?.y}`);

  // One click runs scan -> auto tick -> apply -> save -> render. The fill
  // response is held so the auto-ticked rows can be inspected before apply.
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    /Finding text/.test(document.querySelector("#cut-clean-stage")?.textContent || ""),
  null, { timeout: 20000 });
  const guarded = await page.evaluate(() => ({
    disabled: document.querySelector("#result-mode-edit").disabled,
    title: document.querySelector("#result-mode-edit").title,
  }));
  assert(guarded.disabled && /Wait or Cancel/.test(guarded.title),
    `${label}: the switch did not block during Finding text (${guarded.title})`);
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 3,
  null, { timeout: 20000 });
  await page.waitForFunction(() =>
    /Cleaning/.test(document.querySelector("#cut-clean-stage")?.textContent || ""),
  null, { timeout: 20000 });

  const rows = await page.evaluate(() => {
    const items = [...document.querySelectorAll("#clean-found .clean-found-row")];
    return {
      count: items.length,
      checked: items.filter((node) => node.querySelector("[data-found-tick]")?.checked
        && !node.querySelector("[data-found-tick]")?.disabled).length,
      times: items.map((node) => node.querySelector(".clean-found-time")?.textContent),
      outside: items.filter((node) => node.classList.contains("is-outside")).map((node) => ({
        copy: node.textContent,
        checked: node.querySelector("[data-found-tick]")?.checked,
      })),
      review: Boolean(document.querySelector("[data-found-review]")),
      lowChecked: items.filter((node) => node.classList.contains("is-low"))
        .some((node) => node.querySelector("[data-found-tick]")?.checked),
      applyVisible: [...document.querySelectorAll("[data-found-apply]")]
        .some((node) => node.offsetParent !== null),
    };
  });
  assert(rows.count === 3, `${label}: ${rows.count} found rows`);
  assert(rows.checked === 1, `${label}: ${rows.checked} auto ticks`);
  assert(rows.review, `${label}: no review path for the low-confidence row`);
  assert(!rows.lowChecked, `${label}: the low-confidence row was ticked by default`);
  assert(rows.outside.length === 1 && !rows.outside[0].checked,
    `${label}: the outside row was ticked or missing`);
  assert(/Not in this cut/.test(rows.outside[0].copy),
    `${label}: the outside row does not say Not in this cut`);
  assert(rows.times[0] === "0:01.0 – 0:03.0",
    `${label}: the cut-time range is ${rows.times[0]}`);
  assert(rows.times[rows.times.length - 1] === "—",
    `${label}: the outside row shows ${rows.times[rows.times.length - 1]}`);
  assert(!rows.applyVisible, `${label}: a second primary Remove ticked still shows`);

  // Outside rows do not move the playhead.
  const beforeTime = await page.evaluate(() => document.querySelector("#clean-scrub").value);
  await page.locator("#clean-found .clean-found-row.is-outside").click();
  await page.waitForFunction(() =>
    /Not in this cut/.test(document.querySelector("#clean-status")?.textContent || ""),
  null, { timeout: 10000 });
  const afterTime = await page.evaluate(() => document.querySelector("#clean-scrub").value);
  assert(beforeTime === afterTime, `${label}: an outside row moved the playhead`);

  // Keyboard: Enter on a row seeks to start − 0.5 s; Space toggles a tick.
  await page.evaluate(() => {
    document.querySelector('#clean-found [data-found-index="0"]').focus();
  });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() =>
    document.querySelector("#clean-scrub").value === "0.5",
  null, { timeout: 10000 });
  await page.evaluate(() => {
    document.querySelector('#clean-found .clean-found-row.is-low [data-found-tick]').focus();
  });
  await page.keyboard.press("Space");
  await page.waitForFunction(() =>
    document.querySelector('#clean-found .clean-found-row.is-low [data-found-tick]')?.checked === true,
  null, { timeout: 10000 });
  await page.keyboard.press("Space");
  await page.waitForFunction(() =>
    document.querySelector('#clean-found .clean-found-row.is-low [data-found-tick]')?.checked === false,
  null, { timeout: 10000 });

  // Release AI fill, then the same click cleans and renders.
  releaseFill();
  await page.waitForFunction(() =>
    /Rendering/.test(document.querySelector("#cut-clean-stage")?.textContent || ""),
  null, { timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelector("#cut-clean-cancel")?.hidden === false,
  null, { timeout: 10000 });
  assert(await page.locator("#cut-clean-cancel").isVisible(),
    `${label}: the rendering stage offers no Cancel`);
  await page.waitForFunction(() =>
    !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });

  const result = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    meta: document.querySelector("#cut-clean-meta")?.textContent || "",
    href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
    download: document.querySelector("#cut-clean-download")?.getAttribute("download") || "",
    runHidden: document.querySelector("#cut-clean-run").hidden,
    primaries: [...document.querySelectorAll(".primary")]
      .filter((node) => node.offsetParent !== null).length,
    progress: document.querySelector("#cut-clean-progress").hidden,
    again: document.querySelector("#cut-clean-again").textContent.trim(),
    switchDisabled: document.querySelector("#result-mode-edit").disabled,
  }));
  assert(/Clean cut ready/.test(result.summary), `${label}: result summary is ${result.summary}`);
  assert(/LaMa/.test(result.meta), `${label}: the rail engine is ${result.meta}`);
  assert(/media\/reel_15_1\.mp4/.test(result.href), `${label}: download is ${result.href}`);
  assert(result.download === "cut-source-15s.mp4", `${label}: download name is ${result.download}`);
  assert(result.runHidden && result.primaries === 1,
    `${label}: ${result.primaries} primary actions after ready`);
  assert(result.progress, `${label}: progress stayed visible after ready`);
  assert(result.again === "Clean again", `${label}: the retry action is ${result.again}`);
  assert(!result.switchDisabled, `${label}: the switch stayed blocked after ready`);
  const downloadBox = await page.locator("#cut-clean-download").boundingBox();
  assert(downloadBox && downloadBox.y + downloadBox.height <= viewport.height,
    `${label}: Download sits below the fold at y=${downloadBox?.y}`);

  // Reload after the first render: the ready record must survive, match the
  // normalized ranges, and agree with Edit. No stale marker.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator('#target-tabs [data-target="15"]').click();
  await page.waitForFunction(() =>
    !document.querySelector("#result-ready").hidden
      && /media\/reel_15_1\.mp4/.test(document.querySelector("#result-ready-download")?.getAttribute("href") || ""),
  null, { timeout: 30000 });
  const editReadyHref = await page.locator("#result-ready-download").getAttribute("href");
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    !document.querySelector("#cut-clean-result-actions").hidden
      && /Clean cut ready/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
  null, { timeout: 30000 });
  const reloadedClean = await page.evaluate(() => ({
    href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
    className: document.querySelector("#cut-clean-download")?.className || "",
    stale: !document.querySelector("#render-stale")?.hidden,
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
  }));
  assert(reloadedClean.href === editReadyHref,
    `${label}: Edit and Clean disagree after reload (${editReadyHref} / ${reloadedClean.href})`);
  assert(reloadedClean.className.includes("primary") && !reloadedClean.stale,
    `${label}: the reloaded Clean download is stale (${reloadedClean.summary})`);

  // A missing local baseline is a warning, not a stale file: the current
  // Download stays current and the rail uses the no-baseline copy.
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("classic-render-sig:j1:")) localStorage.removeItem(key);
    }
  });
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"));
  const noBaseline = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
    className: document.querySelector("#cut-clean-download")?.className || "",
    runHidden: document.querySelector("#cut-clean-run").hidden,
  }));
  assert(/No render baseline/.test(noBaseline.summary),
    `${label}: no-baseline summary is ${noBaseline.summary}`);
  assert(!/Changed since this render/.test(noBaseline.summary),
    `${label}: no baseline was treated as changed`);
  assert(noBaseline.runHidden && /media\/reel_15_1\.mp4/.test(noBaseline.href)
    && noBaseline.className.includes("primary"),
  `${label}: no baseline demoted the current file (${noBaseline.href} / ${noBaseline.className})`);

  const savedPut = textPuts.find((body) => Array.isArray(body.clean) && body.clean.length === 1);
  assert(savedPut, `${label}: the save never carried one Clean layer`);
  assert(!textPuts.some((body) => (body.clean || []).some((layer) => layer.tracklet_id === "t3")),
    `${label}: the outside row was saved`);
  const saved = savedPut.clean[0];
  assert(saved.tracklet_id === "t1", `${label}: the wrong row was saved (${saved.tracklet_id})`);
  assert(JSON.stringify(saved.ranges) === JSON.stringify([{ start: 1, end: 3 }]),
    `${label}: saved range is ${JSON.stringify(saved.ranges)}`);
  assert(renderBodies.length === 1 && renderBodies[0].edit?.clean?.length === 1,
    `${label}: the render carried ${renderBodies[0]?.edit?.clean?.length} layers`);
  assert(renderBodies[0].quality === "final", `${label}: the render quality is ${renderBodies[0].quality}`);

  // Double-click opens the detail strip with cut time, not source time.
  await page.locator('#clean-found [data-found-index="0"]').dblclick();
  await page.locator("#clean-detail").waitFor({ state: "visible", timeout: 10000 });
  const detail = await page.locator("#clean-detail").textContent();
  assert(/0:01\.0 – 0:03\.0/.test(detail), `${label}: the detail strip is ${detail}`);
  assert(!/0:03\.0 – 0:05\.0/.test(detail), `${label}: the detail strip kept source time`);

  // Before sends no Clean layers; After sends the current layers.
  frameBodies.length = 0;
  fillPreviewBodies.length = 0;
  const beforeRequest = page.waitForRequest((request) =>
    /\/api\/classic\/jobs\/j1\/frame$/.test(request.url()) && request.method() === "POST");
  await page.locator("#clean-preview-before").click();
  await beforeRequest;
  await page.waitForTimeout(150);
  assert(frameBodies.length >= 1 && frameBodies[0].clean.length === 0,
    `${label}: Before sent ${frameBodies[0]?.clean?.length} Clean layers`);
  // Move inside the cleaned range so After can use the fill preview.
  await page.evaluate(() => {
    const scrub = document.querySelector("#clean-scrub");
    scrub.value = "2";
    scrub.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForTimeout(350);
  const afterRequest = page.waitForRequest((request) =>
    /\/api\/classic\/jobs\/j1\/fill\/preview$/.test(request.url()) && request.method() === "POST");
  await page.locator("#clean-preview-after").click();
  await afterRequest;
  await page.waitForFunction(() =>
    document.querySelector("#clean-frame")?.getAttribute("src")?.startsWith("data:image/jpeg"),
  null, { timeout: 20000 });
  assert(fillPreviewBodies.length >= 1 && fillPreviewBodies[0].clean.length === 1,
    `${label}: After sent ${fillPreviewBodies[0]?.clean?.length} Clean layers`);

  // The AI fill choices are offered, and the next render carries them.
  const fillOptions = await page.evaluate(() => ({
    engine: document.querySelector("#clean-fill-engine")?.value,
    device: document.querySelector("#clean-fill-device")?.value,
    follow: document.querySelector("#clean-fill-follow")?.checked,
    disabled: [...document.querySelectorAll("#clean-fill-engine option")]
      .filter((node) => node.disabled).map((node) => node.value),
  }));
  assert(fillOptions.engine === "lama" && fillOptions.device === "" && fillOptions.follow === false,
    `${label}: the AI fill defaults are ${JSON.stringify(fillOptions)}`);
  assert(fillOptions.disabled.join() === "migan,ns",
    `${label}: the engines not ready are ${fillOptions.disabled.join()}`);
  await page.locator("#clean-fill-device").selectOption("cpu");
  await page.locator("#clean-fill-follow").check();
  const remembered = await page.evaluate(() => JSON.parse(localStorage.getItem("vibecut.classic.fillChoice")));
  assert(remembered.device === "cpu" && remembered.follow === true,
    `${label}: the AI fill choice was not kept: ${JSON.stringify(remembered)}`);

  // Clean again reaches a second ready record through the normal render path.
  const secondRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-again").click();
  await secondRender;
  assert(renderBodies.at(-1).fill_device === "cpu" && renderBodies.at(-1).fill_follow === true,
    `${label}: the render carried ${renderBodies.at(-1).fill_device} / ${renderBodies.at(-1).fill_follow}`);
  await page.waitForFunction(() =>
    /media\/reel_15_2\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  const secondReady = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
    className: document.querySelector("#cut-clean-download")?.className || "",
  }));
  assert(/Clean cut ready/.test(secondReady.summary),
    `${label}: the second ready summary is ${secondReady.summary}`);
  assert(/reel_15_2\.mp4/.test(secondReady.href) && secondReady.className.includes("primary"),
    `${label}: the second ready Download is ${secondReady.href} / ${secondReady.className}`);

  // Changing the method after ready makes the record stale: no current
  // Download, a stale summary and the Clean + render-again action.
  await page.locator("#clean-layers [data-clean-method=\"blur\"]").first().click();
  await page.waitForFunction(() =>
    /Changed since this render/.test(document.querySelector("#cut-clean-summary")?.textContent || "")
      && !document.querySelector("#cut-clean-run").hidden,
  null, { timeout: 20000 });
  const stale = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    runText: document.querySelector("#cut-clean-run").textContent.trim(),
    downloadText: document.querySelector("#cut-clean-download")?.textContent.trim() || "",
    downloadClass: document.querySelector("#cut-clean-download")?.className || "",
    downloadHidden: document.querySelector("#cut-clean-download")?.hidden,
    staleVisible: !document.querySelector("#render-stale")?.hidden,
    staleText: document.querySelector("#render-stale")?.textContent || "",
  }));
  assert(stale.runText.includes("render again"),
    `${label}: the stale action is ${stale.runText}`);
  assert(!/Clean cut ready/.test(stale.summary),
    `${label}: stale still says ready: ${stale.summary}`);
  assert(!stale.downloadHidden && stale.downloadText.includes("older")
    && stale.downloadClass.includes("ghost"),
  `${label}: the stale file is presented as current (${stale.downloadText} / ${stale.downloadClass})`);
  assert(stale.staleVisible && /Changed since this render/.test(stale.staleText),
    `${label}: #render-stale is hidden in Clean`);

  // A stale record with the layer deleted must say something, not do nothing.
  const staleRendersBefore = renderBodies.length;
  await page.locator("#clean-layers [data-clean-delete]").first().click();
  await page.waitForFunction(() => document.querySelectorAll("#clean-layers .clean-row").length === 0,
    null, { timeout: 10000 });
  const staleReviewLabel = (await page.locator("#cut-clean-run").textContent()).trim();
  assert(staleReviewLabel === "Review 1 low-confidence",
    `${label}: stale review label is ${staleReviewLabel}`);
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    (document.querySelector("#clean-status")?.textContent || "").trim().length > 0,
  null, { timeout: 10000 });
  const staleNotice = await page.evaluate(() => ({
    note: document.querySelector("#clean-status")?.textContent.trim() || "",
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
  }));
  assert(/Review/.test(staleNotice.note) || /found/.test(staleNotice.note),
    `${label}: the stale delete note is ${staleNotice.note}`);
  assert(renderBodies.length === staleRendersBefore,
    `${label}: a stale delete started a render`);
  await page.locator("#clean-undo").click();
  await page.waitForFunction(() => document.querySelectorAll("#clean-layers .clean-row").length === 1,
    null, { timeout: 10000 });

  // Re-render from stale; the same record becomes current again.
  const thirdRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-run").click();
  await thirdRender;
  await page.waitForFunction(() =>
    /media\/reel_15_3\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  const fresh = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    href: document.querySelector("#cut-clean-download")?.getAttribute("href") || "",
    className: document.querySelector("#cut-clean-download")?.className || "",
    staleVisible: !document.querySelector("#render-stale")?.hidden,
  }));
  assert(/Clean cut ready/.test(fresh.summary), `${label}: the fresh summary is ${fresh.summary}`);
  assert(/reel_15_3\.mp4/.test(fresh.href) && fresh.className.includes("primary"),
    `${label}: the fresh Download is ${fresh.href} / ${fresh.className}`);
  assert(!fresh.staleVisible, `${label}: the stale note survived a fresh render`);
  assert(renderBodies.length === 3 && renderBodies[2].edit?.clean?.[0]?.method === "blur",
    `${label}: the stale re-render did not carry the changed method`);

  // Ready -> another render -> Cancel. The cancelled record keeps no current
  // Download and shows the cancelled note.
  const fourthRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-again").click();
  await fourthRender;
  await page.waitForFunction(() =>
    /Rendering/.test(document.querySelector("#cut-clean-stage")?.textContent || "")
      && !document.querySelector("#cut-clean-cancel").hidden,
  null, { timeout: 30000 });
  await page.waitForTimeout(1000);
  await page.locator("#cut-clean-cancel").click();
  await page.waitForFunction(() =>
    /Render cancelled/.test(document.querySelector("#cut-clean-summary")?.textContent || ""),
  null, { timeout: 30000 });
  const cancelled = await page.evaluate(() => ({
    summary: document.querySelector("#cut-clean-summary")?.textContent || "",
    downloadHidden: document.querySelector("#cut-clean-download").hidden,
    actionsHidden: document.querySelector("#cut-clean-result-actions").hidden,
    againHidden: document.querySelector("#cut-clean-again").hidden,
    runHidden: document.querySelector("#cut-clean-run").hidden,
  }));
  assert(cancelRequests === 1, `${label}: Cancel called the route ${cancelRequests} times`);
  assert(renderBodies.length === 4, `${label}: the cancel gate made ${renderBodies.length} renders`);
  assert(cancelled.downloadHidden,
    `${label}: a cancelled render still offers Download`);
  assert(!cancelled.runHidden && !cancelled.actionsHidden && !cancelled.againHidden,
    `${label}: a cancelled render leaves no retry path`);
  assert(/Render cancelled/.test(cancelled.summary),
    `${label}: the cancelled state is ${cancelled.summary}`);

  // Draw mode is Edit state: Clean turns it off, Edit gets it back.
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"),
    null, { timeout: 10000 });
  await page.locator("#clean-draw").click();
  assert(await page.locator("#clean-draw").getAttribute("aria-pressed") === "true",
    `${label}: the draw tool did not turn on in Edit`);
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"),
    null, { timeout: 10000 });
  assert(await page.locator("#clean-draw").getAttribute("aria-pressed") === "false",
    `${label}: Clean kept the draw tool on`);
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"),
    null, { timeout: 10000 });
  assert(await page.locator("#clean-draw").getAttribute("aria-pressed") === "true",
    `${label}: Edit did not get its draw tool back`);

  // Edit focus returns to the same moment card when it still exists.
  await page.evaluate(() => {
    document.querySelector("[data-moment-scene]")?.focus();
  });
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"));
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
  assert(await page.evaluate(() =>
    Boolean(document.activeElement?.matches?.("[data-moment-scene]"))),
  `${label}: Edit did not return focus to the moment card`);

  // One click back restores Edit and its state.
  const restored = await page.evaluate(() => ({
    target: document.querySelector('#target-tabs [data-target="15"]')?.classList.contains("active"),
    timeline: getComputedStyle(document.querySelector(".editor-pane-timeline")).display,
    audio: getComputedStyle(document.querySelector("#audio-panel")).display,
    cleanLayers: document.querySelectorAll("#clean-layers .clean-row").length,
    pressed: document.querySelector("#result-mode-edit")?.getAttribute("aria-pressed"),
  }));
  assert(restored.target, `${label}: Edit lost the 15s target`);
  assert(restored.timeline !== "none" && restored.audio !== "none",
    `${label}: Edit panels did not come back`);
  assert(restored.cleanLayers === 1, `${label}: Edit lost its Clean layer`);
  assert(restored.pressed === "true", `${label}: Edit is not pressed after returning`);

  // Unticked found rows plus a drawn layer still go to review, not straight to
  // a render. Reload clears the session render record; the all-high fixture
  // proves a drawn layer is not counted as an applied scan layer.
  await page.locator("#clean-layers [data-clean-delete]").first().click();
  await page.waitForFunction(() => document.querySelectorAll("#clean-layers .clean-row").length === 0,
    null, { timeout: 10000 });
  if (await page.locator("#clean-draw").getAttribute("aria-pressed") !== "true") {
    await page.locator("#clean-draw").click();
  }
  const canvasBox = await page.locator("#clean-canvas").boundingBox();
  await page.mouse.move(canvasBox.x + canvasBox.width * 0.2, canvasBox.y + canvasBox.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(
    canvasBox.x + canvasBox.width * 0.5,
    canvasBox.y + canvasBox.height * 0.45,
    { steps: 6 },
  );
  await page.mouse.up();
  await page.waitForFunction(() => document.querySelectorAll("#clean-layers .clean-row").length === 1,
    null, { timeout: 10000 });
  await page.waitForTimeout(800);
  allHighScan = true;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 4
      && document.querySelectorAll("#clean-layers .clean-row").length === 1,
  null, { timeout: 30000 });
  await page.locator("#clean-found [data-found-none]").click();
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Review 2 texts$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
      && !document.querySelector("#cut-clean-run").hidden,
  null, { timeout: 10000 });
  const rendersBeforeReview = renderBodies.length;
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    /Review the found text/.test(document.querySelector("#clean-status")?.textContent || ""),
  null, { timeout: 10000 });
  assert(renderBodies.length === rendersBeforeReview,
    `${label}: the review path started a render`);
  assert(await page.evaluate(() =>
    document.activeElement?.classList?.contains("clean-found-row") === true),
  `${label}: the review path did not focus a found row`);

  // B1: four ticked high rows plus one unticked low row still render. Zero
  // ticks go to review; ticking the low row then renders it.
  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
  await page.locator("#clean-layers [data-clean-delete]").first().click();
  await page.waitForFunction(() => document.querySelectorAll("#clean-layers .clean-row").length === 0,
    null, { timeout: 10000 });
  await page.waitForTimeout(800);
  b1Scan = true;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 5
      && document.querySelectorAll("#clean-layers .clean-row").length === 0,
  null, { timeout: 30000 });
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Clean 4 texts & render$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
      && !document.querySelector("#cut-clean-run").hidden,
  null, { timeout: 10000 });
  const b1FirstRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-run").click();
  await b1FirstRender;
  await page.waitForFunction(() =>
    /media\/reel_15_5\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  assert(renderBodies[4].edit?.clean?.length === 4,
    `${label}: the 4-high render carried ${renderBodies[4]?.edit?.clean?.length} layers`);

  const b1Low = page.locator("#clean-found .clean-found-row.is-low [data-found-tick]");
  await b1Low.check();
  const b1SecondRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-again").click();
  await b1SecondRender;
  await page.waitForFunction(() =>
    /media\/reel_15_6\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  const b1Ticked = renderBodies[5].edit?.clean || [];
  assert(b1Ticked.length === 5 && b1Ticked.some((layer) => layer.tracklet_id === "b5"),
    `${label}: the low tick was not added (${b1Ticked.map((layer) => layer.tracklet_id)})`);

  await page.locator("#result-mode-edit").click();
  await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
  for (let index = 5; index > 0; index -= 1) {
    await page.locator("#clean-layers [data-clean-delete]").first().click();
    await page.waitForFunction((count) =>
      document.querySelectorAll("#clean-layers .clean-row").length === count,
    index - 1, { timeout: 10000 });
  }
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    /^Review 1 low-confidence$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
      && !document.querySelector("#cut-clean-run").hidden,
  null, { timeout: 10000 });
  const b1RendersBeforeReview = renderBodies.length;
  await page.locator("#cut-clean-run").click();
  await page.waitForFunction(() =>
    /Review the low-confidence rows/.test(document.querySelector("#clean-status")?.textContent || ""),
  null, { timeout: 10000 });
  assert(await page.evaluate(() =>
    document.activeElement?.classList?.contains("is-low") === true),
  `${label}: the review path did not focus the low-confidence row`);
  assert(renderBodies.length === b1RendersBeforeReview,
    `${label}: zero ticks still started a render`);

  await page.locator("#clean-found .clean-found-row.is-low [data-found-tick]").check();
  await page.waitForFunction(() =>
    /^Clean 1 text & render again$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
      && !document.querySelector("#cut-clean-run").hidden,
  null, { timeout: 10000 });
  const b1LastRender = page.waitForRequest((request) =>
    /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
  await page.locator("#cut-clean-run").click();
  await b1LastRender;
  await page.waitForFunction(() =>
    /media\/reel_15_7\.mp4/.test(document.querySelector("#cut-clean-download")?.getAttribute("href") || "")
      && !document.querySelector("#cut-clean-result-actions").hidden,
  null, { timeout: 30000 });
  const b1Last = renderBodies[6].edit?.clean || [];
  assert(b1Last.length === 1 && b1Last[0].tracklet_id === "b5",
    `${label}: the ticked low row was not rendered (${b1Last.map((layer) => layer.tracklet_id)})`);

  // The locked fill card wraps its long model path inside the 1280 rail.
  fillUnavailable = true;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() =>
    document.body.classList.contains("cut-clean-mode")
      && Boolean(document.querySelector("#clean-fill .clean-fill-locked")),
  null, { timeout: 30000 });
  const fillLayout = await page.evaluate(() => {
    const panel = document.querySelector("#clean-panel");
    const fill = document.querySelector("#clean-fill");
    const reason = document.querySelector("#clean-fill .clean-fill-locked p.hint");
    const panelBox = panel.getBoundingClientRect();
    const reasonBox = reason.getBoundingClientRect();
    return {
      panelScroll: panel.scrollWidth,
      panelClient: panel.clientWidth,
      fillScroll: fill.scrollWidth,
      fillClient: fill.clientWidth,
      reasonRight: reasonBox.right,
      panelRight: panelBox.right,
    };
  });
  assert(fillLayout.panelScroll <= fillLayout.panelClient + 1,
    `${label}: the Clean rail overflows (${fillLayout.panelScroll} > ${fillLayout.panelClient})`);
  assert(fillLayout.fillScroll <= fillLayout.fillClient + 1,
    `${label}: the fill card overflows (${fillLayout.fillScroll} > ${fillLayout.fillClient})`);
  assert(fillLayout.reasonRight <= fillLayout.panelRight + 1,
    `${label}: the fill reason crosses the rail (${fillLayout.reasonRight} > ${fillLayout.panelRight})`);

  // A target change re-runs the auto-tick for the new cut. HELLO WORLD stays
  // inside at 15 and 60; the outside high row stays unticked; the low row is
  // left for review.
  targetScan = true;
  fillUnavailable = false;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 3,
  null, { timeout: 30000 });

  async function expectTargetAutoTick(target) {
    await page.locator("#result-mode-edit").click();
    await page.waitForFunction(() => !document.body.classList.contains("cut-clean-mode"));
    // The stub serves the same Clean rows for every cut. Start each target cut
    // with no applied layers, like a real per-cut record.
    cleanRows = [];
    await page.locator(`#target-tabs [data-target="${target}"]`).click();
    await page.waitForFunction((value) =>
      document.querySelector(`#target-tabs [data-target="${value}"]`)?.classList.contains("active"),
    target, { timeout: 10000 });
    await page.locator("#result-mode-clean").click();
    await page.waitForFunction(() =>
      /^Clean 1 text & render$/.test(document.querySelector("#cut-clean-run")?.textContent.trim() || "")
        && !document.querySelector("#cut-clean-run").hidden,
    null, { timeout: 10000 });
    const ticks = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#clean-found .clean-found-row")];
      const row = (text) => rows.find((node) => node.textContent.includes(text));
      const checked = (node) => node?.querySelector("[data-found-tick]")?.checked === true;
      return {
        hello: checked(row("HELLO WORLD")),
        low: checked(row("low row")),
        outside: checked(row("outside high")),
        outsideClass: row("outside high")?.classList.contains("is-outside") === true,
      };
    });
    assert(ticks.hello, `${label}: HELLO WORLD is not ticked at ${target}s`);
    assert(!ticks.low, `${label}: the low row was auto-ticked at ${target}s`);
    assert(!ticks.outside && ticks.outsideClass,
      `${label}: the outside row was ticked at ${target}s`);

    const rendersBefore = renderBodies.length;
    const targetRender = page.waitForRequest((request) =>
      /\/api\/jobs\/j1\/render$/.test(request.url()) && request.method() === "POST");
    await page.locator("#cut-clean-run").click();
    await targetRender;
    await page.waitForFunction(() =>
      !document.querySelector("#cut-clean-result-actions").hidden,
    null, { timeout: 30000 });
    assert(renderBodies.length === rendersBefore + 1,
      `${label}: the ${target}s primary did not render in one click`);
  }

  await expectTargetAutoTick(15);
  await expectTargetAutoTick(60);

  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    scrollY: window.scrollY,
  }));
  assert(layout.scrollWidth <= layout.innerWidth + 1,
    `${label}: horizontal overflow ${layout.scrollWidth} > ${layout.innerWidth}`);
  assert(layout.scrollY === 0, `${label}: the page moved to ${layout.scrollY}`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(consoleErrors.length === 0, `${label}: console errors: ${consoleErrors.join(" | ")}`);
  assert(!consoleErrors.some((text) => /\b404\b/.test(text)),
    `${label}: a console 404 appeared on a fresh cut`);

  await context.close();
  console.log(`ok cut-clean ${label}`);
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
