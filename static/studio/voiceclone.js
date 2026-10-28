/**
 * Studio — cloned voices.
 *
 * Shared by Setup (My voice: record or upload the creator's own voice) and the
 * Edit audio layer (clone the open video's speaker). A clone is made on
 * HeyGen with the creator's HeyGen key and is then spoken by HeyGen Voice
 * Turbo on OpenRouter like any other HeyGen voice.
 *
 * Routes:
 *   GET    /api/voices/clones
 *   POST   /api/voices/clones                 (multipart: file, name, language, consent)
 *   POST   /api/jobs/{id}/voices/clone        (JSON: name, language, consent, start, end)
 *   GET    /api/voices/clones/{voice_id}      (status, preview URL)
 *   DELETE /api/voices/clones/{voice_id}
 *   POST   /api/voices/clones/{voice_id}/sample
 */

import { invalidateReadCache, request } from "./api.js";
import { el } from "./ui.js";

export const CONSENT_COPY = {
  me: "This is my own voice, and I agree to send this recording to HeyGen to make a clone.",
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

export function cloneStatus(voiceId) {
  return request(`/api/voices/clones/${encodeURIComponent(voiceId)}`);
}

export function deleteClone(voiceId) {
  return request(`/api/voices/clones/${encodeURIComponent(voiceId)}`, { method: "DELETE" });
}

export function cloneFromVideo(jobId, body) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/voices/clone`, { method: "POST", body });
}

/** Multipart upload; `request` only speaks JSON. */
export async function cloneFromFile(file, { name = "", language = "", consent = false } = {}) {
  const form = new FormData();
  form.append("file", file, file.name || "my-voice.webm");
  form.append("name", name);
  form.append("language", language);
  form.append("consent", consent ? "true" : "false");
  const headers = { Accept: "application/json" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch("/api/voices/clones", {
    method: "POST", headers, credentials: "same-origin", body: form,
  });
  invalidateReadCache();
  if (!response.ok) throw new Error(await detailOf(response));
  return response.json();
}

/** Speak a short line in a clone and play it. Resolves once playback starts. */
export async function playClone(voiceId, text = "") {
  const headers = { "Content-Type": "application/json", Accept: "audio/wav" };
  const token = tokenValue();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`/api/voices/clones/${encodeURIComponent(voiceId)}/sample`, {
    method: "POST", headers, credentials: "same-origin", body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(await detailOf(response));
  const url = URL.createObjectURL(await response.blob());
  const player = new Audio(url);
  const done = () => URL.revokeObjectURL(url);
  player.addEventListener("ended", done, { once: true });
  player.addEventListener("error", done, { once: true });
  await player.play();
  return player;
}

export function statusChip(status) {
  const value = String(status || "PENDING").toUpperCase();
  if (value === "ACTIVE") return el("span", { class: "st-chip st-chip-ok", text: "Ready" });
  if (value === "FAILED") return el("span", { class: "st-chip st-chip-bad", text: "Failed" });
  return el("span", { class: "st-chip st-chip-busy", text: "Making…" });
}

const FAILURES = {
  INVALID_AUDIO: "HeyGen could not read the recording.",
  PREPROCESSING_FAILED: "The recording did not pass HeyGen's checks. Try a cleaner recording, or set the language.",
  DESIGN_FAILED: "HeyGen could not build a voice from this recording. Try a different one.",
  INTERNAL_ERROR: "HeyGen had an internal error. Try again.",
};

export function failureCopy(reason) {
  return FAILURES[String(reason || "")] || (reason ? String(reason) : "");
}

/** Poll a PENDING clone until it settles; calls `onUpdate` with each record. */
export async function pollClone(voiceId, onUpdate, { tries = 20, every = 3000 } = {}) {
  for (let index = 0; index < tries; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, every));
    let record;
    try {
      record = await cloneStatus(voiceId);
    } catch (_) {
      continue;
    }
    onUpdate(record);
    if (record?.status && record.status !== "PENDING") return record;
  }
  return null;
}

/**
 * The Setup "My voice" panel. Owns its own node and state so a recording in
 * progress survives the Setup screen re-rendering around it.
 * @param {{ hasKey: () => boolean, onChange?: () => void }} options
 */
export function createMyVoicePanel({ hasKey, onChange = () => {} }) {
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
  let consent = false;
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
    for (const item of clones) {
      if (item.status === "PENDING") void watch(item.voice_id);
    }
  }

  async function watch(voiceId) {
    await pollClone(voiceId, (record) => {
      clones = clones.map((item) => (item.voice_id === voiceId ? { ...item, ...record } : item));
      if (!disposed) render();
    });
    onChange();
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
    setNotice("Sending your recording to HeyGen…", "");
    render();
    try {
      const record = await cloneFromFile(recording, { name, language, consent });
      clones = [record, ...clones.filter((item) => item.voice_id !== record.voice_id)];
      recording = null;
      if (recordingUrl) URL.revokeObjectURL(recordingUrl);
      recordingUrl = "";
      consent = false;
      if (record.status === "ACTIVE") {
        setNotice("Your voice is ready. Pick it under HeyGen Voice Turbo in any voice picker.", "ok");
      } else if (record.status === "FAILED") {
        setNotice(failureCopy(record.failure_reason) || "HeyGen could not clone this recording.", "bad");
      } else {
        setNotice("HeyGen is still making your voice. This list updates when it is ready.", "");
        void watch(record.voice_id);
      }
      onChange();
    } catch (error) {
      setNotice(error?.message || "Could not clone the voice.", "bad");
    } finally {
      busy = "";
      if (!disposed) render();
    }
  }

  async function play(item) {
    busy = `play:${item.voice_id}`;
    render();
    try {
      await playClone(item.voice_id);
      setNotice(`Playing ${item.name}.`, "ok");
    } catch (error) {
      setNotice(error?.message || "Could not play this voice.", "bad");
    } finally {
      busy = "";
      if (!disposed) render();
    }
  }

  async function remove(item) {
    if (!window.confirm(`Delete “${item.name}”? It is removed from HeyGen too, and edits that use it fall back to another voice.`)) return;
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
      disabled: Boolean(busy) || item.status !== "ACTIVE",
    });
    playButton.addEventListener("click", () => { void play(item); });
    const deleteButton = el("button", {
      class: "st-btn st-btn-quiet st-btn-small", type: "button",
      text: busy === `delete:${item.voice_id}` ? "Deleting…" : "Delete",
      disabled: Boolean(busy),
    });
    deleteButton.addEventListener("click", () => { void remove(item); });
    const failure = item.status === "FAILED" ? failureCopy(item.failure_reason) : "";
    return el("div", { class: "st-voice-clone-row" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: item.name || "Cloned voice" }),
        statusChip(item.status),
        el("span", { class: "st-chip", text: item.source === "video" ? "From a video" : "My voice" }),
        item.language ? el("span", { class: "st-mono st-hint", text: item.language }) : null,
      ]),
      failure ? el("p", { class: "st-error", text: failure }) : null,
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
    lang.addEventListener("change", () => { language = lang.value; });
    const tick = el("input", { type: "checkbox", checked: consent, id: "st-voice-consent-me" });
    tick.addEventListener("change", () => { consent = Boolean(tick.checked); render(); });
    const go = el("button", {
      class: "st-btn st-btn-primary st-btn-small", type: "button",
      text: busy === "clone" ? "Cloning…" : "Clone my voice",
      disabled: Boolean(busy) || !recording || !consent || recorder?.state === "recording",
    });
    go.addEventListener("click", () => { void submit(); });
    return el("div", { class: "st-voice-clone-form" }, [
      el("div", { class: "st-setup-key-form" }, [
        el("label", { class: "st-field" }, [el("span", { text: "Name" }), nameInput]),
        el("label", { class: "st-field" }, [el("span", { text: "Language" }), lang]),
      ]),
      el("label", { class: "st-voice-clone-consent", for: "st-voice-consent-me" }, [
        tick, el("span", { text: CONSENT_COPY.me }),
      ]),
      el("div", { class: "st-setup-key-actions" }, [go]),
    ]);
  }

  function render() {
    if (disposed) return;
    node.replaceChildren(el("div", { class: "st-setup-section-head" }, [
      el("h3", { text: "My voice" }),
      el("p", {
        class: "st-hint",
        text: "Clone your own voice once, then use it for Voice-over and Dub. HeyGen makes the clone from 30 s to 3 min of clear speech; it is spoken by HeyGen Voice Turbo on OpenRouter.",
      }),
    ]));
    if (!hasKey()) {
      node.append(el("p", { class: "st-hint", text: "Add a HeyGen API key under Keys to clone a voice. For OpenRouter to speak your clone, add the same HeyGen key to OpenRouter under Integrations (BYOK); otherwise VibeCut speaks it straight on HeyGen." }));
    } else {
      node.append(recorderBlock(), formBlock());
    }
    if (notice) {
      const line = el("p", { class: "st-status", role: "status", text: notice });
      line.dataset.tone = noticeTone;
      node.append(line);
    }
    if (!loaded) {
      node.append(el("p", { class: "st-hint", text: "Reading cloned voices…" }));
    } else if (clones.length) {
      node.append(el("div", { class: "st-voice-clone-list" }, clones.map(cloneRow)));
    } else if (hasKey()) {
      node.append(el("p", { class: "st-hint", text: "No cloned voices yet." }));
    }
  }

  render();
  void load();

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
