/**
 * Studio — Edit step.
 *
 * One editor per story and aspect. The document is the Wave-1 Edit; every
 * control writes through its CRUD API. The preview asks the frame route for
 * the exact current frame and falls back to the story proxy and then to a
 * placeholder, so the editor stays usable while the render hooks land.
 */

import {
  getJob,
  getTrimState,
  invalidateReadCache,
  listClipSets,
  rebindStory,
  trimErrorCode,
  trimErrorCurrent,
  undoTrim,
} from "../api.js";
import { el, formatCount, setStatus } from "../ui.js";
import { receiptSummary } from "../stories.js";
import { mountPreview } from "./preview.js";
import { mountTimeline } from "./timeline.js";
import { mountInspector } from "./inspector.js";
import { renderLayersPanel } from "./layers-panel.js";
import { cropAt } from "./canvas-tools.js";
import { manualLayer } from "./layers/clean.js";
import {
  ASPECTS,
  aspectLabel,
  captionPreset,
  clone,
  clamp,
  formatTime,
  newTextLayer,
  numberOr,
  round,
  storyDuration,
} from "./model.js";
import {
  autoSubtitles,
  buildCaptionTrack,
  createEdit,
  getCaptionTrack,
  getCurrentEdit,
  patchCaptionTrack,
  patchEdit,
  syncMediaCookie,
  undoEdit,
} from "./api.js";

const CSS_ID = "vibecut-studio-edit-css";
const CHOICE_KEY = "vibecut.studio.edit.choice";
const ALL_MOMENTS = "__all_moments";
const LAYER_FIELDS = ["clean", "reframe", "motion", "color", "graphics", "captions", "audio"];

function ensureStyles() {
  if (!document.getElementById(CSS_ID)) {
    const link = document.createElement("link");
    link.id = CSS_ID;
    link.rel = "stylesheet";
    link.href = "/static/studio/edit/edit.css?v=0.3.0";
    document.head.append(link);
  }
}

function readChoice() {
  try {
    const value = JSON.parse(localStorage.getItem(CHOICE_KEY) || "null");
    if (value && typeof value === "object") return value;
  } catch (_) {
    /* A private window may refuse storage; the first story is fine. */
  }
  return {};
}

function writeChoice(value) {
  try {
    localStorage.setItem(CHOICE_KEY, JSON.stringify(value));
  } catch (_) {
    /* The editor still works without a remembered choice. */
  }
}

function storyTitle(story, index) {
  const title = String(story?.title || story?.hook?.text || "").replace(/\s+/g, " ").trim();
  return `${String(index + 1).padStart(2, "0")} · ${title || `Moment ${index + 1}`}`;
}

