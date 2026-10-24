(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const dom = {
    ingest: $("#ingest-view"),
    progress: $("#progress-view"),
    result: $("#result-view"),
    brand: $("#brand"),
    health: $("#health"),
    footerHealth: $("#footer-health"),
    setup: $("#setup"),
    setupOpen: $("#setup-open"),
    setupClose: $("#setup-close"),
    setupSave: $("#setup-save"),
    setupStatus: $("#setup-status"),
    setupOpencodeEnabled: $("#setup-opencode-enabled"),
    setupOpencodeStatus: $("#setup-opencode-status"),
    setupOpencodeKey: $("#setup-opencode-key"),
    setupOpenrouterKey: $("#setup-openrouter-key"),
    setupOpencodeModel: $("#setup-opencode-model"),
    setupOpencodeVariant: $("#setup-opencode-variant"),
    setupUseRewrite: $("#setup-use-rewrite"),
    setupUseBrief: $("#setup-use-brief"),
    setupTranslationMode: $("#setup-translation-mode"),
    setupSttProvider: $("#setup-stt-provider"),
    setupSttLanguage: $("#setup-stt-language"),
    setupSttModel: $("#setup-stt-model"),
    setupTtsProvider: $("#setup-tts-provider"),
    setupMinimaxKey: $("#setup-minimax-key"),
    setupTestOpencode: $("#setup-test-opencode"),
    setupTestOpenrouter: $("#setup-test-openrouter"),
    setupTestStt: $("#setup-test-stt"),
    setupTestSttLive: $("#setup-test-stt-live"),
    setupTestTts: $("#setup-test-tts"),
    setupTestTtsLive: $("#setup-test-tts-live"),
    setupTtsAudio: $("#setup-tts-audio"),
    dropzone: $("#dropzone"),
    fileInput: $("#file-input"),
    fileCard: $("#file-card"),
    fileName: $("#file-name"),
    fileInfo: $("#file-info"),
    clearFile: $("#clear-file"),
    pathInput: $("#path-input"),
    pathLoad: $("#path-load"),
    optCrop: $("#opt-crop"),
    optTrack: $("#opt-track"),
    optOcr: $("#opt-ocr"),
    optSpeech: $("#opt-speech"),
    speechNote: $("#speech-note"),
    analyze: $("#analyze"),
    ingestNote: $("#ingest-note"),
    ingestError: $("#ingest-error"),
    progressTitle: $("#progress-title"),
    progressFile: $("#progress-file"),
    progressPct: $("#progress-pct"),
    progressBar: $("#progress-bar"),
    progressElapsed: $("#progress-elapsed"),
    progressMessage: $("#progress-message"),
    stages: $("#stages"),
    progressError: $("#progress-error"),
    progressBack: $("#progress-back"),
    resultTitle: $("#result-title"),
    resultMeta: $("#result-meta"),
    usageReadout: $("#usage-readout"),
    newVideo: $("#new-video"),
    deleteJob: $("#delete-job"),
    cleanJob: $("#clean-job"),
    cleanProfile: $("#clean-profile"),
    hookImg: $("#hook-img"),
    hookTime: $("#hook-time"),
    hookCopy: $("#hook-copy"),
    hookWhy: $("#hook-why"),
    hookScores: $("#hook-scores"),
    hookTags: $("#hook-tags"),
    hookCrop: $("#hook-crop"),
    hookChange: $("#hook-change"),
    targetTabs: $("#target-tabs"),
    planTotal: $("#plan-total"),
    planBadge: $("#plan-badge"),
    resetHook: $("#reset-hook"),
    editCut: $("#edit-cut"),
    editBar: $("#edit-bar"),
    saveVariant: $("#save-variant"),
    variantName: $("#variant-name"),
    doneEdit: $("#done-edit"),
    variantList: $("#variant-list"),
    hookLab: $("#hook-lab"),
    hookLabToggle: $("#hook-lab-toggle"),
    transcriptToggle: $("#transcript-toggle"),
    transcriptPanel: $("#transcript-panel"),
    planWhy: $("#plan-why"),
    timeline: $("#timeline"),
    timelineDrop: $("#timeline-drop"),
    momentsSection: $("#moments-section"),
    momentsRail: $("#moments-rail"),
    momentsScrub: $("#moments-scrub"),
    momentsFull: $("#moments-full"),
    momentsExpand: $("#moments-expand"),
    render: $("#render"),
    renderDraft: $("#render-draft"),
    renderAll: $("#render-all"),
    renderAb: $("#render-ab"),
    presetSelect: $("#preset-select"),
    arcOrder: $("#arc-order"),
    renderCancel: $("#render-cancel"),
    aspect: $("#aspect-select"),
    captions: $("#captions"),
    audioPanel: $("#audio-panel"),
    audioMode: $("#audio-mode"),
    audioModeTabs: $("#audio-mode-tabs"),
    audioRewriteStep: $("#audio-rewrite-step"),
    audioVoiceStep: $("#audio-voice-step"),
    audioMusicStep: $("#audio-music-step"),
    audioRewriteRun: $("#audio-rewrite-run"),
    audioRewriteNote: $("#audio-rewrite-note"),
    audioVoiceGenerate: $("#audio-voice-generate"),
    audioVoiceUpload: $("#audio-voice-upload"),
    audioMusicSource: $("#audio-music-source"),
    audioTrackField: $("#audio-track-field"),
    audioMusicUploadBox: $("#audio-music-upload-box"),
    audioMusicUpload: $("#audio-music-upload"),
    audioMusicUploadButton: $("#audio-music-upload-button"),
    audioMusicUploadClear: $("#audio-music-upload-clear"),
    audioMusicUploadName: $("#audio-music-upload-name"),
    audioMusicWarning: $("#audio-music-warning"),
    audioPromptField: $("#audio-prompt-field"),
    audioGainField: $("#audio-gain-field"),
    audioDuckField: $("#audio-duck-field"),
    audioBeatSyncField: $("#audio-beatsync-field"),
    audioVoiceSource: $("#audio-voice-source"),
    audioSourceGenerate: $("#audio-source-generate"),
    audioSourceUpload: $("#audio-source-upload"),
    audioUpload: $("#audio-upload"),
    audioUploadButton: $("#audio-upload-button"),
    audioUploadName: $("#audio-upload-name"),
    audioLang: $("#audio-lang"),
    audioStyle: $("#audio-style"),
    audioRewrite: $("#audio-rewrite"),
    audioBeatSync: $("#audio-beatsync"),
    audioBpm: $("#audio-bpm"),
    mixerPanel: $("#mixer-panel"),
    mixerCanvas: $("#mixer-canvas"),
    mixerReadout: $("#mixer-readout"),
    mixerReset: $("#mixer-reset"),
    mixerSmooth: $("#mixer-smooth"),
    audioProvider: $("#audio-provider"),
    audioEngine: $("#audio-engine"),
    audioVoice: $("#audio-voice"),
    audioRate: $("#audio-rate"),
    audioMusic: $("#audio-music"),
    audioTrack: $("#audio-track"),
    audioPrompt: $("#audio-prompt"),
    audioGain: $("#audio-gain"),
    audioDuck: $("#audio-duck"),
    audioPreview: $("#audio-preview"),
    audioStatus: $("#audio-status"),
    audioScript: $("#audio-script"),
    renderNote: $("#render-note"),
    renderProgress: $("#render-progress"),
    renderError: $("#render-error"),
    playerWrap: $("#player-wrap"),
    reelVideo: $("#reel-video"),
    reelDuration: $("#reel-duration"),
    reelSize: $("#reel-size"),
    download: $("#download"),
    exportSrt: $("#export-srt"),
    exportVtt: $("#export-vtt"),
    exportEdl: $("#export-edl"),
    exportXml: $("#export-xml"),
    shareLink: $("#share-link"),
    sortTabs: $("#sort-tabs"),
    sceneCount: $("#scene-count"),
    sceneGrid: $("#scene-grid"),
    loadMore: $("#load-more"),
    recentSection: $("#recent-section"),
    recent: $("#recent"),
    recentCount: $("#recent-count"),
    historyPanel: $("#history-panel"),
    historyCount: $("#history-count"),
    historyList: $("#history-list"),
    historyDetail: $("#history-detail"),
    drawer: $("#drawer"),
    drawerContent: $("#drawer-content"),
    toast: $("#toast"),
  };

  const state = {
    health: null,
    file: null,
    localPath: null,
    meta: null,
    fileName: "",
    job: null,
    plan: null,
    target: 30,
    aspect: "9:16",
    captions: false,
    audio: {
      mode: "keep",
      source: "generate",
      upload: "",
      uploadName: "",
      uploadDuration: 0,
      lang: "",
      provider: "auto",
      style: "smooth",
      musicSource: "none",
      rewrite: "auto",
      beatSync: false,
      engine: "say",
      voice: "",
      rate: 1,
      music: "none",
      musicUpload: "",
      musicUploadName: "",
      musicUploadDuration: 0,
      track: "",
      prompt: "",
      gain: -18,
      duck: true,
    },
    audioEngines: null,
    mixer: { ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [] },
    scriptOverrides: {},
    scriptId: null,
    lastScript: null,
    history: [],
    historyEntry: null,
    showLiteral: false,
    order: "source",
    preset: "",
    audioMoods: [],
    audioPromptAuto: "",
    overrideHook: null,
    editMode: false,
    editIndex: null,
    edited: false,
    momentsExpanded: false,
    trim: null,
    timelineScroll: 0,
    drawerScene: null,
    sort: "best",
    visible: 96,
    busy: false,
    pollTimer: null,
    pollStart: null,
    toastTimer: null,
  };

  init();

  function init() {
    bind();
    loadHealth();
    loadRecent();
    loadSetup(true);
    routeFromHash();
    setInterval(tickElapsed, 1000);
  }

  // ---------------------------------------------------------------- setup

  function setSecretHint(input, configured, source, allowOverride = false) {
    if (source === "env") {
      input.placeholder = allowOverride
        ? "env key active · paste project key to override"
        : "set by environment · env wins";
      input.disabled = !allowOverride;
      input.dataset.configured = "1";
      return;
    }
    input.disabled = false;
    input.placeholder = configured
      ? "configured · leave blank to keep"
      : (input.dataset.empty || "not set");
    input.dataset.configured = configured ? "1" : "0";
  }

  function applySetup(data) {
    const settings = data.settings || {};
    const secrets = data.secrets || {};
    const sources = data.sources || {};
    const opencode = settings.opencode || {};
    dom.setupOpencodeEnabled.checked = opencode.enabled !== false;
    dom.setupOpencodeModel.value = opencode.model || "deepseek-v4.1-flash";
    dom.setupOpencodeVariant.value = opencode.variant || "low";
    dom.setupUseRewrite.checked = opencode.use_rewrite !== false;
    dom.setupUseBrief.checked = opencode.use_brief !== false;
    dom.setupTranslationMode.value = (settings.translation || {}).mode || "auto";
    const runtime = data.runtime || {};
    if (runtime.opencode_mode === "api") {
      dom.setupOpencodeStatus.textContent = "Direct OpenCode Go API key configured for this project · low reasoning.";
    } else if (runtime.opencode) {
      dom.setupOpencodeStatus.textContent = "Local OpenCode service ready · uses your OpenCode Go login · low reasoning.";
    } else {
      dom.setupOpencodeStatus.textContent = "No OpenCode key or service. Add a key here, or sign in with OpenCode, or use local MLX / Ollama.";
    }
    dom.setupOpencodeStatus.classList.toggle("warn", !runtime.opencode);
    dom.setupSttProvider.value = (settings.stt || {}).provider || "auto";
    dom.setupSttLanguage.value = (settings.stt || {}).language || "en";
    const whisperModels = runtime.whisper_models || [];
    const modelOptions = whisperModels.length
      ? whisperModels.map((item) => [
        item.id,
        `${item.name}${item.cached ? " · cached" : ` · ~${item.size_mb} MB download`}`,
      ])
      : [["mlx-community/whisper-small-mlx", "Whisper small"]];
    fillSelect(dom.setupSttModel, modelOptions);
    dom.setupSttModel.value = (settings.stt || {}).model || "mlx-community/whisper-small-mlx";
    dom.setupTtsProvider.value = (settings.tts || {}).provider || "auto";
    setSecretHint(dom.setupOpencodeKey, !!secrets.opencode, sources.opencode);
    setSecretHint(dom.setupOpenrouterKey, !!secrets.openrouter, sources.openrouter, true);
    setSecretHint(dom.setupMinimaxKey, !!secrets.minimax, sources.minimax);
    [dom.setupOpencodeKey, dom.setupOpenrouterKey, dom.setupMinimaxKey].forEach((input) => {
      if (input) input.value = "";
    });
    state.setup = settings;
    state.setupSecrets = secrets;
    if (dom.speechNote && !dom.speechNote.textContent.includes("unavailable")) {
      dom.speechNote.textContent = "Apple / local Whisper";
    }
  }

  async function loadSetup(quiet = false) {
    try {
      const data = await api("/api/settings");
      applySetup(data);
      if (quiet) return data;
      dom.setupStatus.textContent = data.runtime?.opencode_mode === "api"
        ? "OpenCode Go is ready with this project's API key."
        : data.runtime?.opencode
          ? "OpenCode Go is ready through the local login."
          : "OpenCode service not found. Local engines are active.";
      return data;
    } catch (error) {
      if (!quiet) dom.setupStatus.textContent = error.message;
      return null;
    }
  }

  async function openSetup() {
    dom.setup.hidden = false;
    dom.setupStatus.textContent = "Loading…";
    await loadSetup();
  }

  function closeSetup() {
    dom.setup.hidden = true;
  }

  function setupSecrets() {
    const values = {
      opencode: dom.setupOpencodeKey.value.trim(),
      openrouter: dom.setupOpenrouterKey.value.trim(),
      minimax: dom.setupMinimaxKey.value.trim(),
    };
    return Object.fromEntries(Object.entries(values).filter(([, value]) => value));
  }

  async function saveSetup() {
    dom.setupSave.disabled = true;
    dom.setupStatus.textContent = "Saving…";
    try {
      const payload = {
        settings: {
          opencode: {
            enabled: dom.setupOpencodeEnabled.checked,
            model: dom.setupOpencodeModel.value.trim() || "deepseek-v4.1-flash",
            variant: "low",
            use_rewrite: dom.setupUseRewrite.checked,
            use_brief: dom.setupUseBrief.checked,
            use_translate: dom.setupTranslationMode.value !== "local_only",
          },
          translation: {
            mode: dom.setupTranslationMode.value,
          },
          stt: {
            provider: dom.setupSttProvider.value,
            language: dom.setupSttLanguage.value,
            model: dom.setupSttModel.value,
          },
          tts: { provider: dom.setupTtsProvider.value },
        },
        secrets: setupSecrets(),
      };
      const data = await api("/api/settings", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      applySetup(data);
      dom.setupStatus.textContent = "Saved. Local fallback still active.";
      toast("Setup saved.");
      await loadAudioEngines();
      const preferred = dom.setupTtsProvider.value;
      if (preferred && preferred !== "auto" && preferred !== "local"
          && state.audioEngines?.voices?.[preferred]?.available) {
        state.audio.engine = preferred;
        dom.audioEngine.value = preferred;
        loadAudioVoices();
      }
      refreshAudioStatus();
    } catch (error) {
      dom.setupStatus.textContent = error.message;
    } finally {
      dom.setupSave.disabled = false;
    }
  }

  async function testSetup(kind, button, extra = {}) {
    const old = button.textContent;
    button.disabled = true;
    button.textContent = "Testing…";
    dom.setupStatus.textContent = "";
    try {
      const result = await api("/api/settings/test", {
        method: "POST",
        body: JSON.stringify({ kind, ...extra }),
      });
      const bits = [result.ok ? "OK" : "Not ready", result.detail];
      if (result.model) bits.push(result.model);
      if (result.engine) bits.push(result.engine);
      if (result.voice) bits.push(result.voice);
      if (result.text) bits.push(`“${result.text.slice(0, 120)}”`);
      if (result.seconds !== undefined) bits.push(`${result.seconds}s`);
      dom.setupStatus.textContent = bits.filter(Boolean).join(" · ");
      if (result.url && dom.setupTtsAudio) {
        dom.setupTtsAudio.src = withToken(result.url);
        dom.setupTtsAudio.hidden = false;
        dom.setupTtsAudio.play().catch(() => {});
      }
    } catch (error) {
      dom.setupStatus.textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  }

  function bindSetup() {
    dom.setupOpen.addEventListener("click", openSetup);
    dom.setupClose.addEventListener("click", closeSetup);
    dom.setup.querySelectorAll("[data-setup-close]").forEach((node) => {
      node.addEventListener("click", closeSetup);
    });
    dom.setupSave.addEventListener("click", saveSetup);
    dom.setupTestOpencode.addEventListener("click", () => testSetup("opencode", dom.setupTestOpencode));
    dom.setupTestOpenrouter.addEventListener("click", () => testSetup("openrouter", dom.setupTestOpenrouter));
    dom.setupTestStt.addEventListener("click", () => testSetup("stt", dom.setupTestStt));
    dom.setupTestSttLive.addEventListener("click", () => testSetup(
      "stt_live", dom.setupTestSttLive, { provider: dom.setupSttProvider.value },
    ));
    dom.setupTestTts.addEventListener("click", () => testSetup("tts", dom.setupTestTts));
    dom.setupTestTtsLive.addEventListener("click", () => testSetup(
      "tts_live", dom.setupTestTtsLive, { engine: dom.setupTtsProvider.value },
    ));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !dom.setup.hidden) closeSetup();
    });
  }

  // ---------------------------------------------------------------- api

  async function api(path, options = {}) {
    const config = { ...options };
    if (config.body && !config.headers) {
      config.headers = { "Content-Type": "application/json" };
    }
    const token = tokenValue();
    if (token) {
      config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
    }
    let response = await fetch(path, config);
    if (response.status === 401 && !config.__retried) {
      const supplied = window.prompt("VibeCut token");
      if (supplied) {
        try { localStorage.setItem("vibecut_token", supplied.trim()); } catch (_) { /* ignore */ }
        config.__retried = true;
        return api(path, config);
      }
    }
    if (!response.ok) {
      let detail = response.statusText || "Request failed";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) { /* ignore */ }
      if (typeof detail !== "string") detail = JSON.stringify(detail);
      throw new Error(detail);
    }
    return response.json();
  }

  function tokenValue() {
    try { return localStorage.getItem("vibecut_token") || ""; } catch (_) { return ""; }
  }

  function withToken(url) {
    const token = tokenValue();
    if (!token || !url) return url;
    return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
  }

  function uploadFile(file, options, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/jobs/upload");
      const uploadToken = tokenValue();
      if (uploadToken) xhr.setRequestHeader("Authorization", `Bearer ${uploadToken}`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(event.loaded / event.total, event.loaded, event.total);
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.response);
          return;
        }
        const detail = xhr.response && xhr.response.detail;
        reject(new Error(typeof detail === "string" ? detail : (xhr.statusText || "Upload failed.")));
      };
      xhr.onerror = () => reject(new Error("Upload failed. Is the server running?"));
      const form = new FormData();
      form.append("file", file);
      form.append("options", JSON.stringify(options));
      xhr.send(form);
    });
  }

  // ---------------------------------------------------------------- health + recent

  async function loadHealth() {
    try {
      const health = await api("/api/health");
      state.health = health;
      const version = (health.ffmpeg.match(/ffmpeg version (\S+)/) || [])[1] || "ffmpeg";
      dom.health.textContent = `${version} · ${health.vision ? "vision" : "center crop"} · ${health.whisper ? "whisper" : "no speech"}`;
      dom.footerHealth.textContent = `local · ${health.vision ? "apple vision" : "center crop"}`;
      if (!health.vision) {
        dom.optOcr.checked = false;
        dom.optOcr.disabled = true;
        const note = dom.optOcr.closest(".check")?.querySelector("small");
        if (note) note.textContent = "unavailable";
      }
      if (!health.whisper) {
        dom.optSpeech.disabled = true;
        dom.optSpeech.checked = false;
        dom.speechNote.textContent = "unavailable";
      }
      syncOptions();
    } catch (_) {
      dom.health.textContent = "engine offline";
      dom.footerHealth.textContent = "engine offline";
    }
  }

  async function loadRecent() {
    try {
      const data = await api("/api/jobs");
      const jobs = data.jobs || [];
      if (!jobs.length) {
        dom.recentSection.hidden = true;
        return;
      }
      dom.recentSection.hidden = false;
      dom.recentCount.textContent = `${jobs.length} local`;
      dom.recent.innerHTML = jobs.map((job) => {
        const status = job.status === "ready"
          ? "ready"
          : job.status === "failed"
            ? "failed"
            : `${Math.round((job.progress || 0) * 100)}%`;
        const thumb = job.hook_thumb
          ? `<img src="${esc(job.hook_thumb)}" alt="" loading="lazy">`
          : `<div class="empty">${job.scene_count ? `${job.scene_count} scenes` : "working"}</div>`;
        return `
          <button class="recent-card" data-id="${esc(job.id)}">
            <div class="recent-thumb">${thumb}</div>
            <div class="recent-copy">
              <strong title="${esc(job.name || "Untitled video")}">${esc(job.name || "Untitled video")}</strong>
              <span>${esc(fmtDuration(job.duration))} · ${esc(formatDate(job.created))}</span>
            </div>
            <div class="recent-status"><span>${esc(job.scene_count ? `${job.scene_count} scenes` : job.message || "queued")}</span><span class="dot">${esc(status)}</span></div>
          </button>`;
      }).join("");
    } catch (_) {
      dom.recentSection.hidden = true;
    }
  }

  // ---------------------------------------------------------------- events

  function bind() {
    dom.brand.addEventListener("click", (event) => {
      event.preventDefault();
      resetToIngest();
    });

    dom.dropzone.addEventListener("click", () => dom.fileInput.click());
    dom.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        dom.fileInput.click();
      }
    });
    dom.fileInput.addEventListener("change", () => {
      const file = dom.fileInput.files && dom.fileInput.files[0];
      if (file) handleFile(file);
    });

    ["dragenter", "dragover"].forEach((name) => {
      dom.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dom.dropzone.classList.add("dragging");
      });
    });
    ["dragleave", "dragend"].forEach((name) => {
      dom.dropzone.addEventListener(name, () => dom.dropzone.classList.remove("dragging"));
    });
    dom.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dom.dropzone.classList.remove("dragging");
      const file = event.dataTransfer?.files?.[0];
      if (file) handleFile(file);
    });

    dom.clearFile.addEventListener("click", clearFile);
    dom.pathLoad.addEventListener("click", inspectPath);
    dom.pathInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") inspectPath();
    });
    dom.analyze.addEventListener("click", startAnalysis);
    dom.optCrop.addEventListener("change", syncOptions);
    dom.progressBack.addEventListener("click", resetToIngest);
    dom.newVideo.addEventListener("click", resetToIngest);
    dom.deleteJob.addEventListener("click", deleteJob);
    dom.cleanJob.addEventListener("click", cleanJobFiles);

    dom.targetTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-target]");
      if (button) setTarget(Number(button.dataset.target));
    });
    dom.sortTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-sort]");
      if (button) setSort(button.dataset.sort);
    });
    dom.loadMore.addEventListener("click", () => {
      state.visible += 96;
      renderScenes();
    });
    dom.hookChange.addEventListener("click", () => {
      setSort("best");
      state.momentsExpanded = true;
      dom.momentsFull.hidden = false;
      dom.momentsExpand.textContent = "Collapse";
      renderScenes();
      dom.momentsSection?.scrollIntoView({ behavior: "smooth", block: "start" });
      toast("Tap a scene, then use it as the hook.");
    });
    dom.resetHook.addEventListener("click", resetHook);
    dom.render.addEventListener("click", () => startRender("final"));
    dom.renderDraft.addEventListener("click", () => startRender("draft"));
    dom.renderAll.addEventListener("click", startRenderAll);
    dom.renderCancel.addEventListener("click", cancelRender);
    dom.aspect.addEventListener("change", () => {
      state.aspect = dom.aspect.value;
      state.preset = "";
      dom.presetSelect.value = "";
      updateRenderPanel();
      if (state.plan) renderHook();
    });
    dom.presetSelect.addEventListener("change", applyPreset);
    dom.arcOrder.addEventListener("change", async () => {
      state.order = dom.arcOrder.checked ? "arc" : "source";
      state.edited = false;
      state.scriptOverrides = {};
      state.scriptId = null;
      state.lastScript = null;
      try {
        await refreshPlan();
        loadAudioMoods();
        loadAudioScript();
        toast(state.order === "arc" ? "Story arc order." : "Source order.");
      } catch (error) {
        toast(error.message);
      }
    });
    dom.renderAb.addEventListener("click", abHooks);
    bindMixer();
    dom.exportSrt.addEventListener("click", () => exportCut("srt"));
    dom.exportVtt.addEventListener("click", () => exportCut("vtt"));
    dom.exportEdl.addEventListener("click", () => exportCut("edl"));
    dom.exportXml.addEventListener("click", () => exportCut("xml"));
    dom.shareLink.addEventListener("click", createReviewLink);
    dom.captions.addEventListener("change", () => {
      state.captions = dom.captions.checked;
      updateRenderPanel();
    });
    bindAudio();
    bindSetup();

    dom.timeline.addEventListener("click", (event) => {
      if (event.target.closest(".trim-handle")) return;
      const tool = event.target.closest("[data-edit]");
      if (tool) {
        event.stopPropagation();
        editClip(Number(tool.dataset.index), tool.dataset.edit);
        return;
      }
      const clip = event.target.closest(".clip[data-index]");
      if (state.editMode && clip) {
        state.editIndex = Number(clip.dataset.index);
        renderPlan();
        return;
      }
      const button = event.target.closest("[data-scene]");
      if (button) openDrawer(Number(button.dataset.scene));
    });
    dom.timeline.addEventListener("dragstart", (event) => {
      const clip = event.target.closest(".clip[data-index]");
      if (!clip || event.target.closest(".trim-handle")) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-vibecut-clip", clip.dataset.index);
      clip.classList.add("dragging");
      dom.timelineDrop.hidden = false;
    });
    dom.timeline.addEventListener("dragover", (event) => {
      if (!event.dataTransfer.types.length) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = event.dataTransfer.types.includes("application/x-vibecut-scene")
        ? "copy" : "move";
      dom.timeline.querySelectorAll(".drop-target").forEach((node) => node.classList.remove("drop-target"));
      const target = event.target.closest(".clip[data-index]");
      if (target) target.classList.add("drop-target");
    });
    dom.timeline.addEventListener("dragleave", (event) => {
      if (!dom.timeline.contains(event.relatedTarget)) {
        dom.timeline.querySelectorAll(".drop-target").forEach((node) => node.classList.remove("drop-target"));
      }
    });
    dom.timeline.addEventListener("drop", (event) => {
      event.preventDefault();
      const target = event.target.closest(".clip[data-index]");
      const at = target ? Number(target.dataset.index) : null;
      const scene = event.dataTransfer.getData("application/x-vibecut-scene");
      const clipIndex = event.dataTransfer.getData("application/x-vibecut-clip");
      dom.timeline.querySelectorAll(".drop-target").forEach((node) => node.classList.remove("drop-target"));
      if (scene !== "") {
        addSceneToPlan(Number(scene), at);
      } else if (clipIndex !== "") {
        moveClip(Number(clipIndex), at === null ? (state.plan?.clips.length || 0) : at);
      }
      dom.timelineDrop.hidden = true;
    });
    dom.timeline.addEventListener("dragend", () => {
      dom.timeline.querySelectorAll(".dragging, .drop-target").forEach((node) => {
        node.classList.remove("dragging", "drop-target");
      });
      dom.timelineDrop.hidden = true;
    });
    dom.timelineDrop.addEventListener("dragover", (event) => {
      if (event.dataTransfer.types.includes("application/x-vibecut-clip")
          || event.dataTransfer.types.includes("application/x-vibecut-scene")) {
        event.preventDefault();
        event.dataTransfer.dropEffect = event.dataTransfer.types.includes("application/x-vibecut-scene")
          ? "copy" : "move";
        dom.timelineDrop.classList.add("armed");
      }
    });
    dom.timelineDrop.addEventListener("dragleave", () => dom.timelineDrop.classList.remove("armed"));
    dom.timelineDrop.addEventListener("drop", (event) => {
      event.preventDefault();
      const scene = event.dataTransfer.getData("application/x-vibecut-scene");
      const clipIndex = event.dataTransfer.getData("application/x-vibecut-clip");
      dom.timelineDrop.classList.remove("armed");
      if (scene !== "") addSceneToPlan(Number(scene), null);
      else if (clipIndex !== "") removeClipAt(Number(clipIndex));
      dom.timelineDrop.hidden = true;
    });
    dom.timeline.addEventListener("scroll", () => {
      state.timelineScroll = dom.timeline.scrollLeft;
    });
    dom.timeline.addEventListener("pointerdown", (event) => {
      const handle = event.target.closest(".trim-handle");
      if (!handle || !state.plan) return;
      event.preventDefault();
      event.stopPropagation();
      const index = Number(handle.dataset.index);
      const clip = state.plan.clips[index];
      const scene = sceneById(clip?.scene);
      if (!clip || !scene) return;
      state.trim = {
        index,
        side: handle.dataset.trim,
        startX: event.clientX,
        start: Number(clip.start),
        end: Number(clip.end),
        sceneStart: Number(scene.start),
        sceneEnd: Number(scene.end),
      };
      state.editIndex = index;
    });
    document.addEventListener("pointermove", (event) => {
      const trim = state.trim;
      if (!trim || !state.plan) return;
      const clip = state.plan.clips[trim.index];
      if (!clip) return;
      const secondsPerPixel = Math.max(0.01, (trim.sceneEnd - trim.sceneStart) / 86);
      const delta = (event.clientX - trim.startX) * secondsPerPixel;
      if (trim.side === "start") {
        clip.start = Math.max(trim.sceneStart, Math.min(trim.end - 0.5, trim.start + delta));
      } else {
        clip.end = Math.min(trim.sceneEnd, Math.max(trim.start + 0.5, trim.end + delta));
      }
      clip.dur = Math.round((clip.end - clip.start) * 100) / 100;
      const node = dom.timeline.querySelector(`.clip[data-index="${trim.index}"] .clip-time`);
      if (node) node.textContent = `${clip.dur.toFixed(1)}s`;
      const clipNode = dom.timeline.querySelector(`.clip[data-index="${trim.index}"]`);
      if (clipNode) clipNode.style.flex = `0 0 ${clipWidth(clip)}`;
    });
    document.addEventListener("pointerup", () => {
      if (!state.trim) return;
      state.trim = null;
      syncEditedPlan();
      renderPlan();
      renderScenes();
      updateRenderPanel();
    });
    dom.editCut.addEventListener("click", () => toggleEdit());
    dom.doneEdit.addEventListener("click", () => toggleEdit(false));
    dom.saveVariant.addEventListener("click", saveVariant);
    dom.variantList.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-variant-delete]");
      if (remove) {
        deleteVariant(remove.dataset.variantDelete);
        return;
      }
      const load = event.target.closest("[data-variant-load]");
      if (load) loadVariant(load.dataset.variantLoad);
    });
    dom.hookLabToggle.addEventListener("click", toggleHookLab);
    dom.hookLab.addEventListener("click", (event) => {
      const pick = event.target.closest("[data-lab-hook]");
      if (pick) useHook(Number(pick.dataset.labHook));
    });
    dom.transcriptToggle.addEventListener("click", toggleTranscript);
    dom.transcriptPanel.addEventListener("click", (event) => {
      const row = event.target.closest("[data-transcript-time]");
      if (!row) return;
      const text = row.dataset.transcriptText || "";
      if (navigator.clipboard && text) {
        navigator.clipboard.writeText(text).then(() => toast("Transcript line copied.")).catch(() => {});
      }
    });
    dom.sceneGrid.addEventListener("click", (event) => {
      const button = event.target.closest("[data-scene]");
      if (button) openDrawer(Number(button.dataset.scene));
    });
    dom.momentsRail.addEventListener("click", (event) => {
      const card = event.target.closest("[data-moment-scene]");
      if (card) openDrawer(Number(card.dataset.momentScene));
    });
    dom.momentsRail.addEventListener("dragstart", (event) => {
      const card = event.target.closest("[data-moment-scene]");
      if (!card) return;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-vibecut-scene", card.dataset.momentScene);
      dom.timelineDrop.hidden = false;
    });
    dom.momentsRail.addEventListener("dragend", () => {
      dom.timelineDrop.hidden = true;
    });
    dom.sceneGrid.addEventListener("dragstart", (event) => {
      const card = event.target.closest("[data-scene]");
      if (!card) return;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-vibecut-scene", card.dataset.scene);
      dom.timelineDrop.hidden = false;
    });
    dom.sceneGrid.addEventListener("dragend", () => {
      dom.timelineDrop.hidden = true;
    });
    dom.momentsExpand.addEventListener("click", () => {
      state.momentsExpanded = !state.momentsExpanded;
      dom.momentsFull.hidden = !state.momentsExpanded;
      dom.momentsExpand.textContent = state.momentsExpanded ? "Collapse" : "Expand";
      if (state.momentsExpanded) renderScenes();
    });
    dom.momentsScrub.addEventListener("input", () => {
      const index = Number(dom.momentsScrub.value) || 0;
      const card = dom.momentsRail.querySelector(`[data-rail-index="${index}"]`);
      card?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    });
    let railScrollFrame = null;
    dom.momentsRail.addEventListener("scroll", () => {
      if (railScrollFrame) return;
      railScrollFrame = requestAnimationFrame(() => {
        railScrollFrame = null;
        syncRailScrub();
      });
    });
    dom.recent.addEventListener("click", (event) => {
      const card = event.target.closest("[data-id]");
      if (card) openJob(card.dataset.id);
    });
    dom.historyList.addEventListener("click", (event) => {
      const row = event.target.closest("[data-history-entry]");
      if (row) viewHistoryEntry(row.dataset.historyEntry);
    });
    dom.historyDetail.addEventListener("click", (event) => {
      const restore = event.target.closest("[data-history-restore]");
      if (restore) {
        restoreHistoryEntry(restore.dataset.historyRestore);
        return;
      }
      const remove = event.target.closest("[data-history-delete]");
      if (remove) {
        deleteHistoryEntry(remove.dataset.historyDelete);
        return;
      }
      const copy = event.target.closest("[data-history-copy]");
      if (copy && state.historyEntry) {
        const snapshot = state.historyEntry.snapshot || {};
        const lines = copy.dataset.historyCopy === "original"
          ? (snapshot.original_lines || [])
          : (snapshot.final_lines || []).map((line) => line.text || "");
        copyText(lines.join("\n"), copy.dataset.historyCopy === "original"
          ? "Original script copied." : "Final script copied.");
      }
    });

    dom.drawer.addEventListener("click", (event) => {
      if (event.target.closest("[data-close]")) {
        closeDrawer();
        return;
      }
      const use = event.target.closest("[data-use-hook]");
      if (use) useHook(Number(use.dataset.useHook));
      const add = event.target.closest("[data-add-scene]");
      if (add && addSceneToPlan(Number(add.dataset.addScene))) closeDrawer();
      const read = event.target.closest("[data-read-scene]");
      if (read) readScene(Number(read.dataset.readScene));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeDrawer();
    });
    document.addEventListener("keydown", (event) => {
      if (dom.result.hidden || !state.plan) return;
      if (dom.setup && !dom.setup.hidden) return;
      const tag = String(event.target?.tagName || "").toLowerCase();
      if (["input", "select", "textarea"].includes(tag) || event.target?.isContentEditable) return;
      if (event.metaKey || event.ctrlKey) return;
      if (!dom.drawer.hidden) {
        if (event.key.toLowerCase() === "a" && state.drawerScene !== null) {
          event.preventDefault();
          if (addSceneToPlan(state.drawerScene)) closeDrawer();
        }
        return;
      }
      const clips = state.plan.clips || [];
      if (!clips.length) return;
      if (event.key === "e") {
        event.preventDefault();
        toggleEdit();
        return;
      }
      if (event.key === "s") {
        event.preventDefault();
        saveVariant();
        return;
      }
      if (event.key === "r") {
        event.preventDefault();
        startRender("draft");
        return;
      }
      if (event.key === " ") {
        if (dom.reelVideo?.src) {
          event.preventDefault();
          if (dom.reelVideo.paused) dom.reelVideo.play().catch(() => {});
          else dom.reelVideo.pause();
        }
        return;
      }
      if (!state.editMode) return;
      if (event.key === "Escape") {
        state.editIndex = null;
        state.editMode = false;
        renderPlan();
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const step = event.key === "ArrowLeft" ? -1 : 1;
        if (event.altKey) {
          editClip(state.editIndex ?? 0, step < 0 ? "up" : "down");
        } else {
          state.editIndex = Math.max(0, Math.min(clips.length - 1, (state.editIndex ?? 0) + step));
          renderPlan();
        }
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        editClip(state.editIndex ?? 0, "remove");
        return;
      }
      if (event.key === "-" || event.key === "+" || event.key === "=") {
        event.preventDefault();
        editClip(state.editIndex ?? 0, event.key === "-" ? "shorter" : "longer");
      }
    });
    window.addEventListener("hashchange", () => {
      const match = location.hash.match(/^#job=([a-z0-9]+)/i);
      if (match && state.job?.id !== match[1]) openJob(match[1]);
    });
  }

  // ---------------------------------------------------------------- file intake

  function handleFile(file) {
    state.file = file;
    state.localPath = null;
    state.meta = null;
    state.fileName = file.name;
    dom.ingestError.hidden = true;
    dom.dropzone.hidden = true;
    dom.fileCard.hidden = false;
    dom.fileName.textContent = file.name;
    dom.fileInfo.textContent = formatSize(file.size);
    dom.ingestNote.textContent = "Uploads a local copy into vibecut/data.";
    dom.pathInput.value = "";
    syncOptions();
    updateAnalyzeState();
    readBrowserMeta(file);
  }

  function readBrowserMeta(file) {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    let finished = false;
    const cleanup = () => {
      if (finished) return;
      finished = true;
      URL.revokeObjectURL(url);
      video.removeAttribute("src");
      video.load();
    };
    video.preload = "metadata";
    video.muted = true;
    video.onloadedmetadata = () => {
      if (state.file !== file) {
        cleanup();
        return;
      }
      state.meta = {
        duration: Number.isFinite(video.duration) ? video.duration : 0,
        width: video.videoWidth || 0,
        height: video.videoHeight || 0,
        has_audio: true,
      };
      updateFileInfo();
      applyMetaDefaults();
      cleanup();
    };
    video.onerror = cleanup;
    video.src = url;
  }

  function clearFile() {
    state.file = null;
    state.localPath = null;
    state.meta = null;
    state.fileName = "";
    dom.fileInput.value = "";
    dom.pathInput.value = "";
    dom.dropzone.hidden = false;
    dom.fileCard.hidden = true;
    dom.fileName.textContent = "";
    dom.fileInfo.textContent = "";
    dom.ingestError.hidden = true;
    dom.ingestNote.textContent = "ffmpeg cuts first. Analysis follows.";
    dom.optSpeech.checked = false;
    dom.optCrop.checked = true;
    dom.optOcr.checked = state.health ? state.health.vision : true;
    syncOptions();
    updateAnalyzeState();
  }

  async function inspectPath() {
    const path = dom.pathInput.value.trim();
    if (!path) return;
    dom.ingestError.hidden = true;
    dom.pathLoad.disabled = true;
    dom.pathLoad.textContent = "Reading…";
    try {
      const meta = await api("/api/inspect", {
        method: "POST",
        body: JSON.stringify({ path }),
      });
      state.file = null;
      state.localPath = path;
      state.meta = meta;
      state.fileName = basename(path);
      dom.dropzone.hidden = true;
      dom.fileCard.hidden = false;
      dom.fileName.textContent = state.fileName;
      dom.ingestNote.textContent = "Read in place · no copy.";
      updateFileInfo();
      applyMetaDefaults();
      updateAnalyzeState();
      toast("Video loaded in place.");
    } catch (error) {
      dom.ingestError.textContent = error.message;
      dom.ingestError.hidden = false;
    } finally {
      dom.pathLoad.disabled = false;
      dom.pathLoad.textContent = "Load";
    }
  }

  function updateFileInfo() {
    const meta = state.meta;
    const bits = [];
    if (meta?.duration) bits.push(fmtDuration(meta.duration));
    if (meta?.width && meta?.height) bits.push(`${meta.width}×${meta.height}`);
    const size = state.file?.size || meta?.size;
    if (size) bits.push(formatSize(size));
    if (meta && meta.has_audio === false) bits.push("no audio");
    dom.fileInfo.textContent = bits.join(" · ");
  }

  function applyMetaDefaults() {
    const hasAudio = state.meta?.has_audio !== false;
    const whisper = state.health ? state.health.whisper : true;
    const duration = Number(state.meta?.duration) || 0;
    const short = duration > 0 && duration <= 900;
    dom.optSpeech.checked = hasAudio && whisper && short;
    dom.optCrop.checked = true;
    dom.optOcr.checked = state.health ? state.health.vision : true;
    syncOptions();
    updateAnalyzeState();
  }

  function syncOptions() {
    const hasAudio = state.meta ? state.meta.has_audio !== false : true;
    const whisper = state.health ? state.health.whisper : true;
    const vision = state.health ? state.health.vision : true;
    dom.optSpeech.disabled = !hasAudio || !whisper;
    if (dom.optSpeech.disabled) dom.optSpeech.checked = false;
    if (!hasAudio) {
      dom.speechNote.textContent = "no audio track";
    } else if (!whisper) {
      dom.speechNote.textContent = "unavailable";
    } else if (state.meta?.duration > 900) {
      dom.speechNote.textContent = "long video · adds time";
    } else {
      dom.speechNote.textContent = "Apple / local Whisper";
    }
    if (!vision) {
      dom.optOcr.checked = false;
      dom.optOcr.disabled = true;
    } else if (!dom.optOcr.disabled) {
      dom.optOcr.disabled = false;
    }
    dom.optTrack.disabled = !vision || !dom.optCrop.checked;
    updateAnalyzeState();
  }

  function readOptions() {
    return {
      ocr: dom.optOcr.checked,
      crop_tracking: dom.optTrack.checked,
      transcribe: dom.optSpeech.checked,
      transcribe_engine: state.setup?.stt?.provider || "auto",
      speech_language: state.setup?.stt?.language || "en",
      smart_crop: dom.optCrop.checked,
    };
  }

  function updateAnalyzeState() {
    dom.analyze.disabled = state.busy || (!state.file && !state.localPath);
  }

  // ---------------------------------------------------------------- analysis

  async function startAnalysis() {
    if (!state.file && !state.localPath) return;
    const options = readOptions();
    dom.ingestError.hidden = true;
    state.busy = true;
    updateAnalyzeState();
    state.pollStart = Date.now();
    state.progressStart = Date.now();

    if (state.file) {
      showView("progress");
      setProgressFile(state.file.name);
      dom.progressTitle.textContent = "Sending the file";
      updateUploadProgress(0, 0, state.file.size);
      try {
        const result = await uploadFile(state.file, options, updateUploadProgress);
        state.pollStart = Date.now();
        setProgressFile(state.file.name);
        updateProgress({ status: "queued", progress: 0.01, message: "Queued for dissection" });
        startAnalysisPoll(result.id);
      } catch (error) {
        state.busy = false;
        updateAnalyzeState();
        showView("ingest");
        showIngestError(error.message);
      }
    } else {
      showView("progress");
      setProgressFile(state.fileName);
      updateProgress({ status: "queued", progress: 0.01, message: "Queued for dissection" });
      try {
        const result = await api("/api/jobs/path", {
          method: "POST",
          body: JSON.stringify({ path: state.localPath, options }),
        });
        state.pollStart = Date.now();
        startAnalysisPoll(result.id);
      } catch (error) {
        state.busy = false;
        updateAnalyzeState();
        showView("ingest");
        showIngestError(error.message);
      }
    }
  }

  function startAnalysisPoll(id) {
    stopPoll();
    const tick = async () => {
      try {
        const status = await api(`/api/jobs/${id}/status`);
        updateProgress(status);
        if (status.status === "ready") {
          stopPoll();
          await openJob(id);
          return;
        }
        if (status.status === "failed") {
          stopPoll();
          state.busy = false;
          updateAnalyzeState();
          showProgressError(status.error || status.message || "Analysis failed.");
          return;
        }
        state.pollTimer = setTimeout(tick, 750);
      } catch (_) {
        state.pollTimer = setTimeout(tick, 1600);
      }
    };
    tick();
  }

  function updateUploadProgress(fraction, loaded, total) {
    const pct = Math.round(fraction * 100);
    dom.progressBar.style.width = `${pct}%`;
    dom.progressPct.textContent = `${pct}%`;
    dom.progressMessage.textContent = `Sending source · ${formatSize(loaded)}${total ? ` / ${formatSize(total)}` : ""}`;
    $$(".stage-list > div").forEach((element) => {
      element.classList.remove("active", "done");
    });
  }

  function updateProgress(status) {
    const pct = Math.max(0, Math.min(100, Math.round((status.progress || 0) * 100)));
    dom.progressBar.style.width = `${pct}%`;
    dom.progressPct.textContent = `${pct}%`;
    dom.progressMessage.textContent = status.message || "Working";
    dom.progressError.hidden = status.status !== "failed";
    if (status.status === "failed") {
      dom.progressError.textContent = status.error || status.message || "Analysis failed.";
    }
    dom.progressBack.hidden = status.status !== "failed";

    const titles = {
      queued: "Queued",
      scanning: "Finding the cuts",
      reading: "Reading the video",
      scoring: "Choosing the hook",
      ready: "Cut ready",
      failed: "That didn't work",
    };
    dom.progressTitle.textContent = titles[status.status] || "Reading the video";

    const order = ["scanning", "reading", "scoring", "ready"];
    const current = order.indexOf(status.status);
    $$(".stage-list > div").forEach((element, index) => {
      const stage = element.dataset.stage;
      const stageIndex = order.indexOf(stage);
      element.classList.toggle("active", stageIndex === current && status.status !== "ready");
      element.classList.toggle("done", current > stageIndex || status.status === "ready");
    });
  }

  function showProgressError(message) {
    dom.progressError.textContent = message || "Analysis failed.";
    dom.progressError.hidden = false;
    dom.progressBack.hidden = false;
  }

  function setProgressFile(name) {
    dom.progressFile.textContent = name || "video";
  }

  function showProgressForJob(job) {
    state.progressStart = Date.now();
    state.pollStart = Date.now();
    setProgressFile(job.source?.name || state.fileName || "video");
    showView("progress");
    updateProgress(job);
    if (job.status === "failed") {
      showProgressError(job.error || job.message);
    }
  }

  function tickElapsed() {
    if (dom.progress.hidden) return;
    const start = state.pollStart || state.progressStart;
    if (!start) return;
    const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
    dom.progressElapsed.textContent = fmtTime(seconds);
  }

  function stopPoll() {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  }

  // ---------------------------------------------------------------- open + render result

  async function openJob(id) {
    stopPoll();
    try {
      const job = await api(`/api/jobs/${id}`);
      if (state.job?.id !== job.id) {
        state.audio.upload = "";
        state.audio.uploadName = "";
        state.audio.uploadDuration = 0;
        state.audio.musicUpload = "";
        state.audio.musicUploadName = "";
        state.audio.musicUploadDuration = 0;
        state.audio.source = "generate";
        state.scriptOverrides = {};
        state.scriptId = null;
        state.lastScript = null;
        state.history = [];
        state.historyEntry = null;
        state.timelineScroll = 0;
        if (dom.historyList) dom.historyList.innerHTML = "";
        if (dom.historyDetail) {
          dom.historyDetail.hidden = true;
          dom.historyDetail.innerHTML = "";
        }
        if (dom.historyCount) dom.historyCount.textContent = "";
        if (dom.audioUpload) dom.audioUpload.value = "";
        if (dom.audioMusicUpload) dom.audioMusicUpload.value = "";
        if (dom.audioSourceGenerate) dom.audioSourceGenerate.checked = true;
        syncAudioVisibility();
      }
      state.job = job;
      if (job.status === "ready") {
        prepareResult(job);
      } else if (job.status === "failed") {
        state.busy = false;
        updateAnalyzeState();
        showProgressForJob(job);
      } else {
        state.busy = true;
        updateAnalyzeState();
        showProgressForJob(job);
        startAnalysisPoll(job.id);
      }
      history.replaceState(null, "", `#job=${job.id}`);
    } catch (error) {
      toast(error.message);
      resetToIngest();
    }
  }

  function prepareResult(job) {
    state.job = job;
    state.meta = {
      width: job.source.width,
      height: job.source.height,
      duration: job.source.duration,
      has_audio: job.source.has_audio,
    };
    state.fileName = job.source.name;
    state.target = 30;
    state.overrideHook = null;
    state.editMode = false;
    state.edited = false;
    state.momentsExpanded = false;
    state.trim = null;
    state.timelineScroll = 0;
    state.sort = "best";
    state.visible = 96;
    state.busy = false;
    dom.hookLab.hidden = true;
    dom.hookLab.innerHTML = "";
    dom.transcriptPanel.hidden = true;
    dom.transcriptPanel.innerHTML = "";
    dom.momentsFull.hidden = true;
    dom.momentsExpand.textContent = "Expand";
    state.plan = job.analysis.plans[String(state.target)];
    $$("#target-tabs button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.target) === state.target);
    });
    $$("#sort-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.sort === state.sort);
    });
    updateAnalyzeState();
    showView("result");
    renderResult();
    loadAudioEngines();
    loadAudioMoods();
    loadTranslateCheck();
    loadHistory();
    history.replaceState(null, "", `#job=${job.id}`);
    document.title = `${fileStem(job.source.name)} · VibeCut`;
    const active = Object.values(job.renders || {}).some(
      (record) => record && (record.status === "queued" || record.status === "rendering" || record.status === "cancelling"),
    );
    if (active) startRenderPoll(job.id);
  }

  function mergeScene(scene) {
    if (!state.job?.analysis?.scenes || !scene) return;
    const index = state.job.analysis.scenes.findIndex((item) => item.id === scene.id);
    if (index >= 0) state.job.analysis.scenes[index] = { ...state.job.analysis.scenes[index], ...scene };
  }

  function renderResult() {
    const job = state.job;
    const analysis = job.analysis;
    dom.resultTitle.textContent = fileStem(job.source.name);
    dom.resultTitle.title = job.source.name;
    const engine = [
      analysis.engine?.vision ? "vision" : "center crop",
      analysis.engine?.whisper ? "whisper" : null,
    ].filter(Boolean).join(" + ");
    const deep = analysis.deep_count ?? analysis.scene_count;
    dom.resultMeta.textContent = `${fmtDuration(job.source.duration)} source · ${analysis.scene_count} scenes · ${deep} deep-read · ${analysis.elapsed.toFixed(1)}s analysis · ${engine}`;
    renderUsage();
    renderHook();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  function renderUsage() {
    if (!dom.usageReadout) return;
    const usage = state.job?.usage;
    const totals = usage?.totals;
    if (!totals) {
      dom.usageReadout.textContent = "";
      return;
    }
    const parts = [];
    if (totals.calls) parts.push(`${totals.calls} cloud call${totals.calls === 1 ? "" : "s"}`);
    if (totals.input_tokens || totals.output_tokens) {
      parts.push(`${Math.round((totals.input_tokens + totals.output_tokens) / 1000)}k tokens`);
    }
    if (totals.audio_seconds) parts.push(`${(totals.audio_seconds / 60).toFixed(1)} min STT`);
    if (totals.chars) parts.push(`${Math.round(totals.chars / 1000)}k TTS chars`);
    if (!parts.length) {
      dom.usageReadout.textContent = "";
      return;
    }
    parts.push(`~$${Number(totals.cost_usd || 0).toFixed(4)}`);
    dom.usageReadout.textContent = `usage · ${parts.join(" · ")}`;
  }

  async function loadUsage() {
    if (!state.job) return;
    try {
      const result = await api(`/api/jobs/${state.job.id}/usage`);
      state.job.usage = result;
      renderUsage();
    } catch (_) { /* usage is optional */ }
  }

  function renderHook() {
    const scene = currentHookScene();
    if (!scene) return;
    dom.hookImg.src = thumbUrl(scene);
    dom.hookImg.alt = `Hook at ${fmtTime(scene.start)}`;
    dom.hookImg.style.objectPosition = objectPosition(scene.crop);
    dom.hookTime.textContent = `${fmtTime(scene.start, 1)} – ${fmtTime(scene.end, 1)} · ${scene.dur.toFixed(1)}s`;
    dom.hookCopy.textContent = sceneLine(scene);
    dom.hookWhy.textContent = state.plan?.hook_why
      || `Picked as the opening: ${sceneLine(scene)}`;
    dom.transcriptToggle.hidden = !state.job?.analysis?.engine?.whisper;
    if (dom.transcriptToggle.hidden) {
      dom.transcriptPanel.hidden = true;
      dom.transcriptPanel.innerHTML = "";
    }
    dom.hookScores.innerHTML = [
      ["Hook", scene.hook],
      ["Visual", scene.visual_score],
      ["Motion", scene.motion_score],
      ["Audio", scene.audio_score],
      ["Text", scene.text_score],
    ].map(([label, value]) => scoreItem(label, value)).join("");
    dom.hookTags.innerHTML = tagsHtml(scene);
    dom.hookCrop.textContent = cropLabel(scene);
  }

  function renderPlan() {
    const plan = state.plan;
    if (!plan) return;
    const scroll = Number(state.timelineScroll) || 0;
    dom.planTotal.textContent = `${plan.total.toFixed(1)}s cut · ${plan.clip_count} beats`;
    dom.planBadge.textContent = plan.auto ? "auto hook" : "custom hook";
    dom.planBadge.classList.toggle("custom", !plan.auto);
    dom.resetHook.hidden = state.overrideHook === null;
    dom.editCut.textContent = state.editMode ? "Editing…" : "Edit cut";
    dom.editBar.hidden = !state.editMode;
    dom.planWhy.textContent = [
      plan.hook_why ? `Hook: ${plan.hook_why}` : "",
      plan.payoff_why ? `Payoff: ${plan.payoff_why}` : "",
    ].filter(Boolean).join(" ");
    if (state.editIndex !== null) {
      state.editIndex = Math.max(0, Math.min(plan.clips.length - 1, state.editIndex));
    }
    dom.timeline.innerHTML = plan.clips.map((clip, index) => {
      const scene = sceneById(clip.scene);
      if (!scene) return "";
      const why = clip.why || sceneNote(scene);
      const tools = state.editMode
        ? `<span class="clip-tools">
             <button data-edit="up" data-index="${index}" title="Move earlier">↑</button>
             <button data-edit="down" data-index="${index}" title="Move later">↓</button>
             <button data-edit="shorter" data-index="${index}" title="Trim 0.25s">−</button>
             <button data-edit="longer" data-index="${index}" title="Extend 0.25s">+</button>
             <button data-edit="remove" data-index="${index}" title="Remove">✕</button>
           </span>`
        : "";
      return `
        <div class="clip ${clip.role === "hook" ? "hook" : ""} ${clip.role === "payoff" ? "payoff" : ""} ${state.editMode ? "editing" : ""} ${state.editIndex === index ? "selected" : ""}"
          data-scene="${scene.id}" data-index="${index}" draggable="true" style="flex:0 0 ${clipWidth(clip)}"
          title="${esc(`${clip.role}: ${why}`)}">
          <img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(scene.crop)}">
          <span class="clip-role">${esc(clip.role)}</span>
          <span class="clip-time">${clip.dur.toFixed(1)}s</span>
          <span class="trim-handle start" data-trim="start" data-index="${index}" title="Drag to trim start"></span>
          <span class="trim-handle end" data-trim="end" data-index="${index}" title="Drag to trim end"></span>
          ${tools}
        </div>`;
    }).join("");
    dom.timeline.scrollLeft = scroll;
    renderVariants();
    renderMixer();
  }

  function clipWidth(clip) {
    const dur = Number(clip?.dur) || 1;
    return `${Math.max(54, Math.min(150, 46 + dur * 10))}px`;
  }

  function renderVariants() {
    const variants = state.job?.variants || [];
    dom.variantList.innerHTML = variants.map((variant) => `
      <span class="variant-chip">
        <button data-variant-load="${esc(variant.id)}" title="Load this cut">${esc(variant.name)} · ${Number(variant.total || 0).toFixed(1)}s</button>
        <button data-variant-delete="${esc(variant.id)}" title="Delete variant">✕</button>
      </span>`).join("");
  }

  const MIXER_MIN_DB = -24;
  const MIXER_MAX_DB = 6;

  function automationPoints() {
    const mixer = state.mixer;
    if (!mixer.ready) return null;
    const changed = [...mixer.voice, ...mixer.bed]
      .some((point) => Math.abs(Number(point.db) || 0) > 0.01);
    if (!changed) return null;
    return {
      voice: mixer.voice.map((point) => [round2(point.t), round2(point.db)]),
      music: mixer.bed.map((point) => [round2(point.t), round2(point.db)]),
    };
  }

  function round2(value) {
    return Math.round((Number(value) || 0) * 100) / 100;
  }

  function defaultAutomation() {
    return { voice: [], bed: [] };
  }

  function renderMixer() {
    if (!dom.mixerPanel) return;
    loadMixer();
  }

  async function loadMixer() {
    const plan = state.plan;
    if (!plan || state.audio.mode === "keep") {
      state.mixer.ready = false;
      dom.mixerPanel.hidden = true;
      return;
    }
    try {
      const result = await api(
        `/api/jobs/${state.job.id}/mixer?target=${state.target}`
        + `&order=${encodeURIComponent(state.order)}`
        + (state.overrideHook !== null ? `&hook_scene=${state.overrideHook}` : ""),
      );
      const keepVoice = state.mixer.ready && state.mixer.voice.length ? state.mixer.voice : null;
      const keepBed = state.mixer.ready && state.mixer.bed.length ? state.mixer.bed : null;
      state.mixer = {
        ready: true,
        total: result.total || 0,
        clips: result.clips || [],
        original: result.envelopes?.original || [],
        music: result.envelopes?.music || [],
        voice: keepVoice || [],
        bed: keepBed || [],
        selected: null,
      };
      dom.mixerPanel.hidden = false;
      drawMixer();
    } catch (error) {
      dom.mixerPanel.hidden = true;
      state.mixer.ready = false;
    }
  }

  function formatGain(db) {
    const value = Number(db) || 0;
    const percent = Math.round(Math.pow(10, value / 20) * 100);
    const sign = value >= 0 ? "+" : "";
    return `${percent}% · ${sign}${value.toFixed(1)} dB`;
  }

  function lanePoints(lane) {
    return state.mixer[lane] || [];
  }

  function anchorsFor(points) {
    const total = state.mixer.total;
    const pts = points.map((point) => ({ ...point })).sort((a, b) => a.t - b.t);
    if (!pts.length) return [{ t: 0, db: 0 }, { t: total, db: 0 }];
    if (pts[0].t > 0.05) pts.unshift({ t: 0, db: 0 });
    if (Math.abs(pts[pts.length - 1].t - total) > 0.05) pts.push({ t: total, db: 0 });
    return pts;
  }

  function sampleCurve(points) {
    const layout = mixerLayout();
    const anchors = anchorsFor(points);
    const samples = [];
    for (let index = 0; index < anchors.length - 1; index += 1) {
      const a = anchors[index];
      const b = anchors[index + 1];
      const spanPx = Math.abs(timeToX(b.t, layout) - timeToX(a.t, layout));
      const steps = Math.max(2, Math.min(80, Math.ceil(spanPx / 5)));
      for (let step = 0; step < steps; step += 1) {
        const u = step / steps;
        const eased = (1 - Math.cos(Math.PI * u)) / 2;
        samples.push({ t: a.t + (b.t - a.t) * u, db: a.db + (b.db - a.db) * eased });
      }
    }
    const last = anchors[anchors.length - 1];
    samples.push({ t: last.t, db: last.db });
    return samples;
  }

  function mixerLayout() {
    const canvas = dom.mixerCanvas;
    const width = canvas.clientWidth || 720;
    const height = canvas.clientHeight || 220;
    return {
      width,
      height,
      padL: 6,
      padR: 6,
      rulerH: 18,
      laneH: 82,
      gap: 10,
      top: 24,
      get musicTop() { return this.rulerH + 6; },
      get voiceTop() { return this.rulerH + 6 + this.laneH + this.gap; },
    };
  }

  function timeToX(t, layout) {
    const span = Math.max(0.001, state.mixer.total);
    const usable = layout.width - layout.padL - layout.padR;
    return layout.padL + (Math.max(0, Math.min(span, t)) / span) * usable;
  }

  function xToTime(x, layout) {
    const usable = layout.width - layout.padL - layout.padR;
    return ((x - layout.padL) / usable) * state.mixer.total;
  }

  function dbToY(db, laneTop, laneH) {
    const value = Math.max(MIXER_MIN_DB, Math.min(MIXER_MAX_DB, Number(db) || 0));
    return laneTop + ((MIXER_MAX_DB - value) / (MIXER_MAX_DB - MIXER_MIN_DB)) * laneH;
  }

  function yToDb(y, laneTop, laneH) {
    const ratio = (y - laneTop) / laneH;
    const value = MIXER_MAX_DB - ratio * (MIXER_MAX_DB - MIXER_MIN_DB);
    return Math.round(Math.max(MIXER_MIN_DB, Math.min(MIXER_MAX_DB, value)) * 10) / 10;
  }

  function drawEnvelope(ctx, lane, laneTop, laneH, color) {
    const points = lanePoints(lane);
    const layout = mixerLayout();
    const curve = sampleCurve(points);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    curve.forEach((point, index) => {
      const x = timeToX(point.t, layout);
      const y = dbToY(point.db, laneTop, laneH);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    points.forEach((point, index) => {
      const x = timeToX(point.t, layout);
      const y = dbToY(point.db, laneTop, laneH);
      const selected = state.mixer.selected
        && state.mixer.selected.lane === lane
        && state.mixer.selected.index === index;
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.arc(x, y, selected ? 6 : 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = selected ? "#fff" : "rgba(10,10,11,0.9)";
      ctx.lineWidth = selected ? 2 : 1.5;
      ctx.stroke();
    });
  }

  function drawWave(ctx, envelope, laneTop, laneH, color) {
    if (!envelope || !envelope.length) return;
    const layout = mixerLayout();
    const mid = laneTop + laneH / 2;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(timeToX(envelope[0][0], layout), mid);
    envelope.forEach(([t, db]) => {
      const norm = Math.max(0, Math.min(1, (Number(db) + 40) / 40));
      ctx.lineTo(timeToX(t, layout), mid - norm * (laneH * 0.42));
    });
    for (let index = envelope.length - 1; index >= 0; index -= 1) {
      const [t, db] = envelope[index];
      const norm = Math.max(0, Math.min(1, (Number(db) + 40) / 40));
      ctx.lineTo(timeToX(t, layout), mid + norm * (laneH * 0.42));
    }
    ctx.closePath();
    ctx.fill();
  }

  function drawMixer() {
    const canvas = dom.mixerCanvas;
    if (!canvas || !state.mixer.ready) return;
    const ratio = window.devicePixelRatio || 1;
    const layout = mixerLayout();
    canvas.width = layout.width * ratio;
    canvas.height = layout.height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, layout.width, layout.height);

    let offset = 0;
    state.mixer.clips.forEach((clip, index) => {
      const x0 = timeToX(offset, layout);
      const x1 = timeToX(offset + (Number(clip.dur) || 0), layout);
      ctx.fillStyle = index % 2 ? "rgba(255,255,255,0.022)" : "rgba(255,255,255,0.045)";
      ctx.fillRect(x0, layout.rulerH, x1 - x0, layout.height - layout.rulerH);
      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.beginPath();
      ctx.moveTo(x0, layout.rulerH);
      ctx.lineTo(x0, layout.height);
      ctx.stroke();
      const label = `${clip.role === "hook" ? "HOOK" : clip.role === "payoff" ? "PAYOFF" : "beat"} ${clip.label || ""}`;
      ctx.fillStyle = clip.role === "hook" ? "#e8a266" : "rgba(255,255,255,0.42)";
      ctx.font = "9px ui-monospace, monospace";
      ctx.fillText(label, x0 + 4, layout.rulerH + 11);
      offset += Number(clip.dur) || 0;
    });

    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.font = "9px ui-monospace, monospace";
    const step = state.mixer.total > 40 ? 5 : state.mixer.total > 15 ? 2 : 1;
    for (let t = 0; t <= state.mixer.total + 0.001; t += step) {
      const x = timeToX(t, layout);
      ctx.fillRect(x, layout.rulerH - 4, 1, 4);
      ctx.fillText(`${t}s`, x + 3, layout.rulerH - 4);
    }

    [6, 0, -6, -12, -18, -24].forEach((db) => {
      [layout.musicTop, layout.voiceTop].forEach((laneTop) => {
        const y = dbToY(db, laneTop, layout.laneH);
        ctx.strokeStyle = db === 0 ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.06)";
        ctx.beginPath();
        ctx.moveTo(layout.padL, y);
        ctx.lineTo(layout.width - layout.padR, y);
        ctx.stroke();
      });
      const y = dbToY(db, layout.voiceTop, layout.laneH);
      ctx.fillStyle = "rgba(255,255,255,0.24)";
      ctx.font = "8.5px ui-monospace, monospace";
      ctx.fillText(`${Math.round(Math.pow(10, db / 20) * 100)}%`, layout.width - layout.padR - 32, y - 2);
    });

    ctx.fillStyle = "rgba(255,255,255,0.5)";
    ctx.font = "9px ui-monospace, monospace";
    ctx.fillText("MUSIC", layout.padL + 2, layout.musicTop - 4);
    ctx.fillText("VOICE", layout.padL + 2, layout.voiceTop - 4);

    drawWave(ctx, state.mixer.original, layout.musicTop, layout.laneH, "rgba(255,255,255,0.075)");
    drawWave(ctx, state.mixer.original, layout.voiceTop, layout.laneH, "rgba(255,255,255,0.075)");
    drawWave(ctx, state.mixer.music, layout.musicTop, layout.laneH, "rgba(120,170,255,0.18)");

    drawEnvelope(ctx, "bed", layout.musicTop, layout.laneH, "#e8a266");
    drawEnvelope(ctx, "voice", layout.voiceTop, layout.laneH, "#8fd18a");

    if (!state.mixer.bed.length && !state.mixer.voice.length) {
      ctx.fillStyle = "rgba(255,255,255,0.28)";
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("click a lane to add the first node · drag it anywhere", layout.padL + 90, layout.height - 10);
    }
  }

  function mixerPointer(event) {
    const canvas = dom.mixerCanvas;
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function laneAtY(y) {
    const layout = mixerLayout();
    if (y >= layout.voiceTop && y <= layout.voiceTop + layout.laneH) return "voice";
    if (y >= layout.musicTop && y <= layout.musicTop + layout.laneH) return "bed";
    return null;
  }

  function hitNode(lane, x, y) {
    const layout = mixerLayout();
    const laneTop = lane === "voice" ? layout.voiceTop : layout.musicTop;
    let best = null;
    let bestDistance = 11;
    lanePoints(lane).forEach((point, index) => {
      const distance = Math.hypot(
        timeToX(point.t, layout) - x,
        dbToY(point.db, laneTop, layout.laneH) - y,
      );
      if (distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    });
    return best;
  }

  function showPoint(lane, point) {
    const name = lane === "voice" ? "voice" : "music";
    dom.mixerReadout.textContent = `${name} ${point.t.toFixed(1)}s · ${formatGain(point.db)}`;
  }

  function addNode(lane, t, db) {
    const points = lanePoints(lane);
    points.push({ t: round2(t), db: Math.round(db * 10) / 10 });
    points.sort((a, b) => a.t - b.t);
    const index = points.findIndex((point) => point.t === round2(t) && point.db === Math.round(db * 10) / 10);
    state.mixer.selected = { lane, index: index >= 0 ? index : 0 };
    return state.mixer.selected.index;
  }

  function bindMixer() {
    if (!dom.mixerCanvas) return;
    let dragging = null;
    dom.mixerCanvas.addEventListener("pointerdown", (event) => {
      if (!state.mixer.ready) return;
      const { x, y } = mixerPointer(event);
      const layout = mixerLayout();
      const lane = laneAtY(y);
      if (!lane) {
        state.mixer.selected = null;
        drawMixer();
        return;
      }
      const hit = hitNode(lane, x, y);
      const laneTop = lane === "voice" ? layout.voiceTop : layout.musicTop;
      if (hit !== null) {
        state.mixer.selected = { lane, index: hit };
        dragging = { lane, index: hit };
      } else {
        const t = Math.max(0, Math.min(state.mixer.total, xToTime(x, layout)));
        const index = addNode(lane, t, yToDb(y, laneTop, layout.laneH));
        dragging = { lane, index };
      }
      dom.mixerCanvas.setPointerCapture(event.pointerId);
      showPoint(lane, state.mixer[lane][dragging.index]);
      drawMixer();
    });
    dom.mixerCanvas.addEventListener("pointermove", (event) => {
      if (!state.mixer.ready) return;
      const { x, y } = mixerPointer(event);
      const layout = mixerLayout();
      if (dragging) {
        const laneTop = dragging.lane === "voice" ? layout.voiceTop : layout.musicTop;
        const points = lanePoints(dragging.lane);
        const point = points[dragging.index];
        const previous = points[dragging.index - 1];
        const next = points[dragging.index + 1];
        let t = xToTime(x, layout);
        t = Math.max(0, Math.min(state.mixer.total, t));
        if (previous) t = Math.max(previous.t + 0.06, t);
        if (next) t = Math.min(next.t - 0.06, t);
        point.t = round2(t);
        point.db = yToDb(y, laneTop, layout.laneH);
        showPoint(dragging.lane, point);
        drawMixer();
        updateRenderPanel();
        return;
      }
      const lane = laneAtY(y);
      if (!lane) {
        dom.mixerReadout.textContent = "";
        return;
      }
      const hit = hitNode(lane, x, y);
      if (hit === null) {
        const t = xToTime(x, layout);
        dom.mixerReadout.textContent = `click at ${t.toFixed(1)}s to add a node`;
        return;
      }
      showPoint(lane, state.mixer[lane][hit]);
    });
    dom.mixerCanvas.addEventListener("pointerup", () => { dragging = null; });
    dom.mixerCanvas.addEventListener("dblclick", (event) => {
      if (!state.mixer.ready) return;
      const { x, y } = mixerPointer(event);
      const lane = laneAtY(y);
      if (!lane) return;
      const hit = hitNode(lane, x, y);
      if (hit === null) return;
      state.mixer[lane].splice(hit, 1);
      state.mixer.selected = null;
      dom.mixerReadout.textContent = "";
      drawMixer();
      updateRenderPanel();
    });
    dom.mixerReset.addEventListener("click", () => {
      state.mixer.voice = [];
      state.mixer.bed = [];
      state.mixer.selected = null;
      drawMixer();
      updateRenderPanel();
    });
    dom.mixerSmooth.addEventListener("click", () => {
      ["voice", "bed"].forEach((lane) => {
        state.mixer[lane] = state.mixer[lane].map((point) => ({ t: point.t, db: 0 }));
      });
      drawMixer();
      updateRenderPanel();
    });
    window.addEventListener("resize", () => drawMixer());
  }

  function syncEditedPlan() {
    if (!state.plan) return;
    const clips = state.plan.clips;
    const total = Math.round(clips.reduce((sum, clip) => sum + clip.dur, 0) * 1000) / 1000;
    state.plan = {
      ...state.plan,
      clips,
      total,
      clip_count: clips.length,
      hook_scene: clips.length ? clips[0].scene : state.plan.hook_scene,
      auto: false,
      note: "Manual edit",
    };
    state.edited = true;
    state.scriptId = null;
  }

  function editClip(index, action) {
    if (!state.plan || !state.plan.clips[index]) return;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    const clip = clips[index];
    if (action === "up" && (index <= 1 || index >= clips.length - 1)) {
      toast("Hook and payoff stay first and last.");
      return;
    }
    if (action === "down" && (index <= 0 || index >= clips.length - 2)) {
      toast("Hook and payoff stay first and last.");
      return;
    }
    if (action === "remove" && (index <= 0 || index >= clips.length - 1)) {
      toast("Hook and payoff stay first and last.");
      return;
    }
    if (action === "up" && index > 1) {
      [clips[index - 1], clips[index]] = [clips[index], clips[index - 1]];
      state.editIndex = index - 1;
    } else if (action === "down" && index < clips.length - 1) {
      [clips[index + 1], clips[index]] = [clips[index], clips[index + 1]];
      state.editIndex = index + 1;
    } else if (action === "remove") {
      if (clips.length <= 2) {
        toast("Hook and payoff stay first and last.");
        return;
      }
      clips.splice(index, 1);
      state.editIndex = Math.max(0, Math.min(clips.length - 1, index));
    } else if (action === "shorter" || action === "longer") {
      const scene = sceneById(clip.scene);
      const step = 0.25;
      const room = scene ? scene.end - clip.start : clip.dur;
      const wanted = Math.max(0.5, Math.min(room, clip.dur + (action === "longer" ? step : -step)));
      const dur = Math.round(wanted * 100) / 100;
      if (Math.abs(dur - clip.dur) < 0.001) return;
      clip.end = Math.round(Math.min(scene?.end ?? clip.end, clip.start + dur) * 1000) / 1000;
      clip.dur = Math.round((clip.end - clip.start) * 1000) / 1000;
    }
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  function normalizePlanRoles(clips) {
    clips.forEach((clip, index) => {
      clip.role = index === 0 ? "hook" : index === clips.length - 1 ? "payoff" : "beat";
    });
  }

  function addSceneToPlan(sceneId, at = null) {
    if (!state.plan) return false;
    const scene = sceneById(sceneId);
    if (!scene) return false;
    if (scene.deep === false) {
      toast("Quick scan · deep-read this moment before adding it.");
      openDrawer(scene.id);
      return false;
    }
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    if (clips.some((clip) => clip.scene === scene.id)) {
      toast("Moment already in Smart Cut.");
      return false;
    }
    const room = Math.max(0.6, scene.end - scene.start);
    const dur = Math.min(4, room);
    let index = at === null ? clips.length : Math.max(1, at);
    if (clips.length && clips[clips.length - 1].role === "payoff" && index >= clips.length - 1) {
      index = clips.length - 1;
    }
    index = Math.max(1, Math.min(index, clips.length));
    clips.splice(index, 0, {
      scene: scene.id,
      role: "beat",
      start: scene.start,
      end: Math.min(scene.end, scene.start + dur),
      dur,
      why: sceneNote(scene),
    });
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    state.edited = true;
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    toast("Moment added to Smart Cut.");
    return true;
  }

  function moveClip(from, to) {
    if (!state.plan) return;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    if (from <= 0 || from >= clips.length - 1) {
      toast("Hook and payoff stay first and last.");
      return;
    }
    const target = Math.max(1, Math.min(clips.length - 2, to));
    if (from === target) return;
    const [clip] = clips.splice(from, 1);
    // Drop-on-target means "place after this beat" for a later move, and
    // "place before this beat" for an earlier move. Inserting at target in
    // the shortened array handles both directions without a no-op.
    const index = Math.max(1, Math.min(target, clips.length - 1));
    clips.splice(index, 0, clip);
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    state.edited = true;
    state.editIndex = null;
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  function removeClipAt(index) {
    if (!state.plan) return;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    if (index <= 0 || index >= clips.length - 1 || clips.length <= 2) {
      toast("Hook and payoff stay first and last.");
      return;
    }
    clips.splice(index, 1);
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    state.edited = true;
    state.editIndex = null;
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  function toggleEdit(force) {
    if (!state.plan) return;
    state.editMode = typeof force === "boolean" ? force : !state.editMode;
    state.editIndex = state.editMode ? (state.editIndex ?? 0) : null;
    renderPlan();
  }

  async function saveVariant() {
    if (!state.job || !state.plan || !state.edited) {
      toast("Edit the cut first.");
      return;
    }
    const name = (dom.variantName.value || "").trim() || `${state.target}s edit`;
    try {
      const result = await api(`/api/jobs/${state.job.id}/variants`, {
        method: "POST",
        body: JSON.stringify({
          name,
          target: state.target,
          hook_scene: state.plan.hook_scene,
          clips: state.plan.clips,
        }),
      });
      state.job.variants = result.variants;
      dom.variantName.value = "";
      renderVariants();
      toast("Variant saved.");
    } catch (error) {
      toast(error.message);
    }
  }

  async function loadVariant(variantId) {
    const variant = (state.job?.variants || []).find((item) => item.id === variantId);
    if (!variant) return;
    const clips = variant.clips.map((clip) => ({ ...clip }));
    normalizePlanRoles(clips);
    const target = [15, 30, 60].includes(Number(variant.target)) ? Number(variant.target) : state.target;
    state.target = target;
    $$("#target-tabs button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.target) === target);
    });
    const hookScene = variant.hook_scene ?? clips[0]?.scene ?? null;
    state.overrideHook = hookScene;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    state.timelineScroll = 0;
    state.plan = {
      target,
      total: Number(variant.total) || Math.round(clips.reduce((sum, clip) => sum + Number(clip.dur || 0), 0) * 1000) / 1000,
      hook_scene: hookScene,
      auto: false,
      clip_count: clips.length,
      clips,
      note: `Variant · ${variant.name}`,
    };
    state.edited = true;
    state.editMode = true;
    renderHook();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    loadAudioMoods();
    loadAudioScript();
    toast(`Loaded “${variant.name}”.`);
  }

  async function deleteVariant(variantId) {
    if (!state.job) return;
    try {
      const result = await api(`/api/jobs/${state.job.id}/variants/${variantId}`, { method: "DELETE" });
      state.job.variants = result.variants;
      renderVariants();
      toast("Variant removed.");
    } catch (error) {
      toast(error.message);
    }
  }

  async function toggleHookLab() {
    if (!state.job) return;
    const hidden = dom.hookLab.hidden;
    dom.hookLab.hidden = !hidden;
    if (!hidden) return;
    dom.hookLab.innerHTML = `<p class="hint">Loading hook candidates…</p>`;
    try {
      const result = await api(`/api/jobs/${state.job.id}/hooks?target=${state.target}&limit=8`);
      dom.hookLab.innerHTML = (result.hooks || []).map((hook) => `
        <button class="lab-card" data-lab-hook="${hook.scene}">
          <img src="${esc(withToken(hook.thumb_url))}" alt="" loading="lazy">
          <span class="lab-copy">
            <b>${Math.round(hook.hook)} hook</b>
            <small>${esc(fmtTime(hook.start, 1))} · ${hook.dur.toFixed(1)}s · ${hook.clip_count} beats · ${hook.plan_total.toFixed(0)}s cut</small>
            <small>${esc((hook.why || hook.ocr || hook.speech || "no text").slice(0, 120))}</small>
          </span>
        </button>`).join("");
    } catch (error) {
      dom.hookLab.innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    }
  }

  async function toggleTranscript() {
    if (!state.job) return;
    const hidden = dom.transcriptPanel.hidden;
    dom.transcriptPanel.hidden = !hidden;
    if (!hidden) return;
    dom.transcriptPanel.innerHTML = `<p class="hint">Loading transcript…</p>`;
    try {
      const result = await api(`/api/jobs/${state.job.id}/transcript`);
      const segments = result.segments || [];
      if (!segments.length) {
        dom.transcriptPanel.innerHTML = `<p class="hint">${esc(result.text || result.note || "No transcript kept for this job.")}</p>`;
        return;
      }
      dom.transcriptPanel.innerHTML = `
        <div class="transcript-head">
          <span class="label">Transcript · ${esc(result.language || "auto")} · ${segments.length} lines</span>
          <input id="transcript-search" class="variant-name" placeholder="Search transcript">
        </div>
        <div class="transcript-list">
          ${segments.map((segment) => `
            <button class="transcript-row" data-transcript-time="${segment.start}" data-transcript-text="${esc(segment.text)}">
              <span class="transcript-time">${esc(fmtTime(segment.start, 1))}</span>
              <span class="transcript-text">${esc(segment.text)}</span>
            </button>`).join("")}
        </div>`;
      const search = dom.transcriptPanel.querySelector("#transcript-search");
      search?.addEventListener("input", () => {
        const query = search.value.trim().toLowerCase();
        dom.transcriptPanel.querySelectorAll(".transcript-row").forEach((row) => {
          row.hidden = query.length > 0 && !row.textContent.toLowerCase().includes(query);
        });
      });
    } catch (error) {
      dom.transcriptPanel.innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    }
  }

  function renderScenes() {
    if (!state.job) return;
    const scenes = [...state.job.analysis.scenes];
    if (state.sort === "best") {
      scenes.sort((a, b) => b.hook - a.hook || a.start - b.start);
    } else {
      scenes.sort((a, b) => a.start - b.start);
    }
    const roles = new Map((state.plan?.clips || []).map((clip) => [clip.scene, clip.role]));
    const hookId = currentHookId();
    const clips = state.plan?.clips || [];
    const payoffId = clips.length ? clips[clips.length - 1].scene : null;
    const visible = scenes.slice(0, state.visible);
    const deep = state.job.analysis.deep_count ?? scenes.length;
    dom.sceneCount.textContent = `${scenes.length.toLocaleString()} scenes · ${deep.toLocaleString()} deep · showing ${visible.length}`;
    dom.sceneGrid.innerHTML = visible.map((scene) => {
      const role = roles.get(scene.id) || "";
      const tags = [...(scene.tags || []), ...(scene.deep === false ? ["quick"] : [])].join(" · ");
      const still = scene.deep === false
        ? `<span class="scene-placeholder"><span>quick</span></span>`
        : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(scene.crop)}">`;
      return `
        <button class="scene-card ${role ? "in-plan" : ""} ${scene.id === hookId ? "is-hook" : ""} ${scene.id === payoffId ? "is-payoff" : ""}"
          data-scene="${scene.id}" draggable="true" title="${esc(scene.ocr || scene.speech || `Scene ${scene.id + 1}`)}">
          ${still}
          <span class="scene-top"><span>${esc(fmtTime(scene.start))}</span><span class="score">${Math.round(scene.hook)}</span></span>
          <span class="scene-bottom"><span class="scene-role">${esc(role)}</span><span class="scene-tags">${esc(tags)}</span></span>
        </button>`;
    }).join("");
    dom.loadMore.hidden = visible.length >= scenes.length;
    renderMomentsRail();
  }

  function renderMomentsRail() {
    if (!state.job || !dom.momentsRail) return;
    const clips = state.plan?.clips || [];
    const used = new Set(clips.map((clip) => clip.scene));
    const hookId = currentHookId();
    const payoffId = clips.length ? clips[clips.length - 1].scene : null;
    const scenes = [...state.job.analysis.scenes];
    if (state.sort === "best") {
      scenes.sort((a, b) => b.hook - a.hook || a.start - b.start);
    } else {
      scenes.sort((a, b) => a.start - b.start);
    }
    const pinned = new Set([hookId, payoffId].filter((id) => id !== null && id !== undefined));
    const railScenes = [];
    scenes.forEach((scene) => {
      if (pinned.has(scene.id)) railScenes.push(scene);
    });
    scenes.forEach((scene) => {
      if (!pinned.has(scene.id) && railScenes.length < 48) railScenes.push(scene);
    });
    dom.momentsScrub.max = Math.max(0, railScenes.length - 1);
    dom.momentsScrub.value = Math.min(Number(dom.momentsScrub.value) || 0, railScenes.length - 1);
    dom.momentsRail.innerHTML = railScenes.map((scene, index) => {
      const still = scene.deep === false
        ? `<span class="scene-placeholder"><span>quick</span></span>`
        : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(scene.crop)}">`;
      return `
        <button class="moment-card ${used.has(scene.id) ? "in-plan" : ""} ${scene.id === hookId ? "is-hook" : ""} ${scene.id === payoffId ? "is-payoff" : ""}"
          data-moment-scene="${scene.id}" data-rail-index="${index}" draggable="true"
          title="Drag into Smart Cut · ${esc(scene.ocr || scene.speech || `Scene ${scene.id + 1}`)}">
          ${still}
          <span class="moment-time">${esc(fmtTime(scene.start))}</span>
        </button>`;
    }).join("");
    if (dom.momentsFull && !dom.momentsFull.hidden) {
      // Scene grid is rendered separately; expand state only controls visibility.
    }
  }

  function syncRailScrub() {
    if (!dom.momentsRail || !dom.momentsScrub) return;
    const cards = dom.momentsRail.querySelectorAll(".moment-card");
    if (!cards.length) return;
    const first = cards[0];
    const styles = getComputedStyle(dom.momentsRail);
    const gap = parseFloat(styles.columnGap || styles.gap) || 8;
    const width = first.getBoundingClientRect().width + gap;
    if (!width) return;
    const index = clamp(Math.round(dom.momentsRail.scrollLeft / width), 0, cards.length - 1);
    dom.momentsScrub.value = String(index);
  }

  // ---------------------------------------------------------------- plans + targets

  async function setTarget(target) {
    if (state.target === target) return;
    state.target = target;
    state.edited = false;
    state.editMode = false;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    state.timelineScroll = 0;
    $$("#target-tabs button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.target) === target);
    });
    try {
      await refreshPlan();
      loadAudioMoods();
      loadAudioScript();
      updateRenderPanel();
    } catch (error) {
      toast(error.message);
    }
  }

  async function refreshPlan() {
    if (!state.job) return;
    if (state.overrideHook === null && state.order !== "arc") {
      state.plan = state.job.analysis.plans[String(state.target)];
    } else {
      const result = await api(`/api/jobs/${state.job.id}/plan`, {
        method: "POST",
        body: JSON.stringify({
          target: state.target,
          hook_scene: state.overrideHook,
          order: state.order,
        }),
      });
      state.plan = result.plan;
      mergeScene(result.scene);
    }
    renderHook();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  function setSort(sort) {
    state.sort = sort;
    state.visible = 96;
    $$("#sort-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.sort === sort);
    });
    renderScenes();
  }

  async function resetHook() {
    state.overrideHook = null;
    state.edited = false;
    state.editMode = false;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    try {
      await refreshPlan();
      toast("Auto hook restored.");
    } catch (error) {
      toast(error.message);
    }
  }

  async function useHook(sceneId) {
    if (!state.job) return;
    const previous = state.overrideHook;
    const scene = sceneById(sceneId);
    state.overrideHook = sceneId === state.job.analysis.hook_scene ? null : sceneId;
    state.edited = false;
    state.editMode = false;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    dom.hookLab.hidden = true;
    closeDrawer();
    try {
      await refreshPlan();
      loadAudioMoods();
      loadAudioScript();
      toast(state.overrideHook === null ? "Auto hook restored." : `Hook set to ${fmtTime(scene?.start || 0, 1)}.`);
      document.querySelector(".export-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      state.overrideHook = previous;
      await refreshPlan();
      toast(error.message);
    }
  }

  // ---------------------------------------------------------------- audio

  const AUDIO_LANGUAGES = [
    ["", "No translation (same language)"],
    ["en", "English"], ["vi", "Vietnamese"], ["zh", "Chinese"],
    ["ja", "Japanese"], ["ko", "Korean"], ["es", "Spanish"],
    ["fr", "French"], ["de", "German"], ["pt", "Portuguese"],
    ["it", "Italian"], ["ru", "Russian"], ["hi", "Hindi"],
    ["th", "Thai"], ["id", "Indonesian"], ["tr", "Turkish"],
    ["ar", "Arabic"], ["nl", "Dutch"], ["pl", "Polish"],
    ["sv", "Swedish"], ["da", "Danish"], ["no", "Norwegian"],
    ["fi", "Finnish"], ["uk", "Ukrainian"], ["cs", "Czech"],
  ];

  function canonicalAudio(value) {
    if (Array.isArray(value)) return `[${value.map(canonicalAudio).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value).sort()
        .map((key) => `${JSON.stringify(key)}:${canonicalAudio(value[key])}`)
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  function fnv1a(text) {
    let hash = 0x811c9dc5;
    const bytes = new TextEncoder().encode(text);
    for (const byte of bytes) {
      hash ^= byte;
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
  }

  function musicSourceMode() {
    const checked = document.querySelector('input[name="audio-music-source"]:checked');
    return checked?.value || state.audio.musicSource || "none";
  }

  function currentAudioPlan() {
    const audio = state.audio;
    if (!audio || audio.mode === "keep") return null;
    const uploadMode = audio.source === "upload" && ["bed", "voice", "full"].includes(audio.mode);
    const overrides = { ...(state.scriptOverrides || {}) };
    const hasOverrides = Object.keys(overrides).length > 0;
    const plan = { mode: audio.mode };
    if (state.scriptId) plan.script_id = state.scriptId;
    if (hasOverrides) plan.script_overrides = overrides;
    plan.translate = uploadMode ? {
      target: "", provider: "auto", mode: "literal", rewrite_provider: "auto",
    } : {
      target: audio.lang || "",
      provider: "auto",
      mode: audio.style || "smooth",
      rewrite_provider: "auto",
    };
    plan.beat_sync = !!audio.beatSync;
    const automation = automationPoints();
    if (automation) plan.automation = automation;
    plan.voice = audio.mode === "music"
      ? null
      : uploadMode
        ? {
          source: "upload",
          upload: audio.upload || "",
          gain_db: 0,
          ...(hasOverrides ? { script_overrides: overrides } : {}),
        }
        : {
          engine: audio.engine,
          voice: audio.voice || "",
          rate: Number(audio.rate) || 1,
          gain_db: 0,
          ...(hasOverrides ? { script_overrides: overrides } : {}),
        };
    const source = musicSourceMode();
    if (audio.mode === "bed" || audio.mode === "voice" || source === "none") {
      plan.music = { source: "none" };
    } else if (source === "own") {
      plan.music = audio.musicUpload
        ? {
          source: "upload",
          upload: audio.musicUpload,
          gain_db: Number(audio.gain) || -18,
          duck: !!audio.duck,
        }
        : {
          source: ["library", "cc0"].includes(audio.music) ? audio.music : "library",
          track: audio.track || "",
          gain_db: Number(audio.gain) || -18,
          duck: !!audio.duck,
        };
    } else {
      plan.music = {
        source: ["minimax-music", "lyria-clip"].includes(audio.music) ? audio.music : "minimax-music",
        prompt: audio.prompt || "auto",
        gain_db: Number(audio.gain) || -18,
        duck: !!audio.duck,
      };
      if (state.audioMoods.length) plan.music.moods = state.audioMoods;
    }
    return plan;
  }

  function currentAudioSignature() {
    const plan = currentAudioPlan();
    return plan ? fnv1a(canonicalAudio(plan)) : "";
  }

  function bindAudio() {
    const touch = () => {
      state.audio.mode = dom.audioMode.value;
      dom.audioModeTabs.querySelectorAll("[data-audio-mode]").forEach((button) => {
        button.classList.toggle("active", button.dataset.audioMode === state.audio.mode);
      });
      state.audio.source = dom.audioSourceUpload.checked ? "upload" : "generate";
      state.audio.lang = dom.audioLang.value;
      state.audio.provider = "auto";
      state.audio.style = dom.audioStyle.value || "smooth";
      state.audio.rewrite = "auto";
      state.audio.musicSource = musicSourceMode();
      state.audio.beatSync = dom.audioBeatSync.checked;
      state.audio.engine = dom.audioEngine.value;
      state.audio.voice = dom.audioVoice.value;
      state.audio.rate = Number(dom.audioRate.value) || 1;
      state.audio.music = dom.audioMusic.value;
      state.audio.track = dom.audioTrack.value;
      state.audio.prompt = dom.audioPrompt.value.trim();
      state.audio.gain = Number(dom.audioGain.value) || -18;
      state.audio.duck = dom.audioDuck.checked;
      syncAudioVisibility();
      updateRenderPanel();
      refreshAudioStatus();
      renderMixer();
    };
    ["change", "input"].forEach((event) => {
      dom.audioMode.addEventListener(event, () => {
        touch();
        loadAudioTracks();
        loadAudioMoods();
        loadAudioScript();
      });
      dom.audioMusic.addEventListener(event, () => {
        touch();
        loadAudioTracks();
      });
      dom.audioLang.addEventListener(event, () => {
        state.scriptOverrides = {};
        state.scriptId = null;
        state.lastScript = null;
        touch();
        loadTranslateCheck();
        loadAudioScript();
      });
      dom.audioProvider.addEventListener(event, () => {
        touch();
        loadAudioScript();
      });
      dom.audioStyle.addEventListener(event, () => {
        state.scriptOverrides = {};
        state.scriptId = null;
        state.lastScript = null;
        touch();
        loadAudioScript();
      });
      dom.audioRewrite.addEventListener(event, () => {
        touch();
        loadAudioScript();
      });
      dom.audioBeatSync.addEventListener(event, () => {
        touch();
        loadBpm();
      });
      dom.audioEngine.addEventListener(event, () => {
        touch();
        loadAudioVoices();
      });
      dom.audioVoice.addEventListener(event, touch);
      dom.audioRate.addEventListener(event, touch);
      dom.audioTrack.addEventListener(event, () => {
        if (state.audio.musicUpload) clearMusicUpload();
        touch();
      });
      dom.audioPrompt.addEventListener(event, touch);
      dom.audioGain.addEventListener(event, touch);
      dom.audioDuck.addEventListener(event, touch);
    });
    dom.audioModeTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-audio-mode]");
      if (!button) return;
      dom.audioMode.value = button.dataset.audioMode;
      dom.audioMode.dispatchEvent(new Event("change", { bubbles: true }));
    });
    dom.audioRewriteRun.addEventListener("click", () => {
      loadAudioScript({ run: true, forceTranslate: true });
    });
    document.querySelectorAll('input[name="audio-music-source"]').forEach((input) => {
      input.addEventListener("change", () => {
        state.audio.musicSource = musicSourceMode();
        syncMusicOptions();
        syncAudioVisibility();
        touch();
        loadAudioTracks();
      });
    });
    dom.audioPreview.addEventListener("click", previewVoice);
    dom.audioSourceGenerate.addEventListener("change", () => {
      setVoiceSource("generate");
      loadAudioScript();
    });
    dom.audioSourceUpload.addEventListener("change", () => {
      if (state.audio.upload) {
        setVoiceSource("upload");
        loadAudioScript();
        return;
      }
      openVoicePicker();
    });
    dom.audioUploadButton.addEventListener("click", () => openVoicePicker());
    dom.audioUpload.addEventListener("change", () => {
      const file = dom.audioUpload.files && dom.audioUpload.files[0];
      if (file) uploadVoice(file);
    });
    dom.audioUpload.addEventListener("cancel", () => {
      setVoiceSource(voicePickerPrevious);
      toast(voicePickerPrevious === "upload"
        ? "No new recording selected. Previous recording kept."
        : "No recording selected. Generate stays active.");
    });
    dom.audioMusicUploadButton.addEventListener("click", () => dom.audioMusicUpload.click());
    dom.audioMusicUpload.addEventListener("change", () => {
      const file = dom.audioMusicUpload.files && dom.audioMusicUpload.files[0];
      if (file) uploadMusic(file);
    });
    dom.audioMusicUploadClear.addEventListener("click", clearMusicUpload);
    syncAudioVisibility();
  }

  let voicePickerPrevious = "generate";

  function setVoiceSource(source) {
    state.audio.source = source;
    if (dom.audioSourceGenerate) dom.audioSourceGenerate.checked = source === "generate";
    if (dom.audioSourceUpload) dom.audioSourceUpload.checked = source === "upload";
    syncAudioVisibility();
    updateRenderPanel();
  }

  function openVoicePicker() {
    if (!state.job || !state.plan) return;
    voicePickerPrevious = state.audio.source === "upload" ? "upload" : "generate";
    dom.audioUpload.value = "";
    dom.audioUpload.click();
    const focusHandler = () => {
      window.removeEventListener("focus", focusHandler);
      setTimeout(() => {
        const picked = dom.audioUpload.files && dom.audioUpload.files.length;
        if (!picked && state.audio.source !== "upload") {
          setVoiceSource(voicePickerPrevious);
          toast(voicePickerPrevious === "upload"
            ? "No new recording selected. Previous recording kept."
            : "No recording selected. Generate stays active.");
        }
      }, 400);
    };
    window.addEventListener("focus", focusHandler, { once: true });
  }

  function clearMusicUpload() {
    state.audio.musicUpload = "";
    state.audio.musicUploadName = "";
    state.audio.musicUploadDuration = 0;
    if (dom.audioMusicUpload) dom.audioMusicUpload.value = "";
    syncAudioVisibility();
    dom.audioMusic.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function syncMusicOptions() {
    const source = musicSourceMode();
    const full = state.audioMusicOptions || [["none", "No music"]];
    const allowed = source === "own"
      ? new Set(["library", "cc0"])
      : source === "generate"
        ? new Set(["minimax-music", "lyria-clip"])
        : new Set(["none"]);
    const options = full.filter(([id]) => allowed.has(id));
    const current = state.audio.music;
    fillSelect(dom.audioMusic, options.length ? options : [["none", "No music"]]);
    const next = options.some(([id]) => id === current) ? current : (options[0]?.[0] || "none");
    dom.audioMusic.value = next;
    state.audio.music = next;
  }

  function syncAudioVisibility() {
    const mode = dom.audioMode.value;
    const voiceMode = ["bed", "voice", "full"].includes(mode);
    const upload = voiceMode && state.audio.source === "upload";
    const musicMode = ["music", "full"].includes(mode);
    const rewriteMode = voiceMode && !upload;
    dom.audioRewriteStep.hidden = !rewriteMode;
    dom.audioVoiceStep.hidden = !voiceMode;
    dom.audioMusicStep.hidden = !musicMode;
    dom.audioVoiceSource.hidden = !voiceMode;
    dom.audioVoiceGenerate.hidden = upload;
    dom.audioVoiceUpload.hidden = !upload;
    dom.audioUploadButton.hidden = !upload;
    dom.audioUploadName.hidden = !upload;
    dom.audioUploadName.textContent = upload && state.audio.upload
      ? `${state.audio.uploadName || "recording"} · ${Number(state.audio.uploadDuration || 0).toFixed(1)}s`
      : "Fit your recording to the cut length.";
    if (dom.audioPreview) dom.audioPreview.hidden = upload;
    syncMusicOptions();
    const source = musicSourceMode();
    const hasUpload = !!state.audio.musicUpload;
    dom.audioTrackField.hidden = source !== "own" || hasUpload;
    dom.audioTrack.disabled = hasUpload;
    dom.audioMusicUploadBox.hidden = source !== "own";
    dom.audioMusicUploadClear.hidden = !hasUpload;
    dom.audioMusicUploadName.textContent = source === "own" && hasUpload
      ? `${state.audio.musicUploadName || "music"} · ${Number(state.audio.musicUploadDuration || 0).toFixed(1)}s`
      : "Use your own music file.";
    dom.audioPromptField.hidden = source !== "generate";
    dom.audioGainField.hidden = source === "none";
    dom.audioDuckField.hidden = source === "none";
    dom.audioBeatSyncField.hidden = source === "none";
    const block = audioBlockReason();
    if (dom.audioMusicWarning) {
      dom.audioMusicWarning.hidden = !block;
      dom.audioMusicWarning.textContent = block;
    }
    if (state.job && state.plan) updateRenderPanel();
  }

  function audioBlockReason() {
    if (state.audio.mode === "music" && musicSourceMode() === "none") {
      return "Music mode needs a source. Choose Use my sound or Generate before rendering.";
    }
    return "";
  }

  async function uploadMusic(file) {
    if (!state.job || !state.plan) return;
    const form = new FormData();
    form.append("file", file);
    const headers = {};
    const token = tokenValue();
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      const response = await fetch(`/api/jobs/${state.job.id}/audio/music-upload`, {
        method: "POST", headers, body: form,
      });
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const result = await response.json();
      state.audio.musicUpload = result.path;
      state.audio.musicUploadName = result.name || file.name;
      state.audio.musicUploadDuration = Number(result.duration) || 0;
      state.audio.musicSource = "own";
      document.querySelector('input[name="audio-music-source"][value="own"]').checked = true;
      dom.audioMusicUpload.value = "";
      syncAudioVisibility();
      dom.audioMusic.dispatchEvent(new Event("change", { bubbles: true }));
      loadHistory();
      toast(`Music added: ${state.audio.musicUploadName}`);
    } catch (error) {
      loadHistory();
      toast(error.message);
    }
  }

  async function uploadVoice(file) {
    if (!state.job || !state.plan) return;
    const form = new FormData();
    form.append("file", file);
    const headers = {};
    const token = tokenValue();
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      const response = await fetch(`/api/jobs/${state.job.id}/audio/voice-upload`, {
        method: "POST", headers, body: form,
      });
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const result = await response.json();
      state.audio.upload = result.path;
      state.audio.uploadName = result.name || file.name;
      state.audio.uploadDuration = Number(result.duration) || 0;
      state.audio.source = "upload";
      dom.audioUpload.value = "";
      setVoiceSource("upload");
      loadHistory();
      toast(`Voice fitted source: ${state.audio.uploadName}`);
    } catch (error) {
      setVoiceSource(voicePickerPrevious || "generate");
      loadHistory();
      toast(error.message);
    }
  }

  function fillSelect(select, options) {
    select.innerHTML = options.map(([value, label]) => (
      `<option value="${esc(value)}">${esc(label)}</option>`
    )).join("");
  }

  function applyPreset() {
    const value = dom.presetSelect.value;
    state.preset = value;
    const presets = {
      tiktok: { aspect: "9:16", captions: true },
      reels: { aspect: "9:16", captions: true },
      shorts: { aspect: "9:16", captions: true },
      square: { aspect: "1:1", captions: true },
      landscape: { aspect: "16:9", captions: false },
    };
    const config = presets[value];
    if (!config) {
      updateRenderPanel();
      return;
    }
    state.aspect = config.aspect;
    state.captions = config.captions;
    dom.aspect.value = config.aspect;
    dom.captions.checked = config.captions;
    updateRenderPanel();
  }

  async function loadBpm() {
    if (!state.audio.beatSync) {
      dom.audioBpm.textContent = "";
      return;
    }
    const source = state.audio.music;
    if (source !== "library" && source !== "cc0" && source !== "generated") {
      dom.audioBpm.textContent = "pick a library track";
      return;
    }
    dom.audioBpm.textContent = "detecting…";
    try {
      const result = await api(
        `/api/audio/beats?source=${encodeURIComponent(source)}&track=${encodeURIComponent(state.audio.track || "")}`,
      );
      dom.audioBpm.textContent = `${result.bpm} BPM`;
    } catch (error) {
      dom.audioBpm.textContent = error.message.slice(0, 40);
    }
  }

  async function createReviewLink() {
    if (!state.job) return;
    try {
      const result = await api(
        `/api/jobs/${state.job.id}/share?target=${state.target}&aspect=${encodeURIComponent(state.aspect)}`,
        { method: "POST" },
      );
      const url = `${location.origin}${result.url}`;
      try {
        await navigator.clipboard.writeText(url);
        toast("Review link copied.");
      } catch (_) {
        window.prompt("Review link", url);
      }
    } catch (error) {
      toast(error.message);
    }
  }

  function exportCut(kind) {
    if (!state.job) return;
    const token = tokenValue();
    const url = `/api/jobs/${state.job.id}/export/${kind}?target=${state.target}`
      + `&order=${encodeURIComponent(state.order)}`
      + (state.overrideHook !== null ? `&hook_scene=${state.overrideHook}` : "")
      + (token ? `&token=${encodeURIComponent(token)}` : "");
    window.open(url, "_blank");
  }

  function clipsForHook(hookScene) {
    if (!state.plan) return [];
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    const scene = sceneById(hookScene);
    if (!scene) return clips;
    const index = clips.findIndex((clip) => clip.scene === hookScene);
    let hookClip;
    if (index >= 0) {
      hookClip = clips.splice(index, 1)[0];
    } else {
      const room = Math.max(0.6, scene.end - scene.start);
      const dur = Math.min(Number(clips[0]?.dur) || 3, room, 4);
      hookClip = {
        scene: hookScene,
        start: scene.start,
        end: Math.min(scene.end, scene.start + dur),
        dur,
        why: sceneNote(scene),
      };
      if (clips.length) clips[0] = hookClip;
      else clips.push(hookClip);
    }
    if (index >= 0) clips.unshift(hookClip);
    hookClip.role = "hook";
    normalizePlanRoles(clips);
    return clips;
  }

  async function abHooks() {
    if (!state.job || !state.plan) return;
    const block = audioBlockReason();
    if (block) {
      toast(block);
      updateRenderPanel();
      return;
    }
    dom.renderAb.disabled = true;
    try {
      let records = [];
      const errors = [];
      if (state.edited) {
        const hooks = await api(`/api/jobs/${state.job.id}/hooks?target=${state.target}&limit=3`);
        for (const hook of (hooks.hooks || []).slice(0, 3)) {
          try {
            const result = await api(`/api/jobs/${state.job.id}/render`, {
              method: "POST",
              body: JSON.stringify({
                target: state.target,
                hook_scene: hook.scene,
                quality: "final",
                aspect: state.aspect,
                captions: state.captions,
                preset: state.preset || null,
                order: state.order,
                clips: clipsForHook(hook.scene),
                script_id: state.scriptId || null,
                audio: currentAudioPlan(),
              }),
            });
            if (result.render) records.push(result.render);
          } catch (error) {
            errors.push({ hook: hook.scene, detail: error.message });
          }
        }
      } else {
        const result = await api(`/api/jobs/${state.job.id}/ab`, {
          method: "POST",
          body: JSON.stringify({
            target: state.target,
            hook_scene: state.overrideHook,
            quality: "final",
            aspect: state.aspect,
            captions: state.captions,
            preset: state.preset || null,
            order: state.order,
            clips: null,
            script_id: state.scriptId || null,
            audio: currentAudioPlan(),
          }),
        });
        records = result.renders || [];
        errors.push(...(result.errors || []));
      }
      state.job.renders = state.job.renders || {};
      records.forEach((record) => {
        state.job.renders[record.record_key || renderKey(record.target)] = record;
      });
      updateRenderPanel();
      startRenderPoll(state.job.id);
      loadHistory();
      if (errors.length) toast(errors[0].detail);
      else toast(`Queued ${records.length} hook variants${state.edited ? " with the edited cut" : ""}.`);
    } catch (error) {
      toast(error.message);
    } finally {
      updateRenderPanel();
    }
  }

  async function loadAudioEngines() {
    try {
      state.audioEngines = await api("/api/audio/engines");
    } catch (_) {
      state.audioEngines = null;
      return;
    }
    const engines = state.audioEngines;
    const allowedVoices = new Set(["say", "piper", "kokoro", "minimax", "fish", "gemini"]);
    const voiceOptions = Object.entries(engines.voices || {})
      .filter(([id]) => allowedVoices.has(id))
      .map(([id, info]) => [
        id,
        `${info.available ? "" : "unavailable · "}${engineLabel(id)}${info.size_mb ? ` (~${info.size_mb} MB)` : ""}`,
      ]);
    fillSelect(dom.audioEngine, voiceOptions);
    const available = Object.values(engines.voices || {})
      .filter((info) => info.available).length;
    const musicOptions = [["none", "No music"]];
    const allowedMusic = new Set(["library", "cc0", "minimax-music", "lyria-clip"]);
    Object.entries(engines.music || {}).forEach(([id, info]) => {
      if (!allowedMusic.has(id)) return;
      musicOptions.push([
        id,
        `${info.available ? "" : "unavailable · "}${musicLabel(id)}${info.size_mb ? ` (~${info.size_mb} MB)` : ""}`,
      ]);
    });
    state.audioMusicOptions = musicOptions;
    fillSelect(dom.audioMusic, musicOptions);
    fillSelect(dom.audioLang, AUDIO_LANGUAGES);
    const rewriteOptions = [["auto", "Auto · OpenCode → OpenRouter → local"]];
    (engines.rewrite_models || []).forEach((item) => {
      rewriteOptions.push([
        item.id,
        `${item.available ? "" : "unavailable · "}${item.name}${item.size_mb ? ` (~${item.size_mb} MB)` : ""}`,
      ]);
    });
    fillSelect(dom.audioRewrite, rewriteOptions);
    dom.audioRewrite.value = state.audio.rewrite || "auto";
    const translateOptions = [["auto", "Auto · best ready engine"]];
    (engines.translation || []).forEach((item) => {
      translateOptions.push([
        item.id,
        `${item.available ? "" : "unavailable · "}${translateLabel(item.id)}`,
      ]);
    });
    fillSelect(dom.audioProvider, translateOptions);
    const preferredTts = state.setup?.tts?.provider;
    if (preferredTts && allowedVoices.has(preferredTts)
        && !["auto", "local"].includes(preferredTts)
        && engines.voices?.[preferredTts]?.available) {
      state.audio.engine = preferredTts;
    }
    dom.audioEngine.value = state.audio.engine;
    dom.audioMusic.value = state.audio.music;
    syncMusicOptions();
    dom.audioLang.value = state.audio.lang;
    dom.audioProvider.value = state.audio.provider || "auto";
    if (!available) {
      dom.audioStatus.textContent = "No voice engine installed. Apple say is built in.";
    }
    loadAudioVoices();
    loadAudioTracks();
    refreshAudioStatus();
    loadAudioScript();
  }

  function translateLabel(id) {
    return {
      apple_fm: "Apple Translation",
      argos: "Argos (offline)",
      marian: "Marian opus-mt",
      ollama: "Ollama",
      opencode: "OpenCode Go · DeepSeek",
      openrouter: "OpenRouter · DeepSeek",
    }[id] || id;
  }

  function engineLabel(id) {
    return {
      say: "Apple say",
      piper: "Piper medium",
      kokoro: "Kokoro int8",
      elevenlabs: "ElevenLabs (API key)",
      openai: "OpenAI gpt-4o-mini-tts",
      groq: "Groq Orpheus",
      deepgram: "Deepgram Aura",
      cartesia: "Cartesia Sonic",
      minimax: "MiniMax Speech 2.8",
      fish: "OpenRouter Fish S2.1 Free",
      gemini: "OpenRouter Gemini Flash-Lite TTS",
      openrouter: "OpenRouter DeepSeek",
    }[id] || id;
  }

  function musicLabel(id) {
    return {
      library: "My own track",
      cc0: "CC0 library",
      "stable-small": "Stable Audio Open Small",
      "stable-1.0": "Stable Audio Open 1.0",
      "musicgen-small": "MusicGen Small · ungated",
      "minimax-music": "MiniMax Music",
      "lyria-clip": "OpenRouter Lyria 3",
    }[id] || id;
  }

  async function loadAudioVoices() {
    const engine = state.audio.engine;
    dom.audioVoice.innerHTML = `<option value="">Loading…</option>`;
    try {
      const result = await api(`/api/audio/voices?engine=${encodeURIComponent(engine)}`);
      const voices = result.voices || [];
      if (!voices.length) {
        const needsKey = ["elevenlabs", "openai", "groq", "deepgram", "minimax", "fish", "gemini"].includes(engine);
        fillSelect(dom.audioVoice, [["", needsKey ? "Add the key in Setup" : "No voices found"]]);
        return;
      }
      fillSelect(dom.audioVoice, voices.map((voice) => [
        voice.id, `${voice.name}${voice.lang ? ` · ${voice.lang}` : ""}`,
      ]));
      const preferred = voices.find((voice) => voice.id === state.audio.voice)
        || voices.find((voice) => /(en[-_]US|en)/i.test(voice.lang || ""))
        || voices[0];
      dom.audioVoice.value = preferred.id;
      state.audio.voice = preferred.id;
    } catch (error) {
      fillSelect(dom.audioVoice, [["", error.message]]);
    }
  }

  async function loadAudioTracks() {
    const source = state.audio.music;
    if (source !== "library" && source !== "cc0") {
      fillSelect(dom.audioTrack, [["", "Not needed for AI music"]]);
      return;
    }
    dom.audioTrack.innerHTML = `<option value="">Auto mood</option>`;
    try {
      const result = await api(`/api/audio/music?source=${encodeURIComponent(source)}`);
      const tracks = result.tracks || [];
      if (!tracks.length) {
        fillSelect(dom.audioTrack, [["", `Empty folder · drop files in assets/music/${source}`]]);
        return;
      }
      fillSelect(dom.audioTrack, [
        ["", "Auto mood"],
        ...tracks.map((track) => [
          track.id,
          `${track.name}${track.moods.length ? ` · ${track.moods.join("/")}` : ""}`,
        ]),
      ]);
      state.audio.track = dom.audioTrack.value || "";
    } catch (error) {
      fillSelect(dom.audioTrack, [["", error.message]]);
    }
  }

  async function loadAudioMoods() {
    if (!state.job) return;
    try {
      const result = await api(
        `/api/jobs/${state.job.id}/audio/moods?target=${state.target}`,
      );
      state.audioMoods = result.moods || [];
      state.audioPromptAuto = result.prompt || "";
      if (!dom.audioPrompt.value) {
        dom.audioPrompt.placeholder = state.audioPromptAuto || "auto mood";
      }
      updateRenderPanel();
      refreshAudioStatus();
    } catch (_) {
      state.audioMoods = [];
    }
  }

  function resetAudioScript(message = "Click ▶ Rewrite to translate the full script and rewrite this cut.") {
    if (!dom.audioScript) return;
    if (dom.audioRewriteNote) dom.audioRewriteNote.textContent = message;
    dom.audioScript.hidden = false;
    dom.audioScript.innerHTML = `
      <div class="script-head">
        <span class="label">Script</span>
        <span class="hint">${esc(message)}</span>
      </div>`;
  }

  async function loadAudioScript(options = {}) {
    const run = options.run === true;
    const forceTranslate = options.forceTranslate === true;
    if (!state.job || !state.plan || !dom.audioScript) return;
    const audio = state.audio;
    const voiceMode = ["bed", "voice", "full"].includes(audio.mode);
    if (!voiceMode || (audio.source === "upload" && voiceMode)) {
      dom.audioScript.hidden = true;
      dom.audioScript.innerHTML = "";
      return;
    }
    if (!run) {
      resetAudioScript();
      return;
    }
    dom.audioScript.hidden = false;
    dom.audioRewriteNote.textContent = "Translating the full script, then rewriting this cut…";
    dom.audioRewriteRun.disabled = true;
    dom.audioScript.innerHTML =
      `<div class="script-head"><span class="label">Script</span><span class="hint">working…</span></div>`;
    try {
      const result = await api(`/api/jobs/${state.job.id}/audio/script`, {
        method: "POST",
        body: JSON.stringify({
          target: state.target,
          hook_scene: state.overrideHook,
          order: state.order,
          clips: state.edited && state.plan ? state.plan.clips : null,
          translate: audio.lang || null,
          provider: "auto",
          mode: audio.style || "smooth",
          rewrite_provider: "auto",
          force_translate: !!forceTranslate,
          overrides: state.scriptOverrides,
        }),
      });
      const lines = result.lines || [];
      state.lastScript = result;
      state.scriptOverrides = result.overrides && typeof result.overrides === "object"
        ? { ...result.overrides } : state.scriptOverrides;
      state.scriptId = result.script_id || state.scriptId;
      if (result.usage) {
        state.job.usage = result.usage;
        renderUsage();
      } else {
        loadUsage();
      }
      const fallbackText = result.warning
        || (result.rewrite_status?.fallback
          ? (result.rewrite_status?.error || "Rewrite unavailable; kept the literal translation.")
          : "");
      const note = fallbackText
        ? `Fallback: ${fallbackText}`
        : result.translated
          ? `Translated to ${result.target} and rewritten for ${state.target}s.`
          : `Rewritten for ${state.target}s.`;
      renderScriptBlock(lines, result, note);
      loadHistory();
    } catch (error) {
      const message = `Rewrite failed: ${error.message}`;
      if (state.lastScript?.lines?.length) {
        renderScriptBlock(
          state.lastScript.lines,
          state.lastScript,
          `${message} · showing last good script.`,
        );
      } else {
        dom.audioRewriteNote.textContent = message;
        dom.audioScript.innerHTML =
          `<div class="script-head"><span class="hint">${esc(message)}</span></div>`;
      }
      loadHistory();
    } finally {
      dom.audioRewriteRun.disabled = false;
    }
  }

  function scriptHeadLabel(result) {
    const warning = result.warning || result.rewrite_status?.warning || "";
    const rewriteValue = result.rewrite;
    const rewrite = typeof rewriteValue === "string"
      ? rewriteValue
      : rewriteValue?.used || result.rewrite_status?.used || "";
    if (warning || result.rewrite_status?.fallback) return "fallback";
    if (rewrite) return rewrite === "literal" ? "literal" : `rewrite · ${rewrite}`;
    return result.mode || "literal";
  }

  function renderScriptBlock(lines, result, note, options = {}) {
    if (!dom.audioScript) return;
    const originalText = lines.map((line) => String(line.original || line.literal || line.text || "")).join("\n");
    const finalText = lines.map((line) => String(line.text || "")).join("\n");
    const warning = result.warning
      || (result.rewrite_status?.fallback
        ? (result.rewrite_status?.error || "Rewrite unavailable; kept the literal translation.")
        : "");
    const head = `${lines.length} lines · ${result.source_lang || "?"}${
      result.translated ? ` → ${result.target || "?"}` : ""} · ${scriptHeadLabel(result)}`;
    const warn = warning
      ? `<span class="script-flag warn" title="${esc(warning)}">${esc(clipText(warning, 120))}</span>` : "";
    dom.audioRewriteNote.textContent = note;
    dom.audioScript.hidden = false;
    dom.audioScript.innerHTML = `
      <div class="script-head">
        <span class="label">Script</span>
        <span class="hint">${esc(head)}</span>${warn}
        <span class="script-copy-actions">
          <button class="ghost small" data-copy-script="original" type="button">Copy original</button>
          <button class="ghost small" data-copy-script="final" type="button">Copy ${result.translated ? "translation" : "rewrite"}</button>
          ${result.translated && !options.snapshot ? '<button class="ghost small" data-script-retry type="button">Retry translation</button>' : ""}
        </span>
      </div>
      <div class="script-list script-grid">
        <div class="script-column-label">Original</div>
        <div class="script-column-label">${result.translated ? "Translation · rewrite" : "Rewrite"}</div>
        ${lines.map((line) => {
          const original = line.original || line.literal || line.text || "";
          return `
          <div class="script-row script-original">
            <span class="script-time">${esc(fmtTime(line.offset || 0, 1))}</span>
            <span class="script-text">${esc(original)}</span>
          </div>
          <div class="script-row script-final">
            <span class="script-time">${esc(line.emotion || "")}</span>
            <span class="script-text">${esc(line.text)}${
              line.shortened ? '<span class="script-flag">fit</span>' : ""}${
              line.from_ocr ? '<span class="script-flag">screen</span>' : ""}${
              line.overridden ? '<span class="script-flag">edited</span>' : ""}</span>
            <button class="ghost small script-edit" data-script-edit="${line.scene}" type="button">edit</button>
          </div>`;
        }).join("") || `<p class="hint">No speech or on-screen text in this cut.</p>`}
      </div>`;
    dom.audioScript.querySelectorAll("[data-copy-script]").forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.copyScript === "original" ? originalText : finalText;
        copyText(value, button.dataset.copyScript === "original" ? "Original script copied." : "Short script copied.");
      });
    });
    dom.audioScript.querySelectorAll("[data-script-retry]").forEach((button) => {
      button.addEventListener("click", () => loadAudioScript({ run: true, forceTranslate: true }));
    });
    dom.audioScript.querySelectorAll("[data-script-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const sceneId = button.dataset.scriptEdit;
        const line = lines.find((item) => String(item.scene) === String(sceneId));
        const current = state.scriptOverrides[sceneId] || line?.text || "";
        const next = window.prompt("Edit this line", current);
        if (next === null) return;
        if (next.trim()) state.scriptOverrides[sceneId] = next.trim();
        else delete state.scriptOverrides[sceneId];
        state.scriptId = null;
        resetAudioScript("Edit saved. Click ▶ Rewrite to regenerate the cut.");
      });
    });
  }

  function renderScriptSnapshot(snapshot) {
    const lines = Array.isArray(snapshot.final_lines) ? snapshot.final_lines : [];
    const result = {
      ...snapshot,
      lines,
      translated: !!snapshot.translated,
      target: snapshot.target_lang || snapshot.target || "",
      source_lang: snapshot.source_lang || "",
      rewrite: snapshot.rewrite?.used || snapshot.rewrite || "",
      mode: snapshot.style || "",
    };
    const note = "Restored from history. Overrides applied; click ▶ Rewrite to regenerate audio.";
    renderScriptBlock(lines, result, note, { snapshot: true });
  }

  function copyText(value, message) {
    const text = String(value || "");
    if (!text) {
      toast("Nothing to copy.");
      return;
    }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => toast(message || "Copied."))
        .catch(() => window.prompt(message || "Copy", text));
      return;
    }
    window.prompt(message || "Copy", text);
  }

  function refreshAudioStatus() {
    const engines = state.audioEngines;
    if (!engines || !state.job) return;
    const pieces = [];
    const mode = state.audio.mode;
    const preferredTts = state.setup?.tts?.provider;
    if (preferredTts && !["auto", "local"].includes(preferredTts)
        && engines.voices?.[preferredTts] && !engines.voices[preferredTts].available
        && state.audio.engine !== preferredTts) {
      pieces.push(`Preferred ${engineLabel(preferredTts)} unavailable · using ${engineLabel(state.audio.engine)}`);
    }
    if (mode === "voice" && !engines.separation?.demucs?.available) {
      pieces.push(`Demucs missing · ${engines.separation?.demucs?.install || "pip install demucs"}`);
    }
    if (musicSourceMode() === "generate") {
      const info = engines.music?.[state.audio.music];
      if (info && !info.available) pieces.push(info.install);
    }
    if (state.audioMoods.length && ["music", "full"].includes(mode)) {
      pieces.push(`auto mood: ${state.audioMoods.slice(0, 3).join(", ")}`);
    }
    dom.audioStatus.textContent = pieces.join(" · ");
  }

  async function loadTranslateCheck() {
    if (!state.job) return;
    const source = (state.job.analysis?.engine?.transcript_language || "en").split("-")[0];
    const target = state.audio.lang;
    if (!target || target === source) {
      state.translateCheck = null;
      refreshAudioStatus();
      return;
    }
    try {
      const result = await api(
        `/api/audio/translate/status?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
      );
      state.translateCheck = result.check;
    } catch (_) {
      state.translateCheck = null;
    }
    refreshAudioStatus();
  }

  async function previewVoice() {
    if (!state.job) return;
    dom.audioPreview.disabled = true;
    dom.audioStatus.textContent = "Rendering voice sample…";
    try {
      const token = tokenValue();
      const response = await fetch(`/api/jobs/${state.job.id}/voice/sample`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          engine: state.audio.engine,
          voice: state.audio.voice,
          rate: state.audio.rate,
        }),
      });
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.play();
      dom.audioStatus.textContent = "Voice sample ready.";
    } catch (error) {
      dom.audioStatus.textContent = error.message;
    } finally {
      dom.audioPreview.disabled = false;
    }
  }

  // ---------------------------------------------------------------- render reel

  function currentHookId() {
    if (!state.job) return null;
    if (state.overrideHook !== null) return state.overrideHook;
    if (state.plan && state.plan.auto === false && state.plan.hook_scene !== undefined) {
      return state.plan.hook_scene;
    }
    return state.job.analysis.hook_scene;
  }

  function currentHookScene() {
    return sceneById(currentHookId());
  }

  function renderKey(
    target = state.target,
    quality = "final",
    aspect = state.aspect,
    captions = state.captions,
    audioSig = currentAudioSignature(),
  ) {
    let key = String(target);
    if (quality !== "final") key += `:${quality}`;
    if (aspect !== "9:16") key += `:${aspect.replace(":", "x")}`;
    if (captions) key += ":cap";
    if (audioSig) key += `:a${audioSig}`;
    return key;
  }

  function findRender(quality = "final") {
    if (!state.job?.renders) return null;
    const sig = currentAudioSignature();
    const direct = sig
      ? state.job.renders[renderKey(state.target, quality, state.aspect, state.captions, sig)]
      : state.job.renders[renderKey(state.target, quality, state.aspect, state.captions)]
        || state.job.renders[renderKey(state.target, quality, state.aspect, state.captions, "")];
    if (direct) return direct;
    const hookId = currentHookId();
    const matches = Object.values(state.job.renders).filter((record) => record
      && record.status === "ready"
      && record.target === state.target
      && (record.quality || "final") === quality
      && (record.aspect || "9:16") === state.aspect
      && !!record.captions === !!state.captions
      && (record.audio_sig || "") === sig
      && record.hook === hookId);
    matches.sort((a, b) => (b.updated || 0) - (a.updated || 0));
    return matches[0]
      || (!sig && quality === "final" && state.aspect === "9:16" && !state.captions
        ? state.job.renders[String(state.target)] || null
        : null);
  }

  function activeRender() {
    const records = Object.values(state.job?.renders || {});
    return records.find((record) => record
      && (record.status === "queued" || record.status === "rendering" || record.status === "cancelling")) || null;
  }

  function isRenderActive(record) {
    return !!record && (record.status === "queued" || record.status === "rendering" || record.status === "cancelling");
  }

  function updateRenderPanel() {
    if (!state.job || !state.plan) return;
    const target = state.target;
    const finalRecord = findRender("final");
    const draftRecord = findRender("draft");
    const hookId = currentHookId();
    const finalMatches = finalRecord && finalRecord.hook === hookId;
    const draftMatches = draftRecord && draftRecord.hook === hookId;
    const active = activeRender();
    const blocked = audioBlockReason();

    dom.renderError.hidden = true;
    dom.playerWrap.hidden = true;
    dom.renderProgress.hidden = true;
    dom.render.disabled = false;
    dom.renderDraft.disabled = false;
    dom.renderAll.disabled = false;
    dom.renderAb.disabled = false;
    dom.renderCancel.hidden = true;
    dom.renderCancel.disabled = false;
    if (blocked) {
      dom.render.disabled = true;
      dom.renderDraft.disabled = true;
      dom.renderAll.disabled = true;
      dom.renderAb.disabled = true;
    }

    if (active) {
      const pct = Math.round((active.progress || 0) * 100);
      dom.renderProgress.hidden = false;
      dom.renderProgress.querySelector(".bar i").style.width = `${pct}%`;
      const eta = active.eta ? ` · ~${Math.ceil(active.eta)}s left` : "";
      dom.renderProgress.querySelector("span").textContent =
        `${pct}% · ${active.message || "Rendering"}${eta}`;
      dom.render.disabled = true;
      dom.renderDraft.disabled = true;
      dom.renderAll.disabled = true;
      dom.renderCancel.hidden = false;
      renderButton(active.quality === "draft" ? "Rendering draft…" : "Rendering final…");
      dom.renderNote.textContent = state.plan.note || "One render at a time.";
      return;
    }

    const show = (record, quality) => {
      dom.playerWrap.hidden = false;
      if (dom.reelVideo.dataset.key !== record.key) {
        dom.reelVideo.src = withToken(record.url);
        dom.reelVideo.poster = record.poster_url ? withToken(record.poster_url) : "";
        dom.reelVideo.dataset.key = record.key;
        dom.reelVideo.load();
      }
      const tag = quality === "draft" ? "draft · " : "";
      const audioTag = record.audio
        ? ` · ${record.audio.mode}${
          (record.translate || record.audio.translate) ? ` → ${record.translate || record.audio.translate.target}` : ""}${
          record.voice_engine ? ` · ${record.voice_engine}` : ""}`
        : "";
      dom.reelDuration.textContent = `${tag}${record.duration.toFixed(1)}s · ${record.width}×${record.height} · ${record.clip_count} beats`;
      dom.reelSize.textContent = `${formatSize(record.size)} · H.264 / AAC${audioTag}`;
      dom.download.href = withToken(record.url);
      dom.download.download = `${fileStem(state.job.source.name)}-${target}s${quality === "draft" ? "-draft" : ""}.mp4`;
    };

    const draftNewer = draftMatches && draftRecord.status === "ready"
      && (!finalMatches || finalRecord.status !== "ready"
        || (draftRecord.updated || 0) > (finalRecord.updated || 0));
    if (draftNewer) {
      show(draftRecord, "draft");
      dom.renderNote.textContent = blocked
        || "Draft preview · 540×960 · render final when it feels right.";
      renderButton(`Render final ${target}s`);
      return;
    }

    if (finalMatches && finalRecord.status === "ready") {
      show(finalRecord, "final");
      dom.renderNote.textContent = blocked
        || state.plan.note || `${finalRecord.clip_count} beats · original audio · no watermark`;
      renderButton(`Render ${target}s again`);
      return;
    }

    const failed = (finalMatches && finalRecord.status === "failed" && finalRecord)
      || (draftMatches && draftRecord.status === "failed" && draftRecord);
    if (failed) {
      dom.renderError.textContent = failed.error || "Render failed.";
      dom.renderError.hidden = false;
    }

    renderButton(`Render ${target}s reel`);
    const dims = { "9:16": "1080×1920", "4:5": "1080×1350", "1:1": "1080×1080", "16:9": "1920×1080" };
    dom.renderNote.textContent = blocked
      || state.plan.note
      || `${state.aspect} ${dims[state.aspect] || ""} · original audio${state.captions ? " · captions" : ""} · no watermark`;
  }

  function renderButton(label) {
    dom.render.innerHTML = `${esc(label)} <span class="arrow">↗</span>`;
  }

  async function startRender(quality = "final") {
    if (!state.job || !state.plan) return;
    const block = audioBlockReason();
    if (block) {
      toast(block);
      updateRenderPanel();
      return;
    }
    const target = state.target;
    const existing = findRender(quality);
    const force = !!(existing && existing.status === "ready" && existing.hook === currentHookId());
    dom.render.disabled = true;
    dom.renderDraft.disabled = true;
    dom.renderError.hidden = true;
    try {
      const result = await api(`/api/jobs/${state.job.id}/render`, {
        method: "POST",
        body: JSON.stringify({
          target,
          hook_scene: state.overrideHook ?? (state.edited ? state.plan.clips?.[0]?.scene ?? null : null),
          quality,
          aspect: state.aspect,
          captions: state.captions,
          preset: state.preset || null,
          order: state.order,
          clips: state.edited && state.plan ? state.plan.clips : null,
          script_id: state.scriptId || null,
          audio: currentAudioPlan(),
          force,
        }),
      });
      state.job.renders = state.job.renders || {};
      state.job.renders[result.render.record_key || renderKey(
        target, quality, state.aspect, state.captions,
      )] = result.render;
      updateRenderPanel();
      startRenderPoll(state.job.id);
      loadHistory();
      toast(quality === "draft" ? "Rendering draft…" : (force ? "Re-rendering reel…" : "Rendering reel…"));
    } catch (error) {
      toast(error.message);
      updateRenderPanel();
    }
  }

  async function startRenderAll() {
    if (!state.job || !state.plan) return;
    const block = audioBlockReason();
    if (block) {
      toast(block);
      updateRenderPanel();
      return;
    }
    dom.renderAll.disabled = true;
    try {
      let records = [];
      const errors = [];
      if (state.edited) {
        for (const target of [15, 30, 60]) {
          try {
            const result = await api(`/api/jobs/${state.job.id}/render`, {
              method: "POST",
              body: JSON.stringify({
                target,
                hook_scene: state.overrideHook ?? state.plan.hook_scene ?? state.plan.clips?.[0]?.scene ?? null,
                quality: "final",
                aspect: state.aspect,
                captions: state.captions,
                preset: state.preset || null,
                order: state.order,
                clips: state.plan.clips,
                script_id: state.scriptId || null,
                audio: currentAudioPlan(),
              }),
            });
            if (result.render) records.push(result.render);
          } catch (error) {
            errors.push({ target, detail: error.message });
          }
        }
      } else {
        const result = await api(`/api/jobs/${state.job.id}/render-all`, {
          method: "POST",
          body: JSON.stringify({
            hook_scene: state.overrideHook,
            quality: "final",
            aspect: state.aspect,
            captions: state.captions,
            preset: state.preset || null,
            order: state.order,
            clips: null,
            script_id: state.scriptId || null,
            audio: currentAudioPlan(),
          }),
        });
        records = result.renders || [];
        errors.push(...(result.errors || []));
      }
      state.job.renders = state.job.renders || {};
      records.forEach((record) => {
        state.job.renders[record.record_key || renderKey(
          record.target,
          record.quality || "final",
          record.aspect || "9:16",
          record.captions || false,
          record.audio_sig || "",
        )] = record;
      });
      updateRenderPanel();
      startRenderPoll(state.job.id);
      loadHistory();
      if (errors.length) toast(errors[0].detail);
      else toast(state.edited ? "Queued the edited cut at 15/30/60." : "Queued all three reels.");
    } catch (error) {
      toast(error.message);
      updateRenderPanel();
    }
  }

  async function cancelRender() {
    const record = activeRender();
    if (!record) return;
    dom.renderCancel.disabled = true;
    try {
      await api(`/api/jobs/${state.job.id}/render/${record.target}/cancel?quality=${
        encodeURIComponent(record.quality || "final")
      }&aspect=${encodeURIComponent(record.aspect || "9:16")}&captions=${
        record.captions ? "true" : "false"
      }&audio_sig=${encodeURIComponent(record.audio_sig || "")}&record_key=${
        encodeURIComponent(record.record_key || "")
      }`, { method: "POST" });
      toast("Stopping render…");
      startRenderPoll(state.job.id);
    } catch (error) {
      toast(error.message);
      dom.renderCancel.disabled = false;
    }
  }

  function startRenderPoll(id) {
    stopPoll();
    const tick = async () => {
      try {
        const status = await api(`/api/jobs/${id}/status`);
        state.job.renders = status.renders || {};
        updateRenderPanel();
        const active = Object.values(status.renders || {}).some(isRenderActive);
        if (active) {
          state.pollTimer = setTimeout(tick, 900);
        } else {
          loadUsage();
          loadHistory();
          stopPoll();
        }
      } catch (_) {
        state.pollTimer = setTimeout(tick, 1800);
      }
    };
    tick();
  }

  // ---------------------------------------------------------------- history

  async function loadHistory() {
    if (!state.job) return;
    const jobId = state.job.id;
    try {
      const data = await api(`/api/jobs/${jobId}/history?limit=50`);
      if (!state.job || state.job.id !== jobId) return;
      state.history = data.entries || [];
      renderHistory();
    } catch (_) {
      if (dom.historyCount) dom.historyCount.textContent = "";
    }
  }

  function historyMeta(entry) {
    return [
      entry.target ? `${entry.target}s` : "",
      entry.style || "",
      entry.provider || "",
      entry.model || "",
    ].filter(Boolean).join(" · ");
  }

  function renderHistory() {
    if (!dom.historyList) return;
    const entries = state.history || [];
    dom.historyCount.textContent = entries.length ? `${entries.length} attempts` : "empty";
    if (!entries.length) {
      dom.historyList.innerHTML = `<p class="hint history-empty">No script, upload or render attempts yet.</p>`;
      return;
    }
    dom.historyList.innerHTML = entries.map((entry) => {
      const problem = entry.error || entry.warning || "";
      return `
        <button class="history-row status-${esc(entry.status || "ok")}" data-history-entry="${esc(entry.id)}"
          title="${esc(problem || historyMeta(entry))}">
          <span class="history-type">${esc(entry.type || "entry")}</span>
          <span class="history-status">${esc(entry.status || "")}</span>
          <span class="history-meta">${esc(historyMeta(entry))}</span>
          <span class="history-time">${esc(formatHistoryTime(entry.created))}</span>
          ${problem ? `<span class="history-problem">${esc(clipText(problem, 90))}</span>` : ""}
        </button>`;
    }).join("");
  }

  async function viewHistoryEntry(entryId) {
    if (!state.job) return;
    dom.historyDetail.hidden = false;
    dom.historyDetail.innerHTML = `<p class="hint">Loading snapshot…</p>`;
    try {
      const item = await api(`/api/jobs/${state.job.id}/history/${entryId}`);
      state.historyEntry = item;
      renderHistoryDetail(item);
    } catch (error) {
      dom.historyDetail.innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    }
  }

  function renderHistoryDetail(item) {
    const entry = item.entry || {};
    const snapshot = item.snapshot || {};
    const rows = [
      ["Type", entry.type],
      ["Status", entry.status],
      ["When", formatHistoryTime(entry.created)],
      ["Target", entry.target ? `${entry.target}s` : ""],
      ["Style", entry.style],
      ["Provider", entry.provider],
      ["Model", entry.model],
      ["Tried", (entry.tried || []).join(" → ")],
      ["Fallback", entry.fallback ? "yes" : ""],
      ["Latency", entry.latency_ms ? `${entry.latency_ms} ms` : ""],
      ["Script", entry.script_id],
    ].filter(([, value]) => value !== undefined && value !== null && value !== "");
    let body = "";
    if (entry.type === "script") {
      const lines = Array.isArray(snapshot.final_lines) ? snapshot.final_lines : [];
      body = `
        <div class="history-snapshot">
          ${lines.map((line) => `
            <div class="history-line">
              <span class="history-line-time">${esc(fmtTime(line.offset || 0, 1))}</span>
              <span>${esc(line.text || "")}</span>
              ${line.overridden ? '<span class="script-flag">edited</span>' : ""}
            </div>`).join("") || `<p class="hint">No lines in this snapshot.</p>`}
        </div>
        <div class="history-actions">
          <button class="primary small" data-history-restore="${esc(entry.id)}" type="button">Restore script</button>
          <button class="ghost small" data-history-copy="original" type="button">Copy original</button>
          <button class="ghost small" data-history-copy="final" type="button">Copy final</button>
        </div>`;
    } else if (entry.type === "render") {
      const render = snapshot.render || {};
      const plan = snapshot.plan || {};
      const path = String(render.path || entry.path || "");
      const file = path.split("/").pop();
      const link = file
        ? `<a class="ghost small" href="${esc(withToken(`/api/jobs/${state.job.id}/media/${encodeURIComponent(file)}`))}" download>Download reel</a>`
        : "";
      body = `
        <div class="history-snapshot">
          <p class="hint">${esc(`${plan.clip_count || 0} beats · ${Number(plan.total || 0).toFixed(1)}s · hook ${plan.hook_scene ?? "auto"} · ${render.quality || entry.quality || ""} · ${render.aspect || entry.aspect || ""}`)}</p>
        </div>
        <div class="history-actions">${link}</div>`;
    } else if (entry.type === "upload") {
      body = `
        <div class="history-snapshot">
          <p class="hint">${esc(`${snapshot.kind || entry.kind || "upload"} · ${snapshot.name || entry.name || ""} · ${Number(snapshot.duration || entry.duration || 0).toFixed(1)}s`)}</p>
        </div>`;
    } else {
      body = `<div class="history-snapshot"><p class="hint">${esc(JSON.stringify(snapshot).slice(0, 500))}</p></div>`;
    }
    const problem = entry.error || entry.warning || "";
    dom.historyDetail.innerHTML = `
      <div class="history-detail-head">
        <span class="label">${esc(entry.type || "entry")} · ${esc(entry.id || "")}</span>
        <button class="ghost small" data-history-delete="${esc(entry.id)}" type="button">Delete</button>
      </div>
      <div class="history-detail-meta">
        ${rows.map(([label, value]) => `<span><b>${esc(label)}</b> ${esc(value)}</span>`).join("")}
      </div>
      ${problem ? `<p class="history-problem">${esc(problem)}</p>` : ""}
      ${body}`;
  }

  async function restoreHistoryEntry(entryId) {
    if (!state.job) return;
    try {
      const data = await api(`/api/jobs/${state.job.id}/history/${entryId}/restore`, { method: "POST" });
      const snapshot = data.snapshot || {};
      const restored = snapshot.overrides && typeof snapshot.overrides === "object"
        ? { ...snapshot.overrides } : {};
      // The saved final lines are authoritative: apply them as per-scene
      // overrides so render uses the restored text on the current cut.
      (snapshot.final_lines || []).forEach((line) => {
        if (line?.scene !== undefined && line?.text) {
          restored[String(line.scene)] = String(line.text);
        }
      });
      state.scriptOverrides = restored;
      // The current cut is kept. The snapshot may target a different cut, so
      // the old script_id must not be reused; overrides carry the text.
      state.scriptId = null;
      state.lastScript = {
        ...snapshot,
        lines: snapshot.final_lines || [],
        overrides: restored,
      };
      if (snapshot.style && dom.audioStyle.querySelector(`option[value="${snapshot.style}"]`)) {
        state.audio.style = snapshot.style;
        dom.audioStyle.value = snapshot.style;
      }
      if (snapshot.target_lang) {
        state.audio.lang = snapshot.target_lang === snapshot.source_lang ? "" : snapshot.target_lang;
        dom.audioLang.value = state.audio.lang;
      }
      renderHook();
      renderPlan();
      renderScenes();
      updateRenderPanel();
      renderScriptSnapshot(snapshot);
      state.historyEntry = data;
      renderHistoryDetail(data);
      toast("Script restored to the current cut. Overrides are in the render plan.");
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteHistoryEntry(entryId) {
    if (!state.job) return;
    try {
      await api(`/api/jobs/${state.job.id}/history/${entryId}`, { method: "DELETE" });
      if (state.historyEntry?.entry?.id === entryId) {
        state.historyEntry = null;
        dom.historyDetail.hidden = true;
        dom.historyDetail.innerHTML = "";
      }
      loadHistory();
      toast("History entry deleted.");
    } catch (error) {
      toast(error.message);
    }
  }

  function formatHistoryTime(timestamp) {
    if (!timestamp) return "";
    const date = new Date(Number(timestamp) * 1000);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  // ---------------------------------------------------------------- drawer

  function openDrawer(sceneId) {
    const scene = sceneById(sceneId);
    if (!scene) return;
    state.drawerScene = sceneId;
    const planClip = (state.plan?.clips || []).find((clip) => clip.scene === sceneId);
    const role = planClip?.role || "";
    const why = planClip?.why || sceneNote(scene);
    const isHook = sceneId === currentHookId();
    const isDeep = scene.deep !== false;
    const bars = [
      ["Hook", scene.hook],
      ["Visual", scene.visual_score],
      ["Motion", scene.motion_score],
      ["Audio", scene.audio_score],
      ["Text", scene.text_score],
    ].map(([label, value]) => `
      <div class="drawer-bar">
        <span>${esc(label)}</span>
        <div class="bar"><i style="width:${Math.round(value)}%"></i></div>
        <b>${Math.round(value)}</b>
      </div>`).join("");
    const speech = scene.speech
      ? `<div class="drawer-section"><span class="label">Speech</span><p class="drawer-copy" style="font-size:15px">${esc(scene.speech)}</p></div>`
      : "";
    const ocr = !isDeep
      ? `<p class="drawer-copy muted">Quick scan. Deep-read this beat to inspect text, faces and crop.</p>`
      : scene.ocr
        ? `<p class="drawer-copy">${esc(scene.ocr)}</p>`
        : (!scene.speech ? `<p class="drawer-copy muted">No on-screen text or speech on this beat.</p>` : "");
    const targetAspect = aspectValue(state.aspect);
    const cropDetail = state.meta && state.meta.width && state.meta.height
      ? `${state.meta.width}×${state.meta.height} source · ${
        Math.abs(state.meta.width / state.meta.height - targetAspect) < 0.01
          ? `native ${state.aspect} · no crop`
          : cropModeFor(scene) === "smart"
            ? `Vision subject tracking · ${state.aspect}`
            : `center fallback · ${state.aspect}`
      }`
      : "center fallback";
    const frame = isDeep
      ? `<img src="${esc(thumbUrl(scene))}" alt="" style="object-position:${objectPosition(scene.crop)}">`
      : `<div class="drawer-placeholder"><span>quick scan</span><small>no still extracted yet</small></div>`;
    dom.drawerContent.innerHTML = `
      <div class="drawer-frame">
        ${frame}
      </div>
      <div class="drawer-kicker">Scene ${scene.id + 1} · ${esc(role || "outside cut")}</div>
      <h3 class="drawer-title">${esc(fmtTime(scene.start, 1))} – ${esc(fmtTime(scene.end, 1))}</h3>
      <p class="drawer-meta">${scene.dur.toFixed(2)}s · hook ${Math.round(scene.hook)} · interest ${Math.round(scene.score)}</p>
      ${ocr}
      ${speech}
      <div class="drawer-section"><span class="label">Why ${esc(role || "this beat")}</span><p class="drawer-why">${esc(why)}</p></div>
      <div class="drawer-crop"><strong>${esc(cropLabel(scene))}</strong><span>${esc(cropDetail)}</span></div>
      <div class="drawer-section"><span class="label">Score</span><div class="drawer-bars">${bars}</div></div>
      <div class="drawer-section"><span class="label">Signals</span><div class="tag-row">${tagsHtml(scene)}</div></div>
      <div class="drawer-actions">
        ${!isDeep
          ? `<button class="primary" data-read-scene="${scene.id}">Deep-read this scene <span class="arrow">↗</span></button>`
          : planClip
            ? `<button class="ghost" disabled>In Smart Cut</button>`
            : `<button class="primary" data-add-scene="${scene.id}">Add to Smart Cut <span class="arrow">↗</span></button>`}
        ${!isDeep || planClip || isHook ? "" : `<button class="ghost" data-use-hook="${scene.id}">Use as hook</button>`}
        <button class="ghost" data-close>Close</button>
      </div>`;
    dom.drawer.hidden = false;
    document.body.classList.add("no-scroll");
  }

  async function readScene(sceneId) {
    if (!state.job) return;
    const button = dom.drawerContent.querySelector("[data-read-scene]");
    if (button) {
      button.disabled = true;
      button.textContent = "Reading…";
    }
    try {
      const result = await api(`/api/jobs/${state.job.id}/scene/${sceneId}/read`, {
        method: "POST",
      });
      mergeScene(result.scene);
      state.job.analysis.hook_scene = result.hook_scene;
      state.job.analysis.plans = result.plans;
      state.job.analysis.deep_count = result.deep_count;
      closeDrawer();
      await refreshPlan();
      openDrawer(sceneId);
      toast("Scene deep-read.");
    } catch (error) {
      toast(error.message);
      if (button) {
        button.disabled = false;
        button.innerHTML = `Deep-read this scene <span class="arrow">↗</span>`;
      }
    }
  }

  function closeDrawer() {
    dom.drawer.hidden = true;
    state.drawerScene = null;
    document.body.classList.remove("no-scroll");
  }

  // ---------------------------------------------------------------- navigation

  function resetToIngest() {
    stopPoll();
    closeDrawer();
    state.job = null;
    state.plan = null;
    state.overrideHook = null;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    state.history = [];
    state.historyEntry = null;
    state.timelineScroll = 0;
    state.target = 30;
    state.sort = "best";
    state.visible = 96;
    state.busy = false;
    state.progressStart = null;
    state.pollStart = null;
    state.file = null;
    state.localPath = null;
    state.meta = null;
    state.fileName = "";
    dom.fileInput.value = "";
    dom.pathInput.value = "";
    dom.dropzone.hidden = false;
    dom.fileCard.hidden = true;
    dom.fileName.textContent = "";
    dom.fileInfo.textContent = "";
    dom.ingestError.hidden = true;
    dom.progressError.hidden = true;
    dom.progressBack.hidden = true;
    dom.renderError.hidden = true;
    dom.playerWrap.hidden = true;
    dom.renderProgress.hidden = true;
    if (dom.historyList) dom.historyList.innerHTML = "";
    if (dom.historyDetail) {
      dom.historyDetail.hidden = true;
      dom.historyDetail.innerHTML = "";
    }
    if (dom.historyCount) dom.historyCount.textContent = "";
    dom.ingestNote.textContent = "ffmpeg cuts first. Analysis follows.";
    dom.optSpeech.checked = false;
    dom.optCrop.checked = true;
    dom.optOcr.checked = state.health ? state.health.vision : true;
    dom.reelVideo.removeAttribute("src");
    dom.reelVideo.removeAttribute("data-key");
    dom.reelVideo.load();
    $$("#target-tabs button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.target) === 30);
    });
    $$("#sort-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.sort === "best");
    });
    syncOptions();
    updateAnalyzeState();
    showView("ingest");
    history.replaceState(null, "", location.pathname);
    document.title = "VibeCut — long video to reels";
    loadRecent();
  }

  async function deleteJob() {
    if (!state.job) return;
    if (!confirm("Delete this job and its rendered reels?")) return;
    try {
      await api(`/api/jobs/${state.job.id}`, { method: "DELETE" });
      resetToIngest();
      toast("Job deleted.");
    } catch (error) {
      toast(error.message);
    }
  }

  let cleanArmedAt = 0;

  async function cleanJobFiles() {
    if (!state.job) return;
    const now = Date.now();
    if (now - cleanArmedAt > 5000) {
      cleanArmedAt = now;
      dom.cleanJob.textContent = "Click to confirm";
      setTimeout(() => {
        if (Date.now() - cleanArmedAt >= 5000) dom.cleanJob.textContent = "Clean";
      }, 5200);
      return;
    }
    cleanArmedAt = 0;
    dom.cleanJob.disabled = true;
    dom.cleanJob.textContent = "Cleaning…";
    try {
      const result = await api(`/api/jobs/${state.job.id}/clean`, {
        method: "POST",
        body: JSON.stringify({ profile: dom.cleanProfile.value || "workfiles" }),
      });
      toast(`Cleaned: ${(result.cleaned || []).join(", ") || "nothing to remove"}.`);
      await openJob(state.job.id);
    } catch (error) {
      toast(error.message);
    } finally {
      dom.cleanJob.disabled = false;
      dom.cleanJob.textContent = "Clean";
    }
  }

  function showView(view) {
    dom.ingest.hidden = view !== "ingest";
    dom.progress.hidden = view !== "progress";
    dom.result.hidden = view !== "result";
    window.scrollTo(0, 0);
  }

  function showIngestError(message) {
    dom.ingestError.textContent = message;
    dom.ingestError.hidden = false;
  }

  // ---------------------------------------------------------------- helpers

  function sceneById(id) {
    if (!state.job) return null;
    return state.job.analysis.scenes.find((scene) => scene.id === id) || null;
  }

  function thumbUrl(scene) {
    return withToken(scene.thumb_url || `/api/jobs/${state.job.id}/thumb/${scene.id}`);
  }

  function objectPosition(crop) {
    const meta = state.meta || { width: 9, height: 16 };
    const boxW = 9;
    const boxH = 16;
    const srcW = Math.max(1, Number(meta.width) || 9);
    const srcH = Math.max(1, Number(meta.height) || 16);
    const scale = Math.max(boxW / srcW, boxH / srcH);
    const scaledW = srcW * scale;
    const scaledH = srcH * scale;
    const overflowX = scaledW - boxW;
    const overflowY = scaledH - boxH;
    const cx = clamp(Number(crop?.cx ?? 0.5), 0, 1);
    const cy = clamp(Number(crop?.cy ?? 0.5), 0, 1);
    const posX = overflowX > 0 ? (cx * scaledW - boxW / 2) / overflowX : 0.5;
    const posY = overflowY > 0 ? (cy * scaledH - boxH / 2) / overflowY : 0.5;
    return `${clamp(posX, 0, 1) * 100}% ${clamp(posY, 0, 1) * 100}%`;
  }

  function aspectValue(value) {
    const [width, height] = String(value || "9:16").split(":").map(Number);
    return width / Math.max(1, height);
  }

  function cropFor(scene) {
    return scene?.crops?.[state.aspect] || scene?.crop || { cx: 0.5, cy: 0.5 };
  }

  function cropModeFor(scene) {
    return scene?.crop_modes?.[state.aspect] || scene?.crop_mode || "center";
  }

  function cropLabel(scene) {
    const meta = state.meta;
    if (!meta?.width || !meta?.height) return "center crop";
    const sourceAspect = meta.width / meta.height;
    const targetAspect = aspectValue(state.aspect);
    if (Math.abs(sourceAspect - targetAspect) < 0.01) return `${state.aspect} native`;
    if (cropModeFor(scene) !== "smart") return `center ${state.aspect}`;
    const crop = cropFor(scene);
    if (sourceAspect < targetAspect) {
      return `subject ${state.aspect} · ${Math.round((crop.cy ?? 0.5) * 100)}% y`;
    }
    return `subject ${state.aspect} · ${Math.round((crop.cx ?? 0.5) * 100)}% x`;
  }

  function sceneLine(scene) {
    if (scene.ocr) return scene.ocr;
    if (scene.speech) return `“${scene.speech}”`;
    const bits = [];
    if (scene.face) bits.push("a face");
    if (scene.tags?.includes("motion")) bits.push("movement");
    if (scene.tags?.includes("subject")) bits.push("a clear subject");
    const detail = bits.length ? bits.join(", ") : "a quiet frame";
    return `A ${scene.dur.toFixed(1)}s beat at ${fmtTime(scene.start)} — ${detail}.`;
  }

  function sceneNote(scene) {
    const bits = [];
    if (scene.ocr) bits.push(`on-screen text “${clipText(scene.ocr)}”`);
    if (scene.speech) bits.push(`spoken line “${clipText(scene.speech)}”`);
    if (scene.face) bits.push("a face in frame");
    else if (scene.subject) bits.push("a clear subject");
    if (scene.tags?.includes("motion")) bits.push("strong movement");
    if (scene.dur >= 3) bits.push("a long hold");
    if (!bits.length) bits.push("a strong visual + audio beat");
    return bits.join(", ");
  }

  function clipText(value, limit = 70) {
    const text = String(value || "").trim();
    return text.length <= limit ? text : `${text.slice(0, limit - 1).trim()}…`;
  }

  function scoreItem(label, value) {
    const safe = clamp(Number(value) || 0, 0, 100);
    return `
      <div class="score-item">
        <div class="label"><span>${esc(label)}</span><b>${Math.round(safe)}</b></div>
        <div class="mini-bar"><i style="width:${safe}%"></i></div>
      </div>`;
  }

  function tagsHtml(scene) {
    const tags = scene.tags && scene.tags.length ? scene.tags : ["quiet"];
    return tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("");
  }

  function fmtTime(seconds, decimals = 0) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "0:00";
    const total = Math.floor(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const base = hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${minutes}:${String(secs).padStart(2, "0")}`;
    if (!decimals) return base;
    return `${base}.${String(Math.floor((value - total) * 10))}`;
  }

  function fmtDuration(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "—";
    if (value < 60) return `${value.toFixed(1)}s`;
    const total = Math.round(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours) return `${hours}h ${minutes}m`;
    return `${minutes}m ${secs}s`;
  }

  function formatSize(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = 0;
    let size = value;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return `${size.toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function formatDate(timestamp) {
    if (!timestamp) return "";
    const date = new Date(Number(timestamp) * 1000);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function fileStem(name) {
    return String(name || "video").replace(/\.[^.]+$/, "");
  }

  function basename(path) {
    return String(path || "").split(/[\\/]/).pop() || "video";
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));
  }

  function toast(message) {
    dom.toast.textContent = message;
    dom.toast.hidden = false;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      dom.toast.hidden = true;
      state.toastTimer = null;
    }, 3600);
  }

  function routeFromHash() {
    const match = location.hash.match(/^#job=([a-z0-9]+)/i);
    if (match) openJob(match[1]);
  }
})();
