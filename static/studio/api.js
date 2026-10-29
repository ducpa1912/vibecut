/**
 * VibeCut Studio — API client.
 *
 * Thin wrapper around the existing creator endpoints. No new routes, no
 * hidden network calls: every request below is an endpoint the Classic UI
 * already uses.
 */

const TOKEN_KEY = "vibecut_token";

// ---------------------------------------------------------------- read cache
//
// One shared per-job cache for the reads every step repeats: the job, its
// clip-sets, the Check report and the edits list, plus the other job-scoped
// JSON reads (packets, preflight, current Edit). Any write clears it. A
// fresh job with a different `updated` stamp drops that job's derived
// reads, so an external render or Check cannot leave a panel on old data.
// Status, the artifact list (Finish polls it every 2.4 s) and media URLs
// are never cached.

const NEVER_CACHE = /^\/(status|artifacts|frame|proxy|thumb|poster|reel|download|media|source)(\/|$)/;

const readCache = new Map();
const readPending = new Map();
let readEpoch = 0;
let readCounts = { hits: 0, misses: 0, coalesced: 0, writes: 0 };

function cacheablePath(path) {
  const value = String(path || "").split("?")[0];
  const match = /^\/api\/jobs\/[^/]+(\/.*)?$/.exec(value);
  if (!match) return false;
  return !NEVER_CACHE.test(match[1] || "/");
}

function jobFromPath(path) {
  const match = /^\/api\/jobs\/([^/]+)/.exec(String(path || ""));
  return match ? decodeURIComponent(match[1]) : "";
}

