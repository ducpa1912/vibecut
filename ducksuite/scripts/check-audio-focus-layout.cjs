#!/usr/bin/env node
/*
 * Check Audio Focus at the small sizes and at 200 % zoom.
 *
 *   NODE_PATH="$(npm root -g)" node scripts/check-audio-focus-layout.cjs \
 *     --base "http://127.0.0.1:8813/?t=scratch-3a" \
 *     --project prj_e95348a97316 --out build/opencode-3a
 *
 * Needs the shared Chromium under ~/Library/Caches/ms-playwright and the
 * globally installed puppeteer-core. The dev server must already be running.
 * Fails (exit 1) when the dock leaves the viewport, when the page scrolls as
 * one document, when the add/preview actions are not visible without scrolling
 * the body, when the preview escapes its strip, or when the placement strip
 * disagrees with the track list.
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
    await page.evaluate(() => {
      document.querySelector('[data-action="inspector-tab"][data-tab="audio"]')?.click();
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const open = await page.$('[data-action="open-focus"][data-focus="audio"]');
    if (open) await open.click();
    await new Promise((resolve) => setTimeout(resolve, 700));

    const layout = await page.evaluate(() => {
      const dock = document.querySelector(".focus-dock");
      if (!dock) return null;
      const body = document.querySelector(".focus-dock-body");
      const card = document.querySelector(".media-card.preview-large");
      const workspace = document.querySelector(".workspace.edit");
      const back = document.querySelector('[data-action="close-focus"]');
      const addMusic = document.querySelector('[data-action="add-music"]');
      const preview = document.querySelector('[data-action="audio-mix-preview"]');
      const box = (element) => (element ? element.getBoundingClientRect() : null);
      const dockBox = box(dock);
      const cardBox = box(card);
      const workspaceBox = box(workspace);
      const inView = (element) => {
        const rect = box(element);
        if (!rect) return false;
        return rect.top >= 0 && rect.bottom <= innerHeight && rect.width > 0;
      };
      return {
        dockBottom: Math.round(dockBox.bottom),
        bodyScrolls: body ? body.scrollHeight > body.clientHeight + 1 : false,
        pageScroll: document.documentElement.scrollHeight - innerHeight,
        hOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        backVisible: inView(back),
        addVisible: inView(addMusic),
        previewVisible: inView(preview),
        cardInside: cardBox && workspaceBox ? cardBox.bottom <= workspaceBox.bottom + 2 : true,
        tracks: document.querySelectorAll(".audio-track-card").length,
        placement: document.querySelectorAll(".audio-placement-row").length,
        sourceChip: document.querySelector(".audio-source-card .chip")?.textContent.trim() || "",
      };
    });
    if (!layout) {
      rows.push({ viewport: `${width}x${height}`, error: "no focus dock" });
      failed += 1;
      continue;
    }

    const bad = layout.dockBottom > height + 1
      || layout.pageScroll > 1
      || layout.hOverflow > 0
      || !layout.backVisible
      || !layout.addVisible
      || !layout.previewVisible
      || !layout.cardInside
      || !layout.sourceChip
      || layout.placement !== layout.tracks;
    if (bad) failed += 1;

    const label = width === 720 ? "200%" : `${width}x${height}`;
    await page.screenshot({ path: path.join(out, `audio-focus-${label}.png`) });
    rows.push({ viewport: label, ...layout, bad: bad || undefined });
  }

  await browser.close();
  console.log(JSON.stringify(rows, null, 2));
  if (failed) {
    console.error(`${failed} viewport(s) failed the Audio Focus layout check`);
    process.exit(1);
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
