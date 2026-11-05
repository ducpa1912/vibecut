/**
 * Clean layer controls.
 *
 * Check findings become Clean layers in the same Edit document. Boxes and
 * ranges use source coordinates and source time, exactly as the renderer
 * expects; the panel never converts them to output space.
 *
 * Adding is gated by the server policy on the job (`job.rights_policy`).
 * Every kind of found text can be cleaned. A watermark, handle or logo needs
 * the per-video rights tick, even with the lock off. The browser never decides
 * policy; it only renders the server's reasons.
 */

import { getJob, request } from "../../api.js";
import {
  cleanBlockReason,
  cleanReasonText,
  policyLocked,
} from "../../import.js";
import { ensureCheckStyles } from "../../check.js";
import { el, formatCount } from "../../ui.js";
import { icon } from "../icons.js";
import {
  CLEAN_LABELS,
  clamp,
  clone,
  formatSpan,
  formatTime,
  numberOr,
  round,
} from "../model.js";

const CHECK_POLL_MS = 2500;
const MAX_CLEAN = 1000;
const SCAN_REQUIRED = "Run Scan footage first.";

// The status outlives one panel mount: selecting a new layer remounts the
// inspector, and the summary must stay visible after that refresh.
const AUTO_CLEAN_STATE = new Map();

// Clean has two methods. The other kinds stay in the Edit format so saved
// layers still render, and show their old name with a switch to these two.
const KIND_ORDER = ["fill", "blur"];

const KIND_COPY = {
  delogo: "Remove text",
  fill: "AI fill",
  plate: "Cover plate",
  blur: "Blur",
  mask: "Mask",
  mosaic: "Mosaic",
  crop_guard: "Keep out of crop",
};

// AI fill engines. The server keeps the same list (edits.FILL_METHODS).
const FILL_METHODS = [
  ["lama", "LaMa · per frame, best on still backgrounds"],
  ["sttn", "STTN · video, best on subtitles"],
  ["telea", "Telea · OpenCV, very fast, for plain backgrounds"],
  ["ns", "Navier-Stokes · OpenCV, very fast, for smooth backgrounds"],
];
const FILL_KINDS = new Set(["delogo", "blur", "plate", "mask"]);

// Drawn boxes start with the last method used; the first is AI fill when an
// engine is ready, else Blur.
let fillAvailable = false;
let lastDrawKind = "";
let lastEngine = "";

export function setFillAvailable(value) {
  fillAvailable = Boolean(value);
}

export function isFillAvailable() {
  return fillAvailable;
}

export function rememberDrawKind(kind) {
  if (KIND_ORDER.includes(kind)) lastDrawKind = kind;
}

/** The engine every AI fill in this session uses. LaMa until changed. */
export function rememberEngine(method) {
  if (FILL_METHODS.some(([value]) => value === method)) lastEngine = method;
}

export function drawEngine() {
  return lastEngine || FILL_METHODS[0][0];
}

export function drawKind() {
  if (lastDrawKind === "fill" && !fillAvailable) return "blur";
  return lastDrawKind || (fillAvailable ? "fill" : "blur");
}

/** Set a layer's kind, adding or dropping the fill engine to match. */
export function setLayerKind(layer, kind) {
  layer.kind = kind;
  if (kind === "fill") {
    if (!FILL_METHODS.some(([value]) => value === layer.method)) layer.method = drawEngine();
  } else {
    delete layer.method;
  }
  return layer;
}

const TRACKLET_LABELS = {
  subtitle: "Burned-in subtitles",
  title: "Title or card",
  lower_third: "Lower third",
  handle_or_logo: "Handle or logo",
  watermark: "Platform watermark",
  credit: "Credit or source mark",
  screen_text: "Screen interface",
};

function currentJobId() {
  try {
    const raw = localStorage.getItem("vibecut.studio.job");
    if (!raw) return "";
    const value = JSON.parse(raw);
    return value && typeof value === "object" && value.id ? String(value.id) : "";
  } catch (_) {
    return "";
  }
}

async function fetchCheck(jobId) {
  if (!jobId) return { report: null, pending: false };
  try {
    const report = await request(`/api/jobs/${encodeURIComponent(jobId)}/check`);
    const status = String(report?.status || "").toLowerCase();
    return {
      report,
      pending: status === "queued" || status === "running" || report?.complete === false,
    };
  } catch (error) {
    if (error?.status === 404) return { report: null, pending: false };
    if (error?.status === 202) {
      return {
        report: error.detail && typeof error.detail === "object" ? error.detail : null,
        pending: true,
      };
    }
    throw error;
  }
}

/**
 * POST the Edit's auto-clean route with an empty body.
 *
 * Handles are excluded. The server keeps the rights gate and the per-kind
 * refusals, and returns only the layers the saved Edit does not already hold.
 */
export function autoCleanRequest(jobId, editId, body = {}) {
  return request(
    `/api/jobs/${encodeURIComponent(jobId)}/edits/${encodeURIComponent(editId)}/auto-clean`,
    { method: "POST", body },
  );
}

function autoCleanStateFor(jobId) {
  const key = String(jobId || "open");
  let state = AUTO_CLEAN_STATE.get(key);
  if (!state) {
    state = { busy: false, notice: null };
    AUTO_CLEAN_STATE.set(key, state);
    if (AUTO_CLEAN_STATE.size > 8) {
      AUTO_CLEAN_STATE.delete(AUTO_CLEAN_STATE.keys().next().value);
    }
  }
  return state;
}

function sameArea(first, second) {
  if (!first || !second) return false;
  const left = Math.max(numberOr(first.x), numberOr(second.x));
  const top = Math.max(numberOr(first.y), numberOr(second.y));
  const right = Math.min(numberOr(first.x) + numberOr(first.w), numberOr(second.x) + numberOr(second.w));
  const bottom = Math.min(numberOr(first.y) + numberOr(first.h), numberOr(second.y) + numberOr(second.h));
  if (right > left && bottom > top) {
    const shared = (right - left) * (bottom - top);
    const union = numberOr(first.w) * numberOr(first.h) + numberOr(second.w) * numberOr(second.h) - shared;
    if (union > 0 && shared / union >= 0.3) return true;
  }
  const dx = Math.abs(numberOr(first.x) + numberOr(first.w) / 2 - numberOr(second.x) - numberOr(second.w) / 2);
  const dy = Math.abs(numberOr(first.y) + numberOr(first.h) / 2 - numberOr(second.y) - numberOr(second.h) / 2);
  return dx <= 0.04 && dy <= 0.03;
}

/**
 * The same text in the same area, mirroring `cleanup._same_scan_text`.
 * Overlapping different text is allowed. Drawn boxes never match.
 */
export function sameScanText(layer, other) {
  if (!String(layer?.tracklet_id || "").trim()) return false;
  if (!sameArea(layer?.box, other?.box)) return false;
  if (layer?.text_key && layer.text_key === other?.text_key) return true;
  const first = Array.isArray(layer?.ranges) ? layer.ranges : [];
  const second = Array.isArray(other?.ranges) ? other.ranges : [];
  if (!first.length || !second.length) return true;
  // Lines that follow each other can touch; only a real overlap is one text.
  return first.some((a) => second.some((b) => (
    Math.min(Number(a.end), Number(b.end)) - Math.max(Number(a.start), Number(b.start)) > 0.05
  )));
}

