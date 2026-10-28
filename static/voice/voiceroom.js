/**
 * Voice Room — every voice this machine can speak, and voice cloning.
 *
 * A page of its own (`/voices`), opened from the Voice Room button beside
 * Open Studio. It lists each voice engine with the voices it has here (Apple
 * voices, Kokoro, cloud engines with a saved key, HeyGen Voice Turbo and the
 * creator's clones), plays any voice with a test line, and clones a voice from
 * a recording, a file, or a video already in the library.
 *
 * Routes:
 *   GET  /api/voices/catalog
 *   POST /api/voices/sample
 *   GET  /api/settings, GET /api/jobs
 *   /api/voices/clones and /api/jobs/{id}/voices/clone (voiceclone.js)
 */

import { listJobs, request } from "./api.js";
import { el, formatDuration } from "./ui.js";
import {
  CONSENT_COPY,
  cloneFromVideo,
  createMyVoicePanel,
  playVoice,
  stopPlayback,
} from "./voiceclone.js";

const DEFAULT_LINE = "Hi, this is how I sound in VibeCut. Short, clear and easy to follow.";

const ENGINE_NOTES = {
  say: "On this Mac · offline",
  kokoro: "On this Mac · Voice Pack",
  heygen: "OpenRouter · free until 30 Nov 2026 · voice cloning",
  fish: "OpenRouter",
  gemini: "OpenRouter",
  minimax: "MiniMax key",
  elevenlabs: "ElevenLabs key",
};

const root = document.getElementById("studio-root");

let catalog = null;
let settings = null;
let loading = true;
let error = "";
let notice = "";
let noticeTone = "";
let testLine = DEFAULT_LINE;
let rate = 1;
let query = "";
let language = "";
let playing = "";
let jobs = [];
let videoJob = "";
let videoName = "";
let videoStart = "";
let videoEnd = "";
let videoConsent = false;
let videoBusy = false;
const collapsed = new Set(["say"]);

const myVoice = createMyVoicePanel({
  hasKey: () => Boolean(settings?.secrets?.openrouter),
  onChange: () => { void loadCatalog(); },
  sampleText: () => testLine,
  title: "Clone my voice",
});

function setNotice(message, tone = "") {
  notice = message || "";
  noticeTone = tone;
}

function langOf(voice) {
  return String(voice?.lang || "").toLowerCase().replace("_", "-").split("-")[0] || "multi";
}

function matches(voice) {
  if (language && langOf(voice) !== language && langOf(voice) !== "multi") return false;
  if (!query) return true;
  const hay = `${voice.name || ""} ${voice.id || ""} ${voice.lang || ""}`.toLowerCase();
  return hay.includes(query.toLowerCase());
}

async function loadCatalog() {
  try {
    catalog = await request("/api/voices/catalog", { fresh: true });
  } catch (cause) {
    error = cause?.message || "Could not read the voices on this machine.";
  }
  render();
}

async function load() {
  loading = true;
  error = "";
  render();
  try {
    const [state, voices, recent] = await Promise.all([
      request("/api/settings"),
      request("/api/voices/catalog", { fresh: true }),
      listJobs({ limit: 30 }).catch(() => ({ jobs: [] })),
    ]);
    settings = state;
    catalog = voices;
    jobs = (recent?.jobs || []).filter((job) => job.status === "ready" && !job.source_deleted && !job.source_missing);
  } catch (cause) {
    error = cause?.message || "Could not open the Voice Room.";
  } finally {
    loading = false;
    render();
  }
}

async function play(engine, voice, label) {
  const key = `${engine}:${voice}`;
  if (playing) return;
  playing = key;
  setNotice(`Making a sample of ${label}…`);
  render();
  try {
    await playVoice(engine, voice, testLine, rate);
    setNotice(`Playing ${label}.`, "ok");
  } catch (cause) {
    setNotice(cause?.message || `Could not play ${label}.`, "bad");
  } finally {
    playing = "";
    render();
  }
}

