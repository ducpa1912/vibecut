/**
 * Studio — cloned voices.
 *
 * Studio's own copy, used by Setup (My voice: record or upload the creator's
 * own voice) and the Edit audio layer (clone the open video's speaker). It
 * imports Studio's api/ui modules, not the Voice Room's, so the Voice Room
 * tree can be absent. A clone is a reference sample kept on this Mac; HeyGen
 * Voice Turbo on OpenRouter clones it on every speech request, with the
 * OpenRouter key only.
 *
 * Routes:
 *   GET    /api/voices/clones
 *   POST   /api/voices/clones                 (multipart: file, name, language, consent)
 *   POST   /api/jobs/{id}/voices/clone        (JSON: name, language, consent, start, end)
 *   GET    /api/voices/clones/{voice_id}
 *   PATCH  /api/voices/clones/{voice_id}       (JSON: name)
 *   DELETE /api/voices/clones/{voice_id}
 *   POST   /api/voices/clones/{voice_id}/sample
 *   DELETE /api/voices/tasks/{task}            (cancel a clone in progress)
 */

import { announceChange, request } from "../api.js";
import { el } from "../ui.js";

/** The server's cleaning warning for a new clone, or "" when it was cleaned. */
export function cleaningNote(record) {
  const notes = [];
  for (const text of [record?.warning, ...(Array.isArray(record?.warnings) ? record.warnings : [])]) {
    const line = String(text || "").trim();
    if (line && !notes.includes(line)) notes.push(line);
  }
  if (!notes.length && record?.cleaned === false) {
    notes.push("It uses the raw recording, which was not cleaned.");
  }
  return notes.slice(0, 2).join(" ");
}

export const CONSENT_COPY = {
  me: "This is my own voice, and I agree to send this recording to OpenRouter and HeyGen with each voice line.",
  video: "I am the speaker in this video, or I have their written permission to clone their voice.",
};

const READ_LINES = [
  "Hi, this is my voice for VibeCut. I am reading a few lines so the clone can learn how I sound.",
  "I speak at my normal pace, with my normal energy, the same way I talk in my videos.",
  "Some days I am calm and slow. Other days I get excited, and my voice goes up a little.",
  "Numbers like twenty-four, one hundred and ninety, and two thousand twenty-six should sound natural too.",
  "Thanks for listening. Now let's turn this into something great.",
];

function tokenValue() {
  try {
    return localStorage.getItem("vibecut_token") || "";
  } catch (_) {
    return "";
  }
}

async function detailOf(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
  } catch (_) {
    /* not JSON */
  }
  return `Request failed (${response.status}).`;
}

export function listClones() {
  return request("/api/voices/clones", { fresh: true });
}

export function renameClone(voiceId, name) {
  return request(`/api/voices/clones/${encodeURIComponent(voiceId)}`, { method: "PATCH", body: { name } });
}

export function deleteClone(voiceId) {
  return request(`/api/voices/clones/${encodeURIComponent(voiceId)}`, { method: "DELETE" });
}

export function cloneFromVideo(jobId, body) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/voices/clone`, { method: "POST", body });
}

/** A fresh id for one clone request, so it can be cancelled while it runs. */
export function newVoiceTask() {
  const random = Math.random().toString(36).slice(2, 12);
  return `vt_${Date.now().toString(36)}_${random}`;
}

/**
 * Cancel a clone in progress. The request stops at its next check, answers
 * 409 and saves no voice; a cancel sent before the upload lands still counts.
 */
export function cancelVoiceTask(taskId) {
  return request(`/api/voices/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}

/** True for the server's answer to a cancelled clone. */
export function wasCancelled(error) {
  return Number(error?.status) === 409 || /cancelled/i.test(String(error?.message || ""));
}

/** Start the clean candidate search; a second call returns the running task. */
export function findVoiceCandidates(jobId, { full = false, start = 0, fast = false } = {}) {
  const params = new URLSearchParams();
  if (full) params.set("full", "1");
  if (fast) params.set("fast", "1");
  const offset = Number(start) || 0;
  if (offset > 0) params.set("start", String(offset));
  const query = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/jobs/${encodeURIComponent(jobId)}/voices/candidates${query}`, { method: "POST", body: {} });
}

export function voiceCandidateState(jobId) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/voices/candidates`, { fresh: true });
}

