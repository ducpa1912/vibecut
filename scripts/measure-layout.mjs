#!/usr/bin/env node
// Measure the six screens at two sizes with headless Chrome, and capture them.
//
// Usage:
//   node scripts/measure-layout.mjs --base "http://127.0.0.1:8797/?t=token" \
//     --project prj_... --out docs/teams/loop-10-layout-balance --phase before
//
// Prints one JSON line per screen and size: content bottom %, overlaps, scroll
// lists with count/fade, horizontal overflow, clipped labels, portrait width.

import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
const base = args.get("base");
const project = args.get("project");
const out = path.resolve(args.get("out") || "docs/teams/loop-10-layout-balance");
const phase = args.get("phase") || "after";
const chrome = args.get("chrome") || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = Number(args.get("port") || 9411);
if (!base || !project) { console.error("need --base and --project"); process.exit(2); }

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const SIZES = [[1440, 900], [1280, 800]];
const ROUTES = [
  ["welcome", "welcome"],
  ["check", `project/${project}/check`],
  ["edit", `project/${project}/edit`],
  ["clean-focus", `project/${project}/clean`],
  ["preview", `project/${project}/preview`],
  ["render", `project/${project}/render`],
];

async function waitForEndpoint() {
  for (let i = 0; i < 100; i += 1) {
    try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) return; } catch {}
    await sleep(100);
  }
  throw new Error("Chrome DevTools endpoint did not start");
}

