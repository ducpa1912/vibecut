/**
 * VibeCut Studio — shell.
 *
 * Five steps: Import · Check · Stories · Edit · Finish.
 * Native ES modules, no build step, no new backend routes.
 *
 * Classic stays whole. This app is an overlay; Settings → "Use Classic editor"
 * saves the choice in this browser and reopens the Classic page.
 */

import { mount as mountImport } from "./import.js";
import { mount as mountCheck } from "./check.js";
import { mount as mountStories } from "./stories.js";
import { mount as mountEdit } from "./edit.js";
import { mount as mountFinish } from "./finish.js";
import { mount as mountSetup } from "./setup.js";
import { getJobStatus, listClipSets, listJobs, request } from "./api.js";
import { el, formatDuration, shortDate, statusText, statusTone } from "./ui.js";

const JOB_KEY = "vibecut.studio.job";
const EDITOR_KEY = "vibecut.editor";

const STEPS = [
  { id: "import", label: "Import", note: "Bring in a video", mount: mountImport },
  { id: "check", label: "Check", note: "Find what it needs", mount: mountCheck },
  { id: "stories", label: "Stories", note: "Pick the moments", mount: mountStories },
  { id: "edit", label: "Edit", note: "Shape each story", mount: mountEdit },
  { id: "finish", label: "Finish", note: "Render and share", mount: mountFinish },
];

const STEP_IDS = new Set(STEPS.map((step) => step.id));
const WATCH_BUSY_MS = 2000;
const WATCH_IDLE_MS = 15000;
const EMPTY_STATE = {
  jobId: "", loaded: false, status: "", progress: 0, message: "",
  check: "none", stories: 0, missing: false, sourceMissing: "",
};

const STOPPED = new Set(["cancelled", "interrupted"]);

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
  if (state?.check === "done") return "stories";
  return "check";
}

/** The top strip's one action: stop a read, or start a stopped one again. */
export function readingAction(status) {
  if (isReading(status)) return { kind: "cancel", label: "Cancel reading" };
  if (STOPPED.has(status) || status === "failed" || status === "error") {
    return { kind: "retry", label: "Read again" };
  }
  return null;
}

function checkState(payload) {
  const state = String(payload?.status || "").toLowerCase();
  if (state === "queued" || state === "running" || payload?.complete === false) return "running";
  if (state === "failed") return "failed";
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
  return STEP_IDS.has(value) ? value : "";
}

function statusWord(status) {
  return status ? statusText(status) : "";
}

