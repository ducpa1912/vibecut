/**
 * Effects controls: motion and graphic effects.
 *
 * Motion layers write `edit.motion`; arrows, circles, underlines, progress bars
 * and stickers write `edit.graphics` entries with type "fx". Coordinates are
 * output space, matching the renderer. Beat snapping uses the local beat read
 * for the music bed already chosen in the Audio panel.
 */

import { request } from "../../api.js";
import { ensureCheckStyles } from "../../check.js";
import { el } from "../../ui.js";
import {
  FX_LABELS,
  MOTION_LABELS,
  TEXT_ANCHORS,
  clamp,
  clone,
  formatSpan,
  numberOr,
  round,
  uid,
} from "../model.js";

const MOTION_DEFAULTS = {
  punch_in: { amount: 0.08, ramp: 0.4 },
  snap_zoom: { amount: 0.12, ramp: 0.2 },
  push: { amount: 0.06, ramp: 0 },
  shake: { amount: 0.01, ramp: 0.2 },
};

const FX_DEFAULTS = {
  arrow: { w: 0.3, h: 0.12 },
  circle: { w: 0.3, h: 0.3 },
  underline: { w: 0.4, h: 0.06 },
  progress_bar: { w: 0.7, h: 0.02 },
  sticker: { w: 0.24, h: 0.24 },
};

const BEAT_TOLERANCE = 0.12;
const MAX_MOTION = 8;
const MAX_GRAPHICS = 32;

function field(label, control, hint = "") {
  const wrapper = el("label", { class: "st-field" }, [
    el("span", { text: label }),
    control,
  ]);
  if (hint) wrapper.append(el("small", { class: "st-field-hint", text: hint }));
  return wrapper;
}

