#!/usr/bin/env node
// Measure reachable screens at several sizes with headless Chrome, and capture them.
//
// Usage:
//   node scripts/measure-layout.mjs --base "http://127.0.0.1:8797/?t=token" \
//     --project prj_... --out docs/teams/loop-10-layout-balance --phase before
//
// Default sizes: 1440x900, 1280x800, 1024x700 and 512x350 (the CSS viewport a
// 1024x700 window gives at 200 % zoom). Pass --sizes "1440x900,1280x800" to
// narrow it. Project screens are skipped without --project.
//
// Prints one JSON line per screen and size: content bottom %, overlaps, scroll
// lists with count/fade, horizontal overflow, clipped labels, portrait width.

import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
const base = args.get("base");
const project = args.get("project") || "";
const out = path.resolve(args.get("out") || "docs/teams/loop-10-layout-balance");
const phase = args.get("phase") || "after";
const chrome = args.get("chrome") || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = Number(args.get("port") || 9411);
if (!base) { console.error("need --base"); process.exit(2); }

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const SIZES = (args.get("sizes") || "1440x900,1280x800,1024x700,512x350")
  .split(",")
  .map((pair) => pair.trim().split("x").map(Number))
  .filter(([w, h]) => w > 0 && h > 0);
const ROUTES = [
  ["welcome", "welcome"],
  ...(project ? [
    ["check", `project/${project}/check`],
    ["edit", `project/${project}/edit`],
    ["clean-focus", `project/${project}/clean`],
    ["preview", `project/${project}/preview`],
    ["render", `project/${project}/render`],
  ] : []),
];
// Modals reachable without footage: Settings (Local engine / Models) and the
// project Import dialog. Each opens from a known button after a route loads.
const MODALS = [
  ["settings", "welcome", '[data-action="settings"]'],
  ...(project ? [["import", `project/${project}/edit`, '[data-action="import"]']] : []),
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
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}

