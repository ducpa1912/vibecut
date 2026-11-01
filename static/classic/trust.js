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
  } = {}) {
    const cloudKey = CLOUD_KEYS.some((name) => secrets[name] === true);
    const cloudVoice = CLOUD_VOICES.includes(voiceEngine);
    const cloudMusic = musicSource === "generate"
      || ["minimax-music", "lyria-clip"].includes(musicEngine);
    return cloudKey || cloudVoice || cloudMusic || onlineTranslation
      ? "Online features on"
      : "Local by default";
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

  const apiExport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = apiExport;
  if (typeof window !== "undefined") window.ClassicTrust = apiExport;
})();
