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

  // Raw engine detail is logged once per label + message, never inside visible
  // copy and never in a tooltip.
  const diagnosticsLogged = new Set();

  // Merge identity is pure and testable without a browser. The page ships the
  // module before this script, so the rail, the overlay and the saved layers
  // all share one rule for "the same text".
  const {
    sameArea,
    foundTextKey,
    mergeRanges: mergeCleanRangeList,
    mergeFoundEntries,
    dedupeCleanLayers,
  } = window.ClassicCleanMerge;

  // Timeline identity is pure too: one bar per tight member range, with the
  // source/cut mapping left to the caller.
  const CleanTimeline = window.ClassicCleanTimeline;

  // Authored 16 px icons. One stroke weight, currentColor, no Unicode glyphs.
  const CLEAN_ICONS = {
    play: '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>',
    trash: '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="m6 7 1 14h10l1-14"/></svg>',
    eye: '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.1 12.3a1 1 0 0 1 0-.7 10.8 10.8 0 0 1 19.8 0 1 1 0 0 1 0 .7 10.8 10.8 0 0 1-19.8 0"/><circle cx="12" cy="12" r="3"/></svg>',
    "eye-off": '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.7 5.1a10.7 10.7 0 0 1 11.2 6.6 1 1 0 0 1 0 .7 10.7 10.7 0 0 1-1.4 2.5"/><path d="M14.1 14.2a3 3 0 0 1-4.2-4.2"/><path d="M17.5 17.5a10.7 10.7 0 0 1-15.4-5.2 1 1 0 0 1 0-.7 10.7 10.7 0 0 1 4.4-5.1"/><path d="m2 2 20 20"/></svg>',
    chevron: '<svg class="clean-model-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
    sliders: '<svg class="clean-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></svg>',
  };

  function cleanIcon(name) {
    return CLEAN_ICONS[name] || CLEAN_ICONS.play;
  }

  // Motion is a preference, not a decoration: any programmatic scroll must ask
  // before it animates. CSS also disables animations and transitions in the
  // reduced-motion media query; this covers the JS-only smooth scrolls.
  function reducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches === true;
    } catch (_) {
      return false;
    }
  }

  function scrollIntoViewSafe(node, options = {}) {
    if (!node || typeof node.scrollIntoView !== "function") return;
    node.scrollIntoView({
      ...options,
      behavior: reducedMotion() ? "auto" : (options.behavior || "auto"),
    });
  }

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
    setupCleanFlow: $("#setup-clean-flow"),
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
    cleanVideo: $("#clean-video"),
    sourceBack: $("#source-back"),
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
    progressDownload: $("#progress-download"),
    progressRetry: $("#progress-retry"),
    progressSource: $("#progress-source"),
    progressBack: $("#progress-back"),
    progressCancelUrl: $("#progress-cancel-url"),
    resultTitle: $("#result-title"),
    resultEyebrow: $("#result-eyebrow"),
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
    textScanStatus: $("#clean-scan-status"),
    textScanProgress: $("#clean-scan-progress"),
    textScanFill: $("#clean-scan-fill"),
    textScanProgressText: $("#clean-scan-progress-text"),
    textScanStart: $("#clean-scan-start"),
    textScanCancel: $("#clean-scan-cancel"),
    cleanStage: $("#clean-stage"),
    cleanCanvas: $("#clean-canvas"),
    cleanFrame: $("#clean-frame"),
    cleanReviewVideo: $("#clean-review-video"),
    cleanReviewBlur: $("#clean-review-blur"),
    cleanReviewCopy: $("#clean-review-copy"),
    cleanReviewNote: $("#clean-review-note"),
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
    cleanPanelCopy: $("#clean-panel-copy"),
    cleanCount: $("#clean-count"),
    cleanFound: $("#clean-found"),
    cleanLayers: $("#clean-layers"),
    cleanEmpty: $("#clean-empty"),
    cleanScan: $("#clean-scan"),
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
    cleanPreviewExpand: $("#clean-preview-expand"),
    cleanTimelinePanel: $("#clean-timeline-panel"),
    cleanTimeline: $("#clean-timeline"),
    cleanRuler: $("#clean-ruler"),
    cleanLanes: $("#clean-lanes"),
    cleanPlayhead: $("#clean-playhead"),
    cleanTimelineTotal: $("#clean-timeline-total"),
    cleanTimelineCount: $("#clean-timeline-count"),
    cleanTimelineEmpty: $("#clean-timeline-empty"),
    cleanAddRange: $("#clean-add-range"),
    cleanActionBar: $("#clean-action-bar"),
    cleanDetail: $("#clean-detail"),
    sourceCleanHead: $("#source-clean-head"),
    sourceCleanName: $("#source-clean-name"),
    sourceCleanMeta: $("#source-clean-meta"),
    sourceCleanAction: $("#source-clean-action"),
    sourceCleanSummary: $("#source-clean-summary"),
    sourceCleanProgress: $("#source-clean-progress"),
    sourceCleanProgressFill: $("#source-clean-progress-fill"),
    sourceCleanStage: $("#source-clean-stage"),
    sourceCleanButtons: $("#source-clean-buttons"),
    sourceCleanRun: $("#source-clean-run"),
    sourceCleanCancel: $("#source-clean-cancel"),
    sourceCleanResultActions: $("#source-clean-result-actions"),
    sourceCleanResult: $("#source-clean-result"),
    sourceCleanOutput: $("#source-clean-output"),
    sourceCleanDownload: $("#source-clean-download"),
    sourceCleanReel: $("#source-clean-reel"),
    sourceCleanAnalysisBack: $("#source-clean-analysis-back"),
    sourceCleanAgain: $("#source-clean-again"),
    cutCleanHead: $("#cut-clean-head"),
    cutCleanName: $("#cut-clean-name"),
    cutCleanMeta: $("#cut-clean-meta"),
    cutCleanAction: $("#cut-clean-action"),
    cutCleanSummary: $("#cut-clean-summary"),
    cutCleanPlayNote: $("#cut-clean-play-note"),
    cutCleanProgress: $("#cut-clean-progress"),
    cutCleanProgressFill: $("#cut-clean-progress-fill"),
    cutCleanStage: $("#cut-clean-stage"),
    cutCleanButtons: $("#cut-clean-buttons"),
    cutCleanRun: $("#cut-clean-run"),
    cutCleanCancel: $("#cut-clean-cancel"),
    cutCleanResultActions: $("#cut-clean-result-actions"),
    cutCleanDownload: $("#cut-clean-download"),
    cutCleanAgain: $("#cut-clean-again"),
    resultMode: $("#result-mode"),
    resultModeEdit: $("#result-mode-edit"),
    resultModeClean: $("#result-mode-clean"),
    jobMenuWrap: $("#job-menu-wrap"),
    jobMenuOpen: $("#job-menu-open"),
    jobMenu: $("#job-menu"),
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
      deletedClean: new Map(),
      durableCleanDeleted: new Map(),
      newCleanTokens: new Map(),
      seq: 0,
      rev: 0,
      saveTimer: null,
      savePromise: null,
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
      foundTicksInit: false,
      pendingTickReset: "",
      tickStoreKey: "",
      foundMethod: "fill",
      detailIdentity: "",
      // Timeline selection and scan-only range edits. A bar drag on a row
      // that is not applied yet stores an override here; applying the row
      // uses it instead of the scan range, so a repaint cannot lose it.
      selectedBar: "",
      rangeOverrides: {},
      fillPreview: null,
      // Clean opens on the first text-bearing row when it can, so a black hook
      // fade is not the only first impression. The zero note is a plain
      // explanation when there is no row to open on.
      openedAtFirstText: false,
      zeroNote: false,
      // The frame is cropped; boxes are stored in source space. The server
      // sends each segment's crop with its frame, keyed by segment position.
      crops: {},
      // Detection check: play the real video, with an outline over every found
      // row. `review.active` means the video element owns the frame; the still
      // image comes back on Before/After or a video error.
      review: {
        active: false,
        playing: false,
        key: "",
        error: "",
        raf: 0,
        boxesAt: 0,
      },
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
    cleanScope: "cut",
    // Review first is the safe default: a scan only selects rows. One click
    // keeps the old scan -> clean -> render path as an opt-in.
    cleanFlow: "review_first",
    resultMode: "edit",
    cutCleanBusy: false,
    cutCleanPhase: "",
    cutCleanNote: "",
    cutCleanCancelled: false,
    cutCleanRecordKey: "",
    editDrawMode: false,
    editFocusElement: null,
    editSettingsScroll: 0,
    sourceClean: null,
    sourceCleanTimer: null,
    sourceCleanPollToken: 0,
    sourceReelTimer: null,
    sourceReelToken: 0,
    sourceCleanBusy: false,
    sourceCleanRunCancelled: false,
    sourceCleanNeedConfirm: false,
    sourceCleanEstimate: null,
    sourceCleanNotFound: false,
    sourceCleanNote: "",
    sourceCleanAnalysisError: "",
    sourceCleanAnalysisDetail: "",
    sourceCleanPhase: "",
    sourceCleanMediaSize: 0,
    sourceCleanReelStarted: false,
    sourceAspect: null,
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
    const classicClean = settings.classic_clean || {};
    const cleanFlow = classicClean.flow === "one_click" ? "one_click" : "review_first";
    state.cleanFlow = cleanFlow;
    if (dom.setupCleanFlow) dom.setupCleanFlow.value = cleanFlow;
    syncCleanFlowButtons();
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
    if (state.job) {
      paintSourceClean();
      paintCutClean();
    }
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
          classic_clean: {
            flow: dom.setupCleanFlow?.value === "one_click" ? "one_click" : "review_first",
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

  function syncCleanFlowButtons() {
    if (!dom.setupCleanFlow) return;
    const flow = dom.setupCleanFlow.value === "one_click" ? "one_click" : "review_first";
    dom.setup?.querySelectorAll("#setup-clean-flow-control [data-clean-flow]").forEach((button) => {
      const active = button.dataset.cleanFlow === flow;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function bindSetup() {
    dom.setupOpen.addEventListener("click", openSetup);
    dom.setupClose.addEventListener("click", closeSetup);
    dom.setup.querySelectorAll("[data-setup-close]").forEach((node) => {
      node.addEventListener("click", closeSetup);
    });
    dom.setupSave.addEventListener("click", saveSetup);
    dom.setup?.querySelectorAll("#setup-clean-flow-control [data-clean-flow]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!dom.setupCleanFlow) return;
        dom.setupCleanFlow.value = button.dataset.cleanFlow === "one_click" ? "one_click" : "review_first";
        syncCleanFlowButtons();
      });
    });
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

  function uploadFile(file, options, onProgress, rights = null, mode = "reel") {
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
      form.append("mode", mode);
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
    const plainError = error ? plainJobError(error) : "";
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
          ${error ? `<span class="recent-error">${esc(plainError)}</span>` : ""}
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
    dom.cleanVideo?.addEventListener("click", startCleanVideo);
    dom.sourceBack?.addEventListener("click", resetToIngest);
    dom.sourceCleanRun?.addEventListener("click", sourceCleanPrimaryAction);
    dom.sourceCleanCancel?.addEventListener("click", cancelSourceCleanRender);
    dom.sourceCleanAgain?.addEventListener("click", cleanAgainSource);
    dom.sourceCleanReel?.addEventListener("click", makeReelFromSource);
    dom.sourceCleanAnalysisBack?.addEventListener("click", backToSourceClean);
    dom.cutCleanRun?.addEventListener("click", cutCleanPrimaryAction);
    dom.cutCleanCancel?.addEventListener("click", cancelCutClean);
    dom.cutCleanAgain?.addEventListener("click", cleanAgainCut);
    dom.resultModeEdit?.addEventListener("click", () => setResultMode("edit"));
    dom.resultModeClean?.addEventListener("click", () => setResultMode("clean"));
    dom.resultModeClean?.addEventListener("pointerdown", captureEditFocus);
    dom.resultModeClean?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") captureEditFocus();
    });
    dom.optCrop.addEventListener("change", syncOptions);
    dom.progressBack.addEventListener("click", resetToIngest);
    dom.progressSource?.addEventListener("click", () => {
      if (state.job) prepareSourceClean(state.job);
    });
    dom.progressRetry?.addEventListener("click", retryCleanAnalysis);
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
      scrollIntoViewSafe(dom.momentsSection, { behavior: "smooth", block: "start" });
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
        scrollIntoViewSafe(dom.momentsFull, { behavior: "smooth", block: "nearest" });
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
    dom.ingestNote.textContent = "Clean removes text from the whole video. Dissect cuts a reel.";
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
    const disabled = state.busy || (!state.file && !state.localPath);
    dom.analyze.disabled = disabled;
    if (dom.cleanVideo) dom.cleanVideo.disabled = disabled;
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

  async function startCleanVideo() {
    if (!state.file && !state.localPath) return;
    const options = readOptions();
    dom.ingestError.hidden = true;
    state.busy = true;
    state.ingestJob = null;
    state.cancelRequested = false;
    updateAnalyzeState();
    state.pollStart = Date.now();
    state.progressStart = Date.now();

    if (state.file) {
      showView("progress");
      setProgressFile(state.file.name);
      dom.progressTitle.textContent = "Preparing the source";
      updateUploadProgress(0, 0, state.file.size);
      try {
        const rights = await importRights();
        const result = await uploadFile(
          state.file, options, updateUploadProgress, rights, "clean",
        );
        setProgressFile(state.file.name);
        updateProgress({
          status: "reading", progress: 1, message: "Source ready. Opening Clean.",
        });
        await openJob(result.id);
      } catch (error) {
        state.busy = false;
        updateAnalyzeState();
        showView("ingest");
        showIngestError(error.message);
      }
      return;
    }

    showView("progress");
    setProgressFile(state.fileName || basename(state.localPath));
    dom.progressTitle.textContent = "Preparing the source";
    updateProgress({ status: "reading", progress: 0.2, message: "Reading the source" });
    try {
      const rights = await importRights();
      const result = await api("/api/jobs/path", {
        method: "POST",
        body: JSON.stringify({
          path: state.localPath, options, rights, mode: "clean",
        }),
      });
      await openJob(result.id);
    } catch (error) {
      state.busy = false;
      updateAnalyzeState();
      showView("ingest");
      showIngestError(error.message);
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
        if (CLEAN_TERMINAL.has(status.status)) {
          stopPoll();
          state.ingestJob = null;
          state.cancelRequested = false;
          state.busy = false;
          updateAnalyzeState();
          if (state.job?.mode === "clean") {
            state.job = { ...state.job, ...status };
            await showProgressForJob(state.job);
          } else {
            updateProgress(status);
          }
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

  const CLEAN_TERMINAL = new Set(["failed", "cancelled", "interrupted"]);

  function cleanTerminalCopy(status) {
    if (status === "cancelled") return "Analysis was cancelled.";
    if (status === "interrupted") return "Analysis was interrupted.";
    return "Analysis stopped before it could build the cut. Your clean video is still available.";
  }

  function updateProgress(status) {
    const pct = Math.max(0, Math.min(100, Math.round((status.progress || 0) * 100)));
    dom.progressBar.style.width = `${pct}%`;
    dom.progressPct.textContent = `${pct}%`;
    dom.progressMessage.textContent = status.message || "Working";
    const clean = state.job?.mode === "clean";
    const terminal = CLEAN_TERMINAL.has(status.status);
    const cleanTerminal = clean && terminal;
    const raw = String(status.error || status.message || "").trim();
    dom.progressError.hidden = !(cleanTerminal || status.status === "failed");
    if (cleanTerminal) {
      dom.progressError.textContent = tr(cleanTerminalCopy(status.status));
      dom.progressError.title = "";
      if (raw) console.warn("Classic clean analysis stopped:", raw);
    } else if (status.status === "failed") {
      if (raw) console.warn("Classic analysis failed:", raw);
      dom.progressError.textContent = `${tr("Analysis failed.")} ${tr("Retry analysis, or go back to ingest.")}`;
      dom.progressError.title = "";
    } else {
      dom.progressError.textContent = "";
      dom.progressError.title = "";
    }
    // A clean terminal job recovers from Source Clean; other jobs keep the
    // existing ingest back link for failures.
    dom.progressBack.hidden = clean ? true : !(terminal);
    if (dom.progressSource) dom.progressSource.hidden = !cleanTerminal;
    if (dom.progressRetry) {
      dom.progressRetry.hidden = !cleanTerminal;
      dom.progressRetry.disabled = false;
      dom.progressRetry.textContent = "Retry analysis";
    }
    if (dom.progressDownload) {
      if (!cleanTerminal) {
        dom.progressDownload.hidden = true;
        dom.progressDownload.removeAttribute("href");
      }
    }
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
      cancelled: "Analysis cancelled",
      interrupted: "Analysis interrupted",
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
    dom.progressError.title = "";
    dom.progressError.hidden = false;
    dom.progressBack.hidden = false;
  }

  function setProgressFile(name) {
    dom.progressFile.textContent = name || "video";
  }

  async function loadProgressCleanRecovery(job) {
    if (!state.job || state.job.id !== job.id || state.job.mode !== "clean") return;
    if (!CLEAN_TERMINAL.has(job.status)) return;
    let record = null;
    try {
      record = await api(`/api/classic/jobs/${job.id}/clean/source`);
    } catch (_) { /* the recovery buttons stay usable */ }
    if (!state.job || state.job.id !== job.id) return;
    if (dom.progressDownload) {
      if (record?.status === "ready" && record.url) {
        dom.progressDownload.hidden = false;
        dom.progressDownload.href = withToken(record.url);
        dom.progressDownload.download = `${fileStem(job.source?.name || "source")}-clean.mp4`;
      } else {
        dom.progressDownload.hidden = true;
        dom.progressDownload.removeAttribute("href");
      }
    }
  }

  async function showProgressForJob(job) {
    state.progressStart = Date.now();
    state.pollStart = Date.now();
    setProgressFile(job.source?.name || state.fileName || "video");
    showView("progress");
    updateProgress(job);
    if (job.mode === "clean" && CLEAN_TERMINAL.has(job.status)) {
      await loadProgressCleanRecovery(job);
    }
  }

  async function retryCleanAnalysis() {
    const job = state.job;
    if (!job || job.mode !== "clean" || !CLEAN_TERMINAL.has(job.status)) return;
    if (dom.progressRetry) {
      dom.progressRetry.disabled = true;
      dom.progressRetry.textContent = "Retrying…";
    }
    try {
      await api(`/api/jobs/${job.id}/analyze`, { method: "POST" });
      await openJob(job.id);
    } catch (error) {
      if (dom.progressRetry) {
        dom.progressRetry.disabled = false;
        dom.progressRetry.textContent = "Retry analysis";
      }
      dom.progressError.hidden = false;
      dom.progressError.textContent = "Analysis did not start. Try again.";
      dom.progressError.title = "";
      if (error.message) console.warn("Classic analysis did not start:", error.message);
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
    stopSourceReelPoll();
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
        stopCleanReview();
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
      if (job.status === "source_ready") {
        // Extraction-only job: open Source Clean directly. No analysis poll and
        // no prepareResult here; a source_ready job has no scenes to render.
        await prepareSourceClean(job);
        if (state.job?.id !== job.id) return;
        history.replaceState(null, "", jobHash(job.id));
        return;
      }
      if (job.status === "ready") {
        await prepareResult(job);
        if (state.job?.id !== job.id) return;
      } else if (CLEAN_TERMINAL.has(job.status)) {
        state.busy = false;
        updateAnalyzeState();
        await showProgressForJob(job);
      } else {        state.busy = true;
        updateAnalyzeState();
        await showProgressForJob(job);
        startAnalysisPoll(job.id);
      }
      history.replaceState(null, "", jobHash(job.id));
    } catch (error) {
      toast(error.message);
      resetToIngest();
    }
  }

  // ---------------------------------------------------------------- source clean

  function stopSourceCleanPoll() {
    state.sourceCleanPollToken = (state.sourceCleanPollToken || 0) + 1;
    if (state.sourceCleanTimer) {
      clearTimeout(state.sourceCleanTimer);
      state.sourceCleanTimer = null;
    }
  }

  // The Make a reel handoff polls the job while the founder stays on Source
  // Clean. Leaving that screen, opening another job or cancelling the handoff
  // stops this timer; a later tick must never navigate for them.
  function stopSourceReelPoll() {
    state.sourceReelToken = (state.sourceReelToken || 0) + 1;
    if (state.sourceReelTimer) {
      clearTimeout(state.sourceReelTimer);
      state.sourceReelTimer = null;
    }
  }

  function resetSourceCleanState() {
    stopSourceCleanPoll();
    stopSourceReelPoll();
    stopCleanReview();
    state.sourceClean = null;
    state.sourceCleanBusy = false;
    state.sourceCleanRunCancelled = false;
    state.sourceCleanNeedConfirm = false;
    state.sourceCleanEstimate = null;
    state.sourceCleanNotFound = false;
    state.sourceCleanNote = "";
    state.sourceCleanAnalysisError = "";
    state.sourceCleanAnalysisDetail = "";
    state.sourceCleanPhase = "";
    state.sourceCleanMediaSize = 0;
    state.sourceCleanReelStarted = false;
    state.sourceAspect = null;
    if (dom.cleanDetail) {
      dom.cleanDetail.hidden = true;
      dom.cleanDetail.innerHTML = "";
    }
  }

  function sourceClipForJob(job = state.job) {
    const duration = Math.max(0, Number(job?.source?.duration) || 0);
    return {
      scene: 0, start: 0, end: duration, dur: duration, role: "source",
    };
  }

  function sourcePlanForJob(job = state.job) {
    const duration = Math.max(0, Number(job?.source?.duration) || 0);
    return {
      target: Math.ceil(duration),
      total: duration,
      clips: [sourceClipForJob(job)],
      clip_count: 1,
      auto: false,
    };
  }

  function applySourceMode(on) {
    document.body.classList.toggle("source-mode", Boolean(on));
    if (dom.resultEyebrow) {
      dom.resultEyebrow.innerHTML = on ? "<span>03</span> source" : "<span>03</span> cut";
    }
    if (dom.sourceBack) dom.sourceBack.hidden = !on;
    if (dom.sourceCleanHead) dom.sourceCleanHead.hidden = !on;
    if (dom.sourceCleanAction) dom.sourceCleanAction.hidden = !on;
    if (dom.sourceCleanResult) dom.sourceCleanResult.hidden = !on;
    if (dom.resultMode) dom.resultMode.hidden = Boolean(on);
    if (dom.cutCleanHead) dom.cutCleanHead.hidden = Boolean(on) || !cutCleanActive();
    if (dom.cutCleanAction) dom.cutCleanAction.hidden = Boolean(on) || !cutCleanActive();
    if (dom.cleanPanelCopy) {
      dom.cleanPanelCopy.textContent = tr(on
        ? "Remove text from the whole video. The frame is the real render."
        : "Remove what should not be in the cut. The frame is the real render.");
    }
    if (dom.cleanFrame) dom.cleanFrame.alt = on ? "Frame of the source video" : "Frame of the cut";
    if (!on && dom.cleanDetail) {
      dom.cleanDetail.hidden = true;
      dom.cleanDetail.innerHTML = "";
    }
  }

  function cutCleanActive() {
    return state.resultMode === "clean" && state.cleanScope === "cut";
  }

  function resetCutCleanState() {
    stopCleanReview();
    state.resultMode = "edit";
    state.editDrawMode = false;
    state.editFocusElement = null;
    state.editSettingsScroll = 0;
    state.cutCleanBusy = false;
    state.cutCleanPhase = "";
    state.cutCleanNote = "";
    state.cutCleanCancelled = false;
    state.cutCleanRecordKey = "";
  }

  function editSettingsPane() {
    return dom.result ? $(".editor-pane-settings", dom.result) : null;
  }

  function captureEditFocus() {
    const active = document.activeElement;
    if (active && active !== document.body && !active.closest?.("#result-mode")) {
      state.editFocusElement = active;
    }
    const pane = editSettingsPane();
    if (pane) state.editSettingsScroll = pane.scrollTop;
  }

  function restoreEditFocus() {
    const target = state.editFocusElement;
    const pane = editSettingsPane();
    const scrollTop = state.editSettingsScroll;
    state.editFocusElement = null;
    if (target && target.isConnected && target.offsetParent !== null && !target.disabled) {
      target.focus({ preventScroll: true });
      if (pane) pane.scrollTop = scrollTop;
      return;
    }
    if (target) {
      dom.resultModeEdit?.focus({ preventScroll: true });
      if (pane) pane.scrollTop = scrollTop;
      setCleanStatus("Edit restored. The previous control is no longer available, so focus is on Edit.");
      return;
    }
    if (pane) pane.scrollTop = scrollTop;
  }

  function applyCleanMode(on) {
    const wasClean = cutCleanActive();
    const enabled = Boolean(on) && state.cleanScope === "cut" && Boolean(state.job);
    state.resultMode = enabled ? "clean" : "edit";
    document.body.classList.toggle("cut-clean-mode", enabled);
    if (dom.resultMode) dom.resultMode.hidden = state.cleanScope === "source" || !state.job;
    if (dom.resultModeEdit) {
      dom.resultModeEdit.setAttribute("aria-pressed", enabled ? "false" : "true");
      dom.resultModeEdit.classList.toggle("is-active", !enabled);
    }
    if (dom.resultModeClean) {
      dom.resultModeClean.setAttribute("aria-pressed", enabled ? "true" : "false");
      dom.resultModeClean.classList.toggle("is-active", enabled);
    }
    if (dom.cutCleanHead) dom.cutCleanHead.hidden = !enabled;
    if (dom.cutCleanAction) dom.cutCleanAction.hidden = !enabled;
    if (enabled) {
      if (!wasClean) state.editDrawMode = state.classicText.drawMode;
      state.classicText.drawMode = false;
      if (state.plan) paintCleanStage({ rows: false });
      paintCutClean();
    } else {
      if (wasClean) {
        stopCleanReview();
        state.classicText.drawMode = Boolean(state.editDrawMode);
        if (state.plan) paintCleanStage({ rows: false });
        restoreEditFocus();
      }
      setCleanFillNote(0);
    }
    updateResultModeGuard();
  }

  function cutCleanSwitchBlocked() {
    if (state.cleanScope !== "cut") return "";
    if (state.cutCleanPhase === "Finding text") {
      return "Finding text. Wait or Cancel before leaving Clean.";
    }
    if (state.cutCleanPhase === "Cleaning" || (state.cutCleanBusy && state.cutCleanPhase !== "Rendering")) {
      return "Cleaning. Wait or Cancel before leaving Clean.";
    }
    return "";
  }

  function updateResultModeGuard() {
    if (!dom.resultModeEdit) return;
    const blocked = cutCleanSwitchBlocked();
    dom.resultModeEdit.disabled = Boolean(blocked);
    dom.resultModeEdit.title = blocked || "";
    dom.resultModeClean.disabled = false;
    dom.resultModeClean.title = "";
  }

  function setResultMode(mode) {
    if (state.cleanScope !== "cut" || !state.job) return;
    const clean = mode === "clean";
    if (clean === cutCleanActive()) return;
    const blocked = !clean && cutCleanSwitchBlocked();
    if (blocked) {
      toast(blocked);
      updateResultModeGuard();
      return;
    }
    if (clean) captureEditFocus();
    applyCleanMode(clean);
    if (clean) {
      renderCutCleanHeader();
      const moved = openCleanAtFirstText();
      paintCleanStage();
      scheduleCleanFrame(moved);
    }
  }

  function sourceCleanEngineLabel(record = state.sourceClean) {
    const method = String(record?.method || "").toLowerCase();
    if (method === "blur") return "Blur";
    if (CLEAN_FILL_ENGINE_LABEL[method]) return CLEAN_FILL_ENGINE_LABEL[method];
    if (method) return method.toUpperCase();
    if (fillEngineReady()) return CLEAN_FILL_ENGINE_LABEL[fillEngineNow()];
    if (state.fill && state.fill.available === false) return "Blur · AI fill unavailable";
    return "LaMa";
  }

  function setSourceAspect(width, height) {
    const w = Number(width);
    const h = Number(height);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w < 2 || h < 2) return;
    state.sourceAspect = { width: Math.round(w), height: Math.round(h) };
    if (dom.cleanCanvas) {
      dom.cleanCanvas.style.aspectRatio = `${Math.round(w)} / ${Math.round(h)}`;
      dom.cleanCanvas.dataset.aspect = "source";
    }
    sizeCleanCanvas();
  }

  function renderSourceCleanHeader() {
    if (state.cleanScope !== "source" || !state.job) return;
    const source = state.job.source || {};
    const duration = Math.max(0, Number(source.duration) || 0);
    const fps = Math.max(0, Number(source.fps) || 0);
    if (dom.sourceCleanName) {
      dom.sourceCleanName.textContent = source.name || "Source video";
      dom.sourceCleanName.title = source.name || "";
    }
    if (dom.sourceCleanMeta) {
      const frames = Math.round(duration * fps);
      const size = `${Math.round(Number(source.width) || 0)}×${Math.round(Number(source.height) || 0)}`;
      dom.sourceCleanMeta.textContent = [
        fmtDuration(duration), size, `${frames} frames`, sourceCleanEngineLabel(),
      ].filter(Boolean).join(" · ");
    }
  }

  function sourceCleanActive(record = state.sourceClean) {
    return !!record && ["queued", "running", "cancelling"].includes(record.status);
  }

  function sourceCleanStageFor(record) {
    const message = String(record?.message || "").toLowerCase();
    if (/encoding|adding|writing|mux|finish/.test(message)) return "Encoding";
    return "Cleaning";
  }

  function formatEstimate(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "";
    if (value < 60) return `${Math.max(1, Math.round(value))}s`;
    return `${Math.max(1, Math.ceil(value / 60))} min`;
  }

  function sourceCleanFailureText(record) {
    const raw = cleanDiagnostic(
      "Classic source clean failed:",
      record?.error || record?.message || "",
    );
    return `Clean failed: ${plainCleanError(raw)}`;
  }

  function sourceLowRows(rows) {
    return rows.filter((row) => !row.manual && Number(row.confidence) < SOURCE_CONFIDENCE_MIN);
  }

  function tickedRowsFor(rows, ticks, options = {}) {
    const sourceScope = Boolean(options.source);
    const byId = new Map(rows.map((row) => [cleanRowIdentity(row), row]));
    return Array.from(ticks)
      .map((identity) => byId.get(identity))
      .filter((row) => row && !row.manual && !row.added
        && (sourceScope || cleanRowCutStart(row) !== null));
  }

  function sourceTickedCount(rows, ticks) {
    return tickedRowsFor(rows, ticks, { source: true }).length;
  }

  function sourceCleanReportReady() {
    const report = state.textScan?.report;
    return state.textScan?.status === "ready"
      && Boolean(report && report.text && report.text.confirmed === true);
  }

  function sourceReviewRows(rows) {
    return (rows || []).filter((row) => !row.manual && sourceInsideRow(row));
  }

  function paintSourceClean() {
    if (state.cleanScope !== "source") return;
    const record = state.sourceClean;
    const active = sourceCleanActive(record);
    const ready = record?.status === "ready";
    const showResult = ready || state.sourceCleanNotFound;
    const scanStatus = state.textScan?.status || "idle";
    const scanActive = scanStatus === "queued" || scanStatus === "running";
    const report = state.textScan?.report;
    const confirmed = Boolean(report && report.text && report.text.confirmed === true);
    const rows = cleanScanRows();
    const reviewFirst = state.cleanFlow !== "one_click";
    const reportReady = scanStatus === "ready" && confirmed;
    const available = sourceReviewRows(rows);
    const ticked = sourceTickedCount(rows, state.classicText.foundTicks);
    const applied = classicCleanLayers().filter((layer) => layer.source === "scan").length;
    const cleanCount = ticked || applied || available.length;
    const needsSelection = reviewFirst && reportReady && available.length > 0
      && !ticked && !applied;
    const low = sourceLowRows(rows).length;
    const engine = sourceCleanEngineLabel(record);
    const duration = Math.max(0, Number(state.job?.source?.duration) || 0);

    renderSourceCleanHeader();
    paintCleanEmptyState();
    if (dom.sourceCleanAction) dom.sourceCleanAction.hidden = false;
    if (dom.sourceCleanResult) dom.sourceCleanResult.hidden = !showResult;
    if (dom.sourceCleanResultActions) dom.sourceCleanResultActions.hidden = !showResult;
    if (dom.sourceCleanButtons) dom.sourceCleanButtons.hidden = showResult;

    let progress = 0;
    let stage = "";
    if (scanActive) {
      progress = Number(report?.progress);
      if (!Number.isFinite(progress)) progress = 0;
      stage = `Finding text · ${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    } else if (active) {
      progress = Number(record.progress);
      if (!Number.isFinite(progress)) progress = 0;
      stage = `${sourceCleanStageFor(record)} · ${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    }
    if (dom.sourceCleanProgress) dom.sourceCleanProgress.hidden = !stage;
    if (dom.sourceCleanProgressFill) {
      dom.sourceCleanProgressFill.style.width = `${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    }
    if (dom.sourceCleanStage) dom.sourceCleanStage.textContent = stage ? tr(stage) : "";

    let summary = state.sourceCleanNote;
    if (!summary) {
      if (active) summary = record.message || "Cleaning the full video.";
      else if (record?.status === "cancelled") {
        summary = "Clean cancelled. Nothing partial is kept. Retry when ready.";
      } else if (record?.status === "failed") {
        summary = sourceCleanFailureText(record);
      } else if (!showResult && available.length) {
        if (reviewFirst) {
          const count = available.length;
          const lowTail = low ? ` ${low} low-confidence.` : "";
          summary = `${count} text${count === 1 ? "" : "s"} found. Review the rows, then clean.${lowTail}`;
        } else {
          const count = cleanCount || available.length;
          const tail = low ? ` · review ${low} more` : "";
          summary = `${count} text${count === 1 ? "" : "s"} · ${engine}${tail}`;
          if (state.sourceCleanNeedConfirm) {
            const estimate = state.sourceCleanEstimate;
            if (estimate?.blur) {
              summary += " · Blur needs no fill estimate · render progress will show";
            } else if (estimate?.estimate_seconds) {
              summary += ` · ~${formatEstimate(estimate.estimate_seconds)}`;
            } else if (!estimate) {
              summary += " · estimating…";
            } else {
              summary += " · estimate unavailable";
            }
          }
        }
      } else if (!showResult && confirmed) {
        summary = reviewFirst
          ? "No baked-in text found. Nothing was rendered."
          : `Nothing is ticked yet · ${engine}`;
      }
    }
    if (dom.sourceCleanSummary) {
      dom.sourceCleanSummary.textContent = summary ? tr(summary) : "";
      dom.sourceCleanSummary.hidden = !summary;
    }

    let label = reviewFirst ? "Find text" : "Find text & clean";
    let disabled = false;
    if (active) {
      label = "Cleaning…";
      disabled = true;
    } else if (state.sourceCleanBusy) {
      label = `${state.sourceCleanPhase || "Preparing"}…`;
      disabled = true;
    } else if (record?.status === "failed" || record?.status === "cancelled") {
      if (reviewFirst && reportReady && available.length && cleanCount) {
        label = `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render`;
        disabled = needsSelection;
      } else {
        label = "Retry clean";
      }
    } else if (scanStatus === "failed") {
      label = "Retry scan";
    } else if (scanStatus === "cancelled") {
      label = "Rescan text";
    } else if (scanStatus === "ready" && !confirmed) {
      label = "Rescan text";
    } else if (state.sourceCleanNotFound) {
      label = "Scan again";
    } else if (!reviewFirst && state.sourceCleanNeedConfirm) {
      const estimate = state.sourceCleanEstimate;
      const count = cleanCount || rows.length;
      const time = estimate?.blur
        ? " · Blur"
        : (estimate?.estimate_seconds
          ? ` · ~${formatEstimate(estimate.estimate_seconds)}`
          : (estimate ? " · estimate unavailable" : " · estimating…"));
      label = `Clean ${count} text${count === 1 ? "" : "s"}${time}`;
    } else if (reviewFirst) {
      if (reportReady && available.length) {
        const count = cleanCount || available.length;
        label = `Clean ${count} text${count === 1 ? "" : "s"} & render`;
        disabled = needsSelection;
      } else if (reportReady) {
        label = "Scan again";
      }
    } else if (scanStatus === "ready" && confirmed && rows.length && !ticked) {
      label = applied
        ? `Clean ${applied} text${applied === 1 ? "" : "s"}`
        : `Review ${rows.length} text${rows.length === 1 ? "" : "s"}`;
    } else if (scanStatus === "ready" && confirmed && ticked) {
      label = `Clean ${ticked} text${ticked === 1 ? "" : "s"}`;
    }
    if (dom.sourceCleanRun) {
      dom.sourceCleanRun.textContent = tr(label);
      dom.sourceCleanRun.disabled = disabled || state.sourceCleanBusy || scanActive;
      dom.sourceCleanRun.title = needsSelection && disabled
        ? tr("Select at least one row to clean.")
        : "";
    }
    if (dom.sourceCleanCancel) {
      dom.sourceCleanCancel.hidden = !(active || scanActive);
      dom.sourceCleanCancel.disabled = record?.status === "cancelling";
    }

    if (!showResult) return;
    const note = state.sourceCleanNote ? ` ${tr(state.sourceCleanNote)}` : "";
    if (dom.sourceCleanOutput) {
      if (ready) {
        const source = state.job?.source || {};
        const size = state.sourceCleanMediaSize ? formatSize(state.sourceCleanMediaSize) : "";
        const output = [
          `${Math.round(Number(record.width) || Number(source.width) || 0)}×${Math.round(Number(record.height) || Number(source.height) || 0)}`,
          fmtDuration(Number(record.duration) || duration),
          size,
          engine,
        ].filter(Boolean).join(" · ");
        dom.sourceCleanOutput.textContent = `${output}${note}`;
      } else {
        dom.sourceCleanOutput.textContent = `${tr("No baked-in text found. Nothing was rendered.")}${note}`;
      }
    }
    if (dom.sourceCleanDownload) {
      const url = ready ? (record.url || `/api/classic/jobs/${state.job.id}/clean/source/media`) : "";
      dom.sourceCleanDownload.hidden = !ready;
      if (ready && url) {
        dom.sourceCleanDownload.href = withToken(url);
        dom.sourceCleanDownload.download = `${fileStem(state.job?.source?.name || "source")}-clean.mp4`;
      } else {
        dom.sourceCleanDownload.removeAttribute("href");
      }
    }
    if (dom.sourceCleanReel) {
      dom.sourceCleanReel.disabled = state.sourceCleanReelStarted;
      dom.sourceCleanReel.textContent = tr(
        state.sourceCleanAnalysisError
          ? "Retry analysis"
          : (state.sourceCleanReelStarted ? "Analysis started" : "Make a reel"),
      );
      dom.sourceCleanReel.title = "";
    }
    if (dom.sourceCleanAnalysisBack) {
      dom.sourceCleanAnalysisBack.hidden = !(ready && state.sourceCleanAnalysisError);
    }
    if (dom.sourceCleanAgain) dom.sourceCleanAgain.disabled = false;
  }

  function cutCleanEngineLabel() {
    if (fillEngineReady()) return CLEAN_FILL_ENGINE_LABEL[fillEngineNow()];
    if (state.fill) return "Blur · AI fill unavailable";
    return "Blur";
  }

  function renderCutCleanHeader() {
    if (state.cleanScope !== "cut" || !state.job) return;
    const total = cleanCutTotal();
    const fps = Number(state.job.source?.fps) || 0;
    const frames = fps ? Math.round(total * fps) : 0;
    const rows = cleanScanRows().length;
    if (dom.cutCleanName) dom.cutCleanName.textContent = `${state.target}s clean cut`;
    if (dom.cutCleanMeta) {
      dom.cutCleanMeta.textContent = [
        fmtDuration(total),
        rows ? `${rows} row${rows === 1 ? "" : "s"}` : (frames ? `${frames} frames` : ""),
        cutCleanEngineLabel(),
      ].filter(Boolean).join(" · ");
    }
  }

  function cutCleanRenderRecord() {
    const key = state.cutCleanRecordKey;
    const record = key ? state.job?.renders?.[key] : null;
    if (record
      && (record.target === undefined || Number(record.target) === Number(state.target))
      && (record.aspect || "9:16") === state.aspect) {
      return record;
    }
    const active = activeRender();
    if (isRenderActive(active)) return active;
    const existing = findRender("final");
    if (existing?.status === "ready") return existing;
    return null;
  }

  function ensureCutFoundTicks() {
    if (state.cleanScope !== "cut" || state.classicText.foundTicksInit) return;
    applyStoredFoundTicks(cleanScanRows(), { source: false });
  }

  function cutCleanLowRows(rows) {
    return rows.filter((row) => !row.manual && !row.added
      && cleanRowCutStart(row) !== null
      && Number(row.confidence) < SOURCE_CONFIDENCE_MIN);
  }

  function cutCleanTickedCount(rows, ticks) {
    return tickedRowsFor(rows, ticks, { source: false }).length;
  }

  // One review predicate for the label, the summary and the action. A found
  // row that is still unticked needs a human choice when it is low-confidence,
  // or when no Clean scan layer has been applied yet. A drawn box alone does
  // not count as an applied scan layer.
  function cutCleanReviewState(rows, ticks) {
    const available = rows.filter((row) => !row.manual && !row.added
      && cleanRowCutStart(row) !== null);
    const low = available.filter((row) => (
      Number(row.confidence) < SOURCE_CONFIDENCE_MIN
    )).length;
    const ticked = cutCleanTickedCount(rows, ticks);
    const applied = classicCleanLayers().filter((layer) => layer.source === "scan").length;
    return {
      available,
      low,
      ticked,
      applied,
      needsReview: available.length > 0 && ticked === 0 && applied === 0,
    };
  }

  function setCutCleanNote(message) {
    state.cutCleanNote = message || "";
    setCleanStatus(state.cutCleanNote);
  }

  function cutCleanFoundRows(rows) {
    return (rows || []).filter((row) => !row.manual);
  }

  function cutCleanReportReady() {
    const report = state.textScan?.report;
    return state.textScan?.status === "ready"
      && Boolean(report && report.text && report.text.confirmed === true);
  }

  function cutCleanEmptyConfirmed(rows) {
    return cutCleanReportReady() && cutCleanFoundRows(rows).length === 0;
  }

  function cutCleanNoInsideFound(rows) {
    const found = cutCleanFoundRows(rows);
    return cutCleanReportReady()
      && found.length > 0
      && !found.some((row) => cleanRowCutStart(row) !== null);
  }

  function paintCutClean() {
    if (!state.job || state.cleanScope !== "cut") return;
    const active = cutCleanActive();
    if (dom.cutCleanHead) dom.cutCleanHead.hidden = !active;
    if (dom.cutCleanAction) dom.cutCleanAction.hidden = !active;
    renderCutCleanHeader();

    const scan = state.textScan;
    const scanStatus = scan?.status || "idle";
    const scanActive = scanStatus === "queued" || scanStatus === "running";
    const report = scan?.report;
    const confirmed = Boolean(report && report.text && report.text.confirmed === true);
    const rows = cleanScanRows();
    const ticks = state.classicText.foundTicks;
    const review = cutCleanReviewState(rows, ticks);
    const reviewFirst = state.cleanFlow !== "one_click";
    const { ticked, applied, low, needsReview } = review;
    const foundRows = cutCleanFoundRows(rows);
    const emptyConfirmed = cutCleanEmptyConfirmed(rows);
    const noInsideFound = cutCleanNoInsideFound(rows);
    const needsSelection = reviewFirst && cutCleanReportReady()
      && review.available.length > 0 && ticked === 0 && applied === 0;
    const working = scanActive || state.cutCleanBusy;
    const record = working ? null : cutCleanRenderRecord();
    const renderActive = isRenderActive(record);
    const missingFile = Boolean(record?.status === "ready" && !record.url);
    const recordReady = Boolean(record?.status === "ready" && record.url);
    const staleState = recordReady ? renderStaleFor(record) : { stale: false, noBaseline: false };
    const stale = Boolean(recordReady && staleState.stale);
    const noBaseline = Boolean(recordReady && staleState.noBaseline);
    const ready = Boolean(recordReady && !stale);
    const failed = record?.status === "failed" || record?.status === "cancelled" || missingFile;
    const engine = cutCleanEngineLabel();
    const duration = cleanCutTotal();

    if (recordReady || failed) state.cutCleanPhase = "";
    if (missingFile) {
      setCutCleanNote("The rendered file is missing. Render again; no Download is offered.");
    } else if (record?.status === "cancelled") {
      setCutCleanNote("Render cancelled. Nothing partial is kept. Clean again when ready.");
    } else if (record?.status === "failed") {
      const raw = cleanDiagnostic("Classic cut render failed:", record?.error || "");
      setCutCleanNote(`Render failed: ${tr(plainRenderError(raw))}`);
    }

    let progress = 0;
    let stage = "";
    if (scanActive || state.cutCleanPhase === "Finding text") {
      progress = Number(report?.progress);
      if (!Number.isFinite(progress)) progress = 0;
      stage = `Finding text · ${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    } else if (state.cutCleanPhase === "Cleaning") {
      progress = 0.5;
      stage = "Cleaning";
    } else if (renderActive || state.cutCleanPhase === "Rendering") {
      progress = Number(record?.progress);
      if (!Number.isFinite(progress)) progress = 0;
      stage = `Rendering · ${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    }
    if (dom.cutCleanProgress) dom.cutCleanProgress.hidden = !stage;
    if (dom.cutCleanProgressFill) {
      dom.cutCleanProgressFill.style.width = `${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`;
    }
    if (dom.cutCleanStage) dom.cutCleanStage.textContent = stage ? tr(stage) : "";

    let summary = state.cutCleanNote;
    if (!summary) {
      if (stale) {
        summary = "Changed since this render. The older file is still available; render again to update it.";
      } else if (ready) {
        summary = `Clean cut ready · ${state.target}s · ${fmtDuration(duration)} · ${engine}`;
        if (noBaseline) {
          summary += ` · ${tr("No render baseline on this browser. Render again to confirm this cut matches.")}`;
        }
      } else if (failed) {
        summary = `Render failed: ${tr(plainRenderError(record?.error || record?.message || ""))}`;
      } else if (renderActive || state.cutCleanPhase === "Rendering") {
        summary = "Rendering the cut with its Clean boxes.";
      } else if (state.cutCleanPhase === "Cleaning") {
        summary = "Applying the ticked Clean boxes.";
      } else if (scanActive) {
        summary = "Finding text on screen.";
      } else if (emptyConfirmed) {
        summary = "No baked-in text found. Nothing was rendered.";
      } else if (scanStatus === "failed") {
        const reason = clipText(report?.message || report?.error || "the scan did not finish.", 180).replace(/[.!?]+$/, "");
        summary = `The scan failed: ${reason}. Retry the scan; nothing was rendered.`;
      } else if (scanStatus === "cancelled") {
        summary = "Scan cancelled. Scan again when ready.";
      } else if (noInsideFound) {
        summary = "No found text is inside this cut. Nothing to clean here.";
      } else if (foundRows.length) {
        if (reviewFirst) {
          summary = `${foundRows.length} text${foundRows.length === 1 ? "" : "s"} found. `
            + `Review the rows, then clean.${low ? ` ${low} low-confidence.` : ""}`;
        } else {
          const count = ticked || applied || foundRows.length;
          const reviewNote = low ? ` · review ${low} more` : "";
          const fillReason = !fillEngineReady()
            ? "AI fill needs its model pack · Blur and Crop guard work"
            : "";
          if (!fillEngineReady()) {
            cleanDiagnostic("Classic AI fill unavailable:", state.fill?.engines?.[fillEngineNow()]?.reason
              || state.fill?.note || "");
          }
          summary = `${count} text${count === 1 ? "" : "s"} · ${engine}${reviewNote}${fillReason ? ` · ${fillReason}` : ""}`;
        }
      } else {
        summary = "No text scan yet for this cut.";
      }
    }
    if (dom.cutCleanSummary) {
      dom.cutCleanSummary.textContent = summary ? tr(summary) : "";
      dom.cutCleanSummary.hidden = !summary;
    }
    if (dom.cutCleanPlayNote) {
      const playable = Boolean(cleanReviewRecord());
      const showPlayNote = cutCleanActive() && !playable && !renderActive && !ready && !working;
      dom.cutCleanPlayNote.hidden = !showPlayNote;
      dom.cutCleanPlayNote.textContent = showPlayNote
        ? tr("Render a draft once to play this cut.")
        : "";
    }

    let label = reviewFirst ? "Find text" : "Find text & clean";
    let disabled = false;
    const cleanCount = ticked || applied || review.available.length;
    const staleNeedsReview = stale && needsReview && applied === 0;
    if (ready) {
      label = "";
    } else if (scanActive) {
      label = "Finding text…";
      disabled = true;
    } else if (state.cutCleanBusy) {
      label = `${state.cutCleanPhase || "Preparing"}…`;
      disabled = true;
    } else if (renderActive) {
      label = "Rendering…";
      disabled = true;
    } else if (emptyConfirmed) {
      label = "Render cut";
    } else if (noInsideFound && !applied) {
      label = "Render cut";
    } else if (stale && !staleNeedsReview && cleanCount) {
      label = `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render again`;
    } else if (scanStatus === "failed") {
      label = "Retry scan";
    } else if (scanStatus === "cancelled") {
      label = "Rescan text";
    } else if (scanStatus === "ready" && !confirmed) {
      label = "Rescan text";
    } else if (reviewFirst) {
      if (failed) {
        label = (ticked || applied)
          ? `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render`
          : "Render cut";
      } else if (cutCleanReportReady() && review.available.length) {
        label = `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render`;
        disabled = needsSelection;
      } else if (cutCleanReportReady()) {
        label = (ticked || applied)
          ? `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render`
          : "Scan again";
      }
    } else if (ticked) {
      label = `Clean ${ticked} text${ticked === 1 ? "" : "s"} & render`;
    } else if (needsReview && applied === 0 && !failed) {
      label = review.low
        ? `Review ${review.low} low-confidence`
        : `Review ${review.available.length} text${review.available.length === 1 ? "" : "s"}`;
    } else if (applied) {
      label = `Clean ${applied} text${applied === 1 ? "" : "s"} & render`;
    } else if (failed) {
      label = cleanCount
        ? `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render`
        : "Render cut";
    }
    if (dom.cutCleanRun) {
      dom.cutCleanRun.textContent = label ? tr(label) : "";
      dom.cutCleanRun.hidden = ready;
      dom.cutCleanRun.disabled = disabled || state.cutCleanBusy || scanActive || renderActive;
      dom.cutCleanRun.title = needsSelection && disabled
        ? tr("Select at least one row to clean.")
        : "";
    }
    if (dom.cutCleanCancel) {
      dom.cutCleanCancel.hidden = !(scanActive
        || state.cutCleanPhase === "Cleaning"
        || renderActive);
      dom.cutCleanCancel.disabled = false;
    }
    if (dom.cutCleanButtons) dom.cutCleanButtons.hidden = ready;
    if (dom.cutCleanResultActions) dom.cutCleanResultActions.hidden = !(ready || stale || failed);

    if (dom.cutCleanDownload) {
      if ((ready || stale) && record.url) {
        dom.cutCleanDownload.hidden = false;
        dom.cutCleanDownload.href = withToken(record.url);
        dom.cutCleanDownload.download = `${fileStem(state.job?.source?.name || "cut")}-${state.target}s.mp4`;
        dom.cutCleanDownload.className = stale ? "ghost small" : "primary small";
        const downloadLabel = tr(stale ? "Download older file" : "Download");
        dom.cutCleanDownload.innerHTML = `${esc(downloadLabel)} <span class="arrow">↓</span>`;
        dom.cutCleanDownload.title = stale
          ? tr("This file is older than the current Clean changes.")
          : "";
      } else {
        dom.cutCleanDownload.hidden = true;
        dom.cutCleanDownload.removeAttribute("href");
        dom.cutCleanDownload.title = "";
      }
    }
    if (dom.cutCleanAgain) {
      dom.cutCleanAgain.hidden = stale;
      dom.cutCleanAgain.disabled = false;
    }
    updateResultModeGuard();
  }

  async function runCutClean(options = {}) {
    if (!state.job || state.cleanScope !== "cut") return;
    if (state.cutCleanBusy || isRenderActive(cutCleanRenderRecord())) return;
    const { forceScan = false, renderOnly = false, scanOnly = false } = options;
    state.cutCleanBusy = true;
    state.cutCleanCancelled = false;
    setCutCleanNote("");
    try {
      if (renderOnly) {
        state.cutCleanPhase = "Rendering";
        state.cutCleanRecordKey = "";
        paintCutClean();
        const result = await startRender("final");
        if (!result?.render) {
          state.cutCleanPhase = "";
          setCutCleanNote("Render did not start. Check the render note in Edit.");
        } else {
          state.cutCleanRecordKey = result.render.record_key || result.render.key
            || renderKey(state.target, "final");
        }
        return;
      }

      let scanStatus = state.textScan?.status || "idle";
      let report = state.textScan?.report;
      let confirmed = Boolean(report && report.text && report.text.confirmed === true);
      if (forceScan || scanStatus !== "ready" || !confirmed) {
        state.cutCleanPhase = "Finding text";
        paintCutClean();
        await startTextScan(true);
        if (!state.job || state.cleanScope !== "cut") return;
        scanStatus = state.textScan?.status || "idle";
        report = state.textScan?.report;
        confirmed = Boolean(report && report.text && report.text.confirmed === true);
      }
      if (state.cutCleanCancelled || scanStatus === "cancelled") {
        setCutCleanNote("Scan cancelled. Nothing was cleaned or rendered. Scan again when ready.");
        return;
      }
      if (scanStatus === "failed") {
        const reason = clipText(report?.message || report?.error || "the text scan did not finish.", 200)
          .replace(/[.!?]+$/, "");
        setCutCleanNote(`The scan failed: ${reason}. Retry the scan; nothing was rendered.`);
        return;
      }
      if (!confirmed) {
        setCutCleanNote("The scan could not confirm on-screen text, so nothing was cleaned. Rescan to try again.");
        return;
      }

      const rows = cleanScanRows();
      if (scanOnly) {
        ensureCutFoundTicks();
        const found = cutCleanFoundRows(rows);
        if (!found.length) {
          setCutCleanNote("No baked-in text found. Nothing was rendered.");
          paintCutClean();
          return;
        }
        const inside = found.filter((row) => cleanRowCutStart(row) !== null).length;
        if (!inside) {
          setCutCleanNote("No found text is inside this cut. Nothing was cleaned.");
          paintCutClean();
          return;
        }
        const low = cutCleanLowRows(rows).length;
        setCutCleanNote(`${found.length} text${found.length === 1 ? "" : "s"} found. `
          + `Review the rows, then clean.${low ? ` ${low} low-confidence.` : ""}`);
        paintCutClean();
        scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
        dom.cleanFound?.querySelector(".clean-found-row")?.focus();
        return;
      }
      if (!cutCleanFoundRows(rows).length) {
        setCutCleanNote("");
        return;
      }
      ensureCutFoundTicks();
      const ticked = cutCleanTickedCount(rows, state.classicText.foundTicks);
      const hasLayers = cleanPayloadLayers().length > 0;
      if (!ticked && !hasLayers) {
        const low = cutCleanLowRows(rows).length;
        const inside = cutCleanFoundRows(rows)
          .filter((row) => cleanRowCutStart(row) !== null).length;
        if (!inside) {
          setCutCleanNote("No found text is inside this cut. Nothing was cleaned.");
          paintCutClean();
          return;
        }
        setCutCleanNote(low
          ? `${rows.length} text${rows.length === 1 ? "" : "s"} found · review ${low} low-confidence row${low === 1 ? "" : "s"}; tick the ones to remove.`
          : `${rows.length} text${rows.length === 1 ? "" : "s"} found. Tick the ones to remove, or review the list.`);
        paintCutClean();
        scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
        dom.cleanFound?.querySelector(".clean-found-row")?.focus();
        return;
      }

      if (ticked) {
        state.cutCleanPhase = "Cleaning";
        paintCutClean();
        await loadFillStatus();
        const before = classicCleanLayers().length;
        applyFoundTicks();
        await persistClassicText(classicPlanClips());
        if (state.cutCleanCancelled) {
          setCutCleanNote("Cleaning stopped before render. Nothing was rendered.");
          return;
        }
        if (classicCleanLayers().length <= before) {
          setCutCleanNote("No box was added. Check the fill engine or tick a text row again.");
          return;
        }
      }

      state.cutCleanPhase = "Rendering";
      state.cutCleanRecordKey = "";
      paintCutClean();
      const result = await startRender("final");
      if (!result?.render) {
        state.cutCleanPhase = "";
        setCutCleanNote("Render did not start. Check the render note in Edit.");
        return;
      }
      state.cutCleanRecordKey = result.render.record_key || result.render.key
        || renderKey(state.target, "final");
    } finally {
      state.cutCleanBusy = false;
      if (state.cutCleanPhase !== "Rendering") state.cutCleanPhase = "";
      paintCutClean();
    }
  }

  async function cancelCutClean() {
    if (!state.job || state.cleanScope !== "cut") return;
    const scanActive = ["queued", "running"].includes(state.textScan?.status || "");
    if (scanActive) {
      state.cutCleanCancelled = true;
      setCutCleanNote("Cancelling the scan…");
      paintCutClean();
      try {
        await cancelTextScan();
        if (!state.job || state.cleanScope !== "cut") return;
        setCutCleanNote("Scan cancelled. Nothing was cleaned or rendered. Scan again when ready.");
      } catch (error) {
        setCutCleanNote("Cancel did not reach the scan. Wait, then try again.");
      } finally {
        paintCutClean();
      }
      return;
    }
    if (state.cutCleanPhase === "Cleaning") {
      state.cutCleanCancelled = true;
      setCutCleanNote("Stopping before render…");
      paintCutClean();
      return;
    }
    if (isRenderActive(cutCleanRenderRecord())) {
      setCutCleanNote("Stopping the render…");
      paintCutClean();
      await cancelRender();
      paintCutClean();
      return;
    }
    if (state.cutCleanPhase === "Rendering") {
      setCutCleanNote("The render is starting. Cancel again when it is running.");
      paintCutClean();
    }
  }

  async function cleanAgainCut() {
    if (!state.job || state.cleanScope !== "cut") return;
    const rows = cleanScanRows();
    const emptyConfirmed = cutCleanEmptyConfirmed(rows);
    setCutCleanNote("");
    state.cutCleanCancelled = false;
    state.cutCleanRecordKey = "";
    state.cutCleanPhase = "";
    paintCutClean();
    if (emptyConfirmed) {
      const note = classicCleanLayers().length
        ? "No baked-in text found. Re-rendering with the existing Clean boxes."
        : "No baked-in text found. Rendering the cut without Clean boxes.";
      await runCutClean({ renderOnly: true });
      setCleanStatus(note);
      return;
    }
    await runCutClean({ forceScan: !classicCleanLayers().length });
  }

  async function cutCleanPrimaryAction() {
    if (!state.job || state.cleanScope !== "cut") return;
    const reviewFirst = state.cleanFlow !== "one_click";
    if (reviewFirst && !cutCleanReportReady()) {
      await runCutClean({ scanOnly: true, forceScan: true });
      return;
    }
    const rows = cleanScanRows();
    const emptyConfirmed = cutCleanEmptyConfirmed(rows);
    const noInsideFound = cutCleanNoInsideFound(rows);
    const review = cutCleanReviewState(rows, state.classicText.foundTicks);
    const ticked = review.ticked;
    const record = cutCleanRenderRecord();
    if (emptyConfirmed) {
      await runCutClean({ renderOnly: true });
      return;
    }
    const staleRecord = record?.status === "ready" && renderStaleFor(record).stale;
    const failedRecord = record?.status === "failed" || record?.status === "cancelled"
      || Boolean(record?.status === "ready" && !record.url);
    const staleNeedsReview = staleRecord && review.needsReview && review.applied === 0;
    if (staleRecord && !staleNeedsReview) {
      await runCutClean();
      return;
    }
    if (noInsideFound && !review.applied) {
      await runCutClean({ renderOnly: true });
      return;
    }
    if (failedRecord && !ticked && review.applied === 0) {
      await runCutClean({ renderOnly: true });
      return;
    }
    if (state.textScan?.status === "ready" && review.needsReview
      && review.applied === 0 && !failedRecord) {
      scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
      const reviewRow = review.low
        ? dom.cleanFound?.querySelector(".clean-found-row.is-low")
        : dom.cleanFound?.querySelector(".clean-found-row");
      reviewRow?.focus();
      setCutCleanNote(review.low
        ? "Review the low-confidence rows. Tick the ones to remove, then use the Clean action again."
        : "Review the found text. Tick the rows to remove, then use the Clean action again.");
      paintCutClean();
      return;
    }
    await runCutClean();
  }

  async function verifySourceCleanMedia(record) {
    if (!state.job || !record) return { ok: false, size: 0 };
    const url = record.url || `/api/classic/jobs/${state.job.id}/clean/source/media`;
    const headers = {};
    const token = tokenValue();
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      const response = await fetch(withToken(url), { method: "GET", headers });
      if (!response.ok) return { ok: false, size: 0 };
      const size = Number(response.headers.get("content-length") || 0);
      try { await response.body?.cancel(); } catch (_) { /* the check is the status */ }
      return { ok: true, size: Number.isFinite(size) ? size : 0 };
    } catch (_) {
      return { ok: false, size: 0 };
    }
  }

  async function finishSourceCleanReady(record) {
    const check = await verifySourceCleanMedia(record);
    if (!check.ok) {
      state.sourceClean = {
        ...record,
        status: "failed",
        error: "The clean file is missing. Render it again; no Download is offered.",
        path: null,
        url: null,
        cached: false,
      };
      return;
    }
    state.sourceCleanMediaSize = check.size;
    state.sourceClean = record;
  }

  function startSourceCleanPoll(id) {
    stopSourceCleanPoll();
    const token = state.sourceCleanPollToken;
    const isCurrent = () => token === state.sourceCleanPollToken
      && state.job?.id === id
      && state.cleanScope === "source";
    const tick = async () => {
      if (!isCurrent()) return;
      try {
        const record = await api(`/api/classic/jobs/${id}/clean/source`);
        if (!isCurrent()) return;
        state.sourceClean = record;
        if (record.status === "ready") {
          await finishSourceCleanReady(record);
          if (!isCurrent()) return;
          paintSourceClean();
          return;
        }
        paintSourceClean();
        if (isCurrent() && sourceCleanActive(record)) {
          state.sourceCleanTimer = setTimeout(tick, 700);
        }
      } catch (error) {
        if (!isCurrent()) return;
        state.sourceClean = {
          ...(state.sourceClean || {}),
          status: "failed",
          error: "The clean status could not be read. Check the server, then retry.",
        };
        cleanDiagnostic("Classic clean status failed:", error.message);
        paintSourceClean();
      }
    };
    state.sourceCleanTimer = setTimeout(tick, 700);
  }

  async function loadSourceCleanRecord() {
    if (!state.job || state.cleanScope !== "source") return;
    const id = state.job.id;
    try {
      const record = await api(`/api/classic/jobs/${id}/clean/source`);
      if (!state.job || state.job.id !== id || state.cleanScope !== "source") return;
      state.sourceClean = record;
      if (record.status === "ready") await finishSourceCleanReady(record);
      else if (sourceCleanActive(record)) startSourceCleanPoll(id);
    } catch (error) {
      if (!state.job || state.job.id !== id) return;
      state.sourceCleanNote = "The Clean status could not be read. Check the server, then retry.";
      cleanDiagnostic("Classic clean status failed:", error.message);
    }
    paintSourceClean();
  }

  function sourceInsideRow(row) {
    if (!row.ranges.length) return true;
    const duration = Math.max(0, Number(state.job?.source?.duration) || 0);
    return row.ranges.every((range) => Number(range.end) > 0
      && (duration <= 0 || Number(range.start) < duration));
  }

  function ensureSourceFoundTicks() {
    if (state.classicText.foundTicksInit) return;
    applyStoredFoundTicks(cleanScanRows(), { source: true });
  }

  async function estimateSourceClean(clean = cleanPayloadLayers()) {
    try {
      return await api(`/api/classic/jobs/${state.job.id}/fill/estimate`, {
        method: "POST",
        body: JSON.stringify({
          clips: classicPlanClips(),
          clean,
          aspect: "source",
          ...fillRequestFields(),
        }),
      });
    } catch (error) {
      return { estimate_seconds: null, text: error.message, failed: true };
    }
  }

  async function runSourceClean(options = {}) {
    if (!state.job || state.cleanScope !== "source") return;
    if (sourceCleanActive(state.sourceClean) || state.sourceCleanBusy) return;
    state.sourceCleanBusy = true;
    state.sourceCleanRunCancelled = false;
    state.sourceCleanPhase = "";
    try {
      await runSourceCleanSteps(options);
    } finally {
      state.sourceCleanBusy = false;
      state.sourceCleanPhase = "";
      paintSourceClean();
    }
  }

  async function runSourceCleanSteps(options = {}) {
    const { confirm = false, forceScan = false, scanOnly = false } = options;
    const reviewFirst = state.cleanFlow !== "one_click";

    state.sourceCleanNote = "";
    state.sourceCleanNotFound = false;
    let report = state.textScan?.report;
    let confirmed = Boolean(report && report.text && report.text.confirmed === true);
    const scanStatus = state.textScan?.status || "idle";
    if (forceScan || scanStatus !== "ready" || !confirmed) {
      state.sourceCleanPhase = "Finding text";
      await startTextScan(true);
      if (!state.job || state.cleanScope !== "source") return;
      report = state.textScan?.report;
      confirmed = Boolean(report && report.text && report.text.confirmed === true);
    }
    if (state.sourceCleanRunCancelled) {
      state.sourceCleanNote = "Scan cancelled. Nothing was cleaned or rendered. Scan again when ready.";
      paintSourceClean();
      return;
    }
    if (state.textScan?.status === "cancelled") {
      state.sourceCleanNote = "Scan cancelled. Nothing was cleaned or rendered. Scan again when ready.";
      paintSourceClean();
      return;
    }
    if (state.textScan?.status === "failed") {
      const reason = clipText(
        report?.message || report?.error || "the text scan did not finish.", 200,
      ).replace(/[.!?]+$/, "");
      state.sourceCleanNote = `The scan failed: ${reason}. Retry the scan; nothing was rendered.`;
      paintSourceClean();
      return;
    }
    if (!confirmed) {
      state.sourceCleanNote = "The scan could not confirm on-screen text, so nothing was cleaned. Rescan to try again.";
      paintSourceClean();
      return;
    }

    const rows = cleanScanRows();
    if (!rows.length) {
      state.sourceCleanNotFound = true;
      state.sourceCleanNeedConfirm = false;
      state.sourceCleanNote = "";
      paintSourceClean();
      return;
    }
    ensureSourceFoundTicks();
    const tickedRows = tickedRowsFor(rows, state.classicText.foundTicks, { source: true });
    const ticked = tickedRows.length;
    const hasLayers = cleanPayloadLayers().length > 0;
    if (scanOnly) {
      const available = sourceReviewRows(rows);
      if (!available.length) {
        state.sourceCleanNotFound = true;
        state.sourceCleanNeedConfirm = false;
        state.sourceCleanEstimate = null;
        state.sourceCleanNote = "";
        paintSourceClean();
        return;
      }
      const low = sourceLowRows(rows).length;
      state.sourceCleanNeedConfirm = false;
      state.sourceCleanEstimate = null;
      state.sourceCleanNote = `${available.length} text`
        + `${available.length === 1 ? "" : "s"} found. `
        + `Review the rows, then clean.${low ? ` ${low} low-confidence.` : ""}`;
      paintSourceClean();
      scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
      dom.cleanFound?.querySelector(".clean-found-row")?.focus();
      return;
    }
    if (!ticked && !hasLayers) {
      state.sourceCleanNote = reviewFirst
        ? `${rows.length} text${rows.length === 1 ? "" : "s"} found. Review the rows, then clean.`
        : `${rows.length} text${rows.length === 1 ? "" : "s"} found. Tick the ones to remove, or review the list.`;
      paintSourceClean();
      scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
      dom.cleanFound?.querySelector(".clean-found-row")?.focus();
      return;
    }

    const duration = Math.max(0, Number(state.job.source.duration) || 0);
    if (!reviewFirst && duration >= 180 && !confirm) {
      state.sourceCleanPhase = "Estimating";
      paintSourceClean();
      const method = cleanMethodForTicks();
      const pending = ticked
        ? cleanEstimatePayload(rows, tickedRows.map((row) => rows.indexOf(row)), method)
        : cleanPayloadLayers();
      const wantsFill = pending.some(
        (layer) => cleanMethodKey(layer) === "fill" && !layer.hidden,
      );
      const estimate = wantsFill
        ? await estimateSourceClean(pending)
        : {
          estimate_seconds: null,
          measured: false,
          blur: true,
          text: "Blur needs no fill estimate. Render progress will show.",
        };
      state.sourceCleanEstimate = estimate;
      state.sourceCleanNeedConfirm = true;
      paintSourceClean();
      return;
    }

    if (ticked) {
      state.sourceCleanPhase = "Preparing clean";
      await loadFillStatus();
      const before = classicCleanLayers().length;
      applyFoundTicks();
      await persistClassicText(classicPlanClips());
      if (classicCleanLayers().length <= before) {
        state.sourceCleanNote = "No box was added. Check the fill engine or tick a text row again.";
        paintSourceClean();
        return;
      }
    }

    state.sourceCleanNeedConfirm = false;
    state.sourceCleanEstimate = null;
    state.sourceCleanPhase = "Cleaning";
    await startSourceCleanRender();
  }

  function sourceCleanErrorText(error) {
    const raw = cleanDiagnostic("Classic clean render did not start:", error?.message || "");
    return plainCleanError(raw);
  }

  async function startSourceCleanRender() {
    if (!state.job || state.cleanScope !== "source") return;
    const layers = cleanPayloadLayers();
    if (!layers.length) {
      state.sourceCleanNote = "No text is ticked, so there is nothing to clean. Tick a text row first.";
      paintSourceClean();
      return;
    }
    state.sourceCleanBusy = true;
    state.sourceCleanNote = "";
    state.sourceCleanNotFound = false;
    paintSourceClean();
    try {
      const record = await api(`/api/classic/jobs/${state.job.id}/clean/source/render`, {
        method: "POST",
        body: JSON.stringify({ clips: classicPlanClips(), clean: layers, ...fillRequestFields() }),
      });
      if (!state.job || state.cleanScope !== "source") return;
      state.sourceClean = record;
      if (record.status === "ready") {
        await finishSourceCleanReady(record);
        paintSourceClean();
        return;
      }
      paintSourceClean();
      if (sourceCleanActive(record)) startSourceCleanPoll(state.job.id);
    } catch (error) {
      if (!state.job || state.cleanScope !== "source") return;
      state.sourceClean = {
        status: "failed",
        error: sourceCleanErrorText(error),
        progress: 1,
        path: null,
        url: null,
        cached: false,
      };
      paintSourceClean();
    } finally {
      state.sourceCleanBusy = false;
      paintSourceClean();
    }
  }

  async function cancelSourceCleanRender() {
    if (!state.job || state.cleanScope !== "source") return;
    const id = state.job.id;
    const scanActive = ["queued", "running"].includes(state.textScan?.status || "");
    if (scanActive && !sourceCleanActive(state.sourceClean)) {
      if (dom.sourceCleanCancel) dom.sourceCleanCancel.disabled = true;
      state.sourceCleanRunCancelled = true;
      state.sourceCleanNote = "Cancelling the scan…";
      paintSourceClean();
      try {
        await cancelTextScan();
        if (!state.job || state.job.id !== id) return;
        state.sourceCleanNote = "Scan cancelled. Nothing was cleaned or rendered. Scan again when ready.";
      } catch (error) {
        state.sourceCleanNote = "Cancel did not reach the scan. Wait, then try again.";
      } finally {
        if (dom.sourceCleanCancel) dom.sourceCleanCancel.disabled = false;
        paintSourceClean();
      }
      return;
    }
    if (dom.sourceCleanCancel) dom.sourceCleanCancel.disabled = true;
    try {
      const answer = await api(`/api/classic/jobs/${id}/clean/source/cancel`, { method: "POST" });
      if (!state.job || state.job.id !== id) return;
      state.sourceClean = {
        ...(state.sourceClean || {}),
        status: answer?.status || "cancelling",
        message: answer?.status === "cancelling" ? "Stopping…" : (answer?.message || "Cancelled"),
      };
      paintSourceClean();
      if (sourceCleanActive(state.sourceClean)) startSourceCleanPoll(id);
    } catch (error) {
      if (!state.job || state.job.id !== id) return;
      state.sourceCleanNote = "Cancel did not reach the render. Wait, then try again.";
      paintSourceClean();
    } finally {
      if (dom.sourceCleanCancel) dom.sourceCleanCancel.disabled = false;
    }
  }

  async function sourceCleanPrimaryAction() {
    if (!state.job || state.cleanScope !== "source") return;
    const record = state.sourceClean;
    if (record?.status === "ready") return;
    const retryRender = record?.status === "failed" || record?.status === "cancelled";
    if (state.cleanFlow !== "one_click") {
      if (!sourceCleanReportReady()) {
        await runSourceClean({ scanOnly: true, forceScan: true });
        return;
      }
      const rows = cleanScanRows();
      const available = sourceReviewRows(rows);
      if (!available.length) {
        await runSourceClean({ scanOnly: true, forceScan: true });
        return;
      }
      const ticked = sourceTickedCount(rows, state.classicText.foundTicks);
      const applied = classicCleanLayers().filter((layer) => layer.source === "scan").length;
      if (!ticked && !applied) {
        const low = sourceLowRows(rows).length;
        state.sourceCleanNote = `${available.length} text${available.length === 1 ? "" : "s"} found. `
          + `Review the rows, then clean.${low ? ` ${low} low-confidence.` : ""}`;
        paintSourceClean();
        scrollIntoViewSafe(dom.cleanFound, { behavior: "smooth", block: "nearest" });
        dom.cleanFound?.querySelector(".clean-found-row")?.focus();
        return;
      }
      await runSourceClean({ confirm: true });
      return;
    }
    await runSourceClean({
      confirm: state.sourceCleanNeedConfirm || retryRender,
    });
  }

  async function cleanAgainSource() {
    stopSourceReelPoll();
    const rescan = state.sourceCleanNotFound;
    state.sourceCleanNeedConfirm = false;
    state.sourceCleanEstimate = null;
    state.sourceCleanNotFound = false;
    state.sourceCleanNote = "";
    state.sourceCleanAnalysisError = "";
    state.sourceCleanAnalysisDetail = "";
    state.sourceClean = null;
    state.sourceCleanReelStarted = false;
    paintSourceClean();
    await runSourceClean({ confirm: true, forceScan: rescan });
  }

  function backToSourceClean() {
    if (!state.job || state.cleanScope !== "source") return;
    state.sourceCleanAnalysisError = "";
    state.sourceCleanAnalysisDetail = "";
    state.sourceCleanNote = "";
    paintSourceClean();
  }

  function sourceAnalysisStopped(status) {
    if (status === "cancelled") return "Analysis was cancelled.";
    if (status === "interrupted") return "Analysis was interrupted.";
    if (status === "ready") return "Analysis finished without a cut.";
    return "Analysis stopped before it could build the cut.";
  }

  function sourceAnalysisStoppedNote(status) {
    return `${tr(sourceAnalysisStopped(status))} ${tr("Download the source clean file, or retry.")}`;
  }

  function startSourceReelPoll(id) {
    stopSourceReelPoll();
    const token = state.sourceReelToken;
    const isCurrent = () => (
      token === state.sourceReelToken
      && state.job?.id === id
      && state.cleanScope === "source"
    );
    let misses = 0;
    const tick = async () => {
      if (!isCurrent()) return;
      try {
        const job = await api(`/api/jobs/${id}`);
        if (!isCurrent()) return;
        misses = 0;
        if (job.status === "ready" && job.analysis) {
          stopSourceReelPoll();
          state.sourceCleanReelStarted = false;
          state.sourceCleanAnalysisError = "";
          state.sourceCleanAnalysisDetail = "";
          state.sourceCleanNote = "";
          await openJob(id);
          return;
        }
        const terminal = job.status === "ready"
          || ["failed", "cancelled", "interrupted"].includes(job.status);
        if (terminal) {
          stopSourceReelPoll();
          state.job = job;
          state.sourceCleanReelStarted = false;
          const detail = String(job.error || job.message || "").trim();
          if (detail) console.warn("Classic analysis stopped:", detail);
          state.sourceCleanAnalysisDetail = detail;
          state.sourceCleanAnalysisError = sourceAnalysisStopped(job.status);
          state.sourceCleanNote = sourceAnalysisStoppedNote(job.status);
          paintSourceClean();
          return;
        }
        state.job = { ...state.job, ...job };
        const progress = Number.isFinite(Number(job.progress))
          ? ` · ${Math.round(Math.max(0, Math.min(1, Number(job.progress))) * 100)}%`
          : "";
        state.sourceCleanNote = `${tr(job.message || "Analysis is running.")}${progress}`;
        paintSourceClean();
        state.sourceReelTimer = setTimeout(tick, 1000);
      } catch (error) {
        if (!isCurrent()) return;
        misses += 1;
        if (misses >= 5) {
          stopSourceReelPoll();
          state.sourceCleanReelStarted = false;
          state.sourceCleanAnalysisDetail = error.message || "";
          if (state.sourceCleanAnalysisDetail) {
            console.warn("Classic analysis status failed:", state.sourceCleanAnalysisDetail);
          }
          state.sourceCleanAnalysisError = "Analysis status could not be checked.";
          state.sourceCleanNote = `${tr(state.sourceCleanAnalysisError)} ${tr("Download the source clean file, or retry.")}`;
          paintSourceClean();
          return;
        }
        state.sourceReelTimer = setTimeout(tick, 1500);
      }
    };
    tick();
  }

  async function makeReelFromSource() {
    if (!state.job || state.cleanScope !== "source") return;
    const job = state.job;
    if (job.status === "ready" && job.analysis) {
      await prepareResult(job);
      return;
    }
    // A second click while a poll is live must not submit another analysis.
    if (state.sourceCleanReelStarted) return;
    state.sourceCleanReelStarted = true;
    state.sourceCleanAnalysisError = "";
    state.sourceCleanAnalysisDetail = "";
    state.sourceCleanNote = "Starting analysis…";
    paintSourceClean();
    try {
      const answer = await api(`/api/jobs/${job.id}/analyze`, { method: "POST" });
      if (!state.job || state.job.id !== job.id || state.cleanScope !== "source") return;
      if (answer && answer.status === "ready") {
        const fresh = await api(`/api/jobs/${job.id}`);
        if (!state.job || state.job.id !== job.id || state.cleanScope !== "source") return;
        if (fresh.status === "ready" && fresh.analysis) {
          await prepareResult(fresh);
          return;
        }
      }
      state.sourceCleanNote = "Analysis started. The cut opens here when it is ready.";
      paintSourceClean();
      startSourceReelPoll(job.id);
    } catch (error) {
      state.sourceCleanReelStarted = false;
      state.sourceCleanAnalysisDetail = error.message || "";
      if (state.sourceCleanAnalysisDetail) {
        console.warn("Classic analysis did not start:", state.sourceCleanAnalysisDetail);
      }
      state.sourceCleanAnalysisError = "Analysis did not start.";
      state.sourceCleanNote = `${tr(state.sourceCleanAnalysisError)} ${tr("Try again.")}`;
      paintSourceClean();
    }
  }

  async function prepareSourceClean(job) {
    state.job = job;
    cancelAudioScript();
    cancelTranslationWarm();
    abortTextScan();
    resetSourceCleanState();
    state.cleanScope = "source";
    state.translation = null;
    state.meta = {
      width: job.source.width,
      height: job.source.height,
      duration: job.source.duration,
      has_audio: job.source.has_audio,
    };
    state.fileName = job.source.name;
    state.plan = sourcePlanForJob(job);
    state.target = state.plan.target || 1;
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
    state.classicText = freshClassicText();
    state.classicText.previewSide = "before";
    setCleanStatus("");
    dom.hookLab.hidden = true;
    dom.hookLab.innerHTML = "";
    dom.transcriptPanel.hidden = true;
    dom.transcriptPanel.innerHTML = "";
    dom.momentsFull.hidden = true;
    dom.momentsRail.hidden = false;
    resetCutCleanState();
    applyCleanMode(false);
    applySourceMode(true);
    setSourceAspect(job.source.width, job.source.height);
    renderSourceCleanHeader();
    dom.resultTitle.textContent = fileStem(job.source.name);
    dom.resultTitle.title = job.source.name || "";
    dom.resultMeta.textContent = `${job.source.name} · ${job.source.width}×${job.source.height} · ${fmtDuration(job.source.duration)} source`;
    dom.resultMeta.title = job.source.name || "";
    if (dom.usageReadout) dom.usageReadout.textContent = "";
    updateAnalyzeState();
    showView("result");
    paintCleanStage();
    await loadFillStatus();
    renderSourceCleanHeader();
    await refreshTextScan();
    await refreshClassicText(true);
    if (state.textScan?.status === "ready") {
      ensureSourceFoundTicks();
      const report = state.textScan.report;
      const confirmed = Boolean(report && report.text && report.text.confirmed === true);
      if (confirmed && !cleanScanRows().some((row) => !row.manual)) {
        state.sourceCleanNotFound = true;
      }
    }
    paintCleanStage();
    scheduleCleanFrame();
    await loadSourceCleanRecord();
    paintSourceClean();
    openCleanAtFirstText();
    paintCleanStage();
    scheduleCleanFrame();
    history.replaceState(null, "", jobHash(job.id));
    document.title = `${fileStem(job.source.name)} · VibeCut`;
  }

  // A source -> cut switch keeps the same job. Flush the source save that is
  // still debounced before the cut lookup, then start the cut with a fresh
  // text/tick state so a late source PUT cannot land on the cut or preselect
  // cut rows.
  async function leaveSourceTextBeforeCut() {
    const pending = state.classicText.saveTimer;
    const inFlight = state.classicText.savePromise;
    if (pending) clearTimeout(pending);
    state.classicText.saveTimer = null;
    if (pending && state.job?.id) {
      await persistClassicText(classicPlanClips());
    }
    if (inFlight) await inFlight;
    stopCleanReview();
    if (state.classicText.frameTimer) clearTimeout(state.classicText.frameTimer);
    state.classicText.frameTimer = null;
    try { state.classicText.frame.controller?.abort(); } catch (_) { /* ignore */ }
    if (state.classicText.frame.url) URL.revokeObjectURL(state.classicText.frame.url);
    state.classicText = freshClassicText();
    renderClassicText();
  }

  async function prepareResult(job) {
    const leavingSource = state.cleanScope === "source";
    const sourceJobId = leavingSource ? state.job?.id : "";
    if (leavingSource) await leaveSourceTextBeforeCut();
    if (leavingSource && (state.job?.id !== sourceJobId || state.cleanScope !== "source")) {
      // A navigation during the flush wins; do not pull the founder back.
      return;
    }
    state.job = job;
    state.cleanScope = "cut";
    resetSourceCleanState();
    resetCutCleanState();
    applySourceMode(false);
    applyCleanMode(false);
    setCleanStatus("");
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
    paintCutClean();
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
    const scenes = state.job?.analysis?.scenes;
    if (!Array.isArray(scenes) || !scene) return;
    const index = scenes.findIndex((item) => item.id === scene.id);
    if (index >= 0) scenes[index] = { ...scenes[index], ...scene };
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
    const cutKey = classicCutKey(classicPlanClips());
    if (state.cleanScope === "cut" && cutKey && cutKey !== state.classicText.loadedKey) {
      // The cut changed. Wait for refreshClassicText to load this cut's Clean
      // layers before deciding which found rows are still available to tick.
      state.classicText.pendingTickReset = cutKey;
      state.cutCleanRecordKey = "";
    }
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
      scrollIntoViewSafe(dom.mixerPanel, { behavior: "smooth", block: "nearest" });
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
        scrollIntoViewSafe(dom.momentsFull, { behavior: "smooth", block: "nearest" });
      }
    }
  }

  function renderScenes() {
    if (!state.job) return;
    const scenes = [...(state.job.analysis?.scenes || [])];
    if (!scenes.length) return;
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
    const scenes = [...(state.job.analysis?.scenes || [])];
    if (!scenes.length) return;
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
    const scenes = [...(state.job.analysis?.scenes || [])];
    if (!scenes.length) return;
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
    state.overrideHook = sceneId === state.job.analysis?.hook_scene ? null : sceneId;
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
      scrollIntoViewSafe(document.querySelector(".export-panel"), { behavior: "smooth", block: "start" });
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
              ...fillRequestFields(),
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
    if (state.cleanScope === "source") return [sourceClipForJob(state.job)];
    return (state.plan?.clips || []).map((clip) => ({ ...clip }));
  }

  // The backend's identity: the scan tracklet first, else the text and the
  // rounded source-space box. Kept local so an undo/re-add can ask for restore.
  function cleanIdentityToken(layer) {
    const tracklet = String(layer?.tracklet_id || "").trim();
    if (tracklet) return JSON.stringify(["tracklet", tracklet]);
    const box = layer?.box || {};
    const rect = ["x", "y", "w", "h"].map((axis) => (
      Math.round((Number(box[axis]) || 0) * 10000) / 10000
    ));
    return JSON.stringify(["text_key", String(layer?.text_key || ""), rect]);
  }

  function durableDeletedTokens(key = state.classicText.dataKey || classicCutKey(classicPlanClips())) {
    if (!(state.classicText.durableCleanDeleted instanceof Map)) {
      state.classicText.durableCleanDeleted = new Map();
    }
    if (!state.classicText.durableCleanDeleted.has(key)) {
      state.classicText.durableCleanDeleted.set(key, new Set());
    }
    return state.classicText.durableCleanDeleted.get(key);
  }

  function newCleanTokenSet(key = state.classicText.dataKey || classicCutKey(classicPlanClips())) {
    if (!(state.classicText.newCleanTokens instanceof Map)) {
      state.classicText.newCleanTokens = new Map();
    }
    if (!state.classicText.newCleanTokens.has(key)) {
      state.classicText.newCleanTokens.set(key, new Set());
    }
    return state.classicText.newCleanTokens.get(key);
  }

  // Pending deletes belong to one cut hash. A lookup on that cut must not
  // forget a delete whose debounced PUT has not been sent yet.
  function pendingCleanDeletes(key = state.classicText.dataKey || classicCutKey(classicPlanClips())) {
    if (!(state.classicText.deletedClean instanceof Map)) {
      state.classicText.deletedClean = new Map();
    }
    let entry = state.classicText.deletedClean.get(key);
    if (!entry || !(entry.ids instanceof Set) || !(entry.tokens instanceof Set)) {
      entry = { ids: new Set(), tokens: new Set() };
      state.classicText.deletedClean.set(key, entry);
    }
    return entry;
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
    // Older cuts can hold the same scanned text many times. One box per text
    // is the saved shape from now on; write the deduped list back when it
    // actually changed.
    const dedupedClean = dedupeCleanLayers(state.classicText.clean);
    const cleanDeduped = dedupedClean.changed;
    if (cleanDeduped) state.classicText.clean = dedupedClean.layers;
    const resetTicks = state.cleanScope === "cut"
      && Boolean(state.classicText.pendingTickReset)
      && state.classicText.pendingTickReset === key;
    if (resetTicks) {
      state.classicText.foundTicks = new Set();
      state.classicText.foundTicksInit = false;
      state.classicText.pendingTickReset = "";
    }
    if (cut && Array.isArray(cut.source_clean_deleted)) {
      const durable = durableDeletedTokens(key);
      durable.clear();
      for (const token of cut.source_clean_deleted) durable.add(String(token));
    }
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
    if (cleanDeduped) saveClassicText();
    if (resetTicks && state.textScan?.status === "ready") ensureCutFoundTicks();
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
      if (state.cleanScope !== "source") {
        if (result.source_clean_note) {
          setCleanStatus(result.source_clean_note);
        } else if (Number(result.source_clean_added) > 0) {
          setCleanStatus("Source Clean layers added.");
        }
      }
      updateRenderPanel();
    } catch (_) {
      if (seq !== state.classicText.seq) return;
      state.classicText.loadedKey = "";
      applyClassicTextCut(null);
    }
  }

  async function persistClassicText(clips) {
    if (!state.job || !clips.length) return;
    const clean = cleanPayloadLayers();
    const presentIds = new Set(clean.map((layer) => String(layer.id || "")));
    const presentTokens = new Set(clean.map((layer) => cleanIdentityToken(layer)));
    const cutKey = classicCutKey(clips);
    const pending = pendingCleanDeletes(cutKey);
    const durable = durableDeletedTokens(cutKey);
    const newlyAdded = newCleanTokenSet(cutKey);
    const restoredIds = Array.from(pending.ids)
      .filter((id) => presentIds.has(id));
    const restoredTokens = Array.from(pending.tokens)
      .filter((token) => presentTokens.has(token));
    const durableRestored = Array.from(newlyAdded)
      .filter((token) => durable.has(token) && presentTokens.has(token));
    const restore = restoredIds.length > 0 || restoredTokens.length > 0
      || durableRestored.length > 0;
    const deleted = Array.from(pending.ids)
      .filter((id) => id && !presentIds.has(id));
    try {
      await api(`/api/classic/jobs/${state.job.id}/text`, {
        method: "PUT",
        body: JSON.stringify({
          clips,
          overlays: state.classicText.overlays,
          effects: state.classicText.effects,
          clean,
          source_clean_deleted: deleted,
          source_clean_restore: restore,
        }),
      });
      for (const id of restoredIds) pending.ids.delete(id);
      for (const token of restoredTokens) pending.tokens.delete(token);
      for (const token of durableRestored) {
        durable.delete(token);
        pending.tokens.delete(token);
      }
      newlyAdded.clear();
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
      const pending = persistClassicText(clips);
      state.classicText.savePromise = pending;
      pending.finally(() => {
        if (state.classicText.savePromise === pending) {
          state.classicText.savePromise = null;
        }
      });
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
  // LaMa is the default engine. No time is promised: the render counts its own frames.
  const CLEAN_FILL_COST = {
    lama: "AI fill is the slowest step of a render. The time left shows while it runs.",
    migan: "Always reads a 512 square, so LaMa is faster on thin lines.",
    telea: "About a fifth of a second a frame. Smears on detail.",
    ns: "About a fifth of a second a frame. Smears on detail.",
  };
  const CLEAN_FILL_ENGINE_LABEL = {
    lama: "LaMa",
    migan: "MI-GAN",
    telea: "Telea",
    ns: "Navier-Stokes",
  };
  const CLEAN_SCAN_METHOD = { plate: "blur", crop_guard: "crop", mask: "blur", blur: "blur" };
  const CLEAN_MIN_BOX = 0.02;
  // These match routes_classic.normalize_classic_clean. A new box and a box
  // reloaded from the server must hash the same before any render signature is
  // compared.
  const CLEAN_DEFAULT_COLOR = "#0b0d12";
  const CLEAN_DEFAULT_OPACITY = 1;
  const CLEAN_DEFAULT_RADIUS = 24;
  const SOURCE_CONFIDENCE_MIN = 0.65;
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
    const deduped = dedupeCleanLayers(state.classicText.clean);
    if (deduped.changed) state.classicText.clean = deduped.layers;
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

  function mergeCleanRanges(ranges) {
    const items = [];
    for (const item of ranges || []) {
      const start = Number(item?.start);
      const end = Number(item?.end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      items.push({
        start: Math.round(start * 1000) / 1000,
        end: Math.round(end * 1000) / 1000,
      });
    }
    items.sort((a, b) => a.start - b.start || a.end - b.end);
    const merged = [];
    for (const item of items) {
      const last = merged[merged.length - 1];
      if (last && item.start <= last.end + 1e-6) {
        last.end = Math.max(last.end, item.end);
      } else {
        merged.push({ ...item });
      }
    }
    return merged;
  }

  function cleanPayloadLayers() {
    return classicCleanLayers().map((layer) => ({
      id: layer.id,
      method: cleanMethodKey(layer),
      box: { x: layer.box.x, y: layer.box.y, w: layer.box.w, h: layer.box.h },
      ranges: mergeCleanRanges(layer.ranges || []),
      label: layer.label || "",
      kind: layer.kind || layer.tracklet_kind || "manual",
      tracklet_id: layer.tracklet_id || undefined,
      tracklet_kind: layer.tracklet_kind || undefined,
      color: layer.color || CLEAN_DEFAULT_COLOR,
      opacity: Number.isFinite(Number(layer.opacity)) ? Number(layer.opacity) : CLEAN_DEFAULT_OPACITY,
      radius: Number.isFinite(Number(layer.radius)) ? Number(layer.radius) : CLEAN_DEFAULT_RADIUS,
      hidden: Boolean(layer.hidden),
      source: layer.source || "manual",
      ...(cleanMethodKey(layer) === "fill" ? { engine: fillEngineNow() } : {}),
      ...(layer.mask ? { mask: layer.mask } : {}),
      ...(layer.text_key ? { text_key: layer.text_key } : {}),
      ...(layer.fill_keys !== undefined && layer.fill_keys !== null ? { fill_keys: layer.fill_keys } : {}),
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

  /** One compact status chip, an engine menu and a small Fill options popover. */
  function fillMenuHtml() {
    const choice = fillChoiceNow();
    const engines = state.fill?.engines || {};
    const options = state.fill?.render_options || {};
    const engine = fillEngineNow();
    const ready = fillEngineReady();
    const rows = window.ClassicCleanOptions.ENGINES.map((key) => {
      const row = engines[key] || {};
      const label = CLEAN_FILL_ENGINE_LABEL[key] || key;
      const isReady = Boolean(row.ready);
      const reason = row.reason || "Not installed.";
      return `<button type="button" class="clean-engine-item" role="menuitemradio"
        data-engine="${esc(key)}"
        aria-checked="${key === engine ? "true" : "false"}"
        ${isReady ? "" : "disabled"}
        aria-label="${esc(isReady ? `${label}, ready` : `${label}, not ready. ${reason}`)}"
        title="${esc(isReady ? CLEAN_FILL_COST[key] : reason)}">
        <span>${esc(label)}</span>
        <span class="clean-engine-state">${isReady ? "Ready" : "Not ready"}</span>
      </button>`;
    }).join("");
    const gpu = options.gpu?.[engine];
    const keyed = Boolean(gpu);
    const onGpu = keyed && gpu.ready && choice.device !== "cpu";
    const follow = options.follow || {};
    const device = keyed ? `
      <p>AI fill on</p>
      <div class="clean-fill-group" role="group" aria-label="Fill device">
        <button type="button" data-fill-device="" aria-pressed="${onGpu ? "true" : "false"}"${gpu.ready ? "" : " disabled"} title="${esc(gpu.ready ? "The GPU is much faster and uses more memory." : (gpu.reason || ""))}">GPU</button>
        <button type="button" data-fill-device="cpu" aria-pressed="${onGpu ? "false" : "true"}">CPU</button>
      </div>` : '<p>This engine has no device choice.</p>';
    const followReady = follow.ready !== false;
    return `<div class="clean-model">
      <span class="clean-model-anchor">
        <button id="clean-model-chip" class="clean-model-chip${ready ? " is-ready" : ""}" type="button"
          aria-haspopup="menu" aria-expanded="false" aria-controls="clean-engine-menu"
          title="${esc(ready ? "Choose the AI fill engine" : (state.fill?.note || "AI fill needs its model pack."))}">
          AI fill · ${ready ? "Ready" : "Not ready"}${cleanIcon("chevron")}
        </button>
        <div id="clean-engine-menu" class="clean-engine-menu" role="menu" aria-label="AI fill engine" hidden>${rows}</div>
      </span>
      <button id="clean-fill-options-open" class="icon-btn" type="button"
        aria-label="Fill options" title="Fill options"
        aria-expanded="false" aria-controls="clean-fill-options">${cleanIcon("sliders")}</button>
      <div id="clean-fill-options" class="clean-fill-popover" role="dialog" aria-label="Fill options" hidden>
        ${device}
        <label class="clean-fill-check" title="${esc(followReady ? "One fill moves with the camera, and real pixels replace it as they come into view." : (follow.reason || ""))}">
          <input id="clean-fill-follow" type="checkbox"${choice.follow && followReady ? " checked" : ""}${followReady ? "" : " disabled"}>
          Follow camera
        </label>
      </div>
    </div>`;
  }

  function closeCleanModelMenus() {
    const chip = $("#clean-model-chip");
    const menu = $("#clean-engine-menu");
    const open = $("#clean-fill-options-open");
    const popover = $("#clean-fill-options");
    if (menu) menu.hidden = true;
    if (chip) chip.setAttribute("aria-expanded", "false");
    if (popover) popover.hidden = true;
    if (open) open.setAttribute("aria-expanded", "false");
  }

  function paintCleanModelMenu() {
    const menu = $("#clean-engine-menu");
    const chip = $("#clean-model-chip");
    if (!menu) return;
    const open = chip?.getAttribute("aria-expanded") === "true";
    menu.hidden = !open;
    if (!open) return;
    const rect = chip.getBoundingClientRect();
    const roomBelow = window.innerHeight - rect.bottom;
    menu.classList.toggle("is-above", roomBelow < 210);
  }

  function toggleCleanEngineMenu(force) {
    const chip = $("#clean-model-chip");
    const menu = $("#clean-engine-menu");
    if (!chip || !menu) return;
    const open = force === undefined ? chip.getAttribute("aria-expanded") !== "true" : Boolean(force);
    closeCleanModelMenus();
    chip.setAttribute("aria-expanded", open ? "true" : "false");
    paintCleanModelMenu();
    if (open) menu.querySelector(".clean-engine-item[aria-checked='true']:not(:disabled), .clean-engine-item:not(:disabled)")?.focus();
  }

  function toggleCleanFillOptions(force) {
    const button = $("#clean-fill-options-open");
    const popover = $("#clean-fill-options");
    if (!button || !popover) return;
    const open = force === undefined ? button.getAttribute("aria-expanded") !== "true" : Boolean(force);
    closeCleanModelMenus();
    button.setAttribute("aria-expanded", open ? "true" : "false");
    popover.hidden = !open;
    if (open) popover.querySelector("button, input")?.focus();
  }

  /** What a big drawn box costs, and the cheaper way when the scan found its text. */
  function bigBoxesHtml() {
    const api = window.ClassicCleanOptions;
    const tracklets = state.textScan?.report?.tracklets;
    return classicCleanLayers().map((layer) => {
      const share = api.bigBoxShare(layer);
      if (!share) return "";
      const lines = api.linesInsideBox(layer, tracklets);
      const count = lines.length === 1 ? "1 line" : `${lines.length} lines`;
      const action = lines.length
        ? `<button class="ghost small" type="button" data-clean-snap="${esc(layer.id)}" title="Tight boxes, each on screen only with its line. Text the scan missed is left as it is.">Clean only the ${count} inside</button>`
        : `<span class="hint">${state.textScan?.report ? "The scan found no text inside this box." : "Scan the video to clean only the text inside."}</span>`;
      return `<div class="clean-big-box"><p class="hint">This box repaints ${share}% of the picture. That is the slowest kind of AI fill, and it can smear what is behind the text.</p>${action}</div>`;
    }).join("");
  }

  /** Swap a big drawn box for tight boxes on the lines the scan found inside it. */
  function snapBoxToLines(id) {
    const api = window.ClassicCleanOptions;
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer) return;
    const lines = api.linesInsideBox(layer, state.textScan?.report?.tracklets);
    if (!lines.length) return;
    const entries = state.textScan?.report?.clean_prefill || [];
    const before = classicCleanLayers().length;
    deleteCleanBox(id);
    for (const line of lines) {
      const entry = entries.find((row) => row.tracklet_id === line.id) || {};
      addCleanFromScan({
        ...entry,
        tracklet_id: line.id,
        kind: entry.kind || line.kind,
        box: entry.box || line.box,
        ranges: api.rangesWithin(line.ranges, layer.ranges),
      }, "fill", fillEngineNow());
    }
    setCleanStatus(`Replaced the box with ${classicCleanLayers().length - before + 1} tight boxes.`);
    renderCleanFill();
  }

  function setFillChoice(patch) {
    state.fillChoice = window.ClassicCleanOptions.normalChoice({ ...fillChoiceNow(), ...patch });
    window.ClassicCleanOptions.saveChoice(window.localStorage, state.fillChoice);
    renderCleanFill();
  }

  function renderCleanFill() {
    if (!dom.cleanFill) return;
    const fill = state.fill;
    if (!fill) {
      dom.cleanFill.hidden = true;
      return;
    }
    dom.cleanFill.hidden = false;
    dom.cleanFill.innerHTML = fillMenuHtml();
    paintCleanModelMenu();
  }

  async function previewFill() {
    if (!state.job) return;
    const sourceScope = state.cleanScope === "source";
    const inPlace = sourceScope || cutCleanActive();
    const bodies = () => ({
      clips: classicPlanClips(),
      clean: cleanPayloadLayers(),
      overlays: state.classicText.overlays.map((layer) => ({ ...layer })),
      effects: state.classicText.effects.map((effect) => ({
        id: effect.id, kind: effect.kind,
        start: Number(effect.start) || 0, end: Number(effect.end) || 0,
      })),
      t: round2(currentCleanTime()),
      aspect: sourceScope ? "source" : state.aspect,
    });
    const button = dom.cleanFill?.querySelector("#clean-fill-preview");
    if (button) {
      button.disabled = true;
      button.textContent = "Filling one frame…";
    }
    setCleanStatus(`Filling one frame with ${state.fill?.engines?.[fillEngineNow()]?.label || "LaMa"}. The first one loads the model, so it takes a moment.`);
    try {
      const payload = await api(`/api/classic/jobs/${state.job.id}/fill/preview`, {
        method: "POST",
        body: JSON.stringify(bodies()),
      });
      if (inPlace) {
        // Clean keeps Before/After on the one frame, not in a second image
        // column: After swaps in this filled JPEG.
        state.classicText.previewSide = "after";
        if (sourceScope) setSourceAspect(payload.width, payload.height);
        if (state.classicText.frame.url) URL.revokeObjectURL(state.classicText.frame.url);
        state.classicText.frame.url = payload.after;
        state.classicText.frame.key = "";
        state.classicText.frame.error = "";
        if (dom.cleanFrame) dom.cleanFrame.src = payload.after;
        setCleanFillNote(0, "After shows the AI fill for this frame. The render uses the same layer.");
      } else {
        state.classicText.fillPreview = payload;
      }
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
    const sourceScope = state.cleanScope === "source";
    if (dom.cleanPreviewTime) {
      dom.cleanPreviewTime.textContent = sourceScope
        ? `Source ${fmtTime(cleanSourceTimeAt(t), 2)}`
        : `Cut ${fmtTime(t, 2)}`;
    }
    if (dom.cleanPreviewMoment) {
      dom.cleanPreviewMoment.textContent = sourceScope
        ? tr("Whole video")
        : (cleanClipTitle(t) || cleanClipLabel(t) || "No moment");
    }
    const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
    const fillLayer = selected && cleanMethodKey(selected) === "fill"
      ? selected
      : classicCleanLayers().find((layer) => cleanMethodKey(layer) === "fill");
    const engine = CLEAN_FILL_ENGINE_LABEL[fillEngineNow()];
    if (dom.cleanPreviewEngine) {
      if (sourceScope) {
        dom.cleanPreviewEngine.textContent = fillLayer
          ? `Engine ${engine}`
          : `Engine ${sourceCleanEngineLabel()}`;
      } else {
        dom.cleanPreviewEngine.textContent = fillLayer
          ? `Engine ${engine}`
          : "Clean preview";
      }
    }
    if (dom.cleanPreviewEta) {
      if (sourceScope) {
        const estimate = state.sourceCleanEstimate?.estimate_seconds;
        dom.cleanPreviewEta.textContent = estimate
          ? `~${formatEstimate(estimate)}`
          : (fillLayer ? "Time shows during the render" : "No fill yet");
      } else if (!fillLayer) {
        dom.cleanPreviewEta.textContent = "No fill yet";
      } else {
        dom.cleanPreviewEta.textContent = "Time shows during the render";
      }
    }
  }

  // The stage frame is the real render minus the fill, which happens in the
  // render. Say that, or an AI fill box looks like a box that does nothing.
  function setCleanFillNote(count, message = "") {
    if (!dom.cleanFillNote) return;
    dom.cleanFillNote.hidden = !count && !message;
    dom.cleanFillNote.textContent = message
      || (count ? "The preview shows the box only. The filled picture appears in the render." : "");
  }

  // ------------------------------------------------------------ the frame

  function cleanFrameBody(clean = cleanPayloadLayers()) {
    // Clean's preview is pixels only: no captions, text overlays, effects or
    // graphics. The render still applies those after the clean stage.
    if (state.cleanScope === "source") {
      return {
        clips: classicPlanClips(),
        clean,
        t: round2(currentCleanTime()),
      };
    }
    return {
      clips: classicPlanClips(),
      clean,
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
    if (state.cleanScope === "source") return "Whole video";
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

  // The bar already shows the clip position and role. The old tooltip put raw
  // OCR or speech analysis into a hover title; diagnostics stay in the detail
  // strip, not in founder-facing copy.
  function cleanClipTitle() {
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
    // The toolbar, the scrub row, the preview controls and the range timeline
    // take the rest. The timeline lives under the frame, so it must be
    // subtracted here or the frame pushes it below the pane.
    const bar = stage.querySelector(".clean-stage-bar");
    const foot = stage.querySelector(".clean-stage-foot");
    const controls = document.querySelector("#clean-preview-controls");
    const timeline = document.querySelector("#clean-timeline-panel");
    const timelineRoom = timeline && !timeline.hidden
      ? (timeline.offsetHeight || 0) + 14
      : 0;
    const chrome = (bar?.offsetHeight || 0) + (foot?.offsetHeight || 0)
      + (controls?.offsetHeight || 0) + timelineRoom + 24;
    const room = Math.max(190, Math.round(height - chrome));
    stage.style.setProperty("--clean-frame-h", `${room}px`);
    const canvas = dom.cleanCanvas;
    if (!canvas) return;
    if (state.cleanScope === "source" && state.sourceAspect) {
      const width = Math.max(2, state.sourceAspect.width);
      const aspect = width / Math.max(2, state.sourceAspect.height);
      const paneWidth = Math.max(190, (pane?.clientWidth || window.innerWidth) - 8);
      let frameHeight = room;
      let frameWidth = frameHeight * aspect;
      if (frameWidth > paneWidth) {
        frameWidth = paneWidth;
        frameHeight = frameWidth / aspect;
      }
      canvas.style.width = `${Math.round(frameWidth)}px`;
      canvas.style.height = `${Math.round(frameHeight)}px`;
    } else {
      canvas.style.width = "";
      canvas.style.height = "";
    }
  }

  function paintCleanStage(options = {}) {
    const stage = dom.cleanStage;
    if (!stage) return;
    const supported = classicTextSupported();
    stage.hidden = !state.job || !state.plan;
    if (!stage.hidden) {
      sizeCleanCanvas();
      const canvas = dom.cleanCanvas;
      const sourceMode = state.cleanScope === "source";
      const aspect = sourceMode ? "source" : (supported ? state.aspect : "9:16");
      canvas.dataset.aspect = aspect;
      canvas.classList.toggle("is-unsupported", !sourceMode && !supported);
      if (sourceMode && state.sourceAspect) {
        canvas.style.aspectRatio = `${state.sourceAspect.width} / ${state.sourceAspect.height}`;
      } else if (!sourceMode) {
        canvas.style.aspectRatio = "";
      }
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
      if (dom.cleanPreviewAi) {
        const ready = fillEngineReady();
        dom.cleanPreviewAi.disabled = !ready;
        if (ready) {
          dom.cleanPreviewAi.title = "Use AI fill for the selected box or the ticked text.";
        } else {
          cleanDiagnostic("Classic AI fill unavailable:", state.fill?.engines?.[fillEngineNow()]?.reason
            || state.fill?.note || "");
          dom.cleanPreviewAi.title = "AI fill needs its model pack. Install it in Setup, or use Blur.";
        }
      }
      dom.cleanCanvas.classList.toggle("is-drawing", state.classicText.drawMode);
    }
    paintCleanBoxes();
    paintCleanPanel(options);
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
    if (state.cleanScope === "source") return CLEAN_FULL_CROP;
    const crops = state.classicText.crops || {};
    const index = cleanSegmentAt(t);
    const own = crops[index];
    if (own) return own;
    const known = Object.keys(crops).length
      ? crops[Object.keys(crops)[Object.keys(crops).length - 1]]
      : null;
    return known || CLEAN_FULL_CROP;
  }

  // A box drawn by hand starts at the playhead and lasts three seconds, inside
  // the clip it was drawn on. Its time can be changed on its row.
  const CLEAN_MANUAL_SECONDS = 3;

  function cleanManualRange(t) {
    const window = cleanClipWindowAt(t);
    if (!window) return null;
    const start = Math.max(window.start, Math.min(window.end, t));
    const end = Math.min(window.end, start + CLEAN_MANUAL_SECONDS);
    return end > start ? { start: round2(start), end: round2(end) } : window;
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

  /** One entry per tight member box at the current time. */
  function cleanScanPartsAt(t, options = {}) {
    const includeAdded = options.includeAdded === true;
    const selected = state.classicText.selectedBar;
    const parts = [];
    for (const row of cleanTimelineRows()) {
      if (row.manual) continue;
      const identity = cleanRowIdentity(row);
      if (row.added && !includeAdded && identity !== selected) continue;
      const members = Array.isArray(row.entryRows) && row.entryRows.length ? row.entryRows : [row];
      for (const member of members) {
        const box = member?.box || row.box;
        if (!box) continue;
        const raw = cleanOverrideFor(row, member) || member.ranges || row.ranges || [];
        const ranges = cleanTimelineMapRanges(raw, row);
        if (raw.length && !ranges.length) continue;
        const active = !ranges.length || ranges.some((range) => (
          t + 1 / 30 > Number(range.start) && t < Number(range.end)
        ));
        if (!active) continue;
        parts.push({
          row,
          member,
          identity,
          box,
          label: CleanTimeline.barLabel(member?.text || member?.text_key || row.text, 0),
          selected: identity === selected,
        });
      }
    }
    return parts;
  }

  function paintCleanBoxes() {
    const overlay = dom.cleanOverlay;
    if (!overlay) return;
    const t = currentCleanTime();
    const crop = cleanCropAt(t);
    const layers = dedupeCleanLayers(classicCleanLayers()).layers;
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
          <span class="clean-box-tag">${selected
            ? esc(CleanTimeline.barLabel(layer.text_key || layer.label || layer.kind, 0))
            : `${esc(cleanMethodLabel(layer))}${layer.hidden ? " · off" : ""}${active ? "" : " · not here"}${offFrame ? " · off frame" : ""}`}</span>
          <span class="clean-handle" data-clean-handle="nw"></span>
          <span class="clean-handle" data-clean-handle="ne"></span>
          <span class="clean-handle" data-clean-handle="sw"></span>
          <span class="clean-handle" data-clean-handle="se"></span>
        </div>`;
    }).join("");
    const selectedRow = state.classicText.selectedBar;
    const scanBoxes = cleanScanPartsAt(t).filter((part) => !part.row.added).map((part) => {
      const box = cleanFrameBox(part.box, crop);
      if (box.w <= 0.0001 || box.h <= 0.0001) return "";
      return `
        <div class="clean-scan-box${part.selected ? " is-selected" : ""}"
             style="left:${(box.x * 100).toFixed(2)}%;top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;height:${(box.h * 100).toFixed(2)}%"
             aria-hidden="true">
          ${part.selected ? `<span class="clean-scan-tag">${esc(part.label)}</span>` : ""}
        </div>`;
    }).join("");
    if (!state.classicText.review.active) overlay.insertAdjacentHTML("beforeend", scanBoxes);
    const focus = state.classicText.focusBox;
    if (focus && !selectedRow && !state.classicText.review.active) {
      const box = cleanFrameBox(focus, crop);
      overlay.insertAdjacentHTML("beforeend", `<div class="clean-focus-box" style="left:${(box.x * 100).toFixed(2)}%;top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;height:${(box.h * 100).toFixed(2)}%" aria-hidden="true"></div>`);
    }
    if (dom.cleanFrameState) {
      const frame = state.classicText.frame;
      let message = "";
      if (state.classicText.drawMode) message = "Drag on the frame to draw a box.";
      else if (frame.busy) message = "Rendering this frame…";
      else if (frame.error) message = cleanShortError(frame.error);
      else if (state.classicText.zeroNote && currentCleanTime() <= 0.05) {
        message = "No text row at 0:00. Scrub the frame or scan again.";
      }
      if (frame.error) cleanDiagnostic("Classic clean frame failed:", frame.error);
      dom.cleanFrameState.textContent = message;
      dom.cleanFrameState.title = "";
      dom.cleanFrameState.hidden = !message;
    }
    if (dom.cleanFrame) dom.cleanFrame.hidden = !state.classicText.frame.url
      || Boolean(state.classicText.review.active);
    updateCleanPreviewMeta();
    paintCleanReviewChrome();
    paintCleanReviewBoxes();
    paintCleanTimeline();
  }

  // ------------------------------------------------- detection check playback
  //
  // Play the real source, or a ready cut render, under one blur box for every
  // found row. This is a check, not a render: no fill, no save and no render
  // ever starts from this control.

  function cleanReviewRecord() {
    for (const quality of ["final", "draft"]) {
      const record = findRender(quality);
      if (record?.status === "ready" && record.url) return record;
    }
    return null;
  }

  function cleanReviewUrl() {
    if (!state.job) return "";
    if (state.cleanScope === "source") {
      return `/api/classic/jobs/${encodeURIComponent(state.job.id)}/source/media`;
    }
    return cutCleanActive() ? (cleanReviewRecord()?.url || "") : "";
  }

  function reviewRangesForRow(row) {
    const raw = Array.isArray(row?.ranges) ? row.ranges : [];
    if (state.cleanScope === "source" || row?.manual) return raw;
    return cleanCutRanges(raw);
  }

  function reviewRowActive(row, t) {
    const raw = Array.isArray(row?.ranges) ? row.ranges : [];
    const ranges = reviewRangesForRow(row);
    if (state.cleanScope === "cut" && !row?.manual && raw.length && !ranges.length) {
      return false;
    }
    if (!ranges.length) return true;
    return ranges.some((range) => (
      t + 1 / 30 > Number(range.start) && t < Number(range.end)
    ));
  }

  function paintCleanReviewBoxes(t = currentCleanTime()) {
    const blur = dom.cleanReviewBlur;
    if (!blur) return;
    if (!state.classicText.review.active) {
      blur.hidden = true;
      if (blur.innerHTML) blur.innerHTML = "";
      delete blur.dataset.reviewKey;
      return;
    }
    // The time readout moves every frame; rebuilding up to 200 boxes can wait
    // for a short beat without the overlay drifting from the video.
    const review = state.classicText.review;
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    if (review.boxesAt && now - review.boxesAt < 55) return;
    review.boxesAt = now;
    blur.hidden = false;
    const crop = cleanCropAt(t);
    const parts = cleanScanPartsAt(t, { includeAdded: true });
    const boxes = parts.map((part) => {
      if (!cleanBoxOnFrame(part.box, crop)) return "";
      const box = cleanFrameBox(part.box, crop);
      if (box.w <= 0.0001 || box.h <= 0.0001) return "";
      return `<span class="clean-review-box${part.selected ? " is-selected" : ""}" style="left:${(box.x * 100).toFixed(2)}%;`
        + `top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;`
        + `height:${(box.h * 100).toFixed(2)}%">`
        + `${part.selected ? `<span class="clean-review-tag">${esc(part.label)}</span>` : ""}</span>`;
    });
    const html = boxes.join("");
    if (html !== (blur.dataset.reviewKey || "")) {
      blur.innerHTML = html;
      blur.dataset.reviewKey = html;
    }
  }

  function updateCleanReviewButton() {
    if (!dom.cleanPreviewPlay) return;
    const review = state.classicText.review;
    const playing = Boolean(review.active && review.playing);
    dom.cleanPreviewPlay.innerHTML = cleanIcon(playing ? "pause" : "play");
    dom.cleanPreviewPlay.setAttribute("aria-pressed", playing ? "true" : "false");
    dom.cleanPreviewPlay.setAttribute("aria-label", tr(
      playing ? "Pause detection check" : "Play detection check",
    ));
    dom.cleanPreviewPlay.title = tr(
      "Play the detection check. Boxes are outlined; this is not the final clean.",
    );
  }

  function cleanHasAfterRender() {
    if (state.cleanScope === "source") return state.sourceClean?.status === "ready";
    return Boolean(cleanReviewRecord());
  }

  function paintCleanReviewChrome() {
    const scopeActive = state.cleanScope === "source" || cutCleanActive();
    const review = state.classicText.review;
    const cutPlayable = !cutCleanActive() || Boolean(cleanReviewRecord());
    if (dom.cleanReviewCopy) {
      dom.cleanReviewCopy.hidden = !scopeActive || Boolean(review.error) || !cutPlayable;
      if (scopeActive) {
        dom.cleanReviewCopy.textContent = tr(
          "Detection check · boxes outlined · not the final clean",
        );
      }
    }
    let note = scopeActive ? (review.error || "") : "";
    if (dom.cleanReviewNote) {
      dom.cleanReviewNote.hidden = !note;
      dom.cleanReviewNote.textContent = note;
    }
    if (dom.cleanPreviewPlay) dom.cleanPreviewPlay.hidden = !scopeActive;
    const hasAfter = cleanHasAfterRender();
    if (dom.cleanPreviewBefore) dom.cleanPreviewBefore.hidden = !hasAfter;
    if (dom.cleanPreviewAfter) dom.cleanPreviewAfter.hidden = !hasAfter;
    updateCleanReviewButton();
  }

  function syncCleanReviewTime() {
    const video = dom.cleanReviewVideo;
    if (!video || !state.classicText.review.active) return;
    const limit = Math.max(0.01, cleanCutTotal() || Number(video.duration) || 0.01);
    const t = clamp(Number(video.currentTime) || 0, 0, limit);
    state.classicText.t = t;
    if (dom.cleanScrub) dom.cleanScrub.value = String(t);
    if (dom.cleanStageTime) dom.cleanStageTime.textContent = `${t.toFixed(1)}s`;
    if (dom.cleanScrubReadout) {
      dom.cleanScrubReadout.textContent = `${t.toFixed(1)} / ${limit.toFixed(1)}s`;
    }
    updateCleanPreviewMeta();
    paintCleanReviewBoxes(t);
    updateCleanPlayhead(t);
  }

  function stopCleanReview(options = {}) {
    const review = state.classicText.review;
    const video = dom.cleanReviewVideo;
    if (review.raf) cancelAnimationFrame(review.raf);
    review.raf = 0;
    if (video) {
      try { video.pause(); } catch (_) { /* the element may not be ready */ }
      // Only a playing check owns the time. Otherwise the video sits at 0.
      if (options.syncTime && review.active) {
        const limit = Math.max(0.01, cleanCutTotal() || Number(video.duration) || 0.01);
        state.classicText.t = clamp(Number(video.currentTime) || 0, 0, limit);
        if (dom.cleanScrub) dom.cleanScrub.value = String(state.classicText.t);
        if (dom.cleanStageTime) dom.cleanStageTime.textContent = `${state.classicText.t.toFixed(1)}s`;
        if (dom.cleanScrubReadout) {
          dom.cleanScrubReadout.textContent = `${state.classicText.t.toFixed(1)} / ${limit.toFixed(1)}s`;
        }
        updateCleanPreviewMeta();
      }
      video.hidden = true;
    }
    review.playing = false;
    review.active = false;
    review.boxesAt = 0;
    dom.cleanCanvas?.classList.remove("is-review-playing");
    if (dom.cleanReviewBlur) {
      dom.cleanReviewBlur.hidden = true;
      dom.cleanReviewBlur.innerHTML = "";
      delete dom.cleanReviewBlur.dataset.reviewKey;
    }
    if (dom.cleanFrame) dom.cleanFrame.hidden = !state.classicText.frame.url;
    updateCleanReviewButton();
  }

  function failCleanReview(message, detail = "") {
    const review = state.classicText.review;
    review.error = message;
    review.key = "";
    review.boxesAt = 0;
    stopCleanReview();
    state.classicText.previewSide = "before";
    setCleanStatus(message);
    if (detail) cleanDiagnostic("Classic clean detection check failed:", detail);
    paintCleanReviewChrome();
    scheduleCleanFrame(true);
  }

  function cleanReviewTick() {
    const review = state.classicText.review;
    if (!review.active || !review.playing) return;
    syncCleanReviewTime();
    review.raf = requestAnimationFrame(cleanReviewTick);
  }

  function seekCleanReview(t) {
    const video = dom.cleanReviewVideo;
    if (!video || !state.classicText.review.active) return;
    const limit = Math.max(0.01, cleanCutTotal() || Number(video.duration) || 0.01);
    const time = clamp(Number(t) || 0, 0, limit);
    try { video.currentTime = time; } catch (_) { /* metadata may still load */ }
    state.classicText.t = time;
    state.classicText.review.boxesAt = 0;
    paintCleanReviewBoxes(time);
  }

  async function startCleanReviewPlayback() {
    if (!state.job) return;
    const review = state.classicText.review;
    const url = cleanReviewUrl();
    if (!url) {
      if (cutCleanActive()) {
        const note = tr("Render a draft once to play this cut.");
        setCleanStatus(note);
        paintCleanReviewChrome();
        paintCutClean();
      }
      return;
    }
    const video = dom.cleanReviewVideo;
    if (!video) return;
    if (state.classicText.frameTimer) clearTimeout(state.classicText.frameTimer);
    state.classicText.frameTimer = null;
    try { state.classicText.frame.controller?.abort(); } catch (_) { /* ignore */ }
    const key = `${state.cleanScope}:${state.job.id}:${url}`;
    review.error = "";
    if (review.key !== key) {
      review.key = key;
      video.src = url;
      try { video.load(); } catch (_) { /* the error event reports it */ }
    }
    const seek = video.ended ? 0 : currentCleanTime();
    review.active = true;
    review.playing = true;
    review.boxesAt = 0;
    dom.cleanCanvas?.classList.add("is-review-playing");
    video.hidden = false;
    if (dom.cleanReviewBlur) dom.cleanReviewBlur.hidden = false;
    if (dom.cleanFrame) dom.cleanFrame.hidden = true;
    video.dataset.reviewSeek = String(seek);
    state.classicText.t = seek;
    if (video.readyState >= 1) {
      try { video.currentTime = seek; } catch (_) { /* keep the browser's time */ }
    }
    paintCleanReviewBoxes(seek);
    paintCleanReviewChrome();
    try {
      await video.play();
    } catch (error) {
      failCleanReview(
        tr("The video could not play here. Showing the still frame."),
        error?.message || "play rejected",
      );
    }
  }

  function toggleCleanReviewPlayback() {
    const review = state.classicText.review;
    const video = dom.cleanReviewVideo;
    if (review.active && video && !video.paused) {
      video.pause();
      return;
    }
    void startCleanReviewPlayback();
  }

  function bindCleanReviewVideo() {
    const video = dom.cleanReviewVideo;
    if (!video) return;
    video.addEventListener("loadedmetadata", () => {
      if (!state.classicText.review.active) return;
      const seek = Number(video.dataset.reviewSeek);
      if (Number.isFinite(seek)) {
        try { video.currentTime = seek; } catch (_) { /* keep the browser's time */ }
      }
      paintCleanReviewBoxes();
    });
    video.addEventListener("play", () => {
      const review = state.classicText.review;
      if (!review.active) return;
      review.playing = true;
      if (!review.raf) review.raf = requestAnimationFrame(cleanReviewTick);
      updateCleanReviewButton();
    });
    video.addEventListener("pause", () => {
      const review = state.classicText.review;
      review.playing = false;
      if (review.raf) cancelAnimationFrame(review.raf);
      review.raf = 0;
      updateCleanReviewButton();
    });
    video.addEventListener("timeupdate", () => {
      if (state.classicText.review.active) syncCleanReviewTime();
    });
    video.addEventListener("seeked", () => {
      if (state.classicText.review.active) syncCleanReviewTime();
    });
    video.addEventListener("ended", () => {
      const review = state.classicText.review;
      review.playing = false;
      if (review.raf) cancelAnimationFrame(review.raf);
      review.raf = 0;
      updateCleanReviewButton();
    });
    video.addEventListener("error", () => {
      if (!state.classicText.review.active) return;
      failCleanReview(
        tr("The video could not play here. Showing the still frame."),
        video.error?.message || `media error ${video.error?.code || ""}`,
      );
    });
  }

  async function refreshCleanFrame(force = false) {
    if (!state.job || !state.plan) return;
    // The detection check owns the frame while its video is up. A still fetch
    // would only hide under the video, and an After frame could start an AI
    // fill. Before/After stops the check first, then asks for the still.
    if (state.classicText.review.active) return;
    const clips = state.plan.clips || [];
    if (!clips.length) return;
    const sourceScope = state.cleanScope === "source";
    const sideMode = sourceScope || cutCleanActive();
    const side = sideMode && state.classicText.previewSide === "after" ? "after" : "before";
    const now = currentCleanTime();
    const activeClean = cleanPayloadLayers();
    const activeFill = sideMode
      ? classicCleanLayers().filter((layer) => (
        !layer.hidden
        && cleanMethodKey(layer) === "fill"
        && cleanVisibleAt(layer, now)
      ))
      : [];
    const visibleClean = sideMode
      ? activeClean.filter((layer) => !layer.hidden && cleanVisibleAt(layer, now))
      : [];
    // Before is the original source: no blur, no fill. After is the same time
    // with the active layers the render will use.
    const body = cleanFrameBody(sideMode && side === "before" ? [] : activeClean);
    const key = sideMode ? `${cleanFrameKey(body)}|${side}` : cleanFrameKey(body);
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
      let sideNote = "";
      if (sideMode) {
        if (side === "after" && activeFill.length) {
          try {
            const payload = await api(`/api/classic/jobs/${state.job.id}/fill/preview`, {
              method: "POST",
              body: JSON.stringify(sourceScope ? { ...body, aspect: "source" } : body),
              signal: controller.signal,
            });
            if (seq !== state.classicText.frame.seq) return;
            if (sourceScope) setSourceAspect(payload.width, payload.height);
            if (state.classicText.frame.url) URL.revokeObjectURL(state.classicText.frame.url);
            state.classicText.frame.url = payload.after;
            state.classicText.frame.key = key;
            state.classicText.frame.error = "";
            if (dom.cleanFrame) dom.cleanFrame.src = payload.after;
            setCleanFillNote(0, "After shows the AI fill for this frame. The render uses the same layer.");
            return;
          } catch (error) {
            if (error && (error.name === "AbortError" || controller.signal.aborted)) throw error;
            sideNote = "The filled frame is unavailable. After shows the source frame with Clean boxes; the render still applies them.";
          }
        } else if (side === "after") {
          sideNote = visibleClean.length
            ? "After shows the blur this render uses."
            : "After matches Before; no Clean layer is active at this time.";
        }
      }
      const config = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      };
      const token = tokenValue();
      if (token) config.headers.Authorization = `Bearer ${token}`;
      const endpoint = sourceScope
        ? `/api/classic/jobs/${encodeURIComponent(state.job.id)}/frame/source`
        : `/api/classic/jobs/${encodeURIComponent(state.job.id)}/frame`;
      const response = await fetch(endpoint, config);
      if (!response.ok) {
        let detail = `Frame answered ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload.detail || payload.message || detail;
        } catch (_) { /* ignore */ }
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      if (sourceScope) {
        setSourceAspect(
          Number(response.headers.get("X-VibeCut-Width")),
          Number(response.headers.get("X-VibeCut-Height")),
        );
        setCleanFillNote(
          Number(response.headers.get("X-VibeCut-Fill")) || 0,
          sideNote || (side === "after"
            ? (visibleClean.length
              ? "After shows the blur this render uses."
              : "After matches Before; no Clean layer is active at this time.")
            : ""),
        );
      } else {
        const crop = cleanCropHeader(response);
        if (crop) {
          state.classicText.crops[crop.index] = crop.box;
          paintCleanBoxes();
        }
        setCleanFillNote(
          Number(response.headers.get("X-VibeCut-Fill")) || 0,
          sideMode ? sideNote : "",
        );
      }
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
      cleanDiagnostic("Classic clean frame failed:", error.message);
      state.classicText.frame.error = "The frame did not render. Retry Refresh; the Clean boxes are unchanged.";
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
  // whole tail in the console. No tooltip carries the raw engine text.
  function cleanShortError(message) {
    const lines = String(message || "").split("\n").map((line) => line.trim()).filter(Boolean);
    const first = lines[0] || "The frame did not render.";
    const more = lines.length > 1 ? ` (${lines.length - 1} more lines)` : "";
    return first.length > 140 ? `${first.slice(0, 137)}…${more}` : `${first}${more}`;
  }

  function cleanDiagnostic(label, value) {
    const raw = String(value || "").trim();
    const key = `${label}\n${raw}`;
    if (raw && !diagnosticsLogged.has(key)) {
      diagnosticsLogged.add(key);
      console.warn(label, raw);
    }
    return raw;
  }

  // Visible copy names the problem and the recovery. Raw paths, ffmpeg tails
  // and model file names stay in the console where a founder can share them.
  function plainCleanError(value) {
    const raw = String(value || "");
    if (/clean file is missing/i.test(raw)) {
      return "The clean file is missing. Render it again; no Download is offered.";
    }
    if (/no readable duration|has no readable duration/i.test(raw)) {
      return "This source has no readable duration. Choose another file.";
    }
    if (/no clean boxes/i.test(raw)) {
      return "No Clean boxes to render. Draw a box or tick a text row.";
    }
    if (/crop guard/i.test(raw)) {
      return "Crop guard is not available on the whole video. Use Blur or AI fill.";
    }
    if (/fill_running|already running/i.test(raw)) {
      return "A fill is already running. Wait for it or cancel it, then retry.";
    }
    if (/model|not installed|model pack/i.test(raw)) {
      return "The clean model is missing. Install it in Setup, or choose Blur, then retry.";
    }
    if (/even width|H\.264|[Oo]dd (width|height)/.test(raw)) {
      return "This file size cannot be encoded. Use an even-size source, then retry.";
    }
    if (/cancel/i.test(raw)) return "The clean was cancelled.";
    return "The clean did not finish. Retry; no partial file is kept.";
  }

  function plainRenderError(value) {
    const raw = String(value || "");
    if (/model|not installed|fill model|model pack/i.test(raw)) {
      return "The fill model is missing. Install it in Setup, or use Blur, then retry.";
    }
    if (/missing scene|scene .* does not exist/i.test(raw)) {
      return "The cut changed while rendering. Render it again.";
    }
    if (/even width|H\.264|[Oo]dd (width|height)/.test(raw)) {
      return "This file size cannot be encoded. Use an even-size source, then retry.";
    }
    if (/cancel/i.test(raw)) return "The render was cancelled.";
    return "The render did not finish. Retry; no partial file is kept.";
  }

  function plainJobError(value) {
    const raw = String(value || "");
    if (/cancel/i.test(raw)) return "The job was cancelled.";
    if (/ffmpeg is not installed|not on PATH/i.test(raw)) {
      return "ffmpeg is missing. Install ffmpeg, then retry.";
    }
    if (/format is not available|requested format/i.test(raw)) {
      return "That video format is not available. Choose another format or link.";
    }
    if (/private|unavailable|not available|sign in|log in/i.test(raw)) {
      return "That video is not available. Check the link or sign in, then retry.";
    }
    if (/unsupported|invalid format/i.test(raw)) {
      return "This video format is not supported. Use another file or link.";
    }
    if (/download|yt-dlp|network/i.test(raw)) {
      return "The video could not be downloaded. Check the link and retry.";
    }
    if (/model|not installed|missing/i.test(raw)) {
      return "The model is missing. Open Setup, then retry.";
    }
    if (/vision|ocr|text/i.test(raw)) return "The text scan failed. Retry the scan.";
    return "The job stopped before it finished. Open it and retry.";
  }

  function cleanFirstTextTime() {
    let first = null;
    let any = false;
    for (const row of cleanScanRows()) {
      if (row.manual || row.added) continue;
      any = true;
      // A row without ranges covers the whole video. Prefer a real timed row,
      // otherwise a logo at 0:00 would hide the subtitle that starts later.
      if (!Array.isArray(row.ranges) || !row.ranges.length) continue;
      const value = state.cleanScope === "source"
        ? Number(row.ranges[0].start)
        : cleanRowCutStart(row);
      if (value === null || value === undefined) continue;
      const start = Number(value);
      if (!Number.isFinite(start) || start < 0) continue;
      if (first === null || start < first) first = start;
    }
    if (first === null && any) return 0;
    return first;
  }

  // One-shot on entering Clean. A row at or near the first frame means there
  // is no fade to explain; a later row moves the playhead to that picture.
  function openCleanAtFirstText() {
    if (state.classicText.openedAtFirstText) return false;
    state.classicText.openedAtFirstText = true;
    const start = cleanFirstTextTime();
    if (start === null) {
      state.classicText.zeroNote = currentCleanTime() <= 0.05;
      return false;
    }
    state.classicText.zeroNote = false;
    if (start > 0.05 && currentCleanTime() <= 0.05) {
      state.classicText.t = start;
      return true;
    }
    return false;
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
    return foundTextKey(value);
  }

  function cleanBoxesMeet(a, b) {
    return sameArea(a, b);
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
    return mergeCleanRangeList(out);
  }

  // Map source-time ranges onto the cut timeline. Source Clean has one clip
  // that starts at 0, so the mapping is the identity there; a cut needs it to
  // answer "is this text on screen in this cut?".
  function cleanCutRanges(ranges) {
    const clips = state.plan?.clips || [];
    const mapped = [];
    let cursor = 0;
    for (const clip of clips) {
      const clipStart = Number(clip.start) || 0;
      const clipEnd = clip.end !== undefined && clip.end !== null
        ? Number(clip.end)
        : clipStart + (Number(clip.dur) || 0);
      const span = Math.max(0, clipEnd - clipStart);
      for (const range of ranges || []) {
        const start = Math.max(Number(range.start) || 0, clipStart);
        const end = Math.min(Number(range.end) || 0, clipEnd);
        if (end > start + 1e-6) {
          mapped.push({
            start: cursor + (start - clipStart),
            end: cursor + (end - clipStart),
          });
        }
      }
      cursor += span;
    }
    mapped.sort((a, b) => a.start - b.start);
    return mapped;
  }

  // One row per distinct text. The scan can read the same words in the same
  // area as separate tracklets, and subtitles are a new tracklet per line, so
  // mergeFoundEntries joins them into one stable row. Drawn boxes are rows too.
  function scanLayerMatchesRow(layer, row) {
    if (!layer || layer.source !== "scan" || !row) return false;
    if (!sameArea(layer.box, row.box)) return false;
    const id = String(layer.tracklet_id || "").trim();
    if (id && (row.tracklet_ids || []).includes(id)) return true;
    if (row.kind === "subtitle" && layer.tracklet_kind === "subtitle") return true;
    return Boolean(row.text_key && layer.text_key
      && cleanTextKey(layer.text_key) === cleanTextKey(row.text_key));
  }

  // A row can hold several ranges. Every interval takes part in lane packing,
  // so a row with a second range later in the cut cannot sit on a neighbour.
  function cleanRowLaneIntervals(row) {
    const raw = Array.isArray(row?.ranges) ? row.ranges : [];
    const mapped = state.cleanScope === "cut" && !row?.manual
      ? cleanCutRanges(raw)
      : raw;
    if (mapped.length) return mapped;
    if (raw.length && state.cleanScope === "cut" && !row?.manual) return [];
    return [{ start: 0, end: Math.max(0.1, cleanCutTotal()) }];
  }

  function assignCleanLanes(rows) {
    const lanes = [];
    for (const row of rows) {
      const intervals = cleanRowLaneIntervals(row);
      let lane = 0;
      while (lane < lanes.length && intervals.some((item) => (
        lanes[lane].some((other) => (
          Math.min(Number(item.end), Number(other.end))
          - Math.max(Number(item.start), Number(other.start)) > 1e-6
        ))
      ))) lane += 1;
      if (!lanes[lane]) lanes[lane] = [];
      lanes[lane].push(...intervals);
      row.lane = lane;
    }
  }

  function cleanScanRows() {
    const rows = mergeFoundEntries(cleanScanEntries()).map((entry) => {
      const text = String(entry.text || entry.text_key || "").trim()
        || String(entry.kind || "Text");
      const ids = Array.isArray(entry.ids) ? entry.ids.slice() : [];
      return {
        key: foundTextKey(text),
        text,
        box: entry.box,
        kind: entry.kind || "text",
        confidence: Number(entry.confidence) || 0,
        ranges: cleanRowRanges([{ ranges: entry.ranges || [] }]),
        entryRows: Array.isArray(entry.members) ? entry.members : [entry],
        entry,
        tracklet_id: entry.tracklet_id || ids[0] || "",
        tracklet_ids: ids,
        text_key: entry.text_key || text,
        identity: `scan:${ids.slice().sort().join("+")}`,
        lines: Math.max(1, Number(entry.lines) || 1),
        method: state.classicText.foundMethod || "fill",
        manual: false,
        added: false,
      };
    });
    for (const layer of classicCleanLayers()) {
      if (layer.source !== "manual") continue;
      rows.push({
        key: `manual:${layer.id}`,
        text: layer.label || "Drawn box",
        box: layer.box,
        kind: layer.kind || "manual",
        confidence: 1,
        ranges: cleanRowRanges([{ ranges: layer.ranges || [] }]),
        entryRows: [],
        entry: null,
        method: cleanMethodKey(layer),
        manual: true,
        added: true,
        layer_id: layer.id,
      });
    }
    for (const row of rows) {
      if (row.manual) continue;
      const matching = classicCleanLayers().filter((layer) => (
        scanLayerMatchesRow(layer, row)
      ));
      row.added = matching.length > 0;
      row.hidden = matching.length > 0 && matching.every((layer) => Boolean(layer.hidden));
      const members = Array.isArray(row.entryRows) && row.entryRows.length ? row.entryRows : [];
      if (members.length) {
        const overridden = members.some((member) => cleanOverrideFor(row, member));
        if (overridden) {
          row.ranges = cleanRowRanges(members.map((member) => ({
            ranges: cleanOverrideFor(row, member) || member.ranges || [],
          })));
        }
      }
    }
    rows.sort((a, b) => {
      const at = a.ranges[0]?.start ?? Number.MAX_SAFE_INTEGER;
      const bt = b.ranges[0]?.start ?? Number.MAX_SAFE_INTEGER;
      if (at !== bt) return at - bt;
      return String(a.kind).localeCompare(String(b.kind));
    });
    assignCleanLanes(rows);
    return rows;
  }

  function roundedBox(axis, value) {
    const number = Number(value) || 0;
    return Math.round(number * 10000) / 10000;
  }

  function cleanRowIdentity(row) {
    if (!row) return "";
    if (row.manual) {
      return `manual:${row.layer_id || String(row.key || "").replace(/^manual:/, "")}`;
    }
    if (row.identity) return row.identity;
    if (row.tracklet_id) return `tracklet:${row.tracklet_id}`;
    const text = cleanTextKey(row.text_key || row.text || String(row.key || "").replace(/^manual:/, ""));
    const box = row.box || {};
    const rect = ["x", "y", "w", "h"].map((axis) => roundedBox(axis, box[axis])).join(",");
    return `text:${text}|${rect}`;
  }

  function tickHash(value) {
    let hash = 2166136261;
    const text = String(value || "");
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(36);
  }

  function cleanTickStorageKey(report = state.textScan?.report) {
    if (!state.job) return "";
    const cutKey = classicCutKey(classicPlanClips());
    if (!cutKey) return "";
    return `classic-clean-ticks:${state.job.id}:${state.cleanScope}:${cutKey}:${tickHash(textScanReportKey(report))}`;
  }

  function loadStoredFoundTicks() {
    const key = cleanTickStorageKey();
    if (!key) return null;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.ticked)) return null;
      return {
        ticked: parsed.ticked.map(String),
        seen: Array.isArray(parsed.seen) ? parsed.seen.map(String) : [],
      };
    } catch (_) {
      return null;
    }
  }

  function saveFoundTicks() {
    const key = cleanTickStorageKey();
    if (!key) return;
    const rows = cleanScanRows().filter((row) => !row.manual && !row.added);
    const seen = rows.map((row) => cleanRowIdentity(row));
    const live = new Set(seen);
    const ticked = Array.from(state.classicText.foundTicks)
      .filter((identity) => live.has(identity));
    try {
      localStorage.setItem(key, JSON.stringify({ ticked, seen }));
      state.classicText.tickStoreKey = key;
    } catch (_) { /* storage may be unavailable */ }
  }

  function clearStoredFoundTicks(key = state.classicText.tickStoreKey) {
    if (!key) return;
    try { localStorage.removeItem(key); } catch (_) { /* ignore */ }
    if (state.classicText.tickStoreKey === key) state.classicText.tickStoreKey = "";
  }

  function applyStoredFoundTicks(rows, options = {}) {
    const sourceScope = Boolean(options.source);
    const stored = loadStoredFoundTicks();
    const actionable = rows.filter((row) => {
      if (row.manual || row.added) return false;
      if (sourceScope) return sourceInsideRow(row);
      return cleanRowCutStart(row) !== null;
    });
    const live = new Set(actionable.map((row) => cleanRowIdentity(row)));
    const ticks = new Set();
    const seen = new Set(stored?.seen || []);
    for (const identity of stored?.ticked || []) {
      if (live.has(identity)) ticks.add(identity);
    }
    for (const row of actionable) {
      const identity = cleanRowIdentity(row);
      if (seen.has(identity)) continue;
      if (Number(row.confidence) < SOURCE_CONFIDENCE_MIN) continue;
      ticks.add(identity);
    }
    state.classicText.foundTicks = ticks;
    state.classicText.foundTicksInit = true;
    saveFoundTicks();
    renderCleanFound();
  }

  function fillChoiceNow() {
    if (!state.fillChoice) state.fillChoice = window.ClassicCleanOptions.loadChoice(window.localStorage);
    return state.fillChoice;
  }

  /** The chosen engine when ready, else the first ready engine, else LaMa. */
  function fillEngineNow() {
    const engines = state.fill?.engines || {};
    const chosen = fillChoiceNow().engine;
    if (engines[chosen]?.ready) return chosen;
    return window.ClassicCleanOptions.ENGINES.find((key) => engines[key]?.ready) || "lama";
  }

  function fillRequestFields() {
    return window.ClassicCleanOptions.requestFields({ ...fillChoiceNow(), engine: fillEngineNow() });
  }

  function fillEngineReady() {
    return Boolean(state.fill?.available && state.fill?.engines?.[fillEngineNow()]?.ready);
  }

  function cleanRowMethod(row) {
    let method = CLEAN_METHODS[row.method] ? row.method : (state.classicText.foundMethod || "fill");
    if (method === "fill" && !fillEngineReady()) method = "blur";
    return method;
  }

  function cleanMethodForTicks() {
    let method = state.classicText.foundMethod || "fill";
    if (method === "fill" && !fillEngineReady()) method = "blur";
    return CLEAN_METHODS[method] ? method : "blur";
  }

  function cleanEstimatePayload(rows, ticks, method) {
    const layers = [];
    for (const index of ticks) {
      const row = rows[index];
      if (!row) continue;
      const members = row.manual
        ? [row]
        : (Array.isArray(row.entryRows) && row.entryRows.length ? row.entryRows : [row.entry]);
      for (const member of members) {
        if (!member) continue;
        const ranges = cleanOverrideFor(row, member) || member.ranges || row.ranges || [];
        layers.push({
          id: `preview${layers.length + 1}`,
          method,
          box: member.box || row.box,
          ranges,
          label: member.kind || row.kind || "text",
          kind: member.kind || row.kind || "text",
          tracklet_id: member.tracklet_id || row.tracklet_id || undefined,
          tracklet_kind: member.kind || row.kind || undefined,
          text_key: member.text_key || member.text || row.text_key || row.text || "",
          ...(member.fill_keys !== undefined ? { fill_keys: member.fill_keys } : {}),
          ...(method === "fill" ? { engine: fillEngineNow() } : {}),
        });
      }
    }
    return layers;
  }

  function cleanThumbStyle(box) {
    const w = Math.max(0.05, Number(box && box.w) || 0.2);
    const h = Math.max(0.05, Number(box && box.h) || 0.2);
    const x = clamp(Number(box && box.x) || 0, 0, 1);
    const y = clamp(Number(box && box.y) || 0, 0, 1);
    const size = 100 / w;
    const posX = w >= 1 ? 0 : (x / (1 - w)) * 100;
    const posY = h >= 1 ? 0 : (y / (1 - h)) * 100;
    return `background-size:${size.toFixed(1)}% ${(100 / h).toFixed(1)}%;`
      + `background-position:${posX.toFixed(1)}% ${posY.toFixed(1)}%`;
  }

  function cleanRowCutStart(row) {
    if (!row) return null;
    if (row.manual) return row.ranges.length ? row.ranges[0].start : 0;
    if (!row.ranges.length) return 0;
    const mapped = cleanCutRanges(row.ranges);
    return mapped.length ? mapped[0].start : null;
  }

  // Scan prefill ranges are source time; a drawn row already stores cut time.
  // The rail shows what the founder sees: cut time on a cut, source time on a
  // whole video.
  function cleanRowDisplayRanges(row) {
    if (!row) return [];
    if (state.cleanScope === "source" || row.manual) return row.ranges || [];
    return cleanCutRanges(row.ranges);
  }

  function cleanRowTimeLabel(row) {
    const ranges = cleanRowDisplayRanges(row);
    if (ranges.length) {
      return `${fmtTime(ranges[0].start, 1)} – ${fmtTime(ranges[ranges.length - 1].end, 1)}`;
    }
    if ((row.ranges || []).length) return "—";
    return state.cleanScope === "source" ? "whole video" : "whole cut";
  }

  // ------------------------------------------------------------ clean timeline
  //
  // One bar is one tight member range. A grouped row keeps one lane, and every
  // member keeps its own box and time. Source Clean reads source time; Cut
  // Clean maps the same ranges to cut time.

  function cleanWorkspaceActive() {
    return state.cleanScope === "source" || cutCleanActive();
  }

  function cleanTimelineTotal() {
    return Math.max(0.1, Number(cleanCutTotal()) || 0.1);
  }

  function cleanTimelineMapRanges(ranges, row) {
    if (state.cleanScope === "cut" && !row?.manual) return cleanCutRanges(ranges);
    return CleanTimeline.normalizeRanges(ranges);
  }

  function cleanDisplayToSourceRange(row, range) {
    if (state.cleanScope !== "cut" || row?.manual) return range;
    return {
      start: cleanSourceTimeAt(Number(range.start) || 0),
      end: cleanSourceTimeAt(Number(range.end) || 0),
    };
  }

  function cleanOverrideKey(row, member) {
    return `${cleanRowIdentity(row)}|${String(member?.tracklet_id || "")}`;
  }

  function cleanOverrideFor(row, member) {
    const key = cleanOverrideKey(row, member);
    const stored = state.classicText.rangeOverrides[key];
    return Array.isArray(stored) ? stored : null;
  }

  function setCleanOverride(row, member, ranges) {
    const key = cleanOverrideKey(row, member);
    if (ranges && ranges.length) state.classicText.rangeOverrides[key] = ranges;
    else delete state.classicText.rangeOverrides[key];
  }

  function cleanTimelineRows() {
    return cleanScanRows().filter((row) => (
      state.cleanScope === "source" || row.manual || cleanRowCutStart(row) !== null
    ));
  }

  function cleanTimelineBars(rows = cleanTimelineRows()) {
    return CleanTimeline.buildBars(rows, {
      total: cleanTimelineTotal(),
      identity: cleanRowIdentity,
      mapRanges: cleanTimelineMapRanges,
      overrideFor: cleanOverrideFor,
      labelFor: (member, index, row) => CleanTimeline.barLabel(
        member?.text || member?.text_key || row?.text,
        index,
      ),
    });
  }

  function updateCleanPlayhead(t = currentCleanTime()) {
    if (!dom.cleanPlayhead || !dom.cleanLanes) return;
    const total = cleanTimelineTotal();
    const time = clamp(Number(t) || 0, 0, total);
    const left = dom.cleanLanes.offsetLeft + (time / total) * dom.cleanLanes.offsetWidth;
    dom.cleanPlayhead.style.left = `${left}px`;
  }

  function paintCleanRuler(total) {
    if (!dom.cleanRuler) return;
    const ticks = CleanTimeline.rulerTicks(total, 6);
    dom.cleanRuler.innerHTML = ticks.map((tick) => `
      <span class="clean-ruler-tick" style="left:${tick.left.toFixed(3)}%">${esc(fmtTime(tick.time, total < 60 ? 1 : 0))}</span>`).join("");
  }

  function paintCleanTimeline() {
    if (!dom.cleanTimelinePanel || !dom.cleanLanes) return;
    const active = Boolean(state.job && state.plan) && cleanWorkspaceActive();
    dom.cleanTimelinePanel.hidden = !active;
    if (!active) return;
    const total = cleanTimelineTotal();
    const rows = cleanTimelineRows();
    const bars = cleanTimelineBars(rows);
    const selected = state.classicText.selectedBar;
    const ticks = state.classicText.foundTicks;
    if (dom.cleanTimelineTotal) dom.cleanTimelineTotal.textContent = fmtTime(total, 1);
    if (dom.cleanTimelineCount) {
      dom.cleanTimelineCount.textContent = `${bars.length} bar${bars.length === 1 ? "" : "s"}`;
    }
    paintCleanRuler(total);
    const laneCount = Math.max(1, rows.reduce((max, row) => Math.max(max, Number(row.lane) || 0), 0) + 1);
    const lanes = Array.from({ length: laneCount }, () => []);
    for (const bar of bars) {
      const lane = clamp(bar.lane, 0, laneCount - 1);
      lanes[lane].push(bar);
    }
    const rowByIdentity = new Map(rows.map((row) => [cleanRowIdentity(row), row]));
    dom.cleanLanes.innerHTML = lanes.map((laneBars, laneIndex) => `
      <div class="clean-lane" data-clean-lane="${laneIndex}">
        ${laneBars.map((bar) => {
          const row = rowByIdentity.get(bar.rowIdentity);
          const isTicked = Boolean(row && (row.added || ticks.has(bar.rowIdentity)));
          const isSelected = bar.rowIdentity === selected;
          return `<div class="clean-bar${bar.manual ? " is-manual" : ""}${isSelected ? " is-selected" : ""}${row && !row.added && !isTicked ? " is-unticked" : ""}"
            role="button" tabindex="0"
            data-clean-bar="${esc(bar.id)}"
            data-bar-row="${esc(bar.rowIdentity)}"
            data-bar-member="${esc(bar.memberId)}"
            data-bar-start="${bar.start}"
            data-bar-end="${bar.end}"
            data-bar-override="${esc(bar.overrideKey)}"
            aria-label="${esc(bar.label)} ${esc(fmtTime(bar.start, 1))} to ${esc(fmtTime(bar.end, 1))}"
            title="${esc(bar.label)} · ${esc(fmtTime(bar.start, 1))} – ${esc(fmtTime(bar.end, 1))}${row && !row.added && !row.manual ? " · double-click to include or leave out" : ""}"
            style="left:${bar.left.toFixed(3)}%;width:${bar.width.toFixed(3)}%">
            <span class="clean-bar-label">${esc(bar.label)}</span>
            <span class="clean-bar-trim" data-trim="start" aria-hidden="true"></span>
            <span class="clean-bar-trim" data-trim="end" aria-hidden="true"></span>
          </div>`;
        }).join("")}
      </div>`).join("");
    if (dom.cleanTimelineEmpty) dom.cleanTimelineEmpty.hidden = bars.length > 0;
    updateCleanPlayhead();
    sizeCleanCanvas();
  }

  function cleanTimelineTimeAt(clientX) {
    const node = dom.cleanLanes || dom.cleanTimeline;
    if (!node) return 0;
    const rect = node.getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / Math.max(1, rect.width), 0, 1);
    return ratio * cleanTimelineTotal();
  }

  function cleanSeek(t) {
    const total = cleanTimelineTotal();
    const time = clamp(Number(t) || 0, 0, total);
    state.classicText.t = time;
    state.classicText.zeroNote = false;
    if (state.classicText.review.active) seekCleanReview(time);
    if (dom.cleanScrub) dom.cleanScrub.value = String(time);
    if (dom.cleanStageTime) dom.cleanStageTime.textContent = `${time.toFixed(1)}s`;
    if (dom.cleanScrubReadout) {
      dom.cleanScrubReadout.textContent = `${time.toFixed(1)} / ${total.toFixed(1)}s`;
    }
    paintCleanBoxes();
    updateCleanPlayhead(time);
    scheduleCleanFrame();
  }

  function selectCleanBar(rowIdentity, options = {}) {
    const row = cleanTimelineRows().find((item) => cleanRowIdentity(item) === rowIdentity);
    if (!row) return;
    state.classicText.selectedBar = rowIdentity;
    const member = options.memberId
      ? (row.entryRows || []).find((item) => String(item.tracklet_id || "") === options.memberId)
      : null;
    const start = Number(options.start);
    if (Number.isFinite(start)) cleanSeek(start);
    const layers = classicCleanLayers();
    const match = row.manual
      ? layers.find((layer) => layer.id === row.layer_id)
      : layers.find((layer) => (
        layer.source === "scan"
        && (!member || String(layer.tracklet_id || "") === String(member.tracklet_id || ""))
        && scanLayerMatchesRow(layer, row)
      ));
    state.classicText.selection = match ? match.id : "";
    paintCleanStage({ rows: false });
    setCleanStatus(`${CleanTimeline.barLabel(member?.text || row.text, 0)} · ${fmtTime(row.ranges?.[0]?.start ?? 0, 1)}`);
  }

  function cleanBarEntry(barId) {
    const rows = cleanTimelineRows();
    for (const row of rows) {
      const identity = cleanRowIdentity(row);
      const members = row.manual ? [{ ...row, tracklet_id: "" }] : (row.entryRows || [row]);
      for (const member of members) {
        if (`${identity}|${String(member?.tracklet_id || "")}|${barId.split("|").pop()}` !== barId) continue;
        return { row, member, identity };
      }
    }
    return null;
  }

  /** Replace one member range, keeping every other member tight and separate. */
  function setCleanBarRange(entry, rangeIndex, range) {
    if (!entry || !range) return;
    const { row, member } = entry;
    const layers = classicCleanLayers().filter((layer) => {
      if (layer.source !== "scan") return row.manual && layer.id === row.layer_id;
      if (!member?.tracklet_id) return false;
      return String(layer.tracklet_id || "") === String(member.tracklet_id || "");
    });
    const override = cleanOverrideFor(row, member);
    const fromLayer = !override && layers[0]?.ranges?.length
      ? layers[0].ranges.map((item) => (state.cleanScope === "cut" && !row.manual
        ? { start: cleanSourceTimeAt(item.start), end: cleanSourceTimeAt(item.end) }
        : { ...item }))
      : null;
    const raw = CleanTimeline.normalizeRanges(fromLayer || override || member.ranges || row.ranges || []);
    const next = raw.map((item, index) => (index === rangeIndex ? range : item));
    if (!next.length) next.push(range);
    if (layers.length) {
      const layerRanges = state.cleanScope === "cut" && !row.manual
        ? cleanCutRanges(next)
        : next;
      for (const layer of layers) layer.ranges = layerRanges.map((item) => ({ ...item }));
      state.classicText.rangeOverrides[cleanOverrideKey(row, member)] = next.map((item) => ({ ...item }));
      saveClassicText();
    } else {
      setCleanOverride(row, member, next);
    }
    paintCleanBoxes();
  }

  function paintCleanRulerAndBarDrag() {
    const timeline = dom.cleanTimeline;
    if (!timeline || timeline.dataset.bound === "1") return;
    timeline.dataset.bound = "1";
    let drag = null;
    const onMove = (event) => {
      if (!drag) return;
      if (drag.kind === "seek") {
        cleanSeek(cleanTimelineTimeAt(event.clientX));
        return;
      }
      const delta = cleanTimelineTimeAt(event.clientX) - drag.originTime;
      const total = cleanTimelineTotal();
      const entry = cleanBarEntry(drag.barId);
      if (!entry) return;
      const base = { start: drag.start, end: drag.end };
      const range = drag.kind === "trim"
        ? CleanTimeline.trimRange(base, drag.side, (drag.side === "start" ? drag.start : drag.end) + delta, total)
        : CleanTimeline.moveRange(base, delta, total);
      setCleanBarRange(entry, drag.rangeIndex, cleanDisplayToSourceRange(entry.row, range));
    };
    const onUp = () => {
      if (!drag) return;
      const finished = drag;
      drag = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (finished.kind !== "seek") {
        saveClassicText();
        scheduleCleanFrame();
      }
    };
    timeline.addEventListener("dblclick", (event) => {
      const bar = event.target.closest("[data-clean-bar]");
      if (!bar) return;
      const row = cleanTimelineRows().find((item) => cleanRowIdentity(item) === bar.dataset.barRow);
      if (!row || row.added || row.manual) return;
      event.preventDefault();
      const identity = cleanRowIdentity(row);
      if (state.classicText.foundTicks.has(identity)) state.classicText.foundTicks.delete(identity);
      else state.classicText.foundTicks.add(identity);
      saveFoundTicks();
      paintCleanStage({ rows: false });
      setCleanStatus(state.classicText.foundTicks.has(identity)
        ? "Bar included in Clean."
        : "Bar left out of Clean. Double-click to include it again.");
    });
    timeline.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const trim = event.target.closest("[data-trim]");
      const bar = event.target.closest("[data-clean-bar]");
      if (bar) {
        event.preventDefault();
        const entry = cleanBarEntry(bar.dataset.cleanBar);
        if (!entry) return;
        const start = Number(bar.dataset.barStart) || 0;
        const end = Number(bar.dataset.barEnd) || 0;
        selectCleanBar(bar.dataset.barRow, {
          memberId: bar.dataset.barMember || "",
          start: trim?.dataset.trim === "end" ? Math.max(0, end - 0.05) : start,
        });
        const rangeIndex = Number(bar.dataset.cleanBar.split("|").pop()) || 0;
        const raw = CleanTimeline.rangesFor(entry.row, entry.member, cleanOverrideFor(entry.row, entry.member));
        const range = raw[rangeIndex] || { start, end };
        drag = {
          kind: trim ? "trim" : "move",
          side: trim?.dataset.trim || "",
          barId: bar.dataset.cleanBar,
          range,
          rangeIndex,
          start,
          end,
          originTime: cleanTimelineTimeAt(event.clientX),
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp, { once: true });
        return;
      }
      if (event.target.closest(".clean-lane, #clean-ruler, .clean-timeline")) {
        event.preventDefault();
        cleanSeek(cleanTimelineTimeAt(event.clientX));
        drag = { kind: "seek" };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp, { once: true });
      }
    });
  }

  function startCleanAddRange() {
    if (!cleanWorkspaceActive()) return;
    stopCleanReview({ syncTime: true });
    state.classicText.drawMode = true;
    state.classicText.brushMode = false;
    setCleanStatus("Draw the box on the frame. It starts at the playhead.");
    paintCleanStage();
    scrollIntoViewSafe(dom.cleanCanvas, { behavior: "smooth", block: "nearest" });
  }

  function toggleCleanExpand() {
    const canvas = dom.cleanCanvas;
    if (!canvas) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
      return;
    }
    if (canvas.requestFullscreen) {
      canvas.requestFullscreen().catch(() => canvas.classList.toggle("is-expanded"));
    } else {
      canvas.classList.toggle("is-expanded");
    }
  }

  function cleanSceneAtCut(t) {
    const clips = state.plan?.clips || [];
    if (!clips.length) return null;
    const index = cleanSegmentAt(t);
    return sceneById(clips[index]?.scene);
  }

  function focusCleanRow(row) {
    if (!row) return;
    const sourceMode = state.cleanScope === "source";
    const cutStart = cleanRowCutStart(row);
    if (cutStart === null) {
      setCleanStatus("Not in this cut. Add the moment to Smart Cut first.");
      return;
    }
    const scene = sourceMode ? null : cleanSceneAtCut(cutStart);
    // Clean is a focus mode: a click seeks and highlights the box on the frame.
    // The moment drawer would cover that frame (and the detail strip on a
    // double-click); Edit keeps the drawer.
    if (scene && !cutCleanActive()) openDrawer(scene.id);
    state.classicText.t = Math.max(0, cutStart - 0.5);
    state.classicText.zeroNote = false;
    state.classicText.focusBox = row.box;
    if (state.classicText.review.active) seekCleanReview(state.classicText.t);
    if (row.layer_id && classicCleanLayers().some((layer) => layer.id === row.layer_id)) {
      state.classicText.selection = row.layer_id;
    }
    if (dom.cleanScrub) dom.cleanScrub.value = String(state.classicText.t);
    paintCleanStage({ rows: false });
    scheduleCleanFrame();
    scrollIntoViewSafe(dom.cleanStage, { behavior: "smooth", block: "nearest" });
    setCleanStatus(scene
      ? `Moment ${scene.id + 1} · ${fmtTime(cutStart, 1)} · ${row.kind}`
      : `${sourceMode ? "Source" : "Cut"} ${fmtTime(cutStart, 1)} · ${row.kind}`);
  }

  function resetSourceConfirmation() {
    if (state.cleanScope !== "source") return;
    state.sourceCleanNeedConfirm = false;
    state.sourceCleanEstimate = null;
  }

  function openCleanDetail(row) {
    if (!row || !dom.cleanDetail) return;
    const sourceScope = state.cleanScope === "source";
    const time = cleanRowTimeLabel(row);
    state.classicText.detailIdentity = cleanRowIdentity(row);
    dom.cleanDetail.hidden = false;
    dom.cleanDetail.innerHTML = `
      <div><strong>${esc(row.text || "Text")}</strong> · ${esc(row.kind || "text")}</div>
      <div>${esc(time)} · ${esc(CLEAN_METHODS[cleanRowMethod(row)].label)}${sourceScope ? ` · ${Math.round((Number(row.confidence) || 0) * 100)}% confidence` : ""}</div>
      <button type="button" data-clean-detail-close>Close details</button>`;
  }

  function renderCleanFound() {
    const panel = dom.cleanFound;
    if (!panel) return;
    const sourceScope = state.cleanScope === "source";
    const rows = cleanScanRows();
    if (!rows.length) {
      panel.hidden = true;
      panel.innerHTML = "";
      if (sourceScope) paintSourceClean();
      return;
    }
    panel.hidden = false;
    const ticks = state.classicText.foundTicks;
    const liveTicks = new Set(rows
      .filter((row) => !row.manual && !row.added)
      .map((row) => cleanRowIdentity(row)));
    for (const identity of Array.from(ticks)) {
      if (!liveTicks.has(identity)) ticks.delete(identity);
    }
    const fill = state.fill || {};
    const methods = [["fill", "AI fill"], ["blur", "Blur"], ["crop", "Crop guard"]]
      .filter(([key]) => key !== "fill" || fillEngineReady())
      .filter(([key]) => !sourceScope || key !== "crop");
    const wanted = state.classicText.foundMethod || "fill";
    const method = methods.some(([key]) => key === wanted) ? wanted : "blur";
    const methodOptions = methods
      .map(([key, label]) => `<option value="${key}"${key === method ? " selected" : ""}>${label}</option>`)
      .join("");
    const lowCount = sourceScope ? sourceLowRows(rows).length : cutCleanLowRows(rows).length;
    const rowsHtml = rows.map((row, index) => {
      const identity = cleanRowIdentity(row);
      const cutStart = cleanRowCutStart(row);
      const outside = !sourceScope && cutStart === null;
      const ticked = !row.manual && !row.added && ticks.has(identity);
      const low = !row.manual && !row.added
        && Number(row.confidence) < SOURCE_CONFIDENCE_MIN
        && (sourceScope || cutStart !== null);
      const scene = sourceScope ? null : cleanSceneAtCut(cutStart ?? 0);
      const thumb = scene ? thumbUrl(scene) : "";
      const time = cleanRowTimeLabel(row);
      return `
        <div class="clean-found-row clean-lane-${Math.min(3, row.lane || 0)}${ticked ? " is-ticked" : ""}${outside ? " is-outside" : ""}${low ? " is-low" : ""}${row.added ? " is-added" : ""}"
             role="listitem" tabindex="0" data-found-index="${index}">
          ${row.manual
            ? '<span class="clean-found-tick-space" aria-hidden="true"></span>'
            : (row.added
              ? `<input type="checkbox" class="clean-found-tick is-cleaned" data-found-tick="${esc(identity)}" checked disabled aria-label="${row.hidden ? "Excluded" : "Already cleaned"}: ${esc(row.text)}">`
              : `<input type="checkbox" class="clean-found-tick" data-found-tick="${esc(identity)}"${ticked ? " checked" : ""} aria-label="Select ${esc(row.text)} for cleaning">`)}
          ${thumb ? `<span class="clean-found-thumb" style="background-image:url('${esc(thumb)}');${cleanThumbStyle(row.box)}" aria-hidden="true"></span>` : '<span class="clean-found-thumb is-empty" aria-hidden="true"></span>'}
          <div class="clean-found-copy">
            <span class="clean-found-time mono">${esc(time)}</span>
            <span class="clean-found-kind">${esc(row.kind)}${sourceScope ? `<span class="clean-found-confidence">${Math.round((Number(row.confidence) || 0) * 100)}%</span>` : ""}</span>
            <span class="clean-found-sample">${esc(row.text)}</span>
            <span class="clean-found-method">${esc(CLEAN_METHODS[cleanRowMethod(row)].label)} · lane ${Number(row.lane) + 1}${row.lines > 1 ? ` · ${row.lines} lines` : ""}${low ? " · review" : ""}${ticked && !row.added ? ' · <b class="clean-found-selected">Selected</b>' : ""}</span>
          </div>
          ${outside ? '<span class="clean-found-blocked">Not in this cut</span>' : ""}
          ${row.manual ? '<span class="clean-found-blocked is-added">drawn</span>' : ""}
          ${row.added && !row.manual ? `<span class="clean-found-blocked is-added">${row.hidden ? "Excluded" : "Already cleaned"}</span>` : ""}
        </div>`;
    }).join("");
    const tickCount = sourceScope
      ? sourceTickedCount(rows, ticks)
      : cutCleanTickedCount(rows, ticks);
    // A scan can finish after Clean opened. The first text-bearing row is then
    // the honest first picture; no paint here, because renderCleanFound runs
    // inside paintCleanStage.
    if (state.classicText.zeroNote) {
      const start = cleanFirstTextTime();
      if (start !== null) {
        state.classicText.zeroNote = false;
        if (start > 0.05 && currentCleanTime() <= 0.05) {
          state.classicText.t = start;
          if (dom.cleanScrub) dom.cleanScrub.value = String(start);
          scheduleCleanFrame(true);
        }
      }
    }
    const readyText = fillEngineReady()
      ? `AI fill ready${fill.default ? ` · ${esc(String(fill.default).toUpperCase())} by default` : ""}`
      : (state.cleanScope === "source"
        ? "AI fill needs its model pack · Blur works now"
        : "AI fill needs its model pack · Blur and Crop guard work now");
    const headerCopy = sourceScope
      ? `${rows.length} row${rows.length === 1 ? "" : "s"} · click a row to jump to the text`
      : `${rows.length} row${rows.length === 1 ? "" : "s"} · click a row to open its moment`;
    panel.innerHTML = `
      <div class="clean-found-head">
        <span class="clean-found-title">Found text</span>
        <span class="hint">${headerCopy}</span>
      </div>
      <div class="clean-found-list" role="list">${rowsHtml}</div>
      <div class="clean-found-actions">
        <button class="ghost small" type="button" data-found-all>Select all</button>
        <button class="ghost small" type="button" data-found-none${tickCount ? "" : " disabled"}>Clear</button>
        ${lowCount ? `<button class="ghost small" type="button" data-found-review>Review ${lowCount} more</button>` : ""}
        <select id="clean-found-method" class="clean-method-select" aria-label="Method for ticked text">${methodOptions}</select>
        ${sourceScope ? "" : `<button class="primary small" type="button" data-found-apply${tickCount ? "" : " disabled"}>Remove ticked (${tickCount})</button>`}
      </div>
      <p class="hint clean-found-note">${readyText}</p>`;
    if (sourceScope) paintSourceClean();
    else paintCutClean();
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
      ...(entry.fill_keys !== undefined ? { fill_keys: entry.fill_keys } : {}),
      ranges,
      source: "scan",
    });
  }

  function applyFoundTicks() {
    const rows = cleanScanRows();
    const byIdentity = new Map(rows.map((row) => [cleanRowIdentity(row), row]));
    const ticks = Array.from(state.classicText.foundTicks)
      .map((identity) => byIdentity.get(identity))
      .filter((row) => row && !row.manual && !row.added)
      .sort((a, b) => rows.indexOf(a) - rows.indexOf(b));
    if (!ticks.length) {
      setCleanStatus("Tick the text you want removed first.");
      return;
    }
    let method = state.classicText.foundMethod || "fill";
    if (method === "fill" && !fillEngineReady()) method = "blur";
    const engine = fillEngineNow();
    if (method === "fill" && !state.fill?.engines?.[engine]?.ready) {
      setCleanStatus(state.fill?.engines?.[engine]?.reason || "That engine is not installed.");
      return;
    }
    let added = 0;
    let outside = 0;
    // One undo step for the whole tick, not one per row.
    pushClassicUndo();
    for (const row of ticks) {
      // A grouped row is one choice, but every member keeps its own tight box,
      // ranges and fill keys. Never union subtitle lines into one large layer.
      const members = row.manual
        ? [row]
        : (Array.isArray(row.entryRows) && row.entryRows.length ? row.entryRows : [row.entry]);
      let outsideRow = false;
      for (const member of members) {
        if (!member) continue;
        const override = cleanOverrideFor(row, member);
        const ranges = override || member.ranges || row.ranges || [];
        if (ranges.length && !cleanCutRanges(ranges).length) {
          outsideRow = true;
          continue;
        }
        addCleanFromScan({
          ...member,
          box: member.box || row.box,
          ranges,
          text_key: member.text_key || member.text || row.text_key || row.text,
          tracklet_id: member.tracklet_id || row.tracklet_id,
          kind: member.kind || row.kind,
        }, method, engine);
        added += 1;
      }
      if (outsideRow) outside += 1;
    }
    const deduped = dedupeCleanLayers(classicCleanLayers());
    if (deduped.changed) state.classicText.clean = deduped.layers;
    if (!classicCleanLayers().some((layer) => layer.id === state.classicText.selection)) {
      state.classicText.selection = "";
    }
    state.classicText.foundTicks = new Set();
    state.classicText.foundTicksInit = true;
    saveFoundTicks();
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
    const skipped = outside ? ` ${outside} not in this cut.` : "";
    if (state.cleanScope === "source") {
      setCleanStatus(added
        ? `Prepared ${added} text spot${added === 1 ? "" : "s"} with ${CLEAN_METHODS[method].label}.`
        : "No text was added.");
      return;
    }
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
        : (state.cleanScope === "source" ? "whole video" : "whole cut");
      const fillReady = fillEngineReady();
      const chips = Object.entries(CLEAN_METHODS)
        .filter(([key]) => key !== "fill" || fillReady)
        .filter(([key]) => state.cleanScope !== "source" || key !== "crop")
        .map(([key, item]) => (
          `<button type="button" class="clean-chip${key === method ? " active" : ""}" data-clean-method="${key}" data-clean-target="${esc(layer.id)}" title="${esc(item.note)}">${item.label}</button>`
        )).join("");
      const enginePicker = method === "fill"
        ? `<span class="clean-engine">${esc(CLEAN_FILL_ENGINE_LABEL[fillEngineNow()])}</span>`
        : "";
      return `
        <div class="clean-row${selected ? " is-selected" : ""}${layer.hidden ? " is-off" : ""}" role="listitem" data-clean-row="${esc(layer.id)}">
          <button class="clean-eye" type="button" data-clean-eye="${esc(layer.id)}" aria-pressed="${layer.hidden ? "false" : "true"}" title="${layer.hidden ? "Show" : "Hide"} this box" aria-label="${layer.hidden ? "Show" : "Hide"} this box">${cleanIcon(layer.hidden ? "eye-off" : "eye")}</button>
          <div class="clean-row-copy">
            <span class="clean-row-label">${esc(layer.label || layer.kind || "Box")} <span class="clean-row-src">${esc(layer.source === "scan" ? "scan" : "manual")}</span></span>
            <span class="clean-row-meta">${esc(ranges)} · ${(layer.box.w * 100).toFixed(0)}×${(layer.box.h * 100).toFixed(0)}%${out ? ` · ${esc(out)}` : ""}</span>
          </div>
          ${cleanRowTimes(layer)}
          <div class="clean-row-methods" role="group" aria-label="Method">${chips}${enginePicker}</div>
          <button class="clean-row-del" type="button" data-clean-delete="${esc(layer.id)}" title="Delete box" aria-label="Delete box">${cleanIcon("trash")}</button>
        </div>`;
    };
    list.innerHTML = layers.map(row).join("");
  }

  // One time on a box can be edited here; a box with several keeps them all.
  function cleanRowTimes(layer) {
    const ranges = layer.ranges || [];
    if (ranges.length !== 1) return "";
    const field = (side, label) => (
      `<label class="clean-row-time">${label}<input type="number" min="0" step="0.05" value="${round2(ranges[0][side])}" data-clean-time="${side}" data-clean-target="${esc(layer.id)}"></label>`
    );
    return `<div class="clean-row-times" role="group" aria-label="When this box applies">${field("start", "From")}${field("end", "To")}</div>`;
  }

  function setCleanTime(id, side, value) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    const range = (layer?.ranges || [])[0];
    const seconds = Number(value);
    if (!range || layer.ranges.length !== 1 || !Number.isFinite(seconds)) return;
    const other = side === "start" ? Number(range.end) : Number(range.start);
    if (side === "start" ? seconds >= other : seconds <= other) {
      setCleanStatus("A box must end after it starts.");
      renderCleanLayers();
      return;
    }
    pushClassicUndo();
    range[side] = round2(Math.max(0, seconds));
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  function cleanOutsideCut(layer) {
    const box = layer.box;
    if (!box) return "";
    if (box.w > 0.96 && box.h > 0.96) return "covers the frame";
    if (box.x + box.w > 1.001 || box.y + box.h > 1.001) return "outside the frame";
    return "";
  }

  function paintCleanEmptyState() {
    if (!dom.cleanEmpty) return;
    const layers = classicCleanLayers();
    const sourceScope = state.cleanScope === "source";
    dom.cleanEmpty.hidden = layers.length > 0;
    const copy = dom.cleanEmpty.querySelector("p");
    if (copy) {
      const report = state.textScan?.report;
      const confirmed = Boolean(report && report.text && report.text.confirmed === true);
      const scannedRows = cleanScanRows().length;
      const scanStatus = state.textScan?.status || "idle";
      if (sourceScope) {
        if (scanStatus === "queued" || scanStatus === "running") {
          copy.textContent = tr("Scanning the whole video…");
        } else if (scanStatus === "ready" && confirmed) {
          copy.textContent = scannedRows
            ? tr("Text was found but is not cleaned yet. Select the rows, then clean.")
            : tr("No baked-in text found. Nothing was rendered.");
        } else if (scanStatus === "ready") {
          copy.textContent = tr("The scan could not confirm on-screen text. Rescan to try again.");
        } else if (scanStatus === "failed") {
          copy.textContent = tr("The scan failed. Retry the scan; nothing was rendered.");
        } else if (scanStatus === "cancelled") {
          copy.textContent = tr("Scan cancelled. Scan again when ready.");
        } else {
          copy.textContent = tr("No text scan yet. Find text scans the whole video. Review first stops so you can check every row.");
        }
      } else if (scanStatus === "queued" || scanStatus === "running") {
        copy.textContent = tr("Scanning the cut for text…");
      } else if (scanStatus === "ready" && confirmed) {
        copy.textContent = scannedRows
          ? tr("Text was found but is not cleaned yet. Tick a row or use the Clean action.")
          : tr("No baked-in text found. Nothing was rendered.");
      } else if (scanStatus === "ready") {
        copy.textContent = tr("The scan could not confirm on-screen text. Rescan to try again.");
      } else if (scanStatus === "failed") {
        copy.textContent = tr("The scan failed. Retry the scan; nothing was rendered.");
      } else if (scanStatus === "cancelled") {
        copy.textContent = tr("Scan cancelled. Scan again when ready.");
      } else {
        copy.textContent = tr("No text scan yet. Find text scans this cut. Review first stops so you can check every row.");
      }
    }
  }

  function paintCleanPanel(options = {}) {
    const layers = classicCleanLayers();
    const rebuildRows = options.rows !== false;
    renderCleanLayers();
    if (rebuildRows) renderCleanFound();
    renderCleanFill();
    paintCleanEmptyState();
    if (dom.cleanCount) {
      dom.cleanCount.hidden = !layers.length;
      dom.cleanCount.textContent = `${layers.length} box${layers.length === 1 ? "" : "es"}`;
      dom.cleanCount.className = "text-scan-badge" + (layers.length ? " is-ready" : "");
    }
    paintCleanBoxes();
  }

  // ------------------------------------------------------------ box actions

  function selectClean(id) {
    state.classicText.selection = id || "";
    if (!id) state.classicText.selectedBar = "";
    paintCleanStage();
  }

  function addCleanBox(options = {}) {
    const sourceScope = state.cleanScope === "source";
    if (!sourceScope && !classicTextSupported()) {
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
    const cap = 1000;
    if (classicCleanLayers().length >= cap) {
      toast(`A video supports at most ${cap} Clean boxes.`);
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
      ...(options.fill_keys !== undefined ? { fill_keys: options.fill_keys } : {}),
      mask: options.mask || null,
      source: options.source === "scan" ? "scan" : "manual",
      color: options.color || CLEAN_DEFAULT_COLOR,
      opacity: Number.isFinite(Number(options.opacity)) ? Number(options.opacity) : CLEAN_DEFAULT_OPACITY,
      radius: Number.isFinite(Number(options.radius)) ? Number(options.radius) : CLEAN_DEFAULT_RADIUS,
      hidden: false,
    };
    classicCleanLayers().push(layer);
    newCleanTokenSet().add(cleanIdentityToken(layer));
    state.classicText.selection = layer.id;
    setCleanStatus(`${CLEAN_METHODS[cleanMethodKey(layer)].label} box added. It saves with the ${state.cleanScope === "source" ? "whole video" : "cut"}.`);
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
    return layer;
  }

  function deleteCleanBox(id) {
    const before = classicCleanLayers().length;
    if (!before) return;
    const layer = classicCleanLayers().find((item) => item.id === id);
    pushClassicUndo();
    const pending = pendingCleanDeletes();
    pending.ids.add(String(id));
    if (layer) pending.tokens.add(cleanIdentityToken(layer));
    state.classicText.clean = classicCleanLayers().filter((item) => item.id !== id);
    if (state.classicText.selection === id) {
      state.classicText.selection = "";
      state.classicText.selectedBar = "";
    }
    saveClassicText();
    paintCleanStage();
    scheduleCleanFrame();
  }

  function defaultFillEngine(_kind) {
    return fillEngineNow();
  }

  function setCleanMethod(id, method) {
    const layer = classicCleanLayers().find((item) => item.id === id);
    if (!layer || !CLEAN_METHODS[method]) return;
    if (state.cleanScope === "source" && method === "crop") {
      setCleanStatus("Crop guard would crop the whole video. Source Clean keeps the full frame; use Blur or AI fill.");
      return;
    }
    if (method === "fill" && !fillEngineReady()) {
      setCleanStatus(state.cleanScope === "source"
        ? "AI fill needs its model pack. Blur works on the whole video now."
        : "AI fill needs its model pack. Blur and Crop guard work now.");
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
      if (state.cleanScope !== "source" && !classicTextSupported()) {
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
            ranges: [cleanManualRange(currentCleanTime())].filter(Boolean),
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
        window: cleanManualRange(currentCleanTime()),
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
    dom.cleanAddRange?.addEventListener("click", startCleanAddRange);
    dom.cleanPreviewExpand?.addEventListener("click", toggleCleanExpand);
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
      cleanSeek(Number(dom.cleanScrub.value) || 0);
      paintCleanStage({ rows: false });
    });
    bindCleanStageDrag();
    paintCleanRulerAndBarDrag();
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
      const field = event.target.closest("[data-clean-time]");
      if (field) setCleanTime(field.dataset.cleanTarget, field.dataset.cleanTime, field.value);
    });
    dom.cleanFound?.addEventListener("click", (event) => {
      if (event.target.closest("[data-found-all]")) {
        const rows = cleanScanRows();
        state.classicText.foundTicks = new Set(
          rows
            .filter((row) => !row.manual && !row.added
              && (state.cleanScope === "source" || cleanRowCutStart(row) !== null))
            .map((row) => cleanRowIdentity(row)),
        );
        resetSourceConfirmation();
        saveFoundTicks();
        renderCleanFound();
        return;
      }
      if (event.target.closest("[data-found-none]")) {
        state.classicText.foundTicks = new Set();
        resetSourceConfirmation();
        saveFoundTicks();
        renderCleanFound();
        return;
      }
      if (event.target.closest("[data-found-review]")) {
        const first = dom.cleanFound?.querySelector(".clean-found-row.is-low");
        scrollIntoViewSafe(first, { behavior: "smooth", block: "nearest" });
        first?.focus();
        setCleanStatus("Low-confidence rows stay visible. Tick the ones you recognise, then clean.");
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
        const identity = tick.dataset.foundTick || "";
        if (tick.checked) state.classicText.foundTicks.add(identity);
        else state.classicText.foundTicks.delete(identity);
        resetSourceConfirmation();
        saveFoundTicks();
        renderCleanFound();
        const restored = Array.from(
          dom.cleanFound?.querySelectorAll("[data-found-tick]") || [],
        ).find((node) => node.dataset.foundTick === identity);
        restored?.focus();
        return;
      }
      if (event.target.id === "clean-found-method") {
        state.classicText.foundMethod = event.target.value;
        renderCleanFound();
        dom.cleanFound?.querySelector("#clean-found-method")?.focus();
        return;
      }
    });
    dom.cleanFound?.addEventListener("keydown", (event) => {
      if (event.target.closest("input, select, button")) return;
      const row = event.target.closest("[data-found-index]");
      if (!row) return;
      const rows = [...(dom.cleanFound?.querySelectorAll("[data-found-index]") || [])];
      const index = rows.indexOf(row);
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusCleanRow(cleanScanRows()[Number(row.dataset.foundIndex)]);
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = rows[clamp(index + (event.key === "ArrowDown" ? 1 : -1), 0, rows.length - 1)];
        next?.focus();
      }
    });
    dom.cleanFill?.addEventListener("click", (event) => {
      if (event.target.closest("#clean-model-chip")) {
        toggleCleanEngineMenu();
        return;
      }
      const engine = event.target.closest("[data-engine]");
      if (engine) {
        if (!engine.disabled) setFillChoice({ engine: engine.dataset.engine });
        toggleCleanEngineMenu(false);
        $("#clean-model-chip")?.focus();
        return;
      }
      if (event.target.closest("#clean-fill-options-open")) {
        toggleCleanFillOptions();
        return;
      }
      const device = event.target.closest("[data-fill-device]");
      if (device && !device.disabled) {
        setFillChoice({ device: device.dataset.fillDevice });
        toggleCleanFillOptions(true);
        return;
      }
      const snap = event.target.closest("[data-clean-snap]");
      if (snap) snapBoxToLines(snap.dataset.cleanSnap);
    });
    dom.cleanFill?.addEventListener("change", (event) => {
      if (event.target.id === "clean-fill-follow") setFillChoice({ follow: event.target.checked });
    });
    dom.cleanFill?.addEventListener("keydown", (event) => {
      const menu = $("#clean-engine-menu");
      if (!menu || menu.hidden) return;
      const items = [...menu.querySelectorAll(".clean-engine-item:not(:disabled)")];
      if (!items.length) return;
      const current = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = items[clamp(current + (event.key === "ArrowDown" ? 1 : -1), 0, items.length - 1)];
        next?.focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeCleanModelMenus();
        $("#clean-model-chip")?.focus();
      }
    });
    dom.cleanPreviewBefore?.addEventListener("click", () => {
      stopCleanReview({ syncTime: true });
      state.classicText.previewSide = "before";
      if (state.cleanScope === "source" || cutCleanActive()) scheduleCleanFrame(true);
      renderCleanFill();
    });
    dom.cleanPreviewAfter?.addEventListener("click", () => {
      stopCleanReview({ syncTime: true });
      state.classicText.previewSide = "after";
      if (state.cleanScope === "source" || cutCleanActive()) scheduleCleanFrame(true);
      renderCleanFill();
    });
    dom.cleanPreviewPlay?.addEventListener("click", toggleCleanReviewPlayback);
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
      if (!fillEngineReady()) {
        cleanDiagnostic("Classic AI fill unavailable:", state.fill?.engines?.[fillEngineNow()]?.reason
          || state.fill?.note || "");
        setCleanStatus("AI fill needs its model pack. Install it in Setup, or use Blur.");
        return;
      }
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      if (selected) setCleanMethod(selected.id, "fill");
      else applyFoundTicks();
    });
    dom.cleanPreviewBlur?.addEventListener("click", () => {
      const selected = classicCleanLayers().find((layer) => layer.id === state.classicText.selection);
      if (selected) setCleanMethod(selected.id, "blur");
      else setCleanStatus("Select a box first.");
    });
    dom.cleanDetail?.addEventListener("click", (event) => {
      if (event.target.closest("[data-clean-detail-close]")) {
        dom.cleanDetail.hidden = true;
        dom.cleanDetail.innerHTML = "";
      }
    });
    dom.cleanFound?.addEventListener("dblclick", (event) => {
      const row = event.target.closest("[data-found-index]");
      if (!row) return;
      const item = cleanScanRows()[Number(row.dataset.foundIndex)];
      if (item) {
        focusCleanRow(item);
        openCleanDetail(item);
        setCleanStatus(`${item.kind} · ${item.text} · ${cleanRowTimeLabel(item)}`);
      }
    });
    bindCleanReviewVideo();
    paintClassicUndo();
    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest?.("#clean-fill")) closeCleanModelMenus();
    });
    document.addEventListener("fullscreenchange", () => {
      dom.cleanCanvas?.classList.toggle("is-expanded", Boolean(document.fullscreenElement));
    });
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
    if (event.key === "Escape" && (
      ($("#clean-engine-menu") && !$("#clean-engine-menu").hidden)
      || ($("#clean-fill-options") && !$("#clean-fill-options").hidden)
    )) {
      event.preventDefault();
      closeCleanModelMenus();
      $("#clean-model-chip")?.focus();
      return true;
    }
    if (event.key === "Escape" && dom.cleanDetail && !dom.cleanDetail.hidden) {
      event.preventDefault();
      const identity = state.classicText.detailIdentity;
      dom.cleanDetail.hidden = true;
      dom.cleanDetail.innerHTML = "";
      const index = identity
        ? cleanScanRows().findIndex((row) => cleanRowIdentity(row) === identity)
        : -1;
      const target = index >= 0
        ? dom.cleanFound?.querySelector(`[data-found-index="${index}"]`)
        : dom.cleanFound?.querySelector("[data-found-index]");
      target?.focus({ preventScroll: true });
      state.classicText.detailIdentity = "";
      return true;
    }
    if (typing) return false;
    if (event.target.closest?.("#clean-fill")) return false;
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
        state.classicText.selectedBar = "";
        paintCleanStage({ rows: false });
      }
      return true;
    }
    if (
      cleanWorkspaceActive()
      && (event.key === "ArrowLeft" || event.key === "ArrowRight")
      && !event.altKey
    ) {
      event.preventDefault();
      const step = event.shiftKey ? 1 : 0.1;
      cleanSeek(currentCleanTime() + (event.key === "ArrowRight" ? step : -step));
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
      stopCleanReview();
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
    if (!state.job || state.cleanScope === "source") {
      chip.hidden = true;
      return;
    }
    chip.hidden = false;
    const facts = textScanFacts(scan && scan.report);
    const labels = {
      idle: "Clean text ›",
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
    if (!state.job || state.cleanScope === "source") return;
    setResultMode("clean");
    scrollIntoViewSafe(dom.cutCleanAction, { block: "nearest", behavior: "smooth" });
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

  function setJobMenu(open, options = {}) {
    if (!dom.jobMenu || !dom.jobMenuOpen) return;
    const on = Boolean(open);
    const restoreFocus = Boolean(options.restoreFocus);
    dom.jobMenu.hidden = !on;
    dom.jobMenuOpen.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) dom.jobMenu.querySelector("select, button")?.focus();
    else if (restoreFocus) dom.jobMenuOpen.focus();
  }

  function bindJobMenu() {
    if (!dom.jobMenuOpen || !dom.jobMenu) return;
    dom.jobMenuOpen.addEventListener("click", () => setJobMenu(dom.jobMenu.hidden));
    dom.jobMenu.addEventListener("click", (event) => {
      if (event.target.closest("#clean-profile")) event.stopPropagation();
      if (event.target.closest(".job-menu-item")) {
        setJobMenu(false);
        // A non-navigating item keeps the user in the result screen. Return
        // focus to More after the click, but never on an outside dismissal.
        setTimeout(() => {
          if (dom.result && !dom.result.hidden) dom.jobMenuOpen.focus();
        }, 0);
      }
    });
    document.addEventListener("mousedown", (event) => {
      if (dom.jobMenu.hidden) return;
      if (event.target.closest("#job-menu-wrap")) return;
      setJobMenu(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || dom.jobMenu.hidden) return;
      event.preventDefault();
      setJobMenu(false, { restoreFocus: true });
    });
  }

  function bindChrome() {
    dom.finishCut?.addEventListener("click", toggleFinishMode);
    document.addEventListener("focusin", (event) => {
      if (state.cleanScope !== "cut" || cutCleanActive()) return;
      const element = event.target;
      if (!element || !dom.result?.contains(element) || element.closest?.("#result-mode")) return;
      state.editFocusElement = element;
    });
    dom.shortcutsOpen?.addEventListener("click", openShortcuts);
    dom.cleanHelp?.addEventListener("click", openShortcuts);
    dom.shortcutsClose?.addEventListener("click", closeShortcuts);
    dom.shortcutsSheet?.addEventListener("click", (event) => {
      if (event.target.closest("[data-shortcuts-close]")) closeShortcuts();
    });
    dom.momentsScan?.addEventListener("click", momentsScanAction);
    bindJobMenu();
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
    return state.job.analysis?.hook_scene ?? null;
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
      ...fillRequestFields(),
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

  function renderStaleFor(record) {
    if (!record) return { stale: false, noBaseline: false };
    let baseline = String(record?.request_sig || "");
    const key = renderSigKey(record);
    if (!baseline && key) {
      try { baseline = localStorage.getItem(key) || ""; } catch (_) { /* ignore */ }
    }
    if (!baseline) return { stale: false, noBaseline: true };
    const current = renderSignatureOf(
      renderRequestFor(record.target, record.quality || "final"),
    );
    return { stale: baseline !== current, noBaseline: false };
  }

  function updateRenderStale(record) {
    if (!dom.renderStale) return;
    const stateForRecord = renderStaleFor(record);
    if (stateForRecord.noBaseline) {
      dom.renderStale.textContent = tr("No render baseline on this browser. Render again to confirm this cut matches.");
      dom.renderStale.hidden = false;
      return;
    }
    dom.renderStale.textContent = tr(
      window.ClassicTrust?.STALE_RENDER_TEXT
      || "Changed since this render — render again to see it.",
    );
    dom.renderStale.hidden = !stateForRecord.stale;
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
    if (state.cleanScope === "cut" && state.job) paintCutClean();

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
          scrollIntoViewSafe(dom.playerWrap, { behavior: "smooth", block: "center" });
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
      cleanDiagnostic("Classic render failed:", failed.error || "");
      dom.renderError.textContent = tr(plainRenderError(failed.error));
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
      return result;
    } catch (error) {
      toast(error.message);
      updateRenderPanel();
      return null;
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
    if (state.cleanScope === "source" || !state.job?.analysis?.scenes) return;
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
    if (
      state.cleanScope === "source"
      && state.job
      && sourceCleanActive(state.sourceClean)
    ) {
      // Leaving is not a silent background render: stop the job first.
      api(`/api/classic/jobs/${state.job.id}/clean/source/cancel`, {
        method: "POST",
      }).catch(() => {});
    }
    stopPoll();
    resetSourceCleanState();
    state.cleanScope = "cut";
    resetCutCleanState();
    applySourceMode(false);
    applyCleanMode(false);
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
    if (dom.progressSource) dom.progressSource.hidden = true;
    if (dom.progressRetry) {
      dom.progressRetry.hidden = true;
      dom.progressRetry.disabled = false;
      dom.progressRetry.textContent = "Retry analysis";
    }
    if (dom.progressDownload) {
      dom.progressDownload.hidden = true;
      dom.progressDownload.removeAttribute("href");
    }
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
    dom.ingestNote.textContent = "Clean removes text from the whole video. Dissect cuts a reel.";
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
      dom.cleanJob.textContent = "Clean work files…";
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

  function textScanReportKey(report) {
    if (!report) return "";
    const text = report.text || {};
    return JSON.stringify({
      confirmed: Boolean(text.confirmed),
      tracklets: Number(text.tracklets) || 0,
      prefill: (report.clean_prefill || []).map((entry) => ({
        id: entry.tracklet_id || "",
        key: entry.text_key || entry.text || "",
        confidence: Number(entry.confidence) || 0,
        ranges: (entry.ranges || []).map((range) => [
          Number(range.start) || 0, Number(range.end) || 0,
        ]),
      })),
    });
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
    const sourceScope = state.cleanScope === "source";

    dom.textScanProgress.hidden = !active;
    dom.textScanCancel.hidden = !active;
    dom.textScanStart.hidden = active;
    if (active) {
      dom.textScanFill.style.width = `${Math.round(pct * 100)}%`;
      dom.textScanProgressText.textContent = `${Math.round(pct * 100)}%`;
    }

    if (status === "queued") {
      dom.textScanStatus.textContent = "Queued. The scan starts as soon as the Mac is free.";
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "running") {
      dom.textScanStatus.textContent = `Scanning for text on screen… ${Math.round(pct * 100)}%`;
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "ready") {
      dom.textScanStatus.textContent = facts.confirmed
        ? `Text on screen: ${facts.regions} ${facts.regions === 1 ? "region" : "regions"} across this ${sourceScope ? "source" : "cut"}.`
        : `Scan finished. No readable text on screen in this ${sourceScope ? "source" : "cut"}.`;
      dom.textScanStart.textContent = "Scan again";
    } else if (status === "cancelled") {
      dom.textScanStatus.textContent = "Scan cancelled. Nothing was written for this cut.";
      dom.textScanStart.textContent = "Find text on screen";
    } else if (status === "failed") {
      const reason = (report && (report.message || report.error)) || "the scan did not finish";
      dom.textScanStatus.textContent = `Scan failed: ${reason}`;
      dom.textScanStart.textContent = "Retry scan";
    } else {
      dom.textScanStatus.textContent = sourceScope
        ? "Not scanned yet. Find text & clean scans the whole video."
        : "Not scanned yet. Find text to look for captions, watermarks and screen UI baked into the cut.";
      dom.textScanStart.textContent = "Find text on screen";
    }
    renderCleanFound();
    paintCleanTimeline();
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

  function textScanFromHttp(status, data) {
    if (status === 200) {
      const reported = String(data?.status || "").toLowerCase();
      if (reported === "cancelled") return { status: "cancelled", report: data };
      if (reported === "failed") return { status: "failed", report: data };
      if (reported === "idle" || data?.report === null) return { status: "idle", report: null };
      const tracklets = Array.isArray(data?.tracklets) ? data.tracklets.length : 0;
      const prefill = Array.isArray(data?.clean_prefill) ? data.clean_prefill.length : 0;
      const readyReport = reported === "ready"
        || data?.text?.confirmed === true
        || data?.complete === true
        || tracklets > 0
        || prefill > 0;
      if (readyReport) return { status: "ready", report: data };
      if (reported === "queued" || reported === "running") {
        return { status: reported, report: data };
      }
      return { status: "idle", report: null };
    }
    if (status === 202) {
      return { status: (data && data.status) || "queued", report: data };
    }
    if (status === 404) return { status: "idle", report: null };
    throw new Error(checkProblem(status, data));
  }

  async function readTextScan(jobId, signal) {
    const { status, data } = await checkRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/check`, { signal },
    );
    return textScanFromHttp(status, data);
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
      if (next.status === "ready") {
        if (state.cleanScope === "cut") ensureCutFoundTicks();
        else if (state.cleanScope === "source") ensureSourceFoundTicks();
      }
      paintTextScan();
      if (next.status !== "queued" && next.status !== "running") return;
    }
  }

  async function refreshTextScan() {
    const jobId = state.job && state.job.id;
    if (!jobId || !dom.textScanStatus) return;
    const previousStatus = state.textScan?.status || "idle";
    const previousKey = textScanReportKey(state.textScan?.report);
    abortTextScan();
    const controller = new AbortController();
    state.textScan = { jobId, status: "idle", report: null, controller };
    paintTextScan();
    try {
      const next = await readTextScan(jobId, controller.signal);
      if (controller.signal.aborted || !state.job || state.job.id !== jobId) return;
      if (
        next.status === "ready"
        && (previousStatus !== "ready" || previousKey !== textScanReportKey(next.report))
      ) {
        clearStoredFoundTicks();
        state.classicText.foundTicks = new Set();
        state.classicText.foundTicksInit = false;
      }
      state.textScan = { jobId, status: next.status, report: next.report, controller };
      if (next.status === "ready") {
        if (state.cleanScope === "cut") ensureCutFoundTicks();
        else if (state.cleanScope === "source") ensureSourceFoundTicks();
      }
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

  async function startTextScan(runAgain = false) {
    const jobId = state.job && state.job.id;
    if (!jobId || !dom.textScanStatus) return;
    const force = Boolean(runAgain) || Boolean(state.textScan && state.textScan.report);
    abortTextScan();
    clearStoredFoundTicks();
    state.classicText.foundTicks = new Set();
    state.classicText.foundTicksInit = false;
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
      if (answer.status === 200 || answer.status === 202) {
        next = textScanFromHttp(answer.status, answer.data);
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
    if (next.status === "ready") {
      if (state.cleanScope === "cut") ensureCutFoundTicks();
      else if (state.cleanScope === "source") ensureSourceFoundTicks();
    }
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
    const scenes = state.job.analysis?.scenes;
    if (!Array.isArray(scenes)) return null;
    return scenes.find((scene) => scene.id === id) || null;
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
