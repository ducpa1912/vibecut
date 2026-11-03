/**
 * Editor API calls.
 *
 * Every path below is an existing route: the Wave-1 Edit CRUD API, the
 * caption-track API, and the frame/proxy routes owned by the render track.
 * There is no new endpoint and no network call outside this local server.
 */

import { request } from "../api.js";

export { ApiError } from "../api.js";

const TOKEN_KEY = "vibecut_token";

function jobRoot(jobId) {
  return `/api/jobs/${encodeURIComponent(jobId)}`;
}

function editRoot(jobId, editId) {
  return `${jobRoot(jobId)}/edits/${encodeURIComponent(editId)}`;
}

function tokenValue() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch (_) {
    return "";
  }
}

/**
 * Media elements cannot send an Authorization header. Keep the read cookie in
 * step with the token, exactly like the Studio API client does for thumbnails.
 */
export function syncMediaCookie() {
  const token = tokenValue();
  const value = token ? encodeURIComponent(token) : "";
  const expiry = token ? "" : "; Max-Age=0";
  document.cookie = `vibecut_token=${value}; Path=/; SameSite=Strict${expiry}`;
}

export function framePath(jobId, editId, time, quality = "draft") {
  const t = Math.max(0, Number(time) || 0).toFixed(3);
  return `${editRoot(jobId, editId)}/frame?t=${encodeURIComponent(t)}&quality=${encodeURIComponent(quality)}`;
}

export function proxyPath(jobId, editId) {
  return `${editRoot(jobId, editId)}/proxy`;
}

/** `GET /api/jobs/{id}/edits/current`. Returns null for 404. */
export async function getCurrentEdit(jobId, setId, storyId, aspect) {
  const params = new URLSearchParams({ set_id: setId, story_id: storyId, aspect });
  try {
    return await request(`${jobRoot(jobId)}/edits/current?${params.toString()}`);
  } catch (error) {
    if (error?.status === 404) return null;
    throw error;
  }
}

/** `GET /api/jobs/{id}/edits/{edit_id}`. */
export function getEdit(jobId, editId) {
  return request(editRoot(jobId, editId));
}

/** `POST /api/jobs/{id}/edits`. Creates, or updates the current story edit. */
export function createEdit(jobId, payload) {
  return request(`${jobRoot(jobId)}/edits`, { method: "POST", body: payload });
}

/** `PATCH /api/jobs/{id}/edits/{edit_id}`. A stale head returns 409. */
export function patchEdit(jobId, editId, layers, { keepalive = false } = {}) {
  return request(editRoot(jobId, editId), { method: "PATCH", body: layers, keepalive });
}

/** `POST /api/jobs/{id}/edits/{edit_id}/undo`. Creates a new head. */
export function undoEdit(jobId, editId) {
  return request(`${editRoot(jobId, editId)}/undo`, { method: "POST", body: {} });
}

/** `POST /api/jobs/{id}/edits/{edit_id}/restore`. Restores one version. */
export function restoreEdit(jobId, editId, version) {
  return request(`${editRoot(jobId, editId)}/restore`, {
    method: "POST",
    body: { version },
  });
}

/** `GET /api/jobs/{id}/edits/{edit_id}/versions`. */
export function listVersions(jobId, editId) {
  return request(`${editRoot(jobId, editId)}/versions`);
}

/** `GET /api/jobs/{id}/transcript` for the full timed transcript. */
export function getTranscript(jobId) {
  return request(`${jobRoot(jobId)}/transcript`);
}

/** Translate the full transcript once for one target language. */
export function translateTranscript(jobId, { target, source = "", provider = "auto", force = false }) {
  return request(`${jobRoot(jobId)}/transcript/translate`, {
    method: "POST",
    body: { target, source, provider, force: Boolean(force) },
  });
}

/** Write the copy for this moment through the existing script route. */
export function writeMomentCopy(jobId, { target, clips, translate = null, mode = "smooth", overrides = {} }) {
  return request(`${jobRoot(jobId)}/audio/script`, {
    method: "POST",
    body: {
      target,
      clips,
      translate: translate || null,
      provider: "auto",
      mode,
      rewrite_provider: "auto",
      overrides,
    },
  });
}

/** `GET /api/jobs/{id}/captions/{track_id}`. Returns null for 404. */
export async function getCaptionTrack(jobId, trackId) {
  try {
    return await request(`${jobRoot(jobId)}/captions/${encodeURIComponent(trackId)}`);
  } catch (error) {
    if (error?.status === 404) return null;
    throw error;
  }
}

/** `POST /api/jobs/{id}/captions` for one story. */
export function buildCaptionTrack(jobId, { setId, storyId, styleId = "clean" }) {
  return request(`${jobRoot(jobId)}/captions`, {
    method: "POST",
    body: {
      target: 30,
      set_id: setId,
      story_id: storyId,
      style_id: styleId,
    },
  });
}

/**
 * `POST /api/jobs/{id}/auto-subtitles`. Builds one caption track per story.
 * The route writes tracks only; the caller attaches each returned track to
 * that story's Edit.
 */
export function autoSubtitles(jobId, { setId, aspect = "9:16", styleId = "clean", storyIds = [] } = {}) {
  return request(`${jobRoot(jobId)}/auto-subtitles`, {
    method: "POST",
    body: {
      set_id: setId,
      aspect,
      style_id: styleId || "clean",
      story_ids: Array.isArray(storyIds) ? storyIds : [],
    },
  });
}

/**
 * `PATCH /api/jobs/{id}/captions/{track_id}`.
 * `style` is the full style object; `cues` is optional.
 */
export function patchCaptionTrack(jobId, trackId, { style = null, cues = null } = {}) {
  const body = {};
  if (style) body.style = style;
  if (cues) body.cues = cues;
  return request(`${jobRoot(jobId)}/captions/${encodeURIComponent(trackId)}`, {
    method: "PATCH",
    body,
  });
}

/**
 * Fetch one preview frame. The response body is JPEG; status codes matter:
 * 404 unknown, 409 stale head, 422 impossible time.
 */
export async function fetchFrame(path, { signal } = {}) {
  syncMediaCookie();
  const headers = { Accept: "image/jpeg" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(path, {
    method: "GET",
    headers,
    credentials: "same-origin",
    signal,
  });
}
