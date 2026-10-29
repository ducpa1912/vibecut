/**
 * Studio — Source Check.
 *
 * Runs the existing `POST/GET /api/jobs/{id}/check` pass and turns its
 * `SourceReport` into findings, a plain recommendation and the rights note.
 * The report is advisory: Edit always stays open, and Clean is the only layer
 * that waits for the own-footage attestation.
 */

import { getJob, listClipSets, request } from "./api.js";
import {
  cleanBlockReason,
  cleanReasonText,
  isReadingStatus,
  needsRightsTick,
} from "./import.js";
import {
  clear,
  el,
  formatCount,
  formatDuration,
  setStatus,
  statusText,
  statusTone,
} from "./ui.js";

const CSS_ID = "vibecut-studio-check-css";
const POLL_MS = 1800;

export const KIND_LABELS = {
  subtitle: "Burned-in subtitles",
  title: "Title or card",
  lower_third: "Lower third",
  handle_or_logo: "Handle or logo",
  watermark: "Platform watermark",
  credit: "Credit or source mark",
  screen_text: "Screen interface",
};

const RECOMMENDATIONS = {
  clean_then_compose: {
    title: "Clean the old text, then add your own",
    copy: "Text on screen was found where your captions and cards will sit. Cover or blur it before the new edit.",
  },
  compose: {
    title: "Ready for your own edit",
    copy: "No old text needs cleaning. Pick stories and start adding captions, text and effects.",
  },
  music_first: {
    title: "Start with a music bed",
    copy: "There is little or no speech in this source. A music-led story fits it better than captions alone.",
  },
};

const SEVERITY_ORDER = { blocker: 0, warning: 1, info: 2 };

/**
 * Text sampling rate for Check. Word-pop captions change every 0.3–1.5 s,
 * so 0.5 fps missed short words; sources up to 10 min sample at 1 fps.
 * Longer sources stay at 0.5 fps so Check time doesn't double.
 */
export function checkFps(duration) {
  const seconds = Number(duration);
  return Number.isFinite(seconds) && seconds > 0 && seconds <= 600 ? 1 : 0.5;
}

/**
 * Pre-run copy. The old line promised "a few minutes on a long video" even
 * for a 53 s clip; use the measured source length and the real cadence.
 */
export function checkIntroCopy(duration) {
  const seconds = Number(duration);
  if (Number.isFinite(seconds) && seconds > 0) {
    const cadence = checkFps(seconds);
    const every = cadence === 1 ? "second" : "two seconds";
    return `Check reads a ${formatDuration(seconds)} source at one frame every ${every}. `
      + "It reads text, speech, music, faces and picture quality. Check is optional: "
      + "you can open Stories now.";
  }
  return "Check reads the source for text, speech, music, faces and picture quality. "
    + "Reading the source takes longer for a longer video; Check is optional and you can open Stories now.";
}

/** Estimate remaining seconds from progress samples: `[{t, p}]`, both finite. */
export function estimateRemaining(samples) {
  const rows = (Array.isArray(samples) ? samples : [])
    .map((row) => ({ t: Number(row?.t), p: Number(row?.p) }))
    .filter((row) => Number.isFinite(row.t) && Number.isFinite(row.p))
    .sort((left, right) => left.t - right.t);
  if (rows.length < 3) return null;
  const first = rows[0];
  const last = rows[rows.length - 1];
  const span = last.t - first.t;
  if (!(span >= 2.0)) return null;
  const gain = last.p - first.p;
  if (!(gain >= 0.004)) return null;
  const rate = gain / span;
  const raw = (1 - last.p) / rate;
  if (!Number.isFinite(raw) || raw <= 0) return null;
  return Math.max(1, Math.round(Math.min(3600, raw)));
}

/** Keep an ETA from jumping by more than 50% up or 45% down per poll. */
export function smoothEta(raw, previous) {
  if (!Number.isFinite(Number(raw))) return null;
  const value = Math.max(1, Number(raw));
  if (!Number.isFinite(Number(previous)) || Number(previous) <= 0) {
    return Math.max(1, Math.round(value));
  }
  const clamped = Math.min(Number(previous) * 1.5, Math.max(Number(previous) * 0.55, value));
  return Math.max(1, Math.round(Number(previous) * 0.55 + clamped * 0.45));
}

