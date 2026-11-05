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
  ["zoom", "Framing: scene zoom and position", "framing"],
  ["border", "Border around the render", "square"],
];

function countFor(id, edit, captions) {
  if (id === "clean") return (edit?.clean || []).length;
  if (id === "filter") return edit?.color?.preset && edit.color.preset !== "none" ? 1 : 0;
  if (id === "transcript") return (captions?.cues || []).length;
  if (id === "narrative") return edit?.audio?.mode && edit.audio.mode !== "original" ? 1 : 0;
  if (id === "zoom") {
    const reframe = edit?.reframe || {};
    const global = Math.abs(Number(reframe.zoom ?? 1) - 1) > 0.001 ? 1 : 0;
    return global + Object.keys(reframe.scenes || {}).length;
  }
  if (id === "border") return Number(edit?.border?.width || 0) > 0 ? 1 : 0;
  return 0;
}

function statusFor(id, edit, captions) {
  const count = countFor(id, edit, captions);
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
      mountFramingLayer(body, ctx);
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
    const captionHost = el("div", { class: "st-caption-layer" });
    host.append(captionHost);
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
    el("span", { class: "st-layer-note", text: "Original sound fade" }),
    el("div", { class: "st-control-grid" }, [
      el("label", { class: "st-field" }, [el("span", { text: "In (s)" }), fadeIn]),
      el("label", { class: "st-field" }, [el("span", { text: "Out (s)" }), fadeOut]),
    ]),
  ]);
  host.append(fadeBlock);
  const audioHost = el("div", { class: "st-narrative-layer" });
  host.append(audioHost);
  mountAudioPanel(audioHost, { ...ctx, narrativeOnly: true });
}

function iconButton(iconName, label, onClick, className = "st-btn st-btn-ghost st-btn-small") {
  const button = el("button", { class: className, type: "button" }, [
    icon(iconName, { size: 15 }),
    el("span", { text: label }),
  ]);
  button.addEventListener("click", onClick);
  return button;
}

/** One scene's zoom and place inside the frame. Layers and audio have their own. */
function mountFramingLayer(host, ctx) {
  const framing = ctx.getFraming?.();
  if (!framing?.key) {
    host.append(el("p", { class: "st-layer-note", text: "Move the playhead onto a video or photo scene to frame it. A blank card has no picture." }));
    return;
  }
  const min = Math.max(0.1, framing.fit * 0.5);
  let zoom = Math.max(min, Math.min(3, framing.zoom));

  const readout = el("span", { class: "st-mono st-zoom-readout", text: `${zoom.toFixed(2)}×` });
  const slider = el("input", {
    type: "range", min: min.toFixed(3), max: "3", step: "0.01", value: String(zoom),
    "aria-label": "Scene zoom",
  });
  const paint = () => {
    readout.textContent = `${zoom.toFixed(2)}×`;
    slider.value = String(zoom);
  };
  const setZoom = (value, commit = true) => {
    zoom = Math.max(min, Math.min(3, value));
    paint();
    ctx.setFraming?.(framing.key, { zoom: Math.round(zoom * 1000) / 1000 }, { commit });
  };
  const smaller = el("button", { class: "st-icon-btn", type: "button", title: "Make the scene smaller", "aria-label": "Make the scene smaller" }, [icon("zoom-out")]);
  const bigger = el("button", { class: "st-icon-btn", type: "button", title: "Make the scene bigger", "aria-label": "Make the scene bigger" }, [icon("zoom-in")]);
  smaller.addEventListener("click", () => setZoom(zoom - 0.05));
  bigger.addEventListener("click", () => setZoom(zoom + 0.05));
  slider.addEventListener("input", () => setZoom(Number(slider.value), false));
  slider.addEventListener("change", () => setZoom(Number(slider.value)));

  host.append(
    el("h3", { class: "st-framing-title", text: framing.label }),
    el("div", { class: "st-zoom-row" }, [smaller, slider, bigger, readout]),
    el("div", { class: "st-framing-actions" }, [
      iconButton("shrink", "Fit scene", () => {
        ctx.setFraming?.(framing.key, { zoom: framing.fit, cx: 0.5, cy: 0.5 });
      }),
      iconButton("expand", "Fill frame", () => {
        ctx.setFraming?.(framing.key, { zoom: 1 });
      }),
      iconButton("move", "Move scene", () => ctx.startMoveScene?.()),
      iconButton("focus", "Area focus", () => ctx.startAreaFocus?.()),
    ]),
    el("div", { class: "st-framing-actions" }, [
      iconButton("copy", "Use on all", () => ctx.framingToAllScenes?.(framing.key), "st-btn st-btn-quiet st-btn-small"),
      iconButton("history", "Reset scene", () => ctx.resetFraming?.(framing.key), "st-btn st-btn-quiet st-btn-small"),
    ]),
    el("p", { class: "st-layer-note", text: "1× fills the frame. Below 1× the whole scene can fit, and black fills the rest. Anything past the frame border is cut in the render." }),
    el("p", { class: "st-layer-note", text: "This changes only the picture of this scene. Sound stays on the timeline. The zoom buttons above the preview only change your view." }),
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
