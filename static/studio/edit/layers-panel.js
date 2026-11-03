/**
 * The editor's Layers list.
 *
 * One row per layer, grouped in timeline order. Selecting a row selects the
 * same layer in the preview and the timeline; the + button is the one place
 * to add a layer of that kind. Nothing here owns the Edit: every action goes
 * back through the parent's callbacks.
 */

import { el } from "../ui.js";
import {
  AUDIO_LABELS,
  CLEAN_LABELS,
  COLOR_PRESETS,
  FX_LABELS,
  LAYER_COLOURS,
  MOTION_LABELS,
  formatSpan,
  numberOr,
} from "./model.js";
import { boxToFrame, visibleRect } from "./canvas-tools.js";
import { icon } from "./icons.js";

const COLLAPSE_KEY = "vibecut.studio.layers.collapsed";

function readCollapsed() {
  try {
    const value = JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "[]");
    return new Set(Array.isArray(value) ? value.map(String) : []);
  } catch (_) {
    return new Set();
  }
}

function saveCollapsed(collapsed) {
  try {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...collapsed]));
  } catch (_) {
    /* The current panel still keeps its state. */
  }
}

const TOOL_TABS = [
  ["clean", "Clean"],
  ["visual", "TextFX"],
  ["audio", "Audio"],
  ["captions", "Caption"],
];

const GROUPS = [
  { kind: "clean", label: "Remove text", empty: "No text layers", action: "Add a text box", icon: "eraser", colour: LAYER_COLOURS.clean },
  { kind: "text", label: "Text", empty: "No text layers", action: "Add text", icon: "type", colour: LAYER_COLOURS.text },
  { kind: "captions", label: "Captions", empty: "No captions", action: "Open captions", icon: "captions", colour: LAYER_COLOURS.captions },
  { kind: "effects", label: "Effects", empty: "No effects", action: "Add an effect", icon: "sparkles", colour: LAYER_COLOURS.effects },
  { kind: "color", label: "Colour", empty: "Original colour", action: "Choose a colour", icon: "palette", colour: LAYER_COLOURS.color },
  { kind: "audio", label: "Audio", empty: "Original sound", action: "Add music", icon: "audio-lines", colour: LAYER_COLOURS.audio },
];

const CLEAN_NAMES = {
  delogo: "Remove text",
  fill: "AI fill",
  blur: "Blur",
  plate: "Cover",
  mask: "Mask",
  crop_guard: "Keep out of crop",
};

function spanLabel(start, end) {
  if (!Number.isFinite(Number(start)) || !Number.isFinite(Number(end))) return "Whole moment";
  return formatSpan(numberOr(start), numberOr(end));
}

function cleanSpan(layer) {
  const ranges = Array.isArray(layer?.ranges) ? layer.ranges.filter(Boolean) : [];
  if (!ranges.length) return "Whole moment";
  const first = ranges[0];
  const more = ranges.length > 1 ? ` +${ranges.length - 1}` : "";
  return `${spanLabel(first.start, first.end)}${more}`;
}

function rowsFor(kind, edit, captions) {
  if (kind === "clean") {
    return (edit?.clean || []).filter(Boolean).map((layer) => ({
      id: layer.id,
      layer,
      name: layer.label || CLEAN_NAMES[layer.kind] || CLEAN_LABELS[layer.kind] || "Remove text",
      time: cleanSpan(layer),
    }));
  }
  if (kind === "text") {
    return (edit?.graphics || [])
      .filter((layer) => layer?.type === "text" && !layer.hidden)
      .map((layer) => ({
        id: layer.id,
        layer,
        name: layer.text || "Text",
        time: spanLabel(layer.start, layer.end),
      }));
  }
  if (kind === "captions") {
    return (captions?.cues || []).map((cue, index) => ({
      id: cue.id,
      layer: cue,
      name: String(cue.text || "").replace(/\s+/g, " ").trim() || `Caption ${index + 1}`,
      time: spanLabel(cue.start, cue.end),
    }));
  }
  if (kind === "effects") {
    return [
      ...(edit?.motion || []).map((layer) => ({
        id: layer.id,
        layer,
        name: MOTION_LABELS[layer.kind] || "Motion",
        time: spanLabel(layer.start, layer.end),
      })),
      ...(edit?.graphics || [])
        .filter((layer) => layer?.type === "fx" && !layer.hidden)
        .map((layer) => ({
          id: layer.id,
          layer,
          name: FX_LABELS[layer.kind] || "Effect",
          time: spanLabel(layer.start, layer.end),
        })),
    ];
  }
  if (kind === "color") {
    const preset = edit?.color?.preset || "none";
    if (!preset || preset === "none") return [];
    return [{
      id: "color",
      layer: edit.color,
      name: COLOR_PRESETS[preset]?.label || preset,
      time: "Whole moment",
    }];
  }
  if (kind === "audio") {
    const mode = edit?.audio?.mode || "original";
    if (!mode || mode === "original") return [];
    return [{
      id: "audio",
      layer: edit.audio,
      name: AUDIO_LABELS[mode] || mode,
      time: "Whole moment",
    }];
  }
  return [];
}

function warningFor(kind, row, crop) {
  if (kind === "clean") {
    const frame = boxToFrame(row.layer?.box, crop);
    if (!visibleRect(frame)) return "Outside the current crop. Move it into the picture.";
    if (numberOr(row.layer?.box?.w) < 0.01 || numberOr(row.layer?.box?.h) < 0.01) {
      return "This box is too small to remove text.";
    }
  }
  if (kind === "text" && !String(row.layer?.text || "").trim()) {
    return "This text layer is empty.";
  }
  return "";
}

function eyeIcon(hidden) {
  return icon(hidden ? "eye-off" : "eye", { size: 14 });
}

