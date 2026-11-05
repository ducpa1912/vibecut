/* Creator workspace. Loaded after app.js; uses the small vibecutBridge. */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const SCREENS = ["clipset", "captions", "preflight", "packet", "artifacts", "queue"];
  const br = () => window.vibecutBridge || {};

  const dom = {
    open: $("#creator-open"),
    close: $("#creator-close"),
    view: $("#creator-view"),
    tabs: $("#creator-tabs"),
    recent: $("#creator-recent"),
    jobInput: $("#creator-job-input"),
    jobLoad: $("#creator-job-load"),
    debug: $("#creator-debug"),
    context: $("#creator-context"),
    globalError: $("#creator-global-error"),

    batchForm: $("#batch-form"),
    batchName: $("#batch-name"),
    batchMax: $("#batch-max"),
    batchMode: $("#batch-mode"),
    batchRights: $("#batch-rights"),
    batchTargets: $("#batch-target-fieldset"),
    batchItems: $("#batch-items"),
    batchCreate: $("#batch-create"),
    batchError: $("#batch-error"),
    storyQueueList: $("#story-queue-list"),
    storyQueueError: $("#story-queue-error"),
    storyQueueRefresh: $("#story-queue-refresh"),
    storyQueueBanner: $("#story-queue-banner"),
    clipsetQueue: $("#clipset-queue"),
    batchList: $("#batch-list"),
    batchRefresh: $("#batch-refresh"),

    clipsetCount: $("#clipset-count"),
    clipsetPrompt: $("#clipset-prompt"),
    clipsetBuild: $("#clipset-build"),
    clipsetReadAnalysis: $("#clipset-read-analysis"),
    clipsetAnalysis: $("#clipset-analysis"),
    analysisTabs: $("#analysis-tabs"),
    analysisOriginal: $("#analysis-original"),
    analysisBeta: $("#analysis-beta"),
    clipsetOriginalOutput: $("#clipset-original-output"),
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
    captionFontSize: $("#caption-font-size"),
    captionColor: $("#caption-color"),
    captionBgOpacity: $("#caption-bg-opacity"),
    captionPosition: $("#caption-position"),
    captionUppercase: $("#caption-uppercase"),
    captionError: $("#caption-error"),
    captionMeta: $("#caption-meta"),
    captionCues: $("#caption-cues"),
    captionPreview: $("#caption-preview"),
    captionPreviewImg: $("#caption-preview-img"),
    captionPreviewSafe: $("#caption-preview-safe"),
    captionPreviewText: $("#caption-preview-text"),
    captionPreviewEmpty: $("#caption-preview-empty"),
    captionPreviewTime: $("#caption-preview-time"),
    captionPreviewReadout: $("#caption-preview-readout"),

    packetForm: $("#packet-form"),
    packetStory: $("#packet-story"),
    packetArtifact: $("#packet-artifact"),
    packetRenderKey: $("#packet-render-key"),
    packetNeedsRender: $("#packet-needs-render"),
    packetRenderStory: $("#packet-render-story"),
    packetSuggest: $("#packet-suggest"),
    packetTitle1: $("#packet-title-1"),
    packetTitle2: $("#packet-title-2"),
    packetTitle3: $("#packet-title-3"),
    packetTitle1Count: $("#packet-title-1-count"),
    packetTitle2Count: $("#packet-title-2-count"),
    packetTitle3Count: $("#packet-title-3-count"),
    packetDescription: $("#packet-description"),
    packetDescCount: $("#packet-desc-count"),
    packetHashtags: $("#packet-hashtags"),
    packetPinComment: $("#packet-pin-comment"),
    packetCover1: $("#packet-cover-1"),
    packetCover2: $("#packet-cover-2"),
    packetCoverImg1: $("#packet-cover-img-1"),
    packetCoverImg2: $("#packet-cover-img-2"),
    packetFilename: $("#packet-filename"),
    packetBuild: $("#packet-build"),
    packetError: $("#packet-error"),
    packetResult: $("#packet-result"),
    packetHistory: $("#packet-history"),

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
    screen: "clipset",
    jobId: "",
    job: null,
    loadingJob: "",
    jobLoading: false,
    recentJobs: [],
    recentLoading: false,
    artifacts: [],
    artifactRenders: {},
    artifactLoading: false,
    shares: [],
    freshShares: [],
    clipset: null,
    clipsetEdits: {},
    clipsetLoading: false,
    storyAspects: {},
    storyQueues: [],
    storyQueueTimer: null,
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
    packets: [],
    preflight: null,
    preflightHidden: new Set(),
    preflightLoading: false,
    preflightSelection: "",
    batches: [],
    batchTimer: null,
    batchLoading: false,
    confirm: {},
    selectedArtifact: "",
    renderJobs: {},
    renderPollers: {},
    renderInFlight: false,
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

  function redactPaths(text) {
    return String(text || "")
      .replace(/(?:[A-Za-z]:\\|\/Users\/|\/home\/|\/Volumes\/|\/private\/|\/var\/|\/tmp\/|\/opt\/|\/mnt\/)[^\s"'<>]+/g, "[local path]")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function humanError(error) {
    const detail = error && (error.detail || (error.payload && error.payload.detail));
    let message = error && error.message ? error.message : "Request failed.";
    let code = error && error.code ? error.code : "";
    let suggestion = "";
    if (detail && typeof detail === "object") {
      code = code || detail.code || "";
      message = detail.message || message;
      suggestion = detail.suggestion || "";
    } else if (typeof detail === "string") {
      message = detail;
    }
    if (!code && typeof message === "string") {
      const match = message.match(/"code"\s*:\s*"([^"]+)"/);
      if (match) code = match[1];
    }
    if (typeof message === "string") {
      const trimmed = message.trim();
      if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
        try {
          const parsed = JSON.parse(trimmed);
          if (parsed && typeof parsed === "object") {
            code = code || parsed.code || "";
            message = parsed.message || message;
            suggestion = suggestion || parsed.suggestion || "";
          }
        } catch (_) { /* keep the original text */ }
      }
    }
    const friendly = {
      story_render_unavailable: "Story rendering is not available in this build yet. Open the story in Smart Cut instead.",
      render_failed: "The render did not finish. Try again, or render a shorter story.",
      artifact_not_found: "That render is not ready yet. Wait for it to finish, then refresh artifacts.",
      artifact_not_ready: "That artifact is still rendering. Wait for it to finish, then refresh artifacts.",
      captions_missing: "This cut has no caption track yet. Build captions first.",
      packet_artifact_missing: "Build a packet from a ready artifact. Render the story first.",
      share_store_unreadable: "The review-link store cannot be read. Check the data folder, then retry.",
    }[code];
    let text = friendly || (typeof message === "string" ? message : "Request failed.");
    if (["", "null", "undefined", "[object Object]"].includes(text.trim())) text = "Request failed.";
    if (!friendly && suggestion) text = `${text} ${suggestion}`;
    text = redactPaths(text);
    return text || "Request failed.";
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

  function captureFocus() {
    const node = document.activeElement;
    if (!node || !dom.view || !dom.view.contains(node)) return null;
    const key = node.dataset ? node.dataset.focusKey || "" : "";
    const id = node.id || "";
    if (!key && !id) return null;
    const snapshot = { key, id };
    if (typeof node.selectionStart === "number" && typeof node.selectionEnd === "number") {
      try {
        snapshot.start = node.selectionStart;
        snapshot.end = node.selectionEnd;
      } catch (_) { /* not a text control */ }
    }
    return snapshot;
  }

  function restoreFocus(snapshot) {
    if (!snapshot) return;
    let node = null;
    if (snapshot.key) {
      const escaped = window.CSS && CSS.escape ? CSS.escape(snapshot.key) : snapshot.key.replace(/"/g, '\\"');
      node = dom.view.querySelector(`[data-focus-key="${escaped}"]`);
    }
    if (!node && snapshot.id) node = document.getElementById(snapshot.id);
    if (!node || typeof node.focus !== "function") return;
    node.focus({ preventScroll: true });
    if (typeof snapshot.start === "number" && typeof node.setSelectionRange === "function") {
      try { node.setSelectionRange(snapshot.start, snapshot.end); } catch (_) { /* not a text control */ }
    }
  }

  function withFocusPreserved(render) {
    const snapshot = captureFocus();
    render();
    restoreFocus(snapshot);
  }

  function focusByKey(key) {
    if (!key || !dom.view) return;
    const escaped = window.CSS && CSS.escape ? CSS.escape(key) : key.replace(/"/g, '\\"');
    const node = dom.view.querySelector(`[data-focus-key="${escaped}"]`);
    if (node) node.focus({ preventScroll: true });
  }

  function readyLegacyRenders() {
    const renders = state.artifactRenders && Object.keys(state.artifactRenders).length
      ? state.artifactRenders
      : (state.job?.renders || {});
    return Object.entries(renders || {})
      .filter(([, record]) => record && record.status === "ready")
      .map(([key, record]) => ({ key, record }));
  }

  function storyById(storyId) {
    return (state.clipset?.stories || []).find((story) => story.id === storyId) || null;
  }

  function artifactForStory(storyId) {
    if (!storyId) return null;
    const exact = state.artifacts.find((item) => item.story_id === storyId && item.status === "ready");
    if (exact) return exact;
    const assigned = state.artifacts.find((item) => item.story_id === storyId);
    if (assigned) return assigned;
    const story = storyById(storyId);
    if (!story) return null;
    const target = Math.max(1, Math.round(Number(story.dur) || 0));
    const candidates = state.artifacts.filter((item) => Number(item.target) === target);
    return candidates.length === 1 ? candidates[0] : null;
  }

  function artifactById(artifactId) {
    return state.artifacts.find((item) => item.artifact_id === artifactId) || null;
  }

  function artifactForPacketSelection(value) {
    return artifactById(value) || artifactForStory(value);
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
      const active = button.dataset.creatorTab === screen;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    $$("[data-creator-panel]", dom.view).forEach((panel) => {
      panel.hidden = panel.dataset.creatorPanel !== screen;
    });
  }

  function focusActiveTab() {
    const button = dom.tabs?.querySelector('[role="tab"][aria-selected="true"]');
    if (button) button.focus({ preventScroll: true });
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
    const bridgeJob = br().getJob && br().getJob();
    const wanted = jobId || (bridgeJob && bridgeJob.id) || (state.job && state.job.id) || params.job || "";
    const chosen = wanted ? (screen || params.screen || "clipset") : "queue";
    document.body.classList.add("creator-mode");
    dom.view.hidden = false;
    if (wanted) {
      state.jobId = wanted;
      dom.jobInput.value = wanted;
    }
    setScreen(chosen, wanted);
    loadRecentJobs().catch(() => {});
    loadStoryQueues().catch(() => {});
    requestAnimationFrame(focusActiveTab);
  }

  function closeCreator() {
    document.body.classList.remove("creator-mode");
    dom.view.hidden = true;
    if (state.batchTimer) {
      clearInterval(state.batchTimer);
      state.batchTimer = null;
    }
    Object.values(state.renderPollers).forEach((timer) => clearTimeout(timer));
    state.renderPollers = {};
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
        state.preflightSelection = "";
        state.selection = null;
        state.matrix = null;
        state.clipset = null;
        state.selectedArtifact = "";
        state.renderJobs = {};
        state.freshShares = [];
        state.artifacts = [];
        state.artifactRenders = {};
        state.shares = [];
        Object.values(state.renderPollers).forEach((timer) => clearTimeout(timer));
        state.renderPollers = {};
        const oldPreviewUrl = state.caption.previewUrl;
        state.caption = { track: null, cues: [], artifactId: "", preview: null, previewUrl: "" };
        state.preflightHidden = new Set();
        if (oldPreviewUrl) URL.revokeObjectURL(oldPreviewUrl);
        for (const input of [dom.packetTitle1, dom.packetTitle2, dom.packetTitle3, dom.packetDescription, dom.packetHashtags, dom.packetPinComment]) {
          if (input) input.value = "";
        }
        if (dom.packetRenderKey) dom.packetRenderKey.value = "";
        updateTitleCounts();
        updateDescriptionCount();
        renderPacket(null);
        renderPreflight();
        renderCaptionCues();
        renderSelection();
        renderMatrix();
        renderArtifacts();
        renderShares();
        if (dom.captionPreviewImg) {
          dom.captionPreviewImg.hidden = true;
          dom.captionPreviewImg.removeAttribute("src");
        }
        if (dom.captionPreviewText) dom.captionPreviewText.hidden = true;
        if (dom.captionPreviewEmpty) dom.captionPreviewEmpty.hidden = false;
        if (dom.captionPreviewSafe) dom.captionPreviewSafe.innerHTML = "";
      }
      writeHash(state.jobId, state.screen);
      setJobContext();
      await loadArtifacts().catch((error) => setError(dom.globalError, error));
      await loadClipSets().catch((error) => setError(dom.clipsetError, error));
      populateCommonSelects();
      await refreshScreen(state.screen);
      loadRecentJobs().catch(() => {});
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
    if (screen === "queue") {
      loadStoryQueues().catch((error) => setError(dom.storyQueueError, error));
      return loadBatches();
    }
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
      updateCaptionControls();
      return;
    }
    if (screen === "packet") {
      populateCommonSelects();
      loadPacketHistory().catch((error) => setError(dom.packetError, error));
      updatePacketNeedsRender();
      updatePacketFilename();
      updatePacketCovers();
      return;
    }
    if (screen === "preflight") {
      populateCommonSelects();
      maybeAutoPreflight();
      return;
    }
    if (screen === "artifacts") {
      await loadArtifacts();
      await loadShares();
      renderArtifacts();
      renderShares();
    }
  }

  function packetStoryValue() {
    return dom.packetStory?.value || "";
  }

  function selectedPacketStory() {
    const value = packetStoryValue();
    if (!value) return null;
    return storyById(value) || null;
  }

  function packetStoryId() {
    const value = packetStoryValue();
    if (!value) return "";
    const story = storyById(value);
    if (story) return story.id;
    const artifact = artifactById(value);
    return artifact?.story_id || value;
  }

  function shortTitle(value, limit = 64) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    if (text.length <= limit) return text;
    const cut = text.slice(0, limit - 1);
    const space = cut.lastIndexOf(" ");
    // Cut at the last word boundary; a hard slice left titles ending in "o…".
    const base = space >= Math.max(8, Math.floor((limit - 1) * 0.55))
      ? cut.slice(0, space)
      : cut;
    return `${base.trimEnd()}…`;
  }

  function titleCandidates(story) {
    const fallback = story ? shortTitle(story.title || "Untitled story", 90) : "Untitled story";
    const hook = shortTitle((story?.hook || {}).text || "", 90);
    const payoff = shortTitle((story?.payoff || {}).text || "", 90);
    const values = [fallback, hook, payoff, `${fallback} · alt`]
      .map((value) => shortTitle(value, 100))
      .filter(Boolean);
    const unique = [];
    for (const value of values) {
      if (!unique.some((item) => item.toLowerCase() === value.toLowerCase())) unique.push(value);
      if (unique.length === 3) break;
    }
    while (unique.length < 3) unique.push(`${fallback} ${unique.length + 1}`.slice(0, 100));
    return unique;
  }

  function hashtagsForStory(story) {
    const stop = new Set([
      "the", "and", "for", "with", "this", "that", "your", "you", "from", "have",
      "about", "into", "they", "them", "there", "their", "what", "when", "where",
      "will", "just", "like", "more", "than", "then", "very", "can", "not", "but",
      "are", "was", "were", "our", "out", "get", "got", "has", "how", "why", "who",
      "all", "one", "two", "his", "her", "its", "it's", "i'm", "don't", "doesn't",
      "today", "want", "show", "plan", "week", "short", "shorts", "video", "videos",
      "gonna", "really", "know", "think", "make", "made", "take", "took", "come",
      "came", "look", "looks", "going", "day", "days", "new", "first", "next",
      "last", "back", "over", "after", "before", "because", "while", "too", "also",
      "only", "even", "still", "being", "been", "does", "did", "doing", "done",
      "use", "using", "used", "every", "much", "many", "some", "any", "own",
      "same", "other", "now", "here", "thing", "things", "stuff", "way", "ways",
      "lot", "lots", "people",
    ]);
    const source = [
      story?.title || "",
      (story?.hook || {}).text || "",
      (story?.payoff || {}).text || "",
    ].join(" ").toLowerCase();
    const tags = [];
    for (const word of source.match(/[a-z0-9]{3,}/g) || []) {
      if (stop.has(word) || tags.includes(`#${word}`)) continue;
      tags.push(`#${word}`);
      if (tags.length >= 6) break;
    }
    for (const tag of ["#shorts", "#creator", "#video"]) {
      if (!tags.includes(tag)) tags.push(tag);
      if (tags.length >= 3) break;
    }
    return tags.slice(0, 8).join(" ");
  }

  function storyCopy(story) {
    const titles = titleCandidates(story);
    const hook = String((story?.hook || {}).text || "").replace(/\s+/g, " ").trim();
    const description = (hook || story?.title || "").slice(0, 125);
    return {
      titles,
      description,
      hashtags: hashtagsForStory(story),
      pin: hook ? `${hook.slice(0, 160)}${hook.length > 160 ? "…" : ""}` : (story?.title || ""),
    };
  }

  function updateTitleCounts() {
    const pairs = [
      [dom.packetTitle1, dom.packetTitle1Count],
      [dom.packetTitle2, dom.packetTitle2Count],
      [dom.packetTitle3, dom.packetTitle3Count],
    ];
    for (const [input, counter] of pairs) {
      if (input && counter) setText(counter, `${input.value.length}/100`);
    }
  }

  function fillPacketCopy({ force = false } = {}) {
    const story = selectedPacketStory();
    const artifact = artifactById(dom.packetArtifact?.value || "") || artifactForStory(story?.id);
    if (!story && !artifact) return false;
    const copy = storyCopy(story || { title: artifact?.title, hook: { text: "" } });
    const fill = (input, value) => {
      if (!input) return;
      if (force || !input.value.trim()) input.value = value;
    };
    fill(dom.packetTitle1, copy.titles[0]);
    fill(dom.packetTitle2, copy.titles[1]);
    fill(dom.packetTitle3, copy.titles[2]);
    fill(dom.packetDescription, copy.description);
    fill(dom.packetHashtags, copy.hashtags);
    fill(dom.packetPinComment, copy.pin);
    updateTitleCounts();
    updateDescriptionCount();
    return true;
  }



  function setSelectOptions(select, options, preferred = "") {
    if (!select) return;
    const current = select.value;
    select.innerHTML = options.map((item) => (
      `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`
    )).join("");
    const values = options.map((item) => String(item.value));
    const desired = [current, preferred, state.selectedArtifact]
      .map((value) => String(value || ""))
      .find((value) => value && values.includes(value));
    if (desired) select.value = desired;
    else if (values.includes("")) select.value = "";
    else select.value = options[0]?.value || "";
  }

  function populateCommonSelects() {
    const job = state.job;
    if (!job) return;
    const readyRenders = readyLegacyRenders();

    setSelectOptions(dom.packetRenderKey, [
      { value: "", label: "Choose a ready render" },
      ...readyRenders.map(({ key, record }) => ({
        value: key,
        label: `${key} · ${record.target || "?"}s · ${record.aspect || "9:16"}`,
      })),
    ]);

    const artifactOptions = state.artifacts.map((artifact) => ({
      value: artifact.artifact_id,
      label: `${artifact.title || "Artifact"} · ${artifact.status || "unknown"} · ${artifact.target || "?"}s`,
    }));
    const selectedArtifact = artifactById(state.selectedArtifact);
    setSelectOptions(dom.captionArtifact, [{ value: "", label: "Current cut" }, ...artifactOptions], state.caption.artifactId);
    setSelectOptions(dom.packetArtifact, [{ value: "", label: "Choose a ready artifact" }, ...artifactOptions], selectedArtifact?.artifact_id || "");

    const storyOptions = (state.clipset?.stories || []).map((story) => ({
      value: story.id,
      label: `${story.title || "Story"} · ${fmtDuration(story.dur)}`,
    }));
    const storyIds = new Set((state.clipset?.stories || []).map((story) => story.id));
    const orphanArtifacts = state.artifacts
      .filter((artifact) => !artifact.story_id || !storyIds.has(artifact.story_id))
      .map((artifact) => ({
        value: artifact.artifact_id,
        label: `Artifact · ${artifact.title || artifact.artifact_id} · ${artifact.target || "?"}s`,
      }));
    const packetStoryOptions = [...storyOptions, ...orphanArtifacts];
    if (!packetStoryOptions.length) packetStoryOptions.push({ value: "", label: "No stories yet" });
    const preferredStory = selectedArtifact?.story_id && storyIds.has(selectedArtifact.story_id)
      ? selectedArtifact.story_id
      : (packetStoryOptions.find((item) => item.value)?.value || "");
    setSelectOptions(dom.packetStory, packetStoryOptions, preferredStory);
    const inferredArtifact = artifactForStory(packetStoryValue());
    if (inferredArtifact && !dom.packetArtifact.value) {
      dom.packetArtifact.value = inferredArtifact.artifact_id;
    }

    const preflightOptions = [
      ...storyOptions.map((item) => ({ ...item, label: `Story · ${item.label}` })),
      ...artifactOptions.map((item) => ({ ...item, label: `Artifact · ${item.label}` })),
    ];
    if (!preflightOptions.length) {
      for (const target of [30, 15, 60]) {
        preflightOptions.push({ value: String(target), label: `Auto plan · ${target}s` });
      }
    }
    setSelectOptions(dom.preflightStory, preflightOptions, selectedArtifact?.artifact_id || state.artifacts[0]?.artifact_id || "");

    const targetMap = new Map();
    const pushTarget = (value, label) => {
      const key = String(value || "");
      if (!key || targetMap.has(key)) return;
      targetMap.set(key, label);
    };
    const currentArtifact = artifactById(state.caption.artifactId) || selectedArtifact || state.artifacts[0];
    if (currentArtifact?.target) {
      pushTarget(currentArtifact.target, `Artifact · ${currentArtifact.title || "render"} · ${currentArtifact.target}s`);
    }
    const stories = state.clipset?.stories || [];
    for (const story of stories) {
      pushTarget(`story:${story.id}`, `Story · ${story.title || story.id} · ${fmtDuration(story.dur)}`);
    }
    for (const target of [15, 30, 60]) pushTarget(target, `Compatibility · ${target}s`);
    const captionDefault = stories.length ? `story:${stories[0].id}` : (currentArtifact?.target || "");
    setSelectOptions(dom.captionTarget, [...targetMap.entries()].map(([value, label]) => ({ value, label })), dom.captionTarget.value || captionDefault);

    fillPacketCopy({ onlyBlank: true });
    updatePacketNeedsRender();
    updatePacketFilename();
    updatePacketCovers();
  }

  // ---------------------------------------------------------------- queue / batch

  async function loadRecentJobs() {
    if (state.recentLoading) return;
    state.recentLoading = true;
    try {
      const data = await request("/api/jobs");
      state.recentJobs = Array.isArray(data.jobs) ? data.jobs : [];
      if (dom.recent) {
        const current = state.jobId;
        dom.recent.innerHTML = [
          '<option value="">Choose a recent job</option>',
          ...state.recentJobs.map((job) => {
            const bits = [job.name || job.id, fmtDuration(job.duration), job.status || ""]
              .filter(Boolean).join(" · ");
            return `<option value="${escapeHtml(job.id)}">${escapeHtml(bits)}</option>`;
          }),
        ].join("");
        if (state.recentJobs.some((job) => job.id === current)) dom.recent.value = current;
      }
    } catch (error) {
      if (state.screen === "queue") setError(dom.batchError, error);
      throw error;
    } finally {
      state.recentLoading = false;
    }
  }

  function batchStateTag(value) {
    const stateName = String(value || "queued");
    const klass = ["done"].includes(stateName) ? "ok"
      : ["failed", "cancelled", "interrupted"].includes(stateName) ? "bad"
        : ["running", "paused"].includes(stateName) ? "warn" : "";
    return `<span class="creator-tag ${klass}">${escapeHtml(stateName)}</span>`;
  }

  function renderBatches() {
    withFocusPreserved(renderBatchesInner);
  }

  function renderBatchesInner() {
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
        const targets = Array.isArray(item.targets) ? item.targets : [];
        return `
          <div class="creator-item-row">
            <div>
              <strong>${escapeHtml(path)}</strong>
              <div class="creator-meta-row">
                ${batchStateTag(item.state)}
                <span class="creator-tag">try ${Number(item.attempts || 0)}</span>
                ${targets.length ? `<span class="creator-tag">render ${targets.map((target) => `${target}s`).join(", ")}</span>` : '<span class="creator-tag">analysis only</span>'}
                ${item.job_id ? `<span class="creator-tag">job ${escapeHtml(item.job_id)}</span>` : ""}
              </div>
              ${item.error ? `<p class="hint">${escapeHtml(redactPaths(item.error))}</p>` : ""}
            </div>
            <div class="creator-actions">
              ${item.job_id ? `<button class="ghost small" type="button" data-focus-key="batch-open:${escapeHtml(item.job_id)}" data-open-job="${escapeHtml(item.job_id)}">Open</button>` : ""}
              ${canRetry ? `<button class="ghost small" type="button" data-focus-key="batch-retry:${escapeHtml(item.job_id)}" data-retry-job="${escapeHtml(item.job_id)}">Retry job</button>` : ""}
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
          ${batch.error ? `<p class="hint">${escapeHtml(redactPaths(batch.error))}</p>` : ""}
          <div class="creator-actions" style="margin-top:9px">
            ${canResume ? `<button class="ghost small" type="button" data-focus-key="batch:${escapeHtml(batch.id)}:resume" data-batch-action="resume" data-batch="${escapeHtml(batch.id)}">Resume</button>` : ""}
            ${canPause ? `<button class="ghost small" type="button" data-focus-key="batch:${escapeHtml(batch.id)}:pause" data-batch-action="pause" data-batch="${escapeHtml(batch.id)}">Pause</button>` : ""}
            ${canCancel ? (
              confirming
                ? `<span class="creator-inline-confirm">Cancel batch? <button class="ghost small danger" type="button" data-focus-key="batch:${escapeHtml(batch.id)}:cancel-confirm" data-batch-action="cancel-confirm" data-batch="${escapeHtml(batch.id)}">Confirm cancel</button><button class="ghost small" type="button" data-focus-key="batch:${escapeHtml(batch.id)}:cancel-abort" data-batch-action="cancel-abort" data-batch="${escapeHtml(batch.id)}">Keep</button></span>`
                : `<button class="ghost small" type="button" data-focus-key="batch:${escapeHtml(batch.id)}:cancel" data-batch-action="cancel" data-batch="${escapeHtml(batch.id)}">Cancel</button>`
            ) : ""}
          </div>
          <div class="creator-item-list">${items || '<p class="hint">No items.</p>'}</div>
        </article>`;
    }).join("");
  }

  // ---------------------------------------------------------------- story queue

  const QUEUE_LABELS = {
    queued: "waiting", running: "rendering", done: "done", failed: "failed",
    interrupted: "interrupted", cancelled: "cancelled", paused: "paused",
  };

  async function loadStoryQueues() {
    const data = await request("/api/story-queues");
    state.storyQueues = data.queues || [];
    renderStoryQueues();
    renderStoryQueueBanner(data.interrupted || []);
    const active = state.storyQueues.some((queue) => ["queued", "running"].includes(queue.status));
    if (active && !state.storyQueueTimer) {
      state.storyQueueTimer = setInterval(() => {
        if (!document.body.classList.contains("creator-mode")) return;
        loadStoryQueues().catch(() => {});
      }, 3500);
    }
    if (!active && state.storyQueueTimer) {
      clearInterval(state.storyQueueTimer);
      state.storyQueueTimer = null;
      refreshArtifactsOnly().catch(() => {});
    }
  }

  function renderStoryQueueBanner(interrupted) {
    if (!dom.storyQueueBanner) return;
    if (!interrupted.length) {
      dom.storyQueueBanner.hidden = true;
      dom.storyQueueBanner.innerHTML = "";
      return;
    }
    const waiting = interrupted.reduce((total, queue) => total + (queue.items || []).filter((item) => ["queued", "interrupted"].includes(item.state)).length, 0);
    dom.storyQueueBanner.innerHTML = `
      <span>VibeCut stopped during a story queue. ${waiting} stor${waiting === 1 ? "y is" : "ies are"} waiting; finished stories are kept.</span>
      <button class="primary small" type="button" data-story-queue-action="resume" data-queue-id="${escapeHtml(interrupted[0].id)}">Resume</button>`;
    dom.storyQueueBanner.hidden = false;
  }

  function renderStoryQueues() {
    if (!dom.storyQueueList) return;
    if (!state.storyQueues.length) {
      dom.storyQueueList.innerHTML = '<p class="hint">No story queues yet. Use Queue stories on the Clip Set screen.</p>';
      return;
    }
    dom.storyQueueList.innerHTML = state.storyQueues.map((queue) => {
      const actions = [];
      if (["queued", "running"].includes(queue.status)) actions.push(["pause", "Pause"], ["cancel", "Cancel"]);
      if (queue.status === "paused") actions.push(["resume", "Resume"], ["cancel", "Cancel"]);
      const rows = (queue.items || []).map((item, index) => `
        <li><span class="mono">${index + 1}.</span> ${escapeHtml(item.title || item.story_id)} · ${escapeHtml(item.aspect)}
          <span class="creator-tag ${item.state === "done" ? "ok" : (["failed", "interrupted"].includes(item.state) ? "bad" : "")}">${escapeHtml(QUEUE_LABELS[item.state] || item.state)}</span>
          ${item.error ? `<span class="hint">${escapeHtml(item.error)}</span>` : ""}</li>`).join("");
      return `
        <article class="batch-card">
          <header><div><h4>${escapeHtml(queue.message || queue.status)}</h4><div class="creator-meta-row">
            <span class="creator-tag">${Math.round(Number(queue.progress || 0) * 100)}%</span>
            <span class="creator-tag">${(queue.items || []).length} stories</span>
          </div></div>
          <div class="creator-actions">${actions.map(([action, label]) => `<button class="ghost small" type="button" data-story-queue-action="${action}" data-queue-id="${escapeHtml(queue.id)}">${label}</button>`).join("")}</div></header>
          <ol class="story-queue-items">${rows}</ol>
        </article>`;
    }).join("");
  }

  async function storyQueueAction(action, queueId, button) {
    clearError(dom.storyQueueError);
    await withBusy(button, async () => {
      try {
        await request(`/api/story-queues/${encodeURIComponent(queueId)}/${encodeURIComponent(action)}`, { method: "POST" });
        await loadStoryQueues();
        toast(action === "resume" ? "Queue resumed." : `Queue ${action === "pause" ? "paused" : "cancelled"}.`);
      } catch (error) {
        setError(dom.storyQueueError, error);
      }
    }, "Working…");
  }

  async function queueStories(button) {
    clearError(dom.clipsetError);
    const stories = state.clipset?.stories || [];
    if (!stories.length || !state.jobId) {
      setError(dom.clipsetError, new Error("Build a Clip Set before queueing stories."));
      return;
    }
    const items = stories.slice(0, 10).map((story) => ({
      job_id: state.jobId,
      set_id: state.clipset.id,
      story_id: story.id,
      aspect: storyAspect(story.id),
      title: story.title || story.id,
    }));
    await withBusy(button, async () => {
      try {
        await request("/api/story-queues", { method: "POST", body: JSON.stringify({ items }) });
        toast(`${items.length} stor${items.length === 1 ? "y" : "ies"} queued.`);
        setScreen("queue", state.jobId);
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Queueing…");
  }

  async function loadBatches() {
    if (state.batchLoading) return;
    state.batchLoading = true;
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
    } finally {
      state.batchLoading = false;
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
    const mode = dom.batchMode?.value || "analyze_render";
    const targets = $$('input[name="batch-target"]:checked', dom.batchForm)
      .map((input) => Number(input.value))
      .filter((value) => [15, 30, 60].includes(value))
      .sort((a, b) => a - b);
    if (mode === "analyze_render" && !targets.length) {
      setError(dom.batchError, new Error("Choose at least one render target, or switch to Analyze only."));
      return;
    }
    const items = lines.map((line) => (
      /^https?:\/\//i.test(line)
        ? { url: line, targets: mode === "analyze_render" ? targets : [] }
        : { path: line, targets: mode === "analyze_render" ? targets : [] }
    ));
    await withBusy(dom.batchCreate, async () => {
      try {
        const batch = await request("/api/batches", {
          method: "POST",
          body: JSON.stringify({
            name: dom.batchName.value.trim(),
            items,
            max,
          }),
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

  function syncBatchMode() {
    const analyzeOnly = (dom.batchMode?.value || "") === "analyze_only";
    if (dom.batchTargets) {
      dom.batchTargets.disabled = analyzeOnly;
      dom.batchTargets.classList.toggle("is-disabled", analyzeOnly);
      $$('input[name="batch-target"]', dom.batchTargets).forEach((input) => {
        input.disabled = analyzeOnly;
      });
    }
  }

  async function batchAction(action, batchId) {
    clearError(dom.batchError);
    if (action === "cancel") {
      state.confirm[`batch:${batchId}`] = "cancel";
      renderBatches();
      focusByKey(`batch:${batchId}:cancel-confirm`);
      return;
    }
    if (action === "cancel-abort") {
      delete state.confirm[`batch:${batchId}`];
      renderBatches();
      focusByKey(`batch:${batchId}:cancel`);
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
    if (!state.jobId || state.clipsetLoading) return;
    const requestJobId = state.jobId;
    state.clipsetLoading = true;
    try {
      const data = await request(`/api/jobs/${encodeURIComponent(requestJobId)}/clip-sets`);
      if (state.jobId !== requestJobId) return;
      const list = data.clip_sets || [];
      state.clipset = list.length ? list[0] : null;
      initClipsetEdits(state.clipset);
      renderClipSet();
      renderSelection();
      renderOriginalAnalysis();
      populateCommonSelects();
    } catch (error) {
      if (state.jobId !== requestJobId) return;
      state.clipset = null;
      renderClipSet();
      setError(dom.clipsetError, error);
      throw error;
    } finally {
      state.clipsetLoading = false;
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
    withFocusPreserved(renderClipSetInner);
  }

  function renderClipSetInner() {
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
      renderEmpty(dom.clipsetStories, "No Clip Set yet. Auto Select reads the analysis and builds stories.");
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
      ? `<div class="creator-card" style="margin-bottom:10px"><p class="hint">${warnings.map((item) => escapeHtml(redactPaths(item))).join("<br>")}</p></div>`
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
              <button class="ghost small" type="button" data-focus-key="sentence:${escapeHtml(story.id)}:${escapeHtml(id)}:up" data-sentence-action="up" ${!included || selectedIndex <= 0 ? "disabled" : ""} aria-label="Move sentence up">↑</button>
              <button class="ghost small" type="button" data-focus-key="sentence:${escapeHtml(story.id)}:${escapeHtml(id)}:down" data-sentence-action="down" ${!included || selectedIndex < 0 || selectedIndex >= ids.length - 1 ? "disabled" : ""} aria-label="Move sentence down">↓</button>
              <button class="ghost small" type="button" data-focus-key="sentence:${escapeHtml(story.id)}:${escapeHtml(id)}:toggle" data-sentence-action="${included ? "exclude" : "include"}">${included ? "Exclude" : "Include"}</button>
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
            <button type="button" data-focus-key="beat:${escapeHtml(story.id)}:${sceneId}:lock" data-beat-action="lock" data-scene-id="${sceneId}" data-story-id="${escapeHtml(story.id)}" title="Lock beat">${locked ? "unlock" : "lock"}</button>
            <button type="button" data-focus-key="beat:${escapeHtml(story.id)}:${sceneId}:ban" data-beat-action="ban" data-scene-id="${sceneId}" data-story-id="${escapeHtml(story.id)}" title="Ban beat">${banned ? "unban" : "ban"}</button>
          </span>`;
      }).join("");
      const overlap = overlapForStory(story);
      const evidence = (story.evidence || []).slice(0, 3).map((item) => `<li>${escapeHtml(item.text || "")}</li>`).join("");
      const renderState = state.renderJobs[story.id] || null;
      const busy = renderState && ["starting", "rendering", "polling"].includes(renderState.status);
      const artifact = artifactForStory(story.id);
      const ready = artifact && artifact.status === "ready";
      const renderLabel = busy
        ? (renderState.status === "starting" ? "Starting…" : `Rendering ${Number(renderState.progress || 0)}%`)
        : (ready ? "Render again" : "Render story");
      let statusHtml = "";
      if (renderState?.error) {
        statusHtml = `<p class="story-render bad">${escapeHtml(renderState.error)}</p>`;
      } else if (busy) {
        statusHtml = `<p class="story-render warn">Rendering story${renderState.artifactId ? ` · ${escapeHtml(renderState.artifactId)}` : ""}. Keep this panel open; artifacts refresh when ready.</p>`;
      } else if (ready) {
        statusHtml = `<p class="story-render ok">Ready artifact ${escapeHtml(artifact.title || artifact.artifact_id)} · ${escapeHtml(artifact.artifact_id)}. Packet and preflight use this artifact.</p>`;
      } else if (artifact) {
        statusHtml = `<p class="story-render warn">Artifact ${escapeHtml(artifact.artifact_id)} is ${escapeHtml(artifact.status || "pending")}. Wait for ready, then refresh artifacts.</p>`;
      }
      return `
        <article class="story-card" data-story-card="${escapeHtml(story.id)}">
          <header>
            <div>
              <h4>${escapeHtml(story.title || story.id)}</h4>
              <div class="creator-meta-row">
                <span class="creator-tag">${fmtDuration(story.dur)}</span>
                <span class="creator-tag">${fmtClock(story.start)} → ${fmtClock(story.end)}</span>
                <span class="creator-tag ${overlap > 0.2 ? "warn" : "ok"}">overlap ${overlap.toFixed(1)}s</span>
                ${ready ? '<span class="creator-tag ok">render ready</span>' : ""}
              </div>
            </div>
            <div class="creator-actions">
              <label class="creator-inline-field">Aspect
                <select data-story-aspect="${escapeHtml(story.id)}" aria-label="Render aspect for ${escapeHtml(story.title || story.id)}">
                  <option value="9:16" ${storyAspect(story.id) === "9:16" ? "selected" : ""}>9:16</option>
                  <option value="4:5" ${storyAspect(story.id) === "4:5" ? "selected" : ""}>4:5</option>
                </select>
              </label>
              <button class="primary small" type="button" data-focus-key="story-render:${escapeHtml(story.id)}" data-story-render="${escapeHtml(story.id)}" ${busy ? "disabled" : ""}>${escapeHtml(renderLabel)}</button>
              <button class="ghost small" type="button" data-focus-key="story-smartcut:${escapeHtml(story.id)}" data-story-smartcut="${escapeHtml(story.id)}">Open in Smart Cut</button>
              <button class="ghost small" type="button" data-focus-key="story-packet:${escapeHtml(story.id)}" data-story-packet="${escapeHtml(story.id)}">Build packet</button>
            </div>
          </header>
          ${statusHtml}
          <p class="story-copy"><strong>Hook</strong> ${escapeHtml((story.hook || {}).text || "—")}</p>
          <p class="story-copy"><strong>Payoff</strong> ${escapeHtml((story.payoff || {}).text || "—")}</p>
          ${evidence ? `<ul class="story-evidence">${evidence}</ul>` : ""}
          <div class="beat-list">${beats || '<span class="hint">No scene beats.</span>'}</div>
          <div class="sentence-list">${sentences || '<p class="hint">No sentences.</p>'}</div>
          <div class="creator-actions" style="margin-top:10px">
            <button class="ghost small" type="button" data-focus-key="clipset-save:${escapeHtml(story.id)}" data-clipset-save="1">Save edits</button>
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
        state.selectedArtifact = "";
        state.renderJobs = {};
        for (const input of [dom.packetTitle1, dom.packetTitle2, dom.packetTitle3, dom.packetDescription, dom.packetHashtags, dom.packetPinComment]) {
          if (input) input.value = "";
        }
        if (dom.packetArtifact) dom.packetArtifact.value = "";
        updateTitleCounts();
        updateDescriptionCount();
        renderPacket(null);
        initClipsetEdits(state.clipset);
        renderClipSet();
        renderSelection();
        renderOriginalAnalysis();
        renderMatrix();
        populateCommonSelects();
        setAnalysisOpen(false);
        const storyCount = state.clipset?.stories?.length || 0;
        if (!storyCount) {
          toast("Clip Set built, but no stories fit this source. Check the note above.");
        } else {
          toast("Clip Set built. Review the stories, then render one or open it in Smart Cut.");
        }
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Selecting…");
  }

  async function saveClipSetEdits() {
    clearError(dom.clipsetError);
    if (!state.clipset) {
      setError(dom.clipsetError, new Error("Build a Clip Set first."));
      return;
    }
    const excluded = new Set();
    const stories = (state.clipset.stories || []).map((story) => {
      const selected = (state.clipsetEdits[story.id] || []).map(Number);
      const selectedSet = new Set(selected);
      for (const sentence of (story.sentences || [])) {
        const id = Number(sentence.id);
        if (!selectedSet.has(id)) excluded.add(id);
      }
      return { id: story.id, sentences: selected };
    });
    try {
      const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets/${encodeURIComponent(state.clipset.id)}`, {
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

  function setAnalysisOpen(open) {
    if (!dom.clipsetAnalysis) return;
    dom.clipsetAnalysis.hidden = !open;
    dom.clipsetReadAnalysis?.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) renderOriginalAnalysis();
  }

  function setAnalysisTab(tab) {
    const chosen = tab === "beta" ? "beta" : "original";
    $$("[data-analysis-tab]", dom.analysisTabs).forEach((button) => {
      const active = button.dataset.analysisTab === chosen;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    if (dom.analysisOriginal) dom.analysisOriginal.hidden = chosen !== "original";
    if (dom.analysisBeta) dom.analysisBeta.hidden = chosen !== "beta";
    if (chosen === "original") renderOriginalAnalysis();
  }

  function renderOriginalAnalysis() {
    withFocusPreserved(renderOriginalAnalysisInner);
  }

  function renderOriginalAnalysisInner() {
    if (!dom.clipsetOriginalOutput) return;
    if (!state.job) {
      dom.clipsetOriginalOutput.innerHTML = '<p class="hint">Open a job to read its analysis.</p>';
      return;
    }
    if (!state.clipset) {
      dom.clipsetOriginalOutput.innerHTML = '<p class="hint">No Clip Set yet. Use Auto Select to build the original story read.</p>';
      return;
    }
    const stories = state.clipset.stories || [];
    if (!stories.length) {
      dom.clipsetOriginalOutput.innerHTML = '<p class="hint">The Clip Set has no stories to read.</p>';
      return;
    }
    dom.clipsetOriginalOutput.innerHTML = stories.map((story) => `
      <div class="batch-card">
        <header><div><h4>${escapeHtml(story.title || story.id)}</h4><div class="creator-meta-row">
          <span class="creator-tag">${fmtDuration(story.dur)}</span>
          <span class="creator-tag">${fmtClock(story.start)} → ${fmtClock(story.end)}</span>
        </div></div><button class="ghost small" type="button" data-focus-key="original-render:${escapeHtml(story.id)}" data-story-render="${escapeHtml(story.id)}">Render story</button></header>
        <p class="hint"><strong>Hook</strong> ${escapeHtml((story.hook || {}).text || "—")}</p>
        <p class="hint"><strong>Payoff</strong> ${escapeHtml((story.payoff || {}).text || "—")}</p>
      </div>`).join("");
  }

  async function runSelectionV2() {
    clearError(dom.clipsetError);
    if (!state.job || !state.clipset) {
      setError(dom.clipsetError, new Error("Build a Clip Set before the beta read."));
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
    }, "Reading…");
  }

  function renderSelection() {
    if (!dom.clipsetV2Output) return;
    const data = state.selection;
    if (!data) {
      dom.clipsetV2Output.innerHTML = '<p class="hint">No beta read yet. This optional pass ranks the current stories; the original read stays available.</p>';
      return;
    }
    const ranked = (data.ranked || []).map((story) => `
      <div class="batch-card">
        <header><div><h4>${escapeHtml(story.title || story.id)}</h4><div class="creator-meta-row"><span class="creator-tag ok">rank ${Number(story.v2_score || 0).toFixed(1)}</span><span class="creator-tag">${fmtDuration(story.dur)}</span></div></div></header>
        <p class="hint">${escapeHtml(story.why || "")}</p>
        ${(story.hook_candidates || []).length ? `<p class="hint">Hooks: ${(story.hook_candidates || []).map((hook) => escapeHtml(hook.text || "")).join(" · ")}</p>` : `<p class="hint">Incomplete hook set.</p>`}
      </div>`).join("");
    const excluded = (data.excluded || []).map((story) => `
      <div class="batch-card"><header><div><h4>${escapeHtml(story.title || story.id)}</h4><div class="creator-meta-row"><span class="creator-tag bad">excluded</span></div></div></header><p class="hint">${escapeHtml(story.why || "Prompt exclusion matched.")}</p></div>`).join("");
    const stale = (data.warnings || []).length
      ? `<p class="hint">${escapeHtml(data.warnings.join(" "))}</p>`
      : "";
    dom.clipsetV2Output.innerHTML = (ranked || '<p class="hint">No stories ranked.</p>') + excluded + stale + (
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
      <div class="matrix-cell error"><strong>${escapeHtml(item.story_title || item.story_id || "story")}</strong>${escapeHtml(redactPaths(item.error || "incomplete"))}</div>`).join("");
    dom.matrixOutput.innerHTML = (matrices || "") + (errors ? `<div class="matrix-grid">${errors}</div>` : "") + (
      !matrices && !errors ? '<p class="hint">No matrix built.</p>' : ""
    );
  }

  function setSelectedArtifact(artifactId) {
    state.selectedArtifact = artifactId || "";
    if (!artifactId) return;
    populateCommonSelects();
    if (dom.packetArtifact) dom.packetArtifact.value = artifactId;
    if (dom.preflightStory) dom.preflightStory.value = artifactId;
    updatePacketNeedsRender();
    updatePacketCovers();
  }

  function setRenderProgress(storyId, patch) {
    state.renderJobs[storyId] = {
      ...(state.renderJobs[storyId] || {}),
      ...patch,
    };
    renderClipSet();
    renderOriginalAnalysis();
    updatePacketNeedsRender();
  }

  function storyAspect(storyId) {
    return state.storyAspects[storyId] === "4:5" ? "4:5" : "9:16";
  }

  function storyRenderTarget(story) {
    const value = Math.round(Number(story?.dur) || 0);
    return Math.max(1, Math.min(180, value || 30));
  }

  function renderRecordStatus(record) {
    return String(record?.status || "").toLowerCase();
  }

  async function refreshArtifactsOnly() {
    if (!state.jobId) return;
    const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/artifacts`);
    state.artifacts = data.artifacts || [];
    state.artifactRenders = data.renders || state.artifactRenders || {};
    populateCommonSelects();
    renderArtifacts();
  }

  async function completeStoryRender(storyId, artifactId) {
    clearTimeout(state.renderPollers[storyId]);
    delete state.renderPollers[storyId];
    await refreshArtifactsOnly().catch(() => {});
    const artifact = artifactById(artifactId);
    if (artifact && artifact.status === "ready") {
      setRenderProgress(storyId, {
        status: "ready",
        progress: 100,
        artifactId: artifact.artifact_id,
        error: "",
      });
      setSelectedArtifact(artifact.artifact_id);
      if (dom.packetStory) dom.packetStory.value = storyId;
      toast("Story render ready. Packet and preflight now use its artifact.");
    } else {
      setRenderProgress(storyId, {
        status: "error",
        progress: 100,
        artifactId,
        error: "The render finished, but its artifact is not listed yet. Refresh artifacts.",
      });
    }
    renderClipSet();
    renderOriginalAnalysis();
    updatePacketNeedsRender();
    updatePacketCovers();
    if (state.screen === "preflight") maybeAutoPreflight(true);
  }

  function scheduleRenderPoll(storyId, artifactId, renderKey, target) {
    clearTimeout(state.renderPollers[storyId]);
    const started = Date.now();
    const pollJobId = state.jobId;
    const timeout = 20 * 60 * 1000;
    const tick = async () => {
      if (state.jobId !== pollJobId) {
        delete state.renderPollers[storyId];
        return;
      }
      if (Date.now() - started > timeout) {
        setRenderProgress(storyId, {
          status: "error",
          error: "Rendering is taking longer than expected. Refresh artifacts when it finishes.",
        });
        delete state.renderPollers[storyId];
        return;
      }
      if (state.renderInFlight) {
        state.renderPollers[storyId] = setTimeout(tick, 1200);
        return;
      }
      state.renderInFlight = true;
      try {
        const job = await request(`/api/jobs/${encodeURIComponent(state.jobId)}`);
        state.job = job;
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/artifacts`);
        state.artifacts = data.artifacts || [];
        state.artifactRenders = data.renders || {};
        if (state.jobId !== pollJobId) return;
        let artifact = artifactId ? artifactById(artifactId) : null;
        if (!artifact) artifact = artifactForStory(storyId);
        const records = state.artifactRenders || {};
        const record = (renderKey && records[renderKey])
          || Object.values(records).find((item) => item && artifactId && item.artifact_id === artifactId)
          || Object.values(records).find((item) => item && Number(item.target) === Number(target))
          || null;
        if (artifact?.status === "ready" || renderRecordStatus(record) === "ready") {
          state.renderInFlight = false;
          await completeStoryRender(storyId, artifact?.artifact_id || artifactId || record?.artifact_id || "");
          return;
        }
        if (["failed", "cancelled", "interrupted"].includes(renderRecordStatus(artifact || record))) {
          setRenderProgress(storyId, {
            status: "error",
            artifactId: artifact?.artifact_id || artifactId,
            error: "The story render failed. Try again, or open the story in Smart Cut and render from there.",
          });
          delete state.renderPollers[storyId];
          return;
        }
        const rawProgress = Number(record?.progress);
        const progress = Number.isFinite(rawProgress)
          ? Math.max(0, Math.min(100, Math.round(rawProgress * 100)))
          : 0;
        setRenderProgress(storyId, {
          status: "rendering",
          progress,
          artifactId: artifact?.artifact_id || artifactId,
        });
        renderArtifacts();
        populateCommonSelects();
        state.renderPollers[storyId] = setTimeout(tick, 2500);
      } catch (error) {
        setRenderProgress(storyId, {
          status: "rendering",
          error: "",
          progress: Number(state.renderJobs[storyId]?.progress || 0),
        });
        state.renderPollers[storyId] = setTimeout(tick, 3500);
      } finally {
        state.renderInFlight = false;
      }
    };
    state.renderPollers[storyId] = setTimeout(tick, 900);
  }

  async function renderStory(storyId, button) {
    clearError(dom.clipsetError);
    const story = storyById(storyId);
    if (!story || !state.clipset || !state.job) {
      setError(dom.clipsetError, new Error("Build a Clip Set before rendering a story."));
      return;
    }
    const target = storyRenderTarget(story);
    const requestJobId = state.jobId;
    const requestSetId = state.clipset.id;
    setRenderProgress(storyId, {
      status: "starting",
      progress: 0,
      artifactId: "",
      error: "",
      target,
    });
    await withBusy(button, async () => {
      try {
        const data = await request(`/api/jobs/${encodeURIComponent(requestJobId)}/clip-sets/${encodeURIComponent(requestSetId)}/stories/${encodeURIComponent(storyId)}/render`, {
          method: "POST",
          // Duration is the stored story duration and captions burn the
          // story's current caption track; the server owns both.
          body: JSON.stringify({
            quality: "final",
            aspect: storyAspect(storyId),
            captions: true,
          }),
        });
        if (state.jobId !== requestJobId) return;
        const render = data.render || {};
        const artifactId = data.artifact_id || data.artifact?.artifact_id || render.artifact_id || "";
        const renderKey = data.render_key || render.key || render.record_key || "";
        if (data.artifact?.status === "ready" || renderRecordStatus(render) === "ready") {
          await completeStoryRender(storyId, artifactId || data.artifact?.artifact_id || "");
          return;
        }
        setRenderProgress(storyId, {
          status: "rendering",
          progress: Math.max(0, Math.min(100, Number(render.progress || 0) * 100)),
          artifactId,
          renderKey,
        });
        scheduleRenderPoll(storyId, artifactId, renderKey, target);
        toast("Story render started. Progress updates in the card.");
      } catch (error) {
        const message = error.status === 404
          ? "Story rendering is not available in this build yet. Open the story in Smart Cut instead."
          : humanError(error);
        setRenderProgress(storyId, { status: "error", error: message });
        setError(dom.clipsetError, error);
      }
    }, "Starting…");
  }

  async function openStoryInSmartCut(storyId, button) {
    clearError(dom.clipsetError);
    const story = storyById(storyId);
    if (!story || !state.clipset || !state.job) {
      setError(dom.clipsetError, new Error("Build a Clip Set before opening a story in Smart Cut."));
      return;
    }
    const target = storyRenderTarget(story);
    await withBusy(button, async () => {
      try {
        const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets/${encodeURIComponent(state.clipset.id)}/plans`, {
          method: "POST",
          body: JSON.stringify({ target }),
        });
        const row = (data.plans || []).find((item) => item.story_id === storyId) || (data.plans || [])[0];
        const plan = row?.plan;
        if (!plan) throw new Error("This story has no plan to open.");
        const applied = br().applyPlan ? br().applyPlan(plan) : false;
        if (applied) {
          toast("Story loaded into Smart Cut.");
          closeCreator();
        } else {
          toast("Plan is ready. Smart Cut could not apply it automatically.");
        }
      } catch (error) {
        setError(dom.clipsetError, error);
      }
    }, "Opening…");
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
          const plans = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets/${encodeURIComponent(state.clipset.id)}/plans`, {
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

  function captionOverrides() {
    const zones = {
      bottom: { top: 0.08, right: 0.08, bottom: 0.16, left: 0.08 },
      center: { top: 0.36, right: 0.08, bottom: 0.36, left: 0.08 },
      top: { top: 0.12, right: 0.08, bottom: 0.4, left: 0.08 },
    };
    return {
      font_size: Number(dom.captionFontSize?.value) || 56,
      color: dom.captionColor?.value || "#ffffff",
      background: "#000000",
      background_opacity: Number(dom.captionBgOpacity?.value) || 0,
      safe_zone: zones[dom.captionPosition?.value] || zones.bottom,
      uppercase: Boolean(dom.captionUppercase?.checked),
    };
  }

  function updateCaptionControls() {
    const hasCues = (state.caption.cues || []).length > 0;
    if (dom.captionSave) dom.captionSave.disabled = !hasCues || Boolean(state.caption.artifactId);
    if (dom.captionExport) dom.captionExport.disabled = !hasCues && !state.caption.track && !state.caption.artifactId;
    if (dom.captionPreviewRun) dom.captionPreviewRun.disabled = !hasCues;
  }

  function showCaptionEmpty(message) {
    if (dom.captionPreviewEmpty) {
      dom.captionPreviewEmpty.innerHTML = `<strong>No caption preview yet</strong><span>${escapeHtml(message)}</span>`;
      dom.captionPreviewEmpty.hidden = false;
    }
    if (dom.captionPreviewText) dom.captionPreviewText.hidden = true;
    if (dom.captionPreviewImg) dom.captionPreviewImg.hidden = true;
    if (dom.captionPreviewSafe) dom.captionPreviewSafe.innerHTML = "";
  }

  function applyCaptionPreviewStyle() {
    const style = state.caption.preview?.style || {};
    const overrides = captionOverrides();
    if (!dom.captionPreviewText) return;
    dom.captionPreviewText.style.color = overrides.color || style.color || "#ffffff";
    dom.captionPreviewText.style.textTransform = overrides.uppercase ? "uppercase" : "none";
    const scale = (dom.captionPreview?.clientWidth || 360) / 1080;
    const size = Number(overrides.font_size || style.font_size || 56) * scale;
    dom.captionPreviewText.style.fontSize = `${Math.max(11, Math.min(30, size)).toFixed(1)}px`;
    const opacity = Number(overrides.background_opacity);
    dom.captionPreviewText.style.background = Number.isFinite(opacity)
      ? `rgba(0,0,0,${Math.max(0, Math.min(1, opacity))})`
      : "rgba(0,0,0,0.55)";
    const zone = overrides.safe_zone || style.safe_zone || { bottom: 0.16 };
    dom.captionPreviewText.style.bottom = `${Math.max(2, Number(zone.bottom || 0.16) * 100)}%`;
  }

  function renderCaptionCues() {
    if (!dom.captionCues) return;
    const cues = state.caption.cues || [];
    updateCaptionControls();
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

  async function planForCaptionTarget(target) {
    const bridgePlan = br().getPlan ? br().getPlan() : null;
    if (bridgePlan && Number(bridgePlan.target) === target && Array.isArray(bridgePlan.clips)) {
      return bridgePlan;
    }
    if (!state.clipset) return null;
    try {
      const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/clip-sets/${encodeURIComponent(state.clipset.id)}/plans`, {
        method: "POST",
        body: JSON.stringify({ target }),
      });
      const rows = data.plans || [];
      const story = (state.clipset.stories || []).find((item) => Math.round(Number(item.dur) || 0) === target);
      const row = (story && rows.find((item) => item.story_id === story.id)) || rows[0];
      return row?.plan || null;
    } catch (_) {
      return null;
    }
  }

  async function buildCaptionTrack() {
    clearError(dom.captionError);
    if (!state.job) {
      setError(dom.captionError, new Error("Open a job first."));
      return;
    }
    await withBusy(dom.captionBuild, async () => {
      try {
        const choice = String(dom.captionTarget.value || "");
        const body = {
          style_id: dom.captionStyle.value || "clean",
          order: "source",
          overrides: captionOverrides(),
        };
        if (choice.startsWith("story:") && state.clipset) {
          // A story track is built at the story's own length and becomes the
          // track its render, SRT and packet use.
          body.set_id = state.clipset.id;
          body.story_id = choice.slice("story:".length);
        } else {
          const target = Number(choice) || 30;
          const plan = await planForCaptionTarget(target);
          body.target = target;
          if (plan && Array.isArray(plan.clips)) {
            body.clips = plan.clips;
            body.hook_scene = plan.hook_scene;
          }
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
          body: JSON.stringify({ cues, style_id: dom.captionStyle.value || "clean", overrides: captionOverrides() }),
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
    if (!cues.length) {
      state.caption.preview = null;
      showCaptionEmpty("Build a caption track for this target, or load captions from a ready artifact. The poster appears automatically.");
      return;
    }
    if (state.caption.artifactId) {
      poster = artifactPosterPath(state.caption.artifactId);
    } else if (state.caption.track) {
      const preview = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/captions/${encodeURIComponent(state.caption.track.id)}/preview`);
      cues = preview.cues || cues;
      poster = preview.poster_url || "";
      safe = preview.safe_zones || safe;
      duration = Number(preview.duration) || duration;
    }
    state.caption.preview = { cues, safe_zones: safe, duration, style: state.caption.track?.style || {} };
    if (poster) {
      await setCaptionPreviewImage(poster).catch(() => {
        if (dom.captionPreviewImg) dom.captionPreviewImg.hidden = true;
      });
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
    dom.captionPreviewImg.onerror = () => { dom.captionPreviewImg.hidden = true; };
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
    if (!preview) {
      showCaptionEmpty("Build a caption track for this target, or load captions from a ready artifact. The poster appears automatically.");
      return;
    }
    const cues = preview.cues || [];
    const cue = cues.find((item) => Number(item.start) <= time && time <= Number(item.end))
      || cues.filter((item) => Number(item.start) <= time).slice(-1)[0]
      || cues[0];
    if (!cue) {
      showCaptionEmpty("This track has no cues near this time.");
      return;
    }
    if (dom.captionPreviewEmpty) dom.captionPreviewEmpty.hidden = true;
    if (dom.captionPreviewText) dom.captionPreviewText.hidden = false;
    dom.captionPreviewText.textContent = cue.text;
    applyCaptionPreviewStyle();
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

  function packetStoryThumb(story) {
    const scenes = state.job?.analysis?.scenes || [];
    for (const clip of story?.clips || []) {
      const scene = scenes.find((item) => Number(item.id) === Number(clip.scene));
      if (scene?.thumb_url) return scene.thumb_url;
    }
    return "";
  }

  function currentPacketArtifact() {
    const chosen = artifactById(dom.packetArtifact?.value || "");
    if (chosen) return chosen;
    const story = selectedPacketStory();
    return (story ? artifactForStory(story.id) : null) || artifactById(packetStoryValue());
  }

  function updatePacketNeedsRender() {
    if (!dom.packetNeedsRender) return;
    const story = selectedPacketStory();
    const artifact = currentPacketArtifact();
    const renderState = story ? state.renderJobs[story.id] : null;
    const busy = renderState && ["starting", "rendering", "polling"].includes(renderState.status);
    const ready = artifact && artifact.status === "ready";
    const legacy = dom.packetRenderKey?.value;
    const selected = packetStoryValue();
    const needs = Boolean(selected) && !ready && !legacy;
    dom.packetNeedsRender.hidden = !needs;
    if (!needs) return;
    const text = busy
      ? `Rendering story · ${Number(renderState.progress || 0)}%. Keep this panel open; packet fields unlock when the artifact is ready.`
      : (story
        ? "Render the story first. Packet, preflight and review links unlock when the artifact is ready."
        : "This artifact is still rendering. Wait for it to become ready, then refresh artifacts.");
    dom.packetNeedsRender.querySelector("p")?.replaceChildren(document.createTextNode(text));
    if (dom.packetRenderStory) {
      dom.packetRenderStory.hidden = !story;
      dom.packetRenderStory.disabled = Boolean(busy);
      dom.packetRenderStory.textContent = busy ? `Rendering ${Number(renderState.progress || 0)}%` : "Render story";
    }
  }

  function updatePacketCovers() {
    const artifact = currentPacketArtifact();
    const story = selectedPacketStory();
    const poster = artifact?.poster_url || "";
    const thumb = packetStoryThumb(story);
    const sources = [poster || thumb, thumb || poster];
    [dom.packetCoverImg1, dom.packetCoverImg2].forEach((img, index) => {
      if (!img) return;
      const src = sources[index];
      if (!src) {
        img.hidden = true;
        img.removeAttribute("src");
        return;
      }
      img.hidden = false;
      img.onerror = () => { img.hidden = true; };
      img.src = absoluteUrl(src);
    });
  }

  function updatePacketFilename() {
    if (!dom.packetFilename) return;
    const story = packetStoryId() || "story";
    const render = dom.packetRenderKey.value || "";
    const artifact = artifactById(dom.packetArtifact.value) || (!render ? currentPacketArtifact() : null);
    const selectedStory = selectedPacketStory();
    const target = artifact?.target
      || (render && state.job?.renders?.[render]?.target)
      || Math.round(Number(selectedStory?.dur) || 0)
      || 30;
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
    let artifactId = dom.packetArtifact.value;
    if (!artifactId && !dom.packetRenderKey.value) {
      const inferred = currentPacketArtifact();
      if (inferred) {
        artifactId = inferred.artifact_id;
        dom.packetArtifact.value = artifactId;
      }
    }
    const renderKey = dom.packetRenderKey.value;
    const story = packetStoryId() || artifactId || renderKey;
    const coverTimes = [Number(dom.packetCover1.value), Number(dom.packetCover2.value)];
    if (!coverTimes.every((value) => Number.isFinite(value) && value >= 0)) {
      setError(dom.packetError, new Error("Both cover times must be non-negative numbers."));
      return;
    }
    if (!story) {
      setError(dom.packetError, new Error("Choose a story first."));
      updatePacketNeedsRender();
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
      updatePacketNeedsRender();
      setError(dom.packetError, new Error("This story has no ready artifact. Use Render story above, or a legacy render key under Advanced."));
      return;
    }
    const artifact = artifactById(artifactId);
    if (artifact && artifact.status !== "ready") {
      setError(dom.packetError, new Error(`Artifact ${artifactId} is ${artifact.status || "pending"}. Wait for ready, then refresh artifacts.`));
      return;
    }
    if (!hashtags.length) {
      setError(dom.packetError, new Error("Add 3 to 8 hashtags."));
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
          pin_comment: (dom.packetPinComment?.value || "").trim(),
        };
        const packet = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/packets`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        state.packet = packet;
        renderPacket(packet);
        await loadPacketHistory().catch(() => {});
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

  async function loadPacketHistory() {
    if (!state.jobId) return;
    const data = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/packets`);
    state.packets = data.packets || [];
    renderPacketHistory();
  }

  function renderPacketHistory() {
    if (!dom.packetHistory) return;
    if (!state.packets.length) {
      dom.packetHistory.innerHTML = '<p class="hint">No packets yet. Packets stay here after you close the app.</p>';
      return;
    }
    dom.packetHistory.innerHTML = state.packets.map((row) => {
      const when = row.created ? new Date(Number(row.created) * 1000).toLocaleString() : "";
      const versions = (row.versions || []).filter(Boolean).map((value) => `v${value}`).join(", ");
      return `
        <div class="creator-item-row"><div><strong>${escapeHtml(row.title || row.packet_id)}</strong><div class="creator-meta-row">
          <span class="creator-tag">${escapeHtml(row.story_id || "")}</span>
          <span class="creator-tag">${escapeHtml((row.aspects || []).join(" · "))}</span>
          ${versions ? `<span class="creator-tag">${escapeHtml(versions)}</span>` : ""}
          <span class="creator-tag">${escapeHtml(when)}</span>
        </div></div>
        <button class="ghost small" type="button" data-packet-history-zip="${escapeHtml(row.packet_id)}" aria-label="Download packet ${escapeHtml(row.title || row.packet_id)}">Download ZIP</button></div>`;
    }).join("");
  }

  async function downloadPacketZip(packetId) {
    const packet = state.packet;
    if (!packet || packet.packet_id !== packetId) {
      const row = state.packets.find((item) => item.packet_id === packetId);
      if (!row) {
        setError(dom.packetError, new Error("Packet not found. Refresh the packet history."));
        return;
      }
      try {
        await downloadPath(row.zip_url, row.zip_file || `${packetId}.zip`);
      } catch (error) {
        setError(dom.packetError, error);
      }
      return;
    }
    try {
      await downloadPath(packet.zip_url || `/api/jobs/${encodeURIComponent(state.jobId)}/packets/${encodeURIComponent(packetId)}/zip`, packet.zip_file || `${packetId}.zip`);
    } catch (error) {
      setError(dom.packetError, error);
    }
  }

  // ---------------------------------------------------------------- preflight

  const PREFLIGHT_CHECKS = [
    { id: "dangling_claims", label: "Dangling claims", style: "copy" },
    { id: "truncated_payoff", label: "Truncated payoff", style: "edit" },
    { id: "caption_density", label: "Caption density", style: "captions" },
    { id: "safe_zone_contrast", label: "Safe-zone contrast", style: "frame" },
    { id: "loudness", label: "Loudness", style: "audio" },
  ];

  const PREFLIGHT_FIX = {
    caption_density: "captions",
    safe_zone_contrast: "captions",
    dangling_claims: "clipset",
    truncated_payoff: "clipset",
  };

  function renderPreflightPlaceholder() {
    if (!dom.preflightChecks) return;
    dom.preflightChecks.innerHTML = PREFLIGHT_CHECKS.map((check) => `
      <div class="check-row is-off" data-check-id="${escapeHtml(check.id)}">
        <input type="checkbox" disabled aria-label="${escapeHtml(check.label)}">
        <div>
          <h4>${escapeHtml(check.label)} <span class="creator-tag">not run</span></h4>
          <p>${escapeHtml(check.style)} check · selected story or artifact</p>
        </div>
        <span class="creator-tag">pending</span>
      </div>`).join("");
    dom.preflightFindings.innerHTML = '<p class="hint">Findings appear after preflight runs.</p>';
    setText(dom.preflightSummary, "Not run");
  }

  function maybeAutoPreflight(force = false) {
    if (state.screen !== "preflight" || !state.job) return;
    const story = dom.preflightStory?.value || "";
    if (!story) {
      renderPreflightPlaceholder();
      return;
    }
    if (!force && state.preflight && state.preflightSelection === story) return;
    runPreflight(true, story);
  }

  async function runPreflight(auto = false, preset = "") {
    if (state.preflightLoading) return;
    clearError(dom.preflightError);
    if (!state.job) {
      setError(dom.preflightError, new Error("Open a job first."));
      return;
    }
    const story = preset || dom.preflightStory.value;
    if (!story) {
      setError(dom.preflightError, new Error("Choose a story or artifact."));
      return;
    }
    state.preflightLoading = true;
    if (!auto) setBusy(dom.preflightRun, true, "Checking…");
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(state.jobId)}/preflight?story_id=${encodeURIComponent(story)}`);
      state.preflight = result;
      state.preflightSelection = story;
      state.preflightHidden = new Set();
      renderPreflight();
    } catch (error) {
      setError(dom.preflightError, error);
    } finally {
      state.preflightLoading = false;
      if (!auto) setBusy(dom.preflightRun, false);
      if (state.screen === "preflight" && dom.preflightStory?.value && dom.preflightStory.value !== state.preflightSelection) {
        setTimeout(() => maybeAutoPreflight(true), 0);
      }
    }
  }

  function renderPreflight() {
    withFocusPreserved(renderPreflightInner);
  }

  function renderPreflightInner() {
    const data = state.preflight;
    if (!data) {
      renderPreflightPlaceholder();
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
          <input type="checkbox" ${visible ? "checked" : ""} ${enabled ? "" : "disabled"} data-focus-key="preflight-toggle:${escapeHtml(id)}" data-preflight-toggle="${escapeHtml(id)}" aria-label="View ${escapeHtml(check.label || id)}">
          <div>
            <h4>${escapeHtml(check.label || id)} <span class="creator-tag ${check.severity === "block" ? "bad" : check.severity === "warn" ? "warn" : "ok"}">${escapeHtml(check.severity || "warn")}</span></h4>
            <p>${escapeHtml(check.style || "style")} · ${escapeHtml(check.status || "pass")}${check.reason ? ` · ${escapeHtml(redactPaths(check.reason))}` : ""}</p>
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
    dom.preflightFindings.innerHTML = visible.length ? visible.map((finding) => {
      const fix = PREFLIGHT_FIX[finding.id];
      const fixLabel = fix === "captions" ? "Fix in Captions" : "Fix in Clip Set";
      return `
        <div class="finding-card ${escapeHtml(finding.severity === "block" ? "block" : finding.severity === "warn" ? "warn" : "info")}">
          <header><div><h4>${escapeHtml(finding.toggle || finding.id)}</h4><div class="creator-meta-row"><span class="creator-tag ${finding.severity === "block" ? "bad" : finding.severity === "warn" ? "warn" : "ok"}">${escapeHtml(finding.severity)}</span></div></div></header>
          <p>${escapeHtml(redactPaths(finding.message || ""))}</p>
          <p class="finding-suggestion">${escapeHtml(redactPaths(finding.suggestion || ""))}</p>
          ${fix ? `<div class="finding-actions"><button class="ghost small" type="button" data-preflight-fix="${fix}">${fixLabel}</button></div>` : ""}
        </div>`;
    }).join("") : '<div class="creator-empty-state"><p>No visible findings. Toggles here only change this view; server settings remain authoritative.</p></div>';
  }

  // ---------------------------------------------------------------- artifacts + shares

  async function loadArtifacts() {
    if (!state.jobId) {
      state.artifacts = [];
      return;
    }
    if (state.artifactLoading) return;
    const requestJobId = state.jobId;
    state.artifactLoading = true;
    try {
      const data = await request(`/api/jobs/${encodeURIComponent(requestJobId)}/artifacts`);
      if (state.jobId !== requestJobId) return;
      state.artifacts = data.artifacts || [];
      state.artifactRenders = data.renders || state.artifactRenders || {};
      populateCommonSelects();
      renderArtifacts();
    } finally {
      state.artifactLoading = false;
    }
  }

  async function loadShares() {
    if (!state.jobId) {
      state.shares = [];
      return;
    }
    const requestJobId = state.jobId;
    // Tokens are capabilities. List records without them and copy only a token
    // returned by the create call in this session.
    const data = await request(`/api/shares?job_id=${encodeURIComponent(requestJobId)}`);
    if (state.jobId !== requestJobId) return;
    state.shares = data.shares || [];
    renderShares();
  }

  function artifactMediaUrl(artifactId, name) {
    return `/api/jobs/${encodeURIComponent(state.jobId)}/artifacts/${encodeURIComponent(artifactId)}/media/${name}`;
  }

  function renderArtifacts() {
    withFocusPreserved(renderArtifactsInner);
  }

  function renderArtifactsInner() {
    if (!dom.artifactList) return;
    const legacy = readyLegacyRenders();
    const count = state.artifacts.length || legacy.length;
    if (!count) setText(dom.artifactCount, "0 artifacts");
    else setText(dom.artifactCount, `${count} ${state.artifacts.length ? "artifact" : "ready render"}${count === 1 ? "" : "s"}`);
    if (!state.artifacts.length) {
      if (legacy.length) {
        dom.artifactList.innerHTML = legacy.map(({ key, record }) => `
          <article class="artifact-card is-ready" data-artifact-id="${escapeHtml(key)}">
            <header>
              <div><h4>${escapeHtml(key)}</h4><div class="creator-meta-row">
                <span class="creator-tag ok">ready</span>
                <span class="creator-tag">legacy render</span>
                <span class="creator-tag">${record.target || "?"}s · ${escapeHtml(record.aspect || "9:16")}</span>
              </div></div>
            </header>
            <p class="hint">This render is ready. Refresh artifacts to adopt it as an artifact, or use its render key under Packet → Advanced.</p>
          </article>`).join("");
        return;
      }
      renderEmpty(dom.artifactList, "No artifacts yet. Render a story from Clip Set to create one.");
      return;
    }
    dom.artifactList.innerHTML = state.artifacts.map((artifact) => {
      const id = artifact.artifact_id;
      const ready = artifact.status === "ready" || Boolean(artifact.completed);
      const share = state.shares.find((row) => row.artifact_id === id && row.status !== "revoked");
      const freshIndex = state.freshShares.findIndex((row) => row.artifact_id === id && !row.revoked);
      const fresh = freshIndex >= 0 ? state.freshShares[freshIndex] : null;
      return `
        <article class="artifact-card ${ready ? "is-ready" : ""}" data-artifact-id="${escapeHtml(id)}">
          <header>
            <div><h4>${escapeHtml(artifact.title || id)}</h4><div class="creator-meta-row">
              <span class="creator-tag ${ready ? "ok" : "bad"}">${escapeHtml(ready ? "ready" : (artifact.status || "unknown"))}</span>
              <span class="creator-tag">${escapeHtml(id)}</span>
              ${artifact.pinned ? '<span class="creator-tag ok">pinned</span>' : ""}
              <span class="creator-tag">${artifact.target || "?"}s · ${escapeHtml(artifact.aspect || "9:16")}</span>
              ${artifact.versions?.label ? `<span class="creator-tag ${artifact.versions.current ? "ok" : "warn"}">${escapeHtml(artifact.versions.label)}</span>` : ""}
              ${share ? '<span class="creator-tag ok">review link</span>' : ""}
            </div></div>
            <button class="ghost small" type="button" data-focus-key="artifact-pin:${escapeHtml(id)}" data-artifact-pin="${escapeHtml(id)}" data-pinned="${artifact.pinned ? "1" : "0"}">${artifact.pinned ? "Unpin" : "Pin"}</button>
          </header>
          <p class="hint">${escapeHtml(artifact.record_key || "")} · ${escapeHtml(artifact.resolved_encoder || "")} · ${artifact.cue_count ? `${artifact.cue_count} cues` : "no caption track"}</p>
          <div class="artifact-links">
            ${ready ? `<button class="ghost small" type="button" data-focus-key="artifact-srt:${escapeHtml(id)}" data-artifact-download="${escapeHtml(id)}" data-kind="captions.srt">SRT</button>
            <button class="ghost small" type="button" data-focus-key="artifact-vtt:${escapeHtml(id)}" data-artifact-download="${escapeHtml(id)}" data-kind="captions.vtt">VTT</button>
            <button class="ghost small" type="button" data-focus-key="artifact-captions:${escapeHtml(id)}" data-artifact-caption-preview="${escapeHtml(id)}">Caption preview</button>` : ""}
            ${fresh ? `<button class="ghost small" type="button" data-focus-key="artifact-fresh:${escapeHtml(id)}" data-fresh-copy="${freshIndex}">Copy new review link</button>` : ""}
          </div>
          <div class="share-form">
            <input type="text" maxlength="120" placeholder="Review label" data-share-label="${escapeHtml(id)}" aria-label="Review label">
            <input type="number" min="0" step="1" value="7" aria-label="Expiry days" data-share-days="${escapeHtml(id)}">
            <button class="primary small" type="button" data-focus-key="share-create:${escapeHtml(id)}" data-share-create="${escapeHtml(id)}">Create review link</button>
          </div>
        </article>`;
    }).join("");
  }

  function renderShares() {
    withFocusPreserved(renderSharesInner);
  }

  function renderSharesInner() {
    if (!dom.shareList) return;
    if (!state.shares.length) {
      renderEmpty(dom.shareList, "No review links for this job. Create one from an artifact.");
      return;
    }
    dom.shareList.innerHTML = state.shares.map((share, index) => {
      const status = share.status || (share.revoked_at ? "revoked" : "active");
      const expiry = share.expires_at ? new Date(Number(share.expires_at) * 1000).toLocaleString() : "never";
      const fresh = state.freshShares.find((row) => row.artifact_id === share.artifact_id && (row.label || "") === (share.label || "") && !row.revoked);
      const freshIndex = fresh ? state.freshShares.indexOf(fresh) : -1;
      const confirming = freshIndex >= 0 && state.confirm[`fresh:${freshIndex}`] === "revoke";
      return `
        <article class="share-card" data-share-index="${index}">
          <header><div><h4>${escapeHtml(share.label || "review link")}</h4><div class="creator-meta-row">
            <span class="creator-tag ${status === "active" ? "ok" : status === "expired" ? "warn" : "bad"}">${escapeHtml(status)}</span>
            ${share.artifact_id ? `<span class="creator-tag">${escapeHtml(share.artifact_id)}</span>` : ""}
            <span class="creator-tag">expires ${escapeHtml(expiry)}</span>
          </div></div></header>
          <div class="creator-actions">
            ${freshIndex >= 0 ? `<button class="ghost small" type="button" data-focus-key="fresh-copy:${freshIndex}" data-fresh-copy="${freshIndex}">Copy new link</button>` : ""}
            ${freshIndex >= 0 && status !== "revoked" ? (
              confirming
                ? `<span class="creator-inline-confirm">Revoke link? <button class="ghost small danger" type="button" data-focus-key="fresh-revoke-confirm:${freshIndex}" data-fresh-revoke-confirm="${freshIndex}">Confirm revoke</button><button class="ghost small" type="button" data-focus-key="fresh-revoke-abort:${freshIndex}" data-fresh-revoke-abort="${freshIndex}">Keep</button></span>`
                : `<button class="ghost small" type="button" data-focus-key="fresh-revoke:${freshIndex}" data-fresh-revoke="${freshIndex}">Revoke</button>`
            ) : ""}
            ${freshIndex < 0 ? '<span class="hint">Token is only available when the link is created.</span>' : ""}
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
        if (share.token) {
          state.freshShares.unshift({
            token: share.token,
            url: share.url || `/r/${share.token}`,
            artifact_id: artifactId,
            label,
          });
          // Tokens are returned at creation and by the loopback job-scoped
          // re-copy endpoint only; listings always redact them.
          await copyText(absoluteUrl(share.url || `/r/${share.token}`));
        }
        await loadShares();
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

  async function revokeFreshShare(index) {
    clearError(dom.artifactError);
    const fresh = state.freshShares[index];
    if (!fresh?.token) {
      setError(dom.artifactError, new Error("That review link token is no longer available in this session."));
      return;
    }
    try {
      await request(`/api/shares/${encodeURIComponent(fresh.token)}`, {
        method: "PATCH",
        body: JSON.stringify({ revoked: true }),
      });
      delete state.confirm[`fresh:${index}`];
      state.freshShares.splice(index, 1);
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
    dom.recent?.addEventListener("change", () => {
      const jobId = dom.recent.value;
      if (!jobId) return;
      state.jobId = jobId;
      loadJob(jobId)
        .then(() => {
          setScreen("clipset", jobId);
          writeHash(jobId, "clipset");
        })
        .catch((error) => setError(dom.globalError, error));
    });
    dom.jobLoad?.addEventListener("click", () => {
      const jobId = dom.jobInput.value.trim();
      if (!jobId) {
        setError(dom.globalError, new Error("Enter a job id."));
        return;
      }
      state.jobId = jobId;
      loadJob(jobId).then(() => setScreen(state.screen, jobId)).catch((error) => setError(dom.globalError, error));
    });
    dom.jobInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") dom.jobLoad?.click();
    });
    dom.tabs?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-creator-tab]");
      if (button) setScreen(button.dataset.creatorTab);
    });
    dom.tabs?.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const buttons = $$('[role="tab"]', dom.tabs);
      const current = buttons.indexOf(document.activeElement);
      if (current < 0) return;
      event.preventDefault();
      let next = current;
      if (event.key === "ArrowLeft") next = (current - 1 + buttons.length) % buttons.length;
      if (event.key === "ArrowRight") next = (current + 1) % buttons.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = buttons.length - 1;
      buttons[next].focus();
      setScreen(buttons[next].dataset.creatorTab);
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
        Object.values(state.renderPollers).forEach((timer) => clearTimeout(timer));
        state.renderPollers = {};
      }
    });

    dom.batchForm?.addEventListener("submit", createBatch);
    dom.batchMode?.addEventListener("change", syncBatchMode);
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
    dom.clipsetQueue?.addEventListener("click", () => queueStories(dom.clipsetQueue));
    dom.storyQueueRefresh?.addEventListener("click", () => loadStoryQueues().catch((error) => setError(dom.storyQueueError, error)));
    for (const host of [dom.storyQueueList, dom.storyQueueBanner]) {
      host?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-story-queue-action]");
        if (button) storyQueueAction(button.dataset.storyQueueAction, button.dataset.queueId, button);
      });
    }
    dom.clipsetReadAnalysis?.addEventListener("click", () => {
      const open = Boolean(dom.clipsetAnalysis?.hidden);
      setAnalysisOpen(open);
      if (open) dom.analysisTabs?.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    });
    dom.analysisTabs?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-analysis-tab]");
      if (button) setAnalysisTab(button.dataset.analysisTab);
    });
    dom.analysisTabs?.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const buttons = $$('[role="tab"]', dom.analysisTabs);
      const current = buttons.indexOf(document.activeElement);
      if (current < 0) return;
      event.preventDefault();
      let next = current;
      if (event.key === "ArrowLeft") next = (current - 1 + buttons.length) % buttons.length;
      if (event.key === "ArrowRight") next = (current + 1) % buttons.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = buttons.length - 1;
      buttons[next].focus();
      setAnalysisTab(buttons[next].dataset.analysisTab);
    });
    dom.clipsetV2?.addEventListener("click", runSelectionV2);
    dom.matrixBuild?.addEventListener("click", () => runMatrix(""));
    dom.tightenRun?.addEventListener("click", runTighten);
    const clipsetClick = (event) => {
      const packet = event.target.closest("[data-story-packet]");
      if (packet) {
        const storyId = packet.dataset.storyPacket;
        dom.packetStory.value = storyId;
        const artifact = artifactForStory(storyId);
        dom.packetArtifact.value = artifact ? artifact.artifact_id : "";
        dom.packetRenderKey.value = "";
        fillPacketCopy({ onlyBlank: true });
        updatePacketNeedsRender();
        updatePacketFilename();
        updatePacketCovers();
        setScreen("packet");
        return;
      }
      const render = event.target.closest("[data-story-render]");
      if (render) {
        const picker = document.querySelector(`[data-story-aspect="${CSS.escape(render.dataset.storyRender)}"]`);
        if (picker) state.storyAspects[render.dataset.storyRender] = picker.value;
        renderStory(render.dataset.storyRender, render);
        return;
      }
      const smartcut = event.target.closest("[data-story-smartcut]");
      if (smartcut) {
        openStoryInSmartCut(smartcut.dataset.storySmartcut, smartcut);
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
    };
    dom.clipsetStories?.addEventListener("click", clipsetClick);
    dom.clipsetStories?.addEventListener("change", (event) => {
      const picker = event.target.closest("[data-story-aspect]");
      if (picker) state.storyAspects[picker.dataset.storyAspect] = picker.value === "4:5" ? "4:5" : "9:16";
    });
    dom.clipsetOriginalOutput?.addEventListener("click", clipsetClick);
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
    const brandPreview = () => {
      if (state.caption.preview) updateCaptionPreviewText(Number(dom.captionPreviewTime?.value || 0));
    };
    dom.captionFontSize?.addEventListener("input", brandPreview);
    dom.captionColor?.addEventListener("input", brandPreview);
    dom.captionBgOpacity?.addEventListener("input", brandPreview);
    dom.captionPosition?.addEventListener("change", brandPreview);
    dom.captionUppercase?.addEventListener("change", brandPreview);
    dom.captionArtifact?.addEventListener("change", () => {
      if (dom.captionArtifact.value) {
        loadArtifactCaptions();
      } else {
        state.caption.artifactId = "";
        state.caption.track = null;
        state.caption.cues = [];
        state.caption.preview = null;
        renderCaptionCues();
        showCaptionEmpty("Build a caption track for this target, or load captions from a ready artifact. The poster appears automatically.");
      }
    });

    dom.packetForm?.addEventListener("submit", buildPacket);
    dom.packetDescription?.addEventListener("input", updateDescriptionCount);
    for (const input of [dom.packetTitle1, dom.packetTitle2, dom.packetTitle3]) {
      input?.addEventListener("input", updateTitleCounts);
    }
    dom.packetSuggest?.addEventListener("click", () => {
      if (!selectedPacketStory()) {
        setError(dom.packetError, new Error("Choose a story first."));
        return;
      }
      const fields = [dom.packetTitle1, dom.packetTitle2, dom.packetTitle3, dom.packetDescription, dom.packetHashtags, dom.packetPinComment];
      const blank = fields.some((input) => input && !input.value.trim());
      if (!blank) {
        toast("All packet fields already have copy.");
        return;
      }
      fillPacketCopy();
      toast("Blank packet fields filled from the selected story.");
    });
    dom.packetRenderStory?.addEventListener("click", () => {
      const story = selectedPacketStory();
      if (!story) {
        setError(dom.packetError, new Error("Choose a story first."));
        return;
      }
      renderStory(story.id, dom.packetRenderStory);
    });
    dom.packetStory?.addEventListener("change", () => {
      const artifact = artifactForPacketSelection(packetStoryValue());
      dom.packetArtifact.value = artifact ? artifact.artifact_id : "";
      if (artifact) dom.packetRenderKey.value = "";
      fillPacketCopy({ onlyBlank: true });
      updatePacketNeedsRender();
      updatePacketFilename();
      updatePacketCovers();
    });
    dom.packetArtifact?.addEventListener("change", () => {
      if (dom.packetArtifact.value) dom.packetRenderKey.value = "";
      updatePacketNeedsRender();
      updatePacketFilename();
      updatePacketCovers();
    });
    dom.packetRenderKey?.addEventListener("change", () => {
      if (dom.packetRenderKey.value) dom.packetArtifact.value = "";
      updatePacketNeedsRender();
      updatePacketFilename();
    });
    dom.packetForm?.addEventListener("click", (event) => {
      const copy = event.target.closest("[data-copy-field]");
      if (!copy) return;
      const kind = copy.dataset.copyField;
      let value = "";
      if (kind === "titles") {
        value = [dom.packetTitle1.value, dom.packetTitle2.value, dom.packetTitle3.value]
          .map((item) => item.trim()).filter(Boolean).join("\n");
      } else if (kind === "description") {
        value = dom.packetDescription.value.trim();
      } else if (kind === "hashtags") {
        value = dom.packetHashtags.value.trim();
      } else if (kind === "pin") {
        value = dom.packetPinComment.value.trim();
      }
      if (!value) {
        setError(dom.packetError, new Error("That field is empty."));
        return;
      }
      copyText(value);
    });
    dom.packetResult?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-packet-zip]");
      if (button) downloadPacketZip(button.dataset.packetZip);
    });
    dom.packetHistory?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-packet-history-zip]");
      if (button) downloadPacketZip(button.dataset.packetHistoryZip);
    });

    dom.preflightRun?.addEventListener("click", () => runPreflight(false));
    dom.preflightStory?.addEventListener("change", () => maybeAutoPreflight(true));
    dom.preflightChecks?.addEventListener("change", (event) => {
      const toggle = event.target.closest("[data-preflight-toggle]");
      if (!toggle) return;
      if (toggle.checked) state.preflightHidden.delete(toggle.dataset.preflightToggle);
      else state.preflightHidden.add(toggle.dataset.preflightToggle);
      renderPreflight();
    });
    dom.preflightFindings?.addEventListener("click", (event) => {
      const fix = event.target.closest("[data-preflight-fix]");
      if (!fix) return;
      if (fix.dataset.preflightFix === "clipset") {
        setScreen("clipset");
        return;
      }
      const candidate = state.preflight?.story_id || dom.preflightStory.value;
      const artifact = artifactById(candidate);
      if (artifact) dom.captionArtifact.value = artifact.artifact_id;
      setScreen("captions");
      if (artifact && artifact.status === "ready") {
        loadArtifactCaptions().catch((error) => setError(dom.captionError, error));
      }
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
      const fresh = event.target.closest("[data-fresh-copy]");
      if (fresh) {
        const item = state.freshShares[Number(fresh.dataset.freshCopy)];
        if (item) copyText(absoluteUrl(item.url));
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
      const copy = event.target.closest("[data-fresh-copy]");
      if (copy) {
        const item = state.freshShares[Number(copy.dataset.freshCopy)];
        if (item) copyText(absoluteUrl(item.url));
        return;
      }
      const revoke = event.target.closest("[data-fresh-revoke]");
      if (revoke) {
        state.confirm[`fresh:${revoke.dataset.freshRevoke}`] = "revoke";
        renderShares();
        focusByKey(`fresh-revoke-confirm:${revoke.dataset.freshRevoke}`);
        return;
      }
      const abort = event.target.closest("[data-fresh-revoke-abort]");
      if (abort) {
        delete state.confirm[`fresh:${abort.dataset.freshRevokeAbort}`];
        renderShares();
        focusByKey(`fresh-revoke:${abort.dataset.freshRevokeAbort}`);
        return;
      }
      const confirm = event.target.closest("[data-fresh-revoke-confirm]");
      if (confirm) revokeFreshShare(Number(confirm.dataset.freshRevokeConfirm));
    });
  }

  // ---------------------------------------------------------------- boot

  function init() {
    bind();
    updateDescriptionCount();
    updateTitleCounts();
    syncBatchMode();
    renderPreflightPlaceholder();
    renderCaptionCues();
    showCaptionEmpty("Build a caption track for this target, or load captions from a ready artifact. The poster appears automatically.");
    const params = parseHash();
    if (params.screen) {
      openCreator(params.screen, params.job || "");
    } else if (document.body.classList.contains("creator-mode")) {
      openCreator(undefined, params.job || "");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
