/**
 * Recent previews for the Voice Room.
 *
 * A small store on this Mac: the last voices that actually started speaking,
 * newest first, capped at 20. Storage failures and corrupt JSON degrade to an
 * empty list; reading or writing recents never throws into the page.
 *
 * Entry shape:
 *   { kind: "stock" | "clone", engine, voice, clone?, label, timestamp }
 *
 * The page replays an entry through the same path as the library: stock voices
 * through play(engine, voice, label), clones through playMine(item).
 */

import { el } from "./ui.js";

export const RECENT_KEY = "vibecut.voice.recent.v1";
export const MAX_RECENT = 20;
export const EMPTY_HINT = "Nothing yet. Play a voice and it appears here.";

function storage() {
  try {
    return globalThis.localStorage || null;
  } catch (_) {
    return null;
  }
}

function text(value, limit) {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

/** One stored row, or null when it cannot be replayed. */
function cleanRow(value) {
  if (!value || typeof value !== "object") return null;
  const kind = value.kind === "stock" || value.kind === "clone" ? value.kind : "";
  if (!kind) return null;
  const label = text(value.label, 120);
  const engine = text(value.engine, 40);
  const voice = text(value.voice, 200);
  const clone = text(value.clone, 200);
  const timestamp = Number(value.timestamp);
  if (!label || !Number.isFinite(timestamp) || timestamp <= 0) return null;
  if (kind === "stock" && (!engine || !voice)) return null;
  if (kind === "clone" && !clone && !voice) return null;
  const row = { kind, engine, voice: voice || clone, label, timestamp };
  if (kind === "clone") row.clone = clone || voice;
  return row;
}

function signature(row) {
  return `${row.kind}|${row.engine}|${row.voice}|${row.clone || ""}`;
}

function writeRecent(rows) {
  try {
    storage()?.setItem(RECENT_KEY, JSON.stringify(rows));
  } catch (_) {
    /* Private mode, quota, or storage disabled: keep the page usable. */
  }
}

/** The stored list, newest first. Corrupt storage reads as empty. */
export function readRecent() {
  let raw = "";
  try {
    raw = storage()?.getItem(RECENT_KEY) || "";
  } catch (_) {
    return [];
  }
  if (!raw) return [];
  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch (_) {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const rows = [];
  for (const value of parsed) {
    const row = cleanRow(value);
    if (row) rows.push(row);
  }
  rows.sort((a, b) => b.timestamp - a.timestamp);
  const seen = new Set();
  const unique = [];
  for (const row of rows) {
    const key = signature(row);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(row);
  }
  return unique.slice(0, MAX_RECENT);
}

/**
 * Put one preview at the top of the list. The same voice moves instead of
 * duplicating. A row that cannot be replayed is ignored.
 */
export function recordRecent(entry) {
  const timestamp = Number(entry?.timestamp);
  const row = cleanRow({
    ...entry,
    timestamp: Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now(),
  });
  if (!row) return readRecent();
  const key = signature(row);
  const rows = [row, ...readRecent().filter((item) => signature(item) !== key)].slice(0, MAX_RECENT);
  writeRecent(rows);
  return rows;
}

/** Empty the list. Safe when storage is unavailable. */
export function clearRecent() {
  try {
    storage()?.removeItem(RECENT_KEY);
  } catch (_) {
    /* Nothing to clear, or storage disabled. */
  }
}

/** The audience key the Voice Room already uses for a row. */
export function recentKey(entry) {
  if (!entry) return "";
  return entry.kind === "clone"
    ? `clone:${entry.clone || entry.voice || ""}`
    : `${entry.engine || ""}:${entry.voice || ""}`;
}

/** "just now", "3 min ago", "2 hr ago" — short enough for one row. */
export function relativeTime(timestamp, now = Date.now()) {
  const then = Number(timestamp);
  const current = Number(now);
  if (!Number.isFinite(then) || !Number.isFinite(current)) return "";
  const seconds = Math.max(0, Math.floor((current - then) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 90) return "1 min ago";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  const weeks = Math.round(days / 7);
  if (weeks < 5) return `${weeks} wk ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} mo ago`;
  return `${Math.round(days / 365)} yr ago`;
}

/**
 * A compact card with one row per recent preview. Repaints itself when
 * cleared; the page builds a fresh panel on every render, so recording a new
 * preview needs no extra wiring.
 */
export function createRecentPanel({ isSpeaking = () => false, onPlay = () => {} } = {}) {
  let entries = readRecent();
  const section = el("section", { class: "vr-section vr-recent", "data-panel": "recent" });

  function paint() {
    const clear = el("button", {
      class: "ghost small", type: "button", text: "Clear",
      "aria-label": "Clear recent previews",
    });
    clear.addEventListener("click", () => {
      clearRecent();
      entries = [];
      paint();
    });
    const head = el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "recent" }), "previews"]),
        el("h2", { text: "Recent previews" }),
      ]),
      entries.length ? clear : null,
    ]);
    const card = el("div", { class: "vr-card vr-recent-card" });
    if (!entries.length) {
      card.append(el("p", { class: "hint vr-recent-empty", text: EMPTY_HINT }));
    } else {
      card.append(el("ul", { class: "vr-recent-list" }, entries.map((entry) => {
        const speaking = Boolean(isSpeaking(entry));
        const button = el("button", {
          class: "ghost small", type: "button",
          text: speaking ? "Stop" : "Play again",
          "aria-label": `${speaking ? "Stop" : "Play again"} ${entry.label}`,
        });
        button.addEventListener("click", () => onPlay(entry));
        return el("li", { class: "vr-recent-row", "data-kind": entry.kind }, [
          el("div", { class: "vr-recent-copy" }, [
            el("strong", { text: entry.label }),
            el("span", { class: "hint mono", text: relativeTime(entry.timestamp) }),
          ]),
          button,
        ]);
      })));
    }
    section.replaceChildren(head, card);
  }

  function refresh() {
    entries = readRecent();
    paint();
  }

  paint();
  return { node: section, render: refresh };
}
