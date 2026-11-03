/**
 * Layers — the right panel.
 *
 * A compact icon rail selects one layer category. The content is the single
 * active layer, with no panel title and no duplicate tool tabs. Existing clean,
 * filter, transcript and audio panels keep their logic; this module only owns
 * the rail and the compact wrappers.
 */

import { el } from "../ui.js";
import { icon } from "./icons.js";
import { mountCleanPanel } from "./layers/clean.js";
import { mountColorPanel } from "./layers/color.js";
import { mountTranscriptPanel, mountAudioPanel } from "./layers/audio.js";
import { mountCaptionsPanel } from "./layers/captions.js";

const LAYERS = [
  ["clean", "Clean", "eraser"],
  ["filter", "Filter & LUTs", "palette"],
  ["transcript", "Transcript & Translation", "captions"],
  ["narrative", "Narrative", "mic"],
  ["zoom", "Zoom", "search"],
  ["border", "Border", "square"],
];

function countFor(id, edit, captions) {
  if (id === "clean") return (edit?.clean || []).length;
  if (id === "filter") return edit?.color?.preset && edit.color.preset !== "none" ? 1 : 0;
  if (id === "transcript") return (captions?.cues || []).length;
  if (id === "narrative") return edit?.audio?.mode && edit.audio.mode !== "original" ? 1 : 0;
  if (id === "zoom") return Number(edit?.reframe?.zoom || 1) > 1.001 ? 1 : 0;
  if (id === "border") return Number(edit?.border?.width || 0) > 0 ? 1 : 0;
  return 0;
}

function statusFor(id, edit, captions) {
  const count = countFor(id, edit, captions);
  if (id === "zoom") return `${Number(edit?.reframe?.zoom || 1).toFixed(1)}×`;
  if (id === "border") {
    const width = Number(edit?.border?.width || 0);
    return width > 0 ? `${width}px` : "";
  }
  return count ? String(count) : "";
}

export function mountLayersPanel(host, ctx) {
  if (!host) return null;
  let active = String(ctx.getActiveLayer?.() || "clean");
  let signature = "";

  const rail = el("nav", { class: "st-layer-rail", "aria-label": "Layers" });
  const content = el("div", { class: "st-layer-content" });
  host.replaceChildren(content, rail);

  function renderRail() {
    const edit = ctx.getEdit();
    const captions = ctx.getCaptions();
    rail.replaceChildren();
    for (const [id, label, iconName] of LAYERS) {
      const selected = id === active;
      const badge = statusFor(id, edit, captions);
      const button = el("button", {
        class: `st-layer-rail-btn${selected ? " is-active" : ""}`,
        type: "button",
        title: label,
        "aria-label": label,
        "aria-pressed": selected ? "true" : "false",
        dataset: { layer: id },
      }, [icon(iconName, { size: 16 })]);
      if (badge) button.append(el("span", { class: "st-layer-badge", text: badge }));
      button.addEventListener("click", () => {
        active = id;
        ctx.setActiveLayer?.(id);
        signature = "";
        render();
      });
      rail.append(button);
    }
  }

  function render() {
    if (!host.isConnected) return;
    const edit = ctx.getEdit();
    const captions = ctx.getCaptions();
    const countChangesShape = ["clean", "transcript", "narrative", "filter"].includes(active);
    const sig = [
      active,
      countChangesShape ? countFor(active, edit, captions) : "",
      ctx.getSelected?.()?.kind || "",
      ctx.getSelected?.()?.id || "",
    ].join("|");
    renderRail();
    if (sig === signature && content.childElementCount) return;
    signature = sig;
    content.replaceChildren();
    const body = el("div", { class: "st-layer-scroll" });
    content.append(body);
    if (active === "clean") {
      mountCleanPanel(body, ctx);
    } else if (active === "filter") {
      mountColorPanel(body, ctx);
    } else if (active === "transcript") {
      mountTranscriptLayer(body, ctx);
    } else if (active === "narrative") {
      mountNarrativeLayer(body, ctx);
    } else if (active === "zoom") {
      mountZoomLayer(body, ctx);
    } else {
      mountBorderLayer(body, ctx);
    }
  }

  render();
  return {
    refresh() {
      signature = "";
      render();
    },
    setActive(id) {
      if (!LAYERS.some(([value]) => value === id)) return;
      active = id;
      signature = "";
      render();
    },
    getActive() {
      return active;
    },
  };
}

function mountTranscriptLayer(host, ctx) {
  const edit = ctx.getEdit();
  const enabled = edit?.captions?.enabled !== false;

  const toggle = el("input", { type: "checkbox", checked: enabled });
  toggle.addEventListener("change", () => {
    ctx.setCaptionsEnabled?.(toggle.checked);
    ctx.refresh?.();
  });
  host.append(el("div", { class: "st-layer-toggle" }, [
    el("label", { class: "st-switch" }, [toggle, el("span", { text: "Captions" })]),
    el("span", {
      class: "st-layer-note",
      text: `${(ctx.getCaptions()?.cues || []).length} lines`,
    }),
  ]));

  const transcriptHost = el("div", { class: "st-transcript-layer" });
  host.append(transcriptHost);
  mountTranscriptPanel(transcriptHost, ctx);

  if (enabled) {
    const details = el("details", { class: "st-caption-style-fold" });
    details.append(el("summary", { text: "Caption style" }));
    const captionHost = el("div", { class: "st-caption-layer" });
    details.append(captionHost);
    host.append(details);
    mountCaptionsPanel(captionHost, ctx);
  }
}

