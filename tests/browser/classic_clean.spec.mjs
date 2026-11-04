/**
 * C1/C2 · Clean boxes on the real frame.
 *
 * This spec drives the editor the founder uses: draw a box by dragging on the
 * preview, move it, switch method, hide it, delete it, add a found-text box,
 * read the locked AI-fill row, open the key sheet and switch to Finish.
 *
 * The frame it asserts is a real JPEG from `POST /api/classic/jobs/{id}/frame`:
 * the route compiles the cut on screen through the same graph the reel uses, so
 * a box that shows here is a box the export renders. Only Check is stubbed
 * (a live text pass takes minutes); its report carries `clean_prefill` so the
 * found-text list is driven by the server's own shape, refusals included.
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

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

const frames = [
  { width: 1280, height: 720 },
  { width: 1024, height: 680 },
];

async function dragOnCanvas(page, from, to) {
  const canvas = page.locator("#clean-canvas");
  const rect = await canvas.boundingBox();
  assert(rect, "the frame canvas has no box");
  await page.mouse.move(rect.x + rect.width * from.x, rect.y + rect.height * from.y);
  await page.mouse.down();
  await page.mouse.move(rect.x + rect.width * to.x, rect.y + rect.height * to.y, { steps: 6 });
  await page.mouse.up();
}

async function run(viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  await page.route(/\/api\/jobs\/[^/]+\/check$/, async (route) => {
    if (route.request().method() === "POST") return route.fulfill(json(SCAN_REPORT));
    return route.fulfill(json(SCAN_REPORT));
  });

  await page.goto(`${base}/#job=${jobId}`, { waitUntil: "domcontentloaded" });
  await page.locator("#result-view").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#clean-stage").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(800);

  const label = `${viewport.width}×${viewport.height}`;

  // The stage shows a real rendered frame, not a placeholder.
  await page.waitForFunction(() => {
    const img = document.querySelector("#clean-frame");
    return Boolean(img && !img.hidden && img.naturalWidth > 0);
  }, null, { timeout: 60000 });
  const frameInfo = await page.evaluate(() => {
    const img = document.querySelector("#clean-frame");
    return {
      src: img.getAttribute("src") || "",
      width: img.naturalWidth,
      height: img.naturalHeight,
      ratio: img.naturalWidth / img.naturalHeight,
    };
  });
  assert(frameInfo.src.startsWith("blob:"), `${label}: the frame is not a rendered image`);
  assert(Math.abs(frameInfo.ratio - 9 / 16) < 0.02, `${label}: the frame is not 9:16 (${frameInfo.ratio})`);

  // Nothing named a percentage anywhere: the founder drags.
  const numbers = await page.evaluate(() => {
    const panel = document.querySelector("#clean-panel");
    const inputs = [...panel.querySelectorAll("input")];
    return inputs.filter((input) => input.type === "number" || input.type === "range").length;
  });
  assert(numbers === 0, `${label}: the Clean panel asks for numbers (${numbers} inputs)`);

  // Both viewports run against the same cut, so every count is relative to
  // what the previous run stored.
  const start = await page.locator("#clean-overlay .clean-box").count();

  // Draw → one more box on the frame and one more row in the layers panel.
  await page.locator("#clean-draw").click();
  await dragOnCanvas(page, { x: 0.12, y: 0.72 }, { x: 0.88, y: 0.9 });
  await page.waitForFunction((n) => document.querySelectorAll("#clean-overlay .clean-box").length === n,
    start + 1, { timeout: 10000 });
  assert(await page.locator("#clean-layers .clean-row").count() === start + 1,
    `${label}: the drawn box has no layers row`);
  assert((await page.locator("#clean-status").textContent()).includes("added"),
    `${label}: the panel did not confirm the box`);

  // Move it: the box follows the drag.
  const before = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    return parseFloat(boxes[boxes.length - 1].style.top);
  });
  await dragOnCanvas(page, { x: 0.5, y: 0.8 }, { x: 0.5, y: 0.62 });
  await page.waitForTimeout(150);
  const after = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    return parseFloat(boxes[boxes.length - 1].style.top);
  });
  assert(after < before - 2, `${label}: dragging did not move the box (${before} → ${after})`);

  // Method switch: Cover is a different render, and the chip says so.
  const row = `[data-clean-row="${await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    return boxes[boxes.length - 1].dataset.cleanId;
  })}"]`;
  await page.locator(`${row} [data-clean-method="cover"]`).click();
  await page.waitForFunction((id) => {
    const box = document.querySelector(`#clean-overlay [data-clean-id="${id}"]`);
    return box && box.dataset.method === "cover";
  }, await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    return boxes[boxes.length - 1].dataset.cleanId;
  }), { timeout: 10000 });

  // Eye toggle: hidden in the panel, still on the frame as off.
  const eye = `${row} [data-clean-eye]`;
  await page.locator(eye).click();
  await page.waitForFunction((id) => document.querySelector(`#clean-overlay [data-clean-id="${id}"]`)?.classList.contains("is-off") === true,
    await page.evaluate(() => {
      const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
      return boxes[boxes.length - 1].dataset.cleanId;
    }), { timeout: 10000 });
  await page.locator(eye).click();

  // The box is on the cut, not in the tab: a reload reads it back from the
  // saved record through the same route the reel uses.
  await page.waitForTimeout(900);
  const picked = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    const box = boxes[boxes.length - 1];
    return { id: box.dataset.cleanId, method: box.dataset.method };
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#clean-stage").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction((n) => document.querySelectorAll("#clean-overlay .clean-box").length === n,
    start + 1, { timeout: 20000 });
  const reloaded = await page.evaluate((id) => {
    const box = document.querySelector(`#clean-overlay [data-clean-id="${id}"]`);
    return box ? { id: box.dataset.cleanId, method: box.dataset.method } : { id: "", method: "" };
  }, picked.id);
  assert(reloaded.id === picked.id, `${label}: the saved box came back as ${reloaded.id}`);
  assert(reloaded.method === "cover", `${label}: the saved method came back as ${reloaded.method}`);

  // Found text: one addable subtitle, one refused watermark.
  await page.waitForFunction(() => {
    const rows = document.querySelectorAll("#clean-found .clean-found-row");
    return rows.length === 2;
  }, null, { timeout: 20000 });
  const found = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#clean-found .clean-found-row")];
    return rows.map((row) => ({
      blocked: row.classList.contains("is-blocked"),
      badge: row.querySelector(".clean-found-blocked")?.textContent || "",
      hasAdd: Boolean(row.querySelector("[data-found-add]")),
      addLabel: (row.querySelector("[data-found-add]")?.textContent || "").trim(),
      reason: row.querySelector(".clean-found-reason")?.textContent || "",
      thumb: Boolean(row.querySelector(".clean-found-thumb")?.style.backgroundImage),
    }));
  });
  assert(found[0].hasAdd && !found[0].blocked, `${label}: the subtitle cannot be added`);
  assert(found[0].thumb, `${label}: the found row has no thumbnail`);
  assert(found[1].blocked && !found[1].hasAdd, `${label}: the watermark is addable`);
  assert(found[1].badge === "locked", `${label}: the watermark does not say locked`);
  assert(/watermark/i.test(found[1].reason), `${label}: the watermark reason is missing`);

  // The other viewport already added this subtitle, so the row says Added and
  // there is nothing left to add; both paths keep the count honest.
  const scanAlready = found[0].addLabel === "Added";
  const afterScan = start + (scanAlready ? 1 : 2);
  if (!scanAlready) {
    await page.locator("[data-found-add]").first().click();
    await page.waitForFunction((n) => document.querySelectorAll("#clean-overlay .clean-box").length === n,
      afterScan, { timeout: 20000 });
  }
  const scanBox = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll("#clean-overlay .clean-box")];
    const last = boxes[boxes.length - 1];
    return { method: last.dataset.method };
  });
  assert(scanBox.method === "cover", `${label}: the found subtitle defaulted to ${scanBox.method}`);

  // AI fill is locked with the missing model names, not a dead button.
  await page.waitForFunction(() => {
    const fill = document.querySelector("#clean-fill");
    return fill && !fill.hidden && /AI fill is locked/.test(fill.textContent || "");
  }, null, { timeout: 15000 });
  const fillText = await page.locator("#clean-fill").textContent();
  assert(/lama_fp32\.onnx/.test(fillText), `${label}: the fill row hides the missing LaMa file`);
  assert(/sttn_infer_model\.pth/.test(fillText), `${label}: the fill row hides the missing STTN file`);
  assert(!(await page.locator("#clean-fill-preview").count()), `${label}: a ready fill button exists`);

  // Delete removes the box and its row.
  await page.locator(`${row} [data-clean-delete]`).click();
  await page.waitForFunction((n) => document.querySelectorAll("#clean-overlay .clean-box").length === n,
    afterScan - 1, { timeout: 10000 });
  assert(await page.locator("#clean-layers .clean-row").count() === afterScan - 1,
    `${label}: the deleted box kept its row`);

  // Undo brings it back; the stack is real.
  await page.keyboard.press("Meta+z");
  await page.waitForFunction((n) => document.querySelectorAll("#clean-overlay .clean-box").length === n,
    afterScan, { timeout: 10000 });

  // Keys sheet, then Finish and back.
  await page.keyboard.press("Shift+/");
  await page.locator("#shortcuts-sheet").waitFor({ state: "visible", timeout: 5000 });
  await page.keyboard.press("Escape");
  await page.locator("#shortcuts-sheet").waitFor({ state: "hidden", timeout: 5000 });

  await page.locator("#finish-cut").click();
  await page.waitForFunction(() => document.body.classList.contains("finish-frame"),
    null, { timeout: 5000 });
  const finish = await page.evaluate(() => {
    const pane = document.querySelector(".editor-pane-timeline");
    const settings = document.querySelector(".editor-pane-settings");
    return {
      timeline: getComputedStyle(pane).display,
      settings: getComputedStyle(settings).display,
      label: document.querySelector("#finish-cut").textContent.trim(),
      player: Boolean(document.querySelector("#player-wrap")),
    };
  });
  assert(finish.timeline === "none" && finish.settings === "none",
    `${label}: Finish did not clear the edit panes`);
  assert(finish.label === "Back to edit", `${label}: Finish does not offer the way back`);
  await page.locator("#finish-cut").click();
  await page.waitForFunction(() => !document.body.classList.contains("finish-frame"),
    null, { timeout: 5000 });
  assert(await page.locator("#clean-layers .clean-row").count() === afterScan,
    `${label}: Back to edit lost the boxes`);

  await page.waitForTimeout(400);
  const metrics = await page.evaluate(() => ({
    scrollY: window.scrollY,
    doc: document.documentElement.scrollHeight,
    inner: window.innerHeight,
  }));
  assert(metrics.scrollY === 0, `${label}: the page scrolled to ${metrics.scrollY}`);
  assert(metrics.doc <= metrics.inner + 1, `${label}: the page is taller than the frame`);

  assert(pageErrors.length === 0, `${label}: page errors: ${pageErrors.join(" | ")}`);

  if (shotDir) {
    const { mkdir } = await import("node:fs/promises");
    await mkdir(shotDir, { recursive: true }).catch(() => {});
    await page.screenshot({ path: `${shotDir}/classic-clean-${label}.png` });
  }
  await context.close();
  console.log(`ok ${label}`);
}

try {
  for (const viewport of frames) await run(viewport);
} catch (error) {
  console.error(error?.stack || String(error));
  await browser.close().catch(() => {});
  process.exit(1);
}

await browser.close().catch(() => {});