const MEASURE = String.raw`(rootSelector) => {
  const vw = innerWidth, vh = innerHeight;
  const root = rootSelector ? (document.querySelector(rootSelector) || document.body) : document.body;
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
  const designed = (el) => Boolean(el.closest('.tc, .duration, .media-badge, .split-tag, .media-overlay, .proof-box'));
  const screen = rootSelector ? root : (document.querySelector('main.screen') || document.body);
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
  for (const el of root.querySelectorAll('*')) {
    const r = seen(el);
    if (!r) continue;
    const tag = el.tagName.toLowerCase();
    if (['script','style','path','svg','i','br'].includes(tag)) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').trim();
    const img = tag === 'img' || tag === 'video';
    // A control with an icon is still a control: its own children hide its box.
    const button = tag === 'button' || el.classList.contains('btn');
    const text = !button && own.length >= 2 && !el.querySelector('img, video');
    if (!img && !button && !text) continue;
    if (text && el.closest('button, a, label') && el.querySelector('*')) continue;
    if (!button && el.closest('button, .btn')) continue;
    boxes.push({ r, kind: img ? 'img' : button ? 'button' : 'text', text: (own || el.getAttribute('aria-label') || el.getAttribute('alt') || el.textContent || '').trim().slice(0, 22), el });
  }
  const overlaps = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const clamp = (el, r) => {
        let box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        let node = el.parentElement;
        while (node) {
          const s = getComputedStyle(node);
          if (['auto', 'scroll', 'hidden'].includes(s.overflowY) || ['auto', 'scroll', 'hidden'].includes(s.overflowX)) {
            const n = node.getBoundingClientRect();
            box = { left: Math.max(box.left, n.left), right: Math.min(box.right, n.right), top: Math.max(box.top, n.top), bottom: Math.min(box.bottom, n.bottom) };
          }
          node = node.parentElement;
        }
        return box;
      };
      const ca = clamp(a.el, a.r), cb = clamp(b.el, b.r);
      const ix = Math.min(ca.right, cb.right) - Math.max(ca.left, cb.left);
      const iy = Math.min(ca.bottom, cb.bottom) - Math.max(ca.top, cb.top);
      if (ix > 2 && iy > 2) {
        const stageOf = (el) => el.closest('.proof-frame') || el.closest('.media-card') || el.closest('.split-stage');
        const playerPair = (a.kind === 'img' || b.kind === 'img')
          && stageOf(a.el) && stageOf(a.el) === stageOf(b.el);
        const intended = designed(a.el) || designed(b.el) || playerPair;
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
  for (const el of root.querySelectorAll('*')) {
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
  for (const el of root.querySelectorAll('button, .btn')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 8 && !el.closest('.path')) {
      clipped.push({ cls: String(el.className || el.tagName).split(' ')[0], text: (el.textContent || '').trim().slice(0, 24) });
    }
  }
  // A control past the right or left viewport edge is cut off even when
  // overflow-x: hidden keeps documentElement.scrollWidth quiet.
  const offscreen = [];
  for (const el of root.querySelectorAll('button, input, select, .btn, h1, h2, h3, .toolbar-tabs')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.right > vw + 1 || r.left < -1) {
      offscreen.push({
        cls: String(el.className || el.tagName).split(' ')[0],
        text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 24),
        left: Math.round(r.left), right: Math.round(r.right),
      });
    }
  }
  // Labels that clip their own text (nowrap + overflow hidden).
  const cutLabels = [];
  for (const el of root.querySelectorAll('h1, h2, h3, .small, .meta, .kv span, .kv strong, label, .chip, .toolbar-tab')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    if (!['hidden', 'clip'].includes(s.overflowX) && s.whiteSpace !== 'nowrap') continue;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 8) {
      cutLabels.push({ cls: String(el.className || el.tagName).split(' ')[0], text: (el.textContent || '').trim().slice(0, 30) });
    }
  }
  let media = null;
  let mediaArea = 0;
  for (const el of document.querySelectorAll('.preview-stage img, .preview-stage video, .preview-block img, .preview-block video, .media-card img, .media-card video')) {
    const b = el.getBoundingClientRect();
    const nw = Number(el.naturalWidth || el.videoWidth || 0);
    const nh = Number(el.naturalHeight || el.videoHeight || 0);
    const area = b.width * b.height;
    if (nw > 0 && nh > 0 && area > mediaArea) { media = el; mediaArea = area; }
  }
  const stageBox = document.querySelector('.preview-stage') || document.querySelector('.media-card.preview-large') || document.querySelector('.media-card.hug');
  let picture = null, pictureShare = null, stageBlack = null;
  if (media && stageBox) {
    const box = media.getBoundingClientRect();
    const nw = Number(media.naturalWidth || media.videoWidth || 0);
    const nh = Number(media.naturalHeight || media.videoHeight || 0);
    let pw = box.width, ph = box.height;
    if (nw > 0 && nh > 0) {
      const fit = Math.min(box.width / nw, box.height / nh);
      pw = nw * fit; ph = nh * fit;
    }
    const stage = stageBox.getBoundingClientRect();
    picture = { w: Math.round(pw), h: Math.round(ph), box: [Math.round(box.x), Math.round(box.y)] };
    const column = (stageBox.closest('.preview-main') || stageBox.parentElement || stageBox).getBoundingClientRect();
    // A portrait picture is judged on height, a landscape one on width: its dominant fit.
    const share = Math.max(pw / Math.max(1, column.width), ph / Math.max(1, column.height));
    pictureShare = Math.round(share * 1000) / 10;
    stageBlack = Math.round((stage.width - pw) / 2);
  }
  let controls = null;
  const overlay = document.querySelector('.transcript-overlay');
  if (overlay && media) {
    const o = overlay.getBoundingClientRect();
    const m = media.getBoundingClientRect();
    const barTop = m.bottom - 52;
    const ix = Math.min(o.right, m.right) - Math.max(o.left, m.left);
    const iy = Math.min(o.bottom, m.bottom) - Math.max(o.top, barTop);
    const hit = document.elementFromPoint(Math.round(m.left + 20), Math.round(m.bottom - 26));
    controls = {
      overlap: ix > 1 && iy > 1 ? Math.round(ix * iy) : 0,
      hit: hit ? String(hit.className || hit.tagName).split(' ')[0] : 'none',
      clickable: Boolean(hit && (hit === media || media.contains(hit))),
    };
  }
  const cut = [];
  for (const el of root.querySelectorAll('*')) {
    const s = getComputedStyle(el);
    if (!['auto', 'scroll'].includes(s.overflowY)) continue;
    const fade = el.classList.contains('has-more') || s.maskImage !== 'none' || s.webkitMaskImage !== 'none';
    if (fade) continue;
    const box = el.getBoundingClientRect();
    for (const child of el.querySelectorAll('*')) {
      const own = [...child.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('').trim();
      if (own.length < 2) continue;
      const c = child.getBoundingClientRect();
      if (c.height < 4 || c.bottom > box.bottom + 1 || c.top < box.top) continue;
      if (c.bottom > box.bottom - 1 && c.top < box.bottom) { cut.push({ cls: String(child.className || child.tagName).split(' ')[0], text: own.slice(0, 20) }); break; }
    }
  }
  const rgb = (value) => {
    const text = String(value || '');
    const m = text.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const parts = m[1].split(',').map((x) => parseFloat(x));
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    }
    const c = text.match(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)/);
    if (c) {
      return { r: parseFloat(c[1]) * 255, g: parseFloat(c[2]) * 255, b: parseFloat(c[3]) * 255, a: c[4] === undefined ? 1 : parseFloat(c[4]) };
    }
    return null;
  };
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const contrast = (a, b) => {
    const la = lum(a), lb = lum(b);
    return Math.round(((Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)) * 100) / 100;
  };
  const nativeControls = document.querySelectorAll('video[controls]').length;
  const controlBoxes = [];
  for (const el of document.querySelectorAll('.player-bar button, .player-bar .player-time, .player-bar .player-scrub, .media-overlay .tc, .overlay-toggle')) {
    const b = el.getBoundingClientRect();
    if (b.width > 2 && b.height > 2) controlBoxes.push({ el, b, cls: String(el.className || el.tagName).split(' ')[0] });
  }
  let controlOverlaps = 0;
  for (let i = 0; i < controlBoxes.length; i += 1) for (let j = i + 1; j < controlBoxes.length; j += 1) {
    const a = controlBoxes[i].b, b = controlBoxes[j].b;
    const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ix > 1 && iy > 1) controlOverlaps += 1;
  }
  const stepOverlaps = (() => {
    const steps = [...document.querySelectorAll('.proof-step')].map((el) => el.getBoundingClientRect());
    const controls = [...document.querySelectorAll('.player-bar button, .player-bar .player-time, .player-bar .player-scrub, .media-overlay button, .media-overlay .tc, .split-tag')].map((el) => el.getBoundingClientRect());
    let hits = 0;
    for (const s of steps) for (const c of controls) {
      const ix = Math.min(s.right, c.right) - Math.max(s.left, c.left);
      const iy = Math.min(s.bottom, c.bottom) - Math.max(s.top, c.top);
      if (ix > 1 && iy > 1) hits += 1;
    }
    return hits;
  })();
  const transcriptHit = (() => {
    const controls = [...document.querySelectorAll('.player-bar button, .player-bar input, .media-overlay button')];
    let blocked = 0;
    const who = [];
    for (const el of controls) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (!hit) continue;
      if (!(hit === el || el.contains(hit) || (el.closest('.player-bar') || el).contains(hit))) {
        blocked += 1;
        who.push(String(hit.className || hit.tagName).slice(0, 30));
      }
    }
    return { blocked, who: who.slice(0, 5) };
  })();
  const side = document.querySelector('.transcript-side');
  let transcript = null;
  if (side) {
    const s = side.getBoundingClientRect();
    const picBox = media ? media.getBoundingClientRect() : null;
    const ix = picBox ? Math.min(s.right, picBox.right) - Math.max(s.left, picBox.left) : 0;
    const iy = picBox ? Math.min(s.bottom, picBox.bottom) - Math.max(s.top, picBox.top) : 0;
    const p = side.querySelector('.transcript-side-copy');
    const fg = rgb(p ? getComputedStyle(p).color : '');
    const bg = rgb(getComputedStyle(side).backgroundColor);
    const lineHeight = p ? parseFloat(getComputedStyle(p).lineHeight) || 15 : 15;
    transcript = {
      intersect: ix > 1 && iy > 1 ? Math.round(ix * iy) : 0,
      contrast: fg && bg ? contrast(fg, bg) : null,
      lines: p ? Math.max(1, Math.round(p.getBoundingClientRect().height / lineHeight)) : 0,
    };
  }
  const listEl = document.querySelector('.proof-list');
  let listEdges = null;
  if (listEl) {
    const panel = listEl.closest('.panel');
    const line = panel ? rgb(getComputedStyle(panel).borderTopColor) : null;
    const lineLum = line ? lum(line) : null;
    const dark = [];
    for (const el of [listEl, ...listEl.querySelectorAll('.proof-row')]) {
      const s = getComputedStyle(el);
      for (const sideName of ['borderTop', 'borderRight', 'borderBottom', 'borderLeft', 'outlineTop']) {
        const width = parseFloat(s[sideName + 'Width'] || 0);
        if (!width) continue;
        const c = rgb(s[sideName + 'Color'] || '');
        if (!c || c.a === 0) continue;
        if (lineLum !== null && lum(c) < lineLum - 0.01) dark.push({ cls: String(el.className || el.tagName).split(' ')[0], side: sideName, color: s[sideName + 'Color'] });
      }
    }
    listEdges = { dark: dark.length, sample: dark.slice(0, 4) };
  }
  const videoBars = [];
  for (const v of document.querySelectorAll('video')) {
    const bar = v.parentElement?.querySelector('[data-player-bar]') || v.closest('.media-card, .modal-body, .split-stage')?.querySelector('[data-player-bar]');
    const info = { hasBar: Boolean(bar), play: false, mute: false, volume: false, full: false, muted: null, vol: null, fullcall: null };
    if (bar) {
      info.play = Boolean(bar.querySelector('.player-play'));
      info.mute = Boolean(bar.querySelector('.player-mute'));
      info.volume = Boolean(bar.querySelector('.player-volume'));
      info.full = Boolean(bar.querySelector('.player-full'));
      const m = bar.querySelector('.player-mute');
      if (m) { const before = v.muted; m.click(); info.muted = v.muted; v.muted = before; m.setAttribute('aria-pressed', String(before)); }
      const vol = bar.querySelector('.player-volume');
      if (vol) { const before = v.volume; vol.value = '0.35'; vol.dispatchEvent(new Event('input', { bubbles: true })); info.vol = Math.round(v.volume * 100) / 100; v.volume = before; vol.value = String(before); }
      const f = bar.querySelector('.player-full');
      if (f) {
        const stage = v.closest('.media-card, .split-stage, .modal-body');
        if (stage) {
          const old = stage.requestFullscreen;
          let called = false;
          stage.requestFullscreen = () => { called = true; return Promise.resolve(); };
          f.click();
          info.fullcall = called;
          stage.requestFullscreen = old;
        }
      }
    }
    videoBars.push(info);
  }
  const filter = document.querySelector('.scene-filter input');
  const filterPanel = filter ? filter.closest('.panel') : null;
  let filterInsets = null;
  if (filter && filterPanel) {
    const f = filter.getBoundingClientRect();
    const pane = filterPanel.getBoundingClientRect();
    const style = getComputedStyle(filterPanel);
    const innerLeft = pane.left + parseFloat(style.borderLeftWidth || 0);
    const innerRight = pane.right - parseFloat(style.borderRightWidth || 0);
    const label = document.querySelector('.scene-filter .small');
    const l = label ? label.getBoundingClientRect() : f;
    filterInsets = { left: Math.round(Math.min(l.left, f.left) - innerLeft), right: Math.round(innerRight - f.right) };
  }
  const left = document.querySelector('.render-left');
  const right = document.querySelector('.render-right');
  const stage = document.querySelector('.preview-stage');
  const mainCol = document.querySelector('.preview-main');
  const portrait = stage && stage.classList.contains('portrait-stage');
  // The Edit bar carries the frame timecode next to the clock. With no footage
  // there is no real bar, so mount the same markup in a 340 px host: that is
  // the tightest Edit column at 1024x700.
  const timecode = (() => {
    const read = (bar) => {
      const time = bar.querySelector('.player-time');
      const tc = bar.querySelector('.player-tc');
      const bench = bar.querySelector('.player-play');
      const box = bar.getBoundingClientRect();
      const inside = (el) => {
        const r = el?.getBoundingClientRect();
        return Boolean(r && r.right <= box.right + 1 && r.left >= box.left - 1);
      };
      const sameLine = (a, b) => {
        const ra = a?.getBoundingClientRect(), rb = b?.getBoundingClientRect();
        return Boolean(ra && rb && Math.abs(ra.top - rb.top) < Math.max(ra.height, rb.height) / 2);
      };
      return {
        text: tc ? tc.textContent.trim() : '',
        barFits: bar.scrollWidth <= bar.clientWidth + 1,
        timeLines: time ? time.getClientRects().length : 0,
        tcLines: tc ? tc.getClientRects().length : 0,
        sameLine: sameLine(time, tc),
        tcInside: inside(tc),
        benchVisible: inside(bench),
        barWidth: Math.round(box.width),
        contentWidth: bar.scrollWidth,
      };
    };
    const probeAt = (width) => {
      const card = document.createElement('div');
      card.className = 'media-card preview-large';
      card.style.cssText = 'position:fixed;left:-9999px;top:0;width:' + width + 'px;height:120px;--media-ratio:1.7778';
      card.innerHTML = '<div class="player-bar" data-player-bar><button class="player-play" type="button">p</button><span class="player-time">59:59 / 59:59</span><span class="player-tc">59:59:29</span><input class="player-scrub" type="range" min="0" max="1000" value="0" aria-label="Seek"><button class="player-mute" type="button">m</button><input class="player-volume" type="range" min="0" max="1" value="1" aria-label="Volume"><button class="player-full" type="button">f</button></div>';
      document.body.appendChild(card);
      const result = read(card.firstElementChild);
      card.remove();
      return result;
    };
    const real = document.querySelector('[data-player-bar] [data-player-tc]')?.closest('[data-player-bar]') || null;
    return {
      real: real ? read(real) : null,
      probe340: probeAt(340),
      probe132: probeAt(132),
    };
  })();
  return {
    vw, vh,
    bottom: Math.round(bottom), bottomPct: Math.round((bottom / vh) * 1000) / 10, bottomWho: who,
    overlaps: overlaps.slice(0, 40), overlapCount: overlaps.length,
    layoutOverlaps: overlaps.filter((item) => !item.intended), layoutOverlapCount: overlaps.filter((item) => !item.intended).length,
    scrolls, hScroll: doc.scrollWidth > doc.clientWidth + 1, clipped: clipped.slice(0, 12), offscreen: offscreen.slice(0, 20), cutLabels: cutLabels.slice(0, 12),
    picture, pictureShare, stageBlack, controls, cutText: cut.length, cut, filterInsets,
    nativeControls, controlOverlaps, transcript, listEdges, videoBars, stepOverlaps, transcriptHit, timecode,
    renderCols: left && right ? {
      left: Math.round(left.getBoundingClientRect().width),
      right: Math.round(right.getBoundingClientRect().width),
      leftHeight: Math.round(left.getBoundingClientRect().height),
      leftBottomPct: Math.round((left.getBoundingClientRect().bottom / vh) * 1000) / 10,
      workspace: Math.round((left.parentElement?.getBoundingClientRect().width) || 0),
      workspaceScroll: left.parentElement?.scrollWidth || 0,
    } : null,
    preview: stage && mainCol ? {
      portrait: Boolean(portrait),
      stage: Math.round(stage.getBoundingClientRect().width),
      main: Math.round(mainCol.getBoundingClientRect().width),
      pct: Math.round((stage.getBoundingClientRect().width / Math.max(1, mainCol.getBoundingClientRect().width)) * 1000) / 10,
    } : null,
  };
}`;

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
  const waitScreen = async () => {
    for (let i = 0; i < 60; i += 1) {
      const ready = await evaluate(cdp, `Boolean(document.querySelector('main.screen'))`).catch(() => false);
      if (ready) break;
      await sleep(250);
    }
  };
  for (const [width, height] of SIZES) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: false,
    });
    const size = `${width}x${height}`;
    for (const [name, route] of ROUTES) {
      await evaluate(cdp, `(() => { const r = document.querySelector('#modal-root'); if (r) r.innerHTML = ''; return true; })()`).catch(() => false);
      await cdp.send("Page.navigate", { url: `${base}#/${route}` });
      await waitScreen();
      await sleep(2600);
      let data;
      try { data = await evaluate(cdp, `(${MEASURE})('')`); } catch (error) { data = { error: String(error) }; }
      if (name === "edit") {
        const count = await evaluate(cdp, `document.querySelectorAll('.layer-row').length`).catch(() => 0);
        data.layerRows = count;
      }
      report[`${name}-${size}`] = data;
      const shot = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 82, captureBeyondViewport: false });
      await writeFile(path.join(out, `${phase}-${name}-${size}.jpg`), Buffer.from(shot.data, "base64"));
    }
    for (const [name, route, opener] of MODALS) {
      await evaluate(cdp, `(() => { const r = document.querySelector('#modal-root'); if (r) r.innerHTML = ''; return true; })()`).catch(() => false);
      await cdp.send("Page.navigate", { url: `${base}#/${route}` });
      await waitScreen();
      await sleep(1400);
      const opened = await evaluate(cdp, `(() => { const b = document.querySelector(${JSON.stringify(opener)}); if (!b) return false; b.click(); return true; })()`).catch(() => false);
      await sleep(900);
      const modal = await evaluate(cdp, `Boolean(document.querySelector('.modal'))`).catch(() => false);
      let data;
      try { data = await evaluate(cdp, `(${MEASURE})('.modal')`); } catch (error) { data = { error: String(error) }; }
      data.opened = Boolean(opened);
      data.modal = Boolean(modal);
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
