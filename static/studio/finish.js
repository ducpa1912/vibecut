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

import { request } from "./api.js";
import {
  clear,
  el,
  formatCount,
  formatDuration,
  setStatus,
  shortDate,
  statusText,
  statusTone,
} from "./ui.js";

const POLL_MS = 2400;
const ACTIVE_QUEUE = new Set(["queued", "running"]);
const ACTIVE_ITEM = new Set(["queued", "running"]);
const ASPECTS = ["9:16", "4:5"];

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

function severityWord(value) {
  const key = String(value || "info").toLowerCase();
  if (key === "block" || key === "blocker" || key === "error") return "Must fix";
  if (key === "warning" || key === "warn") return "Look";
  return "Note";
}

function severityTone(value) {
  const key = String(value || "info").toLowerCase();
  if (key === "block" || key === "blocker" || key === "error") return "bad";
  if (key === "warning" || key === "warn") return "busy";
  return "quiet";
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

function artifactLabel(artifact) {
  const version = plainVersion(artifact?.versions?.label || `v${artifact?.version || "?"}`);
  const quality = artifact?.quality === "draft" ? "Draft" : "Final";
  const when = artifact?.created ? shortDate(artifact.created) : "";
  return [version, quality, when].filter(Boolean).join(" · ");
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
  let aspect = "9:16";
  let quality = "final";
  let selectedArtifactId = "";
  let packetArtifactId = "";
  let shareArtifactId = "";
  let compareA = "";
  let compareB = "";
  let packetDraft = null;
  let packetBusy = false;
  let shareBusy = false;
  let applyBusy = false;
  let applyNotice = "";
  let applySourceId = "";
  let applyFields = {
    captions: true,
    text: true,
    color: true,
    music: true,
    voice: true,
  };
  const sessionLinks = [];
  let shareExpiry = "30";
  let shareLabel = "";

  root.innerHTML = `
    <section class="st-panel st-finish-panel" aria-labelledby="st-finish-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 5 · Finish</p>
        <h1 id="st-finish-title">Render and share</h1>
        <p class="st-lede">Render every story in 9:16 or 4:5. Keep every version. Hand off a publish kit, a review link and the same look across stories.</p>
      </header>
      <p id="st-finish-status" class="st-status" role="status" aria-live="polite" hidden></p>
      <p id="st-finish-error" class="st-error" role="alert" hidden></p>
      <div id="st-finish-body" class="st-finish-body"></div>
    </section>
  `;

  const dom = {
    status: root.querySelector("#st-finish-status"),
    error: root.querySelector("#st-finish-error"),
    body: root.querySelector("#st-finish-body"),
  };

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

  function readyArtifacts() {
    return artifacts.filter(artifactReady);
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

  function keepArtifactSelection() {
    const rows = allArtifactsFor();
    const ids = new Set(rows.map((item) => item.artifact_id));
    if (!ids.has(selectedArtifactId)) selectedArtifactId = rows[0]?.artifact_id || "";
    const ready = rows.filter(artifactReady).map((item) => item.artifact_id);
    if (!ready.includes(packetArtifactId)) packetArtifactId = ready[0] || "";
    if (!ready.includes(shareArtifactId)) shareArtifactId = ready[0] || "";
    if (!ready.includes(compareA)) compareA = ready[0] || "";
    if (!ready.includes(compareB)) {
      compareB = ready.find((id) => id !== compareA) || ready[1] || "";
    }
  }

  function packetArtifact() {
    return readyArtifacts().find((item) => item.artifact_id === packetArtifactId) || null;
  }

  function shareArtifact() {
    return readyArtifacts().find((item) => item.artifact_id === shareArtifactId) || null;
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
    return edits
      .filter((item) => item.key === key)
      .sort((left, right) => Number(right.version || 0) - Number(left.version || 0));
  }

  function editHead(storyId = selectedStory()?.id, shape = aspect) {
    return String(editPointers[storyKey(activeSetId, String(storyId || ""), shape)] || "");
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
    if (!sets.some((item) => item.id === activeSetId)) activeSetId = sets[0]?.id || "";
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
      return;
    }
    const seq = ++checkSeq;
    const edit = await currentEditFor(story.id, aspect).catch(() => null);
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
      const params = new URLSearchParams({ story_id: story.id });
      payload = await request(`${jobRoot(job.id)}/preflight?${params.toString()}`);
      fallback = true;
    }
    if (disposed || seq !== checkSeq) return;
    const value = normalizeMarkers(payload);
    checks = { ...value, fallback };
  }

  async function loadAll({ quiet = false } = {}) {
    if (loading) return;
    loading = true;
    clearError();
    if (!quiet) announce("Reading renders…");
    try {
      const hasJob = await loadJob();
      if (!hasJob) {
        renderEmpty("No video open", "Import a video first. Finish needs stories and renders.", "import", "Go to Import");
        return;
      }
      await loadSets();
      await Promise.all([loadArtifacts(), loadQueues(), loadEdits(), loadPackets(), loadShares()]);
      if (stories().length) {
        await loadChecks().catch(() => {
          checks = {
            markers: [],
            blocked: false,
            note: "Checks could not run for this story.",
            fallback: true,
          };
        });
      }
      renderAll();
      if (!notice) announce("");
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

  async function poll() {
    if (disposed || loading) return;
    const wasActive = hasActiveWork();
    try {
      await Promise.all([loadQueues(), loadArtifacts()]);
      if (disposed) return;
      renderQueueCard();
      renderStoryCard();
      if (wasActive && !hasActiveWork()) {
        await Promise.all([loadPackets(), loadShares()]);
        renderVersionsCard();
        renderPacketCard();
        renderShareCard();
        announce("Renders finished. New versions are ready.", "ok");
        return;
      }
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      showError(error?.message || "Could not refresh the render queue.");
      schedulePoll();
    }
  }

  function renderEmpty(title, copy, step, action) {
    clear(dom.body);
    const card = el("div", { class: "st-empty" }, [
      el("span", { class: "st-empty-mark", "aria-hidden": "true", text: "05" }),
      el("h2", { text: title }),
      el("p", { text: copy }),
    ]);
    const button = el("button", { class: "st-btn st-btn-primary", type: "button", text: action });
    button.addEventListener("click", () => ctx.go(step));
    card.append(button);
    dom.body.append(card);
  }

  function renderAll() {
    keepArtifactSelection();
    clear(dom.body);
    if (!stories().length) {
      renderEmpty(
        "No stories yet",
        "Pick stories before finishing. Finish renders one story at a time with its own shape and version history.",
        "stories",
        "Go to Stories",
      );
      return;
    }
    dom.body.append(
      storyCard(),
      queueCard(),
      versionsCard(),
      checksCard(),
      packetCard(),
      shareCard(),
      applyCard(),
    );
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
        text: `${stamp} · ${formatCount(set.stories?.length, "story", "stories")}`,
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
      keepArtifactSelection();
      void refreshChecks();
      renderAll();
    });
    label.append(select);
    return label;
  }

  function storyCard() {
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-render-title" });
    const set = activeSet();
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-render-title", text: "Render" }),
        el("p", {
          class: "st-hint",
          text: `${formatCount(stories().length, "story", "stories")} from this set. Every render is a new version; nothing is overwritten.`,
        }),
      ]),
      setPicker(),
    ]);
    card.append(head);

    const bar = el("div", { class: "st-finish-bar" });
    const shapeLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Shape" })]);
    const shape = el("select", { "aria-label": "Render shape" });
    for (const value of ASPECTS) {
      shape.append(el("option", {
        value,
        text: value === "9:16" ? "9:16 vertical" : "4:5 feed",
        selected: value === aspect,
      }));
    }
    shape.addEventListener("change", () => {
      aspect = shape.value;
      selectedArtifactId = "";
      packetArtifactId = "";
      shareArtifactId = "";
      compareA = "";
      compareB = "";
      keepArtifactSelection();
      void refreshChecks();
      renderAll();
    });
    shapeLabel.append(shape);

    const qualityLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Quality" })]);
    const qualitySelect = el("select", { "aria-label": "Render quality" });
    qualitySelect.append(el("option", { value: "final", text: "Final", selected: quality === "final" }));
    qualitySelect.append(el("option", { value: "draft", text: "Draft", selected: quality === "draft" }));
    qualitySelect.addEventListener("change", () => { quality = qualitySelect.value; });
    qualityLabel.append(qualitySelect);

    const queueAll = el("button", {
      class: "st-btn st-btn-primary",
      type: "button",
      text: `Queue all stories · ${aspect}`,
    });
    queueAll.addEventListener("click", () => { void queueStories(stories(), queueAll); });
    bar.append(shapeLabel, qualityLabel, queueAll);
    if (set?.note) bar.append(el("p", { class: "st-hint", text: set.note }));
    card.append(bar);

    const list = el("div", { class: "st-finish-story-list" });
    stories().forEach((story, index) => {
      const storyId = String(story.id || "");
      const ready = artifactsFor(storyId, aspect);
      const all = allArtifactsFor(storyId, aspect);
      const latest = ready[0] || all[0] || null;
      const current = selectedStory()?.id === storyId;
      const row = el("article", { class: `st-finish-story${current ? " is-active" : ""}` });
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
        keepArtifactSelection();
        void refreshChecks();
        renderAll();
      });
      const meta = el("div", { class: "st-finish-story-meta" }, [
        el("span", { class: "st-mono st-hint", text: formatDuration(storyDuration(story)) }),
        latest
          ? el("span", {
            class: `st-chip ${latest.status === "ready" ? "st-chip-ok" : latest.status === "failed" ? "st-chip-bad" : "st-chip-busy"}`,
            text: latest.status === "ready"
              ? artifactLabel(latest).replace(" · current", "")
              : `${statusText(latest.status)} · ${artifactLabel(latest).replace(" · current", "")}`,
          })
          : el("span", { class: "st-chip", text: "Not rendered" }),
        all.length > 1 ? el("span", { class: "st-chip", text: formatCount(all.length, "version") }) : null,
      ]);
      const actions = el("div", { class: "st-finish-story-actions" });
      for (const shapeValue of ASPECTS) {
        const button = el("button", {
          class: "st-btn st-btn-ghost st-btn-small",
          type: "button",
          text: `Queue ${shapeValue}`,
          disabled: busy,
        });
        button.addEventListener("click", () => { void queueStories([story], button, shapeValue); });
        actions.append(button);
      }
      row.append(title, meta, actions);
      list.append(row);
    });
    card.append(list);
    return card;
  }

  function renderStoryCard() {
    const existing = dom.body.querySelector(".st-finish-card");
    if (!existing) return;
    const fresh = storyCard();
    existing.replaceWith(fresh);
  }

  function queueCard() {
    return el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-queue-title" }, [
      el("div", { class: "st-card-head" }, [
        el("div", {}, [
          el("h2", { id: "st-finish-queue-title", text: "Queue" }),
          el("p", { class: "st-hint", text: "One story at a time. A finished queue stays in this list; a paused queue never restarts by itself." }),
        ]),
      ]),
      queueBody(),
    ]);
  }

  function queueBody() {
    const wrap = el("div", { class: "st-finish-queue" });
    const rows = queues.slice(0, 8);
    if (!rows.length) {
      wrap.append(el("p", { class: "st-hint", text: "Nothing is queued. Queued stories appear here with their progress." }));
      return wrap;
    }
    for (const queue of rows) {
      const status = String(queue.status || "queued");
      const active = ACTIVE_QUEUE.has(status);
      const progress = Math.max(0, Math.min(1, Number(queue.progress) || 0));
      const card = el("div", { class: "st-finish-queue-row" });
      const head = el("div", { class: "st-finish-queue-head" }, [
        el("strong", { text: queue.message || statusText(status) }),
        el("span", { class: `st-chip st-chip-${statusTone(status)}`, text: statusText(status) }),
        el("span", { class: "st-mono st-hint", text: `${Math.round(progress * 100)}%` }),
        queue.created ? el("span", { class: "st-hint", text: shortDate(queue.created) }) : null,
      ]);
      const track = el("div", {
        class: "st-progress-bar",
        role: "progressbar",
        "aria-valuemin": "0",
        "aria-valuemax": "100",
        "aria-valuenow": String(Math.round(progress * 100)),
      });
      track.append(el("i", { style: `width:${Math.round(progress * 100)}%` }));
      const items = el("div", { class: "st-finish-queue-items" });
      for (const item of queue.items || []) {
        const itemState = String(item.state || "queued");
        const name = item.title || item.story_id;
        items.append(el("div", { class: "st-finish-queue-item" }, [
          el("span", {
            class: `st-chip ${itemState === "done" ? "st-chip-ok" : itemState === "failed" ? "st-chip-bad" : itemState === "running" ? "st-chip-busy" : ""}`,
            text: statusText(itemState),
          }),
          el("span", { class: "st-finish-queue-name", text: name }),
          el("span", { class: "st-mono st-hint", text: item.aspect || "9:16" }),
        ]));
        if (item.error) items.append(el("p", { class: "st-error", text: String(item.error).slice(0, 300) }));
      }
      const actions = el("div", { class: "st-layer-add" });
      if (active) {
        const pause = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Pause" });
        pause.addEventListener("click", () => { void queueAction(queue.id, "pause", pause); });
        const cancel = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Cancel" });
        cancel.addEventListener("click", () => { void queueAction(queue.id, "cancel", cancel); });
        actions.append(pause, cancel);
      } else if (queue.needs_resume || status === "paused") {
        const resume = el("button", { class: "st-btn st-btn-primary st-btn-small", type: "button", text: "Resume" });
        resume.addEventListener("click", () => { void queueAction(queue.id, "resume", resume); });
        actions.append(resume);
      }
      card.append(head, track, items, actions);
      wrap.append(card);
    }
    return wrap;
  }

  function renderQueueCard() {
    const card = dom.body.querySelectorAll(".st-finish-card")[1];
    if (!card) return;
    const body = card.querySelector(".st-finish-queue");
    if (body) body.replaceWith(queueBody());
  }

  function versionsCard() {
    const story = selectedStory();
    if (!story) return el("div");
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-versions-title" });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-versions-title", text: "Versions" }),
        el("p", {
          class: "st-hint",
          text: `${storyName(story, selectedIndex())} · ${aspect}. Old renders and old edits stay side by side.`,
        }),
      ]),
    ]));

    const rows = allArtifactsFor();
    if (!rows.length) {
      card.append(el("p", { class: "st-hint", text: "No render for this story and shape yet. Queue it above." }));
    } else {
      const list = el("div", { class: "st-layer-list st-finish-version-list" });
      for (const item of rows) {
        const ready = artifactReady(item);
        const active = item.artifact_id === selectedArtifactId;
        const row = el("div", { class: `st-finish-version${active ? " is-active" : ""}` }, [
          el("span", {
            class: `st-chip ${ready ? "st-chip-ok" : item.status === "failed" ? "st-chip-bad" : "st-chip-busy"}`,
            text: ready ? (item.versions?.label || `v${item.version || "?"}`) : statusText(item.status),
          }),
          el("span", { class: "st-finish-version-copy" }, [
            el("strong", { text: artifactLabel(item).replace(" · current", "") }),
            el("small", {
              text: [
                item.pinned ? "Pinned" : "",
                item.cue_count ? formatCount(item.cue_count, "caption") : "",
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
            renderPacketCard();
            renderShareCard();
          });
          const pin = el("button", {
            class: "st-btn st-btn-quiet st-btn-small",
            type: "button",
            text: item.pinned ? "Unpin" : "Keep",
          });
          pin.addEventListener("click", () => { void togglePin(item, pin); });
          actions.append(use, pin);
        }
        row.append(actions);
        row.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          if (!ready) return;
          selectedArtifactId = item.artifact_id;
          packetArtifactId = item.artifact_id;
          shareArtifactId = item.artifact_id;
          renderVersionsCard();
          renderPacketCard();
          renderShareCard();
        });
        list.append(row);
      }
      card.append(list);

      const readyRows = rows.filter(artifactReady);
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
                row.layer_counts?.graphics ? `${row.layer_counts.graphics} graphics` : "",
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
    const cards = dom.body.querySelectorAll(".st-finish-card");
    const existing = cards[2];
    if (!existing) return;
    existing.replaceWith(versionsCard());
  }

  function checksCard() {
    const story = selectedStory();
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-checks-title" });
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-checks-title", text: "Before you publish" }),
        el("p", {
          class: "st-hint",
          text: story
            ? `${storyName(story, selectedIndex())} · ${aspect}. Notes point at the timeline where the server can place them.`
            : "Choose a story to see its notes.",
        }),
      ]),
    ]);
    const refresh = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Check again" });
    refresh.addEventListener("click", () => { void refreshChecks(true, refresh); });
    head.append(refresh);
    card.append(head);

    if (checks.blocked) {
      card.append(el("div", { class: "st-check-warning", dataset: { severity: "warning" } }, [
        el("span", { class: "st-chip st-chip-bad", text: "Must fix" }),
        el("p", { text: "A check blocks this hand-off. Fix it before packing or sharing." }),
      ]));
    }
    if (!checks.markers.length) {
      card.append(el("p", {
        class: "st-hint",
        text: checks.note || (checks.fallback
          ? "No notes for this story. Frame-level markers appear after this build adds them; whole-story checks were used."
          : "No notes for this story and shape."),
      }));
    } else {
      const list = el("div", { class: "st-finish-markers" });
      for (const marker of checks.markers.slice(0, 30)) {
        const row = el("div", { class: "st-finish-marker", dataset: { tone: severityTone(marker.severity) } }, [
          el("span", { class: "st-chip", text: severityWord(marker.severity) }),
          marker.at !== null
            ? el("span", { class: "st-mono st-hint", text: formatDuration(marker.at) })
            : null,
          el("span", { class: "st-finish-marker-copy" }, [
            el("strong", { text: marker.message }),
            marker.suggestion ? el("small", { text: marker.suggestion }) : null,
          ]),
        ]);
        list.append(row);
      }
      card.append(list);
      if (checks.markers.length > 30) {
        card.append(el("p", { class: "st-hint", text: `Showing 30 of ${checks.markers.length}.` }));
      }
    }
    const foot = el("div", { class: "st-layer-add" });
    const edit = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Open Edit" });
    edit.addEventListener("click", () => ctx.go("edit"));
    foot.append(edit);
    card.append(foot);
    return card;
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
      const existing = dom.body.querySelectorAll(".st-finish-card")[3];
      if (existing) existing.replaceWith(checksCard());
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
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-packet-title" });
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-packet-title", text: "Publish kit" }),
        el("p", { class: "st-hint", text: "One ready cut, three titles, one description and three to eight hashtags. The kit carries the video, captions and covers." }),
      ]),
    ]);
    card.append(head);

    const ready = readyArtifacts();
    if (!ready.length) {
      card.append(el("p", { class: "st-hint", text: "No ready cut yet. Queue a render first." }));
      return card;
    }
    const artifact = packetArtifact() || ready[0];
    if (!artifact) return card;

    const select = el("select", { "aria-label": "Cut for the publish kit" });
    for (const item of ready) {
      const story = stories().find((row) => String(row.id) === artifactStoryId(item));
      const index = stories().findIndex((row) => String(row.id) === artifactStoryId(item));
      select.append(el("option", {
        value: item.artifact_id,
        text: `${story ? storyName(story, index) : "Cut"} · ${artifactAspect(item)} · ${artifactLabel(item).replace(" · current", "")}`,
        selected: item.artifact_id === artifact.artifact_id,
      }));
    }
    select.addEventListener("change", () => {
      packetArtifactId = select.value;
      selectedArtifactId = select.value;
      initPacketDraft(packetArtifact());
      renderPacketCard();
      renderShareCard();
    });
    card.append(el("label", { class: "st-field st-finish-field-wide" }, [
      el("span", { text: "Cut" }),
      select,
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
      el("small", { class: "st-field-hint", text: "Two frames from the exact cut." }),
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
    const cards = dom.body.querySelectorAll(".st-finish-card");
    const existing = cards[4];
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
            story_id: artifactStoryId(artifact),
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
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-share-title" });
    card.append(el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { id: "st-finish-share-title", text: "Review link" }),
        el("p", { class: "st-hint", text: "A private link to one exact cut. It never points at a newer render." }),
      ]),
    ]));
    const ready = readyArtifacts();
    if (!ready.length) {
      card.append(el("p", { class: "st-hint", text: "Render a cut before making a review link." }));
      return card;
    }
    const artifact = shareArtifact() || ready[0];
    const select = el("select", { "aria-label": "Cut for the review link" });
    for (const item of ready) {
      select.append(el("option", {
        value: item.artifact_id,
        text: `${artifactLabel(item).replace(" · current", "")} · ${artifactAspect(item)}`,
        selected: item.artifact_id === artifact.artifact_id,
      }));
    }
    select.addEventListener("change", () => {
      shareArtifactId = select.value;
      renderShareCard();
    });

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
        el("label", { class: "st-field" }, [el("span", { text: "Cut" }), select]),
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
    const cards = dom.body.querySelectorAll(".st-finish-card");
    const existing = cards[5];
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
    const card = el("section", { class: "st-card st-finish-card", "aria-labelledby": "st-finish-apply-title" });
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
      ["captions", "Caption style", "Same font, colour and size on every story with captions."],
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
        dataset: { tone: applyNotice.startsWith("Could not") ? "bad" : "ok" },
        text: applyNotice,
      }));
    }
    return card;
  }

  function renderApplyCard() {
    const cards = dom.body.querySelectorAll(".st-finish-card");
    const existing = cards[6];
    if (!existing) return;
    existing.replaceWith(applyCard());
  }

  async function applyToAll(button) {
    if (!job || applyBusy) return;
    const selected = Object.entries(applyFields).filter(([, value]) => value).map(([key]) => key);
    if (!selected.length) {
      applyNotice = "Pick at least one thing to copy.";
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
      let changed = 0;
      let skipped = 0;
      const problems = [];
      for (const story of targets) {
        try {
          const current = await currentEditFor(story.id, aspect);
          if (!current?.edit) {
            const created = await createAppliedEdit(story, {
              color: applyFields.color ? sourceEdit.color : null,
              textStyle: applyFields.text ? sourceStyle : null,
              brief: applyFields.music ? sourceBrief : null,
              voice: applyFields.voice ? sourceVoice : null,
            });
            if (created) changed += 1;
            else skipped += 1;
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
          if (applyFields.captions && sourceCaptions && target.captions?.track_id) {
            const caption = await copyCaptionStyle(target, sourceCaptions, sourceEdit);
            if (caption) patch.captions = caption;
          }
          if (!Object.keys(patch).length) {
            skipped += 1;
            continue;
          }
          await request(`${jobRoot(job.id)}/edits/${encodeURIComponent(target.id)}`, {
            method: "PATCH",
            body: patch,
          });
          changed += 1;
        } catch (error) {
          problems.push(`${storyName(story, stories().indexOf(story))}: ${error?.message || "could not apply"}`);
        }
      }
      await loadEdits();
      if (disposed) return;
      applyNotice = changed
        ? `Applied to ${formatCount(changed, "story", "stories")}.${skipped ? ` ${skipped} had nothing to change.` : ""}`
        : "No story needed a change.";
      if (problems.length) {
        applyNotice = `Applied to ${formatCount(changed, "story", "stories")}. ${problems.length} could not be updated: ${problems[0]}`;
      }
      renderApplyCard();
      renderVersionsCard();
      announce(applyNotice, problems.length ? "bad" : "ok");
    } catch (error) {
      if (disposed) return;
      applyNotice = error?.message || "Could not apply the style.";
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
    if (!values.color && !values.textStyle && !Object.keys(audio).length) return false;
    await request(`${jobRoot(job.id)}/edits`, { method: "POST", body });
    return true;
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
    announce(`Queueing ${formatCount(list.length, "story", "stories")} in ${shape}…`);
    clearError();
    try {
      const items = list.map((story) => ({
        job_id: job.id,
        set_id: activeSetId,
        story_id: story.id,
        aspect: shape,
        quality,
        title: storyName(story, stories().indexOf(story)),
      }));
      await request("/api/story-queues", { method: "POST", body: { items } });
      await loadQueues();
      if (disposed) return;
      busy = false;
      renderQueueCard();
      renderStoryCard();
      announce(`${formatCount(items.length, "story", "stories")} queued in ${shape}. They render one at a time.`, "ok");
      schedulePoll();
    } catch (error) {
      if (disposed) return;
      announce(error?.message || "Could not queue these stories.", "bad");
    } finally {
      busy = false;
      if (button?.isConnected) {
        button.disabled = false;
        button.textContent = button.classList.contains("st-btn-primary")
          ? `Queue all stories · ${shape}`
          : `Queue ${shape}`;
      }
    }
  }

  async function queueAction(queueId, action, button) {
    if (!queueId) return;
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = "Working…";
    announce(action === "pause" ? "Pausing after the current story…"
      : action === "cancel" ? "Cancelling the queue…" : "Resuming the queue…");
    try {
      await request(`/api/story-queues/${encodeURIComponent(queueId)}/${action}`, {
        method: "POST",
        body: {},
      });
      await loadQueues();
      if (disposed) return;
      renderQueueCard();
      announce(action === "pause" ? "Queue paused." : action === "cancel" ? "Queue cancelled." : "Queue resumed.", "ok");
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
      announce("That edit is current again. Render a new cut to see it.", "ok");
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
    renderEmpty("No video open", "Import a video first. Finish needs stories and renders.", "import", "Go to Import");
    return () => { disposed = true; stopPoll(); };
  }

  void loadAll();

  return () => {
    disposed = true;
    stopPoll();
  };
}