function cloneValue(value) {
  if (value === null || typeof value !== "object") return value;
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function jobStamp(job) {
  const value = job?.updated_at ?? job?.updated;
  return value === undefined || value === null ? "" : String(value);
}

function dropJob(jobId, { keepJob = false } = {}) {
  readEpoch += 1;
  if (!jobId) {
    readCache.clear();
    readPending.clear();
    return;
  }
  const prefix = `/api/jobs/${encodeURIComponent(jobId)}`;
  for (const key of [...readCache.keys()]) {
    if (key !== prefix) {
      if (key.startsWith(`${prefix}/`)) readCache.delete(key);
    } else if (!keepJob) {
      readCache.delete(key);
    }
  }
}

/** Drop cached reads. No id clears everything; with an id, keep the job row
 *  when `keepJob` is true and drop only its derived reads. */
export function invalidateReadCache(jobId = "", options = {}) {
  dropJob(jobId ? String(jobId) : "", options);
}

// Voice Room panels (static/voice/) use their own client; their writes
// announce themselves so this cache drops reads they may have changed.
if (typeof window !== "undefined") {
  window.addEventListener("vibecut:data-changed", () => invalidateReadCache());
}

/** Cache counters for the network-count check. */
export function readCacheStats() {
  return { ...readCounts, size: readCache.size };
}

/** Clear the cache and counters. Test hook; safe in the browser. */
export function resetReadCache() {
  readCache.clear();
  readPending.clear();
  readEpoch += 1;
  readCounts = { hits: 0, misses: 0, coalesced: 0, writes: 0 };
}

/** Cached job payload without a network call, or null. */
export function peekCachedJob(jobId) {
  const value = readCache.get(`/api/jobs/${encodeURIComponent(jobId)}`);
  return value ? cloneValue(value) : null;
}

/** Cached job's change stamp without cloning the payload; "" when absent. */
export function cachedJobStamp(jobId) {
  return jobStamp(readCache.get(`/api/jobs/${encodeURIComponent(jobId)}`));
}

function observeJob(path, value) {
  if (!/^\/api\/jobs\/[^/]+$/.test(path)) return;
  const previous = readCache.get(path);
  if (!previous) return;
  const before = jobStamp(previous);
  const after = jobStamp(value);
  if (before && after && before !== after) {
    dropJob(jobFromPath(path), { keepJob: true });
  }
}

/**
 * A running or queued payload (Check reports answer 202 while they work) is
 * a snapshot of progress, not a result. Caching it froze polls on the first
 * snapshot until the job stamp changed, so it is never stored.
 */
function inProgress(value) {
  if (!value || typeof value !== "object") return false;
  const state = String(value.status || "").toLowerCase();
  return state === "queued" || state === "running" || value.complete === false;
}

function readThrough(path, load, { fresh = false } = {}) {
  if (!fresh && readCache.has(path)) {
    readCounts.hits += 1;
    return Promise.resolve(cloneValue(readCache.get(path)));
  }
  if (readPending.has(path)) {
    readCounts.coalesced += 1;
    return readPending.get(path).then(cloneValue);
  }
  readCounts.misses += 1;
  const epoch = readEpoch;
  const task = load().then((value) => {
    if (epoch === readEpoch) {
      observeJob(path, value);
      if (inProgress(value)) readCache.delete(path);
      else readCache.set(path, cloneValue(value));
    }
    return cloneValue(value);
  });
  readPending.set(path, task);
  return task.finally(() => {
    if (readPending.get(path) === task) readPending.delete(path);
  });
}

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
async function performRequest(path, options = {}) {
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const config = {
    method: options.method || "GET",
    headers,
    credentials: "same-origin",
    signal: options.signal,
    // Lets a save started while the page unloads finish after it is gone.
    keepalive: Boolean(options.keepalive),
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

/**
 * Perform a JSON request against the local server.
 *
 * GETs of the job, its clip-sets, its Check report and its edits list are
 * served from the shared read cache. Every write clears the cache. Pass
 * `fresh: true` to force the job read that the shell watcher uses to detect
 * an external `updated` change. Pass `invalidate: false` for a POST that
 * writes nothing (a trim dry run) so dragging never empties the cache.
 * @param {string} path
 * @param {{method?: string, body?: unknown, signal?: AbortSignal, fresh?: boolean, invalidate?: boolean}} options
 * @returns {Promise<any>}
 */
export async function request(path, options = {}) {
  syncTokenCookie();
  const method = String(options.method || "GET").toUpperCase();
  if (method !== "GET") {
    readCounts.writes += 1;
    try {
      return await performRequest(path, options);
    } finally {
      if (options.invalidate !== false) invalidateReadCache();
    }
  }
  if (!options.signal && cacheablePath(path)) {
    return readThrough(
      path,
      () => performRequest(path, options),
      { fresh: Boolean(options.fresh) },
    );
  }
  return performRequest(path, options);
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
export function getJob(jobId, { fresh = false } = {}) {
  return request(jobPath(jobId), fresh ? { fresh: true } : {});
}

/** The latest Check report. `GET /api/jobs/{id}/check`. */
export function getCheckReport(jobId) {
  return request(jobPath(jobId, "/check"));
}

/** Every Edit for a job. `GET /api/jobs/{id}/edits`. */
export function listEdits(jobId) {
  return request(jobPath(jobId, "/edits"));
}

/** Small polling payload. `GET /api/jobs/{id}/status`. */
export function getJobStatus(jobId) {
  return request(jobPath(jobId, "/status"));
}

/**
 * Upload a local video. `POST /api/jobs/upload`.
 * Upload uses XHR so the creator sees byte progress on long files. Pass an
 * AbortSignal as `signal` to let them cancel it.
 */
export function uploadVideo(file, options, onProgress, { rights = null, signal = null } = {}) {
  syncTokenCookie();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (signal) {
      if (signal.aborted) {
        reject(new ApiError("Upload cancelled.", 0, null));
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
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
        invalidateReadCache();
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
    if (rights !== null) form.append("rights", rights ? "true" : "false");
    xhr.send(form);
  });
}

/** Use a video already on this Mac. `POST /api/jobs/path`. */
export function createJobFromPath(path, options, { rights = null } = {}) {
  return request("/api/jobs/path", {
    method: "POST",
    body: { path, options: options || {}, rights },
  });
}

/** Bring in a link. `POST /api/jobs/from-url`. */
export function createJobFromUrl(url, options, provider = null, { rights = null } = {}) {
  return request("/api/jobs/from-url", {
    method: "POST",
    body: { url, options: options || {}, provider: provider || null, rights },
  });
}

/** Story sets already built for a job. `GET /api/jobs/{id}/clip-sets`. */
export function listClipSets(jobId) {
  return request(jobPath(jobId, "/clip-sets"));
}

// ------------------------------------------------------------- story trim
//
// R2 atomic trim. The range, every live aspect's Edit, the caption track and
// the pointers commit together on the server. Studio never PATCHes a story
// range on its own, so these helpers are the only range writes.

/** One story's trim route prefix. */
export function trimPath(jobId, setId, storyId) {
  return jobPath(
    jobId,
    `/clip-sets/${encodeURIComponent(setId)}/stories/${encodeURIComponent(storyId)}/trim`,
  );
}

/**
 * Current range, sentence pool, neighbours, aspect health and limits.
 * `GET …/stories/{story}/trim`.
 */
export function getTrimState(jobId, setId, storyId, { fresh = false } = {}) {
  return request(trimPath(jobId, setId, storyId), fresh ? { fresh: true } : {});
}

/**
 * Trim a story at sentence bounds. `dry_run` returns the same shape and
 * writes nothing, so it can run on every drag step.
 */
export function trimStory(jobId, setId, storyId, {
  expectedRevision = 0,
  startSentence,
  endSentence,
  dryRun = false,
} = {}) {
  const body = {
    expected_revision: Number(expectedRevision) || 0,
    start_sentence: startSentence,
    end_sentence: endSentence,
  };
  if (dryRun) body.dry_run = true;
  return request(trimPath(jobId, setId, storyId), {
    method: "POST",
    body,
    invalidate: dryRun ? false : true,
  });
}

/** Undo the trim that produced `undoToken`. `POST …/trim/undo`. */
export function undoTrim(jobId, setId, storyId, { undoToken, expectedRevision = 0 } = {}) {
  return request(`${trimPath(jobId, setId, storyId)}/undo`, {
    method: "POST",
    body: {
      undo_token: String(undoToken || ""),
      expected_revision: Number(expectedRevision) || 0,
    },
  });
}

/** Rebind every stale aspect Edit to the current range. `POST <story>/rebind`. */
export function rebindStory(jobId, setId, storyId, { expectedRevision = 0 } = {}) {
  const path = jobPath(
    jobId,
    `/clip-sets/${encodeURIComponent(setId)}/stories/${encodeURIComponent(storyId)}/rebind`,
  );
  return request(path, {
    method: "POST",
    body: { expected_revision: Number(expectedRevision) || 0 },
  });
}

/** Structured code from a trim 409/422 (`revision_mismatch`, `edit_stale`, …). */
export function trimErrorCode(error) {
  const payload = error?.detail;
  const detail = payload?.detail ?? payload;
  if (!detail || typeof detail !== "object") return "";
  return typeof detail.code === "string" ? detail.code : "";
}

/** The current GET payload a trim 409 carries, or null. */
export function trimErrorCurrent(error) {
  const payload = error?.detail;
  const detail = payload?.detail ?? payload;
  const current = detail && typeof detail === "object" ? detail.current : null;
  return current && typeof current === "object" ? current : null;
}

/** Build a new story set. `POST /api/jobs/{id}/clip-sets`. */
export function createClipSet(jobId, { count = 3, order = "source", minS = null, maxS = null, locks = null, banScenes = null } = {}) {
  const body = { count, order };
  if (Number.isFinite(minS) && Number.isFinite(maxS)) Object.assign(body, { min_s: minS, max_s: maxS });
  if (Array.isArray(locks) && locks.length) body.locks = locks;
  if (Array.isArray(banScenes) && banScenes.length) body.ban_scenes = banScenes;
  return request(jobPath(jobId, "/clip-sets"), {
    method: "POST",
    body,
  });
}

/** Rename or retitle one story without changing its range. */
export function patchClipSet(jobId, setId, stories) {
  return request(jobPath(jobId, `/clip-sets/${encodeURIComponent(setId)}`), {
    method: "PATCH",
    body: { stories },
  });
}

/** Append one custom story from selected scenes. */
export function addStory(jobId, setId, sceneIds, title = "") {
  return request(jobPath(jobId, `/clip-sets/${encodeURIComponent(setId)}/stories`), {
    method: "POST",
    body: { scene_ids: sceneIds, title },
  });
}

/** Show a not-yet-imported video in Finder. */
export function revealPath(path) {
  return request("/api/path/reveal", {
    method: "POST",
    body: { path },
  });
}

/** Remove a moment set that has no stories left. */
export function deleteClipSet(jobId, setId) {
  return request(jobPath(jobId, `/clip-sets/${encodeURIComponent(setId)}`), {
    method: "DELETE",
  });
}

/**
 * Wait for a voice task. The server answers 202 `{state: "running"}` when the
 * work outlasts the request; poll `GET /api/jobs/{id}/voice-tasks/{kind}`
 * until it returns the result (or throws its error).
 */
async function untilVoiceTask(jobId, kind, first, { interval = 2000 } = {}) {
  let result = first;
  while (result && result.kind === kind && (result.state === "queued" || result.state === "running")) {
    await new Promise((resolve) => setTimeout(resolve, interval));
    result = await request(jobPath(jobId, `/voice-tasks/${kind}`), { fresh: true });
  }
  return result;
}

/** Write a voice script for a video with no speech. `POST /api/jobs/{id}/script-brief`. */
export async function writeScriptBrief(jobId, brief, { language = "" } = {}) {
  const first = await request(jobPath(jobId, "/script-brief"), { method: "POST", body: { brief, language } });
  return untilVoiceTask(jobId, "script", first);
}

/** Read a finished video's speech again. `POST /api/jobs/{id}/transcribe`. */
export async function transcribeJob(jobId, { language = "" } = {}) {
  const first = await request(jobPath(jobId, "/transcribe"), { method: "POST", body: { language } });
  return untilVoiceTask(jobId, "transcribe", first);
}

/** Cancel a speech re-read or script. `DELETE /api/jobs/{id}/voice-tasks/{kind}`. */
export function cancelVoiceTask(jobId, kind) {
  return request(jobPath(jobId, `/voice-tasks/${kind}`), { method: "DELETE" });
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
