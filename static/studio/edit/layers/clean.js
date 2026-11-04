/**
 * Clean layer controls.
 *
 * Check findings become Clean layers in the same Edit document. Boxes and
 * ranges use source coordinates and source time, exactly as the renderer
 * expects; the panel never converts them to output space.
 *
 * Adding is gated by the server policy on the job (`job.rights_policy`).
 * A watermark tracklet is never offered, screen text is never cleaned, and a
 * handle or logo under a lock-off policy needs its own "this is mine" tick.
 * The browser never decides policy; it only renders the server's reasons.
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
const MAX_CLEAN = 32;
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
  ["sttn", "STTN · video, best on subtitles"],
  ["lama", "LaMa · per frame, best on still backgrounds"],
];
const FILL_KINDS = new Set(["delogo", "blur", "plate", "mask"]);

// Drawn boxes start with the last method used; the first is AI fill when an
// engine is ready, else Blur.
let fillAvailable = false;
let lastDrawKind = "";

export function setFillAvailable(value) {
  fillAvailable = Boolean(value);
}

export function isFillAvailable() {
  return fillAvailable;
}

export function rememberDrawKind(kind) {
  if (KIND_ORDER.includes(kind)) lastDrawKind = kind;
}

export function drawKind() {
  if (lastDrawKind === "fill" && !fillAvailable) return "blur";
  return lastDrawKind || (fillAvailable ? "fill" : "blur");
}

/** Set a layer's kind, adding or dropping the fill engine to match. */
export function setLayerKind(layer, kind) {
  layer.kind = kind;
  if (kind === "fill") {
    if (!FILL_METHODS.some(([value]) => value === layer.method)) layer.method = FILL_METHODS[0][0];
  } else {
    delete layer.method;
  }
  return layer;
}

/** Turn every detected text cover (remove, blur, plate, mask) into an AI fill.
 *
 * Manual boxes are left alone: the model should only invent pixels where a
 * scan found text, not inside a box the creator drew for another reason.
 */
export function useFillForAll(layers, method = FILL_METHODS[0][0]) {
  return layers.map((layer) => (
    FILL_KINDS.has(layer.kind) && String(layer.tracklet_id || "").trim()
      ? setLayerKind({ ...clone(layer), method }, "fill")
      : layer
  ));
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
  return first.some((a) => second.some((b) => (
    Number(a.start) < Number(b.end) && Number(b.start) < Number(a.end)
  )));
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
    label: "Remove text",
  };
  return setLayerKind(layer, drawKind());
}

