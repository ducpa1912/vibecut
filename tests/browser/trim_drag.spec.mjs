/**
 * Mounted trim drag for the Studio Edit step.
 *
 * Starts from the synthetic `trim_job` fixture: one 24 s story, a text layer
 * over sentence 2, a tail layer after sentence 4 and six caption cues.
 * Drags the real start and end handles, then checks the one duration source,
 * the layer bar geometry and the caption cue times.
 *
 * Exit 0 passes, exit 2 means the host cannot run Playwright (skip), any
 * other exit fails. The Python wrapper owns the server and its cleanup.
 */

import process from "node:process";

const base = String(process.env.TRIM_BASE_URL || "").replace(/\/$/, "");
const jobId = String(process.env.TRIM_JOB_ID || "j1");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
const screenshot = process.env.TRIM_SCREENSHOT || "";

function skip(message) {
  console.error(`SKIP: ${message}`);
  process.exit(2);
}

if (!base) skip("TRIM_BASE_URL is not set");
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

function seconds(text) {
  const value = String(text || "");
  const clock = value.match(/(\d+):(\d+(?:\.\d+)?)/);
  if (clock) return Number(clock[1]) * 60 + Number(clock[2]);
  const plain = value.match(/(\d+(?:\.\d+)?)\s*(?:s|sec)/i);
  if (plain) return Number(plain[1]);
  return NaN;
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch (error) {
  skip(`Chromium did not launch: ${error?.message || error}`);
}

const pageErrors = [];
let page;
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  await context.addInitScript(({ id }) => {
    localStorage.setItem("vibecut.studio.job", JSON.stringify({
      id, name: "trim-fixture.mp4", status: "ready",
    }));
  }, { id: jobId });
  page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

  await page.goto(`${base}/#/edit`, { waitUntil: "domcontentloaded" });
  await page.locator(".st-tl-trim-start").first().waitFor({
    state: "visible", timeout: 30000,
  });
  await page.waitForFunction(() => {
    const text = document.querySelector("#st-edit-meta")?.textContent || "";
    return /\d+:\d+/.test(text);
  }, null, { timeout: 30000 });

  const headerSeconds = async () => seconds(
    await page.locator("#st-edit-meta").textContent(),
  );
  const waitNumberBelow = async (locator, limit, timeout = 20000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = Number(await locator.getAttribute("data-start"));
      if (Number.isFinite(value) && value < limit - 1.0) return value;
      await page.waitForTimeout(100);
    }
    throw new Error(`timed out waiting for a bar below ${limit}`);
  };

  const durationChanged = async (previous, direction) => {
    await page.waitForFunction(({ before, sign }) => {
      const raw = document.querySelector("#st-edit-meta")?.textContent || "";
      const clock = raw.match(/(\d+):(\d+(?:\.\d+)?)/);
      const value = clock
        ? Number(clock[1]) * 60 + Number(clock[2])
        : Number((raw.match(/(\d+(?:\.\d+)?)\s*(?:s|sec)/i) || [])[1]);
      if (!Number.isFinite(value)) return false;
      return sign > 0 ? value > before + 0.4 : value < before - 0.4;
    }, { before: previous, sign: direction }, { timeout: 20000 });
    return headerSeconds();
  };

  const movedBar = page.locator('.st-tl-bar[data-layer="moved"]').first();
  const tailBar = page.locator('.st-tl-bar[data-layer="tail"]').first();
  const captionBar = page
    .locator(".st-tl-track-captions .st-tl-bar")
    .filter({ hasText: "Sentence 2 " })
    .first();
  await movedBar.waitFor({ state: "visible", timeout: 20000 });
  await tailBar.waitFor({ state: "visible", timeout: 20000 });
  await captionBar.waitFor({ state: "visible", timeout: 20000 });
  await page.waitForTimeout(700);

  const initialHeader = await headerSeconds();
  assert(Number.isFinite(initialHeader) && initialHeader > 20,
    `header duration did not load: ${initialHeader}`);
  const movedBefore = Number(await movedBar.getAttribute("data-start"));
  const captionBefore = Number(await captionBar.getAttribute("data-start"));

  async function sentenceBars() {
    return page.locator(".st-tl-track-sentences .st-tl-bar").evaluateAll(
      (nodes) => nodes.map((node) => {
        const box = node.getBoundingClientRect();
        return {
          x: box.x,
          width: box.width,
          start: Number(node.dataset.start),
          end: Number(node.dataset.end),
        };
      }).sort((left, right) => left.x - right.x),
    );
  }

  async function dragHandle(handle, direction) {
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    assert(box, "trim handle has no box");
    const bars = await sentenceBars();
    const centre = box.x + box.width / 2;
    const target = direction > 0
      ? bars.find((bar) => bar.x > centre + 2)
      : [...bars].reverse().find((bar) => bar.x + bar.width < centre - 2);
    assert(target, "no sentence bar next to the trim handle");
    const inset = Math.min(3, Math.max(1, target.width * 0.1));
    const targetX = direction > 0
      ? target.x + inset
      : target.x + target.width - inset;
    const y = box.y + box.height / 2;
    await page.mouse.move(centre, y);
    await page.mouse.down();
    await page.mouse.move(targetX, y, { steps: 10 });
    await page.mouse.up();
  }

  // 1. Drag the start handle one sentence later.
  await dragHandle(page.locator(".st-tl-trim-start").first(), 1);
  const afterStart = await durationChanged(initialHeader, -1);
  assert(afterStart < initialHeader - 0.5,
    `start trim did not shorten the header (${initialHeader} -> ${afterStart})`);

  const movedAfter = await waitNumberBelow(movedBar, movedBefore);
  const captionAfter = await waitNumberBelow(captionBar, captionBefore);
  assert(movedAfter < movedBefore - 1.0,
    `text layer did not ripple (${movedBefore} -> ${movedAfter})`);
  assert(captionAfter < captionBefore - 1.0,
    `caption cue did not follow (${captionBefore} -> ${captionAfter})`);

  // 2. Drag the end handle one sentence earlier; the tail layer leaves range.
  await dragHandle(page.locator(".st-tl-trim-end").first(), -1);
  const afterEnd = await durationChanged(afterStart, -1);
  assert(afterEnd < afterStart - 0.5,
    `end trim did not shorten the header (${afterStart} -> ${afterEnd})`);
  await page.waitForFunction(() => {
    const node = document.querySelector('.st-tl-bar[data-layer="tail"]');
    return node?.dataset.outside === "1";
  }, null, { timeout: 20000 });

  // 3. Focus and widen the start again; the same handle keeps focus.
  const startHandle = page.locator(".st-tl-trim-start").first();
  await startHandle.focus();
  assert(await startHandle.evaluate(
    (node) => document.activeElement === node,
  ), "start handle did not take focus");
  await page.keyboard.press("ArrowLeft");
  const afterWiden = await durationChanged(afterEnd, 1);
  assert(afterWiden > afterEnd + 0.5,
    `keyboard widen did not lengthen the header (${afterEnd} -> ${afterWiden})`);
  await page.waitForFunction(
    () => document.activeElement?.dataset?.edge === "start",
    null,
    { timeout: 5000 },
  ).catch(() => {});
  assert(await startHandle.evaluate(
    (node) => document.activeElement === node,
  ), "start handle lost focus after the keyboard trim");

  // One duration source: the header and the timeline span agree.
  const spanText = String(
    await page.locator("#st-timeline-span").textContent() || "",
  );
  const clocks = [...spanText.matchAll(/(\d+):(\d+(?:\.\d+)?)/g)];
  const lastClock = clocks.at(-1);
  const spanEnd = lastClock
    ? Number(lastClock[1]) * 60 + Number(lastClock[2])
    : seconds(spanText);
  assert(Number.isFinite(spanEnd) && Math.abs(spanEnd - afterWiden) < 0.3,
    `header ${afterWiden} and timeline ${spanEnd} disagree`);

  assert(pageErrors.length === 0,
    `page errors: ${pageErrors.join(" | ")}`);
  console.log(JSON.stringify({
    initial: initialHeader,
    afterStart,
    afterEnd,
    afterWiden,
    movedBefore,
    movedAfter,
    captionBefore,
    captionAfter,
  }));
} catch (error) {
  if (screenshot) {
    try {
      await page?.screenshot({ path: screenshot, fullPage: true });
    } catch (_) {
      // The screenshot is diagnostic only.
    }
  }
  console.error(error?.stack || String(error));
  process.exitCode = 1;
} finally {
  await browser.close();
}
