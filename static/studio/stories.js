/**
 * Studio — Stories.
 *
 * Works on the existing story routes:
 *   GET  /api/jobs/{id}
 *   GET  /api/jobs/{id}/status
 *   GET  /api/jobs/{id}/clip-sets
 *   POST /api/jobs/{id}/clip-sets
 *   POST /api/jobs/{id}/clip-sets/{set}/stories/{story}/trim
 *   POST /api/jobs/{id}/clip-sets/{set}/stories/{story}/render
 *   POST /api/story-queues
 *
 * Stories ± moves the range through the same atomic trim route as the Edit
 * timeline. Nothing here PATCHes a range on its own.
 */

import {
  addStory,
  createClipSet,
  createStoryQueue,
  deleteClipSet,
  getCheckReport,
  getJob,
  getJobStatus,
  invalidateReadCache,
  listClipSets,
  patchClipSet,
  renderStory,
  request,
  transcribeJob,
  trimErrorCode,
  writeScriptBrief,
  trimStory,
} from "./api.js";
import {
  clear,
  el,
  formatCount,
  formatDuration,
  setStatus,
  statusText,
  statusTone,
} from "./ui.js";
import { sentenceSegments } from "./edit/model.js";

const POLL_MS = 1600;
const EDIT_CHOICE_KEY = "vibecut.studio.edit.choice";
const SHAPE_KEY = "vibecut.studio.moments.shape";

export const STORY_SHAPES = [
  { value: "9:16", label: "9:16 vertical" },
  { value: "4:5", label: "4:5 feed" },
  { value: "1:1", label: "1:1 square" },
  { value: "16:9", label: "16:9 wide" },
  { value: "16:10", label: "16:10 wide" },
];

/** Mirrors `clipset.LENGTH_PRESETS`; "auto" is the server default window. */
export const LENGTH_PRESETS = {
  auto: { label: "Auto · 20–75 s", min: 20, max: 75 },
  short: { label: "Short · 15–30 s", min: 15, max: 30 },
  medium: { label: "Medium · 30–60 s", min: 30, max: 60 },
  long: { label: "Long · 45–90 s", min: 45, max: 90 },
  extended: { label: "Extended · 90–180 s", min: 90, max: 180 },
  custom: { label: "Custom range", min: 15, max: 180 },
};

/**
 * A story's sentence ids after moving one edge by one sentence.
 * Sentence ids run in source order, so the start edge grows to `first - 1`
 * and the end edge to `last + 1`. A story never drops below one sentence.
 */
export function adjustSentences(ids, edge, delta) {
  const rows = (Array.isArray(ids) ? ids : [])
    .map((value) => Number(typeof value === "object" && value ? value.id : value))
    .filter(Number.isInteger)
    .sort((left, right) => left - right);
  if (!rows.length) return null;
  if (edge === "start") {
    if (delta < 0) return rows[0] > 0 ? [rows[0] - 1, ...rows] : null;
    return rows.length > 1 ? rows.slice(1) : null;
  }
  if (delta > 0) return [...rows, rows[rows.length - 1] + 1];
  return rows.length > 1 ? rows.slice(0, -1) : null;
}

/** Which preset a stored set was built with, or "auto". */
export function lengthPreset(set) {
  const min = Number(set?.min_s);
  const max = Number(set?.max_s);
  const match = Object.entries(LENGTH_PRESETS).find(
    ([, preset]) => preset.min === min && preset.max === max,
  );
  return match ? match[0] : "auto";
}

/**
 * Group the story's output-time sentence segments by sentence id.
 *
 * A sentence split across scenes has one clip per scene; the trim handles sit
 * on the sentence edges, not the clip edges. The rows stay in output order, so
 * a manually reordered story keeps its order.
 */
export function sentenceSpans(story) {
  const spans = [];
  for (const segment of sentenceSegments(story)) {
    const id = segment.sentenceId ?? null;
    const last = spans[spans.length - 1];
    if (last && last.id === id) {
      last.end = segment.end;
      continue;
    }
    spans.push({
      id,
      index: spans.length,
      start: Number(segment.start) || 0,
      end: Number(segment.end) || 0,
      text: segment.text || "",
    });
  }
  return spans;
}

/** Nearest sentence bound to `time` for one edge of the trim range. */
export function nearestSentenceBoundary(spans, edge, time, low = 0, high = spans.length - 1) {
  if (!Array.isArray(spans) || !spans.length) return null;
  const first = Math.max(0, Math.min(spans.length - 1, Number(low) || 0));
  const last = Math.max(first, Math.min(spans.length - 1, Number(high) || 0));
  const value = Number(time) || 0;
  let best = first;
  let distance = Infinity;
  for (let index = first; index <= last; index += 1) {
    const bound = edge === "start" ? spans[index].start : spans[index].end;
    const gap = Math.abs(bound - value);
    if (gap < distance) {
      best = index;
      distance = gap;
    }
  }
  return best;
}

/**
 * Trim the story to whole sentences between two span indices.
 * Returns null when the range is empty or a clip has no sentence id.
 */
export function trimStoryRange(story, startIndex, endIndex) {
  const spans = sentenceSpans(story);
  if (!spans.length) return null;
  const start = Math.max(0, Math.min(spans.length - 1, Number(startIndex) || 0));
  const end = Math.max(start, Math.min(spans.length - 1, Number(endIndex) || 0));
  const rows = spans.slice(start, end + 1);
  const sentences = rows.map((row) => row.id);
  if (sentences.some((id) => id === null || id === undefined)) return null;
  const ids = [...new Set(sentences)];
  if (ids.length !== sentences.length) return null;
  const spanStart = rows[0].start;
  const spanEnd = rows[rows.length - 1].end;
  return {
    sentences: ids,
    startIndex: start,
    endIndex: end,
    start: spanStart,
    end: spanEnd,
    duration: Math.max(0.05, spanEnd - spanStart),
  };
}

