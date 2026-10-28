/**
 * Studio editor timeline.
 *
 * One sentence lane plus the fixed layer lanes. Bars are buttons, the ruler
 * and empty space seek, and the playhead is a percentage so the timeline never
 * needs horizontal scrolling.
 */

import { el } from "../ui.js";
import {
  formatSpan,
  formatTime,
  layerSpans,
  numberOr,
  sentenceSegments,
} from "./model.js";
import { patchClipSetStories } from "../api.js";
import { createEdit } from "./api.js";
import {
  nearestSentenceBoundary,
  outsideLayerIds,
  sentenceSpans,
  trimStoryRange,
} from "../stories.js";

const JOB_KEY = "vibecut.studio.job";
const TRIM_CSS_ID = "vibecut-studio-timeline-trim";

const TRIM_CSS = `
.st-tl-trim {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 12px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: rgba(232, 162, 102, 0.16);
  cursor: ew-resize;
  touch-action: none;
  z-index: 4;
}
.st-tl-trim::before {
  content: "";
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 5px;
  width: 2px;
  border-radius: 1px;
  background: var(--st-accent, #e8a266);
}
.st-tl-trim:hover,
.st-tl-trim.is-dragging {
  background: rgba(232, 162, 102, 0.4);
}
.st-tl-trim:focus-visible {
  outline: 2px solid var(--st-accent, #e8a266);
  outline-offset: -3px;
}
.st-tl-trim-end { transform: translateX(-100%); }
.st-tl-trim[aria-disabled="true"] { display: none; }
.st-tl-bar.is-outside {
  border-style: dashed;
  border-color: rgba(226, 138, 124, 0.85);
  box-shadow: 0 0 0 1px rgba(226, 138, 124, 0.25);
}
`;

const LANE_LABELS = {
  clean: "Clean",
  text: "Text",
  captions: "Captions",
  effects: "Effects",
  color: "Color",
  audio: "Audio",
};

const EMPTY_COPY = {
  clean: "No old text marked",
  text: "No text yet",
  captions: "No captions yet",
  effects: "No motion or effects",
  color: "Original colour",
  audio: "Original sound",
};

function niceStep(duration) {
  const target = Math.max(0.5, duration / 6);
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  return steps.find((step) => step >= target) || 600;
}

function ensureTrimStyles() {
  if (typeof document === "undefined" || document.getElementById(TRIM_CSS_ID)) return;
  const style = document.createElement("style");
  style.id = TRIM_CSS_ID;
  style.textContent = TRIM_CSS;
  document.head.append(style);
}

/** The job Studio has open. The edit document does not carry a job id. */
function currentJobId() {
  try {
    const value = JSON.parse(localStorage.getItem(JOB_KEY) || "null");
    return value && typeof value === "object" ? String(value.id || "") : "";
  } catch (_) {
    return "";
  }
}

