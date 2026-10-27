/**
 * VibeCut Studio — API client.
 *
 * Thin wrapper around the existing creator endpoints. No new routes, no
 * hidden network calls: every request below is an endpoint the Classic UI
 * already uses.
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

function tokenValue() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch (_) {
    return "";
  }
}

/**
 * Media elements cannot send an Authorization header. The server accepts the
 * token in a SameSite=Strict cookie for reads, so thumbnails keep working on a
 * non-loopback bind. Same behaviour as the Classic UI.
 */
function syncTokenCookie() {
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
  // Structured errors ({detail: {code, message, suggestion}}) carry the
  // human sentence in message; fall back to the code so it is never generic.
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

function offlineMessage(error) {
  if (error && error.name === "AbortError") return "Request cancelled.";
  return "Cannot reach VibeCut. Is the server running?";
}

/**
 * Perform a JSON request against the local server.
 * @param {string} path
 * @param {{method?: string, body?: unknown, signal?: AbortSignal}} options
 * @returns {Promise<any>}
 */
export async function request(path, options = {}) {
  syncTokenCookie();
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const config = {
    method: options.method || "GET",
    headers,
    credentials: "same-origin",
    signal: options.signal,
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(options.body);
  }

  let response;
  try {
    response = await fetch(path, config);
  } catch (error) {
    throw new ApiError(offlineMessage(error), 0, null);
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

function jobPath(jobId, suffix = "") {
  return `/api/jobs/${encodeURIComponent(jobId)}${suffix}`;
}

/** Recent videos, newest first. Existing `GET /api/jobs`. */
export function listJobs({ query = "", limit = 8, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request(`/api/jobs?${params.toString()}`);
}

/** One job, including source details and analysis. `GET /api/jobs/{id}`. */
export function getJob(jobId) {
  return request(jobPath(jobId));
}

/** Small polling payload. `GET /api/jobs/{id}/status`. */
export function getJobStatus(jobId) {
  return request(jobPath(jobId, "/status"));
}

/**
 * Upload a local video. `POST /api/jobs/upload`.
 * Upload uses XHR so the creator sees byte progress on long files.
 */
export function uploadVideo(file, options, onProgress) {
  syncTokenCookie();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs/upload");
    xhr.responseType = "text";
    xhr.timeout = 0;
    const token = tokenValue();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && typeof onProgress === "function") {
        onProgress(event.loaded / event.total, event.loaded, event.total);
      }
    };
    xhr.onload = () => {
      let payload = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch (_) {
        payload = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload);
        return;
      }
      const message = errorDetail(payload) || xhr.statusText || `Upload failed (${xhr.status}).`;
      reject(new ApiError(message, xhr.status, payload));
    };
    xhr.onerror = () => reject(new ApiError(offlineMessage(null), 0, null));
    xhr.onabort = () => reject(new ApiError("Upload cancelled.", 0, null));

    const form = new FormData();
    form.append("file", file);
    form.append("options", JSON.stringify(options || {}));
    xhr.send(form);
  });
}

/** Use a video already on this Mac. `POST /api/jobs/path`. */
export function createJobFromPath(path, options) {
  return request("/api/jobs/path", {
    method: "POST",
    body: { path, options: options || {} },
  });
}

/** Bring in a link. `POST /api/jobs/from-url`. */
export function createJobFromUrl(url, options, provider = null) {
  return request("/api/jobs/from-url", {
    method: "POST",
    body: { url, options: options || {}, provider: provider || null },
  });
}

/** Story sets already built for a job. `GET /api/jobs/{id}/clip-sets`. */
export function listClipSets(jobId) {
  return request(jobPath(jobId, "/clip-sets"));
}

/** Build a new story set. `POST /api/jobs/{id}/clip-sets`. */
export function createClipSet(jobId, { count = 3, order = "source" } = {}) {
  return request(jobPath(jobId, "/clip-sets"), {
    method: "POST",
    body: { count, order },
  });
}

/** Queue one story for render. `POST /api/jobs/{id}/clip-sets/{set}/stories/{story}/render`. */
export function renderStory(jobId, setId, storyId, { aspect = "9:16", quality = "final", captions = true } = {}) {
  return request(
    jobPath(
      jobId,
      `/clip-sets/${encodeURIComponent(setId)}/stories/${encodeURIComponent(storyId)}/render`,
    ),
    {
      method: "POST",
      body: { aspect, quality, captions },
    },
  );
}

/** Queue several stories, one after another. `POST /api/story-queues`. */
export function createStoryQueue(items) {
  return request("/api/story-queues", {
    method: "POST",
    body: { items },
  });
}

/** Existing queues, for a quiet count in Stories. `GET /api/story-queues`. */
export function listStoryQueues() {
  return request("/api/story-queues");
}
