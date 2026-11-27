#!/usr/bin/env node
/*
 * Check SFX Focus and its timeline lane at the small sizes and at 200 % zoom.
 *
 *   NODE_PATH="$(npm root -g)" node scripts/check-sfx-focus-layout.cjs \
 *     --base "http://127.0.0.1:8813/?t=scratch-3a" \
 *     --project prj_e95348a97316 --out build/opencode-3a
 *
 * Needs the shared Chromium under ~/Library/Caches/ms-playwright and the
 * globally installed puppeteer-core. The dev server must already be running.
 * Fails (exit 1) when a add button clips its own label, when the dock leaves the
 * viewport or the page scrolls, when two lane blocks share a row and overlap,
 * or when the effect preview draws outside the frame.
 */
const fs = require("node:fs/promises");
const path = require("node:path");

let puppeteer;
try {
  puppeteer = require("puppeteer-core");
} catch {
  console.error('puppeteer-core not found. Run with NODE_PATH="$(npm root -g)" and a live dev server.');
  process.exit(2);
}

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}
const base = args.get("base");
const project = args.get("project");
const out = path.resolve(args.get("out") || "build");
const sizes = [[800, 600], [960, 640], [1024, 700], [1100, 800], [1200, 800], [1280, 800], [1440, 900], [720, 450]];

if (!base || !project) {
  console.error("need --base and --project");
  process.exit(2);
}

const executablePath = path.join(
  process.env.HOME,
  "Library/Caches/ms-playwright/chromium-1255/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);

async function run() {
  const browser = await puppeteer.launch({
    executablePath, headless: "new", args: ["--no-sandbox", "--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await fs.mkdir(out, { recursive: true });
  const rows = [];
  let failed = 0;

  for (const [width, height] of sizes) {
    await page.setViewport({ width, height, deviceScaleFactor: width === 720 ? 2 : 1 });
    await page.goto(`${base}#/project/${project}/edit`, { waitUntil: "domcontentloaded" });
    await new Promise((resolve) => setTimeout(resolve, 3000));
    // A previous round may have restored focus mode from saved state: go back first.
    await page.evaluate(() => {
      document.querySelector('[data-action="close-focus"]')?.click();
    });
    await new Promise((resolve) => setTimeout(resolve, 400));

    const lane = await page.evaluate(() => {
      const track = document.querySelector(".timeline-track.sfx");
      if (!track) return null;
      const box = track.getBoundingClientRect();
      const blocks = [...track.querySelectorAll(".timeline-block")].map((block) => {
        const rect = block.getBoundingClientRect();
        return { top: Math.round(rect.top - box.top), left: rect.left, right: rect.right, h: Math.round(rect.height) };
      });
      let overlaps = 0;
      for (let i = 0; i < blocks.length; i += 1) {
        for (let j = i + 1; j < blocks.length; j += 1) {
          if (blocks[i].top !== blocks[j].top) continue;
          if (blocks[i].left < blocks[j].right - 1 && blocks[j].left < blocks[i].right - 1) overlaps += 1;
        }
      }
      const tallest = blocks.reduce((value, block) => Math.max(value, block.top + block.h), 0);
      return { laneH: Math.round(box.height), blocks: blocks.length, overlaps, tallest };
    });

    await page.evaluate(() => {
      document.querySelector('[data-action="inspector-tab"][data-tab="sfx"]')?.click();
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const open = await page.$('[data-action="open-focus"][data-focus="sfx"]');
    if (open) await open.click();
    await new Promise((resolve) => setTimeout(resolve, 700));

    const layout = await page.evaluate(() => {
      const dock = document.querySelector(".focus-dock");
      if (!dock) return null;
      const card = document.querySelector(".media-card.preview-large");
      const box = (element) => (element ? element.getBoundingClientRect() : null);
      const buttons = [...document.querySelectorAll(".sfx-add-grid .btn")].map((button) => ({
        label: button.textContent.trim(),
        clipped: button.scrollWidth > button.clientWidth + 1,
      }));
      const preview = box(document.querySelector(".sfx-text"));
      const cardBox = box(card);
      const back = box(document.querySelector('[data-action="close-focus"]'));
      return {
        dockBottom: Math.round(dock.getBoundingClientRect().bottom),
        pageScroll: document.documentElement.scrollHeight - innerHeight,
        hOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        buttons: buttons.length,
        clipped: buttons.filter((button) => button.clipped).length,
        hasFilter: buttons.some((button) => /filter/i.test(button.label)),
        rows: document.querySelectorAll(".sfx-row").length,
        times: document.querySelectorAll(".sfx-time").length,
        previewInside: preview && cardBox
          ? preview.left >= cardBox.left - 2 && preview.right <= cardBox.right + 2
            && preview.top >= cardBox.top - 2 && preview.bottom <= cardBox.bottom + 2
          : true,
        backVisible: back ? back.top >= 0 && back.bottom <= innerHeight : false,
      };
    });
    if (!layout) {
      rows.push({ viewport: `${width}x${height}`, error: "no focus dock" });
      failed += 1;
      continue;
    }

    const bad = !lane
      || (lane.overlaps > 0 || lane.tallest > lane.laneH + 1)
      || layout.dockBottom > height + 1
      || layout.pageScroll > 1
      || layout.hOverflow > 0
      || layout.clipped > 0
      || !layout.hasFilter
      || layout.times !== layout.rows
      || !layout.previewInside
      || !layout.backVisible;
    if (bad) failed += 1;

    const label = width === 720 ? "200%" : `${width}x${height}`;
    await page.screenshot({ path: path.join(out, `sfx-focus-${label}.png`) });
    rows.push({ viewport: label, lane, ...layout, bad: bad || undefined });
  }

  await browser.close();
  console.log(JSON.stringify(rows, null, 2));
  if (failed) {
    console.error(`${failed} viewport(s) failed the SFX Focus layout check`);
    process.exit(1);
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
