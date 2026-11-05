/**
 * C2b · AI fill on a machine where the models are ready.
 *
 * The model pack is not installed on this Mac, so this spec mocks the three
 * routes that would touch it — engine status, the one-frame LaMa preview — and
 * asserts the founder's path: tick the subtitle, remove it with AI fill and
 * LaMa, compare one frame, and read the copy that says
 * the stage box is not the filled picture. The frame route stays real.
 *
 * Exit 0 passes, exit 2 means this host cannot run Playwright (skip).
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

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function json(payload, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(payload) };
}

const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==";

const SCAN_REPORT = {
  status: "ready",
  complete: true,
  message: "",
  progress: 1,
  text: { confirmed: true, tracklets: 2, present: true },
  tracklets: [{ id: 1 }, { id: 2 }],
  clean_prefill: [
    {
      tracklet_id: "t1",
      kind: "subtitle",
      box: { x: 0.1, y: 0.74, w: 0.8, h: 0.16 },
      ranges: [{ start: 0.5, end: 8.0 }],
      action: "plate",
      enabled: true,
      confidence: 0.9,
      reason: "Burned-in subtitles sit in the new caption zone.",
      blocked: null,
    },
    {
      tracklet_id: "t2",
      kind: "watermark",
      box: { x: 0.78, y: 0.03, w: 0.18, h: 0.06 },
      ranges: [{ start: 0.0, end: 24.0 }],
      action: "refused",
      enabled: false,
      confidence: 0.9,
      reason: "Use your original file — it has no watermark.",
      blocked: "watermark",
    },
  ],
  error: null,
};

const FILL_STATUS = {
  available: true,
  path: "/models/fill",
  missing: [],
  files: [],
  engines: {
    lama: {
      id: "lama", label: "LaMa", ready: true, reason: "", model: true,
      runtime: "onnxruntime", runtime_installed: true,
    },
  },
  default: "lama",
  preview: "lama",
  methods: ["blur", "crop", "lama"],
  note: "AI fill is ready with LaMa.",
};

async function run() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  const pageErrors = [];
  const previewBodies = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  await page.route(/\/api\/jobs\/[^/]+\/check$/, (route) => route.fulfill(json(SCAN_REPORT)));
  await page.route(/\/api\/classic\/fill$/, (route) => route.fulfill(json(FILL_STATUS)));
  await page.route(/\/api\/classic\/jobs\/[^/]+\/fill\/preview$/, async (route) => {
    previewBodies.push(JSON.parse(route.request().postData() || "{}"));
    return route.fulfill(json({
      before: PNG, after: PNG, width: 540, height: 960, time: 1,
      method: "lama", render_method: "lama", cached: false,
    }));
  });

  await page.goto(`${base}/#job=${jobId}`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#clean-stage").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => {
    const fill = document.querySelector("#clean-fill");
    return fill && !fill.hidden && /AI fill is ready/.test(fill.textContent || "");
  }, null, { timeout: 20000 });

  const panel = await page.locator("#clean-fill").textContent();
  assert(/LaMa/.test(panel), "the panel hides the engine");
  assert(!/STTN/.test(panel), "the panel still offers STTN");
  assert(/time left shows/.test(panel), "the panel hides what AI fill costs");

  // Tick the found subtitle and remove it with AI fill.
  await page.locator("[data-found-tick]").first().click();
  await page.selectOption("#clean-found-method", "fill");
  assert(await page.locator("#clean-found-engine").count() === 0, "the panel still offers an engine choice");
  await page.locator("[data-found-apply]").click();
  await page.waitForFunction(() => {
    const box = [...document.querySelectorAll("#clean-overlay .clean-box")].pop();
    return box && box.dataset.method === "fill";
  }, null, { timeout: 15000 });
  const boxId = await page.evaluate(() => {
    const box = [...document.querySelectorAll("#clean-overlay .clean-box")].pop();
    return box.dataset.cleanId;
  });
  assert(await page.locator(`[data-clean-row="${boxId}"] [data-clean-engine]`).count() === 0, "the box still offers an engine choice");

  // The stage says why the box is a box and not a filled picture — but only on
  // a frame the fill is active on, so move the playhead inside the scan range.
  await page.evaluate(() => {
    const scrub = document.querySelector("#clean-scrub");
    scrub.value = "4";
    scrub.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const frameHeaders = [];
  const frameBodies = [];
  page.on("request", (request) => {
    if (/\/frame$/.test(new URL(request.url()).pathname)) {
      frameBodies.push(request.postData() || "");
    }
  });
  page.on("response", (response) => {
    if (/\/frame$/.test(new URL(response.url()).pathname)) {
      frameHeaders.push(response.headers()["x-vibecut-fill"]);
    }
  });
  try {
    await page.waitForFunction(() => {
      const note = document.querySelector("#clean-fill-note");
      return note && !note.hidden && /filled picture appears in the render/.test(note.textContent || "");
    }, null, { timeout: 20000 });
  } catch (error) {
    const diag = await page.evaluate(() => ({
      note: document.querySelector("#clean-fill-note")?.outerHTML || "none",
      status: document.querySelector("#clean-status")?.textContent || "",
      frame: document.querySelector("#clean-frame-state")?.textContent || "",
      time: document.querySelector("#clean-stage-time")?.textContent || "",
      boxes: [...document.querySelectorAll("#clean-overlay .clean-box")].map((box) => ({
        id: box.dataset.cleanId, method: box.dataset.method,
      })),
    }));
    throw new Error(`${error.message} ${JSON.stringify(diag)} headers=${JSON.stringify(frameHeaders)} body=${frameBodies[frameBodies.length - 1] || ""}`);
  }

  // Preview one frame.
  await page.locator("#clean-fill-preview").click();
  await page.waitForFunction(() => document.querySelectorAll(".clean-fill-compare img").length === 2,
    null, { timeout: 20000 });
  const compare = await page.evaluate(() => {
    const images = [...document.querySelectorAll(".clean-fill-compare img")];
    const captions = [...document.querySelectorAll(".clean-fill-compare figcaption")].map((item) => item.textContent.trim());
    const fillText = document.querySelector("#clean-fill").textContent || "";
    return {
      srcs: images.map((image) => image.getAttribute("src") || ""),
      captions,
      copy: /Preview uses LAMA\. The render uses the same engine/.test(fillText),
    };
  });
  assert(compare.srcs.every((src) => src.startsWith("data:image/png")), "the preview images are not pictures");
  assert(compare.captions.join("|") === "Before|After", `the preview captions are ${compare.captions.join("|")}`);
  assert(compare.copy, "the preview hides that the render uses the same engine");

  const body = previewBodies[previewBodies.length - 1] || {};
  const sent = (body.clean || []).find((layer) => layer.method === "fill");
  assert(sent, "the preview did not send the fill box");
  assert(sent.engine === "lama", `the preview sent engine ${sent.engine}`);
  assert(Array.isArray(body.clips) && body.clips.length, "the preview sent no clips");
  assert(!("box" in body), "the preview still sends the old single-box body");

  assert(pageErrors.length === 0, `page errors: ${pageErrors.join(" | ")}`);

  if (shotDir) {
    const { mkdir } = await import("node:fs/promises");
    await mkdir(shotDir, { recursive: true }).catch(() => {});
    await page.screenshot({ path: `${shotDir}/classic-fill-ready.png` });
  }
  await context.close();
  console.log("ok fill ready");
}

try {
  await run();
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
