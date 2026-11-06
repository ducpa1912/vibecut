/**
 * Phase 5 · polish gate, driven without real media.
 *
 * Source Clean and Cut Clean are opened through stubbed routes at 1440×900,
 * 1280×800, 1050×800 and 900×800. The spec proves the rail is a bottom sheet
 * under 1100 px, the primary action stays reachable, motion respects the OS
 * preference, focus rings stay visible, no visible text is under 11 px, the
 * Clean entry time moves to the first text row (or explains a black 0:00), and
 * the normal flows keep the console clean.
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

const SOURCE = {
  name: "phase5-source.mp4", duration: 12, width: 1280, height: 720,
  fps: 30, has_audio: true, size: 2048,
};

const SOURCE_JOB = {
  id: "j1", created: 1, updated: 1, status: "source_ready",
  progress: 1, message: "Source ready", error: null, mode: "clean",
  source: SOURCE, options: {}, analysis: null, renders: {},
  artifacts: {}, artifact_ids: [],
  source_clean: { status: "idle", progress: 0, message: "No Source Clean render has run." },
};

const FILL = {
  available: true, missing: [], files: [],
  engines: { lama: { id: "lama", ready: true, reason: "" } },
  default: "lama", preview: "lama", methods: ["blur", "crop", "lama"],
  note: "AI fill is ready with LaMa.",
};

const ROW_SCAN = {
  status: "ready", complete: true, message: "", progress: 1,
  text: { confirmed: true, tracklets: 2, present: true },
  tracklets: [{ id: 1 }, { id: 2 }],
  clean_prefill: [
    {
      tracklet_id: "t1", kind: "subtitle",
      box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
      ranges: [{ start: 2.0, end: 4.0 }], action: "blur", enabled: true,
      confidence: 0.92, text: "first words", text_key: "first words",
    },
    {
      tracklet_id: "t2", kind: "handle_or_logo",
      box: { x: 0.78, y: 0.03, w: 0.18, h: 0.08 },
      ranges: [], action: "blur", enabled: true,
      confidence: 0.81, text: "mark", text_key: "mark",
    },
  ],
};

const EMPTY_SCAN = {
  status: "ready", complete: true, message: "", progress: 1,
  text: { confirmed: true, tracklets: 0, present: false },
  tracklets: [], clean_prefill: [],
};

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
  reasoning: { hook: { headline: "Opening" }, payoff: { headline: "Ending" } },
};
const CUT_JOB = {
  ...SOURCE_JOB, status: "ready", message: "Ready", mode: "reel", analysis: {
    scene_count: 1, hook_scene: 0, deep_count: 1, elapsed: 1.2, engine: {},
    scenes: [CUT_SCENE],
    plans: { "15": { ...PLAN, target: 15 }, "30": PLAN, "60": { ...PLAN, target: 60 } },
  },
};
const CUT_SCAN = {
  ...ROW_SCAN,
  clean_prefill: [
    {
      tracklet_id: "c1", kind: "subtitle",
      box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
      ranges: [{ start: 3.0, end: 5.0 }], action: "blur", enabled: true,
      confidence: 0.92, text: "cut words", text_key: "cut words",
    },
  ],
};

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  console.error(`SKIP: Chromium did not launch: ${error?.message || error}`);
  process.exit(2);
}

async function stubContext(viewport, sourceMode) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  let scan = sourceMode ? ROW_SCAN : CUT_SCAN;
  let sourceStatus = "idle";
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const job = () => (sourceMode ? SOURCE_JOB : CUT_JOB);
  await page.route(/\/api\/jobs\/j1$/, (route) => route.fulfill(json(job())));
  await page.route(/\/api\/jobs\/j1\/check$/, (route) => route.fulfill(json(scan)));
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(FILL)));
  await page.route(/\/api\/jobs\/j1\/history/, (route) =>
    route.fulfill(json({ entries: [] })));
  await page.route(/\/api\/jobs\/j1\/audio\/moods/, (route) =>
    route.fulfill(json({ moods: [] })));
  await page.route(/\/api\/audio\/engines$/, (route) =>
    route.fulfill(json({ voices: {}, music: {}, translation: [] })));
  await page.route(/\/api\/jobs\/j1\/mixer/, (route) =>
    route.fulfill(json({ ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [] })));
  await page.route(/\/api\/jobs\/j1\/usage/, (route) =>
    route.fulfill(json({ total_calls: 0, items: [] })));
  await page.route(/\/api\/jobs\/j1\/thumb\/0$/, (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: JPEG_BYTES }));
  await page.route(/\/api\/classic\/jobs\/j1\/text$/, (route) => {
    if (route.request().method() === "PUT") {
      return route.fulfill(json({ cut: { overlays: [], effects: [], clean: [] }, aspects: ["9:16", "4:5"] }));
    }
    return route.fulfill(json({
      cut: { overlays: [], effects: [], clean: [], source_clean_seeded: false },
      aspects: ["9:16", "4:5"], source_clean_added: 0, source_clean_note: "",
    }));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/frame$/, (route) =>
    route.fulfill({
      status: 200, contentType: "image/jpeg",
      headers: { "X-VibeCut-Segment": "0", "X-VibeCut-Crop": "0,0,1,1", "X-VibeCut-Fill": "0" },
      body: JPEG_BYTES,
    }));
  await page.route(/\/api\/classic\/jobs\/j1\/frame\/source$/, (route) =>
    route.fulfill({
      status: 200, contentType: "image/jpeg",
      headers: { "X-VibeCut-Width": "1280", "X-VibeCut-Height": "720", "X-VibeCut-Fill": "0" },
      body: JPEG_BYTES,
    }));
  await page.route(/\/api\/classic\/jobs\/j1\/fill\/preview$/, (route) =>
    route.fulfill(json({
      before: `data:image/jpeg;base64,${JPEG_BASE64}`,
      after: `data:image/jpeg;base64,${JPEG_BASE64}`,
      width: 1280, height: 720, time: 2, method: "lama", render_method: "lama",
      scope: sourceMode ? "source" : "cut",
    })));
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source$/, (route) =>
    route.fulfill(json({ status: sourceStatus, progress: 0, message: "Idle" })));
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source\/render$/, (route) => {
    sourceStatus = "ready";
    return route.fulfill(json({
      status: "ready", progress: 1, message: "Clean video ready",
      path: "/tmp/out.mp4", url: "/api/classic/jobs/j1/clean/source/media?v=1",
      width: 1280, height: 720, duration: 12, method: "lama", cached: false,
    }));
  });
  await page.route(/\/api\/classic\/jobs\/j1\/clean\/source\/media/, (route) =>
    route.fulfill({
      status: 200, contentType: "video/mp4",
      headers: { "content-length": "2048" }, body: Buffer.alloc(2048, 1),
    }));
  await page.route(/\/api\/jobs\/j1\/render$/, (route) =>
    route.fulfill(json({
      render: {
        key: "30", record_key: "30", target: 30, quality: "final", aspect: "9:16",
        status: "ready", progress: 1, message: "Ready", width: 1080, height: 1920,
        duration: 7, clip_count: 1, size: 2048, updated: 1,
        url: "/api/jobs/j1/media/reel_30_1.mp4",
      },
    })));
  await page.route(/\/api\/jobs\/j1\/status$/, (route) =>
    route.fulfill(json({ renders: {} })));
  await page.route(/\/api\/jobs\/j1\/media\//, (route) =>
    route.fulfill({ status: 200, contentType: "video/mp4", body: Buffer.alloc(64, 1) }));

  return { context, page, pageErrors, consoleErrors, setScan: (next) => { scan = next; }, setSourceStatus: (next) => { sourceStatus = next; } };
}

function visibleTextBelowFloor() {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const text = String(node.nodeValue || "").trim();
    const el = node.parentElement;
    if (text && el) {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      const shown = style.display !== "none" && style.visibility !== "hidden"
        && Number(style.opacity) > 0.01 && rect.width > 0 && rect.height > 0;
      const size = parseFloat(style.fontSize);
      if (shown && size < 10.99) {
        out.push({ text: text.slice(0, 48), size: style.fontSize, tag: el.tagName, cls: String(el.className) });
      }
    }
    node = walker.nextNode();
  }
  return out;
}

async function layout(page, viewport, mode) {
  const label = `${mode} ${viewport.width}×${viewport.height}`;
  const box = await page.evaluate(() => {
    const rect = (selector) => {
      const node = document.querySelector(selector);
      if (!node || node.hidden) return null;
      const r = node.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height, bottom: r.bottom, right: r.right };
    };
    return {
      viewport: { w: innerWidth, h: innerHeight },
      docWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      docHeight: document.documentElement.scrollHeight,
      resultOverflow: (() => {
        const node = document.querySelector("#result-view");
        return node ? node.scrollWidth - node.clientWidth : 0;
      })(),
      settingsOverflow: (() => {
        const node = document.querySelector(".editor-pane-settings");
        return node ? node.scrollWidth - node.clientWidth : 0;
      })(),
      preview: rect(".editor-pane-preview"),
      settings: rect(".editor-pane-settings"),
      top: rect(".result-top"),
      run: rect("#source-clean-run") || rect("#cut-clean-run"),
      download: rect("#source-clean-download") || rect("#cut-clean-download"),
      radius: (() => {
        const node = document.querySelector(".editor-pane-settings");
        return node ? getComputedStyle(node).borderTopLeftRadius : "";
      })(),
      slider: (() => {
        const node = document.querySelector("#clean-scrub");
        return node ? { value: node.value, y: node.getBoundingClientRect().y } : null;
      })(),
    };
  });
  assert(box.docWidth <= viewport.width + 1,
    `${label}: horizontal overflow ${box.docWidth} > ${viewport.width}`);
  assert(box.bodyWidth <= viewport.width + 1,
    `${label}: body overflow ${box.bodyWidth} > ${viewport.width}`);
  assert(box.resultOverflow <= 1,
    `${label}: result-view clips content (${box.resultOverflow}px)`);
  assert(box.settingsOverflow <= 1,
    `${label}: settings rail clips content (${box.settingsOverflow}px)`);
  assert(box.preview && box.settings, `${label}: preview or rail is missing`);
  if (viewport.width >= 1100) {
    assert(box.settings.x >= box.preview.right - 2,
      `${label}: the rail is not beside the frame (${box.settings.x} < ${box.preview.right})`);
  } else {
    assert(box.settings.y >= box.preview.bottom - 2,
      `${label}: the rail is not below the frame (${box.settings.y} < ${box.preview.bottom})`);
    assert(parseFloat(box.radius) >= 10,
      `${label}: the rail is not a bottom sheet (radius ${box.radius})`);
  }
  assert(box.run && box.run.y >= 0 && box.run.bottom <= viewport.height + 1,
    `${label}: the primary action is outside the viewport (${JSON.stringify(box.run)})`);
  return box;
}

async function checkTypeAndFocus(page, label) {
  const small = await page.evaluate(visibleTextBelowFloor);
  assert(small.length === 0, `${label}: text below 11px: ${JSON.stringify(small.slice(0, 6))}`);

  const seen = [];
  for (let i = 0; i < 22; i += 1) {
    await page.keyboard.press("Tab");
    const state = await page.evaluate(() => {
      const active = document.activeElement;
      if (!active || active === document.body) return null;
      const style = getComputedStyle(active);
      const rect = active.getBoundingClientRect();
      return {
        tag: active.tagName,
        id: active.id || "",
        cls: String(active.className || "").slice(0, 40),
        outlineStyle: style.outlineStyle,
        outlineWidth: parseFloat(style.outlineWidth) || 0,
        visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden",
      };
    });
    if (state && state.visible) seen.push(state);
  }
  assert(seen.length >= 6, `${label}: keyboard tab order stopped (${seen.length} stops)`);
  for (const item of seen) {
    assert(item.outlineStyle !== "none" && item.outlineWidth >= 2,
      `${label}: ${item.tag} ${item.id || item.cls} has no focus ring (${item.outlineStyle}/${item.outlineWidth})`);
  }
}

async function reducedMotion(page, label) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await page.evaluate(() => {
    const button = document.querySelector(".primary, .ghost");
    const animated = document.querySelector(".rights-tick, .live-dot, .clean-fill-dot");
    return {
      scroll: getComputedStyle(document.documentElement).scrollBehavior,
      transition: button ? getComputedStyle(button).transitionDuration : "",
      animation: animated ? getComputedStyle(animated).animationName : "",
    };
  });
  assert(state.scroll === "auto", `${label}: reduced motion kept smooth scroll (${state.scroll})`);
  assert(state.transition === "0s" || state.transition === "",
    `${label}: reduced motion kept a transition (${state.transition})`);
  assert(state.animation === "none" || state.animation === "",
    `${label}: reduced motion kept an animation (${state.animation})`);
}

async function sourceRun(viewport) {
  const { context, page, pageErrors, consoleErrors, setScan, setSourceStatus } = await stubContext(viewport, true);
  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.body.classList.contains("source-mode")
      && document.querySelectorAll("#clean-found .clean-found-row").length === 2,
  null, { timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelector("#clean-scrub")?.value === "2",
  null, { timeout: 10000 }).catch(() => {});
  const label = `source ${viewport.width}×${viewport.height}`;

  const initial = await page.evaluate(() => ({
    value: document.querySelector("#clean-scrub")?.value || "",
    times: [...document.querySelectorAll("#clean-found .clean-found-time")].map((node) => node.textContent),
    stage: document.querySelector("#clean-stage-time")?.textContent || "",
    state: document.querySelector("#clean-frame-state")?.textContent || "",
  }));
  assert(initial.value === "2",
    `${label}: Clean did not open on the first text row (${JSON.stringify(initial)})`);
  assert(!/No text row at 0:00/.test(initial.state),
    `${label}: a text row was present but the no-text-row note showed`);

  await layout(page, viewport, label);
  const primaries = await page.evaluate(() =>
    [...document.querySelectorAll(".primary")]
      .filter((node) => node.offsetParent !== null && !node.hidden).length);
  assert(primaries === 1, `${label}: ${primaries} primary actions in Source Clean`);
  await reducedMotion(page, label);
  const scrollBehaviors = await page.evaluate(() => {
    const seen = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function scrollSpy(options) {
      seen.push((options && options.behavior) || "auto");
      return original.call(this, options);
    };
    const row = document.querySelector("#clean-found .clean-found-row");
    if (row) row.click();
    Element.prototype.scrollIntoView = original;
    return seen;
  });
  assert(scrollBehaviors.length > 0 && scrollBehaviors.every((value) => value === "auto"),
    `${label}: reduced motion still asked for ${JSON.stringify(scrollBehaviors)}`);
  await checkTypeAndFocus(page, label);

  const vi = await page.evaluate(() => {
    localStorage.setItem("vibecut.ui_lang", "vi");
    const values = [
      "No baked-in text found. Re-rendering with the existing Clean boxes.",
      "Review the low-confidence rows. Tick the ones to remove, then use the Clean action again.",
      "No text row at 0:00. Scrub the frame or scan again.",
      "No render baseline on this browser. Render again to confirm this cut matches.",
      "Changed since this render. The older file is still available; render again to update it.",
    ].map((text) => window.VibeCutI18N.translateValue(text));
    localStorage.setItem("vibecut.ui_lang", "en");
    return values;
  });
  vi.forEach((text, index) => {
    assert(/[à-ỹ]/i.test(text), `${label}: Vietnamese entry ${index} is not translated (${text})`);
  });

  // A live run must keep the Download inside the viewport at desktop sizes.
  await page.locator("#source-clean-run").click();
  await page.locator("#source-clean-result").waitFor({ state: "visible", timeout: 30000 });
  const download = await page.locator("#source-clean-download").boundingBox();
  assert(download && download.y + download.height <= viewport.height + 1,
    `${label}: Download sits below the fold (${JSON.stringify(download)})`);
  assert(await page.evaluate(() => document.querySelectorAll(".primary:not([hidden])").length) >= 1,
    `${label}: no primary action after ready`);

  // A scan that finds nothing must explain the missing 0:00 text row instead of hiding it.
  setScan(EMPTY_SCAN);
  setSourceStatus("idle");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() =>
    document.querySelector("#source-clean-result")?.hidden === false,
  null, { timeout: 30000 });
  await page.waitForFunction(() =>
    /No text row at 0:00/.test(document.querySelector("#clean-frame-state")?.textContent || ""),
  null, { timeout: 10000 }).catch(() => {});
  const zero = await page.evaluate(() => ({
    value: document.querySelector("#clean-scrub")?.value || "",
    note: document.querySelector("#clean-frame-state")?.textContent || "",
    output: document.querySelector("#source-clean-output")?.textContent || "",
  }));
  assert(zero.value === "0", `${label}: empty scan did not open at 0:00 (${zero.value})`);
  assert(/No text row at 0:00/.test(zero.note),
    `${label}: empty scan did not explain the missing text row (${zero.note})`);
  assert(/No baked-in text found/.test(zero.output),
    `${label}: empty scan output is ${zero.output}`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(consoleErrors.length === 0, `${label}: console errors: ${consoleErrors.join(" | ")}`);
  await context.close();
  console.log(`ok phase5 ${label}`);
}

async function cutRun(viewport) {
  const { context, page, pageErrors, consoleErrors } = await stubContext(viewport, false);
  await page.goto(`${base}/#job=j1`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() =>
    document.querySelectorAll("#clean-found .clean-found-row").length === 1,
  null, { timeout: 30000 });
  const label = `cut ${viewport.width}×${viewport.height}`;

  await page.locator("#result-mode-clean").click();
  await page.waitForFunction(() => document.body.classList.contains("cut-clean-mode"),
    null, { timeout: 20000 });
  await page.waitForFunction(() =>
    document.querySelector("#clean-scrub")?.value === "1",
  null, { timeout: 10000 }).catch(() => {});
  const initial = await page.evaluate(() => document.querySelector("#clean-scrub")?.value || "");
  assert(initial === "1",
    `${label}: Cut Clean did not open on the first text row (${initial})`);

  const box = await layout(page, viewport, label);
  assert(box.settings && box.settings.bottom <= viewport.height + 1,
    `${label}: the bottom sheet runs past the viewport`);

  // The sticky action stays reachable after the rail scrolls to its end.
  await page.evaluate(() => {
    const pane = document.querySelector(".editor-pane-settings");
    if (pane) pane.scrollTop = pane.scrollHeight;
  });
  const sticky = await page.locator("#cut-clean-run").boundingBox();
  assert(sticky && sticky.y >= 0 && sticky.y + sticky.height <= viewport.height + 1,
    `${label}: the sticky primary left the viewport (${JSON.stringify(sticky)})`);

  const primaries = await page.evaluate(() =>
    [...document.querySelectorAll(".primary")]
      .filter((node) => node.offsetParent !== null && !node.hidden).length);
  assert(primaries === 1, `${label}: ${primaries} primary actions in Clean`);

  await reducedMotion(page, label);
  await checkTypeAndFocus(page, label);

  // Double-click opens the detail; Escape closes it and keeps focus in the list.
  await page.locator('#clean-found [data-found-index="0"]').dblclick();
  await page.locator("#clean-detail").waitFor({ state: "visible", timeout: 10000 });
  await page.keyboard.press("Escape");
  assert(await page.locator("#clean-detail").isHidden(), `${label}: Escape kept the detail open`);

  // Escape closes the job menu and returns focus to More.
  await page.locator("#job-menu-open").click();
  assert(await page.locator("#job-menu").isVisible(), `${label}: the job menu did not open`);
  await page.keyboard.press("Escape");
  assert(await page.locator("#job-menu").isHidden(), `${label}: Escape kept the job menu open`);
  const focusId = await page.evaluate(() => document.activeElement?.id || "");
  assert(focusId === "job-menu-open", `${label}: Escape did not return focus to More (${focusId})`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);
  assert(consoleErrors.length === 0, `${label}: console errors: ${consoleErrors.join(" | ")}`);
  await context.close();
  console.log(`ok phase5 ${label}`);
}

try {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1050, height: 800 },
    { width: 900, height: 800 },
  ]) {
    await sourceRun(viewport);
  }
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1050, height: 800 },
    { width: 900, height: 800 },
  ]) {
    await cutRun(viewport);
  }
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