/** One honest ETA line: estimating, measured, or elapsed + stage. */
export function etaText(progress, seconds, elapsed, stage) {
  const fraction = Number(progress);
  if (Number.isFinite(fraction) && fraction < 0.10) return "Estimating time left";
  if (Number.isFinite(Number(seconds)) && Number(seconds) > 0) {
    return `About ${formatDuration(Number(seconds))} left`;
  }
  const name = String(stage || "Reading the source");
  return `${formatDuration(elapsed)} elapsed · ${name}`;
}

/** Plain speech status for the media card, without claiming a wrong fix. */
export function speechStatus(audio) {
  const value = audio || {};
  if (value.transcript) {
    const language = value.language ? ` · ${value.language}` : "";
    return `Read${language}`;
  }
  const state = String(value.speech_state || "unknown");
  if (state === "off") return "Off at import";
  if (state === "engine_empty") return "Engine returned nothing";
  if (state === "no_speech") return "No speech found";
  if (state === "no_audio") return "No sound track";
  return "Not measured";
}

export function ensureCheckStyles() {
  if (document.getElementById(CSS_ID)) return;
  const style = document.createElement("style");
  style.id = CSS_ID;
  style.textContent = `
    .st-check-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.78fr);
      gap: 14px;
      align-items: start;
    }
    .st-check-stack { display: grid; gap: 12px; min-width: 0; }
    .st-check-card { min-width: 0; padding: 16px 18px; }
    .st-check-card > h2 { margin: 0 0 4px; font-size: 14px; font-weight: 620; }
    .st-check-card > h3 { margin: 0 0 4px; font-size: 12.5px; font-weight: 620; }
    .st-check-facts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
      gap: 7px;
      margin-top: 11px;
    }
    .st-check-fact {
      display: grid;
      gap: 2px;
      padding: 8px 10px;
      border: 1px solid var(--st-line);
      border-radius: 8px;
      background: rgba(9, 9, 11, 0.35);
      min-width: 0;
    }
    .st-check-fact span { color: var(--st-dim); font-size: 9.5px; letter-spacing: 0.04em; text-transform: uppercase; }
    .st-check-fact strong { font-size: 12.5px; font-weight: 600; overflow-wrap: anywhere; }
    .st-check-recommend {
      border-color: rgba(232, 162, 102, 0.34);
      background: linear-gradient(180deg, rgba(232, 162, 102, 0.09), rgba(16, 16, 18, 0.96));
    }
    .st-check-recommend p { margin: 6px 0 0; color: var(--st-muted); font-size: 12px; line-height: 1.55; }
    .st-check-reasons { margin: 9px 0 0; padding-left: 18px; color: var(--st-muted); font-size: 11.5px; line-height: 1.55; }
    .st-check-reasons li + li { margin-top: 3px; }
    .st-check-warning {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      padding: 9px 10px;
      border: 1px solid var(--st-line);
      border-radius: 8px;
      background: rgba(9, 9, 11, 0.35);
    }
    .st-check-warning + .st-check-warning { margin-top: 6px; }
    .st-check-warning[data-severity="blocker"] { border-color: rgba(226, 138, 124, 0.42); background: var(--st-bad-soft); }
    .st-check-warning p { margin: 0; color: var(--st-muted); font-size: 11.5px; line-height: 1.5; }
    .st-check-tracklet { display: grid; gap: 8px; padding: 11px; border: 1px solid var(--st-line); border-radius: 9px; background: rgba(9, 9, 11, 0.35); }
    .st-check-tracklet + .st-check-tracklet { margin-top: 8px; }
    .st-check-tracklet-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
    .st-check-tracklet-head strong { min-width: 0; flex: 1 1 auto; font-size: 12px; font-weight: 600; overflow-wrap: anywhere; }
    .st-check-tracklet-meta { display: flex; flex-wrap: wrap; gap: 4px 9px; color: var(--st-dim); font-size: 10px; }
    .st-check-sample { margin: 0; color: var(--st-muted); font-size: 11.5px; line-height: 1.45; overflow-wrap: anywhere; }
    .st-check-box {
      position: relative;
      flex: 0 0 auto;
      width: 34px;
      height: 56px;
      border: 1px solid var(--st-line-2);
      border-radius: 4px;
      background: rgba(9, 9, 11, 0.8);
      overflow: hidden;
    }
    .st-check-box i {
      position: absolute;
      border: 1px solid var(--st-accent);
      background: rgba(232, 162, 102, 0.28);
      border-radius: 1px;
    }
    .st-check-lock {
      display: grid;
      gap: 7px;
      padding: 10px;
      border: 1px dashed var(--st-line-2);
      border-radius: 8px;
      background: rgba(9, 9, 11, 0.3);
    }
    .st-check-lock p { margin: 0; color: var(--st-muted); font-size: 11.5px; line-height: 1.5; }
    .st-check-progress { display: grid; gap: 7px; margin-top: 10px; }
    .st-check-progress p { margin: 0; color: var(--st-muted); font-size: 12px; }
    .st-check-list { display: grid; gap: 6px; margin: 9px 0 0; padding: 0; list-style: none; }
    .st-check-list li { display: grid; gap: 2px; padding: 8px 10px; border: 1px solid var(--st-line); border-radius: 8px; background: rgba(9, 9, 11, 0.3); }
    .st-check-list strong { font-size: 11.5px; font-weight: 600; }
    .st-check-list span { color: var(--st-muted); font-size: 11px; line-height: 1.45; }
    .st-check-head-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .st-check-note { margin: 8px 0 0; color: var(--st-dim); font-size: 10.5px; line-height: 1.45; }
    @media (max-width: 960px) {
      .st-check-layout { grid-template-columns: minmax(0, 1fr); }
    }
  `;
  document.head.append(style);
}