function foundTextKey(tracklet) {
  return String(tracklet?.text_sample || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

function sameFoundText(first, second) {
  if (first === second) return true;
  // The scan can misread a line ("Hello worl") or catch part of it.
  return Math.min(first.length, second.length) >= 4
    && (first.includes(second) || second.includes(first));
}

/**
 * One row per text. The scan can read the same words in the same area as
 * separate tracklets, so they join, and the longest reading names the row.
 * Subtitles are a new tracklet per line, so all lines in one area are one row.
 * `ids` and `members` carry every tracklet to Clean.
 */
export function mergeFoundTracklets(tracklets) {
  const rows = [];
  for (const tracklet of Array.isArray(tracklets) ? tracklets : []) {
    const id = String(tracklet?.id || "");
    if (!id) continue;
    const key = foundTextKey(tracklet);
    const home = rows.find((row) => row.ids.includes(id))
      || rows.find((row) => {
        if (row.kind !== tracklet.kind || !sameArea(row.box, tracklet.box)) return false;
        return tracklet.kind === "subtitle"
          || (key && sameFoundText(foundTextKey(row), key));
      });
    if (!home) {
      rows.push({
        ...tracklet,
        ids: [id],
        members: [tracklet],
        keys: new Set(key ? [key] : []),
        ranges: [...(tracklet.ranges || [])],
      });
      continue;
    }
    if (!home.ids.includes(id)) {
      home.ids.push(id);
      home.members.push(tracklet);
    }
    if (key && ![...home.keys].some((other) => sameFoundText(other, key))) home.keys.add(key);
    if (key.length > foundTextKey(home).length) home.text_sample = tracklet.text_sample;
    home.box = joinBoxes(home.box, tracklet.box);
    const sorted = [...home.ranges, ...(tracklet.ranges || [])]
      .sort((a, b) => numberOr(a.start) - numberOr(b.start));
    home.ranges = sorted.reduce((joined, range) => {
      const last = joined.at(-1);
      if (last && numberOr(range.start) <= numberOr(last.end)) {
        last.end = Math.max(numberOr(last.end), numberOr(range.end));
      } else {
        joined.push({ ...range });
      }
      return joined;
    }, []);
  }
  return rows.map(({ keys, ...row }) => ({ ...row, lines: Math.max(1, keys.size) }));
}

function joinBoxes(first, second) {
  if (!first || !second) return first || second || null;
  const x = Math.min(numberOr(first.x), numberOr(second.x));
  const y = Math.min(numberOr(first.y), numberOr(second.y));
  return {
    x,
    y,
    w: Math.max(numberOr(first.x) + numberOr(first.w), numberOr(second.x) + numberOr(second.w)) - x,
    h: Math.max(numberOr(first.y) + numberOr(first.h), numberOr(second.y) + numberOr(second.h)) - y,
  };
}

/**
 * One group per found text. Layers saved before scans were deduplicated can
 * hold the same text many times; they read as one row with its pieces inside.
 * Drawn boxes stay on their own rows.
 */
export function cleanGroups(layers) {
  const groups = [];
  for (const layer of Array.isArray(layers) ? layers : []) {
    const scanned = String(layer?.tracklet_id || "").trim();
    const home = scanned && groups.find((group) => {
      const first = group.layers[0];
      if (!String(first?.tracklet_id || "").trim() || !sameArea(first.box, layer.box)) return false;
      if (first.tracklet_kind === "subtitle" && layer.tracklet_kind === "subtitle") return true;
      return first.tracklet_id === layer.tracklet_id
        || (first.label && first.label === layer.label)
        || sameScanText(first, layer);
    });
    if (home) home.layers.push(layer);
    else groups.push({ key: String(layer?.id || groups.length), layers: [layer] });
  }
  return groups;
}

/**
 * Merge generated layers into the current Edit without touching what is there.
 *
 * The server already dedupes against the saved Edit, but this panel can hold
 * unsaved layers. The same text in the same area is one layer, and an existing
 * id is a second guard for older layers.
 */
export function mergeAutoCleanLayers(existing, generated, limit = MAX_CLEAN) {
  const current = Array.isArray(existing)
    ? existing.filter((layer) => layer && typeof layer === "object")
    : [];
  const layers = current.map((layer) => clone(layer));
  const ids = new Set();
  for (const layer of layers) {
    const id = String(layer?.id || "").trim();
    if (id) ids.add(id);
  }

  const cap = Math.max(0, Math.trunc(numberOr(limit, MAX_CLEAN)));
  const added = [];
  const skipped = [];
  let overflow = 0;

  for (const layer of Array.isArray(generated) ? generated : []) {
    if (!layer || typeof layer !== "object") continue;
    const trackletId = String(layer.tracklet_id || "").trim();
    const layerId = String(layer.id || "").trim();
    if (trackletId && layers.some((item) => sameScanText(item, layer))) {
      skipped.push({
        tracklet_id: trackletId,
        reason: "This text already has a Clean layer in the Edit.",
      });
      continue;
    }
    if (layerId && ids.has(layerId)) {
      skipped.push({
        tracklet_id: trackletId || null,
        reason: "An identical Clean layer is already in the Edit.",
      });
      continue;
    }
    if (layers.length >= cap) {
      overflow += 1;
      continue;
    }
    const next = clone(layer);
    if (!layerId) {
      let id = `cl_auto_${layers.length + 1}`;
      while (ids.has(id)) id = `${id}_${layers.length + 1}`;
      next.id = id;
    }
    layers.push(next);
    added.push(next);
    if (next.id) ids.add(String(next.id));
  }

  if (overflow) {
    skipped.push({
      tracklet_id: null,
      reason: `${formatCount(overflow, "region")} did not fit; an Edit supports ${cap} clean layers.`,
    });
  }
  return { layers, added, skipped, overflow };
}

/** One sentence for the panel: counts, the first refusal, then warnings. */
export function autoCleanSummary(result) {
  const added = Math.max(0, Math.trunc(numberOr(result?.added, 0)));
  const skipped = Array.isArray(result?.skipped)
    ? result.skipped.filter((item) => item && typeof item === "object")
    : [];
  const warnings = Array.isArray(result?.warnings)
    ? result.warnings.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const parts = [
    added ? `Added ${formatCount(added, "Clean layer")}.` : "No new text was found.",
  ];
  if (skipped.length) {
    const reason = String(skipped[0]?.reason || "").trim();
    parts.push(`Skipped ${formatCount(skipped.length, "region")}${reason ? `: ${reason}` : "."}`);
  }
  if (!added) parts.push("Your current Clean layers are unchanged.");
  parts.push(...warnings);
  return {
    text: parts.join(" "),
    tone: added && !warnings.length ? "ok" : "",
    added,
    skipped: skipped.length,
    warnings,
  };
}

/** Never throw a raw 404: the panel asks for a Scan instead. */
export function autoCleanFailure(error) {
  const message = String(error?.message || "").trim();
  if (error?.status === 404 && /run scan footage first/i.test(message)) {
    return { text: SCAN_REQUIRED, tone: "bad", scan: true };
  }
  return {
    text: message || "Could not remove detected text.",
    tone: "bad",
    scan: false,
  };
}

function safeId(value) {
  return String(value || "")
    .replace(/[^A-Za-z0-9_-]/g, "_")
    .replace(/^[^A-Za-z]+/, "x")
    .slice(0, 50) || "region";
}

function actionKind(action) {
  const value = String(action || "").toLowerCase();
  if (value === "plate" || value === "cover") return "plate";
  if (value === "crop" || value === "crop_guard") return "crop_guard";
  if (value === "mask") return "mask";
  if (value === "blur") return "blur";
  if (value === "delogo" || value === "remove") return "delogo";
  return "blur";
}

function paddedBox(box, kind) {
  const source = box && typeof box === "object" ? box : { x: 0.08, y: 0.72, w: 0.84, h: 0.16 };
  const x = clamp(numberOr(source.x, 0.08), 0, 1);
  const y = clamp(numberOr(source.y, 0.72), 0, 1);
  const w = clamp(numberOr(source.w, 0.84), 0.002, 1 - x);
  const h = clamp(numberOr(source.h, 0.16), 0.002, 1 - y);
  if (kind === "crop_guard") {
    return { x: round(x, 4), y: round(y, 4), w: round(w, 4), h: round(h, 4) };
  }
  const padX = Math.min(0.012, (1 - w) / 2);
  const padY = Math.min(0.008, (1 - h) / 2);
  return {
    x: round(clamp(x - padX, 0, 1), 4),
    y: round(clamp(y - padY, 0, 1), 4),
    w: round(clamp(w + padX * 2, 0.002, 1 - clamp(x - padX, 0, 1)), 4),
    h: round(clamp(h + padY * 2, 0.002, 1 - clamp(y - padY, 0, 1)), 4),
  };
}

function rangeList(entry) {
  return Array.isArray(entry?.ranges)
    ? entry.ranges
      .filter((range) => Number.isFinite(Number(range?.start)) && Number.isFinite(Number(range?.end)))
      .filter((range) => Number(range.end) > Number(range.start))
      .map((range) => ({ start: round(Number(range.start)), end: round(Number(range.end)) }))
    : [];
}

function safeLabel(value, fallback) {
  const cleaned = String(value || "")
    .replace(/inpaint|generative|delogo|watermark|voice[\s_-]*clon\w*|avatar|stock[\s_-]*b-?roll/gi, "text")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return cleaned || fallback;
}

export function safeRadius(box, source) {
  const width = Math.max(1, numberOr(source?.width, 1920));
  const height = Math.max(1, numberOr(source?.height, 1080));
  const minPixels = Math.min(
    clamp(numberOr(box?.w, 0.2), 0.001, 1) * width,
    clamp(numberOr(box?.h, 0.2), 0.001, 1) * height,
  );
  return Math.max(2, Math.min(12, Math.floor(minPixels / 4) - 1));
}

function layerFromEntry(entry, tracklet, index, source) {
  const kind = actionKind(entry?.action);
  const text = String(tracklet?.text_sample || "").trim();
  const label = safeLabel(text, TRACKLET_LABELS[tracklet?.kind] || KIND_COPY[kind]);
  const box = paddedBox(entry?.box || tracklet?.box || {}, kind);
  return {
    id: `cl_${safeId(tracklet?.id || entry?.tracklet_id || index + 1)}`,
    kind,
    box,
    ranges: rangeList(entry?.ranges?.length ? entry : tracklet),
    z: index,
    color: "#000000",
    opacity: 1,
    radius: kind === "blur" ? safeRadius(box, source) : 12,
    label,
  };
}

export function maskStrokes(layer) {
  const mask = layer?.mask;
  if (!mask) return [];
  if (Array.isArray(mask)) {
    const points = mask.filter(Boolean);
    return points.length
      ? [{ id: "st_legacy", r: Number(points[0]?.r) || 0.025, points }]
      : [];
  }
  return Array.isArray(mask.strokes) ? mask.strokes.filter(Boolean) : [];
}

export function maskPointCount(layer) {
  return maskStrokes(layer).reduce((sum, stroke) => sum + (stroke.points || []).length, 0);
}

export function emptyMask(aspect = "9:16") {
  return { space: "source", aspect, strokes: [] };
}

/** Move a brush mask with its box, so the strokes stay where they were drawn. */
export function remapMask(layer, from, to) {
  const strokes = maskStrokes(layer);
  if (!strokes.length || !from || !to) return;
  if (!Array.isArray(layer.mask) && layer.mask.space !== "source") return;
  const scaleX = numberOr(to.w, 1) / Math.max(1e-6, numberOr(from.w, 1));
  const scaleY = numberOr(to.h, 1) / Math.max(1e-6, numberOr(from.h, 1));
  for (const stroke of strokes) {
    stroke.points = (stroke.points || []).map((point) => ({
      x: round(clamp(numberOr(to.x) + (numberOr(point.x) - numberOr(from.x)) * scaleX, 0, 1), 4),
      y: round(clamp(numberOr(to.y) + (numberOr(point.y) - numberOr(from.y)) * scaleY, 0, 1), 4),
    }));
  }
}

export function manualLayer(index, box = null) {
  const layer = {
    id: `cl_manual_${Date.now().toString(36)}`,
    kind: "blur",
    box: paddedBox(box, "blur"),
    ranges: [],
    z: index,
    color: "#000000",
    opacity: 1,
    radius: 12,
    label: "Drawn box",
  };
  return setLayerKind(layer, drawKind());
}

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
  const safe = /^#[0-9a-fA-F]{6}$/.test(String(value || "")) ? value : "#000000";
  return el("input", { type: "color", value: safe });
}

function warningNode(warning) {
  const severity = String(warning?.severity || "info").toLowerCase();
  return el("div", { class: "st-check-warning", dataset: { severity } }, [
    el("span", {
      class: `st-chip${severity === "blocker" ? " st-chip-bad" : severity === "warning" ? " st-chip-busy" : ""}`,
      text: severity === "blocker" ? "Blocked" : severity === "warning" ? "Warning" : "Note",
    }),
    el("p", { text: warning?.message || warning?.code || "Check reported an issue." }),
  ]);
}

function rangeSummary(ranges) {
  const rows = rangeList({ ranges });
  if (!rows.length) return "Whole story";
  const parts = rows.slice(0, 2).map((range) => formatSpan(range.start, range.end));
  if (rows.length > 2) parts.push(`+${rows.length - 2} more`);
  return parts.join(" · ");
}

const FOUND_TICKS = new Map();
// Open rows outlive a panel remount, which happens on every selection.
const OPEN_CLEAN_GROUPS = new Set();
let outsideOpen = false;

// The panel is rebuilt often; the estimate is only asked for when layers change.
let fillEstimateText = "";
let fillEstimateFor = "";
let foundAddedOpen = false;

export function mountCleanPanel(host, ctx) {
  ensureCheckStyles();
  const jobId = currentJobId();
  const edit = ctx.getEdit();
  let disposed = false;
  let report = null;
  let pending = false;
  let loadError = "";
  let timer = 0;
  let loading = true;
  let scanBusy = false;
  let policy = null;
  let policyError = "";
  let rightsBusy = false;
  let handleTicked = false;
  let focusedFound = "";
  let seekMissFound = "";
  let sceneOnly = false;
  const autoState = autoCleanStateFor(jobId);
  // P2 found-text list and AI fill preview.
  let fillStatus = null;
  let fillStatusError = "";
  let fillEstimateTimer = 0;
  let moreOpen = false;
  if (!FOUND_TICKS.has(jobId)) FOUND_TICKS.set(jobId, new Map());
  const foundTicks = FOUND_TICKS.get(jobId);

  host.replaceChildren(el("p", { class: "st-hint", text: "Reading Check findings…" }));

  function stopPoll() {
    if (timer) window.clearTimeout(timer);
    timer = 0;
  }

  function policyReady() {
    return Boolean(policy && typeof policy.lock === "boolean");
  }

  /** General old-caption cleaning. Watermarks and screen text are per-kind. */
  function canClean() {
    if (!policyReady()) return false;
    if (!policyLocked(policy)) return true;
    return Boolean(policy.attested);
  }

  function canCleanKind(kind) {
    return policyReady() && !cleanBlockReason(policy, kind);
  }

  function kindReason(kind) {
    return cleanBlockReason(policy, kind);
  }

  /** With the lock off, only a watermark, handle or logo still needs the tick. */
  function needsOwnTick() {
    return (report?.tracklets || []).some((tracklet) => (
      kindReason(String(tracklet?.kind || "")) === "attestation_required"
    ));
  }

  async function refreshPolicy() {
    if (!jobId) return;
    try {
      const loaded = await getJob(jobId);
      if (disposed) return;
      if (loaded?.rights_policy && typeof loaded.rights_policy === "object") {
        policy = loaded.rights_policy;
        policyError = "";
      }
    } catch (error) {
      if (!disposed) policyError = error?.message || "Could not read the rights policy.";
    }
  }

  async function recordRights() {
    if (!jobId || rightsBusy) return false;
    rightsBusy = true;
    render();
    try {
      await request(`/api/jobs/${encodeURIComponent(jobId)}/rights`, {
        method: "POST",
        // Existing rights route accepts "check"; the tick itself is per video.
        body: { attested: true, source: "check" },
      });
      await refreshPolicy();
      ctx.notify("Rights note recorded for this video.", "ok");
      return true;
    } catch (error) {
      ctx.notify(error?.message || "Could not record the rights note.", "bad");
      return false;
    } finally {
      rightsBusy = false;
      if (!disposed) render();
    }
  }

  function reasonText(kind, entry) {
    const code = kindReason(kind);
    if (code) return cleanReasonText(code, policy);
    return entry?.reason || "";
  }

  function rightsTick(label, copy, onTick) {
    const input = el("input", {
      type: "checkbox",
      checked: handleTicked,
      disabled: rightsBusy,
    });
    input.addEventListener("change", () => {
      handleTicked = Boolean(input.checked);
      if (!handleTicked) {
        render();
        return;
      }
      void onTick();
    });
    return el("label", { class: "st-check st-attest" }, [
      input,
      el("span", {}, [
        el("strong", { text: label }),
        el("small", { text: copy }),
      ]),
    ]);
  }

  function trackletById() {
    const map = new Map();
    for (const tracklet of report?.tracklets || []) {
      if (tracklet?.id) map.set(String(tracklet.id), tracklet);
    }
    return map;
  }

  function prefillByTracklet() {
    const map = new Map();
    for (const entry of report?.clean_prefill || []) {
      if (entry?.tracklet_id) map.set(String(entry.tracklet_id), entry);
    }
    return map;
  }

  function foundRows() {
    const current = ctx.getEdit()?.clean || [];
    const prefill = prefillByTracklet();
    const full = current.length >= MAX_CLEAN;
    const rows = [];
    for (const tracklet of mergeFoundTracklets(report?.tracklets)) {
      const id = String(tracklet.id);
      const kind = String(tracklet?.kind || "");
      const entry = prefill.get(id) || null;
      const reasonCode = kindReason(kind);
      const locked = Boolean(reasonCode);
      const added = tracklet.members.every((member) => (
        current.some((layer) => sameScanText(layer, member))
      ));
      let reason = reasonText(kind, entry);
      if (added) reason = "Already added to this moment.";
      else if (full) {
        reason = `This moment has ${MAX_CLEAN} text layers, the most it can hold.`;
      }
      const allowed = !locked
        && !added
        && !full
        && canCleanKind(kind);
      // Text likely in the scene, like a logo on a cup, starts unticked.
      const minor = tracklet.members.every((member) => member?.minor);
      const ticked = foundTicks.has(id) ? Boolean(foundTicks.get(id)) : allowed && !minor;
      rows.push({
        id,
        tracklet,
        kind,
        entry,
        box: tracklet?.box && typeof tracklet.box === "object" ? tracklet.box : null,
        text: tracklet.lines > 1
          ? `Subtitles · ${tracklet.lines} lines`
          : String(tracklet?.text_sample || "").trim() || "No words read",
        ranges: Array.isArray(tracklet?.ranges) ? tracklet.ranges : [],
        time: rangeSummary(tracklet?.ranges),
        reason,
        locked,
        added,
        allowed,
        ticked,
      });
    }
    return rows;
  }

  function tickedFoundRows() {
    return foundRows().filter((row) => row.allowed && row.ticked);
  }

  function setFoundTicked(id, value) {
    foundTicks.set(String(id), Boolean(value));
    render();
  }

  function setAllFoundTicked(value) {
    for (const row of foundRows()) {
      if (row.allowed) foundTicks.set(row.id, Boolean(value));
    }
    render();
  }

  /** Each line shows its own box on the preview, at its own time. */
  function pushFoundToPreview(rows) {
    if (!ctx.setFoundText) return;
    ctx.setFoundText(
      rows
        .filter((row) => !row.added)
        .flatMap((row) => row.tracklet.members
          .filter((member) => member?.box)
          .map((member) => ({
            id: String(member.id),
            box: { ...member.box },
            ranges: Array.isArray(member.ranges) ? member.ranges : [],
            text: String(member.text_sample || row.text),
            kind: row.kind,
            ticked: row.ticked,
          }))),
    );
  }

  function syncCleanTab(count) {
    const tab = document.querySelector('.st-inspector-tab[data-tab="clean"]');
    if (!tab) return;
    let badge = tab.querySelector(".st-tab-count");
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("small");
        badge.className = "st-tab-count";
        tab.append(badge);
      }
      badge.textContent = String(count);
    } else if (badge) {
      badge.remove();
    }
  }

  async function runAutoClean() {
    if (autoState.busy) return;
    const activeJob = currentJobId() || jobId;
    const currentEdit = ctx.getEdit();
    if (!activeJob || !currentEdit?.id) {
      autoState.notice = {
        text: "Open an Edit to remove detected text.",
        tone: "bad",
        scan: false,
      };
      render();
      return;
    }
    const ticked = tickedFoundRows();
    if (!ticked.length) {
      autoState.notice = {
        text: "Tick at least one found text region first.",
        tone: "bad",
        scan: false,
      };
      render();
      return;
    }
    if (drawKind() === "fill" && !fillReady(drawEngine())) {
      autoState.notice = {
        text: fillStatusError || "The AI fill model is not available. Choose Blur.",
        tone: "bad",
        scan: false,
      };
      render();
      return;
    }
    autoState.busy = true;
    autoState.notice = null;
    render();
    try {
      const result = await autoCleanRequest(activeJob, currentEdit.id, {
        tracklet_ids: ticked.flatMap((row) => row.tracklet.ids),
        method: drawKind() === "fill" ? "ai" : "blur",
        fill_method: drawEngine(),
      });
      if (disposed) {
        autoState.busy = false;
        return;
      }
      const widened = clone(ctx.getEdit()?.clean || []);
      for (const change of Array.isArray(result?.updated) ? result.updated : []) {
        const layer = widened.find((item) => item.id === change.id);
        if (layer) layer.ranges = change.ranges;
      }
      const merged = mergeAutoCleanLayers(widened, result?.layers);
      const first = merged.added[0]?.id || "";
      for (const layer of merged.added) {
        if (layer.tracklet_id) foundTicks.delete(String(layer.tracklet_id));
      }
      if (merged.added.length || result?.updated?.length) ctx.setClean(merged.layers);
      const summary = autoCleanSummary({
        ...(result && typeof result === "object" ? result : {}),
        added: merged.added.length,
        skipped: [
          ...(Array.isArray(result?.skipped) ? result.skipped : []),
          ...merged.skipped,
        ],
      });
      autoState.busy = false;
      autoState.notice = { text: summary.text, tone: summary.tone, scan: false };
      if (first) ctx.select("clean", first);
      else ctx.refresh();
    } catch (error) {
      if (disposed) {
        autoState.busy = false;
        return;
      }
      autoState.busy = false;
      autoState.notice = autoCleanFailure(error);
      ctx.refresh();
    }
  }

  function scanState() {
    const status = String(report?.status || "").toLowerCase();
    if (pending || status === "queued" || status === "running") return "running";
    if (!report) return "missing";
    if (status === "cancelled") return "cancelled";
    if (status === "failed") return "failed";
    if (report.text?.confirmed !== true) return "unconfirmed";
    return "ready";
  }

  function scanPercent() {
    return Math.max(0, Math.min(100, Math.round(numberOr(report?.progress, 0) * 100)));
  }

  async function startTextScan({ scene = false } = {}) {
    if (!jobId || scanBusy || pending) return;
    const range = scene ? ctx.getSceneRange?.() : null;
    const scoped = Boolean(range && Number(range.end) > Number(range.start));
    scanBusy = true;
    loadError = "";
    sceneOnly = scoped;
    render();
    try {
      const next = await request(`/api/jobs/${encodeURIComponent(jobId)}/check`, {
        method: "POST",
        body: {
          force: true,
          sample_text: true,
          ...(scoped ? { start: Number(range.start), end: Number(range.end) } : {}),
        },
      });
      if (disposed) return;
      const status = String(next?.status || "").toLowerCase();
      report = next || null;
      pending = status === "queued" || status === "running" || next?.complete === false;
      loading = false;
      scanBusy = false;
      render();
      if (pending) {
        stopPoll();
        timer = window.setTimeout(() => { void load(); }, CHECK_POLL_MS);
      }
    } catch (error) {
      if (disposed) return;
      scanBusy = false;
      loadError = error?.message || "Could not start the text scan.";
      render();
    }
  }

  async function cancelTextScan() {
    if (!jobId || scanBusy) return;
    scanBusy = true;
    render();
    try {
      await request(`/api/jobs/${encodeURIComponent(jobId)}/check/cancel`, {
        method: "POST",
        body: {},
      });
      await load();
    } catch (error) {
      if (!disposed) loadError = error?.message || "Could not cancel the text scan.";
    } finally {
      scanBusy = false;
      if (!disposed) render();
    }
  }

  function scanButton(label = "Find text on screen", { primary = true, quiet = false } = {}) {
    const button = el("button", {
      class: `st-btn st-btn-small ${primary ? "st-btn-primary" : "st-btn-ghost"}${quiet ? " st-btn-quiet" : ""} st-clean-scan-start`,
      type: "button",
      text: scanBusy ? "Starting the scan…" : label,
      disabled: scanBusy || pending,
    });
    button.addEventListener("click", () => { void startTextScan(); });
    return button;
  }

  function scanProgressRow() {
    const row = el("div", { class: "st-clean-scan is-running", role: "status" }, [
      el("div", { class: "st-clean-scan-head" }, [
        el("strong", { text: "Finding text on screen" }),
        el("span", { class: "st-mono", text: `${scanPercent()}%` }),
      ]),
      el("progress", {
        class: "st-clean-progress",
        max: "100",
        value: String(scanPercent()),
        "aria-label": "Text scan progress",
      }),
      el("p", { class: "st-hint", text: report?.message || "Reading frames for burned-in text…" }),
    ]);
    const cancel = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: scanBusy ? "Stopping…" : "Cancel scan",
      disabled: scanBusy,
    });
    cancel.addEventListener("click", () => { void cancelTextScan(); });
    row.append(cancel);
    return row;
  }

  function scanPrompt(state) {
    const copy = {
      missing: "Find the text burned into this video, then choose what to remove.",
      cancelled: "The last text scan was cancelled, so no text has been found yet. Run it again.",
      failed: "The last text scan failed. Try it again; your layers are unchanged.",
      unconfirmed: "The text pass did not finish, so an empty result is unconfirmed. Run it again.",
      empty: "No on-screen text was found in the last scan. Scan again if the video changed.",
    }[state] || "Find on-screen text before removing it.";
    const row = el("div", { class: "st-clean-scan" }, [
      el("p", { class: "st-hint", text: copy }),
    ]);
    if (state === "failed" && report?.error) {
      row.append(el("p", { class: "st-error", text: String(report.error) }));
    }
    const scanScene = el("button", {
      class: "st-btn st-btn-primary st-btn-small st-clean-scan-start",
      type: "button",
      text: "Check this scene",
      disabled: scanBusy || pending,
    });
    scanScene.addEventListener("click", () => { void startTextScan({ scene: true }); });
    const scanVideo = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-clean-scan-start",
      type: "button",
      text: "Scan video",
      disabled: scanBusy || pending,
    });
    scanVideo.addEventListener("click", () => { void startTextScan(); });
    row.append(el("div", { class: "st-clean-scan-actions" }, [scanScene, scanVideo]));
    return row;
  }

  function scanToolbar() {
    const status = scanState();
    if (status === "running") return scanProgressRow();
    if (status === "missing" || status === "cancelled" || status === "failed" || status === "unconfirmed") {
      return scanPrompt(status);
    }
    if (!(report?.tracklets || []).length) return scanPrompt("empty");
    return null;
  }

  /** The one choice that applies to everything added here, and the ways to add by hand. */
  function methodBar() {
    const current = drawKind();
    const switcher = el("div", { class: "st-method-switch st-clean-method", role: "group", "aria-label": "Remove text with" });
    for (const value of KIND_ORDER) {
      const locked = value === "fill" && !isFillAvailable();
      const on = current === value;
      const button = el("button", {
        class: `st-method-option${on ? " is-active" : ""}`,
        type: "button",
        text: KIND_COPY[value],
        "aria-pressed": on ? "true" : "false",
        disabled: locked,
        title: locked ? (fillStatusError || "AI fill needs its model in the fill models folder.") : "",
      });
      button.addEventListener("click", () => {
        rememberDrawKind(value);
        render();
      });
      switcher.append(button);
    }
    const layers = ctx.getEdit()?.clean || [];
    const full = layers.length >= MAX_CLEAN;
    const addBox = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-clean-add-box",
      type: "button",
      disabled: !canClean() || full,
      title: full ? `A story supports ${MAX_CLEAN} clean layers.` : "Add a box at the playhead, for three seconds",
    }, [icon("square", { size: 13 }), "Add box"]);
    addBox.addEventListener("click", () => { ctx.addBox?.(drawKind()); });
    const paint = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-clean-add-paint",
      type: "button",
      disabled: !canClean() || full || !isFillAvailable(),
      title: "Brush over text at the playhead, for three seconds. Always AI fill.",
    }, [icon("brush", { size: 13 }), "Paint"]);
    paint.addEventListener("click", () => { ctx.addPaint?.(); });
    return el("div", { class: "st-clean-bar" }, [
      el("span", { class: "st-clean-bar-label", text: "Remove with" }),
      switcher,
      el("div", { class: "st-clean-add" }, [addBox, paint]),
    ]);
  }

  function runBar(rows) {
    const running = Boolean(autoState.busy);
    const editId = ctx.getEdit()?.id || "";
    const ticked = rows.filter((row) => row.allowed && row.ticked);
    const button = el("button", {
      class: "st-btn st-btn-primary st-btn-small st-auto-clean-run",
      type: "button",
      text: running ? "Cleaning…" : ticked.length ? `Clean ${ticked.length}` : "Clean",
      disabled: running || !editId || !ticked.length,
      "aria-busy": running ? "true" : "false",
      title: !editId
        ? "Open an Edit to remove detected text."
        : !ticked.length ? "Tick the text to clean." : "",
    });
    button.addEventListener("click", () => { void runAutoClean(); });
    const wrap = el("div", { class: "st-found-actions st-clean-toolbar" }, [button]);
    if (drawKind() === "blur" && ticked.some((row) => row.entry?.quality_warning)) {
      wrap.append(el("p", {
        class: "st-found-note",
        text: "Some of this text crosses the middle of the frame. Blur may leave it readable; AI fill removes it.",
      }));
    }
    return wrap;
  }

  /** Whole video or this scene: only filters the list, unless no scan covers it. */
  function scopeSwitch() {
    const thisScene = el("button", {
      class: `st-method-option st-clean-scope-scene${sceneOnly ? " is-active" : ""}`,
      type: "button",
      text: "This scene",
      "aria-pressed": sceneOnly ? "true" : "false",
    });
    thisScene.addEventListener("click", () => {
      sceneOnly = true;
      // A whole-video scan already covers this scene, so only filter it.
      if (!report?.scope || reportMatchesScene(ctx.getSceneRange?.())) { render(); return; }
      void startTextScan({ scene: true });
    });
    const video = el("button", {
      class: `st-method-option st-clean-scope-video${sceneOnly ? "" : " is-active"}`,
      type: "button",
      text: "Whole video",
      "aria-pressed": sceneOnly ? "false" : "true",
    });
    video.addEventListener("click", () => {
      sceneOnly = false;
      if (report?.scope) { void startTextScan(); return; }
      render();
    });
    const again = el("button", {
      class: "st-btn st-btn-quiet st-btn-small st-clean-rescan",
      type: "button",
      text: "Scan again",
      disabled: scanBusy || pending,
    });
    again.addEventListener("click", () => { void startTextScan({ scene: sceneOnly }); });
    return el("div", { class: "st-clean-scope" }, [
      el("div", { class: "st-method-switch", role: "group", "aria-label": "Show text from" }, [thisScene, video]),
      again,
    ]);
  }

  function autoCleanStatusNode() {
    const notice = autoState.notice;
    if (!notice?.text) return null;
    const row = el("div", {
      class: "st-auto-clean-status",
      role: "status",
      dataset: { tone: notice.tone || "" },
      style: "margin-top:7px",
    }, [
      el("p", {
        class: notice.tone === "bad" ? "st-error" : "st-hint",
        text: notice.text,
      }),
    ]);
    if (notice.scan) {
      row.append(el("div", { class: "st-clean-scan-actions" }, [
        scanButton("Find text on screen"),
        el("a", {
          class: "st-btn st-btn-ghost st-btn-small",
          href: "#/check",
          text: "Open Check",
        }),
      ]));
    }
    return row;
  }

  function renderRights() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Rights" }));
    if (!policy) {
      card.append(el("p", {
        class: "st-hint",
        text: policyError || "Reading the rights policy…",
      }));
      return card;
    }
    if (!policyLocked(policy)) {
      if (needsOwnTick()) {
        card.append(rightsTick(
          "This video is mine.",
          "A watermark, handle or logo needs this tick for each video.",
          recordRights,
        ));
        return card;
      }
      return null;
    }
    if (policy.attested) return null;
    card.append(el("p", {
      class: "st-hint",
      text: "The rights lock is on. Confirm the box to clean old text; you can still add your own text and captions.",
    }));
    card.append(rightsTick(
      "I own this footage or have the rights to it.",
      "Stored on the server for this video.",
      recordRights,
    ));
    card.append(el("a", { class: "st-btn st-btn-ghost st-btn-small", href: "#/check", text: "Record rights in Check" }));
    return card;
  }

  function renderWarnings() {
    const warnings = [];
    const seen = new Set();
    for (const warning of report?.warnings || []) {
      const key = `${warning?.code}:${warning?.message}`;
      if (!seen.has(key)) {
        warnings.push(warning);
        seen.add(key);
      }
    }
    for (const issue of report?.quality?.issues || []) {
      const key = `${issue?.code}:${issue?.message}`;
      if (!seen.has(key)) {
        warnings.push(issue);
        seen.add(key);
      }
    }
    const midFrame = (report?.clean_prefill || []).find((entry) => entry?.quality_warning);
    if (midFrame) {
      warnings.push({
        severity: "warning",
        message: "Burned-in text crosses the middle of the frame. Check the rendered patch at 1×.",
      });
    }
    if (!warnings.length) return null;
    return el("p", {
      class: "st-clean-alert",
      text: warnings.length === 1 ? warnings[0].message : `${warnings.length} quality warnings`,
      title: warnings.map((item) => item.message).filter(Boolean).join("\n"),
    });
  }

  function foundRowNode(row) {
    const checkbox = el("input", {
      type: "checkbox",
      class: "st-found-tick",
      checked: row.ticked,
      disabled: !row.allowed,
      "aria-label": `Clean ${row.text}`,
    });
    checkbox.addEventListener("change", () => {
      setFoundTicked(row.id, checkbox.checked);
    });
    const copy = el("div", { class: "st-found-copy" }, [
      el("div", { class: "st-found-line" }, [
        el("strong", { text: row.text }),
      ]),
      el("small", {
        class: "st-found-meta",
        text: seekMissFound === String(row.id) ? "Not in this cut" : row.time,
      }),
    ]);
    const node = el("div", {
      class: `st-found-row${row.ticked ? " is-ticked" : ""}${row.added ? " is-added" : ""}`,
      role: "listitem",
      tabindex: "0",
      title: row.reason || "",
      dataset: { id: row.id, kind: row.kind, reason: row.reason || "" },
    }, [checkbox, copy]);
    const activate = () => {
      const at = row.ranges?.[0]?.start ?? row.tracklet?.ranges?.[0]?.start;
      const seek = typeof ctx.seekSource === "function" ? ctx.seekSource(at) : false;
      seekMissFound = seek === false ? row.id : "";
      ctx.focusFound?.(row.id);
      render();
    };
    node.addEventListener("click", (event) => {
      if (event.target.closest("input")) return;
      activate();
    });
    node.addEventListener("keydown", (event) => {
      if (event.target.closest("input")) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
    return node;
  }

  function reportMatchesScene(range) {
    const scope = report?.scope;
    if (!range || !scope) return false;
    return Math.abs(Number(scope.start) - Number(range.start)) < 0.05
      && Math.abs(Number(scope.end) - Number(range.end)) < 0.05;
  }

  function sceneFiltered(rows) {
    if (!sceneOnly) return rows;
    const range = ctx.getSceneRange?.();
    if (!range) return rows;
    return rows.filter((row) => {
      const ranges = Array.isArray(row.ranges) && row.ranges.length
        ? row.ranges
        : (row.tracklet?.ranges || []);
      if (!ranges.length) return true;
      return ranges.some((item) => Number(item.end) > range.start && Number(item.start) < range.end);
    });
  }

  function suggestionsCard() {
    const scan = scanState();
    const rows = scan === "ready" ? sceneFiltered(foundRows()) : [];
    pushFoundToPreview(rows);
    if (scan !== "ready" || !(report?.tracklets || []).length) return null;
    const allowed = rows.filter((row) => row.allowed);
    const allTicked = allowed.length > 0 && allowed.every((row) => row.ticked);
    const card = el("div", { class: "st-found-card" });
    const toggle = allowed.length ? el("button", {
      class: "st-btn st-btn-quiet st-btn-small st-found-select-all",
      type: "button",
      text: allTicked ? "Clear" : "Select all",
    }) : null;
    if (toggle) {
      toggle.addEventListener("click", () => setAllFoundTicked(!allTicked));
    }
    card.append(el("div", { class: "st-found-head" }, [
      el("div", { class: "st-found-heading" }, [
        el("strong", { text: "Found on screen" }),
        el("span", { text: String(rows.length) }),
      ]),
      toggle,
    ]));
    card.append(scopeSwitch());
    const list = el("div", { class: "st-found-list", role: "list" });
    // Text that already has a layer folds away, so the list holds what is left.
    const waiting = rows.filter((row) => !row.added);
    const added = rows.filter((row) => row.added);
    for (const row of waiting.slice(0, 40)) list.append(foundRowNode(row));
    if (waiting.length) card.append(list);
    else if (!added.length) card.append(el("p", { class: "st-hint", text: "No text found in this scene." }));
    if (added.length) {
      const fold = el("details", { class: "st-found-added", open: foundAddedOpen }, [
        el("summary", { text: `${added.length} already added` }),
      ]);
      fold.addEventListener("toggle", () => { foundAddedOpen = fold.open; });
      const addedList = el("div", { class: "st-found-list", role: "list" });
      for (const row of added.slice(0, 40)) addedList.append(foundRowNode(row));
      fold.append(addedList);
      card.append(fold);
    }
    if (waiting.length > 40) {
      card.append(el("p", { class: "st-hint", text: `Showing 40 of ${waiting.length}.` }));
    }
    if (waiting.length) card.append(runBar(rows));
    const status = autoCleanStatusNode();
    if (status) card.append(status);
    return card;
  }

  /** Two clicks, since it takes every layer of this moment at once. Undo restores them. */
  function deleteAllButton() {
    const label = "Delete all";
    const button = el("button", {
      class: "st-btn st-btn-quiet st-btn-small st-danger st-clean-delete-all",
      type: "button",
      text: label,
    });
    let armed = false;
    button.addEventListener("click", () => {
      if (!armed) {
        armed = true;
        button.textContent = "Click again to delete all";
        return;
      }
      ctx.setClean([]);
      ctx.select("clean", "");
    });
    button.addEventListener("blur", () => {
      armed = false;
      button.textContent = label;
    });
    return button;
  }

  function existingCard(selectedId) {
    const layers = ctx.getEdit()?.clean || [];
    const card = el("div", { class: "st-clean-layers" });
    card.append(el("div", { class: "st-clean-layers-head" }, [
      el("strong", { text: "Clean layers" }),
      el("span", { text: String(layers.length) }),
      layers.length > 1 ? deleteAllButton() : null,
    ]));
    if (!layers.length) {
      card.append(el("p", { class: "st-hint", text: "Nothing cleaned yet." }));
    } else {
      const inside = layers.filter((layer) => ctx.isOutsideStory?.(layer) !== true);
      const outside = layers.filter((layer) => ctx.isOutsideStory?.(layer) === true);
      const list = el("div", { class: "st-layer-list", role: "list" });
      for (const group of cleanGroups(inside)) list.append(groupRow(group, selectedId));
      card.append(list);
      if (outside.length) {
        const fold = el("details", { class: "st-clean-outside", open: outsideOpen }, [
          el("summary", { text: `${formatCount(outside.length, "layer")} outside this moment. Kept, not deleted.` }),
        ]);
        fold.addEventListener("toggle", () => { outsideOpen = fold.open; });
        const hidden = el("div", { class: "st-layer-list", role: "list" });
        for (const group of cleanGroups(outside)) hidden.append(groupRow(group, selectedId));
        fold.append(hidden);
        card.append(fold);
      }
    }
    const cost = el("p", { class: "st-field-hint st-fill-estimate", text: fillEstimateText, hidden: !fillEstimateText });
    card.append(cost);
    scheduleFillEstimate(cost);
    if (!canClean()) {
      card.append(el("p", {
        class: "st-hint",
        text: policy
          ? "Adding is locked by the server rights policy. Record the rights note above, or in Check, to unlock it."
          : (policyError || "Reading the rights policy…"),
      }));
    }
    return card;
  }

  /** The engine is one choice for the whole Edit, kept out of the way. */
  function engineFold() {
    const ready = Object.entries(fillStatus?.methods || {}).filter(([, value]) => value?.ready);
    if (ready.length < 2) return null;
    const engine = el("select", { class: "st-found-engine", "aria-label": "AI fill engine", disabled: !canClean() });
    for (const [value, text] of FILL_METHODS) {
      if (!ready.some(([id]) => id === value)) continue;
      engine.append(el("option", { value, text, selected: value === drawEngine() }));
    }
    engine.addEventListener("change", () => {
      rememberEngine(engine.value);
      ctx.setClean((ctx.getEdit()?.clean || []).map((layer) => (
        layer.kind === "fill" ? { ...layer, method: engine.value } : layer
      )));
      ctx.refresh?.();
    });
    const fold = el("details", { class: "st-clean-more", open: moreOpen }, [
      el("summary", { text: "AI engine" }),
      engine,
    ]);
    fold.addEventListener("toggle", () => { moreOpen = fold.open; });
    return fold;
  }

  /** How long the render will take for these layers. Asks only when they change. */
  function scheduleFillEstimate(node) {
    const current = ctx.getEdit();
    if (!current?.id || !jobId) return;
    const clean = current.clean || [];
    const signature = JSON.stringify([current.id, clean]);
    if (signature === fillEstimateFor) return;
    fillEstimateFor = signature;
    window.clearTimeout(fillEstimateTimer);
    fillEstimateTimer = window.setTimeout(async () => {
      try {
        const result = await request(
          `/api/jobs/${encodeURIComponent(jobId)}/edits/${encodeURIComponent(current.id)}/fill-estimate`,
          { method: "POST", body: { clean } },
        );
        if (disposed || signature !== fillEstimateFor) return;
        fillEstimateText = String(result?.text || "");
      } catch (_) {
        if (disposed || signature !== fillEstimateFor) return;
        fillEstimateText = "";
      }
      const live = host.querySelector(".st-fill-estimate") || node;
      live.textContent = fillEstimateText;
      live.hidden = !fillEstimateText;
    }, 500);
  }

  /** AI fill or Blur for this box, or for every piece of a grouped row. */
  function methodSwitch(target) {
    const layers = Array.isArray(target) ? target : [target];
    const wrap = el("div", { class: "st-method-switch", role: "group", "aria-label": "Clean method for this box" });
    for (const value of KIND_ORDER) {
      const locked = value === "fill" && !isFillAvailable();
      const on = layers.every((layer) => layer.kind === value);
      const button = el("button", {
        class: `st-method-option${on ? " is-active" : ""}`,
        type: "button",
        text: KIND_COPY[value],
        "aria-pressed": on ? "true" : "false",
        disabled: !canClean() || locked,
        title: locked ? (fillStatusError || "AI fill needs its model in the fill models folder.") : "",
      });
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        for (const layer of layers) ctx.setCleanMethod?.(layer.id, value);
      });
      wrap.append(button);
    }
    return wrap;
  }

  function layerRow(layer, selectedId, name, meta) {
    const active = selectedId === layer.id;
    const hiddenByCrop = ctx.isHiddenByCrop?.(layer) === true;
    const row = el("button", {
      class: `st-layer-row${active ? " is-active" : ""}`,
      type: "button",
      role: "listitem",
      "aria-pressed": active ? "true" : "false",
      dataset: { kind: "clean", layer: layer.id, box: JSON.stringify(layer.box || {}) },
    }, [
      el("span", { class: "st-layer-name", text: name || layer.label || KIND_COPY[layer.kind] || "Clean" }),
      el("small", { class: "st-layer-meta", text: meta ?? rangeSummary(layer.ranges) }),
      hiddenByCrop ? el("span", { class: "st-layer-hidden-note", text: "Hidden by crop" }) : null,
    ]);
    row.addEventListener("click", () => ctx.select("clean", layer.id));
    return row;
  }

  /** One text, or all the lines of the subtitles: a row, with its lines folded inside. */
  function groupRow(group, selectedId) {
    const first = group.layers[0];
    const wrap = el("div", { class: "st-clean-group" });
    const head = el("div", { class: "st-clean-row" });
    const many = group.layers.length > 1;
    const hasSelected = group.layers.some((layer) => layer.id === selectedId);
    const open = many && (OPEN_CLEAN_GROUPS.has(group.key) || hasSelected);
    if (many) {
      const toggle = el("button", {
        class: "st-clean-group-toggle",
        type: "button",
        title: open ? "Fold the lines" : "Show the lines",
        "aria-label": `${open ? "Fold" : "Show"} the lines of ${first.label || "this text"}`,
        "aria-expanded": open ? "true" : "false",
      }, [icon(open ? "chevron-down" : "chevron-right", { size: 14 })]);
      toggle.addEventListener("click", () => {
        if (OPEN_CLEAN_GROUPS.has(group.key)) OPEN_CLEAN_GROUPS.delete(group.key);
        else OPEN_CLEAN_GROUPS.add(group.key);
        render();
      });
      head.append(toggle);
    }
    const method = group.layers.every((layer) => layer.kind === first.kind)
      ? (KIND_COPY[first.kind] || "Clean") : "Mixed";
    const ranges = group.layers.flatMap((layer) => (Array.isArray(layer.ranges) ? layer.ranges : []));
    const time = ranges.length ? rangeSummary([{
      start: Math.min(...ranges.map((range) => numberOr(range.start))),
      end: Math.max(...ranges.map((range) => numberOr(range.end))),
    }]) : "Whole moment";
    const subtitles = many && group.layers.every((layer) => layer.tracklet_kind === "subtitle");
    head.append(layerRow(
      first,
      many ? "" : selectedId,
      many ? `${subtitles ? "Subtitles" : first.label || "Text"} · ${group.layers.length} lines` : "",
      `${time} · ${method}`,
    ));
    const remove = el("button", {
      class: "st-icon-btn st-icon-small",
      type: "button",
      title: many ? "Delete these lines" : "Delete this layer",
      "aria-label": `Delete ${first.label || "this layer"}`,
    }, [icon("trash", { size: 14 })]);
    remove.addEventListener("click", () => {
      const gone = new Set(group.layers.map((layer) => layer.id));
      ctx.setClean((ctx.getEdit()?.clean || []).filter((layer) => !gone.has(layer.id)));
      if (gone.has(selectedId)) ctx.select("clean", "");
      else ctx.refresh?.();
    });
    head.append(remove);
    wrap.append(head);
    const selected = group.layers.find((layer) => layer.id === selectedId) || null;
    if (open) {
      const inside = el("div", { class: "st-clean-pieces" });
      for (const layer of group.layers) {
        inside.append(layerRow(layer, selectedId, layer.label, rangeSummary(layer.ranges)));
        if (layer === selected) inside.append(editorCard(selected, group));
      }
      wrap.append(inside);
    } else if (selected) {
      wrap.append(editorCard(selected, group));
    }
    return wrap;
  }

  /** The selected box: how it is removed, and when. Its place is set on the video. */
  function editorCard(selected, group) {
    const layer = clone(selected);
    const stage = el("div", { class: "st-clean-editor" });
    const many = group.layers.length > 1;

    stage.append(methodSwitch(group.layers));
    if (many) stage.append(el("small", { class: "st-field-hint", text: `Applies to all ${group.layers.length} lines.` }));
    if (!KIND_ORDER.includes(layer.kind)) {
      stage.append(el("p", {
        class: "st-found-note",
        text: `This is an old ${KIND_COPY[layer.kind] || layer.kind} layer. Switch it to AI fill or Blur to change it.`,
      }));
    }

    const ranges = Array.isArray(layer.ranges) ? layer.ranges : [];
    if (!ranges.length) stage.append(el("p", { class: "st-hint", text: "On for the whole moment." }));
    ranges.forEach((range) => {
      const start = numberInput(range.start, { min: 0, max: 100000, step: 0.1 });
      const end = numberInput(range.end, { min: 0, max: 100000, step: 0.1 });
      start.disabled = !canClean();
      end.disabled = !canClean();
      start.addEventListener("change", () => {
        range.start = round(clamp(numberOr(start.value), 0, 100000));
        if (range.end <= range.start) range.end = round(range.start + 0.1);
        commit();
        ctx.refresh();
      });
      end.addEventListener("change", () => {
        range.end = round(clamp(numberOr(end.value), range.start + 0.01, 100000));
        commit();
        ctx.refresh();
      });
      const remove = ranges.length > 1 ? el("button", {
        class: "st-icon-btn st-icon-small",
        type: "button",
        "aria-label": "Delete this time",
        disabled: !canClean(),
      }, [icon("x", { size: 14 })]) : null;
      remove?.addEventListener("click", () => {
        layer.ranges = ranges.filter((item) => item !== range);
        commit();
        ctx.refresh();
      });
      stage.append(el("div", { class: "st-clean-times" }, [
        field("From (s)", start),
        field("To (s)", end),
        remove,
      ]));
    });

    if (layer.kind === "blur") {
      const cap = safeRadius(layer.box, report?.source);
      const radius = numberInput(Math.min(numberOr(layer.radius, cap), cap), { min: 2, max: cap, step: 1 });
      radius.disabled = !canClean();
      radius.addEventListener("change", () => {
        layer.radius = Math.round(clamp(numberOr(radius.value), 2, cap));
        commit();
      });
      stage.append(el("div", { class: "st-clean-times" }, [field(`Blur strength (2–${cap})`, radius)]));
    }

    if (layer.kind === "fill") {
      const maskPoints = maskStrokes(layer);
      const actions = el("div", { class: "st-clean-actions" });
      const paint = el("button", {
        class: "st-btn st-btn-ghost st-btn-small",
        type: "button",
        text: maskPoints.length ? `Paint more (${maskPointCount(layer)})` : "Paint",
        disabled: !canClean(),
      });
      paint.addEventListener("click", () => { ctx.startPaint?.(layer.id); });
      actions.append(paint);
      if (maskPoints.length) {
        const clear = el("button", {
          class: "st-btn st-btn-quiet st-btn-small",
          type: "button",
          text: "Clear paint",
          disabled: !canClean(),
        });
        clear.addEventListener("click", () => {
          layer.mask = emptyMask(ctx.getAspect?.() || "9:16");
          commit();
          ctx.refresh();
        });
        actions.append(clear);
      }
      const compare = el("button", {
        class: "st-btn st-btn-ghost st-btn-small st-clean-compare",
        type: "button",
        text: "Before / After",
        title: "One frame, without saving. STTN shows LaMa here; the render uses the Edit's engine.",
      });
      compare.addEventListener("click", () => ctx.compareLayer?.(layer.id));
      const testing = ctx.isFillTesting?.() === true;
      const test = el("button", {
        class: "st-btn st-btn-ghost st-btn-small st-clean-test",
        type: "button",
        text: testing ? "Cancel test" : "Test 1 second",
        "aria-busy": testing ? "true" : "false",
        title: "Run the real engine on about a second, without saving. It can take a few minutes.",
      });
      test.addEventListener("click", () => ctx.testLayer?.(layer.id));
      actions.append(compare, test);
      stage.append(actions);
    }

    function commit() {
      const layers = (ctx.getEdit()?.clean || []).map((item) => (
        item.id === layer.id ? clone(layer) : item
      ));
      ctx.setClean(layers);
    }

    return stage;
  }

  function render() {
    const scrollTop = host.scrollTop;
    host.replaceChildren();
    const selectedId = ctx.getSelectedId("clean");

    const head = el("div", { class: "st-clean-status" });
    const scan = scanToolbar();
    if (scan) head.append(scan);
    const rights = renderRights();
    if (rights) head.append(rights);
    const warnings = renderWarnings();
    if (warnings) head.append(warnings);
    if (loadError) head.append(el("p", { class: "st-error", text: loadError }));
    if (head.childElementCount) host.append(head);

    host.append(methodBar());
    const found = suggestionsCard();
    if (found) host.append(found);
    host.append(existingCard(selectedId));
    const more = engineFold();
    if (more) host.append(more);

    if (!canClean() && report) {
      host.append(el("p", {
        class: "st-layer-note",
        text: policy
          ? "Clean is locked by the server rights policy."
          : (policyError || "Reading the rights policy…"),
      }));
    }
    host.scrollTop = scrollTop;
  }

  function fillReady(method) {
    return Boolean(fillStatus?.methods?.[method]?.ready);
  }

  function firstFillMethod() {
    const methods = fillStatus?.methods || {};
    if (fillStatus?.default && methods[fillStatus.default]?.ready) return fillStatus.default;
    return ["lama", "sttn"].find((method) => methods[method]?.ready) || "";
  }

  async function loadFillStatus() {
    try {
      const status = await request("/api/fill/status");
      if (disposed) return;
      fillStatus = status && typeof status === "object" ? status : null;
      fillStatusError = "";
      const first = firstFillMethod();
      setFillAvailable(Boolean(first));
      if (first && !fillReady(drawEngine())) rememberEngine(first);
      render();
    } catch (error) {
      if (disposed) return;
      fillStatusError = error?.message || "Could not check the AI fill models.";
      render();
    }
  }

  async function loadPolicy() {    if (!jobId) return;
    try {
      const loaded = await getJob(jobId);
      if (disposed) return;
      policy = loaded?.rights_policy && typeof loaded.rights_policy === "object"
        ? loaded.rights_policy
        : null;
      if (!policy) {
        const fallback = await request("/api/rights/policy").catch(() => null);
        if (fallback && typeof fallback === "object") policy = fallback;
      }
      policyError = "";
    } catch (error) {
      if (!disposed) policyError = error?.message || "Could not read the rights policy.";
    }
  }

  async function load() {
    if (!jobId) {
      loading = false;
      loadError = "This panel could not read the open video. Reopen the story from Stories.";
      render();
      return;
    }
    try {
      if (!policy && !policyError) await loadPolicy();
      const result = await fetchCheck(jobId);
      if (disposed) return;
      report = result.report;
      pending = Boolean(result.pending);
      loading = false;
      loadError = "";
      if (disposed) return;
      render();
      if (pending) {
        timer = window.setTimeout(() => { void load(); }, CHECK_POLL_MS);
      }
    } catch (error) {
      if (disposed) return;
      loading = false;
      loadError = error?.message || "Could not read Check findings.";
      render();
    }
  }

  void loadFillStatus();
  void load();

  return () => {
    disposed = true;
    stopPoll();
  };
}
