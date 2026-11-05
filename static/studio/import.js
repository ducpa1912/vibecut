/**
 * Studio — Import.
 *
 * Works on the existing ingest routes:
 *   POST /api/jobs/upload
 *   POST /api/jobs/path
 *   POST /api/jobs/from-url
 *   GET  /api/jobs
 *
 * The rights lock is a server setting. Import reads `GET /api/rights/policy`
 * and asks for the own-footage tick only while the lock is on. The note is
 * stored on the job (`job.rights`, source "import"); browser storage is never
 * a policy source.
 */

import { paintIcons } from "./edit/icons.js";
import {
  createJobFromPath,
  createJobFromUrl,
  deleteCheck,
  deleteJob,
  listJobs,
  request,
  revealPath,
  uploadVideo,
} from "./api.js";
import {
  deleteVideoButton,
  el,
  formatBytes,
  formatDuration,
  setStatus,
  shortDate,
  statusText,
  statusTone,
} from "./ui.js";

/**
 * The server policy is the only authority. These helpers only read the
 * payload from `GET /api/rights/policy` and `job.rights_policy`.
 *
 * When the policy is still loading (null), the UI keeps the conservative gate
 * and shows the tick. That is a loading fallback, never a policy decision.
 */
export function policyLocked(policy) {
  return policy && typeof policy.lock === "boolean" ? policy.lock : true;
}

export function importNeedsTick(policy) {
  if (!policy) return true;
  if (typeof policy.needs_import_tick === "boolean") return policy.needs_import_tick;
  return policyLocked(policy) && !policy.attested;
}

export function needsRightsTick(policy) {
  return policyLocked(policy) && !policy?.attested;
}

/** The server reason code for one detected kind, or null when it may be cleaned. */
export function cleanBlockReason(policy, kind) {
  if (!policy) return "rights_not_attested";
  const map = policy.clean;
  const key = String(kind || "");
  if (map && typeof map === "object" && Object.prototype.hasOwnProperty.call(map, key)) {
    return map[key] || null;
  }
  return policyLocked(policy) && !policy.attested ? "rights_not_attested" : null;
}

export const CLEAN_REASON_TEXT = {
  watermark: "This platform watermark is never removed. Use the original file.",
  screen_text: "Screen interface text is left alone; it is never cleaned.",
  attestation_required: "This handle or logo needs the per-video 'this is mine' tick.",
  rights_not_attested: "Confirm you own this footage or have the rights to it before cleaning.",
};

