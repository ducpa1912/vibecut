/**
 * Phase 2 gate scenarios that need a real browser: long-video confirmation,
 * unconfirmed OCR, no text, scan cancel, failed scan, missing media and the
 * ready-cut route after Make a reel. No media file is generated or committed.
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
  return { status, contentType: "application/json", body: JSON.stringify(payload) };
}

const JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==";
const JPEG_BYTES = Buffer.from(JPEG_BASE64, "base64");
const JPEG_DATA = `data:image/jpeg;base64,${JPEG_BASE64}`;

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

function sourceJob(id, duration, status = "source_ready") {
  return {
    id,
    created: 1,
    updated: 1,
    status,
    progress: 1,
    message: status === "source_ready" ? "Source ready" : status,
    error: null,
    mode: "clean",
    source: {
      name: `${id}.mp4`, duration, width: 1280, height: 720, fps: 30,
      has_audio: true, size: 2048,
    },
    options: {},
    analysis: null,
    renders: {},
    artifacts: {},
    artifact_ids: [],
    source_clean: { status: "idle", progress: 0, message: "No Source Clean render has run." },
  };
}

function report(confidence = 0.9, confirmed = true) {
  return {
    status: "ready",
    complete: true,
    message: "",
    progress: 1,
    text: { confirmed, tracklets: confirmed ? 1 : 0, present: confirmed },
    tracklets: confirmed ? [{ id: 1 }] : [],
    clean_prefill: confirmed ? [{
      tracklet_id: "t1",
      kind: "subtitle",
      box: { x: 0.1, y: 0.7, w: 0.8, h: 0.2 },
      ranges: [{ start: 0.5, end: 8.0 }],
      action: "blur",
      enabled: true,
      confidence,
    }] : [],
  };
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  console.error(`SKIP: Chromium did not launch: ${error?.message || error}`);
  process.exit(2);
}

const consoleErrors = [];

async function install(page, job, options = {}) {
  const id = job.id;
  let statusReads = 0;
  let checkReads = 0;
  let cancelCalled = false;
  let scanCancelCalled = false;
  let jobReads = 0;
  const calls = {
    render: 0, renderBodies: [], scanCancel: 0, cancel: 0, analyze: 0,
    estimate: 0, fillPreview: 0, frameBodies: [],
  };

  await page.route(/\/api\/.*/, (route) => route.fulfill(json({ detail: "not found" }, 404)));

  await page.route(new RegExp(`/api/jobs/${id}$`), (route) => {
    jobReads += 1;
    if (jobReads > 1 && options.jobAfterAnalyze) {
      return route.fulfill(json(options.jobAfterAnalyze));
    }
    return route.fulfill(json(job));
  });
  await page.route(new RegExp(`/api/jobs/${id}/check$`), (route) => {
    if (route.request().method() === "POST") {
      if (options.scanPost) return route.fulfill(options.scanPost);
      return route.fulfill(json(options.scan || report()));
    }
    if (scanCancelCalled && options.reloadCancelled) {
      return route.fulfill(json({
        status: "cancelled",
        complete: false,
        progress: 1,
        message: "Cancelled",
        text: { confirmed: false, present: false, tracklets: 0 },
        tracklets: [],
        clean_prefill: [],
      }));
    }
    checkReads += 1;
    if (options.checkGet) return route.fulfill(options.checkGet(checkReads));
    return route.fulfill(json(options.scan || report()));
  });
  await page.route(new RegExp(`/api/jobs/${id}/check/cancel$`), (route) => {
    calls.scanCancel += 1;
    scanCancelCalled = true;
    return route.fulfill(json({ status: "cancelled" }));
  });
  await page.route(new RegExp(`/api/jobs/${id}/analyze$`), (route) => {
    calls.analyze += 1;
    return route.fulfill(json({
      ok: true,
      id,
      status: options.analyzeStatus || "queued",
      started: true,
    }, options.analyzeStatus === "ready" ? 200 : 202));
  });
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(
    options.fillAvailable === false
      ? {
        available: false,
        missing: ["LaMa"],
        files: [],
        engines: {
          lama: {
            id: "lama", ready: false,
            reason: "lama_fp32.onnx is missing from the model folder.",
          },
        },
        default: null,
        preview: null,
        methods: ["blur"],
        note: "AI fill needs its model pack.",
      }
      : FILL,
  )));
  await page.route(new RegExp(`/api/classic/jobs/${id}/text$`), (route) =>
    route.fulfill(json({ cut: { overlays: [], effects: [], clean: [] } })));

  await page.route(new RegExp(`/api/classic/jobs/${id}/fill/estimate$`), async (route) => {
    calls.estimate += 1;
    if (options.estimateDelay) await new Promise((resolve) => setTimeout(resolve, options.estimateDelay));
    return route.fulfill(json(options.estimate || {
      method: "lama", estimate_seconds: 120, seconds: 120, measured: true,
    }));
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/fill/preview$`), (route) => {
    calls.fillPreview += 1;
    return route.fulfill(json({
      before: JPEG_DATA, after: JPEG_DATA, width: 1280, height: 720,
      time: 1, method: "lama", render_method: "lama", scope: "source",
    }));
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/frame/source$`), (route) => {
    try { calls.frameBodies.push(JSON.parse(route.request().postData() || "{}")); } catch (_) { calls.frameBodies.push({}); }
    return route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: {
        "X-VibeCut-Width": "1280", "X-VibeCut-Height": "720", "X-VibeCut-Fill": "1",
      },
      body: JPEG_BYTES,
    });
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/frame$`), (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      headers: {
        "X-VibeCut-Segment": "0",
        "X-VibeCut-Crop": "0,0,1,1",
        "X-VibeCut-Fill": "0",
      },
      body: JPEG_BYTES,
    }));

  await page.route(new RegExp(`/api/classic/jobs/${id}/clean/source/render$`), (route) => {
    calls.render += 1;
    try { calls.renderBodies.push(JSON.parse(route.request().postData() || "{}")); } catch (_) { calls.renderBodies.push({}); }
    return route.fulfill(json({ status: "queued", progress: 0, message: "Queued for Clean" }, 202));
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/clean/source/cancel$`), (route) => {
    calls.cancel += 1;
    cancelCalled = true;
    return route.fulfill(json({ ok: true, cancelled: true, status: "cancelling" }));
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/clean/source/media`), (route) => {
    if (options.mediaMissing) return route.fulfill(json({ detail: "not ready" }, 404));
    return route.fulfill({
      status: 200,
      contentType: "video/mp4",
      headers: { "content-length": "2048" },
      body: Buffer.alloc(2048, 1),
    });
  });
  await page.route(new RegExp(`/api/classic/jobs/${id}/clean/source$`), (route) => {
    statusReads += 1;
    if (cancelCalled) {
      return route.fulfill(json({ status: "cancelled", progress: 1, message: "Cancelled" }));
    }
    if (options.recordReady) {
      return route.fulfill(json({
        status: "ready", progress: 1, message: "Clean video ready",
        path: "/tmp/last.mp4", url: `/api/classic/jobs/${id}/clean/source/media?v=last`,
        width: 1280, height: 720, duration: job.source.duration, method: "lama",
      }));
    }
    if (options.recordIdle) {
      return route.fulfill(json({
        status: "idle", progress: 0, message: "No Source Clean render has run.",
      }));
    }
    if (statusReads === 1) {
      return route.fulfill(json({ status: "idle", progress: 0, message: "No Source Clean render has run." }));
    }
    if (statusReads === 2) {
      return route.fulfill(json({ status: "running", progress: 0.4, message: "Cleaning text with AI fill" }));
    }
    if (options.readyMissing) {
      return route.fulfill(json({
        status: "ready", progress: 1, message: "Clean video ready",
        path: "/tmp/missing.mp4", url: `/api/classic/jobs/${id}/clean/source/media`,
        width: 1280, height: 720, duration: job.source.duration, method: "lama",
      }));
    }
    return route.fulfill(json({
      status: "ready", progress: 1, message: "Clean video ready",
      path: "/tmp/out.mp4", url: `/api/classic/jobs/${id}/clean/source/media?v=ok`,
      width: 1280, height: 720, duration: job.source.duration, method: "lama",
    }));
  });
  return calls;
}

async function open(page, job) {
  await page.goto(`${base}/#job=${job.id}`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
}

