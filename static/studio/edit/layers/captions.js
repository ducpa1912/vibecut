/**
 * Caption layer controls.
 *
 * Caption tracks keep their own versions on the server. This panel edits the
 * track style and cue text through `PATCH /api/jobs/{id}/captions/{track_id}`
 * and then points the Edit at the returned track id.
 */

import { el } from "../../ui.js";
import {
  CAPTION_PRESETS,
  CAPTION_STYLE_DEFAULTS,
  SAFE_ZONE_PRESETS,
  captionPreset,
  clone,
  clamp,
  formatSpan,
  numberOr,
  round,
} from "../model.js";

function field(label, control, hint = "") {
  const wrapper = el("label", { class: "st-field" }, [
    el("span", { text: label }),
    control,
  ]);
  if (hint) wrapper.append(el("small", { class: "st-field-hint", text: hint }));
  return wrapper;
}

function numberInput(value, { min, max, step = 1 } = {}) {
  return el("input", {
    type: "number",
    value: String(value),
    min: min === undefined ? null : String(min),
    max: max === undefined ? null : String(max),
    step: String(step),
  });
}

function colorInput(value) {
  const safe = /^#[0-9a-fA-F]{6}$/.test(String(value || "")) ? value : "#ffffff";
  return el("input", { type: "color", value: safe });
}