export function cleanReasonText(reason, policy = null) {
  const code = String(reason || "");
  if (code === "attestation_required" && policyLocked(policy)) {
    // Under the lock on, the one own-footage tick unlocks handles too. The
    // per-video tick is only the lock-off rule.
    return "Confirm you own this footage or have the rights to it before cleaning.";
  }
  return CLEAN_REASON_TEXT[code] || code.replace(/_/g, " ");
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
  let selectedFile = null;
  let busy = false;
  let disposed = false;
  let recentRequest = 0;
  let recentTimer = 0;
  let readingTimer = 0;
  let upload = null;
  let policy = null;
  let policyLoading = true;
  let policyError = "";

  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-import-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 1 · Import</p>
        <h1 id="st-import-title">Bring in a video</h1>
        <p class="st-lede">Choose a file, a path on this Mac, or a link. The video stays on this machine.</p>
      </header>

      <div class="st-import-grid">
        <div class="st-card st-import-card">
          <div id="st-dropzone" class="st-dropzone" role="button" tabindex="0" aria-label="Choose a video file">
            <span class="st-drop-icon" data-icon="upload" data-icon-size="22" aria-hidden="true"></span>
            <strong>Drop a video here</strong>
            <span>or choose a file from this Mac</span>
            <input id="st-file-input" type="file" accept="video/*,.mkv,.avi,.mpg,.mpeg" aria-label="Choose a video file" hidden>
          </div>
          <div id="st-file-card" class="st-file-card" hidden>
            <span class="st-file-glyph" data-icon="film" aria-hidden="true"></span>
            <span class="st-file-copy"><strong id="st-file-name"></strong><span id="st-file-size"></span></span>
            <button id="st-file-clear" class="st-icon-btn" type="button" data-icon="x" aria-label="Remove chosen file"></button>
          </div>

          <label class="st-field" for="st-location-input" style="margin-top:18px">
            <span>Or use a link or full path</span>
            <input id="st-location-input" type="text" inputmode="url" spellcheck="false" autocomplete="off" placeholder="https://… or /Users/you/Movies/long-video.mp4">
          </label>
          <p class="st-hint">A link downloads through the local downloader. A path is read in place and is not copied.</p>
          <div class="st-layer-add" style="margin-top:8px">
            <button id="st-path-reveal" class="st-btn st-btn-ghost st-btn-small" type="button" hidden>Show in Finder</button>
          </div>

          <div class="st-import-start">
            <label id="st-attest-row" class="st-attest" hidden>
              <input id="st-attest" type="checkbox">
              <span><strong>I own this footage or have the rights to it.</strong><small>Required while the rights lock is on. VibeCut never removes platform watermarks.</small></span>
            </label>
            <div class="st-actions st-import-actions">
              <button id="st-import" class="st-btn st-btn-primary" type="button" disabled>Import video</button>
              <span id="st-import-note" class="st-hint">Confirm the rights note to start.</span>
            </div>
          </div>
          <div class="st-progress" id="st-progress" hidden>
            <div class="st-progress-bar"><i id="st-progress-fill"></i></div>
            <span id="st-progress-text" class="st-mono"></span>
            <button id="st-upload-cancel" class="st-btn st-btn-ghost" type="button" hidden>Cancel upload</button>
          </div>
          <div class="st-progress" id="st-reading" hidden>
            <div class="st-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i id="st-reading-fill"></i></div>
            <span id="st-reading-text" class="st-mono"></span>
            <button id="st-reading-cancel" class="st-btn st-btn-ghost" type="button">Cancel reading</button>
          </div>
          <p id="st-import-status" class="st-status" role="status" aria-live="polite" hidden></p>
          <p id="st-import-error" class="st-error" role="alert" hidden></p>

          <section class="st-options-panel" aria-labelledby="st-options-title">
            <div class="st-card-head">
              <h2 id="st-options-title">What to read</h2>
              <span class="st-hint">Text, speech, smart crop and spoken language</span>
            </div>
            <div class="st-options-details-body">
              <div class="st-options-grid">
                <label class="st-check"><input id="st-opt-ocr" type="checkbox" checked><span><strong>Text and faces</strong><small>Apple Vision · on this Mac</small></span></label>
                <label class="st-check"><input id="st-opt-transcribe" type="checkbox" checked><span><strong>Speech</strong><small>word timing for captions</small></span></label>
                <label class="st-check"><input id="st-opt-crop" type="checkbox" checked><span><strong>Smart crop</strong><small>follows the subject</small></span></label>
                <label class="st-check"><input id="st-opt-track" type="checkbox" checked><span><strong>Track crop</strong><small>smooths the move</small></span></label>
              </div>
              <label class="st-field st-field-inline" style="margin-top:10px">
                <span>Spoken language</span>
                <select id="st-speech-language" aria-label="Spoken language">
                  <option value="auto">Auto detect</option>
                  <option value="en">English</option>
                  <option value="zh">Chinese</option>
                  <option value="vi">Vietnamese</option>
                  <option value="ja">Japanese</option>
                  <option value="ko">Korean</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                  <option value="pt">Portuguese</option>
                  <option value="it">Italian</option>
                  <option value="hi">Hindi</option>
                  <option value="ar">Arabic</option>
                  <option value="th">Thai</option>
                  <option value="ru">Russian</option>
                </select>
              </label>
              <p class="st-hint">Set this when the title does not reveal the language. It stops a long fallback on the speech engine.</p>
            </div>
          </section>
        </div>

        <aside class="st-card st-recent-card" aria-labelledby="st-recent-title">
          <div class="st-card-head">
            <h2 id="st-recent-title">Recent videos</h2>
            <span class="st-recent-actions">
              <button id="st-recent-all" class="st-btn st-btn-quiet" type="button">All videos</button>
              <button id="st-recent-refresh" class="st-btn st-btn-quiet" type="button">Refresh</button>
            </span>
          </div>
          <div id="st-recent-list" class="st-recent-list">
            <p class="st-hint">Loading recent videos…</p>
          </div>
          <p id="st-recent-error" class="st-error" role="alert" hidden></p>
        </aside>
      </div>
    </section>
  `;
  paintIcons(root);

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    dropzone: $("#st-dropzone"),
    fileInput: $("#st-file-input"),
    fileCard: $("#st-file-card"),
    fileName: $("#st-file-name"),
    fileSize: $("#st-file-size"),
    fileClear: $("#st-file-clear"),
    locationInput: $("#st-location-input"),
    pathReveal: $("#st-path-reveal"),
    speechLanguage: $("#st-speech-language"),
    ocr: $("#st-opt-ocr"),
    transcribe: $("#st-opt-transcribe"),
    crop: $("#st-opt-crop"),
    track: $("#st-opt-track"),
    attest: $("#st-attest"),
    attestRow: $("#st-attest-row"),
    submit: $("#st-import"),
    note: $("#st-import-note"),
    progress: $("#st-progress"),
    progressFill: $("#st-progress-fill"),
    progressText: $("#st-progress-text"),
    uploadCancel: $("#st-upload-cancel"),
    reading: $("#st-reading"),
    readingBar: root.querySelector("#st-reading .st-progress-bar"),
    readingFill: $("#st-reading-fill"),
    readingText: $("#st-reading-text"),
    readingCancel: $("#st-reading-cancel"),
    status: $("#st-import-status"),
    error: $("#st-import-error"),
    recentList: $("#st-recent-list"),
    recentAll: $("#st-recent-all"),
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
    const result = {
      ocr: dom.ocr.checked,
      transcribe: dom.transcribe.checked,
      smart_crop: dom.crop.checked,
      crop_tracking: dom.track.checked,
    };
    const language = String(dom.speechLanguage?.value || "auto");
    if (language !== "auto") {
      result.speech_language = language;
      result.speech_language_explicit = language;
    }
    return result;
  }

  function locationValue() {
    return String(dom.locationInput?.value || "").trim();
  }

  /** file, url, path, or "" when nothing usable is chosen. */
  function currentSource() {
    if (selectedFile) return "file";
    const value = locationValue();
    if (!value) return "";
    return /^https?:\/\//i.test(value) ? "url" : "path";
  }

  function selectedDisplayName() {
    const kind = currentSource();
    if (kind === "file") return selectedFile ? selectedFile.name : "";
    if (kind === "path") return nameFromPath(locationValue());
    if (kind === "url") return nameFromUrl(locationValue());
    return "";
  }

  function selectionReady() {
    const kind = currentSource();
    if (kind === "file") return Boolean(selectedFile);
    if (kind === "path") return Boolean(locationValue());
    if (kind === "url") return validHttpUrl(locationValue());
    return false;
  }

  function syncSubmit() {
    const ready = selectionReady();
    const reading = currentlyReading();
    const needsTick = importNeedsTick(policy);
    dom.attestRow.hidden = !needsTick;
    const ticked = !needsTick || dom.attest.checked;
    dom.submit.disabled = busy || reading || !ready || policyLoading || Boolean(policyError) || !ticked;
    if (busy) return;
    if (reading) {
      dom.note.textContent = "A video is reading now. Import the next one when it finishes, or press Cancel reading.";
    } else if (policyLoading) {
      dom.note.textContent = "Reading the rights policy…";
    } else if (policyError) {
      dom.note.textContent = "The rights policy could not be read. Reload this page before importing.";
    } else if (!ticked) {
      dom.note.textContent = "Confirm the rights note to start.";
    } else if (!ready) {
      const kind = currentSource();
      dom.note.textContent = kind === "file"
        ? "Choose a video file."
        : kind === "path"
          ? "Enter a full path to a video on this Mac."
          : kind === "url"
            ? "Enter a full link starting with http:// or https://."
            : "Choose a file, or paste a link or full path.";
    } else {
      dom.note.textContent = needsTick
        ? "Import starts reading the video. Moments unlock when it finishes."
        : "The rights lock is off, so import starts straight away. Watermarks are never removed.";
    }
  }

  function setBusy(value) {
    busy = value;
    dom.submit.textContent = value ? "Importing…" : "Import video";
    for (const control of [dom.dropzone, dom.fileInput, dom.fileClear, dom.locationInput,
      dom.ocr, dom.transcribe, dom.crop, dom.track, dom.attest, dom.recentRefresh]) {
      if (!control) continue;
      if ("disabled" in control && control !== dom.dropzone) control.disabled = value;
      else if (control === dom.dropzone) control.setAttribute("aria-disabled", value ? "true" : "false");
    }
    if (!value) {
      dom.progress.hidden = true;
      dom.progressFill.style.width = "0%";
      dom.progressText.textContent = "";
      dom.uploadCancel.hidden = true;
    }
    syncSubmit();
  }

  // The open video's read, shown here too: percent, the server's time-left
  // estimate and Cancel reading. It follows the shell's job polling.
  function syncReading() {
    const state = ctx.getStepState?.() || {};
    const line = currentlyReading() ? readingLine(state) : null;
    dom.reading.hidden = !line;
    if (line) {
      dom.readingFill.style.width = `${line.percent}%`;
      dom.readingBar.setAttribute("aria-valuenow", String(line.percent));
      dom.readingText.textContent = line.text;
      if (!dom.readingCancel.dataset.busy) {
        dom.readingCancel.disabled = false;
        dom.readingCancel.textContent = "Cancel reading";
      }
    }
    syncSubmit();
    if (readingTimer) window.clearTimeout(readingTimer);
    if (!disposed) readingTimer = window.setTimeout(syncReading, line ? 1000 : 3000);
  }

  async function cancelReading() {
    const jobId = ctx.getJobId?.();
    if (!jobId || dom.readingCancel.dataset.busy) return;
    dom.readingCancel.dataset.busy = "1";
    dom.readingCancel.disabled = true;
    dom.readingCancel.textContent = "Stopping…";
    clearError();
    try {
      await request(`/api/jobs/${encodeURIComponent(jobId)}/reading/cancel`, { method: "POST", body: {} });
      if (!disposed) setStatus(dom.status, "Stopping the read. Other videos can read now.", "ok");
    } catch (error) {
      if (!disposed) showError(error?.message || "Could not stop reading.");
    } finally {
      delete dom.readingCancel.dataset.busy;
    }
  }

  function setFile(file) {
    if (!file) return;
    if (!looksLikeVideo(file)) {
      showError("That file does not look like a video. Choose an MP4, MOV, WebM, MKV, AVI or MPEG file.");
      return;
    }
    selectedFile = file;
    dom.locationInput.value = "";
    dom.pathReveal.hidden = true;
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
    if (policyLoading || policyError) {
      showError("The rights policy is not available. Reload this page before importing.");
      return;
    }
    const needsTick = importNeedsTick(policy);
    if (needsTick && !dom.attest.checked) {
      showError("Confirm that you own this footage or have the rights to it.");
      dom.attest.focus();
      return;
    }
    if (!selectionReady()) {
      const kind = currentSource();
      showError(kind === "file" ? "Choose a video file first."
        : kind === "path" ? "Enter a full path to a video on this Mac."
        : kind === "url" ? "Enter a full link starting with http:// or https://."
        : "Choose a file, or paste a link or full path.");
      return;
    }

    setBusy(true);
    setStatus(dom.status, "Starting import…");
    try {
      const options = currentOptions();
      const rights = needsTick ? true : null;
      let created;
      const kind = currentSource();
      if (kind === "file") {
        dom.progress.hidden = false;
        dom.uploadCancel.hidden = false;
        dom.uploadCancel.disabled = false;
        upload = new AbortController();
        const started = Date.now();
        created = await uploadVideo(selectedFile, options, (ratio) => {
          const percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
          dom.progressFill.style.width = `${percent}%`;
          dom.submit.textContent = `Importing… ${percent}%`;
          dom.progressText.textContent = uploadLine(ratio, (Date.now() - started) / 1000);
        }, { rights, signal: upload.signal });
      } else if (kind === "path") {
        created = await createJobFromPath(locationValue(), options, { rights });
      } else {
        created = await createJobFromUrl(locationValue(), options, null, { rights });
      }

      if (!created || !created.id) throw new Error("The server did not return a video id.");
      if (disposed) return;
      setStatus(dom.status, "Imported. Reading the video now — Moments opens by itself when it is ready.", "ok");
      ctx.openJob(created.id, { name: selectedDisplayName(), status: "queued" });
    } catch (error) {
      if (disposed) return;
      if (upload?.signal.aborted) setStatus(dom.status, "Upload cancelled. Nothing was imported.");
      else showError(error.message || "Could not import this video.");
    } finally {
      upload = null;
      if (!disposed) setBusy(false);
    }
  }

  dom.recentAll?.addEventListener("click", () => ctx.openLibrary?.());

  function renderRecent(jobs) {
    root.querySelector(".st-import-grid")?.classList.toggle("has-recent", jobs.length > 0);
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
        // Reopen where the work stopped: reading, Moments, Edit or Finish.
        ctx.openJobAndContinue(job.id, { name: job.name || "", status: job.status || "" });
      });
      dom.recentList.append(el("div", { class: "st-recent-row" }, [
        button,
        deleteVideoButton({
          name: job.name || job.title || job.id,
          check: () => deleteCheck(job.id),
          onDelete: async () => {
            await deleteJob(job.id);
            ctx.jobDeleted?.(job.id);
            await loadRecent({ quiet: true });
          },
          onError: (error) => setStatus(dom.recentError, error.message || "Could not delete that video.", "bad"),
        }),
      ]));
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

  async function loadPolicy() {
    policyLoading = true;
    policyError = "";
    syncSubmit();
    try {
      const result = await request("/api/rights/policy");
      if (disposed) return;
      if (!result || typeof result !== "object" || typeof result.lock !== "boolean") {
        policy = null;
        policyError = "The server did not return a rights policy.";
      } else {
        policy = result;
      }
    } catch (error) {
      if (disposed) return;
      policy = null;
      policyError = error?.message || "Could not read the rights policy.";
    } finally {
      policyLoading = false;
      if (!disposed) syncSubmit();
    }
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
  dom.locationInput.addEventListener("input", () => {
    if (locationValue()) {
      selectedFile = null;
      dom.fileInput.value = "";
      dom.fileCard.hidden = true;
      dom.dropzone.hidden = false;
    }
    dom.pathReveal.hidden = currentSource() !== "path";
    clearError();
    syncSubmit();
  });
  dom.pathReveal.addEventListener("click", async () => {
    const path = locationValue();
    if (!path) {
      showError("Type the full path first.");
      dom.locationInput.focus();
      return;
    }
    dom.pathReveal.disabled = true;
    try {
      await revealPath(path);
    } catch (error) {
      showError(error?.message || "Could not show that file in Finder.");
    } finally {
      if (!disposed) dom.pathReveal.disabled = false;
    }
  });
  dom.locationInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!dom.submit.disabled) startImport();
    }
  });
  dom.attest.addEventListener("change", syncSubmit);
  dom.submit.addEventListener("click", startImport);
  dom.uploadCancel.addEventListener("click", () => {
    dom.uploadCancel.disabled = true;
    upload?.abort();
  });
  dom.readingCancel.addEventListener("click", () => { void cancelReading(); });
  dom.recentRefresh.addEventListener("click", () => {
    void loadRecent();
    void loadPolicy();
  });

  syncSubmit();
  syncReading();
  loadPolicy();
  loadRecent();

  return () => {
    disposed = true;
    if (recentTimer) window.clearTimeout(recentTimer);
    if (readingTimer) window.clearTimeout(readingTimer);
  };
}

/** The Import screen's read line: percent and the server's stage and ETA. */
export function readingLine(state) {
  const percent = Math.max(0, Math.min(100, Math.round(Number(state?.progress || 0) * 100)));
  const message = String(state?.message || "").trim();
  return { percent, text: `Reading the video · ${percent}%${message ? ` · ${message}` : ""}` };
}

/** Upload percent plus time left, once there is enough to measure. */
export function uploadLine(ratio, elapsedSeconds) {
  const fraction = Math.max(0, Math.min(1, Number(ratio) || 0));
  const percent = Math.round(fraction * 100);
  const elapsed = Number(elapsedSeconds) || 0;
  if (fraction >= 1) return "100% · reading starts next";
  if (fraction < 0.03 || elapsed < 2) return `${percent}% · estimating`;
  const left = Math.max(1, Math.round(elapsed * (1 - fraction) / fraction));
  return `${percent}% · about ${left < 60 ? `${left} s` : `${Math.round(left / 60)} min`} left`;
}

/** Statuses that mean the video is still being read. */
export function isReadingStatus(status) {
  return ["queued", "downloading", "scanning", "reading", "scoring"].includes(String(status || ""));
}