export function renderLayersPanel(host, ctx) {
  if (!host) return;
  const edit = ctx.getEdit();
  const captions = ctx.getCaptions();
  const selected = ctx.getSelected();
  const crop = ctx.getCrop();
  const groups = GROUPS.map((group) => ({
    ...group,
    rows: rowsFor(group.kind, edit, captions),
  }));
  const total = groups.reduce((count, group) => count + group.rows.length, 0);

  const collapsed = readCollapsed();
  const addMenu = el("details", { class: "st-layers-add" }, [
    el("summary", { class: "st-layers-add-summary", title: "Add a layer" }, [
      icon("plus", { size: 12 }),
      el("span", { text: "Add" }),
    ]),
    el("div", { class: "st-layers-add-menu", role: "menu" }, GROUPS.map((group) => {
      const button = el("button", {
        class: "st-layers-add-item",
        type: "button",
        role: "menuitem",
      }, [
        icon(group.icon, { size: 13 }),
        el("span", { text: group.label }),
      ]);
      button.addEventListener("click", () => {
        addMenu.open = false;
        ctx.add(group.kind);
      });
      return button;
    })),
  ]);
  const activeTab = String(ctx.getActiveTab?.() || "clean");
  const tools = el("nav", { class: "st-tool-list", "aria-label": "Edit tools" }, TOOL_TABS.map(([id, label]) => {
    const button = el("button", {
      class: `st-tool${activeTab === id || (id === "visual" && ["text", "effects", "color"].includes(activeTab)) ? " is-active" : ""}`,
      type: "button",
      text: label,
      "aria-pressed": activeTab === id ? "true" : "false",
    });
    button.addEventListener("click", () => ctx.setTab?.(id));
    return button;
  }));
  const head = el("header", { class: "st-layers-head" }, [
    el("div", { class: "st-layers-heading" }, [
      el("h2", { text: "Layers" }),
      el("span", { class: "st-layers-count", text: String(total) }),
    ]),
    addMenu,
  ]);
  const body = el("div", { class: "st-layers-scroll" });

  for (const group of groups) {
    const isCollapsed = collapsed.has(group.kind);
    const section = el("section", {
      class: `st-layer-group${isCollapsed ? " is-collapsed" : ""}`,
      dataset: { kind: group.kind },
      "aria-label": group.label,
    });
    const title = el("button", {
      class: "st-layer-group-title",
      type: "button",
      title: `${isCollapsed ? "Expand" : "Collapse"} ${group.label.toLowerCase()}`,
      "aria-expanded": isCollapsed ? "false" : "true",
      style: `--layer-colour:${group.colour}`,
    }, [
      el("span", { class: "st-layer-caret", text: isCollapsed ? "▸" : "▾", "aria-hidden": "true" }),
      icon(group.icon, { size: 13, className: "st-layer-group-icon" }),
      el("span", { text: group.label }),
      el("small", { text: String(group.rows.length) }),
    ]);
    title.addEventListener("click", () => {
      if (collapsed.has(group.kind)) collapsed.delete(group.kind);
      else collapsed.add(group.kind);
      saveCollapsed(collapsed);
      renderLayersPanel(host, ctx);
    });
    section.append(el("div", { class: "st-layer-group-head" }, [title]));

    if (!group.rows.length) {
      section.append(el("p", { class: "st-layer-empty-copy", text: group.empty }));
    } else {
      const list = el("div", { class: "st-layer-items", role: "list" });
      for (const row of group.rows) {
        const active = selected?.kind === group.kind && selected?.id === row.id;
        const hidden = ctx.isHidden(group.kind, row.id);
        const warning = warningFor(group.kind, row, crop);
        const canHide = group.kind !== "audio";
        const item = el("div", {
          class: `st-layer-item${active ? " is-active" : ""}${hidden ? " is-hidden" : ""}`,
          role: "button",
          tabindex: "0",
          "aria-pressed": active ? "true" : "false",
          "aria-label": `${row.name} · ${row.time}`,
          dataset: {
            kind: group.kind,
            id: row.id,
            box: group.kind === "clean" ? JSON.stringify(row.layer?.box || {}) : null,
          },
        }, [
          el("i", {
            class: "st-layer-colour st-layer-colour-row",
            "aria-hidden": "true",
            style: `background:${group.colour}`,
          }),
          el("span", { class: "st-layer-copy" }, [
            el("strong", { text: row.name }),
            el("small", { text: row.time }),
          ]),
          warning ? el("span", {
            class: "st-layer-warning",
            text: "!",
            title: warning,
            "aria-label": warning,
          }) : null,
          canHide ? el("button", {
            class: "st-layer-eye",
            type: "button",
            title: hidden ? "Show in preview" : "Hide in preview",
            "aria-label": hidden ? `Show ${row.name} in preview` : `Hide ${row.name} in preview`,
            "aria-pressed": hidden ? "true" : "false",
          }, [eyeIcon(hidden)]) : null,
        ]);
        item.addEventListener("click", (event) => {
          if (event.target.closest(".st-layer-eye")) return;
          ctx.select(group.kind, row.id);
        });
        item.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            ctx.select(group.kind, row.id);
          } else if (event.key === "Delete" || event.key === "Backspace") {
            event.preventDefault();
            event.stopPropagation();
            ctx.remove(group.kind, row.id);
          }
        });
        item.querySelector(".st-layer-eye")?.addEventListener("click", (event) => {
          event.stopPropagation();
          ctx.toggleHidden(group.kind, row.id);
        });
        list.append(item);
      }
      section.append(list);
    }
    body.append(section);
  }

  host.replaceChildren(el("section", { class: "st-layers-panel" }, [tools, head, body]));
}