class CDP {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
      }
    });
  }
  open() {
    return new Promise((resolve, reject) => {
      if (this.socket.readyState === WebSocket.OPEN) return resolve();
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
  }
  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  close() { this.socket.close(); }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression, returnByValue: true, awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

const MEASURE = String.raw`(() => {
  const vw = innerWidth, vh = innerHeight;
  const clippedByScroll = (el, r) => {
    let node = el.parentElement;
    while (node) {
      const s = getComputedStyle(node);
      if (['auto', 'scroll', 'hidden'].includes(s.overflowY) || ['auto', 'scroll', 'hidden'].includes(s.overflowX)) {
        const box = node.getBoundingClientRect();
        if (r.bottom <= box.top + 1 || r.top >= box.bottom - 1 || r.right <= box.left + 1 || r.left >= box.right - 1) return true;
      }
      node = node.parentElement;
    }
    return false;
  };
  const seen = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) < 0.02) return null;
    const r = el.getBoundingClientRect();
    if (r.width < 3 || r.height < 3 || r.bottom < 0 || r.top > vh) return null;
    if (clippedByScroll(el, r)) return null;
    return r;
  };
  // Chips, timecodes and scene labels sit on media by design: not layout overlaps.
  const designed = (el) => Boolean(el.closest('.tc, .chip, .scene-label, .layer-flag, .transcript-overlay, .transcript-panel, .status, .badge, .thumb .label, .duration, .media-badge, .split-tag, .media-overlay, .cleaning-pill'));
  const screen = document.querySelector('main.screen') || document.body;
  let bottom = 0, who = '';
  const visibleBottom = (el, r) => {
    let bottom = r.bottom;
    let node = el.parentElement;
    while (node) {
      const s = getComputedStyle(node);
      if (['auto', 'scroll', 'hidden'].includes(s.overflowY)) {
        bottom = Math.min(bottom, node.getBoundingClientRect().bottom);
      }
      node = node.parentElement;
    }
    return bottom;
  };
  for (const el of screen.querySelectorAll('*')) {
    const r = seen(el);  // seen() drops anything a scroll container has clipped
    if (!r) continue;
    const b = visibleBottom(el, r);
    if (b > bottom) { bottom = b; who = (el.className && String(el.className).split(' ')[0]) || el.tagName; }
  }
  const boxes = [];
  for (const el of document.body.querySelectorAll('*')) {
    const r = seen(el);
    if (!r) continue;
    const tag = el.tagName.toLowerCase();
    if (['script','style','path','svg','i','br'].includes(tag)) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').trim();
    const img = tag === 'img' || tag === 'video';
    const button = tag === 'button' && !el.querySelector('*');
    const text = own.length >= 2 && !el.querySelector('img, video');
    if (!img && !button && !text) continue;
    if (text && el.closest('button, a, label') && el.querySelector('*')) continue;
    boxes.push({ r, kind: img ? 'img' : button ? 'button' : 'text', text: (own || el.getAttribute('alt') || el.textContent || '').trim().slice(0, 22), el });
  }
  const overlaps = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ix = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const iy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (ix > 2 && iy > 2) {
        const intended = designed(a.el) || designed(b.el);
        overlaps.push({
          a: a.kind + ':' + a.text, b: b.kind + ':' + b.text, area: Math.round(ix * iy),
          aCls: String(a.el.className || a.el.tagName).split(' ')[0],
          bCls: String(b.el.className || b.el.tagName).split(' ')[0],
          intended,
        });
      }
    }
  }
  const scrolls = [];
  for (const el of document.querySelectorAll('*')) {
    const s = getComputedStyle(el);
    if (!['auto', 'scroll'].includes(s.overflowY)) continue;
    if (el.scrollHeight <= el.clientHeight + 4) continue;
    const box = seen(el);
    if (!box) continue;
    const host = el.closest('.panel, aside, section') || el.parentElement || el;
    const full = (host.textContent || '').slice(0, 2000);
    const headEl = host.querySelector('h2, h3') || host.querySelector('.layer-head, .panel-head, .render-queue-head, .scene-strip-head, .section-head');
    const head = headEl ? headEl.textContent.trim() : full.slice(0, 200);
    scrolls.push({
      cls: String(el.className || el.tagName).split(' ')[0],
      over: el.scrollHeight - el.clientHeight,
      head,
      count: /\d+\s*(of|\/)\s*\d+/i.test(full)
        || /\d+\s*(scenes|layers|cues|jobs|renders|proofs|effects|shown|total)/i.test(full)
        || /\b(all|yours)\s+\d+/i.test(full),
      fade: el.classList.contains('has-more') || s.maskImage !== 'none' || s.webkitMaskImage !== 'none',
    });
  }
  const doc = document.documentElement;
  const clipped = [];
  for (const el of document.querySelectorAll('button, .btn')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 8 && !el.closest('.path, .small')) {
      clipped.push({ cls: String(el.className || el.tagName).split(' ')[0], text: (el.textContent || '').trim().slice(0, 24) });
    }
  }
  const left = document.querySelector('.render-left');
  const right = document.querySelector('.render-right');
  const stage = document.querySelector('.preview-stage');
  const mainCol = document.querySelector('.preview-main');
  const portrait = stage && stage.classList.contains('portrait-stage');
  return {
    vw, vh,
    bottom: Math.round(bottom), bottomPct: Math.round((bottom / vh) * 1000) / 10, bottomWho: who,
    overlaps: overlaps.slice(0, 40), overlapCount: overlaps.length,
    layoutOverlaps: overlaps.filter((item) => !item.intended), layoutOverlapCount: overlaps.filter((item) => !item.intended).length,
    scrolls, hScroll: doc.scrollWidth > doc.clientWidth + 1, clipped: clipped.slice(0, 12),
    renderCols: left && right ? {
      left: Math.round(left.getBoundingClientRect().height),
      right: Math.round(right.getBoundingClientRect().height),
      leftBottomPct: Math.round((left.getBoundingClientRect().bottom / vh) * 1000) / 10,
    } : null,
    preview: stage && mainCol ? {
      portrait: Boolean(portrait),
      stage: Math.round(stage.getBoundingClientRect().width),
      main: Math.round(mainCol.getBoundingClientRect().width),
      pct: Math.round((stage.getBoundingClientRect().width / Math.max(1, mainCol.getBoundingClientRect().width)) * 1000) / 10,
    } : null,
  };
})()`;

await mkdir(out, { recursive: true });
const chromeProcess = spawn(chrome, [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
  "--no-default-browser-check", `--remote-debugging-port=${port}`,
  `--user-data-dir=/tmp/duck-layout-chrome-${port}`, "--window-size=1440,900", "about:blank",
], { stdio: "ignore" });

try {
  await waitForEndpoint();
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  const report = {};
  for (const [width, height] of SIZES) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: false,
    });
    for (const [name, route] of ROUTES) {
      await cdp.send("Page.navigate", { url: `${base}#/${route}` });
      for (let i = 0; i < 60; i += 1) {
        const ready = await evaluate(cdp, `Boolean(document.querySelector('main.screen'))`).catch(() => false);
        if (ready) break;
        await sleep(250);
      }
      await sleep(2600);
      const size = `${width}x${height}`;
      let data;
      try { data = await evaluate(cdp, MEASURE); } catch (error) { data = { error: String(error) }; }
      if (name === "edit") {
        const count = await evaluate(cdp, `document.querySelectorAll('.layer-row').length`).catch(() => 0);
        data.layerRows = count;
      }
      report[`${name}-${size}`] = data;
      const shot = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 82, captureBeyondViewport: false });
      await writeFile(path.join(out, `${phase}-${name}-${size}.jpg`), Buffer.from(shot.data, "base64"));
    }
  }
  cdp.close();
  await writeFile(path.join(out, `${phase}-measure.json`), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
} finally {
  chromeProcess.kill("SIGTERM");
}
