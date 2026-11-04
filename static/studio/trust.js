/**
 * Studio trust helpers. Pure functions so Node tests can run them without a DOM.
 *
 * They do not decide policy. They only make capability, cost and stale-output
 * state explicit in the UI before a creator spends credits or publishes.
 */

export const CLOUD_VOICE_ENGINES = ["heygen", "minimax", "elevenlabs", "fish", "gemini"];
export const CLOUD_MUSIC_ENGINES = ["minimax-music", "lyria-clip"];
export const STALE_RENDER_TEXT = "Changed since this render — render again to see it.";

export function capabilityLabel({ platform = null, cloud = false } = {}) {
  const nativeStt = platform?.native_stt === true;
  const nativeTts = platform?.native_tts === true;
  const nativeVision = platform?.native_vision === true;
  const anyNative = nativeStt || nativeTts || nativeVision;
  const allNative = nativeStt && nativeTts && nativeVision;
  if (cloud) return anyNative ? "Mixed AI" : "Cloud AI";
  if (allNative) return "On-device AI";
  if (anyNative) return "Mixed AI";
  return "AI off";
}

export function capabilityDetail({ platform = null, cloud = false } = {}) {
  const system = platform?.apple_silicon
    ? "Apple Silicon"
    : [platform?.system, platform?.machine].filter(Boolean).join(" · ") || "This machine";
  const parts = [];
  if (platform?.native_stt) parts.push("speech");
  if (platform?.native_tts) parts.push("voices");
  if (platform?.native_vision) parts.push("vision");
  const local = parts.length ? `On-device: ${parts.join(", ")}.` : "No on-device AI is ready.";
  const remote = cloud
    ? "Cloud keys are saved; provider calls happen only when you run a cloud action."
    : "No cloud key is saved; this build stays local.";
  return `${system}. ${local} ${remote}`;
}

export function costNotice({ provider = "", what = "", cached = false } = {}) {
  if (cached) return "Cached · no new provider call.";
  if (!provider || !what) return "";
  return `${provider} · sends ${what} · may cost credits.`;
}

export function dataNotice({ provider = "", what = "" } = {}) {
  if (!provider || !what) return "";
  return `This action sends ${what} to ${provider}.`;
}

export function renderCostNote({ voiceProvider = "", musicProvider = "" } = {}) {
  const names = [voiceProvider, musicProvider].filter(Boolean);
  if (!names.length) return "";
  return `Render calls ${names.join(" and ")} · may cost credits.`;
}

export function artifactIsStale(artifact = null, currentEditHash = "") {
  const madeFrom = String(artifact?.edit_hash || artifact?.spec?.edit_hash || "");
  const current = String(currentEditHash || "");
  return Boolean(madeFrom && current && madeFrom !== current);
}

export function graphicsCapNotice({ count = 0, cap = 32 } = {}) {
  const used = Math.max(0, Number(count) || 0);
  const limit = Math.max(1, Number(cap) || 32);
  if (used >= limit) return `All ${limit} text/effect slots are used. Delete one before adding another.`;
  const left = limit - used;
  if (left <= 3) return `${left} text/effect ${left === 1 ? "slot" : "slots"} left of ${limit}.`;
  return "";
}
