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
  listJobs,
  rebindStory,
  request,
  trimErrorCode,
  trimErrorCurrent,
  undoTrim,
} from "../api.js";
import { el, formatCount, setStatus } from "../ui.js";
import { receiptSummary } from "../stories.js";
import { mountPreview } from "./preview.js";
import { mountTimeline } from "./timeline.js";
import { mountLayersPanel } from "./layers-panel.js";
import { mountElementsPanel } from "./elements-panel.js";
import { cropAt } from "./canvas-tools.js";
import { icon } from "./icons.js";
import { manualLayer, setLayerKind } from "./layers/clean.js";
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
  restoreEdit,
  syncMediaCookie,
  undoEdit,
} from "./api.js";

const CSS_ID = "vibecut-studio-edit-css";
const CHOICE_KEY = "vibecut.studio.edit.choice";
const LAYER_FIELDS = ["sequence", "clean", "reframe", "motion", "color", "graphics", "captions", "audio", "border", "output", "assets"];

function ensureStyles() {
  if (!document.getElementById(CSS_ID)) {
    const link = document.createElement("link");
    link.id = CSS_ID;
    link.rel = "stylesheet";
    link.href = "/static/studio/edit/edit.css?v=20261103-11";
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
    activeTab: "moments",
    activeLayer: "clean",
    loop: false,
    output: { resolution: "1080p", fps: 30 },
    selected: null,
    // Preview-only hide toggles. Clean layers have no `hidden` field on the
    // server, and hiding a layer in the editor should never change the render.
    hiddenLayers: new Set(),
    // Check tracklets shown on the preview before they become Clean layers.
    foundText: [],
    dirty: new Set(),
    revisions: {},
    // R2 atomic trim: the GET payload, the last receipt and its undo token.
    trim: null,
    trimRevision: 0,
    undoToken: "",
    // Version ids undone in this session, newest last. Any new change clears
    // them, so Redo never jumps across a different edit path.
    redoIds: [],
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
  let momentScenesOpen = false;

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
        <header class="st-edit-toolbar st-edit-command" aria-label="Edit commands">
          <div class="st-edit-command-start">
            <button id="st-edit-back" class="st-btn st-btn-ghost st-btn-small st-edit-back" type="button" aria-label="Back to Moments" title="Back to Moments">← Moments</button>
            <div class="st-moment-picker">
              <button id="st-edit-moment-btn" class="st-moment-btn" type="button" aria-haspopup="menu" aria-expanded="false" title="Switch moment">
                <span id="st-edit-moment-num" class="st-mono">01</span>
                <span class="st-moment-caret" aria-hidden="true">▾</span>
              </button>
              <div id="st-edit-moment-menu" class="st-moment-menu" role="menu" hidden></div>
            </div>
          </div>
          <nav class="st-mobile-panels" aria-label="Editor panels">
            <button type="button" data-panel="elements" title="Elements" aria-label="Elements"></button>
            <button type="button" data-panel="preview" class="is-active" title="Preview" aria-label="Preview"></button>
            <button type="button" data-panel="layers" title="Layers" aria-label="Layers"></button>
          </nav>
          <div class="st-edit-command-end">
            <button id="st-edit-repair" class="st-btn st-btn-ghost st-btn-small st-trim-repair" type="button" hidden>Repair shape</button>
            <span id="st-edit-meta" class="st-visually-hidden"></span>
            <button id="st-edit-next" class="st-btn st-btn-primary st-btn-small" type="button" aria-label="Next: Finish" title="Next: Finish" disabled>Finish →</button>
          </div>
        </header>
        <div id="st-edit-receipt" class="st-trim-receipt" role="status" aria-live="polite" hidden></div>
        <div id="st-edit-notice" class="st-edit-notice" role="alert" hidden></div>
        <div class="st-edit-stage">
          <aside id="st-edit-elements" class="st-elements" aria-label="Elements"></aside>
          <div id="st-edit-preview"></div>
          <aside id="st-edit-layers" class="st-layers" aria-label="Layers"></aside>
          <div id="st-edit-timeline"></div>
        </div>
        <dialog id="st-edit-shortcuts" class="st-shortcuts" aria-labelledby="st-edit-shortcuts-title">
          <header class="st-shortcuts-head">
            <h2 id="st-edit-shortcuts-title">Keyboard shortcuts</h2>
            <button id="st-edit-shortcuts-close" class="st-icon-btn" type="button" aria-label="Close shortcuts">×</button>
          </header>
          <div class="st-shortcuts-body">
            <dl class="st-shortcuts-list">
              <div><dt>Play / pause</dt><dd><kbd>Space</kbd></dd></div>
              <div><dt>Back 1 second</dt><dd><kbd>J</kbd></dd></div>
              <div><dt>Pause</dt><dd><kbd>K</kbd></dd></div>
              <div><dt>Play</dt><dd><kbd>L</kbd></dd></div>
              <div><dt>One frame back / forward</dt><dd><kbd>←</kbd> <kbd>→</kbd></dd></div>
              <div><dt>One second back / forward</dt><dd><kbd>Shift</kbd> + <kbd>←</kbd> / <kbd>→</kbd></dd></div>
              <div><dt>Select tool</dt><dd><kbd>V</kbd></dd></div>
              <div><dt>Draw a Remove-text box</dt><dd><kbd>B</kbd></dd></div>
              <div><dt>Remove the selected layer</dt><dd><kbd>Delete</kbd></dd></div>
              <div><dt>Undo / redo</dt><dd><kbd>⌘Z</kbd> / <kbd>⇧⌘Z</kbd></dd></div>
              <div><dt>This list</dt><dd><kbd>?</kbd></dd></div>
              <div><dt>Close a panel or tool</dt><dd><kbd>Esc</kbd></dd></div>
            </dl>
            <p class="st-hint">Shortcuts work when you are not typing in a field.</p>
          </div>
        </dialog>
      </section>
    `;
    dom.momentBtn = root.querySelector("#st-edit-moment-btn");
    dom.momentMenu = root.querySelector("#st-edit-moment-menu");
    dom.momentNum = root.querySelector("#st-edit-moment-num");
    dom.repair = root.querySelector("#st-edit-repair");
    dom.receipt = root.querySelector("#st-edit-receipt");
    dom.save = document.querySelector("#st-edit-ready");
    dom.meta = root.querySelector("#st-edit-meta");
    dom.back = root.querySelector("#st-edit-back");
    dom.next = root.querySelector("#st-edit-next");
    dom.notice = root.querySelector("#st-edit-notice");
    dom.elements = root.querySelector("#st-edit-elements");
    dom.layers = root.querySelector("#st-edit-layers");
    dom.preview = root.querySelector("#st-edit-preview");
    dom.help = document.querySelector("#st-edit-shortcuts-open");
    dom.shortcuts = root.querySelector("#st-edit-shortcuts");
    dom.shortcutsClose = root.querySelector("#st-edit-shortcuts-close");
    dom.timeline = root.querySelector("#st-edit-timeline");
    dom.stage = root.querySelector(".st-edit-stage");
    dom.mobilePanels = Array.from(root.querySelectorAll(".st-mobile-panels [data-panel]"));

    if (dom.momentBtn) dom.momentBtn.prepend(icon("layers", { size: 12 }));
    if (dom.save) {
      dom.save.hidden = false;
      dom.save.textContent = "Ready";
      dom.save.dataset.tone = "quiet";
    }
    if (dom.help) dom.help.hidden = false;

    dom.momentBtn?.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = dom.momentMenu?.hidden !== false;
      if (dom.momentMenu) dom.momentMenu.hidden = !open;
      dom.momentBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (event) => {
      if (!root.querySelector(".st-moment-picker")?.contains(event.target)) {
        if (dom.momentMenu) dom.momentMenu.hidden = true;
        dom.momentBtn?.setAttribute("aria-expanded", "false");
      }
    });
    for (const button of dom.mobilePanels) {
      const iconName = button.dataset.panel === "elements" ? "layers" : button.dataset.panel === "layers" ? "settings" : "expand";
      button.append(icon(iconName, { size: 14 }));
      button.addEventListener("click", () => {
        dom.stage.dataset.panel = button.dataset.panel;
        for (const item of dom.mobilePanels) item.classList.toggle("is-active", item === button);
      });
    }
    dom.back.addEventListener("click", () => { void leaveTo("moments", dom.back); });
    dom.next.addEventListener("click", () => { void leaveTo("finish", dom.next); });
    dom.help?.addEventListener("click", openShortcuts);
    dom.shortcutsClose?.addEventListener("click", closeShortcuts);
    dom.shortcuts?.addEventListener("click", (event) => {
      if (event.target === dom.shortcuts) closeShortcuts();
    });
    dom.repair.addEventListener("click", () => { void repairAspects(); });
    document.addEventListener("keydown", onLayerKeydown);
    document.addEventListener("keydown", onEditorKeydown);

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

  function setFocusMode(on) {
    const panel = root.querySelector(".st-edit-panel");
    if (!panel) return;
    panel.dataset.focus = on ? "1" : "0";
    dom.focus?.setAttribute("aria-pressed", on ? "true" : "false");
    if (on) {
      closeInspector({ restore: false });
      preview?.refresh();
    }
  }

  function toggleFocusMode() {
    const panel = root.querySelector(".st-edit-panel");
    setFocusMode(panel?.dataset.focus !== "1");
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

  function openShortcuts() {
    if (!dom.shortcuts) return;
    if (!dom.shortcuts.open) dom.shortcuts.showModal();
    requestAnimationFrame(() => dom.shortcutsClose?.focus());
  }

  function closeShortcuts() {
    if (dom.shortcuts?.open) dom.shortcuts.close();
  }

  function onEditorKeydown(event) {
    if (dom.shortcuts?.open) return;
    const target = event.target;
    if (target instanceof HTMLElement) {
      if (target.isContentEditable
        || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) {
        return;
      }
      if ((event.key === " " || event.key === "Enter")
        && target.closest("button, a, [role=button]")) {
        return;
      }
    }
    if ((event.metaKey || event.ctrlKey) && !event.altKey) {
      const key = String(event.key || "").toLowerCase();
      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) void redoLastChange();
        else void undoLastChange();
      }
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      preview?.togglePlay();
      return;
    }
    if (event.key === "f" || event.key === "F") {
      event.preventDefault();
      preview?.toggleFocus();
      return;
    }
    if (event.key === "?" || (event.key === "/" && event.shiftKey)) {
      event.preventDefault();
      openShortcuts();
      return;
    }
    if (event.key === "j" || event.key === "J") {
      event.preventDefault();
      preview?.pause();
      seek(state.playhead - 1);
    } else if (event.key === "k" || event.key === "K") {
      event.preventDefault();
      preview?.pause();
    } else if (event.key === "l" || event.key === "L") {
      event.preventDefault();
      preview?.play();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      seek(state.playhead - (event.shiftKey ? 1 : 1 / 30));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      seek(state.playhead + (event.shiftKey ? 1 : 1 / 30));
    } else if (event.key === "Home") {
      event.preventDefault();
      seek(0);
    } else if (event.key === "End") {
      event.preventDefault();
      seek(state.duration);
    } else if (event.key === "v" || event.key === "V") {
      event.preventDefault();
      preview?.setTool("select");
    } else if (event.key === "b" || event.key === "B") {
      event.preventDefault();
      preview?.setTool("box");
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
    const text = message === "Saved" ? "Ready" : message;
    dom.save.hidden = false;
    dom.save.textContent = text;
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
    timeline?.setHistory({
      canUndo: !saving && Boolean(state.edit?.parent),
      canRedo: !saving && Boolean(state.redoIds.length),
      canUndoTrim: !saving && !state.trimBusy && Boolean(state.undoToken),
    });
    updateTrimChrome();
  }

  function updateTrimChrome() {
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
    state.redoIds = [];
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
    if (!state.set) return;
    const stories = state.set.stories || [];
    const index = Math.max(0, stories.findIndex((story) => story.id === state.story?.id));
    if (dom.momentNum) dom.momentNum.textContent = String(index + 1).padStart(2, "0");
    if (dom.momentBtn) dom.momentBtn.title = state.story ? storyTitle(state.story, index) : "Switch moment";
    if (!dom.momentMenu) return;
    dom.momentMenu.replaceChildren();
    stories.forEach((story, storyIndex) => {
      const active = story.id === state.story?.id;
      const button = el("button", {
        class: `st-moment-item${active ? " is-active" : ""}`,
        type: "button",
        role: "menuitemradio",
        "aria-checked": active ? "true" : "false",
      }, [
        el("span", { class: "st-mono", text: String(storyIndex + 1).padStart(2, "0") }),
        el("span", { class: "st-moment-item-copy" }, [
          el("strong", { text: String(story.title || story.hook?.text || `Moment ${storyIndex + 1}`).slice(0, 70) }),
          el("small", { text: formatTime(story.dur || story.duration || 0) }),
        ]),
      ]);
      button.addEventListener("click", () => {
        dom.momentMenu.hidden = true;
        dom.momentBtn?.setAttribute("aria-expanded", "false");
        if (story.id !== state.story?.id) void switchStory(story.id);
      });
      dom.momentMenu.append(button);
    });
  }

  function updateAspectButtons() {
    // Aspect now lives inside the preview. Keep the repair state on the
    // command bar only; the preview owns the ratio selector.
    const stale = new Set(state.staleAspects || []);
    if (dom.repair) {
      dom.repair.hidden = stale.length === 0;
      dom.repair.textContent = stale.length === 1 ? `Repair ${stale[0]}` : `Repair ${stale.length} shapes`;
    }
  }

  function storyTrack(storyId = state.story?.id) {
    if (!state.job || !state.set || !storyId) return null;
    const key = `${state.set.id}:${storyId}`;
    const value = state.job.story_captions?.[key];
    if (!value) return null;
    return getCaptionTrack(state.job.id, value).catch(() => null);
  }

  function defaultLayers(fork, _jobTrack) {
    if (fork) {
      return {
        sequence: clone(fork.sequence || []),
        clean: clone(fork.clean || []),
        reframe: clone(fork.reframe || {}),
        motion: clone(fork.motion || []),
        color: clone(fork.color || { preset: "none" }),
        graphics: clone(fork.graphics || []),
        captions: clone(fork.captions || {}),
        audio: clone(fork.audio || { mode: "original" }),
        border: clone(fork.border || {}),
        output: clone(fork.output || {}),
        assets: clone(fork.assets || []),
      };
    }
    return {
      sequence: [],
      clean: [],
      reframe: {},
      motion: [],
      color: { preset: "none" },
      graphics: [],
      // Captions are opt-in: a new Edit starts with no track and captions off.
      // The creator adds them from the Captions tool or Auto subtitles.
      captions: { enabled: false },
      audio: { mode: "original" },
      border: {},
      output: {},
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
    state.duration = sequenceDuration() || storyDuration(state.story, state.edit);
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
    renderLayers();
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
      foundText: state.foundText,
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


  function sequenceDuration() {
    const sequence = state.edit?.sequence || [];
    if (!sequence.length) return 0;
    return sequence.reduce((total, clip) => (
      total + Math.max(0, numberOr(clip.end) - numberOr(clip.start))
    ), 0);
  }

  function effectiveDuration() {
    return sequenceDuration() || state.duration;
  }

  function cleanClip(clip) {
    const next = {
      start: Number(clip?.start) || 0,
      end: Number(clip?.end) || 0,
      role: clip?.role || "beat",
    };
    if (clip?.kind) next.kind = String(clip.kind);
    if (clip?.kind === "file") next.asset_id = String(clip.asset_id || "");
    else if (clip?.kind !== "blank") next.scene = Number(clip?.scene);
    if (clip?.beat_kind) next.beat_kind = String(clip.beat_kind);
    if (clip?.color) next.color = String(clip.color);
    if (clip?.reverse === true) next.reverse = true;
    return next;
  }

  function currentSequence() {
    const saved = Array.isArray(state.edit?.sequence) ? state.edit.sequence : [];
    if (saved.length) return saved.map(cleanClip);
    return (state.story?.clips || []).map((clip) => cleanClip({
      scene: Number(clip.scene),
      start: Number(clip.start),
      end: Number(clip.end),
      role: clip.role || "beat",
    }));
  }

  function setSequence(sequence) {
    if (!state.edit) return;
    state.edit.sequence = sequence.map(cleanClip);
    state.duration = sequenceDuration() || state.duration;
    touch("sequence");
    renderLayers();
    renderMomentBoard();
    preview?.setData({
      aspect: state.aspect,
      edit: state.edit,
      captions: state.captions,
      duration: state.duration,
      selected: state.selected,
      jobId: state.job?.id,
    });
    preview?.refresh();
    scheduleTimeline();
  }

  function reorderScene(from, to) {
    const sequence = currentSequence();
    if (from < 0 || from >= sequence.length || to < 0 || to >= sequence.length) return;
    const [moved] = sequence.splice(from, 1);
    sequence.splice(to, 0, moved);
    setSequence(sequence);
    notify("Scene order changed. The timeline and render use the new order.", "ok");
  }


  function sceneRoleDialog(index, item) {
    const sequence = currentSequence();
    const clip = sequence[index];
    if (!clip) return;
    const dialog = el("dialog", { class: "st-dialog", "aria-labelledby": "st-role-title" });
    const close = () => { dialog.close(); dialog.remove(); };
    const head = el("header", { class: "st-dialog-head" }, [
      el("h2", { id: "st-role-title", text: "Scene role" }),
      el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close" }),
    ]);
    head.lastChild.addEventListener("click", close);
    dialog.append(head);
    dialog.append(el("p", { class: "st-hint", text: "Hook and Payoff open and close the cut. The other roles are editorial labels; B-roll can come from any unused scene." }));
    for (const [label, role, beatKind] of [
      ["Hook", "hook", ""],
      ["Context", "beat", "context"],
      ["Bold statement", "beat", "statement"],
      ["Proof", "beat", "proof"],
      ["B-roll", "beat", "broll"],
      ["Transition", "beat", "transition"],
      ["Payoff", "payoff", ""],
    ]) {
      const active = (clip.role || "beat") === role
        && String(clip.beat_kind || "") === beatKind;
      const button = el("button", {
        class: `st-layer-row${active ? " is-active" : ""}`,
        type: "button",
        "aria-pressed": active ? "true" : "false",
      }, [
        el("span", { class: "st-layer-badge", text: label }),
        el("span", { class: "st-layer-name", text: active ? "Current role" : "Use this role" }),
      ]);
      button.addEventListener("click", () => {
        const next = currentSequence();
        next[index] = { ...next[index], role, ...(beatKind ? { beat_kind: beatKind } : {}) };
        if (!beatKind) delete next[index].beat_kind;
        setSequence(next);
        close();
        notify(`Scene ${index + 1} is now ${label}.`, "ok");
      });
      dialog.append(button);
    }
    const cancel = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Cancel" });
    cancel.addEventListener("click", close);
    dialog.append(el("div", { class: "st-actions" }, [cancel]));
    document.body.append(dialog);
    dialog.showModal();
  }

  function appendMomentDialog() {
    if (!state.set?.id) return;
    const stories = (state.set.stories || []).filter((story) => story.id !== state.story?.id);
    const dialog = el("dialog", { class: "st-dialog", "aria-labelledby": "st-append-title" });
    const close = () => { dialog.close(); dialog.remove(); };
    const head = el("header", { class: "st-dialog-head" }, [
      el("h2", { id: "st-append-title", text: "Add clips to this edit" }),
      el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close" }),
    ]);
    head.lastChild.addEventListener("click", close);
    dialog.append(head);
    dialog.append(el("p", {
      class: "st-hint",
      text: "The selected moments are appended after the current cut. Drag scenes in the timeline to reorder them.",
    }));
    if (!stories.length) {
      dialog.append(el("p", { class: "st-hint", text: "No other moments in this set. Build another moment in Moments first." }));
    }
    for (const story of stories) {
      const row = el("button", { class: "st-layer-row", type: "button" }, [
        el("span", { class: "st-layer-badge", text: "Moment" }),
        el("span", { class: "st-layer-name", text: story.title || story.id }),
        el("span", { class: "st-hint", text: `${story.clips?.length || 0} scenes` }),
      ]);
      row.addEventListener("click", () => {
        const appended = (story.clips || []).map((clip) => ({
          scene: Number(clip.scene),
          start: Number(clip.start),
          end: Number(clip.end),
          role: "beat",
          beat_kind: "context",
        }));
        if (!appended.length) return;
        setSequence([...currentSequence(), ...appended]);
        close();
        notify(`Added ${appended.length} scene${appended.length === 1 ? "" : "s"} to this edit.`, "ok");
      });
      dialog.append(row);
    }

    const used = new Set(currentSequence().map((clip) => Number(clip.scene)));
    const unused = ((state.job?.analysis?.scenes || []).filter((scene) => !used.has(Number(scene.id)))).slice(0, 30);
    dialog.append(el("div", { class: "st-layer-stage-head", style: "margin-top:14px" }, [
      el("h3", { text: "Unused scenes as b-roll" }),
      el("span", { class: "st-hint", text: `${unused.length} available` }),
    ]));
    if (!unused.length) {
      dialog.append(el("p", { class: "st-hint", text: "Every scene is already in this cut." }));
    }
    for (const scene of unused) {
      const text = String(scene.speech || scene.ocr || "").replace(/\s+/g, " ").trim();
      const row = el("button", { class: "st-layer-row", type: "button" }, [
        scene.thumb_url ? el("img", {
          src: scene.thumb_url,
          alt: "",
          loading: "lazy",
          style: "width:44px;height:44px;object-fit:cover;border-radius:5px;flex:0 0 auto",
        }) : el("span", { class: "st-layer-badge", text: "B-roll" }),
        el("span", { class: "st-layer-name", text: text || `Scene ${Number(scene.id) + 1}` }),
        el("span", { class: "st-hint", text: formatTime(scene.start) }),
      ]);
      row.addEventListener("click", () => {
        setSequence([...currentSequence(), {
          scene: Number(scene.id),
          start: Number(scene.start),
          end: Number(scene.end),
          role: "beat",
          beat_kind: "broll",
        }]);
        close();
        notify("B-roll added to the end of this edit.", "ok");
      });
      dialog.append(row);
    }
    const cancel = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Cancel" });
    cancel.addEventListener("click", close);
    dialog.append(el("div", { class: "st-actions" }, [cancel]));
    document.body.append(dialog);
    dialog.showModal();
  }

  let layerPanelCtx = null;

  function renderInspector() {
    const panelCtx = {
      getEdit: () => state.edit,
      getCaptions: () => state.captions,
      getStory: () => state.story,
      getJob: () => state.job,
      getSelected: () => state.selected,
      getDuration: () => state.duration,
      getPlayhead: () => state.playhead,
      save: () => saveNow(),
      setFoundText: (rows) => {
        state.foundText = Array.isArray(rows) ? rows : [];
        preview?.setFoundText(state.foundText);
      },
      getSelectedId: (kind) => (state.selected?.kind === kind ? state.selected.id : ""),
      // Hooks carry the R2 `story_start` pin only once the trim route exists,
      // so an older server keeps accepting the layout anchor.
      trimReady: () => Boolean(state.trim),
      select: (kind, id) => selectLayer(kind, id),
      setTab: (tab) => setActiveTab(tab),
      refresh: () => {
        renderLayers();
        renderElements();
      },
      getActiveLayer: () => state.activeLayer,
      setActiveLayer: (id) => { state.activeLayer = String(id || "clean"); },
      getTab: () => state.activeTab,
      getExpanded: () => momentScenesOpen,
      toggleExpanded: () => {
        momentScenesOpen = !momentScenesOpen;
        renderElements();
      },
      appendBlank: () => {
        setSequence([...currentSequence(), {
          kind: "blank",
          start: 0,
          end: 0.8,
          role: "beat",
          color: "#000000",
        }]);
        notify("0.8s blank filler added.", "ok");
        renderElements();
        scheduleTimeline();
      },
      appendScene: (scene) => {
        setSequence([...currentSequence(), {
          scene: Number(scene.id),
          start: Number(scene.start),
          end: Number(scene.end),
          role: "beat",
          beat_kind: "context",
        }]);
        notify(`Scene ${Number(scene.id) + 1} added to this cut.`, "ok");
        renderElements();
        scheduleTimeline();
      },
      reorder: (from, to) => reorderScene(from, to),
      openImport: () => { void leaveTo("import", dom.back); },
      openDissect: () => { openMediaDialog(); },
      setReframe(next) {
        if (!state.edit) return;
        state.edit.reframe = { ...(state.edit.reframe || {}), ...clone(next) };
        touch("reframe");
        renderLayers();
        preview?.refresh();
        scheduleTimeline();
      },
      setOutput(next) {
        if (!state.edit) return;
        const width = Number(next?.width) || 0;
        const height = Number(next?.height) || 0;
        if (!width || !height) return;
        state.edit.output = {
          width,
          height,
          fps: [24, 30, 60].includes(Number(next.fps)) ? Number(next.fps) : 30,
          hdr: false,
          ...(next.optical_flow ? { optical_flow: true } : {}),
          ...(next.stabilize ? { stabilize: true } : {}),
          ...((next.optical_flow || next.stabilize)
            ? { strength: Math.max(0, Math.min(1, Number(next.strength ?? 0.5))) }
            : {}),
        };
        state.output = { ...state.edit.output };
        touch("output");
      },
      setAudioFade(next) {
        if (!state.edit) return;
        state.edit.audio = { ...(state.edit.audio || {}), fade: clone(next) };
        touch("audio");
        scheduleTimeline();
      },
      setBorder(next) {
        if (!state.edit) return;
        state.edit.border = clone(next);
        touch("border");
        renderLayers();
        preview?.refresh();
        scheduleTimeline();
      },
      startAreaFocus: () => {
        preview?.setTool("box");
        notify("Draw the area to keep, then set the zoom in Layers.", "ok");
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
      addText(kind = "lower_third") {
        if (!state.edit) return null;
        const graphics = (state.edit.graphics || []).slice();
        const layer = newTextLayer(kind, {
          duration: state.duration,
          playhead: state.playhead,
          index: graphics.length,
        });
        graphics.push(layer);
        state.edit.graphics = graphics;
        touch("graphics");
        selectLayer("text", layer.id);
        renderElements();
        scheduleTimeline();
        preview?.refresh();
        return layer;
      },
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
    layerPanelCtx = panelCtx;
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

  function renderTranscriptPanel() {}

  function renderMomentBoard() {}

  let layersPanel = null;
  let elementsPanel = null;

  function renderLayers() {
    if (!dom.layers || !state.edit) return;
    if (!layerPanelCtx) renderInspector();
    if (!layersPanel) {
      layersPanel = mountLayersPanel(dom.layers, layerPanelCtx);
    } else {
      layersPanel.refresh();
    }
  }

  function renderElements() {
    if (!dom.elements || !state.edit) return;
    if (!layerPanelCtx) renderInspector();
    if (!elementsPanel) {
      elementsPanel = mountElementsPanel(dom.elements, layerPanelCtx);
    } else {
      elementsPanel.refresh();
    }
  }

  function addCleanBox(box = null, kind = "") {
    if (!state.edit) return;
    const layers = (state.edit.clean || []).slice();
    const layer = manualLayer(layers.length, box);
    if (kind) setLayerKind(layer, kind);
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
    if (state.selected.kind === "scenes") {
      const index = Number(state.selected.id);
      const sequence = currentSequence();
      if (!Number.isInteger(index) || index < 0 || index >= sequence.length) return;
      sequence.splice(index, 1);
      state.selected = null;
      setSequence(sequence);
      preview?.setSelected(null);
      timeline?.setSelected(null);
      notify("Scene removed from this cut.", "ok");
      return;
    }
    removeLayer(state.selected.kind, state.selected.id);
  }

  function selectLayer(kind, id) {
    if (kind === "sentences") return;
    state.selected = id ? { kind, id } : null;
    if (kind === "clean") state.activeLayer = "clean";
    else if (kind === "captions") state.activeLayer = "transcript";
    else if (kind === "audio") state.activeLayer = "narrative";
    else if (kind === "color") state.activeLayer = "filter";
    else if (kind === "text" || kind === "effects") state.activeTab = "elements";
    preview?.setSelected(
      ["clean", "text", "captions"].includes(kind) ? state.selected : null,
    );
    timeline?.setSelected(state.selected);
    renderLayers();
    renderElements();
  }

  function setActiveTab(tab) {
    const next = ["moments", "elements", "text", "audio"].includes(tab)
      ? tab
      : tab === "clean" ? "moments" : tab === "captions" ? "audio" : "elements";
    state.activeTab = next;
    elementsPanel?.setActive(next);
  }

  function touch(field) {
    if (!LAYER_FIELDS.includes(field)) return;
    state.redoIds = [];
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
    state.duration = sequenceDuration() || storyDuration(state.story, state.edit);
    if (!state.dirty.size) setSaveStatus("Saved", "ok");
    if (!disposed) {
      syncPreview();
      syncTimeline();
      setUndoState();
      setMeta();
      if (fields.includes("sequence") || fields.includes("assets")) {
        preview?.rebuildProxy?.();
      }
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
    state.duration = sequenceDuration() || storyDuration(state.story, state.edit);
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
    state.foundText = [];
    state.redoIds = [];
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
      console.error("Edit load failed", error);
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

  function activeSceneAt(time) {
    const clips = (Array.isArray(state.edit?.sequence) && state.edit.sequence.length)
      ? state.edit.sequence
      : (state.story?.clips || []);
    let offset = 0;
    for (let index = 0; index < clips.length; index += 1) {
      const clip = clips[index];
      const start = offset;
      const end = offset + Math.max(0, Number(clip.end) - Number(clip.start));
      if (time < end || index === clips.length - 1) {
        return {
          num: String(index + 1).padStart(2, "0"),
          role: clip?.kind === "blank" ? "Blank" : String(clip?.role === "hook" ? "Hook" : clip?.role === "payoff" ? "Payoff" : "Scene"),
          start,
          end,
          clip,
          index,
        };
      }
      offset = end;
    }
    return { num: "01", role: "Scene", start: 0, end: 0, clip: null, index: 0 };
  }

  function paintSceneTag() {
    const tag = activeSceneAt(state.playhead);
    preview?.setScene(tag.num, tag.role);
  }

  function openRecordDialog() {
    if (!state.job || !state.edit) return;
    const dialog = el("dialog", { class: "st-dialog st-record-dialog", "aria-labelledby": "st-record-title" });
    const close = () => {
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stream?.getTracks().forEach((track) => track.stop());
      if (timer) window.clearInterval(timer);
      dialog.close();
      dialog.remove();
    };
    const head = el("header", { class: "st-dialog-head" }, [
      el("h2", { id: "st-record-title", text: "Record voice-over" }),
      el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close" }),
    ]);
    head.lastChild.addEventListener("click", close);
    const status = el("p", { class: "st-hint", text: "Press record, speak, then save the take." });
    const time = el("p", { class: "st-mono st-record-time", text: "0:00" });
    const start = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Record" });
    const stop = el("button", { class: "st-btn st-btn-ghost", type: "button", text: "Stop", disabled: true });
    const save = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Save take", disabled: true });
    let stream = null;
    let recorder = null;
    let chunks = [];
    let timer = 0;
    let seconds = 0;
    let blob = null;
    const audio = el("audio", { controls: true, hidden: true });

    start.addEventListener("click", async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
        recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
        chunks = [];
        blob = null;
        audio.hidden = true;
        seconds = 0;
        time.textContent = "0:00";
        recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
        recorder.addEventListener("stop", () => {
          blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          audio.src = URL.createObjectURL(blob);
          audio.hidden = false;
          save.disabled = false;
          status.textContent = "Take ready. Listen, then save.";
        });
        recorder.start();
        start.disabled = true;
        stop.disabled = false;
        status.textContent = "Recording…";
        timer = window.setInterval(() => {
          seconds += 1;
          time.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
        }, 1000);
      } catch (error) {
        status.textContent = error?.message || "Microphone permission was refused.";
      }
    });
    stop.addEventListener("click", () => {
      if (timer) window.clearInterval(timer);
      timer = 0;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stream?.getTracks().forEach((track) => track.stop());
      start.disabled = false;
      stop.disabled = true;
      status.textContent = "Saving take…";
    });
    save.addEventListener("click", async () => {
      if (!blob || !state.job) return;
      save.disabled = true;
      save.textContent = "Saving…";
      try {
        const form = new FormData();
        form.append("file", blob, "voice-over.webm");
        const response = await fetch(`/api/jobs/${encodeURIComponent(state.job.id)}/audio/voice-upload`, {
          method: "POST", body: form, credentials: "same-origin",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || payload.error || "The voice take could not be saved.");
        state.edit.audio = {
          ...(state.edit.audio || {}),
          mode: "voice_over",
          mode_chosen: true,
          voice: {
            ...(state.edit.audio?.voice || {}),
            recorded: {
              path: payload.path,
              name: payload.name || "Voice-over",
              duration: payload.duration || seconds,
            },
          },
        };
        touch("audio");
        await saveNow();
        notify("Voice-over take saved to this moment.", "ok");
        close();
      } catch (error) {
        save.disabled = false;
        save.textContent = "Save take";
        status.textContent = error?.message || "The take could not be saved.";
      }
    });

    dialog.append(head, status, time, audio, el("div", { class: "st-actions" }, [start, stop, save]));
    document.body.append(dialog);
    dialog.showModal();
  }

  function parseSubtitle(text) {
    const rows = String(text || "").replace(/\r/g, "").split(/\n{2,}/);
    const cues = [];
    for (const row of rows) {
      const lines = row.split("\n").map((line) => line.trim()).filter(Boolean);
      const timeLine = lines.find((line) => line.includes("-->"));
      if (!timeLine) continue;
      const [from, to] = timeLine.split("-->").map((part) => part.trim().split(" ")[0]);
      const seconds = (value) => {
        const parts = String(value).replace(",", ".").split(":").map(Number);
        if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
        if (parts.length === 2) return parts[0] * 60 + parts[1];
        return Number(value) || 0;
      };
      const start = seconds(from);
      const end = Math.max(start + 0.2, seconds(to));
      const body = lines.slice(lines.indexOf(timeLine) + 1).join(" ").replace(/<[^>]+>/g, "").trim();
      if (body) cues.push({ start: round(start, 2), end: round(end, 2), text: body });
    }
    return cues;
  }

  function openSubtitleDialog() {
    if (!state.job || !state.edit) return;
    const dialog = el("dialog", { class: "st-dialog", "aria-labelledby": "st-subtitle-title" });
    const close = () => { dialog.close(); dialog.remove(); };
    const head = el("header", { class: "st-dialog-head" }, [
      el("h2", { id: "st-subtitle-title", text: "Import subtitles" }),
      el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close" }),
    ]);
    head.lastChild.addEventListener("click", close);
    const file = el("input", { type: "file", accept: ".srt,.vtt,text/plain", "aria-label": "Subtitle file" });
    const status = el("p", { class: "st-hint", text: "Choose an SRT or VTT file." });
    const importButton = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Import", disabled: true });
    let cues = [];
    file.addEventListener("change", async () => {
      const chosen = file.files?.[0];
      if (!chosen) return;
      cues = parseSubtitle(await chosen.text());
      status.textContent = cues.length ? `${cues.length} lines ready.` : "No timed lines found in that file.";
      importButton.disabled = !cues.length;
    });
    importButton.addEventListener("click", async () => {
      importButton.disabled = true;
      importButton.textContent = "Importing…";
      try {
        let track = state.captions;
        if (!track?.id) {
          const result = await buildCaptionTrack(state.job.id, {
            setId: state.set.id, storyId: state.story.id, styleId: "clean",
          });
          track = result?.track || result;
        }
        if (!track?.id) throw new Error("Build captions once before importing a file.");
        const result = await patchCaptionTrack(state.job.id, track.id, { cues });
        state.captions = result?.track || result;
        state.edit.captions = {
          ...(state.edit.captions || {}),
          track_id: state.captions.id,
          style_id: state.captions.style_id || "clean",
          enabled: true,
        };
        touch("captions");
        await saveNow();
        notify(`Imported ${cues.length} subtitle lines.`, "ok");
        close();
      } catch (error) {
        status.textContent = error?.message || "The subtitles could not be imported.";
        importButton.disabled = false;
        importButton.textContent = "Import";
      }
    });
    dialog.append(head, file, status, el("div", { class: "st-actions" }, [importButton]));
    document.body.append(dialog);
    dialog.showModal();
  }

  function duplicateSceneAtPlayhead() {
    const tag = activeSceneAt(state.playhead);
    if (!tag.clip) return;
    const sequence = currentSequence();
    sequence.splice(tag.index + 1, 0, cleanClip(tag.clip));
    setSequence(sequence);
    notify("Scene duplicated.", "ok");
  }

  function reverseSceneAtPlayhead() {
    const tag = activeSceneAt(state.playhead);
    if (!tag.clip || tag.clip.kind === "blank") return;
    const sequence = currentSequence();
    sequence[tag.index] = { ...sequence[tag.index], reverse: !sequence[tag.index].reverse };
    setSequence(sequence);
    notify(sequence[tag.index].reverse ? "Clip will play in reverse." : "Reverse removed.", "ok");
  }

  function freezeAtPlayhead() {
    const tag = activeSceneAt(state.playhead);
    if (!tag.clip || tag.clip.kind === "blank") return;
    const sequence = currentSequence();
    sequence.splice(tag.index + 1, 0, {
      kind: "freeze",
      scene: Number(tag.clip.scene),
      start: Number(tag.clip.start) + Math.max(0, state.playhead - tag.start),
      end: Number(tag.clip.start) + Math.max(0, state.playhead - tag.start) + 1.5,
      role: "beat",
    });
    setSequence(sequence);
    notify("Freeze frame added for 1.5s.", "ok");
  }

  function addMosaicLayer() {
    addCleanBox(null, "mosaic");
    layersPanel?.setActive("clean");
    notify("Mosaic layer added. Draw the area on the picture.", "ok");
  }

  function addAsset(asset, label = "Media") {
    if (!state.edit || !asset?.id) return;
    const duration = Math.max(0.2, Number(asset.duration) || 2.5);
    state.edit.assets = [
      ...(state.edit.assets || []).filter((item) => item.id !== asset.id),
      {
        id: asset.id,
        kind: asset.kind === "photo" ? "photo" : "video",
        name: asset.name || label,
        path: asset.path,
        width: Number(asset.width) || 0,
        height: Number(asset.height) || 0,
        duration,
        has_audio: Boolean(asset.has_audio),
      },
    ];
    state.edit.sequence = [
      ...currentSequence(),
      {
        kind: "file",
        asset_id: asset.id,
        start: 0,
        end: duration,
        role: "beat",
      },
    ];
    state.duration = sequenceDuration() || state.duration;
    touch("assets");
    touch("sequence");
    renderElements();
    scheduleTimeline();
    preview?.rebuildProxy?.();
    preview?.refresh();
    notify(`${asset.kind === "photo" ? "Photo" : "Scene"} added to this cut.`, "ok");
  }

  async function addSceneAsAsset(sourceJobId, scene) {
    if (!state.job) return;
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(state.job.id)}/assets/from-scene`, {
        method: "POST",
        body: { source_job_id: sourceJobId, scene: Number(scene.id) },
      });
      if (result?.asset) addAsset(result.asset, "Scene");
    } catch (error) {
      notify(error?.message || "Could not add that scene.", "bad");
    }
  }

  function openMediaDialog() {
    if (!state.job) return;
    const dialog = el("dialog", { class: "st-dialog st-media-dialog", "aria-labelledby": "st-media-title" });
    const close = () => { dialog.close(); dialog.remove(); };
    const head = el("header", { class: "st-dialog-head" }, [
      el("h2", { id: "st-media-title", text: "Add media" }),
      el("button", { class: "st-icon-btn", type: "button", text: "×", "aria-label": "Close" }),
    ]);
    head.lastChild.addEventListener("click", close);
    const tabs = el("div", { class: "st-media-tabs", role: "tablist" });
    const body = el("div", { class: "st-media-body" });
    let active = "this";

    async function renderPanel() {
      tabs.replaceChildren();
      for (const [id, label] of [["this", "This video"], ["other", "Other videos"], ["photos", "Photos"]]) {
        const button = el("button", {
          class: `st-media-tab${active === id ? " is-active" : ""}`,
          type: "button", role: "tab", "aria-selected": active === id ? "true" : "false", text: label,
        });
        button.addEventListener("click", () => { active = id; void renderPanel(); });
        tabs.append(button);
      }
      body.replaceChildren();
      if (active === "this") {
        const scenes = state.job?.analysis?.scenes || [];
        const grid = el("div", { class: "st-media-grid" });
        for (const scene of scenes) {
          const tile = el("button", { class: "st-media-tile", type: "button", title: `Add scene ${Number(scene.id) + 1}` }, [
            el("img", { src: `/api/jobs/${encodeURIComponent(state.job.id)}/thumb/${Number(scene.id)}`, alt: "", loading: "lazy" }),
            el("span", { text: `+ ${Number(scene.id) + 1}` }),
          ]);
          tile.addEventListener("click", () => { void addSceneAsAsset(state.job.id, scene).then(close); });
          grid.append(tile);
        }
        body.append(grid);
        return;
      }
      if (active === "other") {
        const grid = el("div", { class: "st-media-jobs" });
        body.append(el("p", { class: "st-hint", text: "Choose a ready video, then a scene." }));
        const jobs = await listJobs({ limit: 12 }).catch(() => ({ jobs: [] }));
        for (const job of jobs.jobs || []) {
          if (String(job.id) === String(state.job.id) || job.status !== "ready") continue;
          const button = el("button", { class: "st-media-job", type: "button" }, [
            el("strong", { text: job.name || job.id }),
            el("small", { text: "Ready" }),
          ]);
          button.addEventListener("click", async () => {
            body.replaceChildren(el("p", { class: "st-hint", text: "Reading scenes…" }));
            const full = await getJob(job.id).catch(() => null);
            const scenes = full?.analysis?.scenes || [];
            const scenesGrid = el("div", { class: "st-media-grid" });
            for (const scene of scenes) {
              const tile = el("button", { class: "st-media-tile", type: "button", title: `Add scene ${Number(scene.id) + 1}` }, [
                el("img", { src: `/api/jobs/${encodeURIComponent(job.id)}/thumb/${Number(scene.id)}`, alt: "", loading: "lazy" }),
                el("span", { text: `+ ${Number(scene.id) + 1}` }),
              ]);
              tile.addEventListener("click", () => { void addSceneAsAsset(job.id, scene).then(close); });
              scenesGrid.append(tile);
            }
            if (!scenes.length) scenesGrid.append(el("p", { class: "st-hint", text: "This video has no scenes yet." }));
            body.replaceChildren(scenesGrid);
          });
          grid.append(button);
        }
        body.append(grid);
        return;
      }
      const input = el("input", { type: "file", accept: "image/*", "aria-label": "Choose a photo" });
      const upload = el("button", { class: "st-btn st-btn-primary", type: "button", text: "Add photo" });
      const status = el("p", { class: "st-hint", text: "JPG, PNG, WEBP or HEIC. The photo becomes a 2.5s clip." });
      upload.addEventListener("click", async () => {
        const chosen = input.files?.[0];
        if (!chosen) return;
        upload.disabled = true;
        upload.textContent = "Adding…";
        try {
          const form = new FormData();
          form.append("file", chosen, chosen.name);
          const response = await fetch(`/api/jobs/${encodeURIComponent(state.job.id)}/assets/photo`, {
            method: "POST", body: form, credentials: "same-origin",
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || "Could not add the photo.");
          addAsset(payload.asset, "Photo");
          close();
        } catch (error) {
          status.textContent = error?.message || "Could not add the photo.";
          upload.disabled = false;
          upload.textContent = "Add photo";
        }
      });
      body.append(input, el("div", { class: "st-media-upload" }, [upload]), status);
    }

    dialog.append(head, tabs, body);
    document.body.append(dialog);
    dialog.showModal();
    void renderPanel();
  }

  function renderEditorParts() {
    if (!dom.preview || !dom.timeline) return;
    if (!preview) {
      preview = mountPreview(dom.preview, {
        jobId: state.job.id,
        onTime: (time) => {
          state.playhead = time;
          timeline?.setTime(time);
          paintSceneTag();
        },
        onStale: () => { void handleStalePreview(); },
        onSelect: (kind, id) => selectLayer(kind, id),
        onBoxChange: (id, box, options) => updateCleanBox(id, box, options),
        onBoxCreate: (box) => createCleanBox(box),
        onAspect: (value) => { void switchAspect(value); },
        onOutput: (value) => {
          state.output = value || state.output;
          layerPanelCtx?.setOutput?.(value);
        },
      });
    }
    if (!timeline) {
      timeline = mountTimeline(dom.timeline, {
        jobId: state.job.id,
        onSeek: (time) => seek(time),
        onSelect: (kind, id) => selectLayer(kind, id),
        onAdd: (kind) => addLayer(kind),
        onAddMoment: () => appendMomentDialog(),
        onReorder: (from, to) => reorderScene(from, to),
        onRole: (index, item) => sceneRoleDialog(index, item),
        onAudioBus: (mode) => {
          if (!state.edit) return;
          state.edit.audio = { ...(state.edit.audio || {}), mode, mode_chosen: true };
          touch("audio");
          renderLayers();
          preview?.refresh();
          scheduleTimeline();
        },
        onUndo: () => { void undoLastChange(); },
        onRedo: () => { void redoLastChange(); },
        onUndoTrim: () => { void undoTrimChange(); },
        onDelete: () => { removeSelectedLayer(); },
        onExtractFrame: () => { preview?.captureFrame(); },
        onAddMedia: () => { void leaveTo("import", dom.back); },
        onAddText: () => { elementsPanel?.setActive("text"); },
        onAddAudio: () => { elementsPanel?.setActive("audio"); },
        onEffects: () => { elementsPanel?.setActive("elements"); },
        onMosaic: () => { addMosaicLayer(); },
        onAutoCaptions: () => {
          layersPanel?.setActive("transcript");
          void runAutoSubtitles("story");
        },
        onOverlayTrack: () => { elementsPanel?.setActive("text"); },
        onReverse: () => { reverseSceneAtPlayhead(); },
        onDuplicate: () => { duplicateSceneAtPlayhead(); },
        onFreeze: () => { freezeAtPlayhead(); },
        onRecord: () => { openRecordDialog(); },
        onImportSubtitle: () => { openSubtitleDialog(); },
        onSplit: () => { notify("Split is applied by trimming the clip at the playhead.", ""); },
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
      story: state.story,
      job: state.job,
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
    paintSceneTag();
    renderElements();
    renderLayers();
    renderInspector();
  }

  function seek(time) {
    state.playhead = clamp(numberOr(time), 0, Math.max(0.1, state.duration));
    preview?.seek(state.playhead);
    timeline?.setTime(state.playhead);
    paintSceneTag();
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
    if (!state.edit || disposed) return;
    const saved = await flushSave();
    if (!saved) return;
    if (!state.edit?.parent) return;
    if (dom.undo) dom.undo.disabled = true;
    const undoneId = state.edit.id;
    try {
      const result = await undoEdit(state.job.id, state.edit.id);
      if (disposed || !result?.edit) return;
      state.redoIds.push(undoneId);
      state.edit = result.edit;
      state.duration = sequenceDuration() || storyDuration(state.story, state.edit);
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

  async function redoLastChange() {
    if (!state.redoIds.length || !state.edit || disposed) return;
    const saved = await flushSave();
    if (!saved) return;
    const target = state.redoIds[state.redoIds.length - 1];
    if (dom.redo) dom.redo.disabled = true;
    try {
      const result = await restoreEdit(state.job.id, state.edit.id, target);
      if (disposed || !result?.edit) return;
      state.redoIds.pop();
      state.edit = result.edit;
      state.duration = sequenceDuration() || storyDuration(state.story, state.edit);
      state.selected = null;
      state.dirty.clear();
      await resolveCaptionTrack(state.edit);
      await refreshTrimState();
      if (disposed) return;
      renderEditorParts();
      populateHeader();
      setSaveStatus("Redid the last change", "ok");
      notify("Redid the last change.", "ok");
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
        notify(error?.message || "Could not redo the last change.", "bad");
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
    document.removeEventListener("keydown", onEditorKeydown);
    if (dom.save) { dom.save.hidden = true; dom.save.textContent = "Ready"; }
    if (dom.help) dom.help.hidden = true;
    delete root.dataset.editorFrame;
    root.replaceChildren();
  };
}
