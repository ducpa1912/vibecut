/**
 * Voice Room — API client.
 *
 * Its own small copy of the request helper, so the hidden Voice Room feature
 * does not depend on Studio's client (see docs/branching.md). Writes announce
 * `vibecut:data-changed`, which Studio's read cache listens to when a voice
 * panel runs inside Studio.
 */

const TOKEN_KEY = "vibecut_token";

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function tokenValue() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch (_) {
    return "";
  }
}

/** Media elements cannot send a header; the server reads this cookie instead. */
export function syncTokenCookie() {
  const token = tokenValue();
  const value = token ? encodeURIComponent(token) : "";
  const expiry = token ? "" : "; Max-Age=0";
  document.cookie = `vibecut_token=${value}; Path=/; SameSite=Strict${expiry}`;
}

export function errorDetail(payload) {
  if (!payload) return "";
  if (typeof payload === "string") return payload;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = typeof detail.message === "string" ? detail.message.trim() : "";
    const suggestion = typeof detail.suggestion === "string" ? detail.suggestion.trim() : "";
    if (message) return suggestion ? `${message} ${suggestion}` : message;
    if (typeof detail.code === "string" && detail.code) return detail.code.replace(/_/g, " ");
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item) return "";
        if (typeof item === "string") return item;
        const where = Array.isArray(item.loc) ? item.loc.filter((key) => key !== "body").join(".") : "";
        const message = item.msg || item.message || "";
        return where ? `${where}: ${message}` : message;
      })
      .filter(Boolean);
    if (parts.length) return parts.join(" ");
  }
  return typeof payload.message === "string" ? payload.message
    : typeof payload.error === "string" ? payload.error
    : "";
}

/** Tell other panels on the page that server data changed. */
export function announceChange() {
  try {
    window.dispatchEvent(new CustomEvent("vibecut:data-changed"));
  } catch (_) { /* no window (tests); nothing to tell */ }
}

/**
 * JSON request against the local server. Never cached.
 * @param {string} path
 * @param {{method?: string, body?: unknown, signal?: AbortSignal}} options
 */
export async function request(path, options = {}) {
  syncTokenCookie();
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const config = { method, headers, credentials: "same-origin", signal: options.signal };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(path, config);
  } catch (error) {
    const message = error && error.name === "AbortError"
      ? "Request cancelled."
      : "Cannot reach VibeCut. Is the server running?";
    throw new ApiError(message, 0, null);
  } finally {
    if (method !== "GET") announceChange();
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (_) {
      payload = text;
    }
  }
  if (!response.ok) {
    const message = errorDetail(payload) || `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

/** Recent videos, newest first. `GET /api/jobs`. */
export function listJobs({ query = "", limit = 8, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request(`/api/jobs?${params.toString()}`);
}
