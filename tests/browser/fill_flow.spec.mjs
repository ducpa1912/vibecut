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

  assert(await page.locator(".st-found-row.is-blocked").count() === 0, "every found text can be cleaned");
  assert(await page.locator(".st-found-tick:checked").count() === 3,
    "every found text should start ticked");
  assert(await page.locator(".st-clean-method .st-method-option.is-active").textContent() === "AI fill",
    "AI fill should be the default method when its model is ready");
  await page.locator(".st-found-row .st-found-copy").first().click();
  assert(
    !(await page.locator(".st-found-row .st-found-meta").first().textContent())?.includes("Not in this cut"),
    "row seek with real tracklet ranges must find the cut",
  );
  await page.locator(".st-clean-more > summary").click();
  assert(await page.locator(".st-found-engine").inputValue() === "lama",
    "the default fill engine should come from /api/fill/status");

  await page.locator(".st-auto-clean-run").click();
  // Text that has a layer folds away, so the list holds only what is left.
  await page.locator(".st-found-added > summary").click({ timeout: 30000 });
  await page.locator(".st-found-row.is-added").waitFor({ state: "visible", timeout: 30000 });
  assert(captured.autoBody?.method === "ai", "Remove all sent the wrong method");
  assert(captured.autoBody?.fill_method === "lama", "Remove all sent the wrong engine");
  assert(
    JSON.stringify([...(captured.autoBody?.tracklet_ids || [])].sort()) === JSON.stringify(["trk_sub", "trk_ui", "trk_water"]),
    "Remove all sent the wrong tracklets",
  );

  // Painter QA: create a mask on the detected subtitle and confirm it saves.
  await page.locator(".st-clean-editor .st-btn", { hasText: /^Paint/ }).first().click();
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

  // The found text's layer is selected after Clean, so the brush uses it.
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
  // Clean and the timeline stay readable, and the Clean lane is in view.
  const tiny = await page.evaluate(() => {
    const out = [];
    for (const scope of document.querySelectorAll(".st-layer-scroll, .st-timeline")) {
      for (const node of scope.querySelectorAll("*")) {
        if (node.children.length || !node.textContent.trim() || !node.getClientRects().length) continue;
        const size = parseFloat(getComputedStyle(node).fontSize);
        if (size < 11) out.push(`${node.className || node.tagName}:${size}`);
      }
    }
    return [...new Set(out)];
  });
  assert(tiny.length === 0, `text under 11 px: ${tiny.join(", ")}`);
  const lane = await page.evaluate(() => {
    const label = document.querySelector(".st-tl-label-clean");
    const scroll = document.querySelector(".st-timeline-scroll");
    if (!label || !scroll) return null;
    const a = label.getBoundingClientRect();
    const b = scroll.getBoundingClientRect();
    return { inView: a.top >= b.top && a.bottom <= b.bottom };
  });
  assert(lane?.inView, "the Clean lane is not in view with Clean open");

  // Each box has its own method, on the box itself. It waits while comparing.
  assert(await page.locator("#st-box-method").isHidden(), "the box switch covers the comparison");
  await page.locator("#st-compare-close").click();
  const onBox = page.locator('#st-box-method button[data-kind="blur"]');
  assert(await onBox.isVisible(), "the selected box has no method switch");
  await onBox.click();
  await page.waitForFunction(() => (
    document.querySelector('#st-box-method button[data-kind="blur"]')?.classList.contains("is-active")
  ));

  // A taller timeline makes its lanes taller, not only its empty space.
  const rectOf = (selector) => page.evaluate((query) => {
    const node = document.querySelector(query);
    if (!node) return null;
    node.scrollIntoView({ block: "nearest" });
    const { x, y, width, height } = node.getBoundingClientRect();
    return { x, y, width, height };
  }, selector);
  const laneBefore = (await rectOf(".st-tl-track-sentences")).height;
  const edge = await rectOf(".st-timeline-resize");
  await page.mouse.move(edge.x + edge.width / 2, edge.y + edge.height / 2);
  await page.mouse.down();
  await page.mouse.move(edge.x + edge.width / 2, edge.y - 200, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(100);
  const laneAfter = (await rectOf(".st-tl-track-sentences")).height;
  assert(laneAfter > laneBefore, `the lanes did not grow: ${laneBefore} to ${laneAfter}`);
  await page.mouse.dblclick(edge.x + edge.width / 2, (await rectOf(".st-timeline-resize")).y + 2);
  await page.waitForTimeout(100);

  // Clean bars sit at story time, and dragging an edge changes the saved range.
  const savedEdit = async () => {
    await page.waitForTimeout(900);
    return page.evaluate(async (id) => {
      const sets = await (await fetch(`/api/jobs/${encodeURIComponent(id)}/clip-sets`)).json();
      const set = (sets.clip_sets || [])[0];
      const story = (set?.stories || [])[0];
      const current = await (await fetch(
        `/api/jobs/${encodeURIComponent(id)}/edits/current?set_id=${encodeURIComponent(set.id)}`
        + `&story_id=${encodeURIComponent(story.id)}&aspect=9%3A16`,
      )).json();
      return current.edit || current;
    }, jobId);
  };
  const barEnd = async (selector) => {
    await page.waitForTimeout(250);
    const box = await rectOf(selector);
    assert(box, `${selector} is not on the timeline`);
    return box;
  };
  const dragTo = async (fromX, fromY, toX, toY) => {
    await page.mouse.move(fromX, fromY);
    await page.mouse.down();
    await page.mouse.move((fromX + toX) / 2, (fromY + toY) / 2, { steps: 4 });
    await page.mouse.move(toX, toY, { steps: 4 });
    await page.mouse.up();
  };
  // Every Clean bar can change time, found text and drawn boxes alike.
  assert(
    await page.locator(".st-tl-bar-clean:not(.is-found):not(.is-drawn).is-timed").count() > 0,
    "an auto-detected bar cannot be dragged",
  );
  const drawArea = await rectOf("#st-preview-canvas");
  await page.locator('.st-preview-tool[data-tool="box"]').click();
  await dragTo(
    drawArea.x + drawArea.width * 0.3, drawArea.y + drawArea.height * 0.3,
    drawArea.x + drawArea.width * 0.6, drawArea.y + drawArea.height * 0.36,
  );
  await page.waitForTimeout(300);
  // A drawn box starts at the playhead and runs three seconds forward.
  const drawnFirst = (await savedEdit()).clean.find((layer) => !layer.tracklet_id);
  const drawnSpan = drawnFirst?.ranges?.[0];
  assert(drawnSpan && Math.abs(drawnSpan.end - drawnSpan.start - 3) < 0.05,
    `a drawn box should last three seconds: ${JSON.stringify(drawnSpan)}`);

  // It can be clicked, moved and resized on the video, even after Framing.
  await page.locator('[data-layer="zoom"]').click();
  await page.locator('[data-layer="clean"]').click();
  await page.waitForTimeout(150);
  const boxCentre = {
    x: drawArea.x + drawArea.width * 0.45,
    y: drawArea.y + drawArea.height * 0.33,
  };
  await dragTo(boxCentre.x, boxCentre.y, boxCentre.x + drawArea.width * 0.1, boxCentre.y + drawArea.height * 0.1);
  const movedBox = (await savedEdit()).clean.find((layer) => !layer.tracklet_id).box;
  assert(Math.abs(movedBox.x - drawnFirst.box.x) > 0.02, `the box did not move: ${JSON.stringify(movedBox)}`);
  // The box is padded and sits in source space, so find its corner on the frame.
  const cropW = (movedBox.x - drawnFirst.box.x) / 0.1;
  const cropH = (movedBox.y - drawnFirst.box.y) / 0.1;
  const corner = {
    x: 0.55 + (movedBox.w / 2) / cropW,
    y: 0.43 + (movedBox.h / 2) / cropH,
  };
  await dragTo(
    drawArea.x + drawArea.width * corner.x, drawArea.y + drawArea.height * corner.y,
    drawArea.x + drawArea.width * (corner.x + 0.1), drawArea.y + drawArea.height * (corner.y + 0.05),
  );
  const grownBox = (await savedEdit()).clean.find((layer) => !layer.tracklet_id).box;
  assert(grownBox.w > movedBox.w + 0.02, `the box did not resize: ${JSON.stringify(grownBox)}`);

  const cleanBar = await barEnd(".st-tl-bar-clean.is-drawn.is-timed");
  const stacked = await page.evaluate(() => {
    const bars = [...document.querySelectorAll(".st-tl-track-clean .st-tl-bar")];
    const box = (bar) => bar.getBoundingClientRect();
    return bars.filter((bar) => bar.classList.contains("is-found")).every((found) => (
      bars.filter((bar) => !bar.classList.contains("is-found")).every((layer) => (
        box(found).top >= box(layer).bottom - 1 || box(found).bottom <= box(layer).top + 1
      ))
    ));
  });
  assert(stacked, "found text still covers a layer's bar");
  assert(cleanBar.width > 8, "the Clean bar is too thin to drag");
  await dragTo(
    cleanBar.x + cleanBar.width - 2, cleanBar.y + cleanBar.height / 2,
    cleanBar.x + cleanBar.width * 0.6, cleanBar.y + cleanBar.height / 2,
  );
  const shorter = await barEnd(".st-tl-bar-clean.is-drawn.is-timed");
  assert(shorter.width < cleanBar.width - 4, "dragging the Clean bar's edge did not shorten it");
  const afterClean = await savedEdit();
  const drawnLayer = afterClean.clean.find((layer) => !layer.tracklet_id);
  const savedRange = drawnLayer?.ranges?.[0];
  assert(savedRange && savedRange.end - savedRange.start < 4, `the Clean range was not saved: ${JSON.stringify(savedRange)}`);

  // A box shows only at its own time on the timeline.
  await page.locator(".st-tl-bar-clean.is-drawn.is-timed").first().click();
  await page.waitForTimeout(250);
  assert(await page.locator("#st-box-method").isVisible(), "the selected box is not on the preview at its time");
  await page.evaluate(() => document.activeElement?.blur());
  await page.keyboard.press("End");
  await page.waitForTimeout(250);
  assert(!(await page.locator("#st-box-method").isVisible()), "the box still shows past its time");
  await page.locator(".st-tl-bar-clean.is-drawn.is-timed").first().click();
  await page.waitForTimeout(250);
  assert(await page.locator("#st-box-method").isVisible(), "selecting the layer did not go to its time");

  // A Text layer drags on the video, and its bar changes how long it shows.
  await page.locator('[aria-label="Text"], [title="Text"]').first().click();
  await page.locator('.st-text-preset[data-kind="hook"]').click();
  await page.waitForTimeout(300);
  const textBar = await barEnd(".st-tl-bar-text.is-timed");
  await dragTo(
    textBar.x + textBar.width - 2, textBar.y + textBar.height / 2,
    textBar.x + textBar.width * 0.7, textBar.y + textBar.height / 2,
  );
  const textShorter = await barEnd(".st-tl-bar-text.is-timed");
  assert(textShorter.width < textBar.width - 2, "dragging the text bar's edge did not shorten it");
  const afterBar = await savedEdit();
  const savedText = (afterBar.graphics || []).find((layer) => layer.id === "prefix");
  assert(savedText && savedText.end < 2.5, `the text time was not saved: ${JSON.stringify(savedText)}`);
  assert(!savedText.video, "changing the text's time placed it on the video");

  await page.locator(".st-tl-bar-text.is-timed").first().click();
  await page.waitForTimeout(300);
  const canvas = await rectOf("#st-preview-canvas");
  assert(canvas, "the preview is not measurable");
  const middle = { x: canvas.x + canvas.width * 0.5, y: canvas.y + canvas.height * 0.12 };
  await page.mouse.click(middle.x, middle.y);
  await page.waitForTimeout(200);
  assert(!(await savedEdit()).graphics.some((layer) => layer.video), "a click placed the text on the video");
  await dragTo(middle.x, middle.y, middle.x + canvas.width * 0.12, middle.y + canvas.height * 0.2);
  const placed = (await savedEdit()).graphics.find((layer) => layer.video);
  assert(placed?.video?.box, "dragging the text did not place it on the video");
  console.log("Timeline and text drags passed.");

  // Icons: no typed glyph stands in for one, and every icon control draws an SVG.
  const iconFaults = await page.evaluate(() => {
    const controls = [...document.querySelectorAll(
      "#studio-root .st-icon-btn, #studio-root .st-tl-icon, #studio-root .st-preview-tool, #studio-root .st-layer-rail-btn",
    )];
    return controls
      .filter((node) => !node.querySelector("svg.st-icon") || !node.getAttribute("aria-label"))
      .map((node) => node.id || node.outerHTML.slice(0, 80));
  });
  assert(!iconFaults.length, `icon controls without an icon or name: ${iconFaults.join(", ")}`);
  const playGlyph = await page.locator("#st-preview-play svg.st-icon").count();
  assert(playGlyph === 1, "Play does not draw its icon");

  // The frame: real size on its border, and a network's safe area to choose.
  const frameText = await page.locator("#st-preview-frame-size").textContent();
  assert(/^Frame \d+×\d+$/.test(frameText.trim()), `frame size label: ${frameText}`);
  assert(await page.locator('#st-preview-platform option[value="instagram"]').count() === 1, "no Instagram safe area");
  await page.selectOption("#st-preview-platform", "tiktok");

  // The view zooms out past 100%, and that is not an edit.
  await page.locator("#st-preview-zoom-out").click();
  assert((await page.locator("#st-preview-zoom-level").textContent()).trim() === "75%", "the view did not shrink");
  await page.locator("#st-preview-zoom-level").click();

  // A scene zooms out to fit the frame, moves inside it, and saves on that scene.
  await page.locator('.st-layer-rail-btn[data-layer="zoom"]').click();
  await page.locator(".st-framing-actions button", { hasText: "Fit scene" }).click();
  await page.waitForTimeout(900);
  const fitted = (await savedEdit()).reframe;
  const fittedScenes = Object.values(fitted.scenes || {});
  assert(fittedScenes.length === 1 && fittedScenes[0].zoom < 1, `Fit was not saved: ${JSON.stringify(fitted)}`);
  await page.locator(".st-framing-actions button", { hasText: "Move and zoom" }).click();
  const framed = await rectOf("#st-preview-canvas");
  await dragTo(
    framed.x + framed.width * 0.5, framed.y + framed.height * 0.5,
    framed.x + framed.width * 0.7, framed.y + framed.height * 0.6,
  );
  await page.waitForTimeout(900);
  const moved = Object.values((await savedEdit()).reframe.scenes)[0];
  assert(moved.cx < 0.5 && moved.cy < 0.5, `moving the scene was not saved: ${JSON.stringify(moved)}`);
  // A corner handle zooms the scene itself, and scrolling does too.
  const zoomBefore = moved.zoom;
  const handleArea = await rectOf("#st-preview-canvas");
  // The project says 1920×1080, so this is the scene's corner in the 9:16 frame.
  const windowW = (1080 * 9 / 16) / moved.zoom / 1920;
  const windowH = 1 / moved.zoom;
  const cornerX = Math.min(0.99, -(moved.cx - windowW / 2) / windowW + 1 / windowW);
  const cornerY = Math.min(0.99, -(moved.cy - windowH / 2) / windowH + 1 / windowH);
  await dragTo(
    handleArea.x + handleArea.width * cornerX, handleArea.y + handleArea.height * cornerY,
    handleArea.x + handleArea.width * (cornerX - 0.1), handleArea.y + handleArea.height * (cornerY - 0.05),
  );
  await page.waitForTimeout(900);
  const scaled = Object.values((await savedEdit()).reframe.scenes)[0];
  assert(scaled.zoom !== zoomBefore, `dragging a corner did not zoom the scene: ${JSON.stringify(scaled)}`);
  await page.mouse.move(handleArea.x + handleArea.width / 2, handleArea.y + handleArea.height / 2);
  await page.mouse.wheel(0, -200);
  await page.waitForTimeout(1200);
  const wheeled = Object.values((await savedEdit()).reframe.scenes)[0];
  assert(wheeled.zoom > scaled.zoom, `scrolling did not zoom the scene: ${JSON.stringify(wheeled)}`);
  if (screenshot) {
    await page.waitForTimeout(1200);
    await page.screenshot({ path: screenshot.replace(/\.png$/, "_framing.png"), fullPage: false });
  }
  await page.locator('.st-preview-tool[data-tool="select"]').click();
  console.log("Frame, safe area, framing and icons passed.");

  // Moments: the whole video opens in Edit, every scene in time order, with no trim.
  await page.evaluate(() => { window.location.hash = "#/moments"; });
  await page.waitForTimeout(600);
  await page.locator("button", { hasText: "Edit full video" }).click();
  await page.waitForFunction(() => window.location.hash.includes("edit"));
  await page.waitForSelector("#st-preview-canvas");
  await page.waitForTimeout(1500);
  const opened = await page.evaluate(() => JSON.parse(localStorage.getItem("vibecut.studio.edit.choice") || "{}"));
  assert(opened.storyId === "st_full_video", `the full video did not open: ${JSON.stringify(opened)}`);
  assert(opened.aspect === "16:9", `a wide video did not open wide: ${JSON.stringify(opened)}`);
  assert(await page.locator(".st-tl-trim").count() === 0, "the full video shows trim handles");
  assert(await page.locator(".st-tl-bar-scenes").count() > 1, "the full video has no scenes on the timeline");
  console.log("Full video passed.");

  // The safe area stays on the frame through everything done in the preview.
  const safeAreaShows = async (step) => {
    const toggle = page.locator("#st-preview-safe-toggle");
    const pixels = () => page.evaluate(() => {
      const canvas = document.querySelector("#st-preview-canvas");
      const small = document.createElement("canvas");
      small.width = 96; small.height = 96;
      small.getContext("2d").drawImage(canvas, 0, 0, 96, 96);
      return Array.from(small.getContext("2d").getImageData(0, 0, 96, 96).data);
    });
    const on = await pixels();
    await toggle.click();
    await page.waitForTimeout(60);
    const off = await pixels();
    await toggle.click();
    await page.waitForTimeout(60);
    const changed = on.reduce((sum, value, index) => sum + (Math.abs(value - off[index]) > 6 ? 1 : 0), 0);
    assert(changed > 40, `the safe area is gone after: ${step} (${changed})`);
    const inside = await page.evaluate(() => {
      const canvas = document.querySelector("#st-preview-canvas").getBoundingClientRect();
      const label = document.querySelector("#st-preview-frame-size").getBoundingClientRect();
      return Math.abs(label.left - canvas.left) < 2 && Math.abs(label.bottom - canvas.top) < 24;
    });
    assert(inside, `the frame size left the frame after: ${step}`);
  };
  await page.selectOption("#st-preview-platform", "tiktok");
  await safeAreaShows("opening the full video");
  for (const network of ["auto", "instagram", "youtube", "facebook", "rednote", "tiktok"]) {
    await page.selectOption("#st-preview-platform", network);
    await safeAreaShows(`choosing ${network}`);
  }
  await page.locator("#st-preview-zoom-out").click();
  await safeAreaShows("shrinking the view");
  await page.locator("#st-preview-zoom-in").click();
  await page.locator("#st-preview-zoom-in").click();
  await safeAreaShows("magnifying the view");
  await page.locator("#st-preview-zoom-level").click();
  await page.locator("#st-preview-play").click();
  await page.waitForTimeout(1500);
  await safeAreaShows("playing");
  await page.locator("#st-preview-play").click();
  await page.waitForTimeout(500);
  await safeAreaShows("pausing");
  for (const shape of ["9:16", "1:1", "4:5", "16:10", "16:9"]) {
    await page.locator("#st-preview-aspect").click();
    await page.locator(`#st-preview-aspect-menu [data-aspect="${shape}"]`).click();
    await page.waitForTimeout(1500);
    await safeAreaShows(`changing the shape to ${shape}`);
    if (screenshot) {
      await page.screenshot({ path: screenshot.replace(/\.png$/, `_shape_${shape.replace(":", "x")}.png`), fullPage: false });
    }
  }
  console.log("Safe area passed.");

  // Space after using the toggle plays, and does not hide the guides.
  await page.locator("#st-preview-safe-toggle").click();
  await page.locator("#st-preview-safe-toggle").click();
  assert(
    await page.evaluate(() => document.activeElement?.id !== "st-preview-safe-toggle"),
    "the safe area button keeps focus, so Space would hide the guides",
  );

  // Edit has a Finish button, and the chosen network comes back on return.
  const finishButton = page.locator("#st-edit-finish");
  assert(await finishButton.isVisible(), "Edit has no Finish button");
  await finishButton.click();
  await page.waitForFunction(() => window.location.hash.includes("finish"));
  assert(!(await finishButton.isVisible()), "Finish still shows on the Finish step");
  await page.evaluate(() => { window.location.hash = "#/edit"; });
  await page.waitForSelector("#st-preview-platform");
  await page.waitForTimeout(600);
  assert(await page.locator("#st-preview-platform").inputValue() === "tiktok", "the network was lost");
  await safeAreaShows("coming back to Edit");

  // Import lists old videos with a delete that asks once more, and the library.
  await page.evaluate(() => { window.location.hash = "#/import"; });
  await page.waitForSelector("#st-recent-all");
  await page.waitForSelector(".st-recent-row .st-delete-video");
  await page.locator("#st-recent-all").click();
  await page.waitForSelector(".st-library-row .st-delete-video");
  await page.locator("#st-library-dialog [data-library-close]").first().click();
  const removeVideo = page.locator(".st-recent-row .st-delete-video").first();
  await removeVideo.click();
  await page.waitForSelector(".st-delete-dialog");
  await page.locator(".st-delete-dialog button", { hasText: "Cancel" }).click();
  assert(await page.locator(".st-delete-dialog").count() === 0, "Cancel left the prompt open");
  assert(await page.locator(".st-recent-row").count() > 0, "Cancel deleted the video");
  await removeVideo.click();
  await page.waitForSelector(".st-delete-dialog");
  await page.locator(".st-delete-confirm").click();
  await page.waitForFunction(() => !document.querySelector(".st-recent-row"));
  await page.waitForTimeout(1500);
  const gone = await page.evaluate(async (id) => (await fetch(`/api/jobs/${id}`)).status, jobId);
  assert(gone === 404, `the video was not deleted: ${gone}`);
  console.log("Finish button and delete video passed.");
  console.log("Found-text list, Remove all and painter mask passed.");
} finally {
  await browser.close();
}