/** The server's cleaning warning for a new clone, or "" when it was cleaned. */
function cleaningNote(record) {
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

async function cloneVideo() {
  if (!videoJob || !videoConsent || videoBusy) return;
  const body = { name: videoName.trim(), consent: true };
  const start = Number.parseFloat(videoStart);
  const end = Number.parseFloat(videoEnd);
  if (Number.isFinite(start) && start >= 0) body.start = start;
  if (Number.isFinite(end) && end > 0) body.end = end;
  videoBusy = true;
  setNotice("Cutting the speech out of the video…");
  render();
  try {
    const record = await cloneFromVideo(videoJob, body);
    videoConsent = false;
    videoName = "";
    const note = cleaningNote(record);
    setNotice(
      `Cloned “${record.name}”${record.used_transcript ? " from the transcript's speech" : ""}.${note ? ` ${note}` : ""} It is listed under HeyGen Voice Turbo.`,
      note ? "" : "ok",
    );
    await myVoice.refresh();
    await loadCatalog();
  } catch (cause) {
    setNotice(cause?.message || "Could not clone the video voice.", "bad");
  } finally {
    videoBusy = false;
    render();
  }
}

// ------------------------------------------------------------------ views

function header() {
  const studio = el("a", { class: "st-btn st-btn-ghost st-btn-small", href: "/?studio=1", text: "Open Studio" });
  const refresh = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Refresh" });
  refresh.addEventListener("click", () => { void load(); });
  return el("header", { class: "vr-top" }, [
    el("a", { class: "vr-brand", href: "/", text: "VibeCut" }),
    el("span", { class: "vr-room", text: "Voice Room" }),
    el("div", { class: "vr-top-actions" }, [refresh, studio]),
  ]);
}

function testCard() {
  const line = el("textarea", { rows: 2, maxLength: 300, value: testLine, "aria-label": "Test line" });
  line.addEventListener("input", () => { testLine = line.value.trim() || DEFAULT_LINE; });
  const speed = el("input", { type: "range", min: "0.7", max: "1.4", step: "0.05", value: String(rate), "aria-label": "Rate" });
  const speedValue = el("span", { class: "st-mono st-hint", text: `${rate.toFixed(2)}×` });
  speed.addEventListener("input", () => {
    rate = Number(speed.value) || 1;
    speedValue.textContent = `${rate.toFixed(2)}×`;
  });
  const stop = el("button", { class: "st-btn st-btn-quiet st-btn-small", type: "button", text: "Stop" });
  stop.addEventListener("click", () => stopPlayback());
  return el("section", { class: "st-card vr-card" }, [
    el("div", { class: "st-card-head" }, [
      el("h2", { text: "Test line" }),
      el("p", { class: "st-hint", text: "Every Play button speaks this line." }),
    ]),
    line,
    el("div", { class: "vr-rate" }, [el("span", { class: "st-hint", text: "Rate" }), speed, speedValue, stop]),
  ]);
}

function videoCard() {
  const card = el("section", { class: "st-card vr-card" }, [
    el("div", { class: "st-card-head" }, [
      el("h2", { text: "Clone a voice from a video" }),
      el("p", { class: "st-hint", text: "Pick a video already in VibeCut. Up to 3 minutes of its speech becomes the voice sample; the transcript picks the speech when there is one. To use a video file instead, upload it under Clone my voice." }),
    ]),
  ]);
  if (!catalog?.clone_available) {
    card.append(el("p", { class: "st-hint", text: "Add an OpenRouter key in Setup to clone a voice." }));
    return card;
  }
  if (!jobs.length) {
    card.append(el("p", { class: "st-hint", text: "No finished videos yet. Import one in Studio first." }));
    return card;
  }
  const select = el("select", { "aria-label": "Video" }, [
    el("option", { value: "", text: "Choose a video", selected: !videoJob }),
    ...jobs.map((job) => el("option", {
      value: job.id,
      text: `${job.name || job.id} · ${formatDuration(job.duration)}`,
      selected: job.id === videoJob,
    })),
  ]);
  select.addEventListener("change", () => { videoJob = select.value; render(); });
  const name = el("input", { type: "text", maxLength: 64, value: videoName, placeholder: "Video voice", "aria-label": "Voice name" });
  name.addEventListener("input", () => { videoName = name.value; });
  const start = el("input", { type: "number", min: "0", step: "1", value: videoStart, placeholder: "auto", "aria-label": "From (seconds)" });
  start.addEventListener("input", () => { videoStart = start.value; });
  const end = el("input", { type: "number", min: "0", step: "1", value: videoEnd, placeholder: "auto", "aria-label": "To (seconds)" });
  end.addEventListener("input", () => { videoEnd = end.value; });
  const tick = el("input", { type: "checkbox", checked: videoConsent, id: "vr-consent-video" });
  tick.addEventListener("change", () => { videoConsent = Boolean(tick.checked); render(); });
  const go = el("button", {
    class: "st-btn st-btn-primary st-btn-small", type: "button",
    text: videoBusy ? "Cloning…" : "Clone this voice",
    disabled: videoBusy || !videoJob || !videoConsent,
  });
  go.addEventListener("click", () => { void cloneVideo(); });
  card.append(
    el("label", { class: "st-field" }, [el("span", { text: "Video" }), select]),
    el("div", { class: "vr-row" }, [
      el("label", { class: "st-field" }, [el("span", { text: "Name" }), name]),
      el("label", { class: "st-field" }, [el("span", { text: "From (s)" }), start]),
      el("label", { class: "st-field" }, [el("span", { text: "To (s)" }), end]),
    ]),
    el("label", { class: "st-voice-clone-consent", for: "vr-consent-video" }, [tick, el("span", { text: CONSENT_COPY.video })]),
    el("div", { class: "st-setup-key-actions" }, [go]),
  );
  return card;
}

function voiceRow(engine, voice) {
  const id = String(voice.id ?? "");
  const label = voice.name || id || "Default";
  const key = `${engine.id}:${id}`;
  const button = el("button", {
    class: "st-btn st-btn-ghost st-btn-small", type: "button",
    text: playing === key ? "…" : "Play",
    disabled: Boolean(playing),
    "aria-label": `Play ${label}`,
  });
  button.addEventListener("click", () => { void play(engine.id, id, label); });
  return el("li", { class: `vr-voice${voice.clone ? " is-clone" : ""}` }, [
    el("div", { class: "vr-voice-name" }, [
      el("strong", { text: `${voice.clone ? "★ " : ""}${label}` }),
      el("span", { class: "st-mono st-hint", text: voice.lang || "" }),
    ]),
    button,
  ]);
}

function engineCard(engine) {
  const shown = engine.voices.filter(matches);
  const open = !collapsed.has(engine.id) || Boolean(query || language);
  const toggle = el("button", {
    class: "vr-engine-head", type: "button", "aria-expanded": open ? "true" : "false",
  }, [
    el("strong", { text: engine.label }),
    el("span", { class: `st-chip ${engine.local ? "" : "st-chip-busy"}`, text: ENGINE_NOTES[engine.id] || (engine.local ? "On this Mac" : "Cloud") }),
    el("span", { class: "st-mono st-hint", text: `${shown.length}${shown.length !== engine.voices.length ? ` / ${engine.voices.length}` : ""} voices` }),
    el("span", { class: "vr-caret", "aria-hidden": "true", text: open ? "▾" : "▸" }),
  ]);
  toggle.addEventListener("click", () => {
    if (collapsed.has(engine.id)) collapsed.delete(engine.id);
    else collapsed.add(engine.id);
    render();
  });
  const card = el("section", { class: "st-card vr-engine" }, [toggle]);
  if (engine.error) card.append(el("p", { class: "st-error", text: engine.error }));
  if (open) {
    if (shown.length) {
      card.append(el("ul", { class: "vr-voices" }, shown.map((voice) => voiceRow(engine, voice))));
    } else {
      card.append(el("p", { class: "st-hint", text: "No voice matches the filter." }));
    }
  }
  return card;
}

function voicesSection() {
  const engines = catalog?.engines || [];
  const ready = engines.filter((engine) => engine.available);
  const missing = engines.filter((engine) => !engine.available);
  const total = ready.reduce((sum, engine) => sum + engine.voices.length, 0);

  const languages = new Set();
  for (const engine of ready) for (const voice of engine.voices) languages.add(langOf(voice));
  const search = el("input", { type: "search", value: query, placeholder: "Search voices", "aria-label": "Search voices" });
  search.addEventListener("input", () => {
    query = search.value.trim();
    render();
    const again = root.querySelector('input[type="search"]');
    if (again) {
      again.focus();
      again.setSelectionRange(again.value.length, again.value.length);
    }
  });
  const lang = el("select", { "aria-label": "Language" }, [
    el("option", { value: "", text: "All languages", selected: !language }),
    ...[...languages].filter((code) => code !== "multi").sort().map(
      (code) => el("option", { value: code, text: code, selected: code === language }),
    ),
  ]);
  lang.addEventListener("change", () => { language = lang.value; render(); });

  const section = el("section", { class: "vr-voices-section" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("h2", { text: "Voices on this machine" }),
        el("p", { class: "st-hint", text: `${total} voices across ${ready.length} engines. Cloud voices use your own keys; Apple voices work offline.` }),
      ]),
      el("div", { class: "vr-filters" }, [search, lang]),
    ]),
  ]);
  const filtering = Boolean(query || language);
  const visible = ready.filter((engine) => !filtering || engine.voices.some(matches));
  for (const engine of visible) section.append(engineCard(engine));
  if (filtering && !visible.length) {
    section.append(el("p", { class: "st-hint", text: "No voice on this machine matches the filter." }));
  }
  if (missing.length) {
    section.append(el("details", { class: "st-card vr-missing" }, [
      el("summary", { text: `Not set up on this machine (${missing.length})` }),
      el("ul", { class: "vr-missing-list" }, missing.map((engine) => el("li", {}, [
        el("strong", { text: engine.label }),
        el("span", { class: "st-hint", text: engine.install || "Not available." }),
      ]))),
    ]));
  }
  return section;
}