export function mount(root, ctx) {
  ensureStyles();
  syncMediaCookie();

  let disposed = false;
  let preview = null;
  let timeline = null;
  let saving = false;
  let savePromise = null;
  let saveTimer = 0;
  // Set on pagehide: the remaining saves use keepalive requests.
  let unloading = false;
  let loadSeq = 0;
  let timelineRaf = 0;
  let staleReload = false;
  let noticeTimer = 0;

  const state = {
    job: null,
    sets: [],
    set: null,
    story: null,
    aspect: "9:16",
    edit: null,
    captions: null,
    duration: 10,
    playhead: 0,
    activeTab: "text",
    selected: null,
    // Preview-only hide toggles. Clean layers have no `hidden` field on the
    // server, and hiding a layer in the editor should never change the render.
    hiddenLayers: new Set(),
    dirty: new Set(),
    revisions: {},
    // R2 atomic trim: the GET payload, the last receipt and its undo token.
    trim: null,
    trimRevision: 0,
    undoToken: "",
    receipt: null,
    staleAspects: [],
    invalidated: 0,
    trimBusy: false,
    // Batch auto-subtitles: one route call, then one Edit patch per story.
    autoSubs: {
      running: false,
      phase: "idle",
      done: 0,
      total: 0,
      attached: 0,
      failures: 0,
      summary: "",
    },
    autoSubsScope: "story",
  };

  const dom = {};

  function renderLoading(message) {
    delete root.dataset.editorFrame;
    root.replaceChildren(el("section", { class: "st-panel" }, [
      el("p", { class: "st-eyebrow", text: "Step 3 · Edit" }),
      el("div", { class: "st-card st-edit-loading" }, [
        el("h1", { text: "Opening the editor" }),
        el("p", { class: "st-hint", text: message || "Reading this moment…" }),
      ]),
    ]));
  }

  function renderEmpty({ title, copy, action = "Go to Import", step = "import", tone = "" }) {
    delete root.dataset.editorFrame;
    const section = el("section", { class: "st-panel", "aria-labelledby": "st-edit-empty-title" }, [
      el("p", { class: "st-eyebrow", text: "Step 3 · Edit" }),
      el("div", { class: "st-empty" }, [
        el("h1", { id: "st-edit-empty-title", text: title }),
        el("p", { text: copy }),
      ]),
    ]);
    if (tone) section.querySelector(".st-empty").dataset.tone = tone;
    const button = el("button", { class: "st-btn st-btn-primary", type: "button", text: action });
    button.addEventListener("click", () => ctx.go(step));
    section.querySelector(".st-empty").append(button);
    root.replaceChildren(section);
  }

  function renderError(message) {
    delete root.dataset.editorFrame;
    const section = el("section", { class: "st-panel" }, [
      el("p", { class: "st-eyebrow", text: "Step 3 · Edit" }),
      el("div", { class: "st-empty" }, [
        el("h1", { text: "The editor could not open" }),
        el("p", { text: message || "Reload the page to try again." }),
      ]),
    ]);
    const retry = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Try again" });
    retry.addEventListener("click", () => { void boot(); });
    section.querySelector(".st-empty").append(retry);
    root.replaceChildren(section);
  }

  function renderShell() {
    root.dataset.editorFrame = "fixed";
    root.innerHTML = `
      <section class="st-panel st-edit-panel" aria-labelledby="st-edit-title">
        <h1 id="st-edit-title" class="st-visually-hidden">Edit this moment</h1>
        <header class="st-edit-toolbar" aria-label="Edit toolbar">
          <div class="st-edit-toolbar-start">
            <button id="st-edit-back" class="st-btn st-btn-ghost st-btn-small st-edit-back" type="button" aria-label="Back to Moments" title="Back to Moments">← Moments</button>
            <label class="st-field st-field-inline st-edit-moment">
              <span>Moment</span>
              <select id="st-edit-story" aria-label="Moment"></select>
            </label>
            <div class="st-aspect-group" role="group" aria-label="Moment shape">
              <button class="st-aspect" type="button" data-aspect="9:16" aria-pressed="true">9:16</button>
              <button class="st-aspect" type="button" data-aspect="4:5" aria-pressed="false">4:5</button>
              <button class="st-aspect" type="button" data-aspect="1:1" aria-pressed="false">1:1</button>
              <button class="st-aspect" type="button" data-aspect="16:9" aria-pressed="false">16:9</button>
              <button class="st-aspect" type="button" data-aspect="16:10" aria-pressed="false">16:10</button>
            </div>
            <button id="st-edit-repair" class="st-btn st-btn-small st-trim-repair" type="button" hidden>Repair shape</button>
            <div class="st-edit-history" role="group" aria-label="Undo">
              <button id="st-edit-undo-trim" class="st-btn st-btn-ghost st-btn-small" type="button" disabled>Undo trim</button>
              <button id="st-edit-undo" class="st-btn st-btn-ghost st-btn-small" type="button" disabled>Undo</button>
            </div>
          </div>
          <div class="st-edit-toolbar-end">
            <span id="st-edit-meta" class="st-hint st-edit-meta"></span>
            <span id="st-edit-save" class="st-edit-save" role="status" aria-live="polite">Opening…</span>
            <button id="st-edit-inspector-toggle" class="st-btn st-btn-ghost st-btn-small st-edit-inspector-toggle" type="button" aria-controls="st-edit-inspector" aria-expanded="false">Adjust</button>
            <button id="st-edit-next" class="st-btn st-btn-primary st-btn-small" type="button" aria-label="Next: Finish" title="Next: Finish" disabled>Finish →</button>
          </div>
        </header>
        <div id="st-edit-receipt" class="st-trim-receipt" role="status" aria-live="polite" hidden></div>
        <div id="st-edit-notice" class="st-edit-notice" role="alert" hidden></div>
        <div class="st-edit-stage">
          <aside id="st-edit-layers" class="st-layers" aria-label="Layers"></aside>
          <div id="st-edit-preview"></div>
          <div id="st-edit-timeline"></div>
          <aside id="st-edit-inspector" class="st-inspector" aria-label="Moment controls">
            <div class="st-inspector-sheet-head">
              <strong>Adjust this moment</strong>
              <button id="st-edit-inspector-close" class="st-btn st-btn-ghost st-btn-small" type="button">Done</button>
            </div>
            <div id="st-edit-inspector-body"></div>
          </aside>
        </div>
        <div id="st-edit-inspector-scrim" class="st-inspector-scrim" hidden></div>
      </section>
    `;
    dom.story = root.querySelector("#st-edit-story");
    dom.aspect = Array.from(root.querySelectorAll(".st-aspect"));
    dom.undo = root.querySelector("#st-edit-undo");
    dom.undoTrim = root.querySelector("#st-edit-undo-trim");
    dom.repair = root.querySelector("#st-edit-repair");
    dom.receipt = root.querySelector("#st-edit-receipt");
    dom.save = root.querySelector("#st-edit-save");
    dom.meta = root.querySelector("#st-edit-meta");
    dom.back = root.querySelector("#st-edit-back");
    dom.next = root.querySelector("#st-edit-next");
    dom.notice = root.querySelector("#st-edit-notice");
    dom.layers = root.querySelector("#st-edit-layers");
    dom.preview = root.querySelector("#st-edit-preview");
    dom.inspector = root.querySelector("#st-edit-inspector");
    dom.inspectorBody = root.querySelector("#st-edit-inspector-body");
    dom.inspectorToggle = root.querySelector("#st-edit-inspector-toggle");
    dom.inspectorClose = root.querySelector("#st-edit-inspector-close");
    dom.inspectorScrim = root.querySelector("#st-edit-inspector-scrim");
    dom.timeline = root.querySelector("#st-edit-timeline");

    dom.story.addEventListener("change", () => {
      if (dom.story.value === ALL_MOMENTS) {
        dom.story.value = state.story?.id || "";
        void leaveTo("moments", dom.back);
        return;
      }
      void switchStory(dom.story.value);
    });
    for (const button of dom.aspect) {
      button.addEventListener("click", () => { void switchAspect(button.dataset.aspect); });
    }
    dom.back.addEventListener("click", () => { void leaveTo("moments", dom.back); });
    dom.next.addEventListener("click", () => { void leaveTo("finish", dom.next); });
    dom.undo.addEventListener("click", () => { void undoLastChange(); });
    dom.undoTrim.addEventListener("click", () => { void undoTrimChange(); });
    dom.repair.addEventListener("click", () => { void repairAspects(); });
    dom.inspectorToggle?.addEventListener("click", () => {
      if (dom.inspector?.classList.contains("is-open")) closeInspector();
      else openInspector();
    });
    dom.inspectorClose?.addEventListener("click", closeInspector);
    dom.inspectorScrim?.addEventListener("click", closeInspector);
    document.addEventListener("keydown", onInspectorKeydown);
    document.addEventListener("keydown", onLayerKeydown);
  }

  function openInspector() {
    if (!dom.inspector) return;
    dom.inspector.classList.add("is-open");
    if (dom.inspectorScrim) dom.inspectorScrim.hidden = false;
    dom.inspectorToggle?.setAttribute("aria-expanded", "true");
    requestAnimationFrame(() => {
      dom.inspectorBody?.querySelector("[role=tab]")?.focus();
    });
  }

  function closeInspector({ restore = true } = {}) {
    if (!dom.inspector) return;
    const wasOpen = dom.inspector.classList.contains("is-open");
    dom.inspector.classList.remove("is-open");
    if (dom.inspectorScrim) dom.inspectorScrim.hidden = true;
    dom.inspectorToggle?.setAttribute("aria-expanded", "false");
    if (wasOpen && restore) dom.inspectorToggle?.focus();
  }

  function onInspectorKeydown(event) {
    if (event.key === "Escape" && dom.inspector?.classList.contains("is-open")) {
      closeInspector();
    }
  }

  function onLayerKeydown(event) {
    if (event.key !== "Delete" && event.key !== "Backspace") return;
    const target = event.target;
    if (target instanceof HTMLElement
      && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable)) {
      return;
    }
    if (!state.selected || saving) return;
    event.preventDefault();
    removeSelectedLayer();
  }

  function setSaveStatus(message, tone = "") {
    if (!dom.save) return;
    dom.save.textContent = message;
    dom.save.dataset.tone = tone;
  }

  function notify(message, tone = "") {
    if (!dom.notice) return;
    if (noticeTimer) {
      window.clearTimeout(noticeTimer);
      noticeTimer = 0;
    }
    setStatus(dom.notice, message, tone);
    if (message && tone !== "bad") {
      noticeTimer = window.setTimeout(() => {
        noticeTimer = 0;
        if (dom.notice) setStatus(dom.notice, "");
      }, 6000);
    }
  }

  function setUndoState() {
    if (dom.undo) dom.undo.disabled = saving || !state.edit?.parent;
    updateTrimChrome();
  }

  function updateTrimChrome() {
    if (dom.undoTrim) {
      dom.undoTrim.disabled = saving || state.trimBusy || !state.undoToken;
    }
    if (dom.repair) {
      const stale = state.staleAspects || [];
      dom.repair.hidden = stale.length === 0;
      dom.repair.disabled = saving || state.trimBusy;
      dom.repair.textContent = stale.length === 1
        ? `Repair ${stale[0]}`
        : `Repair ${stale.length} shapes`;
      dom.repair.title = stale.length
        ? `Rebind ${stale.join(" and ")} to the current story range.`
        : "";
    }
  }

  function setMeta() {
    if (!dom.meta) return;
    const story = state.story;
    dom.meta.textContent = story
      ? `${formatTime(state.duration)} · ${aspectLabel(state.aspect)}`
      : "";
  }

  /** Merge a trim's compact story into the full story the screen already has. */
  function mergeStory(partial) {
    if (!partial) return state.story;
    return {
      ...(state.story || {}),
      ...partial,
      sentences: partial.sentences || state.story?.sentences || [],
    };
  }

  function upsertStory(story) {
    if (!story || !state.set) return;
    const stories = (state.set.stories || []).map((item) => (
      item.id === story.id ? { ...item, ...story, sentences: item.sentences || story.sentences } : item
    ));
    state.set = { ...state.set, stories };
    state.sets = (state.sets || []).map((item) => (item.id === state.set.id ? state.set : item));
  }

  function renderReceipt() {
    if (!dom.receipt) return;
    if (!state.receipt) {
      dom.receipt.hidden = true;
      dom.receipt.replaceChildren();
      return;
    }
    const receipt = state.receipt;
    const summary = receiptSummary(receipt);
    const oldDuration = numberOr(receipt.old?.dur);
    const newDuration = numberOr(receipt.new?.dur, state.duration);
    const note = state.invalidated
      ? `${formatCount(state.invalidated, "older render")} keep${state.invalidated === 1 ? "s" : ""} the old cut.`
      : "";
    const undo = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: "Undo trim",
      disabled: saving || state.trimBusy || !state.undoToken,
    });
    undo.addEventListener("click", () => { void undoTrimChange(); });
    const dismiss = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: "Dismiss",
    });
    dismiss.addEventListener("click", () => {
      state.receipt = null;
      renderReceipt();
    });
    dom.receipt.hidden = false;
    dom.receipt.replaceChildren(
      el("div", { class: "st-trim-receipt-copy" }, [
        el("p", { class: "st-eyebrow", text: "Last trim" }),
        el("p", { class: "st-trim-receipt-line", text: summary || "The moment range changed." }),
        el("p", {
          class: "st-hint",
          text: `${formatTime(oldDuration)} → ${formatTime(newDuration)}${note ? ` · ${note}` : ""}`,
        }),
      ]),
      el("div", { class: "st-trim-receipt-actions" }, [undo, dismiss]),
    );
  }

  async function refreshStoryFromSets() {
    if (!state.job?.id) return;
    try {
      const data = await listClipSets(state.job.id);
      if (disposed) return;
      state.sets = Array.isArray(data?.clip_sets) ? data.clip_sets : state.sets;
      const set = state.sets.find((item) => item.id === state.set?.id) || state.set;
      const story = set?.stories?.find((item) => item.id === state.story?.id);
      if (set) state.set = set;
      if (story) state.story = story;
    } catch (_) {
      /* The trim result already carries enough to keep editing. */
    }
  }

  async function refreshTrimState({ authoritative = false, fresh = false } = {}) {
    if (!state.job?.id || !state.set?.id || !state.story?.id) return null;
    try {
      const trim = await getTrimState(state.job.id, state.set.id, state.story.id, { fresh });
      if (disposed) return null;
      state.trim = trim || null;
      state.trimRevision = numberOr(trim?.revision, state.trimRevision);
      state.staleAspects = Object.entries(trim?.aspects || {})
        .filter(([, value]) => value?.stale)
        .map(([aspect]) => aspect);
      if (trim?.story) {
        state.story = mergeStory(trim.story);
        upsertStory(state.story);
        if (authoritative) {
          state.duration = Math.max(0.1, numberOr(trim.story.dur, state.duration));
          state.playhead = clamp(state.playhead, 0, state.duration);
        }
      }
      if (!disposed) {
        renderStoryOptions();
        updateAspectButtons();
        updateTrimChrome();
        setMeta();
      }
      return trim;
    } catch (error) {
      if (error?.status === 404 || error?.status === 405) {
        // The trim route is not in this build; editing still works.
        state.trim = null;
        state.staleAspects = [];
        if (!disposed) updateTrimChrome();
        return null;
      }
      return null;
    }
  }

  /** The one place a TrimResult lands. Header, preview, scrubber, player and timeline read from here. */
  function applyTrimResult(result, label = "Trimmed") {
    if (!result) return;
    const story = mergeStory(result.story);
    if (story) {
      state.story = story;
      upsertStory(story);
    }
    const nextEdit = result.edits?.[state.aspect];
    if (nextEdit) state.edit = clone(nextEdit);
    const captionInfo = result.captions;
    const trackId = captionInfo?.track_id || null;
    if (state.edit && captionInfo) {
      state.edit = {
        ...state.edit,
        captions: { ...(state.edit.captions || {}), track_id: trackId },
      };
      // Never draw the old cues over the new cut while the track loads.
      if (!trackId || (state.captions?.id && state.captions.id !== trackId)) {
        state.captions = null;
      }
    }
    state.duration = Math.max(
      0.1,
      numberOr(result.duration, numberOr(result.story?.dur, state.duration)),
    );
    state.playhead = clamp(state.playhead, 0, state.duration);
    state.dirty.clear();
    state.revisions = {};
    state.receipt = result.receipt || null;
    state.undoToken = result.undo_token || state.undoToken;
    state.trimRevision = numberOr(result.revision, state.trimRevision);
    state.staleAspects = Array.isArray(result.stale_aspects) ? result.stale_aspects : [];
    state.invalidated = Array.isArray(result.invalidated_artifacts)
      ? result.invalidated_artifacts.length
      : 0;
    // Keep the pool the timeline already has, but move its window now. The
    // fresh GET below replaces the neighbours and aspect map.
    if (state.trim && result.story) {
      state.trim = {
        ...state.trim,
        revision: state.trimRevision,
        story: result.story,
      };
    }

    renderStoryOptions();
    renderEditorParts();
    populateHeader();
    renderReceipt();
    updateTrimChrome();
    const summary = receiptSummary(state.receipt);
    notify(
      summary
        ? `${label}: ${summary}. New length ${formatTime(state.duration)}.`
        : `${label}: story is now ${formatTime(state.duration)}.`,
      "ok",
    );

    void (async () => {
      const track = trackId
        ? await getCaptionTrack(state.job.id, trackId).catch(() => null)
        : null;
      await refreshStoryFromSets();
      await refreshTrimState({ fresh: true });
      if (disposed) return;
      // One render after every read: a drag started from the new header must
      // not have the handle replaced underneath it.
      if (trackId) state.captions = track;
      renderStoryOptions();
      syncPreview();
      scheduleTimeline();
      setMeta();
      updateAspectButtons();
      updateTrimChrome();
    })();
  }

  async function handleTrimConflict(error) {
    if (disposed) return;
    state.trimBusy = true;
    updateTrimChrome();
    try {
      const current = trimErrorCurrent(error);
      // A 409 writes nothing, so the shared read cache still holds the state
      // the caller saw. Drop it before reading the latest head and range.
      invalidateReadCache(state.job?.id || "");
      if (current) {
        state.trim = current;
        state.trimRevision = numberOr(current.revision, state.trimRevision);
        state.staleAspects = Object.entries(current.aspects || {})
          .filter(([, value]) => value?.stale)
          .map(([aspect]) => aspect);
        if (current.story) {
          state.story = mergeStory(current.story);
          upsertStory(state.story);
          state.duration = Math.max(0.1, numberOr(current.story.dur, state.duration));
          state.playhead = clamp(state.playhead, 0, state.duration);
        }
      }
      const reloaded = await reloadHead();
      await refreshStoryFromSets();
      await refreshTrimState({ authoritative: true, fresh: true });
      if (disposed) return;
      renderStoryOptions();
      renderEditorParts();
      populateHeader();
      renderReceipt();
      const code = trimErrorCode(error);
      const why = code === "caption_rebuild_failed"
        ? "The captions could not be rebuilt, so nothing changed."
        : "This moment changed in another window.";
      if (reloaded) {
        setSaveStatus("Latest cut open");
        notify(`${why} The latest range is open; check it and drag again.`, "bad");
      } else {
        notify(`${why} Open the moment again from Moments.`, "bad");
      }
    } catch (failure) {
      if (!disposed) {
        notify(failure?.message || "Could not reload the latest cut.", "bad");
      }
    } finally {
      state.trimBusy = false;
      if (!disposed) updateTrimChrome();
    }
  }

  async function repairAspects() {
    if (!state.job?.id || !state.set?.id || !state.story?.id || state.trimBusy) return;
    const saved = await flushSave();
    if (!saved) return;
    state.trimBusy = true;
    updateTrimChrome();
    setSaveStatus("Repairing the shape…", "busy");
    try {
      const result = await rebindStory(state.job.id, state.set.id, state.story.id, {
        expectedRevision: numberOr(state.trim?.revision, state.trimRevision),
      });
      if (disposed) return;
      state.trimBusy = false;
      applyTrimResult(result, "Shapes repaired");
      setSaveStatus("Saved", "ok");
    } catch (error) {
      if (disposed) return;
      state.trimBusy = false;
      if (error?.status === 409) {
        await handleTrimConflict(error);
      } else {
        notify(trimErrorMessage(error) || "Could not repair this shape.", "bad");
        setSaveStatus("Not repaired", "bad");
      }
    } finally {
      if (!disposed) updateTrimChrome();
    }
  }

  async function undoTrimChange() {
    if (!state.job?.id || !state.set?.id || !state.story?.id || !state.undoToken || state.trimBusy) return;
    const saved = await flushSave();
    if (!saved) return;
    state.trimBusy = true;
    updateTrimChrome();
    setSaveStatus("Undoing the trim…", "busy");
    try {
      const result = await undoTrim(state.job.id, state.set.id, state.story.id, {
        undoToken: state.undoToken,
        expectedRevision: numberOr(state.trim?.revision, state.trimRevision),
      });
      if (disposed) return;
      state.trimBusy = false;
      applyTrimResult(result, "Trim undone");
      setSaveStatus("Saved", "ok");
    } catch (error) {
      if (disposed) return;
      state.trimBusy = false;
      if (error?.status === 409) {
        await handleTrimConflict(error);
      } else {
        notify(trimErrorMessage(error) || "Could not undo the trim.", "bad");
        setSaveStatus("Not undone", "bad");
      }
    } finally {
      if (!disposed) updateTrimChrome();
    }
  }

  function trimErrorMessage(error) {
    if (!error) return "";
    if (error.status === 404 || error.status === 405) {
      return "Trimming needs the latest server. Restart VibeCut and open this moment again.";
    }
    return error.message || "";
  }

  function renderStoryOptions() {
    if (!dom.story || !state.set) return;
    dom.story.replaceChildren();
    (state.set.stories || []).forEach((story, index) => {
      dom.story.append(el("option", {
        value: story.id,
        text: storyTitle(story, index),
        selected: story.id === state.story?.id,
      }));
    });
    dom.story.append(el("option", { value: ALL_MOMENTS, text: "All moments…" }));
    dom.story.value = state.story?.id || "";
  }

  function updateAspectButtons() {
    const stale = new Set(state.staleAspects || []);
    for (const button of dom.aspect || []) {
      const aspect = button.dataset.aspect;
      const active = aspect === state.aspect;
      const needsRepair = stale.has(aspect);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.classList.toggle("is-active", active);
      button.classList.toggle("is-stale", needsRepair);
      button.dataset.stale = needsRepair ? "true" : "false";
      button.title = needsRepair
        ? "This shape's Edit was made before the moment changed. Press Repair."
        : "";
      button.setAttribute(
        "aria-label",
        `${aspect}${needsRepair ? ", needs repair" : ""}`,
      );
    }
  }

  function storyTrack(storyId = state.story?.id) {
    if (!state.job || !state.set || !storyId) return null;
    const key = `${state.set.id}:${storyId}`;
    const value = state.job.story_captions?.[key];
    if (!value) return null;
    return getCaptionTrack(state.job.id, value).catch(() => null);
  }

  function defaultLayers(fork, jobTrack) {
    if (fork) {
      return {
        clean: clone(fork.clean || []),
        reframe: clone(fork.reframe || {}),
        motion: clone(fork.motion || []),
        color: clone(fork.color || { preset: "none" }),
        graphics: clone(fork.graphics || []),
        captions: clone(fork.captions || {}),
        audio: clone(fork.audio || { mode: "original" }),
      };
    }
    return {
      clean: [],
      reframe: {},
      motion: [],
      color: { preset: "none" },
      graphics: [],
      captions: jobTrack
        ? { track_id: jobTrack.id, style_id: jobTrack.style_id, enabled: true }
        : { enabled: true },
      audio: { mode: "original" },
    };
  }

  function autoSubsStoryIds(scope) {
    const ids = (state.set?.stories || [])
      .map((story) => story.id)
      .filter(Boolean);
    if (scope === "set") return ids;
    return state.story?.id ? [state.story.id] : [];
  }

  function currentCaptionStyle() {
    return String(
      state.edit?.captions?.style_id
      || state.captions?.style_id
      || "clean",
    );
  }

  function autoSubsSummary({ attached, failures, firstError, keptStyles = 0 }) {
    const parts = [
      formatCount(attached, "track"),
      formatCount(failures, "failure"),
    ];
    if (keptStyles) parts.push(`${formatCount(keptStyles, "existing style")} kept`);
    const head = `Auto subtitles: ${parts.join(", ")}.`;
    return firstError ? `${head} First error: ${firstError}` : head;
  }

  /** Keep the current open Edit pointing at the head the batch just patched. */
  function adoptAutoCaptions(patched, fallbackCaptions) {
    if (!state.edit) return;
    const fresh = patched?.edit;
    if (fresh) {
      state.edit.id = fresh.id;
      state.edit.version = fresh.version;
      state.edit.parent = fresh.parent;
      state.edit.hash = fresh.hash;
      state.edit.created = fresh.created;
      state.edit.story_ref = fresh.story_ref || state.edit.story_ref;
      state.edit.aspect = fresh.aspect || state.edit.aspect;
      state.edit.captions = clone(fresh.captions || fallbackCaptions || {});
    } else if (fallbackCaptions) {
      state.edit.captions = clone(fallbackCaptions);
    }
    state.dirty.delete("captions");
    state.duration = storyDuration(state.story, state.edit);
    populateHeader();
    syncPreview();
    scheduleTimeline();
    setUndoState();
    setMeta();
  }

  /**
   * The batch builds every track in the requested style. When a story already
   * had a different caption style, copy the old track's full style onto the
   * new track so the creator's style choice survives.
   */
  async function keepExistingCaptionStyle(jobId, previous, trackId) {
    if (!previous?.track_id || !previous.style_id) return false;
    const old = await getCaptionTrack(jobId, previous.track_id).catch(() => null);
    const style = old?.style
      ? { ...clone(old.style), id: old.style.id || previous.style_id }
      : captionPreset(previous.style_id);
    await patchCaptionTrack(jobId, trackId, { style });
    return true;
  }

  /** Read or create one story's Edit, then point its captions at the new track. */
  async function attachAutoSubtitleTrack(row, requestedStyle, { jobId, setId, aspect }) {
    const storyId = String(row?.story_id || "");
    const trackId = String(row?.track_id || "");
    if (!storyId || !trackId) {
      throw new Error("The batch result is missing a story or track id.");
    }
    const returnedStyle = String(row.style_id || requestedStyle || "clean");
    const current = await getCurrentEdit(jobId, setId, storyId, aspect);
    let edit = current?.edit || null;
    if (!edit) {
      const jobTrack = await storyTrack(storyId);
      const layers = defaultLayers(null, jobTrack);
      const created = await createEdit(jobId, {
        set_id: setId,
        story_id: storyId,
        aspect,
        ...layers,
      });
      if (!created?.edit) throw new Error("The server did not return the new edit.");
      edit = created.edit;
    }

    const previous = edit.captions || {};
    const hadTrack = Boolean(previous.track_id);
    const hadStyle = Boolean(previous.style_id);
    const resolvedStyle = hadStyle ? previous.style_id : returnedStyle;
    if (hadStyle && previous.style_id !== returnedStyle) {
      try {
        await keepExistingCaptionStyle(jobId, previous, trackId);
      } catch (_) {
        /* Attaching the track matters more than a restyle; keep the edit ref. */
      }
    }

    const captions = {
      ...previous,
      track_id: trackId,
      style_id: resolvedStyle,
      enabled: true,
    };
    const patched = await patchEdit(jobId, edit.id, { captions });
    if (state.story?.id === storyId && state.aspect === aspect) {
      adoptAutoCaptions(patched, captions);
      const track = await getCaptionTrack(jobId, trackId).catch(() => null);
      if (!disposed) {
        state.captions = track;
        syncPreview();
        scheduleTimeline();
      }
    }
    return { attached: true, keptStyle: hadTrack && hadStyle };
  }

  async function runAutoSubtitles(scope = "story") {
    if (state.autoSubs.running) return false;
    if (!state.job?.id || !state.set?.id || !state.story?.id) {
      notify("Open a moment before building captions.", "bad");
      return false;
    }
    const storyIds = autoSubsStoryIds(scope);
    if (!storyIds.length) {
      notify("This set has no moments to caption.", "bad");
      return false;
    }
    const saved = await flushSave();
    if (!saved) return false;

    const jobId = state.job.id;
    const setId = state.set.id;
    const aspect = state.aspect;
    const styleId = currentCaptionStyle();
    state.autoSubsScope = scope === "set" ? "set" : "story";
    state.autoSubs = {
      running: true,
      phase: "building",
      done: 0,
      total: storyIds.length,
      attached: 0,
      failures: 0,
      summary: "",
    };
    renderAutoSubs();
    setSaveStatus("Building captions…", "busy");

    try {
      const result = await autoSubtitles(jobId, {
        setId,
        aspect,
        styleId,
        storyIds,
      });
      if (disposed) return false;
      const rows = Array.isArray(result?.tracks) ? result.tracks : [];
      const failed = Array.isArray(result?.failed) ? result.failed.slice() : [];
      state.autoSubs = {
        ...state.autoSubs,
        phase: "attaching",
        total: rows.length,
        done: 0,
      };
      renderAutoSubs();

      let attached = 0;
      let keptStyles = 0;
      for (const row of rows) {
        if (disposed) return false;
        try {
          const outcome = await attachAutoSubtitleTrack(row, styleId, {
            jobId,
            setId,
            aspect,
          });
          if (outcome.attached) attached += 1;
          if (outcome.keptStyle) keptStyles += 1;
        } catch (error) {
          failed.push({
            story_id: row?.story_id || "",
            error: error?.message || "Could not attach the caption track.",
          });
        }
        state.autoSubs = { ...state.autoSubs, done: state.autoSubs.done + 1 };
        renderAutoSubs();
      }

      const summary = autoSubsSummary({
        attached,
        failures: failed.length,
        firstError: failed[0]?.error || "",
        keptStyles,
      });
      state.autoSubs = {
        ...state.autoSubs,
        running: false,
        phase: "done",
        attached,
        failures: failed.length,
        summary,
      };
      if (disposed) return true;
      setSaveStatus(
        failed.length ? "Auto subtitles partly done" : "Saved",
        failed.length ? "bad" : "ok",
      );
      notify(summary, failed.length ? "bad" : "ok");
      renderAutoSubs();
      return true;
    } catch (error) {
      if (!disposed) {
        const summary = autoSubsSummary({
          attached: 0,
          failures: 1,
          firstError: error?.message || "Could not build the caption tracks.",
        });
        state.autoSubs = {
          ...state.autoSubs,
          running: false,
          phase: "done",
          attached: 0,
          failures: 1,
          summary,
        };
        setSaveStatus("Captions not built", "bad");
        notify(summary, "bad");
        renderAutoSubs();
      }
      return false;
    }
  }

  function renderAutoSubs() {
    if (disposed) return;
    renderInspector();
  }

  async function resolveCaptionTrack(edit) {
    const trackId = edit?.captions?.track_id;
    if (!trackId) {
      state.captions = null;
      return null;
    }
    const track = await getCaptionTrack(state.job.id, trackId);
    state.captions = track;
    if (!track) {
      edit.captions = { ...(edit.captions || {}), track_id: null, style_id: null };
      touch("captions");
    }
    return track;
  }

  function syncPreview() {
    if (!preview || !state.edit) return;
    preview.setData({
      aspect: state.aspect,
      edit: state.edit,
      captions: state.captions,
      duration: state.duration,
      selected: state.selected,
      jobId: state.job?.id || "",
      job: state.job,
      story: state.story,
      hiddenLayers: state.hiddenLayers,
    });
  }

  function syncTimeline() {
    if (!timeline || !state.edit) return;
    timeline.setData({
      edit: state.edit,
      captions: state.captions,
      story: state.story,
      duration: state.duration,
      aspect: state.aspect,
      trim: state.trim,
      setId: state.set?.id || "",
      jobId: state.job?.id || "",
    });
    timeline.setTime(state.playhead);
    timeline.setSelected(state.selected);
  }

  function scheduleTimeline() {
    if (!timeline || timelineRaf) return;
    timelineRaf = window.requestAnimationFrame(() => {
      timelineRaf = 0;
      syncTimeline();
    });
  }

  function renderInspector() {
    if (!dom.inspectorBody) return;
    const panelCtx = {
      getEdit: () => state.edit,
      getCaptions: () => state.captions,
      getStory: () => state.story,
      getDuration: () => state.duration,
      getPlayhead: () => state.playhead,
      getSelectedId: (kind) => (state.selected?.kind === kind ? state.selected.id : ""),
      // Hooks carry the R2 `story_start` pin only once the trim route exists,
      // so an older server keeps accepting the layout anchor.
      trimReady: () => Boolean(state.trim),
      select: (kind, id) => selectLayer(kind, id),
      setTab: (tab) => setActiveTab(tab),
      refresh: () => {
        renderLayers();
        renderInspector();
      },
      seek: (time) => seek(time),
      notify,
      getAutoSubtitles: () => state.autoSubs,
      getAutoSubtitlesScope: () => state.autoSubsScope,
      setAutoSubtitlesScope: (scope) => {
        state.autoSubsScope = scope === "set" ? "set" : "story";
      },
      autoSubtitlesStoryCount: () => (state.set?.stories || []).length,
      canAutoSubtitles: () => Boolean(state.job?.id && state.set?.id && state.story?.id),
      autoSubtitles: (scope) => runAutoSubtitles(scope),
      setGraphics(next) {
        if (!state.edit) return;
        state.edit.graphics = clone(next);
        touch("graphics");
        scheduleTimeline();
      },
      setColor(next) {
        if (!state.edit) return;
        state.edit.color = clone(next);
        touch("color");
        scheduleTimeline();
        preview?.refresh();
      },
      setClean(next) {
        if (!state.edit) return;
        state.edit.clean = clone(next);
        touch("clean");
        scheduleTimeline();
      },
      setMotion(next) {
        if (!state.edit) return;
        state.edit.motion = clone(next);
        touch("motion");
        scheduleTimeline();
      },
      setCaptionsEnabled(value) {
        if (!state.edit) return;
        state.edit.captions = { ...(state.edit.captions || {}), enabled: Boolean(value) };
        touch("captions");
      },
      async buildCaptions(styleId) {
        if (!state.job || !state.set || !state.story) return false;
        try {
          setSaveStatus("Building captions…", "busy");
          const result = await buildCaptionTrack(state.job.id, {
            setId: state.set.id,
            storyId: state.story.id,
            styleId,
          });
          const track = result?.track || result;
          if (!track?.id) throw new Error("The caption track came back empty.");
          state.captions = track;
          state.edit.captions = {
            ...(state.edit.captions || {}),
            track_id: track.id,
            style_id: track.style_id || "clean",
            enabled: true,
          };
          touch("captions");
          const saved = await saveNow();
          if (!disposed) {
            renderInspector();
            syncPreview();
            scheduleTimeline();
            if (saved) notify(`Built ${formatCount(track.cues?.length || 0, "caption line")}.`, "ok");
          }
          return Boolean(saved);
        } catch (error) {
          if (!disposed) {
            setSaveStatus("Captions not built", "bad");
            notify(error?.message || "Could not build captions for this story.", "bad");
          }
          return false;
        }
      },
      async applyCaptionTrack(payload) {
        if (!state.captions?.id) return false;
        try {
          const result = await patchCaptionTrack(state.job.id, state.captions.id, payload);
          const track = result?.track || result;
          if (!track?.id) throw new Error("The caption track came back empty.");
          state.captions = track;
          state.edit.captions = {
            ...(state.edit.captions || {}),
            track_id: track.id,
            style_id: track.style_id || "clean",
          };
          touch("captions");
          const saved = await saveNow();
          if (!disposed) {
            renderInspector();
            syncPreview();
            scheduleTimeline();
          }
          if (saved) notify("Caption changes saved.", "ok");
          return Boolean(saved);
        } catch (error) {
          if (!disposed) {
            notify(error?.message || "Could not save the caption changes.", "bad");
            setSaveStatus("Captions not saved", "bad");
          }
          return false;
        }
      },
    };
    mountInspector(dom.inspectorBody, {
      active: state.activeTab,
      edit: state.edit,
      captions: state.captions,
      panelCtx,
    });
  }

  function layerCrop() {
    return cropAt({
      edit: state.edit,
      job: state.job,
      story: state.story,
      time: state.playhead,
      aspect: state.aspect,
    });
  }

  function layerHiddenKey(kind, id) {
    return `${kind}:${id}`;
  }

  function renderLayers() {
    if (!dom.layers || !state.edit) return;
    renderLayersPanel(dom.layers, {
      getEdit: () => state.edit,
      getCaptions: () => state.captions,
      getSelected: () => state.selected,
      getCrop: layerCrop,
      isHidden: (kind, id) => state.hiddenLayers.has(layerHiddenKey(kind, id)),
      select: (kind, id) => selectLayer(kind, id),
      add: (kind) => addLayer(kind),
      toggleHidden: (kind, id) => toggleLayerHidden(kind, id),
      remove: (kind, id) => removeLayer(kind, id),
    });
  }

  function addCleanBox(box = null) {
    if (!state.edit) return;
    const layers = (state.edit.clean || []).slice();
    const layer = manualLayer(layers.length, box);
    layers.push(layer);
    state.edit.clean = layers;
    touch("clean");
    selectLayer("clean", layer.id);
    scheduleTimeline();
  }

  function addLayer(kind) {
    if (!state.edit) return;
    if (kind === "clean") {
      addCleanBox();
      notify("Remove-text box added. Drag it on the picture or use Exact position.", "ok");
      return;
    }
    if (kind === "text") {
      const graphics = (state.edit.graphics || []).slice();
      const layer = newTextLayer("lower_third", {
        duration: state.duration,
        playhead: state.playhead,
        index: graphics.length,
      });
      graphics.push(layer);
      state.edit.graphics = graphics;
      touch("graphics");
      selectLayer("text", layer.id);
      scheduleTimeline();
      notify("Text layer added at the playhead.", "ok");
      return;
    }
    setActiveTab(kind);
  }

  function updateCleanBox(id, box, { commit = false } = {}) {
    if (!state.edit || !id) return;
    const layer = (state.edit.clean || []).find((item) => item.id === id);
    if (!layer) return;
    const x = round(clamp(numberOr(box?.x), 0, 1), 4);
    const y = round(clamp(numberOr(box?.y), 0, 1), 4);
    layer.box = {
      x,
      y,
      w: round(clamp(numberOr(box?.w, 0.004), 0.004, 1 - x), 4),
      h: round(clamp(numberOr(box?.h, 0.004), 0.004, 1 - y), 4),
    };
    if (commit) {
      touch("clean");
      renderLayers();
    }
  }

  function createCleanBox(box) {
    addCleanBox(box);
    notify("Remove-text box drawn.", "ok");
  }

  function toggleLayerHidden(kind, id) {
    if (!id) return;
    const key = layerHiddenKey(kind, id);
    if (state.hiddenLayers.has(key)) state.hiddenLayers.delete(key);
    else state.hiddenLayers.add(key);
    preview?.setHiddenLayers(state.hiddenLayers);
    renderLayers();
  }

  function removeLayer(kind, id) {
    if (!state.edit || !id) return;
    let removed = false;
    if (kind === "clean") {
      const layers = state.edit.clean || [];
      const next = layers.filter((layer) => layer.id !== id);
      removed = next.length !== layers.length;
      if (removed) {
        state.edit.clean = next;
        touch("clean");
      }
    } else if (kind === "text" || kind === "effects") {
      const graphics = state.edit.graphics || [];
      const next = graphics.filter((layer) => layer.id !== id);
      removed = next.length !== graphics.length;
      if (removed) {
        state.edit.graphics = next;
        touch("graphics");
      }
      if (!removed && kind === "effects") {
        const motion = state.edit.motion || [];
        const nextMotion = motion.filter((layer) => layer.id !== id);
        removed = nextMotion.length !== motion.length;
        if (removed) {
          state.edit.motion = nextMotion;
          touch("motion");
        }
      }
    } else if (kind === "color") {
      state.edit.color = { ...(state.edit.color || {}), preset: "none" };
      touch("color");
      removed = true;
    } else if (kind === "audio") {
      state.edit.audio = { ...(state.edit.audio || {}), mode: "original" };
      touch("audio");
      removed = true;
    }
    if (!removed) {
      notify("Open the Captions panel to remove this caption line.", "");
      setActiveTab(kind);
      return;
    }
    if (state.selected?.kind === kind && state.selected?.id === id) {
      state.selected = null;
      preview?.setSelected(null);
      timeline?.setSelected(null);
    }
    renderLayers();
    renderInspector();
    scheduleTimeline();
    preview?.refresh();
    notify("Layer removed.", "ok");
  }

  function removeSelectedLayer() {
    if (!state.selected) return;
    removeLayer(state.selected.kind, state.selected.id);
  }

  function selectLayer(kind, id) {
    const tab = kind === "sentences" ? state.activeTab : kind;
    if (tab) state.activeTab = tab;
    if (kind === "sentences") return;
    state.selected = id ? { kind, id } : null;
    preview?.setSelected(
      ["clean", "text", "captions"].includes(kind) ? state.selected : null,
    );
    timeline?.setSelected(state.selected);
    renderLayers();
    renderInspector();
  }

  function setActiveTab(tab) {
    if (!["clean", "text", "captions", "effects", "color", "audio"].includes(tab)) return;
    state.activeTab = tab;
    renderInspector();
  }

  function touch(field) {
    if (!LAYER_FIELDS.includes(field)) return;
    state.revisions[field] = (state.revisions[field] || 0) + 1;
    state.dirty.add(field);
    setSaveStatus("Unsaved changes", "dirty");
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => { void saveNow(); }, 450);
    scheduleTimeline();
  }

  function applySaved(saved, fields, revisions) {
    const previousId = state.edit.id;
    state.edit.id = saved.id;
    state.edit.version = saved.version;
    state.edit.parent = saved.parent;
    state.edit.hash = saved.hash;
    state.edit.created = saved.created;
    state.edit.story_ref = saved.story_ref || state.edit.story_ref;
    state.edit.aspect = saved.aspect || state.edit.aspect;
    for (const field of fields) {
      if ((state.revisions[field] || 0) === revisions[field]) {
        state.edit[field] = clone(saved[field]);
      }
    }
    state.duration = storyDuration(state.story, state.edit);
    if (!state.dirty.size) setSaveStatus("Saved", "ok");
    if (!disposed) {
      syncPreview();
      syncTimeline();
      setUndoState();
      setMeta();
    }
    return previousId !== saved.id;
  }

  async function reloadHead() {
    const current = await getCurrentEdit(state.job.id, state.set.id, state.story.id, state.aspect);
    if (!current) {
      notify("This moment has no edit now. Open Moments and choose it again.", "bad");
      return false;
    }
    const fresh = current.edit;
    const keep = new Set(state.dirty);
    for (const field of LAYER_FIELDS) {
      if (!keep.has(field)) state.edit[field] = clone(fresh[field]);
    }
    Object.assign(state.edit, {
      id: fresh.id,
      version: fresh.version,
      parent: fresh.parent,
      hash: fresh.hash,
      created: fresh.created,
      story_ref: fresh.story_ref,
      aspect: fresh.aspect,
    });
    if (!keep.has("captions")) await resolveCaptionTrack(state.edit);
    state.duration = storyDuration(state.story, state.edit);
    syncPreview();
    syncTimeline();
    setUndoState();
    setMeta();
    return true;
  }

  function saveNow() {
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = 0;
    }
    if (!state.edit || !state.dirty.size) return Promise.resolve(true);
    if (saving) return savePromise || Promise.resolve(true);

    saving = true;
    setUndoState();
    setSaveStatus("Saving…", "busy");

    let wrapped = null;
    const run = (async () => {
      let failed = null;
      let retried = false;
      try {
        while (state.dirty.size) {
          const fields = Array.from(state.dirty);
          state.dirty.clear();
          const body = {};
          const revisions = {};
          for (const field of fields) {
            body[field] = clone(state.edit[field]);
            revisions[field] = state.revisions[field] || 0;
          }
          // Autosaves within a few seconds fold into one version on the server.
          body.coalesce = true;
          try {
            const result = await patchEdit(state.job.id, state.edit.id, body, { keepalive: unloading });
            if (disposed) return true;
            if (!result?.edit) throw new Error("The server did not return the saved edit.");
            applySaved(result.edit, fields, revisions);
            if (!state.dirty.size) setSaveStatus("Saved", "ok");
          } catch (error) {
            if (disposed) return true;
            if (error?.status === 409 && !retried) {
              retried = true;
              for (const field of fields) state.dirty.add(field);
              const reloaded = await reloadHead();
              if (!reloaded) {
                failed = error;
                break;
              }
              await refreshTrimState({ authoritative: true, fresh: true });
              if (!disposed) {
                renderEditorParts();
                populateHeader();
              }
              continue;
            }
            for (const field of fields) state.dirty.add(field);
            failed = error;
            break;
          }
        }
      } catch (error) {
        failed = error;
      }

      if (failed) {
        const stale = failed.status === 409;
        setSaveStatus(stale ? "Changed in another window" : "Not saved", "bad");
        notify(
          stale
            ? "This moment changed in another window. The latest save is open; check it and try again."
            : (failed.message || "Could not save this change."),
          "bad",
        );
        return false;
      }
      if (state.dirty.size) {
        setSaveStatus("Saving…", "busy");
        saveTimer = window.setTimeout(() => { void saveNow(); }, 450);
      } else if (dom.notice && dom.notice.dataset.tone === "bad") {
        setSaveStatus("Saved", "ok");
      }
      return true;
    })();

    wrapped = run.finally(() => {
      saving = false;
      if (savePromise === wrapped) savePromise = null;
      setUndoState();
    });
    savePromise = wrapped;
    return wrapped;
  }

  async function flushSave() {
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = 0;
    }
    if (saving && savePromise) await savePromise.catch(() => {});
    if (state.dirty.size) return saveNow();
    return true;
  }

  /** Leave Edit only after the autosave lands; a failed save keeps the user here. */
  async function leaveTo(step, button = null) {
    if (disposed) return;
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    }
    try {
      const saved = await flushSave();
      if (!saved) {
        setSaveStatus("Not saved — staying here", "bad");
        notify(
          "This change is not saved yet. Stay on this screen and try again; leaving would drop it.",
          "bad",
        );
        return;
      }
      setSaveStatus("Saved", "ok");
      ctx.go(step);
    } finally {
      if (button?.isConnected) {
        button.disabled = step === "finish" && !state.edit;
        button.removeAttribute("aria-busy");
      }
    }
  }

  async function loadStory({ forkFrom = null } = {}) {
    const seq = ++loadSeq;
    if (!state.job || !state.set || !state.story) return;
    state.selected = null;
    state.hiddenLayers.clear();
    state.playhead = Math.min(state.playhead, Math.max(0.1, state.duration));
    setSaveStatus("Opening moment…", "busy");
    notify("");
    if (dom.inspectorBody) {
      dom.inspectorBody.replaceChildren(el("p", { class: "st-hint", text: "Opening moment…" }));
    }

    try {
      let current = await getCurrentEdit(
        state.job.id, state.set.id, state.story.id, state.aspect,
      );
      if (disposed || seq !== loadSeq) return;
      let edit = current?.edit || null;

      if (!edit) {
        let fork = forkFrom;
        if (!fork && state.aspect === "4:5") {
          const other = await getCurrentEdit(
            state.job.id, state.set.id, state.story.id, "9:16",
          );
          fork = other?.edit || null;
        }
        const jobTrack = await storyTrack();
        if (disposed || seq !== loadSeq) return;
        const layers = defaultLayers(fork, jobTrack);
        const result = await createEdit(state.job.id, {
          set_id: state.set.id,
          story_id: state.story.id,
          aspect: state.aspect,
          ...layers,
        });
        if (disposed || seq !== loadSeq) return;
        if (!result?.edit) throw new Error("The server did not return the new edit.");
        edit = result.edit;
      }

      state.edit = edit;
      // The trim route's story `dur` is the same number the server will
      // render. Use it as the one duration source when it is present.
      const trim = await refreshTrimState({ authoritative: true, fresh: true });
      state.duration = Math.max(
        0.1,
        numberOr(trim?.story?.dur, storyDuration(state.story, edit)),
      );
      state.playhead = clamp(state.playhead, 0, state.duration);
      await resolveCaptionTrack(edit);
      if (!edit.captions?.track_id) {
        const jobTrack = await storyTrack();
        if (disposed || seq !== loadSeq) return;
        if (jobTrack) {
          state.captions = jobTrack;
          edit.captions = {
            ...(edit.captions || {}),
            track_id: jobTrack.id,
            style_id: jobTrack.style_id || "clean",
            enabled: edit.captions?.enabled !== false,
          };
          touch("captions");
        }
      }
      if (disposed || seq !== loadSeq) return;

      renderEditorParts();
      populateHeader();
      writeChoice({ setId: state.set.id, storyId: state.story.id, aspect: state.aspect });
      setSaveStatus(state.dirty.size ? "Unsaved changes" : "Saved", state.dirty.size ? "dirty" : "ok");
      if (state.dirty.size) {
        saveTimer = window.setTimeout(() => { void saveNow(); }, 300);
      }
    } catch (error) {
      if (disposed || seq !== loadSeq) return;
      setSaveStatus("Could not open", "bad");
      notify(
        error?.status === 409
          ? "This moment changed since it was cut. Open Moments and build it again."
          : (error?.message || "Could not open this moment."),
        "bad",
      );
      if (state.edit) {
        renderEditorParts();
        populateHeader();
      } else {
        renderError(error?.message || "Could not open this moment.");
      }
    }
  }

  function populateHeader() {
    renderStoryOptions();
    updateAspectButtons();
    setMeta();
    setUndoState();
    renderReceipt();
    updateTrimChrome();
    if (dom.next) dom.next.disabled = !state.edit;
  }

  function renderEditorParts() {
    if (!dom.preview || !dom.timeline) return;
    if (!preview) {
      preview = mountPreview(dom.preview, {
        jobId: state.job.id,
        onTime: (time) => {
          state.playhead = time;
          timeline?.setTime(time);
        },
        onStale: () => { void handleStalePreview(); },
        onSelect: (kind, id) => selectLayer(kind, id),
        onBoxChange: (id, box, options) => updateCleanBox(id, box, options),
        onBoxCreate: (box) => createCleanBox(box),
      });
    }
    if (!timeline) {
      timeline = mountTimeline(dom.timeline, {
        jobId: state.job.id,
        onSeek: (time) => seek(time),
        onSelect: (kind, id) => selectLayer(kind, id),
        onAdd: (kind) => addLayer(kind),
        beforeTrim: () => flushSave(),
        onTrim: (result) => applyTrimResult(result, "Trimmed"),
        onConflict: (error) => { void handleTrimConflict(error); },
      });
    }
    preview.setData({
      aspect: state.aspect,
      edit: state.edit,
      captions: state.captions,
      duration: state.duration,
      selected: state.selected,
      jobId: state.job.id,
    });
    preview.setTime(state.playhead);
    timeline.setData({
      edit: state.edit,
      captions: state.captions,
      story: state.story,
      duration: state.duration,
      aspect: state.aspect,
      trim: state.trim,
      setId: state.set?.id || "",
      jobId: state.job.id,
    });
    timeline.setTime(state.playhead);
    timeline.setSelected(state.selected);
    renderLayers();
    renderInspector();
  }

  function seek(time) {
    state.playhead = clamp(numberOr(time), 0, Math.max(0.1, state.duration));
    preview?.seek(state.playhead);
    timeline?.setTime(state.playhead);
  }

  async function handleStalePreview() {
    if (staleReload || disposed) return;
    staleReload = true;
    try {
      if (state.dirty.size) await saveNow();
      else await reloadHead();
      await refreshTrimState({ authoritative: true, fresh: true });
      if (!disposed) {
        renderEditorParts();
        populateHeader();
        notify("This moment changed in another window. The latest save is open.", "bad");
      }
    } catch (error) {
      if (!disposed) notify(error?.message || "Could not reload the latest cut.", "bad");
    } finally {
      staleReload = false;
    }
  }

  async function switchStory(storyId) {
    if (!state.set || !storyId || storyId === state.story?.id) return;
    const next = (state.set.stories || []).find((story) => story.id === storyId);
    if (!next) return;
    const saved = await flushSave();
    if (!saved) {
      dom.story.value = state.story?.id || "";
      return;
    }
    state.story = next;
    state.playhead = 0;
    state.trim = null;
    state.trimRevision = 0;
    state.undoToken = "";
    state.receipt = null;
    state.staleAspects = [];
    state.invalidated = 0;
    await loadStory();
  }

  async function switchAspect(aspect) {
    const next = ASPECTS.includes(aspect) ? aspect : "9:16";
    if (next === state.aspect) return;
    const saved = await flushSave();
    if (!saved) return;
    const forkFrom = next === "4:5" && state.aspect === "9:16" ? state.edit : null;
    const previous = state.aspect;
    state.aspect = next;
    state.playhead = 0;
    updateAspectButtons();
    await loadStory({ forkFrom });
    if (!state.edit || state.edit.aspect !== next) {
      state.aspect = previous;
      updateAspectButtons();
    }
  }

  async function undoLastChange() {
    if (!state.edit?.parent || disposed) return;
    const saved = await flushSave();
    if (!saved) return;
    dom.undo.disabled = true;
    try {
      const result = await undoEdit(state.job.id, state.edit.id);
      if (disposed || !result?.edit) return;
      state.edit = result.edit;
      state.duration = storyDuration(state.story, state.edit);
      state.selected = null;
      state.dirty.clear();
      await resolveCaptionTrack(state.edit);
      await refreshTrimState();
      if (disposed) return;
      renderEditorParts();
      populateHeader();
      setSaveStatus("Undid the last change", "ok");
      notify("Undid the last change.", "ok");
    } catch (error) {
      if (disposed) return;
      if (error?.status === 409) {
        const reloaded = await reloadHead();
        notify(
          reloaded
            ? "This moment changed in another window. The latest save is open."
            : "This moment changed in another window. Open it again from Moments.",
          "bad",
        );
      } else {
        notify(error?.message || "Could not undo the last change.", "bad");
      }
    } finally {
      if (!disposed) setUndoState();
    }
  }

  async function boot() {
    const jobId = ctx.getJobId();
    if (!jobId) {
      renderEmpty({
        title: "Open a video first",
        copy: "The editor works on one moment at a time. Import a video, then pick its moments.",
      });
      return;
    }
    renderLoading("Reading the video and its moment picks…");
    const seq = ++loadSeq;
    try {
      const [job, result] = await Promise.all([getJob(jobId), listClipSets(jobId)]);
      if (disposed || seq !== loadSeq) return;
      state.job = job;
      state.sets = Array.isArray(result?.clip_sets) ? result.clip_sets : [];
      if (job.status !== "ready") {
        renderEmpty({
          title: job.status === "failed" ? "This video could not be read" : "This video is still being read",
          copy: job.error || "Wait for the read to finish, then open Edit.",
          action: "Open Moments",
          step: "moments",
        });
        return;
      }
      const usable = state.sets.filter((set) => Array.isArray(set.stories) && set.stories.length);
      if (!usable.length) {
        renderEmpty({
          title: "Pick moments first",
          copy: "Edit needs a moment. Open Moments, choose or add one, then come back.",
          action: "Open Moments",
          step: "moments",
        });
        return;
      }
      const choice = readChoice();
      state.set = usable.find((set) => set.id === choice.setId) || usable[0];
      const choices = state.set.stories || [];
      state.story = choices.find((story) => story.id === choice.storyId) || choices[0];
      state.aspect = ASPECTS.includes(choice.aspect) ? choice.aspect : "9:16";
      renderShell();
      renderStoryOptions();
      updateAspectButtons();
      await loadStory();
    } catch (error) {
      if (disposed || seq !== loadSeq) return;
      if (error?.status === 404) {
        renderEmpty({
          title: "This video is no longer on file",
          copy: "Choose another video from Import.",
          action: "Go to Import",
        });
      } else {
        renderError(error?.message || "Reload the page to try again.");
      }
    }
  }

  function onBeforeUnload(event) {
    if (!state.dirty.size && !saving) return;
    event.preventDefault();
    event.returnValue = "";
  }

  function onVisibilityChange() {
    if (document.visibilityState === "hidden" && state.dirty.size) void flushSave();
  }

  // A reload inside the 450 ms debounce used to drop the last edit. Flush
  // with a keepalive request so the save survives the page going away.
  function onPageHide() {
    unloading = true;
    if (state.dirty.size || saveTimer) void flushSave();
  }

  window.addEventListener("beforeunload", onBeforeUnload);
  window.addEventListener("pagehide", onPageHide);
  document.addEventListener("visibilitychange", onVisibilityChange);
  void boot();

  return () => {
    disposed = true;
    if (saveTimer) window.clearTimeout(saveTimer);
    if (noticeTimer) window.clearTimeout(noticeTimer);
    if (timelineRaf) window.cancelAnimationFrame(timelineRaf);
    if (state.dirty.size) void saveNow();
    preview?.destroy();
    timeline?.destroy();
    window.removeEventListener("beforeunload", onBeforeUnload);
    window.removeEventListener("pagehide", onPageHide);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    document.removeEventListener("keydown", onInspectorKeydown);
    document.removeEventListener("keydown", onLayerKeydown);
    delete root.dataset.editorFrame;
    root.replaceChildren();
  };
}