/** Layer row ids that cross or sit outside the trimmed story window. */
export function outsideLayerIds(rows, start, end) {
  const low = Number(start) || 0;
  const high = Number(end) || 0;
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => {
      const rowStart = Number(row?.start) || 0;
      const rowEnd = Number(row?.end) || rowStart;
      return rowStart < low - 0.001 || rowEnd > high + 0.001;
    })
    .map((row) => String(row.layerId ?? row.id ?? ""));
}

/**
 * One plain sentence for the trim receipt, for example
 * "Moved 3 layers · 1 hidden outside · captions: 12 kept, 2 added".
 * Never claims a layer was deleted: outside layers are hidden, not removed.
 */
export function receiptSummary(receipt) {
  if (!receipt || typeof receipt !== "object") return "";
  const layers = receipt.layers || {};
  const count = (value) => (Array.isArray(value) ? value.length : 0);
  const parts = [];
  const moved = count(layers.moved);
  const clipped = count(layers.clipped);
  const outside = count(layers.outside);
  const pinned = count(layers.pinned);
  if (moved) parts.push(`Moved ${formatCount(moved, "layer")}`);
  if (clipped) parts.push(`${clipped} clipped`);
  if (outside) parts.push(`${outside} hidden outside`);
  if (pinned) parts.push(`${pinned} pinned`);
  const captions = receipt.captions;
  if (captions && typeof captions === "object") {
    const caption = `${Number(captions.kept) || 0} kept, ${Number(captions.added) || 0} added`;
    const dropped = Number(captions.dropped) || 0;
    parts.push(`captions: ${caption}${dropped ? `, ${dropped} dropped` : ""}`);
  }
  if (!parts.length) return "The story range changed.";
  return parts.join(" · ");
}

function readSetShapes() {
  try {
    const value = JSON.parse(localStorage.getItem(SHAPE_KEY) || "{}");
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
  } catch (_) {
    /* A private window may refuse storage; 9:16 is the safe default. */
  }
  return {};
}

