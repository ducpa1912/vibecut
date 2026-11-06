/**
 * VibeCut Studio — shell.
 *
 * Four steps: Import · Moments · Edit · Finish.
 * Native ES modules, no build step, no new backend routes.
 *
 * Studio is its own workspace: one page, one app, no link into Classic or the
 * Voice Room. Voice features live in Setup and the Edit audio layer.
 */

import { mount as mountImport } from "./import.js";
import { mount as mountMoments } from "./stories.js";
import { mount as mountEdit } from "./edit.js?v=20261106-4";
import { mount as mountFinish } from "./finish.js";
import { mount as mountLibrary } from "./library.js";
import { SOURCES_TAB } from "./library.js";
import { mount as mountSetup } from "./setup.js";
import { cachedJobStamp, getJob, getJobStatus, invalidateReadCache, listClipSets, request } from "./api.js";
import { paintIcons } from "./edit/icons.js";
import { el, statusText } from "./ui.js";

const JOB_KEY = "vibecut.studio.job";

const STEPS = [
  { id: "import", label: "Import", note: "Bring in a video", mount: mountImport },
  { id: "moments", label: "Moments", note: "Find and build moments", mount: mountMoments },
  { id: "edit", label: "Edit", note: "Shape each moment", mount: mountEdit },
  { id: "finish", label: "Finish", note: "Review, render and share", mount: mountFinish },
];

const STEP_IDS = new Set(STEPS.map((step) => step.id));
const WATCH_BUSY_MS = 2000;
const WATCH_IDLE_MS = 15000;
// The shell re-reads the full job every 150 s to see `updated` change.
// Status keeps its 15 s cadence; this adds two reads per five minutes.
const JOB_RECHECK_MS = 150000;
const EMPTY_STATE = {
  jobId: "", loaded: false, status: "", progress: 0, message: "",
  check: "none", stories: 0, missing: false, sourceMissing: "", updatedAt: "",
};

const STOPPED = new Set(["cancelled", "interrupted"]);

/** A job's change stamp. Newer data uses `updated_at`; job.json uses `updated`. */
export function jobUpdatedAt(job) {
  const value = job?.updated_at ?? job?.updated;
  return value === undefined || value === null ? "" : String(value);
}

/** Whether two job payloads carry different change stamps. */
export function jobChanged(previous, next) {
  const before = jobUpdatedAt(previous);
  const after = jobUpdatedAt(next);
  return Boolean(before && after && before !== after);
}

function isReading(status) {
  return Boolean(status) && status !== "ready" && status !== "failed" && status !== "error"
    && !STOPPED.has(status);
}

/**
 * Whether a light refresh may keep the last Check and Stories answers:
 * same ready video, still ready, and no Check running.
 */
export function canReuseSteps(previous, jobId, status, light) {
  return Boolean(light) && previous?.jobId === jobId && Boolean(previous?.loaded)
    && previous?.status === "ready" && status === "ready" && previous?.check !== "running";
}

/** The step where a video's work continues (boot and the video library). */
export function bestStepFor(hasJob, state) {
  if (!hasJob) return "import";
  const status = state?.status;
  if (isReading(status) || state?.missing || STOPPED.has(status)
    || status === "failed" || status === "error" || state?.sourceMissing) return "import";
  if (state?.stories) return "edit";
  return "moments";
}

/** The top strip's one action: stop a read, or start a stopped one again. */
export function readingAction(status) {
  if (isReading(status)) return { kind: "cancel", label: "Cancel reading" };
  if (STOPPED.has(status) || status === "failed" || status === "error") {
    return { kind: "retry", label: "Read again" };
  }
  return null;
}

/** What Open in Finish hands to Finish: the cut's job, set, story and shape. */
export function finishFocusFrom(artifact = {}) {
  return {
    jobId: String(artifact.job_id || ""),
    setId: String(artifact.set_id || ""),
    storyId: String(artifact.story_id || ""),
    aspect: String(artifact.aspect || artifact.shape || ""),
    artifactId: String(artifact.artifact_id || ""),
  };
}

export function checkState(payload) {
  const state = String(payload?.status || "").toLowerCase();
  if (state === "cancelled") return "none";
  if (state === "failed") return "failed";
  if (state === "queued" || state === "running" || payload?.complete === false) return "running";
  return "done";
}

