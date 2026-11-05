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
 * A bin button that asks once more before it deletes. The second click runs
 * `onDelete`; moving away resets it. Failures go to `onError`.
 */
export function deleteVideoButton({ name, onDelete, onError }) {
  const label = `Delete ${name}`;
  const button = el("button", {
    class: "st-icon-btn st-delete-video",
    type: "button",
    title: "Delete this video and its edits and renders",
    "aria-label": label,
  }, [icon("trash")]);
  let armed = false;
  const reset = () => {
    armed = false;
    button.classList.remove("is-armed");
    button.setAttribute("aria-label", label);
    button.replaceChildren(icon("trash"));
  };
  button.addEventListener("click", async (event) => {
    event.stopPropagation();
    if (!armed) {
      armed = true;
      button.classList.add("is-armed");
      button.setAttribute("aria-label", `Click again to delete ${name} for good`);
      button.replaceChildren(document.createTextNode("Delete?"));
      return;
    }
    button.disabled = true;
    try {
      await onDelete();
    } catch (error) {
      button.disabled = false;
      reset();
      onError?.(error);
    }
  });
  button.addEventListener("blur", reset);
  return button;
}
