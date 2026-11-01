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

  const apiExport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = apiExport;
  if (typeof window !== "undefined") window.ClassicTrust = apiExport;
})();