export function mount(root, ctx) {
  let disposed = false;
  let timer = 0;
  let job = null;
  let sets = [];
  let activeSetId = "";
  let loading = false;
  let transcribing = false;
  let scripting = false;
  let briefDraft = null;
  // One persisted shape per set. Every queue action and every Edit hand-off
  // for this set uses it, so a card and Queue all cannot disagree.
  let setShapes = readSetShapes();
  let checkReport = null;
  let checkError = "";
  let checkBusy = false;
  let checkTimer = 0;

  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-stories-title">
      <header class="st-panel-head st-panel-head-row">
        <div>
          <p class="st-eyebrow">Step 2 · Moments</p>
          <h1 id="st-stories-title">Find the moments</h1>
          <p class="st-lede">Every moment is a complete beat: a frame, its hook and payoff, the text already on screen, and the shape it will render in. Pick one, tune the range, or build your own from scenes.</p>
        </div>
        <div id="st-moment-actions" class="st-panel-actions"></div>
      </header>
      <div id="st-story-body" class="st-story-body"></div>
      <p id="st-story-status" class="st-status" role="status" aria-live="polite" hidden></p>
      <p id="st-story-error" class="st-error" role="alert" hidden></p>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    body: $("#st-story-body"),
    actions: $("#st-moment-actions"),
    status: $("#st-story-status"),
    error: $("#st-story-error"),
  };

  function stopPoll() {
    if (timer) window.clearTimeout(timer);
    timer = 0;
  }

  function showError(message) {
    setStatus(dom.error, message, "bad");
  }

  function clearError() {
    setStatus(dom.error, "");
  }

  function showStatus(message, tone = "") {
    setStatus(dom.status, message, tone);
  }

  function schedulePoll() {
    stopPoll();
    if (disposed) return;
    timer = window.setTimeout(refreshStatus, POLL_MS);
  }

  function sourceName(value) {
    return value?.source?.name || value?.name || "This video";
  }

  function announceJob() {
    if (!job) return;
    ctx.updateJob({ name: sourceName(job), status: job.status });
  }

  function emptyNoJob() {
    clear(dom.body);
    const card = el("div", { class: "st-empty" }, [
      el("h2", { text: "No video open" }),
      el("p", { text: "Import a video first. Moments need a finished read of the footage." }),
    ]);
    const button = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Go to Import" });
    button.addEventListener("click", () => ctx.go("import"));
    card.append(button);
    dom.body.append(card);
  }

  function waitingCard(status) {
    const progress = Math.max(0, Math.min(1, Number(status?.progress) || 0));
    const card = el("div", { class: "st-card st-waiting" }, [
      el("div", { class: "st-card-head" }, [
        el("h2", { text: "Reading the video" }),
        el("span", { class: `st-chip st-chip-${statusTone(status?.status)}`, text: statusText(status?.status) }),
      ]),
      el("p", { class: "st-hint", text: status?.message || "Finding speech, scenes and text." }),
    ]);
    const track = el("div", { class: "st-progress-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(progress * 100)) });
    track.append(el("i", { style: `width:${Math.round(progress * 100)}%` }));
    card.append(track, el("p", {
      class: "st-mono st-progress-label",
      text: `${Math.round(progress * 100)}%`,
    }));
    clear(dom.body);
    dom.body.append(card);
  }

  function failedCard(value) {
    stopPoll();
    clear(dom.body);
    const card = el("div", { class: "st-card st-empty" }, [
      el("h2", { text: "The video could not be read" }),
      el("p", { text: value?.error || value?.message || "The server stopped without a reason." }),
    ]);
    const button = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Import another video" });
    button.addEventListener("click", () => ctx.go("import"));
    card.append(button);
    dom.body.append(card);
  }

  function activeShape() {
    const value = setShapes[String(activeSetId || "")];
    return STORY_SHAPES.some((shape) => shape.value === value) ? value : "9:16";
  }

  function rememberShape(value) {
    if (!STORY_SHAPES.some((shape) => shape.value === value)) return;
    setShapes = { ...setShapes, [String(activeSetId || "")]: value };
    try {
      localStorage.setItem(SHAPE_KEY, JSON.stringify(setShapes));
    } catch (_) {
      /* The current screen still holds the choice. */
    }
  }

  function openInEdit(story, shape = activeShape()) {
    // Edit reads this choice on open; the shape follows the set picker.
    try {
      localStorage.setItem(EDIT_CHOICE_KEY, JSON.stringify({
        setId: activeSetId,
        storyId: story.id,
        aspect: STORY_SHAPES.some((item) => item.value === shape) ? shape : "9:16",
      }));
    } catch (_) {
      /* Edit falls back to the first story. */
    }
    ctx.go("edit", { force: true });
  }

  function sceneAt(time) {
    const scenes = Array.isArray(job?.analysis?.scenes) ? job.analysis.scenes : [];
    return scenes.find((scene) => Number(scene.start) <= time && time < Number(scene.end))
      || scenes.find((scene) => Number(scene.end) > time)
      || scenes[0]
      || null;
  }

  function trackletsFor(story, limit = 4) {
    const rows = Array.isArray(checkReport?.tracklets) ? checkReport.tracklets : [];
    const start = Number(story?.start) || 0;
    const end = Number(story?.end) || start;
    return rows.filter((item) => {
      const ranges = Array.isArray(item?.ranges) ? item.ranges : [];
      if (!ranges.length) return true;
      return ranges.some((range) => Number(range.end) > start && Number(range.start) < end);
    }).slice(0, limit);
  }

  function momentFrame(story, index) {
    const scene = sceneAt(Number(story?.start) || 0);
    if (!scene?.thumb_url) return null;
    const figure = el("figure", { class: "st-moment-frame" });
    const source = job?.source || {};
    if (Number(source.width) > 0 && Number(source.height) > 0) {
      figure.style.aspectRatio = `${Number(source.width)} / ${Number(source.height)}`;
    }
    figure.append(el("img", {
      src: scene.thumb_url,
      alt: `Frame at the start of moment ${index + 1}`,
      loading: "lazy",
    }));
    for (const tracklet of trackletsFor(story)) {
      const box = tracklet?.box;
      if (!box || typeof box !== "object") continue;
      const mark = el("i", {
        class: "st-moment-box",
        title: tracklet.text_sample || "Text found here",
      });
      mark.style.left = `${Math.max(0, Math.min(100, Number(box.x) * 100 || 0))}%`;
      mark.style.top = `${Math.max(0, Math.min(100, Number(box.y) * 100 || 0))}%`;
      mark.style.width = `${Math.max(1, Math.min(100, Number(box.w) * 100 || 1))}%`;
      mark.style.height = `${Math.max(1, Math.min(100, Number(box.h) * 100 || 1))}%`;
      figure.append(mark);
    }
    if (checkReport?.audio?.music?.present) {
      figure.append(el("span", { class: "st-moment-tag st-moment-sfx", text: "Music bed" }));
    }
    if (trackletsFor(story, 1).length) {
      figure.append(el("span", { class: "st-moment-tag st-moment-text", text: "Text here" }));
    }
    return figure;
  }

  // One read of the scan. A queued or running pass keeps polling; a
  // cancelled or failed one has no findings to show (a cancelled re-run comes
  // back "ready" with the last report).
  function takeCheck(report, { announce = false } = {}) {
    const state = String(report?.status || "");
    if (state === "queued" || state === "running") {
      checkReport = report;
      checkBusy = true;
      return true;
    }
    checkReport = state === "cancelled" || state === "failed" ? null : report;
    if (announce && state === "cancelled") checkError = "Scan cancelled. Nothing was saved from it.";
    if (state === "failed") checkError = report?.error || "The scan stopped without a reason.";
    checkBusy = false;
    return false;
  }

  function followCheck() {
    stopCheckPoll();
    checkTimer = window.setTimeout(async () => {
      if (disposed) return;
      try {
        if (takeCheck(await getCheckReport(job.id), { announce: true })) {
          followCheck();
          return;
        }
      } catch (error) {
        checkBusy = false;
        checkError = error?.message || "Could not read the scan.";
      }
      stopCheckPoll();
      if (!disposed) renderStories();
    }, 1800);
  }

  async function loadCheck() {
    if (!job?.id) return;
    try {
      checkError = "";
      if (takeCheck(await getCheckReport(job.id))) followCheck();
    } catch (error) {
      checkReport = null;
      checkError = Number(error?.status) === 404 ? "" : (error?.message || "");
    }
  }

  function stopCheckPoll() {
    if (checkTimer) window.clearTimeout(checkTimer);
    checkTimer = 0;
  }

  async function refreshCheck(button) {
    if (!job?.id || checkBusy) return;
    checkBusy = true;
    if (button) {
      button.disabled = true;
      button.textContent = "Scanning…";
    }
    checkError = "";
    // "Scan again" must re-run; without force the server returns the last report.
    const force = Boolean(checkReport);
    try {
      await request(`/api/jobs/${encodeURIComponent(job.id)}/check`, {
        method: "POST",
        body: { sample_text: true, force },
      });
      followCheck();
    } catch (error) {
      checkBusy = false;
      checkError = error?.message || "Could not start the scan.";
    }
    // Show the busy card with its Cancel scan button, or the error.
    if (!disposed) renderStories();
  }

  async function cancelCheck(button) {
    if (!job?.id) return;
    button.disabled = true;
    button.textContent = "Stopping…";
    try {
      await request(`/api/jobs/${encodeURIComponent(job.id)}/check/cancel`, { method: "POST" });
    } catch (error) {
      button.disabled = false;
      button.textContent = "Cancel scan";
      checkError = error?.message || "Could not cancel the scan.";
      renderStories();
    }
  }

  function scanStatusText() {
    if (checkBusy) return { text: "Checking text…", tone: "busy" };
    if (checkError) return { text: "Scan needs attention", tone: "bad" };
    if (checkReport) {
      const count = Array.isArray(checkReport.tracklets) ? checkReport.tracklets.length : 0;
      return {
        text: count ? `${formatCount(count, "text region")} found` : "No on-screen text",
        tone: count ? "ok" : "quiet",
      };
    }
    return { text: "Text not scanned", tone: "quiet" };
  }

  function renderScanAction() {
    if (!dom.actions) return;
    if (!job || job.status !== "ready") {
      dom.actions.replaceChildren();
      return;
    }
    const state = scanStatusText();
    const chip = el("span", {
      class: `st-chip st-chip-${state.tone}`,
      text: state.text,
    });
    const button = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: checkBusy ? "Cancel scan" : checkReport ? "Scan again" : "Scan for text",
      disabled: false,
    });
    button.addEventListener("click", () => {
      if (checkBusy) void cancelCheck(button);
      else void refreshCheck(button);
    });
    dom.actions.replaceChildren(chip, button);
  }

  function checkCard() {
    const card = el("div", { class: "st-card st-moment-check" });
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { text: checkReport ? "Footage notes" : "Scan the footage" }),
        el("p", {
          class: "st-hint",
          text: checkReport
            ? "Text and sound the moments already carry. Boxes show where old text sits on the frame."
            : "Optional: find old text, music and picture issues before you pick a moment.",
        }),
      ]),
    ]);
    const scan = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: checkBusy ? "Scanning…" : checkReport ? "Scan again" : "Scan footage",
      disabled: checkBusy,
    });
    scan.addEventListener("click", () => { void refreshCheck(scan); });
    head.append(scan);
    if (checkBusy) {
      const cancel = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Cancel scan" });
      cancel.addEventListener("click", () => { void cancelCheck(cancel); });
      head.append(cancel);
    }
    card.append(head);
    if (checkError) card.append(el("p", { class: "st-error", text: checkError }));
    if (!checkReport) {
      if (!checkBusy) card.append(el("p", { class: "st-hint", text: "No scan yet. Moments still work from the read; the scan adds old-text boxes and sound notes." }));
      return card;
    }
    const tracklets = Array.isArray(checkReport.tracklets) ? checkReport.tracklets : [];
    const warnings = Array.isArray(checkReport.warnings) ? checkReport.warnings : [];
    const music = checkReport?.audio?.music;
    const facts = [
      tracklets.length
        ? el("span", { class: "st-chip st-chip-quiet", text: `${tracklets.length} text region${tracklets.length === 1 ? "" : "s"}` })
        : null,
      warnings.length
        ? el("span", { class: "st-chip st-chip-busy", text: `${warnings.length} warning${warnings.length === 1 ? "" : "s"}` })
        : null,
      music?.present ? el("span", { class: "st-chip st-chip-busy", text: "Music bed detected" }) : null,
    ].filter(Boolean);
    if (facts.length) card.append(el("div", { class: "st-moment-facts" }, facts));
    for (const warning of warnings.slice(0, 2)) {
      const text = typeof warning === "string"
        ? warning
        : (warning?.message || warning?.code || "The scan reported an issue.");
      card.append(el("p", { class: "st-warning", text }));
    }
    return card;
  }

  function storyCard(story, index) {
    const hook = story.hook?.text || story.title || `Moment ${index + 1}`;
    const payoff = story.payoff?.text || "";
    const strength = Number(story.score);
    const card = el("article", { class: "st-story" });
    const head = el("div", { class: "st-story-head" }, [
      el("div", { class: "st-story-title" }, [
        el("span", { class: "st-story-number", text: String(index + 1).padStart(2, "0") }),
        el("h3", { text: hook }),
      ]),
    ]);
    const meta = el("div", { class: "st-story-meta" }, [
      el("span", {
        class: "st-story-span st-mono",
        text: `${formatDuration(story.start)} → ${formatDuration(story.end)}`,
      }),
      el("span", { class: "st-chip st-chip-quiet", text: formatDuration(story.dur) }),
      Number.isFinite(strength)
        ? el("span", { class: "st-chip st-chip-quiet", text: `Strength ${Math.round(strength)}` })
        : null,
    ]);
    const quotes = el("div", { class: "st-story-quotes" }, [
      el("div", {}, [
        el("span", { class: "st-label", text: "Payoff" }),
        el("p", { text: payoff || "No speech at the end." }),
      ]),
    ]);
    const note = el("p", { class: "st-story-note", role: "status", "aria-live": "polite", hidden: true });
    const trim = el("div", { class: "st-story-trim", role: "group", "aria-label": "Adjust moment range" });
    for (const [edge, delta, text, label] of [
      ["start", -1, "− start", "Start one sentence earlier"],
      ["start", 1, "+ start", "Start one sentence later"],
      ["end", -1, "− end", "End one sentence earlier"],
      ["end", 1, "+ end", "End one sentence later"],
    ]) {
      const next = adjustSentences(story.sentences, edge, delta);
      const control = el("button", {
        class: "st-btn st-btn-quiet st-btn-small",
        type: "button",
        text,
        title: label,
        "aria-label": label,
        disabled: !next,
      });
      control.addEventListener("click", () => { void adjustStory(story, next, note, trim); });
      trim.append(control);
    }
    const add = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-story-add",
      type: "button",
      text: "+ Add to queue",
      title: "Add this moment to the render queue",
    });
    add.addEventListener("click", () => queueOne(story, add, note));
    const editButton = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: "Start edit",
    });
    editButton.addEventListener("click", () => openInEdit(story));
    const foot = el("div", { class: "st-story-foot" }, [
      el("span", { class: "st-hint", text: formatCount(story.sentences?.length, "sentence") }),
      el("div", { class: "st-story-actions" }, [
        el("span", { class: "st-chip st-chip-quiet st-story-shape-chip", text: activeShape() }),
        add,
        editButton,
      ]),
    ]);
    card.append(head);
    const frame = momentFrame(story, index);
    if (frame) card.append(frame);
    card.append(meta, quotes, trim, foot, note);
    return card;
  }

  async function adjustStory(story, sentences, note, group) {
    if (!job || !activeSetId || !sentences?.length) return;
    for (const control of group.querySelectorAll("button")) control.disabled = true;
    note.hidden = false;
    setStatus(note, "Trimming the moment…");
    try {
      // The trim route owns the range, the Edits and the captions. It also
      // rebinds every live aspect, so Stories ± cannot strand an Edit.
      const result = await trimStory(job.id, activeSetId, story.id, {
        expectedRevision: Number(story.revision) || 0,
        startSentence: sentences[0],
        endSentence: sentences[sentences.length - 1],
      });
      if (disposed) return;
      const receipt = receiptSummary(result?.receipt);
      const duration = Number(result?.duration ?? result?.story?.dur);
      await loadSets();
      if (disposed) return;
      showStatus(
        `${receipt || "Moment range updated."}${Number.isFinite(duration) ? ` New length ${formatDuration(duration)}.` : ""}`,
        "ok",
      );
    } catch (error) {
      if (disposed) return;
      const code = trimErrorCode(error);
      const stale = code === "revision_mismatch" || code === "edit_changed";
      setStatus(
        note,
        stale
          ? `${error?.message || "This moment changed."} The latest range is open; try again.`
          : (error?.message || "Could not change this moment's range."),
        "bad",
      );
      for (const control of group.querySelectorAll("button")) control.disabled = false;
      if (stale) {
        invalidateReadCache(job.id);
        await loadSets();
      }
    }
  }

  function openBuilder() {
    const scenes = Array.isArray(job?.analysis?.scenes) ? job.analysis.scenes : [];
    if (!scenes.length) {
      showError("This video has no scenes yet. Finish reading it first.");
      return;
    }
    const dialog = el("dialog", { class: "st-dialog st-moment-builder", "aria-labelledby": "st-moment-builder-title" });
    const body = el("div", { class: "st-dialog-body" });
    const picked = new Set();
    const total = el("span", { class: "st-chip st-chip-quiet", text: "0 scenes · 0 s" });
    const log = el("div", { class: "st-build-log", role: "status", "aria-live": "polite" });
    const addLog = (message) => {
      log.append(el("p", { text: message }));
      log.scrollTop = log.scrollHeight;
    };
    const update = () => {
      const chosen = scenes.filter((scene) => picked.has(Number(scene.id)));
      const seconds = chosen.reduce((sum, scene) => sum + Math.max(0, Number(scene.end) - Number(scene.start)), 0);
      total.textContent = `${chosen.length} scene${chosen.length === 1 ? "" : "s"} · ${formatDuration(seconds)}`;
      if (chosen.length) addLog(`Selected ${chosen.length} scene${chosen.length === 1 ? "" : "s"} · ${formatDuration(seconds)}`);
      // A moment needs at least one scene before Add can do anything.
      if (build) build.disabled = chosen.length === 0;
    };
    const collage = el("div", { class: "st-moment-collage" });
    for (const scene of scenes) {
      const id = Number(scene.id);
      const text = String(scene.ocr || scene.speech || "").replace(/\s+/g, " ").trim();
      const tile = el("button", {
        class: "st-moment-tile",
        type: "button",
        "aria-pressed": "false",
        title: text || `Scene ${id + 1}`,
      });
      if (scene.thumb_url) tile.append(el("img", { src: scene.thumb_url, alt: "", loading: "lazy" }));
      tile.append(el("span", { class: "st-moment-tile-time", text: formatDuration(scene.start) }));
      tile.append(el("span", { class: "st-moment-tile-copy", text: text || "No speech or text" }));
      tile.addEventListener("click", () => {
        if (picked.has(id)) picked.delete(id);
        else picked.add(id);
        tile.classList.toggle("is-picked", picked.has(id));
        tile.setAttribute("aria-pressed", picked.has(id) ? "true" : "false");
        update();
      });
      collage.append(tile);
    }
    const selectAll = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Select all" });
    selectAll.addEventListener("click", () => {
      for (const scene of scenes) picked.add(Number(scene.id));
      for (const tile of collage.querySelectorAll(".st-moment-tile")) {
        tile.classList.add("is-picked");
        tile.setAttribute("aria-pressed", "true");
      }
      update();
    });
    const clearAll = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Clear" });
    clearAll.addEventListener("click", () => {
      picked.clear();
      for (const tile of collage.querySelectorAll(".st-moment-tile")) {
        tile.classList.remove("is-picked");
        tile.setAttribute("aria-pressed", "false");
      }
      update();
    });
    const title = el("input", { type: "text", maxLength: "120", placeholder: "Moment title", "aria-label": "Moment title" });
    const error = el("p", { class: "st-error", role: "alert", hidden: true });
    const build = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Add moment", disabled: true });
    build.addEventListener("click", async () => {
      const ids = [...picked].sort((a, b) => a - b);
      if (!ids.length) {
        error.hidden = false;
        error.textContent = "Pick at least one scene.";
        return;
      }
      const chosen = scenes.filter((scene) => picked.has(Number(scene.id)));
      const seconds = chosen.reduce((sum, scene) => sum + Math.max(0, Number(scene.end) - Number(scene.start)), 0);
      if (seconds < 15) {
        error.hidden = false;
        error.textContent = `Those scenes are ${formatDuration(seconds)}; a moment needs at least 15 s.`;
        return;
      }
      const first = Math.min(...chosen.map((scene) => Number(scene.start)));
      const last = Math.max(...chosen.map((scene) => Number(scene.end)));
      const duplicate = sets.flatMap((item) => item.stories || []).find(
        (story) => Math.abs(Number(story.start) - first) < 0.4 && Math.abs(Number(story.end) - last) < 0.4,
      );
      if (duplicate) {
        error.hidden = false;
        error.textContent = `That moment already exists: ${duplicate.title || duplicate.id}.`;
        addLog(`Skipped duplicate ${duplicate.id}.`);
        return;
      }
      error.hidden = true;
      build.disabled = true;
      build.textContent = "Adding…";
      addLog(`Adding ${ids.length} scene${ids.length === 1 ? "" : "s"}…`);
      try {
        let record;
        if (activeSetId) {
          const result = await addStory(job.id, activeSetId, ids, title.value.trim());
          record = result?.clip_set;
          addLog(`Added ${result?.story?.id || "a new moment"} to this set.`);
        } else {
          const result = await createClipSet(job.id, {
            count: 3,
            minS: 15,
            maxS: Math.min(180, Math.max(15, Math.ceil(seconds))),
            locks: ids,
            banScenes: scenes.map((scene) => Number(scene.id)).filter((id) => !picked.has(id)),
          });
          record = result?.clip_set;
          if (!record?.stories?.length) {
            if (record?.id) await deleteClipSet(job.id, record.id).catch(() => {});
            error.hidden = false;
            error.textContent = "Those scenes do not make a 15–180 s moment. Add another scene.";
            addLog("No moment fit those scenes.");
            return;
          }
          if (title.value.trim()) {
            const patched = await patchClipSet(job.id, record.id, [
              { id: record.stories[0].id, title: title.value.trim() },
            ]);
            record = patched?.clip_set || record;
          }
          addLog(`Created set with ${record.stories.length} moment.`);
        }
        if (!record?.stories?.length) {
          error.hidden = false;
          error.textContent = "The server returned no moment.";
          return;
        }
        sets = [record, ...sets.filter((item) => item.id !== record.id)];
        activeSetId = record.id;
        dialog.close();
        showStatus(`Added a ${formatDuration(record.stories[record.stories.length - 1]?.dur)} moment.`, "ok");
        renderStories();
      } catch (problem) {
        error.hidden = false;
        error.textContent = problem?.message || "Could not add that moment.";
        addLog(`Failed: ${problem?.message || "unknown error"}`);
      } finally {
        build.disabled = false;
        build.textContent = "Add moment";
      }
    });
    const cancel = el("button", { class: "st-btn st-btn-quiet", type: "button", text: "Cancel" });
    cancel.addEventListener("click", () => dialog.close());
    dialog.append(
      el("div", { class: "st-dialog-head" }, [
        el("h2", { id: "st-moment-builder-title", text: "Add a moment" }),
        el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close moment builder", onclick: () => dialog.close() }),
      ]),
      body,
      el("div", { class: "st-dialog-foot" }, [total, cancel, build]),
    );
    body.append(
      el("p", { class: "st-hint", text: "Tap the frames that belong together. A moment needs 15–180 s and cannot overlap one already in this set." }),
      el("div", { class: "st-layer-add" }, [selectAll, clearAll]),
      collage,
      el("label", { class: "st-field" }, [el("span", { text: "Moment title (optional)" }), title]),
      log,
      error,
    );
    dialog.addEventListener("close", () => dialog.remove());
    root.append(dialog);
    dialog.showModal();
  }

  function controlsCard() {
    const set = sets.find((item) => item.id === activeSetId) || sets[0];
    const requested = Number(set?.requested) || 3;
    const card = el("div", { class: "st-card st-story-controls" });
    const headActions = el("div", { class: "st-controls-head-actions" });
    const scan = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: checkBusy ? "Scanning…" : "Scan footage",
      disabled: checkBusy,
      title: "Find old text, music and picture issues",
    });
    scan.addEventListener("click", () => { void refreshCheck(scan); });
    headActions.append(scan);
    if (sets.length > 1) headActions.append(setPicker());
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { text: set ? "Moments in this set" : "No moments yet" }),
        el("p", {
          class: "st-hint",
          text: set
            ? `${formatCount(set.stories?.length, "moment")} from ${formatCount(set.sentence_count || 0, "sentence")}.`
            : "Build the first set from the finished read.",
        }),
      ]),
      headActions,
    ]);
    card.append(head);

    const actions = el("div", { class: "st-controls-row" });
    const countLabel = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "How many" }),
    ]);
    const count = el("select", { "aria-label": "How many moments" });
    for (let value = 3; value <= 12; value += 1) {
      count.append(el("option", { value: String(value), text: String(value), selected: value === requested }));
    }
    countLabel.append(count);
    const lengthLabel = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "Length" }),
    ]);
    const length = el("select", { "aria-label": "Moment length" });
    const current = lengthPreset(set);
    for (const [value, preset] of Object.entries(LENGTH_PRESETS)) {
      length.append(el("option", { value, text: preset.label, selected: value === current }));
    }
    lengthLabel.append(length);
    const custom = el("div", { class: "st-moment-custom", hidden: current !== "custom" });
    const minInput = el("input", { type: "number", min: "15", max: "180", step: "1", value: "30", "aria-label": "Minimum moment length in seconds" });
    const maxInput = el("input", { type: "number", min: "15", max: "180", step: "1", value: "90", "aria-label": "Maximum moment length in seconds" });
    custom.append(
      el("label", { class: "st-field st-field-inline" }, [el("span", { text: "From (s)" }), minInput]),
      el("label", { class: "st-field st-field-inline" }, [el("span", { text: "To (s)" }), maxInput]),
      el("span", { class: "st-hint", text: "15–180 s" }),
    );
    length.addEventListener("change", () => { custom.hidden = length.value !== "custom"; });
    const build = el("button", {
      // After results, queueing is the primary action; finding again is secondary.
      class: set ? "st-btn st-btn-ghost" : "st-btn st-btn-primary",
      type: "button",
      text: set ? "Find moments again" : "Find moments",
    });
    build.addEventListener("click", () => {
      if (length.value === "custom") {
        const low = Number(minInput.value);
        const high = Number(maxInput.value);
        if (!(low >= 15 && high <= 180 && high >= low)) {
          showError("Custom length must be 15–180 seconds, with the low end first.");
          return;
        }
        buildStories(Number(count.value), build, "custom", low, high);
        return;
      }
      buildStories(Number(count.value), build, length.value);
    });
    const own = el("button", {
      class: "st-btn st-btn-ghost",
      type: "button",
      text: "Add moment",
      title: "Choose scenes and add one moment yourself",
    });
    own.addEventListener("click", () => { openBuilder(card); });
    actions.append(countLabel, lengthLabel, build, own);
    card.append(actions, custom);

    const speech = speechCard();
    if (speech) card.append(speech);
    if (set?.note) card.append(el("p", { class: "st-hint", text: set.note }));
    for (const warning of set?.warnings || []) {
      card.append(el("p", { class: "st-warning", text: warning }));
    }
    return card;
  }

  /** Stories are cut on speech. Say so when this video has none to read. */
  function speechState() {
    if (!job?.analysis) return "";
    if (job.analysis.engine?.transcript_provider === "script") return "scripted";
    if (job.source?.has_audio === false) return "no_audio";
    const transcript = job.analysis.transcript;
    if (!transcript || (!transcript.segments && !transcript.no_speech)) return "no_transcript";
    if (transcript.no_speech) return "no_speech";
    return "";
  }

  function briefCard(state) {
    const scripted = state === "scripted";
    if (briefDraft === null) briefDraft = job?.script_brief?.brief || "";
    const intro = scripted
      ? `Moments are cut on a written voice script (${formatCount(job.script_brief?.lines || job.analysis?.transcript?.segments || 0, "line", "lines")}). Change the description to write it again.`
      : state === "no_audio"
        ? "This video has no sound, so there is nothing to cut moments on. Describe it and VibeCut writes a voice-over that fits each scene."
        : "No speech was heard in this video. Describe it and VibeCut writes a voice-over that fits each scene.";
    const box = el("textarea", {
      rows: 4,
      maxLength: 6000,
      value: briefDraft,
      placeholder: 'What it is about, the tone and mood, what the voice should say. Exact lines go in [script:"..."].\nExample: Cozy Sunday at home, warm and slow. [script:"Some days you just stay in."] [script:"And that is enough."]',
      "aria-label": "Video description for the voice script",
    });
    box.addEventListener("input", () => { briefDraft = box.value; });
    const write = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: scripting ? "Writing the script…" : scripted ? "Write the script again" : "Write voice script",
      disabled: scripting,
    });
    write.addEventListener("click", () => { void writeScript(write); });
    return el("div", { class: "st-script-brief" }, [
      el("p", { class: scripted ? "st-hint" : "st-warning", text: intro }),
      el("label", { class: "st-field" }, [el("span", { text: "Describe the video" }), box]),
      el("div", { class: "st-script-actions" }, [
        write,
        el("span", { class: "st-hint", text: "These moments render with this script as a voice-over and captions." }),
      ]),
    ]);
  }

  async function writeScript(button) {
    if (!job || scripting) return;
    const brief = String(briefDraft || "").trim();
    if (!brief) {
      showError('Describe the video first: the topic, tone and mood, or exact lines in [script:"..."].');
      return;
    }
    scripting = true;
    button.disabled = true;
    button.textContent = "Writing the script…";
    clearError();
    showStatus("Looking at the scenes and writing a voice-over that fits them…");
    try {
      const result = await writeScriptBrief(job.id, brief);
      invalidateReadCache(job.id);
      job = await getJob(job.id, { fresh: true });
      if (disposed) return;
      showStatus(
        `Wrote ${formatCount(result?.lines || 0, "line", "lines")} (${result?.language || "auto"}${result?.exact_lines ? `, ${result.exact_lines} kept word for word` : ""}). Find moments now.`,
        "ok",
      );
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not write a voice script for this video.");
    } finally {
      scripting = false;
      if (!disposed) renderStories();
    }
  }

  function speechCard() {
    const state = speechState();
    if (state === "no_audio" || state === "no_speech" || state === "scripted") {
      return briefCard(state);
    }
    if (state !== "no_transcript") return null;
    const read = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: transcribing ? "Reading speech…" : "Read speech",
      disabled: transcribing,
    });
    read.addEventListener("click", () => { void readSpeech(read); });
    return el("div", { class: "st-speech-missing" }, [
      el("p", {
        class: "st-warning",
        text: "This video was read without its speech, so moments cannot be cut on what people say. Read the speech now (OpenRouter, about 30 s for a 15 min video), then find moments.",
      }),
      read,
    ]);
  }

  async function readSpeech(button) {
    if (!job || transcribing) return;
    transcribing = true;
    button.disabled = true;
    button.textContent = "Reading speech…";
    clearError();
    showStatus("Reading the speech in this video…");
    try {
      const result = await transcribeJob(job.id);
      invalidateReadCache(job.id);
      job = await getJob(job.id, { fresh: true });
      if (disposed) return;
      showStatus(
        result?.segments
          ? `Read ${formatCount(result.segments, "line", "lines")} of speech (${result.language || "auto"}). Find moments now.`
          : "No speech was heard in this video.",
        result?.segments ? "ok" : "",
      );
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not read the speech in this video.");
    } finally {
      transcribing = false;
      if (!disposed) renderStories();
    }
  }

  function setPicker() {
    const label = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "Earlier picks" }),
    ]);
    const select = el("select", { "aria-label": "Earlier moment picks" });
    for (const set of sets) {
      const stamp = set.created
        ? new Date(Number(set.created) * 1000).toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        })
        : set.id;
      select.append(el("option", {
        value: set.id,
        text: `${stamp} · ${formatCount(set.stories?.length, "moment")}`,
        selected: set.id === activeSetId,
      }));
    }
    select.addEventListener("change", () => {
      activeSetId = select.value;
      renderStories();
    });
    label.append(select);
    return label;
  }

  function renderStories() {
    renderScanAction();
    if (!job) {
      emptyNoJob();
      return;
    }
    if (job.status !== "ready") {
      waitingCard(job);
      return;
    }
    const set = sets.find((item) => item.id === activeSetId) || sets[0];
    clear(dom.body);
    dom.body.append(controlsCard());
    if (!set) {
      appendScan();
      return;
    }

    const stories = Array.isArray(set.stories) ? set.stories : [];
    if (!stories.length) {
      const state = speechState();
      dom.body.append(el("div", { class: "st-empty" }, [
        el("h2", { text: "No complete moment found" }),
        el("p", {
          text: state === "no_audio" || state === "no_speech"
            ? "Describe the video above and write a voice script, then find moments again."
            : state === "no_transcript"
              ? "Read the speech first (button above), then find moments again."
              : "Try another length, fewer moments, or a source with more speech.",
        }),
      ]));
      appendScan();
      return;
    }

    const bar = el("div", { class: "st-card st-render-bar" });
    const aspectLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Moment shape" })]);
    const aspect = el("select", { "aria-label": "Moment shape" });
    for (const shape of STORY_SHAPES) {
      aspect.append(el("option", {
        value: shape.value,
        text: shape.label,
        selected: shape.value === activeShape(),
      }));
    }
    aspect.addEventListener("change", () => {
      rememberShape(aspect.value);
      for (const chip of root.querySelectorAll(".st-story-shape-chip")) chip.textContent = aspect.value;
    });
    aspectLabel.append(aspect);
    const qualityLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Quality" })]);
    const quality = el("select", { "aria-label": "Render quality" });
    quality.append(el("option", { value: "final", text: "1080p final" }));
    quality.append(el("option", { value: "720", text: "720p" }));
    quality.append(el("option", { value: "draft", text: "540p draft" }));
    qualityLabel.append(quality);
    const all = el("button", {
      class: "st-btn st-btn-primary",
      type: "button",
      text: `Queue all ${stories.length}`,
    });
    all.addEventListener("click", () => queueAll(stories, activeShape(), quality.value, all));
    bar.append(aspectLabel, qualityLabel, all);
    dom.body.append(bar);

    const list = el("div", { class: "st-story-list" });
    stories.forEach((story, index) => {
      list.append(storyCard(story, index));
    });
    dom.body.append(list);
    appendScan();
  }

  function appendScan() {
    // The scan card is optional detail; it never sits above the moments.
    if (checkReport || checkBusy || checkError) dom.body.append(checkCard());
  }

  async function queueOne(story, button, note) {
    if (!job || !activeSetId || button.disabled) return;
    const aspect = activeShape();
    const quality = root.querySelectorAll(".st-render-bar select")[1]?.value || "final";
    button.disabled = true;
    button.textContent = "Adding…";
    setStatus(note, "");
    try {
      await renderStory(job.id, activeSetId, story.id, { aspect, quality, captions: true });
      if (disposed) return;
      setStatus(note, `Added to the queue in ${aspect}.`, "ok");
      button.textContent = "Added";
    } catch (error) {
      if (disposed) return;
      setStatus(note, error.message || "Could not add this moment to the queue.", "bad");
      button.textContent = "+ Add to queue";
    } finally {
      if (!disposed) button.disabled = false;
    }
  }

  async function queueAll(stories, aspect, quality, button) {
    if (!job || !activeSetId || button.disabled) return;
    button.disabled = true;
    button.textContent = "Queueing…";
    clearError();
    showStatus("");
    try {
      const items = stories.map((story) => ({
        job_id: job.id,
        set_id: activeSetId,
        story_id: story.id,
        aspect,
        quality,
        title: story.title || "",
      }));
      await createStoryQueue(items);
      if (disposed) return;
      showStatus(`${formatCount(items.length, "moment")} queued. They render one at a time.`, "ok");
      button.textContent = "Queued";
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not queue these moments.");
      button.textContent = `Queue all ${stories.length}`;
      button.disabled = false;
    }
  }

  async function buildStories(count, button, length = "auto", minOverride = null, maxOverride = null) {
    if (!job || loading) return;
    loading = true;
    button.disabled = true;
    button.textContent = "Finding…";
    clearError();
    showStatus("Reading the transcript and choosing complete moments…");
    try {
      const preset = LENGTH_PRESETS[length] || LENGTH_PRESETS.auto;
      const minS = Number.isFinite(minOverride) ? minOverride : preset.min;
      const maxS = Number.isFinite(maxOverride) ? maxOverride : preset.max;
      const result = await createClipSet(job.id, { count, minS, maxS });
      ctx.refreshSteps?.();
      if (disposed) return;
      const record = result?.clip_set;
      if (record?.id) {
        sets = [record, ...sets.filter((item) => item.id !== record.id)];
        activeSetId = record.id;
      } else {
        await loadSets();
      }
      showStatus(`Found ${formatCount(record?.stories?.length || 0, "moment")}.`, "ok");
      renderStories();
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not find moments in this video.");
      button.disabled = false;
    } finally {
      loading = false;
      if (!disposed) {
        if (button.isConnected) button.textContent = sets.length ? "Find moments again" : "Find moments";
      }
    }
  }

  async function loadSets() {
    try {
      const data = await listClipSets(job.id);
      if (disposed) return;
      sets = Array.isArray(data?.clip_sets) ? data.clip_sets : [];
      const usable = sets.filter((item) => Array.isArray(item.stories) && item.stories.length);
      if (!usable.some((item) => item.id === activeSetId)) {
        activeSetId = usable[0]?.id || sets[0]?.id || "";
      }
      renderStories();
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not load stories for this video.");
      clear(dom.body);
      dom.body.append(emptyNoJobCard("Moments are unavailable", "The video is open, but its moment list could not be read."));
    }
  }

  function emptyNoJobCard(title, copy) {
    const card = el("div", { class: "st-empty" }, [
      el("h2", { text: title }),
      el("p", { text: copy }),
    ]);
    const button = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Go to Import" });
    button.addEventListener("click", () => ctx.go("import"));
    card.append(button);
    return card;
  }

  async function refreshStatus() {
    if (disposed || !job) return;
    try {
      const status = await getJobStatus(job.id);
      if (disposed) return;
      job = { ...job, ...status };
      announceJob();
      if (status.status === "ready") {
        stopPoll();
        await loadJob();
        return;
      }
      if (status.status === "failed") {
        failedCard(status);
        return;
      }
      waitingCard(status);
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not check this video.");
      schedulePoll();
    }
  }

  async function loadJob() {
    const id = ctx.getJobId();
    if (!id) {
      emptyNoJob();
      return;
    }
    loading = true;
    clearError();
    clear(dom.body);
    dom.body.append(el("p", { class: "st-hint", text: "Opening video…" }));
    try {
      const value = await getJob(id);
      if (disposed) return;
      job = value;
      announceJob();
      if (value.status === "ready") {
        await loadCheck();
        await loadSets();
      } else if (value.status === "failed") {
        failedCard(value);
      } else {
        waitingCard(value);
        schedulePoll();
      }
    } catch (error) {
      if (disposed) return;
      clear(dom.body);
      dom.body.append(emptyNoJobCard(
        error.status === 404 ? "This video is no longer on file" : "Could not open this video",
        error.message || "Choose another video from Import.",
      ));
    } finally {
      loading = false;
    }
  }

  loadJob();

  return () => {
    disposed = true;
    stopPoll();
    stopCheckPoll();
  };
}
