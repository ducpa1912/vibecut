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

        await page.keyboard.press("Shift+/");
        await page.locator("#st-edit-shortcuts").waitFor({ state: "visible", timeout: 5000 });
        assert(
          await page.locator("#st-edit-shortcuts kbd").count() >= 12,
          `${where}: shortcut sheet is missing keys`,
        );
        if (screenshotPrefix) {
          await page.screenshot({ path: `${screenshotPrefix}-shortcuts-${viewport.width}.png` });
        }
        await page.keyboard.press("Escape");
        await page.waitForFunction(
          () => !document.querySelector("#st-edit-shortcuts")?.open,
          null,
          { timeout: 5000 },
        );

        await page.keyboard.press("b");
        assert(
          await page.locator("#st-preview-tool-box").getAttribute("aria-pressed") === "true",
          `${where}: B did not choose the draw tool`,
        );
        await page.keyboard.press("v");
        assert(
          await page.locator("#st-preview-tool-select").getAttribute("aria-pressed") === "true",
          `${where}: V did not choose the select tool`,
        );

        const scrub = page.locator("#st-preview-scrub");
        const beforeStep = Number(await scrub.inputValue());
        await page.keyboard.press("ArrowRight");
        await page.waitForFunction(
          (before) => Math.abs(Number(document.querySelector("#st-preview-scrub")?.value) - before) > 0.02,
          beforeStep,
          { timeout: 5000 },
        );
        const afterStep = Number(await scrub.inputValue());
        assert(
          Math.abs(afterStep - beforeStep - 1 / 30) < 0.01,
          `${where}: one frame step was ${afterStep - beforeStep}s`,
        );
        await page.keyboard.press("Shift+ArrowRight");
        await page.waitForFunction(
          (before) => Number(document.querySelector("#st-preview-scrub")?.value) - before > 0.9,
          afterStep,
          { timeout: 5000 },
        );

        const textRows = page.locator('.st-layer-item[data-kind="text"]');
        const textBefore = await textRows.count();
        await page.locator('.st-layers-add summary').click();
        await page.getByRole('menuitem', { name: 'Text', exact: true }).click();
        await page.waitForFunction(
          (count) => document.querySelectorAll('.st-layer-item[data-kind="text"]').length === count + 1,
          textBefore,
          { timeout: 15000 },
        );
        await page.keyboard.press("Meta+z");
        await page.waitForFunction(
          (count) => document.querySelectorAll('.st-layer-item[data-kind="text"]').length === count,
          textBefore,
          { timeout: 15000 },
        );
        await page.keyboard.press("Meta+Shift+z");
        await page.waitForFunction(
          (count) => document.querySelectorAll('.st-layer-item[data-kind="text"]').length === count + 1,
          textBefore,
          { timeout: 15000 },
        );
      }

      if (screenshotPrefix) {
        await page.screenshot({
          path: `${screenshotPrefix}-${viewport.width}.png`,
          fullPage: false,
        });
      }

      // P4: Finish keeps the same one-screen frame as Edit.
      if (viewport.width === 1280) {
        await page.waitForFunction(
          () => !document.querySelector("#st-edit-next")?.disabled,
          null,
          { timeout: 15000 },
        );
        await page.locator("#st-edit-next").click();
        await page.locator(".st-finish-panel").waitFor({ state: "visible", timeout: 30000 });
        const finish = await page.evaluate(() => {
          const main = document.querySelector("main.st-main");
          const body = document.querySelector(".st-finish-body");
          const panel = document.querySelector(".st-finish-panel");
          const back = document.querySelector("#st-finish-back");
          return {
            overflowY: getComputedStyle(main).overflowY,
            bodyOverflowY: getComputedStyle(body).overflowY,
            gutter: getComputedStyle(body).scrollbarGutter,
            panelHeight: panel.getBoundingClientRect().height,
            backVisible: Boolean(back && back.offsetParent !== null),
          };
        });
        assert(finish.overflowY === "hidden", `${where}: Finish still scrolls the page`);
        assert(finish.bodyOverflowY === "auto", `${where}: Finish body does not own its scroll`);
        assert(finish.gutter === "stable", `${where}: Finish body has no stable gutter`);
        assert(finish.panelHeight > 400, `${where}: Finish panel collapsed`);
        assert(finish.backVisible, `${where}: Finish has no Back to Edit`);
        if (screenshotPrefix) {
          await page.screenshot({ path: `${screenshotPrefix}-finish-${viewport.width}.png` });
        }

        // P4: Moments shows the per-video text scan next to its title.
        await page.locator('.st-step[data-step="moments"]').click();
        await page.locator(".st-panel-head-row").waitFor({ state: "visible", timeout: 30000 });
        const scanAction = page.locator("#st-moment-actions button");
        await scanAction.waitFor({ state: "visible", timeout: 15000 });
        assert(
          (await scanAction.textContent())?.trim() === "Scan for text",
          `${where}: Moments has no Scan for text action`,
        );
        if (screenshotPrefix) {
          await page.screenshot({ path: `${screenshotPrefix}-moments-${viewport.width}.png` });
        }

        // P4: Import puts the rights gate beside Start and recent videos first.
        await page.locator('.st-step[data-step="import"]').click();
        await page.locator(".st-import-grid.has-recent").waitFor({ state: "visible", timeout: 20000 });
        const importState = await page.evaluate(() => {
          const attest = document.querySelector("#st-attest-row");
          const start = document.querySelector(".st-import-start");
          return {
            attestInStart: Boolean(attest && start && start.contains(attest)),
            startInStart: Boolean(start && start.contains(document.querySelector("#st-import"))),
            recentFirst: document.querySelector(".st-import-grid")?.classList.contains("has-recent"),
          };
        });
        assert(importState.attestInStart, `${where}: rights gate is not beside Start`);
        assert(importState.startInStart, `${where}: Start is not in the import start block`);
        assert(importState.recentFirst, `${where}: recent videos are not first`);
        if (screenshotPrefix) {
          await page.screenshot({ path: `${screenshotPrefix}-import-${viewport.width}.png` });
        }
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
