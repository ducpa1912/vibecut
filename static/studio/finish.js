/**
 * Studio — Finish.
 *
 * Renders every story in 9:16 or 4:5 through the durable story queue, lists
 * versions, shows preflight notes and hands off a publish kit, a review link
 * and a one-click "apply the same look to every story" pass.
 *
 * All work uses existing local routes. The two newer contracts are used when
 * the server has them:
 *   GET  /api/jobs/{id}/edits/{edit_id}/preflight
 *   POST /api/jobs/{id}/artifacts/{artifact_id}/packet
 * When either route is absent, the screen falls back to:
 *   GET  /api/jobs/{id}/preflight?story_id=
 *   POST /api/jobs/{id}/packets
 * Nothing outside this Mac is contacted.
 */

import { icon, paintIcons } from "./edit/icons.js";
import {
  getTrimState,
  rebindStory,
  request,
  trimErrorCode,
} from "./api.js";
import { artifactIsStale, STALE_RENDER_TEXT } from "./trust.js";
import {
  clear,
  el,
  fillChoice,
  formatBytes,
  formatCount,
  formatDuration,
  saveFillChoice,
  setStatus,
  shortDate,
  statusText,
  statusTone,
} from "./ui.js";

const POLL_MS = 2400;
const ACTIVE_QUEUE = new Set(["queued", "running"]);
const ACTIVE_ITEM = new Set(["queued", "running"]);
const LOADING_NOTE = "Reading renders…";
const ASPECTS = ["9:16", "4:5", "1:1", "16:9", "16:10"];
const ASPECT_LABELS = {
  "9:16": "9:16 vertical",
  "4:5": "4:5 feed",
  "1:1": "1:1 square",
  "16:9": "16:9 wide",
  "16:10": "16:10 wide",
};
const QUALITY_LABELS = {
  "360": "360p",
  draft: "540p draft",
  "720": "720p",
  final: "1080p final",
  "1440": "2K",
  "2160": "4K",
};
const EDIT_CHOICE_KEY = "vibecut.studio.edit.choice";
const QUEUE_QUALITY = {
  "360": "360p", draft: "540p", "720": "720p", final: "1080p", "1440": "2K", "2160": "4K",
};
const FILL_MODEL_LABELS = {
  lama: "LaMa", migan: "MI-GAN", sttn: "STTN", telea: "Telea", ns: "Navier-Stokes",
};

/**
 * Where Finish opens after Open in Finish: the cut's set, story, shape and
 * cut, each kept only when it still exists. A story found in another set
 * moves the set with it. Empty strings keep Finish's own defaults.
 */
export function finishFocusPick(focus, sets) {
  if (!focus) return null;
  const list = Array.isArray(sets) ? sets : [];
  const storyId = String(focus.storyId || "");
  const has = (set) => Array.isArray(set?.stories)
    && set.stories.some((story) => String(story?.id) === storyId);
  let set = list.find((item) => item?.id === focus.setId) || null;
  if (storyId && !has(set)) set = list.find(has) || set;
  const aspect = String(focus.aspect || "");
  return {
    setId: set?.id || "",
    storyId: set && has(set) ? storyId : "",
    aspect: ASPECTS.includes(aspect) ? aspect : "",
    artifactId: String(focus.artifactId || ""),
  };
}

function jobRoot(jobId) {
  return `/api/jobs/${encodeURIComponent(jobId)}`;
}

function storyKey(setId, storyId, aspect) {
  return `${setId}:${storyId}:${aspect}`;
}

function storyName(story, index) {
  const title = String(story?.title || story?.hook?.text || "").replace(/\s+/g, " ").trim();
  return title || `Story ${index + 1}`;
}

function storyDuration(story) {
  const direct = Number(story?.dur ?? story?.duration);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  return clips.reduce((sum, clip) => {
    const value = Number(clip?.dur);
    if (Number.isFinite(value)) return sum + value;
    return sum + Math.max(0, Number(clip?.end) - Number(clip?.start));
  }, 0);
}

function firstNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

/**
 * Read either preflight contract into one marker shape.
 * The newer route returns ``markers``; the base route returns ``findings``.
 */
export function normalizeMarkers(payload) {
  if (!payload || typeof payload !== "object") {
    return { markers: [], blocked: false, note: "" };
  }
  const raw = Array.isArray(payload.markers) ? payload.markers
    : Array.isArray(payload.findings) ? payload.findings
      : Array.isArray(payload.issues) ? payload.issues
        : [];
  const markers = [];
  raw.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const range = item.range && typeof item.range === "object" ? item.range : {};
    const at = firstNumber(
      item.at, item.time, item.t, item.start,
      range.start, item.marker?.at, item.marker?.start,
    );
    const message = String(
      item.message || item.label || item.text || item.title || "",
    ).replace(/\s+/g, " ").trim();
    if (!message) return;
    markers.push({
      id: String(item.id || item.check || `marker-${index}`),
      severity: String(item.severity || item.level || "info").toLowerCase(),
      message,
      suggestion: String(item.suggestion || item.fix || item.hint || "").trim(),
      at,
      lane: String(item.lane || item.track || item.check || "").trim(),
    });
  });
  markers.sort((left, right) => {
    const a = left.at === null ? Number.POSITIVE_INFINITY : left.at;
    const b = right.at === null ? Number.POSITIVE_INFINITY : right.at;
    return a - b;
  });
  return {
    markers,
    blocked: Boolean(payload.blocked),
    note: String(payload.note || payload.message || "").trim(),
  };
}

