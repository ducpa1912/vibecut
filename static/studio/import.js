/**
 * Studio — Import.
 *
 * Works on the existing ingest routes:
 *   POST /api/jobs/upload
 *   POST /api/jobs/path
 *   POST /api/jobs/from-url
 *   GET  /api/jobs
 *
 * Rights attestation is a required gate before any import starts. The note is
 * sent with the import and stored on the job (`job.rights`, source "import"),
 * where Check and Clean read it; the browser copy is only a convenience.
 */

import {
  createJobFromPath,
  createJobFromUrl,
  listJobs,
  uploadVideo,
} from "./api.js";
import {
  el,
  formatBytes,
  formatDuration,
  setStatus,
  shortDate,
  statusText,
  statusTone,
} from "./ui.js";

const ATTEST_PREFIX = "vibecut.studio.attested.";

export function rememberAttestation(jobId) {
  try {
    localStorage.setItem(ATTEST_PREFIX + jobId, String(Date.now()));
  } catch (_) {
    /* A private window may refuse storage; the import still proceeds. */
  }
}

export function hasAttestation(jobId) {
  try {
    return Boolean(localStorage.getItem(ATTEST_PREFIX + jobId));
  } catch (_) {
    return false;
  }
}

const VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg"];

function looksLikeVideo(file) {
  if (!file) return false;
  if (file.type && file.type.startsWith("video/")) return true;
  const name = String(file.name || "").toLowerCase();
  return VIDEO_EXTENSIONS.some((extension) => name.endsWith(extension));
}

function nameFromPath(path) {
  const parts = String(path || "").split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "Video";
}

function nameFromUrl(value) {
  try {
    const url = new URL(value);
    const parts = url.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : url.hostname;
  } catch (_) {
    return "Link";
  }
}

function validHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_) {
    return false;
  }
}

