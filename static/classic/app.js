(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const CLASSIC_TEXT_ASPECTS = ["9:16", "4:5"];
  const CLASSIC_TEXT_ANCHORS = {
    top: "top-center",
    center: "center",
    bottom: "bottom-center",
  };
  const CLASSIC_TEXT_POSITIONS = {
    "top-center": "top",
    center: "center",
    "bottom-center": "bottom",
  };
  const CLASSIC_TEXT_KINDS = {
    top: "hook",
    center: "title",
    bottom: "lower_third",
  };
  const CLASSIC_TEXT_BOX = {
    hook: { w: 0.76, h: 0.16 },
    title: { w: 0.76, h: 0.14 },
    lower_third: { w: 0.64, h: 0.14 },
  };
  const CLASSIC_EFFECT_LABELS = {
    punch_in: "Punch in",
    shake: "Shake",
    circle: "Circle (centre)",
  };

  const dom = {
    ingest: $("#ingest-view"),
    progress: $("#progress-view"),
    result: $("#result-view"),
    brand: $("#brand"),
    health: $("#health"),
    privacyPill: $("#privacy-pill"),
    privacyLabel: $("#privacy-label"),
    footerHealth: $("#footer-health"),
    setup: $("#setup"),
    setupOpen: $("#setup-open"),
    setupClose: $("#setup-close"),
    setupSave: $("#setup-save"),
    setupStatus: $("#setup-status"),
    setupPlatformBadge: $("#setup-platform-badge"),
    setupPlatformSummary: $("#setup-platform-summary"),
    setupPlatformRows: $("#setup-platform-rows"),
    setupOpencodeEnabled: $("#setup-opencode-enabled"),
    setupOpencodeStatus: $("#setup-opencode-status"),
    setupOpencodeKey: $("#setup-opencode-key"),
    setupOpenrouterKey: $("#setup-openrouter-key"),
    setupOpencodeModel: $("#setup-opencode-model"),
    setupOpencodeVariant: $("#setup-opencode-variant"),
    setupUseRewrite: $("#setup-use-rewrite"),
    setupUseBrief: $("#setup-use-brief"),
    setupTranslationMode: $("#setup-translation-mode"),
    setupSttLanguage: $("#setup-stt-language"),
    setupMinimaxKey: $("#setup-minimax-key"),
    setupElevenlabsKey: $("#setup-elevenlabs-key"),
    setupVoicePreserve: $("#setup-voice-preserve"),
    setupVoiceMax: $("#setup-voice-max"),
    setupVoiceEngine: $("#setup-voice-engine"),
    setupVoiceExtreme: $("#setup-voice-extreme"),
    setupVoiceWarning: $("#setup-voice-warning"),
    setupVoiceEngines: $("#setup-voice-engines"),
    setupPacks: $("#setup-packs"),
    setupPacksRefresh: $("#setup-packs-refresh"),
    setupRightsLock: $("#setup-rights-lock"),
    firstRunNudge: $("#first-run-nudge"),
    firstRunSetup: $("#first-run-setup"),
    setupTestOpencode: $("#setup-test-opencode"),
    setupTestOpenrouter: $("#setup-test-openrouter"),
    setupTestStt: $("#setup-test-stt"),
    setupTestSttLive: $("#setup-test-stt-live"),
    setupTestTts: $("#setup-test-tts"),
    setupTestTtsLive: $("#setup-test-tts-live"),
    setupTtsAudio: $("#setup-tts-audio"),
    setupIngestProvider: $("#setup-ingest-provider"),
    setupYtdlpStatus: $("#setup-ytdlp-status"),
    setupYtdlpQuality: $("#setup-ytdlp-quality"),
    setupYtdlpCodec: $("#setup-ytdlp-codec"),
    setupYtdlpContainer: $("#setup-ytdlp-container"),
    setupYtdlpAudio: $("#setup-ytdlp-audio"),
    setupYtdlpCookies: $("#setup-ytdlp-cookies"),
    setupYtdlpBrowser: $("#setup-ytdlp-browser"),
    setupYtdlpBrowserField: $("#setup-ytdlp-browser-field"),
    setupYtdlpCookieFile: $("#setup-ytdlp-cookie-file"),
    setupYtdlpFileField: $("#setup-ytdlp-file-field"),
    setupYtdlpDetail: $("#setup-ytdlp-detail"),
    setupTestYtdlp: $("#setup-test-ytdlp"),
    setupXhsStatus: $("#setup-xhs-status"),
    setupXhsUrl: $("#setup-xhs-url"),
    setupXhsToken: $("#setup-xhs-token"),
    setupXhsNoRecord: $("#setup-xhs-no-record"),
    setupXhsInterval: $("#setup-xhs-interval"),
    setupXhsDetail: $("#setup-xhs-detail"),
    setupXhsOpen: $("#setup-xhs-open"),
    setupXhsCopy: $("#setup-xhs-copy"),
    setupXhsInvite: $("#setup-xhs-invite"),
    setupXhsCheck: $("#setup-xhs-check"),
    setupXhsCookie: $("#setup-xhs-cookie"),
    setupXhsSendCookie: $("#setup-xhs-send-cookie"),
    setupTestXhs: $("#setup-test-xhs"),
    dropzone: $("#dropzone"),
    urlForm: $("#url-form"),
    urlInput: $("#url-input"),
    urlGet: $("#url-get"),
    urlHint: $("#url-hint"),
    urlProviderLabel: $("#url-provider-label"),
    urlStatus: $("#url-status"),
    urlError: $("#url-error"),
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
    progressCancelUrl: $("#progress-cancel-url"),
    resultTitle: $("#result-title"),
    resultMeta: $("#result-meta"),
    resultReady: $("#result-ready"),
    resultReadyText: $("#result-ready-text"),
    resultReadyDownload: $("#result-ready-download"),
    speechNotice: $("#speech-notice"),
    speechNoticeDetail: $("#speech-notice-detail"),
    speechRetry: $("#speech-retry"),
    speechRetryStatus: $("#speech-retry-status"),
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
    planRoute: $("#plan-route"),
    shapeNote: $("#shape-note"),
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
    planReasoning: $("#plan-reasoning"),
    planReasoningBody: $("#plan-reasoning-body"),
    timeline: $("#timeline"),
    timelineDrop: $("#timeline-drop"),
    momentsSection: $("#moments-section"),
    momentsRail: $("#moments-rail"),
    momentsFull: $("#moments-full"),
    momentsList: $("#moments-list"),
    momentsExpand: $("#moments-expand"),
    render: $("#render"),
    clipMenu: $("#clip-menu"),
    renderDraft: $("#render-draft"),
    renderAll: $("#render-all"),
    renderAb: $("#render-ab"),
    presetSelect: $("#preset-select"),
    arcOrder: $("#arc-order"),
    renderCancel: $("#render-cancel"),
    aspect: $("#aspect-select"),
    captions: $("#captions"),
    textEffectsStep: $("#text-effects-step"),
    textShapeNote: $("#text-shape-note"),
    textLayerControls: $("#text-layer-controls"),
    textOverlayList: $("#text-overlay-list"),
    textOverlayText: $("#text-overlay-text"),
    textOverlayAnchor: $("#text-overlay-anchor"),
    textOverlayStart: $("#text-overlay-start"),
    textOverlayEnd: $("#text-overlay-end"),
    textOverlayAdd: $("#text-overlay-add"),
    effectList: $("#effect-list"),
    effectKind: $("#effect-kind"),
    effectDuration: $("#effect-duration"),
    effectAdd: $("#effect-add"),
    audioPanel: $("#audio-panel"),
    audioMode: $("#audio-mode"),
    audioModeTabs: $("#audio-mode-tabs"),
    audioModeDesc: $("#audio-mode-desc"),
    audioRewriteStep: $("#audio-rewrite-step"),
    audioCopyForm: $("#audio-copy-form"),
    audioCopyNote: $("#audio-copy-note"),
    audioCopyNoteText: $("#audio-copy-note-text"),
    audioCopySwitch: $("#audio-copy-switch"),
    audioVoiceStep: $("#audio-voice-step"),
    audioMusicStep: $("#audio-music-step"),
    audioMusicBlock: $("#audio-music-block"),
    audioMusicBlockBgm: $("#audio-music-block-bgm"),
    audioMusicBlockGenerate: $("#audio-music-block-generate"),
    audioRewriteRun: $("#audio-rewrite-run"),
    audioRewriteNote: $("#audio-rewrite-note"),
    translateBadge: $("#translate-badge"),
    copyTranscript: $("#copy-transcript"),
    audioVoiceGenerate: $("#audio-voice-generate"),
    audioVoiceUpload: $("#audio-voice-upload"),
    audioMusicSource: $("#audio-music-source"),
    audioTrackField: $("#audio-track-field"),
    audioMusicField: $("#audio-music-field"),
    audioVoicePreviewStatus: $("#audio-voice-preview-status"),
    audioMusicPreviewStatus: $("#audio-music-preview-status"),
    audioVoiceCost: $("#audio-voice-cost"),
    audioMusicCost: $("#audio-music-cost"),
    audioCopyCost: $("#audio-copy-cost"),
    audioVoiceUse: $("#audio-voice-use"),
    audioMusicUse: $("#audio-music-use"),
    audioMusicUploadBox: $("#audio-music-upload-box"),
    audioMusicUpload: $("#audio-music-upload"),
    audioMusicUploadButton: $("#audio-music-upload-button"),
    audioMusicUploadClear: $("#audio-music-upload-clear"),
    audioMusicUploadName: $("#audio-music-upload-name"),
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
    mixerOpen: $("#mixer-open"),
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
    audioGenerateVoice: $("#audio-generate-voice"),
    audioUseRecording: $("#audio-use-recording"),
    audioGenerateMusic: $("#audio-generate-music"),
    audioPlayMusic: $("#audio-play-music"),
    audioUseBgm: $("#audio-use-bgm"),
    audioStatus: $("#audio-status"),
    audioStatusSetup: $("#audio-status-setup"),
    audioScript: $("#audio-script"),
    renderNote: $("#render-note"),
    renderStale: $("#render-stale"),
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
    recentResume: $("#recent-resume"),
    recentCount: $("#recent-count"),
    recentError: $("#recent-error"),
    recentAll: $("#recent-all"),
    recentAllLabel: $("#recent-all-label"),
    recentAllCount: $("#recent-all-count"),
    recentAllPanel: $("#recent-all-panel"),
    recentAllList: $("#recent-all-list"),
    historyPanel: $("#history-panel"),
    historyCount: $("#history-count"),
    historyLatest: $("#history-latest"),
    historyList: $("#history-list"),
    historyDetail: $("#history-detail"),
    textScan: $("#text-scan"),
    textScanStatus: $("#text-scan-status"),
    textScanBadge: $("#text-scan-badge"),
    textScanProgress: $("#text-scan-progress"),
    textScanFill: $("#text-scan-fill"),
    textScanProgressText: $("#text-scan-progress-text"),
    textScanStart: $("#text-scan-start"),
    textScanCancel: $("#text-scan-cancel"),
    cleanStage: $("#clean-stage"),
    cleanCanvas: $("#clean-canvas"),
    cleanFrame: $("#clean-frame"),
    cleanOverlay: $("#clean-overlay"),
    cleanFrameState: $("#clean-frame-state"),
    cleanStageTime: $("#clean-stage-time"),
    cleanStageClip: $("#clean-stage-clip"),
    cleanScrub: $("#clean-scrub"),
    cleanScrubReadout: $("#clean-scrub-readout"),
    cleanDraw: $("#clean-draw"),
    cleanBrush: $("#clean-brush"),
    cleanUndo: $("#clean-undo"),
    cleanRedo: $("#clean-redo"),
    cleanRefresh: $("#clean-refresh"),
    cleanPanel: $("#clean-panel"),
    cleanCount: $("#clean-count"),
    cleanFound: $("#clean-found"),
    cleanLayers: $("#clean-layers"),
    cleanEmpty: $("#clean-empty"),
    cleanStatus: $("#clean-status"),
    cleanFillNote: $("#clean-fill-note"),
    cleanFill: $("#clean-fill"),
    cleanPreviewTime: $("#clean-preview-time"),
    cleanPreviewMoment: $("#clean-preview-moment"),
    cleanPreviewEngine: $("#clean-preview-engine"),
    cleanPreviewEta: $("#clean-preview-eta"),
    cleanPreviewBefore: $("#clean-preview-before"),
    cleanPreviewAfter: $("#clean-preview-after"),
    cleanPreviewPlay: $("#clean-preview-play"),
    cleanPreviewAi: $("#clean-preview-ai"),
    cleanPreviewBlur: $("#clean-preview-blur"),
    cleanPreviewExclude: $("#clean-preview-exclude"),
    cleanEmptyScanThis: $("#clean-empty-scan-this"),
    cleanEmptyScanVideo: $("#clean-empty-scan-video"),
    cleanHelp: $("#clean-help"),
    finishCut: $("#finish-cut"),
    shortcutsOpen: $("#shortcuts-open"),
    shortcutsSheet: $("#shortcuts-sheet"),
    shortcutsClose: $("#shortcuts-close"),
    momentsScan: $("#moments-scan"),
    rightsTick: $("#rights-tick"),
    rightsOwn: $("#rights-own"),
    drawer: $("#drawer"),
    drawerContent: $("#drawer-content"),
    toast: $("#toast"),
  };

  // One shape for the cut's text/effect/clean state, so a reset cannot drop a
  // field the editor reads back (the frame cache and undo stack live here).
  function freshClassicText() {
    return {
      loadedKey: "",
      dataKey: "",
      clipsHash: "",
      overlays: [],
      effects: [],
      clean: [],
      seq: 0,
      rev: 0,
      saveTimer: null,
      selection: "",
      drawMode: false,
      drawMethod: "blur",
      t: 0,
      undo: [],
      redo: [],
      frameTimer: null,
      frame: { url: "", key: "", busy: false, error: "", seq: 0, controller: null },
      // Ticks live in the panel, not the cut: they are a working choice for
      // "Remove ticked" and are cleared when the scan changes.
      foundTicks: new Set(),
      foundMethod: "fill",
      foundEngine: "",
      fillPreview: null,
      // The frame is cropped; boxes are stored in source space. The server
      // sends each segment's crop with its frame, keyed by segment position.
      crops: {},
    };
  }

  const state = {
    health: null,
    file: null,
    localPath: null,
    meta: null,
    fileName: "",
    urlBusy: false,
    urlButtonLabel: "",
    urlInspect: null,
    urlInspectUrl: "",
    ingestStatus: null,
    job: null,
    textScan: null,
    plan: null,
    setupSecrets: {},
    target: 30,
    aspect: "9:16",
    captions: false,
    classicText: freshClassicText(),
    fill: null,
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
    voiceSampleUrl: "",
    voiceSampleKey: "",
    voicePreviewBusy: false,
    musicPreviewUrl: "",
    musicPreviewKey: "",
    musicPreviewBusy: false,
    soundPlayer: null,
    audioEngines: null,
    mixer: { ready: false, total: 0, clips: [], original: [], music: [], voice: [], bed: [] },
    scriptOverrides: {},
    scriptId: null,
    lastScript: null,
    scriptAbort: null,
    scriptTimer: null,
    translation: null,
    translationWarm: null,
    history: [],
    historyEntry: null,
    recentJobs: [],
    recentSelectedId: "",
    recentOpened: {},
    recentExpanded: false,
    showLiteral: false,
    order: "source",
    preset: "",
    audioMoods: [],
    audioPromptAuto: "",
    overrideHook: null,
    rightsPolicy: null,
    editMode: false,
    editIndex: null,
    edited: false,
    cutDirty: false,
    momentsExpanded: false,
    trim: null,
    timelineScroll: 0,
    clipMenuIndex: null,
    clipMenuTrigger: null,
    playerScrollKey: null,
    renderWasActive: null,
    drawerScene: null,
    sort: "best",
    visible: 96,
    busy: false,
    pollTimer: null,
    pollStart: null,
    toastTimer: null,
    ingestJob: null,
    cancelRequested: false,
  };

  // The role menu and every reorder share one order: Hook, Beat, Payoff.
  const CLIP_ROLES = ["hook", "beat", "payoff"];
  const CLIP_ROLE_LABELS = { hook: "Hook", beat: "Beat", payoff: "Payoff" };

  // Native <select> popups on macOS ignore the page font size. The audio
  // controls open this list instead, at a readable 15px.
  const selectMenu = document.createElement("div");
  selectMenu.className = "select-menu";
  selectMenu.hidden = true;
  selectMenu.setAttribute("role", "listbox");
  document.body.appendChild(selectMenu);
  let menuSelect = null;

  function closeSelectMenu() {
    selectMenu.hidden = true;
    if (menuSelect) menuSelect.classList.remove("menu-open");
    menuSelect = null;
  }

  function openSelectMenu(select) {
    if (!select || select.disabled) return;
    menuSelect = select;
    selectMenu.innerHTML = [...select.options].map((option, index) => `
      <button type="button" role="option" data-index="${index}"
        class="${option.value === select.value ? "active" : ""}"
        ${option.disabled ? "disabled" : ""}>${esc(option.textContent)}</button>`).join("");
    selectMenu.hidden = false;
    select.classList.add("menu-open");
    const rect = select.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 240), window.innerWidth - 24);
    const spaceBelow = window.innerHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const openAbove = spaceBelow < 240 && spaceAbove > spaceBelow;
    const available = Math.max(160, openAbove ? spaceAbove : spaceBelow);
    selectMenu.style.maxHeight = `${Math.min(320, available)}px`;
    selectMenu.style.width = `${width}px`;
    selectMenu.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`;
    selectMenu.style.top = openAbove
      ? `${Math.max(8, rect.top - Math.min(320, available) - 4)}px`
      : `${rect.bottom + 4}px`;
    requestAnimationFrame(() => {
      const menuRect = selectMenu.getBoundingClientRect();
      if (menuRect.bottom > window.innerHeight - 8) {
        selectMenu.style.top = `${Math.max(8, rect.top - menuRect.height - 4)}px`;
      }
      if (menuRect.top < 8) selectMenu.style.top = "8px";
      selectMenu.querySelector(".active")?.scrollIntoView({ block: "nearest" });
    });
  }

  function enhanceSelect(select) {
    if (!select || select.dataset.enhanced) return;
    select.dataset.enhanced = "1";
    select.addEventListener("mousedown", (event) => {
      event.preventDefault();
      openSelectMenu(select);
    });
    select.addEventListener("keydown", (event) => {
      if (!["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      openSelectMenu(select);
    });
  }

  function enhanceAudioSelects() {
    [dom.audioLang, dom.audioStyle, dom.audioEngine, dom.audioVoice].forEach(enhanceSelect);
  }

  selectMenu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-index]");
    if (!button || !menuSelect) return;
    const option = menuSelect.options[Number(button.dataset.index)];
    if (!option) return;
    menuSelect.value = option.value;
    menuSelect.dispatchEvent(new Event("change", { bubbles: true }));
    const select = menuSelect;
    closeSelectMenu();
    select.focus();
  });
  document.addEventListener("mousedown", (event) => {
    if (event.target.closest("select[data-enhanced]")) return;
    if (!selectMenu.hidden && !event.target.closest(".select-menu")) closeSelectMenu();
  });
  window.addEventListener("scroll", (event) => {
    // Scrolling inside the open list must not close it.
    if (event.target?.closest?.(".select-menu")) return;
    closeSelectMenu();
  }, true);
  window.addEventListener("resize", closeSelectMenu);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSelectMenu();
  });

  window.VibeCutClassicHasUnsaved = () => Boolean(state.cutDirty);

  function init() {
    syncTokenCookie();
    state.recentOpened = readRecentOpened();
    bind();
    enhanceAudioSelects();
    updateUrlState();
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

  function syncYtdlpCookieFields() {
    if (!dom.setupYtdlpCookies) return;
    const mode = dom.setupYtdlpCookies.value;
    if (dom.setupYtdlpBrowserField) dom.setupYtdlpBrowserField.hidden = mode !== "browser";
    if (dom.setupYtdlpFileField) dom.setupYtdlpFileField.hidden = mode !== "file";
  }

  function renderSetupModelRoutes(workflows) {
    const target = $("#setup-model-routes");
    if (!target) return;
    target.replaceChildren();
    const labels = {
      story_brief: "Story brief",
      rewrite: "Script rewrite",
      translate: "Translation",
      hook_rank: "Hook ranking",
      script: "Silent-video script",
      tts: "Voice-over",
      music: "Music",
      stt: "Transcription",
    };
    Object.entries(labels).forEach(([name, label]) => {
      const value = workflows?.[name];
      if (!value) return;
      const row = document.createElement("div");
      row.className = "setup-model-row";
      const title = document.createElement("strong");
      title.textContent = label;
      const copy = document.createElement("span");
      const routes = (value.routes || []).map((route) => `${route.provider} · ${route.model}`);
      copy.textContent = routes.join("  →  ") || "No routes configured";
      copy.title = copy.textContent;
      const meta = document.createElement("small");
      meta.textContent = `${value.reasoning || "no reasoning"} · ${value.max_output_tokens || 0} tokens · ${value.timeout_s || 0}s`;
      row.append(title, copy, meta);
      target.append(row);
    });
  }

  function renderPlatformCapabilities() {
    const platform = state.health?.platform;
    if (!platform) return;
    const nativeStt = platform.native_stt === true;
    const nativeTts = platform.native_tts === true;
    const nativeVision = platform.native_vision === true;
    const rows = [
      ["STT / transcript", nativeStt ? "Native" : "Not native · check Setup"],
      ["TTS / voice", nativeTts ? "Native" : "Not native · check Setup"],
      ["Vision / text", nativeVision ? "Native" : "Not available · center crop"],
      ["Translation / rewrite", "See Setup routes"],
      ["Render", "Local"],
    ];
    if (dom.setupPlatformBadge) dom.setupPlatformBadge.textContent = dom.privacyLabel?.textContent || "AI";
    if (dom.setupPlatformSummary) {
      dom.setupPlatformSummary.textContent = `${platform.system || "unknown"} · ${platform.machine || "unknown"} · ${platform.apple_silicon ? "Apple Silicon" : "non-Apple-Silicon"}`;
    }
    if (dom.setupPlatformRows) {
      dom.setupPlatformRows.innerHTML = rows.map(([label, value]) => `
        <div class="setup-model-row"><strong>${esc(tr(label))}</strong><span>${esc(tr(value))}</span></div>
      `).join("");
    }
  }

  function updatePrivacyPill() {
    const trust = window.ClassicTrust;
    const label = trust && typeof trust.privacyLabel === "function"
      ? trust.privacyLabel({
        secrets: state.setupSecrets || {},
        voiceEngine: state.audio.engine || "",
        musicEngine: state.audio.music || "",
        musicSource: state.audio.musicSource || "",
        // OpenCode Go signs in without a saved key, and rewrite or translate
        // can still go online through it.
        onlineTranslation: translationMayUseCloudNow() || rewriteMayUseCloudNow(),
        platform: state.health?.platform || null,
      })
      : "Cloud AI";
    if (dom.privacyLabel) dom.privacyLabel.textContent = tr(label);
    dom.privacyPill?.classList.toggle("online", label === "Cloud AI" || label === "Mixed AI");
    renderPlatformCapabilities();
  }

  function updateVoiceFitWarning() {
    const preserve = dom.setupVoicePreserve?.checked !== false;
    if (dom.setupVoiceExtreme) {
      dom.setupVoiceExtreme.disabled = preserve;
      if (preserve) dom.setupVoiceExtreme.checked = false;
    }
    if (dom.setupVoiceMax) {
      for (const option of dom.setupVoiceMax.options) {
        const value = Number(option.value);
        if (Number.isFinite(value) && value > 1.25) option.disabled = preserve;
      }
      if (preserve && Number(dom.setupVoiceMax.value) > 1.25) {
        dom.setupVoiceMax.value = "1.25";
      }
      if (dom.setupVoiceExtreme?.checked) dom.setupVoiceMax.value = "2.50";
      else if (dom.setupVoiceMax.value === "2.50") dom.setupVoiceMax.value = "1.80";
    }
    if (!dom.setupVoiceWarning) return;
    if (preserve) {
      dom.setupVoiceWarning.hidden = true;
      dom.setupVoiceWarning.textContent = "";
      return;
    }
    dom.setupVoiceWarning.hidden = false;
    dom.setupVoiceWarning.textContent = dom.setupVoiceExtreme?.checked
      ? "Preserve voice is off. Speeds above 1.8× will raise the pitch sharply and may sound like a chipmunk."
      : "Preserve voice is off. Faster lines will raise the voice pitch and may create a chipmunk sound.";
  }

  function applySetup(data) {
    const settings = data.settings || {};
    const secrets = data.secrets || {};
    const sources = data.sources || {};
    const opencode = settings.opencode || {};
    dom.setupOpencodeEnabled.checked = opencode.enabled !== false;
    if (dom.setupOpencodeModel) dom.setupOpencodeModel.value = opencode.model || "";
    if (dom.setupOpencodeVariant) dom.setupOpencodeVariant.value = opencode.variant || "";
    renderSetupModelRoutes(settings.workflows || {});
    dom.setupUseRewrite.checked = opencode.use_rewrite !== false;
    dom.setupUseBrief.checked = opencode.use_brief !== false;
    dom.setupTranslationMode.value = (settings.translation || {}).mode || "auto";
    const voiceFit = settings.voice_fit || {};
    if (dom.setupVoicePreserve) dom.setupVoicePreserve.checked = voiceFit.preserve_pitch !== false;
    if (dom.setupVoiceMax) {
      const speed = Number(voiceFit.max_speed || 1.80);
      const value = [1.10, 1.15, 1.20, 1.25, 1.50, 1.80, 2.50]
        .find((item) => Math.abs(item - speed) < 0.005) || 1.80;
      dom.setupVoiceMax.value = value.toFixed(2);
    }
    if (dom.setupVoiceEngine) {
      dom.setupVoiceEngine.value = ["auto", "ffmpeg", "signalsmith"].includes(voiceFit.engine)
        ? voiceFit.engine : "auto";
    }
    if (dom.setupVoiceExtreme) dom.setupVoiceExtreme.checked = voiceFit.allow_extreme_speed === true;
    const runtime = data.runtime || {};
    if (dom.setupVoiceEngine) {
      const signalsmith = runtime.voice_fit?.signalsmith === true;
      const option = dom.setupVoiceEngine.querySelector('option[value="signalsmith"]');
      if (option) {
        option.disabled = !signalsmith;
        option.textContent = signalsmith
          ? "Signalsmith Stretch"
          : "Signalsmith Stretch · not installed";
      }
      if (!signalsmith && dom.setupVoiceEngine.value === "signalsmith") {
        dom.setupVoiceEngine.value = "auto";
      }
    }
    updateVoiceFitWarning();
    if (runtime.opencode_mode === "api") {
      dom.setupOpencodeStatus.textContent = "Direct OpenCode Go API key configured for this project · low reasoning.";
    } else if (runtime.opencode) {
      dom.setupOpencodeStatus.textContent = "Local OpenCode service ready · uses your OpenCode Go login · low reasoning.";
    } else {
      dom.setupOpencodeStatus.textContent = "No OpenCode key or service. Add a key here, or sign in with OpenCode, or use local MLX / Ollama.";
    }
    dom.setupOpencodeStatus.classList.toggle("warn", !runtime.opencode);
    dom.setupSttLanguage.value = (settings.stt || {}).language || "en";
    if (dom.setupRightsLock) dom.setupRightsLock.checked = (settings.rights || {}).lock !== false;
    const ingest = settings.ingest || {};
    dom.setupIngestProvider.value = ["auto", "ytdlp", "xhs"].includes(ingest.provider)
      ? ingest.provider : "auto";
    if (dom.urlProviderLabel) {
      dom.urlProviderLabel.textContent = `provider ${{
        auto: "auto",
        ytdlp: "yt-dlp",
        xhs: "XHS",
      }[dom.setupIngestProvider.value] || "auto"}`;
    }
    dom.setupYtdlpQuality.value = ["max", "2160", "1440", "1080", "720", "480", "360"].includes(ingest.ytdlp_quality)
      ? ingest.ytdlp_quality : "max";
    dom.setupYtdlpCodec.value = ingest.ytdlp_codec === "any" ? "any" : "h264";
    dom.setupYtdlpContainer.value = ["mp4", "mkv", "webm"].includes(ingest.ytdlp_container)
      ? ingest.ytdlp_container : "mp4";
    dom.setupYtdlpAudio.value = ["best", "192", "128"].includes(ingest.ytdlp_audio)
      ? ingest.ytdlp_audio : "best";
    dom.setupYtdlpCookies.value = ["none", "browser", "file"].includes(ingest.ytdlp_cookies)
      ? ingest.ytdlp_cookies : "none";
    dom.setupYtdlpBrowser.value = ["safari", "chrome", "chromium", "firefox", "edge", "brave", "opera", "vivaldi", "whale"].includes(ingest.ytdlp_browser)
      ? ingest.ytdlp_browser : "safari";
    dom.setupYtdlpCookieFile.value = ingest.ytdlp_cookie_file || "";
    syncYtdlpCookieFields();
    dom.setupXhsUrl.value = ingest.xhs_url || "";
    dom.setupXhsNoRecord.checked = ingest.xhs_no_record !== false;
    dom.setupXhsInterval.value = ingest.xhs_interval ?? 12;
    setSecretHint(dom.setupOpencodeKey, !!secrets.opencode, sources.opencode);
    setSecretHint(dom.setupOpenrouterKey, !!secrets.openrouter, sources.openrouter, true);
    setSecretHint(dom.setupMinimaxKey, !!secrets.minimax, sources.minimax);
    setSecretHint(dom.setupElevenlabsKey, !!secrets.elevenlabs, sources.elevenlabs);
    setSecretHint(dom.setupXhsToken, !!secrets.xhs, sources.xhs);
    [
      dom.setupOpencodeKey,
      dom.setupOpenrouterKey,
      dom.setupMinimaxKey,
      dom.setupElevenlabsKey,
      dom.setupXhsToken,
      dom.setupXhsCookie,
    ].forEach((input) => {
      if (input) input.value = "";
    });
    state.setup = settings;
    state.setupSecrets = secrets;
    updatePrivacyPill();
    renderSetupEngines();
    renderFirstRunNudge();
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
    await Promise.all([
      loadSetup(), loadIngestStatus(), loadAudioEngines(), loadPackStatus(),
    ]);
  }

  function closeSetup() {
    dom.setup.hidden = true;
  }

  function setupSecrets() {
    const values = {
      opencode: dom.setupOpencodeKey.value.trim(),
      openrouter: dom.setupOpenrouterKey.value.trim(),
      minimax: dom.setupMinimaxKey.value.trim(),
      elevenlabs: dom.setupElevenlabsKey?.value.trim() || "",
      xhs: dom.setupXhsToken.value.trim(),
    };
    return Object.fromEntries(Object.entries(values).filter(([, value]) => value));
  }

  const SETUP_VOICE_ORDER = [
    ["say", "Apple voices"],
    ["kokoro", "Kokoro"],
    ["heygen", "HeyGen Voice Turbo"],
    ["fish", "Fish Audio"],
    ["gemini", "Gemini TTS"],
    ["minimax", "MiniMax Speech"],
    ["elevenlabs", "ElevenLabs"],
  ];

  function renderSetupEngines() {
    if (!dom.setupVoiceEngines) return;
    const voices = state.audioEngines?.voices;
    if (!voices) {
      dom.setupVoiceEngines.innerHTML = '<p class="setup-hint">Voice engine status unavailable. Reopen Setup to check again.</p>';
      return;
    }
    dom.setupVoiceEngines.innerHTML = SETUP_VOICE_ORDER.map(([id, label]) => {
      const info = voices[id] || {};
      const ready = info.available === true;
      const detail = info.install || (ready ? "Ready." : "Needs setup.");
      return `
        <div class="setup-engine-row">
          <div><strong>${esc(label)}</strong><p class="setup-hint">${esc(detail)}</p></div>
          <span class="setup-chip ${ready ? "ok" : "warn"}">${ready ? "Ready" : "Needs setup"}</span>
        </div>`;
    }).join("");
  }

  async function loadPackStatus() {
    if (!dom.setupPacks) return;
    try {
      const data = await api("/api/classic/packs");
      const list = data.packs || [];
      if (!list.length) {
        dom.setupPacks.innerHTML = '<p class="setup-hint">No optional packs are listed in this build.</p>';
        return;
      }
      dom.setupPacks.innerHTML = list.map((pack) => {
        const installed = pack.installed === true;
        // Engines installed outside the pack (pip, Homebrew) already work.
        const usable = !installed && pack.usable === true;
        const size = Number(pack.installed_size || pack.size_bytes || 0);
        const detail = installed
          ? `${pack.installed_version || pack.version || ""} on disk${size ? ` · ${formatSize(size)}` : ""}.`
          : usable
            ? pack.usable_detail || "Already works on this Mac."
            : `Not on disk${size ? ` · ${formatSize(size)} download` : ""}. No install starts from Classic.`;
        const chip = installed ? "Installed" : usable ? "Ready" : "Not installed";
        return `
          <div class="setup-engine-row">
            <div><strong>${esc(pack.name || pack.id)}</strong><p class="setup-hint">${esc(detail)}</p></div>
            <span class="setup-chip ${installed || usable ? "ok" : "warn"}">${chip}</span>
          </div>`;
      }).join("");
    } catch (error) {
      dom.setupPacks.innerHTML = `<p class="setup-hint">${esc(error.message)}</p>`;
    }
  }

  function renderFirstRunNudge() {
    if (!dom.firstRunNudge) return;
    let saved = false;
    try { saved = localStorage.getItem("vibecut.setupSaved") === "1"; } catch (_) { saved = true; }
    const secrets = state.setupSecrets || {};
    const hasCloudKey = ["opencode", "openrouter", "minimax", "elevenlabs"]
      .some((name) => secrets[name] === true);
    dom.firstRunNudge.hidden = saved || hasCloudKey;
  }

  async function saveSetup() {
    dom.setupSave.disabled = true;
    dom.setupStatus.textContent = "Saving…";
    const pendingXhsCookie = dom.setupXhsCookie.value.trim();
    try {
      const opencode = {
        enabled: dom.setupOpencodeEnabled.checked,
        use_rewrite: dom.setupUseRewrite.checked,
        use_brief: dom.setupUseBrief.checked,
        use_translate: dom.setupTranslationMode.value !== "local_only",
      };
      if (dom.setupOpencodeModel?.value.trim()) opencode.model = dom.setupOpencodeModel.value.trim();
      if (dom.setupOpencodeVariant?.value) opencode.variant = dom.setupOpencodeVariant.value;
      const payload = {
        settings: {
          opencode,
          translation: {
            mode: dom.setupTranslationMode.value,
          },
          stt: {
            language: dom.setupSttLanguage.value,
          },
          rights: {
            lock: false,
          },
          voice_fit: {
            preserve_pitch: dom.setupVoicePreserve ? dom.setupVoicePreserve.checked : true,
            max_speed: Number(dom.setupVoiceMax?.value || 1.80),
            engine: dom.setupVoiceEngine?.value || "auto",
            allow_extreme_speed: dom.setupVoiceExtreme?.checked === true,
          },
          ingest: {
            provider: dom.setupIngestProvider.value || "auto",
            ytdlp_quality: dom.setupYtdlpQuality.value || "max",
            ytdlp_codec: dom.setupYtdlpCodec.value || "h264",
            ytdlp_container: dom.setupYtdlpContainer.value || "mp4",
            ytdlp_audio: dom.setupYtdlpAudio.value || "best",
            ytdlp_cookies: dom.setupYtdlpCookies.value || "none",
            ytdlp_browser: dom.setupYtdlpBrowser.value || "safari",
            ytdlp_cookie_file: dom.setupYtdlpCookieFile.value.trim(),
            xhs_url: dom.setupXhsUrl.value.trim(),
            xhs_no_record: dom.setupXhsNoRecord.checked,
            xhs_interval: readInterval(dom.setupXhsInterval.value, 12),
          },
        },
        secrets: setupSecrets(),
      };
      const data = await api("/api/settings", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (pendingXhsCookie) {
        await api("/api/ingest/xhs/cookie", {
          method: "POST",
          body: JSON.stringify({ cookie: pendingXhsCookie }),
        });
      }
      applySetup(data);
      try { localStorage.setItem("vibecut.setupSaved", "1"); } catch (_) { /* ignore */ }
      dom.setupStatus.textContent = "Saved. Local fallback still active.";
      toast("Setup saved.");
      await loadIngestStatus(true);
      await loadAudioEngines();
      await loadPackStatus();
      renderFirstRunNudge();
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

  function setSetupChip(element, text, tone = "", title = "") {
    if (!element) return;
    element.textContent = text;
    element.classList.toggle("ok", tone === "ok");
    element.classList.toggle("warn", tone === "warn");
    element.title = title || text;
  }

  function applyYtdlpStatus(entry) {
    const value = entry && typeof entry === "object" ? entry : {};
    const error = String(value.error || "").trim();
    const version = String(value.version || "").trim();
    if (value.available === true) {
      setSetupChip(dom.setupYtdlpStatus, version ? `Ready · ${version}` : "Ready", "ok", error);
      if (dom.setupYtdlpDetail) {
        dom.setupYtdlpDetail.textContent = `Native yt-dlp${version ? ` ${version}` : ""} is ready. No sidecar needed.`;
        dom.setupYtdlpDetail.classList.remove("warn");
      }
      return;
    }
    setSetupChip(dom.setupYtdlpStatus, value.configured === false ? "Unavailable" : "Not ready", "warn", error);
    if (dom.setupYtdlpDetail) {
      dom.setupYtdlpDetail.textContent = error || "Install yt-dlp from requirements.txt.";
      dom.setupYtdlpDetail.classList.add("warn");
    }
  }

  function applyXhsStatus(entry) {
    const value = entry && typeof entry === "object" ? entry : {};
    const session = value.session && typeof value.session === "object" ? value.session : {};
    const cookieSet = !!(value.cookie_set ?? session.cookie_set);
    const sessionRaw = value.session_ok !== undefined ? value.session_ok : session.session_ok;
    const sessionOk = sessionRaw === true ? true : sessionRaw === false ? false : null;
    const user = String(value.user || session.user || "").trim();
    const error = String(value.error || "").trim();
    const tokenProblem = /token/i.test(error)
      && /(missing|invalid|required|not set|unauthori[sz]ed|forbidden|401|403)/i.test(error);
    const offline = /not reachable|connection refused|unreachable|timed? out|network|failed to connect|start xhs/i.test(error);
    const configured = value.configured !== false
      && !!(value.service_url || value.configured || value.id || value.label);
    let text = "Not checked";
    let tone = "";
    let detail = "Open sign-in, scan the QR code in xhs_get, then Check session.";

    if (value.available === true) {
      text = sessionOk === false ? "Session expired" : cookieSet ? "Cookie set · signed in" : "Reachable";
      tone = sessionOk === false ? "warn" : "ok";
      detail = user
        ? `Signed in to xhs_get as ${user}. The cookie stays in xhs_get.`
        : "Cookie set in xhs_get. VibeCut never stores it.";
    } else if (configured === false) {
      text = "Not set";
      tone = "warn";
      detail = error || "Set the XHS service URL, then save.";
    } else if (error || value.available === false) {
      if (tokenProblem) text = "Needs token";
      else if (offline) text = "Offline";
      else if (!cookieSet) text = "No cookie";
      else if (sessionOk === false) text = "Session expired";
      else text = "Offline";
      tone = "warn";
      detail = error || (cookieSet
        ? "xhs_get is not reachable. Check the service URL."
        : "No signed-in cookie. Use Open sign-in, then Check session.");
    }

    setSetupChip(dom.setupXhsStatus, text, tone, error);
    if (dom.setupXhsDetail) {
      dom.setupXhsDetail.textContent = detail;
      dom.setupXhsDetail.classList.toggle("warn", tone === "warn");
    }
  }

  function applyIngestStatus(data) {
    state.ingestStatus = data || null;
    const providers = data && typeof data === "object" ? (data.providers || data) : {};
    if (providers.ytdlp) applyYtdlpStatus(providers.ytdlp);
    if (providers.xhs) applyXhsStatus(providers.xhs);
  }

  async function loadIngestStatus(quiet = false) {
    try {
      const data = await api("/api/ingest/status");
      applyIngestStatus(data);
      return data;
    } catch (error) {
      setSetupChip(dom.setupYtdlpStatus, "Status unavailable", "warn", error.message);
      setSetupChip(dom.setupXhsStatus, "Status unavailable", "warn", error.message);
      if (!quiet && dom.setupStatus) dom.setupStatus.textContent = error.message;
      return null;
    }
  }

  async function testIngest(kind, button) {
    const old = button.textContent;
    button.disabled = true;
    button.textContent = "Testing…";
    dom.setupStatus.textContent = "";
    try {
      const result = await api("/api/settings/test", {
        method: "POST",
        body: JSON.stringify({ kind }),
      });
      if (kind === "ytdlp") {
        applyYtdlpStatus(result.status || result);
      } else {
        applyXhsStatus(result);
      }
      const seconds = result.seconds !== undefined ? ` · ${result.seconds}s` : "";
      dom.setupStatus.textContent = `${result.detail || (result.ok ? "Reachable." : "Not ready.")}${seconds}`;
      toast(result.ok
        ? `${result.label || kind} is reachable.`
        : `${result.label || kind} is not ready.`);
    } catch (error) {
      dom.setupStatus.textContent = error.message;
      if (kind === "ytdlp") {
        setSetupChip(dom.setupYtdlpStatus, "Unavailable", "warn", error.message);
        if (dom.setupYtdlpDetail) dom.setupYtdlpDetail.textContent = error.message;
      } else {
        setSetupChip(dom.setupXhsStatus, "Offline", "warn", error.message);
        if (dom.setupXhsDetail) dom.setupXhsDetail.textContent = error.message;
      }
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  }

  async function sendXhsCookie() {
    const cookie = dom.setupXhsCookie.value.trim();
    if (!cookie) {
      dom.setupXhsDetail.textContent = "Paste a RedNote cookie first.";
      return;
    }
    dom.setupXhsSendCookie.disabled = true;
    dom.setupXhsDetail.textContent = "Sending cookie to xhs_get…";
    try {
      await api("/api/ingest/xhs/cookie", {
        method: "POST",
        body: JSON.stringify({
          cookie,
          url: dom.setupXhsUrl.value.trim(),
          token: dom.setupXhsToken.value.trim(),
        }),
      });
      dom.setupXhsCookie.value = "";
      dom.setupXhsDetail.textContent = "Cookie accepted by xhs_get. Checking session…";
      await checkXhsSession(dom.setupXhsCheck);
    } catch (error) {
      dom.setupXhsDetail.textContent = error.message;
    } finally {
      dom.setupXhsSendCookie.disabled = false;
    }
  }

  async function checkXhsSession(button) {
    const old = button.textContent;
    button.disabled = true;
    button.textContent = "Checking…";
    dom.setupStatus.textContent = "";
    try {
      const data = await api("/api/ingest/xhs/check", {
        method: "POST",
        body: JSON.stringify({
          url: dom.setupXhsUrl.value.trim(),
          token: dom.setupXhsToken.value.trim(),
        }),
      });
      const xhs = data.status || {};
      dom.setupStatus.textContent = xhs.available
        ? "XHS session is ready."
        : (xhs.error || "XHS is not ready. Open sign-in, then retry.");
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  }

  function xhsServiceUrl() {
    const saved = state.ingestStatus?.providers?.xhs?.service_url
      || state.ingestStatus?.xhs?.service_url
      || "";
    return httpUrl(dom.setupXhsUrl.value) || httpUrl(saved);
  }

  async function xhsLoginUrl() {
    const fallback = xhsServiceUrl();
    if (!fallback) return "";
    try {
      const data = await api("/api/ingest/xhs/invite", {
        method: "POST",
        body: JSON.stringify({
          url: dom.setupXhsUrl.value.trim(),
          token: dom.setupXhsToken.value.trim(),
        }),
      });
      return httpUrl(data.url) || fallback;
    } catch (_) {
      return fallback;
    }
  }

  async function openXhsSignIn() {
    const url = await xhsLoginUrl();
    if (!url) {
      dom.setupStatus.textContent = "Set the XHS / RedNote service URL first.";
      dom.setupXhsUrl.focus();
      return;
    }
    window.open(url, "_blank", "noopener");
  }

  async function copyXhsInvite() {
    const url = await xhsLoginUrl();
    if (!url) {
      dom.setupXhsDetail.textContent = "Set the XHS / RedNote service URL first.";
      return;
    }
    copyText(url, "XHS login link copied.");
  }

  function copyXhsServiceUrl() {
    copyText(xhsServiceUrl(), "XHS service URL copied.");
  }

  function httpUrl(value) {
    try {
      const parsed = new URL(String(value || "").trim());
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
    } catch (_) {
      return "";
    }
  }

  function readInterval(value, fallback) {
    const text = String(value ?? "").trim();
    if (!text) return fallback;
    const number = Number(text);
    return Number.isFinite(number) && number >= 0 ? number : fallback;
  }

  function bindSetup() {
    dom.setupOpen.addEventListener("click", openSetup);
    dom.setupClose.addEventListener("click", closeSetup);
    dom.setup.querySelectorAll("[data-setup-close]").forEach((node) => {
      node.addEventListener("click", closeSetup);
    });
    dom.setupSave.addEventListener("click", saveSetup);
    dom.setupVoicePreserve?.addEventListener("change", updateVoiceFitWarning);
    dom.setupVoiceExtreme?.addEventListener("change", updateVoiceFitWarning);
    dom.setupVoiceEngine?.addEventListener("change", updateVoiceFitWarning);
    dom.setupVoiceMax?.addEventListener("change", () => {
      if (dom.setupVoiceMax.value === "2.50" && dom.setupVoicePreserve?.checked === false) {
        dom.setupVoiceExtreme.checked = true;
      }
      updateVoiceFitWarning();
    });
    dom.setupTestOpencode.addEventListener("click", () => testSetup("opencode", dom.setupTestOpencode));
    dom.setupTestOpenrouter.addEventListener("click", () => testSetup("openrouter", dom.setupTestOpenrouter));
    dom.setupTestStt.addEventListener("click", () => testSetup("stt", dom.setupTestStt));
    dom.setupTestSttLive.addEventListener("click", () => testSetup(
      "stt_live", dom.setupTestSttLive, { provider: "auto" },
    ));
    dom.setupTestTts.addEventListener("click", () => testSetup("tts", dom.setupTestTts));
    dom.setupTestTtsLive.addEventListener("click", () => testSetup(
      "tts_live", dom.setupTestTtsLive, { engine: "auto" },
    ));
    dom.setupTestYtdlp.addEventListener("click", () => testIngest("ytdlp", dom.setupTestYtdlp));
    dom.setupYtdlpCookies.addEventListener("change", syncYtdlpCookieFields);
    dom.setupTestXhs.addEventListener("click", () => testIngest("xhs", dom.setupTestXhs));
    dom.setupXhsCheck.addEventListener("click", () => checkXhsSession(dom.setupXhsCheck));
    dom.setupXhsSendCookie.addEventListener("click", sendXhsCookie);
    dom.setupXhsOpen.addEventListener("click", openXhsSignIn);
    dom.setupXhsCopy.addEventListener("click", copyXhsServiceUrl);
    dom.setupXhsInvite.addEventListener("click", copyXhsInvite);
    dom.setupPacksRefresh?.addEventListener("click", loadPackStatus);
    dom.firstRunSetup?.addEventListener("click", openSetup);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !dom.setup.hidden) closeSetup();
      if (event.key === "Escape") closeClipMenu({ restoreFocus: true });
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest("#clip-menu") && !event.target.closest("[data-role-index]")) {
        closeClipMenu();
      }
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
        syncTokenCookie();
        config.__retried = true;
        return api(path, config);
      }
    }
    if (!response.ok) {
      let detail = response.statusText || "Request failed";
      let payload = null;
      try {
        payload = await response.json();
        detail = payload.detail || payload.message || payload.error || detail;
      } catch (_) { /* ignore */ }
      const normalized = typeof detail === "string" ? detail : (
        detail && typeof detail.message === "string"
          ? detail.message
          : JSON.stringify(detail)
      );
      const error = new Error(normalized);
      error.status = response.status;
      error.detail = detail;
      error.code = detail && typeof detail === "object" ? detail.code : null;
      error.payload = payload;
      throw error;
    }
    return response.json();
  }

  function tokenValue() {
    try { return localStorage.getItem("vibecut_token") || ""; } catch (_) { return ""; }
  }

  // Media elements cannot send headers. The token rides in a SameSite=Strict
  // cookie the server accepts for reads only; it never goes in a URL.
  function syncTokenCookie() {
    const token = tokenValue();
    const value = token ? encodeURIComponent(token) : "";
    const expiry = token ? "" : "; Max-Age=0";
    document.cookie = `vibecut_token=${value}; Path=/; SameSite=Strict${expiry}`;
  }

  function withToken(url) {
    return url;
  }

  // The rights lock is a Setup setting. While it is on, the server refuses an
  // import without the own-footage tick, so Classic asks for it first.
  // C4: the tick lives beside Start instead of a blocking dialog. It appears
  // only when the Setup rights lock asks for one, and a start that forgets it
  // points at the tick rather than cancelling silently.
  async function importRights() {
    // Classic has no attestation step. The founder is responsible for the
    // footage; the server does not gate the import.
    if (dom.rightsTick) dom.rightsTick.hidden = true;
    return null;
  }

  async function syncRightsTick() {
    if (dom.rightsTick) dom.rightsTick.hidden = true;
  }

  function uploadFile(file, options, onProgress, rights = null) {
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
      if (rights !== null) form.append("rights", rights ? "true" : "false");
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
      const platform = health.platform || {};
      const anyNative = platform.native_stt || platform.native_tts || platform.native_vision;
      const mode = platform.native_ai ? "on-device" : (anyNative ? "mixed" : "AI not configured");
      dom.footerHealth.textContent = tr(`${mode} · ${health.vision ? "apple vision" : "center crop"}`);
      updatePrivacyPill();
      renderPlatformCapabilities();
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

  const LIVE_JOB_STATUS = new Set(["queued", "downloading", "scanning", "reading", "scoring"]);
  const RECENT_OPENED_KEY = "vibecut.classic.opened";

  function readRecentOpened() {
    try {
      const raw = JSON.parse(localStorage.getItem(RECENT_OPENED_KEY) || "{}");
      if (!raw || typeof raw !== "object") return {};
      return Object.fromEntries(
        Object.entries(raw)
          .map(([id, stamp]) => [id, Number(stamp) || 0])
          .filter(([, stamp]) => stamp > 0)
          .slice(-80),
      );
    } catch (_) {
      return {};
    }
  }

  function rememberRecentOpened(id) {
    if (!id) return;
    state.recentOpened[id] = Math.floor(Date.now() / 1000);
    try {
      localStorage.setItem(RECENT_OPENED_KEY, JSON.stringify(state.recentOpened));
    } catch (_) { /* storage may be unavailable; the in-memory map still works */ }
  }

  function printRecentTime(timestamp) {
    const value = Number(timestamp);
    if (!value) return "";
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - value));
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))}m ago`;
    const date = new Date(value * 1000);
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }
    return formatDate(value);
  }

  function recentOpenedLabel(job) {
    const opened = state.recentOpened[job.id];
    if (opened) return `Opened ${printRecentTime(opened)}`;
    return `Added ${formatDate(job.created)}`;
  }

  function recentGroupOpened(group) {
    const stamps = group.jobs.map((job) => state.recentOpened[job.id] || 0);
    const newest = Math.max(0, ...stamps);
    const job = group.jobs[0];
    if (newest) return `Opened ${printRecentTime(newest)}`;
    return `Added ${formatDate(job.created)}`;
  }

  function recentLabel(name) {
    let label = fileStem(name).replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    label = label
      .replace(/^(en|cn|vi|ja|ko|es|fr|de|pt|it|ru|hi|th|id|tr|ar)\s+/i, "")
      .replace(/\b\d{2,4}x\d{2,4}\b/gi, " ")
      .replace(/\b\d+s\b/gi, " ")
      .replace(/\b(sub|subs|subtitle|subtitles|subtitle?d|final|draft)\b/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
    return label || fileStem(name);
  }

  function groupRecent(jobs) {
    const groups = new Map();
    jobs.forEach((job) => {
      const key = String(job.name || "Untitled video").trim().toLowerCase();
      if (!groups.has(key)) groups.set(key, { name: job.name || "Untitled video", jobs: [] });
      groups.get(key).jobs.push(job);
    });
    return [...groups.values()];
  }

  function recentStatus(job) {
    const failed = job.status === "failed";
    const progress = Math.max(0, Math.min(1, Number(job.progress) || 0));
    const status = job.status === "ready"
      ? "ready"
      : failed
        ? "failed"
        : job.status === "downloading"
          ? "downloading"
          : job.status === "queued"
            ? "queued"
            : `${Math.round(progress * 100)}%`;
    const statusText = failed
      ? job.message || "Ingest failed"
      : job.scene_count
        ? `${job.scene_count} moments`
        : job.message || (job.status === "ready" ? "ready" : "queued");
    return { failed, status, statusText, progress };
  }

  function recentDeleteBlock(job) {
    if (job.status === "downloading") return "Cancel download first.";
    if (LIVE_JOB_STATUS.has(job.status)) return "This job is still working.";
    return "";
  }

  function recentThumb(job, cls = "recent-thumb") {
    if (job.hook_thumb) {
      return `<span class="${cls}"><img src="${esc(withToken(job.hook_thumb))}" alt="" loading="lazy"></span>`;
    }
    return `<span class="${cls}"><span class="empty">${job.scene_count ? `${job.scene_count} moments` : "working"}</span></span>`;
  }

  async function loadRecent() {
    try {
      const data = await api("/api/jobs");
      const jobs = data.jobs || [];
      state.recentJobs = jobs;
      if (state.job?.id) state.recentSelectedId = state.job.id;
      if (state.recentSelectedId && !jobs.some((job) => job.id === state.recentSelectedId)) {
        state.recentSelectedId = "";
      }
      clearRecentError();
      if (!jobs.length) {
        dom.recentSection.hidden = true;
        dom.recentCount.textContent = "";
        dom.recentResume.innerHTML = "";
        dom.recent.innerHTML = "";
        dom.recentAllPanel.hidden = true;
        dom.recentAll.hidden = true;
        return;
      }
      const groups = groupRecent(jobs);
      const openedId = Object.entries(state.recentOpened)
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .map(([id]) => id)
        .find((id) => jobs.some((job) => job.id === id));
      const resumeId = openedId || jobs[0].id;
      const resume = groups.find((group) => group.jobs.some((job) => job.id === resumeId)) || groups[0];
      const resumeJob = resume.jobs.find((job) => job.id === resumeId) || resume.jobs[0];
      const rest = groups.filter((group) => group !== resume);
      dom.recentSection.hidden = false;
      dom.recentCount.textContent = tr(`${jobs.length} cut${jobs.length === 1 ? "" : "s"} · ${groups.length} source${groups.length === 1 ? "" : "s"}`);
      dom.recentResume.hidden = !resume;
      dom.recentResume.innerHTML = resume ? resumeCard(resume, resumeJob) : "";
      dom.recent.innerHTML = rest.slice(0, 5).map(recentCard).join("");
      dom.recentAll.hidden = jobs.length <= 1;
      dom.recentAllCount.textContent = `(${jobs.length})`;
      if (jobs.length <= 1) state.recentExpanded = false;
      dom.recentAllPanel.hidden = !state.recentExpanded;
      dom.recentAll.setAttribute("aria-expanded", state.recentExpanded ? "true" : "false");
      dom.recentAllLabel.textContent = state.recentExpanded ? "Hide all cuts" : "View all cuts";
      dom.recentAllList.innerHTML = recentAllList(groups);
    } catch (_) {
      state.recentJobs = [];
      dom.recentSection.hidden = true;
      dom.recentCount.textContent = "";
    }
  }

  function resumeCard(group, job = group.jobs[0]) {
    const count = group.jobs.length;
    return `
      <button type="button" class="recent-resume-card${state.recentSelectedId === job.id ? " selected" : ""}" data-id="${esc(job.id)}" aria-pressed="${state.recentSelectedId === job.id ? "true" : "false"}">
        ${recentThumb(job, "recent-resume-thumb")}
        <span class="recent-resume-copy">
          <span class="resume-kicker">Resume last cut</span>
          <strong title="${esc(job.name || "Untitled video")}">${esc(recentLabel(job.name))}</strong>
          <span class="recent-resume-meta">${esc(recentOpenedLabel(job))} · ${esc(fmtDuration(job.duration))} · ${count} cut${count === 1 ? "" : "s"}</span>
        </span>
        <span class="resume-cta">Open cut →</span>
      </button>`;
  }

  function recentCard(group) {
    const job = group.jobs[0];
    const count = group.jobs.length;
    const { failed, status, statusText } = recentStatus(job);
    const error = String(job.error || job.ingest_error || (failed ? job.message : "") || "").trim();
    const selected = state.recentSelectedId === job.id || state.job?.id === job.id;
    return `
      <div class="recent-item">
        <button type="button" class="recent-card${selected ? " selected" : ""}" data-id="${esc(job.id)}" aria-pressed="${selected ? "true" : "false"}">
          ${recentThumb(job)}
          ${count > 1 ? `<span class="recent-count-pill">${count} cuts</span>` : ""}
          <span class="recent-copy">
            <strong title="${esc(job.name || "Untitled video")}">${esc(recentLabel(job.name))}</strong>
            <span>${esc(recentGroupOpened(group))}</span>
          </span>
          <span class="recent-status">
            <span class="recent-status-text">${esc(statusText)}</span>
            <span class="dot${failed ? " failed" : LIVE_JOB_STATUS.has(job.status) ? " live" : ""}">${esc(status)}</span>
          </span>
          ${error ? `<span class="recent-error" title="${esc(error)}">${esc(error)}</span>` : ""}
        </button>
      </div>`;
  }

  function recentAllList(groups) {
    return groups.map((group) => {
      const count = group.jobs.length;
      const rows = group.jobs.map((job) => {
        const { failed, status, statusText } = recentStatus(job);
        const blockReason = recentDeleteBlock(job);
        const deleteLabel = blockReason ? `Delete ${job.name}: ${blockReason}` : `Delete ${job.name}`;
        return `
          <div class="recent-all-row">
            <button type="button" class="recent-all-open" data-id="${esc(job.id)}">
              ${recentThumb(job, "recent-all-thumb")}
              <span class="recent-all-copy">
                <strong>${esc(recentLabel(job.name))}</strong>
                <span>${esc(recentOpenedLabel(job))} · ${esc(statusText)}${count > 1 ? " · version" : ""}</span>
              </span>
              <span class="recent-all-state${failed ? " failed" : ""}">${esc(status)}</span>
            </button>
            <button type="button" class="recent-delete" data-delete-id="${esc(job.id)}"
              ${blockReason ? `data-delete-blocked="${esc(blockReason)}" aria-disabled="true"` : ""}
              aria-label="${esc(deleteLabel)}" title="${esc(blockReason || deleteLabel)}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>
            </button>
          </div>`;
      }).join("");
      return `<div class="recent-all-group">
        ${count > 1 ? `<p class="recent-all-group-title">${esc(recentLabel(group.name))} · ${count} cuts</p>` : ""}
        ${rows}
      </div>`;
    }).join("");
  }

  function syncRecentSelection(id) {
    state.recentSelectedId = id || "";
    $$(".recent-card, .recent-resume-card", dom.recentSection).forEach((card) => {
      const selected = card.dataset.id === id;
      card.classList.toggle("selected", selected);
      card.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    $$(".recent-all-open", dom.recentSection).forEach((row) => {
      row.classList.toggle("selected", row.dataset.id === id);
    });
  }

  async function deleteRecentJob(id, button) {
    const job = state.recentJobs.find((item) => item.id === id);
    if (!job) return;
    const name = job.name || "this cut";
    if (!confirm(`Delete “${name}” and its rendered reels?`)) return;
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    }
    clearRecentError();
    try {
      await api(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.job?.id === id) {
        state.recentSelectedId = "";
        resetToIngest();
      } else {
        await loadRecent();
      }
      toast("Job deleted.");
    } catch (error) {
      const message = error.message || "Could not delete this cut.";
      showRecentError(message);
      toast(message);
    } finally {
      if (button) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      }
    }
  }

  function showRecentError(message) {
    if (!dom.recentError) return;
    dom.recentError.textContent = message || "Could not delete this cut.";
    dom.recentError.hidden = false;
  }

  function clearRecentError() {
    if (!dom.recentError) return;
    dom.recentError.textContent = "";
    dom.recentError.hidden = true;
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
    dom.urlForm.addEventListener("submit", submitUrl);
    dom.urlInput.addEventListener("input", () => {
      if (state.urlInspect && dom.urlInput.value.trim() !== state.urlInspectUrl) {
        resetUrlInspect();
      }
    });
    dom.analyze.addEventListener("click", startAnalysis);
    dom.optCrop.addEventListener("change", syncOptions);
    dom.progressBack.addEventListener("click", resetToIngest);
    dom.progressCancelUrl.addEventListener("click", async () => {
      if (!state.ingestJob) return;
      state.cancelRequested = true;
      dom.progressCancelUrl.disabled = true;
      dom.progressCancelUrl.textContent = "Cancelling…";
      try {
        await api(`/api/jobs/${state.ingestJob}/url/cancel`, { method: "POST" });
      } catch (error) {
        showProgressError(error.message);
      }
    });
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
      setMomentsExpanded(true, { scroll: false });
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
      updateTextAvailability();
      updateRenderPanel();
      if (state.plan) {
        renderScenes();
        renderHook();
      }
    });
    dom.presetSelect.addEventListener("change", applyPreset);
    dom.arcOrder.addEventListener("change", async () => {
      state.order = dom.arcOrder.checked ? "arc" : "source";
      state.edited = false;
      state.cutDirty = false;
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
    bindTextScan();
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
    bindClassicText();
    bindClean();
    bindChrome();
    updateTextAvailability();
    document.addEventListener("keydown", (event) => {
      if (dom.result.hidden || !state.plan) return;
      cleanShortcut(event);
    });
    bindSetup();

    dom.timeline.addEventListener("contextmenu", (event) => {
      const clip = event.target.closest(".clip[data-index]");
      if (!clip) return;
      event.preventDefault();
      openClipMenu(
        Number(clip.dataset.index),
        event.clientX,
        event.clientY,
        clip.querySelector("[data-role-index]"),
      );
    });
    dom.clipMenu.addEventListener("keydown", (event) => {
      const buttons = [...dom.clipMenu.querySelectorAll("[data-clip-role]")];
      if (!buttons.length) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeClipMenu({ restoreFocus: true });
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.stopPropagation();
        return;
      }
      const current = buttons.indexOf(document.activeElement);
      let next = null;
      if (event.key === "ArrowDown") next = (current + 1 + buttons.length) % buttons.length;
      else if (event.key === "ArrowUp") next = (current - 1 + buttons.length) % buttons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else if (event.key === "Tab") {
        closeClipMenu();
        return;
      }
      if (next === null) return;
      event.preventDefault();
      buttons[next].focus();
    });
    dom.timeline.addEventListener("click", (event) => {
      if (event.target.closest(".trim-handle")) return;
      const role = event.target.closest("[data-role-index]");
      if (role) {
        event.preventDefault();
        event.stopPropagation();
        const rect = role.getBoundingClientRect();
        openClipMenu(Number(role.dataset.roleIndex), rect.left, rect.bottom + 6, role);
        return;
      }
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
    dom.speechRetry?.addEventListener("click", retrySpeech);
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
      const toggle = event.target.closest("[data-moment-toggle]");
      if (toggle) {
        event.preventDefault();
        event.stopPropagation();
        toggleMomentSelection(Number(toggle.dataset.momentToggle));
        return;
      }
      const card = event.target.closest("[data-moment-scene]");
      if (card) openDrawer(Number(card.dataset.momentScene));
    });
    dom.momentsList.addEventListener("click", (event) => {
      const toggle = event.target.closest("[data-moment-toggle]");
      if (toggle) {
        event.preventDefault();
        event.stopPropagation();
        toggleMomentSelection(Number(toggle.dataset.momentToggle));
        return;
      }
      const row = event.target.closest("[data-moment-scene]");
      if (row) openDrawer(Number(row.dataset.momentScene));
    });
    const momentKeydown = (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("[data-moment-toggle]")) return;
      const card = event.target.closest("[data-moment-scene]");
      if (!card || card !== event.target) return;
      event.preventDefault();
      event.stopPropagation();
      openDrawer(Number(card.dataset.momentScene));
    };
    dom.momentsRail.addEventListener("keydown", momentKeydown);
    dom.momentsList.addEventListener("keydown", momentKeydown);
    const momentSelectPointer = (event) => {
      if (event.target.closest("[data-moment-toggle]")) event.stopPropagation();
    };
    dom.momentsRail.addEventListener("pointerdown", momentSelectPointer);
    dom.momentsList.addEventListener("pointerdown", momentSelectPointer);
    dom.momentsList.addEventListener("dragstart", (event) => {
      if (event.target.closest("[data-moment-toggle]")) {
        event.preventDefault();
        return;
      }
      const row = event.target.closest("[data-moment-scene]");
      if (!row) return;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-vibecut-scene", row.dataset.momentScene);
      dom.timelineDrop.hidden = false;
    });
    dom.momentsList.addEventListener("dragend", () => {
      dom.timelineDrop.hidden = true;
    });
    dom.momentsRail.addEventListener("dragstart", (event) => {
      if (event.target.closest("[data-moment-toggle]")) {
        event.preventDefault();
        return;
      }
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
      dom.momentsRail.hidden = state.momentsExpanded;
      dom.momentsExpand.setAttribute("aria-expanded", state.momentsExpanded ? "true" : "false");
      if (state.momentsExpanded) {
        renderMomentList();
        dom.momentsFull.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      updateMomentControls(
        state.job?.analysis?.scenes?.length || 0,
        Math.min(state.visible, state.job?.analysis?.scenes?.length || 0),
        state.sort === "best" ? "best first" : "timeline order",
      );
    });
    const handleRecentClick = (event) => {
      const remove = event.target.closest("[data-delete-id]");
      if (remove) {
        event.preventDefault();
        event.stopPropagation();
        const blocked = remove.dataset.deleteBlocked || "";
        if (blocked) {
          showRecentError(blocked);
          toast(blocked);
          return;
        }
        deleteRecentJob(remove.dataset.deleteId, remove);
        return;
      }
      const card = event.target.closest("[data-id]");
      if (card) {
        syncRecentSelection(card.dataset.id);
        openJob(card.dataset.id);
      }
    };
    dom.recent.addEventListener("click", handleRecentClick);
    dom.recentResume.addEventListener("click", handleRecentClick);
    dom.recentAllPanel.addEventListener("click", handleRecentClick);
    dom.recentAll.addEventListener("click", () => {
      state.recentExpanded = !state.recentExpanded;
      dom.recentAllPanel.hidden = !state.recentExpanded;
      dom.recentAll.setAttribute("aria-expanded", state.recentExpanded ? "true" : "false");
      dom.recentAllLabel.textContent = state.recentExpanded ? "Hide all cuts" : "View all cuts";
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
      const remove = event.target.closest("[data-remove-scene]");
      if (remove && removeSceneFromPlan(Number(remove.dataset.removeScene))) closeDrawer();
      const read = event.target.closest("[data-read-scene]");
      if (read) readScene(Number(read.dataset.readScene));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeDrawer();
    });
    document.addEventListener("keydown", (event) => {
      if (dom.result.hidden || !state.plan) return;
      if (dom.setup && !dom.setup.hidden) return;
      if (dom.clipMenu && !dom.clipMenu.hidden) return;
      const tag = String(event.target?.tagName || "").toLowerCase();
      if (["input", "select", "textarea", "button", "a"].includes(tag) || event.target?.isContentEditable) return;
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
    resetUrlInspect();
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
      resetUrlInspect();
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
    updateUrlState();
  }

  // ---------------------------------------------------------------- url ingest

  const URL_HINT_DEFAULT = "yt-dlp for most sites · XHS / RedNote for share links.";

  function ingestLabel(provider, label) {
    if (label) return label;
    if (provider === "ytdlp") return "yt-dlp";
    if (provider === "xhs") return "XHS / RedNote";
    return "yt-dlp";
  }

  function resetUrlHint() {
    dom.urlHint.textContent = URL_HINT_DEFAULT;
    dom.urlHint.removeAttribute("data-provider");
  }

  function setUrlBusy(busy, label = "") {
    state.urlBusy = busy;
    state.urlButtonLabel = busy ? label : "";
    updateUrlState();
  }

  function updateUrlState() {
    const busy = state.busy || state.urlBusy;
    dom.urlInput.disabled = busy;
    dom.urlGet.disabled = busy;
    dom.urlGet.textContent = state.urlBusy ? (state.urlButtonLabel || "Working…") : "Get video";
    dom.urlForm.classList.toggle("busy", busy);
    dom.urlForm.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function resetUrlInspect() {
    state.urlInspect = null;
    state.urlInspectUrl = "";
    dom.urlStatus.hidden = true;
    dom.urlStatus.replaceChildren();
    dom.urlError.hidden = true;
    dom.urlError.textContent = "";
    resetUrlHint();
  }

  function showUrlError(message) {
    dom.urlError.textContent = message || "Could not use this link.";
    dom.urlError.hidden = false;
  }

  function showUrlLines(lines) {
    dom.urlStatus.replaceChildren();
    const items = (lines || []).filter((line) => line && line.text);
    if (!items.length) {
      dom.urlStatus.hidden = true;
      return;
    }
    items.forEach((line) => {
      const row = document.createElement("div");
      row.className = `url-status-line ${line.tone || ""}`.trim();
      row.textContent = line.text;
      dom.urlStatus.append(row);
    });
    dom.urlStatus.hidden = false;
  }

  function showUrlChoices(choices, inspected) {
    if (!Array.isArray(choices) || !choices.length) return;
    const wrap = document.createElement("div");
    wrap.className = "url-choices";
    const heading = document.createElement("p");
    heading.className = "url-choices-title";
    heading.textContent = `Choose one of ${choices.length} videos`;
    wrap.append(heading);
    choices.forEach((choice, index) => {
      if (!choice || !choice.url) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "url-choice";
      const title = document.createElement("strong");
      title.textContent = choice.title || `Video ${index + 1}`;
      const meta = document.createElement("span");
      const bits = [];
      if (choice.uploader) bits.push(choice.uploader);
      if (Number(choice.duration)) bits.push(fmtDuration(choice.duration));
      meta.textContent = bits.join(" · ") || urlHost(choice.url);
      button.append(title, meta);
      button.addEventListener("click", () => startUrlChoice(choice, inspected));
      wrap.append(button);
    });
    dom.urlStatus.append(wrap);
    dom.urlStatus.hidden = false;
  }

  async function startUrlChoice(choice, inspected) {
    if (!choice?.url || state.urlBusy || state.busy) return;
    const url = choice.url;
    dom.urlInput.value = url;
    state.urlInspectUrl = url;
    setUrlBusy(true, "Starting…");
    try {
      const rights = await importRights();
      const job = await api("/api/jobs/from-url", {
        method: "POST",
        body: JSON.stringify({ url, options: readOptions(), rights }),
      });
      startUrlJob(job, { ...inspected, title: choice.title || inspected.title }, url);
    } catch (error) {
      setUrlBusy(false);
      showUrlError(error.message);
    }
  }

  function tidyWarning(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    const seen = new Set();
    return text
      .replace(/([.!?])\s+/g, "$1\n")
      .split("\n")
      .filter((part) => {
        const key = part.trim();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .join(" ");
  }

  function renderUrlInspect(inspected) {
    const provider = inspected.provider || "ytdlp";
    const label = ingestLabel(provider, inspected.label);
    const title = String(inspected.title || "").trim();
    const duration = Number(inspected.duration);
    const durationBit = Number.isFinite(duration) && duration > 0 ? ` · ${fmtDuration(duration)}` : "";
    dom.urlHint.textContent = `${label} · ${title || (provider === "xhs" ? "RedNote share link" : "video link")}${durationBit}`;
    dom.urlHint.dataset.provider = provider;

    const lines = [];
    const session = inspected.session && typeof inspected.session === "object"
      ? inspected.session : {};
    if (provider === "xhs") {
      const cookieSet = !!(session.cookie_set ?? inspected.cookie_set);
      const sessionRaw = session.session_ok !== undefined
        ? session.session_ok : inspected.session_ok;
      const sessionOk = sessionRaw === true ? true : sessionRaw === false ? false : null;
      const user = String(session.user || inspected.user || "").trim();
      if (cookieSet && sessionOk === false) {
        lines.push({
          text: "RedNote session · expired. Sign in again in xhs_get.",
          tone: "warn",
        });
      } else if (cookieSet) {
        lines.push({
          text: `RedNote session · signed in${user ? ` as ${user}` : ""}.`,
          tone: "ok",
        });
      } else if (!/cookie|session/i.test(String(inspected.warning || ""))) {
        lines.push({
          text: "RedNote session · not verified.",
          tone: "warn",
        });
      }
    }
    if (inspected.warning) {
      lines.push({ text: tidyWarning(inspected.warning), tone: "warn" });
    } else if (inspected.available === false) {
      lines.push({
        text: "This link is not ready. Check Setup and try again.",
        tone: "error",
      });
    }
    showUrlLines(lines);
    const choices = Array.isArray(inspected.choices)
      ? inspected.choices
      : (Array.isArray(inspected.meta?.choices) ? inspected.meta.choices : []);
    if (choices.length) {
      if (!lines.length) dom.urlStatus.hidden = false;
      showUrlChoices(choices, inspected);
    }
  }

  async function submitUrl(event) {
    event.preventDefault();
    if (state.urlBusy || state.busy) return;
    const url = dom.urlInput.value.trim();
    if (!url) {
      showUrlError("Paste a video link first.");
      dom.urlInput.focus();
      return;
    }
    dom.urlError.hidden = true;
    dom.urlError.textContent = "";
    dom.urlStatus.hidden = true;
    dom.urlStatus.replaceChildren();
    resetUrlHint();
    state.urlInspect = null;
    state.urlInspectUrl = "";
    setUrlBusy(true, "Checking…");

    let inspected;
    try {
      inspected = await api("/api/url/inspect", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
    } catch (error) {
      setUrlBusy(false);
      showUrlError(error.message);
      dom.urlInput.focus();
      return;
    }

    state.urlInspect = inspected;
    state.urlInspectUrl = url;
    renderUrlInspect(inspected);
    if (inspected.available === false) {
      setUrlBusy(false);
      return;
    }
    const meta = inspected.meta && typeof inspected.meta === "object" ? inspected.meta : {};
    const xhsTokenMissing = (inspected.provider || "") === "xhs" && (
      (meta.has_xsec_token === false && meta.short_link !== true)
      || /no xsec_token/i.test(String(inspected.warning || ""))
    );
    if (xhsTokenMissing) {
      setUrlBusy(false);
      return;
    }
    const choices = Array.isArray(inspected.choices)
      ? inspected.choices
      : (Array.isArray(meta.choices) ? meta.choices : []);
    if (inspected.needs_choice || choices.length) {
      setUrlBusy(false);
      if (!choices.length) showUrlError("This link contains multiple videos, but no selectable entries were returned.");
      return;
    }

    setUrlBusy(true, "Starting…");
    try {
      const rights = await importRights();
      const job = await api("/api/jobs/from-url", {
        method: "POST",
        body: JSON.stringify({ url, options: readOptions(), rights }),
      });
      startUrlJob(job, inspected, url);
    } catch (error) {
      setUrlBusy(false);
      showUrlError(error.message);
    }
  }

  function startUrlJob(job, inspected, url) {
    const provider = inspected.provider || job.provider || "ytdlp";
    const label = ingestLabel(provider, inspected.label || job.label);
    setUrlBusy(false);
    state.busy = true;
    state.ingestJob = job.id;
    state.cancelRequested = false;
    state.pollStart = Date.now();
    state.progressStart = Date.now();
    updateAnalyzeState();
    showView("progress");
    setProgressFile(`${label} · ${inspected.title || urlHost(url)}`);
    updateProgress({
      status: "downloading",
      progress: 0,
      message: "Preparing download",
    });
    startAnalysisPoll(job.id);
  }

  function urlHost(value) {
    try {
      return new URL(value).hostname.replace(/^www\./, "") || value;
    } catch (_) {
      return value;
    }
  }

  // ---------------------------------------------------------------- analysis

  async function startAnalysis() {
    if (!state.file && !state.localPath) return;
    const options = readOptions();
    dom.ingestError.hidden = true;
    state.busy = true;
    state.ingestJob = null;
    updateAnalyzeState();
    state.pollStart = Date.now();
    state.progressStart = Date.now();

    if (state.file) {
      showView("progress");
      setProgressFile(state.file.name);
      dom.progressTitle.textContent = "Sending the file";
      updateUploadProgress(0, 0, state.file.size);
      try {
        const rights = await importRights();
        const result = await uploadFile(state.file, options, updateUploadProgress, rights);
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
        const rights = await importRights();
        const result = await api("/api/jobs/path", {
          method: "POST",
          body: JSON.stringify({ path: state.localPath, options, rights }),
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
          state.ingestJob = null;
          state.cancelRequested = false;
          await openJob(id);
          return;
        }
        if (status.status === "failed") {
          stopPoll();
          state.ingestJob = null;
          state.cancelRequested = false;
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
    if (dom.progressCancelUrl) {
      const downloading = status.status === "downloading" && !!state.ingestJob;
      dom.progressCancelUrl.hidden = !downloading;
      dom.progressCancelUrl.disabled = !!state.cancelRequested;
      dom.progressCancelUrl.textContent = state.cancelRequested
        ? "Cancelling…" : "Cancel download";
    }

    const titles = {
      downloading: "Downloading the video",
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
        resetSoundPreviews();
        state.scriptOverrides = {};
        state.scriptId = null;
        state.lastScript = null;
        state.history = [];
        state.historyEntry = null;
        state.timelineScroll = 0;
        if (state.classicText.saveTimer) clearTimeout(state.classicText.saveTimer);
        if (state.classicText.frameTimer) clearTimeout(state.classicText.frameTimer);
        try { state.classicText.frame.controller?.abort(); } catch (_) { /* ignore */ }
        if (state.classicText.frame.url) URL.revokeObjectURL(state.classicText.frame.url);
        state.classicText = freshClassicText();
        renderClassicText();
        if (dom.historyList) dom.historyList.innerHTML = "";
        if (dom.historyDetail) {
          dom.historyDetail.hidden = true;
          dom.historyDetail.innerHTML = "";
        }
        if (dom.historyCount) dom.historyCount.textContent = "";
        if (dom.historyLatest) dom.historyLatest.textContent = "";
        if (dom.audioUpload) dom.audioUpload.value = "";
        if (dom.audioMusicUpload) dom.audioMusicUpload.value = "";
        if (dom.audioSourceGenerate) dom.audioSourceGenerate.checked = true;
        syncAudioVisibility();
      }
      state.job = job;
      rememberRecentOpened(job.id);
      syncRecentSelection(job.id);
      state.ingestJob = job.status === "downloading" ? job.id : null;
      state.cancelRequested = false;
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
      history.replaceState(null, "", jobHash(job.id));
    } catch (error) {
      toast(error.message);
      resetToIngest();
    }
  }

  function prepareResult(job) {
    state.job = job;
    cancelAudioScript();
    cancelTranslationWarm();
    abortTextScan();
    state.translation = null;
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
      state.cutDirty = false;
    state.momentsExpanded = false;
    state.trim = null;
    state.timelineScroll = 0;
    state.playerScrollKey = null;
    state.renderWasActive = null;
    state.sort = "best";
    state.visible = 96;
    state.busy = false;
    dom.hookLab.hidden = true;
    dom.hookLab.innerHTML = "";
    dom.transcriptPanel.hidden = true;
    dom.transcriptPanel.innerHTML = "";
    dom.momentsFull.hidden = true;
    dom.momentsRail.hidden = false;
    dom.momentsExpand.textContent = "Show all";
    dom.momentsExpand.setAttribute("aria-expanded", "false");
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
    refreshTextScan();
    loadFillStatus();
    paintCleanStage();
    scheduleCleanFrame();
    loadAudioEngines();
    loadAudioMoods();
    loadTranslateCheck();
    warmTranslation();
    loadHistory();
    history.replaceState(null, "", jobHash(job.id));
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

  function resultHeading() {
    const scene = currentHookScene();
    const line = scene ? clipText(sceneLine(scene), 84) : "";
    if (line) return line;
    return `${state.target}s cut`;
  }

  function updateResultHeading() {
    if (!dom.resultTitle || !state.job) return;
    const title = resultHeading();
    dom.resultTitle.textContent = title;
    dom.resultTitle.title = state.job.source.name || title;
  }

  function renderResult() {
    const job = state.job;
    const analysis = job.analysis;
    const engine = [
      analysis.engine?.vision ? "vision" : "center crop",
      analysis.engine?.whisper ? "whisper" : null,
    ].filter(Boolean).join(" + ");
    const deep = analysis.deep_count ?? analysis.scene_count;
    dom.resultMeta.textContent = tr(`${fileStem(job.source.name)} · ${fmtDuration(job.source.duration)} source · ${analysis.scene_count} moments · ${deep} deep-read · ${analysis.elapsed.toFixed(1)}s analysis · ${engine}`);
    dom.resultMeta.title = job.source.name || "";
    renderSpeechNotice();
    paintTranscriptReady();
    renderUsage();
    renderHook();
    updateResultHeading();
    renderPlan();
    renderScenes();
    updateRenderPanel();
  }

  const SPEECH_ENGINE_LABELS = {
    apple: "Apple Speech",
    whisper: "Local Whisper",
    openrouter: "OpenRouter",
    groq: "Groq",
    deepgram: "Deepgram",
  };

  function speechFailure(engine) {
    const failed = !!engine?.stt_enabled && !engine?.whisper;
    if (!failed || state.job?.analysis?.transcript) return "";
    const errors = Array.isArray(engine.stt_errors) ? engine.stt_errors : [];
    // An engine that ran and failed explains more than a route that was never
    // set up (a cloud engine with no key says only "not available").
    const ran = errors.filter((item) => item && item.error && item.error !== "Speech engine is not available.");
    const pick = ran[ran.length - 1] || [...errors].reverse().find((item) => item && item.error);
    if (!pick) return engine.stt_error || "No speech engine returned a transcript.";
    const label = SPEECH_ENGINE_LABELS[pick.provider] || pick.provider || "";
    return label ? `${label}: ${pick.error}` : pick.error;
  }

  function renderSpeechNotice() {
    if (!dom.speechNotice) return;
    const reason = speechFailure(state.job?.analysis?.engine);
    dom.speechNotice.hidden = !reason;
    if (!reason) {
      if (dom.speechRetryStatus) dom.speechRetryStatus.textContent = "";
      return;
    }
    if (dom.speechNoticeDetail) dom.speechNoticeDetail.textContent = `Last error: ${reason}`;
  }

  async function retrySpeech() {
    if (!state.job) return;
    const jobId = state.job.id;
    dom.speechRetry.disabled = true;
    if (dom.speechRetryStatus) dom.speechRetryStatus.textContent = "Reading speech…";
    try {
      let result = await api(`/api/jobs/${jobId}/transcribe`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      let ticks = 0;
      // Only a running task (202) carries task_id. A finished one returns its
      // result, and a task the server no longer tracks answers "idle".
      while (result && result.task_id && ticks < 300) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        result = await api(`/api/jobs/${jobId}/voice-tasks/transcribe`);
        ticks += 1;
        if (dom.speechRetryStatus) dom.speechRetryStatus.textContent = `Reading speech… ${ticks * 2}s`;
        if (state.job?.id !== jobId) return;
      }
      // The job is the truth: reload it and read its transcript.
      await openJob(jobId);
      if (state.job?.id !== jobId) return;
      // The job API sends the transcript summary: segments is a count there.
      const segments = state.job?.analysis?.transcript?.segments;
      const lines = Array.isArray(segments) ? segments.length : Number(segments) || 0;
      if (lines) {
        if (dom.speechRetryStatus) dom.speechRetryStatus.textContent = `Transcript ready · ${lines} lines.`;
        toast("Speech read again.");
      } else if (dom.speechRetryStatus) {
        dom.speechRetryStatus.textContent = "No transcript returned. Check Setup → Transcription.";
      }
    } catch (error) {
      if (dom.speechRetryStatus) dom.speechRetryStatus.textContent = error.message;
    } finally {
      dom.speechRetry.disabled = false;
    }
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
    if (scene.deep === false) {
      dom.hookImg.removeAttribute("src");
      dom.hookImg.classList.add("quick");
    } else {
      dom.hookImg.src = thumbUrl(scene);
      dom.hookImg.classList.remove("quick");
    }
    dom.hookImg.alt = `Hook at ${fmtTime(scene.start)}`;
    dom.hookImg.style.objectPosition = objectPosition(cropFor(scene));
    dom.hookTime.textContent = `${fmtTime(scene.start, 1)} – ${fmtTime(scene.end, 1)} · ${scene.dur.toFixed(1)}s`;
    dom.hookCopy.textContent = sceneLine(scene);
    dom.hookWhy.textContent = state.plan?.reasoning?.hook?.headline
      || state.plan?.hook_why
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
    if (dom.shapeNote) dom.shapeNote.textContent = cropLabel(scene);
    updateResultHeading();
  }

  function renderReasoning(plan) {
    if (!dom.planReasoning || !dom.planReasoningBody) return;
    const reasoning = plan?.reasoning;
    if (!reasoning || typeof reasoning !== "object") {
      dom.planReasoning.hidden = true;
      dom.planReasoningBody.replaceChildren();
      return;
    }
    dom.planReasoning.hidden = false;
    dom.planReasoningBody.replaceChildren();
    const addBlock = (title, lines) => {
      const items = (lines || []).filter((line) => line && String(line).trim());
      if (!items.length) return;
      const block = document.createElement("section");
      block.className = "reasoning-block";
      const heading = document.createElement("h4");
      heading.textContent = title;
      const list = document.createElement("ul");
      items.forEach((line) => {
        const item = document.createElement("li");
        item.textContent = String(line);
        list.append(item);
      });
      block.append(heading, list);
      dom.planReasoningBody.append(block);
    };
    const hook = reasoning.hook || {};
    addBlock("Opening", [hook.headline, ...(hook.evidence || [])]);
    addBlock(
      "Alternatives",
      (hook.alternatives || []).map((alternative) => (
        `Scene ${Number(alternative.scene) + 1}: ${alternative.why_not || "not selected"}`
      )),
    );
    const structure = reasoning.structure || {};
    addBlock("Structure", [structure.why]);
    const payoff = reasoning.payoff || {};
    addBlock("Ending", [payoff.headline, ...(payoff.evidence || [])]);
    const selection = reasoning.selection || {};
    addBlock("Selection", [selection.strategy, ...(selection.evidence || [])]);
  }

  function renderPlan() {
    const plan = state.plan;
    if (!plan) return;
    const scroll = Number(state.timelineScroll) || 0;
    dom.planTotal.textContent = tr(`${plan.total.toFixed(1)}s cut · ${plan.clip_count} beats`);
    dom.planBadge.textContent = tr(plan.auto ? "auto hook" : "custom hook");
    dom.planBadge.classList.toggle("custom", !plan.auto);
    dom.resetHook.hidden = state.overrideHook === null;
    dom.editCut.textContent = state.editMode ? "Editing…" : "Edit cut";
    dom.editBar.hidden = !state.editMode;
    const clips = plan.clips || [];
    const first = clips[0];
    const last = clips[clips.length - 1];
    dom.planRoute.textContent = tr(first && last
      ? `Hook ${fmtTime(first.start, 1)} → payoff ${fmtTime(last.start, 1)} · ${plan.clip_count} beats · ${plan.total.toFixed(1)}s`
      : `${plan.clip_count} beats · ${plan.total.toFixed(1)}s`);
    renderReasoning(plan);
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
          ${scene.deep === false
            ? `<span class="clip-placeholder"><span>quick</span></span>`
            : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(cropFor(scene))}">`}
          <button type="button" class="clip-role" data-role-index="${index}" aria-haspopup="menu" aria-controls="clip-menu" aria-expanded="false"
            title="Change hook / beat / payoff">${esc(clip.role)}</button>
          <span class="clip-time">${clip.dur.toFixed(1)}s</span>
          <span class="trim-handle start" data-trim="start" data-index="${index}" title="Drag to trim start"></span>
          <span class="trim-handle end" data-trim="end" data-index="${index}" title="Drag to trim end"></span>
          ${tools}
        </div>`;
    }).join("");
    dom.timeline.scrollLeft = scroll;
    renderVariants();
    renderMixer();
    syncClassicTextDefaults();
    updateTextAvailability();
    refreshClassicText();
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

  async function toggleMixer() {
    if (!state.mixer.ready) await loadMixer();
    if (!state.mixer.ready) {
      toast("Open a cut to use the mixer.");
      return;
    }
    state.mixerOpen = !state.mixerOpen;
    dom.mixerPanel.hidden = !state.mixerOpen;
    if (state.mixerOpen) {
      drawMixer();
      dom.mixerPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  async function loadMixer() {
    const plan = state.plan;
    if (!state.job || !plan) {
      state.mixer.ready = false;
      dom.mixerPanel.hidden = true;
      state.mixerOpen = false;
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
      dom.mixerPanel.hidden = !state.mixerOpen;
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

  function manualPlanReasoning(plan, clips, note) {
    const target = Number(plan.target) || state.target || 30;
    const sourceDuration = Number(state.job?.source?.duration) || 0;
    const total = Math.round(clips.reduce((sum, clip) => sum + (Number(clip.dur) || 0), 0) * 1000) / 1000;
    const body = clips.filter((clip) => clip.role === "beat");
    const bodyOrder = body.every((clip, index) => index === 0
      || Number(clip.start) >= Number(body[index - 1].start));
    const starts = clips.map((clip) => Number(clip.start) || 0);
    const ends = clips.map((clip) => Number(clip.end) || 0);
    const hookScene = clips[0]?.scene;
    const payoffScene = clips[clips.length - 1]?.scene;
    const orderText = bodyOrder
      ? "Bridge beats remain in source order."
      : "Bridge beats were reordered; source order no longer holds.";
    return {
      target,
      source_duration: sourceDuration,
      summary: `${note}: ${clips.length} clip${clips.length === 1 ? "" : "s"}, ${total.toFixed(1)}s of a ${target}s target. ${orderText} Automatic hook/payoff scoring does not describe this manual cut.`,
      hook: {
        headline: Number.isInteger(hookScene) ? `Manual opening: scene ${hookScene + 1}.` : "Manual opening.",
        evidence: ["opening clip supplied by the manual edit"],
        alternatives: [],
      },
      structure: {
        roles: clips.map((clip) => clip.role || "beat"),
        clip_count: clips.length,
        beat_count: body.length,
        body_order: bodyOrder ? "source" : "manual",
        body_in_source_order: bodyOrder,
        hook_first: clips[0]?.role === "hook",
        source_span: clips.length ? { start: Math.min(...starts), end: Math.max(...ends) } : null,
        why: `${note} controls the clip list. ${orderText} The original automatic hook/payoff explanation is not used.`,
      },
      payoff: {
        headline: Number.isInteger(payoffScene) ? `Manual ending: scene ${payoffScene + 1}.` : "Manual ending.",
        evidence: ["last clip supplied by the manual edit"],
        why_late: null,
        position_pct: null,
        late_zone_pct: 68,
        candidates: 0,
      },
      selection: {
        strategy: `${note}: automatic ranking, spacing, and budget claims were replaced by the manual clip list.`,
        evidence: [
          `${clips.length} manual clips totalling ${total.toFixed(1)}s`,
          orderText,
          "re-run automatic Smart Cut to restore scored reasoning",
        ],
        kept: clips.map((clip) => ({
          scene: clip.scene,
          role: clip.role || "beat",
          start: Number(clip.start) || 0,
          end: Number(clip.end) || 0,
          dur: Number(clip.dur) || 0,
          why: clip.why || "",
          evidence: [],
        })),
        target_budget: {
          target,
          source_duration: sourceDuration,
          total,
          headroom: Math.max(0, target - total),
          over_target: Math.max(0, total - target),
        },
      },
    };
  }

  function syncEditedPlan() {
    if (!state.plan) return;
    const clips = state.plan.clips.map((clip) => ({
      ...clip,
      why: `Manual ${clip.role || "clip"}: ${(Number(clip.dur) || 0).toFixed(1)}s at ${(Number(clip.start) || 0).toFixed(1)}s.`,
    }));
    const total = Math.round(clips.reduce((sum, clip) => sum + clip.dur, 0) * 1000) / 1000;
    const reasoning = manualPlanReasoning(state.plan, clips, "Manual edit");
    state.plan = {
      ...state.plan,
      clips,
      total,
      clip_count: clips.length,
      hook_scene: clips.length ? clips[0].scene : state.plan.hook_scene,
      auto: false,
      note: "Manual edit",
      reasoning,
      hook_why: reasoning.hook.headline,
      payoff_why: reasoning.payoff.headline,
    };
    state.edited = true;
    state.cutDirty = true;
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

  function openClipMenu(index, x, y, trigger = null) {
    if (!state.plan?.clips[index] || !dom.clipMenu) return;
    if (state.clipMenuTrigger && state.clipMenuTrigger !== trigger) {
      state.clipMenuTrigger.setAttribute("aria-expanded", "false");
    }
    state.clipMenuIndex = index;
    state.clipMenuTrigger = trigger || null;
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    const current = state.plan.clips[index].role || "beat";
    dom.clipMenu.innerHTML = `
      <span class="clip-menu-head">Change role</span>
      ${CLIP_ROLES.map((role) => `
      <button type="button" role="menuitemradio" aria-checked="${role === current}" data-clip-role="${role}" class="${role === current ? "active" : ""}">
        ${CLIP_ROLE_LABELS[role]}
      </button>`).join("")}`;
    dom.clipMenu.hidden = false;
    const width = dom.clipMenu.offsetWidth || 140;
    const height = dom.clipMenu.offsetHeight || 120;
    dom.clipMenu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - width - 8))}px`;
    dom.clipMenu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - height - 8))}px`;
    dom.clipMenu.querySelectorAll("[data-clip-role]").forEach((button) => {
      button.addEventListener("click", () => {
        setClipRole(index, button.dataset.clipRole);
      });
    });
    const checked = dom.clipMenu.querySelector(`[data-clip-role="${current}"]`);
    (checked || dom.clipMenu.querySelector("[data-clip-role]"))?.focus({ preventScroll: true });
  }

  function closeClipMenu(options = {}) {
    if (!dom.clipMenu) return;
    const trigger = state.clipMenuTrigger;
    dom.clipMenu.hidden = true;
    state.clipMenuIndex = null;
    state.clipMenuTrigger = null;
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
      if (options.restoreFocus && trigger.isConnected) trigger.focus({ preventScroll: true });
    }
  }

  function setClipRole(index, role) {
    if (!state.plan || !state.plan.clips[index]) return;
    if (!CLIP_ROLES.includes(role)) return;
    const sceneId = state.plan.clips[index].scene;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    if (role === "beat" && clips.length <= 2) {
      closeClipMenu();
      toast("A two-moment cut needs a hook and a payoff.");
      return;
    }
    const [clip] = clips.splice(index, 1);
    if (role === "hook") {
      clips.unshift(clip);
    } else if (role === "payoff") {
      clips.push(clip);
    } else {
      // Beat means "inside the body", never first or last. A demoted payoff
      // must not land at the end again and keep its payoff position.
      const at = Math.max(1, Math.min(index, clips.length - 2));
      clips.splice(at, 0, clip);
    }
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    state.edited = true;
    state.cutDirty = true;
    state.scriptId = null;
    syncEditedPlan();
    closeClipMenu();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    const next = dom.timeline.querySelector(`.clip[data-scene="${sceneId}"] [data-role-index]`);
    next?.focus({ preventScroll: true });
    toast(`Moved to ${CLIP_ROLE_LABELS[role].toLowerCase()} position.`);
  }

  function normalizePlanRoles(clips) {
    clips.forEach((clip, index) => {
      clip.role = index === 0 ? "hook" : index === clips.length - 1 ? "payoff" : "beat";
    });
  }

  function planClipsForRender() {
    if (!state.plan?.clips?.length) return null;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    normalizePlanRoles(clips);
    return clips;
  }

  function addSceneToPlan(sceneId, at = null) {
    if (!state.plan) return false;
    const scene = sceneById(sceneId);
    if (!scene) return false;
    if (scene.deep === false) {
      toast("Quick scan · deep-read this moment before adding it.");
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
    state.cutDirty = true;
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    toast("Moment added to Smart Cut.");
    return true;
  }

  function removeSceneFromPlan(sceneId) {
    if (!state.plan) return false;
    const clips = state.plan.clips.map((clip) => ({ ...clip }));
    const index = clips.findIndex((clip) => clip.scene === sceneId);
    if (index === -1) return false;
    if (clips.length <= 2) {
      toast("Smart Cut needs at least two moments.");
      return false;
    }
    clips.splice(index, 1);
    normalizePlanRoles(clips);
    state.plan = { ...state.plan, clips };
    state.edited = true;
    state.cutDirty = true;
    state.scriptId = null;
    syncEditedPlan();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    toast("Moment removed from Smart Cut.");
    return true;
  }

  function toggleSceneInPlan(sceneId) {
    const inPlan = (state.plan?.clips || []).some((clip) => clip.scene === sceneId);
    if (inPlan) return removeSceneFromPlan(sceneId);
    return addSceneToPlan(sceneId);
  }

  function toggleMomentSelection(sceneId) {
    const railScroll = Number(dom.momentsRail?.scrollLeft) || 0;
    const listScroll = Number(dom.momentsList?.scrollTop) || 0;
    const changed = toggleSceneInPlan(sceneId);
    if (!changed) return;
    // Re-rendering replaces the card the user just pressed. Keep the rail
    // where it was and put focus back on the same moment's select.
    if (dom.momentsRail) dom.momentsRail.scrollLeft = railScroll;
    if (dom.momentsList) dom.momentsList.scrollTop = listScroll;
    const scope = state.momentsExpanded ? dom.momentsList : dom.momentsRail;
    const next = scope?.querySelector(`[data-moment-toggle="${sceneId}"]`);
    next?.focus({ preventScroll: true });
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
    state.cutDirty = true;
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
    state.cutDirty = true;
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
      state.cutDirty = false;
      renderVariants();
      toast("Variant saved.");
    } catch (error) {
      toast(error.message);
    }
  }

  async function loadVariant(variantId) {
    const variant = (state.job?.variants || []).find((item) => item.id === variantId);
    if (!variant) return;
    const clips = variant.clips.map((clip) => ({
      ...clip,
      why: `Manual ${clip.role || "clip"}: ${(Number(clip.dur) || 0).toFixed(1)}s at ${(Number(clip.start) || 0).toFixed(1)}s.`,
    }));
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
    const reasoning = manualPlanReasoning(state.plan, clips, `Variant · ${variant.name}`);
    state.plan.reasoning = reasoning;
    state.plan.hook_why = reasoning.hook.headline;
    state.plan.payoff_why = reasoning.payoff.headline;
    state.edited = true;
    state.cutDirty = true;
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
            <b>${roundScoreHalfEven(hook.hook)} hook</b>
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

  function momentCheck(scene, checked) {
    const action = checked ? "Remove" : "Add";
    return `<button type="button" class="moment-check ${checked ? "checked" : ""}" data-moment-toggle="${scene.id}"
      role="checkbox" aria-checked="${checked}" aria-label="${action} ${esc(fmtTime(scene.start))} moment ${checked ? "from" : "to"} Smart Cut"
      title="${checked ? "Remove from Smart Cut" : "Add to Smart Cut"}"></button>`;
  }

  function updateMomentControls(total, shown, order) {
    const count = `${total} moment${total === 1 ? "" : "s"} · ${order}`;
    dom.sceneCount.textContent = shown < total ? tr(`${count} · ${shown} shown`) : count;
    dom.momentsExpand.textContent = state.momentsExpanded ? "Show less" : `Show all ${total}`;
    dom.momentsExpand.setAttribute("aria-expanded", state.momentsExpanded ? "true" : "false");
  }

  function setMomentsExpanded(expanded, options = {}) {
    state.momentsExpanded = !!expanded;
    dom.momentsFull.hidden = !state.momentsExpanded;
    dom.momentsRail.hidden = state.momentsExpanded;
    const total = state.job?.analysis?.scenes?.length || 0;
    dom.momentsExpand.textContent = state.momentsExpanded ? "Show less" : `Show all ${total}`;
    dom.momentsExpand.setAttribute("aria-expanded", state.momentsExpanded ? "true" : "false");
    if (state.momentsExpanded) {
      renderMomentList();
      if (options.scroll !== false) {
        dom.momentsFull.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
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
    const order = state.sort === "best" ? "best first" : "timeline order";
    updateMomentControls(scenes.length, visible.length, order);
    dom.sceneGrid.innerHTML = visible.map((scene) => {
      const role = roles.get(scene.id) || "";
      const tags = [...(scene.tags || []), ...(scene.deep === false ? ["quick"] : [])].join(" · ");
      const still = scene.deep === false
        ? `<span class="scene-placeholder"><span>quick</span></span>`
        : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(cropFor(scene))}">`;
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
    dom.momentsRail.innerHTML = railScenes.map((scene, index) => {
      const still = scene.deep === false
        ? `<span class="scene-placeholder"><span>quick</span></span>`
        : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(cropFor(scene))}">`;
      const role = scene.id === hookId ? "hook" : scene.id === payoffId ? "payoff" : (used.has(scene.id) ? "in cut" : "");
      const text = (scene.ocr || scene.speech || `Scene ${scene.id + 1}`).trim();
      return `
        <div class="moment-card ${used.has(scene.id) ? "in-plan" : ""} ${scene.id === hookId ? "is-hook" : ""} ${scene.id === payoffId ? "is-payoff" : ""}"
          data-moment-scene="${scene.id}" data-rail-index="${index}" draggable="true"
          role="button" tabindex="0" aria-label="${esc(text)}${role ? ` · ${esc(role)}` : ""} · open details"
          title="Click for details · ${esc(text)}">
          ${still}
          ${momentCheck(scene, used.has(scene.id))}
          <span class="moment-time">${esc(fmtTime(scene.start))}</span>
          <span class="moment-score">${Math.round(scene.hook)}</span>
        </div>`;
    }).join("");
    if (dom.momentsFull && !dom.momentsFull.hidden) {
      renderMomentList();
    }
  }

  function renderMomentList() {
    if (!state.job || !dom.momentsList || dom.momentsFull.hidden) return;
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
    dom.momentsList.innerHTML = scenes.map((scene) => {
      const still = scene.deep === false
        ? `<span class="moment-placeholder"><span>quick</span></span>`
        : `<img src="${esc(thumbUrl(scene))}" alt="" loading="lazy" style="object-position:${objectPosition(cropFor(scene))}">`;
      const text = (scene.ocr || scene.speech || `Scene ${scene.id + 1}`).trim();
      const role = scene.id === hookId ? "hook" : scene.id === payoffId ? "payoff" : (used.has(scene.id) ? "in cut" : "");
      return `
        <div class="moment-card ${used.has(scene.id) ? "in-plan" : ""} ${scene.id === hookId ? "is-hook" : ""} ${scene.id === payoffId ? "is-payoff" : ""}"
          data-moment-scene="${scene.id}" draggable="true" role="listitem" tabindex="0"
          aria-label="${esc(text)}${role ? ` · ${esc(role)}` : ""} · open details"
          title="${esc(text)}${role ? ` · ${esc(role)}` : ""} · click for details">
          ${still}
          ${momentCheck(scene, used.has(scene.id))}
          <span class="moment-time">${esc(fmtTime(scene.start))}</span>
          <span class="moment-score">${Math.round(scene.hook)}</span>
        </div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- plans + targets

  async function setTarget(target) {
    if (state.target === target) return;
    state.target = target;
    state.edited = false;
      state.cutDirty = false;
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
      state.cutDirty = false;
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
      state.cutDirty = false;
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

  const AUDIO_MODE_META = {
    keep: "Original audio and transcript. No new voice or music.",
    bed: "New voice over the original audio bed.",
    voice: "Replace only the spoken voice with a dub.",
    music: "Replace all audio with a music bed.",
    full: "New voice and a new music bed.",
  };

  const AUDIO_COPY_NOTE = {
    keep: "Original audio and transcript.",
    music: "Music only. Copy and script are off.",
    full: "New voice and music. Copy is off while a recording is used.",
  };

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

  function setAudioMode(mode) {
    if (!dom.audioMode || !mode) return;
    dom.audioMode.value = mode;
    dom.audioMode.dispatchEvent(new Event("change", { bubbles: true }));
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
        const active = button.dataset.audioMode === state.audio.mode;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (dom.audioModeDesc) {
        dom.audioModeDesc.textContent = AUDIO_MODE_META[state.audio.mode] || AUDIO_MODE_META.keep;
      }
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
      updatePrivacyPill();
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
        clearMusicPreview("Music engine changed. Generate a new preview.");
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
        warmTranslation();
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
        clearVoicePreview("Voice list changed. Generate a new preview.");
        touch();
        loadAudioVoices();
      });
      dom.audioVoice.addEventListener(event, () => {
        clearVoicePreview("Voice changed. Generate a new preview.");
        touch();
      });
      dom.audioRate.addEventListener(event, () => {
        clearVoicePreview("Rate changed. Generate a new preview.");
        touch();
      });
      dom.audioTrack.addEventListener(event, () => {
        if (state.audio.musicUpload) clearMusicUpload();
        clearMusicPreview("Track changed. Play the BGM to preview it.");
        touch();
      });
      dom.audioPrompt.addEventListener(event, () => {
        clearMusicPreview("Prompt changed. Generate a new preview.");
        touch();
      });
      dom.audioGain.addEventListener(event, touch);
      dom.audioDuck.addEventListener(event, touch);
    });
    dom.audioModeTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-audio-mode]");
      if (!button) return;
      setAudioMode(button.dataset.audioMode);
    });
    dom.audioCopySwitch?.addEventListener("click", () => {
      const upload = ["bed", "voice", "full"].includes(state.audio.mode) && state.audio.source === "upload";
      if (upload) {
        setVoiceSource("generate");
        loadAudioScript();
      } else if (state.audio.mode === "music") {
        setAudioMode("bed");
      } else {
        setAudioMode("voice");
      }
    });
    dom.mixerOpen?.addEventListener("click", toggleMixer);
    dom.audioRewriteRun.addEventListener("click", () => {
      // Reuse the on-disk translation memo. Only a language change or the
      // explicit Retry translation button asks for fresh translations.
      if (state.scriptAbort) return;
      loadAudioScript({ run: true });
    });
    document.querySelectorAll('input[name="audio-music-source"]').forEach((input) => {
      input.addEventListener("change", () => {
        state.audio.musicSource = musicSourceMode();
        syncMusicOptions();
        syncAudioVisibility();
        clearMusicPreview(defaultMusicPreviewNote(), "");
        touch();
        loadAudioTracks();
      });
    });
    dom.audioPreview.addEventListener("click", playVoiceSample);
    dom.audioGenerateVoice?.addEventListener("click", () => {
      setVoiceSource("generate");
      generateVoicePreview();
    });
    dom.audioUseRecording?.addEventListener("click", openVoicePicker);
    dom.audioGenerateMusic?.addEventListener("click", () => {
      setMusicSource("generate");
      generateMusicPreview();
    });
    dom.audioMusicBlockBgm?.addEventListener("click", () => {
      setMusicSource("own");
      dom.audioMusicUploadButton?.click();
    });
    dom.audioMusicBlockGenerate?.addEventListener("click", () => {
      setMusicSource("generate");
      generateMusicPreview();
    });
    dom.audioUseBgm?.addEventListener("click", () => {
      setMusicSource("own");
      dom.audioMusicUploadButton?.click();
    });
    dom.audioStatusSetup?.addEventListener("click", openSetup);
    dom.audioPlayMusic?.addEventListener("click", playMusicSample);
    document.querySelectorAll("[data-sound-tab]").forEach((button) => {
      button.addEventListener("click", () => showSoundTab(button.dataset.soundTab));
      button.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const tabs = [...document.querySelectorAll("[data-sound-tab]")];
        const current = tabs.indexOf(button);
        const next = event.key === "Home"
          ? 0
          : event.key === "End"
            ? tabs.length - 1
            : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        tabs[next].focus();
        showSoundTab(tabs[next].dataset.soundTab);
      });
    });
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
    showSoundTab(state.soundTab || "voice");
  }

  let voicePickerPrevious = "generate";

  function setVoiceSource(source) {
    state.audio.source = source;
    if (dom.audioSourceGenerate) dom.audioSourceGenerate.checked = source === "generate";
    if (dom.audioSourceUpload) dom.audioSourceUpload.checked = source === "upload";
    if (source === "upload") {
      setSoundStatus(dom.audioVoicePreviewStatus, "Your recording replaces the generated voice.", "");
    } else if (!state.voiceSampleUrl) {
      setSoundStatus(dom.audioVoicePreviewStatus, defaultVoicePreviewNote(), "");
    }
    syncAudioVisibility();
    updateRenderPanel();
  }

  function showSoundTab(tab) {
    state.soundTab = tab === "music" ? "music" : "voice";
    document.querySelectorAll("[data-sound-tab]").forEach((button) => {
      const active = button.dataset.soundTab === state.soundTab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    [dom.audioVoiceStep, dom.audioMusicStep].forEach((panel) => {
      if (!panel) return;
      panel.hidden = panel.dataset.soundPanel !== state.soundTab;
    });
  }

  function setMusicSource(source) {
    const input = document.querySelector(`input[name="audio-music-source"][value="${source}"]`);
    if (!input) return;
    input.checked = true;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setSoundStatus(node, message, tone = "") {
    if (!node) return;
    node.textContent = message || "";
    if (tone) node.dataset.tone = tone;
    else delete node.dataset.tone;
  }

  function stopSoundPlayer() {
    if (!state.soundPlayer) return;
    try {
      state.soundPlayer.pause();
    } catch (_) { /* the element may already be detached */ }
    state.soundPlayer = null;
  }

  function playSoundUrl(url) {
    if (!url) return;
    stopSoundPlayer();
    const player = new Audio(url);
    state.soundPlayer = player;
    player.addEventListener("ended", () => {
      if (state.soundPlayer === player) state.soundPlayer = null;
    }, { once: true });
    player.play().catch(() => {
      if (state.soundPlayer === player) state.soundPlayer = null;
      toast("Playback was blocked. Press play again.");
    });
  }

  function defaultMusicPreviewNote() {
    const source = musicSourceMode();
    if (source === "own") return "Play a 12s preview of your BGM.";
    if (source === "generate") return "Generate a 12s AI preview; the render uses the full bed.";
    return "Choose Use my BGM or Generate.";
  }

  function defaultVoicePreviewNote() {
    return "Generate a short voice preview.";
  }

  function previewVoiceText() {
    const line = (state.lastScript?.lines || []).find((item) => String(item.text || "").trim());
    if (line) return String(line.text).replace(/\s+/g, " ").trim().slice(0, 180);
    const clip = state.plan?.clips?.[0];
    const scene = clip ? sceneById(clip.scene) : null;
    return String(scene?.speech || "This is a VibeCut voice test.").replace(/\s+/g, " ").trim().slice(0, 180);
  }

  function voicePreviewKey() {
    return [
      state.job?.id || "",
      state.audio.engine || "",
      state.audio.voice || "",
      Number(state.audio.rate) || 1,
      JSON.stringify(state.setup?.voice_fit || {}),
      previewVoiceText(),
    ].join("|");
  }

  function musicPreviewKey() {
    const source = musicSourceMode();
    if (source === "own") {
      return ["own", state.audio.musicUpload || "", state.audio.track || ""].join("|");
    }
    return [
      "generate",
      state.audio.music || "",
      state.audio.prompt || "",
      (state.audioMoods || []).join(","),
      "12",
    ].join("|");
  }

  function voiceEngineReady() {
    const engines = state.audioEngines?.voices;
    if (!engines) return true;
    const info = engines[state.audio.engine];
    return !!info && info.available !== false;
  }

  function musicGenerationReady() {
    const music = state.audioEngines?.music;
    if (!music) return true;
    const selected = music[state.audio.music];
    if (selected && selected.available === false) return false;
    return ["minimax-music", "lyria-clip"].some((key) => Boolean(music[key]?.available));
  }

  function voicePreviewBlock() {
    if (!voiceEngineReady()) {
      return "This voice engine needs setup. Pick an available voice or use my recording.";
    }
    if (!state.audio.voice) return "Choose a voice first.";
    return "";
  }

  function musicGenerationBlock() {
    if (musicSourceMode() !== "generate") return "Choose Generate as the music source.";
    const music = state.audioEngines?.music;
    if (!music) return "";
    const selected = state.audio.music;
    if (!selected || selected === "none") return "Choose a music engine first.";
    if (music[selected]?.available === false) {
      return "This music engine needs setup. Pick an available engine or use my BGM.";
    }
    if (!["minimax-music", "lyria-clip"].some((key) => music[key]?.available)) {
      return "AI music needs a MiniMax or OpenRouter key. Add one in Setup or use my BGM.";
    }
    return "";
  }

  function syncSoundPreviewButtons() {
    const voiceMode = ["bed", "voice", "full"].includes(state.audio.mode);
    const musicMode = ["music", "full"].includes(state.audio.mode);
    const voiceReady = !!state.voiceSampleUrl && state.voiceSampleKey === voicePreviewKey();
    if (dom.audioPreview) {
      dom.audioPreview.disabled = !voiceMode || !voiceReady || state.voicePreviewBusy;
      dom.audioPreview.title = voiceReady
        ? "Play the generated voice"
        : "Generate a voice preview first";
    }
    if (dom.audioGenerateVoice) {
      const blocked = voicePreviewBlock();
      dom.audioGenerateVoice.disabled = !voiceMode || !!blocked || state.voicePreviewBusy;
      dom.audioGenerateVoice.title = blocked || "";
    }
    const source = musicSourceMode();
    const musicReady = source === "own"
      || (source === "generate" && !!state.musicPreviewUrl && state.musicPreviewKey === musicPreviewKey());
    if (dom.audioGenerateMusic) {
      const blocked = musicGenerationBlock();
      dom.audioGenerateMusic.disabled = !musicMode || source === "none"
        || state.musicPreviewBusy
        || (source === "generate" && !!blocked);
      dom.audioGenerateMusic.title = source === "none"
        ? "Choose a music source first."
        : source === "own"
          ? "Switch to Generate and make a short AI bed."
          : (blocked || "");
    }
    if (dom.audioPlayMusic) {
      dom.audioPlayMusic.disabled = !musicMode || !musicReady || state.musicPreviewBusy;
      dom.audioPlayMusic.title = musicReady
        ? "Play the 12s preview"
        : (source === "none" ? "Choose a music source first." : "Generate a music preview first.");
    }
    dom.audioEngine?.closest(".audio-field")?.classList.toggle("is-unavailable", !voiceEngineReady());
    dom.audioMusicField?.classList.toggle(
      "is-unavailable",
      source === "generate" && !musicGenerationReady(),
    );
  }

  function clearVoicePreview(message = "", tone = "bad") {
    stopSoundPlayer();
    if (state.voiceSampleUrl) {
      try { URL.revokeObjectURL(state.voiceSampleUrl); } catch (_) { /* already gone */ }
    }
    state.voiceSampleUrl = "";
    state.voiceSampleKey = "";
    if (message) setSoundStatus(dom.audioVoicePreviewStatus, message, tone);
    syncSoundPreviewButtons();
  }

  function clearMusicPreview(message = "", tone = "bad") {
    stopSoundPlayer();
    if (state.musicPreviewUrl) {
      try { URL.revokeObjectURL(state.musicPreviewUrl); } catch (_) { /* already gone */ }
    }
    state.musicPreviewUrl = "";
    state.musicPreviewKey = "";
    if (message) setSoundStatus(dom.audioMusicPreviewStatus, message, tone);
    syncSoundPreviewButtons();
  }

  function resetSoundPreviews() {
    stopSoundPlayer();
    if (state.voiceSampleUrl) {
      try { URL.revokeObjectURL(state.voiceSampleUrl); } catch (_) { /* already gone */ }
    }
    if (state.musicPreviewUrl) {
      try { URL.revokeObjectURL(state.musicPreviewUrl); } catch (_) { /* already gone */ }
    }
    state.voiceSampleUrl = "";
    state.voiceSampleKey = "";
    state.musicPreviewUrl = "";
    state.musicPreviewKey = "";
    state.voicePreviewBusy = false;
    state.musicPreviewBusy = false;
    setSoundStatus(dom.audioVoicePreviewStatus, defaultVoicePreviewNote(), "");
    setSoundStatus(dom.audioMusicPreviewStatus, defaultMusicPreviewNote(), "");
    syncSoundPreviewButtons();
  }

  async function fetchSoundBlob(url, options = {}) {
    const token = tokenValue();
    const response = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch (_) { /* not JSON */ }
      throw new Error(detail);
    }
    return {
      blob: await response.blob(),
      cache: response.headers.get("X-VibeCut-Preview") || "",
    };
  }

  async function generateVoicePreview() {
    if (!state.job) return;
    const blocked = voicePreviewBlock();
    if (blocked) {
      setSoundStatus(dom.audioVoicePreviewStatus, blocked, "bad");
      syncSoundPreviewButtons();
      return;
    }
    const key = voicePreviewKey();
    if (state.voiceSampleUrl && state.voiceSampleKey === key) {
      playSoundUrl(state.voiceSampleUrl);
      setSoundStatus(dom.audioVoicePreviewStatus, "Voice preview ready.", "ok");
      return;
    }
    state.voicePreviewBusy = true;
    dom.audioGenerateVoice.textContent = "Generating…";
    setSoundStatus(dom.audioVoicePreviewStatus, "Generating a short voice preview…");
    syncSoundPreviewButtons();
    try {
      const { blob, cache } = await fetchSoundBlob(`/api/jobs/${state.job.id}/voice/sample`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          engine: state.audio.engine,
          voice: state.audio.voice,
          rate: state.audio.rate,
          text: previewVoiceText(),
        }),
      });
      if (state.voiceSampleUrl) URL.revokeObjectURL(state.voiceSampleUrl);
      state.voiceSampleUrl = URL.createObjectURL(blob);
      state.voiceSampleKey = key;
      setSoundStatus(
        dom.audioVoicePreviewStatus,
        tr(cache === "cached"
          ? "Voice preview ready · cached, no new call. Play ▶ or render to use this voice."
          : "Voice preview ready. Play ▶ or render to use this voice."),
        "ok",
      );
      playSoundUrl(state.voiceSampleUrl);
    } catch (error) {
      setSoundStatus(dom.audioVoicePreviewStatus, error.message, "bad");
    } finally {
      state.voicePreviewBusy = false;
      dom.audioGenerateVoice.textContent = "Generate voice sample";
      syncSoundPreviewButtons();
    }
  }

  function playVoiceSample() {
    if (!state.voiceSampleUrl || state.voiceSampleKey !== voicePreviewKey()) {
      setSoundStatus(dom.audioVoicePreviewStatus, "Generate a voice preview first.", "bad");
      return;
    }
    playSoundUrl(state.voiceSampleUrl);
  }

  async function generateMusicPreview() {
    if (!state.job) return;
    const blocked = musicGenerationBlock();
    if (blocked) {
      setSoundStatus(dom.audioMusicPreviewStatus, blocked, "bad");
      syncSoundPreviewButtons();
      return;
    }
    const key = musicPreviewKey();
    if (state.musicPreviewUrl && state.musicPreviewKey === key) {
      playSoundUrl(state.musicPreviewUrl);
      setSoundStatus(dom.audioMusicPreviewStatus, "Music preview ready.", "ok");
      return;
    }
    state.musicPreviewBusy = true;
    dom.audioGenerateMusic.textContent = "Generating…";
    setSoundStatus(dom.audioMusicPreviewStatus, "Generating a 12s AI music preview. One provider call, cached by prompt.");
    syncSoundPreviewButtons();
    try {
      const { blob, cache } = await fetchSoundBlob(`/api/classic/jobs/${state.job.id}/sound/music-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          engine: state.audio.music,
          prompt: state.audio.prompt,
          moods: state.audioMoods,
          seconds: 12,
        }),
      });
      if (state.musicPreviewUrl) URL.revokeObjectURL(state.musicPreviewUrl);
      state.musicPreviewUrl = URL.createObjectURL(blob);
      state.musicPreviewKey = key;
      setSoundStatus(
        dom.audioMusicPreviewStatus,
        cache === "hit"
          ? tr(window.ClassicTrust?.costNotice({ cached: true }) || "Cached · no new call")
          : "Music preview ready · 12s. The render uses the full bed.",
        "ok",
      );
      playSoundUrl(state.musicPreviewUrl);
    } catch (error) {
      setSoundStatus(dom.audioMusicPreviewStatus, error.message, "bad");
    } finally {
      state.musicPreviewBusy = false;
      dom.audioGenerateMusic.textContent = "Generate music preview";
      syncSoundPreviewButtons();
    }
  }

  async function playMusicSample() {
    const source = musicSourceMode();
    if (source === "none") {
      setSoundStatus(dom.audioMusicPreviewStatus, "Choose Use my BGM or Generate first.", "bad");
      return;
    }
    if (source === "generate") {
      if (!state.musicPreviewUrl || state.musicPreviewKey !== musicPreviewKey()) {
        setSoundStatus(dom.audioMusicPreviewStatus, "Press Generate music preview for a 12s preview. The render makes the full bed.", "bad");
        return;
      }
      playSoundUrl(state.musicPreviewUrl);
      return;
    }
    state.musicPreviewBusy = true;
    setSoundStatus(dom.audioMusicPreviewStatus, "Loading a 12s BGM preview…");
    syncSoundPreviewButtons();
    try {
      const query = new URLSearchParams({ seconds: "12" });
      if (state.audio.musicUpload) {
        query.set("source", "upload");
        query.set("upload", state.audio.musicUpload);
      } else {
        query.set("source", "library");
        query.set("track", state.audio.track || "");
        if (state.audioMoods.length) query.set("moods", state.audioMoods.join(","));
      }
      const { blob } = await fetchSoundBlob(
        `/api/classic/jobs/${state.job.id}/sound/bgm-preview?${query}`,
      );
      if (state.musicPreviewUrl) URL.revokeObjectURL(state.musicPreviewUrl);
      state.musicPreviewUrl = URL.createObjectURL(blob);
      state.musicPreviewKey = musicPreviewKey();
      setSoundStatus(dom.audioMusicPreviewStatus, "Playing your BGM · 12s preview.", "ok");
      playSoundUrl(state.musicPreviewUrl);
    } catch (error) {
      setSoundStatus(dom.audioMusicPreviewStatus, error.message, "bad");
    } finally {
      state.musicPreviewBusy = false;
      syncSoundPreviewButtons();
    }
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
    clearMusicPreview(defaultMusicPreviewNote(), "");
    if (dom.audioMusicUpload) dom.audioMusicUpload.value = "";
    syncAudioVisibility();
    dom.audioMusic.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function syncMusicOptions() {
    const source = musicSourceMode();
    const full = state.audioMusicOptions || [["none", "No music"]];
    const allowed = source === "own"
      ? new Set(["library"])
      : source === "generate"
        ? new Set(["minimax-music", "lyria-clip"])
        : new Set(["none"]);
    const options = full.filter(([id]) => allowed.has(id));
    const current = state.audio.music;
    const available = options.find(([id, , disabled]) => id !== "none" && !disabled);
    fillSelect(dom.audioMusic, options.length ? options : [["none", "No music"]]);
    let next = options.some(([id]) => id === current) ? current : (options[0]?.[0] || "none");
    if (source === "generate" && next !== "none") {
      const info = state.audioEngines?.music?.[next];
      if (info?.available === false && available) next = available[0];
    }
    dom.audioMusic.value = next;
    state.audio.music = next;
  }

  function voiceProviderName(engine) {
    return {
      elevenlabs: "ElevenLabs",
      minimax: "MiniMax Speech",
      heygen: "OpenRouter (HeyGen)",
      fish: "OpenRouter (Fish Audio)",
      gemini: "OpenRouter (Gemini TTS)",
    }[engine] || "";
  }

  function musicProviderName(engine) {
    return {
      "minimax-music": "MiniMax Music",
      "lyria-clip": "OpenRouter (Lyria 3)",
    }[engine] || "";
  }

  function translationMayUseCloudNow() {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.translationMayUseCloud !== "function") return false;
    return trust.translationMayUseCloud({
      mode: state.setup?.translation?.mode || "auto",
      providers: state.audioEngines?.translation || [],
    });
  }

  function rewriteMayUseCloudNow() {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.rewriteMayUseCloud !== "function") return false;
    return trust.rewriteMayUseCloud({ models: state.audioEngines?.rewrite_models || [] });
  }

  function cloudTextProviderName() {
    const translation = state.audioEngines?.translation || [];
    const rewrite = state.audioEngines?.rewrite_models || [];
    const ready = (id) => translation.some((item) => item.id === id && item.available !== false)
      || rewrite.some((item) => item.id === id && item.available !== false);
    const names = [];
    if (ready("opencode")) names.push("OpenCode Go");
    if (ready("openrouter")) names.push("OpenRouter");
    return names.join(" or ");
  }

  function setCostNote(node, text) {
    if (!node) return;
    node.textContent = text || "";
    node.hidden = !text;
  }

  function updateSoundUseNotes() {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.soundUseNote !== "function") return;
    const upload = state.audio.source === "upload";
    if (dom.audioVoiceUse) {
      dom.audioVoiceUse.textContent = trust.soundUseNote({
        kind: "voice",
        source: upload ? "upload" : "generate",
      });
    }
    const source = musicSourceMode();
    if (dom.audioMusicUse) {
      const note = trust.soundUseNote({ kind: "music", source });
      dom.audioMusicUse.textContent = note;
      dom.audioMusicUse.hidden = !note;
    }
  }

  function updateCostNotices() {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.costNotice !== "function") return;
    const mode = state.audio.mode;
    const voiceMode = ["bed", "voice", "full"].includes(mode);
    const upload = voiceMode && state.audio.source === "upload";
    const translate = voiceMode && !upload
      && !!targetLanguage() && targetLanguage() !== sourceLanguage()
      && translationMayUseCloudNow();
    const rewrite = voiceMode && !upload && rewriteMayUseCloudNow();
    const provider = cloudTextProviderName();
    const what = translate && rewrite
      ? "the transcript text and the cut script"
      : translate ? "the transcript text" : "the cut script";
    setCostNote(
      dom.audioCopyCost,
      (translate || rewrite)
        ? tr(trust.costNotice({ provider, what }))
        : "",
    );

    const voiceCloud = voiceMode && !upload && !!voiceProviderName(state.audio.engine);
    setCostNote(
      dom.audioVoiceCost,
      voiceCloud
        ? tr(trust.costNotice({
          provider: voiceProviderName(state.audio.engine),
          what: "the preview line and script text",
        }))
        : "",
    );

    const source = musicSourceMode();
    const musicCloud = ["music", "full"].includes(mode)
      && source === "generate"
      && !!musicProviderName(state.audio.music);
    setCostNote(
      dom.audioMusicCost,
      musicCloud
        ? tr(trust.costNotice({
          provider: musicProviderName(state.audio.music),
          what: "a music prompt",
        }))
        : "",
    );
  }

  function syncAudioVisibility() {
    const mode = dom.audioMode.value;
    const voiceMode = ["bed", "voice", "full"].includes(mode);
    const upload = voiceMode && state.audio.source === "upload";
    const musicMode = ["music", "full"].includes(mode);
    const rewriteMode = voiceMode && !upload;
    const hasUpload = !!state.audio.musicUpload;

    const setDisabled = (root, disabled) => {
      if (!root) return;
      root.querySelectorAll("input, select, textarea, button").forEach((node) => {
        node.disabled = disabled;
      });
      root.classList.toggle("is-disabled", disabled);
    };

    if (dom.audioModeDesc) {
      dom.audioModeDesc.textContent = AUDIO_MODE_META[mode] || AUDIO_MODE_META.keep;
    }
    setDisabled(dom.audioRewriteStep, !rewriteMode);
    // The copy card is a one-line note outside voice modes, never a dimmed form.
    dom.audioRewriteStep.classList.remove("is-disabled");
    dom.audioCopyForm.hidden = !rewriteMode;
    dom.audioCopyNote.hidden = rewriteMode;
    if (!rewriteMode) {
      const note = AUDIO_COPY_NOTE[mode] || AUDIO_COPY_NOTE.keep;
      dom.audioCopyNoteText.textContent = upload
        ? "Using your recording. Copy is off."
        : note;
      dom.audioCopySwitch.textContent = upload
        ? "Switch to generated voice →"
        : mode === "music" ? "Add a voice-over →" : "Rewrite this cut →";
    }
    if (dom.audioCopySwitch) dom.audioCopySwitch.disabled = false;
    setDisabled(dom.audioVoiceStep, !voiceMode);
    setDisabled(dom.audioMusicStep, !musicMode);
    if (voiceMode) {
      [dom.audioSourceGenerate, dom.audioSourceUpload].forEach((node) => {
        if (node) node.disabled = false;
      });
      if (dom.audioUploadButton) dom.audioUploadButton.disabled = false;
      if (!upload) {
        [dom.audioEngine, dom.audioVoice, dom.audioRate].forEach((node) => {
          if (node) node.disabled = false;
        });
      }
    }
    if (musicMode) {
      dom.audioMusicStep.querySelectorAll('input[name="audio-music-source"]').forEach((node) => {
        node.disabled = false;
      });
      if (dom.audioMusic) dom.audioMusic.disabled = false;
      if (dom.audioTrack) dom.audioTrack.disabled = hasUpload;
      if (dom.audioPrompt) dom.audioPrompt.disabled = false;
      if (dom.audioGain) dom.audioGain.disabled = false;
      if (dom.audioDuck) dom.audioDuck.disabled = false;
      if (dom.audioBeatSync) dom.audioBeatSync.disabled = false;
      if (dom.audioMusicUploadButton) dom.audioMusicUploadButton.disabled = false;
      [dom.audioMusicBlockBgm, dom.audioMusicBlockGenerate, dom.audioUseBgm].forEach((node) => {
        if (node) node.disabled = false;
      });
    }
    if (dom.mixerOpen) dom.mixerOpen.disabled = false;
    if (state.lastAudioMode !== mode) {
      state.lastAudioMode = mode;
      if (mode === "music") showSoundTab("music");
      else if (voiceMode) showSoundTab("voice");
    }
    if (dom.audioGenerateVoice) dom.audioGenerateVoice.hidden = upload;
    if (dom.audioUseRecording) dom.audioUseRecording.disabled = !voiceMode;
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
    const noSource = source === "none";
    dom.audioTrackField.hidden = source !== "own" || hasUpload;
    dom.audioTrack.disabled = hasUpload;
    dom.audioMusicUploadBox.hidden = source !== "own";
    dom.audioMusicUploadClear.hidden = !hasUpload;
    dom.audioMusicUploadName.textContent = source === "own" && hasUpload
      ? `${state.audio.musicUploadName || "music"} · ${Number(state.audio.musicUploadDuration || 0).toFixed(1)}s`
      : "Use your own music file.";
    dom.audioPromptField.hidden = source !== "generate";
    dom.audioGainField.hidden = noSource;
    dom.audioDuckField.hidden = noSource;
    dom.audioBeatSyncField.hidden = noSource;
    if (musicMode) {
      if (dom.audioMusic) {
        dom.audioMusic.disabled = noSource;
        dom.audioMusic.title = noSource ? "Choose a music source first." : "";
      }
      if (dom.audioGenerateMusic) dom.audioGenerateMusic.disabled = noSource;
      if (dom.audioMusicBlock) dom.audioMusicBlock.hidden = !noSource;
    } else if (dom.audioMusicBlock) {
      dom.audioMusicBlock.hidden = true;
    }
    syncSoundPreviewButtons();
    updateSoundUseNotes();
    updateCostNotices();
    if (state.job && state.plan) updateRenderPanel();
  }

  function audioBlockReason() {
    const mode = state.audio.mode;
    if (mode === "music" && musicSourceMode() === "none") {
      return "Choose a music source before rendering.";
    }
    const music = state.audioEngines?.music;
    if (["music", "full"].includes(mode) && musicSourceMode() === "generate" && music) {
      const ready = ["minimax-music", "lyria-clip"].filter((id) => music[id]?.available);
      if (!ready.length) {
        return "Music generation needs a MiniMax or OpenRouter key. Add one in Setup, or choose Use my BGM.";
      }
      const selected = state.audio.music;
      if (selected && music[selected] && music[selected].available === false) {
        return `${musicLabel(selected)} is unavailable. Add a key in Setup, or choose the other music engine.`;
      }
    }
    const voices = state.audioEngines?.voices;
    if (["bed", "voice", "full"].includes(mode) && state.audio.source !== "upload"
        && voices && state.audio.engine && voices[state.audio.engine]
        && voices[state.audio.engine].available === false) {
      return `${engineLabel(state.audio.engine)} is unavailable. Add a key in Setup, or choose Use my recording.`;
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
      clearMusicPreview("Your BGM is ready. Play ▶ for a 12s preview.", "ok");
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
      clearVoicePreview("Using your recording. Copy is off.");
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
    select.innerHTML = options.map(([value, label, disabled]) => (
      `<option value="${esc(value)}"${disabled ? " disabled" : ""}>${esc(label)}</option>`
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
    updateTextAvailability();
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

  function shownRender() {
    const finalRecord = findRender("final");
    const draftRecord = findRender("draft");
    const hookId = currentHookId();
    const finalMatches = finalRecord && finalRecord.hook === hookId;
    const draftMatches = draftRecord && draftRecord.hook === hookId;
    const draftNewer = draftMatches && draftRecord.status === "ready"
      && (!finalMatches || finalRecord.status !== "ready"
        || (draftRecord.updated || 0) > (finalRecord.updated || 0));
    if (draftNewer) return draftRecord;
    if (finalMatches && finalRecord.status === "ready") return finalRecord;
    return null;
  }

  async function createReviewLink() {
    if (!state.job) return;
    // Share the artifact on screen, not whichever render wrote reel_<target>.mp4 last.
    const artifactId = String(shownRender()?.artifact_id || "");
    try {
      const query = artifactId
        ? ""
        : `?target=${state.target}&aspect=${encodeURIComponent(state.aspect)}`;
      const result = await api(
        `/api/jobs/${state.job.id}/share${query}`,
        {
          method: "POST",
          body: JSON.stringify(artifactId ? { artifact_id: artifactId } : {}),
        },
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

  async function exportCut(kind) {
    if (!state.job) return;
    const clips = state.edited && state.plan?.clips?.length ? state.plan.clips : null;
    const headers = {};
    const token = tokenValue();
    if (token) headers.Authorization = `Bearer ${token}`;
    // Fetch, not a new tab: a refusal (no transcript) shows as a toast
    // instead of a raw JSON tab.
    const request = clips
      ? fetch(`/api/classic/jobs/${state.job.id}/export/${kind}`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          target: state.target,
          order: state.order,
          hook_scene: state.overrideHook,
          clips,
        }),
      })
      : fetch(`/api/jobs/${state.job.id}/export/${kind}?target=${state.target}`
        + `&order=${encodeURIComponent(state.order)}`
        + (state.overrideHook !== null ? `&hook_scene=${state.overrideHook}` : ""), { headers });
    try {
      const response = await request;
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = /filename="([^"]+)"/.exec(disposition);
      const name = match ? match[1] : `cut-${state.target}s.${kind}`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(clips ? `Exported the edited cut as ${kind.toUpperCase()}.` : `Exported ${kind.toUpperCase()}.`);
    } catch (error) {
      toast(error.message);
    }
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
    state.playerScrollKey = null;
    try {
      let records = [];
      const errors = [];
      if (state.edited) {
        const hooks = await api(`/api/jobs/${state.job.id}/hooks?target=${state.target}&limit=3`);
        for (const hook of (hooks.hooks || []).slice(0, 3)) {
          try {
            const body = {
              target: state.target,
              hook_scene: hook.scene,
              quality: "final",
              aspect: state.aspect,
              captions: state.captions,
              preset: state.preset || null,
              order: "source",
              clips: clipsForHook(hook.scene),
              script_id: state.scriptId || null,
              audio: currentAudioPlan(),
              edit: classicEditPayload(),
            };
            const requestSig = renderSignatureOf(body);
            const result = await api(`/api/jobs/${state.job.id}/render`, {
              method: "POST",
              body: JSON.stringify({ ...body, request_sig: requestSig }),
            });
            if (result.render) {
              records.push(result.render);
              rememberRenderSignature(result.render, body);
            }
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
        records.forEach((record) => {
          const base = renderRequestFor(record.target, record.quality || "final");
          rememberRenderSignature(record, {
            ...base,
            hook_scene: record.hook,
            clips: null,
          });
        });
        errors.push(...(result.errors || []));
      }
      state.cutDirty = false;
      state.job.renders = state.job.renders || {};
      records.forEach((record) => {
        state.job.renders[record.record_key || renderKey(record.target)] = record;
        if (record.hook === currentHookId()) {
          rememberRenderSignature(
            record,
            renderRequestFor(record.target, record.quality || "final"),
          );
        }
      });
      state.cutDirty = false;
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
    const allowedVoices = new Set(["say", "kokoro", "minimax", "heygen", "fish", "gemini", "elevenlabs"]);
    const voiceOptions = Object.entries(engines.voices || {})
      .filter(([id]) => allowedVoices.has(id))
      .map(([id, info]) => [
        id,
        `${engineLabel(id)}${info.size_mb ? ` (~${info.size_mb} MB)` : ""}`, !info.available,
      ]);
    fillSelect(dom.audioEngine, voiceOptions);
    const musicOptions = [["none", "No music"]];
    const allowedMusic = new Set(["library", "minimax-music", "lyria-clip"]);
    Object.entries(engines.music || {}).forEach(([id, info]) => {
      if (!allowedMusic.has(id)) return;
      musicOptions.push([
        id,
        `${musicLabel(id)}${info.size_mb ? ` (~${info.size_mb} MB)` : ""}`, !info.available,
      ]);
    });
    state.audioMusicOptions = musicOptions;
    fillSelect(dom.audioMusic, musicOptions);
    fillSelect(dom.audioLang, AUDIO_LANGUAGES);
    const rewriteOptions = [["auto", "Auto · OpenCode → OpenRouter"]];
    (engines.rewrite_models || []).forEach((item) => {
      rewriteOptions.push([
        item.id,
        `${item.name}${item.size_mb ? ` (~${item.size_mb} MB)` : ""}`, !item.available,
      ]);
    });
    fillSelect(dom.audioRewrite, rewriteOptions);
    dom.audioRewrite.value = state.audio.rewrite || "auto";
    const translateOptions = [["auto", "Auto · best ready engine"]];
    (engines.translation || []).forEach((item) => {
      translateOptions.push([
        item.id,
        `${translateLabel(item.id)}`, !item.available,
      ]);
    });
    fillSelect(dom.audioProvider, translateOptions);
    const preferredTts = state.setup?.tts?.provider;
    if (preferredTts && allowedVoices.has(preferredTts)
        && !["auto", "local"].includes(preferredTts)
        && engines.voices?.[preferredTts]?.available) {
      state.audio.engine = preferredTts;
    }
    const firstVoice = voiceOptions.find(([, , disabled]) => !disabled);
    if (!state.audio.engine || engines.voices?.[state.audio.engine]?.available === false) {
      state.audio.engine = firstVoice?.[0] || state.audio.engine || "";
    }
    dom.audioEngine.value = state.audio.engine;
    dom.audioMusic.value = state.audio.music;
    syncMusicOptions();
    dom.audioLang.value = state.audio.lang;
    dom.audioProvider.value = state.audio.provider || "auto";
    loadAudioVoices();
    loadAudioTracks();
    refreshAudioStatus();
    loadAudioScript();
    syncSoundPreviewButtons();
    renderSetupEngines();
    updatePrivacyPill();
    updateCostNotices();
    if (state.job && targetLanguage() && targetLanguage() !== sourceLanguage()) {
      warmTranslation();
    }
  }

  function translateLabel(id) {
    return {
      apple_fm: "Apple Translation",
      opencode: "OpenCode Go · DeepSeek",
      openrouter: "OpenRouter · DeepSeek",
    }[id] || id;
  }

  function engineLabel(id) {
    return {
      say: "Apple say",
      kokoro: "Kokoro int8",
      elevenlabs: "ElevenLabs (API key)",
      minimax: "MiniMax Speech 2.8",
      fish: "OpenRouter Fish S2.1 Free",
      heygen: "OpenRouter HeyGen Voice Turbo (free)",
      gemini: "OpenRouter Gemini Flash-Lite TTS",
      openrouter: "OpenRouter",
    }[id] || id;
  }

  function musicLabel(id) {
    return {
      library: "My own track",
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
        const needsKey = ["elevenlabs", "minimax", "heygen", "fish", "gemini"].includes(engine);
        fillSelect(dom.audioVoice, [["", needsKey ? "Add the key in Setup" : "No voices found"]]);
        state.audio.voice = "";
        syncSoundPreviewButtons();
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
      syncSoundPreviewButtons();
    } catch (error) {
      fillSelect(dom.audioVoice, [["", error.message]]);
      state.audio.voice = "";
      syncSoundPreviewButtons();
    }
  }

  async function loadAudioTracks() {
    const source = state.audio.music;
    if (source !== "library" && source !== "cc0") {
      fillSelect(dom.audioTrack, [["", "Not needed for AI music"]]);
      state.audio.track = "";
      syncSoundPreviewButtons();
      return;
    }
    dom.audioTrack.innerHTML = `<option value="">Auto mood</option>`;
    try {
      const result = await api(`/api/audio/music?source=${encodeURIComponent(source)}`);
      const tracks = result.tracks || [];
      if (!tracks.length) {
        fillSelect(dom.audioTrack, [["", `Empty folder · drop files in assets/music/${source}`]]);
        state.audio.track = "";
        syncSoundPreviewButtons();
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
      syncSoundPreviewButtons();
    } catch (error) {
      fillSelect(dom.audioTrack, [["", error.message]]);
      state.audio.track = "";
      syncSoundPreviewButtons();
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

  function languageCode(value) {
    return String(value || "").split("-")[0];
  }

  function sourceLanguage() {
    return languageCode(
      (state.job?.analysis?.engine || {}).transcript_language || "en",
    );
  }

  function targetLanguage() {
    return languageCode(state.audio?.lang || "");
  }

  function transcriptInfo() {
    const summary = state.job?.analysis?.transcript || null;
    const engine = state.job?.analysis?.engine || {};
    const segments = summary?.segments;
    const lines = Array.isArray(segments) ? segments.length : Number(segments) || 0;
    const text = String(summary?.text || "").trim();
    return { ready: lines > 0 || !!text || !!engine.whisper, lines };
  }

  function paintTranscriptReady() {
    if (!dom.copyTranscript) return;
    const info = transcriptInfo();
    dom.copyTranscript.hidden = !info.ready;
    dom.copyTranscript.title = info.ready
      ? `Transcript ready${info.lines ? ` · ${info.lines} lines` : ""}`
      : "";
  }

  function isAbortError(error) {
    return error?.name === "AbortError";
  }

  function paintTranslateBadge(info) {
    if (!dom.translateBadge) return;
    const target = targetLanguage();
    if (!target || target === sourceLanguage() || !transcriptInfo().ready) {
      dom.translateBadge.hidden = true;
      delete dom.translateBadge.dataset.status;
      return;
    }
    const current = state.translation?.target === target ? state.translation : null;
    const incoming = info && (!info.target || languageCode(info.target) === target)
      ? info
      : null;
    const status = incoming?.status || current?.status || "idle";
    if (!["ready", "running", "failed"].includes(status)) {
      dom.translateBadge.hidden = true;
      delete dom.translateBadge.dataset.status;
      return;
    }
    dom.translateBadge.hidden = false;
    dom.translateBadge.dataset.status = status;
    if (status === "ready") {
      dom.translateBadge.textContent = "✓ Translation ready";
    } else if (status === "failed") {
      dom.translateBadge.textContent = "Translation failed";
    } else {
      dom.translateBadge.textContent = "Translating…";
    }
  }

  async function translationStatus(target, jobId = state.job?.id, signal = null) {
    return api(
      `/api/classic/jobs/${jobId}/translate/status?target=${encodeURIComponent(target)}`,
      signal ? { signal } : {},
    );
  }

  async function ensureTranslation(controller) {
    const scriptOwned = controller?.scriptOwned === true;
    const target = targetLanguage();
    const jobId = state.job?.id;
    if (!jobId || !target || target === sourceLanguage()) {
      paintTranslateBadge(null);
      return true;
    }
    if (!transcriptInfo().ready) {
      state.translation = null;
      paintTranslateBadge(null);
      dom.audioRewriteNote.textContent = "No transcript to translate. Change Language back to the source.";
      return false;
    }
    if (state.translation?.job_id === jobId
        && state.translation.target === target
        && state.translation.status === "ready") {
      paintTranslateBadge(state.translation);
      return true;
    }
    let info;
    try {
      info = await translationStatus(target, jobId, controller?.signal);
    } catch (error) {
      if (isAbortError(error) || controller?.signal.aborted) return false;
      dom.audioRewriteNote.textContent = `Translation check failed: ${error.message}`;
      return false;
    }
    if (state.job?.id !== jobId || targetLanguage() !== target) return false;
    if (info.status !== "ready" && info.status !== "running") {
      try {
        info = await api(`/api/classic/jobs/${jobId}/translate`, {
          method: "POST",
          signal: controller?.signal,
          body: JSON.stringify({ target, provider: "auto" }),
        });
      } catch (error) {
        if (isAbortError(error) || controller?.signal.aborted) return false;
        if (error.status === 409) {
          // No transcript is not a translation failure.
          state.translation = null;
          paintTranslateBadge(null);
          dom.audioRewriteNote.textContent = "No transcript to translate. Change Language back to the source.";
          return false;
        }
        dom.audioRewriteNote.textContent = `Translation failed: ${error.message}`;
        paintTranslateBadge({ status: "failed", target });
        return false;
      }
    }
    if (state.job?.id !== jobId || targetLanguage() !== target) return false;
    state.translation = { ...info, target, job_id: jobId };
    paintTranslateBadge(state.translation);
    let misses = 0;
    while (info.status === "running") {
      if (controller?.signal.aborted) return false;
      if (scriptOwned && controller && state.scriptAbort !== controller) return false;
      if (state.job?.id !== jobId || targetLanguage() !== target) return false;
      await new Promise((resolve) => setTimeout(resolve, 900));
      if (controller?.signal.aborted) return false;
      if (state.job?.id !== jobId || targetLanguage() !== target) return false;
      try {
        info = await translationStatus(target, jobId, controller?.signal);
        misses = 0;
      } catch (error) {
        if (isAbortError(error) || controller?.signal.aborted) return false;
        // A failed status read is not a failed translation. Try again.
        misses += 1;
        if (misses >= 3) {
          dom.audioRewriteNote.textContent =
            `Could not read translation status: ${error.message}`;
          return false;
        }
        continue;
      }
      if (state.job?.id !== jobId || targetLanguage() !== target) return false;
      state.translation = { ...info, target, job_id: jobId };
      paintTranslateBadge(state.translation);
    }
    if (info.status === "failed") {
      dom.audioRewriteNote.textContent =
        `Translation failed: ${info.error || "unknown error"}`;
      return false;
    }
    return info.status === "ready";
  }

  function cancelTranslationWarm() {
    const warm = state.translationWarm;
    state.translationWarm = null;
    if (warm?.controller) {
      try { warm.controller.abort(); } catch (_) { /* already settled */ }
    }
  }

  function warmTranslation() {
    const jobId = state.job?.id;
    const target = targetLanguage();
    if (!jobId || !target || target === sourceLanguage() || !transcriptInfo().ready) {
      cancelTranslationWarm();
      paintTranslateBadge(null);
      return;
    }
    // A cloud translation costs credits. Never start one automatically: the
    // founder presses Story cut after seeing the cost notice. Local-only
    // translation can still warm in the background.
    if (!state.audioEngines || translationMayUseCloudNow()) {
      cancelTranslationWarm();
      paintTranslateBadge(null);
      return;
    }
    if (state.translation?.job_id === jobId
        && state.translation.target === target
        && state.translation.status === "ready") {
      paintTranslateBadge(state.translation);
      return;
    }
    if (state.translationWarm?.jobId === jobId
        && state.translationWarm?.target === target) return;
    cancelTranslationWarm();
    const controller = new AbortController();
    state.translationWarm = { jobId, target, controller };
    state.translation = {
      job_id: jobId, target, status: "running",
      done: 0, total: transcriptInfo().lines, batch: 0, batches: 0,
    };
    paintTranslateBadge(state.translation);
    ensureTranslation(controller)
      .catch(() => {})
      .finally(() => {
        if (state.translationWarm?.controller === controller) state.translationWarm = null;
      });
  }

  function resetAudioScript(message = "Choose a mode, then Story cut. The full transcript is reused.") {
    if (!dom.audioScript) return;
    cancelAudioScript();
    if (dom.audioRewriteNote) dom.audioRewriteNote.textContent = message;
    dom.audioScript.hidden = false;
    dom.audioScript.innerHTML = `
      <div class="script-head">
        <span class="label">Script</span>
        <span class="hint">${esc(message)}</span>
      </div>`;
  }

  function cancelAudioScript() {
    // A setting change replaces the cut or the language. The old request no
    // longer owns the panel, so stop waiting on it and free the button.
    if (state.scriptAbort) {
      try { state.scriptAbort.abort(); } catch (_) { /* already settled */ }
      state.scriptAbort = null;
    }
    if (state.scriptTimer) {
      clearInterval(state.scriptTimer);
      state.scriptTimer = null;
    }
    if (dom.audioRewriteRun) dom.audioRewriteRun.disabled = false;
  }

  function showScriptFailure(message) {
    const note = String(message || "Copy failed.");
    if (state.lastScript?.lines?.length) {
      renderScriptBlock(
        state.lastScript.lines,
        state.lastScript,
        `${note} · showing last good script.`,
      );
      return;
    }
    dom.audioRewriteNote.textContent = note;
    dom.audioScript.innerHTML =
      `<div class="script-head"><span class="hint">${esc(note)}</span></div>`;
  }

  async function loadAudioScript(options = {}) {
    const run = options.run === true;
    const forceTranslate = options.forceTranslate === true;
    if (!state.job || !state.plan || !dom.audioScript) return;
    const audio = state.audio;
    const voiceMode = ["bed", "voice", "full"].includes(audio.mode);
    if (!voiceMode || (audio.source === "upload" && voiceMode)) {
      cancelAudioScript();
      dom.audioScript.hidden = true;
      dom.audioScript.innerHTML = "";
      return;
    }
    if (!run) {
      resetAudioScript();
      return;
    }
    // One rewrite at a time. A repeat click while the cut is being written
    // must not start a second request or a second server job.
    if (state.scriptAbort) return;
    const jobId = state.job.id;
    const controller = new AbortController();
    controller.scriptOwned = true;
    state.scriptAbort = controller;
    dom.audioScript.hidden = false;
    const startedAt = Date.now();
    if (state.scriptTimer) clearInterval(state.scriptTimer);
    const ticking = setInterval(() => {
      if (state.scriptAbort !== controller) return;
      const seconds = Math.round((Date.now() - startedAt) / 1000);
      dom.audioRewriteNote.textContent =
        `Translating and rewriting… ${seconds}s. The first run translates the whole video once; later runs reuse the cache.`;
    }, 1000);
    state.scriptTimer = ticking;
    dom.audioRewriteNote.textContent =
      "Translating and rewriting… 0s. The first run translates the whole video once; later runs reuse the cache.";
    dom.audioRewriteRun.disabled = true;
    try {
      // The language warm-up owns translation. Story cut only waits for the
      // on-disk memo, then writes this cut.
      const translatedReady = await ensureTranslation(controller);
      if (!translatedReady) {
        if (controller.signal.aborted || state.scriptAbort !== controller) return;
        showScriptFailure(
          dom.audioRewriteNote.textContent || "Translation is not ready.",
        );
        return;
      }
      if (dom.translateBadge) {
        dom.translateBadge.hidden = false;
        dom.translateBadge.dataset.status = "running";
        dom.translateBadge.textContent = "Rewriting…";
      }
      dom.audioScript.innerHTML =
        `<div class="script-head"><span class="label">Script</span><span class="hint">working…</span></div>`;
      const result = await api(`/api/jobs/${jobId}/audio/script`, {
        method: "POST",
        signal: controller.signal,
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
      if (state.job?.id !== jobId) return;
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
          ? (result.rewrite_status?.error || "Copy unavailable; kept the literal translation.")
          : "");
      const note = fallbackText
        ? `Fallback: ${fallbackText}`
        : result.translated
          ? `${result.translation_status?.provider === "cache" ? "Translation reused · " : ""}Translated to ${result.target} and rewritten for ${state.target}s.`
          : `Copied for ${state.target}s.`;
      renderScriptBlock(lines, result, note);
      state.translation = {
        job_id: state.job.id, target: targetLanguage(), status: "ready",
        done: 1, total: 1, batch: 1, batches: 1,
      };
      paintTranslateBadge(state.translation);
      loadHistory();
    } catch (error) {
      if (error?.name === "AbortError") {
        // A setting change already cleared the panel; keep that message.
        if (state.scriptAbort === controller) {
          dom.audioRewriteNote.textContent = "Copy cancelled. Press Story cut to run it again.";
        }
        return;
      }
      showScriptFailure(`Copy failed: ${error.message}`);
      loadHistory();
    } finally {
      if (state.scriptTimer === ticking) {
        clearInterval(ticking);
        state.scriptTimer = null;
      }
      if (state.scriptAbort === controller) {
        state.scriptAbort = null;
        dom.audioRewriteRun.disabled = false;
      }
      // Rewriting is over; the badge belongs to translation again.
      if (state.job?.id === jobId) paintTranslateBadge(state.translation);
    }
  }

  function scriptHeadLabel(result) {
    const warning = result.warning || result.rewrite_status?.warning || "";
    const rewriteValue = result.rewrite;
    const rewrite = typeof rewriteValue === "string"
      ? rewriteValue
      : rewriteValue?.used || result.rewrite_status?.used || "";
    if (warning || result.rewrite_status?.fallback) return "fallback";
    if (rewrite) return rewrite === "literal" ? "literal" : `copy · ${rewrite}`;
    return result.mode || "literal";
  }

  function renderScriptBlock(lines, result, note, options = {}) {
    if (!dom.audioScript) return;
    const originalText = lines.map((line) => String(line.original || line.literal || line.text || "")).join("\n");
    const finalText = lines.map((line) => String(line.text || "")).join("\n");
    const warning = result.warning
      || (result.rewrite_status?.fallback
        ? (result.rewrite_status?.error || "Copy unavailable; kept the literal translation.")
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
          <button class="ghost small" data-copy-script="final" type="button">Copy ${result.translated ? "translation" : "copy"}</button>
          ${result.translated && !options.snapshot ? '<button class="ghost small" data-script-retry type="button">Retry translation</button>' : ""}
        </span>
      </div>
      <div class="script-list script-grid">
        <div class="script-column-label">Original</div>
        <div class="script-column-label">${result.translated ? "Translation · copy" : "Copy"}</div>
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
        resetAudioScript("Edit saved. Press Story cut to regenerate the cut.");
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
    const note = "Restored from history. Overrides applied; press Story cut to regenerate audio.";
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
    if (!state.job) return;
    const pieces = [];
    const mode = state.audio.mode;
    if (mode === "voice" && !engines?.separation?.demucs?.available) {
      pieces.push(`Demucs missing · ${engines?.separation?.demucs?.install || "pip install demucs"}`);
    }
    if (state.audioMoods.length && ["music", "full"].includes(mode)) {
      pieces.push(`auto mood: ${state.audioMoods.slice(0, 3).join(", ")}`);
    }
    const block = audioBlockReason();
    const musicNeedsSource = mode === "music" && musicSourceMode() === "none";
    if (block && !musicNeedsSource) pieces.push(block);
    const needsSetup = !!block && !musicNeedsSource && /setup|key|engine|unavailable/i.test(block);
    dom.audioStatus.textContent = pieces.join(" · ");
    dom.audioStatus.hidden = !pieces.length;
    if (dom.audioStatusSetup) dom.audioStatusSetup.hidden = !needsSetup;
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

  function classicTextSupported() {
    return CLASSIC_TEXT_ASPECTS.includes(state.aspect);
  }

  function classicCutKey(clips) {
    return (clips || []).map((clip) => {
      const start = Number(clip.start) || 0;
      const end = clip.end !== undefined && clip.end !== null
        ? Number(clip.end)
        : start + (Number(clip.dur) || 0);
      return [
        clip.scene,
        start.toFixed(3),
        end.toFixed(3),
        clip.role || "beat",
      ].join(":");
    }).join("|");
  }

  function classicPlanClips() {
    return (state.plan?.clips || []).map((clip) => ({ ...clip }));
  }

  function classicLayerId(prefix) {
    const taken = new Set([
      ...state.classicText.overlays.map((layer) => layer.id),
      ...state.classicText.effects.map((effect) => effect.id),
    ]);
    let suffix = 1;
    while (taken.has(`${prefix}${suffix}`)) suffix += 1;
    return `${prefix}${suffix}`;
  }

  function updateTextAvailability() {
    const trust = window.ClassicTrust;
    const supported = trust && typeof trust.textShapeNote === "function"
      ? !trust.textShapeNote({ aspect: state.aspect })
      : classicTextSupported();
    if (dom.textShapeNote) {
      const note = trust && typeof trust.textShapeNote === "function"
        ? trust.textShapeNote({ aspect: state.aspect })
        : (supported ? "" : "Text overlays and effects render on 9:16 and 4:5. Switch the shape to use them.");
      dom.textShapeNote.hidden = !note;
      dom.textShapeNote.textContent = note;
    }
    if (!dom.textLayerControls) return;
    dom.textLayerControls.querySelectorAll("input, select, button").forEach((node) => {
      node.disabled = !supported;
    });
    dom.textLayerControls.classList.toggle("is-disabled", !supported);
  }

  function syncClassicTextDefaults() {
    const total = Math.max(0, Number(state.plan?.total) || 0);
    [dom.textOverlayStart, dom.textOverlayEnd].forEach((input) => {
      if (input) input.max = String(total);
    });
    if (dom.effectDuration) {
      dom.effectDuration.max = String(Math.max(0.2, total));
    }
    if (dom.textOverlayStart) {
      const start = Number(dom.textOverlayStart.value);
      if (!Number.isFinite(start) || start < 0 || start >= total) {
        dom.textOverlayStart.value = "0";
      }
    }
    if (dom.textOverlayEnd) {
      const end = Number(dom.textOverlayEnd.value);
      if (!Number.isFinite(end) || end <= 0 || end > total) {
        dom.textOverlayEnd.value = Math.min(2.5, total).toFixed(1);
      }
    }
  }

  function renderClassicText() {
    if (!dom.textOverlayList || !dom.effectList) return;
    const overlays = state.classicText.overlays;
    const effects = state.classicText.effects;
    dom.textOverlayList.innerHTML = overlays.length
      ? overlays.map((layer) => {
        const position = CLASSIC_TEXT_POSITIONS[layer.anchor] || "center";
        return `
          <div class="text-layer-row" role="listitem" data-overlay-id="${esc(layer.id)}">
            <span class="text-layer-copy" title="${esc(layer.text)}">${esc(layer.text)}</span>
            <span class="text-layer-meta">${esc(position)} · ${fmtTime(layer.start, 1)}–${fmtTime(layer.end, 1)}</span>
            <button class="text-layer-del" type="button" data-overlay-delete="${esc(layer.id)}" title="Delete text" aria-label="Delete text">✕</button>
          </div>`;
      }).join("")
      : '<p class="hint text-layer-empty">No text yet.</p>';
    dom.effectList.innerHTML = effects.length
      ? effects.map((effect) => `
          <div class="text-layer-row effect-row" role="listitem" data-effect-id="${esc(effect.id)}">
            <span class="text-layer-copy">${esc(CLASSIC_EFFECT_LABELS[effect.kind] || effect.kind)}</span>
            <span class="text-layer-meta">${fmtTime(effect.start, 1)}–${fmtTime(effect.end, 1)}</span>
            <button class="text-layer-del" type="button" data-effect-delete="${esc(effect.id)}" title="Delete effect" aria-label="Delete effect">✕</button>
          </div>`).join("")
      : '<p class="hint text-layer-empty">No effects yet.</p>';
  }

  function applyClassicTextCut(cut, key = "") {
    state.classicText.dataKey = key;
    state.classicText.clipsHash = cut?.clips_hash || "";
    state.classicText.overlays = Array.isArray(cut?.overlays) ? cut.overlays : [];
    state.classicText.effects = Array.isArray(cut?.effects) ? cut.effects : [];
    state.classicText.clean = Array.isArray(cut?.clean) ? cut.clean : [];
    if (cut && cut.clean_reset) {
      // Boxes saved before boxes were stored in source space would land in the
      // wrong place, so the server drops them. Say so instead of going quiet.
      setCleanStatus(`${cut.clean_reset} old box${cut.clean_reset === 1 ? "" : "es"} were drawn before this fix and were cleared. Draw them again.`);
    }
    if (!state.classicText.clean.some((layer) => layer.id === state.classicText.selection)) {
      state.classicText.selection = "";
    }
    renderClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  async function refreshClassicText(force = false) {
    if (!state.job || !state.plan) return;
    const clips = classicPlanClips();
    if (!clips.length) return;
    const key = classicCutKey(clips);
    if (!force && key === state.classicText.loadedKey) return;
    state.classicText.loadedKey = key;
    const seq = ++state.classicText.seq;
    const rev = state.classicText.rev;
    try {
      const result = await api(`/api/classic/jobs/${state.job.id}/text`, {
        method: "POST",
        body: JSON.stringify({ clips }),
      });
      if (seq !== state.classicText.seq || rev !== state.classicText.rev) return;
      applyClassicTextCut(result.cut, key);
      updateRenderPanel();
    } catch (_) {
      if (seq !== state.classicText.seq) return;
      state.classicText.loadedKey = "";
      applyClassicTextCut(null);
    }
  }

  async function persistClassicText(clips) {
    if (!state.job || !clips.length) return;
    try {
      await api(`/api/classic/jobs/${state.job.id}/text`, {
        method: "PUT",
        body: JSON.stringify({
          clips,
          overlays: state.classicText.overlays,
          effects: state.classicText.effects,
          clean: cleanPayloadLayers(),
        }),
      });
    } catch (error) {
      toast(error.message);
    }
  }

  function saveClassicText() {
    state.classicText.rev += 1;
    if (!state.job || !state.plan) return;
    updateRenderPanel();
    const clips = classicPlanClips();
    const key = classicCutKey(clips);
    state.classicText.loadedKey = key;
    state.classicText.dataKey = key;
    if (state.classicText.saveTimer) clearTimeout(state.classicText.saveTimer);
    state.classicText.saveTimer = setTimeout(() => {
      state.classicText.saveTimer = null;
      persistClassicText(clips);
    }, 350);
  }

  function addClassicOverlay() {
    if (!classicTextSupported()) {
      toast("Text overlays render on 9:16 and 4:5 only.");
      return;
    }
    const text = (dom.textOverlayText?.value || "").trim();
    if (!text) {
      toast("Type the text first.");
      return;
    }
    const total = Math.max(0, Number(state.plan?.total) || 0);
    if (total < 0.2) {
      toast("The cut is too short for text.");
      return;
    }
    const start = clamp(Number(dom.textOverlayStart?.value) || 0, 0, Math.max(0, total - 0.2));
    let end = Number(dom.textOverlayEnd?.value);
    if (!Number.isFinite(end)) end = Math.min(total, start + 2.5);
    end = clamp(end, start + 0.2, total);
    if (end <= start) {
      toast("End must be after start.");
      return;
    }
    const position = dom.textOverlayAnchor?.value || "center";
    const kind = CLASSIC_TEXT_KINDS[position] || "title";
    state.classicText.overlays.push({
      id: classicLayerId("tx"),
      type: "text",
      kind,
      text,
      start: round2(start),
      end: round2(end),
      anchor: CLASSIC_TEXT_ANCHORS[position] || "center",
      box: { ...CLASSIC_TEXT_BOX[kind] },
      z: 10 + state.classicText.overlays.length,
      style: {},
      safe_zone: true,
      opacity: 1,
    });
    dom.textOverlayText.value = "";
    dom.textOverlayStart.value = String(round2(end));
    dom.textOverlayEnd.value = Math.min(total, round2(end) + 2.5).toFixed(1);
    saveClassicText();
    renderClassicText();
  }

  function addClassicEffect() {
    if (!classicTextSupported()) {
      toast("Effects render on 9:16 and 4:5 only.");
      return;
    }
    const total = Math.max(0, Number(state.plan?.total) || 0);
    if (total < 0.2) {
      toast("The cut is too short for an effect.");
      return;
    }
    const kind = dom.effectKind?.value || "punch_in";
    const seconds = clamp(Number(dom.effectDuration?.value) || 1.2, 0.2, total);
    state.classicText.effects.push({
      id: classicLayerId(kind === "circle" ? "fx" : "mo"),
      kind,
      start: 0,
      end: round2(Math.min(total, seconds)),
      duration: round2(Math.min(total, seconds)),
    });
    saveClassicText();
    renderClassicText();
  }

  function deleteClassicOverlay(id) {
    state.classicText.overlays = state.classicText.overlays.filter((layer) => layer.id !== id);
    saveClassicText();
    renderClassicText();
  }

  function deleteClassicEffect(id) {
    state.classicText.effects = state.classicText.effects.filter((effect) => effect.id !== id);
    saveClassicText();
    renderClassicText();
  }

  function classicEditPayload() {
    if (!classicTextSupported()) return null;
    const key = classicCutKey(classicPlanClips());
    if (!key || key !== state.classicText.dataKey) return null;
    const overlays = state.classicText.overlays.map((layer) => ({ ...layer }));
    const effects = state.classicText.effects.map((effect) => ({
      id: effect.id,
      kind: effect.kind,
      start: Number(effect.start) || 0,
      end: Number(effect.end) || 0,
    }));
    // Clean boxes ride with the same Edit, so the reel and the preview agree.
    const clean = cleanPayloadLayers();
    if (!overlays.length && !effects.length && !clean.length) return null;
    return { overlays, effects, clean };
  }

  function bindClassicText() {
    dom.textOverlayAdd?.addEventListener("click", addClassicOverlay);
    dom.effectAdd?.addEventListener("click", addClassicEffect);
    dom.textOverlayText?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addClassicOverlay();
      }
    });
    dom.textOverlayList?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-overlay-delete]");
      if (button) deleteClassicOverlay(button.dataset.overlayDelete);
    });
    dom.effectList?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-effect-delete]");
      if (button) deleteClassicEffect(button.dataset.effectDelete);
    });
  }

  // ---------------------------------------------------------------- clean boxes
  //
  // C1/C2: the Clean layer is a box on the cut. The frame beside it is not a
  // CSS approximation — it is the frame the renderer builds from the same
  // layers the reel renders, so a box cannot look right here and wrong in the
  // export. Boxes are stored with the cut (overlays/effects/clean share one
  // save) and the final render reads the same record through
  // `prepare_classic_render`.

  const CLEAN_METHODS = {
    blur: { label: "Blur", note: "Smears the region. Works on any clip." },
    crop: { label: "Crop guard", note: "Keeps the frame inside the safe area." },
    fill: { label: "AI fill", note: "Repairs the region with the fill models." },
  };
  // Honest numbers, measured once on this Mac. The point is that the founder
  // chooses AI fill knowing a 30 s subtitle run is not a coffee break.
  const CLEAN_FILL_COST = {
    sttn: "About 5 s per frame on this Mac. A 4 s subtitle run takes a few minutes.",
    lama: "About 16 s per frame on this Mac. Use it for one still overlay, not a subtitle.",
  };
  const CLEAN_FILL_ENGINE_LABEL = {
    sttn: "STTN · video, best on subtitles",
    lama: "LaMa · per frame, best on still backgrounds",
  };
  const CLEAN_SCAN_METHOD = { plate: "blur", crop_guard: "crop", mask: "blur", blur: "blur" };
  const CLEAN_MIN_BOX = 0.02;
  const CLASSIC_UNDO_LIMIT = 40;

  function classicCleanLayers() {
    return state.classicText.clean;
  }

  function cleanId() {
    const taken = new Set(classicCleanLayers().map((layer) => layer.id));
    let index = 1;
    while (taken.has(`cl${String(index).padStart(2, "0")}`)) index += 1;
    return `cl${String(index).padStart(2, "0")}`;
  }

  function cleanSnapshot() {
    return JSON.stringify({
      overlays: state.classicText.overlays,
      effects: state.classicText.effects,
      clean: state.classicText.clean,
    });
  }

  function pushClassicUndo() {
    const stack = state.classicText.undo;
    const snapshot = cleanSnapshot();
    if (stack[stack.length - 1] === snapshot) return;
    stack.push(snapshot);
    if (stack.length > CLASSIC_UNDO_LIMIT) stack.shift();
    state.classicText.redo.length = 0;
    paintClassicUndo();
  }

  function restoreClassicSnapshot(snapshot) {
    if (!snapshot) return;
    let parsed = null;
    try { parsed = JSON.parse(snapshot); } catch (_) { return; }
    state.classicText.overlays = Array.isArray(parsed.overlays) ? parsed.overlays : [];
    state.classicText.effects = Array.isArray(parsed.effects) ? parsed.effects : [];
    state.classicText.clean = Array.isArray(parsed.clean) ? parsed.clean : [];
    if (!classicCleanLayers().some((layer) => layer.id === state.classicText.selection)) {
      state.classicText.selection = "";
    }
    renderClassicText();
    paintCleanStage();
    saveClassicText();
    scheduleCleanFrame();
  }

  function undoClassic() {
    const stack = state.classicText.undo;
    if (!stack.length) return;
    const snapshot = stack.pop();
    state.classicText.redo.push(cleanSnapshot());
    restoreClassicSnapshot(snapshot);
    paintClassicUndo();
  }

  function redoClassic() {
    const stack = state.classicText.redo;
    if (!stack.length) return;
    const snapshot = stack.pop();
    state.classicText.undo.push(cleanSnapshot());
    restoreClassicSnapshot(snapshot);
    paintClassicUndo();
  }

  function paintClassicUndo() {
    if (dom.cleanUndo) dom.cleanUndo.disabled = !state.classicText.undo.length;
    if (dom.cleanRedo) dom.cleanRedo.disabled = !state.classicText.redo.length;
  }

  function cleanMethodKey(layer) {
    const method = String(layer && layer.method || "").toLowerCase();
    return CLEAN_METHODS[method] ? method : "blur";
  }

  function cleanMethodLabel(layer) {
    return CLEAN_METHODS[cleanMethodKey(layer)].label;
  }

  function cleanPayloadLayers() {
    return classicCleanLayers().map((layer) => ({
      id: layer.id,
      method: cleanMethodKey(layer),
      box: { x: layer.box.x, y: layer.box.y, w: layer.box.w, h: layer.box.h },
      ranges: (layer.ranges || []).map((item) => ({
        start: Number(item.start) || 0,
        end: Number(item.end) || 0,
      })),
      label: layer.label || "",
      kind: layer.kind || layer.tracklet_kind || "manual",
      tracklet_id: layer.tracklet_id || undefined,
      tracklet_kind: layer.tracklet_kind || undefined,
      color: layer.color || undefined,
      opacity: layer.opacity,
      radius: layer.radius,
      hidden: Boolean(layer.hidden),
      source: layer.source || "manual",
      ...(cleanMethodKey(layer) === "fill" ? { engine: layer.engine || "lama" } : {}),
      ...(layer.mask ? { mask: layer.mask } : {}),
      ...(layer.text_key ? { text_key: layer.text_key } : {}),
    }));
  }

  function cleanCutTotal() {
    return Math.max(0, Number(state.plan?.total) || 0);
  }

  function currentCleanTime() {
    return clamp(Number(state.classicText.t) || 0, 0, Math.max(0.01, cleanCutTotal()));
  }

  function cleanBoxAt(box, start, end) {
    const ranges = Array.isArray(box.ranges) ? box.ranges : [];
    if (!ranges.length) return true;
    return ranges.some((item) => start < Number(item.end) && end > Number(item.start));
  }

  function cleanVisibleAt(layer, t) {
    if (!cleanBoxAt(layer, t, t + 1 / 30)) return false;
    return true;
  }

  async function loadFillStatus(force = false) {
    if (state.fill && !force) return state.fill;
    try {
      state.fill = await api("/api/classic/fill");
    } catch (_) {
      state.fill = { available: false, missing: [], files: [], note: "AI fill status is unavailable." };
    }
    renderCleanFill();
    return state.fill;
  }

  function renderCleanFill() {
    if (!dom.cleanFill) return;
    const fill = state.fill;
    if (!fill) {
      dom.cleanFill.hidden = true;
      return;
    }
    dom.cleanFill.hidden = false;
    const engines = fill.engines || {};
    const rows = Object.keys(CLEAN_FILL_ENGINE_LABEL).map((key) => {
      const engine = engines[key] || {};
      const ready = Boolean(engine.ready);
      return `
        <li class="clean-engine-row${ready ? " is-ready" : ""}">
          <span class="clean-file-name">${esc(CLEAN_FILL_ENGINE_LABEL[key])}</span>
          <span class="clean-file-state">${ready ? "ready" : "missing"}</span>
          <span class="clean-file-meta">${esc(ready ? CLEAN_FILL_COST[key] : (engine.reason || "Not installed."))}</span>
        </li>`;
    }).join("");
    if (!fill.available) {
      dom.cleanFill.innerHTML = `
        <div class="clean-fill-locked">
          <span class="clean-fill-lock" aria-hidden="true">🔒</span>
          <div>
            <p class="clean-fill-title">AI fill is not ready on this Mac</p>
            <p class="hint">${esc(fill.note)}</p>
            <ul class="clean-file-list">${rows}</ul>
            <p class="hint">Blur and Crop guard work on this cut now.</p>
          </div>
        </div>`;
      return;
    }
    const hasFill = classicCleanLayers().some((layer) => cleanMethodKey(layer) === "fill");
    const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
    const fillLayer = selected && cleanMethodKey(selected) === "fill" ? selected : null;
    const previewEngine = fillLayer?.engine || fill.default || "lama";
    const previewReady = Boolean(engines[previewEngine]?.ready);
    const previewHint = previewReady
      ? (hasFill
        ? `Compare the frame before and after with ${String(previewEngine).toUpperCase()}. The render uses the same engine.`
        : "Draw a box, choose AI fill, then compare one frame here.")
      : (engines[previewEngine]?.reason || "That engine is not ready on this Mac.");
    const preview = state.classicText.fillPreview;
    const side = state.classicText.previewSide === "before" ? "before" : "after";
    const result = preview
      ? `<div class="clean-fill-compare is-${side}">
           <figure class="is-before"><img src="${esc(preview.before)}" alt="The frame before the fill"><figcaption>Before</figcaption></figure>
           <figure class="is-after"><img src="${esc(preview.after)}" alt="The same frame after the fill"><figcaption>After</figcaption></figure>
         </div>
         <p class="hint">Preview uses ${esc(String(preview.method || preview.render_method || "lama").toUpperCase())}. The render uses the same engine; model memory is released after this frame.</p>`
      : "";
    dom.cleanFill.innerHTML = `
      <div class="clean-fill-ready">
        <span class="clean-fill-dot" aria-hidden="true"></span>
        <div>
          <p class="clean-fill-title">AI fill is ready</p>
          <ul class="clean-file-list">${rows}</ul>
          <p class="hint">${esc(previewHint)}</p>
        </div>
        <button id="clean-fill-preview" class="ghost small" type="button"${previewReady && hasFill ? "" : " disabled"}${previewReady ? "" : ` title="${esc(previewHint)}"`}>Preview one frame</button>
      </div>
      ${result}`;
  }

  async function previewFill() {
    if (!state.job) return;
    const bodies = () => ({
      clips: classicPlanClips(),
      clean: cleanPayloadLayers(),
      overlays: state.classicText.overlays.map((layer) => ({ ...layer })),
      effects: state.classicText.effects.map((effect) => ({
        id: effect.id, kind: effect.kind,
        start: Number(effect.start) || 0, end: Number(effect.end) || 0,
      })),
      t: round2(currentCleanTime()),
      aspect: state.aspect,
    });
    const button = dom.cleanFill?.querySelector("#clean-fill-preview");
    if (button) {
      button.disabled = true;
      button.textContent = "Filling one frame…";
    }
    setCleanStatus("Filling one frame with LaMa. The first one loads the model, so it takes a moment.");
    try {
      const payload = await api(`/api/classic/jobs/${state.job.id}/fill/preview`, {
        method: "POST",
        body: JSON.stringify(bodies()),
      });
      state.classicText.fillPreview = payload;
      setCleanStatus(payload.render_method && payload.render_method !== "lama"
        ? `One frame filled with LaMa at ${Number(payload.time).toFixed(2)}s. The render uses ${String(payload.render_method).toUpperCase()}.`
        : `One frame filled at ${Number(payload.time).toFixed(2)}s.`);
    } catch (error) {
      setCleanStatus(fillPreviewError(error));
    } finally {
      if (button && button.isConnected) {
        button.disabled = false;
        button.textContent = "Preview one frame";
      }
      renderCleanFill();
    }
  }

  function fillPreviewError(error) {
    const message = String(error && error.message || "The preview failed.");
    if (/fill_running/i.test(message) || /already running/i.test(message)) {
      return "A fill is already running. Wait for the render, or cancel it, then preview.";
    }
    if (/No AI fill box/i.test(message)) {
      return "No AI fill box is active at this second. Move the playhead inside its range.";
    }
    return message;
  }

  function setCleanStatus(message) {
    if (dom.cleanStatus) dom.cleanStatus.textContent = message || "";
  }

  function cleanSourceTimeAt(t) {
    const clips = state.plan?.clips || [];
    let cursor = 0;
    for (const clip of clips) {
      const span = Math.max(0, Number(clip.end) - Number(clip.start));
      if (t <= cursor + span + 1e-6) {
        return Number(clip.start) + Math.max(0, Math.min(span, t - cursor));
      }
      cursor += span;
    }
    return Number(clips[clips.length - 1]?.end) || 0;
  }

  function updateCleanPreviewMeta() {
    const t = currentCleanTime();
    if (dom.cleanPreviewTime) dom.cleanPreviewTime.textContent = `Source ${fmtTime(cleanSourceTimeAt(t), 2)}`;
    if (dom.cleanPreviewMoment) dom.cleanPreviewMoment.textContent = cleanClipTitle(t) || cleanClipLabel(t) || "No moment";
    const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
    const fillLayer = selected && cleanMethodKey(selected) === "fill"
      ? selected
      : classicCleanLayers().find((layer) => cleanMethodKey(layer) === "fill");
    const engine = fillLayer?.engine || state.fill?.default || "lama";
    if (dom.cleanPreviewEngine) {
      dom.cleanPreviewEngine.textContent = fillLayer
        ? `Engine ${String(engine).toUpperCase()}`
        : "Clean preview";
    }
    if (dom.cleanPreviewEta) {
      if (!fillLayer) {
        dom.cleanPreviewEta.textContent = "No fill yet";
      } else {
        const ranges = fillLayer.ranges || [];
        const seconds = ranges.reduce((total, item) => (
          total + Math.max(0, Number(item.end) - Number(item.start))
        ), 0) || cleanCutTotal();
        const perFrame = engine === "lama" ? 16 : 5;
        const estimate = Math.round(seconds * 30 * perFrame);
        dom.cleanPreviewEta.textContent = `Est. ${estimate < 60 ? `${estimate}s` : `${Math.ceil(estimate / 60)} min`}`;
      }
    }
  }

  // The stage frame is the real render minus the fill, which happens in the
  // render. Say that, or an AI fill box looks like a box that does nothing.
  function setCleanFillNote(count) {
    if (!dom.cleanFillNote) return;
    dom.cleanFillNote.hidden = !count;
    dom.cleanFillNote.textContent = count
      ? "The preview shows the box only. The filled picture appears in the render."
      : "";
  }

  // ------------------------------------------------------------ the frame

  function cleanFrameBody() {
    // Clean's preview is pixels only: no captions, text overlays, effects or
    // graphics. The render still applies those after the clean stage.
    return {
      clips: classicPlanClips(),
      clean: cleanPayloadLayers(),
      overlays: [],
      effects: [],
      t: round2(currentCleanTime()),
      aspect: classicTextSupported() ? state.aspect : "9:16",
      quality: "draft",
    };
  }

  function cleanFrameKey(body) {
    return JSON.stringify(body);
  }

  // Short by design: the bar has one row, and the frame already shows the
  // picture the line would describe.
  function cleanClipLabel(t) {
    const clips = state.plan?.clips || [];
    let cursor = 0;
    for (const clip of clips) {
      const span = Math.max(0, Number(clip.end) - Number(clip.start));
      if (t < cursor + span + 1e-6) {
        const number = clips.findIndex((item) => item === clip) + 1;
        return `clip ${number}/${clips.length} · ${clip.role || "beat"}`;
      }
      cursor += span;
    }
    return clips.length ? `clip ${clips.length}/${clips.length}` : "";
  }

  function cleanClipTitle(t) {
    const clips = state.plan?.clips || [];
    let cursor = 0;
    for (const clip of clips) {
      const span = Math.max(0, Number(clip.end) - Number(clip.start));
      if (t < cursor + span + 1e-6) {
        const scene = sceneById(clip.scene);
        return scene ? clipText(sceneLine(scene), 90) : "";
      }
      cursor += span;
    }
    return "";
  }

  // The preview pane is the real constraint: a 9:16 frame has to fit inside it,
  // not inside the window, or its own corner handles sit below the fold.
  function sizeCleanCanvas() {
    const stage = dom.cleanStage;
    if (!stage || stage.hidden) return;
    const pane = stage.closest(".editor-pane");
    const height = pane && pane.clientHeight
      ? pane.clientHeight
      : window.innerHeight;
    // The toolbar, the scrub row and the stage gaps take the rest.
    const bar = stage.querySelector(".clean-stage-bar");
    const foot = stage.querySelector(".clean-stage-foot");
    const chrome = (bar?.offsetHeight || 0) + (foot?.offsetHeight || 0) + 20;
    const room = Math.max(190, Math.round(height - chrome));
    stage.style.setProperty("--clean-frame-h", `${room}px`);
  }

  function paintCleanStage() {
    const stage = dom.cleanStage;
    if (!stage) return;
    const supported = classicTextSupported();
    stage.hidden = !state.job || !state.plan;
    if (!stage.hidden) {
      sizeCleanCanvas();
      const canvas = dom.cleanCanvas;
      const aspect = supported ? state.aspect : "9:16";
      canvas.dataset.aspect = aspect;
      canvas.classList.toggle("is-unsupported", !supported);
      const total = Math.max(0.1, cleanCutTotal());
      if (dom.cleanScrub) {
        dom.cleanScrub.max = total.toFixed(2);
        dom.cleanScrub.value = String(Math.min(total, currentCleanTime()));
      }
      if (dom.cleanStageTime) dom.cleanStageTime.textContent = `${currentCleanTime().toFixed(1)}s`;
      if (dom.cleanScrubReadout) dom.cleanScrubReadout.textContent = `${currentCleanTime().toFixed(1)} / ${total.toFixed(1)}s`;
      if (dom.cleanStageClip) {
        dom.cleanStageClip.textContent = cleanClipLabel(currentCleanTime());
        dom.cleanStageClip.title = cleanClipTitle(currentCleanTime());
      }
      if (dom.cleanDraw) {
        dom.cleanDraw.classList.toggle("active", state.classicText.drawMode);
        dom.cleanDraw.setAttribute("aria-pressed", state.classicText.drawMode ? "true" : "false");
      }
      dom.cleanCanvas.classList.toggle("is-drawing", state.classicText.drawMode);
    }
    paintCleanBoxes();
    paintCleanPanel();
    paintClassicUndo();
  }

  // ------------------------------------------------- boxes: source ↔ frame
  //
  // The server renders the cropped output frame, and `compose_render` reads
  // boxes as fractions of the *source* frame (it applies them before the
  // crop). Every stored box is source space; the canvas converts on the way in
  // and out, using the crop the frame route returns with each picture.

  const CLEAN_FULL_CROP = { x: 0, y: 0, w: 1, h: 1 };

  function cleanSegmentAt(t) {
    const clips = state.plan?.clips || [];
    let cursor = 0;
    for (let index = 0; index < clips.length; index += 1) {
      const span = Math.max(0, Number(clips[index].end) - Number(clips[index].start));
      if (t < cursor + span + 1e-6) return index;
      cursor += span;
    }
    return Math.max(0, clips.length - 1);
  }

  function cleanCropAt(t) {
    const crops = state.classicText.crops || {};
    const index = cleanSegmentAt(t);
    const own = crops[index];
    if (own) return own;
    const known = Object.keys(crops).length
      ? crops[Object.keys(crops)[Object.keys(crops).length - 1]]
      : null;
    return known || CLEAN_FULL_CROP;
  }

  function cleanClipWindowAt(t) {
    const clips = state.plan?.clips || [];
    const index = cleanSegmentAt(t);
    let cursor = 0;
    for (let position = 0; position < clips.length; position += 1) {
      const span = Math.max(0, Number(clips[position].end) - Number(clips[position].start));
      if (position === index) return { start: round2(cursor), end: round2(cursor + span) };
      cursor += span;
    }
    return null;
  }

  function cleanFrameBox(box, crop) {
    const area = crop || CLEAN_FULL_CROP;
    const x = clamp((Number(box.x) - area.x) / Math.max(1e-6, area.w), 0, 1);
    const y = clamp((Number(box.y) - area.y) / Math.max(1e-6, area.h), 0, 1);
    const w = clamp(Number(box.w) / Math.max(1e-6, area.w), 0, 1 - x);
    const h = clamp(Number(box.h) / Math.max(1e-6, area.h), 0, 1 - y);
    return { x, y, w, h };
  }

  function cleanSourceBox(box, crop) {
    const area = crop || CLEAN_FULL_CROP;
    const minX = CLEAN_MIN_BOX * area.w;
    const minY = CLEAN_MIN_BOX * area.h;
    const x = clamp(area.x + clamp(Number(box.x) || 0, 0, 1) * area.w, 0, 1 - minX);
    const y = clamp(area.y + clamp(Number(box.y) || 0, 0, 1) * area.h, 0, 1 - minY);
    return {
      x,
      y,
      w: clamp((Number(box.w) || minX) * area.w, minX, 1 - x),
      h: clamp((Number(box.h) || minY) * area.h, minY, 1 - y),
    };
  }

  function cleanSourcePoint(point, crop) {
    const area = crop || CLEAN_FULL_CROP;
    return {
      x: clamp(area.x + clamp(Number(point.x) || 0, 0, 1) * area.w, 0, 1),
      y: clamp(area.y + clamp(Number(point.y) || 0, 0, 1) * area.h, 0, 1),
    };
  }

  function cleanBoxOnFrame(box, crop) {
    const area = crop || CLEAN_FULL_CROP;
    const left = Math.max(Number(box.x) || 0, area.x);
    const top = Math.max(Number(box.y) || 0, area.y);
    const right = Math.min((Number(box.x) || 0) + (Number(box.w) || 0), area.x + area.w);
    const bottom = Math.min((Number(box.y) || 0) + (Number(box.h) || 0), area.y + area.h);
    return right - left > 1e-4 && bottom - top > 1e-4;
  }

  function paintCleanBoxes() {
    const overlay = dom.cleanOverlay;
    if (!overlay) return;
    const t = currentCleanTime();
    const crop = cleanCropAt(t);
    const layers = classicCleanLayers();
    overlay.innerHTML = layers.map((layer) => {
      const active = cleanVisibleAt(layer, t);
      const selected = layer.id === state.classicText.selection;
      const hidden = Boolean(layer.hidden) || !active;
      const method = cleanMethodKey(layer);
      const box = cleanFrameBox(layer.box, crop);
      const offFrame = !cleanBoxOnFrame(layer.box, crop);
      const src = [layer.box.x, layer.box.y, layer.box.w, layer.box.h]
        .map((value) => Number(value).toFixed(4)).join(",");
      return `
        <div class="clean-box${selected ? " is-selected" : ""}${hidden ? " is-off" : ""}"
             data-clean-id="${esc(layer.id)}"
             data-method="${esc(method)}"
             data-src-box="${esc(src)}"
             data-src-ranges="${esc(JSON.stringify(layer.ranges || []))}"
             style="left:${(box.x * 100).toFixed(2)}%;top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;height:${(box.h * 100).toFixed(2)}%"
             role="button" tabindex="0"
             aria-label="${esc(cleanMethodLabel(layer))} box ${esc(layer.label || layer.id)}">
          <span class="clean-box-tag">${esc(cleanMethodLabel(layer))}${layer.hidden ? " · off" : ""}${active ? "" : " · not here"}${offFrame ? " · off frame" : ""}</span>
          <span class="clean-handle" data-clean-handle="nw"></span>
          <span class="clean-handle" data-clean-handle="ne"></span>
          <span class="clean-handle" data-clean-handle="sw"></span>
          <span class="clean-handle" data-clean-handle="se"></span>
        </div>`;
    }).join("");
    const focus = state.classicText.focusBox;
    if (focus) {
      const crop = cleanCropAt(t);
      const box = cleanFrameBox(focus, crop);
      overlay.insertAdjacentHTML("beforeend", `<div class="clean-focus-box" style="left:${(box.x * 100).toFixed(2)}%;top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;height:${(box.h * 100).toFixed(2)}%" aria-hidden="true"></div>`);
    }
    if (dom.cleanFrameState) {
      const frame = state.classicText.frame;
      let message = "";
      if (state.classicText.drawMode) message = "Drag on the frame to draw a box.";
      else if (frame.busy) message = "Rendering this frame…";
      else if (frame.error) message = cleanShortError(frame.error);
      dom.cleanFrameState.textContent = message;
      dom.cleanFrameState.title = frame.error || "";
      dom.cleanFrameState.hidden = !message;
    }
    if (dom.cleanFrame) dom.cleanFrame.hidden = !state.classicText.frame.url;
    updateCleanPreviewMeta();
  }

  async function refreshCleanFrame(force = false) {
    if (!state.job || !state.plan) return;
    const clips = state.plan.clips || [];
    if (!clips.length) return;
    const body = cleanFrameBody();
    const key = cleanFrameKey(body);
    if (!force && key === state.classicText.frame.key && state.classicText.frame.url) return;
    const seq = ++state.classicText.frame.seq;
    state.classicText.frame.busy = true;
    if (state.classicText.frame.controller) {
      try { state.classicText.frame.controller.abort(); } catch (_) { /* ignore */ }
    }
    const controller = new AbortController();
    state.classicText.frame.controller = controller;
    paintCleanBoxes();
    try {
      const config = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      };
      const token = tokenValue();
      if (token) config.headers.Authorization = `Bearer ${token}`;
      const response = await fetch(`/api/classic/jobs/${encodeURIComponent(state.job.id)}/frame`, config);
      if (!response.ok) {
        let detail = `Frame answered ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload.detail || payload.message || detail;
        } catch (_) { /* ignore */ }
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      const crop = cleanCropHeader(response);
      if (crop) {
        state.classicText.crops[crop.index] = crop.box;
        paintCleanBoxes();
      }
      setCleanFillNote(Number(response.headers.get("X-VibeCut-Fill")) || 0);
      const blob = await response.blob();
      if (seq !== state.classicText.frame.seq) return;
      const url = URL.createObjectURL(blob);
      if (state.classicText.frame.url) URL.revokeObjectURL(state.classicText.frame.url);
      state.classicText.frame.url = url;
      state.classicText.frame.key = key;
      state.classicText.frame.error = "";
      if (dom.cleanFrame) dom.cleanFrame.src = url;
    } catch (error) {
      if (error && (error.name === "AbortError" || controller.signal.aborted)) return;
      if (seq !== state.classicText.frame.seq) return;
      state.classicText.frame.key = "";
      state.classicText.frame.error = `Frame failed: ${error.message}`;
    } finally {
      if (seq === state.classicText.frame.seq) {
        state.classicText.frame.busy = false;
        paintCleanBoxes();
      }
    }
  }

  // The crop belongs to the segment the server picked for this time; trusting
  // our own arithmetic here is what put boxes in the wrong place before.
  function cleanCropHeader(response) {
    const index = Number(response.headers.get("X-VibeCut-Segment"));
    const raw = response.headers.get("X-VibeCut-Crop");
    if (!Number.isFinite(index) || !raw) return null;
    const parts = String(raw).split(",").map((value) => Number(value));
    if (parts.length !== 4 || !parts.every((value) => Number.isFinite(value))) return null;
    const [x, y, w, h] = parts;
    if (w <= 0 || h <= 0) return null;
    return { index, box: { x, y, w, h } };
  }

  // An ffmpeg tail is diagnostic, not a caption: one line on the frame, the
  // whole tail in the tooltip so nothing is hidden from the founder.
  function cleanShortError(message) {
    const lines = String(message || "").split("\n").map((line) => line.trim()).filter(Boolean);
    const first = lines[0] || "The frame did not render.";
    const more = lines.length > 1 ? ` (${lines.length - 1} more lines)` : "";
    return first.length > 140 ? `${first.slice(0, 137)}…${more}` : `${first}${more}`;
  }

  function scheduleCleanFrame(force = false) {
    if (state.classicText.frameTimer) clearTimeout(state.classicText.frameTimer);
    state.classicText.frameTimer = setTimeout(() => {
      state.classicText.frameTimer = null;
      refreshCleanFrame(force);
    }, 220);
  }

  // ------------------------------------------------------------ the panel

  function cleanScanEntries() {
    const report = state.textScan && state.textScan.report;
    const entries = report && Array.isArray(report.clean_prefill) ? report.clean_prefill : [];
    return entries;
  }

  function cleanTextKey(value) {
    return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function cleanBoxesMeet(a, b) {
    if (!a || !b) return false;
    const ax = Number(a.x) || 0;
    const ay = Number(a.y) || 0;
    const aw = Number(a.w) || 0;
    const ah = Number(a.h) || 0;
    const bx = Number(b.x) || 0;
    const by = Number(b.y) || 0;
    const bw = Number(b.w) || 0;
    const bh = Number(b.h) || 0;
    const left = Math.max(ax, bx);
    const top = Math.max(ay, by);
    const right = Math.min(ax + aw, bx + bw);
    const bottom = Math.min(ay + ah, by + bh);
    if (right > left && bottom > top) {
      const overlap = (right - left) * (bottom - top);
      const area = Math.max(1e-6, Math.min(aw * ah, bw * bh));
      if (overlap / area >= 0.25) return true;
    }
    const cx = Math.abs((ax + aw / 2) - (bx + bw / 2));
    const cy = Math.abs((ay + ah / 2) - (by + bh / 2));
    return cx <= 0.045 && cy <= 0.045;
  }

  function cleanRowRanges(rows) {
    const out = [];
    for (const row of rows || []) {
      for (const range of row.ranges || []) {
        const start = Number(range.start) || 0;
        const end = Number(range.end) || 0;
        if (end > start) out.push({ start, end });
      }
    }
    out.sort((a, b) => a.start - b.start);
    const merged = [];
    for (const item of out) {
      if (merged.length && item.start <= merged[merged.length - 1].end + 1e-6) {
        merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, item.end);
      } else {
        merged.push({ ...item });
      }
    }
    return merged;
  }

  // One row per distinct text. Same text in the same area merges across
  // detection frames; a different area stays a separate row. Rows are packed
  // into lanes so two rows that overlap in time never sit on top of each
  // other. Drawn boxes are rows too.
  function cleanScanRows() {
    const rows = [];
    for (const entry of cleanScanEntries()) {
      const text = String(entry.text || entry.text_key || entry.kind || "Text").trim();
      const key = cleanTextKey(entry.text_key || entry.text || text);
      const existing = rows.find((row) => row.key === key && cleanBoxesMeet(row.box, entry.box));
      if (existing) {
        existing.ranges = cleanRowRanges([
          { ranges: existing.ranges },
          { ranges: entry.ranges || [] },
        ]);
        existing.entryRows.push(entry);
        continue;
      }
      rows.push({
        key,
        text: text || "Text",
        box: entry.box,
        kind: entry.kind || "text",
        ranges: cleanRowRanges([{ ranges: entry.ranges || [] }]),
        entryRows: [entry],
        entry,
        method: state.classicText.foundMethod || "fill",
        manual: false,
      });
    }
    for (const layer of classicCleanLayers()) {
      if (layer.source !== "manual") continue;
      rows.push({
        key: `manual:${layer.id}`,
        text: layer.label || "Drawn box",
        box: layer.box,
        kind: layer.kind || "manual",
        ranges: cleanRowRanges([{ ranges: layer.ranges || [] }]),
        entryRows: [],
        entry: null,
        method: cleanMethodKey(layer),
        manual: true,
        layer_id: layer.id,
      });
    }
    rows.sort((a, b) => {
      const at = a.ranges[0]?.start ?? Number.MAX_SAFE_INTEGER;
      const bt = b.ranges[0]?.start ?? Number.MAX_SAFE_INTEGER;
      if (at !== bt) return at - bt;
      return String(a.kind).localeCompare(String(b.kind));
    });
    const lanes = [];
    for (const row of rows) {
      const start = row.ranges[0]?.start ?? Number.MAX_SAFE_INTEGER;
      const end = row.ranges[row.ranges.length - 1]?.end ?? start;
      let lane = 0;
      while (lane < lanes.length && lanes[lane] > start + 1e-6) lane += 1;
      lanes[lane] = end;
      row.lane = lane;
    }
    return rows;
  }

  function cleanRowMethod(row) {
    return CLEAN_METHODS[row.method] ? row.method : (state.classicText.foundMethod || "fill");
  }

  function cleanRowCutStart(row) {
    if (!row.ranges.length) return 0;
    const mapped = cleanCutRanges(row.ranges);
    return mapped.length ? mapped[0].start : null;
  }

  function cleanSourceScene(at) {
    const scenes = state.job?.analysis?.scenes || [];
    return scenes.find((scene) => at >= scene.start && at < scene.end) || null;
  }

  function focusCleanRow(row) {
    if (!row) return;
    const sourceStart = Number(row.ranges[0]?.start) || 0;
    const cutStart = cleanRowCutStart(row);
    if (cutStart === null) {
      setCleanStatus("Not in this cut. Add the moment to Smart Cut first.");
      return;
    }
    const scene = cleanSourceScene(sourceStart);
    if (scene) openDrawer(scene.id);
    state.classicText.t = Math.max(0, cutStart - 0.5);
    state.classicText.focusBox = row.box;
    if (row.layer_id && classicCleanLayers().some((layer) => layer.id === row.layer_id)) {
      state.classicText.selection = row.layer_id;
    }
    if (dom.cleanScrub) dom.cleanScrub.value = String(state.classicText.t);
    paintCleanStage();
    scheduleCleanFrame();
    dom.cleanStage?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setCleanStatus(scene
      ? `Moment ${scene.id + 1} · ${fmtTime(scene.start, 1)} · ${row.kind}`
      : `Source ${fmtTime(sourceStart, 1)} · ${row.kind}`);
  }

  function renderCleanFound() {
    const panel = dom.cleanFound;
    if (!panel) return;
    const rows = cleanScanRows();
    if (!rows.length) {
      panel.hidden = true;
      panel.innerHTML = "";
      return;
    }
    panel.hidden = false;
    const ticks = state.classicText.foundTicks;
    for (const index of Array.from(ticks)) {
      if (!rows[index] || rows[index].manual) ticks.delete(index);
    }
    const fill = state.fill || {};
    const methods = [["fill", "AI fill"], ["blur", "Blur"], ["crop", "Crop guard"]]
      .filter(([key]) => key !== "fill" || fill.available);
    const wanted = state.classicText.foundMethod || "fill";
    const method = methods.some(([key]) => key === wanted) ? wanted : "blur";
    const methodOptions = methods
      .map(([key, label]) => `<option value="${key}"${key === method ? " selected" : ""}>${label}</option>`)
      .join("");
    const engine = state.classicText.foundEngine || fill.default || "lama";
    const engineOptions = Object.keys(CLEAN_FILL_ENGINE_LABEL).map((key) => {
      const ready = Boolean(fill.engines?.[key]?.ready);
      return `<option value="${key}"${key === engine ? " selected" : ""}${ready ? "" : " disabled"}>${esc(CLEAN_FILL_ENGINE_LABEL[key])}</option>`;
    }).join("");
    const rowsHtml = rows.map((row, index) => {
      const cutStart = cleanRowCutStart(row);
      const outside = cutStart === null;
      const ticked = !row.manual && ticks.has(index);
      const scene = cleanSourceScene(Number(row.ranges[0]?.start) || 0);
      const thumb = scene ? thumbUrl(scene) : "";
      const time = row.ranges.length
        ? `${fmtTime(row.ranges[0].start, 1)} – ${fmtTime(row.ranges[row.ranges.length - 1].end, 1)}`
        : "whole cut";
      return `
        <div class="clean-found-row clean-lane-${Math.min(3, row.lane || 0)}${ticked ? " is-ticked" : ""}${outside ? " is-outside" : ""}" role="listitem" data-found-index="${index}">
          ${row.manual
            ? '<span class="clean-found-tick-space" aria-hidden="true"></span>'
            : `<input type="checkbox" class="clean-found-tick" data-found-tick="${index}"${ticked ? " checked" : ""} aria-label="Include ${esc(row.text)}">`}
          ${thumb ? `<span class="clean-found-thumb" style="background-image:url('${esc(thumb)}');${cleanThumbStyle(row.box)}" aria-hidden="true"></span>` : '<span class="clean-found-thumb is-empty" aria-hidden="true"></span>'}
          <div class="clean-found-copy">
            <span class="clean-found-time mono">${esc(time)}</span>
            <span class="clean-found-kind">${esc(row.kind)}</span>
            <span class="clean-found-sample">${esc(row.text)}</span>
            <span class="clean-found-method">${esc(CLEAN_METHODS[cleanRowMethod(row)].label)} · lane ${Number(row.lane) + 1}</span>
          </div>
          ${outside ? '<span class="clean-found-blocked">Not in this cut</span>' : ""}
          ${row.manual ? '<span class="clean-found-blocked is-added">drawn</span>' : ""}
        </div>`;
    }).join("");
    const tickCount = Array.from(ticks).filter((index) => rows[index] && !rows[index].manual).length;
    const readyText = fill.available
      ? `AI fill ready${fill.default ? ` · ${esc(String(fill.default).toUpperCase())} by default` : ""}`
      : "AI fill needs its model pack · Blur and Crop guard work now";
    panel.innerHTML = `
      <div class="clean-found-head">
        <span class="clean-found-title">Found text</span>
        <span class="hint">${rows.length} row${rows.length === 1 ? "" : "s"} · click a row to open its moment</span>
      </div>
      <div class="clean-found-list" role="list">${rowsHtml}</div>
      <div class="clean-found-actions">
        <button class="ghost small" type="button" data-found-all>Select all</button>
        <button class="ghost small" type="button" data-found-none${tickCount ? "" : " disabled"}>Clear</button>
        <select id="clean-found-method" class="clean-method-select" aria-label="Method for ticked text">${methodOptions}</select>
        <select id="clean-found-engine" class="clean-method-select" aria-label="AI fill engine"${method === "fill" && fill.available ? "" : " hidden"}>${engineOptions}</select>
        <button class="primary small" type="button" data-found-apply${tickCount ? "" : " disabled"}>Remove ticked (${tickCount})</button>
      </div>
      <p class="hint clean-found-note">${readyText}</p>`;
  }

  function addCleanFromScan(entry, method, engine) {
    if (!entry) return;
    const ranges = cleanCutRanges(entry.ranges);
    if ((entry.ranges || []).length && !ranges.length) {
      setCleanStatus("That text is not inside this cut, so there is nothing to clean here.");
      return;
    }
    const wanted = method || CLEAN_SCAN_METHOD[entry.action] || "blur";
    addCleanBox({
      box: entry.box,
      method: wanted,
      ...(wanted === "fill"
        ? { engine: engine || defaultFillEngine(entry.kind) }
        : {}),
      label: entry.kind || "text",
      kind: entry.kind || "manual",
      tracklet_id: entry.tracklet_id,
      tracklet_kind: entry.kind,
      text_key: entry.text_key || entry.text || "",
      ranges,
      source: "scan",
    });
  }

  function applyFoundTicks() {
    const rows = cleanScanRows();
    const ticks = Array.from(state.classicText.foundTicks)
      .filter((index) => rows[index] && !rows[index].manual)
      .sort((a, b) => a - b);
    if (!ticks.length) {
      setCleanStatus("Tick the text you want removed first.");
      return;
    }
    let method = state.classicText.foundMethod || "fill";
    if (method === "fill" && !(state.fill && state.fill.available)) method = "blur";
    const engine = state.classicText.foundEngine
      || state.fill?.default || "lama";
    if (method === "fill" && !state.fill?.engines?.[engine]?.ready) {
      setCleanStatus(state.fill?.engines?.[engine]?.reason || "That engine is not installed.");
      return;
    }
    let added = 0;
    let outside = 0;
    // One undo step for the whole tick, not one per row.
    pushClassicUndo();
    for (const index of ticks) {
      const row = rows[index];
      const entry = row.entry || {
        ...row,
        ranges: row.ranges,
        box: row.box,
        tracklet_id: row.entryRows?.[0]?.tracklet_id,
      };
      if ((entry.ranges || []).length && !cleanCutRanges(entry.ranges).length) {
        outside += 1;
        continue;
      }
      addCleanFromScan(entry, method, engine);
      added += 1;
    }
    state.classicText.foundTicks = new Set();
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
    const skipped = outside ? ` ${outside} not in this cut.` : "";
    setCleanStatus(added
      ? `Removed text from ${added} ticked spot${added === 1 ? "" : "s"} with ${CLEAN_METHODS[method].label}.${skipped}`
      : `Nothing was inside this cut.${skipped}`);
  }

  function renderCleanLayers() {
    const list = dom.cleanLayers;
    if (!list) return;
    const layers = classicCleanLayers();
    if (!layers.length) {
      list.innerHTML = "";
      return;
    }
    const row = (layer) => {
      const method = cleanMethodKey(layer);
      const selected = layer.id === state.classicText.selection;
      const out = cleanOutsideCut(layer);
      const ranges = (layer.ranges || []).length
        ? `${(layer.ranges || []).length} range${(layer.ranges || []).length === 1 ? "" : "s"}`
        : "whole cut";
      const fillReady = Boolean(state.fill && state.fill.available);
      const chips = Object.entries(CLEAN_METHODS)
        .filter(([key]) => key !== "fill" || fillReady)
        .map(([key, item]) => (
          `<button type="button" class="clean-chip${key === method ? " active" : ""}" data-clean-method="${key}" data-clean-target="${esc(layer.id)}" title="${esc(item.note)}">${item.label}</button>`
        )).join("");
      const enginePicker = method === "fill"
        ? `<select class="clean-engine" data-clean-engine="${esc(layer.id)}" aria-label="Fill engine">${
          Object.keys(CLEAN_FILL_ENGINE_LABEL).map((key) => {
            const engine = (state.fill?.engines || {})[key] || {};
            const label = CLEAN_FILL_ENGINE_LABEL[key];
            const current = (layer.engine || "sttn") === key;
            return `<option value="${key}"${current ? " selected" : ""}${engine.ready ? "" : " disabled"} title="${esc(engine.reason || label)}">${esc(label)}</option>`;
          }).join("")}</select>`
        : "";
      return `
        <div class="clean-row${selected ? " is-selected" : ""}${layer.hidden ? " is-off" : ""}" role="listitem" data-clean-row="${esc(layer.id)}">
          <button class="clean-eye" type="button" data-clean-eye="${esc(layer.id)}" aria-pressed="${layer.hidden ? "false" : "true"}" title="${layer.hidden ? "Show" : "Hide"} this box">${layer.hidden ? "◌" : "◉"}</button>
          <div class="clean-row-copy">
            <span class="clean-row-label">${esc(layer.label || layer.kind || "Box")} <span class="clean-row-src">${esc(layer.source === "scan" ? "scan" : "manual")}</span></span>
            <span class="clean-row-meta">${esc(ranges)} · ${(layer.box.w * 100).toFixed(0)}×${(layer.box.h * 100).toFixed(0)}%${out ? ` · ${esc(out)}` : ""}</span>
          </div>
          <div class="clean-row-methods" role="group" aria-label="Method">${chips}${enginePicker}</div>
          <button class="clean-row-del" type="button" data-clean-delete="${esc(layer.id)}" title="Delete box" aria-label="Delete box">✕</button>
        </div>`;
    };
    list.innerHTML = layers.map(row).join("");
  }

  function cleanOutsideCut(layer) {
    const box = layer.box;
    if (!box) return "";
    if (box.w > 0.96 && box.h > 0.96) return "covers the frame";
    if (box.x + box.w > 1.001 || box.y + box.h > 1.001) return "outside the frame";
    return "";
  }

  function paintCleanPanel() {
    const layers = classicCleanLayers();
    renderCleanLayers();
    renderCleanFound();
    renderCleanFill();
    if (dom.cleanCount) {
      dom.cleanCount.hidden = !layers.length;
      dom.cleanCount.textContent = `${layers.length} box${layers.length === 1 ? "" : "es"}`;
      dom.cleanCount.className = "text-scan-badge" + (layers.length ? " is-ready" : "");
    }
    if (dom.cleanEmpty) dom.cleanEmpty.hidden = layers.length > 0;
    paintCleanBoxes();
  }

  // ------------------------------------------------------------ box actions

  function selectClean(id) {
    state.classicText.selection = id || "";
    paintCleanStage();
  }

  function addCleanBox(options = {}) {
    if (!classicTextSupported()) {
      toast("Clean boxes render on 9:16 and 4:5 only.");
      return null;
    }
    const box = options.box || { x: 0.2, y: 0.35, w: 0.6, h: 0.2 };
    if (options.replaceId) {
      const index = classicCleanLayers().findIndex((layer) => layer.id === options.replaceId);
      if (index >= 0) {
        pushClassicUndo();
        classicCleanLayers()[index] = {
          ...classicCleanLayers()[index],
          ...options,
          id: options.replaceId,
        };
        saveClassicText();
        paintCleanStage();
        return classicCleanLayers()[index];
      }
    }
    if (classicCleanLayers().length >= 24) {
      toast("A cut supports at most 24 Clean boxes.");
      return null;
    }
    pushClassicUndo();
    const layer = {
      id: cleanId(),
      method: options.method || "blur",
      box: {
        x: clamp(Number(box.x) || 0, 0, 1),
        y: clamp(Number(box.y) || 0, 0, 1),
        w: clamp(Number(box.w) || 0.3, CLEAN_MIN_BOX, 1),
        h: clamp(Number(box.h) || 0.15, CLEAN_MIN_BOX, 1),
      },
      ranges: Array.isArray(options.ranges) ? options.ranges.map((item) => ({
        start: round2(Number(item.start) || 0),
        end: round2(Number(item.end) || 0),
      })) : [],
      label: options.label || "",
      kind: options.kind || "manual",
      tracklet_id: options.tracklet_id || "",
      tracklet_kind: options.tracklet_kind || "",
      text_key: options.text_key || "",
      mask: options.mask || null,
      source: options.source === "scan" ? "scan" : "manual",
      hidden: false,
    };
    classicCleanLayers().push(layer);
    state.classicText.selection = layer.id;
    setCleanStatus(`${CLEAN_METHODS[cleanMethodKey(layer)].label} box added. It saves with the cut.`);
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
    return layer;
  }

  function deleteCleanBox(id) {
    const before = classicCleanLayers().length;
    if (!before) return;
    pushClassicUndo();
    state.classicText.clean = classicCleanLayers().filter((layer) => layer.id !== id);
    if (state.classicText.selection === id) state.classicText.selection = "";
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  // STTN sees motion, so it is the subtitle default; LaMa is per frame and
  // only wins on a still overlay.
  function defaultFillEngine(_kind) {
    const ready = (key) => Boolean(state.fill?.engines?.[key]?.ready);
    // LaMa is the Classic default: per-frame and safe on a still overlay.
    if (ready("lama")) return "lama";
    return Object.keys(CLEAN_FILL_ENGINE_LABEL).find(ready) || "lama";
  }

  function setCleanMethod(id, method) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer || !CLEAN_METHODS[method]) return;
    if (method === "fill" && !(state.fill && state.fill.available)) {
      setCleanStatus("AI fill needs its model pack. Blur and Crop guard work now.")
      return;
    }
    pushClassicUndo();
    layer.method = method;
    if (method === "fill") {
      const engine = defaultFillEngine(layer.kind || layer.tracklet_kind);
      layer.engine = engine;
      if (!state.fill?.engines?.[engine]?.ready && state.fill?.available) {
        setCleanStatus(`AI fill is not ready on this Mac. ${state.fill?.engines?.[engine]?.reason || ""}`.trim());
        return;
      }
      setCleanStatus(`AI fill with ${CLEAN_FILL_ENGINE_LABEL[engine]}. ${CLEAN_FILL_COST[engine]}`);
    } else {
      setCleanStatus(`${CLEAN_METHODS[method].note}`);
    }
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  function setCleanEngine(id, engine) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer || cleanMethodKey(layer) !== "fill") return;
    if (!CLEAN_FILL_ENGINE_LABEL[engine]) return;
    if (!state.fill?.engines?.[engine]?.ready) {
      const reason = state.fill?.engines?.[engine]?.reason || "That engine is not installed.";
      setCleanStatus(reason);
      renderCleanLayers();
      return;
    }
    pushClassicUndo();
    layer.engine = engine;
    setCleanStatus(`AI fill with ${CLEAN_FILL_ENGINE_LABEL[engine]}. ${CLEAN_FILL_COST[engine]}`);
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  function toggleCleanHidden(id) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer) return;
    pushClassicUndo();
    layer.hidden = !layer.hidden;
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  function updateCleanBox(id, patch) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer) return;
    layer.box = {
      x: clamp(Number(patch.x), 0, 1 - CLEAN_MIN_BOX),
      y: clamp(Number(patch.y), 0, 1 - CLEAN_MIN_BOX),
      w: clamp(Number(patch.w), CLEAN_MIN_BOX, 1 - clamp(Number(patch.x), 0, 1)),
      h: clamp(Number(patch.h), CLEAN_MIN_BOX, 1 - clamp(Number(patch.y), 0, 1)),
    };
    saveClassicText();
    paintCleanBoxes();
  }

  function nudgeClean(id, dx, dy) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer) return;
    updateCleanBox(id, {
      x: layer.box.x + dx,
      y: layer.box.y + dy,
      w: layer.box.w,
      h: layer.box.h,
    });
    scheduleCleanFrame();
  }

  function cleanPointToBox(point) {
    return {
      x: clamp(point.x, 0, 1),
      y: clamp(point.y, 0, 1),
    };
  }

  function cleanLocalPoint(event) {
    const canvas = dom.cleanCanvas;
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) / Math.max(1, rect.width),
      y: (event.clientY - rect.top) / Math.max(1, rect.height),
    };
  }

  function bindCleanStageDrag() {
    const canvas = dom.cleanCanvas;
    if (!canvas) return;
    let drag = null;
    const onMove = (event) => {
      if (!drag) return;
      const point = cleanLocalPoint(event);
      if (drag.kind === "draw") {
        const x = Math.min(drag.origin.x, point.x);
        const y = Math.min(drag.origin.y, point.y);
        drag.last = {
          x, y,
          w: Math.abs(point.x - drag.origin.x),
          h: Math.abs(point.y - drag.origin.y),
        };
        drag.preview.style.left = `${(drag.last.x * 100).toFixed(2)}%`;
        drag.preview.style.top = `${(drag.last.y * 100).toFixed(2)}%`;
        drag.preview.style.width = `${(drag.last.w * 100).toFixed(2)}%`;
        drag.preview.style.height = `${(drag.last.h * 100).toFixed(2)}%`;
        return;
      }
      const layer = classicCleanLayers().find((item) => item.id === drag.id);
      if (!layer) return;
      const dx = point.x - drag.origin.x;
      const dy = point.y - drag.origin.y;
      // The gesture happens in frame space; the box lives in source space.
      const startBox = cleanFrameBox(drag.startBox, drag.crop);
      if (drag.kind === "move") {
        updateCleanBox(drag.id, cleanSourceBox({
          x: clamp(startBox.x + dx, 0, 1 - startBox.w),
          y: clamp(startBox.y + dy, 0, 1 - startBox.h),
          w: startBox.w,
          h: startBox.h,
        }, drag.crop));
        return;
      }
      // resize from one corner, the opposite corner stays put
      const box = startBox;
      let x = box.x;
      let y = box.y;
      let w = box.w;
      let h = box.h;
      if (drag.corner.includes("e")) w = clamp(box.w + dx, CLEAN_MIN_BOX, 1 - box.x);
      if (drag.corner.includes("s")) h = clamp(box.h + dy, CLEAN_MIN_BOX, 1 - box.y);
      if (drag.corner.includes("w")) {
        const nextX = clamp(box.x + dx, 0, box.x + box.w - CLEAN_MIN_BOX);
        w = box.w + (box.x - nextX);
        x = nextX;
      }
      if (drag.corner.includes("n")) {
        const nextY = clamp(box.y + dy, 0, box.y + box.h - CLEAN_MIN_BOX);
        h = box.h + (box.y - nextY);
        y = nextY;
      }
      updateCleanBox(drag.id, cleanSourceBox({ x, y, w, h }, drag.crop));
    };
    const onUp = () => {
      if (!drag) return;
      canvas.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      canvas.releasePointerCapture?.(drag.pointerId);
      const finished = drag;
      drag = null;
      if (finished.kind === "draw") {
        finished.preview.remove();
        const box = finished.last;
        if (box && box.w >= CLEAN_MIN_BOX + 0.005 && box.h >= CLEAN_MIN_BOX + 0.005) {
          // A box drawn here belongs to the clip it was drawn on: without
          // ranges it would apply at the same source time in every clip, and
          // the crop of another clip can put it somewhere else entirely.
          const window = finished.window;
          addCleanBox({
            box: cleanSourceBox(box, finished.crop),
            ranges: window ? [window] : [],
            method: finished.method,
            label: "Drawn box",
          });
        } else {
          setCleanStatus("A box needs a little more room. Drag a wider area.");
        }
        return;
      }
      pushClassicUndo();
      saveClassicText();
      scheduleCleanFrame();
    };
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      if (!classicTextSupported()) {
        setCleanStatus("Clean boxes render on 9:16 and 4:5. Switch the shape first.");
        return;
      }
      const handle = event.target.closest("[data-clean-handle]");
      const boxNode = event.target.closest("[data-clean-id]");
      if (handle && boxNode) {
        const layer = classicCleanLayers().find((item) => item.id === boxNode.dataset.cleanId);
        if (!layer) return;
        event.preventDefault();
        selectClean(layer.id);
        pushClassicUndo();
        drag = {
          kind: "resize",
          corner: handle.dataset.cleanHandle,
          id: layer.id,
          origin: cleanLocalPoint(event),
          startBox: { ...layer.box },
          crop: cleanCropAt(currentCleanTime()),
          pointerId: event.pointerId,
        };
        canvas.setPointerCapture?.(event.pointerId);
        canvas.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp, { once: true });
        return;
      }
      if (boxNode) {
        const layer = classicCleanLayers().find((item) => item.id === boxNode.dataset.cleanId);
        if (!layer) return;
        event.preventDefault();
        selectClean(layer.id);
        pushClassicUndo();
        drag = {
          kind: "move",
          id: layer.id,
          origin: cleanLocalPoint(event),
          startBox: { ...layer.box },
          crop: cleanCropAt(currentCleanTime()),
          pointerId: event.pointerId,
        };
        canvas.setPointerCapture?.(event.pointerId);
        canvas.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp, { once: true });
        return;
      }
      if (state.classicText.brushMode) {
        const source = cleanSourcePoint(cleanLocalPoint(event), cleanCropAt(currentCleanTime()));
        let target = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
        if (!target) {
          target = addCleanBox({
            box: { x: Math.max(0, source.x - 0.02), y: Math.max(0, source.y - 0.02), w: 0.04, h: 0.04 },
            method: state.classicText.drawMethod || "blur",
            label: "Brush stroke",
          });
        }
        if (!target) return;
        const points = [{ x: source.x, y: source.y }];
        target.mask = { strokes: [{ r: 0.02, points }] };
        state.classicText.selection = target.id;
        state.classicText.brushMode = false;
        pushClassicUndo();
        paintCleanStage();
        const brushMove = (moveEvent) => {
          const next = cleanSourcePoint(cleanLocalPoint(moveEvent), cleanCropAt(currentCleanTime()));
          const last = points[points.length - 1];
          if (Math.hypot(next.x - last.x, next.y - last.y) < 0.004) return;
          points.push(next);
          target.mask = { strokes: [{ r: 0.02, points: [...points] }] };
          paintCleanBoxes();
        };
        const brushUp = () => {
          canvas.removeEventListener("pointermove", brushMove);
          window.removeEventListener("pointerup", brushUp);
          saveClassicText();
          scheduleCleanFrame();
          setCleanStatus("Brush mask added. AI fill keeps the box and the stroke.");
        };
        canvas.addEventListener("pointermove", brushMove);
        window.addEventListener("pointerup", brushUp, { once: true });
        event.preventDefault();
        return;
      }
      if (!state.classicText.drawMode) {
        selectClean("");
        return;
      }
      const origin = cleanLocalPoint(event);
      const preview = document.createElement("div");
      preview.className = "clean-box is-new";
      preview.style.left = `${(origin.x * 100).toFixed(2)}%`;
      preview.style.top = `${(origin.y * 100).toFixed(2)}%`;
      preview.style.width = "0%";
      preview.style.height = "0%";
      (dom.cleanOverlay || canvas).appendChild(preview);
      drag = {
        kind: "draw",
        origin,
        last: { x: origin.x, y: origin.y, w: 0, h: 0 },
        preview,
        crop: cleanCropAt(currentCleanTime()),
        window: cleanClipWindowAt(currentCleanTime()),
        method: state.classicText.drawMethod || "blur",
        pointerId: event.pointerId,
      };
      state.classicText.drawMode = false;
      paintCleanStage();
      canvas.setPointerCapture?.(event.pointerId);
      canvas.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp, { once: true });
    });
  }

  function toggleCleanDraw() {
    state.classicText.drawMode = !state.classicText.drawMode;
    setCleanStatus(state.classicText.drawMode
      ? "Drag on the frame to draw the box."
      : "");
    paintCleanStage();
  }

  function bindClean() {
    dom.cleanDraw?.addEventListener("click", toggleCleanDraw);
    dom.cleanBrush?.addEventListener("click", () => {
      state.classicText.brushMode = !state.classicText.brushMode;
      state.classicText.drawMode = false;
      if (dom.cleanBrush) dom.cleanBrush.setAttribute("aria-pressed", state.classicText.brushMode ? "true" : "false");
      setCleanStatus(state.classicText.brushMode
        ? "Drag on the frame to brush a mask. The box stays."
        : "");
      paintCleanStage();
    });
    dom.cleanUndo?.addEventListener("click", undoClassic);
    dom.cleanRedo?.addEventListener("click", redoClassic);
    dom.cleanRefresh?.addEventListener("click", () => {
      setCleanStatus("Rendering this frame again…");
      refreshCleanFrame(true);
    });
    dom.cleanScrub?.addEventListener("input", () => {
      state.classicText.t = Number(dom.cleanScrub.value) || 0;
      paintCleanStage();
      scheduleCleanFrame();
    });
    bindCleanStageDrag();
    dom.cleanLayers?.addEventListener("click", (event) => {
      const eye = event.target.closest("[data-clean-eye]");
      if (eye) {
        toggleCleanHidden(eye.dataset.cleanEye);
        return;
      }
      const del = event.target.closest("[data-clean-delete]");
      if (del) {
        deleteCleanBox(del.dataset.cleanDelete);
        return;
      }
      const chip = event.target.closest("[data-clean-method]");
      if (chip) {
        setCleanMethod(chip.dataset.cleanTarget, chip.dataset.cleanMethod);
        return;
      }
      const row = event.target.closest("[data-clean-row]");
      if (row) selectClean(row.dataset.cleanRow);
    });
    dom.cleanLayers?.addEventListener("change", (event) => {
      const picker = event.target.closest("[data-clean-engine]");
      if (picker) setCleanEngine(picker.dataset.cleanEngine, picker.value);
    });
    dom.cleanFound?.addEventListener("click", (event) => {
      if (event.target.closest("[data-found-all]")) {
        const rows = cleanScanRows();
        state.classicText.foundTicks = new Set(
          rows.map((row, index) => (row.manual || cleanRowCutStart(row) === null ? -1 : index))
            .filter((index) => index >= 0),
        );
        renderCleanFound();
        return;
      }
      if (event.target.closest("[data-found-none]")) {
        state.classicText.foundTicks = new Set();
        renderCleanFound();
        return;
      }
      if (event.target.closest("[data-found-apply]")) {
        applyFoundTicks();
        renderCleanFound();
        return;
      }
      const row = event.target.closest("[data-found-index]");
      if (row && !event.target.closest("input, select, button")) {
        focusCleanRow(cleanScanRows()[Number(row.dataset.foundIndex)]);
      }
    });
    dom.cleanFound?.addEventListener("change", (event) => {
      const tick = event.target.closest("[data-found-tick]");
      if (tick) {
        const index = Number(tick.dataset.foundTick);
        if (tick.checked) state.classicText.foundTicks.add(index);
        else state.classicText.foundTicks.delete(index);
        renderCleanFound();
        return;
      }
      if (event.target.id === "clean-found-method") {
        state.classicText.foundMethod = event.target.value;
        renderCleanFound();
        return;
      }
      if (event.target.id === "clean-found-engine") {
        state.classicText.foundEngine = event.target.value;
      }
    });
    dom.cleanFill?.addEventListener("click", (event) => {
      const button = event.target.closest("#clean-fill-preview");
      if (button) previewFill();
    });
    dom.cleanPreviewBefore?.addEventListener("click", () => {
      state.classicText.previewSide = "before";
      renderCleanFill();
    });
    dom.cleanPreviewAfter?.addEventListener("click", () => {
      state.classicText.previewSide = "after";
      renderCleanFill();
    });
    dom.cleanPreviewPlay?.addEventListener("click", () => {
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      const row = cleanScanRows().find((item) => item.layer_id === state.classicText.selection)
        || cleanScanRows().find((item) => item.method === "fill");
      if (row) focusCleanRow(row);
      else if (selected) {
        const cut = cleanCutRanges(selected.ranges);
        state.classicText.t = Math.max(0, (cut[0]?.start || 0) - 0.5);
        paintCleanStage();
        scheduleCleanFrame();
      } else {
        setCleanStatus("Select a text row or box first.");
      }
    });
    dom.cleanPreviewExclude?.addEventListener("click", () => {
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      if (!selected) {
        setCleanStatus("Select a box to exclude it.");
        return;
      }
      toggleCleanHidden(selected.id);
      setCleanStatus(selected.hidden ? "Box hidden again." : "Box excluded.");
    });
    dom.cleanPreviewAi?.addEventListener("click", () => {
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      if (selected) setCleanMethod(selected.id, "fill");
      else applyFoundTicks();
    });
    dom.cleanPreviewBlur?.addEventListener("click", () => {
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      if (selected) setCleanMethod(selected.id, "blur");
      else setCleanStatus("Select a box first.");
    });
    dom.cleanEmptyScanThis?.addEventListener("click", () => startTextScan());
    dom.cleanEmptyScanVideo?.addEventListener("click", () => startTextScan());
    dom.cleanFound?.addEventListener("dblclick", (event) => {
      const row = event.target.closest("[data-found-index]");
      if (!row) return;
      const item = cleanScanRows()[Number(row.dataset.foundIndex)];
      if (item) {
        focusCleanRow(item);
        setCleanStatus(`${item.kind} · ${item.text} · ${item.ranges.length ? `${fmtTime(item.ranges[0].start, 1)}–${fmtTime(item.ranges[item.ranges.length - 1].end, 1)}` : "whole cut"}`);
      }
    });
    paintClassicUndo();
  }

  function cleanShortcut(event) {
    const target = event.target;
    const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA"
      || target.tagName === "SELECT" || target.isContentEditable);
    // Chromium on macOS reports Shift+/ as "/", so both forms open the sheet.
    const wantsSheet = event.key === "?" || (event.key === "/" && event.shiftKey);
    if (wantsSheet && !typing) {
      event.preventDefault();
      openShortcuts();
      return true;
    }
    if (event.key === "Escape" && dom.shortcutsSheet && !dom.shortcutsSheet.hidden) {
      event.preventDefault();
      closeShortcuts();
      return true;
    }
    if (typing) return false;
    const meta = event.metaKey || event.ctrlKey;
    if (meta && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redoClassic();
      else undoClassic();
      return true;
    }
    if (!state.job || !state.plan) return false;
    if (event.key === "b" || event.key === "B") {
      event.preventDefault();
      toggleCleanDraw();
      return true;
    }
    if ((event.key === "Backspace" || event.key === "Delete") && state.classicText.selection) {
      event.preventDefault();
      deleteCleanBox(state.classicText.selection);
      return true;
    }
    if (event.key === "Escape") {
      if (state.classicText.drawMode) {
        state.classicText.drawMode = false;
        paintCleanStage();
      } else {
        selectClean("");
      }
      return true;
    }
    if (state.classicText.selection && event.key.startsWith("Arrow")) {
      const step = event.shiftKey ? 0.02 : 0.005;
      const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
      const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
      if (dx || dy) {
        event.preventDefault();
        nudgeClean(state.classicText.selection, dx, dy);
        return true;
      }
    }
    return false;
  }

  // ------------------------------------------------------------ finish mode
  //
  // C4: one fixed Finish frame. The editor panes step aside so the player and
  // Render/Download have the page; Back to edit returns to the same cut with
  // its boxes intact.

  function setFinishMode(on) {
    const enabled = Boolean(on) && Boolean(state.job) && !dom.result.hidden;
    document.body.classList.toggle("finish-frame", enabled);
    if (dom.finishCut) {
      dom.finishCut.textContent = enabled ? "Back to edit" : "Finish";
      dom.finishCut.setAttribute("aria-pressed", enabled ? "true" : "false");
    }
    if (enabled) {
      state.classicText.drawMode = false;
      paintCleanStage();
      updateRenderPanel();
    }
  }

  function toggleFinishMode() {
    const enabled = !document.body.classList.contains("finish-frame");
    if (enabled && !state.job) {
      toast("Open a cut first.");
      return;
    }
    setFinishMode(enabled);
  }

  // ------------------------------------------------------------ scan state

  function paintMomentsScan() {
    const chip = dom.momentsScan;
    if (!chip) return;
    const scan = state.textScan;
    const status = (scan && scan.status) || "idle";
    if (!state.job) {
      chip.hidden = true;
      return;
    }
    chip.hidden = false;
    const facts = textScanFacts(scan && scan.report);
    const labels = {
      idle: "Find text on screen ›",
      queued: "text scan queued",
      running: "scanning text…",
      ready: facts.confirmed ? "text scanned ✓" : "scanned · no text",
      cancelled: "text scan cancelled",
      failed: "text scan failed",
    };
    chip.textContent = labels[status] || labels.idle;
    chip.dataset.status = status;
    chip.classList.toggle("is-live", status === "queued" || status === "running");
    chip.classList.toggle("is-ready", status === "ready");
    chip.classList.toggle("is-failed", status === "failed");
  }

  function momentsScanAction() {
    if (!state.job) return;
    const status = (state.textScan && state.textScan.status) || "idle";
    if (status === "idle" || status === "cancelled" || status === "failed") {
      startTextScan();
      return;
    }
    if (dom.cleanPanel) dom.cleanPanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  // ------------------------------------------------------------ shortcut sheet

  function openShortcuts() {
    if (!dom.shortcutsSheet) return;
    dom.shortcutsSheet.hidden = false;
    dom.shortcutsClose?.focus();
  }

  function closeShortcuts() {
    if (!dom.shortcutsSheet || dom.shortcutsSheet.hidden) return;
    dom.shortcutsSheet.hidden = true;
  }

  function bindChrome() {
    dom.finishCut?.addEventListener("click", toggleFinishMode);
    dom.shortcutsOpen?.addEventListener("click", openShortcuts);
    dom.cleanHelp?.addEventListener("click", openShortcuts);
    dom.shortcutsClose?.addEventListener("click", closeShortcuts);
    dom.shortcutsSheet?.addEventListener("click", (event) => {
      if (event.target.closest("[data-shortcuts-close]")) closeShortcuts();
    });
    dom.momentsScan?.addEventListener("click", momentsScanAction);
    const pane = dom.cleanStage?.closest(".editor-pane");
    if (pane && typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(() => sizeCleanCanvas());
      observer.observe(pane);
    }
    window.addEventListener("resize", sizeCleanCanvas);
    dom.rightsOwn?.addEventListener("change", () => {
      if (dom.rightsOwn.checked) dom.rightsTick?.classList.remove("is-required");
    });
    syncRightsTick();
    paintMomentsScan();
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

  function renderRequestFor(target = state.target, quality = "final") {
    const clips = state.edited && state.plan ? planClipsForRender() : null;
    return {
      target,
      hook_scene: clips ? clips[0]?.scene ?? null : state.overrideHook,
      quality,
      aspect: state.aspect,
      captions: state.captions,
      preset: state.preset || null,
      // An explicit cut carries its own Hook > Beat > Payoff order.
      order: clips ? "source" : state.order,
      clips,
      script_id: state.scriptId || null,
      audio: currentAudioPlan(),
      edit: classicEditPayload(),
    };
  }

  function renderSignatureOf(body) {
    const trust = window.ClassicTrust;
    return trust && typeof trust.renderSignature === "function"
      ? trust.renderSignature(body)
      : JSON.stringify(body);
  }

  function renderSigKey(record) {
    const key = record?.key || record?.record_key;
    return key && state.job?.id ? `classic-render-sig:${state.job.id}:${key}` : "";
  }

  function rememberRenderSignature(record, body) {
    const key = renderSigKey(record);
    if (!key) return;
    try {
      localStorage.setItem(key, renderSignatureOf(body));
    } catch (_) { /* storage may be unavailable */ }
  }

  function updateRenderStale(record) {
    if (!dom.renderStale) return;
    let stale = false;
    let baseline = String(record?.request_sig || "");
    const key = renderSigKey(record);
    if (!baseline && record && key) {
      try { baseline = localStorage.getItem(key) || ""; } catch (_) { /* ignore */ }
    }
    if (baseline) {
      stale = baseline !== renderSignatureOf(
        renderRequestFor(record.target, record.quality || "final"),
      );
    } else if (record) {
      dom.renderStale.textContent = tr("No render baseline on this browser. Render again to confirm this cut matches.");
      dom.renderStale.hidden = false;
      return;
    }
    dom.renderStale.textContent = tr(
      window.ClassicTrust?.STALE_RENDER_TEXT
      || "Changed since this render — render again to see it.",
    );
    dom.renderStale.hidden = !stale;
  }

  // The render itself can call a paid provider (cloud voice, generated
  // music). Say so next to the Render button, not only in the cards.
  function renderCostText() {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.renderCostNote !== "function") return "";
    const mode = state.audio.mode;
    const voiceMode = ["bed", "voice", "full"].includes(mode);
    const upload = voiceMode && state.audio.source === "upload";
    const musicMode = ["music", "full"].includes(mode);
    return tr(trust.renderCostNote({
      voiceProvider: voiceMode && !upload ? voiceProviderName(state.audio.engine) : "",
      musicProvider: musicMode && musicSourceMode() === "generate"
        ? musicProviderName(state.audio.music) : "",
    }));
  }

  function withRenderNotes(text) {
    const base = String(withLayerNote(text) || "").trim();
    const cost = renderCostText();
    if (!cost) return base;
    return `${base}${/[.!?]$/.test(base) ? " " : ". "}${cost}`;
  }

  function withLayerNote(text) {
    const trust = window.ClassicTrust;
    if (!trust || typeof trust.layerRenderNote !== "function") return text;
    const hasLayers = !!(
      (state.classicText?.overlays || []).length
      || (state.classicText?.effects || []).length
    );
    const note = trust.layerRenderNote({ aspect: state.aspect, hasLayers });
    if (!note) return text;
    const base = String(text || "").trim();
    return `${base}${/[.!?]$/.test(base) ? " " : ". "}${note}`;
  }

  function lastReadyRender() {
    const records = Object.values(state.job?.renders || {}).filter((record) => record
      && record.status === "ready"
      && record.target === state.target);
    records.sort((a, b) => (b.updated || 0) - (a.updated || 0));
    return records[0] || null;
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
    refreshAudioStatus();

    const revealPlayer = state.renderWasActive === true && !active;
    state.renderWasActive = !!active;

    dom.renderError.hidden = true;
    dom.resultReady.hidden = true;
    if (dom.renderStale) dom.renderStale.hidden = true;
    dom.render.title = blocked || "";
    dom.renderDraft.title = blocked || "";
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
      dom.renderNote.textContent = withRenderNotes(state.plan.note || "One render at a time.");
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
      const downloadName = `${fileStem(state.job.source.name)}-${target}s${quality === "draft" ? "-draft" : ""}.mp4`;
      dom.download.href = withToken(record.url);
      dom.download.download = downloadName;
      dom.resultReadyText.textContent = `${quality === "draft" ? "Draft" : "Final"} ${target}s reel ready · ${record.duration.toFixed(1)}s`;
      dom.resultReadyDownload.href = withToken(record.url);
      dom.resultReadyDownload.download = downloadName;
      dom.resultReady.hidden = false;
      updateRenderStale(record);
      if (revealPlayer && state.playerScrollKey !== record.key) {
        state.playerScrollKey = record.key;
        setTimeout(() => {
          dom.playerWrap.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 60);
      }
    };

    const draftNewer = draftMatches && draftRecord.status === "ready"
      && (!finalMatches || finalRecord.status !== "ready"
        || (draftRecord.updated || 0) > (finalRecord.updated || 0));
    if (draftNewer) {
      show(draftRecord, "draft");
      dom.renderNote.textContent = withRenderNotes("Draft preview · 540×960 · render final when it feels right.");
      renderButton(`Render final ${target}s`);
      return;
    }

    if (finalMatches && finalRecord.status === "ready") {
      show(finalRecord, "final");
      dom.renderNote.textContent = withRenderNotes(state.plan.note
        || `${finalRecord.clip_count} beats · ${renderAudioNote()} · no watermark`);
      renderButton(`Render ${target}s again`);
      return;
    }

    const last = lastReadyRender();
    if (last) {
      const isDraft = (last.quality || "final") === "draft";
      show(last, isDraft ? "draft" : "final");
      dom.renderNote.textContent = withRenderNotes(
        isDraft
          ? "Draft preview · 540×960 · render final when it feels right."
          : `${last.clip_count} beats · ${renderAudioNote()} · no watermark`,
      );
      renderButton(isDraft ? `Render final ${target}s` : `Render ${target}s again`);
      return;
    }

    const failed = (finalMatches && finalRecord.status === "failed" && finalRecord)
      || (draftMatches && draftRecord.status === "failed" && draftRecord);
    if (failed) {
      dom.renderError.textContent = failed.error || "Render failed.";
      dom.renderError.hidden = false;
    }

    renderButton(`Render ${target}s reel`);
    const dims = { "9:16": "1080×1920", "4:5": "1080×1350", "1:1": "1080×1080", "16:9": "1920×1080", "16:10": "1920×1200" };
    dom.renderNote.textContent = withRenderNotes(state.plan.note
      || `${state.aspect} ${dims[state.aspect] || ""} · ${renderAudioNote()}${state.captions ? " · captions" : ""} · no watermark`);
  }

  function renderAudioNote() {
    switch (state.audio.mode) {
      case "bed": return "voice-over · original audio bed";
      case "voice": return "dubbed voice";
      case "music": return "music bed";
      case "full": return "new voice + music";
      default: return "original audio";
    }
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
    const body = renderRequestFor(target, quality);
    const requestSig = renderSignatureOf(body);
    state.playerScrollKey = null;
    dom.render.disabled = true;
    dom.renderDraft.disabled = true;
    dom.renderError.hidden = true;
    try {
      const result = await api(`/api/jobs/${state.job.id}/render`, {
        method: "POST",
        body: JSON.stringify({ ...body, force, request_sig: requestSig }),
      });
      state.job.renders = state.job.renders || {};
      state.job.renders[result.render.record_key || renderKey(
        target, quality, state.aspect, state.captions,
      )] = result.render;
      rememberRenderSignature(result.render, body);
      state.cutDirty = false;
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
    state.playerScrollKey = null;
    try {
      let records = [];
      const errors = [];
      if (state.edited) {
        for (const target of [15, 30, 60]) {
          try {
            const body = renderRequestFor(target, "final");
            const requestSig = renderSignatureOf(body);
            const result = await api(`/api/jobs/${state.job.id}/render`, {
              method: "POST",
              body: JSON.stringify({ ...body, request_sig: requestSig }),
            });
            if (result.render) {
              records.push(result.render);
              rememberRenderSignature(result.render, body);
            }
          } catch (error) {
            errors.push({ target, detail: error.message });
          }
        }
      } else {
        const body = renderRequestFor(state.target, "final");
        const requestSigs = Object.fromEntries(
          [15, 30, 60].map((target) => [
            String(target),
            renderSignatureOf(renderRequestFor(target, "final")),
          ]),
        );
        const result = await api(`/api/jobs/${state.job.id}/render-all`, {
          method: "POST",
          body: JSON.stringify({
            hook_scene: body.hook_scene,
            quality: body.quality,
            aspect: body.aspect,
            captions: body.captions,
            preset: body.preset,
            order: body.order,
            clips: null,
            script_id: body.script_id,
            audio: body.audio,
            request_sigs: requestSigs,
          }),
        });
        records = result.renders || [];
        records.forEach((record) => {
          rememberRenderSignature(
            record,
            renderRequestFor(record.target, record.quality || "final"),
          );
        });
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
          // The status snapshot can land between the last progress write and
          // the ready record. Read the job once more so the player and the
          // stale marker reflect the finished render.
          try {
            const job = await api(`/api/jobs/${id}`);
            if (state.job?.id === id) {
              state.job.renders = job.renders || {};
              updateRenderPanel();
            }
          } catch (_) { /* keep the last snapshot */ }
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
      if (dom.historyLatest) dom.historyLatest.textContent = "";
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

  function historyEventLabel(entry) {
    const quality = entry.quality || entry.snapshot?.render?.quality || "";
    const target = entry.target ? `${entry.target}s` : "";
    const bits = [entry.type || "event"];
    if (entry.type === "render") {
      bits[0] = quality || "final";
      if (target) bits.push(target);
    } else if (target) {
      bits.push(target);
    }
    if (entry.status) bits.push(entry.status);
    return bits.filter(Boolean).join(" ");
  }

  function renderHistory() {
    if (!dom.historyList) return;
    const entries = state.history || [];
    dom.historyCount.textContent = entries.length
      ? `${entries.length} event${entries.length === 1 ? "" : "s"}`
      : "empty";
    if (dom.historyLatest) {
      const latest = entries[0];
      dom.historyLatest.textContent = latest
        ? `Last: ${historyEventLabel(latest)} · ${formatHistoryTime(latest.created)}`
        : "";
      dom.historyLatest.hidden = !latest;
    }
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
          <span class="history-chevron" aria-hidden="true">›</span>
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
      const artifactId = String(entry.artifact_id || render.artifact_id || "");
      // The reel_<target>.mp4 name is shared by every render of that length.
      // Prefer the immutable artifact so an old row downloads its own cut.
      const link = artifactId
        ? `<a class="ghost small" href="${esc(withToken(`/api/jobs/${state.job.id}/artifacts/${encodeURIComponent(artifactId)}/media/reel.mp4`))}" download>Download reel</a>`
        : file
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
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
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
      ? `<img src="${esc(thumbUrl(scene))}" alt="" style="object-position:${objectPosition(cropFor(scene))}">`
      : `<div class="drawer-placeholder"><span>quick scan</span><small>no still extracted yet</small></div>`;
    dom.drawerContent.innerHTML = `
      <div class="drawer-frame">
        ${frame}
      </div>
      <div class="drawer-kicker">Scene ${scene.id + 1} · ${esc(role || "outside cut")}</div>
      <h3 class="drawer-title">${esc(fmtTime(scene.start, 1))} – ${esc(fmtTime(scene.end, 1))}</h3>
      <p class="drawer-meta">${scene.dur.toFixed(2)}s · hook ${roundScoreHalfEven(scene.hook)} · interest ${roundScoreHalfEven(scene.score)}</p>
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
            ? `<button class="ghost danger" data-remove-scene="${scene.id}">Remove from Smart Cut</button>`
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
    if (state.ingestJob) {
      api(`/api/jobs/${state.ingestJob}/url/cancel`, { method: "POST" }).catch(() => {});
    }
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
    state.playerScrollKey = null;
    state.renderWasActive = null;
    state.target = 30;
    state.sort = "best";
    state.visible = 96;
    state.busy = false;
    state.urlBusy = false;
    state.urlButtonLabel = "";
    state.ingestJob = null;
    state.cancelRequested = false;
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
    resetUrlInspect();
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
    if (dom.historyLatest) dom.historyLatest.textContent = "";
    dom.ingestNote.textContent = "ffmpeg cuts first. Analysis follows.";
    if (dom.planReasoning) {
      dom.planReasoning.hidden = true;
      dom.planReasoning.open = false;
    }
    if (dom.planReasoningBody) dom.planReasoningBody.replaceChildren();
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

  async function cleanJobFiles() {
    if (!state.job) return;
    const profile = dom.cleanProfile?.value || "workfiles";
    const trust = window.ClassicTrust;
    const message = trust && typeof trust.cleanConfirmText === "function"
      ? trust.cleanConfirmText(profile)
      : "Clean this job? The source video stays.";
    const localized = window.VibeCutI18N?.tBlock ? window.VibeCutI18N.tBlock(message) : message;
    if (!window.confirm(localized)) return;
    dom.cleanJob.disabled = true;
    dom.cleanJob.textContent = "Cleaning…";
    try {
      const result = await api(`/api/jobs/${state.job.id}/clean`, {
        method: "POST",
        body: JSON.stringify({ profile }),
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

  function jobHash(id) {
    let screen = "";
    try {
      screen = new URLSearchParams(location.hash.replace(/^#/, "")).get("screen") || "";
    } catch (_) { /* ignore */ }
    return screen
      ? `#job=${encodeURIComponent(id)}&screen=${encodeURIComponent(screen)}`
      : `#job=${encodeURIComponent(id)}`;
  }

  function showView(view) {
    dom.ingest.hidden = view !== "ingest";
    dom.progress.hidden = view !== "progress";
    dom.result.hidden = view !== "result";
    // C0 frame: only the result screen is a fixed three-pane editor, so the
    // class rides with that view and nothing else. The CSS decides the width.
    document.body.classList.toggle("editor-frame", view === "result");
    if (view !== "result") setFinishMode(false);
    if (view !== "result") abortTextScan();
    window.scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- text scan
  //
  // C0 scans for text on screen through the shared Check pass rather than a
  // second Classic-only scan, so the card only reports what that pass says:
  // queued, running, ready, cancelled or failed. Nothing here claims text was
  // found unless the report confirms it.

  function textScanFacts(report) {
    const text = (report && report.text) || {};
    const tracklets = Array.isArray(report && report.tracklets) ? report.tracklets : [];
    const counted = Number(text.tracklets);
    return {
      regions: Number.isFinite(counted) ? counted : tracklets.length,
      confirmed: text.confirmed === true,
      present: text.present === true,
    };
  }

  function abortTextScan() {
    const scan = state.textScan;
    if (scan && scan.controller) {
      try { scan.controller.abort(); } catch (_) { /* ignore */ }
    }
    state.textScan = null;
  }

  function paintTextScan() {
    if (!dom.textScanStatus) return;
    const scan = state.textScan;
    const status = (scan && scan.status) || "idle";
    const report = (scan && scan.report) || null;
    const facts = textScanFacts(report);
    const active = status === "queued" || status === "running";
    const progress = Number(report && report.progress);
    const pct = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;

    dom.textScanProgress.hidden = !active;
    dom.textScanCancel.hidden = !active;
    dom.textScanStart.hidden = active;
    dom.textScanBadge.hidden = active || status === "idle";
    dom.textScanBadge.className = "text-scan-badge"
      + (status === "ready" && facts.confirmed ? " is-ready" : "")
      + (status === "failed" ? " is-failed" : "");
    if (active) {
      dom.textScanFill.style.width = `${Math.round(pct * 100)}%`;
      dom.textScanProgressText.textContent = `${Math.round(pct * 100)}%`;
    }

    if (status === "queued") {
      dom.textScanBadge.textContent = "queued";
      dom.textScanStatus.textContent = "Queued. The scan starts as soon as the Mac is free.";
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "running") {
      dom.textScanBadge.textContent = "scanning";
      dom.textScanStatus.textContent = `Scanning for text on screen… ${Math.round(pct * 100)}%`;
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "ready") {
      dom.textScanBadge.textContent = facts.confirmed ? "✓ text found" : "no text";
      dom.textScanStatus.textContent = facts.confirmed
        ? `Text on screen: ${facts.regions} ${facts.regions === 1 ? "region" : "regions"} across this cut.`
        : "Scan finished. No readable text on screen in this cut.";
      dom.textScanStart.textContent = "Scan again";
    } else if (status === "cancelled") {
      dom.textScanBadge.textContent = "cancelled";
      dom.textScanStatus.textContent = "Scan cancelled. Nothing was written for this cut.";
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "failed") {
      const reason = (report && (report.message || report.error)) || "the scan did not finish";
      dom.textScanBadge.textContent = "failed";
      dom.textScanStatus.textContent = `Scan failed: ${reason}`;
      dom.textScanStart.textContent = "Retry scan";
    } else {
      dom.textScanStatus.textContent = "Not scanned yet. Find text to look for captions, watermarks and screen UI baked into the cut.";
      dom.textScanStart.textContent = "Find text on screen";
    }
    renderCleanFound();
    paintMomentsScan();
  }

  // 202 is success to `fetch`, so Check's "still running" envelope has to be
  // read by status code instead of by whether the promise rejected.
  async function checkRequest(path, options = {}) {
    const config = { ...options };
    if (config.body && !config.headers) {
      config.headers = { "Content-Type": "application/json" };
    }
    const token = tokenValue();
    if (token) {
      config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
    }
    const response = await fetch(path, config);
    let data = null;
    try { data = await response.json(); } catch (_) { /* ignore */ }
    return { status: response.status, data };
  }

  function checkProblem(status, data) {
    const detail = (data && (data.detail || data.message)) || `Check answered ${status}`;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }

  async function readTextScan(jobId, signal) {
    const { status, data } = await checkRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/check`, { signal },
    );
    if (status === 200) return { status: "ready", report: data };
    if (status === 202) return { status: (data && data.status) || "queued", report: data };
    if (status === 404) return { status: "idle", report: null };
    throw new Error(checkProblem(status, data));
  }

  async function pollTextScan(jobId, controller) {
    let misses = 0;
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 900));
      if (controller.signal.aborted || !state.job || state.job.id !== jobId) return;
      let next;
      try {
        next = await readTextScan(jobId, controller.signal);
        misses = 0;
      } catch (error) {
        if (isAbortError(error) || controller.signal.aborted) return;
        misses += 1;
        if (misses < 3) continue;
        state.textScan = { jobId, status: "failed", controller: null, report: { message: error.message } };
        paintTextScan();
        return;
      }
      if (!state.job || state.job.id !== jobId) return;
      state.textScan = { jobId, status: next.status, report: next.report, controller };
      paintTextScan();
      if (next.status !== "queued" && next.status !== "running") return;
    }
  }

  async function refreshTextScan() {
    const jobId = state.job && state.job.id;
    if (!jobId || !dom.textScanStatus) return;
    abortTextScan();
    const controller = new AbortController();
    state.textScan = { jobId, status: "idle", report: null, controller };
    paintTextScan();
    try {
      const next = await readTextScan(jobId, controller.signal);
      if (controller.signal.aborted || !state.job || state.job.id !== jobId) return;
      state.textScan = { jobId, status: next.status, report: next.report, controller };
      paintTextScan();
      if (next.status === "queued" || next.status === "running") {
        await pollTextScan(jobId, controller);
      }
    } catch (error) {
      if (isAbortError(error) || controller.signal.aborted) return;
      if (!state.job || state.job.id !== jobId) return;
      state.textScan = { jobId, status: "failed", controller: null, report: { message: error.message } };
      paintTextScan();
    }
  }

  async function startTextScan() {
    const jobId = state.job && state.job.id;
    if (!jobId || !dom.textScanStatus) return;
    const force = Boolean(state.textScan && state.textScan.report);
    abortTextScan();
    const controller = new AbortController();
    state.textScan = { jobId, status: "queued", report: null, controller };
    paintTextScan();
    let next;
    try {
      const answer = await checkRequest(`/api/jobs/${encodeURIComponent(jobId)}/check`, {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ force, sample_text: true }),
      });
      if (answer.status === 200) {
        next = { status: "ready", report: answer.data };
      } else if (answer.status === 202) {
        next = {
          status: (answer.data && answer.data.status) || "queued",
          report: answer.data,
        };
      } else {
        if (controller.signal.aborted || !state.job || state.job.id !== jobId) return;
        state.textScan = {
          jobId, status: "failed", controller: null,
          report: {
            message: answer.status === 409
              ? "this cut is still being analysed"
              : checkProblem(answer.status, answer.data),
          },
        };
        paintTextScan();
        return;
      }
    } catch (error) {
      if (isAbortError(error) || controller.signal.aborted) return;
      if (!state.job || state.job.id !== jobId) return;
      state.textScan = { jobId, status: "failed", controller: null, report: { message: error.message } };
      paintTextScan();
      return;
    }
    if (controller.signal.aborted || !state.job || state.job.id !== jobId) return;
    state.textScan = { jobId, status: next.status, report: next.report, controller };
    paintTextScan();
    if (next.status === "queued" || next.status === "running") {
      await pollTextScan(jobId, controller);
    }
  }

  async function cancelTextScan() {
    const jobId = state.job && state.job.id;
    if (!jobId || !dom.textScanStatus) return;
    abortTextScan();
    dom.textScanCancel.hidden = true;
    dom.textScanStart.hidden = true;
    dom.textScanProgress.hidden = true;
    dom.textScanStatus.textContent = "Cancelling the scan…";
    try {
      const answer = await api(`/api/jobs/${encodeURIComponent(jobId)}/check/cancel`, { method: "POST" });
      if (!state.job || state.job.id !== jobId) return;
      // A cut that already had a report keeps it; the route says so by
      // returning the last one as ready.
      const kept = answer && answer.status === "ready";
      state.textScan = {
        jobId,
        status: kept ? "ready" : "cancelled",
        controller: null,
        report: { status: kept ? "ready" : "cancelled", message: "Cancelled", text: {} },
      };
      paintTextScan();
      if (kept) await refreshTextScan();
    } catch (error) {
      if (!state.job || state.job.id !== jobId) return;
      state.textScan = { jobId, status: "failed", controller: null, report: { message: error.message } };
      paintTextScan();
    }
  }

  function bindTextScan() {
    if (!dom.textScanStart) return;
    dom.textScanStart.addEventListener("click", () => { startTextScan(); });
    dom.textScanCancel.addEventListener("click", () => { cancelTextScan(); });
    paintTextScan();
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
    const stored = scene?.crops?.[state.aspect];
    if (stored) return stored;
    // Older analyses did not store 16:10 (or every shape). Mirror the
    // renderer's attention fallback so the preview matches the cut.
    const meta = state.meta;
    const attention = scene?.attention;
    if (attention && meta?.width && meta?.height) {
      const source = Number(meta.width) / Math.max(1, Number(meta.height));
      const target = aspectValue(state.aspect);
      if (Math.abs(source - target) <= 0.01) return { cx: 0.5, cy: 0.5 };
      const faces = (attention.face ? [attention.face] : (scene?.faces || []))
        .filter((box) => Number(box?.confidence || 0) > 0.35
          && Number(box?.w || 0) * Number(box?.h || 0) > 0.003);
      const salient = (attention.salient ? [attention.salient] : (scene?.salient || []))
        .filter((box) => Number(box?.confidence || 0) > 0.25
          && Number(box?.w || 0) * Number(box?.h || 0) > 0.006
          && !(Number(box?.w || 0) > 0.88 && Number(box?.h || 0) > 0.88));
      const area = (box) => Number(box.w || 0) * Number(box.h || 0) * Number(box.confidence || 0);
      const face = faces.sort((a, b) => area(b) - area(a))[0];
      const sal = salient.sort((a, b) => area(b) - area(a))[0];
      let cx = 0.5;
      let cy = 0.5;
      if (face) {
        cx = Number(face.x || 0) + Number(face.w || 0) / 2;
        cy = Number(face.y || 0) + Number(face.h || 0) / 2;
        if (sal) {
          cx = 0.78 * cx + 0.22 * (Number(sal.x || 0) + Number(sal.w || 0) / 2);
          cy = 0.78 * cy + 0.22 * (Number(sal.y || 0) + Number(sal.h || 0) / 2);
        }
      } else if (sal) {
        cx = Number(sal.x || 0) + Number(sal.w || 0) / 2;
        cy = Number(sal.y || 0) + Number(sal.h || 0) / 2;
      }
      if (source > target) {
        const width = target * Number(meta.height) / Math.max(1, Number(meta.width));
        cx = clamp(cx, width / 2, 1 - width / 2);
        cy = 0.5;
      } else {
        const height = (Number(meta.width) / Math.max(0.01, target)) / Math.max(1, Number(meta.height));
        cy = clamp(cy, height / 2, 1 - height / 2);
        cx = 0.5;
      }
      return { cx, cy };
    }
    if (state.aspect !== "9:16") return { cx: 0.5, cy: 0.5 };
    return scene?.crop || { cx: 0.5, cy: 0.5 };
  }

  function cropModeFor(scene) {
    const stored = scene?.crop_modes?.[state.aspect];
    if (stored) return stored;
    if (scene?.attention && state.aspect !== "9:16") return "smart";
    return scene?.crop_mode || "center";
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

  function roundScoreHalfEven(value) {
    const number = Number(value) || 0;
    const floor = Math.floor(number);
    // Python's format(score, ".0f") rounds halves to even; match it so the
    // hook-lab badge and the "Hook score" sentence never differ by one.
    if (Math.abs(number - floor - 0.5) < 1e-9) {
      return floor % 2 === 0 ? floor : floor + 1;
    }
    return Math.round(number);
  }

  function scoreItem(label, value) {
    const safe = clamp(Number(value) || 0, 0, 100);
    return `
      <div class="score-item">
        <div class="label"><span>${esc(label)}</span><b>${roundScoreHalfEven(safe)}</b></div>
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

  function tr(value) {
    return window.VibeCutI18N?.t ? window.VibeCutI18N.t(value) : value;
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

  async function bridgeRequestRaw(path, options = {}) {
    const config = { ...options };
    const token = tokenValue();
    if (token) {
      config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
    }
    const response = await fetch(path, config);
    if (!response.ok) {
      let detail = response.statusText || `Request failed (${response.status})`;
      try {
        const payload = await response.json();
        detail = payload.detail || payload.message || detail;
      } catch (_) { /* ignore */ }
      const message = typeof detail === "string"
        ? detail
        : (detail && detail.message) || `Request failed (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.detail = detail;
      error.code = detail && typeof detail === "object" ? detail.code : null;
      throw error;
    }
    return response.blob();
  }

  function bridgeApplyPlan(plan) {
    if (!state.job || !plan || !Array.isArray(plan.clips) || !plan.clips.length) {
      return false;
    }
    state.target = Number(plan.target) || state.target;
    state.plan = plan;
    state.edited = true;
    state.cutDirty = true;
    state.editMode = false;
    state.overrideHook = plan.hook_scene ?? null;
    state.scriptOverrides = {};
    state.scriptId = null;
    state.lastScript = null;
    $$("#target-tabs button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.target) === state.target);
    });
    renderHook();
    renderPlan();
    renderScenes();
    updateRenderPanel();
    return true;
  }

  const shellBridge = window.vibecutBridge || {};
  window.vibecutBridge = {
    ...shellBridge,
    request: shellBridge.request || api,
    requestRaw: shellBridge.requestRaw || bridgeRequestRaw,
    toast: shellBridge.toast || toast,
    escapeHtml: shellBridge.escapeHtml || esc,
    fmtTime: shellBridge.fmtTime || fmtTime,
    fmtDuration: shellBridge.fmtDuration || fmtDuration,
    withToken: shellBridge.withToken || withToken,
    token: shellBridge.token || tokenValue,
    getJob: shellBridge.getJob || (() => state.job),
    getPlan: shellBridge.getPlan || (() => state.plan),
    getTarget: shellBridge.getTarget || (() => state.target),
    openJob: shellBridge.openJob || openJob,
    applyPlan: shellBridge.applyPlan || bridgeApplyPlan,
  };

  function routeFromHash() {
    const match = location.hash.match(/^#job=([a-z0-9]+)/i);
    if (match) openJob(match[1]);
  }

  init();
})();