function checkBlueprint() {
  return el("div", { class: "st-check-box", "aria-hidden": "true" });
}

function boxSketch(box) {
  const sketch = checkBlueprint();
  if (!box || typeof box !== "object") return sketch;
  const mark = el("i");
  mark.style.left = `${Math.max(0, Math.min(100, Number(box.x) * 100 || 0))}%`;
  mark.style.top = `${Math.max(0, Math.min(100, Number(box.y) * 100 || 0))}%`;
  mark.style.width = `${Math.max(1, Math.min(100, Number(box.w) * 100 || 1))}%`;
  mark.style.height = `${Math.max(1, Math.min(100, Number(box.h) * 100 || 1))}%`;
  sketch.append(mark);
  return sketch;
}

function rangeText(ranges, limit = 3) {
  const rows = Array.isArray(ranges) ? ranges : [];
  if (!rows.length) return "Whole story";
  const parts = rows.slice(0, limit).map(
    (range) => `${formatDuration(range.start)}–${formatDuration(range.end)}`,
  );
  if (rows.length > limit) parts.push(`+${rows.length - limit} more`);
  return parts.join(" · ");
}

function percent(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${(number * 100).toFixed(digits)}%`;
}

function sortWarnings(warnings) {
  return [...(Array.isArray(warnings) ? warnings : [])].sort(
    (left, right) => (SEVERITY_ORDER[left?.severity] ?? 3) - (SEVERITY_ORDER[right?.severity] ?? 3),
  );
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

export function mount(root, ctx) {
  ensureCheckStyles();

  let disposed = false;
  let timer = 0;
  let job = null;
  let report = null;
  let hasStories = false;
  let loading = false;
  let runPending = false;
  let policy = null;
  let ticks = false;
  let rightsSaving = false;
  let etaSeconds = null;
  let etaSamples = [];
  let etaStartedAt = 0;
  let progressFloor = 0;

  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-check-title">
      <header class="st-panel-head">
        <div class="st-check-head-actions" style="float:right;margin-left:12px">
          <button id="st-check-run" class="st-btn st-btn-primary" type="button">Run Check</button>
        </div>
        <p class="st-eyebrow">Step 2 · Check</p>
        <h1 id="st-check-title">See what the footage needs</h1>
        <p class="st-lede">Check reads the source before any story is cut. It finds old text, speech, music, faces and picture problems, then suggests the smallest fix.</p>
      </header>
      <div id="st-check-body"></div>
      <p id="st-check-status" class="st-status" role="status" aria-live="polite" hidden></p>
      <p id="st-check-error" class="st-error" role="alert" hidden></p>
      <div class="st-actions">
        <button id="st-check-import" class="st-btn st-btn-ghost" type="button">Back to Import</button>
        <button id="st-check-stories" class="st-btn st-btn-ghost" type="button">Open Stories</button>
        <button id="st-check-edit" class="st-btn st-btn-primary" type="button" hidden>Open Edit</button>
      </div>
    </section>
  `;

  const dom = {
    body: root.querySelector("#st-check-body"),
    run: root.querySelector("#st-check-run"),
    status: root.querySelector("#st-check-status"),
    error: root.querySelector("#st-check-error"),
    edit: root.querySelector("#st-check-edit"),
  };

  dom.run.addEventListener("click", () => { void startCheck(true); });
  root.querySelector("#st-check-import").addEventListener("click", () => ctx.go("import"));
  root.querySelector("#st-check-stories").addEventListener("click", () => ctx.go("stories"));
  dom.edit.addEventListener("click", () => ctx.go("edit"));

  function stopPoll() {
    if (timer) window.clearTimeout(timer);
    timer = 0;
  }

  function resetEta() {
    etaSeconds = null;
    etaSamples = [];
    etaStartedAt = 0;
    progressFloor = 0;
  }

  function setBusy(value) {
    loading = Boolean(value);
    dom.run.disabled = loading || runPending;
    dom.run.textContent = loading || runPending ? "Checking…" : "Run Check";
  }

  function showError(message) {
    setStatus(dom.error, message || "", "bad");
  }

  function clearError() {
    setStatus(dom.error, "");
  }

  function showStatus(message, tone = "") {
    setStatus(dom.status, message, tone);
  }

  async function refreshPolicy() {
    if (!job?.id) return;
    try {
      const loaded = await getJob(job.id);
      if (disposed) return;
      if (loaded?.rights_policy && typeof loaded.rights_policy === "object") {
        policy = loaded.rights_policy;
      }
    } catch (_) {
      /* Keep the last server policy; the save itself already failed or won. */
    }
  }

  async function recordRights(jobId) {
    if (!jobId) return false;
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(jobId)}/rights`, {
        method: "POST",
        body: { attested: true, source: "check" },
      });
      const recorded = Boolean(result?.rights?.attested ?? result?.attested);
      if (recorded) await refreshPolicy();
      return recorded;
    } catch (_) {
      return false;
    }
  }

  function isPending(value) {
    const state = String(value?.status || "").toLowerCase();
    if (state === "failed" || state === "cancelled") return false;
    return state === "queued" || state === "running" || value?.complete === false;
  }

  function recommendation(reportValue) {
    const key = String(reportValue?.recommendation || "");
    return RECOMMENDATIONS[key] || {
      title: reportValue?.status === "failed" ? "Check did not finish" : "Check is ready",
      copy: reportValue?.status === "failed"
        ? (reportValue?.error || "The server stopped without a reason.")
        : "Read the findings below, then open Stories.",
    };
  }

  function renderEmpty(title, copy, actionLabel = "", action = "") {
    const card = el("div", { class: "st-empty" }, [
      el("h2", { text: title }),
      el("p", { text: copy }),
    ]);
    if (actionLabel) {
      const button = el("button", { class: "st-btn st-btn-primary", type: "button", text: actionLabel });
      button.addEventListener("click", () => {
        if (action === "run-check") void startCheck(false);
        else ctx.go(action);
      });
      card.append(button);
    }
    clear(dom.body);
    dom.body.append(card);
    dom.run.hidden = true;
  }

  function fact(label, value) {
    return el("div", { class: "st-check-fact" }, [
      el("span", { text: label }),
      el("strong", { text: value }),
    ]);
  }

  function rightsCard() {
    if (!policy) {
      return el("div", { class: "st-card st-check-card" }, [
        el("h2", { text: "Rights" }),
        el("p", { class: "st-hint", text: "Reading the rights policy…" }),
      ]);
    }
    // The tick appears only while the server says the lock is on and this
    // video has no rights note. With the lock off there is nothing to tick.
    if (!needsRightsTick(policy)) return null;

    const input = el("input", {
      type: "checkbox",
      checked: ticks,
      disabled: rightsSaving,
    });
    input.addEventListener("change", () => {
      ticks = Boolean(input.checked);
      if (!ticks || !job?.id) {
        showStatus("");
        renderReport();
        return;
      }
      rightsSaving = true;
      showStatus("Recording the rights note…", "busy");
      void recordRights(job.id).then((recorded) => {
        if (disposed) return;
        rightsSaving = false;
        if (recorded) {
          ticks = false;
          showStatus("Rights note recorded for this video. Clean is open.", "ok");
        } else {
          showStatus("The server could not record the rights note. Try again.", "bad");
        }
        renderReport();
        ctx.refreshSteps?.();
      });
    });

    const card = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "Rights" }),
      el("p", { class: "st-hint", text: "The rights lock is on. Cleaning old text needs a rights note for this video." }),
      el("label", { class: "st-check st-attest" }, [
        input,
        el("span", {}, [
          el("strong", { text: "I own this footage or have the rights to it." }),
          el("small", { text: "Stored on the server for this video. Watermarks are still never removed." }),
        ]),
      ]),
      el("div", { class: "st-check-lock" }, [
        el("strong", { text: "Clean is locked" }),
        el("p", { text: "Confirm the box to unlock Clean for this video. You can still open Stories and Edit and add your own text." }),
      ]),
    ]);
    return card;
  }

  function recommendationCard(reportValue) {
    const copy = recommendation(reportValue);
    const card = el("div", { class: "st-card st-check-card st-check-recommend" }, [
      el("h2", { text: copy.title }),
      el("p", { text: copy.copy }),
    ]);
    const reasons = Array.isArray(reportValue?.recommendation_reasons)
      ? reportValue.recommendation_reasons.filter(Boolean)
      : [];
    if (reasons.length) {
      card.append(el("ul", { class: "st-check-reasons" }, reasons.map(
        (reason) => el("li", { text: String(reason) }),
      )));
    }
    return card;
  }

  function trackletCard(tracklet) {
    const kind = String(tracklet?.kind || "");
    const blocked = kind === "watermark";
    const badge = el("span", {
      class: `st-chip${blocked ? " st-chip-bad" : kind === "handle_or_logo" ? " st-chip-busy" : ""}`,
      text: KIND_LABELS[kind] || "On-screen text",
    });
    const confidence = Number(tracklet?.confidence);
    const meta = [
      rangeText(tracklet?.ranges),
      Number.isFinite(confidence) ? `${Math.round(confidence * 100)}% confidence` : "",
      tracklet?.approximate ? "approximate box" : "",
    ].filter(Boolean);

    const card = el("div", { class: "st-check-tracklet" }, [
      el("div", { class: "st-check-tracklet-head" }, [
        badge,
        el("strong", { text: tracklet?.text_sample || "No words read" }),
        boxSketch(tracklet?.box),
      ]),
      el("div", { class: "st-check-tracklet-meta" }, meta.map(
        (text) => el("span", { text }),
      )),
    ]);
    if (blocked) {
      card.append(el("p", { class: "st-check-sample", text: cleanReasonText(cleanBlockReason(policy, kind), policy) }));
    } else if (kind === "handle_or_logo") {
      const reason = cleanBlockReason(policy, kind);
      if (reason) {
        card.append(el("p", { class: "st-check-sample", text: cleanReasonText(reason, policy) }));
      }
    }
    return card;
  }

  function findingsCard(reportValue) {
    const tracklets = Array.isArray(reportValue?.tracklets) ? reportValue.tracklets : [];
    const card = el("div", { class: "st-card st-check-card" });
    const text = reportValue?.text || {};
    card.append(el("h2", { text: "Text on screen" }));
    if (text.confirmed && !tracklets.length) {
      card.append(el("p", { class: "st-hint", text: "No on-screen text was found in the sampled pass." }));
      return card;
    }
    if (!text.confirmed) {
      card.append(el("p", { class: "st-hint", text: "The full text pass did not run, so an empty result is unconfirmed." }));
    }
    card.append(el("p", { class: "st-hint", text: `${formatCount(tracklets.length, "region")} found. Edit keeps every one available in the Clean layer.` }));
    if (tracklets.length) {
      const list = el("div", { style: "margin-top:10px" });
      for (const tracklet of tracklets.slice(0, 40)) list.append(trackletCard(tracklet));
      card.append(list);
      if (tracklets.length > 40) {
        const rest = tracklets.slice(40);
        const more = el("button", {
          class: "st-btn st-btn-quiet st-btn-small",
          type: "button",
          text: `Show all ${tracklets.length} regions`,
          style: "margin-top:8px",
        });
        more.addEventListener("click", () => {
          for (const tracklet of rest) list.append(trackletCard(tracklet));
          more.remove();
        });
        card.append(more);
      }
    }
    return card;
  }

  function warningsCard(reportValue) {
    const warnings = sortWarnings(reportValue?.warnings);
    const issues = Array.isArray(reportValue?.quality?.issues) ? reportValue.quality.issues : [];
    const seen = new Set(warnings.map((item) => `${item?.code}:${item?.message}`));
    for (const issue of issues) {
      const key = `${issue?.code}:${issue?.message}`;
      if (!seen.has(key)) {
        warnings.push(issue);
        seen.add(key);
      }
    }
    if (!warnings.length) {
      return el("div", { class: "st-card st-check-card" }, [
        el("h2", { text: "Warnings" }),
        el("p", { class: "st-hint", text: "Nothing needs attention." }),
      ]);
    }
    const card = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "Warnings" }),
      el("p", { class: "st-hint", text: "These are advisory. Edit stays open." }),
    ]);
    const list = el("div", { style: "margin-top:10px" });
    for (const warning of warnings) list.append(warningNode(warning));
    card.append(list);
    return card;
  }

  function mediaCard(reportValue) {
    const audio = reportValue?.audio || {};
    const faces = reportValue?.faces || {};
    const quality = reportValue?.quality || {};
    const rows = [];
    if (!audio.transcript) {
      rows.push(["Speech", speechStatus(audio)]);
    } else if (Number.isFinite(Number(audio.speech_ratio))) {
      rows.push(["Speech", `${percent(audio.speech_ratio)}${audio.language ? ` · ${audio.language}` : ""}`]);
    } else {
      rows.push(["Speech", speechStatus(audio)]);
    }
    if (audio.music && typeof audio.music === "object") {
      rows.push(["Music", audio.music.present ? `Found${Number.isFinite(Number(audio.music.score)) ? ` · score ${Number(audio.music.score).toFixed(2)}` : ""}` : "Not found"]);
    }
    rows.push(["Faces", faces.present ? `${formatCount(faces.count, "face")} · ${percent(faces.coverage)}` : "None found"]);
    if (quality.orientation) rows.push(["Shape", quality.orientation]);
    if (quality.bitrate_mbps) rows.push(["Bitrate", `${Number(quality.bitrate_mbps).toFixed(1)} Mbps`]);

    const card = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "Sound, faces and picture" }),
    ]);
    const facts = el("div", { class: "st-check-facts" });
    for (const [label, value] of rows) facts.append(fact(label, value));
    card.append(facts);
    return card;
  }

  function runningCard(reportValue) {
    const reported = Math.max(0, Math.min(1, Number(reportValue?.progress) || 0));
    const progress = Math.max(progressFloor, reported);
    progressFloor = progress;
    if (!etaStartedAt) etaStartedAt = Date.now() / 1000;
    const now = Date.now() / 1000;
    etaSamples.push({ t: now - etaStartedAt, p: progress });
    etaSamples = etaSamples.slice(-16);
    etaSeconds = smoothEta(estimateRemaining(etaSamples), etaSeconds);
    const stage = reportValue?.message || "Reading the source";
    const card = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "Checking the source" }),
      el("p", { class: "st-hint", text: stage }),
    ]);
    if (job?.source?.duration) {
      card.append(el("p", { class: "st-hint", text: `Source length ${formatDuration(job.source.duration)} · one pass, no re-import needed.` }));
    }
    const track = el("div", { class: "st-progress-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(progress * 100)) });
    track.append(el("i", { style: `width:${Math.round(progress * 100)}%` }));
    card.append(el("div", { class: "st-check-progress" }, [
      track,
      el("p", { class: "st-mono", text: `${Math.round(progress * 100)}% · ${etaText(progress, etaSeconds, now - etaStartedAt, stage)}` }),
    ]));
    const stopping = /^Stopping/.test(stage);
    const cancel = el("button", {
      class: "st-btn st-btn-ghost",
      type: "button",
      text: stopping ? "Stopping…" : "Cancel Check",
      style: "margin-top:10px",
      disabled: stopping,
    });
    cancel.addEventListener("click", () => { void cancelCheck(cancel); });
    card.append(cancel);
    return card;
  }

  async function cancelCheck(button) {
    if (!job?.id) return;
    button.disabled = true;
    button.textContent = "Stopping…";
    clearError();
    try {
      await request(`/api/jobs/${encodeURIComponent(job.id)}/check/cancel`, { method: "POST" });
      if (disposed) return;
      showStatus("Stopping Check… it ends at the next batch of frames.", "busy");
      await refreshReport({ quiet: true });
    } catch (error) {
      if (disposed) return;
      button.disabled = false;
      button.textContent = "Cancel Check";
      showError(error?.message || "Could not cancel Check.");
    }
  }

  function syncRunButton() {
    dom.run.hidden = !job;
    dom.run.disabled = loading || runPending;
    dom.run.textContent = runPending ? "Checking…" : "Run Check";
  }

  function renderReport() {
    clear(dom.body);
    dom.edit.hidden = !hasStories;
    syncRunButton();
    if (!report) {
      renderEmpty(
        "Check has not run",
        checkIntroCopy(job?.source?.duration),
        "Run Check",
        "run-check",
      );
      dom.run.hidden = false;
      dom.run.disabled = loading || runPending;
      return;
    }
    if (String(report.status || "").toLowerCase() === "failed") {
      const card = el("div", { class: "st-card st-check-card" }, [
        el("h2", { text: "Check did not finish" }),
        el("p", { text: report.error || "The server stopped without a reason." }),
      ]);
      const retry = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Try Check again", style: "margin-top:10px" });
      retry.addEventListener("click", () => { void startCheck(true); });
      card.append(retry);
      dom.body.append(card);
      return;
    }
    if (String(report.status || "").toLowerCase() === "cancelled") {
      renderEmpty(
        "Check was cancelled",
        "Nothing was saved from that pass. Run Check again when you are ready, or open Stories without it.",
        "Run Check",
        "run-check",
      );
      return;
    }
    if (isPending(report)) {
      dom.body.append(runningCard(report));
      return;
    }

    const layout = el("div", { class: "st-check-layout" });
    const main = el("div", { class: "st-check-stack" });
    const side = el("div", { class: "st-check-stack" });
    main.append(recommendationCard(report));
    main.append(findingsCard(report));
    main.append(warningsCard(report));
    main.append(mediaCard(report));
    const rights = rightsCard();
    if (rights) side.append(rights);

    const facts = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "Source" }),
    ]);
    const grid = el("div", { class: "st-check-facts" });
    const source = report.source || {};
    if (source.duration) grid.append(fact("Length", formatDuration(source.duration)));
    if (source.width && source.height) grid.append(fact("Frame", `${source.width}×${source.height}`));
    if (source.fps) grid.append(fact("Rate", `${Number(source.fps).toFixed(2)} fps`));
    if (report.text && Number.isFinite(Number(report.text.coverage))) {
      grid.append(fact("Text coverage", percent(report.text.coverage)));
    }
    facts.append(grid);
    side.append(facts);

    const guide = el("div", { class: "st-card st-check-card" }, [
      el("h2", { text: "What happens next" }),
      el("ul", { class: "st-check-list" }, [
        el("li", {}, [
          el("strong", { text: "Old text becomes Clean layers" }),
          el("span", { text: "Open Edit → Clean to cover, blur or crop the text Check found. Nothing is applied twice." }),
        ]),
        el("li", {}, [
          el("strong", { text: "Watermarks are refused" }),
          el("span", { text: "Use your original file — it has no watermark. VibeCut never removes a platform mark." }),
        ]),
        el("li", {}, [
          el("strong", { text: "Every finding is advisory" }),
          el("span", { text: "You can ignore Check and edit the story your way." }),
        ]),
      ]),
    ]);
    side.append(guide);

    layout.append(main, side);
    dom.body.append(layout);
    dom.body.append(el("p", {
      class: "st-check-note",
      text: `Checked in ${Number(report.timings?.total || 0).toFixed(1)}s · ${report.engine?.vision ? "Vision text read" : "Vision text read unavailable"}`,
    }));
  }

  async function refreshReport({ quiet = false } = {}) {
    if (!job?.id) return;
    if (!quiet) showStatus("Reading the latest Check…");
    try {
      let payload = null;
      let pending = false;
      try {
        payload = await request(`/api/jobs/${encodeURIComponent(job.id)}/check`);
      } catch (error) {
        if (error?.status === 404) payload = null;
        else if (error?.status === 202 || error?.status === 500) {
          payload = error.detail && typeof error.detail === "object" ? error.detail : null;
          pending = Boolean(payload);
          if (!payload) throw error;
        } else throw error;
      }
      if (disposed) return;
      const wasPending = runPending;
      report = payload;
      runPending = Boolean(pending || isPending(report));
      if (runPending && !wasPending) resetEta();
      renderReport();
      if (isPending(report)) {
        showStatus(report.message || "Check is running…", "busy");
        schedulePoll();
      } else {
        showStatus("");
        if (wasPending) ctx.refreshSteps?.();
      }
    } catch (error) {
      if (disposed) return;
      runPending = false;
      renderReport();
      showError(error?.message || "Could not read Check.");
    }
  }

  async function startCheck(force) {
    if (!job?.id || loading) return;
    clearError();
    resetEta();
    loading = true;
    runPending = true;
    setBusy(true);
    showStatus("Running Check…", "busy");
    try {
      let payload = null;
      try {
        payload = await request(`/api/jobs/${encodeURIComponent(job.id)}/check`, {
          method: "POST",
          body: {
            force: Boolean(force),
            sample_text: true,
            fps: checkFps(job?.source?.duration),
          },
        });
      } catch (error) {
        if (error?.status === 202 || error?.status === 500) {
          payload = error.detail && typeof error.detail === "object" ? error.detail : null;
          if (!payload) throw error;
        } else throw error;
      }
      if (disposed) return;
      report = payload;
      runPending = isPending(report);
      renderReport();
      if (isPending(report)) {
        showStatus(report.message || "Queued for Check…", "busy");
        schedulePoll();
      } else {
        showStatus("Check finished.", "ok");
        ctx.refreshSteps?.();
      }
    } catch (error) {
      if (disposed) return;
      runPending = false;
      showError(error?.message || "Check could not start.");
      showStatus("");
      syncRunButton();
    } finally {
      if (!disposed) {
        loading = false;
        setBusy(false);
      }
    }
  }

  function schedulePoll() {
    stopPoll();
    if (disposed) return;
    timer = window.setTimeout(() => { void refreshReport({ quiet: true }); }, POLL_MS);
  }

  async function boot() {
    const jobId = ctx.getJobId();
    if (!jobId) {
      renderEmpty("No video open", "Import a video first. Check reads the source before stories are cut.", "Go to Import", "import");
      return;
    }
    clear(dom.body);
    dom.body.append(el("p", { class: "st-hint", text: "Reading this video…" }));
    try {
      const [loadedJob, sets] = await Promise.all([
        getJob(jobId),
        listClipSets(jobId).catch(() => null),
      ]);
      if (disposed) return;
      job = loadedJob;
      ctx.updateJob({ name: loadedJob?.source?.name || loadedJob?.name || "", status: loadedJob?.status });
      hasStories = Boolean(
        (sets?.clip_sets || []).some(
          (set) => Array.isArray(set?.stories) && set.stories.length,
        ),
      );
      // The job's server policy carries this video's attestation. The global
      // policy is only a fallback when an older server omits the field.
      policy = loadedJob?.rights_policy && typeof loadedJob.rights_policy === "object"
        ? loadedJob.rights_policy
        : null;
      if (!policy) {
        try {
          const fallback = await request("/api/rights/policy");
          if (fallback && typeof fallback === "object") policy = fallback;
        } catch (_) {
          /* The report still renders; Clean stays locked until policy loads. */
        }
        if (disposed) return;
      }
      if (job.status !== "ready") {
        clear(dom.body);
        dom.run.hidden = true;
        dom.edit.hidden = true;
        const card = el("div", { class: "st-card st-check-card" }, [
          el("h2", { text: job.status === "failed" ? "This video could not be read" : "This video is still being read" }),
          el("p", { class: "st-hint", text: job.error || job.message || "Wait for the read to finish, then open Check." }),
          el("span", {
            class: `st-chip st-chip-${statusTone(job.status)}`,
            text: statusText(job.status),
          }),
        ]);
        if (isReadingStatus(job.status)) {
          const cancel = el("button", {
            class: "st-btn st-btn-ghost",
            type: "button",
            text: "Cancel reading",
            style: "margin-top:10px",
          });
          cancel.addEventListener("click", () => {
            cancel.disabled = true;
            showStatus("Stopping the read…", "busy");
            void request(`/api/jobs/${encodeURIComponent(job.id)}/reading/cancel`, {
              method: "POST",
            }).then(() => {
              if (!disposed) showStatus("Stopping… the running ffmpeg will close.", "busy");
            }).catch((error) => {
              cancel.disabled = false;
              showError(error?.message || "Could not stop the read.");
            });
          });
          card.append(cancel);
        }
        dom.body.append(card);
        return;
      }
      dom.run.hidden = false;
      await refreshReport({ quiet: true });
    } catch (error) {
      if (disposed) return;
      if (error?.status === 404) {
        renderEmpty("This video is no longer on file", "Choose another video from Import.", "Go to Import", "import");
        return;
      }
      showError(error?.message || "Could not open Check.");
    }
  }

  void boot();

  return () => {
    disposed = true;
    stopPoll();
  };
}