export function mount(root, ctx) {
  let source = "file";
  let selectedFile = null;
  let busy = false;
  let disposed = false;
  let recentRequest = 0;
  let recentTimer = 0;

  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-import-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 1 · Import</p>
        <h1 id="st-import-title">Bring in a video</h1>
        <p class="st-lede">Choose a file, a path on this Mac, or a link. The video stays on this machine.</p>
      </header>

      <div class="st-import-grid">
        <div class="st-card st-import-card">
          <div class="st-source-tabs" role="tablist" aria-label="Where the video comes from">
            <button type="button" role="tab" id="st-tab-file" aria-controls="st-source-file" aria-selected="true" tabindex="0" data-source="file">File</button>
            <button type="button" role="tab" id="st-tab-path" aria-controls="st-source-path" aria-selected="false" tabindex="-1" data-source="path">Path</button>
            <button type="button" role="tab" id="st-tab-url" aria-controls="st-source-url" aria-selected="false" tabindex="-1" data-source="url">Link</button>
          </div>

          <div id="st-source-file" role="tabpanel" aria-labelledby="st-tab-file" class="st-source-panel">
            <div id="st-dropzone" class="st-dropzone" role="button" tabindex="0" aria-label="Choose a video file">
              <span class="st-drop-icon" aria-hidden="true">↓</span>
              <strong>Drop a video here</strong>
              <span>or choose a file from this Mac</span>
              <input id="st-file-input" type="file" accept="video/*,.mkv,.avi,.mpg,.mpeg" aria-label="Choose a video file" hidden>
            </div>
            <div id="st-file-card" class="st-file-card" hidden>
              <span class="st-file-glyph" aria-hidden="true">▶</span>
              <span class="st-file-copy"><strong id="st-file-name"></strong><span id="st-file-size"></span></span>
              <button id="st-file-clear" class="st-icon-btn" type="button" aria-label="Remove chosen file">×</button>
            </div>
          </div>

          <div id="st-source-path" role="tabpanel" aria-labelledby="st-tab-path" class="st-source-panel" hidden>
            <label class="st-field" for="st-path-input">
              <span>Full path on this Mac</span>
              <input id="st-path-input" type="text" spellcheck="false" autocomplete="off" placeholder="/Users/you/Movies/long-video.mp4">
            </label>
            <p class="st-hint">The file is read in place. Nothing is uploaded or copied.</p>
          </div>

          <div id="st-source-url" role="tabpanel" aria-labelledby="st-tab-url" class="st-source-panel" hidden>
            <label class="st-field" for="st-url-input">
              <span>Video link</span>
              <input id="st-url-input" type="url" inputmode="url" spellcheck="false" autocomplete="off" placeholder="https://…">
            </label>
            <p class="st-hint">Most sites work through the local downloader. Link downloads need a connection.</p>
          </div>

          <fieldset class="st-options">
            <legend>What to read</legend>
            <div class="st-options-grid">
              <label class="st-check"><input id="st-opt-ocr" type="checkbox" checked><span><strong>Text and faces</strong><small>Apple Vision · on this Mac</small></span></label>
              <label class="st-check"><input id="st-opt-transcribe" type="checkbox" checked><span><strong>Speech</strong><small>word timing for captions</small></span></label>
              <label class="st-check"><input id="st-opt-crop" type="checkbox" checked><span><strong>Smart crop</strong><small>follows the subject</small></span></label>
              <label class="st-check"><input id="st-opt-track" type="checkbox" checked><span><strong>Track crop</strong><small>smooths the move</small></span></label>
            </div>
          </fieldset>

          <label class="st-attest">
            <input id="st-attest" type="checkbox">
            <span><strong>I own this footage or have permission to edit it.</strong><small>Required. VibeCut will not remove platform watermarks.</small></span>
          </label>

          <div class="st-actions">
            <button id="st-import" class="st-btn st-btn-primary" type="button" disabled>Import video</button>
            <span id="st-import-note" class="st-hint">Confirm the rights note to start.</span>
          </div>
          <div class="st-progress" id="st-progress" hidden>
            <div class="st-progress-bar"><i id="st-progress-fill"></i></div>
            <span id="st-progress-text" class="st-mono"></span>
          </div>
          <p id="st-import-status" class="st-status" role="status" aria-live="polite" hidden></p>
          <p id="st-import-error" class="st-error" role="alert" hidden></p>
        </div>

        <aside class="st-card st-recent-card" aria-labelledby="st-recent-title">
          <div class="st-card-head">
            <h2 id="st-recent-title">Recent videos</h2>
            <button id="st-recent-refresh" class="st-btn st-btn-quiet" type="button">Refresh</button>
          </div>
          <div id="st-recent-list" class="st-recent-list">
            <p class="st-hint">Loading recent videos…</p>
          </div>
          <p id="st-recent-error" class="st-error" role="alert" hidden></p>
        </aside>
      </div>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    tabs: Array.from(root.querySelectorAll("[role=tab]")),
    panels: {
      file: $("#st-source-file"),
      path: $("#st-source-path"),
      url: $("#st-source-url"),
    },
    dropzone: $("#st-dropzone"),
    fileInput: $("#st-file-input"),
    fileCard: $("#st-file-card"),
    fileName: $("#st-file-name"),
    fileSize: $("#st-file-size"),
    fileClear: $("#st-file-clear"),
    pathInput: $("#st-path-input"),
    urlInput: $("#st-url-input"),
    ocr: $("#st-opt-ocr"),
    transcribe: $("#st-opt-transcribe"),
    crop: $("#st-opt-crop"),
    track: $("#st-opt-track"),
    attest: $("#st-attest"),
    submit: $("#st-import"),
    note: $("#st-import-note"),
    progress: $("#st-progress"),
    progressFill: $("#st-progress-fill"),
    progressText: $("#st-progress-text"),
    status: $("#st-import-status"),
    error: $("#st-import-error"),
    recentList: $("#st-recent-list"),
    recentError: $("#st-recent-error"),
    recentRefresh: $("#st-recent-refresh"),
  };

  function showError(message) {
    setStatus(dom.error, message, "bad");
  }

  function clearError() {
    setStatus(dom.error, "");
  }

  function currentOptions() {
    return {
      ocr: dom.ocr.checked,
      transcribe: dom.transcribe.checked,
      smart_crop: dom.crop.checked,
      crop_tracking: dom.track.checked,
    };
  }

  function selectedDisplayName() {
    if (source === "file") return selectedFile ? selectedFile.name : "";
    if (source === "path") return nameFromPath(dom.pathInput.value.trim());
    return nameFromUrl(dom.urlInput.value.trim());
  }

  function selectionReady() {
    if (source === "file") return Boolean(selectedFile);
    if (source === "path") return Boolean(dom.pathInput.value.trim());
    return validHttpUrl(dom.urlInput.value.trim());
  }

  function syncSubmit() {
    const ready = selectionReady();
    const reading = currentlyReading();
    dom.submit.disabled = busy || reading || !ready || !dom.attest.checked;
    if (busy) return;
    if (reading) {
      dom.note.textContent = "A video is reading now. Import the next one when it finishes, or press Cancel reading at the top.";
    } else if (!dom.attest.checked) {
      dom.note.textContent = "Confirm the rights note to start.";
    } else if (!ready) {
      dom.note.textContent = source === "file"
        ? "Choose a video file."
        : source === "path"
          ? "Enter a full path."
          : "Enter a full link starting with http:// or https://.";
    } else {
      dom.note.textContent = "Import starts reading the video. Stories unlock when it finishes.";
    }
  }

  function setBusy(value) {
    busy = value;
    dom.submit.textContent = value ? "Importing…" : "Import video";
    for (const control of [dom.dropzone, dom.fileInput, dom.fileClear, dom.pathInput, dom.urlInput,
      dom.ocr, dom.transcribe, dom.crop, dom.track, dom.attest, dom.recentRefresh, ...dom.tabs]) {
      if (!control) continue;
      if ("disabled" in control && control !== dom.dropzone) control.disabled = value;
      else if (control === dom.dropzone) control.setAttribute("aria-disabled", value ? "true" : "false");
    }
    if (!value) {
      dom.progress.hidden = true;
      dom.progressFill.style.width = "0%";
      dom.progressText.textContent = "";
    }
    syncSubmit();
  }

  function chooseSource(next) {
    if (!dom.panels[next] || next === source) return;
    source = next;
    for (const tab of dom.tabs) {
      const active = tab.dataset.source === next;
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.tabIndex = active ? 0 : -1;
    }
    for (const [key, panel] of Object.entries(dom.panels)) {
      panel.hidden = key !== next;
    }
    clearError();
    syncSubmit();
    const target = next === "file" ? dom.dropzone : next === "path" ? dom.pathInput : dom.urlInput;
    target?.focus();
  }

  function setFile(file) {
    if (!file) return;
    if (!looksLikeVideo(file)) {
      showError("That file does not look like a video. Choose an MP4, MOV, WebM, MKV, AVI or MPEG file.");
      return;
    }
    selectedFile = file;
    dom.fileName.textContent = file.name;
    dom.fileSize.textContent = formatBytes(file.size);
    dom.fileCard.hidden = false;
    dom.dropzone.hidden = true;
    clearError();
    syncSubmit();
  }

  function clearFile() {
    selectedFile = null;
    dom.fileInput.value = "";
    dom.fileCard.hidden = true;
    dom.dropzone.hidden = false;
    syncSubmit();
    dom.dropzone.focus();
  }

  async function startImport() {
    if (busy) return;
    clearError();
    if (!dom.attest.checked) {
      showError("Confirm that you own this footage or have permission to edit it.");
      dom.attest.focus();
      return;
    }
    if (!selectionReady()) {
      showError(source === "file" ? "Choose a video file first."
        : source === "path" ? "Enter a full path to a video on this Mac."
        : "Enter a full link starting with http:// or https://.");
      return;
    }

    setBusy(true);
    setStatus(dom.status, "Starting import…");
    try {
      const options = currentOptions();
      let created;
      if (source === "file") {
        dom.progress.hidden = false;
        created = await uploadVideo(selectedFile, options, (ratio) => {
          const percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
          dom.progressFill.style.width = `${percent}%`;
          dom.submit.textContent = `Importing… ${percent}%`;
          dom.progressText.textContent = `${percent}%`;
        }, { rights: dom.attest.checked });
      } else if (source === "path") {
        created = await createJobFromPath(dom.pathInput.value.trim(), options, { rights: dom.attest.checked });
      } else {
        created = await createJobFromUrl(dom.urlInput.value.trim(), options, null, { rights: dom.attest.checked });
      }

      if (!created || !created.id) throw new Error("The server did not return a video id.");
      rememberAttestation(created.id);
      if (disposed) return;
      setStatus(dom.status, "Imported. Reading the video now — Check opens by itself when it is ready.", "ok");
      ctx.openJob(created.id, { name: selectedDisplayName(), status: "queued" });
    } catch (error) {
      if (!disposed) showError(error.message || "Could not import this video.");
    } finally {
      if (!disposed) setBusy(false);
    }
  }

  function renderRecent(jobs) {
    dom.recentList.replaceChildren();
    setStatus(dom.recentError, "");
    if (!jobs.length) {
      dom.recentList.append(el("p", { class: "st-hint", text: "No videos yet. Import one to begin." }));
      return;
    }
    for (const job of jobs) {
      const meta = [
        formatDuration(job.duration),
        shortDate(job.created),
      ].filter(Boolean).join(" · ");
      const button = el("button", { class: "st-recent-item", type: "button" }, [
        el("span", { class: "st-recent-copy" }, [
          el("strong", { text: job.name || job.title || job.id }),
          el("span", { text: meta }),
        ]),
        el("span", { class: `st-chip st-chip-${statusTone(job.status)}`, text: statusText(job.status) }),
      ]);
      button.addEventListener("click", () => {
        // Reopen where the work stopped: reading, Check, Stories or Edit.
        ctx.openJobAndContinue(job.id, { name: job.name || "", status: job.status || "" });
      });
      dom.recentList.append(button);
    }
  }

  /** True while the open video is still being read (one import at a time). */
  function currentlyReading() {
    const state = ctx.getStepState?.() || {};
    return Boolean(state.jobId) && state.jobId === ctx.getJobId?.() && isReadingStatus(state.status);
  }

  // Recent videos refresh on their own: every few seconds while one is
  // reading, slower otherwise. Imports from another tab or the API appear.
  function scheduleRecent(jobs) {
    if (recentTimer) window.clearTimeout(recentTimer);
    if (disposed) return;
    const active = (jobs || []).some((job) => isReadingStatus(job?.status));
    recentTimer = window.setTimeout(() => { void loadRecent({ quiet: true }); }, active ? 4000 : 20000);
  }

  async function loadRecent({ quiet = false } = {}) {
    const ticket = ++recentRequest;
    if (!quiet) {
      setStatus(dom.recentError, "");
      dom.recentList.replaceChildren(el("p", { class: "st-hint", text: "Loading recent videos…" }));
    }
    try {
      const data = await listJobs({ limit: 8 });
      if (disposed || ticket !== recentRequest) return;
      const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
      renderRecent(jobs);
      syncSubmit();
      scheduleRecent(jobs);
    } catch (error) {
      if (disposed || ticket !== recentRequest) return;
      dom.recentList.replaceChildren(el("p", { class: "st-hint", text: "Recent videos are unavailable." }));
      setStatus(dom.recentError, error.message || "Could not load recent videos.", "bad");
    }
  }

  // ---- events -------------------------------------------------------------

  for (const tab of dom.tabs) {
    tab.addEventListener("click", () => chooseSource(tab.dataset.source));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = dom.tabs.indexOf(tab);
      let next = index;
      if (event.key === "ArrowLeft") next = (index - 1 + dom.tabs.length) % dom.tabs.length;
      if (event.key === "ArrowRight") next = (index + 1) % dom.tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = dom.tabs.length - 1;
      const target = dom.tabs[next];
      chooseSource(target.dataset.source);
      target.focus();
    });
  }

  dom.dropzone.addEventListener("click", () => dom.fileInput.click());
  dom.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      dom.fileInput.click();
    }
  });
  dom.dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!busy) dom.dropzone.classList.add("is-over");
  });
  dom.dropzone.addEventListener("dragleave", () => dom.dropzone.classList.remove("is-over"));
  dom.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dom.dropzone.classList.remove("is-over");
    if (busy) return;
    const file = event.dataTransfer?.files?.[0];
    if (file) setFile(file);
  });
  dom.fileInput.addEventListener("change", () => setFile(dom.fileInput.files?.[0] || null));
  dom.fileClear.addEventListener("click", clearFile);
  dom.pathInput.addEventListener("input", syncSubmit);
  dom.urlInput.addEventListener("input", syncSubmit);
  dom.urlInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!dom.submit.disabled) startImport();
    }
  });
  dom.pathInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!dom.submit.disabled) startImport();
    }
  });
  dom.attest.addEventListener("change", syncSubmit);
  dom.submit.addEventListener("click", startImport);
  dom.recentRefresh.addEventListener("click", () => { void loadRecent(); });

  syncSubmit();
  loadRecent();

  return () => {
    disposed = true;
    if (recentTimer) window.clearTimeout(recentTimer);
  };
}

/** Statuses that mean the video is still being read. */
export function isReadingStatus(status) {
  return ["queued", "downloading", "scanning", "reading", "scoring"].includes(String(status || ""));
}
