/**
 * Clean layer controls.
 *
 * Check findings become Clean layers in the same Edit document. Boxes and
 * ranges use source coordinates and source time, exactly as the renderer
 * expects; the panel never converts them to output space.
 *
 * Adding is gated by the report's rights policy. A watermark tracklet is never
 * offered, and a handle or logo stays off unless the own-footage attestation
 * was recorded by Check.
 */

import { request } from "../../api.js";
import { ensureCheckStyles } from "../../check.js";
import { el, formatCount } from "../../ui.js";
import {
  CLEAN_LABELS,
  clamp,
  clone,
  formatSpan,
  numberOr,
  round,
} from "../model.js";

const CHECK_POLL_MS = 2500;
const MAX_CLEAN = 32;
const PREFILL_PREFIX = "vibecut.studio.clean.prefill.";

const KIND_ORDER = ["plate", "blur", "mask", "crop_guard"];

const KIND_COPY = {
  plate: "Cover plate",
  blur: "Blur",
  mask: "Mask",
  crop_guard: "Keep out of crop",
};

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
    return { report: await request(`/api/jobs/${encodeURIComponent(jobId)}/check`), pending: false };
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

function prefillKey(jobId, storyRef, aspect) {
  return `${PREFILL_PREFIX}${jobId}:${storyRef?.set_id || ""}:${storyRef?.story_id || ""}:${aspect || ""}`;
}

function readFlag(key) {
  try {
    return Boolean(localStorage.getItem(key));
  } catch (_) {
    return false;
  }
}