function storySourceSpan(story, fallback = 0) {
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  if (clips.length) {
    const start = Math.min(...clips.map((clip) => numberOr(clip.start)));
    const end = Math.max(...clips.map((clip) => numberOr(clip.end, numberOr(clip.start) + numberOr(clip.dur))));
    if (end > start + 0.05) return { start: round(start), end: round(end) };
  }
  return { start: 0, end: round(Math.max(0.1, numberOr(fallback, 0.1))) };
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
  let sceneOnly = true;
  const autoState = autoCleanStateFor(jobId);
  // P2 found-text list and AI fill preview.
  let fillStatus = null;
  let fillStatusError = "";
  let removeMethod = "blur";
  let fillMethod = "sttn";
  let methodTouched = false;
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

  function hasHandles() {
    return (report?.tracklets || []).some(
      (tracklet) => String(tracklet?.kind || "") === "handle_or_logo",
    );
  }

  function handleNeedsTick() {
    return kindReason("handle_or_logo") === "attestation_required";
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
    if (code === "watermark" || code === "screen_text") {
      return entry?.reason || cleanReasonText(code);
    }
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
    for (const tracklet of report?.tracklets || []) {
      const id = String(tracklet?.id || "");
      if (!id) continue;
      const kind = String(tracklet?.kind || "");
      const entry = prefill.get(id) || null;
      const reasonCode = kindReason(kind);
      const blocked = kind === "watermark" || reasonCode === "watermark";
      const skipped = kind === "screen_text"
        || reasonCode === "screen_text"
        || entry?.action === "none"
        || entry?.blocked === "screen_text";
      const locked = !blocked && !skipped && Boolean(reasonCode);
      const added = current.some((layer) => sameScanText(layer, tracklet));
      let reason = reasonText(kind, entry);
      if (added) reason = "Already added to this moment.";
      else if (full && !blocked && !skipped) {
        reason = `This moment has ${MAX_CLEAN} text layers, the most it can hold.`;
      }
      const allowed = !blocked
        && !skipped
        && !locked
        && !added
        && !full
        && canCleanKind(kind);
      const ticked = foundTicks.has(id) ? Boolean(foundTicks.get(id)) : allowed;
      rows.push({
        id,
        tracklet,
        kind,
        entry,
        box: tracklet?.box && typeof tracklet.box === "object" ? tracklet.box : null,
        text: String(tracklet?.text_sample || "").trim() || "No words read",
        ranges: Array.isArray(tracklet?.ranges) ? tracklet.ranges : [],
        time: rangeSummary(tracklet?.ranges),
        reason,
        blocked: blocked || skipped,
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

  function pushFoundToPreview(rows) {
    if (!ctx.setFoundText) return;
    ctx.setFoundText(
      rows
        .filter((row) => row.box && !row.added)
        .map((row) => ({
          id: row.id,
          box: { ...row.box },
          ranges: Array.isArray(row.tracklet?.ranges) ? row.tracklet.ranges : [],
          text: row.text,
          kind: row.kind,
          ticked: row.ticked,
          blocked: row.blocked,
        })),
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
    if (removeMethod === "ai" && !fillReady(fillMethod)) {
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
        include_handles: false,
        tracklet_ids: ticked.map((row) => row.id),
        method: removeMethod,
        fill_method: fillMethod,
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
    sceneOnly = scoped ? true : scene ? false : false;
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
    const wrap = el("div", { class: "st-clean-scan-tools" });
    const scope = el("p", {
      class: "st-hint",
      text: `${formatCount(sceneFiltered(foundRows()).length, "text region")} in this ${sceneOnly ? "scene" : "video"}. Tick to remove. AI fill rebuilds the background.`,
    });
    const thisScene = el("button", {
      class: `st-btn st-btn-small${sceneOnly ? " st-btn-ghost" : " st-btn-quiet"} st-clean-scope-scene`,
      type: "button",
      text: "Check this scene",
    });
    thisScene.addEventListener("click", () => {
      sceneOnly = true;
      if (reportMatchesScene(ctx.getSceneRange?.())) { render(); return; }
      void startTextScan({ scene: true });
    });
    const video = el("button", {
      class: `st-btn st-btn-small${sceneOnly ? " st-btn-quiet" : " st-btn-ghost"} st-clean-scope-video`,
      type: "button",
      text: "Scan video",
    });
    video.addEventListener("click", () => {
      sceneOnly = false;
      if (!report?.scope) { render(); return; }
      void startTextScan();
    });
    wrap.append(scope, el("div", { class: "st-clean-scope" }, [thisScene, video]));
    return wrap;
  }

  function autoCleanToolbar() {
    const running = Boolean(autoState.busy);
    const editId = ctx.getEdit()?.id || "";
    const rows = sceneFiltered(foundRows());
    const ticked = rows.filter((row) => row.allowed && row.ticked);
    const aiReady = Boolean(firstFillMethod());
    const method = el("select", {
      class: "st-found-method",
      "aria-label": "Remove text with",
      disabled: running || !editId,
    }, [
      el("option", {
        value: "ai",
        text: aiReady
          ? "AI fill"
          : fillStatusError ? "AI fill (status unavailable)" : "AI fill (model missing)",
        selected: removeMethod === "ai",
        disabled: !aiReady,
      }),
      el("option", { value: "blur", text: "Blur", selected: removeMethod === "blur" }),
    ]);
    method.addEventListener("change", () => {
      methodTouched = true;
      removeMethod = method.value === "ai" ? "ai" : "blur";
      render();
    });
    const controls = [
      el("label", { class: "st-found-method-wrap" }, [
        el("span", { text: "Remove with" }),
        method,
      ]),
    ];
    if (removeMethod === "ai" && aiReady) {
      const engine = el("select", {
        class: "st-found-engine",
        "aria-label": "AI fill engine",
        disabled: running || !editId,
      }, Object.entries(fillStatus?.methods || {})
        .filter(([, value]) => value?.ready)
        .map(([id, value]) => el("option", {
          value: id,
          text: value.label || id,
          selected: fillMethod === id,
        })));
      engine.addEventListener("change", () => {
        fillMethod = engine.value;
        render();
      });
      controls.push(el("label", { class: "st-found-method-wrap" }, [
        el("span", { text: "Engine" }),
        engine,
      ]));
    }
    const button = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-auto-clean-run",
      type: "button",
      text: running ? "Removing found text…" : "Remove all found text",
      disabled: running || !editId || !ticked.length,
      "aria-busy": running ? "true" : "false",
      title: !editId
        ? "Open an Edit to remove detected text."
        : !ticked.length
          ? "Tick at least one found text region first."
          : `Remove ${ticked.length} ticked ${ticked.length === 1 ? "region" : "regions"} with ${removeMethod === "ai" ? "AI fill" : removeMethod}.`,
    });
    button.addEventListener("click", () => { void runAutoClean(); });
    controls.push(button);
    const wrap = el("div", { class: "st-found-actions st-clean-toolbar" }, controls);
    if (removeMethod === "ai" && !aiReady) {
      wrap.append(el("p", {
        class: "st-found-note",
        text: fillStatusError || "AI fill needs its model in the fill models folder. Blur works without it.",
      }));
    }
    if (removeMethod === "blur" && ticked.some((row) => row.entry?.quality_warning)) {
      wrap.append(el("p", {
        class: "st-found-note",
        text: "Some of this text crosses the middle of the frame. Blur may leave it readable; AI fill removes it.",
      }));
    }
    return wrap;
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
      card.append(el("p", {
        class: "st-hint",
        text: "Rights lock is off. Cleaning old captions is open. Watermarks are never removed.",
      }));
      if (hasHandles() && handleNeedsTick()) {
        card.append(rightsTick(
          "This handle or logo is mine.",
          "A handle or logo always needs this per-video tick, even with the lock off.",
          recordRights,
        ));
      }
      return card;
    }
    if (policy.attested && !(hasHandles() && handleNeedsTick())) {
      return null;
    }
    card.append(el("p", {
      class: "st-hint",
      text: "The rights lock is on. Confirm the box to clean old text; you can still add your own text and captions.",
    }));
    card.append(rightsTick(
      "I own this footage or have the rights to it.",
      "Stored on the server for this video. Watermarks are never removed.",
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
      "aria-label": row.allowed
        ? `Remove ${row.text}`
        : `${row.text} is not removed`,
    });
    checkbox.addEventListener("change", () => {
      setFoundTicked(row.id, checkbox.checked);
    });
    const status = row.added
      ? "Done"
      : row.blocked
        ? row.kind === "watermark"
          ? "Watermark · not removed"
          : row.kind === "screen_text"
            ? "Screen UI · not cleaned"
            : "Not removed"
        : TRACKLET_LABELS[row.kind] || "Text";
    const copy = el("div", { class: "st-found-copy" }, [
      el("div", { class: "st-found-line" }, [
        el("strong", { text: row.text }),
      ]),
      el("small", {
        class: "st-found-meta",
        text: seekMissFound === String(row.id) ? "Not in this cut" : `${row.time} · ${status}`,
      }),
    ]);
    const painted = (ctx.getEdit()?.clean || []).some((layer) => (
      String(layer.tracklet_id || "") === String(row.id) && maskPointCount(layer) > 0
    ));
    const paint = (row.allowed || row.added) ? el("button", {
      class: `st-found-paint${painted ? " is-painted" : ""}`,
      type: "button",
      text: "",
      title: painted
        ? "Paint layer ready — use Paint more in the layer editor"
        : "Paint a freehand AI-fill mask (Shift-click adds another layer)",
      "aria-label": painted ? "Paint layer ready" : "Paint mask",
      disabled: painted,
    }) : null;
    if (paint) {
      paint.append(icon("brush", { size: 13 }));
      paint.addEventListener("click", (event) => {
        event.stopPropagation();
        startPaintRow(row, event.shiftKey || event.altKey);
      });
    }
    const node = el("div", {
      class: `st-found-row${row.ticked ? " is-ticked" : ""}${row.added ? " is-added" : ""}${row.blocked ? " is-blocked" : ""}${painted ? " is-painted" : ""}`,
      role: "listitem",
      tabindex: "0",
      dataset: { id: row.id, kind: row.kind, reason: row.reason || "" },
    }, [checkbox, copy, paint]);
    const activate = () => {
      const at = row.ranges?.[0]?.start ?? row.tracklet?.ranges?.[0]?.start;
      const seek = typeof ctx.seekSource === "function" ? ctx.seekSource(at) : false;
      seekMissFound = seek === false ? row.id : "";
      ctx.focusFound?.(row.id);
      render();
    };
    node.addEventListener("click", (event) => {
      if (event.target.closest("input, .st-found-paint")) return;
      activate();
    });
    node.addEventListener("keydown", (event) => {
      if (event.target.closest("input, .st-found-paint")) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
    return node;
  }

  function startPaintRow(row, fresh = false) {
    if (!row || (!row.allowed && !row.added)) return;
    const layers = (ctx.getEdit()?.clean || []).slice();
    // One layer per found text: clicking again reuses it, painted or not.
    let layer = !fresh && layers.find((item) => (
      item.kind === "fill" && sameScanText(item, row.tracklet)
    ));
    const created = !layer;
    if (!layer) {
      layer = layerFromEntry(
        { box: row.box, ranges: row.ranges },
        row.tracklet,
        layers.length,
        report?.source,
      );
      layer.id = `cl_paint_${safeId(row.id)}_${Date.now().toString(36)}`;
      layer.tracklet_id = row.id;
      layer.tracklet_kind = row.kind;
      layer.kind = "fill";
      layer.method = FILL_METHODS[0][0];
      layer.mask = emptyMask(ctx.getAspect?.() || "9:16");
      layer.label = safeLabel(row.text, KIND_COPY.fill);
      layers.push(layer);
      ctx.setClean(layers);
      render();
    }
    ctx.select("clean", layer.id);
    ctx.startPaint?.(layer.id, { created });
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
    if (scan !== "ready" || !rows.length) return null;
    const allowed = rows.filter((row) => row.allowed);
    const ticked = rows.filter((row) => row.allowed && row.ticked);
    const allTicked = allowed.length > 0 && allowed.every((row) => row.ticked);
    const card = el("div", { class: "st-found-card" });
    const toggle = allowed.length ? el("button", {
      class: "st-btn st-btn-quiet st-btn-small st-found-select-all",
      type: "button",
      text: allTicked ? "Clear ticks" : "Select all",
    }) : null;
    if (toggle) {
      toggle.addEventListener("click", () => setAllFoundTicked(!allTicked));
    }
    card.append(el("div", { class: "st-found-head" }, [
      el("div", { class: "st-found-heading" }, [
        el("strong", { text: "Found on screen" }),
        el("span", { text: `${rows.length} · ${ticked.length} ticked` }),
      ]),
      toggle,
    ]));
    const list = el("div", { class: "st-found-list", role: "list" });
    for (const row of rows.slice(0, 40)) list.append(foundRowNode(row));
    card.append(list);
    if (rows.length > 40) {
      card.append(el("p", { class: "st-hint", text: `Showing 40 of ${rows.length} found regions.` }));
    }
    card.append(autoCleanToolbar());
    const status = autoCleanStatusNode();
    if (status) card.append(status);
    return card;
  }

  function existingCard(selectedId) {
    const layers = ctx.getEdit()?.clean || [];
    const card = el("div", { class: "st-clean-layers" });
    card.append(el("div", { class: "st-clean-layers-head" }, [
      el("strong", { text: "Clean layers" }),
      el("span", { text: String(layers.length) }),
    ]));
    if (!layers.length) {
      card.append(el("p", { class: "st-hint", text: "Nothing is covered yet. Add a Check region, or place a box by hand." }));
    } else {
      const list = el("div", { class: "st-layer-list", role: "list", style: "margin-top:8px" });
      for (const layer of layers) {
        const active = selectedId === layer.id;
        const hiddenByCrop = ctx.isHiddenByCrop?.(layer) === true;
        const row = el("button", {
          class: `st-layer-row${active ? " is-active" : ""}`,
          type: "button",
          role: "listitem",
          "aria-pressed": active ? "true" : "false",
          dataset: { kind: "clean", layer: layer.id, box: JSON.stringify(layer.box || {}) },
        }, [
          el("span", { class: "st-layer-badge", text: CLEAN_LABELS[layer.kind] || KIND_COPY[layer.kind] || "Clean" }),
          el("span", { class: "st-layer-name", text: layer.label || rangeSummary(layer.ranges) }),
          hiddenByCrop ? el("span", { class: "st-layer-hidden-note", text: "Hidden by crop" }) : null,
        ]);
        row.addEventListener("click", () => ctx.select("clean", layer.id));
        list.append(el("div", { class: "st-clean-row" }, [row, methodSwitch(layer)]));
      }
      card.append(list);
      const covers = layers.filter((layer) => (
        FILL_KINDS.has(layer.kind) && String(layer.tracklet_id || "").trim()
      )).length;
      if (covers) {
        const toFill = el("button", {
          class: "st-btn st-btn-ghost st-btn-small",
          type: "button",
          text: `Use AI fill for all ${covers} detected ${covers === 1 ? "layer" : "layers"}`,
          disabled: !canClean(),
          style: "margin-top:8px",
        });
        toFill.addEventListener("click", () => {
          ctx.setClean(useFillForAll(ctx.getEdit()?.clean || []));
          ctx.refresh();
        });
        card.append(toFill);
      }
    }

    const addRow = el("div", { class: "st-layer-add", style: "margin-top:9px" });
    const kind = el("select", { "aria-label": "New Clean kind", disabled: !canClean() });
    for (const value of KIND_ORDER) {
      kind.append(el("option", {
        value,
        text: KIND_COPY[value],
        selected: value === drawKind(),
        disabled: value === "fill" && !isFillAvailable(),
      }));
    }
    const add = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Add box",
      disabled: !canClean() || layers.length >= MAX_CLEAN,
      title: layers.length >= MAX_CLEAN ? `A story supports ${MAX_CLEAN} clean layers.` : "",
    });
    add.addEventListener("click", () => {
      rememberDrawKind(kind.value);
      ctx.addBox?.(kind.value);
    });
    addRow.append(kind, add);
    card.append(addRow);
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

  /** AI fill or Blur for this box only. */
  function methodSwitch(layer) {
    const wrap = el("div", { class: "st-method-switch", role: "group", "aria-label": "Clean method for this box" });
    for (const value of KIND_ORDER) {
      const locked = value === "fill" && !isFillAvailable();
      const button = el("button", {
        class: `st-method-option${layer.kind === value ? " is-active" : ""}`,
        type: "button",
        text: KIND_COPY[value],
        "aria-pressed": layer.kind === value ? "true" : "false",
        disabled: !canClean() || locked,
        title: locked ? (fillStatusError || "AI fill needs its model in the fill models folder.") : "",
      });
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        ctx.setCleanMethod?.(layer.id, value);
      });
      wrap.append(button);
    }
    return wrap;
  }

  function editorCard(selected, selectedId) {
    if (!selected) return null;
    const layer = clone(selected);
    const stage = el("div", { class: "st-card st-check-card" });
    stage.append(el("div", { class: "st-layer-stage-head" }, [
      el("h3", { text: CLEAN_LABELS[layer.kind] || "Clean layer" }),
      el("span", { class: "st-mono st-hint", text: rangeSummary(layer.ranges) }),
    ]));

    const kindSelect = el("select", { "aria-label": "Clean kind", disabled: !canClean() });
    for (const value of KIND_ORDER) {
      kindSelect.append(el("option", {
        value,
        text: KIND_COPY[value],
        selected: value === layer.kind,
        disabled: value === "fill" && !isFillAvailable(),
      }));
    }
    if (!KIND_ORDER.includes(layer.kind)) {
      // A saved layer from before Clean had two methods: it renders as it was
      // until it is switched.
      kindSelect.prepend(el("option", {
        value: layer.kind,
        text: `${KIND_COPY[layer.kind] || layer.kind} (old)`,
        selected: true,
        disabled: true,
      }));
    }
    kindSelect.addEventListener("change", () => {
      ctx.setCleanMethod?.(layer.id, kindSelect.value);
    });

    const labelInput = el("input", {
      type: "text",
      maxlength: 80,
      value: layer.label || "",
      "aria-label": "Clean label",
      disabled: !canClean(),
    });
    labelInput.addEventListener("input", () => {
      layer.label = safeLabel(labelInput.value, KIND_COPY[layer.kind] || "Clean layer");
      commit();
    });
    labelInput.addEventListener("change", () => {
      if (labelInput.value !== layer.label) labelInput.value = layer.label;
    });

    let radiusInput = null;
    const maxBlur = () => safeRadius(layer.box, report?.source);

    const xInput = numberInput(Math.round(numberOr(layer.box?.x) * 100), { min: 0, max: 100, step: 0.5 });
    const yInput = numberInput(Math.round(numberOr(layer.box?.y) * 100), { min: 0, max: 100, step: 0.5 });
    const wInput = numberInput(Math.round(numberOr(layer.box?.w) * 100), { min: 0.5, max: 100, step: 0.5 });
    const hInput = numberInput(Math.round(numberOr(layer.box?.h) * 100), { min: 0.5, max: 100, step: 0.5 });
    for (const [input, key] of [[xInput, "x"], [yInput, "y"], [wInput, "w"], [hInput, "h"]]) {
      input.disabled = !canClean();
      input.addEventListener("input", () => {
        const value = clamp(numberOr(input.value) / 100, key === "w" || key === "h" ? 0.001 : 0, 1);
        const box = { ...(layer.box || {}) };
        if (key === "x") box.x = clamp(value, 0, 1 - numberOr(box.w, 0.1));
        else if (key === "y") box.y = clamp(value, 0, 1 - numberOr(box.h, 0.1));
        else if (key === "w") box.w = clamp(value, 0.001, 1 - numberOr(box.x, 0));
        else box.h = clamp(value, 0.001, 1 - numberOr(box.y, 0));
        layer.box = {
          x: round(box.x, 4), y: round(box.y, 4),
          w: round(box.w, 4), h: round(box.h, 4),
        };
        if (layer.kind === "blur") {
          const cap = maxBlur();
          if (layer.radius > cap) {
            layer.radius = cap;
            if (radiusInput) {
              radiusInput.value = String(cap);
              radiusInput.max = String(cap);
              const hint = radiusInput.parentElement?.querySelector(".st-field-hint");
              if (hint) hint.textContent = `2–${cap}. The cap keeps small boxes from failing.`;
            }
          }
        }
        commit();
      });
    }

    const details = el("details", { class: "st-clean-details" }, [
      el("summary", { text: "Box and timing" }),
    ]);
    const grid = el("div", { class: "st-control-grid" }, [
      field("Kind", kindSelect),
      field("Label", labelInput),
      field("Box left (%)", xInput),
      field("Box top (%)", yInput),
      field("Box width (%)", wInput),
      field("Box height (%)", hInput),
    ]);
    details.append(grid);
    details.append(el("p", { class: "st-field-hint", text: "Boxes stay on the original video: they move and scale with it, and the crop only hides them." }));
    stage.append(methodSwitch(layer));
    stage.append(details);
    if (layer.kind === "delogo" && numberOr(layer.box?.w) * numberOr(layer.box?.h) > 0.1) {
      stage.append(el("p", {
        class: "st-found-note",
        text: "This old Remove box is large and smears the picture. Switch it to AI fill or Blur.",
      }));
    }

    const maskPoints = maskStrokes(layer);
    if (layer.kind === "fill") {
      const paintRow = el("div", { class: "st-layer-add" }, [
        el("button", {
          class: "st-btn st-btn-ghost st-btn-small",
          type: "button",
          text: maskPoints.length ? `Paint more (${maskPointCount(layer)})` : "Paint mask",
          disabled: !canClean(),
        }),
        maskPoints.length ? el("button", {
          class: "st-btn st-btn-quiet st-btn-small",
          type: "button",
          text: "Clear mask",
          disabled: !canClean(),
        }) : null,
      ]);
      const [paintButton, clearButton] = paintRow.querySelectorAll("button");
      paintButton.addEventListener("click", () => {
        ctx.startPaint?.(layer.id);
      });
      clearButton?.addEventListener("click", () => {
        layer.mask = emptyMask(ctx.getAspect?.() || "9:16");
        commit();
        ctx.refresh();
      });
      stage.append(paintRow);
      if (maskPoints.length) {
        stage.append(el("p", {
          class: "st-field-hint",
          text: "Only the painted part is filled, and only inside the box. A single click is ignored.",
        }));
      }
      const compare = el("button", {
        class: "st-btn st-btn-ghost st-btn-small st-clean-compare",
        type: "button",
        text: "Before / After",
        title: "Run the engine on this frame without saving",
      });
      compare.addEventListener("click", () => ctx.compareLayer?.(layer.id));
      stage.append(compare);
    }

    if (layer.kind === "plate" || layer.kind === "mask") {
      const color = colorInput(layer.color);
      color.disabled = !canClean();
      color.addEventListener("input", () => {
        layer.color = color.value;
        commit();
      });
      const opacity = el("input", {
        type: "range", min: "0", max: "1", step: "0.01",
        value: String(numberOr(layer.opacity, 1)),
        "aria-label": "Cover opacity",
        disabled: !canClean(),
      });
      const opacityValue = el("span", { class: "st-mono st-range-value", text: `${Math.round(numberOr(layer.opacity, 1) * 100)}%` });
      opacity.addEventListener("input", () => {
        layer.opacity = clamp(numberOr(opacity.value), 0, 1);
        opacityValue.textContent = `${Math.round(layer.opacity * 100)}%`;
        commit();
      });
      stage.append(el("div", { class: "st-control-grid" }, [field("Fill colour", color)]));
      stage.append(el("div", { class: "st-range-row" }, [
        el("span", { class: "st-field-label", text: "Opacity" }),
        opacity,
        opacityValue,
      ]));
    }

    if (layer.kind === "fill") {
      const method = el("select", { "aria-label": "AI fill engine", disabled: !canClean() });
      for (const [value, text] of FILL_METHODS) {
        method.append(el("option", { value, text, selected: value === (layer.method || FILL_METHODS[0][0]) }));
      }
      method.addEventListener("change", () => {
        layer.method = method.value;
        commit();
      });
      stage.append(el("div", { class: "st-control-grid" }, [
        field("Engine", method, "Runs on this Mac when you render. It can take minutes per beat."),
      ]));
      stage.append(el("p", {
        class: "st-field-hint",
        text: "The preview shows the box only. The filled picture appears in the render.",
      }));
    }

    if (layer.kind === "blur") {
      const cap = maxBlur();
      const radius = numberInput(Math.min(numberOr(layer.radius, cap), cap), { min: 2, max: cap, step: 1 });
      radiusInput = radius;
      radius.disabled = !canClean();
      radius.addEventListener("input", () => {
        layer.radius = Math.round(clamp(numberOr(radius.value), 2, maxBlur()));
        commit();
      });
      stage.append(el("div", { class: "st-control-grid" }, [field("Blur strength", radius, `2–${cap}. The cap keeps small boxes from failing.`)]));
    }

    const ranges = Array.isArray(layer.ranges) ? layer.ranges : [];
    const rangeBox = el("div", { class: "st-layer-stage" });
    rangeBox.append(el("h4", { text: "Source time ranges" }));
    if (!ranges.length) {
      rangeBox.append(el("p", { class: "st-hint", text: "No ranges: the layer stays on for the whole story." }));
    }
    ranges.forEach((range, index) => {
      const start = numberInput(range.start, { min: 0, max: 100000, step: 0.01 });
      const end = numberInput(range.end, { min: 0, max: 100000, step: 0.01 });
      start.disabled = !canClean();
      end.disabled = !canClean();
      start.addEventListener("input", () => {
        range.start = round(clamp(numberOr(start.value), 0, 100000));
        if (range.end <= range.start) range.end = round(range.start + 0.1);
        commit();
      });
      end.addEventListener("input", () => {
        range.end = round(clamp(numberOr(end.value), range.start + 0.01, 100000));
        commit();
      });
      const remove = el("button", {
        class: "st-icon-btn st-icon-small",
        type: "button",
        "aria-label": "Remove time range",
        text: "×",
        disabled: !canClean(),
      });
      remove.addEventListener("click", () => {
        layer.ranges = ranges.filter((item) => item !== range);
        commit();
        ctx.refresh();
      });
      rangeBox.append(el("div", { class: "st-control-grid", style: "grid-template-columns:1fr 1fr auto;align-items:end" }, [
        field(`From ${index + 1} (s)`, start),
        field(`To ${index + 1} (s)`, end),
        remove,
      ]));
    });
    const addRange = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: "Add story range",
      disabled: !canClean(),
    });
    addRange.addEventListener("click", () => {
      const span = storySourceSpan(ctx.getStory(), ctx.getDuration());
      layer.ranges = [...(layer.ranges || []), span];
      commit();
      ctx.refresh();
    });
    rangeBox.append(addRange);
    rangeBox.append(el("p", { class: "st-field-hint", text: "Times are from the original video, not the cut." }));
    details.append(rangeBox);

    const remove = el("button", { class: "st-btn st-btn-quiet st-btn-small st-danger", type: "button", text: "Remove layer" });
    remove.addEventListener("click", () => {
      const layers = (ctx.getEdit()?.clean || []).filter((item) => item.id !== layer.id);
      ctx.setClean(layers);
      ctx.select("clean", "");
    });
    stage.append(el("div", { class: "st-layer-foot" }, [remove]));

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
    const layers = ctx.getEdit()?.clean || [];
    const selected = layers.find((layer) => layer.id === selectedId) || null;

    const head = el("div", { class: "st-clean-status" });
    head.append(scanToolbar());
    const rights = renderRights();
    if (rights) head.append(rights);
    const warnings = renderWarnings();
    if (warnings) head.append(warnings);
    if (loadError) head.append(el("p", { class: "st-error", text: loadError }));
    host.append(head);

    const found = suggestionsCard();
    if (found) host.append(found);
    host.append(existingCard(selectedId));
    const editor = editorCard(selected, selectedId);
    if (editor) host.append(editor);

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
    return ["sttn", "lama"].find((method) => methods[method]?.ready) || "";
  }

  async function loadFillStatus() {
    try {
      const status = await request("/api/fill/status");
      if (disposed) return;
      fillStatus = status && typeof status === "object" ? status : null;
      fillStatusError = "";
      const first = firstFillMethod();
      setFillAvailable(Boolean(first));
      if (!methodTouched) removeMethod = first ? "ai" : "blur";
      if (removeMethod === "ai" && !first) removeMethod = "blur";
      if (first && (!methodTouched || !fillReady(fillMethod))) fillMethod = first;
      render();
    } catch (error) {
      if (disposed) return;
      fillStatusError = error?.message || "Could not check the AI fill models.";
      if (!methodTouched) removeMethod = "blur";
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
