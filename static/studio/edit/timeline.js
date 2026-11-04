/**
 * Studio editor timeline.
 *
 * The sentence lane is drawn over the server's sentence `pool`, not only over
 * the current story. That is what lets either handle move outward as well as
 * inward. Dragging asks the trim route for a `dry_run` so the length and the
 * layer/caption receipt update before the drop; the drop commits through the
 * same atomic trim route as Stories ±.
 *
 * One duration source: the parent passes the story duration and receives the
 * committed `TrimResult`. The timeline never keeps a private override.
 */

import { el } from "../ui.js";
import { formatSpan, formatTime, layerSpans, numberOr } from "./model.js";
import { icon } from "./icons.js";
import { trimStory } from "../api.js";
import { receiptSummary } from "../stories.js";

const LANE_LABELS = {
  scenes: "Scenes",
  clean: "Clean",
  text: "Text",
  captions: "Captions",
  effects: "Effects",
  color: "Color",
  audio: "Audio",
};

const DRY_RUN_MS = 90;

function niceStep(duration) {
  const target = Math.max(0.5, duration / 6);
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  return steps.find((step) => step >= target) || 600;
}

/** One sentence in the server pool, in source order. */
function poolRows(trim) {
  const list = Array.isArray(trim?.pool) ? trim.pool : [];
  return list
    .filter((row) => row && row.id !== undefined && row.id !== null)
    .map((row) => {
      const start = numberOr(row.start);
      const end = Math.max(start + 0.05, numberOr(row.end, start + 0.05));
      return {
        id: row.id,
        text: String(row.text || "").replace(/\s+/g, " ").trim(),
        start,
        end,
        duration: Math.max(0.05, end - start),
      };
    });
}

function sentenceIds(trim, story) {
  const fromTrim = Array.isArray(trim?.story?.sentence_ids) ? trim.story.sentence_ids : [];
  if (fromTrim.length) return fromTrim.map(String);
  return (Array.isArray(story?.sentences) ? story.sentences : []).map((row) => String(row?.id));
}

/** Committed range as indexes into the pool. Falls back to the whole pool. */
function rangeInPool(pool, trim, story) {
  if (!pool.length) return { startIndex: 0, endIndex: 0 };
  const ids = new Set(sentenceIds(trim, story));
  let startIndex = pool.findIndex((row) => ids.has(String(row.id)));
  if (startIndex < 0) startIndex = 0;
  let endIndex = startIndex;
  for (let index = pool.length - 1; index >= startIndex; index -= 1) {
    if (ids.has(String(pool[index].id))) {
      endIndex = index;
      break;
    }
  }
  if (endIndex < startIndex) endIndex = pool.length - 1;
  return { startIndex, endIndex };
}

function sumDurations(rows) {
  return rows.reduce((total, row) => total + Math.max(0, numberOr(row.duration)), 0);
}

function clampIndex(value, low, high) {
  return Math.max(low, Math.min(high, Math.round(numberOr(value, low))));
}

/** A readable message for a refused dry run or commit. */
function trimMessage(error) {
  if (!error) return "";
  if (error.status === 404 || error.status === 405) {
    return "Trimming needs the latest server. Restart VibeCut and open this story again.";
  }
  return error.message || "The new range could not be checked.";
}