async function newPage(viewport, job, options) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  const checkStatuses = [];
  page.on("pageerror", (error) => errors.push(String(error?.message || error)));
  page.on("response", (response) => {
    if (/\/api\/jobs\/[^/]+\/check$/.test(response.url()) && response.status() >= 400) {
      checkStatuses.push(response.status());
    }
  });
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Intentional stub statuses (404/500 from gate routes) are network noise,
    // not page errors. Every other console error still fails the spec.
    if (/^Failed to load resource:/.test(message.text())) return;
    consoleErrors.push(message.text());
  });
  const calls = await install(page, job, options);
  return { context, page, errors, checkStatuses, calls };
}

async function longVideo() {
  const job = sourceJob("long", 200);
  const { context, page, calls, errors } = await newPage(
    { width: 1440, height: 900 }, job,
    {
      estimate: { method: "lama", estimate_seconds: null, seconds: null, measured: false },
      estimateDelay: 350,
    },
  );
  await open(page, job);
  await page.waitForFunction(() => /Clean 1 text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => /Estimating…/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.waitForFunction(() => /estimate unavailable/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  assert(calls.render === 0, "long video rendered before the second click");
  const confirmState = await page.evaluate(() => ({
    layers: document.querySelectorAll("#clean-layers .clean-row").length,
    cleaned: document.querySelectorAll("#clean-found .clean-found-blocked.is-added").length,
  }));
  assert(confirmState.layers === 0, `long confirm shows ${confirmState.layers} layers`);
  assert(confirmState.cleaned === 0, `long confirm shows ${confirmState.cleaned} cleaned badges`);
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => document.querySelector("#source-clean-result")?.hidden === false,
    null, { timeout: 30000 });
  assert(calls.render === 1, `long video made ${calls.render} renders`);
  const afterConfirm = await page.evaluate(() => document.querySelectorAll("#clean-layers .clean-row").length);
  assert(afterConfirm > 0, "the second click did not apply the ticked layers");
  assert(errors.length === 0, `long video errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates long-video");
}

async function unconfirmed() {
  const job = sourceJob("unconfirmed", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job,
    { scan: report(0.4, false) },
  );
  await open(page, job);
  await page.waitForFunction(() => /Rescan text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => /could not confirm/.test(document.querySelector("#source-clean-summary").textContent || ""),
    null, { timeout: 20000 });
  assert(calls.render === 0, "unconfirmed OCR rendered");
  assert(/could not confirm/.test(await page.locator("#clean-empty p").textContent()),
    "the empty state does not name the unconfirmed scan");
  assert(errors.length === 0, `unconfirmed errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates unconfirmed");
}

async function noText() {
  const job = sourceJob("empty", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job, { scan: report(0.9, true) },
  );
  // A confirmed report with no rows is the real no-text state.
  const empty = report(0.9, true);
  empty.clean_prefill = [];
  empty.tracklets = [];
  await page.unroute(/\/api\/jobs\/empty\/check$/);
  await page.route(/\/api\/jobs\/empty\/check$/, (route) => route.fulfill(json(empty)));
  await open(page, job);
  await page.waitForFunction(() => document.querySelector("#source-clean-result")?.hidden === false,
    null, { timeout: 20000 });
  const output = await page.locator("#source-clean-output").textContent();
  assert(/No baked-in text found/.test(output), `no-text output is ${output}`);
  assert(calls.render === 0, "no-text rendered");
  assert(errors.length === 0, `no-text errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates no-text");
}

async function scanCancel() {
  const job = sourceJob("scancancel", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job,
    {
      checkGet: (reads) => (reads === 1 ? json({ detail: "no report" }, 404) : json({ status: "running" }, 202)),
      scanPost: json({ status: "running" }, 202),
      reloadCancelled: true,
      recordIdle: true,
    },
  );
  await open(page, job);
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => !document.querySelector("#source-clean-cancel").hidden,
    null, { timeout: 20000 });
  await page.locator("#source-clean-cancel").click();
  await page.waitForFunction(() => /Scan cancelled/.test(document.querySelector("#source-clean-summary").textContent || ""),
    null, { timeout: 20000 });
  assert(calls.scanCancel === 1, `scan cancel route called ${calls.scanCancel} times`);
  assert(calls.render === 0, "scan cancel rendered");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => document.body.classList.contains("source-mode"),
    null, { timeout: 20000 });
  const reloaded = await page.evaluate(() => ({
    copy: document.querySelector("#clean-empty p").textContent,
    action: document.querySelector("#source-clean-run").textContent,
    body: document.body.textContent,
  }));
  assert(/Scan cancelled/.test(reloaded.copy),
    `cancelled reload copy is ${reloaded.copy}`);
  assert(!/could not confirm/.test(reloaded.copy),
    `cancelled reload used the unconfirmed copy: ${reloaded.copy}`);
  assert(/Rescan text/.test(reloaded.action),
    `cancelled reload action is ${reloaded.action}`);
  assert(!/could not confirm/.test(reloaded.body),
    "the cancelled reload still says it could not confirm");
  assert(errors.length === 0, `scan cancel errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates scan-cancel");
}

async function failedScan() {
  const job = sourceJob("scanfail", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job,
    {
      checkGet: () => json({ detail: "no report" }, 404),
      scanPost: json({ detail: "vision crashed" }, 500),
    },
  );
  await open(page, job);
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => /The scan failed/.test(document.querySelector("#source-clean-summary").textContent || ""),
    null, { timeout: 20000 });
  assert(/The scan failed: vision crashed\. Retry the scan; nothing was rendered\./
    .test(await page.locator("#source-clean-summary").textContent()),
  "the scan failure copy is not punctuated");
  assert(/Retry scan/.test(await page.locator("#source-clean-run").textContent()), "failed scan has no retry");
  assert(/scan failed/i.test(await page.locator("#clean-empty p").textContent()),
    "the empty state kept the pre-scan copy after a failure");
  assert(calls.render === 0, "failed scan rendered");
  assert(errors.length === 0, `failed scan errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates failed-scan");
}

async function cancelledRender() {
  const job = sourceJob("cancel", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job, {},
  );
  await open(page, job);
  await page.waitForFunction(() => /Clean 1 text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => !document.querySelector("#source-clean-cancel").hidden,
    null, { timeout: 20000 });
  await page.locator("#source-clean-cancel").click();
  await page.waitForFunction(() => /Clean cancelled/.test(document.querySelector("#source-clean-summary").textContent || ""),
    null, { timeout: 20000 });
  assert(calls.cancel === 1, `render cancel route called ${calls.cancel} times`);
  assert(await page.locator("#source-clean-download").isHidden(), "cancelled render offers a download");
  assert(errors.length === 0, `cancelled errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates cancel-cancelling");
}

async function missingMedia() {
  const job = sourceJob("missing", 10);
  const { context, page, errors } = await newPage(
    { width: 1280, height: 800 }, job, { readyMissing: true, mediaMissing: true },
  );
  await open(page, job);
  await page.waitForFunction(() => /Clean 1 text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => /clean file is missing/.test(document.querySelector("#source-clean-summary").textContent || ""),
    null, { timeout: 30000 });
  assert(/Retry clean/.test(await page.locator("#source-clean-run").textContent()), "missing media has no retry");
  assert(await page.locator("#source-clean-download").isHidden(), "missing media offers a download");
  assert(errors.length === 0, `missing media errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates missing-media");
}

async function failedCleanBackToSource() {
  const job = sourceJob("failedclean", 10, "failed");
  job.message = "Analysis failed";
  job.error = "analysis crashed";
  const { context, page, errors } = await newPage(
    { width: 1280, height: 800 }, job, { recordReady: true },
  );
  await page.goto(`${base}/#job=failedclean`, { waitUntil: "domcontentloaded" });
  await page.locator("#progress-view").waitFor({ state: "visible", timeout: 20000 });
  await page.locator("#progress-source").waitFor({ state: "visible", timeout: 10000 });
  await page.locator("#progress-source").click();
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#source-clean-result").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => document.body.classList.contains("source-mode"),
    null, { timeout: 20000 });
  const result = await page.evaluate(() => ({
    output: document.querySelector("#source-clean-output").textContent,
    summary: document.querySelector("#source-clean-summary").textContent,
    head: document.querySelector("#source-clean-head").hidden,
    resultHidden: document.querySelector("#source-clean-result").hidden,
    shown: document.querySelector("#source-clean-result").hidden === false,
    download: document.querySelector("#source-clean-download").hidden === false,
  }));
  assert(/1280×720/.test(result.output),
    `failed clean output is ${result.output} · ${result.summary} · ${JSON.stringify(result)} · ${errors.join(" | ")}`);
  assert(result.shown && result.download, "the last source result is not reachable");
  assert(errors.length === 0, `failed clean errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates failed-clean-back");
}

async function backCancelsRunning() {
  const job = sourceJob("backcancel", 10);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job, {},
  );
  await open(page, job);
  await page.waitForFunction(() => /Clean 1 text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => !document.querySelector("#source-clean-cancel").hidden,
    null, { timeout: 20000 });
  const cancelRequest = page.waitForRequest((request) =>
    /\/clean\/source\/cancel$/.test(request.url()) && request.method() === "POST");
  await page.locator("#source-back").click();
  await cancelRequest;
  await page.locator("#ingest-view").waitFor({ state: "visible", timeout: 20000 });
  assert(calls.cancel === 1, `back cancel called the route ${calls.cancel} times`);
  assert(errors.length === 0, `back cancel errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates back-cancel");
}

async function idleEnvelope() {
  const job = sourceJob("idleenvelope", 10);
  const { context, page, errors, checkStatuses } = await newPage(
    { width: 1280, height: 800 }, job,
    {
      checkGet: () => json({
        status: "idle",
        report: null,
        complete: false,
        progress: 0,
        message: "No Check report yet for this source.",
        text: { confirmed: false, present: false, tracklets: 0 },
        tracklets: [],
        clean_prefill: [],
      }),
    },
  );
  await open(page, job);
  await page.waitForFunction(() =>
    /Find text & clean/.test(document.querySelector("#source-clean-run").textContent || ""),
  null, { timeout: 20000 });
  assert(checkStatuses.length === 0, `idle first open got check status ${checkStatuses.join(",")}`);
  assert(await page.locator("#clean-found .clean-found-row").count() === 0,
    "the idle envelope rendered rows");
  assert(/No text scan yet/.test(await page.locator("#clean-empty p").textContent()),
    "the idle envelope kept stale empty copy");
  assert(errors.length === 0, `idle envelope errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates idle-envelope");
}

async function blurLong() {
  const job = sourceJob("blurlong", 200);
  const { context, page, calls, errors } = await newPage(
    { width: 1280, height: 800 }, job, { fillAvailable: false },
  );
  await open(page, job);
  await page.waitForFunction(() => /Blur/.test(
    document.querySelector("#clean-found .clean-found-method")?.textContent || "",
  ), null, { timeout: 20000 });
  const row = await page.locator("#clean-found .clean-found-method").first().textContent();
  assert(!/AI fill/.test(row), `blur row says ${row}`);
  assert(await page.locator("[data-found-apply]").count() === 0,
    "source mode still shows Remove ticked");
  assert(await page.locator("#clean-preview-ai").isDisabled(),
    "AI fill button is enabled without the model");
  assert(/lama_fp32\.onnx/.test(await page.locator("#clean-preview-ai").getAttribute("title") || ""),
    "AI fill button hides the missing model reason");

  await page.locator("#source-clean-run").click();
  await page.waitForFunction(() => /Blur needs no fill estimate/.test(
    document.querySelector("#source-clean-summary").textContent || "",
  ), null, { timeout: 20000 });
  assert(calls.estimate === 0, `blur-only long video called estimate ${calls.estimate} times`);
  assert(calls.render === 0, "blur-only long video rendered before the second click");
  await page.locator("#source-clean-run").click();
  await page.locator("#source-clean-result").waitFor({ state: "visible", timeout: 30000 });
  assert(calls.render === 1 && calls.renderBodies[0].clean[0].method === "blur",
    `blur render method is ${calls.renderBodies[0]?.clean?.[0]?.method}`);

  const before = await page.locator("#clean-frame").getAttribute("src");
  await page.locator("#clean-preview-before").click();
  await page.waitForFunction(() => (document.querySelector("#clean-frame").getAttribute("src") || "").startsWith("blob:"),
    null, { timeout: 20000 });
  await page.locator("#clean-preview-after").click();
  await page.waitForFunction((previous) => {
    const src = document.querySelector("#clean-frame").getAttribute("src") || "";
    return src.startsWith("blob:") && src !== previous;
  }, before, { timeout: 20000 });
  assert(calls.fillPreview === 0, "blur After called the fill preview");
  const beforeBody = calls.frameBodies[0] || {};
  const afterBody = calls.frameBodies[calls.frameBodies.length - 1] || {};
  assert(Array.isArray(beforeBody.clean) && beforeBody.clean.length === 0,
    `Before carried ${beforeBody.clean?.length} layers`);
  assert(Array.isArray(afterBody.clean) && afterBody.clean.length > 0,
    "After carried no Clean layers");
  assert(errors.length === 0, `blur long errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates blur-long");
}

async function sourceToCutLeak() {
  const job = sourceJob("leak", 10);
  const ready = {
    ...job,
    status: "ready",
    message: "1 moment · hook found",
    analysis: {
      scene_count: 1,
      deep_count: 1,
      elapsed: 0.1,
      hook_scene: 0,
      engine: {},
      scenes: [{
        id: 0, start: 0, end: 10, dur: 10,
        hook: 80, visual_score: 70, motion_score: 60, audio_score: 50,
        text_score: 40, score: 75, ocr: "", speech: "", tags: [],
        deep: true, crops: {}, crop: { cx: 0.5, cy: 0.5 }, crop_modes: {},
      }],
      plans: {
        30: {
          target: 30, total: 10, clip_count: 1, auto: false,
          clips: [{ scene: 0, start: 0, end: 10, dur: 10, role: "beat" }],
          note: "",
        },
      },
    },
  };
  const { context, page, errors } = await newPage(
    { width: 1280, height: 800 }, job,
    { jobAfterAnalyze: ready, analyzeStatus: "ready" },
  );
  await open(page, job);
  await page.waitForFunction(() => /Clean 1 text/.test(document.querySelector("#source-clean-run").textContent || ""),
    null, { timeout: 20000 });
  await page.locator("#source-clean-run").click();
  await page.locator("#source-clean-result").waitFor({ state: "visible", timeout: 30000 });
  assert(/Prepared/.test(await page.locator("#clean-status").textContent()),
    "the source clean did not leave its status");
  await page.locator("#source-clean-reel").click();
  await page.waitForFunction(() => !document.body.classList.contains("source-mode"),
    null, { timeout: 20000 });
  const cut = await page.evaluate(() => ({
    status: document.querySelector("#clean-status").textContent,
    sourceHead: document.querySelector("#source-clean-head").hidden,
    layers: document.querySelectorAll("#clean-layers .clean-row").length,
  }));
  assert(cut.status === "", `source Clean status leaked into the cut: ${cut.status}`);
  assert(cut.sourceHead, "the source header survived the cut switch");
  assert(cut.layers === 0, `the cut inherited ${cut.layers} source layers`);
  assert(errors.length === 0, `source-to-cut errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates source-to-cut");
}

async function readyCutAfterReel() {
  const id = "readycut";
  const job = {
    id,
    created: 1,
    updated: 1,
    status: "ready",
    progress: 1,
    message: "1 moment · hook found",
    error: null,
    mode: "clean",
    source: {
      name: "ready.mp4", duration: 10, width: 1280, height: 720, fps: 30,
      has_audio: true, size: 2048,
    },
    options: {},
    analysis: {
      scene_count: 1,
      deep_count: 1,
      elapsed: 0.1,
      hook_scene: 0,
      engine: {},
      scenes: [{
        id: 0, start: 0, end: 10, dur: 10,
        hook: 80, visual_score: 70, motion_score: 60, audio_score: 50,
        text_score: 40, score: 75, ocr: "", speech: "", tags: [],
        deep: true, crops: {}, crop: { cx: 0.5, cy: 0.5 }, crop_modes: {},
      }],
      plans: {
        30: {
          target: 30, total: 10, clip_count: 1, auto: false,
          clips: [{ scene: 0, start: 0, end: 10, dur: 10, role: "beat" }],
          note: "",
        },
      },
    },
    renders: {},
    artifacts: {},
    artifact_ids: [],
  };
  const { context, page, errors } = await newPage({ width: 1280, height: 800 }, job, {});
  await open(page, job);
  await page.waitForFunction(() => !document.body.classList.contains("source-mode"),
    null, { timeout: 20000 });
  await page.waitForFunction(() => document.querySelectorAll("#clean-found .clean-found-row").length === 1,
    null, { timeout: 20000 });
  const foundRow = await page.evaluate(() => {
    const row = document.querySelector("#clean-found .clean-found-row");
    const thumb = row?.querySelector(".clean-found-thumb");
    return {
      text: row?.textContent || "",
      style: thumb?.getAttribute("style") || "",
      tick: Boolean(row?.querySelector("[data-found-tick]")),
    };
  });
  assert(foundRow.tick, "the ready cut row has no tick");
  assert(/background-size:/.test(foundRow.style),
    `the ready cut row has no thumbnail style: ${foundRow.style}`);
  await page.locator('[data-found-index="0"] [data-found-tick="0"]').check();
  assert(await page.locator('[data-found-index="0"] [data-found-tick="0"]').isChecked(),
    "the ready cut row cannot be ticked");
  const state = await page.evaluate(() => ({
    source: document.body.classList.contains("source-mode"),
    head: document.querySelector("#source-clean-head").hidden,
    title: document.querySelector("#result-title").textContent,
    result: document.querySelector("#result-view").hidden,
  }));
  assert(!state.source, "a ready clean job opened Source Clean");
  assert(state.head, "the source header shows on a ready cut");
  assert(!state.result, "the ready cut result is hidden");
  assert(state.title.length > 0, "the ready cut has no title");
  assert(errors.length === 0, `ready cut errors: ${errors.join(" | ")}`);
  await context.close();
  console.log("ok gates ready-cut");
}

try {
  await longVideo();
  await unconfirmed();
  await noText();
  await scanCancel();
  await failedScan();
  await cancelledRender();
  await missingMedia();
  await failedCleanBackToSource();
  await backCancelsRunning();
  await idleEnvelope();
  await blurLong();
  await sourceToCutLeak();
  await readyCutAfterReel();
  assert(consoleErrors.length === 0, `console errors: ${consoleErrors.join(" | ")}`);
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