export function startStudio() {
  const root = document.getElementById("studio-root");
  if (!root) return;

  if (document.documentElement.dataset.editor === "classic") return;
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
      <aside class="st-rail">
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
        <p id="st-rail-notice" class="st-rail-notice" role="status" aria-live="polite" hidden></p>
        <div class="st-rail-foot">
          <span class="st-local"><i aria-hidden="true"></i>On this Mac</span>
          <button id="st-setup-open" class="st-rail-settings" type="button" aria-haspopup="dialog">Setup</button>
          <button id="st-settings-open" class="st-rail-settings" type="button" aria-haspopup="dialog">Settings</button>
        </div>
      </aside>

      <div class="st-main-wrap">
        <header class="st-top">
          <div class="st-top-job">
            <span class="st-top-label">Current video</span>
            <strong id="st-current-name">No video open</strong>
            <span id="st-current-status" class="st-top-status" hidden></span>
            <div id="st-top-progress" class="st-top-progress" role="status" aria-live="polite" hidden>
              <div class="st-progress-bar"><i id="st-top-progress-fill"></i></div>
              <span id="st-top-progress-text"></span>
              <button id="st-top-reading-action" class="st-btn st-btn-quiet st-btn-small" type="button" hidden></button>
            </div>
          </div>
          <div class="st-top-actions">
            <button id="st-change-video" class="st-btn st-btn-quiet" type="button">Change video</button>
            <button id="st-settings" class="st-icon-btn st-settings-btn" type="button" aria-label="Settings" aria-haspopup="dialog">⚙</button>
          </div>
        </header>
        <main id="st-main" class="st-main" tabindex="-1">
          <p class="st-hint">Opening Studio…</p>
        </main>
      </div>
    </div>
    <dialog id="st-settings-dialog" class="st-dialog" aria-labelledby="st-settings-title">
      <div class="st-dialog-head">
        <h2 id="st-settings-title">Settings</h2>
        <button class="st-icon-btn" type="button" data-dialog-close aria-label="Close settings">×</button>
      </div>
      <div class="st-dialog-body">
        <section class="st-dialog-section">
          <h3>Editor</h3>
          <p>Studio is the new workspace. Classic keeps every older screen, unchanged.</p>
          <a id="st-use-classic" class="st-btn st-btn-ghost" href="/?classic=1">Use Classic editor</a>
          <p class="st-hint">Saved in this browser. Classic opens in a fresh page; an “Open Studio” link brings you back.</p>
        </section>
        <section class="st-dialog-section">
          <h3>Current video</h3>
          <p id="st-dialog-job" class="st-dialog-job">No video open.</p>
          <button id="st-forget-video" class="st-btn st-btn-quiet" type="button">Forget this video</button>
          <p class="st-hint">Forgetting only clears the open video. Nothing is deleted from disk.</p>
        </section>
      </div>
      <div class="st-dialog-foot">
        <button class="st-btn st-btn-primary" type="button" data-dialog-close>Close</button>
      </div>
    </dialog>
    <dialog id="st-library-dialog" class="st-dialog st-library-dialog" aria-labelledby="st-library-title">
      <div class="st-dialog-head">
        <h2 id="st-library-title">Your videos</h2>
        <button class="st-icon-btn" type="button" data-library-close aria-label="Close video list">×</button>
      </div>
      <div class="st-dialog-body">
        <input id="st-library-search" class="st-input" type="search" placeholder="Search by name" aria-label="Search videos">
        <div id="st-library-list" class="st-library-list"></div>
      </div>
      <div class="st-dialog-foot">
        <button id="st-library-import" class="st-btn st-btn-ghost" type="button">Import a new video</button>
        <button class="st-btn st-btn-primary" type="button" data-library-close>Close</button>
      </div>
    </dialog>
    <dialog id="st-setup-dialog" class="st-dialog st-setup-dialog" aria-labelledby="st-setup-title">
      <div class="st-dialog-head">
        <h2 id="st-setup-title">Setup</h2>
        <button class="st-icon-btn" type="button" data-setup-close aria-label="Close setup">×</button>
      </div>
      <div id="st-setup-host" class="st-dialog-body st-setup-host"></div>
      <div class="st-dialog-foot">
        <button class="st-btn st-btn-primary" type="button" data-setup-close>Close</button>
      </div>
    </dialog>
  `;

  const dom = {
    main: root.querySelector("#st-main"),
    settings: root.querySelector("#st-settings-dialog"),
    settingsOpen: root.querySelector("#st-settings-open"),
    settingsTop: root.querySelector("#st-settings"),
    setup: root.querySelector("#st-setup-dialog"),
    setupOpen: root.querySelector("#st-setup-open"),
    setupHost: root.querySelector("#st-setup-host"),
    currentName: root.querySelector("#st-current-name"),
    currentStatus: root.querySelector("#st-current-status"),
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
    librarySearch: root.querySelector("#st-library-search"),
    libraryList: root.querySelector("#st-library-list"),
    libraryImport: root.querySelector("#st-library-import"),
  };
  let jobState = { ...EMPTY_STATE };
  let watchTimer = 0;
  let watchSeq = 0;
  let noticeTimer = 0;
  let libraryTicket = 0;

  function renderJob() {
    const name = currentJob?.name || (currentJob?.id ? `Video ${currentJob.id}` : "");
    dom.currentName.textContent = name || "No video open";
    dom.currentName.title = currentJob?.id || "";
    const status = statusWord(currentJob?.status);
    dom.currentStatus.hidden = !status;
    dom.currentStatus.textContent = status;
    dom.currentStatus.dataset.tone = currentJob?.status === "ready" ? "ok"
      : currentJob?.status === "failed" ? "bad" : "quiet";
    dom.currentStatus.title = "";
    if (currentJob && jobState.jobId === currentJob.id && jobState.sourceMissing) {
      // Said where the creator looks first, not only on a locked step.
      dom.currentStatus.hidden = false;
      dom.currentStatus.textContent = "Original file missing";
      dom.currentStatus.dataset.tone = "bad";
      dom.currentStatus.title = jobState.sourceMissing;
    }
    dom.dialogJob.textContent = currentJob
      ? `${name || currentJob.id}${status ? ` · ${status}` : ""}`
      : "No video open.";
    dom.forget.disabled = !currentJob;
    const known = Boolean(currentJob) && jobState.jobId === currentJob.id;
    const reading = known && isReading(jobState.status);
    const action = known ? readingAction(jobState.status) : null;
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
    dom.readingAction.hidden = !action;
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
      return "Pick stories first. Open Stories and press Find stories.";
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
      if (stepId === "edit" || stepId === "finish") return { state: "locked", text: "Needs stories" };
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
    if (stepId === "check") {
      if (jobState.check === "running") return { state: "working", text: "Checking…" };
      if (jobState.check === "done") return { state: "done", text: "Checked" };
      if (jobState.check === "failed") return { state: "open", text: "Check failed · run again" };
      return { state: "open", text: "Optional · not run" };
    }
    if (stepId === "stories") {
      return jobState.stories
        ? { state: "done", text: `${jobState.stories} ${jobState.stories === 1 ? "story" : "stories"}` }
        : { state: "open", text: "Not picked yet" };
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
    watchTimer = window.setTimeout(() => { void refreshState({ light: true }); }, delay);
  }

  /**
   * Re-read the job's step state. `light` (the idle watcher, step changes)
   * reads only the status once the video is ready and nothing runs, reusing
   * the last Check and Stories answers; panels call ctx.refreshSteps() after
   * they change those. Each poll used to fetch status, check and clip-sets.
   */
  async function refreshState({ light = false } = {}) {
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
    const next = { ...EMPTY_STATE, jobId, loaded: true };
    try {
      const status = await getJobStatus(jobId);
      next.status = String(status?.status || "");
      next.progress = Number(status?.progress || 0);
      next.message = String(status?.message || "");
      next.sourceMissing = status?.source_missing ? String(status.source_missing_message || "") : "";
    } catch (error) {
      if (error?.status === 404) next.missing = true;
      else next.loaded = false;
    }
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
        next.stories = Number(records[0]?.stories?.length || 0);
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
      if (activeStep === "import" && next.status === "ready") go("check");
      else activate(activeStep, { focus: false, force: true });
    }
    const busy = isReading(next.status) || next.check === "running" || !next.loaded;
    scheduleWatch(busy ? WATCH_BUSY_MS : WATCH_IDLE_MS);
    return jobState;
  }

  // --------------------------------------------------------- video library

  function openLibrary() {
    if (typeof dom.library.showModal === "function") dom.library.showModal();
    else dom.library.setAttribute("open", "");
    dom.librarySearch.value = "";
    void loadLibrary("");
    requestAnimationFrame(() => dom.librarySearch.focus());
  }

  async function loadLibrary(query) {
    const ticket = ++libraryTicket;
    dom.libraryList.replaceChildren(el("p", { class: "st-hint", text: "Loading your videos…" }));
    try {
      const data = await listJobs({ query, limit: 30 });
      if (ticket !== libraryTicket) return;
      const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
      dom.libraryList.replaceChildren();
      if (!jobs.length) {
        dom.libraryList.append(el("p", { class: "st-hint", text: query ? "No video matches that name." : "No videos yet. Import one to begin." }));
        return;
      }
      for (const job of jobs) dom.libraryList.append(libraryRow(job));
    } catch (error) {
      if (ticket !== libraryTicket) return;
      dom.libraryList.replaceChildren(el("p", { class: "st-error", text: error?.message || "Could not load your videos." }));
    }
  }

  function libraryRow(job) {
    const current = currentJob?.id === job.id;
    const stories = Array.isArray(job.story_titles) ? job.story_titles.length : 0;
    const meta = [
      formatDuration(job.duration),
      shortDate(job.created),
      stories ? `${stories} ${stories === 1 ? "story" : "stories"}` : "",
    ].filter(Boolean).join(" · ");
    const thumb = job.hook_thumb && !job.source_deleted
      ? el("img", { class: "st-library-thumb", src: job.hook_thumb, alt: "", loading: "lazy" })
      : el("span", { class: "st-library-thumb st-library-thumb-empty", "aria-hidden": "true" });
    const row = el("button", {
      class: `st-library-item${current ? " is-current" : ""}`,
      type: "button",
      "aria-current": current ? "true" : null,
    }, [
      thumb,
      el("span", { class: "st-library-copy" }, [
        el("strong", { text: job.name || job.id }),
        el("span", { text: meta }),
      ]),
      el("span", { class: `st-chip st-chip-${statusTone(job.status)}`, text: current ? "Open now" : statusText(job.status) }),
    ]);
    row.addEventListener("click", () => {
      dom.library.close();
      void openJobAndContinue(job.id, { name: job.name || "", status: job.status || "" });
    });
    return row;
  }

  async function openJobAndContinue(id, meta = {}) {
    setJob({ ...meta, id });
    jobState = { ...EMPTY_STATE };
    renderRail();
    await refreshState();
    go(bestStep(), { force: true });
  }

  function setJob(value) {
    if (value && value.id) {
      const same = currentJob && currentJob.id === value.id;
      currentJob = same ? { ...currentJob, ...value } : { ...value };
    } else {
      currentJob = null;
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

  function go(stepId, options = {}) {
    if (!STEP_IDS.has(stepId)) return;
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
    refreshSteps: () => refreshState(),
    getStepState: () => ({ ...jobState }),
    updateJob,
    clearJob: () => {
      setJob(null);
      go("import");
    },
    go: (stepId, options) => go(stepId, options),
  };

  for (const button of dom.steps) {
    button.addEventListener("click", () => go(button.dataset.step));
  }
  dom.change.addEventListener("click", openLibrary);
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
  let searchTimer = 0;
  dom.librarySearch.addEventListener("input", () => {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadLibrary(dom.librarySearch.value.trim()), 250);
  });
  root.querySelector(".st-skip")?.addEventListener("click", (event) => {
    event.preventDefault();
    dom.main.focus();
  });

  function openSettings() {
    renderJob();
    if (typeof dom.settings.showModal === "function") dom.settings.showModal();
    else dom.settings.setAttribute("open", "");
  }

  function openSetup() {
    if (!dom.setup || !dom.setupHost) return;
    if (typeof setupCleanup === "function") {
      try {
        setupCleanup();
      } catch (_) {
        /* A refresh replaces the old setup tree anyway. */
      }
    }
    setupCleanup = mountSetup(dom.setupHost, ctx) || null;
    if (typeof dom.setup.showModal === "function") dom.setup.showModal();
    else dom.setup.setAttribute("open", "");
  }

  dom.settingsOpen.addEventListener("click", openSettings);
  dom.settingsTop.addEventListener("click", openSettings);
  dom.setupOpen?.addEventListener("click", openSetup);
  for (const button of root.querySelectorAll("[data-setup-close]")) {
    button.addEventListener("click", () => dom.setup.close());
  }
  dom.setup?.addEventListener("close", () => {
    if (typeof setupCleanup === "function") setupCleanup();
    setupCleanup = null;
  });
  dom.setup?.addEventListener("click", (event) => {
    if (event.target === dom.setup) dom.setup.close();
  });
  for (const button of root.querySelectorAll("[data-dialog-close]")) {
    button.addEventListener("click", () => dom.settings.close());
  }
  dom.settings.addEventListener("click", (event) => {
    if (event.target === dom.settings) dom.settings.close();
  });
  dom.forget.addEventListener("click", () => {
    dom.settings.close();
    ctx.clearJob();
  });
  root.querySelector("#st-use-classic")?.addEventListener("click", () => {
    try {
      localStorage.setItem(EDITOR_KEY, "classic");
    } catch (_) {
      /* The query parameter still selects Classic. */
    }
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
    const initial = hashed || "import";
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
