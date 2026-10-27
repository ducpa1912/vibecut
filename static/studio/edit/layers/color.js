/**
 * Colour layer controls.
 *
 * Saving is the whole job of this panel in Wave 2: the render track consumes
 * the `color` object from the Edit. Presets and sliders write absolute values,
 * so reloading the Edit reproduces the same look.
 */

import { el } from "../../ui.js";
import {
  COLOR_CONTROLS,
  COLOR_PRESETS,
  COLOR_RANGES,
  clamp,
  clone,
  numberOr,
} from "../model.js";

function slider(key, value, onInput) {
  const [low, high] = COLOR_RANGES[key];
  const input = el("input", {
    type: "range",
    min: String(low),
    max: String(high),
    step: "0.01",
    value: String(numberOr(value)),
    "aria-label": COLOR_CONTROLS.find(([name]) => name === key)?.[1] || key,
  });
  const readout = el("span", { class: "st-mono st-range-value", text: signed(value) });
  input.addEventListener("input", () => {
    const next = clamp(numberOr(input.value), low, high);
    readout.textContent = signed(next);
    onInput(next);
  });
  return { input, readout };
}

function signed(value) {
  const number = numberOr(value);
  const percent = Math.round(number * 100);
  if (number > 0) return `+${percent}`;
  if (number < 0) return String(percent);
  return "0";
}

export function mountColorPanel(host, ctx) {
  const color = {
    preset: "none",
    ...clone(ctx.getEdit()?.color || {}),
  };
  host.replaceChildren();

  const grid = el("div", { class: "st-color-grid", role: "group", "aria-label": "Colour preset" });
  for (const [value, preset] of Object.entries(COLOR_PRESETS)) {
    const button = el("button", {
      class: `st-color-preset${value === color.preset ? " is-active" : ""}`,
      type: "button",
      "aria-pressed": value === color.preset ? "true" : "false",
      dataset: { preset: value },
    }, [
      el("i", { style: `background:${preset.swatch}`, "aria-hidden": "true" }),
      el("span", { text: preset.label }),
    ]);
    button.addEventListener("click", () => {
      color.preset = value;
      Object.assign(color, clone(preset.values));
      for (const item of grid.querySelectorAll(".st-color-preset")) {
        const active = item.dataset.preset === value;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      }
      syncSliders();
      commit();
    });
    grid.append(button);
  }
  host.append(el("div", { class: "st-layer-stage-head" }, [
    el("h3", { text: "Colour" }),
    el("span", { class: "st-hint", text: COLOR_PRESETS[color.preset]?.label || "Original" }),
  ]));
  host.append(el("p", { class: "st-hint", text: "Pick a look, then make small changes. The render uses these exact values." }));
  host.append(grid);

  const controls = el("div", { class: "st-color-controls" });
  const sliders = {};
  for (const [key, label] of COLOR_CONTROLS) {
    const { input, readout } = slider(key, color[key], (next) => {
      color[key] = next;
      color.preset = currentPreset();
      commit();
    });
    sliders[key] = { input, readout };
    controls.append(el("div", { class: "st-range-row" }, [
      el("span", { class: "st-field-label", text: label }),
      input,
      readout,
    ]));
  }
  host.append(controls);

  const note = el("p", { class: "st-hint", text: "Values are saved as part of this story. Other stories keep their own look." });
  const reset = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Reset this look" });
  reset.addEventListener("click", () => {
    const preset = COLOR_PRESETS[color.preset] || COLOR_PRESETS.none;
    Object.assign(color, clone(preset.values));
    syncSliders();
    commit();
  });
  host.append(note);
  host.append(el("div", { class: "st-layer-foot" }, [reset]));

  function currentPreset() {
    // Keep the preset name while the creator tunes it; that is how the render
    // compiler treats explicit slider values too.
    return color.preset in COLOR_PRESETS ? color.preset : "none";
  }

  function syncSliders() {
    for (const [key] of COLOR_CONTROLS) {
      const { input, readout } = sliders[key];
      const value = numberOr(color[key]);
      input.value = String(value);
      readout.textContent = signed(value);
    }
  }

  function commit() {
    ctx.setColor({
      preset: color.preset in COLOR_PRESETS ? color.preset : "none",
      lut: color.lut || null,
      exposure: clamp(numberOr(color.exposure), -1, 1),
      contrast: clamp(numberOr(color.contrast), -1, 1),
      saturation: clamp(numberOr(color.saturation), -1, 1),
      temperature: clamp(numberOr(color.temperature), -1, 1),
      vignette: clamp(numberOr(color.vignette), 0, 1),
      grain: clamp(numberOr(color.grain), 0, 1),
      sharpen: clamp(numberOr(color.sharpen), 0, 1),
    });
  }

  syncSliders();
}
