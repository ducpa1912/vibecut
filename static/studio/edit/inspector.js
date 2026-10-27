/**
 * Inspector tabs.
 *
 * Text, Captions, Color, Clean, Effects and Audio each mount their own panel
 * module. This file only owns the tab strip, counts and the active panel.
 */

import { el } from "../ui.js";
import { mountTextPanel } from "./layers/text.js";
import { mountCaptionsPanel } from "./layers/captions.js";
import { mountColorPanel } from "./layers/color.js";
import { mountCleanPanel } from "./layers/clean.js";
import { mountEffectsPanel } from "./layers/effects.js";
import { mountAudioPanel } from "./layers/audio.js";

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
    mountCleanPanel(body, panelCtx);
  } else if (active === "effects") {
    mountEffectsPanel(body, panelCtx);
  } else {
    mountAudioPanel(body, panelCtx);
  }
}
