/**
 * Favorites for the Voice Room (`/voices`), kept in this browser.
 *
 * The store is a JSON array of stable keys:
 *
 *   voice:<engine>:<voiceId>   a stock voice
 *   clone:<voiceId>            a cloned voice
 *
 * Reads never throw. A missing localStorage (Node, private mode) or a junk
 * value degrades to an empty list; writes are best effort and fall back to a
 * copy held for this page session.
 */

export const STORAGE_KEY = "vibecut.voice.favorites.v1";

let fallback = [];

function storage() {
  try {
    const value = globalThis.localStorage;
    if (!value || typeof value.getItem !== "function") return null;
    return value;
  } catch (_) {
    return null;
  }
}

function clean(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

/** One stable key for a stock voice. */
export function stockKey(engine, voiceId) {
  return `voice:${clean(engine)}:${clean(voiceId)}`;
}

export const voiceKey = stockKey;

/** One stable key for a clone. */
export function cloneKey(voiceId) {
  return `clone:${clean(voiceId)}`;
}

function normalise(value) {
  const raw = Array.isArray(value)
    ? value
    : Array.isArray(value?.keys)
      ? value.keys
      : value && typeof value === "object"
        ? Object.keys(value).filter((key) => value[key])
        : [];
  const seen = new Set();
  const keys = [];
  for (const item of raw) {
    const key = typeof item === "string" ? item.trim() : "";
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  return keys;
}

/** All favorite keys, in the order they were added. Never throws. */
export function listFavorites() {
  const store = storage();
  if (!store) return fallback.slice();
  try {
    const raw = store.getItem(STORAGE_KEY);
    const keys = raw ? normalise(JSON.parse(raw)) : [];
    fallback = keys;
    return keys.slice();
  } catch (_) {
    return [];
  }
}

/** How many voices are saved. */
export function favoriteCount() {
  return listFavorites().length;
}

/** True when `key` is saved. A missing or unreadable store reads as empty. */
export function isFavorite(key) {
  const wanted = clean(key);
  return Boolean(wanted) && listFavorites().includes(wanted);
}

/**
 * Save or unsave `key`.
 * @returns {boolean} the new state: true when the key is now saved.
 */
export function toggleFavorite(key) {
  const wanted = clean(key);
  if (!wanted) return false;
  const keys = listFavorites();
  const index = keys.indexOf(wanted);
  if (index >= 0) keys.splice(index, 1);
  else keys.push(wanted);
  fallback = keys;
  const store = storage();
  if (store && typeof store.setItem === "function") {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(keys));
    } catch (_) {
      // Quota or a blocked store: the page keeps the fallback copy.
    }
  }
  return index < 0;
}
