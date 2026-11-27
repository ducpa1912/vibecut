#!/usr/bin/env node
/*
 * Check Script Focus at the small sizes and at 200 % zoom.
 *
 *   NODE_PATH="$(npm root -g)" node scripts/check-script-focus-layout.cjs \
 *     --base "http://127.0.0.1:8813/?t=scratch-3a" \
 *     --project prj_e95348a97316 --out build/opencode-3a
 *
 * Needs the shared Chromium under ~/Library/Caches/ms-playwright and the
 * globally installed puppeteer-core. The dev server must already be running.
 * Fails (exit 1) when the preview paints over the focus dock, when the card
 * loses the media aspect ratio, when the page scrolls as one document, or when
 * a row timecode no longer seeks and keeps exactly one current row in view.
 * At 200 % the workspace is hidden on purpose; the row records preview: "hidden".
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
const sizes = [
  [800, 600, 3], [1024, 700, 5], [1100, 800, 6], [1200, 800, 6],
  [1280, 800, 6], [1440, 900, 6], [720, 450, 3],
];

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

  for (const [width, height, minRows] of sizes) {
    await page.setViewport({ width, height, deviceScaleFactor: width === 720 ? 2 : 1 });
    await page.goto(`${base}#/project/${project}/edit`, { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1800));
    await page.evaluate(() => {
      document.querySelector('[data-action="inspector-tab"][data-tab="script"]')?.click();
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const open = await page.$('[data-action="open-focus"][data-focus="script"]');
    if (open) await open.click();
    await new Promise((resolve) => setTimeout(resolve, 600));

    const layout = await page.evaluate(() => {
      const card = document.querySelector(".media-card.preview-large");
      const dock = document.querySelector(".focus-dock");
      const list = document.querySelector("[data-script-scroll]");
      if (!dock) return null;
      const dockBox = dock.getBoundingClientRect();
      const cardBox = card ? card.getBoundingClientRect() : null;
      const ratio = cardBox && cardBox.height ? cardBox.width / cardBox.height : 0;
      const mediaRatio = card
        ? Number(getComputedStyle(card).getPropertyValue("--media-ratio")) || 1.7778
        : 0;
      const rows = [...document.querySelectorAll(".focus-edit-row")];
      const listBox = list ? list.getBoundingClientRect() : null;
      const visibleRows = listBox
        ? rows.filter((row) => {
          const box = row.getBoundingClientRect();
          return box.top >= listBox.top - 1 && box.bottom <= listBox.bottom + 1;
        }).length
        : 0;
      return {
        preview: cardBox && cardBox.width ? "shown" : "hidden",
        card: cardBox ? [Math.round(cardBox.width), Math.round(cardBox.height)] : null,
        ratioError: ratio ? Math.abs(ratio - mediaRatio) : 0,
        objectFit: card ? getComputedStyle(card.querySelector("video,img") || card).objectFit : "",
        overlap: cardBox ? Math.max(0, Math.round(cardBox.bottom - dockBox.top)) : 0,
        pageScroll: document.documentElement.scrollHeight - innerHeight,
        hOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        visibleRows,
        seeks: document.querySelectorAll('[data-action="script-seek"]').length,
      };
    });
    if (!layout) {
      rows.push({ viewport: `${width}x${height}`, error: "no focus dock" });
      failed += 1;
      continue;
    }

    let seek = null;
    if (layout.seeks > 0) {
      await page.evaluate(() => {
        const buttons = [...document.querySelectorAll('[data-action="script-seek"]')];
        buttons[Math.min(20, buttons.length - 1)].click();
      });
      await new Promise((resolve) => setTimeout(resolve, 500));
      seek = await page.evaluate(() => {
        const list = document.querySelector("[data-script-scroll]");
        const current = [...document.querySelectorAll(".focus-edit-row.is-current")];
        if (!current.length || !list) return { current: current.length, inView: null };
        const box = current[0].getBoundingClientRect();
        const view = list.getBoundingClientRect();
        return {
          current: current.length,
          inView: box.top >= view.top - 2 && box.bottom <= view.bottom + 2,
        };
      });
    }

    const label = width === 720 ? "200%" : `${width}x${height}`;
    await page.screenshot({ path: path.join(out, `script-focus-${label}.png`) });
    const bad = layout.overlap > 0 || layout.pageScroll > 1 || layout.hOverflow > 0
      || layout.ratioError > 0.02
      || layout.objectFit !== "contain"
      || layout.visibleRows < minRows
      || (seek && (seek.current !== 1 || seek.inView === false));
    if (bad) failed += 1;
    rows.push({ viewport: label, ...layout, minRows, seek, bad: bad || undefined });
  }

  await browser.close();
  console.log(JSON.stringify(rows, null, 2));
  if (failed) {
    console.error(`${failed} viewport(s) failed the Script Focus layout check`);
    process.exit(1);
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
