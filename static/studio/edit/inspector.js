/**
 * Inspector tabs.
 *
 * Clean, Texts & Effects and Audio each mount their own panel modules.
 * Texts & Effects holds text, captions, effects and colour in one place,
 * because creators change them together.
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
  { id: "visual", label: "Texts & Effects" },
  { id: "audio", label: "Audio" },
];

export function tabCounts(edit, captions) {
  return {
    clean: (edit?.clean || []).length,
    visual: (edit?.graphics || []).filter((layer) => layer.type === "text").length
      + (captions?.cues?.length || 0)
      + (edit?.motion || []).length
      + (edit?.graphics || []).filter((layer) => layer.type === "fx").length
      + (edit?.color?.preset && edit.color.preset !== "none" ? 1 : 0),
    audio: edit?.audio?.mode && edit.audio.mode !== "original" ? 1 : 0,
  };
}

export function mountInspector(host, { active = "visual", edit, captions, panelCtx }) {
  host.replaceChildren();
  const counts = tabCounts(edit, captions);
  const activeTab = ["text", "captions", "effects", "color"].includes(active) ? "visual" : active;

  const tabs = el("div", { class: "st-inspector-tabs", role: "tablist", "aria-label": "Layers" });
  for (const tab of TABS) {
    const selected = tab.id === activeTab;
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

  const body = el("div", { class: "st-inspector-body", role: "tabpanel", "aria-label": `${TABS.find((tab) => tab.id === activeTab)?.label || "Layer"} controls` });
  host.append(body);

  if (activeTab === "clean") {
    mountCleanPanel(body, panelCtx);
  } else if (activeTab === "visual") {
    const group = (title, mount) => {
      const section = el("section", { class: "st-visual-group" }, [
        el("h3", { class: "st-visual-group-title", text: title }),
      ]);
      const content = el("div", { class: "st-visual-group-body" });
      section.append(content);
      body.append(section);
      mount(content, panelCtx);
    };
    group("Text", mountTextPanel);
    group("Captions", mountCaptionsPanel);
    group("Effects", mountEffectsPanel);
    group("Colour", mountColorPanel);
  } else {
    mountAudioPanel(body, panelCtx);
  }
}