export function mountTimeline(root, options = {}) {
  const handlers = {
    onSeek: options.onSeek || (() => {}),
    onSelect: options.onSelect || (() => {}),
    onAdd: options.onAdd || (() => {}),
    onAddMoment: options.onAddMoment || (() => {}),
    onReorder: options.onReorder || (() => {}),
    onRole: options.onRole || (() => {}),
    onAudioBus: options.onAudioBus || (() => {}),
    onTrim: options.onTrim || (() => {}),
    onConflict: options.onConflict || (() => {}),
    onUndo: options.onUndo || (() => {}),
    onRedo: options.onRedo || (() => {}),
    onUndoTrim: options.onUndoTrim || (() => {}),
    onRecord: options.onRecord || (() => {}),
    onImportSubtitle: options.onImportSubtitle || (() => {}),
    onDelete: options.onDelete || (() => {}),
    onSplit: options.onSplit || (() => {}),
    onExtractFrame: options.onExtractFrame || (() => {}),
    onAddMedia: options.onAddMedia || (() => {}),
    onAddText: options.onAddText || (() => {}),
    onAddAudio: options.onAddAudio || (() => {}),
    onEffects: options.onEffects || (() => {}),
    onMosaic: options.onMosaic || (() => {}),
    onAutoCaptions: options.onAutoCaptions || (() => {}),
    onOverlayTrack: options.onOverlayTrack || (() => {}),
    onReverse: options.onReverse || (() => {}),
    onDuplicate: options.onDuplicate || (() => {}),
    onFreeze: options.onFreeze || (() => {}),
    onFound: options.onFound || (() => {}),
    beforeTrim: options.beforeTrim || (() => Promise.resolve(true)),
  };
  let disposed = false;
  const laneLocked = new Set();
  const laneHidden = new Set();
  let jobId = String(options.jobId || "");
  let setId = "";
  let duration = 10;
  let selected = null;
  let seeking = false;
  let busy = false;
  let drag = null;
  let dry = null;
  let dryError = null;
  let dryTimer = 0;
  let drySeq = 0;
  let renderRaf = 0;
  let dragCleanup = null;
  let pendingFocus = "";
  // Keeps "Saving the trim…" and the committed receipt visible across the
  // re-render that follows a drop.
  let statusHold = null;
  let state = {
    edit: null,
    captions: null,
    story: null,
    aspect: "9:16",
    trim: null,
    foundText: [],
    time: 0,
  };

  root.innerHTML = `
    <section class="st-timeline" aria-label="Timeline">
      <div class="st-tl-toolbar st-tl-global">
        <div class="st-tl-toolset">
          <button id="st-timeline-undo-trim" class="st-tl-icon" type="button" title="Undo trim" aria-label="Undo trim"></button>
          <button id="st-timeline-undo" class="st-tl-icon" type="button" title="Undo" aria-label="Undo"></button>
          <button id="st-timeline-redo" class="st-tl-icon" type="button" title="Redo" aria-label="Redo"></button>
          <span class="st-tl-sep" aria-hidden="true"></span>
          <button id="st-timeline-record" class="st-tl-icon is-record" type="button" title="Record voice-over" aria-label="Record voice-over"></button>
          <button id="st-timeline-subtitle" class="st-tl-icon" type="button" title="Import subtitle file" aria-label="Import subtitle file"></button>
        </div>
        <div class="st-tl-toolset">
          <span id="st-timeline-outside" class="st-chip st-chip-quiet" hidden></span>
          <span id="st-timeline-span" class="st-mono st-timeline-span">0:00.0</span>
          <span id="st-timeline-count" class="st-chip st-chip-quiet">0 layers</span>
          <span class="st-tl-sep" aria-hidden="true"></span>
          <button id="st-timeline-zoom-out" class="st-tl-icon" type="button" title="Zoom out" aria-label="Zoom out"></button>
          <button id="st-timeline-fit" class="st-tl-icon" type="button" title="Fit timeline" aria-label="Fit timeline"></button>
          <button id="st-timeline-zoom-in" class="st-tl-icon" type="button" title="Zoom in" aria-label="Zoom in"></button>
          <button id="st-timeline-collapse" class="st-tl-icon" type="button" title="Collapse timeline" aria-label="Collapse timeline"></button>
        </div>
      </div>
      <div id="st-timeline-context" class="st-tl-toolbar st-tl-context" aria-label="Timeline actions">
        <div class="st-tl-toolset st-tl-add-actions">
          <button class="st-tl-icon" type="button" data-tl-action="add-media" title="Add media" aria-label="Add media"></button>
          <button class="st-tl-icon" type="button" data-tl-action="add-text" title="Add text" aria-label="Add text"></button>
          <button class="st-tl-icon" type="button" data-tl-action="add-audio" title="Add audio" aria-label="Add audio"></button>
          <button class="st-tl-icon" type="button" data-tl-action="effects" title="Effects" aria-label="Effects"></button>
          <button class="st-tl-icon" type="button" data-tl-action="mosaic" title="Mosaic layer" aria-label="Mosaic layer"></button>
          <button class="st-tl-icon" type="button" data-tl-action="captions" title="Auto captions" aria-label="Auto captions"></button>
          <button class="st-tl-icon" type="button" data-tl-action="overlay" title="Add overlay track" aria-label="Add overlay track"></button>
        </div>
        <div class="st-tl-toolset st-tl-edit-actions">
          <button class="st-tl-icon" type="button" data-tl-action="trim" title="Trim clip" aria-label="Trim clip"></button>
          <button class="st-tl-icon" type="button" data-tl-action="split" title="Split at playhead" aria-label="Split at playhead"></button>
          <button class="st-tl-icon" type="button" data-tl-action="duplicate" title="Duplicate scene" aria-label="Duplicate scene"></button>
          <button class="st-tl-icon" type="button" data-tl-action="reverse" title="Reverse clip" aria-label="Reverse clip"></button>
          <button class="st-tl-icon" type="button" data-tl-action="delete" title="Delete selected layer" aria-label="Delete selected layer"></button>
          <span class="st-tl-sep" aria-hidden="true"></span>
          <button class="st-tl-icon" type="button" data-tl-action="crop" title="Clip crop (output aspect stays in Preview)" aria-label="Clip crop" disabled></button>
          <button class="st-tl-icon" type="button" data-tl-action="rotate" title="Rotate" aria-label="Rotate" disabled></button>
          <button class="st-tl-icon" type="button" data-tl-action="mirror" title="Mirror" aria-label="Mirror" disabled></button>
          <button class="st-tl-icon" type="button" data-tl-action="flip" title="Flip" aria-label="Flip" disabled></button>
          <span class="st-tl-sep" aria-hidden="true"></span>
          <button class="st-tl-icon" type="button" data-tl-action="extract-audio" title="Extract audio" aria-label="Extract audio" disabled></button>
          <button class="st-tl-icon" type="button" data-tl-action="freeze" title="Freeze frame" aria-label="Freeze frame"></button>
        </div>
      </div>
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
    context: $("#st-timeline-context"),
    undoTrim: $("#st-timeline-undo-trim"),
    undo: $("#st-timeline-undo"),
    redo: $("#st-timeline-redo"),
    record: $("#st-timeline-record"),
    subtitle: $("#st-timeline-subtitle"),
    zoomOut: $("#st-timeline-zoom-out"),
    fit: $("#st-timeline-fit"),
    zoomIn: $("#st-timeline-zoom-in"),
    collapse: $("#st-timeline-collapse"),
    actions: Array.from(root.querySelectorAll("[data-tl-action]")),
  };
  const toolIcons = [
    [dom.undoTrim, "history"], [dom.undo, "undo"], [dom.redo, "redo"],
    [dom.record, "mic"], [dom.subtitle, "captions"],
    [dom.zoomOut, "minus"], [dom.fit, "expand"], [dom.zoomIn, "plus"],
    [dom.collapse, "chevron-up"],
  ];
  for (const [node, name] of toolIcons) {
    if (node) node.append(icon(name, { size: 15 }));
  }
  const actionIcons = {
    "add-media": "plus", "add-text": "type", "add-audio": "audio-lines",
    "effects": "sparkles", "mosaic": "mosaic", "captions": "captions",
    "overlay": "layers", "reverse": "reverse", "trim": "trim", "split": "split",
    "duplicate": "copy", "delete": "trash", "crop": "crop", "rotate": "rotate-cw",
    "mirror": "mirror", "flip": "flip", "extract-audio": "audio-lines",
    "freeze": "freeze",
  };
  for (const button of dom.actions) {
    button.append(icon(actionIcons[button.dataset.tlAction] || "square", { size: 15 }));
  }
  let zoom = 1;
  let loop = false;
  let collapsed = false;

  function applyZoom() {
    dom.grid.style.width = `${Math.round(zoom * 100)}%`;
    dom.grid.style.minWidth = zoom > 1 ? `${Math.round(zoom * 100)}%` : "";
    dom.scroll.classList.toggle("is-zoomed", zoom > 1);
  }
  function setLoop(value) {
    loop = Boolean(value);
    dom.actions.find((button) => button.dataset.tlAction === "loop")?.classList.toggle("is-on", loop);
  }
  function setHistory({ canUndo = false, canRedo = false, canUndoTrim = false } = {}) {
    if (dom.undo) dom.undo.disabled = !canUndo;
    if (dom.redo) dom.redo.disabled = !canRedo;
    if (dom.undoTrim) dom.undoTrim.disabled = !canUndoTrim;
  }
  function updateContext() {
    if (!dom.context) return;
    dom.context.classList.toggle("has-selection", Boolean(selected));
  }
  dom.undoTrim?.addEventListener("click", () => handlers.onUndoTrim());
  dom.undo?.addEventListener("click", () => handlers.onUndo());
  dom.redo?.addEventListener("click", () => handlers.onRedo());
  dom.record?.addEventListener("click", () => handlers.onRecord());
  dom.subtitle?.addEventListener("click", () => handlers.onImportSubtitle());
  dom.zoomOut?.addEventListener("click", () => { zoom = Math.max(1, zoom - 0.25); applyZoom(); });
  dom.zoomIn?.addEventListener("click", () => { zoom = Math.min(4, zoom + 0.25); applyZoom(); });
  dom.fit?.addEventListener("click", () => { zoom = 1; applyZoom(); });
  dom.collapse?.addEventListener("click", () => {
    collapsed = !collapsed;
    root.classList.toggle("is-collapsed", collapsed);
    dom.collapse.setAttribute("aria-pressed", collapsed ? "true" : "false");
    dom.collapse.title = collapsed ? "Expand timeline" : "Collapse timeline";
  });
  for (const button of dom.actions) {
    button.addEventListener("click", () => {
      const action = button.dataset.tlAction;
      if (action === "trim") {
        dom.grid.querySelector('.st-tl-trim[data-edge="start"]')?.focus();
        return;
      }
      const map = {
        "add-media": "onAddMedia", "add-text": "onAddText", "add-audio": "onAddAudio",
        "effects": "onEffects", "mosaic": "onMosaic", "captions": "onAutoCaptions",
        "overlay": "onOverlayTrack", "reverse": "onReverse", "split": "onSplit",
        "duplicate": "onDuplicate", "delete": "onDelete", "freeze": "onFreeze",
      };
      const handler = map[action];
      if (handler) handlers[handler]();
    });
  }
  applyZoom();
  updateContext();

  function setStatus(message, tone = "") {
    dom.status.textContent = message || "";
    dom.status.dataset.tone = tone;
    dom.status.hidden = !message;
  }

  function pool() {
    return poolRows(state.trim);
  }

  function committedRange(rows = pool()) {
    return rangeInPool(rows, state.trim, state.story);
  }

  function workingRange(rows) {
    if (!drag) return committedRange(rows);
    return {
      startIndex: clampIndex(drag.startIndex, 0, rows.length - 1),
      endIndex: clampIndex(drag.endIndex, 0, rows.length - 1),
    };
  }

  /**
   * The axis runs from the first pool sentence to the last one. The story is
   * a window inside it. `leading` is the pool seconds before the window; every
   * layer bar is offset by it so the bars stay over the same words.
   */
  function model() {
    const rows = pool();
    const working = workingRange(rows);
    if (!rows.length) {
      return {
        rows,
        working,
        leading: 0,
        storyDuration: Math.max(0.1, duration),
        trailing: 0,
        axis: Math.max(0.1, duration),
        hasPool: false,
      };
    }
    const leading = sumDurations(rows.slice(0, working.startIndex));
    const estimate = sumDurations(rows.slice(working.startIndex, working.endIndex + 1));
    const storyDuration = drag
      ? Math.max(0.1, numberOr(drag.storyDuration, duration))
      : duration;
    const trailing = sumDurations(rows.slice(working.endIndex + 1));
    // The timeline shows the story, not the whole sentence pool. The pool
    // still drives trim bounds; it is not drawn as empty time. During a drag
    // the view stays fixed so the pointer keeps one stable time axis.
    return {
      rows,
      working,
      leading: 0,
      poolLeading: drag ? numberOr(drag.poolLeading) : leading,
      storyDuration,
      trailing: 0,
      axis: drag ? Math.max(0.1, drag.axis) : Math.max(0.1, storyDuration),
      hasPool: true,
      poolHidden: true,
    };
    return {
      rows,
      working,
      leading,
      storyDuration,
      trailing,
      axis: Math.max(0.1, leading + storyDuration + trailing),
      hasPool: true,
    };
  }

  function axisPosition(value, view) {
    return (numberOr(value) / Math.max(0.1, view.axis)) * 100;
  }

  function position(item, view) {
    const start = Math.max(0, Math.min(view.axis, numberOr(item.start)));
    const end = Math.max(start + 0.02, Math.min(view.axis, numberOr(item.end, start + 0.1)));
    return {
      left: axisPosition(start, view),
      width: Math.max(0.3, axisPosition(end - start, view)),
    };
  }

  function storyTimeFromAxis(value, view) {
    return Math.max(0, Math.min(duration, numberOr(value) - view.leading));
  }

  function timeFromEvent(event) {
    const track = event.currentTarget;
    const box = track.getBoundingClientRect();
    if (!box.width) return 0;
    const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    return ratio * model().axis;
  }

  function makePlayhead() {
    return el("i", { class: "st-tl-playhead", "aria-hidden": "true" });
  }

  function paintPlayheads(view) {
    const time = view.leading + Math.max(0, Math.min(duration, numberOr(state.time)));
    const left = `${axisPosition(time, view)}%`;
    for (const track of dom.grid.querySelectorAll(".st-tl-track")) {
      const line = track.querySelector(".st-tl-playhead");
      if (line) line.style.left = left;
    }
  }

  function outsideIds(view) {
    if (drag && dry?.receipt?.layers) {
      return new Set((dry.receipt.layers.outside || []).map(String));
    }
    return null;
  }

  function pinnedIds() {
    if (!drag || !dry?.receipt?.layers) return new Set();
    return new Set((dry.receipt.layers.pinned || []).map(String));
  }

  function makeBar(item, kind, view) {
    const geometry = position(item, view);
    const label = String(item.label || "").trim();
    const outside = Boolean(item.outside);
    const selectedNow = selected?.kind === kind && selected?.id === item.layerId;
    const storyStart = item.storyStart === null || item.storyStart === undefined
      ? null
      : numberOr(item.storyStart);
    const storyEnd = item.storyEnd === null || item.storyEnd === undefined
      ? null
      : numberOr(item.storyEnd);
    const span = storyStart === null
      ? "Outside the story range"
      : formatSpan(storyStart, storyEnd ?? storyStart);
    const title = `${label || LANE_LABELS[kind] || "Layer"} · ${span}${outside ? " · outside the trimmed story" : ""}${item.hidden ? " · hidden outside, kept in the Edit" : ""}${item.pinned ? " · pinned to the story start" : ""}`;
    const attrs = {
      class: `st-tl-bar st-tl-bar-${kind}${item.found ? " is-found" : ""}${item.sceneClip ? ` st-tl-role-${item.role || "beat"}` : ""}${item.muted ? " is-muted" : ""}${item.dashed ? " is-dashed" : ""}${outside ? " is-outside" : ""}${item.hidden ? " is-hidden-outside" : ""}${item.pinned ? " is-pinned" : ""}${selectedNow ? " is-selected" : ""}`,
      title,
      "aria-label": title,
      style: `left:${geometry.left}%;width:${geometry.width}%`,
      dataset: {
        kind,
        layer: kind === "scenes" ? String(item.index ?? "") : (item.layerId || item.id),
        start: String(storyStart === null ? 0 : storyStart),
        outside: outside ? "1" : "0",
        subgroup: item.subgroup || null,
        audio: String(item.id || "").startsWith("audio_") ? String(item.id).replace("audio_", "") : null,
        found: item.found ? String(item.trackletId || "") : null,
      },
    };
    if (kind === "scenes") {
      attrs.role = "button";
      attrs.tabindex = "0";
    } else {
      attrs.type = "button";
    }
    const button = el(kind === "scenes" ? "div" : "button", attrs, [
      label ? el("span", { text: label }) : null,
      kind === "scenes" ? el("button", {
        class: "st-tl-role-btn",
        type: "button",
        text: "⋯",
        title: "Change this scene's role",
        "aria-label": "Change this scene's role",
      }) : null,
    ]);
    if (kind === "scenes") {
      button.draggable = true;
      button.dataset.sceneIndex = String(item.index ?? 0);
      button.querySelector(".st-tl-role-btn")?.addEventListener("click", (event) => {
        event.stopPropagation();
        handlers.onRole(item.index ?? 0, item);
      });
      button.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handlers.onSeek(Math.max(0, Math.min(duration, storyStart ?? 0)));
        }
      });
      button.addEventListener("dragstart", (event) => {
        event.dataTransfer?.setData("text/plain", String(item.index ?? 0));
        event.dataTransfer.effectAllowed = "move";
      });
      button.addEventListener("dragover", (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      });
      button.addEventListener("drop", (event) => {
        event.preventDefault();
        const from = Number(event.dataTransfer?.getData("text/plain"));
        const to = Number(item.index ?? 0);
        if (Number.isFinite(from) && from !== to) handlers.onReorder(from, to);
      });
    }
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (item.found) {
        handlers.onFound(item.trackletId);
        return;
      }
      if (kind === "scenes") handlers.onSelect("scenes", String(item.index ?? 0));
      else handlers.onSelect(kind, item.layerId || item.id);
      const seekTo = storyStart ?? (numberOr(item.start) < view.leading ? 0 : duration);
      handlers.onSeek(Math.max(0, Math.min(duration, seekTo)));
    });
    return button;
  }

  function sceneRows() {
    const custom = Array.isArray(state.edit?.sequence) ? state.edit.sequence : [];
    const clips = custom.length
      ? custom
      : (Array.isArray(state.story?.clips) ? state.story.clips : []);
    const rows = [];
    let offset = 0;
    for (const clip of clips) {
      const span = Math.max(0.05, numberOr(clip?.dur, numberOr(clip?.end) - numberOr(clip?.start)));
      const scene = Number(clip?.scene);
      const role = String(clip?.role || "beat");
      const beatKind = String(clip?.beat_kind || "");
      const blank = clip?.kind === "blank";
      const roleLabel = blank ? "Blank" : role === "hook" ? "Hook"
        : role === "payoff" ? "Payoff"
          : beatKind === "broll" ? "B-roll"
            : beatKind === "statement" ? "Statement"
              : beatKind === "proof" ? "Proof"
                : beatKind === "context" ? "Context"
                  : "Scene";
      rows.push({
        id: `scene-${clip?.scene}-${offset.toFixed(3)}`,
        index: rows.length,
        label: `${rows.length + 1} ${roleLabel}`.trim(),
        start: offset,
        end: offset + span,
        storyStart: offset,
        storyEnd: offset + span,
        role,
        beat_kind: beatKind,
        scene,
        sourceClip: clip,
        sceneClip: true,
      });
      offset += span;
    }
    return rows;
  }

  function sentenceRows(view) {
    if (view.poolHidden) {
      const rows = [];
      let cursor = 0;
      for (const row of view.rows.slice(view.working.startIndex, view.working.endIndex + 1)) {
        const span = Math.max(0.05, Number(row.duration) || 0.05);
        rows.push({
          id: row.id,
          label: row.text || "Sentence",
          start: cursor,
          end: cursor + span,
          storyStart: cursor,
          storyEnd: cursor + span,
          sentence: true,
        });
        cursor += span;
      }
      return rows;
    }
    if (!view.hasPool) {
      // Before the trim route answers, draw the current story as it is.
      const rows = [];
      let offset = 0;
      for (const sentence of state.story?.sentences || []) {
        const span = Math.max(0.05, numberOr(sentence.end) - numberOr(sentence.start));
        rows.push({
          id: sentence.id,
          label: sentence.text || "Sentence",
          start: offset,
          end: offset + span,
          storyStart: offset,
          storyEnd: offset + span,
          sentence: true,
        });
        offset += span;
      }
      return rows;
    }
    const rows = [];
    const { rows: all, working, leading, storyDuration } = view;
    let cursor = 0;
    for (let index = 0; index < working.startIndex; index += 1) {
      const row = all[index];
      rows.push({
        id: row.id,
        label: row.text || `Sentence ${index + 1}`,
        start: cursor,
        end: cursor + row.duration,
        storyStart: null,
        storyEnd: null,
        sentence: true,
      });
      cursor += row.duration;
    }
    const selectedRows = all.slice(working.startIndex, working.endIndex + 1);
    const weight = sumDurations(selectedRows) || selectedRows.length || 1;
    let at = leading;
    for (const row of selectedRows) {
      const span = storyDuration * ((row.duration || 1) / weight);
      rows.push({
        id: row.id,
        label: row.text || "Sentence",
        start: at,
        end: at + span,
        storyStart: at - leading,
        storyEnd: at + span - leading,
        sentence: true,
      });
      at += span;
    }
    cursor = leading + storyDuration;
    for (let index = working.endIndex + 1; index < all.length; index += 1) {
      const row = all[index];
      rows.push({
        id: row.id,
        label: row.text || `Sentence ${index + 1}`,
        start: cursor,
        end: cursor + row.duration,
        storyStart: null,
        storyEnd: null,
        sentence: true,
      });
      cursor += row.duration;
    }
    return rows;
  }

  function layerRows(view) {
    const rows = layerSpans(state.edit, state.captions, duration);
    const hiddenIds = new Set((state.edit?.graphics || [])
      .filter((layer) => layer?.hidden)
      .map((layer) => String(layer.id)));
    const pinnedEdit = new Set((state.edit?.graphics || [])
      .filter((layer) => layer?.pin && layer.pin !== "source")
      .map((layer) => String(layer.id)));
    const receiptOutside = outsideIds(view);
    const pinned = pinnedIds();
    let outsideCount = 0;
    const cleanRow = rows.find((row) => row.kind === "clean");
    if (cleanRow && state.foundText.length) {
      for (const found of state.foundText) {
        const start = numberOr(found.storyStart, NaN);
        const end = numberOr(found.storyEnd, NaN);
        if (!Number.isFinite(start) || !Number.isFinite(end)) continue;
        cleanRow.items.push({
          id: `found:${found.id}`,
          label: found.text || "Found text",
          start,
          end: Math.max(start + 0.08, end),
          storyStart: start,
          storyEnd: Math.max(start + 0.08, end),
          found: true,
          trackletId: found.id,
          layerCount: numberOr(found.layerCount, 0),
        });
      }
    }
    for (const row of rows) {
      row.items = row.items.map((item) => {
        const storyStart = numberOr(item.start);
        const storyEnd = numberOr(item.end, storyStart);
        const hidden = hiddenIds.has(String(item.layerId));
        const outside = hidden || (receiptOutside
          ? receiptOutside.has(String(item.layerId))
          : storyStart < -0.001 || storyEnd > duration + 0.001);
        if (outside) outsideCount += 1;
        return {
          ...item,
          start: view.leading + storyStart,
          end: view.leading + storyEnd,
          storyStart,
          storyEnd,
          outside,
          hidden,
          pinned: pinned.has(String(item.layerId)) || pinnedEdit.has(String(item.layerId)),
        };
      });
    }
    return { rows, outsideCount };
  }

  function makeTrack(row, view, extra = {}) {
    const track = el("div", {
      class: `st-tl-track st-tl-track-${row.kind} st-tl-track-${row.id}`,
      dataset: { kind: row.kind },
      role: "group",
      "aria-label": `${LANE_LABELS[row.kind] || row.label} track`,
    });
    track.append(makePlayhead());
    const left = view.hasPool ? axisPosition(view.leading, view) : 0;
    const right = view.hasPool ? axisPosition(view.leading + view.storyDuration, view) : 100;
    if (left > 0.2) {
      track.append(el("i", {
        class: "st-tl-dim",
        "aria-hidden": "true",
        style: `left:0;width:${left}%`,
      }));
    }
    if (right < 99.8) {
      track.append(el("i", {
        class: "st-tl-dim",
        "aria-hidden": "true",
        style: `left:${right}%;right:0`,
      }));
    }
    if (view.hasPool) {
      track.append(el("i", {
        class: "st-tl-window",
        "aria-hidden": "true",
        style: `left:${left}%;width:${Math.max(0.3, right - left)}%`,
      }));
    }
    for (const item of row.items) track.append(makeBar(item, row.kind, view));
    if (row.kind === "sentences") {
      track.append(
        makeTrimHandle("start", view),
        makeTrimHandle("end", view),
      );
    }
    track.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-bar, .st-tl-trim")) return;
      seeking = true;
      track.setPointerCapture?.(event.pointerId);
      handlers.onSeek(storyTimeFromAxis(timeFromEvent(event), view));
    });
    track.addEventListener("pointermove", (event) => {
      if (!seeking) return;
      handlers.onSeek(storyTimeFromAxis(timeFromEvent(event), view));
    });
    track.addEventListener("pointerup", () => { seeking = false; });
    track.addEventListener("pointercancel", () => { seeking = false; });
    if (extra.bounds) track.dataset.bounds = extra.bounds;
    return track;
  }

  function cumulativeBoundary(rows, index) {
    return sumDurations(rows.slice(0, index));
  }

  function nearestPoolIndex(view, edge, axisTime) {
    const rows = view.rows;
    if (!rows.length) return null;
    const low = edge === "start" ? 0 : view.working.startIndex;
    const high = edge === "start" ? view.working.endIndex : rows.length - 1;
    let best = low;
    let distance = Infinity;
    for (let index = low; index <= high; index += 1) {
      const boundary = edge === "start"
        ? cumulativeBoundary(rows, index)
        : cumulativeBoundary(rows, index + 1);
      const gap = Math.abs(boundary - axisTime);
      if (gap < distance) {
        best = index;
        distance = gap;
      }
    }
    return best;
  }

  function scheduleRender() {
    if (disposed || renderRaf) return;
    renderRaf = window.requestAnimationFrame(() => {
      renderRaf = 0;
      render();
    });
  }

  function requestDryRun() {
    const view = model();
    if (!drag || !view.hasPool || !state.trim) return;
    if (dryTimer) window.clearTimeout(dryTimer);
    dryTimer = window.setTimeout(() => {
      dryTimer = 0;
      const seq = ++drySeq;
      const working = { startIndex: drag?.startIndex, endIndex: drag?.endIndex };
      if (working.startIndex === undefined) return;
      const start = view.rows[working.startIndex];
      const end = view.rows[working.endIndex];
      if (!start || !end) return;
      const wanted = { ...working };
      const stillCurrent = () => !disposed
        && seq === drySeq
        && drag
        && drag.startIndex === wanted.startIndex
        && drag.endIndex === wanted.endIndex;
      setStatus("Checking the new length and layers…", "busy");
      void trimStory(jobId, setId, state.story.id, {
        expectedRevision: numberOr(state.trim?.revision),
        startSentence: start.id,
        endSentence: end.id,
        dryRun: true,
      }).then((result) => {
        if (!stillCurrent()) return;
        dry = result;
        dryError = null;
        scheduleRender();
        paintTrimStatus();
      }).catch((error) => {
        if (!stillCurrent()) return;
        dry = null;
        dryError = error;
        scheduleRender();
        paintTrimStatus();
      });
    }, DRY_RUN_MS);
  }

  function holdStatus(message, tone = "") {
    statusHold = message ? { message, tone } : null;
    setStatus(message, tone);
  }

  function paintTrimStatus() {
    if (statusHold) {
      setStatus(statusHold.message, statusHold.tone);
      return;
    }
    const view = model();
    if (!drag) {
      if (!state.trim) {
        setStatus(
          view.hasPool
            ? ""
            : "Trim needs the story range from the server. Reload the latest build to drag the handles.",
        );
        return;
      }
      setStatus(
        `Story ${formatTime(0)} → ${formatTime(duration)}. Drag either handle at a sentence bound.`,
      );
      return;
    }
    if (dryError) {
      setStatus(trimMessage(dryError), "bad");
      return;
    }
    const estimate = view.storyDuration;
    if (dry) {
      const summary = receiptSummary(dry.receipt);
      setStatus(
        `${formatTime(estimate)} new length${summary ? ` · ${summary}` : ""}`,
        "ok",
      );
      return;
    }
    setStatus(`${formatTime(estimate)} new length · checking layers and captions…`, "busy");
  }

  function makeTrimHandle(edge, view) {
    const name = edge === "start" ? "Trim the story start" : "Trim the story end";
    const working = view.working;
    const index = edge === "start" ? working.startIndex : working.endIndex;
    const boundary = edge === "start"
      ? cumulativeBoundary(view.rows, working.startIndex)
      : cumulativeBoundary(view.rows, working.endIndex + 1);
    const left = view.hasPool ? axisPosition(boundary, view) : 0;
    const disabled = !state.trim || !view.hasPool || view.rows.length < 2 || busy;
    const handle = el("button", {
      class: `st-tl-trim st-tl-trim-${edge}${drag?.edge === edge ? " is-dragging" : ""}`,
      type: "button",
      title: disabled
        ? "Trim is not available yet."
        : `${name}. Snaps to sentence bounds.`,
      "aria-label": `${name}. Snaps to sentence bounds.`,
      role: "slider",
      "aria-valuemin": "0",
      "aria-valuemax": String(Math.max(0, view.rows.length - 1)),
      "aria-valuenow": String(index),
      "aria-valuetext": `${edge === "start" ? "Start" : "End"} at ${formatTime(
        edge === "start" ? storyTimeFromAxis(boundary, view) : duration,
      )}`,
      "aria-disabled": disabled ? "true" : "false",
      dataset: { edge },
      style: `left:${left}%`,
    });

    function onMove(event) {
      if (!drag || drag.edge !== edge) return;
      event.preventDefault();
      const box = dom.grid.querySelector(".st-tl-track-sentences")?.getBoundingClientRect();
      if (!box?.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
      const viewNow = model();
      const indexNow = nearestPoolIndex(
        viewNow, edge, ratio * viewNow.axis + numberOr(viewNow.poolLeading),
      );
      if (indexNow === null) return;
      if (edge === "start") drag.startIndex = indexNow;
      else drag.endIndex = indexNow;
      dry = null;
      dryError = null;
      requestDryRun();
      scheduleRender();
    }

    function onUp() {
      if (!drag || drag.edge !== edge) return;
      cleanup();
      if (dryTimer) {
        window.clearTimeout(dryTimer);
        dryTimer = 0;
      }
      const done = { startIndex: drag.startIndex, endIndex: drag.endIndex };
      const committed = committedRange();
      const changed = done.startIndex !== committed.startIndex
        || done.endIndex !== committed.endIndex;
      drag = null;
      dry = null;
      dryError = null;
      if (!changed) {
        holdStatus("Story range unchanged.");
        render();
        return;
      }
      void commitRange(done);
    }

    function onCancel() {
      if (!drag || drag.edge !== edge) return;
      cleanup();
      if (dryTimer) {
        window.clearTimeout(dryTimer);
        dryTimer = 0;
      }
      drag = null;
      dry = null;
      dryError = null;
      render();
    }

    function cleanup() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      if (dragCleanup === cleanup) dragCleanup = null;
    }

    function begin(event) {
      if (disabled) return;
      event.preventDefault();
      event.stopPropagation();
      const viewNow = model();
      drag = {
        edge,
        startIndex: viewNow.working.startIndex,
        endIndex: viewNow.working.endIndex,
        axis: viewNow.axis,
        poolLeading: numberOr(viewNow.poolLeading),
        storyDuration: viewNow.storyDuration,
      };
      pendingFocus = edge;
      statusHold = null;
      dry = null;
      dryError = null;
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onCancel);
      dragCleanup = cleanup;
      paintTrimStatus();
      render();
    }

    handle.addEventListener("pointerdown", begin);
    handle.addEventListener("keydown", (event) => {
      if (disabled) return;
      const viewNow = model();
      const current = viewNow.working;
      const low = edge === "start" ? 0 : current.startIndex;
      const high = edge === "start" ? current.endIndex : viewNow.rows.length - 1;
      let next = edge === "start" ? current.startIndex : current.endIndex;
      if (event.key === "ArrowLeft") next -= 1;
      else if (event.key === "ArrowRight") next += 1;
      else if (event.key === "Home") next = low;
      else if (event.key === "End") next = high;
      else return;
      event.preventDefault();
      event.stopPropagation();
      next = Math.max(low, Math.min(high, next));
      if (next === (edge === "start" ? current.startIndex : current.endIndex)) return;
      pendingFocus = edge;
      void commitRange({
        startIndex: edge === "start" ? next : current.startIndex,
        endIndex: edge === "start" ? current.endIndex : next,
      });
    });
    return handle;
  }

  async function commitRange(range) {
    const view = model();
    const rows = view.rows;
    const start = rows[range.startIndex];
    const end = rows[range.endIndex];
    if (!state.trim || !start || !end || !state.story?.id || !setId || !jobId) {
      setStatus(trimMessage({ status: 404 }), "bad");
      render();
      return;
    }
    busy = true;
    holdStatus("Saving the trim…", "busy");
    render();
    try {
      const saved = await handlers.beforeTrim();
      if (saved === false) {
        holdStatus("The layer changes could not be saved, so the trim was not sent.", "bad");
        return;
      }
      // Keep the revision the creator saw. If another window moved the story,
      // the server returns 409 with the current range instead of letting this
      // drop overwrite it. The transaction rebinds the live Edit heads itself.
      const result = await trimStory(jobId, setId, state.story.id, {
        expectedRevision: numberOr(state.trim?.revision),
        startSentence: start.id,
        endSentence: end.id,
      });
      if (disposed) return;
      const summary = receiptSummary(result?.receipt);
      holdStatus(
        `${summary || "Trim saved."} New length ${formatTime(numberOr(result?.duration, duration))}.`,
        "ok",
      );
      handlers.onTrim(result);
    } catch (error) {
      if (disposed) return;
      if (error?.status === 409) {
        holdStatus(
          `${error.message || "This story changed."} The latest cut is open; drag again.`,
          "bad",
        );
        handlers.onConflict(error);
        return;
      }
      holdStatus(trimMessage(error), "bad");
    } finally {
      busy = false;
      if (!disposed) render();
    }
  }

  function makeRuler(view) {
    const ruler = el("div", { class: "st-tl-ruler", role: "group", "aria-label": "Timeline ruler" });
    const step = niceStep(view.axis);
    const count = Math.floor(view.axis / step) + 1;
    for (let index = 0; index < count; index += 1) {
      const time = index * step;
      const ratio = Math.min(1, time / Math.max(0.1, view.axis));
      const tick = el("button", {
        class: "st-tl-tick",
        type: "button",
        style: `left:${ratio * 100}%`,
        title: `Jump to ${formatSpan(view.leading, view.leading + view.storyDuration)} story time`,
        "aria-label": `Jump to ${formatTime(time)} on the pool`,
        dataset: { time: String(time) },
      }, [el("span", { text: formatTime(time) })]);
      tick.addEventListener("click", (event) => {
        event.stopPropagation();
        handlers.onSeek(storyTimeFromAxis(time, view));
      });
      ruler.append(tick);
    }
    ruler.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-tick")) return;
      const box = ruler.getBoundingClientRect();
      if (!box.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
      handlers.onSeek(storyTimeFromAxis(ratio * view.axis, view));
    });
    return ruler;
  }

  function render() {
    if (disposed) return;
    const view = model();
    const focused = document.activeElement?.dataset?.edge || pendingFocus || "";
    pendingFocus = "";
    const sceneRow = {
      id: "scenes",
      label: "Moments · scenes",
      kind: "scenes",
      items: sceneRows(),
    };
    const sentenceRow = {
      id: "sentences",
      label: "Transcript",
      kind: "sentences",
      items: sentenceRows(view),
    };
    const { rows: layers, outsideCount } = layerRows(view);

    dom.grid.replaceChildren();
    dom.grid.append(el("div", { class: "st-tl-corner", text: "Track" }), makeRuler(view));
    for (const row of [sceneRow, sentenceRow, ...layers]) {
      const label = el("div", { class: `st-tl-label st-tl-label-${row.kind} st-tl-label-${row.id}` }, [
        el("span", { text: row.label || LANE_LABELS[row.kind] || "Layer" }),
        row.kind !== "sentences" ? el("small", { text: String(row.items.length) }) : null,
        row.id === "audio_original" ? (() => {
          const mode = String(state.edit?.audio?.mode || "original");
          const hasMusic = Boolean(state.edit?.audio?.music);
          const modes = el("span", { class: "st-tl-modes" });
          for (const [label, title, next, active] of [
            ["O", "Original audio", hasMusic ? "original_bed" : "original", ["original", "original_bed"].includes(mode)],
            ["V", "No voice", "music_only", mode === "music_only"],
            ["B", "No BGM", "original", mode === "original"],
          ]) {
            const button = el("button", {
              class: `st-tl-mode${active ? " is-on" : ""}`,
              type: "button",
              text: label,
              title,
              "aria-label": title,
              "aria-pressed": active ? "true" : "false",
            });
            button.addEventListener("click", (event) => {
              event.stopPropagation();
              handlers.onAudioBus(next);
            });
            modes.append(button);
          }
          return modes;
        })() : null,
        el("span", { class: "st-tl-lane-tools" }, [
          el("button", {
            class: `st-tl-lane-btn${laneLocked.has(row.id) ? " is-on" : ""}`,
            type: "button",
            title: laneLocked.has(row.id) ? "Unlock lane" : "Lock lane",
            "aria-label": laneLocked.has(row.id) ? `Unlock ${row.label}` : `Lock ${row.label}`,
            "aria-pressed": laneLocked.has(row.id) ? "true" : "false",
          }, [icon("lock", { size: 10 })]),
          el("button", {
            class: `st-tl-lane-btn${laneHidden.has(row.id) ? " is-on" : ""}`,
            type: "button",
            title: laneHidden.has(row.id) ? "Show lane" : "Hide lane",
            "aria-label": laneHidden.has(row.id) ? `Show ${row.label}` : `Hide ${row.label}`,
            "aria-pressed": laneHidden.has(row.id) ? "true" : "false",
          }, [icon("eye", { size: 10 })]),
        ]),
      ]);
      if (row.kind !== "sentences" && row.kind !== "scenes") {
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
      const lockBtn = label.querySelectorAll(".st-tl-lane-btn")[0];
      const eyeBtn = label.querySelectorAll(".st-tl-lane-btn")[1];
      lockBtn?.addEventListener("click", (event) => {
        event.stopPropagation();
        if (laneLocked.has(row.id)) laneLocked.delete(row.id);
        else laneLocked.add(row.id);
        render();
      });
      eyeBtn?.addEventListener("click", (event) => {
        event.stopPropagation();
        if (laneHidden.has(row.id)) laneHidden.delete(row.id);
        else laneHidden.add(row.id);
        render();
      });
      const track = makeTrack(row, view);
      if (laneLocked.has(row.id)) track.classList.add("is-lane-locked");
      if (laneHidden.has(row.id)) track.classList.add("is-lane-hidden");
      dom.grid.append(label, track);
    }

    const layerCount = layers.reduce((total, row) => total + row.items.length, 0);
    dom.count.textContent = `${layerCount} ${layerCount === 1 ? "layer" : "layers"}`;
    dom.span.textContent = `${formatTime(0)} – ${formatTime(duration)}`;
    dom.span.title = view.hasPool ? `Sentence pool ${formatTime(view.axis)}` : "";
    const totalOutside = outsideCount;
    dom.outside.hidden = totalOutside === 0;
    dom.outside.textContent = `${totalOutside} outside`;
    dom.outside.title = totalOutside
      ? `${totalOutside} layer${totalOutside === 1 ? "" : "s"} outside the trimmed story; kept, not deleted.`
      : "";
    paintPlayheads(view);
    updateSelected(selected);
    if (focused) {
      const handle = dom.grid.querySelector(`.st-tl-trim[data-edge="${focused}"]`);
      handle?.focus?.({ preventScroll: true });
    }
    paintTrimStatus();
  }

  function updateTime(time) {
    state.time = Math.max(0, Math.min(duration, numberOr(time)));
    paintPlayheads(model());
  }

  function updateSelected(value) {
    selected = value || null;
    for (const bar of dom.grid.querySelectorAll(".st-tl-bar")) {
      const match = selected
        && bar.dataset.kind === selected.kind
        && bar.dataset.layer === selected.id;
      bar.classList.toggle("is-selected", Boolean(match));
    }
    updateContext();
  }

  dom.scroll.addEventListener("keydown", (event) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      event.stopPropagation();
      const delta = event.shiftKey ? 1 : 1 / 30;
      handlers.onSeek(numberOr(state.time) + (event.key === "ArrowRight" ? delta : -delta));
    } else if (event.key === "Home") {
      event.preventDefault();
      event.stopPropagation();
      handlers.onSeek(0);
    } else if (event.key === "End") {
      event.preventDefault();
      event.stopPropagation();
      handlers.onSeek(duration);
    }
  });

  return {
    setLoop,
    setHistory,
    setData({ edit, captions, story, duration: nextDuration, aspect, trim, setId: nextSetId, jobId: nextJobId, foundText } = {}) {
      if (nextJobId) jobId = String(nextJobId);
      if (nextSetId) setId = String(nextSetId);
      const storyId = String(story?.id ?? state.story?.id ?? "");
      const previousStoryId = String(state.story?.id ?? "");
      if (storyId && storyId !== previousStoryId) {
        dragCleanup?.();
        drag = null;
        dry = null;
        dryError = null;
        statusHold = null;
        pendingFocus = "";
      }
      state = {
        edit: edit === undefined ? state.edit : edit,
        captions: captions === undefined ? state.captions : captions,
        story: story === undefined ? state.story : story,
        aspect: aspect || state.aspect,
        trim: trim === undefined ? state.trim : trim,
        foundText: Array.isArray(foundText) ? foundText : state.foundText,
        time: state.time,
      };
      if (typeof nextDuration === "number" && Number.isFinite(nextDuration)) {
        duration = Math.max(0.1, nextDuration);
        state.time = Math.max(0, Math.min(duration, state.time));
      }
      render();
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
    },
    refresh() {
      render();
    },
    destroy() {
      disposed = true;
      drag = null;
      dragCleanup?.();
      if (dryTimer) window.clearTimeout(dryTimer);
      if (renderRaf) window.cancelAnimationFrame(renderRaf);
      root.replaceChildren();
    },
  };
}
