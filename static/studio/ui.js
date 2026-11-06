/** Small DOM and formatting helpers shared by Studio panels. */

import { icon } from "./edit/icons.js";

/**
 * Create an element.
 * @param {string} tag
 * @param {Record<string, any>} [props] `class`, `text`, `dataset`, `on`, or any DOM property.
 * @param {Array<Node|string>} [children]
 */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "on") {
      for (const [event, handler] of Object.entries(value)) {
        node.addEventListener(event, handler);
      }
    } else if (key === "for") node.htmlFor = value;
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function setStatus(node, message, tone = "") {
  node.textContent = message || "";
  node.dataset.tone = tone;
  node.hidden = !message;
}

export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (!value) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 10 || index === 0 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[index]}`;
}

export function formatCount(count, singular, plural = `${singular}s`) {
  const value = Number(count) || 0;
  return `${value} ${value === 1 ? singular : plural}`;
}

const STATUS_TEXT = {
  queued: "Queued",
  downloading: "Downloading",
  analyzing: "Reading",
  ready: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
  rendering: "Rendering",
  paused: "Paused",
  done: "Done",
};

export function statusText(status) {
  const key = String(status || "").toLowerCase();
  if (STATUS_TEXT[key]) return STATUS_TEXT[key];
  if (!key) return "Unknown";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function statusTone(status) {
  const key = String(status || "").toLowerCase();
  if (key === "ready" || key === "done") return "ok";
  if (key === "failed" || key === "cancelled") return "bad";
  if (key === "analyzing" || key === "downloading" || key === "rendering") return "busy";
  return "quiet";
}

export function shortDate(epochSeconds) {
  const value = Number(epochSeconds) || 0;
  if (!value) return "";
  try {
    return new Date(value * 1000).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch (_) {
    return "";
  }
}

/**
 * Ask before deleting a video, saying what is running and what goes with it.
 * Resolves true for Delete, false for Cancel.
 */
function askToDelete(host, name, { work = [], keeps = [] } = {}) {
  return new Promise((resolve) => {
    const finish = (answer) => {
      dialog.close();
      dialog.remove();
      resolve(answer);
    };
    const keep = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Cancel" });
    const remove = el("button", { class: "st-btn st-btn-primary st-delete-confirm", type: "button", text: "Delete" });
    const list = (title, rows) => (rows.length
      ? [el("p", { text: title }), el("ul", { class: "st-delete-list" }, rows.map((row) => el("li", { text: row })))]
      : []);
    const dialog = el("dialog", { class: "st-dialog st-delete-dialog", "aria-labelledby": "st-delete-title" }, [
      el("div", { class: "st-dialog-head" }, [el("h2", { id: "st-delete-title", text: `Delete ${name}?` })]),
      el("div", { class: "st-dialog-body" }, [
        ...list("It is still working on this. Delete stops it first:", work),
        ...list("These go with it:", keeps),
        el("p", { text: "Its edits and renders are deleted for good. Your original file elsewhere on this Mac stays." }),
      ]),
      el("div", { class: "st-dialog-foot" }, [keep, remove]),
    ]);
    keep.addEventListener("click", () => finish(false));
    remove.addEventListener("click", () => finish(true));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });
    host.append(dialog);
    dialog.showModal();
    keep.focus();
  });
}

/**
 * A bin button: it checks what the video is doing, asks, and on Delete queues it.
 * `check` reads the state, `onDelete` deletes, and failures go to `onError`.
 */
export function deleteVideoButton({ name, check, onDelete, onError }) {
  const button = el("button", {
    class: "st-icon-btn st-delete-video",
    type: "button",
    title: "Delete this video and its edits and renders",
    "aria-label": `Delete ${name}`,
  }, [icon("trash")]);
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    button.disabled = true;
    try {
      const state = await check();
      if (await askToDelete(button.closest("#studio-root") || document.body, name, state)) {
        await onDelete();
      }
    } catch (error) {
      onError?.(error);
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });
  return button;
}

const FILL_CHOICE_KEY = "vibecut.fillChoice";

/** The Render step's AI fill choices, remembered on this browser. */
export function fillChoice() {
  try {
    const saved = JSON.parse(localStorage.getItem(FILL_CHOICE_KEY) || "null");
    return { device: saved?.device === "gpu" ? "gpu" : "cpu", follow: saved?.follow === true };
  } catch (_) {
    return { device: "cpu", follow: false };
  }
}

export function saveFillChoice(choice) {
  try {
    localStorage.setItem(FILL_CHOICE_KEY, JSON.stringify(choice));
  } catch (_) {
    /* The choice lasts until the page closes. */
  }
}
