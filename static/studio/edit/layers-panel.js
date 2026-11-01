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
  MOTION_LABELS,
  formatSpan,
  numberOr,
} from "./model.js";
import { boxToFrame, visibleRect } from "./canvas-tools.js";

const GROUPS = [
  { kind: "clean", label: "Remove text", empty: "No text layers", colour: "#e8a266" },
  { kind: "text", label: "Text", empty: "No text layers", colour: "#7b9bb8" },
  { kind: "captions", label: "Captions", empty: "No captions", colour: "#8ec9a3" },
  { kind: "effects", label: "Effects", empty: "No effects", colour: "#c5a0d9" },
  { kind: "color", label: "Colour", empty: "Original colour", colour: "#f4c169" },
  { kind: "audio", label: "Audio", empty: "Original sound", colour: "#5fb7b0" },
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
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", hidden
    ? "M3 3l18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 5.2A10.5 10.5 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 4.2M6.3 6.4A17 17 0 0 0 2 12s3.5 7 10 7a10.7 10.7 0 0 0 4.2-.9"
    : "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.7");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
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

  const head = el("header", { class: "st-layers-head" }, [
    el("div", { class: "st-layers-heading" }, [
      el("h2", { text: "Layers" }),
      el("span", { class: "st-layers-count", text: String(total) }),
    ]),
  ]);
  const body = el("div", { class: "st-layers-scroll" });

  for (const group of groups) {
    const section = el("section", {
      class: "st-layer-group",
      dataset: { kind: group.kind },
      "aria-label": group.label,
    });
    const add = el("button", {
      class: "st-layer-group-add",
      type: "button",
      text: "+",
      title: `Add ${group.label.toLowerCase()}`,
      "aria-label": `Add ${group.label.toLowerCase()}`,
    });
    add.addEventListener("click", (event) => {
      event.stopPropagation();
      ctx.add(group.kind);
    });
    const title = el("button", {
      class: "st-layer-group-title",
      type: "button",
      title: `Show ${group.label.toLowerCase()} settings`,
    }, [
      el("i", { class: "st-layer-colour", "aria-hidden": "true", style: `background:${group.colour}` }),
      el("span", { text: group.label }),
      el("small", { text: String(group.rows.length) }),
    ]);
    title.addEventListener("click", () => ctx.select(group.kind, ""));
    section.append(el("div", { class: "st-layer-group-head" }, [title, add]));

    if (!group.rows.length) {
      section.append(el("p", { class: "st-layer-empty-row", text: group.empty }));
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

  host.replaceChildren(el("section", { class: "st-layers-panel" }, [head, body]));
}
