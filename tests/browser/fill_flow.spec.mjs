/**
 * P2 fill flow in Chromium: found text with thumbnails and ticks, Remove all
 * with the chosen method, then the one-frame AI-fill before/after slider.
 *
 * The Check report, fill status, thumbnail and fill preview are fulfilled by
 * the test so no model or OCR run is needed. The Edit save is real.
 */

import process from "node:process";

const base = String(process.env.FILL_BASE_URL || "").replace(/\/$/, "");
const jobId = String(process.env.FILL_JOB_ID || "j1");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
const screenshot = process.env.FILL_SCREENSHOT || "";

function skip(message) {
  console.error(`SKIP: ${message}`);
  process.exit(2);
}

if (!base) skip("FILL_BASE_URL is not set");
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

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

const gif = "R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
const previewImage = (colour) => (
  "data:image/svg+xml;base64," + Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="540" height="960">`
    + `<rect width="540" height="960" fill="${colour}"/>`
    + `<rect x="60" y="760" width="420" height="90" fill="#111"/>`
    + `</svg>`,
  ).toString("base64")
);
const report = {
  schema: 1,
  status: "ready",
  complete: true,
  job_id: jobId,
  created: 1,
  text: { confirmed: true, present: true },
  tracklets: [
    {
      id: "trk_sub",
      kind: "subtitle",
      box: { x: 0.1, y: 0.76, w: 0.8, h: 0.09 },
      ranges: [{ start: 0, end: 24 }],
      text_sample: "Hello subtitle",
      confidence: 0.9,
      samples: 4,
      duration: 24,
    },
    {
      id: "trk_water",
      kind: "watermark",
      box: { x: 0.84, y: 0.05, w: 0.13, h: 0.05 },
      ranges: [{ start: 0, end: 24 }],
      text_sample: "TikTok",
      confidence: 0.9,
      samples: 4,
      duration: 24,
    },
    {
      id: "trk_ui",
      kind: "screen_text",
      box: { x: 0.05, y: 0.03, w: 0.2, h: 0.05 },
      ranges: [{ start: 0, end: 24 }],
      text_sample: "Search",
      confidence: 0.9,
      samples: 4,
      duration: 24,
    },
  ],
  clean_prefill: [],
};
const captured = {};

const pageErrors = [];
let page;
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(({ id }) => {
    localStorage.setItem("vibecut.studio.job", JSON.stringify({
      id, name: "fill-flow-fixture.mp4", status: "ready",
    }));
  }, { id: jobId });
  page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  page.on("request", (req) => {
    if (req.method() === "PATCH" && req.url().includes("/edits/")) {
      captured.patches = (captured.patches || 0) + 1;
    }
  });

  await page.route(new RegExp(`/api/jobs/${jobId}/check$`), (route) => (
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(report) })
  ));
  await page.route("**/api/fill/status", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      methods: {
        sttn: { id: "sttn", label: "STTN (video)", ready: true, reason: "" },
        lama: { id: "lama", label: "LaMa (per frame)", ready: true, reason: "" },
      },
      default: "lama",
      preview: "lama",
      models_dir: "/tmp/models",
    }),
  }));
  await page.route(new RegExp(`/api/jobs/${jobId}/check/tracklets/[^/]+/thumb(?:\\?.*)?$`), (route) => (
    route.fulfill({ status: 200, contentType: "image/gif", body: Buffer.from(gif, "base64") })
  ));
  await page.route(new RegExp(`/api/jobs/${jobId}/edits/[^/]+/auto-clean$`), (route) => {
    captured.autoBody = route.request().postDataJSON();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layers: [{
          id: "cl_trk_sub",
          kind: "fill",
          method: "lama",
          box: { x: 0.1, y: 0.76, w: 0.8, h: 0.09 },
          ranges: [{ start: 0, end: 24 }],
          z: 0,
          color: "#000000",
          opacity: 1,
          radius: 12,
          label: "Remove text",
          tracklet_id: "trk_sub",
          tracklet_kind: "subtitle",
        }],
        added: 1,
        skipped: [],
        warnings: [],
      }),
    });
  });
  await page.route(new RegExp(`/api/jobs/${jobId}/edits/[^/]+/fill-preview$`), (route) => {
    captured.previewBody = route.request().postDataJSON();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        before: previewImage("#444"),
        after: previewImage("#2d6a4f"),
        width: 540,
        height: 960,
        time: 0.033,
        method: "lama",
        cached: false,
      }),
    });
  });

  await page.goto(`${base}/#/edit`, { waitUntil: "domcontentloaded" });
  await page.locator(".st-edit-panel").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(
    () => document.querySelectorAll(".st-found-row").length === 3,
    null,
    { timeout: 30000 },
  );

  const blocked = page.locator(".st-found-row.is-blocked");
  assert(await blocked.count() === 2, "watermark and screen UI should be blocked");
  const blockedText = await page.locator(".st-found-row.is-blocked .st-found-meta").first().textContent();
  assert(/Watermark|Screen UI/.test(blockedText || ""), "blocked rows need a plain reason");
  assert(await page.locator(".st-found-tick:checked").count() === 1,
    "only the allowed subtitle should start ticked");
  assert(await page.locator(".st-found-method").inputValue() === "ai",
    "AI fill should be the default method when its model is ready");
  await page.locator(".st-found-row .st-found-copy").first().click();
  assert(
    !(await page.locator(".st-found-row .st-found-meta").first().textContent())?.includes("Not in this cut"),
    "row seek with real tracklet ranges must find the cut",
  );
  assert(await page.locator(".st-found-engine").inputValue() === "lama",
    "the default fill engine should come from /api/fill/status");

  await page.locator(".st-auto-clean-run").click();
  await page.locator(".st-found-row.is-added").waitFor({ state: "visible", timeout: 30000 });
  assert(captured.autoBody?.method === "ai", "Remove all sent the wrong method");
  assert(captured.autoBody?.fill_method === "lama", "Remove all sent the wrong engine");
  assert(
    JSON.stringify(captured.autoBody?.tracklet_ids) === JSON.stringify(["trk_sub"]),
    "Remove all sent the wrong tracklets",
  );

  // Painter QA: create a mask on the detected subtitle and confirm it saves.
  await page.locator(".st-found-paint").first().click();
  const paintCanvas = page.locator("#st-preview-canvas");
  const paintBox = await paintCanvas.boundingBox();
  assert(paintBox && paintBox.width > 100, "preview is not measurable for painting");
  await page.mouse.move(
    paintBox.x + paintBox.width * 0.35,
    paintBox.y + paintBox.height * 0.78,
  );
  await page.mouse.down();
  await page.mouse.move(
    paintBox.x + paintBox.width * 0.65,
    paintBox.y + paintBox.height * 0.80,
    { steps: 12 },
  );
  await page.mouse.up();
  await page.waitForTimeout(1600);
  const painter = await page.evaluate(async (id) => {
    const sets = await (await fetch(`/api/jobs/${encodeURIComponent(id)}/clip-sets`)).json();
    const set = (sets.clip_sets || [])[0];
    const story = (set?.stories || [])[0];
    if (!set || !story) return { error: "no story" };
    const current = await (await fetch(
      `/api/jobs/${encodeURIComponent(id)}/edits/current?set_id=${encodeURIComponent(set.id)}`
      + `&story_id=${encodeURIComponent(story.id)}&aspect=9%3A16`,
    )).json();
    const edit = current.edit || current;
    const pointCount = (layer) => {
      const mask = layer.mask;
      if (!mask) return 0;
      if (Array.isArray(mask)) return mask.length;
      return (mask.strokes || []).reduce((sum, stroke) => sum + (stroke.points || []).length, 0);
    };
    return {
      layers: (edit.clean || []).length,
      masks: (edit.clean || []).filter((layer) => pointCount(layer) > 0).length,
      points: (edit.clean || []).reduce((sum, layer) => sum + pointCount(layer), 0),
      ids: (edit.clean || []).map((layer) => layer.id),
    };
  }, jobId);
  assert(painter.layers > 0, "painter did not create a clean layer");
  assert(painter.masks > 0, "painter mask did not save");
  assert(painter.points >= 2, `painter saved too few points (${painter.points})`);

  assert(
    await page.locator(".st-found-row.is-painted .st-found-paint:disabled").count() === 1,
    "the painted detected row must disable its brush",
  );
  // The row already had a layer from Remove all, so the brush reuses it.
  const paintLayerId = painter.ids.find((id) => id === "cl_trk_sub") || "";
  assert(paintLayerId, "the brush did not reuse the found text's layer");
  assert(painter.ids.filter((id) => String(id).startsWith("cl_paint_")).length === 0, "the brush added a second layer");
  const patchesBefore = captured.patches || 0;
  await page.locator(".st-clean-compare").click();
  await page.locator("#st-preview-compare").waitFor({ state: "visible", timeout: 30000 });
  assert(
    JSON.stringify(captured.previewBody?.layer_ids) === JSON.stringify([paintLayerId]),
    `comparison must scope to the selected layer (${JSON.stringify(captured.previewBody?.layer_ids)})`,
  );
  assert(
    Array.isArray(captured.previewBody?.clean) && captured.previewBody.clean.length > 0,
    "comparison must send the draft Clean layers without saving",
  );
  assert((captured.patches || 0) === patchesBefore, "comparison saved the Edit before previewing");
  assert(
    await page.locator(".st-compare-before").evaluate((img) => img.complete && img.naturalWidth > 0),
    "the before image did not load",
  );

  if (screenshot) await page.screenshot({ path: screenshot, fullPage: false });
  assert(pageErrors.length === 0, `page errors: ${pageErrors.join(" | ")}`);
  // Each box has its own method, on the box itself.
  const onBox = page.locator('#st-box-method button[data-kind="blur"]');
  assert(await onBox.isVisible(), "the selected box has no method switch");
  await onBox.click();
  await page.waitForFunction(() => (
    document.querySelector('#st-box-method button[data-kind="blur"]')?.classList.contains("is-active")
  ));
  console.log("Found-text list, Remove all and painter mask passed.");
} finally {
  await browser.close();
}