function render() {
  if (!root) return;
  const page = el("div", { class: "vr-page" });
  page.append(header());
  const body = el("main", { class: "vr-body" });
  body.append(el("div", { class: "vr-hero" }, [
    el("p", { class: "st-eyebrow", text: "Voice Room" }),
    el("h1", { text: "Every voice on this machine, and your own." }),
    el("p", { class: "st-hint", text: "Listen to any voice, clone yours from a recording, or clone a speaker from one of your videos. Cloned voices show up under HeyGen Voice Turbo in Studio's voice picker." }),
  ]));
  if (error) body.append(el("p", { class: "st-error", role: "alert", text: error }));
  if (notice) {
    const line = el("p", { class: "st-status vr-notice", role: "status", text: notice });
    line.dataset.tone = noticeTone;
    body.append(line);
  }
  if (loading && !catalog) {
    body.append(el("p", { class: "st-hint", text: "Reading the voices on this machine…" }));
  } else {
    myVoice.render();
    body.append(el("div", { class: "vr-grid" }, [
      el("div", { class: "vr-side" }, [
        testCard(),
        el("section", { class: "st-card vr-card" }, [myVoice.node]),
        videoCard(),
      ]),
      voicesSection(),
    ]));
  }
  page.append(body);
  const scroll = root.querySelector(".vr-page")?.scrollTop || 0;
  root.replaceChildren(page);
  page.scrollTop = scroll;
}

window.addEventListener("pagehide", () => myVoice.dispose());
void load();