function writeFlag(key) {
  try {
    localStorage.setItem(key, "1");
  } catch (_) {
    /* A private window may refuse storage; the fill still lands in the edit. */
  }
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

function layersFromEntry(entry, tracklet, index, source) {
  const base = layerFromEntry(entry, tracklet, index * 2, source);
  const layers = [base];
  if (base.kind === "blur" && entry?.quality_warning) {
    layers.push({
      ...clone(base),
      id: `${base.id}_plate`,
      kind: "plate",
      z: index * 2 + 1,
      color: "#000000",
      opacity: 1,
      radius: 12,
      label: "Cover plate",
    });
  }
  return layers;
}

function safeRadius(box, source) {
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

function manualLayer(index) {
  return {
    id: `cl_manual_${Date.now().toString(36)}`,
    kind: "plate",
    box: { x: 0.08, y: 0.72, w: 0.84, h: 0.16 },
    ranges: [],
    z: index,
    color: "#000000",
    opacity: 1,
    radius: 12,
    label: "Manual cover",
  };
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

  host.replaceChildren(el("p", { class: "st-hint", text: "Reading Check findings…" }));

  function stopPoll() {
    if (timer) window.clearTimeout(timer);
    timer = 0;
  }

  function canClean() {
    return Boolean(report?.policy?.clean_allowed);
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

  function autoFill() {
    const layers = ctx.getEdit()?.clean || [];
    if (loading || layers.length) return;
    if (!report?.complete || report?.status !== "ready") return;
    if (!report?.text?.present || !canClean()) return;
    if (!jobId || readFlag(prefillKey(jobId, edit.story_ref, edit.aspect))) return;
    const tracklets = trackletById();
    const entries = (report.clean_prefill || []).filter((entry) => (
      entry?.enabled
      && entry.action !== "refused"
      && !entry.blocked
      && tracklets.has(String(entry.tracklet_id))
    ));
    if (!entries.length) return;
    const next = [];
    for (const [index, entry] of entries.slice(0, MAX_CLEAN).entries()) {
      const group = layersFromEntry(
        entry, tracklets.get(String(entry.tracklet_id)), index, report.source,
      );
      if (next.length + group.length > MAX_CLEAN) break;
      next.push(...group);
    }
    writeFlag(prefillKey(jobId, edit.story_ref, edit.aspect));
    ctx.setClean(next);
    syncCleanTab(next.length);
    ctx.notify(
      `Filled ${formatCount(next.length, "cover")} from Check. Remove any you do not want.`
      + (entries.length > next.length ? ` ${entries.length - next.length} more stay in Check.` : ""),
      "ok",
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

  function renderRights() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Rights" }));
    const recorded = Boolean(report?.rights?.attested || report?.policy?.rights_attested);
    if (!report) {
      card.append(el("p", { class: "st-hint", text: "Check has not run for this video. Clean stays locked until the rights note is recorded." }));
      card.append(el("a", { class: "st-btn st-btn-ghost st-btn-small", href: "#/check", text: "Open Check" }));
    } else if (recorded) {
      card.append(el("p", { class: "st-hint", text: "Own-footage rights note is recorded. Cleaning is available for this source." }));
    } else {
      card.append(el("p", { class: "st-hint", text: "Check found no rights note. Clean is locked for this source; you can still add your own text and captions." }));
      card.append(el("a", { class: "st-btn st-btn-ghost st-btn-small", href: "#/check", text: "Record rights in Check" }));
    }
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
        message: "Burned-in text crosses the middle of the frame. A blur or plate can leave a visible patch; check the rendered frame at 1×.",
      });
    }
    if (!warnings.length) return null;
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Quality warnings" }));
    const list = el("div", { style: "margin-top:9px" });
    for (const warning of warnings.slice(0, 6)) list.append(warningNode(warning));
    if (warnings.length > 6) {
      list.append(el("p", { class: "st-hint", text: `+${warnings.length - 6} more in Check.` }));
    }
    card.append(list);
    return card;
  }

  function suggestionsCard() {
    const tracklets = report?.tracklets || [];
    const prefill = prefillByTracklet();
    const current = ctx.getEdit()?.clean || [];
    const existing = new Set(current.map((layer) => layer.id));
    const full = current.length >= MAX_CLEAN;
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "From Check" }));

    if (!report) {
      card.append(el("p", { class: "st-hint", text: "Run Check to list old text regions for this source." }));
      const link = el("a", { class: "st-btn st-btn-ghost st-btn-small", href: "#/check", text: "Open Check" });
      card.append(link);
      return card;
    }
    if (pending) {
      card.append(el("p", { class: "st-hint", text: report?.message || "Check is still running. Findings appear here when it finishes." }));
      return card;
    }
    if (!tracklets.length) {
      card.append(el("p", { class: "st-hint", text: report?.text?.confirmed
        ? "No on-screen text was found."
        : "The full text pass did not run. Check the frame yourself before publishing." }));
      return card;
    }

    card.append(el("p", { class: "st-hint", text: full
      ? `This edit already has ${MAX_CLEAN} clean layers, the most one story can hold.`
      : "Each region can become one Clean layer. The box and times stay in source coordinates." }));
    const list = el("div", { class: "st-layer-list", style: "margin-top:9px" });
    let shown = 0;
    for (const tracklet of tracklets.slice(0, 40)) {
      const kind = String(tracklet?.kind || "");
      const blocked = kind === "watermark";
      const entry = prefill.get(String(tracklet.id)) || null;
      const candidates = layersFromEntry(
        entry || {}, tracklet, current.length, report?.source,
      );
      const missing = candidates.filter((layer) => !existing.has(layer.id));
      const added = missing.length === 0;
      const wouldOverflow = current.length + missing.length > MAX_CLEAN;
      const skipped = kind === "screen_text"
        || entry?.action === "none"
        || entry?.blocked === "screen_text";
      if (added && !blocked && !skipped) continue;
      shown += 1;
      const reason = blocked
        ? "Use your original file — it has no watermark."
        : skipped
          ? (entry?.reason || "Screen interface text is left alone; it is never cleaned.")
          : kind === "handle_or_logo" && !canClean()
            ? "Own handle or logo. Confirm rights in Check first."
            : entry?.reason || "";
      const actionLabel = blocked
        ? "Never cleaned"
        : skipped
          ? "Never cleaned"
          : (KIND_COPY[candidates[0]?.kind] || "Cover");
      const button = el("button", {
        class: "st-btn st-btn-ghost st-btn-small",
        type: "button",
        text: added ? "Added" : blocked || skipped ? "Never" : "Add",
        disabled: blocked || skipped || added || !canClean() || full || wouldOverflow,
        title: reason || `Add a ${actionLabel.toLowerCase()} for this region.`,
        style: "flex:0 0 auto;white-space:nowrap",
      });
      button.addEventListener("click", () => {
        const layers = (ctx.getEdit()?.clean || []).slice();
        const next = candidates.filter((layer) => !layers.some((item) => item.id === layer.id));
        if (!next.length) return;
        layers.push(...next.map((layer) => clone(layer)));
        ctx.setClean(layers.slice(0, MAX_CLEAN));
        ctx.notify(
          candidates.length > 1
            ? "Blur and cover plate added from Check."
            : `${KIND_COPY[candidates[0]?.kind] || "Cover"} added from Check.`,
          "ok",
        );
        ctx.select("clean", candidates[0]?.id || "");
      });

      const row = el("div", { class: "st-layer-row st-layer-row-static", style: "align-items:flex-start" }, [
        el("span", {
          class: `st-chip${blocked ? " st-chip-bad" : kind === "handle_or_logo" ? " st-chip-busy" : ""}`,
          text: TRACKLET_LABELS[kind] || "Text",
        }),
        el("span", { class: "st-layer-name" }, [
          el("strong", { text: tracklet?.text_sample || "No words read", style: "display:block;color:var(--st-text);font-weight:500" }),
          el("small", { text: `${rangeSummary(tracklet?.ranges)}${reason ? ` · ${reason}` : ""}` }),
        ]),
        button,
      ]);
      list.append(row);
    }
    if (!shown) {
      card.append(el("p", { class: "st-hint", text: `All ${tracklets.length} Check ${tracklets.length === 1 ? "region is" : "regions are"} covered. Review them in the layer list above.` }));
      return card;
    }
    card.append(list);
    if (tracklets.length > 40) card.append(el("p", { class: "st-hint", text: `Showing 40 of ${tracklets.length}.` }));
    if (tracklets.length > shown) card.append(el("p", { class: "st-hint", text: `${tracklets.length - shown} already covered ${tracklets.length - shown === 1 ? "region is" : "regions are"} hidden here.` }));
    return card;
  }

  function existingCard(selectedId) {
    const layers = ctx.getEdit()?.clean || [];
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: `Clean layers · ${layers.length}` }));
    if (!layers.length) {
      card.append(el("p", { class: "st-hint", text: "Nothing is covered yet. Add a Check region, or place a box by hand." }));
    } else {
      const list = el("div", { class: "st-layer-list", role: "list", style: "margin-top:8px" });
      for (const layer of layers) {
        const active = selectedId === layer.id;
        const row = el("button", {
          class: `st-layer-row${active ? " is-active" : ""}`,
          type: "button",
          role: "listitem",
          "aria-pressed": active ? "true" : "false",
        }, [
          el("span", { class: "st-layer-badge", text: CLEAN_LABELS[layer.kind] || KIND_COPY[layer.kind] || "Clean" }),
          el("span", { class: "st-layer-name", text: layer.label || rangeSummary(layer.ranges) }),
        ]);
        row.addEventListener("click", () => ctx.select("clean", layer.id));
        list.append(row);
      }
      card.append(list);
    }

    const addRow = el("div", { class: "st-layer-add", style: "margin-top:9px" });
    const kind = el("select", { "aria-label": "New Clean kind", disabled: !canClean() });
    for (const value of KIND_ORDER) {
      kind.append(el("option", { value, text: KIND_COPY[value] }));
    }
    const add = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Add box",
      disabled: !canClean() || layers.length >= MAX_CLEAN,
      title: layers.length >= MAX_CLEAN ? `A story supports ${MAX_CLEAN} clean layers.` : "",
    });
    add.addEventListener("click", () => {
      const layers = (ctx.getEdit()?.clean || []).slice();
      const layer = manualLayer(layers.length);
      layer.kind = kind.value;
      if (layer.kind === "crop_guard") layer.box = { x: 0.08, y: 0.72, w: 0.84, h: 0.16 };
      layers.push(layer);
      ctx.setClean(layers);
      ctx.select("clean", layer.id);
    });
    addRow.append(kind, add);
    card.append(addRow);
    if (!canClean()) {
      card.append(el("p", { class: "st-hint", text: "Adding is locked until Check records the rights note." }));
    }
    return card;
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
      kindSelect.append(el("option", { value, text: KIND_COPY[value], selected: value === layer.kind }));
    }
    kindSelect.addEventListener("change", () => {
      layer.kind = kindSelect.value;
      commit();
      ctx.refresh();
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

    const grid = el("div", { class: "st-control-grid" }, [
      field("Kind", kindSelect),
      field("Label", labelInput),
      field("Box left (%)", xInput),
      field("Box top (%)", yInput),
      field("Box width (%)", wInput),
      field("Box height (%)", hInput),
    ]);
    stage.append(grid);
    stage.append(el("p", { class: "st-field-hint", text: "Boxes are measured on the original frame, before the 9:16 crop." }));

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
    stage.append(rangeBox);

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
    host.replaceChildren();
    const selectedId = ctx.getSelectedId("clean");
    const layers = ctx.getEdit()?.clean || [];
    const selected = layers.find((layer) => layer.id === selectedId) || null;

    const head = el("div", { class: "st-card st-check-card" }, [
      el("h3", { text: "Clean old text" }),
      el("p", { class: "st-hint", text: "Cover, blur, mask or keep the crop away from baked-in text. Nothing here invents missing pixels or removes platform watermarks." }),
    ]);
    head.append(renderRights());
    if (loadError) head.append(el("p", { class: "st-error", text: loadError }));
    host.append(head);

    const warnings = renderWarnings();
    if (warnings) host.append(warnings);

    host.append(existingCard(selectedId));
    const editor = editorCard(selected, selectedId);
    if (editor) host.append(editor);
    host.append(suggestionsCard());

    if (!canClean() && report) {
      host.append(el("p", { class: "st-hint", text: "Clean is locked by the rights policy. You can still open Stories and Edit to compose new text over the source." }));
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
      const result = await fetchCheck(jobId);
      if (disposed) return;
      report = result.report;
      pending = Boolean(result.pending);
      loading = false;
      autoFill();
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

  void load();

  return () => {
    disposed = true;
    stopPoll();
  };
}
