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

  const apiExport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = apiExport;
  if (typeof window !== "undefined") window.ClassicTrust = apiExport;
})();