function readJob() {
  try {
    const raw = localStorage.getItem(JOB_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (value && typeof value === "object" && value.id) return value;
  } catch (_) {
    /* Ignore a stale or unreadable value. */
  }
  return null;
}

function writeJob(value) {
  try {
    if (value && value.id) localStorage.setItem(JOB_KEY, JSON.stringify(value));
    else localStorage.removeItem(JOB_KEY);
  } catch (_) {
    /* A private window may refuse storage; the session still works. */
  }
}

function routeFromHash() {
  const value = String(location.hash || "").replace(/^#\/?/, "").split("?")[0];
  const step = value === "check" || value === "stories" ? "moments" : value;
  return STEP_IDS.has(step) ? step : "";
}

function statusWord(status) {
  return status ? statusText(status) : "";
}

export function startStudio() {
  const root = document.getElementById("studio-root");
  if (!root) return;

  if (document.documentElement.dataset.editor === undefined
    || document.documentElement.dataset.editor === "") {
    document.documentElement.dataset.editor = "studio";
  }

  let currentJob = readJob();
  let activeStep = "";
  let cleanup = null;
  let setupCleanup = null;

  root.innerHTML = `
    <div class="st-shell">
      <a class="st-skip" href="#st-main">Skip to content</a>
      <div class="st-main-wrap">
        <header class="st-top st-appbar">
          <div class="st-top-row">
            <div class="st-brand">
              <span class="st-brand-dot" aria-hidden="true"></span>
              <span class="st-brand-name">VibeCut</span>
              <span class="st-brand-tag">Studio</span>
            </div>
            <nav class="st-rail-nav" aria-label="Studio steps">
              <ol class="st-step-list">
                ${STEPS.map((step, index) => `
                  <li>
                    <button class="st-step" type="button" data-step="${step.id}">
                      <span class="st-step-num">${String(index + 1).padStart(2, "0")}</span>
                      <span class="st-step-copy"><strong>${step.label}</strong><small>${step.note}</small></span>
                    </button>
                  </li>
                `).join("")}
              </ol>
            </nav>
            <div class="st-top-right">
              <div class="st-top-job">
                <span class="st-top-label">Current video</span>
                <strong id="st-current-name">No video open</strong>
                <span id="st-current-status" class="st-top-status" hidden></span>
              </div>
              <div class="st-top-actions">
                <button id="st-edit-finish" class="st-btn st-btn-primary st-btn-small" type="button" hidden>Finish<span data-icon="arrow-right" aria-hidden="true"></span></button>
                <span id="st-edit-ready" class="st-top-status st-edit-ready" role="status" aria-live="polite" hidden>Ready</span>
                <button id="st-edit-shortcuts-open" class="st-btn st-btn-ghost st-btn-small st-edit-shortcuts-open" type="button" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" hidden>⌘</button>
                <button id="st-menu-open" class="st-btn st-btn-ghost st-btn-small st-menu-open" type="button" aria-haspopup="dialog" aria-controls="st-menu-dialog">Menu</button>
              </div>
            </div>
          </div>
          <div id="st-top-progress" class="st-top-progress" role="status" aria-live="polite" hidden>
            <div class="st-progress-bar"><i id="st-top-progress-fill"></i></div>
            <span id="st-top-progress-text"></span>
            <button id="st-top-reading-action" class="st-btn st-btn-quiet st-btn-small" type="button" hidden></button>
          </div>
          <p id="st-rail-notice" class="st-rail-notice" role="status" aria-live="polite" hidden></p>
        </header>
        <main id="st-main" class="st-main" tabindex="-1">
          <p class="st-hint">Opening Studio…</p>
        </main>
      </div>
    </div>
    <dialog id="st-menu-dialog" class="st-dialog st-menu-dialog" aria-labelledby="st-menu-title">
      <div class="st-dialog-head">
        <h2 id="st-menu-title">Studio menu</h2>
        <button class="st-icon-btn" type="button" data-menu-close data-icon="x" aria-label="Close menu"></button>
      </div>
      <div class="st-menu-workspace" aria-label="Workspace">
        <button id="st-change-video" class="st-btn st-btn-ghost st-btn-small" type="button">Change video</button>
      </div>
      <div class="st-menu-tabs" role="tablist" aria-label="Setup and settings">
        <button id="st-menu-tab-setup" class="st-menu-tab" type="button" role="tab" aria-selected="true" aria-controls="st-menu-setup" tabindex="0" data-menu-tab="setup">Setup</button>
        <button id="st-menu-tab-settings" class="st-menu-tab" type="button" role="tab" aria-selected="false" aria-controls="st-menu-settings" tabindex="-1" data-menu-tab="settings">Settings</button>
      </div>
      <div id="st-menu-setup" class="st-dialog-body st-menu-panel" role="tabpanel" aria-labelledby="st-menu-tab-setup">
        <div id="st-setup-host" class="st-setup-host"></div>
      </div>
      <div id="st-menu-settings" class="st-dialog-body st-menu-panel" role="tabpanel" aria-labelledby="st-menu-tab-settings" hidden>
        <section class="st-dialog-section">
          <h3>Current video</h3>
          <p id="st-dialog-job" class="st-dialog-job">No video open.</p>
          <button id="st-forget-video" class="st-btn st-btn-quiet" type="button">Forget this video</button>
          <p class="st-hint">Forgetting only clears the open video. Nothing is deleted from disk.</p>
        </section>
      </div>
      <div class="st-dialog-foot">
        <span class="st-local"><i aria-hidden="true"></i>On this Mac</span>
        <button class="st-btn st-btn-primary" type="button" data-menu-close>Close</button>
      </div>
    </dialog>
    <dialog id="st-library-dialog" class="st-dialog st-library-dialog" aria-labelledby="st-library-title">
      <div class="st-dialog-head">
        <h2 id="st-library-title">Your videos</h2>
        <button class="st-icon-btn" type="button" data-library-close data-icon="x" aria-label="Close video list"></button>
      </div>
      <div class="st-dialog-body">
        <div id="st-library-host" class="st-library-host" style="display:grid;gap:12px"></div>
      </div>
      <div class="st-dialog-foot">
        <button id="st-library-import" class="st-btn st-btn-ghost" type="button">Import a new video</button>
        <button class="st-btn st-btn-primary" type="button" data-library-close>Close</button>
      </div>
    </dialog>
  `;
  paintIcons(root);

  const dom = {
    main: root.querySelector("#st-main"),
    menu: root.querySelector("#st-menu-dialog"),
    menuOpen: root.querySelector("#st-menu-open"),
    menuTabs: Array.from(root.querySelectorAll("[data-menu-tab]")),
    menuPanels: {
      setup: root.querySelector("#st-menu-setup"),
      settings: root.querySelector("#st-menu-settings"),
    },
    setupHost: root.querySelector("#st-setup-host"),
    currentName: root.querySelector("#st-current-name"),
    currentStatus: root.querySelector("#st-current-status"),
    editReady: root.querySelector("#st-edit-ready"),
    editFinish: root.querySelector("#st-edit-finish"),
    editShortcuts: root.querySelector("#st-edit-shortcuts-open"),
    dialogJob: root.querySelector("#st-dialog-job"),
    forget: root.querySelector("#st-forget-video"),
    change: root.querySelector("#st-change-video"),
    steps: Array.from(root.querySelectorAll(".st-step")),
    notice: root.querySelector("#st-rail-notice"),
    progress: root.querySelector("#st-top-progress"),
    progressFill: root.querySelector("#st-top-progress-fill"),
    progressText: root.querySelector("#st-top-progress-text"),
    readingAction: root.querySelector("#st-top-reading-action"),
    library: root.querySelector("#st-library-dialog"),
    libraryHost: root.querySelector("#st-library-host"),
    libraryImport: root.querySelector("#st-library-import"),
  };
  let jobState = { ...EMPTY_STATE };
  let watchTimer = 0;
  let watchSeq = 0;
  let noticeTimer = 0;
  let libraryUi = null;
  let finishFocus = null;
  let lastJobCheck = 0;
  let lastJobUpdated = "";

  function renderJob() {
    const name = currentJob?.name || (currentJob?.id ? `Video ${currentJob.id}` : "");
    dom.currentName.textContent = name || "No video open";
    dom.currentName.title = currentJob?.id || "";
    const status = statusWord(currentJob?.status);
    dom.currentStatus.hidden = activeStep === "edit" || !status;
    dom.currentStatus.textContent = status;
    dom.currentStatus.dataset.tone = currentJob?.status === "ready" ? "ok"
      : currentJob?.status === "failed" ? "bad" : "quiet";
    dom.currentStatus.title = "";
    if (currentJob && jobState.jobId === currentJob.id && jobState.sourceMissing) {
      // Said where the creator looks first, not only on a locked step.
      dom.currentStatus.hidden = activeStep === "edit" ? true : false;
      dom.currentStatus.textContent = "Original file missing";
      dom.currentStatus.dataset.tone = "bad";
      dom.currentStatus.title = jobState.sourceMissing;
    }
    dom.dialogJob.textContent = currentJob
      ? `${name || currentJob.id}${status ? ` · ${status}` : ""}`
      : "No video open.";
    dom.forget.disabled = !currentJob;
    // No video open: there is nothing to change. Import is the one action.
    dom.change.hidden = !currentJob;
    const known = Boolean(currentJob) && jobState.jobId === currentJob.id;
    const reading = known && isReading(jobState.status);
    const action = known ? readingAction(jobState.status) : null;
    // Import carries the same Cancel reading control. Keep one visible surface.
    const duplicate = activeStep === "import";
    dom.progress.hidden = !action;
    if (reading) {
      const percent = Math.max(0, Math.min(100, Math.round(Number(jobState.progress || 0) * 100)));
      dom.progressFill.style.width = `${percent}%`;
      dom.progressText.textContent = `Reading the video · ${percent}%${jobState.message ? ` · ${jobState.message}` : ""}`;
    } else if (action) {
      dom.progressFill.style.width = "0%";
      dom.progressText.textContent = STOPPED.has(jobState.status)
        ? "Reading stopped. Other videos can read now."
        : "Reading this video failed.";
    }
    dom.readingAction.hidden = !action || duplicate;
    if (action && !dom.readingAction.dataset.busy) {
      dom.readingAction.textContent = action.label;
      dom.readingAction.dataset.kind = action.kind;
    }
  }

  async function readingButton() {
    const jobId = currentJob?.id;
    const kind = dom.readingAction.dataset.kind;
    if (!jobId || !kind || dom.readingAction.dataset.busy) return;
    dom.readingAction.dataset.busy = "1";
    dom.readingAction.disabled = true;
    dom.readingAction.textContent = kind === "cancel" ? "Stopping…" : "Starting…";
    try {
      await request(`/api/jobs/${encodeURIComponent(jobId)}/reading/${kind}`, { method: "POST", body: {} });
    } catch (error) {
      showNotice(error?.message || (kind === "cancel" ? "Could not stop reading." : "Could not read this video again."));
    } finally {
      delete dom.readingAction.dataset.busy;
      dom.readingAction.disabled = false;
      await refreshState();
    }
  }

  // ------------------------------------------------------------ step state

  function stepGate(stepId) {
    if (stepId === "import") return "";
    if (!currentJob) return "Open or import a video first.";
    if (jobState.jobId !== currentJob.id || !jobState.loaded) return "";
    if (jobState.missing) return "This video is no longer on file. Choose another one.";
    if (jobState.sourceMissing) return jobState.sourceMissing;
    if (jobState.status === "failed" || jobState.status === "error") {
      return "Reading this video failed. Press Read again at the top, or import it again.";
    }
    if (STOPPED.has(jobState.status)) {
      return "Reading was stopped. Press Read again at the top.";
    }
    if (isReading(jobState.status)) {
      const percent = Math.round(Number(jobState.progress || 0) * 100);
      return `Wait for the video to finish reading (${percent}%).`;
    }
    if ((stepId === "edit" || stepId === "finish") && jobState.stories === 0) {
      return "Pick moments first. Open Moments and press Find moments.";
    }
    return "";
  }

  function stepStatus(stepId) {
    const known = currentJob && jobState.jobId === currentJob.id && jobState.loaded;
    if (stepGate(stepId)) {
      if (!currentJob) return { state: "locked", text: "Needs a video" };
      if (isReading(jobState.status)) return { state: "locked", text: "Waits for reading" };
      if (STOPPED.has(jobState.status)) return { state: "locked", text: "Reading stopped" };
      if (jobState.sourceMissing) return { state: "locked", text: "Original file missing" };
      if (stepId === "edit" || stepId === "finish") return { state: "locked", text: "Needs moments" };
      return { state: "locked", text: "Not available" };
    }
    if (!known) return { state: "open", text: STEPS.find((step) => step.id === stepId)?.note || "" };
    if (stepId === "import") {
      if (isReading(jobState.status)) {
        return { state: "working", text: `Reading ${Math.round(Number(jobState.progress || 0) * 100)}%` };
      }
      if (STOPPED.has(jobState.status)) return { state: "open", text: "Reading stopped" };
      if (jobState.status === "failed" || jobState.status === "error") return { state: "open", text: "Reading failed" };
      if (jobState.sourceMissing) return { state: "open", text: "Original file missing" };
      return { state: "done", text: "Video ready" };
    }
    if (stepId === "moments") {
      if (jobState.stories) {
        return { state: "done", text: `${jobState.stories} ${jobState.stories === 1 ? "moment" : "moments"} ready` };
      }
      return { state: "open", text: "Find or build a moment" };
    }
    return { state: "open", text: STEPS.find((step) => step.id === stepId)?.note || "" };
  }

  function renderRail() {
    for (const button of dom.steps) {
      const status = stepStatus(button.dataset.step);
      button.dataset.state = status.state;
      const small = button.querySelector(".st-step-copy small");
      if (small) small.textContent = status.text;
      const gate = stepGate(button.dataset.step);
      button.setAttribute("aria-disabled", gate ? "true" : "false");
      button.title = gate || "";
    }
  }

  function showNotice(message) {
    if (noticeTimer) window.clearTimeout(noticeTimer);
    dom.notice.textContent = message;
    dom.notice.hidden = !message;
    if (message) noticeTimer = window.setTimeout(() => { dom.notice.hidden = true; }, 6000);
  }

  function bestStep() {
    return bestStepFor(Boolean(currentJob), jobState);
  }

  function scheduleWatch(delay) {
    if (watchTimer) window.clearTimeout(watchTimer);
    watchTimer = window.setTimeout(() => {
      void refreshState({ light: true, watch: true });
    }, delay);
  }

  /**
   * On the watcher's slow beat, read the full job with `fresh: true` and
   * compare its `updated` stamp. A changed stamp means another writer (a
   * render, Check or a second tab) changed the job; api.js drops its derived
   * reads and the read-only screens reopen on the new data.
   */
  async function checkJobUpdated(jobId) {
    const now = Date.now();
    if (now - lastJobCheck < JOB_RECHECK_MS) return { changed: false, stamp: "" };
    lastJobCheck = now;
    try {
      const fresh = await getJob(jobId, { fresh: true });
      const stamp = jobUpdatedAt(fresh);
      const changed = Boolean(lastJobUpdated && stamp && stamp !== lastJobUpdated);
      lastJobUpdated = stamp;
      return { changed, stamp };
    } catch (_) {
      return { changed: false, stamp: "" };
    }
  }

  /**
   * Re-read the job's step state. `light` (the idle watcher, step changes)
   * reads only the status once the video is ready and nothing runs, reusing
   * the last Check and Stories answers; panels call ctx.refreshSteps() after
   * they change those. The watcher adds one full job read every 150 s so an
   * external `updated` change invalidates the shared read cache.
   */
  async function refreshState({ light = false, watch = false } = {}) {
    if (watchTimer) window.clearTimeout(watchTimer);
    watchTimer = 0;
    const jobId = currentJob?.id || "";
    const seq = ++watchSeq;
    if (!jobId) {
      jobState = { ...EMPTY_STATE };
      renderJob();
      renderRail();
      return jobState;
    }
    const next = {
      ...EMPTY_STATE, jobId, loaded: true,
      updatedAt: jobState.jobId === jobId ? jobState.updatedAt : "",
    };
    try {
      const status = await getJobStatus(jobId);
      next.status = String(status?.status || "");
      next.progress = Number(status?.progress || 0);
      next.message = String(status?.message || "");
      next.sourceMissing = status?.source_missing ? String(status.source_missing_message || "") : "";
      const statusStamp = jobUpdatedAt(status);
      if (statusStamp) next.updatedAt = statusStamp;
    } catch (error) {
      if (error?.status === 404) next.missing = true;
      else next.loaded = false;
    }
    const cachedStamp = cachedJobStamp(jobId);
    if (cachedStamp) lastJobUpdated = cachedStamp;
    if (canReuseSteps(jobState, jobId, next.status, light)) {
      next.check = jobState.check;
      next.stories = jobState.stories;
    } else if (next.status === "ready") {
      const [check, sets] = await Promise.allSettled([
        request(`/api/jobs/${encodeURIComponent(jobId)}/check`),
        listClipSets(jobId),
      ]);
      if (check.status === "fulfilled") next.check = checkState(check.value);
      else if (check.reason?.status === 202) next.check = "running";
      else next.check = "none";
      if (sets.status === "fulfilled") {
        const records = Array.isArray(sets.value?.clip_sets) ? sets.value.clip_sets : [];
        // Every set counts, the full video too: each one can be edited and rendered.
        next.stories = records.reduce((total, record) => total + Number(record?.stories?.length || 0), 0);
      }
    }
    if (seq !== watchSeq || jobId !== (currentJob?.id || "")) return jobState;
    const previous = jobState;
    jobState = next;
    if (next.status && next.status !== currentJob.status) updateJob({ status: next.status });
    renderJob();
    renderRail();
    // A screen opened while the video was still reading never sits on a
    // stale "still being read": reopen it once reading finishes.
    if (previous.jobId === jobId && isReading(previous.status) && !isReading(next.status)) {
      if (activeStep === "import" && next.status === "ready") go("moments");
      else activate(activeStep, { focus: false, force: true });
    }
    if (watch && next.loaded && next.status === "ready" && jobId === (currentJob?.id || "")) {
      const { changed, stamp } = await checkJobUpdated(jobId);
      if (stamp) jobState.updatedAt = stamp;
      if (changed && jobId === (currentJob?.id || "")) {
        // The fresh job is already cached; drop only derived reads.
        invalidateReadCache(jobId, { keepJob: true });
        if (activeStep === "moments") {
          activate(activeStep, { focus: false, force: true });
        }
      }
    }
    const busy = isReading(next.status) || next.check === "running" || !next.loaded;
    scheduleWatch(busy ? WATCH_BUSY_MS : WATCH_IDLE_MS);
    return jobState;
  }

  // --------------------------------------------------------- video library
  //
  // The dialog body is the finished/sources library component. It keeps one
  // list, one search box and one set of tabs; the shell only opens it and
  // forwards the current job.

  function ensureLibrary() {
    if (!libraryUi) libraryUi = mountLibrary(dom.libraryHost, ctx) || null;
    return libraryUi;
  }

  function openLibrary() {
    ensureLibrary();
    // Change video is choosing a source, not reopening a finished cut.
    libraryUi?.setTab?.(SOURCES_TAB);
    if (typeof dom.library.showModal === "function") dom.library.showModal();
    else dom.library.setAttribute("open", "");
    void libraryUi?.refresh();
    requestAnimationFrame(() => {
      dom.libraryHost.querySelector("#st-library-search")?.focus();
    });
  }

  async function openJobAndContinue(id, meta = {}) {
    setJob({ ...meta, id });
    jobState = { ...EMPTY_STATE };
    renderRail();
    await refreshState();
    go(bestStep(), { force: true });
  }

  function setJob(value) {
    const previousId = currentJob?.id || "";
    if (value && value.id) {
      const same = currentJob && currentJob.id === value.id;
      currentJob = same ? { ...currentJob, ...value } : { ...value };
    } else {
      currentJob = null;
    }
    if ((currentJob?.id || "") !== previousId) {
      lastJobCheck = 0;
      lastJobUpdated = "";
    }
    writeJob(currentJob);
    renderJob();
  }

  function updateJob(patch) {
    if (!currentJob) return;
    currentJob = { ...currentJob, ...(patch || {}) };
    writeJob(currentJob);
    renderJob();
  }

  function setActive(stepId) {
    for (const button of dom.steps) {
      const active = button.dataset.step === stepId;
      if (active) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    }
    const step = STEPS.find((item) => item.id === stepId);
    document.title = `${step?.label || "Studio"} · VibeCut Studio`;
    if (dom.editReady) dom.editReady.hidden = stepId !== "edit";
    if (dom.editFinish) dom.editFinish.hidden = stepId !== "edit";
    if (dom.editShortcuts) dom.editShortcuts.hidden = stepId !== "edit";
    renderJob();
  }

  function activate(stepId, { focus = true, force = false } = {}) {
    const step = STEPS.find((item) => item.id === stepId);
    if (!step || (step.id === activeStep && !force)) {
      if (step && !focus) setActive(step.id);
      return;
    }
    if (typeof cleanup === "function") {
      try {
        cleanup();
      } catch (_) {
        /* A panel teardown must never block navigation. */
      }
    }
    cleanup = null;
    activeStep = step.id;
    dom.main.dataset.step = step.id;
    setActive(step.id);
    dom.main.replaceChildren();
    try {
      cleanup = step.mount(dom.main, ctx) || null;
    } catch (error) {
      dom.main.append(el("div", { class: "st-card st-empty" }, [
        el("h2", { text: "This screen could not open" }),
        el("p", { text: error?.message || "Reload the page to try again." }),
      ]));
    }
    if (focus) {
      requestAnimationFrame(() => dom.main.focus({ preventScroll: true }));
    }
  }

  let leaveGuard = null;

  async function go(stepId, options = {}) {
    if (!STEP_IDS.has(stepId)) return;
    if (activeStep === "edit" && stepId !== "edit" && leaveGuard) {
      const allowed = await leaveGuard();
      if (!allowed) return;
    }
    const gate = stepGate(stepId);
    if (gate && !options.force) {
      showNotice(gate);
      return;
    }
    showNotice("");
    const hash = `#/${stepId}`;
    if (location.hash !== hash) history.pushState(null, "", hash);
    activate(stepId, options);
  }

  const ctx = {
    setLeaveGuard: (fn) => { leaveGuard = typeof fn === "function" ? fn : null; },
    getJobId: () => currentJob?.id || "",
    getJob: () => (currentJob ? { ...currentJob } : null),
    openJob: (id, meta = {}) => {
      const changed = currentJob?.id !== id;
      setJob({ ...meta, id });
      if (changed) jobState = { ...EMPTY_STATE };
      void refreshState();
    },
    // Open a video and move to the step where its work continues.
    openJobAndContinue: (id, meta = {}) => openJobAndContinue(id, meta),
    // Open a finished cut's job on Finish, on that cut's story and shape.
    // The hash stays `#/<step>`; the story, shape and cut travel as a
    // one-time focus that Finish takes when it mounts.
    openFinished: (artifact = {}) => {
      const id = String(artifact.job_id || "");
      if (!id) return;
      finishFocus = finishFocusFrom(artifact);
      setJob({
        id,
        name: artifact.job_title || artifact.source_label || "",
      });
      jobState = { ...EMPTY_STATE };
      renderRail();
      void refreshState();
      go("finish", { force: true });
    },
    // Finish calls this once on mount; the focus applies to that job only.
    takeFinishFocus: (jobId) => {
      const focus = finishFocus;
      finishFocus = null;
      return focus && focus.jobId === String(jobId || "") ? focus : null;
    },
    refreshSteps: () => refreshState(),
    getStepState: () => ({ ...jobState }),
    updateJob,
    clearJob: () => {
      setJob(null);
      go("import");
    },
    openLibrary: () => openLibrary(),
    // A deleted video may be the open one, and then it is gone from every step.
    jobDeleted: (id) => {
      if (currentJob?.id === id) ctx.clearJob();
    },
    go: (stepId, options) => go(stepId, options),
  };

  for (const button of dom.steps) {
    button.addEventListener("click", () => go(button.dataset.step));
  }
  dom.change.addEventListener("click", () => {
    closeMenu();
    openLibrary();
  });
  dom.readingAction.addEventListener("click", () => { void readingButton(); });
  for (const button of root.querySelectorAll("[data-library-close]")) {
    button.addEventListener("click", () => dom.library.close());
  }
  dom.library.addEventListener("click", (event) => {
    if (event.target === dom.library) dom.library.close();
  });
  dom.libraryImport.addEventListener("click", () => {
    dom.library.close();
    go("import", { force: true });
  });
  root.querySelector(".st-skip")?.addEventListener("click", (event) => {
    event.preventDefault();
    dom.main.focus();
  });

  let menuTab = "setup";

  function mountSetupPanel() {
    if (!dom.setupHost) return;
    if (typeof setupCleanup === "function") {
      try {
        setupCleanup();
      } catch (_) {
        /* A refresh replaces the old setup tree anyway. */
      }
    }
    setupCleanup = mountSetup(dom.setupHost, ctx) || null;
  }

  function selectMenuTab(name, { focus = false } = {}) {
    if (!dom.menuPanels[name]) return;
    menuTab = name;
    for (const button of dom.menuTabs) {
      const active = button.dataset.menuTab === name;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    }
    for (const [key, panel] of Object.entries(dom.menuPanels)) {
      panel.hidden = key !== name;
    }
    if (name === "setup") mountSetupPanel();
    if (focus) dom.menuTabs.find((button) => button.dataset.menuTab === name)?.focus();
  }

  function openMenu() {
    renderJob();
    selectMenuTab(menuTab);
    if (typeof dom.menu.showModal === "function") dom.menu.showModal();
    else dom.menu.setAttribute("open", "");
    requestAnimationFrame(() => {
      dom.menuTabs.find((button) => button.dataset.menuTab === menuTab)?.focus();
    });
  }

  function closeMenu() {
    if (typeof dom.menu.close === "function") dom.menu.close();
    else dom.menu.removeAttribute("open");
  }

  dom.menuOpen.addEventListener("click", openMenu);
  for (const button of dom.menuTabs) {
    button.addEventListener("click", () => selectMenuTab(button.dataset.menuTab));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = dom.menuTabs.indexOf(button);
      let next = index;
      if (event.key === "ArrowLeft") next = (index - 1 + dom.menuTabs.length) % dom.menuTabs.length;
      if (event.key === "ArrowRight") next = (index + 1) % dom.menuTabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = dom.menuTabs.length - 1;
      selectMenuTab(dom.menuTabs[next].dataset.menuTab, { focus: true });
    });
  }
  for (const button of root.querySelectorAll("[data-menu-close]")) {
    button.addEventListener("click", closeMenu);
  }
  dom.menu.addEventListener("click", (event) => {
    if (event.target === dom.menu) closeMenu();
  });
  dom.menu.addEventListener("close", () => {
    if (typeof setupCleanup === "function") setupCleanup();
    setupCleanup = null;
    dom.setupHost?.replaceChildren();
  });
  dom.forget.addEventListener("click", () => {
    closeMenu();
    ctx.clearJob();
  });

  document.body.classList.add("st-active");
  for (const node of document.body.children) {
    if (node === root || node.tagName === "SCRIPT") continue;
    node.inert = true;
  }

  window.addEventListener("hashchange", () => {
    const step = routeFromHash();
    if (step) activate(step);
    void refreshState({ light: true });
  });
  window.addEventListener("popstate", () => {
    const step = routeFromHash();
    if (step) activate(step);
  });

  renderJob();
  renderRail();
  // `?studio=1` only opts in; once Studio runs it should not stay in the URL.
  const params = new URLSearchParams(location.search);
  if (params.has("studio")) {
    params.delete("studio");
    const query = params.toString();
    history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
  }
  const hashed = routeFromHash();
  if (hashed || !currentJob) {
    void refreshState();
    // No video open: a stale #/finish from the last video must not win.
    const initial = currentJob ? (hashed || "import") : "import";
    if (location.hash !== `#/${initial}`) history.replaceState(null, "", `#/${initial}`);
    activate(initial, { focus: false });
  } else {
    // A reload with a video open resumes where its work continues, the same
    // rule the video library uses, instead of always landing on Import.
    void openJobAndContinue(currentJob.id, currentJob);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startStudio, { once: true });
} else {
  startStudio();
}
