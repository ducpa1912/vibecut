/**
 * Studio — Edit step.
 *
 * One editor per story and aspect. The document is the Wave-1 Edit; every
 * control writes through its CRUD API. The preview asks the frame route for
 * the exact current frame and falls back to the story proxy and then to a
 * placeholder, so the editor stays usable while the render hooks land.
 */

import { getJob, listClipSets } from "../api.js";
import { el, formatCount, setStatus } from "../ui.js";
import { mountPreview } from "./preview.js";
import { mountTimeline } from "./timeline.js";
import { mountInspector } from "./inspector.js";
import {
  ASPECTS,
  aspectLabel,
  clone,
  clamp,
  formatTime,
  numberOr,
  storyDuration,
} from "./model.js";
import {
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
const LAYER_FIELDS = ["clean", "reframe", "motion", "color", "graphics", "captions", "audio"];

function ensureStyles() {
  if (document.getElementById(CSS_ID)) return;
  const link = document.createElement("link");
  link.id = CSS_ID;
  link.rel = "stylesheet";
  link.href = "/static/studio/edit/edit.css?v=0.1.0";
  document.head.append(link);
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
  return `${String(index + 1).padStart(2, "0")} · ${title || `Story ${index + 1}`}`;
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
  let loadSeq = 0;
  let timelineRaf = 0;
  let staleReload = false;

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
    dirty: new Set(),
    revisions: {},
  };

  const dom = {};

  function renderLoading(message) {
    root.replaceChildren(el("section", { class: "st-panel" }, [
      el("p", { class: "st-eyebrow", text: "Step 4 · Edit" }),
      el("div", { class: "st-card st-edit-loading" }, [
        el("h1", { text: "Opening the editor" }),
        el("p", { class: "st-hint", text: message || "Reading this story…" }),
      ]),
    ]));
  }

  function renderEmpty({ title, copy, action = "Go to Import", step = "import", tone = "" }) {
    const section = el("section", { class: "st-panel", "aria-labelledby": "st-edit-empty-title" }, [
      el("p", { class: "st-eyebrow", text: "Step 4 · Edit" }),
      el("div", { class: "st-empty" }, [
        el("span", { class: "st-empty-mark", "aria-hidden": "true", text: "04" }),
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
    const section = el("section", { class: "st-panel" }, [
      el("p", { class: "st-eyebrow", text: "Step 4 · Edit" }),
      el("div", { class: "st-empty" }, [
        el("span", { class: "st-empty-mark", "aria-hidden": "true", text: "04" }),
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
    root.innerHTML = `
      <section class="st-panel st-edit-panel" aria-labelledby="st-edit-title">
        <header class="st-edit-head">
          <div class="st-edit-heading">
            <p class="st-eyebrow">Step 4 · Edit</p>
            <h1 id="st-edit-title">Shape the story</h1>
            <p id="st-edit-sub" class="st-edit-sub">One edit per story and shape. Changes save as you go.</p>
          </div>
          <div class="st-edit-controls">
            <label class="st-field st-field-inline">
              <span>Story</span>
              <select id="st-edit-story" aria-label="Story"></select>
            </label>
            <div class="st-aspect-group" role="group" aria-label="Story shape">
              <button class="st-aspect" type="button" data-aspect="9:16" aria-pressed="true">9:16</button>
              <button class="st-aspect" type="button" data-aspect="4:5" aria-pressed="false">4:5</button>
            </div>
            <button id="st-edit-all" class="st-btn st-btn-quiet st-btn-small" type="button">All stories</button>
            <button id="st-edit-undo" class="st-btn st-btn-ghost st-btn-small" type="button" disabled>Undo</button>
          </div>
        </header>
        <div class="st-edit-statusline">
          <span id="st-edit-save" class="st-edit-save" role="status" aria-live="polite">Opening…</span>
          <span id="st-edit-meta" class="st-hint"></span>
        </div>
        <div id="st-edit-notice" class="st-edit-notice" role="alert" hidden></div>
        <div class="st-edit-workspace">
          <div id="st-edit-preview"></div>
          <aside id="st-edit-inspector" class="st-inspector" aria-label="Layer controls"></aside>
        </div>
        <div id="st-edit-timeline"></div>
      </section>
    `;
    dom.story = root.querySelector("#st-edit-story");
    dom.aspect = Array.from(root.querySelectorAll(".st-aspect"));
    dom.undo = root.querySelector("#st-edit-undo");
    dom.save = root.querySelector("#st-edit-save");
    dom.meta = root.querySelector("#st-edit-meta");
    dom.notice = root.querySelector("#st-edit-notice");
    dom.sub = root.querySelector("#st-edit-sub");
    dom.preview = root.querySelector("#st-edit-preview");
    dom.inspector = root.querySelector("#st-edit-inspector");
    dom.timeline = root.querySelector("#st-edit-timeline");
    dom.all = root.querySelector("#st-edit-all");

    dom.story.addEventListener("change", () => { void switchStory(dom.story.value); });
    for (const button of dom.aspect) {
      button.addEventListener("click", () => { void switchAspect(button.dataset.aspect); });
    }
    dom.all.addEventListener("click", () => ctx.go("stories"));
    dom.undo.addEventListener("click", () => { void undoLastChange(); });
  }

  function setSaveStatus(message, tone = "") {
    if (!dom.save) return;
    dom.save.textContent = message;
    dom.save.dataset.tone = tone;
  }

  function notify(message, tone = "") {
    if (!dom.notice) return;
    setStatus(dom.notice, message, tone);
  }

  function setUndoState() {
    if (!dom.undo) return;
    dom.undo.disabled = saving || !state.edit?.parent;
  }

  function setMeta() {
    if (!dom.meta) return;
    const story = state.story;
    dom.meta.textContent = story
      ? `${formatTime(state.duration)} · ${aspectLabel(state.aspect)}`
      : "";
    if (dom.sub && story) {
      dom.sub.textContent = String(story.title || "Shape the story");
    }
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
    dom.story.value = state.story?.id || "";
  }

  function updateAspectButtons() {
    for (const button of dom.aspect || []) {
      const active = button.dataset.aspect === state.aspect;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.classList.toggle("is-active", active);
    }
  }

  function storyTrack() {
    if (!state.job || !state.set || !state.story) return null;
    const key = `${state.set.id}:${state.story.id}`;
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
    if (!dom.inspector) return;
    const panelCtx = {
      getEdit: () => state.edit,
      getCaptions: () => state.captions,
      getStory: () => state.story,
      getDuration: () => state.duration,
      getPlayhead: () => state.playhead,
      getSelectedId: (kind) => (state.selected?.kind === kind ? state.selected.id : ""),
      select: (kind, id) => selectLayer(kind, id),
      setTab: (tab) => setActiveTab(tab),
      refresh: () => renderInspector(),
      seek: (time) => seek(time),
      notify,
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
    mountInspector(dom.inspector, {
      active: state.activeTab,
      edit: state.edit,
      captions: state.captions,
      panelCtx,
    });
  }

  function selectLayer(kind, id) {
    const tab = kind === "sentences" ? state.activeTab : kind;
    if (tab) state.activeTab = tab;
    if (kind === "sentences") return;
    state.selected = id ? { kind, id } : null;
    preview?.setSelected(kind === "text" || kind === "captions" ? state.selected : null);
    timeline?.setSelected(state.selected);
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
      notify("This story has no edit now. Open Stories and choose it again.", "bad");
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
          try {
            const result = await patchEdit(state.job.id, state.edit.id, body);
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
            ? "This story changed in another window. The latest save is open; check it and try again."
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

  async function loadStory({ forkFrom = null } = {}) {
    const seq = ++loadSeq;
    if (!state.job || !state.set || !state.story) return;
    state.selected = null;
    state.playhead = Math.min(state.playhead, Math.max(0.1, state.duration));
    setSaveStatus("Opening story…", "busy");
    notify("");
    if (dom.inspector) {
      dom.inspector.replaceChildren(el("p", { class: "st-hint", text: "Opening story…" }));
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
      state.duration = storyDuration(state.story, edit);
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
          ? "This story changed since it was cut. Open Stories and build it again."
          : (error?.message || "Could not open this story."),
        "bad",
      );
      if (state.edit) {
        renderEditorParts();
        populateHeader();
      } else {
        renderError(error?.message || "Could not open this story.");
      }
    }
  }

  function populateHeader() {
    renderStoryOptions();
    updateAspectButtons();
    setMeta();
    setUndoState();
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
      });
    }
    if (!timeline) {
      timeline = mountTimeline(dom.timeline, {
        onSeek: (time) => seek(time),
        onSelect: (kind, id) => selectLayer(kind, id),
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
    });
    timeline.setTime(state.playhead);
    timeline.setSelected(state.selected);
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
      if (!disposed) notify("This story changed in another window. The latest save is open.", "bad");
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
            ? "This story changed in another window. The latest save is open."
            : "This story changed in another window. Open it again from Stories.",
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
        copy: "The editor works on one story at a time. Import a video, then pick its stories.",
      });
      return;
    }
    renderLoading("Reading the video and its story picks…");
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
          action: "Open Stories",
          step: "stories",
        });
        return;
      }
      const usable = state.sets.filter((set) => Array.isArray(set.stories) && set.stories.length);
      if (!usable.length) {
        renderEmpty({
          title: "Pick stories first",
          copy: "Edit needs a story cut. Open Stories, choose how many you want, then come back.",
          action: "Open Stories",
          step: "stories",
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
    if (document.visibilityState === "hidden" && state.dirty.size) void saveNow();
  }

  window.addEventListener("beforeunload", onBeforeUnload);
  document.addEventListener("visibilitychange", onVisibilityChange);
  void boot();

  return () => {
    disposed = true;
    if (saveTimer) window.clearTimeout(saveTimer);
    if (timelineRaf) window.cancelAnimationFrame(timelineRaf);
    if (state.dirty.size) void saveNow();
    preview?.destroy();
    timeline?.destroy();
    window.removeEventListener("beforeunload", onBeforeUnload);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    root.replaceChildren();
  };
}