export function mountCaptionsPanel(host, ctx) {
  const track = ctx.getCaptions();
  host.replaceChildren();

  if (!track) {
    const preset = el("select", { "aria-label": "Caption style" });
    for (const [value, item] of Object.entries(CAPTION_PRESETS)) {
      preset.append(el("option", { value, text: item.label, selected: value === "clean" }));
    }
    const build = el("button", { class: "st-btn st-btn-primary st-btn-small", type: "button", text: "Build captions" });
    build.addEventListener("click", async () => {
      build.disabled = true;
      build.textContent = "Building…";
      try {
        await ctx.buildCaptions(preset.value);
      } finally {
        if (build.isConnected) {
          build.disabled = false;
          build.textContent = "Build captions";
        }
      }
    });
    host.append(el("div", { class: "st-layer-empty" }, [
      el("h3", { text: "No captions yet" }),
      el("p", { text: "Captions follow the spoken words in this story. Build them once, then adjust the style or text." }),
      el("div", { class: "st-layer-add" }, [preset, build]),
      el("p", { class: "st-hint", text: "Captions need the speech read during import. If none was found, import the video again with Speech on." }),
    ]));
    return;
  }

  const style = {
    ...CAPTION_STYLE_DEFAULTS,
    ...clone(track.style || {}),
    safe_zone: { ...CAPTION_STYLE_DEFAULTS.safe_zone, ...(track.style?.safe_zone || {}) },
  };
  const enabled = el("input", { type: "checkbox" });
  enabled.checked = ctx.getEdit()?.captions?.enabled !== false;
  enabled.addEventListener("change", () => {
    ctx.setCaptionsEnabled(enabled.checked);
  });

  const head = el("div", { class: "st-layer-stage-head" }, [
    el("h3", { text: "Captions" }),
    el("label", { class: "st-switch" }, [enabled, el("span", { text: "Show captions" })]),
  ]);
  host.append(head);
  host.append(el("p", { class: "st-hint", text: `${track.cues?.length || 0} lines · style ${track.style_id || "clean"} · version ${track.version || 1}` }));

  const preset = el("select", { "aria-label": "Caption preset" });
  for (const [value, item] of Object.entries(CAPTION_PRESETS)) {
    preset.append(el("option", { value, text: item.label, selected: value === track.style_id }));
  }

  const size = numberInput(style.font_size, { min: 12, max: 200, step: 1 });
  const textColor = colorInput(style.color);
  const strokeColor = colorInput(style.stroke_color);
  const strokeWidth = numberInput(style.stroke_width, { min: 0, max: 20, step: 1 });
  const background = colorInput(style.background);
  const backgroundOpacity = el("input", {
    type: "range", min: "0", max: "1", step: "0.01", value: String(numberOr(style.background_opacity)),
    "aria-label": "Caption background opacity",
  });
  const backgroundValue = el("span", { class: "st-mono st-range-value", text: `${Math.round(numberOr(style.background_opacity) * 100)}%` });
  const position = el("select", { "aria-label": "Caption position" });
  for (const [value, label] of [["bottom", "Bottom"], ["center", "Middle"], ["top", "Top"]]) {
    position.append(el("option", { value, text: label, selected: value === style.position }));
  }
  const maxChars = numberInput(style.max_chars, { min: 8, max: 120, step: 1 });
  const maxLines = numberInput(style.max_lines, { min: 1, max: 4, step: 1 });
  const bottom = numberInput(Math.round(numberOr(style.safe_zone.bottom) * 100), { min: 0, max: 45, step: 1 });
  const top = numberInput(Math.round(numberOr(style.safe_zone.top) * 100), { min: 0, max: 45, step: 1 });
  const upper = el("input", { type: "checkbox", checked: Boolean(style.uppercase) });
  const platform = el("select", { "aria-label": "Safe zone platform" });
  for (const [value, preset] of Object.entries(SAFE_ZONE_PRESETS)) {
    platform.append(el("option", { value, text: preset.label, selected: value === "auto" }));
  }

  const styleDirty = el("span", { class: "st-chip st-chip-busy", text: "Not applied", hidden: true });
  function touchStyle() {
    styleDirty.hidden = false;
  }

  preset.addEventListener("change", () => {
    const next = captionPreset(preset.value);
    Object.assign(style, next);
    style.id = preset.value;
    fillStyle();
    touchStyle();
  });
  size.addEventListener("input", () => {
    style.font_size = clamp(Math.round(numberOr(size.value)), 12, 200);
    touchStyle();
  });
  textColor.addEventListener("input", () => {
    style.color = textColor.value.toUpperCase();
    touchStyle();
  });
  strokeColor.addEventListener("input", () => {
    style.stroke_color = strokeColor.value.toUpperCase();
    touchStyle();
  });
  strokeWidth.addEventListener("input", () => {
    style.stroke_width = clamp(Math.round(numberOr(strokeWidth.value)), 0, 20);
    touchStyle();
  });
  background.addEventListener("input", () => {
    style.background = background.value.toUpperCase();
    touchStyle();
  });
  backgroundOpacity.addEventListener("input", () => {
    style.background_opacity = clamp(numberOr(backgroundOpacity.value), 0, 1);
    backgroundValue.textContent = `${Math.round(style.background_opacity * 100)}%`;
    touchStyle();
  });
  position.addEventListener("change", () => {
    style.position = position.value;
    touchStyle();
  });
  maxChars.addEventListener("input", () => {
    style.max_chars = clamp(Math.round(numberOr(maxChars.value)), 8, 120);
    touchStyle();
  });
  maxLines.addEventListener("input", () => {
    style.max_lines = clamp(Math.round(numberOr(maxLines.value)), 1, 4);
    touchStyle();
  });
  bottom.addEventListener("input", () => {
    style.safe_zone = { ...style.safe_zone, bottom: clamp(numberOr(bottom.value) / 100, 0, 0.45) };
    touchStyle();
  });
  top.addEventListener("input", () => {
    style.safe_zone = { ...style.safe_zone, top: clamp(numberOr(top.value) / 100, 0, 0.45) };
    touchStyle();
  });
  upper.addEventListener("change", () => {
    style.uppercase = upper.checked;
    touchStyle();
  });
  platform.addEventListener("change", () => {
    const preset = SAFE_ZONE_PRESETS[platform.value] || SAFE_ZONE_PRESETS.auto;
    style.safe_zone = { ...style.safe_zone, ...preset.safe_zone };
    fillStyle();
    touchStyle();
  });

  const apply = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Apply style" });
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    apply.textContent = "Applying…";
    try {
      await ctx.applyCaptionTrack({ style: { ...clone(style), id: style.id || track.style_id } });
      styleDirty.hidden = true;
    } finally {
      if (apply.isConnected) {
        apply.disabled = false;
        apply.textContent = "Apply style";
      }
    }
  });

  const styleBlock = el("div", { class: "st-caption-style" }, [
    el("div", { class: "st-layer-stage-head" }, [
      el("h4", { text: "Style" }),
      styleDirty,
    ]),
    preset,
    el("div", { class: "st-control-grid" }, [
      field("Size", size),
      field("Text colour", textColor),
      field("Outline", strokeColor),
      field("Outline width", strokeWidth),
      field("Position", position),
      field("Max characters", maxChars),
      field("Max lines", maxLines),
    ]),
    el("div", { class: "st-control-grid" }, [
      field("Background", background),
      field("Safe zone", platform, "Re-fit captions to this platform."),
      field("Safe bottom (%)", bottom, "Space left for platform buttons."),
      field("Safe top (%)", top),
    ]),
    el("div", { class: "st-range-row" }, [
      el("span", { class: "st-field-label", text: "Background fill" }),
      backgroundOpacity,
      backgroundValue,
    ]),
    el("label", { class: "st-check st-check-inline" }, [
      upper,
      el("span", {}, [el("strong", { text: "Uppercase" })]),
    ]),
    el("div", { class: "st-layer-foot" }, [apply]),
  ]);
  host.append(styleBlock);

  const cueDraft = (track.cues || []).map((cue) => ({ ...cue }));
  const cueDirty = el("span", { class: "st-chip st-chip-busy", text: "Not saved", hidden: true });
  const cueList = el("div", { class: "st-cue-list" });

  function markCueDirty() {
    cueDirty.hidden = false;
  }

  cueDraft.forEach((cue, index) => {
    const label = el("span", { class: "st-cue-number st-mono", text: `${String(index + 1).padStart(2, "0")} · ${formatSpan(cue.start, cue.end)}` });
    const text = el("textarea", {
      rows: 2,
      value: cue.text || "",
      "aria-label": `Caption line ${index + 1}`,
    });
    text.addEventListener("input", () => {
      cue.text = text.value;
      markCueDirty();
    });
    const start = numberInput(cue.start, { min: 0, max: ctx.getDuration(), step: 0.05 });
    const end = numberInput(cue.end, { min: 0, max: ctx.getDuration(), step: 0.05 });
    start.addEventListener("input", () => {
      cue.start = clamp(numberOr(start.value), 0, ctx.getDuration());
      if (cue.end <= cue.start) {
        cue.end = Math.min(ctx.getDuration(), cue.start + 0.2);
        end.value = String(round(cue.end, 2));
      }
      label.textContent = `${String(index + 1).padStart(2, "0")} · ${formatSpan(cue.start, cue.end)}`;
      markCueDirty();
    });
    end.addEventListener("input", () => {
      cue.end = clamp(numberOr(end.value), cue.start + 0.2, ctx.getDuration());
      label.textContent = `${String(index + 1).padStart(2, "0")} · ${formatSpan(cue.start, cue.end)}`;
      markCueDirty();
    });
    cueList.append(el("div", { class: "st-cue" }, [
      label,
      text,
      el("div", { class: "st-cue-times" }, [
        field("Start", start),
        field("End", end),
      ]),
    ]));
  });

  const saveCues = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Save caption text" });
  saveCues.addEventListener("click", async () => {
    saveCues.disabled = true;
    saveCues.textContent = "Saving…";
    try {
      await ctx.applyCaptionTrack({ cues: cueDraft.map((cue) => ({
        id: cue.id,
        start: cue.start,
        end: cue.end,
        text: cue.text,
        clip_index: cue.clip_index,
        scene: cue.scene,
        source_segment: cue.source_segment,
      })) });
      cueDirty.hidden = true;
    } finally {
      if (saveCues.isConnected) {
        saveCues.disabled = false;
        saveCues.textContent = "Save caption text";
      }
    }
  });

  const cueBlock = el("div", { class: "st-caption-cues" }, [
    el("div", { class: "st-layer-stage-head" }, [
      el("h4", { text: "Lines" }),
      cueDirty,
    ]),
    el("p", { class: "st-hint", text: "Edit a line when a word is wrong. Times are in story seconds." }),
    cueList,
    el("div", { class: "st-layer-foot" }, [saveCues]),
  ]);
  host.append(cueBlock);

  for (const warning of track.warnings || []) {
    host.append(el("p", { class: "st-warning", text: String(warning) }));
  }

  function fillStyle() {
    size.value = String(style.font_size);
    textColor.value = style.color;
    strokeColor.value = style.stroke_color;
    strokeWidth.value = String(style.stroke_width);
    background.value = style.background;
    backgroundOpacity.value = String(style.background_opacity);
    backgroundValue.textContent = `${Math.round(numberOr(style.background_opacity) * 100)}%`;
    position.value = style.position;
    maxChars.value = String(style.max_chars);
    maxLines.value = String(style.max_lines);
    bottom.value = String(Math.round(numberOr(style.safe_zone.bottom) * 100));
    top.value = String(Math.round(numberOr(style.safe_zone.top) * 100));
    upper.checked = Boolean(style.uppercase);
    platform.value = "auto";
  }
}
