/**
 * Text layer controls.
 *
 * Every control writes the same shape the Wave-1 Edit API validates:
 * `graphics[]` entries with type "text". The panel never invents fields.
 */

import { el } from "../../ui.js";
import {
  TEXT_ANCHORS,
  TEXT_KINDS,
  TEXT_STYLE_DEFAULTS,
  clone,
  clamp,
  formatSpan,
  newTextLayer,
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

function checkbox(label, checked) {
  const input = el("input", { type: "checkbox", checked: Boolean(checked) });
  const wrapper = el("label", { class: "st-check st-check-inline" }, [
    input,
    el("span", {}, [el("strong", { text: label })]),
  ]);
  return { wrapper, input };
}

export function mountTextPanel(host, ctx) {
  const edit = ctx.getEdit();
  const layers = (edit?.graphics || []).filter((layer) => layer.type === "text");
  const selectedId = ctx.getSelectedId("text");
  const selected = layers.find((layer) => layer.id === selectedId) || layers[0] || null;

  host.replaceChildren();
  if (!layers.length) {
    host.append(el("div", { class: "st-layer-empty" }, [
      el("h3", { text: "No text yet" }),
      el("p", { text: "Add a hook card, a title or an end card. It appears on the preview box and the timeline." }),
    ]));
  } else {
    const list = el("div", { class: "st-layer-list", role: "list" });
    for (const layer of layers) {
      const active = selected?.id === layer.id;
      const row = el("button", {
        class: `st-layer-row${active ? " is-active" : ""}`,
        type: "button",
        role: "listitem",
        "aria-pressed": active ? "true" : "false",
        dataset: { layer: layer.id },
      }, [
        el("span", { class: "st-layer-badge", text: TEXT_KINDS[layer.kind]?.label || "Text" }),
        el("span", { class: "st-layer-name", text: layer.text || "Untitled" }),
      ]);
      row.addEventListener("click", () => ctx.select("text", layer.id));
      list.append(row);
    }
    host.append(list);
  }

  const addRow = el("div", { class: "st-layer-add" });
  const kind = el("select", { "aria-label": "New text kind" });
  for (const [value, preset] of Object.entries(TEXT_KINDS)) {
    kind.append(el("option", { value, text: preset.label }));
  }
  const add = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Add text" });
  add.addEventListener("click", () => {
    const next = newTextLayer(kind.value, {
      duration: ctx.getDuration(),
      playhead: ctx.getPlayhead(),
      index: (ctx.getEdit()?.graphics || []).length,
      hookText: ctx.getStory?.()?.hook?.text || "",
    });
    const graphics = [...(ctx.getEdit()?.graphics || []), next];
    ctx.setGraphics(graphics);
    ctx.select("text", next.id);
  });
  addRow.append(kind, add);
  host.append(addRow);

  if (!selected) return;

  const layer = clone(selected);
  const stage = el("div", { class: "st-layer-stage" });
  stage.append(el("div", { class: "st-layer-stage-head" }, [
    el("h3", { text: TEXT_KINDS[layer.kind]?.label || "Text" }),
    el("span", { class: "st-mono st-hint", text: formatSpan(layer.start, layer.end) }),
  ]));

  const text = el("textarea", {
    rows: 3,
    maxlength: 400,
    value: layer.text || "",
    "aria-label": "Text",
  });
  text.addEventListener("input", () => {
    layer.text = text.value;
    commit();
    const row = host.querySelector(`.st-layer-row[data-layer="${layer.id}"] .st-layer-name`);
    if (row) row.textContent = layer.text || "Untitled";
  });
  stage.append(field("Text", text, "Keep it short. Long text is clipped in the preview."));

  const kindSelect = el("select", { "aria-label": "Text kind" });
  for (const [value, preset] of Object.entries(TEXT_KINDS)) {
    kindSelect.append(el("option", { value, text: preset.label, selected: value === layer.kind }));
  }
  kindSelect.addEventListener("change", () => {
    layer.kind = kindSelect.value;
    const preset = TEXT_KINDS[layer.kind];
    layer.anchor = preset.anchor;
    layer.box = { ...preset.box };
    commit();
    ctx.refresh();
  });

  const start = numberInput(layer.start, { min: 0, max: ctx.getDuration(), step: 0.1 });
  const end = numberInput(layer.end, { min: 0.1, max: ctx.getDuration(), step: 0.1 });
  start.addEventListener("input", () => {
    layer.start = clamp(numberOr(start.value), 0, Math.max(0, ctx.getDuration() - 0.2));
    if (layer.end <= layer.start + 0.2) layer.end = Math.min(ctx.getDuration(), layer.start + 0.2);
    end.value = String(round(layer.end, 1));
    commit();
  });
  end.addEventListener("input", () => {
    layer.end = clamp(numberOr(end.value), layer.start + 0.2, ctx.getDuration());
    commit();
  });

  const anchor = el("select", { "aria-label": "Text position" });
  for (const [value, label] of TEXT_ANCHORS) {
    anchor.append(el("option", { value, text: label, selected: value === layer.anchor }));
  }
  anchor.addEventListener("change", () => {
    layer.anchor = anchor.value;
    commit();
  });

  const width = numberInput(Math.round(numberOr(layer.box?.w, 0.76) * 100), { min: 2, max: 100, step: 1 });
  const height = numberInput(Math.round(numberOr(layer.box?.h, 0.16) * 100), { min: 2, max: 100, step: 1 });
  width.addEventListener("input", () => {
    layer.box = { ...(layer.box || {}), w: clamp(numberOr(width.value) / 100, 0.02, 1) };
    commit();
  });
  height.addEventListener("input", () => {
    layer.box = { ...(layer.box || {}), h: clamp(numberOr(height.value) / 100, 0.02, 1) };
    commit();
  });

  stage.append(el("div", { class: "st-control-grid" }, [
    field("Kind", kindSelect),
    field("Position", anchor),
    field("Start (s)", start),
    field("End (s)", end),
    field("Width (%)", width),
    field("Height (%)", height),
  ]));

  const style = { ...TEXT_STYLE_DEFAULTS, ...(layer.style || {}) };
  const font = el("select", { "aria-label": "Font" });
  for (const [value, label] of [["sans", "Sans"], ["serif", "Serif"], ["mono", "Mono"]]) {
    font.append(el("option", { value, text: label, selected: value === style.font }));
  }
  font.addEventListener("change", () => {
    style.font = font.value;
    writeStyle();
  });

  const size = numberInput(style.size, { min: 12, max: 160, step: 1 });
  size.addEventListener("input", () => {
    style.size = clamp(Math.round(numberOr(size.value)), 12, 160);
    writeStyle();
  });

  const weight = el("select", { "aria-label": "Weight" });
  for (const value of [400, 500, 600, 700, 800, 900]) {
    weight.append(el("option", { value: String(value), text: String(value), selected: Number(style.weight) === value }));
  }
  weight.addEventListener("change", () => {
    style.weight = Number(weight.value);
    writeStyle();
  });

  const textColor = colorInput(style.color);
  textColor.addEventListener("input", () => {
    style.color = textColor.value;
    writeStyle();
  });

  const stroke = colorInput(style.stroke === "none" ? "#000000" : style.stroke);
  stroke.addEventListener("input", () => {
    style.stroke = stroke.value;
    writeStyle();
  });

  const background = el("select", { "aria-label": "Text background" });
  const backgroundValue = !style.background || style.background === "none" ? "none" : "solid";
  for (const [value, label] of [["none", "None"], ["solid", "Dark box"]]) {
    background.append(el("option", { value, text: label, selected: value === backgroundValue }));
  }
  background.addEventListener("change", () => {
    style.background = background.value === "none" ? "none" : "#000000";
    writeStyle();
  });

  const align = el("select", { "aria-label": "Text alignment" });
  for (const [value, label] of [["left", "Left"], ["center", "Centre"], ["right", "Right"]]) {
    align.append(el("option", { value, text: label, selected: value === style.align }));
  }
  align.addEventListener("change", () => {
    style.align = align.value;
    writeStyle();
  });

  stage.append(el("div", { class: "st-control-grid" }, [
    field("Font", font),
    field("Size", size),
    field("Weight", weight),
    field("Text colour", textColor),
    field("Outline", stroke),
    field("Background", background),
    field("Alignment", align),
  ]));

  const upper = checkbox("Uppercase", style.uppercase);
  upper.input.addEventListener("change", () => {
    style.uppercase = upper.input.checked;
    writeStyle();
  });
  const shadow = checkbox("Soft shadow", style.shadow);
  shadow.input.addEventListener("change", () => {
    style.shadow = shadow.input.checked;
    writeStyle();
  });
  const safe = checkbox("Keep inside safe area", layer.safe_zone !== false);
  safe.input.addEventListener("change", () => {
    layer.safe_zone = safe.input.checked;
    commit();
  });

  const opacity = el("input", {
    type: "range",
    min: "0",
    max: "1",
    step: "0.01",
    value: String(numberOr(layer.opacity, 1)),
    "aria-label": "Text opacity",
  });
  const opacityValue = el("span", { class: "st-mono st-range-value", text: `${Math.round(numberOr(layer.opacity, 1) * 100)}%` });
  opacity.addEventListener("input", () => {
    layer.opacity = clamp(numberOr(opacity.value), 0, 1);
    opacityValue.textContent = `${Math.round(layer.opacity * 100)}%`;
    commit();
  });

  stage.append(el("div", { class: "st-check-row" }, [upper.wrapper, shadow.wrapper, safe.wrapper]));
  stage.append(el("div", { class: "st-range-row" }, [
    el("span", { class: "st-field-label", text: "Opacity" }),
    opacity,
    opacityValue,
  ]));

  const remove = el("button", { class: "st-btn st-btn-quiet st-btn-small st-danger", type: "button", text: "Remove text" });
  remove.addEventListener("click", () => {
    const graphics = (ctx.getEdit()?.graphics || []).filter((item) => item.id !== layer.id);
    ctx.setGraphics(graphics);
    ctx.select("text", "");
  });
  stage.append(el("div", { class: "st-layer-foot" }, [remove]));
  host.append(stage);

  function writeStyle() {
    layer.style = { ...style };
    commit();
  }

  function commit() {
    const graphics = (ctx.getEdit()?.graphics || []).map((item) => (
      item.id === layer.id ? clone(layer) : item
    ));
    ctx.setGraphics(graphics);
  }
}
