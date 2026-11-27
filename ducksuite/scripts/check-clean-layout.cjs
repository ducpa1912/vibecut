#!/usr/bin/env node
/*
 * Check the Clean inspector at the small sizes and at 200 % zoom.
 *
 *   NODE_PATH="$(npm root -g)" node scripts/check-clean-layout.cjs \
 *     --base "http://127.0.0.1:8813/?t=scratch-3a" \
 *     --project prj_e95348a97316 --out build/opencode-3a
 *
 * Needs the shared Chromium under ~/Library/Caches/ms-playwright and the
 * globally installed puppeteer-core. The dev server must already be running.
 * Prints one JSON line per viewport: the list height, how many layer rows are
 * on screen, and whether selecting a row then pressing Off reaches the API.
 */
const fs = require("node:fs/promises");
const path = require("node:path");
const puppeteer = require("puppeteer-core");

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}
const base = args.get("base");
const project = args.get("project");
const out = path.resolve(args.get("out") || "build");
const sizes = [[800, 600], [1024, 700], [1280, 800], [1440, 900], [720, 450]];

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

  for (const [width, height] of sizes) {
    await page.setViewport({ width, height });
    await page.goto(`${base}#/project/${project}/edit`, { waitUntil: "networkidle0" });
    await new Promise((resolve) => setTimeout(resolve, 1800));
    await page.evaluate(() => {
      document.querySelector('[data-action="inspector-tab"][data-tab="clean"]')?.click();
    });
    await new Promise((resolve) => setTimeout(resolve, 400));

    const before = await page.evaluate(() => {
      const list = document.querySelector(".layer-list");
      const layerRows = [...document.querySelectorAll(".layer-row")];
      const visible = layerRows.filter((row) => {
        const box = row.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= innerHeight;
      }).length;
      return {
        list: list ? Math.round(list.getBoundingClientRect().height) : 0,
        rows: layerRows.length,
        visible,
        first: layerRows[0] ? Math.round(layerRows[0].getBoundingClientRect().top) : null,
      };
    });

    // The row and the Fill / Blur / Off buttons must still drive the layer.
    await page.click(".layer-row");
    await new Promise((resolve) => setTimeout(resolve, 300));
    const selected = await page.evaluate(() => ({
      row: document.querySelector(".layer-row.is-active")?.textContent.trim().slice(0, 20) || "",
      layer: document.querySelector('[data-action="clean-action"]')?.dataset.layer || "",
    }));
    const off = await page.$('[data-action="clean-action"][data-kind="exclude"]');
    if (off) await off.click();
    await new Promise((resolve) => setTimeout(resolve, 900));
    const afterOff = await page.evaluate(() => ({
      off: document.querySelector(".layer-row.is-active")?.classList.contains("is-off") || false,
      kind: document.querySelector(".layer-row.is-active .layer-kind")?.textContent || "",
    }));

    const label = width === 720 ? "200%" : `${width}x${height}`;
    await page.screenshot({ path: path.join(out, `clean-${label}.png`) });
    rows.push({ viewport: label, ...before, selected, afterOff });
  }

  await browser.close();
  console.log(JSON.stringify(rows, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
