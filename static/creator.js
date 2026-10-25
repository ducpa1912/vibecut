/* Creator workspace. Loaded after app.js; uses the small vibecutBridge. */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const SCREENS = ["queue", "clipset", "captions", "packet", "preflight", "artifacts"];
  const br = () => window.vibecutBridge || {};

  const dom = {
    open: $("#creator-open"),
    close: $("#creator-close"),
    view: $("#creator-view"),
    tabs: $("#creator-tabs"),
    jobInput: $("#creator-job-input"),
    jobLoad: $("#creator-job-load"),
    context: $("#creator-context"),
    globalError: $("#creator-global-error"),

    batchForm: $("#batch-form"),
    batchName: $("#batch-name"),
    batchMax: $("#batch-max"),
    batchItems: $("#batch-items"),
    batchCreate: $("#batch-create"),
    batchError: $("#batch-error"),
    batchList: $("#batch-list"),
    batchRefresh: $("#batch-refresh"),

    clipsetCount: $("#clipset-count"),
    clipsetPrompt: $("#clipset-prompt"),
    clipsetBuild: $("#clipset-build"),
    clipsetV2: $("#clipset-v2"),
    matrixBuild: $("#matrix-build"),
    clipsetError: $("#clipset-error"),
    clipsetTitle: $("#clipset-title"),
    clipsetMeta: $("#clipset-meta"),
    clipsetStories: $("#clipset-stories"),
    clipsetV2Output: $("#clipset-v2-output"),
    matrixOutput: $("#matrix-output"),
    tightenTarget: $("#tighten-target"),
    tightenRun: $("#tighten-run"),
    tightenOutput: $("#tighten-output"),

    captionTarget: $("#caption-target"),
    captionStyle: $("#caption-style"),
    captionArtifact: $("#caption-artifact"),
    captionBuild: $("#caption-build"),
    captionArtifactLoad: $("#caption-artifact-load"),
    captionSave: $("#caption-save"),
    captionExport: $("#caption-export"),
    captionPreviewRun: $("#caption-preview-run"),
    captionError: $("#caption-error"),
    captionMeta: $("#caption-meta"),
    captionCues: $("#caption-cues"),
    captionPreview: $("#caption-preview"),
    captionPreviewImg: $("#caption-preview-img"),
    captionPreviewSafe: $("#caption-preview-safe"),
    captionPreviewText: $("#caption-preview-text"),
    captionPreviewTime: $("#caption-preview-time"),
    captionPreviewReadout: $("#caption-preview-readout"),

    packetForm: $("#packet-form"),
    packetStory: $("#packet-story"),
    packetArtifact: $("#packet-artifact"),
    packetRenderKey: $("#packet-render-key"),
    packetTitle1: $("#packet-title-1"),
    packetTitle2: $("#packet-title-2"),
    packetTitle3: $("#packet-title-3"),
    packetDescription: $("#packet-description"),
    packetDescCount: $("#packet-desc-count"),
    packetHashtags: $("#packet-hashtags"),
    packetCover1: $("#packet-cover-1"),
    packetCover2: $("#packet-cover-2"),
    packetFilename: $("#packet-filename"),
    packetBuild: $("#packet-build"),
    packetError: $("#packet-error"),
    packetResult: $("#packet-result"),

    preflightStory: $("#preflight-story"),
    preflightRun: $("#preflight-run"),
    preflightError: $("#preflight-error"),
    preflightSummary: $("#preflight-summary"),
    preflightChecks: $("#preflight-checks"),
    preflightFindings: $("#preflight-findings"),

    artifactRefresh: $("#artifact-refresh"),
    artifactError: $("#artifact-error"),
    artifactCount: $("#artifact-count"),
    artifactList: $("#artifact-list"),
    shareList: $("#share-list"),
  };

  const state = {
    screen: "queue",
    jobId: "",
    job: null,
    loadingJob: "",
    artifacts: [],
    shares: [],
    clipset: null,
    clipsetEdits: {},
    locks: new Set(),
    bans: new Set(),
    selection: null,
    matrix: null,
    caption: {
      track: null,
      cues: [],
      artifactId: "",
      preview: null,
      previewUrl: "",
    },
    packet: null,
    preflight: null,
    preflightHidden: new Set(),
    batches: [],
    batchTimer: null,
    confirm: {},
  };

  // ---------------------------------------------------------------- helpers

  function escapeHtml(value) {
    const fn = br().escapeHtml;
    if (typeof fn === "function") return fn(value);
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));
  }

  function fmtDuration(seconds) {
    const fn = br().fmtDuration;
    if (typeof fn === "function") return fn(seconds);
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "—";
    if (value < 60) return `${value.toFixed(1)}s`;
    const total = Math.round(value);
    return `${Math.floor(total / 60)}m ${total % 60}s`;
  }

  function fmtClock(seconds, decimals = 1) {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60);
    const rest = value - minutes * 60;
    return `${minutes}:${rest.toFixed(decimals).padStart(decimals ? 4 : 2, "0")}`;
  }

  function slug(value) {
    const text = String(value || "story").normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "").toLowerCase();
    return text.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "story";
  }

  function toast(message) {
    const fn = br().toast;
    if (typeof fn === "function") {
      fn(message);
      return;
    }
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
  }

  function humanError(error) {
    const detail = error && (error.detail || (error.payload && error.payload.detail));
    let message = error && error.message ? error.message : "Request failed.";
    let code = error && error.code ? error.code : "";
    if (detail && typeof detail === "object") {
      code = code || detail.code || "";
      message = detail.message || message;
      if (detail.suggestion) message += ` ${detail.suggestion}`;
    } else if (typeof detail === "string") {
      message = detail;
    }
    if (!code && typeof message === "string") {
      const match = message.match(/"code"\s*:\s*"([^"]+)"/);
      if (match) code = match[1];
    }
    return `${code ? `${code}: ` : ""}${message}`.trim();
  }

  function setError(node, error) {
    if (!node) return;
    node.textContent = humanError(error);
    node.hidden = false;
  }

  function clearError(node) {
    if (!node) return;
    node.textContent = "";
    node.hidden = true;
  }

  function tokenValue() {
    const bridge = br();
    if (typeof bridge.token === "function") {
      try { return bridge.token() || ""; } catch (_) { /* ignore */ }
    }
    try { return localStorage.getItem("vibecut_token") || ""; } catch (_) { return ""; }
  }

  function makeError(response, detail, payload) {
    const normalized = typeof detail === "string"
      ? detail
      : (detail && typeof detail.message === "string" ? detail.message : JSON.stringify(detail));
    const error = new Error(normalized || response.statusText || "Request failed.");
    error.status = response.status;
    error.detail = detail;
    error.code = detail && typeof detail === "object" ? detail.code : null;
    error.payload = payload;
    return error;
  }

  async function fetchJson(path, options = {}) {
    const config = { ...options };
    if (config.body && !config.headers) {
      config.headers = { "Content-Type": "application/json" };
    }
    const token = tokenValue();
    if (token) {
      config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
    }
    const response = await fetch(path, config);
    if (!response.ok) {
      let detail = response.statusText || "Request failed.";
      let payload = null;
      try {
        payload = await response.json();
        detail = payload.detail || payload.message || payload.error || detail;
      } catch (_) { /* ignore */ }
      throw makeError(response, detail, payload);
    }
    return response.json();
  }

  async function request(path, options = {}) {
    const fn = br().request;
    if (typeof fn === "function") return fn(path, options);
    return fetchJson(path, options);
  }

  async function requestRaw(path, options = {}) {
    const fn = br().requestRaw;
    if (typeof fn === "function") return fn(path, options);
    const config = { ...options };
    const token = tokenValue();
    if (token) {
      config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
    }
    const response = await fetch(path, config);
    if (!response.ok) {
      let detail = response.statusText || "Request failed.";
      try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
      throw makeError(response, detail, null);
    }
    return response.blob();
  }

  async function downloadPath(path, filename) {
    const blob = await requestRaw(path, { cache: "no-store" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "download";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  async function copyText(text) {
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard.");
      return true;
    } catch (_) {
      const input = document.createElement("textarea");
      input.value = text;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) { /* ignore */ }
      input.remove();
      toast(ok ? "Copied to clipboard." : "Copy failed.");
      return ok;
    }
  }

  function absoluteUrl(url) {
    if (!url) return "";
    return /^https?:/i.test(url) ? url : `${location.origin}${url}`;
  }

  function setText(node, value) {
    if (node) node.textContent = value || "";
  }

  function renderEmpty(node, message) {
    if (node) node.innerHTML = `<div class="creator-empty-state"><p>${escapeHtml(message)}</p></div>`;
  }

  function parseHash() {
    try {
      const params = new URLSearchParams(String(location.hash || "").replace(/^#/, ""));
      return { job: params.get("job") || "", screen: params.get("screen") || "" };
    } catch (_) {
      return { job: "", screen: "" };
    }
  }

  function writeHash(jobId, screen) {
    const params = new URLSearchParams();
    if (jobId) params.set("job", jobId);
    if (screen) params.set("screen", screen);
    const value = params.toString() ? `#${params.toString()}` : "#";
    if (location.hash !== value) history.replaceState(null, "", value);
  }

  function currentWantedJob() {
    return state.jobId || (br().getJob && br().getJob()?.id) || parseHash().job || "";
  }

  function setJobContext() {
    const job = state.job;
    if (!job) {
      setText(dom.context, "Open a cut to load Clip Set, Caption Studio, packets and shares.");
      return;
    }
    const source = job.source || {};
    setText(dom.context, `${source.name || "cut"} · ${fmtDuration(source.duration)} · ${job.status || "unknown"}`);
    dom.jobInput.value = job.id || "";
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel = button.textContent;
      button.textContent = label || "Working…";
      button.disabled = true;
    } else {
      if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
      button.disabled = false;
    }
  }

  async function withBusy(button, task, label) {
    setBusy(button, true, label);
    try {
      return await task();
    } finally {
      setBusy(button, false);
    }
  }

  // ---------------------------------------------------------------- job + screens

  function setTabs(screen) {
    $$("[data-creator-tab]", dom.tabs).forEach((button) => {
      button.classList.toggle("active", button.dataset.creatorTab === screen);
    });
    $$("[data-creator-panel]", dom.view).forEach((panel) => {
      panel.hidden = panel.dataset.creatorPanel !== screen;
    });
  }

  function setScreen(screen, jobId) {
    const chosen = SCREENS.includes(screen) ? screen : "queue";
    state.screen = chosen;
    if (state.batchTimer && chosen !== "queue") {
      clearInterval(state.batchTimer);
      state.batchTimer = null;
    }
    setTabs(chosen);
    const wanted = jobId || state.jobId || currentWantedJob();
    if (wanted) state.jobId = wanted;
    writeHash(state.jobId, chosen);
    clearError(dom.globalError);
    if (state.jobId && state.jobId !== state.job?.id) {
      loadJob(state.jobId).catch((error) => {
        setError(dom.globalError, error);
        toast(humanError(error));
      });
    } else {
      refreshScreen(chosen).catch((error) => {
        setError(dom.globalError, error);
      });
    }
  }

  function openCreator(screen, jobId) {
    const params = parseHash();
    const chosen = screen || params.screen || state.screen || "queue";
    const wanted = jobId || params.job || state.jobId || (br().getJob && br().getJob()?.id) || "";
    document.body.classList.add("creator-mode");
    dom.view.hidden = false;
    if (wanted) {
      state.jobId = wanted;
      dom.jobInput.value = wanted;
    }
    setScreen(chosen, wanted);
  }

  function closeCreator() {
    document.body.classList.remove("creator-mode");
    dom.view.hidden = true;
    if (state.batchTimer) {
      clearInterval(state.batchTimer);
      state.batchTimer = null;
    }
    writeHash(state.jobId, "");
    const job = state.job || (br().getJob && br().getJob());
    if (job && job.id && br().openJob) {
      // Keep the editor view aligned with the open creator job.
      Promise.resolve(br().openJob(job.id)).catch(() => {});
    }
  }

  async function loadJob(jobId) {
    if (!jobId || state.loadingJob === jobId) return;
    const changed = state.jobId !== jobId || state.job?.id !== jobId;
    state.loadingJob = jobId;
    state.jobId = jobId;
    dom.jobInput.value = jobId;
    clearError(dom.globalError);
    try {
      const job = await request(`/api/jobs/${encodeURIComponent(jobId)}`);
      state.job = job;
      state.jobId = job.id || jobId;
      if (changed) {
        state.packet = null;
        state.preflight = null;
        state.selection = null;
        state.matrix = null;
        const oldPreviewUrl = state.caption.previewUrl;
        state.caption = { track: null, cues: [], artifactId: "", preview: null, previewUrl: "" };
        state.preflightHidden = new Set();
        if (oldPreviewUrl) URL.revokeObjectURL(oldPreviewUrl);
        renderPacket(null);
        renderPreflight();
        renderCaptionCues();
        renderSelection();
        renderMatrix();
        if (dom.captionPreviewImg) {
          dom.captionPreviewImg.hidden = true;
          dom.captionPreviewImg.removeAttribute("src");
        }
        if (dom.captionPreviewText) dom.captionPreviewText.textContent = "No preview yet.";
        if (dom.captionPreviewSafe) dom.captionPreviewSafe.innerHTML = "";
      }
      writeHash(state.jobId, state.screen);
      setJobContext();
      await loadArtifacts().catch((error) => setError(dom.globalError, error));
      await loadClipSets().catch(() => {});
      populateCommonSelects();
      await refreshScreen(state.screen);
      const bridge = br();
      if (typeof bridge.openJob === "function" && bridge.getJob && bridge.getJob()?.id !== state.jobId) {
        try { await bridge.openJob(state.jobId); } catch (_) { /* editor sync is best effort */ }
      }
    } catch (error) {
      state.job = null;
      setJobContext();
      setError(dom.globalError, error);
      throw error;
    } finally {
      state.loadingJob = "";
    }
  }

  async function refreshScreen(screen) {
    if (screen === "queue") return loadBatches();
    if (!state.job) {
      if (screen === "artifacts") return loadArtifacts().then(() => renderArtifacts());
      return;
    }
    if (screen === "clipset") {
      if (!state.clipset) await loadClipSets();
      renderClipSet();
      renderSelection();
      renderMatrix();
      return;
    }
    if (screen === "captions") {
      populateCommonSelects();
      renderCaptionCues();
      return;
    }
    if (screen === "packet") {
      populateCommonSelects();
      updatePacketFilename();
      return;
    }
    if (screen === "preflight") {
      populateCommonSelects();
      return;
    }
    if (screen === "artifacts") {
      await loadArtifacts();
      await loadShares();
      renderArtifacts();
      renderShares();
    }
  }

  function populateCommonSelects() {
    const job = state.job;
    if (!job) return;
    const renders = job.renders || {};
    const readyRenders = Object.entries(renders)
      .filter(([, record]) => record && record.status === "ready")
      .map(([key, record]) => ({ key, record }));
    const keep = (select, options) => {
      if (!select) return;
      const current = select.value;
      select.innerHTML = options.map((item) => (
        `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`
      )).join("");
      if (options.some((item) => item.value === current)) select.value = current;
      else if (options.length) select.value = options[0].value;
    };
    keep(dom.packetRenderKey, [
      { value: "", label: "Choose a ready render" },
      ...readyRenders.map(({ key, record }) => ({
        value: key,
        label: `${key} · ${record.target || "?"}s · ${record.aspect || "9:16"}`,
      })),
    ]);
    const artifactOptions = [
      { value: "", label: "Current cut" },
      ...state.artifacts.map((artifact) => ({
        value: artifact.artifact_id,
        label: `${artifact.title || artifact.artifact_id} · ${artifact.status || ""}`,
      })),
    ];
    keep(dom.captionArtifact, artifactOptions);
    keep(dom.packetArtifact, [
      { value: "", label: "None · use render key" },
      ...state.artifacts.map((artifact) => ({
        value: artifact.artifact_id,
        label: `${artifact.title || artifact.artifact_id} · ${artifact.status || ""}`,
      })),
    ]);
    const storyOptions = [];
    for (const story of (state.clipset?.stories || [])) {
      storyOptions.push({
        value: story.id,
        label: `${story.id} · ${story.title || "story"} · ${fmtDuration(story.dur)}`,
      });
    }
    for (const artifact of state.artifacts) {
      storyOptions.push({
        value: artifact.artifact_id,
        label: `artifact ${artifact.artifact_id} · ${artifact.target || "?"}s`,
      });
    }
    for (const { key, record } of readyRenders) {
      storyOptions.push({
        value: key,
        label: `render ${key} · ${record.target || "?"}s · ${record.aspect || "9:16"}`,
      });
    }
    const knownStories = new Set(storyOptions.map((item) => item.value));
    for (const target of [30, 15, 60]) {
      if (!knownStories.has(String(target))) {
        storyOptions.push({ value: String(target), label: `auto plan · ${target}s` });
      }
    }
    keep(dom.preflightStory, storyOptions);
    if (!dom.packetStory.value) {
      dom.packetStory.value = state.clipset?.stories?.[0]?.id || state.artifacts[0]?.artifact_id || readyRenders[0]?.key || "";
    }
    if (dom.packetTitle1 && !dom.packetTitle1.value) {
      dom.packetTitle1.value = state.clipset?.stories?.[0]?.title || "";
    }
    if (dom.packetDescription && !dom.packetDescription.value) {
      dom.packetDescription.value = (state.clipset?.stories?.[0]?.hook?.text || "").slice(0, 125);
      updateDescriptionCount();
    }
    if (dom.packetHashtags && !dom.packetHashtags.value) {
      dom.packetHashtags.value = "#shorts #creator #video";
    }
  }

  // ---------------------------------------------------------------- queue / batch

  function batchStateTag(value) {
    const stateName = String(value || "queued");
    const klass = ["done"].includes(stateName) ? "ok"
      : ["failed", "cancelled", "interrupted"].includes(stateName) ? "bad"
        : ["running", "paused"].includes(stateName) ? "warn" : "";
    return `<span class="creator-tag ${klass}">${escapeHtml(stateName)}</span>`;
  }

  function renderBatches() {
    if (!dom.batchList) return;
    if (!state.batches.length) {
      renderEmpty(dom.batchList, "No batches yet. Add local paths or URLs above and create one.");
      return;
    }
    dom.batchList.innerHTML = state.batches.map((batch) => {
      const counts = batch.counts || {};
      const items = (batch.items || []).map((item) => {
        const path = item.path || item.url || "(missing source)";
        const canRetry = item.job_id && ["failed", "interrupted", "cancelled"].includes(item.state);
        return `
          <div class="creator-item-row">
            <div>
              <strong>${escapeHtml(path)}</strong>
              <div class="creator-meta-row">
                ${batchStateTag(item.state)}
                <span class="creator-tag">try ${Number(item.attempts || 0)}</span>
                ${item.job_id ? `<span class="creator-tag">job ${escapeHtml(item.job_id)}</span>` : ""}
              </div>
              ${item.error ? `<p class="hint">${escapeHtml(item.error)}</p>` : ""}
            </div>
            <div class="creator-actions">
              ${item.job_id ? `<button class="ghost small" type="button" data-open-job="${escapeHtml(item.job_id)}">Open</button>` : ""}
              ${canRetry ? `<button class="ghost small" type="button" data-retry-job="${escapeHtml(item.job_id)}">Retry job</button>` : ""}
            </div>
          </div>`;
      }).join("");
      const canResume = ["paused", "failed", "queued"].includes(batch.status);
      const canPause = ["queued", "running"].includes(batch.status);
      const canCancel = !["done", "cancelled", "failed"].includes(batch.status);
      const confirming = state.confirm[`batch:${batch.id}`] === "cancel";
      const summary = ["done", "failed", "cancelled", "queued", "paused", "running"]
        .filter((key) => counts[key]).map((key) => `${counts[key]} ${key}`).join(" · ");
      return `
        <article class="batch-card" data-batch-id="${escapeHtml(batch.id)}">
          <header>
            <div>
              <h4>${escapeHtml(batch.name || batch.id)}</h4>
              <div class="creator-meta-row">
                ${batchStateTag(batch.status)}
                <span class="creator-tag">${escapeHtml(summary || `${batch.item_count || 0} items`)}</span>
              </div>
            </div>
            <span class="creator-tag mono">${Math.round(Number(batch.progress || 0) * 100)}%</span>
          </header>
          <div class="creator-bar"><i style="width:${Math.round(Number(batch.progress || 0) * 100)}%"></i></div>
          ${batch.error ? `<p class="hint">${escapeHtml(batch.error)}</p>` : ""}
          <div class="creator-actions" style="margin-top:9px">
            ${canResume ? `<button class="ghost small" type="button" data-batch-action="resume" data-batch="${escapeHtml(batch.id)}">Resume</button>` : ""}
            ${canPause ? `<button class="ghost small" type="button" data-batch-action="pause" data-batch="${escapeHtml(batch.id)}">Pause</button>` : ""}
            ${canCancel ? (
              confirming
                ? `<span class="creator-inline-confirm">Cancel batch? <button class="ghost small danger" type="button" data-batch-action="cancel-confirm" data-batch="${escapeHtml(batch.id)}">Confirm cancel</button><button class="ghost small" type="button" data-batch-action="cancel-abort" data-batch="${escapeHtml(batch.id)}">Keep</button></span>`
                : `<button class="ghost small" type="button" data-batch-action="cancel" data-batch="${escapeHtml(batch.id)}">Cancel</button>`
            ) : ""}
          </div>
          <div class="creator-item-list">${items || '<p class="hint">No items.</p>'}</div>
        </article>`;
    }).join("");
  }

  async function loadBatches() {
    try {
      const data = await request("/api/batches");
      state.batches = data.batches || [];
      renderBatches();
      const active = state.batches.some((batch) => ["queued", "running", "paused"].includes(batch.status));
      if (active && !state.batchTimer && state.screen === "queue") {
        state.batchTimer = setInterval(() => {
          if (state.screen !== "queue" || !document.body.classList.contains("creator-mode")) return;
          loadBatches().catch(() => {});
        }, 4500);
      }
      if (!active && state.batchTimer) {
        clearInterval(state.batchTimer);
        state.batchTimer = null;
      }
    } catch (error) {
      setError(dom.batchError, error);
    }
  }

  async function createBatch(event) {
    event.preventDefault();
    clearError(dom.batchError);
    const lines = String(dom.batchItems.value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length) {
      setError(dom.batchError, new Error("Add at least one local path or URL."));
      return;
    }
    if (lines.length > 10) {
      setError(dom.batchError, new Error("A batch accepts at most 10 items."));
      return;
    }
    let max = Number(dom.batchMax.value) || 10;
    max = Math.max(1, Math.min(10, Math.round(max)));
    if (lines.length > max) {
      setError(dom.batchError, new Error(`This batch allows at most ${max} items.`));
      return;
    }
    const items = lines.map((line) => (
      /^https?:\/\//i.test(line) ? { url: line } : { path: line }
    ));
    await withBusy(dom.batchCreate, async () => {
      try {
        const batch = await request("/api/batches", {
          method: "POST",
          body: JSON.stringify({ name: dom.batchName.value.trim(), items, max }),
        });
        toast(`Batch ${batch.name || batch.id} started.`);
        dom.batchItems.value = "";
        dom.batchName.value = "";
        await loadBatches();
      } catch (error) {
        setError(dom.batchError, error);
      }
    }, "Creating…");
  }

  async function batchAction(action, batchId) {
    clearError(dom.batchError);
    if (action === "cancel") {
      state.confirm[`batch:${batchId}`] = "cancel";
      renderBatches();
      return;
    }
    if (action === "cancel-abort") {
      delete state.confirm[`batch:${batchId}`];
      renderBatches();
      return;
    }
    if (action === "cancel-confirm") {
      delete state.confirm[`batch:${batchId}`];
      action = "cancel";
    }
    const path = `/api/batches/${encodeURIComponent(batchId)}/${action}`;
    try {
      await request(path, { method: "POST" });
      await loadBatches();
    } catch (error) {
      setError(dom.batchError, error);
    }
  }

  async function retryJob(jobId) {
    clearError(dom.batchError);
    try {
      await request(`/api/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
      toast(`Retry requested for ${jobId}.`);
      await loadBatches();
      if (state.jobId === jobId) loadJob(jobId).catch(() => {});
    } catch (error) {
      setError(dom.batchError, error);
    }
  }

  // ---------------------------------------------------------------- clip sets

  function initClipsetEdits(record) {
    state.clipsetEdits = {};
    state.locks = new Set((record?.locks || []).map(Number));
    state.bans = new Set((record?.ban_scenes || []).map(Number));
    for (const story of record?.stories || []) {
      state.clipsetEdits[story.id] = (story.sentences || []).map((sentence) => Number(sentence.id));
    }
  }

  async function loadClipSets() {
    if (!state.jobId) return;
    try {
      const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets`);
      const list = data.clip_sets || [];
      state.clipset = list.length ? list[0] : null;
      initClipsetEdits(state.clipset);
      renderClipSet();
      populateCommonSelects();
    } catch (error) {
      state.clipset = null;
      renderClipSet();
      throw error;
    }
  }

  function overlapForStory(story) {
    let overlap = 0;
    for (const other of state.clipset?.stories || []) {
      if (other.id === story.id) continue;
      overlap += Math.max(0, Math.min(Number(story.end), Number(other.end)) - Math.max(Number(story.start), Number(other.start)));
    }
    return overlap;
  }

  function sentenceText(story) {
    return state.clipsetEdits[story.id] || [];
  }

  function renderClipSet() {
    if (!dom.clipsetStories) return;
    const record = state.clipset;
    if (!state.job) {
      renderEmpty(dom.clipsetStories, "Open a job first.");
      setText(dom.clipsetMeta, "");
      return;
    }
    if (!record) {
      setText(dom.clipsetTitle, "Stories");
      setText(dom.clipsetMeta, "");
      renderEmpty(dom.clipsetStories, "No Clip Set yet. Build the v1 automatic set first.");
      return;
    }
    setText(dom.clipsetTitle, "Stories");
    const bits = [
      `${record.available ?? record.stories?.length ?? 0}/${record.requested ?? "?"} stories`,
      `order ${record.order || "source"}`,
      `${record.sentence_count ?? 0} sentences`,
    ];
    setText(dom.clipsetMeta, bits.join(" · "));
    const warnings = [...(record.warnings || [])];
    if (record.note) warnings.unshift(record.note);
    const warningHtml = warnings.length
      ? `<div class="creator-card" style="margin-bottom:10px"><p class="hint">${warnings.map(escapeHtml).join("<br>")}</p></div>`
      : "";
    const stories = record.stories || [];
    if (!stories.length) {
      dom.clipsetStories.innerHTML = warningHtml + '<div class="creator-empty-state"><p>No stories fit the source. Check the note and source duration.</p></div>';
      return;
    }
    dom.clipsetStories.innerHTML = warningHtml + stories.map((story) => {
      const ids = sentenceText(story);
      const sentenceMap = new Map((story.sentences || []).map((sentence) => [Number(sentence.id), sentence]));
      const selectedSet = new Set(ids.map(Number));
      const ordered = ids.map((id) => sentenceMap.get(Number(id))).filter(Boolean);
      const remaining = (story.sentences || []).filter((sentence) => !selectedSet.has(Number(sentence.id)));
      const sentences = [...ordered, ...remaining].map((sentence) => {
        const id = Number(sentence.id);
        const included = selectedSet.has(id);
        const selectedIndex = ids.findIndex((item) => Number(item) === id);
        return `
          <div class="sentence-row" data-sentence-id="${escapeHtml(id)}" data-story-id="${escapeHtml(story.id)}">
            <input type="checkbox" ${included ? "checked" : ""} data-sentence-toggle="1" aria-label="Include sentence">
            <div class="sentence-copy">
              <p>${escapeHtml(sentence.text || "")}</p>
              <small>${fmtClock(sentence.start)} → ${fmtClock(sentence.end)} · s${escapeHtml(id)}</small>
            </div>
            <div class="sentence-tools">
              <button class="ghost small" type="button" data-sentence-action="up" ${!included || selectedIndex <= 0 ? "disabled" : ""} aria-label="Move sentence up">↑</button>
              <button class="ghost small" type="button" data-sentence-action="down" ${!included || selectedIndex < 0 || selectedIndex >= ids.length - 1 ? "disabled" : ""} aria-label="Move sentence down">↓</button>
              <button class="ghost small" type="button" data-sentence-action="${included ? "exclude" : "include"}">${included ? "Exclude" : "Include"}</button>
            </div>
          </div>`;
      }).join("");
      const clips = story.clips || [];
      const scenes = [...new Set(clips.map((clip) => Number(clip.scene)).filter(Number.isFinite))];
      const beats = scenes.map((sceneId) => {
        const clip = clips.find((item) => Number(item.scene) === sceneId) || {};
        const locked = state.locks.has(sceneId);
        const banned = state.bans.has(sceneId);
        return `
          <span class="beat-chip ${locked ? "locked" : ""} ${banned ? "banned" : ""}">
            s${sceneId} · ${fmtDuration(clip.dur || 0)}
            <button type="button" data-beat-action="lock" data-scene-id="${sceneId}" data-story-id="${escapeHtml(story.id)}" title="Lock beat">${locked ? "unlock" : "lock"}</button>
            <button type="button" data-beat-action="ban" data-scene-id="${sceneId}" data-story-id="${escapeHtml(story.id)}" title="Ban beat">${banned ? "unban" : "ban"}</button>
          </span>`;
      }).join("");
      const score = story.v2_score ?? story.score;
      const overlap = overlapForStory(story);
      const evidence = (story.evidence || []).slice(0, 3).map((item) => `<li>${escapeHtml(item.text || "")}</li>`).join("");
      return `
        <article class="story-card" data-story-card="${escapeHtml(story.id)}">
          <header>
            <div>
              <h4>${escapeHtml(story.title || story.id)}</h4>
              <div class="creator-meta-row">
                <span class="creator-tag">${fmtDuration(story.dur)}</span>
                <span class="creator-tag">${fmtClock(story.start)} → ${fmtClock(story.end)}</span>
                <span class="creator-tag ${overlap > 0.2 ? "warn" : "ok"}">overlap ${overlap.toFixed(1)}s</span>
                ${Number.isFinite(Number(score)) ? `<span class="creator-tag ok">score ${Number(score).toFixed(1)}</span>` : ""}
              </div>
            </div>
            <div class="creator-actions">
              <button class="ghost small" type="button" data-story-packet="${escapeHtml(story.id)}">Build packet</button>
              <button class="ghost small" type="button" data-story-matrix="${escapeHtml(story.id)}">3×3 matrix</button>
            </div>
          </header>
          <p class="story-copy"><strong>Hook</strong> ${escapeHtml((story.hook || {}).text || "—")}</p>
          <p class="story-copy"><strong>Payoff</strong> ${escapeHtml((story.payoff || {}).text || "—")}</p>
          ${evidence ? `<ul class="story-evidence">${evidence}</ul>` : ""}
          <div class="beat-list">${beats || '<span class="hint">No scene beats.</span>'}</div>
          <div class="sentence-list">${sentences || '<p class="hint">No sentences.</p>'}</div>
          <div class="creator-actions" style="margin-top:10px">
            <button class="ghost small" type="button" data-clipset-save="1">Save edits</button>
            <span class="hint">Reorder, include/exclude, lock or ban. Save updates the set.</span>
          </div>
        </article>`;
    }).join("");
  }

  async function buildClipSet() {
    clearError(dom.clipsetError);
    if (!state.job) {
      setError(dom.clipsetError, new Error("Open a job first."));
      return;
    }
    await withBusy(dom.clipsetBuild, async () => {
      try {
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets`, {
          method: "POST",
          body: JSON.stringify({
            count: Number(dom.clipsetCount.value) || 3,
            order: "source",
          }),
        });
        state.clipset = data.clip_set;
        state.selection = null;
        state.matrix = null;
        state.packet = null;
        state.preflight = null;
        initClipsetEdits(state.clipset);
        renderClipSet();
        renderSelection();
        renderMatrix();
        populateCommonSelects();
        toast("Clip Set built with automatic v1 selection.");
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Building…");
  }

  async function saveClipSetEdits() {
    clearError(dom.clipsetError);
    if (!state.clipset) {
      setError(dom.clipsetError, new Error("Build a Clip Set first."));
      return;
    }
    const excluded = new Set((state.clipset.excluded_sentences || []).map(Number));
    const stories = (state.clipset.stories || []).map((story) => {
      const selected = (state.clipsetEdits[story.id] || []).map(Number);
      const all = new Set((story.sentences || []).map((sentence) => Number(sentence.id)));
      for (const id of all) {
        if (!selected.includes(id)) excluded.add(id);
      }
      return { id: story.id, sentences: selected };
    });
    try {
      const data = await request(`/clip-sets/${encodeURIComponent(state.clipset.id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          stories,
          locks: [...state.locks],
          ban_scenes: [...state.bans],
          excluded_sentences: [...excluded],
        }),
      });
      state.clipset = data.clip_set;
      initClipsetEdits(state.clipset);
      renderClipSet();
      populateCommonSelects();
      toast("Clip Set edits saved.");
    } catch (error) {
      setError(dom.clipsetError, error);
    }
  }

  function moveSentence(storyId, direction) {
    const list = state.clipsetEdits[storyId] || [];
    if (!list.length) return;
    const card = $$("[data-story-card]", dom.clipsetStories)
      .find((item) => item.dataset.storyCard === storyId);
    const rows = card ? $$("[data-sentence-id]", card) : [];
    const index = rows.findIndex((row) => row.contains(document.activeElement));
    const current = index >= 0 ? index : 0;
    const target = direction === "up" ? current - 1 : current + 1;
    if (current < 0 || target < 0 || target >= list.length) return;
    [list[current], list[target]] = [list[target], list[current]];
    state.clipsetEdits[storyId] = list;
    renderClipSet();
  }

  async function runSelectionV2() {
    clearError(dom.clipsetError);
    if (!state.job || !state.clipset) {
      setError(dom.clipsetError, new Error("Build a Clip Set before Smart Cut v2."));
      return;
    }
    await withBusy(dom.clipsetV2, async () => {
      try {
        state.selection = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/selection-v2`, {
          method: "POST",
          body: JSON.stringify({
            set_id: state.clipset.id,
            prompt: dom.clipsetPrompt.value.trim(),
            count: Number(dom.clipsetCount.value) || 3,
          }),
        });
        renderSelection();
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Ranking…");
  }

  function renderSelection() {
    if (!dom.clipsetV2Output) return;
    const data = state.selection;
    if (!data) {
      dom.clipsetV2Output.innerHTML = '<p class="hint">v1 automatic plans remain the default. Run v2 only when you want ranked stories.</p>';
      return;
    }
    const ranked = (data.ranked || []).map((story) => `
      <div class="batch-card">
        <header><div><h4>${escapeHtml(story.title || story.id)}</h4><div class="creator-meta-row"><span class="creator-tag ok">v2 ${Number(story.v2_score || 0).toFixed(1)}</span><span class="creator-tag">${fmtDuration(story.dur)}</span></div></div></header>
        <p class="hint">${escapeHtml(story.why || "")}</p>
        ${(story.hook_candidates || []).length ? `<p class="hint">Hooks: ${(story.hook_candidates || []).map((hook) => escapeHtml(hook.text || "")).join(" · ")}</p>` : `<p class="hint">Incomplete hook set.</p>`}
      </div>`).join("");
    const excluded = (data.excluded || []).map((story) => `
      <div class="batch-card"><header><div><h4>${escapeHtml(story.title || story.id)}</h4><div class="creator-meta-row"><span class="creator-tag bad">excluded</span></div></div></header><p class="hint">${escapeHtml(story.why || "Prompt exclusion matched.")}</p></div>`).join("");
    dom.clipsetV2Output.innerHTML = (ranked || '<p class="hint">No stories ranked.</p>') + excluded + (
      data.note ? `<p class="hint">${escapeHtml(data.note)}</p>` : ""
    );
  }

  async function runMatrix(storyId) {
    clearError(dom.clipsetError);
    if (!state.job || !state.clipset) {
      setError(dom.clipsetError, new Error("Build a Clip Set before the hook/cover matrix."));
      return;
    }
    try {
      state.matrix = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/hook-matrix`, {
        method: "POST",
        body: JSON.stringify({
          set_id: state.clipset.id,
          story_id: storyId || null,
          prompt: dom.clipsetPrompt.value.trim(),
          count: Number(dom.clipsetCount.value) || 3,
        }),
      });
      renderMatrix();
    } catch (error) {
      setError(dom.clipsetError, error);
    }
  }

  function renderMatrix() {
    if (!dom.matrixOutput) return;
    const data = state.matrix;
    if (!data) {
      dom.matrixOutput.innerHTML = '<p class="hint">No matrix built.</p>';
      return;
    }
    const matrices = (data.matrices || []).map((matrix) => {
      const cells = (matrix.cells || []).slice().sort((a, b) => Number(a.order) - Number(b.order)).map((cell) => `
        <div class="matrix-cell">
          <strong>${escapeHtml(cell.id || "cell")}</strong>
          hook ${escapeHtml(cell.hook_index + 1)} · cover ${escapeHtml(cell.cover_index + 1)}
        </div>`).join("");
      return `
        <div class="matrix-card">
          <header><div><h4>${escapeHtml(matrix.story_title || matrix.story_id)}</h4><div class="creator-meta-row"><span class="creator-tag ok">${matrix.job_count || 9} cells</span><span class="creator-tag">${fmtDuration(matrix.target)}</span></div></div></header>
          <div class="matrix-grid">${cells || '<div class="matrix-cell error">No 3×3 matrix.</div>'}</div>
          <p class="hint">${escapeHtml(matrix.note || "Metadata only. No renders queued.")}</p>
        </div>`;
    }).join("");
    const errors = (data.errors || []).map((item) => `
      <div class="matrix-cell error"><strong>${escapeHtml(item.story_title || item.story_id || "story")}</strong>${escapeHtml(item.error || "incomplete")}</div>`).join("");
    dom.matrixOutput.innerHTML = (matrices || "") + (errors ? `<div class="matrix-grid">${errors}</div>` : "") + (
      !matrices && !errors ? '<p class="hint">No matrix built.</p>' : ""
    );
  }

  async function runTighten() {
    clearError(dom.clipsetError);
    if (!state.job) {
      setError(dom.clipsetError, new Error("Open a job first."));
      return;
    }
    await withBusy(dom.tightenRun, async () => {
      try {
        const target = Number(dom.tightenTarget.value) || 30;
        let plan = null;
        let sourceLabel = "current plan";
        if (state.clipset) {
          const plans = await request(`/clip-sets/${encodeURIComponent(state.clipset.id)}/plans`, {
            method: "POST",
            body: JSON.stringify({ target }),
          });
          plan = (plans.plans || [])[0]?.plan || null;
          sourceLabel = `first story · ${plans.plans?.[0]?.title || plans.plans?.[0]?.story_id || "story"}`;
          if (!plan) throw new Error("The Clip Set has no plan to tighten.");
        }
        const body = plan ? { plan } : { target };
        const result = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/tighten`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        const tightened = result.plan || {};
        const applied = br().applyPlan ? br().applyPlan(tightened) : false;
        renderTightenReport(tightened, sourceLabel, applied);
        if (applied) toast("Tightened plan loaded into Smart Cut.");
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Tightening…");
  }

  function renderTightenReport(plan, sourceLabel, applied) {
    const report = plan.tighten || {};
    dom.tightenOutput.innerHTML = `
      <div class="tighten-card">
        <header><div><h4>Tightened plan</h4><div class="creator-meta-row">
          <span class="creator-tag ok">${fmtDuration(plan.total)} new</span>
          <span class="creator-tag">${fmtDuration(report.source_total)} source</span>
          <span class="creator-tag warn">−${Number(report.removed_seconds || 0).toFixed(2)}s</span>
        </div></div></header>
        <p class="hint">${escapeHtml(sourceLabel)} · ${Number(report.punch_ins || 0)} punch-ins · filler ${Number(report.filler_removed_seconds || 0).toFixed(2)}s · silence ${Number(report.silence_removed_seconds || 0).toFixed(2)}s</p>
        ${applied ? '<p class="hint">Loaded into the Smart Cut editor. Close Creator to review it.</p>' : '<p class="hint">The API returned a new plan. Reopen Smart Cut to apply it.</p>'}
      </div>`;
  }

  // ---------------------------------------------------------------- captions

  function captionArtifactSelected() {
    return Boolean(dom.captionArtifact?.value);
  }

  function renderCaptionCues() {
    if (!dom.captionCues) return;
    const cues = state.caption.cues || [];
    if (!cues.length) {
      dom.captionCues.innerHTML = '<p class="hint">Build a track to load speech-timed cues.</p>';
      setText(dom.captionMeta, "");
      return;
    }
    setText(
      dom.captionMeta,
      state.caption.artifactId
        ? `artifact ${state.caption.artifactId} · immutable`
        : `${state.caption.track?.id || "track"} · v${state.caption.track?.version || 1} · ${cues.length} cues`,
    );
    dom.captionCues.innerHTML = cues.map((cue, index) => `
      <div class="cue-row" data-cue-index="${index}">
        <input type="number" step="0.001" min="0" value="${Number(cue.start || 0).toFixed(3)}" data-cue-field="start" aria-label="Cue start">
        <input type="number" step="0.001" min="0" value="${Number(cue.end || 0).toFixed(3)}" data-cue-field="end" aria-label="Cue end">
        <textarea data-cue-field="text" aria-label="Caption text">${escapeHtml(cue.text || "")}</textarea>
      </div>`).join("");
  }

  async function buildCaptionTrack() {
    clearError(dom.captionError);
    if (!state.job) {
      setError(dom.captionError, new Error("Open a job first."));
      return;
    }
    await withBusy(dom.captionBuild, async () => {
      try {
        const target = Number(dom.captionTarget.value) || 30;
        const bridgePlan = br().getPlan ? br().getPlan() : null;
        const body = {
          target,
          style_id: dom.captionStyle.value || "clean",
          order: "source",
        };
        if (bridgePlan && Number(bridgePlan.target) === target && Array.isArray(bridgePlan.clips)) {
          body.clips = bridgePlan.clips;
          body.hook_scene = bridgePlan.hook_scene;
        }
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/captions`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        state.caption.track = data.track || data;
        state.caption.cues = (data.track?.cues || data.cues || []).map((cue) => ({ ...cue }));
        state.caption.artifactId = "";
        dom.captionArtifact.value = "";
        renderCaptionCues();
        await loadCaptionPreview().catch((error) => setError(dom.captionError, error));
        toast("Caption track built.");
      } catch (error) {
        if (error.status === 404) {
          setError(dom.captionError, new Error("Caption Studio API is unavailable on this build (404). Pull the captions integration to use tracks."));
        } else {
          setError(dom.captionError, error);
        }
      }
    }, "Building…");
  }

  async function loadArtifactCaptions() {
    clearError(dom.captionError);
    if (!state.job || !dom.captionArtifact.value) {
      setError(dom.captionError, new Error("Choose an artifact first."));
      return;
    }
    await withBusy(dom.captionArtifactLoad, async () => {
      try {
        const artifactId = dom.captionArtifact.value;
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(artifactId)}/captions`);
        state.caption.artifactId = artifactId;
        state.caption.track = null;
        state.caption.cues = (data.cues || []).map((cue) => ({ ...cue }));
        renderCaptionCues();
        await loadCaptionPreview().catch((error) => setError(dom.captionError, error));
        toast("Artifact captions loaded.");
      } catch (error) {
        setError(dom.captionError, error);
      }
    }, "Loading…");
  }

  function collectEditedCues() {
    const rows = $$(".cue-row", dom.captionCues);
    return rows.map((row, index) => {
      const base = state.caption.cues[index] || {};
      const start = Number($('[data-cue-field="start"]', row).value);
      const end = Number($('[data-cue-field="end"]', row).value);
      const text = $('[data-cue-field="text"]', row).value;
      return { ...base, start, end, text };
    });
  }

  async function saveCaptionTrack() {
    clearError(dom.captionError);
    if (state.caption.artifactId) {
      setError(dom.captionError, new Error("Artifact captions are immutable. Edit the caption track instead."));
      return;
    }
    if (!state.caption.track) {
      setError(dom.captionError, new Error("Build a caption track first."));
      return;
    }
    const cues = collectEditedCues();
    if (!cues.length) {
      setError(dom.captionError, new Error("Add at least one cue."));
      return;
    }
    await withBusy(dom.captionSave, async () => {
      try {
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/captions/${encodeURIComponent(state.caption.track.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ cues, style_id: dom.captionStyle.value || "clean" }),
        });
        state.caption.track = data.track || data;
        state.caption.cues = (data.track?.cues || cues).map((cue) => ({ ...cue }));
        renderCaptionCues();
        await loadCaptionPreview().catch((error) => setError(dom.captionError, error));
        toast("Caption cues saved.");
      } catch (error) {
        setError(dom.captionError, error);
      }
    }, "Saving…");
  }

  function artifactPosterPath(artifactId) {
    return `/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(artifactId)}/media/poster.jpg`;
  }

  function defaultSafeZones() {
    return {
      platform: { x: 0.08, y: 0.08, w: 0.84, h: 0.76 },
      caption: { x: 0.08, y: 0.68, w: 0.84, h: 0.16 },
    };
  }

  async function loadCaptionPreview() {
    clearError(dom.captionError);
    if (!state.job) return;
    let cues = state.caption.cues || [];
    let poster = "";
    let safe = defaultSafeZones();
    let duration = cues.reduce((max, cue) => Math.max(max, Number(cue.end) || 0), 0);
    if (state.caption.artifactId) {
      poster = artifactPosterPath(state.caption.artifactId);
    } else if (state.caption.track) {
      const preview = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/captions/${encodeURIComponent(state.caption.track.id)}/preview`);
      cues = preview.cues || cues;
      poster = preview.poster_url || "";
      safe = preview.safe_zones || safe;
      duration = Number(preview.duration) || duration;
    }
    if (!cues.length) throw new Error("No cues to preview.");
    state.caption.preview = { cues, safe_zones: safe, duration, style: state.caption.track?.style || {} };
    if (poster) {
      await setCaptionPreviewImage(poster);
    } else if (dom.captionPreviewImg) {
      dom.captionPreviewImg.hidden = true;
    }
    renderCaptionSafeZones(safe);
    dom.captionPreviewTime.max = String(Math.max(0.1, duration));
    dom.captionPreviewTime.value = "0";
    updateCaptionPreviewText(0);
  }

  async function setCaptionPreviewImage(path) {
    if (state.caption.previewUrl) {
      URL.revokeObjectURL(state.caption.previewUrl);
      state.caption.previewUrl = "";
    }
    if (dom.captionPreviewImg) dom.captionPreviewImg.hidden = true;
    const blob = await requestRaw(path, { cache: "no-store" });
    state.caption.previewUrl = URL.createObjectURL(blob);
    dom.captionPreviewImg.src = state.caption.previewUrl;
    dom.captionPreviewImg.hidden = false;
  }

  function renderCaptionSafeZones(safe) {
    if (!dom.captionPreviewSafe) return;
    const entries = safe && typeof safe === "object" ? Object.entries(safe) : [];
    dom.captionPreviewSafe.innerHTML = entries.map(([name, box]) => {
      if (!box) return "";
      const className = name === "platform" ? "caption-safe-platform" : "caption-safe-box";
      return `<div class="${className}" style="left:${Number(box.x || 0) * 100}%;top:${Number(box.y || 0) * 100}%;width:${Number(box.w || 0) * 100}%;height:${Number(box.h || 0) * 100}%"></div>`;
    }).join("");
    dom.captionPreviewSafe.hidden = !entries.length;
  }

  function updateCaptionPreviewText(time) {
    const preview = state.caption.preview;
    if (!preview) return;
    const cues = preview.cues || [];
    const cue = cues.find((item) => Number(item.start) <= time && time <= Number(item.end))
      || cues.filter((item) => Number(item.start) <= time).slice(-1)[0]
      || cues[0];
    dom.captionPreviewText.textContent = cue ? cue.text : "No cue at this time.";
    if (preview.style) {
      if (preview.style.color) dom.captionPreviewText.style.color = preview.style.color;
      dom.captionPreviewText.style.textTransform = preview.style.uppercase ? "uppercase" : "none";
      const scale = (dom.captionPreview?.clientWidth || 360) / 1080;
      const size = Number(preview.style.font_size || 56) * scale;
      dom.captionPreviewText.style.fontSize = `${Math.max(11, Math.min(28, size)).toFixed(1)}px`;
      if (preview.style.background && preview.style.background !== "#000000") {
        dom.captionPreviewText.style.background = preview.style.background;
      }
      if (preview.style.background_opacity !== undefined) {
        dom.captionPreviewText.style.background = `rgba(0,0,0,${Number(preview.style.background_opacity) || 0.55})`;
      }
    }
    dom.captionPreviewReadout.textContent = `${Number(time).toFixed(1)}s`;
  }

  async function exportCaptionSrt() {
    clearError(dom.captionError);
    let path = "";
    let filename = "captions.srt";
    if (state.caption.artifactId) {
      path = `/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(state.caption.artifactId)}/media/captions.srt`;
      filename = `${state.caption.artifactId}.srt`;
    } else if (state.caption.track) {
      path = `/api/jobs/${encodeURIComponent(state.jobId)}/captions/${encodeURIComponent(state.caption.track.id)}/srt`;
      filename = `${state.caption.track.id}.srt`;
    } else {
      setError(dom.captionError, new Error("Build or load captions first."));
      return;
    }
    await withBusy(dom.captionExport, async () => {
      try {
        await downloadPath(path, filename);
      } catch (error) {
        setError(dom.captionError, error);
      }
    }, "Exporting…");
  }

  // ---------------------------------------------------------------- packet

  function updateDescriptionCount() {
    const length = String(dom.packetDescription?.value || "").length;
    setText(dom.packetDescCount, `${length}/125`);
  }

  function updatePacketFilename() {
    if (!dom.packetFilename) return;
    const story = dom.packetStory.value || "story";
    const render = dom.packetRenderKey.value || "";
    const artifact = state.artifacts.find((item) => item.artifact_id === dom.packetArtifact.value);
    const target = artifact?.target || (render && state.job?.renders?.[render]?.target) || 30;
    dom.packetFilename.textContent = `${slug(story)}-${target}s-<packet>.mp4 · ${slug(story)}-packet-<packet>.zip`;
  }

  async function buildPacket(event) {
    event.preventDefault();
    clearError(dom.packetError);
    if (!state.job) {
      setError(dom.packetError, new Error("Open a job first."));
      return;
    }
    const titles = [dom.packetTitle1.value.trim(), dom.packetTitle2.value.trim(), dom.packetTitle3.value.trim()];
    const description = dom.packetDescription.value.trim();
    const hashtags = dom.packetHashtags.value.split(/[\s,]+/).map((tag) => tag.trim()).filter(Boolean);
    const artifactId = dom.packetArtifact.value;
    const renderKey = dom.packetRenderKey.value;
    const story = dom.packetStory.value.trim() || artifactId || renderKey;
    const coverTimes = [Number(dom.packetCover1.value), Number(dom.packetCover2.value)];
    if (!coverTimes.every((value) => Number.isFinite(value) && value >= 0)) {
      setError(dom.packetError, new Error("Both cover times must be non-negative numbers."));
      return;
    }
    if (!story) {
      setError(dom.packetError, new Error("Choose a story, artifact or render key."));
      return;
    }
    if (!titles.every(Boolean)) {
      setError(dom.packetError, new Error("All three titles are required."));
      return;
    }
    if (!description) {
      setError(dom.packetError, new Error("The 125-character description is required."));
      return;
    }
    if (!artifactId && !renderKey) {
      setError(dom.packetError, new Error("Choose an artifact or a ready render key."));
      return;
    }
    await withBusy(dom.packetBuild, async () => {
      try {
        const body = {
          story_id: story,
          titles,
          description,
          hashtags,
          cover_times: coverTimes,
          artifact_ids: artifactId ? [artifactId] : [],
          render_keys: !artifactId && renderKey ? [renderKey] : [],
        };
        const packet = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/packets`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        state.packet = packet;
        renderPacket(packet);
        toast("Publish packet built.");
      } catch (error) {
        setError(dom.packetError, error);
      }
    }, "Building…");
  }

  function renderPacket(packet) {
    if (!dom.packetResult) return;
    if (!packet) {
      dom.packetResult.innerHTML = '<p class="hint">No packet built in this session.</p>';
      return;
    }
    const media = (packet.media || []).map((item) => `
      <div class="creator-item-row"><div><strong>${escapeHtml(item.file || "media")}</strong><div class="creator-meta-row"><span class="creator-tag">${escapeHtml(item.artifact_id || "")}</span><span class="creator-tag">${Number(item.bytes || 0)} bytes</span></div></div><span class="creator-tag ok">MP4</span></div>`).join("");
    const covers = (packet.covers || []).map((cover) => `
      <div class="creator-item-row"><div><strong>${escapeHtml(cover.file || "cover")}</strong><div class="creator-meta-row"><span class="creator-tag">${Number(cover.time || 0).toFixed(1)}s</span></div></div><span class="creator-tag">JPG</span></div>`).join("");
    dom.packetResult.innerHTML = `
      <div class="batch-card">
        <header><div><h4>${escapeHtml(packet.packet_id || "packet")}</h4><div class="creator-meta-row"><span class="creator-tag ok">built</span><span class="creator-tag">${escapeHtml(packet.story_id || "")}</span></div></div>
        <button class="primary small" type="button" data-packet-zip="${escapeHtml(packet.packet_id || "")}">Download ZIP</button></header>
        <p class="hint">${escapeHtml(packet.description || "")}</p>
        <p class="hint">${(packet.titles || []).map(escapeHtml).join(" · ")}</p>
        <p class="hint">${(packet.hashtags || []).map(escapeHtml).join(" ")}</p>
        <div class="creator-item-list">${media}${covers}</div>
      </div>`;
  }

  async function downloadPacketZip(packetId) {
    const packet = state.packet;
    if (!packet || packet.packet_id !== packetId) {
      setError(dom.packetError, new Error("Build the packet again before downloading."));
      return;
    }
    try {
      await downloadPath(packet.zip_url || `/api/jobs/${encodeURIComponent(state.jobId)}/packets/${encodeURIComponent(packetId)}/zip`, packet.zip_file || `${packetId}.zip`);
    } catch (error) {
      setError(dom.packetError, error);
    }
  }

  // ---------------------------------------------------------------- preflight

  async function runPreflight() {
    clearError(dom.preflightError);
    if (!state.job) {
      setError(dom.preflightError, new Error("Open a job first."));
      return;
    }
    const story = dom.preflightStory.value;
    if (!story) {
      setError(dom.preflightError, new Error("Choose a story, artifact or render key."));
      return;
    }
    await withBusy(dom.preflightRun, async () => {
      try {
        const result = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/preflight?story_id=${encodeURIComponent(story)}`);
        state.preflight = result;
        state.preflightHidden = new Set();
        renderPreflight();
      } catch (error) {
        setError(dom.preflightError, error);
      }
    }, "Checking…");
  }

  function renderPreflight() {
    const data = state.preflight;
    if (!data) {
      renderEmpty(dom.preflightChecks, "Run preflight for a story or artifact.");
      renderEmpty(dom.preflightFindings, "No findings yet.");
      setText(dom.preflightSummary, "");
      return;
    }
    const checks = Object.entries(data.checks || {});
    setText(
      dom.preflightSummary,
      `${data.blocked ? "BLOCKED" : "advisory"} · ${data.media_source || "no media"}${data.narrative_only ? " · narrative only" : ""}`,
    );
    dom.preflightChecks.innerHTML = checks.map(([id, check]) => {
      const enabled = Boolean(check.enabled);
      const visible = enabled && !state.preflightHidden.has(id);
      return `
        <div class="check-row ${visible ? "" : "is-off"}" data-check-id="${escapeHtml(id)}">
          <input type="checkbox" ${visible ? "checked" : ""} ${enabled ? "" : "disabled"} data-preflight-toggle="${escapeHtml(id)}" aria-label="View ${escapeHtml(check.label || id)}">
          <div>
            <h4>${escapeHtml(check.label || id)} <span class="creator-tag ${check.severity === "block" ? "bad" : check.severity === "warn" ? "warn" : "ok"}">${escapeHtml(check.severity || "warn")}</span></h4>
            <p>${escapeHtml(check.style || "style")} · toggle ${escapeHtml(check.toggle || id)} · ${escapeHtml(check.status || "pass")}${check.reason ? ` · ${escapeHtml(check.reason)}` : ""}</p>
          </div>
          <span class="creator-tag">${escapeHtml(check.status || "")}</span>
        </div>`;
    }).join("") || '<p class="hint">No checks returned.</p>';
    renderPreflightFindings();
  }

  function renderPreflightFindings() {
    const data = state.preflight;
    if (!data) return;
    const visible = (data.findings || []).filter((finding) => !state.preflightHidden.has(finding.id));
    dom.preflightFindings.innerHTML = visible.length ? visible.map((finding) => `
      <div class="finding-card ${escapeHtml(finding.severity === "block" ? "block" : finding.severity === "warn" ? "warn" : "info")}">
        <header><div><h4>${escapeHtml(finding.toggle || finding.id)}</h4><div class="creator-meta-row"><span class="creator-tag ${finding.severity === "block" ? "bad" : finding.severity === "warn" ? "warn" : "ok"}">${escapeHtml(finding.severity)}</span></div></div></header>
        <p>${escapeHtml(finding.message || "")}</p>
        <p class="finding-suggestion">${escapeHtml(finding.suggestion || "")}</p>
      </div>`).join("") : '<div class="creator-empty-state"><p>No visible findings. Toggles here only change this view; server settings remain authoritative.</p></div>';
  }

  // ---------------------------------------------------------------- artifacts + shares

  async function loadArtifacts() {
    if (!state.jobId) {
      state.artifacts = [];
      return;
    }
    const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/artifacts`);
    state.artifacts = data.artifacts || [];
    populateCommonSelects();
    renderArtifacts();
  }

  async function loadShares() {
    if (!state.jobId) {
      state.shares = [];
      return;
    }
    const data = await request(`/api/shares?include_tokens=true&job_id=${encodeURIComponent(state.jobId)}`);
    state.shares = data.shares || [];
    renderShares();
  }

  function artifactMediaUrl(artifactId, name) {
    return `/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(artifactId)}/media/${name}`;
  }

  function renderArtifacts() {
    if (!dom.artifactList) return;
    setText(dom.artifactCount, `${state.artifacts.length} artifact${state.artifacts.length === 1 ? "" : "s"}`);
    if (!state.artifacts.length) {
      renderEmpty(dom.artifactList, "No artifacts. Render a cut with the trust-core pipeline first.");
      return;
    }
    dom.artifactList.innerHTML = state.artifacts.map((artifact) => {
      const id = artifact.artifact_id;
      const share = state.shares.find((row) => row.artifact_id === id && row.status !== "revoked");
      return `
        <article class="artifact-card" data-artifact-id="${escapeHtml(id)}">
          <header>
            <div><h4>${escapeHtml(artifact.title || id)}</h4><div class="creator-meta-row">
              <span class="creator-tag ${artifact.status === "ready" ? "ok" : "bad"}">${escapeHtml(artifact.status || "unknown")}</span>
              <span class="creator-tag">${escapeHtml(id)}</span>
              ${artifact.pinned ? '<span class="creator-tag ok">pinned</span>' : ""}
              <span class="creator-tag">${artifact.target || "?"}s · ${escapeHtml(artifact.aspect || "9:16")}</span>
              ${artifact.generation ? `<span class="creator-tag">gen ${artifact.generation}</span>` : ""}
            </div></div>
            <button class="ghost small" type="button" data-artifact-pin="${escapeHtml(id)}" data-pinned="${artifact.pinned ? "1" : "0"}">${artifact.pinned ? "Unpin" : "Pin"}</button>
          </header>
          <p class="hint">${escapeHtml(artifact.record_key || "")} · ${escapeHtml(artifact.resolved_encoder || "")} · ${artifact.cue_count ? `${artifact.cue_count} cues` : "no caption track"}</p>
          <div class="artifact-links">
            <button class="ghost small" type="button" data-artifact-download="${escapeHtml(id)}" data-kind="captions.srt">SRT</button>
            <button class="ghost small" type="button" data-artifact-download="${escapeHtml(id)}" data-kind="captions.vtt">VTT</button>
            <button class="ghost small" type="button" data-artifact-caption-preview="${escapeHtml(id)}">Caption preview</button>
            ${share ? `<button class="ghost small" type="button" data-share-copy="${escapeHtml(share.token || "")}">Copy review link</button>` : ""}
          </div>
          <div class="share-form">
            <input type="text" maxlength="120" placeholder="Review label" data-share-label="${escapeHtml(id)}">
            <input type="number" min="0" step="1" value="7" aria-label="Expiry days" data-share-days="${escapeHtml(id)}">
            <button class="primary small" type="button" data-share-create="${escapeHtml(id)}">Create review link</button>
          </div>
        </article>`;
    }).join("");
  }

  function renderShares() {
    if (!dom.shareList) return;
    if (!state.shares.length) {
      renderEmpty(dom.shareList, "No review links for this job.");
      return;
    }
    dom.shareList.innerHTML = state.shares.map((share) => {
      const token = share.token || "";
      const confirming = state.confirm[`share:${token}`] === "revoke";
      const status = share.status || (share.revoked_at ? "revoked" : "active");
      const expiry = share.expires_at ? new Date(Number(share.expires_at) * 1000).toLocaleString() : "never";
      return `
        <article class="share-card">
          <header><div><h4>${escapeHtml(share.label || "review link")}</h4><div class="creator-meta-row">
            <span class="creator-tag ${status === "active" ? "ok" : status === "expired" ? "warn" : "bad"}">${escapeHtml(status)}</span>
            ${share.artifact_id ? `<span class="creator-tag">${escapeHtml(share.artifact_id)}</span>` : ""}
            <span class="creator-tag">expires ${escapeHtml(expiry)}</span>
          </div></div></header>
          <div class="creator-actions">
            ${token ? `<button class="ghost small" type="button" data-share-copy="${escapeHtml(token)}">Copy URL</button>` : ""}
            ${token && status !== "revoked" ? (
              confirming
                ? `<span class="creator-inline-confirm">Revoke link? <button class="ghost small danger" type="button" data-share-revoke-confirm="${escapeHtml(token)}">Confirm revoke</button><button class="ghost small" type="button" data-share-revoke-abort="${escapeHtml(token)}">Keep</button></span>`
                : `<button class="ghost small" type="button" data-share-revoke="${escapeHtml(token)}">Revoke</button>`
            ) : ""}
          </div>
        </article>`;
    }).join("");
  }

  async function createShare(artifactId) {
    clearError(dom.artifactError);
    const button = $$("[data-share-create]", dom.artifactList)
      .find((node) => node.dataset.shareCreate === artifactId);
    const labelInput = $$("[data-share-label]", dom.artifactList)
      .find((node) => node.dataset.shareLabel === artifactId);
    const daysInput = $$("[data-share-days]", dom.artifactList)
      .find((node) => node.dataset.shareDays === artifactId);
    const label = labelInput ? labelInput.value.trim() : "";
    const days = daysInput ? Number(daysInput.value) : 7;
    await withBusy(button, async () => {
      try {
        const share = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/share`, {
          method: "POST",
          body: JSON.stringify({
            artifact_id: artifactId,
            label,
            expires_in_days: Number.isFinite(days) && days > 0 ? days : 0,
          }),
        });
        await loadShares();
        if (share.url) await copyText(absoluteUrl(share.url));
        toast("Review link created for this artifact.");
        renderArtifacts();
      } catch (error) {
        setError(dom.artifactError, error);
      }
    }, "Creating…");
  }

  async function pinArtifact(artifactId, currentlyPinned) {
    clearError(dom.artifactError);
    try {
      await request(`/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(artifactId)}/pin`, {
        method: "POST",
        body: JSON.stringify({ pinned: !currentlyPinned }),
      });
      await loadArtifacts();
      toast(currentlyPinned ? "Artifact unpinned." : "Artifact pinned.");
    } catch (error) {
      setError(dom.artifactError, error);
    }
  }

  async function revokeShare(token) {
    clearError(dom.artifactError);
    try {
      await request(`/api/shares/${encodeURIComponent(token)}`, {
        method: "PATCH",
        body: JSON.stringify({ revoked: true }),
      });
      delete state.confirm[`share:${token}`];
      await loadShares();
      renderArtifacts();
      toast("Review link revoked.");
    } catch (error) {
      setError(dom.artifactError, error);
    }
  }

  async function downloadArtifact(artifactId, kind) {
    clearError(dom.artifactError);
    try {
      await downloadPath(artifactMediaUrl(artifactId, kind), `${artifactId}.${kind.split(".").pop()}`);
    } catch (error) {
      setError(dom.artifactError, error);
    }
  }

  // ---------------------------------------------------------------- events

  function bind() {
    dom.open?.addEventListener("click", () => openCreator());
    dom.close?.addEventListener("click", closeCreator);
    dom.jobLoad?.addEventListener("click", () => {
      const jobId = dom.jobInput.value.trim();
      if (!jobId) {
        setError(dom.globalError, new Error("Enter a job id."));
        return;
      }
      state.jobId = jobId;
      loadJob(jobId).then(() => setScreen(state.screen)).catch((error) => setError(dom.globalError, error));
    });
    dom.jobInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") dom.jobLoad?.click();
    });
    dom.tabs?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-creator-tab]");
      if (button) setScreen(button.dataset.creatorTab);
    });
    window.addEventListener("hashchange", () => {
      const params = parseHash();
      if (params.screen) {
        openCreator(params.screen, params.job || state.jobId);
      } else if (document.body.classList.contains("creator-mode")) {
        document.body.classList.remove("creator-mode");
        dom.view.hidden = true;
        if (state.batchTimer) {
          clearInterval(state.batchTimer);
          state.batchTimer = null;
        }
      }
    });

    dom.batchForm?.addEventListener("submit", createBatch);
    dom.batchRefresh?.addEventListener("click", () => loadBatches());
    dom.batchList?.addEventListener("click", (event) => {
      const open = event.target.closest("[data-open-job]");
      if (open) {
        state.jobId = open.dataset.openJob;
        loadJob(state.jobId).then(() => setScreen("clipset")).catch((error) => setError(dom.globalError, error));
        return;
      }
      const retry = event.target.closest("[data-retry-job]");
      if (retry) {
        retryJob(retry.dataset.retryJob);
        return;
      }
      const action = event.target.closest("[data-batch-action]");
      if (action) batchAction(action.dataset.batchAction, action.dataset.batch);
    });

    dom.clipsetBuild?.addEventListener("click", buildClipSet);
    dom.clipsetV2?.addEventListener("click", runSelectionV2);
    dom.matrixBuild?.addEventListener("click", () => runMatrix(""));
    dom.tightenRun?.addEventListener("click", runTighten);
    dom.clipsetStories?.addEventListener("click", (event) => {
      const packet = event.target.closest("[data-story-packet]");
      if (packet) {
        const storyId = packet.dataset.storyPacket;
        const story = (state.clipset?.stories || []).find((item) => item.id === storyId);
        dom.packetStory.value = storyId;
        if (story && dom.packetTitle1 && !dom.packetTitle1.value) dom.packetTitle1.value = story.title || "";
        updatePacketFilename();
        setScreen("packet");
        return;
      }
      const matrix = event.target.closest("[data-story-matrix]");
      if (matrix) {
        runMatrix(matrix.dataset.storyMatrix);
        return;
      }
      if (event.target.closest("[data-clipset-save]")) {
        saveClipSetEdits();
        return;
      }
      const sentenceAction = event.target.closest("[data-sentence-action]");
      if (sentenceAction) {
        const storyCard = sentenceAction.closest("[data-story-card]");
        const storyId = storyCard?.dataset.storyCard;
        if (sentenceAction.dataset.sentenceAction === "exclude" || sentenceAction.dataset.sentenceAction === "include") {
          const sentenceRow = sentenceAction.closest("[data-sentence-id]");
          const sentenceId = Number(sentenceRow?.dataset.sentenceId);
          if (storyId && sentenceId !== undefined) {
            const list = state.clipsetEdits[storyId] || [];
            state.clipsetEdits[storyId] = sentenceAction.dataset.sentenceAction === "exclude"
              ? list.filter((id) => Number(id) !== sentenceId)
              : [...list.filter((id) => Number(id) !== sentenceId), sentenceId];
            renderClipSet();
          }
        } else if (storyId) {
          moveSentence(storyId, sentenceAction.dataset.sentenceAction);
        }
        return;
      }
      const beat = event.target.closest("[data-beat-action]");
      if (beat) {
        const sceneId = Number(beat.dataset.sceneId);
        if (beat.dataset.beatAction === "lock") {
          if (state.locks.has(sceneId)) state.locks.delete(sceneId);
          else state.locks.add(sceneId);
        } else if (beat.dataset.beatAction === "ban") {
          if (state.bans.has(sceneId)) state.bans.delete(sceneId);
          else state.bans.add(sceneId);
        }
        renderClipSet();
      }
    });
    dom.clipsetStories?.addEventListener("change", (event) => {
      const toggle = event.target.closest("[data-sentence-toggle]");
      if (!toggle) return;
      const row = toggle.closest("[data-sentence-id]");
      const card = toggle.closest("[data-story-card]");
      const storyId = card?.dataset.storyCard;
      const sentenceId = Number(row?.dataset.sentenceId);
      if (!storyId || !Number.isFinite(sentenceId)) return;
      const list = state.clipsetEdits[storyId] || [];
      state.clipsetEdits[storyId] = toggle.checked
        ? [...list.filter((id) => Number(id) !== sentenceId), sentenceId]
        : list.filter((id) => Number(id) !== sentenceId);
      renderClipSet();
    });

    dom.captionBuild?.addEventListener("click", buildCaptionTrack);
    dom.captionArtifactLoad?.addEventListener("click", loadArtifactCaptions);
    dom.captionSave?.addEventListener("click", saveCaptionTrack);
    dom.captionExport?.addEventListener("click", exportCaptionSrt);
    dom.captionPreviewRun?.addEventListener("click", () => loadCaptionPreview().catch((error) => setError(dom.captionError, error)));
    dom.captionPreviewTime?.addEventListener("input", () => updateCaptionPreviewText(Number(dom.captionPreviewTime.value)));
    dom.captionArtifact?.addEventListener("change", () => {
      if (dom.captionArtifact.value) {
        loadArtifactCaptions();
      } else {
        state.caption.artifactId = "";
        state.caption.track = null;
        state.caption.cues = [];
        renderCaptionCues();
      }
    });

    dom.packetForm?.addEventListener("submit", buildPacket);
    dom.packetDescription?.addEventListener("input", updateDescriptionCount);
    dom.packetStory?.addEventListener("input", updatePacketFilename);
    dom.packetArtifact?.addEventListener("change", () => {
      if (dom.packetArtifact.value) dom.packetRenderKey.value = "";
      updatePacketFilename();
    });
    dom.packetRenderKey?.addEventListener("change", () => {
      if (dom.packetRenderKey.value) dom.packetArtifact.value = "";
      updatePacketFilename();
    });
    dom.packetResult?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-packet-zip]");
      if (button) downloadPacketZip(button.dataset.packetZip);
    });

    dom.preflightRun?.addEventListener("click", runPreflight);
    dom.preflightChecks?.addEventListener("change", (event) => {
      const toggle = event.target.closest("[data-preflight-toggle]");
      if (!toggle) return;
      if (toggle.checked) state.preflightHidden.delete(toggle.dataset.preflightToggle);
      else state.preflightHidden.add(toggle.dataset.preflightToggle);
      renderPreflight();
    });

    dom.artifactRefresh?.addEventListener("click", () => {
      loadArtifacts().then(loadShares).then(() => {
        renderArtifacts();
        renderShares();
      }).catch((error) => setError(dom.artifactError, error));
    });
    dom.artifactList?.addEventListener("click", (event) => {
      const pin = event.target.closest("[data-artifact-pin]");
      if (pin) {
        pinArtifact(pin.dataset.artifactPin, pin.dataset.pinned === "1");
        return;
      }
      const download = event.target.closest("[data-artifact-download]");
      if (download) {
        downloadArtifact(download.dataset.artifactDownload, download.dataset.kind);
        return;
      }
      const preview = event.target.closest("[data-artifact-caption-preview]");
      if (preview) {
        dom.captionArtifact.value = preview.dataset.artifactCaptionPreview;
        setScreen("captions");
        loadArtifactCaptions().catch((error) => setError(dom.captionError, error));
        return;
      }
      const create = event.target.closest("[data-share-create]");
      if (create) {
        createShare(create.dataset.shareCreate);
      }
    });
    dom.shareList?.addEventListener("click", (event) => {
      const copy = event.target.closest("[data-share-copy]");
      if (copy) {
        const token = copy.dataset.shareCopy;
        if (token) copyText(absoluteUrl(`/r/${token}`));
        return;
      }
      const revoke = event.target.closest("[data-share-revoke]");
      if (revoke) {
        state.confirm[`share:${revoke.dataset.shareRevoke}`] = "revoke";
        renderShares();
        return;
      }
      const abort = event.target.closest("[data-share-revoke-abort]");
      if (abort) {
        delete state.confirm[`share:${abort.dataset.shareRevokeAbort}`];
        renderShares();
        return;
      }
      const confirm = event.target.closest("[data-share-revoke-confirm]");
      if (confirm) revokeShare(confirm.dataset.shareRevokeConfirm);
    });
  }

  // ---------------------------------------------------------------- boot

  function init() {
    bind();
    updateDescriptionCount();
    const params = parseHash();
    if (params.screen) {
      openCreator(params.screen, params.job || "");
    } else if (document.body.classList.contains("creator-mode")) {
      openCreator(state.screen, params.job || "");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
