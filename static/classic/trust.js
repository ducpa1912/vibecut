/* Classic trust helpers. Pure functions so tests can run them in node. */
(() => {
  "use strict";

  const api = {};

  const CLOUD_KEYS = ["opencode", "openrouter", "minimax", "elevenlabs"];
  const CLOUD_VOICES = ["elevenlabs", "minimax", "heygen", "fish", "gemini"];

  /**
   * Top pill: honest about optional online features.
   * Any saved cloud key or selected cloud engine turns the pill online.
   */
  api.privacyLabel = function privacyLabel({
    secrets = {},
    voiceEngine = "",
    musicEngine = "",
    musicSource = "",
    onlineTranslation = false,
    platform = null,
  } = {}) {
    const cloudKey = CLOUD_KEYS.some((name) => secrets[name] === true);
    const cloudVoice = CLOUD_VOICES.includes(voiceEngine);
    const cloudMusic = musicSource === "generate"
      || ["minimax-music", "lyria-clip"].includes(musicEngine);
    const cloud = cloudKey || cloudVoice || cloudMusic || onlineTranslation;
    if (!platform || typeof platform !== "object") {
      return cloud ? "Cloud AI" : "On-device AI";
    }
    const nativeStt = platform.native_stt === true;
    const nativeTts = platform.native_tts === true;
    const nativeVision = platform.native_vision === true;
    const anyNative = nativeStt || nativeTts || nativeVision;
    const allNative = nativeStt && nativeTts && nativeVision;
    if (cloud) return anyNative ? "Mixed AI" : "Cloud AI";
    if (allNative) return "On-device AI";
    return anyNative ? "Mixed AI" : "AI off";
  };

  /** One short notice shown next to the button that can reach a provider. */
  api.costNotice = function costNotice({
    provider = "",
    what = "",
    cached = false,
  } = {}) {
    if (cached) return "Cached · no new call";
    if (!provider || !what) return "";
    return `${provider} · sends ${what} · may cost credits.`;
  };

  /** Auto translation tries online providers first unless the mode is local. */
  api.translationMayUseCloud = function translationMayUseCloud({
    mode = "auto",
    providers = [],
  } = {}) {
    if (mode === "local_only") return false;
    return (providers || []).some((item) => item
      && ["opencode", "openrouter"].includes(item.id)
      && item.available !== false);
  };

  /** Rewrite auto uses a cloud model when one is ready, then rules. */
  api.rewriteMayUseCloud = function rewriteMayUseCloud({ models = [] } = {}) {
    return (models || []).some((item) => item
      && ["opencode", "openrouter"].includes(item.id)
      && item.available !== false);
  };

  /** Say what the final render will actually use, next to the preview button. */
  api.soundUseNote = function soundUseNote({ kind = "voice", source = "generate" } = {}) {
    if (kind === "music") {
      if (source === "own") {
        return "The render uses the BGM file you choose; this preview is only a listen.";
      }
      if (source === "generate") {
        return "The render generates its own music bed from this prompt.";
      }
      return "";
    }
    if (source === "upload") {
      return "The render uses your recording; the voice list and sample are not used.";
    }
    return "The render uses the voice and settings above; this sample is only a preview.";
  };

  const TEXT_SHAPES = ["9:16", "4:5"];

  /** The Texts card warns before anything is typed. */
  api.textShapeNote = function textShapeNote({ aspect = "9:16" } = {}) {
    if (TEXT_SHAPES.includes(aspect)) return "";
    return "Text overlays and effects render on 9:16 and 4:5. Switch the shape to use them.";
  };

  /** The render note must never drop existing layers silently. */
  api.layerRenderNote = function layerRenderNote({ aspect = "9:16", hasLayers = false } = {}) {
    if (TEXT_SHAPES.includes(aspect)) return "";
    if (!hasLayers) return "";
    return "Text layers are left out at this shape.";
  };

  /** The Render button's own cost line: the render calls these providers. */
  api.renderCostNote = function renderCostNote({ voiceProvider = "", musicProvider = "" } = {}) {
    const names = [voiceProvider, musicProvider].filter(Boolean);
    if (!names.length) return "";
    return `Render calls ${names.join(" and ")} · may cost credits.`;
  };

  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object") {
      const out = {};
      Object.keys(value).sort().forEach((key) => {
        if (value[key] !== undefined) out[key] = canonical(value[key]);
      });
      return out;
    }
    return value;
  }

  /** Stable signature of the exact render request body. */
  api.renderSignature = function renderSignature(payload) {
    return JSON.stringify(canonical(payload === undefined ? null : payload));
  };

  api.STALE_RENDER_TEXT = "Changed since this render — render again to see it.";

  const CLEAN_PROFILES = {
    workfiles: {
      title: "Clean work files?",
      deletes: "thumbnails, the transcript, extracted audio and deep-read scores",
      keeps: "the source video, rendered reels and job details",
      note: "Analysis work files can be rebuilt by analyzing again.",
    },
    renders: {
      title: "Clean rendered reels?",
      deletes: "rendered reels, render masters and legacy render files",
      keeps: "the source video, transcript, thumbnails and job details",
      note: "Review links and pinned artifacts are protected. If they cannot be protected, Clean stops.",
    },
    all: {
      title: "Clean everything except the source?",
      deletes: "work files and rendered reels (thumbnails, transcript, extracted audio, deep-read scores, render masters)",
      keeps: "the source video and job details",
      note: "Review links and pinned artifacts are protected. If they cannot be protected, Clean stops.",
    },
  };

  /** Plain words for the destructive confirm step. */
  api.cleanProfile = function cleanProfile(profile = "workfiles") {
    return CLEAN_PROFILES[profile] || CLEAN_PROFILES.workfiles;
  };

  api.cleanConfirmText = function cleanConfirmText(profile = "workfiles") {
    const item = api.cleanProfile(profile);
    return [
      item.title,
      "",
      `Deletes: ${item.deletes}.`,
      `Keeps: ${item.keeps}.`,
      "",
      item.note,
    ].join("\n");
  };

  const apiExport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = apiExport;
  if (typeof window !== "undefined") window.ClassicTrust = apiExport;
})();
