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
import { el, statusText } from "./ui.js";

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
  };

  function renderJob() {
    const name = currentJob?.name || (currentJob?.id ? `Video ${currentJob.id}` : "");
    dom.currentName.textContent = name || "No video open";
    dom.currentName.title = currentJob?.id || "";
    const status = statusWord(currentJob?.status);
    dom.currentStatus.hidden = !status;
    dom.currentStatus.textContent = status;
    dom.currentStatus.dataset.tone = currentJob?.status === "ready" ? "ok"
      : currentJob?.status === "failed" ? "bad" : "quiet";
    dom.dialogJob.textContent = currentJob
      ? `${name || currentJob.id}${status ? ` · ${status}` : ""}`
      : "No video open.";
    dom.forget.disabled = !currentJob;
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

  function activate(stepId, { focus = true } = {}) {
    const step = STEPS.find((item) => item.id === stepId);
    if (!step || step.id === activeStep) {
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
    const hash = `#/${stepId}`;
    if (location.hash !== hash) history.pushState(null, "", hash);
    activate(stepId, options);
  }

  const ctx = {
    getJobId: () => currentJob?.id || "",
    getJob: () => (currentJob ? { ...currentJob } : null),
    openJob: (id, meta = {}) => {
      setJob({ ...meta, id });
    },
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
  dom.change.addEventListener("click", () => go("import"));
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
  });
  window.addEventListener("popstate", () => {
    const step = routeFromHash();
    if (step) activate(step);
  });

  renderJob();
  const initial = routeFromHash() || "import";
  if (location.hash !== `#/${initial}`) history.replaceState(null, "", `#/${initial}`);
  activate(initial, { focus: false });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startStudio, { once: true });
} else {
  startStudio();
}
