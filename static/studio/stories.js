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
  createClipSet,
  createStoryQueue,
  getJob,
  getJobStatus,
  invalidateReadCache,
  listClipSets,
  renderStory,
  trimErrorCode,
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

/** Mirrors `clipset.LENGTH_PRESETS`; "auto" is the server default window. */
export const LENGTH_PRESETS = {
  auto: { label: "Auto · 20–75 s", min: 20, max: 75 },
  short: { label: "Short · 15–30 s", min: 15, max: 30 },
  medium: { label: "Medium · 30–60 s", min: 30, max: 60 },
  long: { label: "Long · 45–90 s", min: 45, max: 90 },
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

export function mount(root, ctx) {
  let disposed = false;
  let timer = 0;
  let job = null;
  let sets = [];
  let activeSetId = "";
  let loading = false;

  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-stories-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 3 · Stories</p>
        <h1 id="st-stories-title">Pick the stories</h1>
        <p class="st-lede">VibeCut reads the transcript and proposes complete moments, each with a hook and a payoff.</p>
      </header>
      <div id="st-story-body" class="st-story-body"></div>
      <p id="st-story-status" class="st-status" role="status" aria-live="polite" hidden></p>
      <p id="st-story-error" class="st-error" role="alert" hidden></p>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    body: $("#st-story-body"),
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
      el("span", { class: "st-empty-mark", "aria-hidden": "true", text: "01" }),
      el("h2", { text: "No video open" }),
      el("p", { text: "Import a video first. Stories need a finished read of the footage." }),
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

  function openInEdit(story) {
    // Edit reads this choice on open; the shape follows the picker here.
    try {
      const picked = root.querySelector(".st-render-bar select")?.value;
      const aspect = picked === "4:5" ? "4:5" : "9:16";
      localStorage.setItem(EDIT_CHOICE_KEY, JSON.stringify({
        setId: activeSetId, storyId: story.id, aspect,
      }));
    } catch (_) {
      /* Edit falls back to the first story. */
    }
    ctx.go("edit", { force: true });
  }

  function storyCard(story, index) {
    const hook = story.hook?.text || story.title || `Story ${index + 1}`;
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
    const trim = el("div", { class: "st-story-trim", role: "group", "aria-label": "Adjust story range" });
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
    const button = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Render this story",
    });
    button.addEventListener("click", () => queueOne(story, button, note));
    const editButton = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: "Edit this story",
    });
    editButton.addEventListener("click", () => openInEdit(story));
    const foot = el("div", { class: "st-story-foot" }, [
      el("span", { class: "st-hint", text: formatCount(story.sentences?.length, "sentence") }),
      el("div", { class: "st-story-actions" }, [button, editButton]),
    ]);
    card.append(head, meta, quotes, trim, foot, note);
    return card;
  }

  async function adjustStory(story, sentences, note, group) {
    if (!job || !activeSetId || !sentences?.length) return;
    for (const control of group.querySelectorAll("button")) control.disabled = true;
    note.hidden = false;
    setStatus(note, "Trimming the story…");
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
        `${receipt || "Story range updated."}${Number.isFinite(duration) ? ` New length ${formatDuration(duration)}.` : ""}`,
        "ok",
      );
    } catch (error) {
      if (disposed) return;
      const stale = trimErrorCode(error) === "revision_mismatch";
      setStatus(
        note,
        stale
          ? `${error?.message || "This story changed."} The latest range is open; try again.`
          : (error?.message || "Could not change this story's range."),
        "bad",
      );
      for (const control of group.querySelectorAll("button")) control.disabled = false;
      if (stale) {
        invalidateReadCache(job.id);
        await loadSets();
      }
    }
  }

  function controlsCard() {
    const set = sets.find((item) => item.id === activeSetId) || sets[0];
    const requested = Number(set?.requested) || 3;
    const card = el("div", { class: "st-card st-story-controls" });
    const head = el("div", { class: "st-card-head" }, [
      el("div", {}, [
        el("h2", { text: set ? "Story picks" : "No stories yet" }),
        el("p", {
          class: "st-hint",
          text: set
            ? `${formatCount(set.stories?.length, "story", "stories")} from ${formatCount(set.sentence_count || 0, "sentence")}.`
            : "Build the first set from the finished read.",
        }),
      ]),
      sets.length > 1 ? setPicker() : null,
    ]);
    card.append(head);

    const actions = el("div", { class: "st-controls-row" });
    const countLabel = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "How many" }),
    ]);
    const count = el("select", { "aria-label": "How many stories" });
    for (let value = 3; value <= 12; value += 1) {
      count.append(el("option", { value: String(value), text: String(value), selected: value === requested }));
    }
    countLabel.append(count);
    const lengthLabel = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "Length" }),
    ]);
    const length = el("select", { "aria-label": "Story length" });
    const current = lengthPreset(set);
    for (const [value, preset] of Object.entries(LENGTH_PRESETS)) {
      length.append(el("option", { value, text: preset.label, selected: value === current }));
    }
    lengthLabel.append(length);
    const build = el("button", {
      class: "st-btn st-btn-primary",
      type: "button",
      text: set ? "Find stories again" : "Find stories",
    });
    build.addEventListener("click", () => buildStories(Number(count.value), build, length.value));
    actions.append(countLabel, lengthLabel, build);
    card.append(actions);

    if (set?.note) card.append(el("p", { class: "st-hint", text: set.note }));
    for (const warning of set?.warnings || []) {
      card.append(el("p", { class: "st-warning", text: warning }));
    }
    return card;
  }

  function setPicker() {
    const label = el("label", { class: "st-field st-field-inline" }, [
      el("span", { text: "Earlier picks" }),
    ]);
    const select = el("select", { "aria-label": "Earlier story picks" });
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
      renderStories();
    });
    label.append(select);
    return label;
  }

  function renderStories() {
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
    if (!set) return;

    const stories = Array.isArray(set.stories) ? set.stories : [];
    if (!stories.length) {
      dom.body.append(el("div", { class: "st-empty" }, [
        el("h2", { text: "No complete story found" }),
        el("p", { text: "Try fewer stories or a source with more speech." }),
      ]));
      return;
    }

    const bar = el("div", { class: "st-card st-render-bar" });
    const aspectLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Shape" })]);
    const aspect = el("select", { "aria-label": "Story shape" });
    aspect.append(el("option", { value: "9:16", text: "9:16 vertical" }));
    aspect.append(el("option", { value: "4:5", text: "4:5 feed" }));
    aspectLabel.append(aspect);
    const qualityLabel = el("label", { class: "st-field st-field-inline" }, [el("span", { text: "Quality" })]);
    const quality = el("select", { "aria-label": "Render quality" });
    quality.append(el("option", { value: "final", text: "Final" }));
    quality.append(el("option", { value: "draft", text: "Draft" }));
    qualityLabel.append(quality);
    const all = el("button", {
      class: "st-btn st-btn-primary",
      type: "button",
      text: `Queue all ${stories.length}`,
    });
    all.addEventListener("click", () => queueAll(stories, aspect.value, quality.value, all));
    bar.append(aspectLabel, qualityLabel, all);
    dom.body.append(bar);

    const list = el("div", { class: "st-story-list" });
    stories.forEach((story, index) => {
      list.append(storyCard(story, index));
    });
    dom.body.append(list);
  }

  async function queueOne(story, button, note) {
    if (!job || !activeSetId || button.disabled) return;
    const aspect = root.querySelector(".st-render-bar select")?.value || "9:16";
    const quality = root.querySelectorAll(".st-render-bar select")[1]?.value || "final";
    button.disabled = true;
    button.textContent = "Starting…";
    setStatus(note, "");
    try {
      await renderStory(job.id, activeSetId, story.id, { aspect, quality, captions: true });
      if (disposed) return;
      setStatus(note, `Render started in ${aspect}.`, "ok");
      button.textContent = "Render again";
    } catch (error) {
      if (disposed) return;
      setStatus(note, error.message || "Could not start this render.", "bad");
      button.textContent = "Render this story";
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
      showStatus(`${formatCount(items.length, "story", "stories")} queued. They render one at a time.`, "ok");
      button.textContent = "Queued";
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not queue these stories.");
      button.textContent = `Queue all ${stories.length}`;
      button.disabled = false;
    }
  }

  async function buildStories(count, button, length = "auto") {
    if (!job || loading) return;
    loading = true;
    button.disabled = true;
    button.textContent = "Finding…";
    clearError();
    showStatus("Reading the transcript and choosing complete moments…");
    try {
      const preset = LENGTH_PRESETS[length] || LENGTH_PRESETS.auto;
      const result = await createClipSet(job.id, { count, minS: preset.min, maxS: preset.max });
      ctx.refreshSteps?.();
      if (disposed) return;
      const record = result?.clip_set;
      if (record?.id) {
        sets = [record, ...sets.filter((item) => item.id !== record.id)];
        activeSetId = record.id;
      } else {
        await loadSets();
      }
      showStatus(`Found ${formatCount(record?.stories?.length || 0, "story", "stories")}.`, "ok");
      renderStories();
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not find stories in this video.");
      button.disabled = false;
    } finally {
      loading = false;
      if (!disposed) {
        if (button.isConnected) button.textContent = sets.length ? "Find stories again" : "Find stories";
      }
    }
  }

  async function loadSets() {
    try {
      const data = await listClipSets(job.id);
      if (disposed) return;
      sets = Array.isArray(data?.clip_sets) ? data.clip_sets : [];
      if (!sets.some((item) => item.id === activeSetId)) {
        activeSetId = sets[0]?.id || "";
      }
      renderStories();
    } catch (error) {
      if (disposed) return;
      showError(error.message || "Could not load stories for this video.");
      clear(dom.body);
      dom.body.append(emptyNoJobCard("Stories are unavailable", "The video is open, but its story list could not be read."));
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
  };
}
