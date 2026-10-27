/**
 * Inspector tabs.
 *
 * Text, Captions and Color are full controls. Clean, Effects and Audio show
 * the current document state and the one safe action this base editor can
 * take; their full controls belong to the later feature layers.
 */

import { el } from "../ui.js";
import {
  AUDIO_LABELS,
  CLEAN_LABELS,
  FX_LABELS,
  MOTION_LABELS,
  formatSpan,
  numberOr,
} from "./model.js";
import { mountTextPanel } from "./layers/text.js";
import { mountCaptionsPanel } from "./layers/captions.js";
import { mountColorPanel } from "./layers/color.js";

export const TABS = [
  { id: "clean", label: "Clean" },
  { id: "text", label: "Text" },
  { id: "captions", label: "Captions" },
  { id: "effects", label: "Effects" },
  { id: "color", label: "Color" },
  { id: "audio", label: "Audio" },
];

export function tabCounts(edit, captions) {
  return {
    clean: (edit?.clean || []).length,
    text: (edit?.graphics || []).filter((layer) => layer.type === "text").length,
    captions: captions?.cues?.length || 0,
    effects: (edit?.motion || []).length
      + (edit?.graphics || []).filter((layer) => layer.type === "fx").length,
    color: edit?.color?.preset && edit.color.preset !== "none" ? 1 : 0,
    audio: edit?.audio?.mode && edit.audio.mode !== "original" ? 1 : 0,
  };
}

export function mountInspector(host, { active = "text", edit, captions, panelCtx }) {
  host.replaceChildren();
  const counts = tabCounts(edit, captions);

  const tabs = el("div", { class: "st-inspector-tabs", role: "tablist", "aria-label": "Layers" });
  for (const tab of TABS) {
    const selected = tab.id === active;
    const button = el("button", {
      class: `st-inspector-tab${selected ? " is-active" : ""}`,
      type: "button",
      role: "tab",
      "aria-selected": selected ? "true" : "false",
      dataset: { tab: tab.id },
    }, [
      el("span", { text: tab.label }),
      counts[tab.id] ? el("small", { class: "st-tab-count", text: String(counts[tab.id]) }) : null,
    ]);
    button.addEventListener("click", () => panelCtx.setTab(tab.id));
    tabs.append(button);
  }
  host.append(tabs);

  const body = el("div", { class: "st-inspector-body", role: "tabpanel", "aria-label": `${TABS.find((tab) => tab.id === active)?.label || "Layer"} controls` });
  host.append(body);

  if (active === "text") {
    mountTextPanel(body, panelCtx);
  } else if (active === "captions") {
    mountCaptionsPanel(body, panelCtx);
  } else if (active === "color") {
    mountColorPanel(body, panelCtx);
  } else if (active === "clean") {
    mountCleanPanel(body, panelCtx, edit);
  } else if (active === "effects") {
    mountEffectsPanel(body, panelCtx, edit);
  } else {
    mountAudioPanel(body, edit);
  }
}

function emptyPanel(body, title, copy, hint) {
  body.append(el("div", { class: "st-layer-empty" }, [
    el("h3", { text: title }),
    el("p", { text: copy }),
    hint ? el("p", { class: "st-hint", text: hint }) : null,
  ]));
}

function mountCleanPanel(body, ctx, edit) {
  const layers = edit?.clean || [];
  if (!layers.length) {
    emptyPanel(
      body,
      "No old text marked",
      "This story has no clean layers yet. Check findings and the full Clean controls arrive in the next build.",
      "You can still add text, captions and colour now.",
    );
    return;
  }
  body.append(el("p", { class: "st-hint", text: "These boxes hide old text before the crop. Remove one if it covers something you need." }));
  const list = el("div", { class: "st-layer-list" });
  for (const layer of layers) {
    const range = layer.ranges?.length
      ? layer.ranges.map((item) => formatSpan(item.start, item.end)).join(", ")
      : "Whole story";
    const remove = el("button", { class: "st-icon-btn st-icon-small", type: "button", "aria-label": `Remove ${CLEAN_LABELS[layer.kind] || "clean"} layer`, text: "×" });
    remove.addEventListener("click", () => {
      ctx.setClean((ctx.getEdit()?.clean || []).filter((item) => item.id !== layer.id));
      ctx.refresh();
    });
    list.append(el("div", { class: "st-layer-row st-layer-row-static" }, [
      el("span", { class: "st-layer-badge", text: CLEAN_LABELS[layer.kind] || layer.kind }),
      el("span", { class: "st-layer-name", text: layer.label || range }),
      remove,
    ]));
  }
  body.append(list);
}

function mountEffectsPanel(body, ctx, edit) {
  const motion = edit?.motion || [];
  const fx = (edit?.graphics || []).filter((layer) => layer.type === "fx");
  if (!motion.length && !fx.length) {
    emptyPanel(
      body,
      "No motion or effects",
      "Punch-in, push and the graphic effects arrive with the next build.",
      "The Effects lane stays in the timeline so you can see where they will sit.",
    );
    return;
  }
  const list = el("div", { class: "st-layer-list" });
  for (const layer of motion) {
    const remove = el("button", { class: "st-icon-btn st-icon-small", type: "button", "aria-label": `Remove ${MOTION_LABELS[layer.kind] || "motion"}`, text: "×" });
    remove.addEventListener("click", () => {
      ctx.setMotion((ctx.getEdit()?.motion || []).filter((item) => item.id !== layer.id));
      ctx.refresh();
    });
    list.append(el("div", { class: "st-layer-row st-layer-row-static" }, [
      el("span", { class: "st-layer-badge", text: MOTION_LABELS[layer.kind] || "Motion" }),
      el("span", { class: "st-layer-name", text: formatSpan(layer.start, layer.end) }),
      remove,
    ]));
  }
  for (const layer of fx) {
    list.append(el("div", { class: "st-layer-row st-layer-row-static" }, [
      el("span", { class: "st-layer-badge", text: FX_LABELS[layer.kind] || "Effect" }),
      el("span", { class: "st-layer-name", text: formatSpan(layer.start, layer.end) }),
    ]));
  }
  body.append(list);
  body.append(el("p", { class: "st-hint", text: "Full effect controls arrive with the next build." }));
}

function mountAudioPanel(body, edit) {
  const audio = edit?.audio || {};
  const labels = [
    ["Mode", AUDIO_LABELS[audio.mode] || "Original sound"],
    ["Music duck", `${Math.round(numberOr(audio.duck_db, -12))} dB`],
    ["Loudness", `${Math.round(numberOr(audio.loudness?.lufs, -14))} LUFS`],
    ["True peak", `${numberOr(audio.loudness?.true_peak, -1.5).toFixed(1)} dBTP`],
  ];
  body.append(el("div", { class: "st-audio-summary" }, labels.map(([label, value]) => (
    el("div", { class: "st-audio-row" }, [
      el("span", { class: "st-field-label", text: label }),
      el("span", { class: "st-mono", text: value }),
    ])
  ))));
  body.append(el("p", { class: "st-hint", text: "Voice-over, music and ducking controls arrive with the audio build. The current mix settings stay saved in this edit." }));
}