function numberInput(value, { min, max, step = 0.1 } = {}) {
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

function validAsset(asset) {
  return Boolean(
    asset
    && /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(String(asset.id || ""))
    && /^[a-f0-9]{16,64}$/.test(String(asset.hash || "").toLowerCase()),
  );
}

function spanFromPlayhead(duration, playhead, length = 1.2) {
  const total = Math.max(0.2, numberOr(duration, 0.2));
  let start = clamp(numberOr(playhead), 0, Math.max(0, total - 0.2));
  if (start >= total - 0.1) start = Math.max(0, total - length);
  const end = Math.min(total, start + length);
  return { start: round(start), end: round(Math.max(start + 0.1, end)) };
}

function newMotion(kind, { duration, playhead, count }) {
  const span = spanFromPlayhead(duration, playhead);
  const defaults = MOTION_DEFAULTS[kind] || MOTION_DEFAULTS.punch_in;
  return {
    id: uid("mo"),
    kind,
    start: span.start,
    end: span.end,
    amount: defaults.amount,
    ramp: defaults.ramp,
    seed: kind === "shake" ? Math.floor(Math.random() * 2_000_000_000) : 0,
    _order: count,
  };
}

function newFx(kind, { duration, playhead, count, asset }) {
  const span = spanFromPlayhead(duration, playhead, 1.5);
  const box = FX_DEFAULTS[kind] || FX_DEFAULTS.arrow;
  return {
    id: uid("fx"),
    type: "fx",
    kind,
    start: span.start,
    end: span.end,
    anchor: "center",
    box: { w: box.w, h: box.h },
    z: 20 + count,
    color: "#ffffff",
    thickness: 6,
    opacity: 1,
    asset: kind === "sticker" ? asset : null,
    _order: count,
  };
}

function stripPrivate(layer) {
  const next = clone(layer);
  delete next._order;
  return next;
}

function currentJobId() {
  try {
    const value = JSON.parse(localStorage.getItem("vibecut.studio.job") || "null");
    return value && typeof value === "object" && value.id ? String(value.id) : "";
  } catch (_) {
    return "";
  }
}

function currentJobMusic(edit) {
  const music = edit?.audio?.music;
  if (music && typeof music === "object" && typeof music.track === "string" && music.track) {
    return music;
  }
  return null;
}

export function mountEffectsPanel(host, ctx) {
  ensureCheckStyles();
  let disposed = false;
  let beatState = { status: "loading", bpm: 0, track: "", message: "Reading the music tempo…" };
  let notice = "";
  let addAssetId = "";
  let addAssetHash = "";

  function selectedId() {
    return ctx.getSelectedId("effects");
  }

  function motionList() {
    return ctx.getEdit()?.motion || [];
  }

  function fxList() {
    return (ctx.getEdit()?.graphics || []).filter((layer) => layer.type === "fx");
  }

  function setMotionLayer(layer) {
    const next = motionList().map((item) => (
      item.id === layer.id ? stripPrivate(layer) : item
    ));
    ctx.setMotion(next);
  }

  function setFxLayer(layer) {
    const next = (ctx.getEdit()?.graphics || []).map((item) => (
      item.id === layer.id ? stripPrivate(layer) : item
    ));
    ctx.setGraphics(next);
  }

  function notify(message, tone = "") {
    notice = message || "";
    if (typeof ctx.notify === "function") ctx.notify(notice, tone);
  }

  function beatGrid() {
    const bpm = Number(beatState.bpm);
    if (!Number.isFinite(bpm) || bpm < 20 || bpm > 300) return null;
    return 60 / bpm;
  }

  function nearestBeat(value, period) {
    return Math.round(value / period) * period;
  }

  function snapLayer(layer, period) {
    let changed = false;
    const start = nearestBeat(numberOr(layer.start), period);
    if (Math.abs(start - numberOr(layer.start)) <= BEAT_TOLERANCE) {
      layer.start = round(clamp(start, 0, 100000), 3);
      changed = true;
    }
    const end = nearestBeat(numberOr(layer.end), period);
    if (Math.abs(end - numberOr(layer.end)) <= BEAT_TOLERANCE) {
      layer.end = round(clamp(end, numberOr(layer.start) + 0.05, 100000), 3);
      changed = true;
    }
    if (numberOr(layer.end) <= numberOr(layer.start)) {
      layer.end = round(numberOr(layer.start) + Math.max(0.1, period / 2), 3);
      changed = true;
    }
    return changed;
  }

  function snapSelected() {
    const period = beatGrid();
    if (!period) {
      notify("No tempo is available yet. Choose a music track in Audio, then try again.", "bad");
      return;
    }
    const id = selectedId();
    const motion = motionList().find((layer) => layer.id === id);
    if (motion) {
      const layer = clone(motion);
      if (snapLayer(layer, period)) {
        setMotionLayer(layer);
        notify("Snapped motion to the tempo grid.", "ok");
        ctx.refresh();
      } else notify("No beat within 120 ms of this motion.", "");
      return;
    }
    const fx = fxList().find((layer) => layer.id === id);
    if (fx) {
      const layer = clone(fx);
      if (snapLayer(layer, period)) {
        setFxLayer(layer);
        notify("Snapped effect to the tempo grid.", "ok");
        ctx.refresh();
      } else notify("No beat within 120 ms of this effect.", "");
      return;
    }
    notify("Select a motion or effect first.", "");
  }

  function snapAll() {
    const period = beatGrid();
    if (!period) {
      notify("No tempo is available yet. Choose a music track in Audio, then try again.", "bad");
      return;
    }
    let count = 0;
    const motion = motionList().map((item) => {
      const layer = clone(item);
      if (snapLayer(layer, period)) count += 1;
      return layer;
    });
    const graphics = (ctx.getEdit()?.graphics || []).map((item) => {
      if (item.type !== "fx") return item;
      const layer = clone(item);
      if (snapLayer(layer, period)) count += 1;
      return layer;
    });
    if (!count) {
      notify("No effects were close enough to a beat (within 120 ms).", "");
      return;
    }
    ctx.setMotion(motion);
    ctx.setGraphics(graphics);
    notify(`Snapped ${count} ${count === 1 ? "effect" : "effects"} to the tempo grid.`, "ok");
    ctx.refresh();
  }

  async function loadBeat() {
    const edit = ctx.getEdit();
    const music = currentJobMusic(edit);
    const track = music?.track || "";
    try {
      if (!track) {
        beatState = {
          status: "empty",
          bpm: 0,
          track: "",
          message: "Choose a music track in Audio, then return here to snap effects to its tempo.",
        };
      } else {
        const params = new URLSearchParams({ source: "library", track });
        // Uploaded beds are stored job-relative; the server resolves them
        // inside the job folder only.
        const jobId = currentJobId();
        if (!/^(\/|[A-Za-z]:[\\/])/.test(track) && jobId) params.set("job_id", jobId);
        const result = await request(`/api/audio/beats?${params.toString()}`);
        const bpm = Number(result?.bpm);
        beatState = Number.isFinite(bpm) && bpm > 0
          ? { status: "ready", bpm, track: result?.track || track, message: "" }
          : { status: "error", bpm: 0, track, message: "The track tempo could not be read." };
      }
    } catch (error) {
      if (disposed) return;
      beatState = {
        status: "error",
        bpm: 0,
        track,
        message: error?.status === 404
          ? "Choose a music track in Audio first. Beat snap needs one."
          : (error?.message || "Beat detection is unavailable for this track."),
      };
    }
    if (!disposed) render();
  }

  function beatRow() {
    const row = el("div", { class: "st-audio-row" }, [
      el("span", { class: "st-field-label", text: "Beat snap" }),
      el("span", {
        class: "st-mono",
        text: beatState.status === "ready"
          ? `${Math.round(beatState.bpm)} BPM`
          : beatState.status === "loading" ? "Reading…" : "Unavailable",
      }),
    ]);
    const card = el("div", { class: "st-layer-stage" }, [
      row,
      el("p", { class: "st-hint", text: beatState.status === "ready"
        ? `Snap start and end to the tempo grid within 120 ms. Track: ${String(beatState.track).split("/").pop() || "music"}. Exact beat marks are not returned by this build; the grid comes from the track BPM.`
        : beatState.message }),
    ]);
    if (beatState.status === "ready") {
      const actions = el("div", { class: "st-layer-add" });
      const snapOne = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Snap selected" });
      snapOne.addEventListener("click", snapSelected);
      const snapEvery = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Snap all" });
      snapEvery.addEventListener("click", snapAll);
      actions.append(snapOne, snapEvery);
      card.append(actions);
    }
    return card;
  }

  function layerRow(kind, layer, active) {
    const isMotion = kind === "motion";
    const label = isMotion
      ? MOTION_LABELS[layer.kind] || "Motion"
      : FX_LABELS[layer.kind] || "Effect";
    const row = el("button", {
      class: `st-layer-row${active ? " is-active" : ""}`,
      type: "button",
      "aria-pressed": active ? "true" : "false",
    }, [
      el("span", { class: "st-layer-badge", text: isMotion ? "Motion" : "Effect" }),
      el("span", { class: "st-layer-name", text: `${label} · ${formatSpan(layer.start, layer.end)}` }),
    ]);
    row.addEventListener("click", () => ctx.select("effects", layer.id));
    return row;
  }

  function motionEditor(layer) {
    const stage = el("div", { class: "st-layer-stage" });
    stage.append(el("div", { class: "st-layer-stage-head" }, [
      el("h4", { text: MOTION_LABELS[layer.kind] || "Motion" }),
      el("span", { class: "st-mono st-hint", text: formatSpan(layer.start, layer.end) }),
    ]));

    const kind = el("select", { "aria-label": "Motion kind" });
    for (const value of Object.keys(MOTION_DEFAULTS)) {
      kind.append(el("option", { value, text: MOTION_LABELS[value] || value, selected: value === layer.kind }));
    }
    kind.addEventListener("change", () => {
      const defaults = MOTION_DEFAULTS[kind.value] || MOTION_DEFAULTS.punch_in;
      layer.kind = kind.value;
      layer.amount = defaults.amount;
      layer.ramp = defaults.ramp;
      setMotionLayer(layer);
      ctx.refresh();
    });

    const start = numberInput(layer.start, { min: 0, max: ctx.getDuration(), step: 0.05 });
    const end = numberInput(layer.end, { min: 0, max: ctx.getDuration(), step: 0.05 });
    start.addEventListener("input", () => {
      layer.start = clamp(numberOr(start.value), 0, Math.max(0, ctx.getDuration() - 0.1));
      if (layer.end <= layer.start + 0.05) layer.end = Math.min(ctx.getDuration(), layer.start + 0.2);
      end.value = String(round(layer.end, 3));
      setMotionLayer(layer);
    });
    end.addEventListener("input", () => {
      layer.end = clamp(numberOr(end.value), layer.start + 0.05, ctx.getDuration());
      setMotionLayer(layer);
    });

    const shake = layer.kind === "shake";
    const amount = numberInput(layer.amount, {
      min: shake ? 0.001 : 0.01,
      max: shake ? 0.05 : 0.5,
      step: shake ? 0.001 : 0.01,
    });
    amount.addEventListener("input", () => {
      layer.amount = clamp(numberOr(amount.value), shake ? 0.001 : 0.01, shake ? 0.05 : 0.5);
      setMotionLayer(layer);
    });
    const ramp = numberInput(layer.ramp, { min: 0, max: 10, step: 0.05 });
    ramp.addEventListener("input", () => {
      layer.ramp = clamp(numberOr(ramp.value), 0, 10);
      setMotionLayer(layer);
    });
    const seed = numberInput(layer.seed || 0, { min: 0, max: 2147483647, step: 1 });
    seed.disabled = !shake;
    seed.addEventListener("input", () => {
      layer.seed = Math.round(clamp(numberOr(seed.value), 0, 2147483647));
      setMotionLayer(layer);
    });

    stage.append(el("div", { class: "st-control-grid" }, [
      field("Kind", kind),
      field("Start (s)", start),
      field("End (s)", end),
      field("Amount", amount, shake ? "Shake amplitude in frame width." : "Zoom or push amount."),
      field("Ramp (s)", ramp, "Time to reach full strength."),
      field("Seed", seed, "Shake phase. Same seed gives the same motion."),
    ]));

    if (shake) {
      const reseed = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "New shake seed" });
      reseed.addEventListener("click", () => {
        layer.seed = Math.floor(Math.random() * 2_000_000_000);
        seed.value = String(layer.seed);
        setMotionLayer(layer);
      });
      stage.append(el("div", { class: "st-layer-add" }, [reseed]));
    }

    const remove = el("button", { class: "st-btn st-btn-quiet st-btn-small st-danger", type: "button", text: "Remove motion" });
    remove.addEventListener("click", () => {
      ctx.setMotion(motionList().filter((item) => item.id !== layer.id));
      ctx.select("effects", "");
    });
    stage.append(el("div", { class: "st-layer-foot" }, [remove]));
    return stage;
  }

  function fxEditor(layer) {
    const stage = el("div", { class: "st-layer-stage" });
    stage.append(el("div", { class: "st-layer-stage-head" }, [
      el("h4", { text: FX_LABELS[layer.kind] || "Effect" }),
      el("span", { class: "st-mono st-hint", text: formatSpan(layer.start, layer.end) }),
    ]));

    const kind = el("select", { "aria-label": "Effect kind" });
    for (const value of Object.keys(FX_DEFAULTS)) {
      kind.append(el("option", { value, text: FX_LABELS[value] || value, selected: value === layer.kind }));
    }
    kind.addEventListener("change", () => {
      const box = FX_DEFAULTS[kind.value] || FX_DEFAULTS.arrow;
      if (kind.value === "sticker" && !validAsset(layer.asset)) {
        kind.value = layer.kind;
        notify("To make this a sticker, add an effect with an installed asset id and hash.", "bad");
        return;
      }
      layer.kind = kind.value;
      layer.box = { w: box.w, h: box.h };
      if (layer.kind !== "sticker") layer.asset = null;
      setFxLayer(layer);
      ctx.refresh();
    });

    const start = numberInput(layer.start, { min: 0, max: ctx.getDuration(), step: 0.05 });
    const end = numberInput(layer.end, { min: 0, max: ctx.getDuration(), step: 0.05 });
    start.addEventListener("input", () => {
      layer.start = clamp(numberOr(start.value), 0, Math.max(0, ctx.getDuration() - 0.1));
      if (layer.end <= layer.start + 0.05) layer.end = Math.min(ctx.getDuration(), layer.start + 0.2);
      end.value = String(round(layer.end, 3));
      setFxLayer(layer);
    });
    end.addEventListener("input", () => {
      layer.end = clamp(numberOr(end.value), layer.start + 0.05, ctx.getDuration());
      setFxLayer(layer);
    });

    const anchor = el("select", { "aria-label": "Effect position" });
    for (const [value, label] of TEXT_ANCHORS) {
      anchor.append(el("option", { value, text: label, selected: value === layer.anchor }));
    }
    anchor.addEventListener("change", () => {
      layer.anchor = anchor.value;
      setFxLayer(layer);
    });

    const width = numberInput(Math.round(numberOr(layer.box?.w, 0.3) * 100), { min: 1, max: 100, step: 1 });
    const height = numberInput(Math.round(numberOr(layer.box?.h, 0.2) * 100), { min: 1, max: 100, step: 1 });
    width.addEventListener("input", () => {
      layer.box = { ...(layer.box || {}), w: clamp(numberOr(width.value) / 100, 0.01, 1) };
      setFxLayer(layer);
    });
    height.addEventListener("input", () => {
      layer.box = { ...(layer.box || {}), h: clamp(numberOr(height.value) / 100, 0.01, 1) };
      setFxLayer(layer);
    });

    const color = colorInput(layer.color);
    color.addEventListener("input", () => {
      layer.color = color.value;
      setFxLayer(layer);
    });
    const thickness = numberInput(numberOr(layer.thickness, 6), { min: 1, max: 32, step: 1 });
    thickness.disabled = layer.kind === "sticker";
    thickness.addEventListener("input", () => {
      layer.thickness = Math.round(clamp(numberOr(thickness.value), 1, 32));
      setFxLayer(layer);
    });
    const opacity = el("input", {
      type: "range", min: "0", max: "1", step: "0.01",
      value: String(numberOr(layer.opacity, 1)),
      "aria-label": "Effect opacity",
    });
    const opacityValue = el("span", { class: "st-mono st-range-value", text: `${Math.round(numberOr(layer.opacity, 1) * 100)}%` });
    opacity.addEventListener("input", () => {
      layer.opacity = clamp(numberOr(opacity.value), 0, 1);
      opacityValue.textContent = `${Math.round(layer.opacity * 100)}%`;
      setFxLayer(layer);
    });

    stage.append(el("div", { class: "st-control-grid" }, [
      field("Kind", kind),
      field("Position", anchor),
      field("Start (s)", start),
      field("End (s)", end),
      field("Width (%)", width),
      field("Height (%)", height),
      field("Colour", color),
      field("Thickness", thickness),
    ]));
    stage.append(el("div", { class: "st-range-row" }, [
      el("span", { class: "st-field-label", text: "Opacity" }),
      opacity,
      opacityValue,
    ]));

    if (layer.kind === "sticker") {
      const asset = layer.asset && typeof layer.asset === "object" ? layer.asset : { id: "", hash: "" };
      const assetId = el("input", { type: "text", value: asset.id || "", "aria-label": "Sticker asset id", placeholder: "sticker_id" });
      const assetHash = el("input", { type: "text", value: asset.hash || "", "aria-label": "Sticker content hash", placeholder: "64 hex characters" });
      const applyAsset = () => {
        const candidate = { id: assetId.value.trim(), hash: assetHash.value.trim().toLowerCase() };
        if (!validAsset(candidate)) {
          notify("A sticker needs an installed asset id and a 16–64 character hex hash.", "bad");
          return;
        }
        layer.asset = candidate;
        setFxLayer(layer);
      };
      assetId.addEventListener("change", applyAsset);
      assetHash.addEventListener("change", applyAsset);
      stage.append(el("div", { class: "st-control-grid" }, [
        field("Sticker asset", assetId),
        field("Asset hash", assetHash),
      ]));
      stage.append(el("p", { class: "st-field-hint", text: "Bundled sticker files are not installed on this build yet. An existing sticker keeps its asset; a new one needs the real id and hash." }));
    }

    const remove = el("button", { class: "st-btn st-btn-quiet st-btn-small st-danger", type: "button", text: "Remove effect" });
    remove.addEventListener("click", () => {
      const next = (ctx.getEdit()?.graphics || []).filter((item) => item.id !== layer.id);
      ctx.setGraphics(next);
      ctx.select("effects", "");
    });
    stage.append(el("div", { class: "st-layer-foot" }, [remove]));
    return stage;
  }

  function addControls() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Add" }));

    const motionRow = el("div", { class: "st-layer-add", style: "margin-top:8px" });
    const motionKind = el("select", { "aria-label": "New motion kind" });
    for (const value of Object.keys(MOTION_DEFAULTS)) {
      motionKind.append(el("option", { value, text: MOTION_LABELS[value] || value }));
    }
    const addMotion = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Add motion",
      disabled: motionList().length >= MAX_MOTION,
      title: motionList().length >= MAX_MOTION ? `A story supports ${MAX_MOTION} motion layers.` : "",
    });
    addMotion.addEventListener("click", () => {
      const next = newMotion(motionKind.value, {
        duration: ctx.getDuration(),
        playhead: ctx.getPlayhead(),
        count: motionList().length,
      });
      const layers = [...motionList(), stripPrivate(next)];
      ctx.setMotion(layers);
      ctx.select("effects", next.id);
    });
    motionRow.append(motionKind, addMotion);
    card.append(motionRow);

    const fxRow = el("div", { class: "st-layer-add", style: "margin-top:7px" });
    const fxKind = el("select", { "aria-label": "New effect kind" });
    for (const value of Object.keys(FX_DEFAULTS)) {
      fxKind.append(el("option", { value, text: FX_LABELS[value] || value }));
    }
    const addFx = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Add effect",
      disabled: (ctx.getEdit()?.graphics || []).length >= MAX_GRAPHICS,
      title: (ctx.getEdit()?.graphics || []).length >= MAX_GRAPHICS
        ? `A story supports ${MAX_GRAPHICS} graphics layers.`
        : "",
    });
    fxRow.append(fxKind, addFx);
    card.append(fxRow);

    const assetRow = el("div", { class: "st-control-grid", hidden: true, style: "margin-top:7px" });
    const assetId = el("input", { type: "text", value: addAssetId, "aria-label": "New sticker asset id", placeholder: "sticker_id" });
    const assetHash = el("input", { type: "text", value: addAssetHash, "aria-label": "New sticker hash", placeholder: "asset hash" });
    assetRow.append(field("Sticker asset", assetId), field("Asset hash", assetHash));
    card.append(assetRow);
    const refreshAssetRow = () => {
      assetRow.hidden = fxKind.value !== "sticker";
      addFx.textContent = fxKind.value === "sticker" ? "Add sticker" : "Add effect";
    };
    fxKind.addEventListener("change", refreshAssetRow);
    refreshAssetRow();

    addFx.addEventListener("click", () => {
      addAssetId = assetId.value.trim();
      addAssetHash = assetHash.value.trim().toLowerCase();
      const asset = { id: addAssetId, hash: addAssetHash };
      if (fxKind.value === "sticker" && !validAsset(asset)) {
        notify("A sticker needs an installed asset id and a 16–64 character hex hash.", "bad");
        return;
      }
      const next = newFx(fxKind.value, {
        duration: ctx.getDuration(),
        playhead: ctx.getPlayhead(),
        count: fxList().length,
        asset: fxKind.value === "sticker" ? asset : null,
      });
      const graphics = [...(ctx.getEdit()?.graphics || []), stripPrivate(next)];
      ctx.setGraphics(graphics);
      ctx.select("effects", next.id);
    });

    card.append(el("p", { class: "st-hint", text: "Motion changes the crop window. Effects sit on the finished vertical frame." }));
    return card;
  }

  function render() {
    host.replaceChildren();
    const motions = motionList();
    const fx = fxList();
    const active = selectedId();
    const selectedMotion = motions.find((layer) => layer.id === active) || null;
    const selectedFx = fx.find((layer) => layer.id === active) || null;

    const head = el("div", { class: "st-card st-check-card" }, [
      el("h3", { text: "Motion and effects" }),
      el("p", { class: "st-hint", text: "Punch-in, snap zoom, push and shake change the crop. Arrows, circles, underlines, progress bars and stickers draw over the cut." }),
    ]);
    if (notice) head.append(el("p", { class: "st-status", text: notice }));
    host.append(head);

    if (!motions.length && !fx.length) {
      host.append(el("div", { class: "st-layer-empty" }, [
        el("h3", { text: "No effects yet" }),
        el("p", { text: "Add a motion at the playhead, or draw attention with an arrow, circle or underline." }),
      ]));
    } else {
      const list = el("div", { class: "st-layer-list" });
      for (const layer of motions) list.append(layerRow("motion", layer, layer.id === active));
      for (const layer of fx) list.append(layerRow("fx", layer, layer.id === active));
      host.append(list);
    }

    host.append(beatRow());
    host.append(addControls());
    if (selectedMotion) host.append(motionEditor(clone(selectedMotion)));
    if (selectedFx) host.append(fxEditor(clone(selectedFx)));
  }

  render();
  void loadBeat();

  return () => {
    disposed = true;
  };
}
