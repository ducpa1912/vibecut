/**
 * The Studio Edit frame at the two laptop sizes from the founder report.
 *
 * The page must not scroll: preview, timeline and the settings panel are all
 * on screen at 1280x720 and 1024x680, with the panel on the right and no
 * sticky toolbar over the picture or the timeline rows.
 *
 * Exit 0 passes, exit 2 means the host cannot run Playwright (skip), any
 * other exit fails. The Python wrapper owns the server and its cleanup.
 */

import process from "node:process";

const base = String(process.env.EDIT_BASE_URL || "").replace(/\/$/, "");
const jobId = String(process.env.EDIT_JOB_ID || "j1");
const moduleUrl = process.env.PLAYWRIGHT_MODULE || "";
const screenshotPrefix = process.env.EDIT_SCREENSHOT_PREFIX || "";

function skip(message) {
  console.error(`SKIP: ${message}`);
  process.exit(2);
}

if (!base) skip("EDIT_BASE_URL is not set");
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

const failures = [];
const viewports = [
  { width: 1280, height: 720, label: "1280x720" },
  { width: 1024, height: 680, label: "1024x680" },
];

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport });
    await context.addInitScript(({ id }) => {
      localStorage.setItem("vibecut.studio.job", JSON.stringify({
        id, name: "edit-layout-fixture.mp4", status: "ready",
      }));
    }, { id: jobId });
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

    try {
      await page.goto(`${base}/#/edit`, { waitUntil: "domcontentloaded" });
      await page.locator(".st-edit-panel").waitFor({ state: "visible", timeout: 30000 });
      await page.locator(".st-timeline").waitFor({ state: "visible", timeout: 30000 });
      await page.waitForFunction(() => {
        const text = document.querySelector("#st-edit-meta")?.textContent || "";
        return /\d+:\d+/.test(text);
      }, null, { timeout: 30000 });
      await page.waitForTimeout(500);

      const layout = await page.evaluate(() => {
        const main = document.querySelector("main.st-main");
        const toolbar = document.querySelector(".st-edit-toolbar");
        const preview = document.querySelector(".st-preview");
        const timeline = document.querySelector(".st-timeline");
        const inspector = document.querySelector(".st-inspector");
        const body = document.querySelector(".st-inspector-body");
        const rect = (node) => {
          const box = node.getBoundingClientRect();
          return {
            top: box.top, right: box.right, bottom: box.bottom, left: box.left,
            width: box.width, height: box.height,
          };
        };
        return {
          width: window.innerWidth,
          height: window.innerHeight,
          overflowY: getComputedStyle(main).overflowY,
          scrollHeight: main.scrollHeight,
          clientHeight: main.clientHeight,
          toolbarPosition: getComputedStyle(toolbar).position,
          inspectorDisplay: getComputedStyle(inspector).display,
          bodyOverflowY: getComputedStyle(body).overflowY,
          preview: rect(preview),
          timeline: rect(timeline),
          inspector: rect(inspector),
          toolbar: rect(toolbar),
        };
      });

      const where = viewport.label;
      assert(layout.overflowY === "hidden", `${where}: the editor page still scrolls`);
      assert(
        layout.scrollHeight <= layout.clientHeight + 2,
        `${where}: editor content is taller than the frame (${layout.scrollHeight} > ${layout.clientHeight})`,
      );
      assert(layout.toolbarPosition !== "sticky", `${where}: toolbar is still sticky`);
      assert(layout.toolbar.top >= 0, `${where}: toolbar starts above the viewport`);
      assert(layout.preview.top >= 0, `${where}: preview starts above the viewport`);
      assert(layout.preview.height > 120, `${where}: preview is too small (${layout.preview.height})`);
      assert(
        layout.preview.bottom <= layout.height + 1,
        `${where}: preview leaves the viewport (${layout.preview.bottom} > ${layout.height})`,
      );
      assert(
        layout.timeline.top >= layout.preview.bottom - 1,
        `${where}: timeline is not below the preview`,
      );
      assert(
        layout.timeline.bottom <= layout.height + 1,
        `${where}: timeline leaves the viewport (${layout.timeline.bottom} > ${layout.height})`,
      );
      assert(layout.timeline.height >= 120, `${where}: timeline is too small`);
      assert(layout.inspectorDisplay !== "none", `${where}: settings panel is hidden`);
      assert(
        layout.inspector.top >= 0 && layout.inspector.bottom <= layout.height + 1,
        `${where}: settings panel leaves the viewport`,
      );
      assert(
        layout.inspector.left >= layout.preview.right - 1,
        `${where}: settings panel is not to the right of the preview`,
      );
      assert(layout.bodyOverflowY === "auto", `${where}: settings panel lost its own scroll`);

      await page.locator('.st-inspector-tab[data-tab="clean"]').click();
      const scanButton = page.locator(".st-clean-scan-start").first();
      await scanButton.waitFor({ state: "visible", timeout: 15000 });
      const scanLabel = (await scanButton.textContent())?.trim() || "";
      assert(
        scanLabel.includes("Find text on screen"),
        `${where}: Edit does not offer the text scan (${scanLabel})`,
      );

      // P1: draw, move and delete a Remove-text box without a number field.
      if (viewport.width === 1280) {
        await page.locator("#st-preview-tool-box").click();
        const canvas = page.locator("#st-preview-canvas");
        const box = await canvas.boundingBox();
        assert(box && box.width > 100 && box.height > 100, `${where}: preview canvas is not measurable`);
        const start = { x: box.x + box.width * 0.32, y: box.y + box.height * 0.34 };
        const end = { x: box.x + box.width * 0.68, y: box.y + box.height * 0.48 };
        await page.mouse.move(start.x, start.y);
        await page.mouse.down();
        await page.mouse.move(end.x, end.y, { steps: 8 });
        await page.mouse.up();

        const cleanRow = page.locator('.st-layer-item[data-kind="clean"]').first();
        await cleanRow.waitFor({ state: "visible", timeout: 10000 });
        const before = JSON.parse(await cleanRow.getAttribute("data-box"));
        assert(before.w > 0.01 && before.h > 0.01, `${where}: drawn box has no size`);

        const live = await canvas.boundingBox();
        const centre = { x: live.x + live.width * 0.5, y: live.y + live.height * 0.41 };
        await page.mouse.move(centre.x, centre.y);
        await page.mouse.down();
        await page.mouse.move(centre.x + 14, centre.y + 10, { steps: 6 });
        await page.mouse.up();
        await page.waitForTimeout(150);
        const moved = JSON.parse(await cleanRow.getAttribute("data-box"));
        assert(
          Math.abs(moved.x - before.x) > 0.001 || Math.abs(moved.y - before.y) > 0.001,
          `${where}: dragging the box did not move it`,
        );

        const resizeCanvas = await canvas.boundingBox();
        const corner = {
          x: resizeCanvas.x + (moved.x + moved.w) * resizeCanvas.width,
          y: resizeCanvas.y + (moved.y + moved.h) * resizeCanvas.height,
        };
        await page.mouse.move(corner.x, corner.y);
        await page.mouse.down();
        await page.mouse.move(corner.x + 16, corner.y + 12, { steps: 6 });
        await page.mouse.up();
        const resized = JSON.parse(await cleanRow.getAttribute("data-box"));
        assert(
          Math.abs(resized.w - moved.w) > 0.001 || Math.abs(resized.h - moved.h) > 0.001,
          `${where}: dragging the handle did not resize the box`,
        );

        await page.keyboard.press("Delete");
        await cleanRow.waitFor({ state: "detached", timeout: 10000 });
        await page.waitForFunction(
          () => !document.querySelector(".st-tl-bar-clean"),
          null,
          { timeout: 10000 },
        );
      }

      if (screenshotPrefix) {
        await page.screenshot({
          path: `${screenshotPrefix}-${viewport.width}.png`,
          fullPage: false,
        });
      }
      assert(pageErrors.length === 0, `${where}: page errors: ${pageErrors.join(" | ")}`);
    } catch (error) {
      failures.push(`${viewport.label}: ${error?.message || error}`);
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Edit layout fits at 1280x720 and 1024x680.");