export function mountTimeline(root, options = {}) {
  ensureTrimStyles();
  const handlers = {
    onSeek: options.onSeek || (() => {}),
    onSelect: options.onSelect || (() => {}),
  };
  let disposed = false;
  let duration = 10;
  let selected = null;
  let seeking = false;
  let busy = false;
  let drag = null;
  // A trim changes the story and its Edit. The screen around the timeline
  // keeps the old story until the next open, so remember the newer bounds.
  let trimOverride = null;
  let state = { edit: null, captions: null, story: null, aspect: "9:16" };

  root.innerHTML = `
    <section class="st-timeline" aria-labelledby="st-timeline-title">
      <header class="st-timeline-head">
        <div>
          <h2 id="st-timeline-title">Timeline</h2>
          <p class="st-hint">Click a sentence or a layer to jump to it. Drag the story handles to trim.</p>
        </div>
        <div class="st-timeline-meta">
          <span id="st-timeline-outside" class="st-chip st-chip-quiet" hidden></span>
          <span id="st-timeline-span" class="st-mono st-timeline-span">0:00.0</span>
          <span id="st-timeline-count" class="st-chip st-chip-quiet">0 layers</span>
        </div>
      </header>
      <div class="st-timeline-scroll" tabindex="0" role="group" aria-label="Story timeline">
        <div id="st-timeline-grid" class="st-timeline-grid"></div>
      </div>
      <p id="st-timeline-status" class="st-status" role="status" aria-live="polite" hidden></p>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    grid: $("#st-timeline-grid"),
    span: $("#st-timeline-span"),
    count: $("#st-timeline-count"),
    outside: $("#st-timeline-outside"),
    status: $("#st-timeline-status"),
    scroll: $(".st-timeline-scroll"),
  };

  function setTimelineStatus(message, tone = "") {
    dom.status.textContent = message || "";
    dom.status.dataset.tone = tone;
    dom.status.hidden = !message;
  }

  function position(item) {
    const total = Math.max(0.1, duration);
    const start = Math.max(0, Math.min(total, numberOr(item.start)));
    const end = Math.max(start + 0.05, Math.min(total, numberOr(item.end, start + 0.1)));
    return {
      left: (start / total) * 100,
      width: Math.max(0.35, ((end - start) / total) * 100),
    };
  }

  function timeFromEvent(event) {
    const track = event.currentTarget;
    const box = track.getBoundingClientRect();
    if (!box.width) return 0;
    const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    return ratio * duration;
  }

  function makePlayhead() {
    return el("i", { class: "st-tl-playhead", "aria-hidden": "true" });
  }

  function setPlayhead(track) {
    const line = track.querySelector(".st-tl-playhead");
    if (!line) return;
    line.style.left = `${(Math.max(0, Math.min(duration, numberOr(state.time))) / Math.max(0.1, duration)) * 100}%`;
  }

  function paintPlayheads() {
    for (const track of dom.grid.querySelectorAll(".st-tl-track")) setPlayhead(track);
  }

  function makeBar(item, kind) {
    const geometry = position(item);
    const label = String(item.label || "").trim();
    const button = el("button", {
      class: `st-tl-bar st-tl-bar-${kind}${item.muted ? " is-muted" : ""}${item.dashed ? " is-dashed" : ""}${item.outside ? " is-outside" : ""}${selected?.kind === kind && selected?.id === item.layerId ? " is-selected" : ""}`,
      type: "button",
      title: `${label || LANE_LABELS[kind] || "Layer"} · ${formatSpan(item.start, item.end)}${item.outside ? " · outside the trimmed story" : ""}`,
      "aria-label": `${label || LANE_LABELS[kind] || "Layer"}, ${formatSpan(item.start, item.end)}${item.outside ? ", outside the trimmed story" : ""}`,
      style: `left:${geometry.left}%;width:${geometry.width}%`,
      dataset: {
        kind,
        layer: item.layerId || item.id,
        start: String(numberOr(item.start)),
        outside: item.outside ? "1" : "0",
      },
    }, [
      geometry.width > 5 ? el("span", { text: label }) : null,
    ]);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      handlers.onSelect(kind, item.layerId || item.id);
      handlers.onSeek(numberOr(item.start));
    });
    return button;
  }

  function trimRange() {
    if (drag) return { start: drag.startIndex, end: drag.endIndex };
    const spans = sentenceSpans(state.story);
    return { start: 0, end: Math.max(0, spans.length - 1) };
  }

  function paintTrim() {
    if (!drag) return;
    const spans = drag.spans;
    for (const handle of dom.grid.querySelectorAll(".st-tl-trim")) {
      const edge = handle.dataset.edge;
      const range = trimRange();
      const index = edge === "start" ? range.start : range.end;
      const bound = edge === "start" ? spans[index].start : spans[index].end;
      handle.style.left = `${Math.max(0, Math.min(1, bound / Math.max(0.1, duration))) * 100}%`;
      handle.setAttribute("aria-valuenow", String(index));
      handle.setAttribute("aria-valuetext", `${edge === "start" ? "Start" : "End"} at ${formatTime(bound)}`);
      handle.classList.toggle("is-dragging", drag.edge === edge);
    }
    const range = trimRange();
    setTimelineStatus(
      `Start ${formatTime(spans[range.start].start)} · End ${formatTime(spans[range.end].end)}. Snaps to sentence bounds.`,
    );
  }

  function makeTrimHandle(edge, spans) {
    const range = trimRange();
    const index = edge === "start" ? range.start : range.end;
    const bound = edge === "start" ? spans[index].start : spans[index].end;
    const name = edge === "start" ? "Trim the story start" : "Trim the story end";
    const handle = el("button", {
      class: `st-tl-trim st-tl-trim-${edge}${drag?.edge === edge ? " is-dragging" : ""}`,
      type: "button",
      title: `${name}. Snaps to sentence bounds.`,
      "aria-label": `${name}. Snaps to sentence bounds.`,
      role: "slider",
      "aria-valuemin": "0",
      "aria-valuemax": String(spans.length - 1),
      "aria-valuenow": String(index),
      "aria-valuetext": `${edge === "start" ? "Start" : "End"} at ${formatTime(bound)}`,
      "aria-disabled": spans.length < 2 ? "true" : "false",
      dataset: { edge },
      style: `left:${Math.max(0, Math.min(1, bound / Math.max(0.1, duration))) * 100}%`,
    });

    function begin(event) {
      if (busy || spans.length < 2) return;
      event.preventDefault();
      event.stopPropagation();
      const current = trimRange();
      drag = {
        edge,
        index: edge === "start" ? current.start : current.end,
        startIndex: current.start,
        endIndex: current.end,
        originalStart: current.start,
        originalEnd: current.end,
        spans,
      };
      handle.setPointerCapture?.(event.pointerId);
      paintTrim();
    }

    function move(event) {
      if (!drag || drag.edge !== edge) return;
      event.preventDefault();
      const track = handle.parentElement;
      const box = track?.getBoundingClientRect();
      if (!box?.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
      const low = edge === "start" ? 0 : drag.startIndex;
      const high = edge === "start" ? drag.endIndex : drag.spans.length - 1;
      const index = nearestSentenceBoundary(drag.spans, edge, ratio * duration, low, high);
      if (index === null) return;
      drag.index = index;
      if (edge === "start") drag.startIndex = index;
      else drag.endIndex = index;
      paintTrim();
    }

    function finish() {
      if (!drag || drag.edge !== edge) return;
      const done = drag;
      drag = null;
      const changed = done.startIndex !== done.originalStart || done.endIndex !== done.originalEnd;
      if (!changed) {
        setTimelineStatus("Story range unchanged.");
        render();
        return;
      }
      void commitTrim(done.startIndex, done.endIndex);
    }

    handle.addEventListener("pointerdown", begin);
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", () => {
      if (!drag || drag.edge !== edge) return;
      drag = null;
      render();
      updateSelected(selected);
    });
    handle.addEventListener("keydown", (event) => {
      if (busy || spans.length < 2) return;
      const current = trimRange();
      const edgeIndex = edge === "start" ? current.start : current.end;
      const low = edge === "start" ? 0 : current.start;
      const high = edge === "start" ? current.end : spans.length - 1;
      let next = edgeIndex;
      if (event.key === "ArrowLeft") next -= 1;
      else if (event.key === "ArrowRight") next += 1;
      else if (event.key === "Home") next = low;
      else if (event.key === "End") next = high;
      else return;
      event.preventDefault();
      event.stopPropagation();
      next = Math.max(low, Math.min(high, next));
      if (next === edgeIndex) return;
      drag = {
        edge,
        index: next,
        startIndex: edge === "start" ? next : current.start,
        endIndex: edge === "start" ? current.end : next,
        spans,
      };
      paintTrim();
      drag = null;
      void commitTrim(
        edge === "start" ? next : current.start,
        edge === "start" ? current.end : next,
      );
    });
    return handle;
  }

  async function commitTrim(startIndex, endIndex) {
    const story = state.story;
    const ref = state.edit?.story_ref || {};
    const spans = sentenceSpans(story);
    const range = trimStoryRange(story, startIndex, endIndex);
    if (!story || !ref.set_id || !ref.story_id || !range) {
      setTimelineStatus("This story has no sentence bounds to trim.", "bad");
      return;
    }
    if (range.sentences.length >= spans.length) {
      setTimelineStatus("The whole story is already selected.");
      return;
    }
    const jobId = currentJobId();
    if (!jobId) {
      setTimelineStatus("Open this story from Stories before trimming.", "bad");
      return;
    }
    busy = true;
    setTimelineStatus("Saving the trim…", "busy");
    const oldDuration = duration;
    const oldEnd = numberOr(story.end);
    try {
      const result = await patchClipSetStories(jobId, ref.set_id, [
        { id: ref.story_id, sentences: range.sentences },
      ]);
      const record = result?.clip_set;
      const updated = (record?.stories || []).find((item) => item.id === ref.story_id);
      if (!updated) throw new Error("The server did not return the trimmed story.");
      let rebound = null;
      let rebindError = null;
      try {
        rebound = await createEdit(jobId, {
          set_id: ref.set_id,
          story_id: ref.story_id,
          aspect: state.aspect,
        });
      } catch (error) {
        rebindError = error;
      }
      if (disposed) return;
      const nextDuration = Math.max(0.1, numberOr(updated.dur, range.duration));
      state.story = updated;
      if (rebound?.edit) state.edit = rebound.edit;
      const stale = trimOverride && trimOverride.storyId === updated.id ? trimOverride : null;
      trimOverride = {
        storyId: updated.id,
        story: updated,
        duration: nextDuration,
        // Keep the values the surrounding screen still passes until it
        // reloads the set, so a second trim does not restore the first bounds.
        staleEnd: stale ? stale.staleEnd : oldEnd,
        staleDuration: stale ? stale.staleDuration : oldDuration,
      };
      duration = nextDuration;
      const outside = render();
      updateSelected(selected);
      handlers.onSeek(0);
      if (rebindError) {
        setTimelineStatus(
          `Trim saved, but the edit could not follow: ${rebindError.message || "open the story again."}`,
          "bad",
        );
        return;
      }
      setTimelineStatus(
        `Story trimmed to ${formatTime(0)} → ${formatTime(nextDuration)}. The edit follows the new bounds. `
        + (outside
          ? `${outside} layer${outside === 1 ? "" : "s"} outside them ${outside === 1 ? "was" : "were"} kept and flagged.`
          : "Every layer is inside the new bounds."),
        outside ? "" : "ok",
      );
    } catch (error) {
      if (disposed) return;
      setTimelineStatus(error?.message || "Could not trim this story.", "bad");
      render();
      updateSelected(selected);
    } finally {
      busy = false;
    }
  }

  function makeTrack(row) {
    const track = el("div", {
      class: `st-tl-track st-tl-track-${row.kind}`,
      dataset: { kind: row.kind },
      role: "group",
      "aria-label": `${LANE_LABELS[row.kind] || row.label} track`,
    });
    track.append(makePlayhead());
    for (const item of row.items) track.append(makeBar(item, row.kind));
    if (row.kind === "sentences") {
      const spans = sentenceSpans(state.story);
      if (spans.length) {
        track.append(makeTrimHandle("start", spans), makeTrimHandle("end", spans));
      }
    }
    if (!row.items.length) {
      track.append(el("span", { class: "st-tl-empty", text: EMPTY_COPY[row.kind] || "Empty" }));
    }
    track.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-bar, .st-tl-trim")) return;
      seeking = true;
      track.setPointerCapture?.(event.pointerId);
      handlers.onSeek(timeFromEvent(event));
    });
    track.addEventListener("pointermove", (event) => {
      if (!seeking) return;
      handlers.onSeek(timeFromEvent(event));
    });
    track.addEventListener("pointerup", () => { seeking = false; });
    track.addEventListener("pointercancel", () => { seeking = false; });
    return track;
  }

  function makeRuler() {
    const ruler = el("div", { class: "st-tl-ruler", role: "group", "aria-label": "Timeline ruler" });
    const step = niceStep(duration);
    const count = Math.floor(duration / step) + 1;
    for (let index = 0; index < count; index += 1) {
      const time = index * step;
      const ratio = Math.min(1, time / Math.max(0.1, duration));
      const tick = el("button", {
        class: "st-tl-tick",
        type: "button",
        style: `left:${ratio * 100}%`,
        title: `Jump to ${formatTime(time)}`,
        "aria-label": `Jump to ${formatTime(time)}`,
        dataset: { time: String(time) },
      }, [el("span", { text: formatTime(time) })]);
      tick.addEventListener("click", (event) => {
        event.stopPropagation();
        handlers.onSeek(time);
      });
      ruler.append(tick);
    }
    ruler.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-tick")) return;
      const box = ruler.getBoundingClientRect();
      if (!box.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
      handlers.onSeek(ratio * duration);
    });
    return ruler;
  }

  function render() {
    if (disposed) return;
    const rows = [];
    const sentences = sentenceSegments(state.story);
    rows.push({
      id: "sentences",
      label: "Sentences",
      kind: "sentences",
      items: sentences.map((sentence) => ({
        id: sentence.id,
        label: sentence.text,
        start: sentence.start,
        end: sentence.end,
        sentence: true,
      })),
    });
    const layers = layerSpans(state.edit, state.captions, duration);
    let outsideCount = 0;
    for (const row of layers) {
      for (const item of row.items) {
        item.outside = outsideLayerIds([item], 0, duration).length > 0;
        if (item.outside) outsideCount += 1;
      }
    }
    for (const row of layers) rows.push(row);

    dom.grid.replaceChildren();
    dom.grid.append(el("div", { class: "st-tl-corner", text: "Track" }), makeRuler());

    for (const row of rows) {
      const label = el("div", { class: `st-tl-label st-tl-label-${row.kind}` }, [
        el("span", { text: row.label || LANE_LABELS[row.kind] || "Layer" }),
        row.kind !== "sentences" ? el("small", {
          text: String(row.items.length),
        }) : null,
      ]);
      if (row.kind !== "sentences") {
        label.setAttribute("role", "button");
        label.setAttribute("tabindex", "0");
        label.addEventListener("click", () => handlers.onSelect(row.kind, ""));
        label.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handlers.onSelect(row.kind, "");
          }
        });
      }
      dom.grid.append(label, makeTrack(row));
    }

    const layerCount = rows.reduce((total, row) => total + (row.kind === "sentences" ? 0 : row.items.length), 0);
    dom.count.textContent = `${layerCount} ${layerCount === 1 ? "layer" : "layers"}`;
    dom.span.textContent = `${formatTime(0)} – ${formatTime(duration)}`;
    dom.outside.hidden = outsideCount === 0;
    dom.outside.textContent = `${outsideCount} outside`;
    dom.outside.title = outsideCount
      ? `${outsideCount} layer${outsideCount === 1 ? "" : "s"} outside the trimmed story; kept, not deleted.`
      : "";
    paintPlayheads();
    return outsideCount;
  }

  function updateTime(time) {
    state.time = Math.max(0, Math.min(duration, numberOr(time)));
    paintPlayheads();
  }

  function updateSelected(value) {
    selected = value || null;
    for (const bar of dom.grid.querySelectorAll(".st-tl-bar")) {
      const match = selected
        && bar.dataset.kind === selected.kind
        && bar.dataset.layer === selected.id;
      bar.classList.toggle("is-selected", Boolean(match));
    }
  }

  dom.scroll.addEventListener("keydown", (event) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.shiftKey ? 1 : 0.1;
      handlers.onSeek(numberOr(state.time) + (event.key === "ArrowRight" ? delta : -delta));
    } else if (event.key === "Home") {
      event.preventDefault();
      handlers.onSeek(0);
    } else if (event.key === "End") {
      event.preventDefault();
      handlers.onSeek(duration);
    }
  });

  return {
    setData({ edit, captions, story, duration: nextDuration, aspect } = {}) {
      if (story !== undefined) {
        if (
          trimOverride
          && story?.id === trimOverride.storyId
          && Math.abs(numberOr(story?.end) - trimOverride.staleEnd) < 0.001
        ) {
          // The screen still holds the pre-trim story; keep the newer bounds.
          story = trimOverride.story;
          if (
            typeof nextDuration === "number"
            && Math.abs(nextDuration - trimOverride.staleDuration) < 0.001
          ) {
            nextDuration = trimOverride.duration;
          }
        } else if (trimOverride) {
          trimOverride = null;
        }
      } else if (
        trimOverride
        && typeof nextDuration === "number"
        && Math.abs(nextDuration - trimOverride.staleDuration) < 0.001
      ) {
        nextDuration = trimOverride.duration;
      }
      state = {
        edit: edit === undefined ? state.edit : edit,
        captions: captions === undefined ? state.captions : captions,
        story: story === undefined ? state.story : story,
        aspect: aspect || state.aspect,
        time: state.time,
      };
      if (typeof nextDuration === "number" && Number.isFinite(nextDuration)) {
        duration = Math.max(0.1, nextDuration);
      }
      render();
      updateSelected(selected);
    },
    setTime(time) {
      updateTime(time);
    },
    setSelected(value) {
      updateSelected(value);
    },
    setCaptionData(captions) {
      state.captions = captions;
      render();
      updateSelected(selected);
    },
    destroy() {
      disposed = true;
      root.replaceChildren();
    },
  };
}
