/**
 * Voice Room — compare two voices on the same line.
 *
 * The panel owns only the two selectors and the A/B/Swap buttons. Playback
 * goes through the page's own path (`play` for stock voices, `playMine` for
 * clones), so the Row lists, this panel and the notice line all share one
 * player and one honest playing state.
 *
 * @param {{
 *   catalog?: () => {engines?: Array, clones?: Array} | null,
 *   play?: (engine: string, voice: string, label: string) => void,
 *   playMine?: (item: object) => void,
 *   playback?: () => {phase?: string, key?: string},
 * }} options
 */

import { el } from "./ui.js";

const CLONE_GROUP = "My clones";

function stockVoices(engine) {
  return (engine?.voices || []).filter(
    (voice) => voice && !voice.clone && voice.id !== undefined && voice.id !== null,
  );
}

/** One flat list in the order the selectors show it: clones, then engines. */
function choicesFor(data) {
  const groups = [];
  const clones = (data?.clones || []).filter((item) => item && item.voice_id);
  if (clones.length) {
    groups.push({
      label: CLONE_GROUP,
      options: clones.map((item) => ({
        key: `clone:${item.voice_id}`,
        label: item.name || "Cloned voice",
        kind: "clone",
        item,
      })),
    });
  }
  for (const engine of data?.engines || []) {
    if (!engine?.available) continue;
    const voices = stockVoices(engine);
    if (!voices.length) continue;
    groups.push({
      label: engine.label || engine.id || "Voices",
      options: voices.map((voice) => ({
        key: `${engine.id}:${voice.id}`,
        label: voice.name || String(voice.id) || "Default",
        kind: "stock",
        engine: engine.id,
        voice: String(voice.id),
      })),
    });
  }
  return groups;
}

export function createComparePanel({
  catalog = () => null,
  play = () => {},
  playMine = () => {},
  playback = () => ({ phase: "idle", key: "" }),
} = {}) {
  const node = el("section", { class: "vr-section", "data-panel": "compare" });
  // The chosen keys survive catalog refreshes and page repaints.
  const selection = { A: "", B: "" };

  function ensureSelection(flat) {
    if (!flat.length) {
      selection.A = "";
      selection.B = "";
      return;
    }
    const keys = new Set(flat.map((choice) => choice.key));
    if (!selection.A || !keys.has(selection.A)) selection.A = flat[0].key;
    if (!selection.B || !keys.has(selection.B)) {
      selection.B = (flat.find((choice) => choice.key !== selection.A) || flat[0]).key;
    }
  }

  function paint() {
    const groups = choicesFor(catalog());
    const flat = groups.flatMap((group) => group.options);
    ensureSelection(flat);
    const byKey = new Map(flat.map((choice) => [choice.key, choice]));
    const state = playback() || {};
    const phase = String(state.phase || "idle");
    const key = String(state.key || "");

    const status = (() => {
      if (!flat.length) return "No voices to compare yet.";
      if (phase !== "idle" && key) {
        const side = key === selection.A ? "A" : key === selection.B ? "B" : "";
        const choice = byKey.get(key);
        if (side) {
          const verb = phase === "generating" ? "Making" : "Playing";
          return `${verb} ${side}: ${choice?.label || "this voice"}`;
        }
        return "Another voice is playing.";
      }
      return "Ready. Both sides use the same line.";
    })();

    const selector = (side) => {
      const select = el("select", {
        "aria-label": `Voice ${side}`,
        disabled: !flat.length,
      });
      if (!flat.length) {
        select.append(el("option", { value: "", text: "No voices available" }));
      }
      for (const group of groups) {
        select.append(el("optgroup", { label: group.label }, group.options.map(
          (choice) => el("option", {
            value: choice.key,
            text: choice.label,
            selected: choice.key === selection[side],
          }),
        )));
      }
      select.addEventListener("change", () => {
        selection[side] = select.value;
        paint();
      });
      return el("label", { class: "vr-field" }, [
        el("span", { text: `Voice ${side}` }),
        select,
      ]);
    };

    const button = (side) => {
      const active = phase !== "idle" && key === selection[side];
      const control = el("button", {
        class: "primary small",
        type: "button",
        text: active ? `Stop ${side}` : `Play ${side}`,
        disabled: !byKey.has(selection[side]),
      });
      control.addEventListener("click", () => {
        const choice = byKey.get(selection[side]);
        if (!choice) return;
        if (choice.kind === "clone") playMine(choice.item);
        else void play(choice.engine, choice.voice, choice.label);
      });
      return control;
    };

    const swap = el("button", { class: "ghost small", type: "button", text: "Swap", disabled: !flat.length });
    swap.addEventListener("click", () => {
      const first = selection.A;
      selection.A = selection.B;
      selection.B = first;
      paint();
    });

    const head = el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "A/B" }), "compare"]),
        el("h2", { text: "Compare voices" }),
        el("p", { class: "hint", text: "Put two voices on the same line before you pick one." }),
      ]),
    ]);
    const card = el("div", { class: "vr-card vr-compare" }, [
      el("div", { class: "vr-compare-grid" }, [selector("A"), selector("B")]),
      el("div", { class: "vr-actions vr-compare-actions" }, [button("A"), button("B"), swap]),
      el("p", {
        class: "vr-status vr-compare-status",
        role: "status",
        "aria-live": "polite",
        text: status,
      }),
      el("p", { class: "hint vr-compare-hint", text: "Both sides use the page's Test line and Rate." }),
    ]);
    node.replaceChildren(head, card);
  }

  paint();
  return { node, render: paint };
}
