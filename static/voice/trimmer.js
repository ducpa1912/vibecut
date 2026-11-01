/**
 * Voice Room — reference trimmer.
 *
 * A reference longer than 15 s is never sent whole. The server proposes the
 * cleanest 10-15 s window; this overlay draws the waveform, lets the creator
 * drag or type the start and end, preview the loop, and confirm one range.
 *
 * Keys: Space plays or stops, Enter confirms, Esc cancels. Scroll zooms,
 * Shift+scroll pans, and Fit all / Fit selection reset the view.
 *
 * No audio is changed here. The server cuts the confirmed range.
 */

import { el, formatDuration } from "./ui.js";
import { syncTokenCookie } from "./api.js";

export const MIN_WINDOW = 8;
export const MAX_WINDOW = 15;
const MIN_VIEW = 2;

/** Keep a range inside the file and inside the clone limits. */
export function clampWindow(start, end, duration, min = MIN_WINDOW, max = MAX_WINDOW) {
  const total = Math.max(0, Number(duration) || 0);
  let from = Math.max(0, Math.min(total, Number(start) || 0));
  let to = Math.max(from, Math.min(total, Number(end) || 0));
  if (to - from > max) to = Math.min(total, from + max);
  if (to - from < min) {
    to = Math.min(total, from + min);
    if (to - from < min) from = Math.max(0, to - min);
  }
  return { start: Number(from.toFixed(3)), end: Number(to.toFixed(3)), seconds: Number((to - from).toFixed(2)) };
}

/** "12.0 s · ok", or what is wrong with it. Advisory in the panel, enforced by the server. */
export function windowLabel(start, end, min = MIN_WINDOW, max = MAX_WINDOW) {
  const seconds = Math.max(0, Number(end) - Number(start));
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return { tone: "bad", text: "Choose a start and an end." };
  }
  if (seconds < min - 0.05) {
    return { tone: "bad", text: `${seconds.toFixed(1)} s · too short, at least ${min} s` };
  }
  if (seconds > max + 0.05) {
    return { tone: "bad", text: `${seconds.toFixed(1)} s · too long, trim to ${max} s or less` };
  }
  return { tone: "ok", text: `${seconds.toFixed(1)} s · ok` };
}

/** Zoom or pan the drawn range without leaving the file. */
export function zoomRange(view, factor, center, duration) {
  const total = Math.max(0, Number(duration) || 0);
  const start = Math.max(0, Number(view.start) || 0);
  const end = Math.min(total, Number(view.end) || total);
  const width = Math.max(MIN_VIEW, (end - start) * Number(factor || 1));
  const at = Math.max(start, Math.min(end, Number(center) || (start + end) / 2));
  const ratio = (at - start) / Math.max(0.001, end - start);
  let next = Math.max(0, at - width * ratio);
  next = Math.min(next, Math.max(0, total - width));
  return { start: Number(next.toFixed(3)), end: Number(Math.min(total, next + width).toFixed(3)) };
}

function clampView(view, duration) {
  const total = Math.max(0, Number(duration) || 0);
  let start = Math.max(0, Math.min(total, Number(view.start) || 0));
  let end = Math.max(start + 0.1, Math.min(total, Number(view.end) || total));
  if (end - start > total) start = 0;
  if (end - start < MIN_VIEW && total >= MIN_VIEW) {
    end = Math.min(total, start + MIN_VIEW);
    start = Math.max(0, end - MIN_VIEW);
  }
  return { start, end };
}

/**
 * @param {{ audioUrl: string, duration: number, peaks?: number[], best?: {start:number,end:number},
 *           minSeconds?: number, maxSeconds?: number, title?: string,
 *           onConfirm?: (range: {start:number,end:number,seconds:number}) => void,
 *           onCancel?: () => void }} options
 */