/** Split a hashtag sentence into unique tags, keeping the first eight. */
export function parseHashtags(value) {
  const seen = new Set();
  const rows = [];
  for (const part of String(value || "").split(/[\s,]+/)) {
    let tag = part.trim();
    if (!tag) continue;
    if (!tag.startsWith("#")) tag = `#${tag}`;
    tag = tag.replace(/[^\p{L}\p{N}_#]/gu, "");
    if (tag.length < 2 || seen.has(tag.toLowerCase())) continue;
    seen.add(tag.toLowerCase());
    rows.push(tag);
    if (rows.length >= 8) break;
  }
  return rows;
}

function artifactStoryId(artifact) {
  return String(artifact?.story_id || artifact?.spec?.story_id || "");
}

function artifactAspect(artifact) {
  return String(artifact?.aspect || artifact?.spec?.aspect || "9:16");
}

function artifactReady(artifact) {
  return artifact?.status === "ready" && Boolean(artifact?.url);
}

function plainVersion(value) {
  return String(value || "")
    .replace(/\bv(\d+)\b/g, "Version $1")
    .replace(/\bv\?\b/g, "Version ?");
}

const ARTIFACT_QUALITY = {
  "360": "360p", draft: "Draft", "720": "720p", final: "Final", "1440": "2K", "2160": "4K",
};

/** How a render's AI fill ran, when it was not the default. */
function fillChoiceWords(row) {
  return [
    FILL_MODEL_LABELS[row?.fill_method] || "",
    row?.fill_device === "gpu" ? "GPU" : "",
    row?.fill_follow === true ? "Follow" : "",
  ].filter(Boolean);
}

/**
 * How a queued render's AI fill runs, always in full: model, chip, Follow.
 * Older rows did not record their model, so they use the fallback.
 */
export function queueMethodWords(item, fallbackModel = "") {
  const model = String(item?.fill_model || item?.fill_method || fallbackModel || "");
  if (!model) return fillChoiceWords(item);
  if (model === "mixed") return ["Mixed models", ...(item?.fill_follow === true ? ["Follow"] : [])];
  const keyed = model === "lama" || model === "migan";
  return [
    FILL_MODEL_LABELS[model] || model,
    keyed ? (item?.fill_device === "gpu" ? "GPU" : "CPU") : "",
    keyed && item?.fill_follow === true ? "Follow" : "",
  ].filter(Boolean);
}

/** The order queues will run in: what renders now, then oldest first. */
export function queueRunOrder(rows) {
  const rendering = (queue) => (queue?.items || []).some((item) => String(item?.state) === "running");
  return [...(rows || [])].sort((a, b) => (
    Number(rendering(b)) - Number(rendering(a))
    || Number(a?.created || 0) - Number(b?.created || 0)
  ));
}

/** A finished render's real time: "6 min 42 s". */
export function tookText(seconds) {
  const total = Math.round(Number(seconds) || 0);
  if (total < 1) return "";
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours) return `${hours} h ${minutes} min`;
  return minutes ? `${minutes} min ${rest} s` : `${rest} s`;
}

/** How long a queue's renders really took, over every try. */
export function queueTook(items) {
  return (Array.isArray(items) ? items : []).reduce((sum, item) => {
    const spent = Number(item?.spent);
    if (Number.isFinite(spent) && spent > 0) return sum + spent;
    const started = Number(item?.started);
    const finished = Number(item?.finished);
    return sum + (started > 0 && finished > started ? finished - started : 0);
  }, 0);
}

function artifactLabel(artifact) {
  const version = plainVersion(artifact?.versions?.label || `v${artifact?.version || "?"}`);
  const quality = ARTIFACT_QUALITY[artifact?.quality] || "Final";
  const when = artifact?.created ? shortDate(artifact.created) : "";
  return [version, quality, ...fillChoiceWords(artifact), when].filter(Boolean).join(" · ");
}

/**
 * Count how the work that was running ended. Queue items are the source of
 * truth; artifacts that were rendering outside a queue are counted too.
 */
export function finishOutcome(queues, queueIds, artifactRows, artifactIds) {
  const watched = new Set(queueIds || []);
  let done = 0;
  let failed = 0;
  const counted = new Set();
  for (const queue of queues || []) {
    if (!watched.has(queue?.id)) continue;
    for (const item of queue.items || []) {
      const state = String(item?.state || "");
      if (item?.artifact_id) counted.add(String(item.artifact_id));
      if (state === "done") done += 1;
      else if (state === "failed") failed += 1;
    }
  }
  for (const item of artifactRows || []) {
    const id = String(item?.artifact_id || "");
    if (!(artifactIds || []).includes(id) || counted.has(id)) continue;
    if (item.status === "ready") done += 1;
    else if (item.status === "failed" || item.status === "interrupted") failed += 1;
  }
  return { done, failed };
}

/**
 * Count every story and shape once across all queues, not one queue's own
 * totals. A re-queued identity is the same work, so it is not counted twice.
 */
export function queueSummary(queues, filter = {}) {
  const jobId = String(filter?.jobId || "");
  const setId = String(filter?.setId || "");
  const stories = new Set();
  const shapes = new Map();
  const seen = new Set();
  let total = 0;
  let running = 0;
  let waiting = 0;
  let done = 0;
  let failed = 0;
  let stopped = 0;
  for (const queue of queues || []) {
    for (const item of queue?.items || []) {
      if (jobId && String(item?.job_id || "") !== jobId) continue;
      if (setId && item?.set_id && String(item.set_id) !== setId) continue;
      const state = String(item?.state || "queued");
      const shape = String(item?.aspect || "9:16");
      const story = String(item?.story_id || item?.title || item?.id || "");
      const identity = [
        item?.job_id || jobId, item?.set_id || setId,
        story, shape, item?.quality || "final",
      ].join("|");
      if (seen.has(identity)) continue;
      seen.add(identity);
      if (story) stories.add(`${item?.set_id || ""}:${story}`);
      shapes.set(shape, (shapes.get(shape) || 0) + 1);
      total += 1;
      if (state === "running") running += 1;
      else if (state === "queued") waiting += 1;
      else if (state === "done") done += 1;
      else if (state === "failed") failed += 1;
      else if (state === "cancelled" || state === "interrupted") stopped += 1;
    }
  }
  const shapeText = [...shapes.entries()]
    .sort((left, right) => {
      const order = (shape) => {
        const index = ASPECTS.indexOf(shape);
        return index < 0 ? ASPECTS.length : index;
      };
      return order(left[0]) - order(right[0]);
    })
    .map(([shape, count]) => `${count} in ${shape}`)
    .join(", ");
  const status = [
    running ? `${running} running` : "",
    waiting ? `${waiting} waiting` : "",
    done ? `${done} done` : "",
    failed ? `${failed} failed` : "",
    stopped ? `${stopped} stopped` : "",
  ].filter(Boolean).join(", ");
  let text = "Nothing is queued yet.";
  if (total) {
    const storyWord = stories.size === 1 ? "moment" : "moments";
    const renderWord = total === 1 ? "render" : "renders";
    text = [
      `${stories.size} ${storyWord}`,
      `${total} ${renderWord}${shapeText ? ` (${shapeText})` : ""}`,
      status,
    ].filter(Boolean).join(" · ") + ".";
  }
  return {
    stories: stories.size,
    total,
    shapes: Object.fromEntries(shapes),
    running,
    waiting,
    done,
    failed,
    stopped,
    text,
  };
}

/** The banner after renders stop. Never green when something failed. */
export function finishBanner({ done = 0, failed = 0 } = {}) {
  if (failed && done) {
    return {
      text: `${done} of ${done + failed} renders finished; ${failed} failed. The reason and Retry are under Versions.`,
      tone: "bad",
    };
  }
  if (failed) {
    return {
      text: `${failed === 1 ? "The render" : `All ${failed} renders`} failed. The reason and Retry are under Versions.`,
      tone: "bad",
    };
  }
  if (done) return { text: `${done === 1 ? "Render" : `${done} renders`} finished. New versions are ready.`, tone: "ok" };
  return { text: "Renders stopped.", tone: "" };
}

/**
 * Say what Apply to all really did. `results` holds one row per target:
 * `{name, changed: [field], skipped: [{field, reason}], error}`.
 */
export function applySummary(results) {
  const rows = Array.isArray(results) ? results : [];
  const changed = rows.filter((row) => !row.error && row.changed.length);
  const failed = rows.filter((row) => row.error);
  const counts = new Map();
  for (const row of changed) {
    for (const field of new Set(row.changed)) counts.set(field, (counts.get(field) || 0) + 1);
  }
  const parts = [];
  if (changed.length) {
    const what = [...counts.entries()].map(([field, count]) => `${field} on ${count}`).join(", ");
    parts.push(`Updated ${changed.length} ${changed.length === 1 ? "story" : "stories"} (${what}).`);
  } else {
    parts.push("No story changed.");
  }
  const skipped = rows.flatMap((row) => row.skipped.map((item) => `${row.name}: ${item.field}, ${item.reason}`));
  if (skipped.length) parts.push(`Skipped ${skipped.slice(0, 3).join("; ")}${skipped.length > 3 ? ` and ${skipped.length - 3} more` : ""}.`);
  if (failed.length) parts.push(`${failed.length} could not be updated: ${failed[0].name}: ${failed[0].error}`);
  return { text: parts.join(" "), tone: failed.length ? "bad" : changed.length ? "ok" : "" };
}

export const RENDER_FIRST_NOTE = "Render this story first; checks run on the render.";

/** Why preflight could not run, in one line. Never a bare "could not run". */
export function checksFailedNote(error) {
  const reason = String(error?.message || "").trim();
  // A server 404 that names the story is a real answer. Only an old route
  // with no detail falls back to "render first".
  if (reason) return `Checks could not run for this story: ${reason}`;
  if (Number(error?.status) === 404) return RENDER_FIRST_NOTE;
  return "Checks could not run for this story. Try Check again.";
}

/**
 * The current Edit's history, newest first: the head and its parents.
 * Autosaves folded into one version leave their old sidecars on disk; they
 * are not in the chain, so they are not listed.
 */
export function editChain(rows, headId) {
  const byId = new Map((rows || []).map((row) => [row.id, row]));
  if (!headId || !byId.has(headId)) {
    return [...(rows || [])].sort((left, right) => Number(right.version || 0) - Number(left.version || 0));
  }
  const chain = [];
  const seen = new Set();
  let cursor = byId.get(headId);
  while (cursor && !seen.has(cursor.id)) {
    seen.add(cursor.id);
    chain.push(cursor);
    cursor = cursor.parent ? byId.get(cursor.parent) : null;
  }
  return chain;
}

/** "1 min 20 s" style remaining time. */
export function etaText(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (value < 60) return `${value} s`;
  if (value >= 3600) {
    const hours = Math.floor(value / 3600);
    const left = Math.round((value % 3600) / 60);
    return left ? `${hours} h ${left} min` : `${hours} h`;
  }
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  // Seconds mean nothing on a long wait, and they make it look exact.
  if (value >= 600) return `${Math.round(value / 60)} min`;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

/** A running queue item's live progress: "42% · about 1 min left". */
export function itemProgressText(item) {
  const fraction = Math.max(0, Math.min(1, Number(item?.progress) || 0));
  const percent = `${Math.round(fraction * 100)}%`;
  const eta = Number(item?.eta);
  const measured = item?.eta !== null && item?.eta !== undefined
    && Number.isFinite(eta) && eta > 0;
  return measured ? `${percent} · about ${etaText(eta)} left` : percent;
}

/** Header progress uses its own measured ETA; never "0 s left" while running. */
export function queueProgressText(queue) {
  const fraction = Math.max(0, Math.min(1, Number(queue?.progress) || 0));
  const percent = `${Math.round(fraction * 100)}%`;
  const eta = Number(queue?.eta);
  const measured = ACTIVE_QUEUE.has(String(queue?.status || ""))
    && queue?.eta !== null && queue?.eta !== undefined
    && Number.isFinite(eta) && eta > 0;
  return measured ? `${percent} · ${etaText(eta)} left` : percent;
}

/**
 * What the render had to skip, trimmed and de-duplicated, at most three lines.
 * Old rows carry the list at the top; the manifest keeps it under render.
 */
export function renderWarnings(item) {
  const direct = Array.isArray(item?.warnings) ? item.warnings : [];
  const nested = Array.isArray(item?.render?.warnings) ? item.render.warnings : [];
  const seen = new Set();
  const rows = [];
  for (const value of direct.length ? direct : nested) {
    const text = String(value ?? "").trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    rows.push(text);
    if (rows.length === 3) break;
  }
  return rows;
}

/** One readable line from a failed artifact or queue item. */
export function failureReason(item) {
  const raw = String(item?.error || "").trim();
  if (!raw) {
    const message = String(item?.message || "").trim();
    return message && !/^render failed\.?$/i.test(message) ? message : "No reason was recorded.";
  }
  const line = raw.split("\n").map((part) => part.trim()).find(Boolean) || raw;
  return line.length > 240 ? `${line.slice(0, 237)}…` : line;
}

/** A file name for a downloaded story: story-01-9x16-v2.mp4. */
export function downloadName(artifact, index = 0) {
  const shape = artifactAspect(artifact).replace(":", "x");
  const version = artifact?.versions?.version || artifact?.version || "";
  const story = `story-${String(Math.max(0, index) + 1).padStart(2, "0")}`;
  const quality = artifact?.quality === "draft" ? "draft"
    : artifact?.quality === "720" ? "720p" : "";
  return [story, shape, version ? `v${version}` : "", quality]
    .filter(Boolean).join("-") + ".mp4";
}

function normalizePacket(result) {
  if (!result || typeof result !== "object") return null;
  if (result.packet && typeof result.packet === "object") return result.packet;
  if (result.manifest && typeof result.manifest === "object") return result.manifest;
  return result;
}

function packetDownload(packet, jobId) {
  const direct = String(packet?.zip_url || packet?.zip || "");
  if (direct) return direct;
  const id = String(packet?.packet_id || "");
  return id ? `${jobRoot(jobId)}/packets/${encodeURIComponent(id)}/zip` : "";
}

function coverDefaults(story, artifact) {
  const duration = Math.max(
    1,
    firstNumber(artifact?.target, artifact?.spec?.target, storyDuration(story), 10) || 10,
  );
  const first = Math.min(Math.max(0.4, duration * 0.16), Math.max(0.4, duration - 0.6));
  const second = Math.min(Math.max(first + 0.2, duration * 0.62), Math.max(0.6, duration - 0.2));
  return [Number(first.toFixed(2)), Number(second.toFixed(2))];
}

function defaultTitles(story, index) {
  const base = storyName(story, index).replace(/[#*_]/g, "").trim().slice(0, 82) || `Story ${index + 1}`;
  const variants = [
    base,
    `${base} — the part to watch`.slice(0, 100),
    `Watch this: ${base}`.slice(0, 100),
  ];
  return variants;
}

export function mount(root, ctx) {
  let disposed = false;
  let timer = 0;
  let loading = false;
  let busy = false;
  let job = null;
  let sets = [];
  let activeSetId = "";
  let artifacts = [];
  let queues = [];
  let edits = [];
  let editPointers = {};
  let packets = [];
  let shares = [];
  let checks = { markers: [], blocked: false, note: "", fallback: false };
  let checkSeq = 0;
  let notice = "";
  let noticeTone = "";
  let selectedStoryId = "";
  let currentEdit = null;
  let reviewTime = 0;
  let reviewPicked = false;
  let reviewMode = "fill";
  let queueTab = "queue";
  // Shape is chosen in Edit. Start from the last Edit choice so opening
  // Finish from the step bar still renders the shape the user worked in.
  let aspect = (() => {
    try {
      const choice = JSON.parse(localStorage.getItem(EDIT_CHOICE_KEY) || "null");
      return ASPECTS.includes(choice?.aspect) ? choice.aspect : "9:16";
    } catch (_) {
      return "9:16";
    }
  })();
  let quality = "final";
  let fillChoiceNow = fillChoice();
  let renderOptions = null;
  let fillMethods = {};
  // The Render step's model, for the next render only. Empty keeps the Edit's own.
  let fillMethodNow = "";
  // R2 trim health: per story, the current story revision and whether the
  // chosen shape's Edit still matches the range. A stale Edit is never queued.
  const trimHealth = new Map();
  let trimSeq = 0;
  let selectedArtifactId = "";
  let packetArtifactId = "";
  let shareArtifactId = "";
  let compareA = "";
  let compareB = "";
  let packetDraft = null;
  // Open in Finish (library): the cut to land on, used by the first load.
  let focus = ctx.takeFinishFocus?.(ctx.getJobId()) || null;
  let packetBusy = false;
  let shareBusy = false;
  let applyBusy = false;
  let applyNotice = "";
  let applyTone = "";
  // Set by copyCaptionStyle: false when the target track already had the style.
  let captionChanged = true;
  let applySourceId = "";
  let applyFields = {
    captions: true,
    text: true,
    color: true,
    music: true,
    voice: true,
  };
  const sessionLinks = [];
  let fillEstimate = { key: "", text: "" };
  let shareExpiry = "30";
  let shareLabel = "";

  root.innerHTML = `
    <section class="st-panel st-finish-panel" aria-labelledby="st-finish-title">
      <header class="st-panel-head st-finish-head">
        <div class="st-finish-heading">
          <p class="st-eyebrow">Step 4 · Finish</p>
          <h1 id="st-finish-title">Render and share</h1>
          <p class="st-lede">Render the shape you set in Edit. Keep every version. Review the story, then hand off a publish kit and a review link.</p>
        </div>
        <div class="st-finish-head-actions">
          <button id="st-finish-back" class="st-btn st-btn-ghost st-btn-small" type="button" data-icon="arrow-left">Edit</button>
        </div>
      </header>
      <p id="st-finish-status" class="st-status" role="status" aria-live="polite" hidden></p>
      <p id="st-finish-error" class="st-error" role="alert" hidden></p>
      <div id="st-finish-repair" class="st-trim-stale" role="alert" hidden></div>
      <div id="st-finish-body" class="st-finish-body"></div>
    </section>
  `;
  paintIcons(root);

  const dom = {
    back: root.querySelector("#st-finish-back"),
    status: root.querySelector("#st-finish-status"),
    error: root.querySelector("#st-finish-error"),
    repair: root.querySelector("#st-finish-repair"),
    body: root.querySelector("#st-finish-body"),
  };

  dom.back?.addEventListener("click", () => ctx.go("edit"));

  function setBusyStatus(message, tone = "") {
    setStatus(dom.status, message, tone);
  }

  function showError(message) {
    setStatus(dom.error, message, "bad");
  }

  function clearError() {
    setStatus(dom.error, "");
  }

  function announce(message, tone = "") {
    notice = message || "";
    noticeTone = tone;
    setBusyStatus(notice, noticeTone);
  }

  function stopPoll() {
    if (timer) window.clearTimeout(timer);
    timer = 0;
  }

  function schedulePoll() {
    stopPoll();
    if (disposed) return;
    if (!hasActiveWork()) return;
    timer = window.setTimeout(() => { void poll(); }, POLL_MS);
  }

  function hasActiveWork() {
    return queues.some((queue) => ACTIVE_QUEUE.has(String(queue?.status || "")))
      || artifacts.some((item) => ["queued", "rendering"].includes(String(item?.status || "")));
  }

  function activeSet() {
    return sets.find((item) => item.id === activeSetId) || sets[0] || null;
  }

  /** The GPU only when this Mac can run it, whatever was remembered. */
  function fillDeviceNow() {
    if (fillChoiceNow.device !== "gpu") return "cpu";
    return gpuReady() ? "gpu" : "cpu";
  }

  function gpuReady() {
    const gpu = renderOptions?.gpu || {};
    return Object.values(gpu).some((row) => row?.ready);
  }

  /** How the Render step's AI fill runs. The engine stays each layer's own. */
  function paintFillOptions() {
    const host = dom.body.querySelector(".st-finish-fill-options");
    if (!host) return;
    clear(host);
    host.hidden = !(fillEstimate.beats > 0);
    if (host.hidden) return;
    const gpuBlocked = !gpuReady();
    const device = segmented(
      "AI fill on",
      [
        { value: "cpu", label: "CPU", title: "Slower, and uses less memory." },
        {
          value: "gpu",
          label: "GPU",
          disabled: gpuBlocked,
          title: gpuBlocked
            ? (renderOptions?.gpu?.lama?.reason || "The GPU option is not ready on this Mac.")
            : "Much faster on this Mac, and uses more memory. Layers on an OpenCV or STTN engine stay as they are.",
        },
      ],
      fillDeviceNow(),
      (value) => {
        fillChoiceNow = { ...fillChoiceNow, device: value };
        saveFillChoice(fillChoiceNow);
        renderRenderCard();
      },
    );
    const fillLayers = (Array.isArray(currentEdit?.clean) ? currentEdit.clean : [])
      .filter((layer) => layer?.kind === "fill");
    const models = [...new Set(fillLayers.map((layer) => String(layer?.method || "lama")))];
    if (models.length) {
      const own = models.length === 1 ? models[0] : "";
      const picker = el("select", {
        class: "st-finish-fill-model",
        "aria-label": "AI model for this render",
        title: "For this render only. Clean keeps its own model.",
      });
      if (!own) picker.append(el("option", { value: "", text: "As set in Clean", selected: !fillMethodNow }));
      for (const [value, text] of Object.entries(FILL_MODEL_LABELS)) {
        if (fillMethods[value]?.ready === false && value !== own) continue;
        picker.append(el("option", { value, text, selected: (fillMethodNow || own) === value }));
      }
      picker.addEventListener("change", () => {
        fillMethodNow = picker.value === own ? "" : picker.value;
        renderRenderCard();
      });
      host.append(el("div", { class: "st-seg-group" }, [
        el("span", { class: "st-label", text: "AI model" }),
        picker,
      ]));
    }
    const followBlocked = renderOptions?.follow?.ready === false;
    const follow = el("input", {
      type: "checkbox",
      checked: fillChoiceNow.follow && !followBlocked,
      disabled: followBlocked,
    });
    follow.addEventListener("change", () => {
      fillChoiceNow = { ...fillChoiceNow, follow: follow.checked };
      saveFillChoice(fillChoiceNow);
      renderRenderCard();
    });
    host.append(device, el("label", {
      class: "st-finish-follow",
      title: followBlocked
        ? (renderOptions?.follow?.reason || "")
        : "LaMa and MI-GAN. One fill moves with the camera, and real pixels replace it as they come into view. Other movement falls back to normal fills.",
    }, [follow, el("span", { text: "Follow camera motion" })]));
  }

  async function loadRenderOptions() {
    if (renderOptions) return;
    renderOptions = {};
    try {
      const status = await request("/api/fill/status");
      if (disposed) return;
      renderOptions = status?.render_options || {};
      fillMethods = status?.methods || {};
    } catch (_) {
      renderOptions = {};
    }
    paintFillOptions();
    fillEstimate.key = "";
    void loadFillEstimate();
  }

  /** How long AI fill adds to these renders. Asks once per set, shape and visit. */
  async function loadFillEstimate() {
    const set = activeSet();
    const jobId = ctx.getJobId();
    if (!set?.id || !jobId) return;
    const device = fillDeviceNow();
    const key = `${jobId}:${set.id}:${aspect}:${device}:${fillChoiceNow.follow}:${fillMethodNow}`;
    if (fillEstimate.key === key) return;
    fillEstimate = { key, text: "", beats: fillEstimate.beats || 0 };
    try {
      const query = new URLSearchParams({
        set_id: set.id, aspect, device, follow: String(fillChoiceNow.follow), method: fillMethodNow,
      });
      const result = await request(`${jobRoot(jobId)}/fill-estimate?${query}`);
      if (disposed || fillEstimate.key !== key) return;
      fillEstimate.text = String(result?.text || "");
      const hadFill = fillEstimate.beats > 0;
      fillEstimate.beats = Number(result?.beats) || 0;
      // Whether the choices apply decides what the Queue buttons offer.
      if (hadFill !== fillEstimate.beats > 0) {
        renderRenderCard();
        return;
      }
    } catch (_) {
      return;
    }
    paintFillOptions();
    const node = dom.body.querySelector(".st-finish-fill-note");
    if (node) {
      node.textContent = fillEstimate.text;
      node.hidden = !fillEstimate.text;
    }
  }

  function stories() {
    return Array.isArray(activeSet()?.stories) ? activeSet().stories : [];
  }

  function selectedStory() {
    const rows = stories();
    return rows.find((item) => item.id === selectedStoryId) || rows[0] || null;
  }

  function selectedIndex() {
    const rows = stories();
    const index = rows.findIndex((item) => item.id === selectedStory()?.id);
    return index < 0 ? 0 : index;
  }

  function trimKey(storyId, shape = aspect) {
    return `${activeSetId}:${storyId}:${shape}`;
  }

  function trimHealthFor(storyId, shape = aspect) {
    return trimHealth.get(trimKey(storyId, shape)) || null;
  }

  function staleStoryIds(shape = aspect) {
    return stories()
      .filter((story) => trimHealthFor(story.id, shape)?.stale)
      .map((story) => String(story.id));
  }

  function storyById(storyId) {
    return stories().find((item) => String(item.id) === String(storyId)) || null;
  }

  /**
   * Ask the trim route which shapes still match. A story with a stale Edit
   * cannot queue: the render would fail closed, so Finish explains first.
   */
  async function loadTrimHealth({ shape = aspect, force = false, storyIds = null } = {}) {
    if (!job?.id || !activeSetId) return;
    const setId = activeSetId;
    const wantedIds = storyIds ? new Set(storyIds.map(String)) : null;
    const rows = stories();
    const wanted = rows.filter((story) => {
      if (wantedIds && !wantedIds.has(String(story.id))) return false;
      if (force) return true;
      return !trimHealth.has(`${setId}:${story.id}:${shape}`);
    });
    if (!wanted.length) return;
    const seq = ++trimSeq;
    await Promise.all(wanted.map(async (story) => {
      const key = `${setId}:${story.id}:${shape}`;
      try {
        const trim = await getTrimState(job.id, setId, story.id, { fresh: force });
        if (disposed || seq !== trimSeq) return;
        trimHealth.set(key, {
          stale: Boolean(trim?.aspects?.[shape]?.stale),
          revision: Number(trim?.revision) || 0,
          editId: String(trim?.aspects?.[shape]?.edit_id || ""),
          aspects: trim?.aspects || {},
          duration: Number(trim?.story?.dur) || 0,
        });
      } catch (error) {
        if (disposed || seq !== trimSeq) return;
        // No trim route (older server) or no current Edit: keep the old
        // behaviour and let the queue's own 409 explain.
        trimHealth.set(key, null);
      }
    }));
  }

  function clearRepair() {
    if (!dom.repair) return;
    dom.repair.hidden = true;
    dom.repair.replaceChildren();
  }

  function showRepair(message, storyId, shape = aspect) {
    if (!dom.repair) return;
    const button = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: "Repair this shape",
    });
    button.addEventListener("click", () => { void repairStory(storyId, shape, button); });
    dom.repair.hidden = false;
    dom.repair.replaceChildren(
      el("span", { text: message || "This story changed after its Edit was made." }),
      button,
    );
  }

  async function repairStory(storyId, shape = aspect, button = null) {
    const story = storyById(storyId);
    if (!job?.id || !activeSetId || !story) return;
    if (button) {
      button.disabled = true;
      button.textContent = "Repairing…";
    }
    announce("Rebinding the Edit to the current story range…");
    try {
      let health = trimHealthFor(storyId, shape);
      if (!health) {
        await loadTrimHealth({ shape, force: true });
        health = trimHealthFor(storyId, shape);
      }
      const result = await rebindStory(job.id, activeSetId, storyId, {
        expectedRevision: Number(health?.revision) || 0,
      });
      if (disposed) return;
      trimHealth.delete(trimKey(storyId, shape));
      await Promise.all([loadSets(), loadEdits()]);
      await loadTrimHealth({ shape });
      if (disposed) return;
      clearRepair();
      announce(
        `Repaired. ${formatDuration(Number(result?.duration) || storyDuration(story))} is ready to queue.`,
        "ok",
      );
      renderAll();
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not repair this shape.", "bad");
      const code = trimErrorCode(error);
      if (code === "revision_mismatch" || code === "edit_changed") {
        trimHealth.delete(trimKey(storyId, shape));
        await loadTrimHealth({ shape, force: true, storyIds: [storyId] });
        if (!disposed) renderAll();
      }
      if (button?.isConnected) {
        button.disabled = false;
        button.textContent = "Repair this shape";
      }
    }
  }

  function readyArtifacts() {
    return artifacts.filter(artifactReady);
  }

  /** A full-video render is the natural default for Publish when it exists. */
  function preferredReadyArtifact(rows = readyArtifacts()) {
    return rows.find((item) => artifactStoryId(item) === "st_full_video")
      || rows[0]
      || null;
  }

  /** A story name for any ready artifact, including a full-video render. */
  function artifactStoryLabel(item) {
    const storyId = artifactStoryId(item);
    const index = stories().findIndex((row) => String(row.id) === storyId);
    if (index >= 0) return storyName(stories()[index], index);
    if (storyId === "st_full_video") return "Full video";
    const title = String(item?.title || "").trim();
    return title || "Story";
  }

  function finishedRows() {
    return readyArtifacts().slice().sort((left, right) => {
      const leftFull = artifactStoryId(left) === "st_full_video" ? 0 : 1;
      const rightFull = artifactStoryId(right) === "st_full_video" ? 0 : 1;
      if (leftFull !== rightFull) return leftFull - rightFull;
      return Number(right.created || 0) - Number(left.created || 0);
    });
  }

  function finishedCard() {
    const card = el("section", {
      class: "st-card st-finish-finished",
      "aria-labelledby": "st-finish-finished-title",
    });
    const rows = finishedRows();
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-finished-title", text: "Finished" }),
        el("p", {
          class: "st-hint",
          text: rows.length
            ? `${formatCount(rows.length, "render")} ready. Pick one for the kit and the link.`
            : "No finished story yet. Queue a render.",
        }),
      ]),
    ]));
    if (!rows.length) return card;
    const list = el("div", { class: "st-finish-finished-list" });
    for (const item of rows) {
      const active = item.artifact_id === packetArtifactId
        || item.artifact_id === shareArtifactId;
      const row = el("div", { class: `st-finish-finished-row${active ? " is-active" : ""}` });
      const size = formatBytes(item.size || item.size_bytes || item.bytes || 0);
      const duration = Number(item.duration || 0);
      const meta = [
        artifactAspect(item),
        artifactLabel(item).replace(" · current", ""),
        size,
        duration > 0 ? formatDuration(duration) : "",
      ].filter(Boolean).join(" · ");
      const pick = el("button", {
        class: "st-finish-finished-pick",
        type: "button",
        "aria-pressed": active ? "true" : "false",
        title: `Use ${artifactStoryLabel(item)} for the kit and link.`,
      }, [
        el("strong", { text: artifactStoryLabel(item) }),
        el("span", { class: "st-hint", text: meta }),
      ]);
      pick.addEventListener("click", () => {
        selectedArtifactId = item.artifact_id;
        packetArtifactId = item.artifact_id;
        shareArtifactId = item.artifact_id;
        if (packetDraft?.artifact_id !== item.artifact_id) initPacketDraft(item);
        renderFinishedCard();
        renderPacketCard();
        renderShareCard();
        announce(`${artifactStoryLabel(item)} is selected for Publish.`, "ok");
      });
      const actions = el("div", { class: "st-finish-finished-actions" }, [
        el("a", {
          class: "st-btn st-btn-quiet st-btn-small",
          href: item.url,
          target: "_blank",
          rel: "noreferrer",
          text: "Open file",
        }),
        el("a", {
          class: "st-btn st-btn-quiet st-btn-small",
          href: item.url,
          download: downloadName(item),
          text: "Download",
        }),
      ]);
      row.append(pick, actions);
      list.append(row);
    }
    card.append(list);
    return card;
  }

  function renderFinishedCard() {
    const card = dom.body.querySelector(".st-finish-finished");
    if (card) card.replaceWith(finishedCard());
  }

  function artifactsFor(storyId = selectedStory()?.id, shape = aspect) {
    return readyArtifacts()
      .filter((item) => artifactStoryId(item) === String(storyId || "")
        && artifactAspect(item) === shape)
      .sort((left, right) => Number(right.created || 0) - Number(left.created || 0));
  }

  function allArtifactsFor(storyId = selectedStory()?.id, shape = aspect) {
    return artifacts
      .filter((item) => artifactStoryId(item) === String(storyId || "")
        && artifactAspect(item) === shape)
      .sort((left, right) => Number(right.created || 0) - Number(left.created || 0));
  }

  /** Open Edit on one cut without losing the set, story and shape. */
  function openEdit(storyId, shape = aspect) {
    try {
      localStorage.setItem(EDIT_CHOICE_KEY, JSON.stringify({
        setId: activeSetId,
        storyId: String(storyId || selectedStory()?.id || ""),
        aspect: ASPECTS.includes(shape) ? shape : "9:16",
      }));
    } catch (_) {
      /* Edit falls back to the first story. */
    }
    ctx.go("edit", { force: true });
  }

  /** The live queue item for one story and shape, if it is still waiting/running. */
  function liveQueueItem(storyId, shapeValue, exact = false) {
    for (const queue of queues) {
      if (!ACTIVE_QUEUE.has(String(queue?.status || ""))) continue;
      const item = (queue.items || []).find((row) => (
        String(row?.story_id || "") === String(storyId || "")
        && String(row?.aspect || "9:16") === String(shapeValue || "9:16")
        && ACTIVE_ITEM.has(String(row?.state || ""))
        && (!exact || matchesChoice(row, storyId))
      ));
      if (item) return item;
    }
    return null;
  }

  /** Whether a queued render is the one the Queue button would add now. */
  function matchesChoice(row, storyId) {
    if (String(row?.quality || "final") !== String(quality)) return false;
    if ((row?.fill_device === "gpu" ? "gpu" : "cpu") !== queuedDevice()) return false;
    if ((row?.fill_follow === true) !== queuedFollow()) return false;
    if (String(row?.fill_method || "") !== queuedMethod()) return false;
    // The open Edit is known; a changed one is new work.
    const open = String(selectedStory()?.id || "") === String(storyId || "");
    const editHash = String(row?.edit_hash || "");
    return !(open && editHash && currentEdit?.hash && editHash !== String(currentEdit.hash));
  }

  /** A row from before queues recorded the model: the open Edit's, if it has one. */
  function rowFallbackModel(item) {
    if (String(item?.job_id || "") !== String(job?.id || "")) return "";
    const models = new Set((Array.isArray(currentEdit?.clean) ? currentEdit.clean : [])
      .filter((layer) => layer?.kind === "fill")
      .map((layer) => String(layer?.method || "lama")));
    return models.size === 1 ? [...models][0] : "";
  }

  function queuedMethod() {
    return fillEstimate.beats > 0 ? fillMethodNow : "";
  }

  function queuedDevice() {
    return fillEstimate.beats > 0 ? fillDeviceNow() : "cpu";
  }

  function queuedFollow() {
    return fillEstimate.beats > 0 && fillChoiceNow.follow && renderOptions?.follow?.ready !== false;
  }

  function keepArtifactSelection() {
    const rows = allArtifactsFor();
    const ids = new Set(rows.map((item) => item.artifact_id));
    if (!ids.has(selectedArtifactId)) selectedArtifactId = rows[0]?.artifact_id || "";
    // Publish is job-wide: a full-video artifact stays selected when the
    // review card moves to a different story.
    const allReady = readyArtifacts().map((item) => item.artifact_id);
    const fallback = preferredReadyArtifact()?.artifact_id || "";
    if (!allReady.includes(packetArtifactId)) packetArtifactId = fallback;
    if (!allReady.includes(shareArtifactId)) shareArtifactId = fallback;
    const storyReady = rows.filter(artifactReady).map((item) => item.artifact_id);
    if (!storyReady.includes(compareA)) compareA = storyReady[0] || "";
    if (!storyReady.includes(compareB)) {
      compareB = storyReady.find((id) => id !== compareA) || storyReady[1] || "";
    }
  }

  function packetArtifact() {
    return readyArtifacts().find((item) => item.artifact_id === packetArtifactId)
      || preferredReadyArtifact();
  }

  function shareArtifact() {
    return readyArtifacts().find((item) => item.artifact_id === shareArtifactId)
      || preferredReadyArtifact();
  }

  function currentEditFor(storyId, shape) {
    const setId = activeSetId;
    if (!job || !setId || !storyId) return Promise.resolve(null);
    const params = new URLSearchParams({
      set_id: setId,
      story_id: storyId,
      aspect: shape,
    });
    return request(`${jobRoot(job.id)}/edits/current?${params.toString()}`)
      .catch((error) => (error?.status === 404 ? null : Promise.reject(error)));
  }

  function editRowsFor(storyId = selectedStory()?.id, shape = aspect) {
    const key = storyKey(activeSetId, String(storyId || ""), shape);
    const rows = edits.filter((item) => item.key === key);
    return editChain(rows, editPointers[key]);
  }

  function editHead(storyId = selectedStory()?.id, shape = aspect) {
    return String(editPointers[storyKey(activeSetId, String(storyId || ""), shape)] || "");
  }

  function currentEditHash(storyId = selectedStory()?.id, shape = aspect) {
    const head = editHead(storyId, shape);
    if (!head) return "";
    return String(edits.find((row) => String(row.id) === head)?.hash || "");
  }

  function artifactStale(item, storyId = selectedStory()?.id, shape = aspect) {
    return artifactIsStale(item, currentEditHash(storyId, shape));
  }

  async function loadJob() {
    const jobId = ctx.getJobId();
    if (!jobId) return false;
    job = await request(jobRoot(jobId));
    ctx.updateJob({ name: job?.source?.name || job?.name, status: job?.status });
    return true;
  }

  async function loadSets() {
    const jobId = ctx.getJobId();
    sets = [];
    if (!jobId) return;
    const data = await request(`${jobRoot(jobId)}/clip-sets`).catch(() => ({ clip_sets: [] }));
    sets = Array.isArray(data?.clip_sets) ? data.clip_sets : [];
    if (!sets.some((item) => item.id === activeSetId)) {
      activeSetId = (sets.find((item) => item.kind !== "full_video") || sets[0])?.id || "";
    }
    const pick = finishFocusPick(focus, sets);
    focus = null;
    if (pick) {
      reviewPicked = false;
      reviewTime = 0;
      if (pick.setId) activeSetId = pick.setId;
      if (pick.storyId) selectedStoryId = pick.storyId;
      if (pick.aspect) aspect = pick.aspect;
      if (pick.artifactId) {
        selectedArtifactId = pick.artifactId;
        packetArtifactId = pick.artifactId;
        shareArtifactId = pick.artifactId;
      }
    }
    if (!stories().some((item) => item.id === selectedStoryId)) {
      selectedStoryId = stories()[0]?.id || "";
    }
  }

  async function loadArtifacts() {
    const jobId = ctx.getJobId();
    if (!jobId) return;
    const data = await request(`${jobRoot(jobId)}/artifacts`).catch(() => ({ artifacts: [] }));
    artifacts = Array.isArray(data?.artifacts) ? data.artifacts : [];
    keepArtifactSelection();
  }

  async function loadQueues() {
    const data = await request("/api/story-queues").catch(() => ({ queues: [] }));
    queues = Array.isArray(data?.queues) ? data.queues : [];
    return queues;
  }

  async function loadEdits() {
    const jobId = ctx.getJobId();
    if (!jobId) return;
    const data = await request(`${jobRoot(jobId)}/edits`).catch(() => ({ edits: [], pointers: {} }));
    edits = Array.isArray(data?.edits) ? data.edits : [];
    editPointers = data?.pointers && typeof data.pointers === "object" ? data.pointers : {};
  }

  async function loadPackets() {
    const jobId = ctx.getJobId();
    if (!jobId) return;
    const data = await request(`${jobRoot(jobId)}/packets`).catch(() => ({ packets: [] }));
    packets = Array.isArray(data?.packets) ? data.packets : [];
  }

  async function loadShares() {
    const jobId = ctx.getJobId();
    if (!jobId) return;
    const data = await request(`/api/shares?job_id=${encodeURIComponent(jobId)}`)
      .catch(() => ({ shares: [] }));
    shares = Array.isArray(data?.shares) ? data.shares
      : Array.isArray(data?.links) ? data.links
        : Array.isArray(data?.records) ? data.records
          : [];
  }

  async function loadChecks() {
    const story = selectedStory();
    if (!job || !story) {
      checks = { markers: [], blocked: false, note: "", fallback: false };
      currentEdit = null;
      return;
    }
    const seq = ++checkSeq;
    const edit = await currentEditFor(story.id, aspect).catch(() => null);
    currentEdit = edit?.edit || edit || null;
    let payload = null;
    let fallback = false;
    if (edit?.id) {
      try {
        payload = await request(`${jobRoot(job.id)}/edits/${encodeURIComponent(edit.id)}/preflight`);
      } catch (error) {
        if (![404, 405, 501].includes(Number(error?.status))) throw error;
        fallback = true;
      }
    } else {
      fallback = true;
    }
    if (!payload) {
      const params = new URLSearchParams({ story_id: story.id, set_id: activeSetId });
      try {
        payload = await request(`${jobRoot(job.id)}/preflight?${params.toString()}`);
      } catch (error) {
        if (![404, 405, 501].includes(Number(error?.status))) throw error;
        // The server's own reason wins. A clip-set story id now resolves;
        // a real 404 is never rewritten as "Render this story first".
        if (disposed || seq !== checkSeq) return;
        checks = {
          markers: [],
          blocked: false,
          note: checksFailedNote(error),
          fallback: true,
        };
        return;
      }
      fallback = true;
    }
    if (disposed || seq !== checkSeq) return;
    const value = normalizeMarkers(payload);
    checks = { ...value, fallback };
    if (!reviewPicked) {
      const first = value.markers.find((marker) => Number.isFinite(Number(marker.at)));
      reviewTime = first ? Number(first.at) : 0;
    }
  }

  async function loadAll({ quiet = false } = {}) {
    if (loading) return;
    loading = true;
    clearError();
    if (!quiet) announce(LOADING_NOTE);
    try {
      const hasJob = await loadJob();
      if (!hasJob) {
        renderEmpty("No video open", "Import a video first. Finish needs moments and renders.", "import", "Go to Import");
        return;
      }
      await loadSets();
      await Promise.all([loadArtifacts(), loadQueues(), loadEdits(), loadPackets(), loadShares()]);
      // The page first. Leftover text and trim health fill in when they are ready.
      renderAll();
      if (stories().length) void loadReviewChecks();
      // Clear the loading line, but keep a notice something else set meanwhile.
      if (!notice || notice === LOADING_NOTE) announce("");
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      showError(error?.message || "Could not read the finished work for this video.");
      renderEmpty(
        error?.status === 404 ? "This video is no longer on file" : "Could not open Finish",
        error?.message || "Choose another video from Import.",
        "import",
        "Go to Import",
      );
    } finally {
      loading = false;
    }
  }

  async function loadReviewChecks() {
    await Promise.all([
      loadChecks().catch((error) => {
        checks = {
          markers: [],
          blocked: false,
          note: checksFailedNote(error),
          fallback: true,
        };
      }),
      loadTrimHealth().catch(() => {}),
    ]);
    if (disposed) return;
    // The page renders before the Edit loads; rebuild Review once its id is
    // here, or the player keeps the empty state forever.
    renderReviewCard();
    renderRenderCard();
  }

  async function poll() {
    if (disposed || loading) return;
    const wasActive = hasActiveWork();
    const readyBefore = readyArtifacts().length;
    const queueIds = queues
      .filter((queue) => ACTIVE_QUEUE.has(String(queue?.status || "")))
      .map((queue) => queue.id);
    const artifactIds = artifacts
      .filter((item) => ["queued", "rendering"].includes(String(item?.status || "")))
      .map((item) => String(item.artifact_id || ""));
    try {
      await Promise.all([loadQueues(), loadArtifacts()]);
      if (disposed) return;
      renderQueueCard();
      renderRenderCard();
      // A finished render belongs in Finished and Publish at once.
      if (readyArtifacts().length !== readyBefore) {
        keepArtifactSelection();
        renderFinishedCard();
        renderPacketCard();
        renderShareCard();
      }
      if (wasActive && !hasActiveWork()) {
        await Promise.all([loadPackets(), loadShares()]);
        renderVersionsCard();
        // The render just made the AI fill, so show that rather than the blur check.
        reviewMode = "fill";
        renderReviewCard();
        renderPacketCard();
        renderShareCard();
        const banner = finishBanner(finishOutcome(queues, queueIds, artifacts, artifactIds));
        announce(banner.text, banner.tone);
        return;
      }
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      showError(error?.message || "Could not refresh the render queue.");
      schedulePoll();
    }
  }

  function renderSkeleton() {
    clear(dom.body);
    const wrap = el("div", { class: "st-finish-skeleton", role: "status", "aria-live": "polite" });
    wrap.append(
      el("div", { class: "st-finish-skeleton-stage" }),
      el("div", { class: "st-finish-skeleton-lines" }, [
        el("i", {}), el("i", {}), el("i", {}),
      ]),
    );
    dom.body.append(wrap);
  }

  function renderEmpty(title, copy, step, action) {
    clear(dom.body);
    const card = el("div", { class: "st-empty" }, [
      el("h2", { text: title }),
      el("p", { text: copy }),
    ]);
    const button = el("button", { class: "st-btn st-btn-primary", type: "button", text: action });
    button.addEventListener("click", () => ctx.go(step));
    card.append(button);
    dom.body.append(card);
  }

  function cleanPreviewUrl(mode = reviewMode) {
    const editId = currentEdit?.id;
    const jobId = job?.id || ctx.getJobId();
    if (!editId || !jobId) return "";
    return `${jobRoot(jobId)}/edits/${encodeURIComponent(editId)}/clean-preview?mode=${mode}`;
  }

  /** Playable review of the current Edit, with a diagnostic quick-blur view. */
  function reviewPlayer() {
    const figure = el("figure", { class: "st-finish-player" });
    const src = cleanPreviewUrl();
    if (!src) {
      figure.append(el("div", { class: "st-finish-frame-empty" }, [
        el("p", { class: "st-hint", text: "Open this story in Edit to build its playable preview." }),
      ]));
      return figure;
    }
    const modeText = reviewMode === "blur"
      ? "Blur check · leftover text stays sharp"
      : "Preview · 540p · Clean applied";
    const hint = el("span", { class: "st-hint", text: modeText });
    const video = el("video", {
      src,
      controls: true,
      playsinline: true,
      preload: "metadata",
    });
    video.addEventListener("loadstart", () => { hint.textContent = "Building preview…"; });
    video.addEventListener("canplay", () => { hint.textContent = modeText; });
    video.addEventListener("loadedmetadata", () => {
      const at = Math.max(0, Math.min(reviewTime, Number(video.duration) || reviewTime));
      // The first frames fade in from black, so show the picture at the start.
      if (Number.isFinite(at)) video.currentTime = at || 0.2;
    });
    video.addEventListener("timeupdate", () => {
      const label = figure.querySelector(".st-finish-preview-time");
      if (label) label.textContent = formatDuration(video.currentTime);
    });
    video.addEventListener("seeked", () => {
      reviewTime = video.currentTime;
      const panel = figure.parentElement?.querySelector(".st-finish-clean-panel");
      if (panel) panel.replaceWith(cleanPanel());
    });
    video.addEventListener("error", () => {
      // Building a preview slows a running render, so it waits for the render.
      if (hasActiveWork()) {
        hint.textContent = "Preview waits for the render to finish, so the render keeps its speed.";
        return;
      }
      // AI fill shows here once a render has made it. Until then, the blur check.
      if (reviewMode === "blur") {
        hint.textContent = "Preview could not be built.";
        return;
      }
      reviewMode = "blur";
      announce("AI fill shows here after a render. Showing Quick blur for now.");
      renderReviewCard();
    });
    const toggle = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: reviewMode === "blur" ? "Quick blur on" : "Quick blur",
      "aria-pressed": reviewMode === "blur" ? "true" : "false",
      title: "Show AI-fill boxes as blur, so leftover text stays visible.",
    });
    toggle.addEventListener("click", () => {
      reviewTime = Number(video.currentTime) || reviewTime;
      reviewMode = reviewMode === "blur" ? "fill" : "blur";
      renderReviewCard();
    });
    figure.append(video);
    figure.append(el("figcaption", { class: "st-finish-preview-bar" }, [
      toggle,
      el("span", { class: "st-mono st-finish-preview-time", text: formatDuration(reviewTime) }),
      hint,
    ]));
    return figure;
  }

  /** The quoted text in a check message, without the repeated sentence. */
  function noteSample(marker) {
    const message = String(marker?.message || "").trim();
    const quoted = message.match(/: '(.+)'\.$/);
    return quoted ? quoted[1] : message;
  }

  function cleanAt(time) {
    const layers = Array.isArray(currentEdit?.clean) ? currentEdit.clean : [];
    return layers.filter((layer) => {
      const ranges = Array.isArray(layer?.ranges) ? layer.ranges : [];
      if (!ranges.length) return true;
      return ranges.some((range) => (
        Number(time) >= Number(range.start) - 0.05
        && Number(time) <= Number(range.end) + 0.05
      ));
    });
  }

  function cleanLabel(layer) {
    if (layer?.kind === "fill") {
      return layer.method === "sttn" ? "STTN fill" : "LaMa fill";
    }
    return String(layer?.kind || "clean").replace(/_/g, " ");
  }

  function notesPanel() {
    const col = el("div", { class: "st-finish-notes" });
    const markers = checks.markers;
    col.append(el("div", { class: "st-finish-notes-head" }, [
      el("h3", { text: "Leftover text" }),
      el("p", {
        class: "st-hint",
        text: markers.length
          ? `${formatCount(markers.length, "place")} with no Clean layer · click one to load its frame.`
          : "No leftover text for this story and shape.",
      }),
    ]));
    if (checks.blocked) {
      col.append(el("div", { class: "st-finish-note-blocked" }, [
        el("span", { class: "st-chip st-chip-bad", text: "Must fix" }),
        el("p", { class: "st-hint", text: "A check blocks this hand-off. Fix it before packing or sharing." }),
      ]));
    }
    if (!markers.length && checks.note) {
      col.append(el("p", { class: "st-hint", text: checks.note }));
    }
    if (markers.length) {
      const list = el("div", { class: "st-finish-note-list" });
      for (const marker of markers) {
        const at = Number(marker.at);
        const active = Number.isFinite(at) && Math.abs(at - reviewTime) < 0.05;
        const row = el("button", {
          class: `st-finish-note${active ? " is-active" : ""}`,
          type: "button",
          title: marker.message,
        }, [
          el("span", {
            class: "st-mono st-finish-note-time",
            text: Number.isFinite(at) ? formatDuration(at) : "—",
          }),
          el("span", { class: "st-finish-note-copy", text: `'${noteSample(marker)}'` }),
          icon("arrow-right", { size: 14 }),
        ]);
        row.addEventListener("click", () => {
          if (!Number.isFinite(at)) return;
          reviewTime = at;
          reviewPicked = true;
          renderReviewCard();
        });
        list.append(row);
      }
      col.append(list);
    }
    return col;
  }

  /** What Clean removed at the previewed frame, next to the frame itself. */
  function cleanPanel() {
    const layers = cleanAt(reviewTime);
    const counts = new Map();
    for (const layer of layers) {
      const label = cleanLabel(layer);
      counts.set(label, (counts.get(label) || 0) + 1);
    }
    const parts = [...counts.entries()].map(([label, count]) => `${count} ${label}`);
    const panel = el("div", { class: "st-finish-clean-panel" }, [
      el("span", { class: "st-label", text: "Clean check · this frame" }),
      el("p", {
        class: "st-hint",
        text: currentEdit?.id
          ? (layers.length
            ? `${formatCount(layers.length, "area")} cleaned · ${parts.join(" · ")}`
            : "No Clean layer covers this frame.")
          : "Open this story in Edit to load the Clean check.",
      }),
    ]);
    if (layers.length) {
      const chips = el("div", { class: "st-finish-clean-chips" });
      for (const layer of layers.slice(0, 6)) {
        chips.append(el("span", {
          class: "st-chip",
          text: String(layer.label || layer.tracklet_kind || cleanLabel(layer)).slice(0, 36),
        }));
      }
      if (layers.length > 6) {
        chips.append(el("span", { class: "st-chip", text: `+${layers.length - 6}` }));
      }
      panel.append(chips);
    }
    return panel;
  }

  function reviewCard() {
    const story = selectedStory();
    const rows = allArtifactsFor();
    const ready = rows.filter(artifactReady);
    const fallback = story
      ? artifacts.filter((item) => artifactReady(item) && artifactStoryId(item) === String(story.id))
      : [];
    const item = ready.find((row) => row.artifact_id === selectedArtifactId)
      || ready[0] || fallback[0] || null;
    const card = el("section", { class: "st-card st-finish-card st-finish-review", "aria-labelledby": "st-finish-review-title" });
    const actions = el("div", { class: "st-finish-review-actions" });
    const checkAgain = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Check again",
    });
    checkAgain.addEventListener("click", () => { void refreshChecks(true, checkAgain); });
    actions.append(checkAgain);
    if (story) {
      const edit = el("button", {
        class: "st-btn st-btn-primary st-btn-small",
        type: "button",
        text: "Edit this moment",
      });
      edit.addEventListener("click", () => openEdit(story.id, aspect));
      actions.append(edit);
    }
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-review-title", text: "Review" }),
        el("p", {
          class: "st-hint",
          text: story
            ? `${storyName(story, selectedIndex())} · ${aspect}. Preview the story and check leftover text.`
            : "No moment selected.",
        }),
      ]),
      actions,
    ]);
    card.append(head);

    const grid = el("div", { class: "st-finish-review-grid" });
    const media = el("div", { class: "st-finish-review-media" });
    if (!currentEdit?.id && item) {
      // A stale Edit cannot render, but the finished story can still be watched.
      const box = el("figure", { class: "st-finish-review-video" });
      box.append(el("figcaption", {
        class: "st-label",
        text: `${artifactLabel(item).replace(" · current", "")} · ${artifactAspect(item)}`,
      }));
      box.append(el("video", {
        src: item.url,
        poster: item.poster_url || null,
        controls: true,
        preload: "metadata",
        playsinline: true,
      }));
      media.append(box);
    } else {
      media.append(reviewPlayer());
    }
    if (item) {
      for (const warning of renderWarnings(item)) {
        media.append(el("p", { class: "st-warning st-finish-review-warning", text: warning }));
      }
      if (artifactStale(item)) {
        media.append(el("p", { class: "st-warning st-finish-review-warning", text: STALE_RENDER_TEXT }));
      }
    }
    media.append(cleanPanel());
    grid.append(media, notesPanel());
    card.append(grid);
    return card;
  }

  function stage(number, title, copy, ...cards) {
    return el("section", { class: "st-finish-stage", "aria-label": title }, [
      el("div", { class: "st-finish-stage-head" }, [
        el("span", { class: "st-finish-stage-num", "aria-hidden": "true", text: number }),
        el("div", {}, [
          el("h2", { text: title }),
          el("p", { class: "st-hint", text: copy }),
        ]),
      ]),
      ...cards,
    ]);
  }

  /** A compact segmented picker for the render setup row. */
  function segmented(label, options, value, onPick) {
    const group = el("div", { class: "st-seg-group" }, [
      el("span", { class: "st-label", text: label }),
    ]);
    const row = el("div", {
      class: "st-seg",
      role: "group",
      "aria-label": label,
    });
    for (const option of options) {
      const button = el("button", {
        class: "st-seg-btn",
        type: "button",
        text: option.label,
        title: option.title || option.label,
        disabled: option.disabled === true,
        "aria-pressed": option.value === value ? "true" : "false",
      });
      button.addEventListener("click", () => onPick(option.value));
      row.append(button);
    }
    group.append(row);
    return group;
  }

  function advancedCard() {
    const details = el("details", { class: "st-finish-advanced" });
    details.append(
      el("summary", {}, [
        el("span", { text: "Version history and edit history" }),
        el("small", { text: "Older renders, earlier edits and copy-to-all" }),
      ]),
      el("div", { class: "st-finish-advanced-body" }, [versionsCard(), applyCard()]),
    );
    return details;
  }

  function renderAll() {
    keepArtifactSelection();
    clear(dom.body);
    if (!stories().length) {
      renderEmpty(
        "No moments yet",
        "Find or build a moment before finishing. Finish renders one moment at a time with its own shape and version history.",
        "moments",
        "Go to Moments",
      );
      return;
    }
    dom.body.append(
      stage("01", "Review", "Preview the story and check leftover text before rendering another version.", reviewCard()),
      stage("02", "Render", "One shape and quality for this set. Queue one moment or all of them; every render is a new version.", el("div", { class: "st-finish-render-grid" }, [storyCard(), queueCard()])),
      stage("03", "Publish", "Build the kit for a ready story, then share one exact version with a private link.", el("div", { class: "st-finish-publish-grid" }, [
        el("div", { class: "st-finish-publish-left" }, [packetCard(), shareCard()]),
        finishedCard(),
      ])),
      advancedCard(),
    );
    paintFillOptions();
  }

  function setPicker() {
    if (sets.length <= 1) return null;
    const label = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Story set" })]);
    const select = el("select", { "aria-label": "Story set" });
    for (const set of sets) {
      const stamp = set.created
        ? new Date(Number(set.created) * 1000).toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        })
        : set.id;
      select.append(el("option", {
        value: set.id,
        text: set.kind === "full_video"
          ? "Full video"
          : `${stamp} · ${formatCount(set.stories?.length, "story", "stories")}`,
        selected: set.id === activeSetId,
      }));
    }
    select.addEventListener("change", () => {
      activeSetId = select.value;
      selectedStoryId = stories()[0]?.id || "";
      selectedArtifactId = "";
      packetArtifactId = "";
      shareArtifactId = "";
      compareA = "";
      compareB = "";
      trimHealth.clear();
      clearRepair();
      keepArtifactSelection();
      void refreshChecks();
      renderAll();
      void loadTrimHealth({ force: true }).then(() => { if (!disposed) renderAll(); });
    });
    label.append(select);
    return label;
  }

  function storyCard() {
    const card = el("section", { class: "st-card st-finish-card st-finish-render", "aria-labelledby": "st-finish-render-title" });
    const set = activeSet();
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-render-title", text: "Render" }),
        el("p", {
          class: "st-hint",
          text: `${formatCount(stories().length, "moment")} in this set. Shape comes from Edit; pick quality here. Every render is a new version.`,
        }),
      ]),
      setPicker(),
    ]);
    card.append(head);
    const fillNote = el("p", { class: "st-hint st-finish-fill-note", text: fillEstimate.text, hidden: !fillEstimate.text });
    void loadFillEstimate();

    const staleIds = new Set(staleStoryIds(aspect));
    const setup = el("div", { class: "st-finish-setup" });
    const fields = el("div", { class: "st-finish-setup-fields" });

    fields.append(segmented(
      "Quality",
      [
        { value: "360", label: "360", title: QUALITY_LABELS["360"] },
        { value: "draft", label: "540", title: QUALITY_LABELS.draft },
        { value: "720", label: "720", title: QUALITY_LABELS["720"] },
        { value: "final", label: "1080", title: QUALITY_LABELS.final },
        { value: "1440", label: "2K", title: QUALITY_LABELS["1440"] },
        { value: "2160", label: "4K", title: QUALITY_LABELS["2160"] },
      ],
      quality,
      (value) => {
        quality = value;
        renderRenderCard();
      },
    ));
    fields.append(el("div", { class: "st-finish-fill-options", hidden: !(fillEstimate.beats > 0) }));
    void loadRenderOptions();

    const liveCount = stories().filter((story) => (
      liveQueueItem(String(story.id || ""), aspect, true)
    )).length;
    const allLive = stories().length > 0 && liveCount === stories().length;
    const queueAll = el("button", {
      class: "st-btn st-btn-primary st-finish-queue-all",
      type: "button",
      text: allLive ? "Queued" : `Queue ${formatCount(stories().length, "moment")}`,
      disabled: busy || staleIds.size > 0 || allLive,
      title: staleIds.size
        ? "Repair every stale shape before queueing. A stale Edit never renders."
        : allLive
          ? `Every moment is already queued with these choices. Pick another quality or AI fill choice to queue again.`
          : `Queue every moment in ${ASPECT_LABELS[aspect] || aspect} at ${QUALITY_LABELS[quality] || quality}.`,
    });
    queueAll.addEventListener("click", () => { void queueStories(stories(), queueAll); });
    setup.append(fields, queueAll);
    card.append(setup);

    card.append(el("p", { class: "st-finish-render-summary" }, [
      el("span", { text: formatCount(stories().length, "moment") }),
      el("span", { class: "st-finish-summary-dot", "aria-hidden": "true", text: "·" }),
      el("span", { text: ASPECT_LABELS[aspect] || aspect }),
      el("span", { class: "st-finish-summary-dot", "aria-hidden": "true", text: "·" }),
      el("span", { text: QUALITY_LABELS[quality] || quality }),
      ...(queuedMethod() ? [
        el("span", { class: "st-finish-summary-dot", "aria-hidden": "true", text: "·" }),
        el("span", { text: FILL_MODEL_LABELS[queuedMethod()] }),
      ] : []),
      ...(queuedDevice() === "gpu" ? [
        el("span", { class: "st-finish-summary-dot", "aria-hidden": "true", text: "·" }),
        el("span", { text: "GPU" }),
      ] : []),
      ...(queuedFollow() ? [
        el("span", { class: "st-finish-summary-dot", "aria-hidden": "true", text: "·" }),
        el("span", { text: "Follow camera motion" }),
      ] : []),
    ]));
    card.append(fillNote);
    card.append(el("p", {
      class: "st-finish-cost-note",
      text: "Cloud voices and music call providers and may cost credits. Check the moment's Audio panel before queueing.",
    }));
    if (staleIds.size) {
      card.append(el("p", {
        class: "st-trim-stale-inline",
        text: `${formatCount(staleIds.size, "story", "stories")} changed after its Edit. Repair before queueing; a stale Edit never renders.`,
      }));
    }
    if (set?.note) card.append(el("p", { class: "st-hint", text: set.note }));

    const list = el("div", { class: "st-finish-story-list" });
    stories().forEach((story, index) => {
      const storyId = String(story.id || "");
      const all = allArtifactsFor(storyId, aspect);
      const current = selectedStory()?.id === storyId;
      const stale = staleIds.has(storyId);
      const row = el("article", { class: `st-finish-story${current ? " is-active" : ""}${stale ? " is-stale" : ""}` });
      const title = el("button", {
        class: "st-finish-story-title",
        type: "button",
        "aria-pressed": current ? "true" : "false",
      }, [
        el("span", { class: "st-story-number", text: String(index + 1).padStart(2, "0") }),
        el("strong", { text: storyName(story, index) }),
      ]);
      title.addEventListener("click", () => {
        selectedStoryId = storyId;
        selectedArtifactId = "";
        packetArtifactId = "";
        shareArtifactId = "";
        compareA = "";
        compareB = "";
        reviewPicked = false;
        reviewTime = 0;
        keepArtifactSelection();
        void refreshChecks();
        renderAll();
      });
      const shapeChips = ASPECTS.flatMap((shapeValue) => {
        const rows = allArtifactsFor(storyId, shapeValue);
        const ready = rows.find(artifactReady) || null;
        const latestShape = ready || rows[0] || null;
        const live = liveQueueItem(storyId, shapeValue);
        // Shape is chosen in Edit, so Finish shows that shape only.
        if (shapeValue !== aspect) return [];
        let text;
        if (live) {
          text = `${shapeValue} · ${statusText(live.state)}`;
        } else if (latestShape) {
          text = `${shapeValue} · ${latestShape.status === "ready"
            ? artifactLabel(latestShape).replace(" · current", "")
            : statusText(latestShape.status)}`;
        } else {
          text = `${shapeValue} · Not rendered`;
        }
        const tone = live
          ? (live.state === "running" ? "st-chip-busy" : "")
          : latestShape?.status === "ready" ? "st-chip-ok"
            : latestShape?.status === "failed" ? "st-chip-bad"
              : latestShape?.status ? "st-chip-busy" : "";
        return [el("span", { class: `st-chip ${tone}`.trim(), text })];
      });
      const meta = el("div", { class: "st-finish-story-meta" }, [
        el("span", { class: "st-mono st-hint", text: formatDuration(storyDuration(story)) }),
        ...shapeChips,
        all.length > 1 ? el("span", { class: "st-chip", text: formatCount(all.length, "version") }) : null,
        stale ? el("span", { class: "st-chip st-chip-bad", text: "Edit stale" }) : null,
      ]);
      const actions = el("div", { class: "st-finish-story-actions" });
      const live = liveQueueItem(storyId, aspect, true);
      const queueOne = live
        ? el("span", {
          class: "st-chip st-chip-busy",
          text: statusText(live.state),
          title: `This moment is already ${statusText(live.state).toLowerCase()} with these choices. Pick another quality or AI fill choice to queue again.`,
        })
        : el("button", {
          class: "st-btn st-btn-quiet st-btn-small st-finish-queue-one",
          type: "button",
          text: "Queue",
          "aria-label": `Queue ${storyName(story, index)} in ${aspect}`,
          disabled: busy || stale,
          title: stale
            ? "Repair this shape first; a stale Edit never renders."
            : `Queue this moment in ${aspect}.`,
        });
      if (!live) {
        queueOne.addEventListener("click", () => { void queueStories([story], queueOne); });
        actions.append(queueOne);
      }
      if (stale) {
        const repair = el("button", {
          class: "st-btn st-btn-primary st-btn-small",
          type: "button",
          text: "Repair",
          title: "Rebind this shape's Edit to the current story range.",
        });
        repair.addEventListener("click", () => { void repairStory(storyId, aspect, repair); });
        actions.append(repair);
      }
      row.append(title, meta, actions);
      list.append(row);
    });
    card.append(el("h3", { class: "st-finish-list-title", text: "Moments" }), list);
    return card;
  }

  function renderReviewCard() {
    const existing = dom.body.querySelector(".st-finish-review");
    if (existing) existing.replaceWith(reviewCard());
  }

  /** The Render card alone, so a choice or a poll never reloads the review video. */
  function renderRenderCard() {
    const existing = dom.body.querySelector(".st-finish-render");
    if (!existing) return;
    existing.replaceWith(storyCard());
    paintFillOptions();
  }

  function renderStoryCard() {
    renderRenderCard();
    renderReviewCard();
  }

  function queuesForJob() {
    const jobId = String(job?.id || "");
    return queues.filter((queue) => {
      const items = Array.isArray(queue.items) ? queue.items : [];
      if (!items.length) return true;
      return !jobId || items.some((item) => String(item.job_id || "") === jobId);
    });
  }

  function splitQueues() {
    const rows = queuesForJob();
    const active = rows.filter((queue) => {
      const status = String(queue.status || "queued");
      return ACTIVE_QUEUE.has(status) || queue.needs_resume || status === "paused";
    });
    const history = rows.filter((queue) => !active.includes(queue));
    return { active: queueRunOrder(active), history };
  }

  function queueRow(queue, liveBlock) {
    const status = String(queue.status || "queued");
    const items = Array.isArray(queue.items) ? queue.items : [];
    const running = items.find((item) => String(item.state) === "running")
      || items.find((item) => String(item.state) === "queued")
      || null;
    const failed = items.filter((item) => String(item.state) === "failed");
    const done = items.filter((item) => String(item.state) === "done").length;
    const progress = Math.max(0, Math.min(1, Number(queue.progress) || 0));
    const title = running?.title || items[0]?.title || queue.message || statusText(status);
    const shape = running?.aspect || items[0]?.aspect || "";
    // One moment: its own honest estimate. Several: the queue total, which
    // already includes what is waiting.
    const eta = Number(items.length > 1 ? queue.eta : (running?.eta ?? queue.eta));
    const hasEta = Number.isFinite(eta) && eta > 0;
    const active = ACTIVE_QUEUE.has(status);
    const waitingTurn = active && !items.some((item) => String(item.state) === "running");
    const percent = Math.round(progress * 100);

    const row = el("div", { class: `st-finish-queue-row${liveBlock ? " is-live" : ""}` });
    const top = el("div", { class: "st-finish-queue-top" }, [
      el("span", {
        class: `st-chip st-chip-${waitingTurn ? "quiet" : statusTone(status)}`,
        text: waitingTurn ? "Waiting" : statusText(status),
      }),
      el("strong", { class: "st-finish-queue-title", text: title }),
      shape ? el("span", {
        class: "st-mono st-finish-queue-shape",
        text: [
          shape,
          QUEUE_QUALITY[running?.quality || items[0]?.quality] || "",
          ...queueMethodWords(running || items[0], rowFallbackModel(running || items[0])),
        ].filter(Boolean).join(" · "),
      }) : null,
      el("span", { class: "st-mono st-finish-queue-percent", text: `${percent}%` }),
    ]);
    const track = el("div", {
      class: "st-progress-bar",
      role: "progressbar",
      "aria-valuemin": "0",
      "aria-valuemax": "100",
      "aria-valuenow": String(percent),
    });
    track.append(el("i", { style: `width:${percent}%` }));

    const foot = el("div", { class: "st-finish-queue-foot" });
    const facts = [];
    if (items.length > 1) facts.push(`${done} of ${items.length} done`);
    if (active && hasEta) facts.push(`about ${etaText(eta)} left`);
    if (!active && queue.created) facts.push(shortDate(queue.created));
    const took = active ? "" : tookText(queueTook(items));
    if (took) facts.push(`Took ${took}`);
    foot.append(el("span", { class: "st-hint", text: facts.join(" · ") }));

    const actions = el("div", { class: "st-finish-queue-actions" });
    if (active) {
      const pause = el("button", {
        class: "st-btn st-btn-quiet st-btn-small",
        type: "button",
        text: "Pause",
        dataset: { action: "pause", queueId: String(queue.id || "") },
      });
      pause.addEventListener("click", () => { void queueAction(queue.id, "pause", pause); });
      const cancel = el("button", {
        class: "st-btn st-btn-quiet st-btn-small st-finish-cancel",
        type: "button",
        text: "Cancel",
        dataset: { action: "cancel", queueId: String(queue.id || "") },
      });
      cancel.addEventListener("click", () => { void queueAction(queue.id, "cancel", cancel); });
      actions.append(pause, cancel);
    } else if (queue.needs_resume || status === "paused") {
      const resume = el("button", {
        class: "st-btn st-btn-ghost st-btn-small",
        type: "button",
        text: "Resume",
        dataset: { action: "resume", queueId: String(queue.id || "") },
      });
      resume.addEventListener("click", () => { void queueAction(queue.id, "resume", resume); });
      actions.append(resume);
    }
    if (!active) {
      const remove = el("button", {
        class: "st-btn st-btn-quiet st-btn-small st-finish-cancel",
        type: "button",
        text: "Delete",
        dataset: { action: "delete", queueId: String(queue.id || "") },
        title: "Remove this queue record. Renders and files stay.",
      });
      remove.addEventListener("click", () => { void deleteQueue(queue, remove); });
      actions.append(remove);
    }
    foot.append(actions);

    let list = null;
    if (items.length > 1) {
      list = el("div", { class: "st-finish-queue-items" });
      for (const item of items) {
        const itemState = String(item.state || "queued");
        list.append(el("div", { class: `st-finish-queue-item is-${itemState}` }, [
          el("span", {
            class: "st-finish-queue-dot",
            "aria-hidden": "true",
            title: statusText(itemState),
          }),
          el("span", { class: "st-finish-queue-name", text: item.title || item.story_id }),
          el("span", { class: "st-mono st-hint", text: item.aspect || "9:16" }),
          el("span", {
            class: "st-mono st-hint",
            text: itemState === "running" ? itemProgressText(item) : statusText(itemState),
          }),
        ]));
      }
    }

    row.append(top, track);
    if (list) row.append(list);
    for (const item of failed) {
      row.append(el("p", { class: "st-finish-queue-error", text: failureReason(item) }));
    }
    if (!failed.length && queue.error) {
      row.append(el("p", { class: "st-finish-queue-error", text: failureReason(queue) }));
    }
    row.append(foot);
    return row;
  }

  function queueTabButton(id, label, count) {
    const button = el("button", {
      class: "st-finish-queue-tab",
      type: "button",
      role: "tab",
      "aria-selected": queueTab === id ? "true" : "false",
    }, [
      el("span", { text: label }),
      el("span", { class: "st-finish-queue-count", text: String(count) }),
    ]);
    button.addEventListener("click", () => {
      queueTab = id;
      renderQueueCard();
    });
    return button;
  }

  function queueCard() {
    const { active, history } = splitQueues();
    const summary = queueSummary(queues, { jobId: job?.id || "", setId: activeSetId });
    const card = el("section", {
      class: "st-card st-finish-queue-card",
      "aria-labelledby": "st-finish-queue-title",
    });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-queue-title", text: "Queue" }),
        el("p", { class: "st-hint", text: summary.text }),
      ]),
    ]));
    card.append(el("div", {
      class: "st-finish-queue-tabs",
      role: "tablist",
      "aria-label": "Render queue tabs",
    }, [
      queueTabButton("queue", "Queue", active.length),
      queueTabButton("history", "History", history.length),
    ]));
    const body = el("div", { class: "st-finish-queue-body", role: "tabpanel" });
    const rows = queueTab === "queue" ? active : history;
    if (!rows.length) {
      body.append(el("p", {
        class: "st-hint",
        text: queueTab === "queue"
          ? "Nothing is rendering. Add a moment from the list."
          : "No finished or cancelled queue yet.",
      }));
    }
    for (const queue of rows) body.append(queueRow(queue, queueTab === "queue"));
    card.append(body);
    return card;
  }

  function renderQueueCard() {
    const card = dom.body.querySelector(".st-finish-queue-card");
    if (!card) return;
    const active = document.activeElement;
    const action = active?.dataset?.action || "";
    const queueId = active?.dataset?.queueId || "";
    const body = card.querySelector(".st-finish-queue-body");
    const scroll = body?.scrollTop || 0;
    card.replaceWith(queueCard());
    const nextBody = dom.body.querySelector(".st-finish-queue-body");
    if (nextBody) nextBody.scrollTop = scroll;
    if (action && queueId) {
      dom.body.querySelector(`[data-action="${action}"][data-queue-id="${queueId}"]`)?.focus();
    }
  }

  function versionsCard() {
    const story = selectedStory();
    if (!story) return el("div");
    const card = el("section", { class: "st-card st-finish-card st-finish-versions", "aria-labelledby": "st-finish-versions-title" });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-versions-title", text: "Versions" }),
        el("p", {
          class: "st-hint",
          text: `${storyName(story, selectedIndex())} · ${aspect}. Old renders and old edits stay side by side.`,
        }),
      ]),
      downloadAllButton(),
    ]));

    const rows = allArtifactsFor();
    const readyRows = rows.filter(artifactReady);
    const selectedRow = rows.find((item) => item.artifact_id === selectedArtifactId)
      || readyRows[0] || null;
    const selectedWarnings = selectedRow ? renderWarnings(selectedRow) : [];
    if (selectedWarnings.length) {
      card.append(el("div", { class: "st-finish-current-warnings" },
        selectedWarnings.map((warning) => el("p", { class: "st-warning", text: warning }))));
    }
    if (!rows.length) {
      card.append(el("p", { class: "st-hint", text: "No render for this story and shape yet. Queue it in Render." }));
    } else {
      const list = el("div", { class: "st-layer-list st-finish-version-list" });
      for (const item of rows) {
        const ready = artifactReady(item);
        const active = item.artifact_id === selectedArtifactId;
        const stale = artifactStale(item);
        const row = el("div", { class: `st-finish-version${active ? " is-active" : ""}${stale ? " is-stale" : ""}` }, [
          el("span", {
            class: `st-chip ${ready ? "st-chip-ok" : item.status === "failed" ? "st-chip-bad" : "st-chip-busy"}`,
            text: ready ? (stale ? "Changed since render" : (item.versions?.label || `v${item.version || "?"}`)) : statusText(item.status),
          }),
          el("span", { class: "st-finish-version-copy" }, [
            el("strong", { text: artifactLabel(item).replace(" · current", "") }),
            el("small", {
              text: [
                stale ? STALE_RENDER_TEXT : "",
                !stale && item.pinned ? "Pinned" : "",
                !stale && item.cue_count ? formatCount(item.cue_count, "caption") : "",
              ].filter(Boolean).join(" · ") || "Ready to share",
            }),
          ]),
        ]);
        const actions = el("div", { class: "st-finish-version-actions" });
        if (ready) {
          const use = el("button", {
            class: "st-btn st-btn-ghost st-btn-small",
            type: "button",
            text: active ? "Selected" : "Choose",
            disabled: active,
          });
          use.addEventListener("click", () => {
            selectedArtifactId = item.artifact_id;
            packetArtifactId = item.artifact_id;
            shareArtifactId = item.artifact_id;
            renderVersionsCard();
            renderReviewCard();
            renderPacketCard();
            renderShareCard();
          });
          const pin = el("button", {
            class: "st-btn st-btn-quiet st-btn-small",
            type: "button",
            text: item.pinned ? "Unpin" : "Keep",
          });
          pin.addEventListener("click", () => { void togglePin(item, pin); });
          const download = el("a", {
            class: "st-btn st-btn-ghost st-btn-small",
            href: item.url,
            download: downloadName(item, selectedIndex()),
            text: "Download",
          });
          const reveal = el("button", {
            class: "st-btn st-btn-quiet st-btn-small",
            type: "button",
            text: "Show in Finder",
          });
          reveal.addEventListener("click", () => { void revealArtifact(item, reveal); });
          actions.append(use, download, reveal, pin);
        } else if (["failed", "interrupted"].includes(String(item.status || ""))) {
          const retry = el("button", {
            class: "st-btn st-btn-primary st-btn-small",
            type: "button",
            text: "Retry",
            disabled: busy,
          });
          retry.addEventListener("click", () => {
            void queueStories([story], retry, artifactAspect(item));
          });
          actions.append(retry);
        }
        row.append(actions);
        if (ready) {
          for (const warning of renderWarnings(item)) {
            row.append(el("p", {
              class: "st-warning st-finish-version-warning",
              text: warning,
            }));
          }
        } else if (["failed", "interrupted"].includes(String(item.status || ""))) {
          row.append(el("p", { class: "st-error st-finish-version-error", text: failureReason(item) }));
        }
        row.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          if (!ready) return;
          selectedArtifactId = item.artifact_id;
          packetArtifactId = item.artifact_id;
          shareArtifactId = item.artifact_id;
          renderVersionsCard();
          renderReviewCard();
          renderPacketCard();
          renderShareCard();
        });
        list.append(row);
      }
      card.append(list);

      if (readyRows.length === 1) {
        // One finished cut still gets a player; compare needs two.
        const item = readyRows[0];
        const box = el("figure", { class: "st-finish-compare-video st-finish-single-video" });
        box.append(el("figcaption", { class: "st-label", text: artifactLabel(item).replace(" · current", "") }));
        box.append(el("video", {
          src: item.url,
          poster: item.poster_url || null,
          controls: true,
          preload: "metadata",
          playsinline: true,
        }));
        card.append(box);
      }
      if (readyRows.length > 1) {
        const compare = el("div", { class: "st-finish-compare" });
        const pick = (which) => {
          const label = el("label", { class: "st-field st-field-inline" }, [el("span", { text: which })]);
          const select = el("select", { "aria-label": `Compare ${which}` });
          for (const item of readyRows) {
            select.append(el("option", {
              value: item.artifact_id,
              text: artifactLabel(item).replace(" · current", ""),
              selected: (which === "A" ? compareA : compareB) === item.artifact_id,
            }));
          }
          select.addEventListener("change", () => {
            if (which === "A") compareA = select.value;
            else compareB = select.value;
            renderVersionsCard();
          });
          label.append(select);
          return label;
        };
        compare.append(pick("A"), pick("B"));
        const videos = el("div", { class: "st-finish-compare-videos" });
        for (const [which, id] of [["A", compareA], ["B", compareB]]) {
          const item = readyRows.find((row) => row.artifact_id === id) || readyRows[0];
          const box = el("figure", { class: "st-finish-compare-video" });
          box.append(el("figcaption", { class: "st-label", text: `${which} · ${artifactLabel(item).replace(" · current", "")}` }));
          box.append(el("video", {
            src: item?.url || "",
            poster: item?.poster_url || null,
            controls: true,
            preload: "metadata",
            playsinline: true,
          }));
          videos.append(box);
        }
        compare.append(videos);
        card.append(compare);
      }
    }

    const editCard = el("div", { class: "st-finish-edits" });
    const head = editHead();
    const editRows = editRowsFor();
    editCard.append(el("div", { class: "st-finish-subhead" }, [
      el("h3", { text: "Edit history" }),
      el("span", { class: "st-hint", text: head ? `${formatCount(editRows.length, "version")} · current` : "No edit for this story and shape" }),
    ]));
    if (!editRows.length) {
      editCard.append(el("p", { class: "st-hint", text: "This story has not been shaped in this shape yet. Edit it first, then render again." }));
    } else {
      const editList = el("div", { class: "st-layer-list" });
      for (const row of editRows.slice(0, 12)) {
        const isCurrent = row.id === head;
        const line = el("div", { class: "st-finish-version" }, [
          el("span", { class: `st-chip ${isCurrent ? "st-chip-ok" : ""}`, text: `Version ${row.version}` }),
          el("span", { class: "st-finish-version-copy" }, [
            el("strong", { text: isCurrent ? "Current edit" : "Earlier edit" }),
            el("small", {
              text: [
                row.created ? shortDate(row.created) : "",
                row.layer_counts?.clean ? `${row.layer_counts.clean} clean` : "",
                row.layer_counts?.graphics ? formatCount(row.layer_counts.graphics, "graphic") : "",
              ].filter(Boolean).join(" · ") || "Saved",
            }),
          ]),
        ]);
        if (!isCurrent && head) {
          const use = el("button", {
            class: "st-btn st-btn-ghost st-btn-small",
            type: "button",
            text: "Use this version",
          });
          use.addEventListener("click", () => { void restoreEdit(head, row.id, use); });
          line.append(use);
        }
        editList.append(line);
      }
      editCard.append(editList);
    }
    card.append(editCard);
    return card;
  }

  function renderVersionsCard() {
    const existing = dom.body.querySelector(".st-finish-versions");
    if (!existing) return;
    existing.replaceWith(versionsCard());
  }

  async function refreshChecks(manual = false, button = null) {
    if (manual && button) {
      button.disabled = true;
      button.textContent = "Checking…";
    }
    if (manual) announce("Reading checks…");
    try {
      await loadChecks();
      if (disposed) return;
      const existing = dom.body.querySelector(".st-finish-review");
      if (existing) existing.replaceWith(reviewCard());
      if (manual) announce(checks.markers.length ? `${formatCount(checks.markers.length, "note")} for this story.` : "No notes for this story.", checks.markers.length ? "" : "ok");
    } catch (error) {
      if (disposed) return;
      if (manual) announce(error?.message || "Checks could not run.", "bad");
    } finally {
      if (button?.isConnected) {
        button.disabled = false;
        button.textContent = "Check again";
      }
    }
  }

  function packetCard() {
    const card = el("section", { class: "st-card st-finish-card st-finish-packet", "aria-labelledby": "st-finish-packet-title" });
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-packet-title", text: "Publish kit" }),
        el("p", { class: "st-hint", text: "One ready story, three titles, one description and three to eight hashtags. The kit carries the video, captions and covers." }),
      ]),
    ]);
    card.append(head);

    const ready = readyArtifacts();
    if (!ready.length) {
      card.append(el("p", { class: "st-hint", text: "No ready story yet. Queue a render first." }));
      return card;
    }
    const artifact = packetArtifact() || preferredReadyArtifact(ready);
    if (!artifact) return card;
    // Build uses the cut this card shows, including the first-ready fallback.
    packetArtifactId = artifact.artifact_id;

    card.append(el("div", { class: "st-finish-picked" }, [
      el("span", { class: "st-label", text: "Story" }),
      el("strong", { text: artifactStoryLabel(artifact) }),
      el("span", {
        class: "st-hint",
        text: `${artifactAspect(artifact)} · ${artifactLabel(artifact).replace(" · current", "")}`,
      }),
    ]));

    if (!packetDraft || packetDraft.artifact_id !== artifact.artifact_id) {
      initPacketDraft(artifact);
    }

    const grid = el("div", { class: "st-finish-form-grid" });
    for (const [index, title] of packetDraft.titles.entries()) {
      const input = el("input", {
        type: "text",
        maxlength: "100",
        value: title,
        "aria-label": `Title ${index + 1}`,
      });
      input.addEventListener("input", () => { packetDraft.titles[index] = input.value; });
      grid.append(el("label", { class: "st-field" }, [
        el("span", { text: `Title ${index + 1}` }),
        input,
        el("small", { class: "st-field-hint", text: `${input.value.length}/100` }),
      ]));
    }
    const description = el("textarea", { rows: "3", maxlength: "125", "aria-label": "Description" });
    description.value = packetDraft.description;
    const descCount = el("small", { class: "st-field-hint", text: `${packetDraft.description.length}/125` });
    description.addEventListener("input", () => {
      packetDraft.description = description.value;
      descCount.textContent = `${description.value.length}/125`;
    });
    grid.append(el("label", { class: "st-field st-finish-field-wide" }, [
      el("span", { text: "Description" }),
      description,
      descCount,
    ]));
    const hashtags = el("input", {
      type: "text",
      value: packetDraft.hashtags,
      "aria-label": "Hashtags",
      placeholder: "#shorts #story #video",
    });
    hashtags.addEventListener("input", () => { packetDraft.hashtags = hashtags.value; });
    grid.append(el("label", { class: "st-field" }, [
      el("span", { text: "Hashtags" }),
      hashtags,
      el("small", { class: "st-field-hint", text: "Three to eight, separated by spaces." }),
    ]));
    const pin = el("input", { type: "text", value: packetDraft.pin_comment, "aria-label": "Pinned comment", maxlength: "500" });
    pin.addEventListener("input", () => { packetDraft.pin_comment = pin.value; });
    grid.append(el("label", { class: "st-field" }, [
      el("span", { text: "Pinned comment" }),
      pin,
      el("small", { class: "st-field-hint", text: "Optional. Appears in the kit copy." }),
    ]));
    const covers = el("div", { class: "st-finish-cover-row" });
    for (const [index, time] of packetDraft.cover_times.entries()) {
      const input = el("input", {
        type: "number",
        min: "0",
        step: "0.1",
        value: String(time),
        "aria-label": `Cover ${index + 1} time`,
      });
      input.addEventListener("input", () => {
        packetDraft.cover_times[index] = Number(input.value) || 0;
      });
      covers.append(el("label", { class: "st-field" }, [
        el("span", { text: `Cover ${index + 1} · seconds` }),
        input,
      ]));
    }
    grid.append(el("div", { class: "st-field" }, [
      el("span", { text: "Covers" }),
      covers,
      el("small", { class: "st-field-hint", text: "Two frames from the exact story." }),
    ]));
    card.append(grid);

    const actions = el("div", { class: "st-layer-add" });
    const build = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: packetBusy ? "Building…" : "Build publish kit",
      disabled: packetBusy,
    });
    build.addEventListener("click", () => { void buildPacket(build); });
    actions.append(build);
    card.append(actions);

    if (packets.length) {
      const history = el("div", { class: "st-finish-history" });
      history.append(el("h3", { text: "Recent kits" }));
      for (const item of packets.slice(0, 6)) {
        const id = String(item.packet_id || "");
        const link = packetDownload(item, job?.id || ctx.getJobId());
        history.append(el("div", { class: "st-finish-history-row" }, [
          el("span", { class: "st-mono st-hint", text: id ? id.slice(0, 8) : "Kit" }),
          el("span", { class: "st-finish-history-copy" }, [
            el("strong", { text: item.title || item.story_id || "Publish kit" }),
            el("small", { text: item.created ? new Date(Number(item.created) * 1000).toLocaleString() : "" }),
          ]),
          link ? el("a", { class: "st-btn st-btn-ghost st-btn-small", href: link, text: "Download" }) : null,
        ]));
      }
      card.append(history);
    }
    return card;
  }

  function initPacketDraft(artifact) {
    const storyId = artifactStoryId(artifact);
    const index = stories().findIndex((row) => String(row.id) === storyId);
    const story = stories()[index] || selectedStory();
    const hook = String(story?.hook?.text || story?.title || "").replace(/\s+/g, " ").trim();
    const description = (hook || storyName(story, index < 0 ? 0 : index)).slice(0, 125);
    packetDraft = {
      artifact_id: artifact?.artifact_id || "",
      titles: defaultTitles(story, index < 0 ? 0 : index),
      description,
      hashtags: "#shorts #story #video",
      cover_times: coverDefaults(story, artifact),
      pin_comment: "",
    };
  }

  function renderPacketCard() {
    const existing = dom.body.querySelector(".st-finish-packet");
    if (!existing) return;
    existing.replaceWith(packetCard());
  }

  async function buildPacket(button) {
    const artifact = packetArtifact();
    if (!job || !artifact || !packetDraft) return;
    const titles = packetDraft.titles.map((value) => String(value || "").trim()).filter(Boolean);
    if (titles.length !== 3) {
      announce("Write three titles before building the kit.", "bad");
      return;
    }
    if (!String(packetDraft.description || "").trim()) {
      announce("Write a short description before building the kit.", "bad");
      return;
    }
    const tags = parseHashtags(packetDraft.hashtags);
    if (tags.length < 3) {
      announce("Add at least three hashtags.", "bad");
      return;
    }
    const cover = (packetDraft.cover_times || []).map((value) => Number(value)).filter(Number.isFinite);
    if (cover.length !== 2) {
      announce("Set two cover times in seconds.", "bad");
      return;
    }
    packetBusy = true;
    button.disabled = true;
    button.textContent = "Building…";
    announce("Building the publish kit. This writes the video, captions and covers…");
    clearError();
    const body = {
      story_id: artifactStoryId(artifact),
      titles,
      description: String(packetDraft.description).trim(),
      hashtags: tags,
      cover_times: cover,
      pin_comment: String(packetDraft.pin_comment || "").trim(),
    };
    try {
      let result;
      try {
        result = await request(
          `${jobRoot(job.id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/packet`,
          { method: "POST", body },
        );
      } catch (error) {
        if (![404, 405, 501].includes(Number(error?.status))) throw error;
        result = await request(`${jobRoot(job.id)}/packets`, {
          method: "POST",
          body: {
            ...body,
            artifact_ids: [artifact.artifact_id],
          },
        });
      }
      const packet = normalizePacket(result);
      await loadPackets();
      if (disposed) return;
      renderPacketCard();
      const link = packetDownload(packet, job.id);
      announce(
        link
          ? `Publish kit ready. ${packet?.packet_id ? `Kit ${String(packet.packet_id).slice(0, 8)}. ` : ""}Download it below.`
          : "Publish kit ready. It appears in the recent kits list.",
        "ok",
      );

    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not build the publish kit.", "bad");
    } finally {
      packetBusy = false;
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = "Build publish kit";
      }
    }
  }

  function shareCard() {
    const card = el("section", { class: "st-card st-finish-card st-finish-share", "aria-labelledby": "st-finish-share-title" });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-share-title", text: "Review link" }),
        el("p", { class: "st-hint", text: "A private link to one exact story. It never points at a newer render." }),
      ]),
    ]));
    const ready = readyArtifacts();
    if (!ready.length) {
      card.append(el("p", { class: "st-hint", text: "Render a story before making a review link." }));
      return card;
    }
    const artifact = shareArtifact() || preferredReadyArtifact(ready);
    card.append(el("div", { class: "st-finish-picked" }, [
      el("span", { class: "st-label", text: "Story" }),
      el("strong", { text: artifactStoryLabel(artifact) }),
      el("span", {
        class: "st-hint",
        text: `${artifactAspect(artifact)} · ${artifactLabel(artifact).replace(" · current", "")}`,
      }),
    ]));
    const expiry = el("select", { "aria-label": "Link expiry" });
    for (const [value, label] of [["7", "7 days"], ["30", "30 days"], ["90", "90 days"], ["0", "No expiry"]]) {
      expiry.append(el("option", { value, text: label, selected: value === shareExpiry }));
    }
    expiry.addEventListener("change", () => { shareExpiry = expiry.value; });

    const label = el("input", {
      type: "text",
      maxlength: "120",
      value: shareLabel,
      placeholder: "Who is this for?",
      "aria-label": "Review link label",
    });
    label.addEventListener("input", () => { shareLabel = label.value; });

    const make = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: shareBusy ? "Making link…" : "Make review link",
      disabled: shareBusy,
    });
    make.addEventListener("click", () => { void createShare(make); });
    card.append(
      el("div", { class: "st-finish-form-grid" }, [
        el("label", { class: "st-field" }, [el("span", { text: "Expires" }), expiry]),
        el("label", { class: "st-field" }, [el("span", { text: "Label" }), label]),
      ]),
      el("div", { class: "st-layer-add" }, [make]),
    );

    if (sessionLinks.length) {
      const list = el("div", { class: "st-finish-history" });
      list.append(el("h3", { text: "Links from this session" }));
      for (const link of sessionLinks.slice().reverse()) {
        const row = el("div", { class: "st-finish-history-row" }, [
          el("span", { class: "st-mono st-hint", text: link.aspect || "9:16" }),
          el("span", { class: "st-finish-history-copy" }, [
            el("strong", { text: link.label || "Review link" }),
            el("a", { class: "st-finish-link", href: link.url, text: link.url, target: "_blank", rel: "noreferrer" }),
          ]),
        ]);
        const copy = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Copy" });
        copy.addEventListener("click", () => { void copyLink(link.url, copy); });
        row.append(copy);
        list.append(row);
      }
      card.append(list);
    }

    if (shares.length) {
      const list = el("div", { class: "st-finish-history" });
      list.append(el("h3", { text: "Open links" }));
      for (const item of shares.slice(0, 8)) {
        const state = String(item.status || "active").toLowerCase();
        list.append(el("div", { class: "st-finish-history-row" }, [
          el("span", {
            class: `st-chip ${state === "active" ? "st-chip-ok" : state === "revoked" ? "st-chip-bad" : ""}`,
            text: state === "active" ? "Active" : state === "revoked" ? "Revoked" : "Expired",
          }),
          el("span", { class: "st-finish-history-copy" }, [
            el("strong", { text: item.label || item.share?.label || "Review link" }),
            el("small", {
              text: [
                item.aspect ? String(item.aspect) : "",
                item.expires_at ? `expires ${new Date(Number(item.expires_at) * 1000).toLocaleDateString()}` : "no expiry",
              ].filter(Boolean).join(" · "),
            }),
          ]),
        ]));
      }
      card.append(list);
    }
    return card;
  }

  function renderShareCard() {
    const existing = dom.body.querySelector(".st-finish-share");
    if (!existing) return;
    existing.replaceWith(shareCard());
  }

  async function copyLink(url, button) {
    try {
      await navigator.clipboard.writeText(url);
      button.textContent = "Copied";
      window.setTimeout(() => { if (button.isConnected) button.textContent = "Copy"; }, 1400);
    } catch (_) {
      window.prompt("Copy this review link", url);
    }
  }

  async function createShare(button) {
    const artifact = shareArtifact() || readyArtifacts()[0];
    if (!job || !artifact) return;
    shareBusy = true;
    button.disabled = true;
    button.textContent = "Making link…";
    announce("Making the review link…");
    clearError();
    try {
      const result = await request(`${jobRoot(job.id)}/share`, {
        method: "POST",
        body: {
          artifact_id: artifact.artifact_id,
          expires_in_days: Number(shareExpiry) || 0,
          label: String(shareLabel || "").trim(),
        },
      });
      if (disposed) return;
      const path = String(result?.url || (result?.token ? `/r/${result.token}` : ""));
      const url = path ? new URL(path, location.origin).toString() : "";
      if (url) {
        sessionLinks.push({
          url,
          label: result?.label || shareLabel || "Review link",
          aspect: result?.aspect || artifactAspect(artifact),
        });
      }
      await loadShares().catch(() => null);
      renderShareCard();
      announce(url ? "Review link ready. Copy it below." : "Review link created.", "ok");
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not make the review link.", "bad");
    } finally {
      shareBusy = false;
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = "Make review link";
      }
    }
  }

  function applyCard() {
    const card = el("section", { class: "st-card st-finish-card st-finish-apply", "aria-labelledby": "st-finish-apply-title" });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-apply-title", text: "Apply to all stories" }),
        el("p", { class: "st-hint", text: "Take the look and sound from one story and put it on the rest. Text and timing stay per story." }),
      ]),
    ]));

    const editable = stories().filter((story) => editRowsFor(story.id, aspect).length);
    if (!editable.length) {
      card.append(el("p", { class: "st-hint", text: "No story has an edit in this shape yet. Shape one story first." }));
      return card;
    }
    if (!editable.some((story) => story.id === applySourceId)) {
      applySourceId = selectedStory()?.id && editable.some((story) => story.id === selectedStory().id)
        ? selectedStory().id
        : editable[0].id;
    }
    const sourceLabel = el("label", { class: "st-field" }, [el("span", { text: "Copy from" })]);
    const source = el("select", { "aria-label": "Copy style from story" });
    editable.forEach((story) => {
      source.append(el("option", {
        value: story.id,
        text: storyName(story, stories().indexOf(story)),
        selected: story.id === applySourceId,
      }));
    });
    source.addEventListener("change", () => { applySourceId = source.value; renderApplyCard(); });
    sourceLabel.append(source);

    const fields = el("div", { class: "st-finish-apply-fields" });
    for (const [key, title, copy] of [
      ["captions", "Caption style", "Same font, colour and size everywhere. Stories without captions get them built."],
      ["text", "Text style", "Same look for hook, title and call-to-action text."],
      ["color", "Colour preset", "Same colour look and sliders."],
      ["music", "Music brief", "Same mood, energy, genre and tempo for generated beds."],
      ["voice", "Voice", "Same voice and pace for voice-over and dub."],
    ]) {
      const input = el("input", { type: "checkbox" });
      input.checked = Boolean(applyFields[key]);
      input.addEventListener("change", () => { applyFields[key] = input.checked; });
      fields.append(el("label", { class: "st-check" }, [
        input,
        el("span", {}, [
          el("strong", { text: title }),
          el("small", { text: copy }),
        ]),
      ]));
    }
    card.append(el("div", { class: "st-finish-form-grid" }, [sourceLabel, fields]));

    const actions = el("div", { class: "st-layer-add" });
    const apply = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: applyBusy ? "Applying…" : `Apply to ${formatCount(Math.max(0, stories().length - 1), "other story", "other stories")}`,
      disabled: applyBusy,
    });
    apply.addEventListener("click", () => { void applyToAll(apply); });
    actions.append(apply);
    card.append(actions);
    if (applyNotice) {
      card.append(el("p", {
        class: "st-status",
        dataset: { tone: applyTone },
        text: applyNotice,
      }));
    }
    return card;
  }

  function renderApplyCard() {
    const existing = dom.body.querySelector(".st-finish-apply");
    if (!existing) return;
    existing.replaceWith(applyCard());
  }

  async function applyToAll(button) {
    if (!job || applyBusy) return;
    const selected = Object.entries(applyFields).filter(([, value]) => value).map(([key]) => key);
    if (!selected.length) {
      applyNotice = "Pick at least one thing to copy.";
      applyTone = "bad";
      renderApplyCard();
      return;
    }
    const sourceStory = stories().find((story) => story.id === applySourceId);
    if (!sourceStory) return;
    applyBusy = true;
    button.disabled = true;
    button.textContent = "Applying…";
    applyNotice = "";
    clearError();
    try {
      const source = await currentEditFor(sourceStory.id, aspect);
      if (!source?.edit) throw new Error("The source story has no edit in this shape.");
      const sourceEdit = source.edit;
      const sourceCaptions = sourceEdit.captions?.track_id
        ? await request(`${jobRoot(job.id)}/captions/${encodeURIComponent(sourceEdit.captions.track_id)}`)
          .catch(() => null)
        : null;
      const sourceStyle = Array.isArray(sourceEdit.graphics)
        ? sourceEdit.graphics.find((item) => item?.type === "text" && item?.style)?.style || null
        : null;
      const sourceBrief = sourceEdit.audio?.music?.brief || null;
      const sourceVoice = sourceEdit.audio?.voice || null;

      const targets = stories().filter((story) => story.id !== sourceStory.id);
      const results = [];
      for (const story of targets) {
        const result = { name: storyName(story, stories().indexOf(story)), changed: [], skipped: [], error: "" };
        results.push(result);
        try {
          // Captions go first: building or restyling a track re-points the
          // story's 9:16 Edit on the server, so the Edit is read after it.
          let captionValue = null;
          captionChanged = true;
          const before = await currentEditFor(story.id, aspect);
          if (applyFields.captions) {
            if (!sourceCaptions?.style) {
              result.skipped.push({ field: "captions", reason: "the source story has no captions" });
            } else if (before?.edit?.captions?.enabled === false) {
              result.skipped.push({ field: "captions", reason: "captions are turned off" });
            } else if (before?.edit?.captions?.track_id) {
              captionValue = await copyCaptionStyle(before.edit, sourceCaptions, sourceEdit);
              if (captionValue && !captionChanged) {
                result.skipped.push({ field: "captions", reason: "already in this style" });
              }
            } else {
              captionValue = await buildCaptionsLike(story, sourceCaptions, sourceEdit);
              if (!captionValue) {
                result.skipped.push({ field: "captions", reason: "no speech to caption" });
              }
            }
          }
          const current = await currentEditFor(story.id, aspect);
          if (!current?.edit) {
            const created = await createAppliedEdit(story, {
              color: applyFields.color ? sourceEdit.color : null,
              textStyle: applyFields.text ? sourceStyle : null,
              brief: applyFields.music ? sourceBrief : null,
              voice: applyFields.voice ? sourceVoice : null,
              captions: captionValue,
            });
            result.changed.push(...created);
            continue;
          }
          const target = current.edit;
          const patch = {};
          if (applyFields.color && sourceEdit.color) patch.color = sourceEdit.color;
          if (applyFields.text && sourceStyle) {
            const graphics = Array.isArray(target.graphics) ? target.graphics.map((item) => (
              item?.type === "text" ? { ...item, style: sourceStyle } : item
            )) : [];
            if (graphics.some((item) => item?.type === "text")) patch.graphics = graphics;
            else result.skipped.push({ field: "text", reason: "no text layer" });
          }
          if (applyFields.music || applyFields.voice) {
            const audio = JSON.parse(JSON.stringify(target.audio || {}));
            if (applyFields.voice && sourceVoice) {
              audio.voice = { ...sourceVoice };
            }
            if (applyFields.music && sourceBrief) {
              audio.music = { ...(audio.music || {}), brief: { ...sourceBrief } };
            }
            if (Object.keys(audio).length) patch.audio = audio;
          }
          if (captionValue) {
            if (target.captions?.track_id !== captionValue.track_id
              || target.captions?.style_id !== captionValue.style_id) {
              patch.captions = { ...(target.captions || {}), ...captionValue };
            }
            // The track itself changed even when the server already re-pointed the Edit.
            if (captionChanged) result.changed.push("captions");
          }
          for (const field of ["color", "graphics", "audio"]) {
            if (!(field in patch)) continue;
            if (JSON.stringify(patch[field]) === JSON.stringify(target[field])) delete patch[field];
            else result.changed.push(field === "graphics" ? "text" : field === "audio" ? "sound" : "colour");
          }
          if (!Object.keys(patch).length) continue;
          await request(`${jobRoot(job.id)}/edits/${encodeURIComponent(target.id)}`, {
            method: "PATCH",
            body: patch,
          });
        } catch (error) {
          result.error = error?.message || "could not apply";
        }
      }
      await loadEdits();
      if (disposed) return;
      const summary = applySummary(results);
      applyNotice = summary.text;
      applyTone = summary.tone;
      renderApplyCard();
      renderVersionsCard();
      announce(applyNotice, summary.tone);
    } catch (error) {
      if (disposed) return;
      applyNotice = error?.message || "Could not apply the style.";
      applyTone = "bad";
      renderApplyCard();
      announce(applyNotice, "bad");
    } finally {
      applyBusy = false;
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = `Apply to ${formatCount(Math.max(0, stories().length - 1), "other story", "other stories")}`;
      }
    }
  }

  async function createAppliedEdit(story, values) {
    const body = {
      set_id: activeSetId,
      story_id: story.id,
      aspect,
    };
    if (values.color) body.color = values.color;
    if (values.textStyle) {
      const hookText = String(story?.hook?.text || storyName(story, stories().indexOf(story)))
        .replace(/inpaint|generative|delogo|watermark|voice[\s_-]*clon\w*|avatar|stock[\s_-]*b-?roll/gi, "text")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 200);
      body.graphics = [{
        type: "text",
        kind: "hook",
        text: hookText || "Hook",
        start: 0,
        end: Math.max(0.6, Math.min(3, storyDuration(story) || 3)),
        style: values.textStyle,
      }];
    }
    const audio = {};
    if (values.voice) audio.voice = { ...values.voice };
    if (values.brief) audio.music = { brief: { ...values.brief } };
    if (Object.keys(audio).length) body.audio = audio;
    if (values.captions) body.captions = values.captions;
    const changed = [
      values.captions ? "captions" : "",
      values.color ? "colour" : "",
      values.textStyle ? "text" : "",
      Object.keys(audio).length ? "sound" : "",
    ].filter(Boolean);
    if (!changed.length) return [];
    await request(`${jobRoot(job.id)}/edits`, { method: "POST", body });
    return changed;
  }

  /** Build a caption track for a story that has none, in the source's style. */
  async function buildCaptionsLike(story, sourceTrack, sourceEdit) {
    const styleId = sourceTrack.style_id || sourceEdit.captions?.style_id || "clean";
    let built;
    try {
      built = await request(`${jobRoot(job.id)}/captions`, {
        method: "POST",
        body: { target: 30, set_id: activeSetId, story_id: story.id, style_id: styleId },
      });
    } catch (error) {
      if (Number(error?.status) === 400) return null;
      throw error;
    }
    const track = built?.track || built;
    if (!track?.id || !(track.cues || []).length) return null;
    const styled = await request(`${jobRoot(job.id)}/captions/${encodeURIComponent(track.id)}`, {
      method: "PATCH",
      body: { style: sourceTrack.style, style_id: styleId },
    });
    return {
      track_id: String(styled?.track_id || styled?.id || track.id),
      style_id: styleId,
      enabled: true,
    };
  }

  async function copyCaptionStyle(targetEdit, sourceTrack, sourceEdit) {
    const trackId = String(targetEdit.captions?.track_id || "");
    if (!trackId) return null;
    const style = sourceTrack?.style;
    if (!style || typeof style !== "object") return null;
    const styleId = sourceTrack.style_id || sourceEdit.captions?.style_id || null;
    const body = { style };
    if (styleId) body.style_id = styleId;
    const result = await request(
      `${jobRoot(job.id)}/captions/${encodeURIComponent(trackId)}`,
      { method: "PATCH", body },
    );
    const nextTrack = String(result?.track_id || result?.id || trackId);
    captionChanged = result?.changed !== false;
    return {
      ...(targetEdit.captions || {}),
      track_id: nextTrack,
      style_id: styleId || targetEdit.captions?.style_id || null,
      enabled: targetEdit.captions?.enabled !== false,
    };
  }

  async function queueStories(rows, button, shape = aspect) {
    if (!job || !activeSetId || busy) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) return;
    busy = true;
    if (button) {
      button.disabled = true;
      button.textContent = "Queueing…";
    }
    announce(`Checking the Edit for ${formatCount(list.length, "story", "stories")}…`);
    clearError();
    clearRepair();
    try {
      // The preview and the Edit must agree before a render starts. Ask the
      // trim route rather than trusting the last screen that opened.
      await loadTrimHealth({
        shape,
        force: true,
        storyIds: list.map((story) => story.id),
      });
      if (disposed) return;
      const stale = list.filter((story) => trimHealthFor(story.id, shape)?.stale);
      if (stale.length) {
        showRepair(
          `${formatCount(stale.length, "story", "stories")} changed after its Edit. Repair before queueing.`,
          stale[0].id,
          shape,
        );
        announce("This story changed after its Edit was made. Press Repair, then queue again.", "bad");
        renderAll();
        return;
      }
      announce(`Queueing ${formatCount(list.length, "story", "stories")} in ${shape}…`);
      const items = list.map((story) => ({
        job_id: job.id,
        set_id: activeSetId,
        story_id: story.id,
        aspect: shape,
        quality,
        fill_device: queuedDevice() === "gpu" ? "gpu" : "",
        fill_follow: queuedFollow(),
        fill_method: queuedMethod(),
        title: storyName(story, stories().indexOf(story)),
      }));
      const result = await request("/api/story-queues", { method: "POST", body: { items } });
      const attached = result?.attached === true;
      await loadQueues();
      if (disposed) return;
      busy = false;
      renderQueueCard();
      const summary = queueSummary(queues, { jobId: job.id, setId: activeSetId });
      const lead = attached
        ? "Already queued; attached to the active queue."
        : `Queued ${formatCount(items.length, "story", "stories")} in ${shape}.`;
      announce(`${lead} ${summary.text}`, "ok");
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      const code = trimErrorCode(error);
      if (code === "edit_stale") {
        await loadTrimHealth({
          shape,
          force: true,
          storyIds: list.map((story) => story.id),
        });
        const target = list.find((story) => trimHealthFor(story.id, shape)?.stale)?.id
          || list[0]?.id
          || selectedStory()?.id
          || "";
        showRepair(error?.message || "This story changed after its Edit was made. Open it in Edit and press Repair.", target, shape);
        announce("This story changed after its Edit was made. Press Repair, then queue again.", "bad");
        if (!disposed) renderAll();
        return;
      }
      announce(error?.message || "Could not queue these stories.", "bad");
    } finally {
      busy = false;
      // Rebuild the card so every queue button (not only the one clicked)
      // reflects the new busy/stale state, including after a 409 repair banner.
      if (!disposed) renderRenderCard();
    }
  }

  async function queueAction(queueId, action, button) {
    if (!queueId) return;
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = "Working…";
    announce(action === "pause" ? "Pausing…"
      : action === "cancel" ? "Cancelling the queue…" : "Resuming the queue…");
    try {
      await request(`/api/story-queues/${encodeURIComponent(queueId)}/${action}`, {
        method: "POST",
        body: {},
      });
      await loadQueues();
      if (disposed) return;
      renderQueueCard();
      announce(action === "pause" ? "Queue paused. Resume keeps the work already done." : action === "cancel" ? "Queue cancelled." : "Queue resumed.", "ok");
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not change the queue.", "bad");
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = previous;
      }
    }
  }

  async function deleteQueue(queue, button) {
    if (!queue?.id) return;
    if (button.dataset.confirm !== "1") {
      button.dataset.confirm = "1";
      const previous = button.textContent;
      button.textContent = "Delete?";
      window.setTimeout(() => {
        if (!button.isConnected) return;
        button.dataset.confirm = "";
        button.textContent = previous;
      }, 3000);
      return;
    }
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = "Working…";
    announce("Deleting the queue record…");
    try {
      await request(`/api/story-queues/${encodeURIComponent(queue.id)}`, {
        method: "DELETE",
      });
      await loadQueues();
      if (disposed) return;
      renderQueueCard();
      announce("Queue deleted. Its renders and files stay in Publish.", "ok");
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not delete the queue.", "bad");
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = previous;
        button.dataset.confirm = "";
      }
    }
  }

  /** The newest ready story in the current shape. */
  function latestReadyCuts(shape = aspect) {
    const rows = [];
    for (const [index, story] of stories().entries()) {
      const newest = artifactsFor(story.id, shape)[0];
      if (newest) rows.push({ artifact: newest, index });
    }
    return rows;
  }

  function downloadAllButton() {
    const cuts = latestReadyCuts();
    if (cuts.length < 2) return null;
    const button = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: `Download all · ${cuts.length}`,
    });
    button.addEventListener("click", () => {
      // One anchor click per file; browsers queue them as separate downloads.
      latestReadyCuts().forEach(({ artifact, index }, order) => {
        window.setTimeout(() => {
          const link = el("a", { href: artifact.url, download: downloadName(artifact, index) });
          document.body.append(link);
          link.click();
          link.remove();
        }, order * 400);
      });
      announce(`Downloading ${formatCount(cuts.length, "story", "stories")}.`, "ok");
    });
    return button;
  }

  async function revealArtifact(artifact, button) {
    if (!job || !artifact?.artifact_id) return;
    button.disabled = true;
    try {
      await request(
        `${jobRoot(job.id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/reveal`,
        { method: "POST", body: {} },
      );
      announce("Shown in Finder.", "ok");
    } catch (error) {
      announce(error?.message || "Could not open Finder.", "bad");
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }

  async function togglePin(artifact, button) {
    if (!job || !artifact) return;
    button.disabled = true;
    try {
      await request(
        `${jobRoot(job.id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/pin`,
        { method: "POST", body: { pinned: !artifact.pinned } },
      );
      await loadArtifacts();
      if (disposed) return;
      renderVersionsCard();
      announce(artifact.pinned ? "Version unpinned." : "Version kept.", "ok");
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not change this version.", "bad");
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }

  async function restoreEdit(headId, versionId, button) {
    if (!job || !headId || !versionId) return;
    button.disabled = true;
    button.textContent = "Restoring…";
    announce("Restoring that edit as a new current version…");
    try {
      await request(`${jobRoot(job.id)}/edits/${encodeURIComponent(headId)}/restore`, {
        method: "POST",
        body: { version: versionId },
      });
      await loadEdits();
      if (disposed) return;
      renderVersionsCard();
      announce("That edit is current again. Render a new story to see it.", "ok");
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not restore that edit version.", "bad");
    } finally {
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = "Use this version";
      }
    }
  }

  if (!ctx.getJobId()) {
    renderEmpty("No video open", "Import a video first. Finish needs moments and renders.", "import", "Go to Import");
    return () => { disposed = true; stopPoll(); };
  }

  renderSkeleton();
  void loadAll();

  return () => {
    disposed = true;
    stopPoll();
  };
}