function mountNarrativeLayer(host, ctx) {
  const audio = ctx.getEdit()?.audio || {};
  const fade = { in: 0, out: 0, ...(audio.fade || {}) };
  const fadeIn = el("input", { type: "number", min: "0", max: "10", step: "0.1", value: String(Number(fade.in) || 0), "aria-label": "Fade in seconds" });
  const fadeOut = el("input", { type: "number", min: "0", max: "10", step: "0.1", value: String(Number(fade.out) || 0), "aria-label": "Fade out seconds" });
  function commit() {
    ctx.setAudioFade?.({
      in: Math.max(0, Math.min(10, Number(fadeIn.value) || 0)),
      out: Math.max(0, Math.min(10, Number(fadeOut.value) || 0)),
    });
  }
  fadeIn.addEventListener("input", commit);
  fadeOut.addEventListener("input", commit);
  const fadeBlock = el("div", { class: "st-audio-fade" }, [
    el("span", { class: "st-layer-note", text: "Sound fade" }),
    el("div", { class: "st-control-grid" }, [
      el("label", { class: "st-field" }, [el("span", { text: "In (s)" }), fadeIn]),
      el("label", { class: "st-field" }, [el("span", { text: "Out (s)" }), fadeOut]),
    ]),
  ]);
  host.append(fadeBlock);
  const audioHost = el("div", { class: "st-narrative-layer" });
  host.append(audioHost);
  mountAudioPanel(audioHost, ctx);
}

function mountZoomLayer(host, ctx) {
  const edit = ctx.getEdit();
  const reframe = { mode: "auto", cx: 0.5, cy: 0.5, zoom: 1, ...(edit?.reframe || {}) };
  let zoom = Math.max(1, Math.min(2, Number(reframe.zoom) || 1));

  const readout = el("span", { class: "st-mono st-zoom-readout", text: `${zoom.toFixed(2)}×` });
  const slider = el("input", {
    type: "range", min: "1", max: "2", step: "0.01", value: String(zoom),
    "aria-label": "Zoom",
  });
  const minus = el("button", { class: "st-icon-btn", type: "button", title: "Zoom out", "aria-label": "Zoom out" }, [icon("minus", { size: 14 })]);
  const plus = el("button", { class: "st-icon-btn", type: "button", title: "Zoom in", "aria-label": "Zoom in" }, [icon("plus", { size: 14 })]);
  const area = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Area focus" });
  const reset = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Reset" });

  function commit() {
    readout.textContent = `${zoom.toFixed(2)}×`;
    slider.value = String(zoom);
    ctx.setReframe?.({
      ...reframe,
      mode: reframe.mode === "auto" ? "manual" : reframe.mode,
      zoom,
    });
  }
  minus.addEventListener("click", () => { zoom = Math.max(1, zoom - 0.05); commit(); });
  plus.addEventListener("click", () => { zoom = Math.min(2, zoom + 0.05); commit(); });
  slider.addEventListener("input", () => { zoom = Number(slider.value); commit(); });
  area.addEventListener("click", () => ctx.startAreaFocus?.());
  reset.addEventListener("click", () => {
    zoom = 1;
    ctx.setReframe?.({ mode: "auto", cx: 0.5, cy: 0.5, zoom: 1 });
    ctx.refresh?.();
  });

  host.append(
    el("div", { class: "st-zoom-row" }, [minus, slider, plus, readout]),
    el("div", { class: "st-layer-actions" }, [area, reset]),
    el("p", { class: "st-layer-note", text: "Area focus crops this moment around the box you draw on the preview." }),
  );
}

function mountBorderLayer(host, ctx) {
  const edit = ctx.getEdit();
  const border = { width: 0, color: "#f1efe9", radius: 0, ...(edit?.border || {}) };
  const width = el("input", { type: "number", min: "0", max: "64", step: "1", value: String(Number(border.width) || 0), "aria-label": "Border width" });
  const color = el("input", { type: "color", value: String(border.color || "#f1efe9"), "aria-label": "Border colour" });
  const radius = el("input", { type: "number", min: "0", max: "64", step: "1", value: String(Number(border.radius) || 0), "aria-label": "Border radius" });

  function commit() {
    ctx.setBorder?.({
      width: Math.max(0, Math.min(64, Number(width.value) || 0)),
      color: color.value,
      radius: Math.max(0, Math.min(64, Number(radius.value) || 0)),
    });
  }
  for (const input of [width, color, radius]) input.addEventListener("input", commit);

  host.append(
    el("div", { class: "st-control-grid st-border-grid" }, [
      el("label", { class: "st-field" }, [el("span", { text: "Width" }), width]),
      el("label", { class: "st-field" }, [el("span", { text: "Colour" }), color]),
      el("label", { class: "st-field" }, [el("span", { text: "Radius" }), radius]),
    ]),
    el("p", { class: "st-layer-note", text: "The border is drawn around the finished frame at render time." }),
  );
}