export function openTrimmer({
  audioUrl,
  duration,
  peaks = [],
  best = {},
  minSeconds = MIN_WINDOW,
  maxSeconds = MAX_WINDOW,
  title = "Trim the reference",
  onConfirm = () => {},
  onCancel = () => {},
}) {
  const total = Math.max(0.1, Number(duration) || 0.1);
  let selection = clampWindow(
    Number.isFinite(Number(best?.start)) ? best.start : 0,
    Number.isFinite(Number(best?.end)) ? best.end : Math.min(total, maxSeconds),
    total, minSeconds, maxSeconds,
  );
  let view = { start: 0, end: total };
  let dragging = "";
  let player = null;
  let playing = false;
  let loop = true;
  let closed = false;
  const previousFocus = document.activeElement;

  syncTokenCookie();

  const canvas = el("canvas", { class: "vr-trimmer-wave", width: "760", height: "110", "aria-label": "Reference waveform" });
  const readout = el("span", { class: "vr-trimmer-readout", role: "status" });
  const startOut = el("span", { class: "vr-trimmer-time", text: formatDuration(selection.start) });
  const endOut = el("span", { class: "vr-trimmer-time", text: formatDuration(selection.end) });
  const startRange = el("input", {
    type: "range", min: "0", max: String(total), step: "0.05", value: String(selection.start),
    "aria-label": "Start of the selection",
  });
  const endRange = el("input", {
    type: "range", min: "0", max: String(total), step: "0.05", value: String(selection.end),
    "aria-label": "End of the selection",
  });
  const playButton = el("button", { class: "vr-trimmer-btn", type: "button", text: "Play" });
  const loopTick = el("input", { type: "checkbox", checked: true, id: "vr-trim-loop" });
  const useButton = el("button", { class: "vr-trimmer-btn is-primary", type: "button", text: "Use this part" });
  const cancelButton = el("button", { class: "vr-trimmer-btn", type: "button", text: "Cancel" });
  const hint = el("p", { class: "vr-trimmer-hint", text: "Space plays, Enter confirms, Esc cancels. Scroll zooms; Shift+scroll pans." });

  const dialog = el("section", {
    class: "vr-trimmer", role: "dialog", "aria-modal": "true", "aria-label": title,
  }, [
    el("div", { class: "vr-trimmer-head" }, [
      el("div", {}, [
        el("h2", { text: title }),
        el("p", { class: "hint", text: `${Math.round(total)} s in this file. Keep 8-15 s of clean speech for the clone.` }),
      ]),
      el("button", { class: "vr-trimmer-close", type: "button", text: "✕", "aria-label": "Close the trimmer" }),
    ]),
    el("div", { class: "vr-trimmer-canvas-wrap" }, [canvas]),
    el("div", { class: "vr-trimmer-readout-row" }, [readout]),
    el("div", { class: "vr-trimmer-fields" }, [
      el("label", {}, [el("span", { text: "Start" }), startRange, startOut]),
      el("label", {}, [el("span", { text: "End" }), endRange, endOut]),
    ]),
    el("div", { class: "vr-trimmer-actions" }, [
      playButton,
      el("label", { class: "vr-consent", for: "vr-trim-loop" }, [loopTick, el("span", { text: "Loop the selection" })]),
      el("button", {
        class: "vr-trimmer-btn", type: "button", text: "Fit all",
        on: { click: () => { view = { start: 0, end: total }; draw(); } },
      }),
      el("button", {
        class: "vr-trimmer-btn", type: "button", text: "Fit selection",
        on: { click: () => { view = { start: selection.start, end: selection.end }; draw(); } },
      }),
      el("span", { class: "vr-trimmer-spacer" }),
      cancelButton,
      useButton,
    ]),
    hint,
  ]);
  const backdrop = el("div", { class: "vr-trimmer-backdrop" }, [dialog]);

  function tone() {
    const label = windowLabel(selection.start, selection.end, minSeconds, maxSeconds);
    readout.textContent = label.text;
    readout.dataset.tone = label.tone;
    startOut.textContent = formatDuration(selection.start);
    endOut.textContent = formatDuration(selection.end);
    startRange.value = String(selection.start);
    endRange.value = String(selection.end);
    useButton.disabled = label.tone !== "ok";
    playButton.textContent = playing ? "Stop" : "Play selection";
    return label;
  }

  function draw() {
    view = clampView(view, total);
    const width = canvas.width;
    const height = canvas.height;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#111715";
    context.fillRect(0, 0, width, height);
    const span = Math.max(0.01, view.end - view.start);
    const pixel = (time) => ((Number(time) - view.start) / span) * width;
    // One bar per 2 CSS pixels, taken from the peak buckets.
    const bars = Math.max(20, Math.floor(width / 3));
    context.fillStyle = "#3f5750";
    for (let index = 0; index < bars; index += 1) {
      const time = view.start + (index / bars) * span;
      const bucket = peaks.length
        ? peaks[Math.min(peaks.length - 1, Math.max(0, Math.floor((time / total) * peaks.length)))]
        : 0.25;
      const barHeight = Math.max(2, Math.min(height - 8, Number(bucket || 0) * (height - 12)));
      const x = (index / bars) * width;
      context.fillRect(x, (height - barHeight) / 2, Math.max(1, width / bars - 1), barHeight);
    }
    const left = Math.max(0, pixel(selection.start));
    const right = Math.min(width, pixel(selection.end));
    context.fillStyle = "rgba(168, 213, 191, 0.16)";
    context.fillRect(left, 0, Math.max(0, right - left), height);
    context.strokeStyle = "#a8d5bf";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(left, 0);
    context.lineTo(left, height);
    context.moveTo(right, 0);
    context.lineTo(right, height);
    context.stroke();
    tone();
  }

  function setSelection(next) {
    selection = clampWindow(next.start, next.end, total, minSeconds, maxSeconds);
    draw();
  }

  function timeAt(event) {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
    return view.start + ratio * (view.end - view.start);
  }

  function stopPreview() {
    if (player) {
      try { player.pause(); } catch (_) { /* already closed */ }
    }
    player = null;
    playing = false;
    tone();
  }

  function togglePreview() {
    if (playing) {
      stopPreview();
      return;
    }
    if (!audioUrl) return;
    player = new Audio(audioUrl);
    player.currentTime = selection.start;
    playing = true;
    tone();
    player.addEventListener("timeupdate", () => {
      if (!player) return;
      if (player.currentTime >= selection.end) {
        if (loop) {
          player.currentTime = selection.start;
        } else {
          stopPreview();
        }
      }
    });
    player.addEventListener("ended", stopPreview, { once: true });
    player.addEventListener("error", stopPreview, { once: true });
    void player.play().catch(() => stopPreview());
  }

  function close(confirmed) {
    if (closed) return;
    closed = true;
    stopPreview();
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", draw);
    backdrop.remove();
    if (confirmed) onConfirm({ ...selection });
    else onCancel();
    try { previousFocus?.focus?.(); } catch (_) { /* focus moved on */ }
  }

  function onKey(event) {
    const tag = String(event.target?.tagName || "").toLowerCase();
    if (event.key === "Escape") {
      event.preventDefault();
      close(false);
      return;
    }
    if (tag === "input" || tag === "textarea" || tag === "select") {
      if (event.key === "Enter" && !useButton.disabled) {
        event.preventDefault();
        close(true);
      }
      return;
    }
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      togglePreview();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!useButton.disabled) close(true);
    }
  }

  startRange.addEventListener("input", () => {
    setSelection({ start: Number(startRange.value), end: Math.max(Number(startRange.value) + minSeconds, selection.end) });
  });
  endRange.addEventListener("input", () => {
    setSelection({ start: Math.min(selection.start, Number(endRange.value) - minSeconds), end: Number(endRange.value) });
  });
  playButton.addEventListener("click", togglePreview);
  loopTick.addEventListener("change", () => { loop = Boolean(loopTick.checked); });
  useButton.addEventListener("click", () => { if (!useButton.disabled) close(true); });
  cancelButton.addEventListener("click", () => close(false));
  dialog.querySelector(".vr-trimmer-close").addEventListener("click", () => close(false));
  canvas.addEventListener("pointerdown", (event) => {
    const at = timeAt(event);
    const toStart = Math.abs(at - selection.start);
    const toEnd = Math.abs(at - selection.end);
    dragging = toStart <= toEnd ? "start" : "end";
    canvas.setPointerCapture?.(event.pointerId);
    if (dragging === "start") setSelection({ start: at, end: selection.end });
    else setSelection({ start: selection.start, end: at });
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const at = timeAt(event);
    if (dragging === "start") setSelection({ start: Math.min(at, selection.end - minSeconds), end: selection.end });
    else setSelection({ start: selection.start, end: Math.max(at, selection.start + minSeconds) });
  });
  canvas.addEventListener("pointerup", () => { dragging = ""; });
  canvas.addEventListener("pointercancel", () => { dragging = ""; });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    if (event.shiftKey) {
      const span = view.end - view.start;
      const shift = (event.deltaY / 500) * span;
      view = clampView({ start: view.start + shift, end: view.end + shift }, total);
    } else {
      const factor = event.deltaY > 0 ? 1.25 : 0.8;
      view = zoomRange(view, factor, timeAt(event), total);
    }
    draw();
  }, { passive: false });
  window.addEventListener("resize", draw);

  document.body.append(backdrop);
  document.addEventListener("keydown", onKey, true);
  window.setTimeout(() => {
    draw();
    useButton.focus();
  }, 0);
  tone();
  return { close, element: backdrop };
}