export function cancelVoiceCandidates(jobId) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/voices/candidates`, { method: "DELETE" });
}

export function voiceCandidateAudioUrl(jobId, index) {
  return `/api/jobs/${encodeURIComponent(jobId)}/voices/candidates/${Number(index)}/audio`;
}

/** Multipart upload; `request` only speaks JSON. */
export async function cloneFromFile(file, { name = "", language = "", consent = false, task = "" } = {}) {
  const form = new FormData();
  form.append("file", file, file.name || "my-voice.webm");
  form.append("name", name);
  form.append("language", language);
  form.append("consent", consent ? "true" : "false");
  if (task) form.append("task", task);
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch("/api/voices/clones", {
    method: "POST", headers, credentials: "same-origin", body: form,
  });
  announceChange();
  if (!response.ok) {
    const error = new Error(await detailOf(response));
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/** Detect the language of a recording with local Whisper. */
export async function detectVoiceLanguage(file) {
  const form = new FormData();
  form.append("file", file, file.name || "my-voice.webm");
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch("/api/voices/detect-language", {
    method: "POST", headers, credentials: "same-origin", body: form,
  });
  if (!response.ok) {
    const error = new Error(await detailOf(response));
    error.status = response.status;
    throw error;
  }
  return response.json();
}

let currentPlayer = null;
let pendingSample = null;

/** The error a sample throws when Stop cancels it before it plays. */
export function isStopped(error) {
  return error?.name === "AbortError";
}

async function playSample(path, body) {
  const headers = { "Content-Type": "application/json", Accept: "audio/wav" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  // One sample at a time: a new one, or Stop, cancels the one still being made.
  if (pendingSample) pendingSample.abort();
  const controller = new AbortController();
  pendingSample = controller;
  let blob;
  try {
    const response = await fetch(path, {
      method: "POST", headers, credentials: "same-origin", body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(await detailOf(response));
    blob = await response.blob();
  } catch (error) {
    if (controller.signal.aborted) {
      const stopped = new Error("Stopped.");
      stopped.name = "AbortError";
      throw stopped;
    }
    throw error;
  } finally {
    if (pendingSample === controller) pendingSample = null;
  }
  const url = URL.createObjectURL(blob);
  // One voice at a time: a new sample stops the one already playing.
  if (currentPlayer) currentPlayer.pause();
  const player = new Audio(url);
  currentPlayer = player;
  const done = () => {
    URL.revokeObjectURL(url);
    if (currentPlayer === player) currentPlayer = null;
  };
  player.addEventListener("ended", done, { once: true });
  player.addEventListener("error", done, { once: true });
  try {
    await player.play();
  } catch (error) {
    done();
    throw error;
  }
  return player;
}

/** Speak a short line in a clone and play it. Resolves once playback starts. */
export function playClone(voiceId, text = "") {
  return playSample(`/api/voices/clones/${encodeURIComponent(voiceId)}/sample`, { text });
}

/** Speak a short line in any voice on this machine. */
export function playVoice(engine, voice, text = "", rate = 1) {
  return playSample("/api/voices/sample", { engine, voice, text, rate });
}

/** Stop the voice playing now, and cancel a sample still being made. */
export function stopPlayback() {
  if (pendingSample) pendingSample.abort();
  pendingSample = null;
  if (currentPlayer) currentPlayer.pause();
  currentPlayer = null;
}

/**
 * The Setup "My voice" panel. Owns its own node and state so a recording in
 * progress survives the Setup screen re-rendering around it.
 * `list: false` leaves the cloned voices out, for a page that lists them itself.
 * @param {{ hasKey: () => boolean, onChange?: () => void, sampleText?: () => string, title?: string, list?: boolean }} options
 */
export function createMyVoicePanel({ hasKey, onChange = () => {}, sampleText = () => "", title = "My voice", list = true, description = "Clone your own voice once, then use it for Voice-over and Dub. Give 30 s to 3 min of clear speech; HeyGen Voice Turbo on OpenRouter speaks in it. The sample stays on this Mac and is sent with each voice line." }) {
  const node = el("div", { class: "st-setup-section st-voice-clone" });
  let clones = [];
  let loaded = false;
  let busy = "";
  let notice = "";
  let noticeTone = "";
  let recorder = null;
  let stream = null;
  let chunks = [];
  let recordStart = 0;
  let timer = 0;
  let recording = null;
  let recordingUrl = "";
  let name = "My voice";
  let language = "";
  let languageAuto = true;
  let detecting = false;
  let detectToken = 0;
  let consent = false;
  let task = "";
  let disposed = false;

  function setNotice(message, tone = "") {
    notice = message || "";
    noticeTone = tone;
  }

  async function load() {
    try {
      const result = await listClones();
      clones = Array.isArray(result?.voices) ? result.voices : [];
    } catch (error) {
      setNotice(error?.message || "Could not read cloned voices.", "bad");
    }
    loaded = true;
    render();
  }

  function stopTracks() {
    if (stream) for (const track of stream.getTracks()) track.stop();
    stream = null;
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setNotice("This browser cannot record. Upload a recording instead.", "bad");
      render();
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (_) {
      setNotice("Microphone access was refused. Allow it in the browser, or upload a recording.", "bad");
      render();
      return;
    }
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      stopTracks();
      window.clearInterval(timer);
      const type = recorder?.mimeType || "audio/webm";
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(chunks, { type });
      if (recordingUrl) URL.revokeObjectURL(recordingUrl);
      recording = new File([blob], `my-voice.${ext}`, { type });
      recordingUrl = URL.createObjectURL(blob);
      recorder = null;
      setNotice(`Recorded ${Math.round((Date.now() - recordStart) / 1000)}s. Listen back, then clone it.`, "ok");
      if (!disposed) render();
      void detectLanguageFor(recording);
    });
    recordStart = Date.now();
    recorder.start(1000);
    timer = window.setInterval(() => {
      const seconds = (Date.now() - recordStart) / 1000;
      const clock = node.querySelector("[data-clock]");
      if (clock) clock.textContent = `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")} / 3:00`;
      if (seconds >= 180 && recorder?.state === "recording") recorder.stop();
    }, 250);
    setNotice("Recording. Read the lines below in your normal voice.", "");
    render();
  }

  function stopRecording() {
    if (recorder?.state === "recording") recorder.stop();
  }

  function useFile(file) {
    if (!file) return;
    if (recordingUrl) URL.revokeObjectURL(recordingUrl);
    recording = file;
    recordingUrl = URL.createObjectURL(file);
    setNotice(`Using ${file.name}.`, "ok");
    render();
    void detectLanguageFor(file);
  }

  async function detectLanguageFor(file) {
    if (!file || !languageAuto) return;
    const token = ++detectToken;
    detecting = true;
    setNotice("Detecting the language…", "");
    if (!disposed) render();
    try {
      const result = await detectVoiceLanguage(file);
      if (token !== detectToken || disposed || !languageAuto) return;
      const code = String(result?.language || "").trim().toLowerCase();
      if (!code) throw new Error("No language detected.");
      language = code;
      setNotice(`Detected ${code.toUpperCase()}. You can change it.`, "ok");
    } catch (_) {
      if (token !== detectToken) return;
      setNotice("Could not detect the language. Pick one manually.", "bad");
    } finally {
      if (token === detectToken) {
        detecting = false;
        if (!disposed) render();
      }
    }
  }

  async function submit() {
    if (!recording) {
      setNotice("Record or upload your voice first.", "bad");
      render();
      return;
    }
    if (!consent) {
      setNotice("Tick the box to confirm this is your own voice.", "bad");
      render();
      return;
    }
    busy = "clone";
    task = newVoiceTask();
    setNotice("Preparing your voice sample…", "");
    render();
    try {
      const record = await cloneFromFile(recording, { name, language, consent, task });
      clones = [record, ...clones.filter((item) => item.voice_id !== record.voice_id)];
      recording = null;
      if (recordingUrl) URL.revokeObjectURL(recordingUrl);
      recordingUrl = "";
      consent = false;
      const note = cleaningNote(record);
      setNotice(
        `Your voice is ready.${note ? ` ${note}` : ""} Press Play to hear it, or pick it under HeyGen Voice Turbo in any voice picker.`,
        note ? "" : "ok",
      );
      onChange();
    } catch (error) {
      if (wasCancelled(error)) setNotice("Cancelled. No voice was cloned.", "");
      else setNotice(error?.message || "Could not clone the voice.", "bad");
    } finally {
      busy = "";
      task = "";
      if (!disposed) render();
    }
  }

  async function cancelClone() {
    if (busy !== "clone" || !task) return;
    busy = "cancel";
    setNotice("Cancelling…", "");
    render();
    try {
      await cancelVoiceTask(task);
    } catch (error) {
      setNotice(error?.message || "Could not cancel the clone.", "bad");
      busy = "clone";
      render();
    }
  }

  async function play(item) {
    busy = `play:${item.voice_id}`;
    render();
    try {
      await playClone(item.voice_id, sampleText());
      setNotice(`Playing ${item.name}.`, "ok");
    } catch (error) {
      setNotice(error?.message || "Could not play this voice.", "bad");
    } finally {
      busy = "";
      if (!disposed) render();
    }
  }

  async function remove(item) {
    if (!window.confirm(`Delete “${item.name}”? Its sample is removed from this Mac, and edits that use it fall back to another voice.`)) return;
    busy = `delete:${item.voice_id}`;
    render();
    try {
      await deleteClone(item.voice_id);
      clones = clones.filter((row) => row.voice_id !== item.voice_id);
      setNotice("Voice deleted.", "ok");
      onChange();
    } catch (error) {
      setNotice(error?.message || "Could not delete the voice.", "bad");
    } finally {
      busy = "";
      if (!disposed) render();
    }
  }

  function cloneRow(item) {
    const playButton = el("button", {
      class: "st-btn st-btn-ghost st-btn-small", type: "button",
      text: busy === `play:${item.voice_id}` ? "Speaking…" : "Play",
      disabled: Boolean(busy),
    });
    playButton.addEventListener("click", () => { void play(item); });
    const deleteButton = el("button", {
      class: "st-btn st-btn-quiet st-btn-small", type: "button",
      text: busy === `delete:${item.voice_id}` ? "Deleting…" : "Delete",
      disabled: Boolean(busy),
    });
    deleteButton.addEventListener("click", () => { void remove(item); });
    return el("div", { class: "st-voice-clone-row" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: item.name || "Cloned voice" }),
        item.sample_seconds ? el("span", { class: "st-mono st-hint", text: `${Math.round(item.sample_seconds)}s sample` }) : null,
        el("span", { class: "st-chip", text: item.source === "video" ? "From a video" : "My voice" }),
        item.language ? el("span", { class: "st-mono st-hint", text: item.language }) : null,
      ]),
      el("div", { class: "st-setup-key-actions" }, [playButton, deleteButton]),
    ]);
  }

  function recorderBlock() {
    const isRecording = recorder?.state === "recording";
    const record = el("button", {
      class: `st-btn ${isRecording ? "st-btn-primary" : "st-btn-ghost"} st-btn-small`,
      type: "button",
      text: isRecording ? "Stop recording" : (recording ? "Record again" : "Record my voice"),
      disabled: busy === "clone",
    });
    record.addEventListener("click", () => {
      if (isRecording) stopRecording();
      else void startRecording();
    });
    const upload = el("input", {
      type: "file",
      accept: "audio/*,video/mp4,video/quicktime,.wav,.mp3,.m4a,.ogg,.webm,.flac",
      "aria-label": "Upload a recording of your voice",
      disabled: isRecording || busy === "clone",
    });
    upload.addEventListener("change", () => useFile(upload.files?.[0]));

    const block = el("div", { class: "st-voice-clone-recorder" }, [
      el("div", { class: "st-setup-key-form" }, [
        record,
        isRecording ? el("span", { class: "st-mono st-hint", "data-clock": "", text: "0:00 / 3:00" }) : null,
        el("span", { class: "st-hint", text: "or" }),
        upload,
      ]),
    ]);
    if (isRecording) {
      block.append(el("ol", { class: "st-voice-clone-script" }, READ_LINES.map((line) => el("li", { text: line }))));
    }
    if (recordingUrl && !isRecording) {
      block.append(el("audio", { controls: true, src: recordingUrl, class: "st-voice-clone-audio" }));
    }
    return block;
  }

  function formBlock() {
    const nameInput = el("input", { type: "text", maxLength: 64, value: name, "aria-label": "Voice name" });
    nameInput.addEventListener("input", () => { name = nameInput.value; });
    const lang = el("select", { "aria-label": "Recording language" }, [
      el("option", { value: "", text: "Detect", selected: !language }),
      ...["en", "vi", "zh", "ja", "ko", "es", "fr", "de", "pt", "it", "ru", "hi", "id", "th"].map(
        (code) => el("option", { value: code, text: code, selected: code === language }),
      ),
    ]);
    lang.addEventListener("change", () => {
      language = lang.value;
      languageAuto = !language;
      detectToken += 1;
      detecting = false;
      if (languageAuto && recording) void detectLanguageFor(recording);
      else render();
    });
    const languageHint = el("span", {
      class: "st-hint",
      text: detecting
        ? "Detecting…"
        : languageAuto && language
          ? "Detected from the recording."
          : "Auto-detects after record or upload.",
    });
    const tick = el("input", { type: "checkbox", checked: consent, id: "st-voice-consent-me" });
    tick.addEventListener("change", () => { consent = Boolean(tick.checked); render(); });
    const cloning = busy === "clone" || busy === "cancel";
    const go = el("button", {
      class: "st-btn st-btn-primary st-btn-small", type: "button",
      text: detecting ? "Detecting language…" : cloning ? "Cloning…" : "Clone my voice",
      disabled: Boolean(busy) || detecting || !recording || !consent || recorder?.state === "recording",
    });
    go.addEventListener("click", () => { void submit(); });
    const stop = cloning ? el("button", {
      class: "st-btn st-btn-quiet st-btn-small", type: "button",
      text: busy === "cancel" ? "Cancelling…" : "Cancel",
      disabled: busy === "cancel",
    }) : null;
    stop?.addEventListener("click", () => { void cancelClone(); });
    return el("div", { class: "st-voice-clone-form" }, [
      el("div", { class: "st-setup-key-form" }, [
        el("label", { class: "st-field" }, [el("span", { text: "Name" }), nameInput]),
        el("label", { class: "st-field" }, [el("span", { text: "Language" }), lang, languageHint]),
      ]),
      el("label", { class: "st-voice-clone-consent", for: "st-voice-consent-me" }, [
        tick, el("span", { text: CONSENT_COPY.me }),
      ]),
      el("div", { class: "st-setup-key-actions" }, [go, stop]),
    ]);
  }

  function render() {
    if (disposed) return;
    const head = el("div", { class: "st-setup-section-head" }, [
      el("h3", { text: title }),
    ]);
    if (description) {
      head.append(el("p", { class: "st-hint", text: description }));
    }
    node.replaceChildren(head);
    if (!hasKey()) {
      node.append(el("p", { class: "st-hint", text: "Add an OpenRouter key under Keys to clone a voice." }));
    } else {
      node.append(recorderBlock(), formBlock());
    }
    if (notice) {
      const line = el("p", { class: "st-status", role: "status", text: notice });
      line.dataset.tone = noticeTone;
      node.append(line);
    }
    if (!list) return;
    if (!loaded) {
      node.append(el("p", { class: "st-hint", text: "Reading cloned voices…" }));
    } else if (clones.length) {
      node.append(el("div", { class: "st-voice-clone-list" }, clones.map(cloneRow)));
    } else if (hasKey()) {
      node.append(el("p", { class: "st-hint", text: "No cloned voices yet." }));
    }
  }

  render();
  if (list) void load();

  return {
    node,
    render,
    refresh: load,
    dispose() {
      disposed = true;
      if (recorder?.state === "recording") recorder.stop();
      stopTracks();
      window.clearInterval(timer);
      if (recordingUrl) URL.revokeObjectURL(recordingUrl);
    },
  };
}
