/**
 * Voice Room — every voice this machine can speak, and voice cloning.
 *
 * A page of its own (`/voices`), opened from the Voice Room link in Classic's
 * top bar when the `voice_room` feature is on. One page holds:
 *
 *   * Your voices: the creator's clones, with Play, Rename and Delete.
 *   * Clone a voice: from a recording or a file (voiceclone.js), or from a
 *     video through the clean-clip finder (clipfinder.js).
 *   * Stock voices: each engine with the voices it has here (Apple voices,
 *     Kokoro, cloud engines with a saved key, HeyGen Voice Turbo), played
 *     with a test line.
 *
 * Routes:
 *   GET  /api/voices/catalog
 *   POST /api/voices/sample
 *   GET  /api/settings, GET /api/jobs
 *   /api/voices/clones and /api/jobs/{id}/voices/* (voiceclone.js)
 */

import { listJobs, request } from "./api.js";
import { el } from "./ui.js";
import { createClipFinder } from "./clipfinder.js";
import {
  createMyVoicePanel,
  deleteClone,
  playClone,
  playVoice,
  renameClone,
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

const root = document.getElementById("voice-root");

let catalog = null;
let settings = null;
let loading = true;
let error = "";
let notice = "";
let noticeTone = "";
let testLine = DEFAULT_LINE;
let rate = 1;
let preservePitch = true;
let maxSpeed = 1.80;
let stretchEngine = "auto";
let extremeSpeed = false;
let voiceFitSaving = "";
let query = "";
let language = "";
let playing = "";
let jobs = [];
let renaming = "";
let renameValue = "";
let renameFresh = false;
let cloneBusy = "";
const collapsed = new Set(["say"]);

function setNotice(message, tone = "") {
  notice = message || "";
  noticeTone = tone;
}

const myVoice = createMyVoicePanel({
  hasKey: () => Boolean(catalog?.clone_available),
  onChange: () => { void loadCatalog(); },
  sampleText: () => testLine,
  title: "From a recording or a file",
  list: false,
});

const finder = createClipFinder({
  jobs: () => jobs,
  available: () => Boolean(catalog?.clone_available),
  onCloned: () => { void loadCatalog(); },
  onNotice: (message, tone) => { setNotice(message, tone); render(); },
});

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
    catalog = await request("/api/voices/catalog");
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
      request("/api/voices/catalog"),
      listJobs({ limit: 30 }).catch(() => ({ jobs: [] })),
    ]);
    settings = state;
    const voiceFit = state?.settings?.voice_fit || {};
    preservePitch = voiceFit.preserve_pitch !== false;
    maxSpeed = Number(voiceFit.max_speed || 1.80);
    stretchEngine = ["auto", "ffmpeg", "signalsmith"].includes(voiceFit.engine)
      ? voiceFit.engine : "auto";
    extremeSpeed = voiceFit.allow_extreme_speed === true;
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

async function playMine(item) {
  if (cloneBusy) return;
  cloneBusy = `play:${item.voice_id}`;
  setNotice(`Speaking the test line as ${item.name}…`);
  render();
  try {
    await playClone(item.voice_id, testLine);
    setNotice(`Playing ${item.name}.`, "ok");
  } catch (cause) {
    setNotice(cause?.message || "Could not play this voice.", "bad");
  } finally {
    cloneBusy = "";
    render();
  }
}

async function saveName(item) {
  const name = renameValue.trim();
  if (!name || name === item.name) {
    renaming = "";
    render();
    return;
  }
  cloneBusy = `rename:${item.voice_id}`;
  render();
  try {
    const record = await renameClone(item.voice_id, name);
    renaming = "";
    setNotice(`Renamed to “${record?.name || name}”.`, "ok");
    if (catalog?.clones) {
      catalog.clones = catalog.clones.map((row) => (row.voice_id === item.voice_id ? { ...row, ...record } : row));
    }
    // The stock list shows clones under HeyGen too; refresh it behind the scenes.
    void loadCatalog();
  } catch (cause) {
    setNotice(cause?.message || "Could not rename the voice.", "bad");
  } finally {
    cloneBusy = "";
    render();
  }
}

async function removeMine(item) {
  if (!window.confirm(`Delete “${item.name}”? Its sample is removed from this Mac, and edits that use it fall back to another voice.`)) return;
  cloneBusy = `delete:${item.voice_id}`;
  render();
  try {
    await deleteClone(item.voice_id);
    setNotice(`Deleted “${item.name}”.`, "ok");
    if (catalog?.clones) catalog.clones = catalog.clones.filter((row) => row.voice_id !== item.voice_id);
    void loadCatalog();
  } catch (cause) {
    setNotice(cause?.message || "Could not delete the voice.", "bad");
  } finally {
    cloneBusy = "";
    render();
  }
}

// ------------------------------------------------------------------ views

function header() {
  const refresh = el("button", { class: "ghost small", type: "button", text: "Refresh" });
  refresh.addEventListener("click", () => { void load(); });
  const views = settings?.edition?.views || [];
  const language = el("select", {
    id: "ui-language", class: "ghost small lang-select", "aria-label": "Interface language",
  }, [
    el("option", { value: "en", text: "English" }),
    el("option", { value: "vi", text: "Tiếng Việt" }),
  ]);
  language.value = window.VibeCutI18N?.current?.() || "en";
  language.addEventListener("change", () => window.VibeCutI18N?.setLanguage?.(language.value));
  return el("header", { class: "shell topbar vr-top" }, [
    el("a", { class: "brand", href: "/" }, ["VibeCut", el("span", { class: "brand-mark" })]),
    el("div", { class: "topbar-right" }, [
      el("span", { class: "vr-room", text: "Voice Room" }),
      el("a", { href: "/", text: "Back to VibeCut" }),
      views.includes("studio") ? el("a", { href: "/?studio=1", text: "Open Studio" }) : null,
      language,
      refresh,
    ]),
  ]);
}

function cloneRow(item) {
  const id = item.voice_id;
  const busy = Boolean(cloneBusy);
  const row = el("li", { class: "vr-mine", "data-voice": id });
  if (renaming === id) {
    const input = el("input", { type: "text", maxLength: 64, value: renameValue, "aria-label": `New name for ${item.name}` });
    input.addEventListener("input", () => { renameValue = input.value; });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void saveName(item);
      if (event.key === "Escape") { renaming = ""; render(); }
    });
    const save = el("button", { class: "primary small", type: "button", text: cloneBusy === `rename:${id}` ? "Saving…" : "Save", disabled: busy });
    save.addEventListener("click", () => { void saveName(item); });
    const cancel = el("button", { class: "ghost small", type: "button", text: "Cancel", disabled: busy });
    cancel.addEventListener("click", () => { renaming = ""; render(); });
    row.append(el("div", { class: "vr-mine-copy" }, [input]), el("div", { class: "vr-actions" }, [save, cancel]));
    const fresh = renameFresh;
    renameFresh = false;
    window.setTimeout(() => {
      input.focus();
      if (fresh) input.select();
      else input.setSelectionRange(input.value.length, input.value.length);
    }, 0);
    return row;
  }
  const playButton = el("button", {
    class: "ghost small", type: "button",
    text: cloneBusy === `play:${id}` ? "Speaking…" : "Play",
    disabled: busy, "aria-label": `Play ${item.name}`,
  });
  playButton.addEventListener("click", () => { void playMine(item); });
  const renameButton = el("button", { class: "ghost small", type: "button", text: "Rename", disabled: busy, "aria-label": `Rename ${item.name}` });
  renameButton.addEventListener("click", () => {
    renaming = id;
    renameValue = item.name || "";
    renameFresh = true;
    render();
  });
  const deleteButton = el("button", {
    class: "ghost small danger", type: "button",
    text: cloneBusy === `delete:${id}` ? "Deleting…" : "Delete",
    disabled: busy, "aria-label": `Delete ${item.name}`,
  });
  deleteButton.addEventListener("click", () => { void removeMine(item); });
  const facts = [
    item.source === "video" ? "From a video" : "My voice",
    item.sample_seconds ? `${Math.round(item.sample_seconds)} s sample` : "",
    item.language || "",
  ].filter(Boolean).join(" · ");
  row.append(
    el("div", { class: "vr-mine-copy" }, [
      el("strong", { text: item.name || "Cloned voice" }),
      el("span", { class: "hint mono", text: facts }),
    ]),
    el("div", { class: "vr-actions" }, [playButton, renameButton, deleteButton]),
  );
  return row;
}

function mineSection() {
  const clones = catalog?.clones || [];
  const section = el("section", { class: "vr-section", "data-panel": "your-voices" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "01" }), "your voices"]),
        el("h2", { text: "Cloned voices" }),
        el("p", { class: "hint", text: "Each clone is a short sample kept on this Mac. HeyGen Voice Turbo on OpenRouter speaks in it, and it shows up under HeyGen Voice Turbo in every voice picker." }),
      ]),
    ]),
  ]);
  if (clones.length) {
    section.append(el("ul", { class: "vr-mine-list" }, clones.map(cloneRow)));
  } else {
    section.append(el("p", { class: "hint vr-empty", text: "No cloned voices yet. Clone one below." }));
  }
  return section;
}

function cloneSection() {
  myVoice.render();
  return el("section", { class: "vr-section", "data-panel": "clone" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "02" }), "clone a voice"]),
        el("h2", { text: "Clone a voice" }),
        el("p", { class: "hint", text: "Give 30 s to 3 min of clear speech. Only clone your own voice, or a speaker who gave you permission." }),
      ]),
    ]),
    el("div", { class: "vr-clone-grid" }, [
      el("section", { class: "vr-card", "data-panel": "my-voice" }, [myVoice.node]),
      finder.node,
    ]),
  ]);
}

async function saveVoiceFit(patch) {
  voiceFitSaving = "saving";
  try {
    const result = await request("/api/settings", {
      method: "POST",
      body: { settings: { voice_fit: patch } },
    });
    settings = result;
    const voiceFit = result?.settings?.voice_fit || {};
    preservePitch = voiceFit.preserve_pitch !== false;
    maxSpeed = Number(voiceFit.max_speed || 1.80);
    stretchEngine = ["auto", "ffmpeg", "signalsmith"].includes(voiceFit.engine)
      ? voiceFit.engine : "auto";
    extremeSpeed = voiceFit.allow_extreme_speed === true;
    setNotice("Voice fit saved for this project.", "ok");
  } catch (error) {
    setNotice(error?.message || "Could not save voice fit.", "bad");
  } finally {
    voiceFitSaving = "";
    render();
  }
}

function testCard() {
  const line = el("textarea", { rows: 2, maxLength: 300, value: testLine, "aria-label": "Test line" });
  line.addEventListener("input", () => { testLine = line.value.trim() || DEFAULT_LINE; });
  const sliderMax = preservePitch
    ? Math.min(1.25, maxSpeed)
    : (extremeSpeed ? 2.5 : Math.min(maxSpeed, 1.8));
  const speed = el("input", {
    type: "range", min: "0.7", max: String(sliderMax),
    step: "0.05", value: String(Math.min(rate, sliderMax)),
    "aria-label": "Rate",
  });
  const speedValue = el("span", { class: "mono hint", text: `${rate.toFixed(2)}×` });
  speed.addEventListener("input", () => {
    rate = Number(speed.value) || 1;
    speedValue.textContent = `${rate.toFixed(2)}×`;
  });
  const stop = el("button", { class: "ghost small", type: "button", text: "Stop" });
  stop.addEventListener("click", () => stopPlayback());

  const preserve = el("input", { type: "checkbox", checked: preservePitch, "aria-label": "Preserve voice pitch and tone" });
  preserve.addEventListener("change", () => {
    preservePitch = preserve.checked;
    if (preservePitch) {
      extremeSpeed = false;
      if (maxSpeed > 1.8) maxSpeed = 1.8;
      if (rate > 1.25) rate = 1.25;
    }
    void saveVoiceFit({
      preserve_pitch: preservePitch,
      max_speed: maxSpeed,
      engine: stretchEngine,
      allow_extreme_speed: extremeSpeed,
    });
  });

  const max = el("select", { "aria-label": "Maximum voice speed" });
  [1.10, 1.15, 1.20, 1.25, 1.50, 1.80, 2.50].forEach((value) => {
    const option = el("option", { value: value.toFixed(2), text: `${value.toFixed(2)}×` });
    if (Math.abs(value - maxSpeed) < 0.005) option.selected = true;
    max.append(option);
  });
  max.addEventListener("change", () => {
    maxSpeed = Number(max.value) || 1.80;
    if (maxSpeed >= 2.5) extremeSpeed = true;
    else if (maxSpeed <= 1.8) extremeSpeed = false;
    void saveVoiceFit({
      preserve_pitch: preservePitch,
      max_speed: maxSpeed,
      engine: stretchEngine,
      allow_extreme_speed: extremeSpeed,
    });
  });

  const signalsmith = settings?.runtime?.voice_fit?.signalsmith === true;
  const engine = el("select", { "aria-label": "Stretch engine" });
  [
    ["auto", "Auto · Signalsmith if installed, then FFmpeg"],
    ["ffmpeg", "FFmpeg · atempo"],
    ["signalsmith", signalsmith ? "Signalsmith Stretch" : "Signalsmith Stretch · not installed"],
  ].forEach(([value, label]) => {
    const option = el("option", { value, text: label });
    if (value === stretchEngine) option.selected = true;
    if (value === "signalsmith" && !signalsmith) option.disabled = true;
    engine.append(option);
  });
  engine.addEventListener("change", () => {
    stretchEngine = engine.value || "auto";
    void saveVoiceFit({
      preserve_pitch: preservePitch,
      max_speed: maxSpeed,
      engine: stretchEngine,
      allow_extreme_speed: extremeSpeed,
    });
  });

  const extreme = el("input", { type: "checkbox", checked: extremeSpeed, "aria-label": "Allow extreme chipmunk speed" });
  extreme.disabled = preservePitch;
  extreme.addEventListener("change", () => {
    extremeSpeed = extreme.checked;
    if (extremeSpeed) {
      maxSpeed = 2.5;
      max.value = "2.50";
    } else if (maxSpeed > 1.8) {
      maxSpeed = 1.8;
      max.value = "1.80";
    }
    void saveVoiceFit({
      preserve_pitch: preservePitch,
      max_speed: maxSpeed,
      engine: stretchEngine,
      allow_extreme_speed: extremeSpeed,
    });
  });

  const warning = el("p", {
    class: "hint",
    text: preservePitch
      ? "Preserve voice keeps pitch and tone; lines are capped at 1.25× and the script is shortened if needed."
      : "Preserve voice is off. Faster lines raise pitch and may create a chipmunk sound.",
  });

  return el("div", { class: "vr-card vr-test" }, [
    el("label", { class: "vr-field" }, [el("span", { text: "Test line · every Play button speaks it" }), line]),
    el("div", { class: "vr-rate" }, [el("span", { class: "hint", text: "Rate" }), speed, speedValue, stop]),
    el("details", { class: "vr-advanced" }, [
      el("summary", { text: "Advanced voice fit" }),
      el("label", { class: "vr-check" }, [preserve, el("span", { text: "Preserve voice pitch & tone" })]),
      warning,
      el("div", { class: "vr-rate" }, [el("span", { class: "hint", text: "Max speed" }), max]),
      el("div", { class: "vr-rate" }, [el("span", { class: "hint", text: "Stretch engine" }), engine]),
      el("label", { class: "vr-check" }, [extreme, el("span", { text: "Allow extreme chipmunk speed above 1.8×" })]),
      voiceFitSaving ? el("p", { class: "hint", text: "Saving voice fit…" }) : "",
    ]),
  ]);
}

function voiceRow(engine, voice) {
  const id = String(voice.id ?? "");
  const label = voice.name || id || "Default";
  const key = `${engine.id}:${id}`;
  const button = el("button", {
    class: "ghost small", type: "button",
    text: playing === key ? "…" : "Play",
    disabled: Boolean(playing),
    "aria-label": `Play ${label}`,
  });
  button.addEventListener("click", () => { void play(engine.id, id, label); });
  return el("li", { class: `vr-voice${voice.clone ? " is-clone" : ""}` }, [
    el("div", { class: "vr-voice-name" }, [
      el("strong", { text: `${voice.clone ? "★ " : ""}${label}` }),
      el("span", { class: "mono hint", text: voice.lang || "" }),
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
    el("span", { class: `vr-chip${engine.local ? "" : " is-cloud"}`, text: ENGINE_NOTES[engine.id] || (engine.local ? "On this Mac" : "Cloud") }),
    el("span", { class: "mono hint", text: `${shown.length}${shown.length !== engine.voices.length ? ` / ${engine.voices.length}` : ""} voices` }),
    el("span", { class: "vr-caret", "aria-hidden": "true", text: open ? "▾" : "▸" }),
  ]);
  toggle.addEventListener("click", () => {
    if (collapsed.has(engine.id)) collapsed.delete(engine.id);
    else collapsed.add(engine.id);
    render();
  });
  const card = el("section", { class: "vr-card vr-engine", "data-engine": engine.id }, [toggle]);
  if (engine.error) card.append(el("p", { class: "error", text: engine.error }));
  if (open) {
    if (shown.length) {
      card.append(el("ul", { class: "vr-voices" }, shown.map((voice) => voiceRow(engine, voice))));
    } else {
      card.append(el("p", { class: "hint", text: "No voice matches the filter." }));
    }
  }
  return card;
}

function stockSection() {
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

  const section = el("section", { class: "vr-section", "data-panel": "stock-voices" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "03" }), "stock voices"]),
        el("h2", { text: "Voices on this machine" }),
        el("p", { class: "hint", text: `${total} voices across ${ready.length} engines. Cloud voices use your own keys; Apple voices work offline.` }),
      ]),
      el("div", { class: "vr-filters" }, [search, lang]),
    ]),
    testCard(),
  ]);
  const filtering = Boolean(query || language);
  const visible = ready.filter((engine) => !filtering || engine.voices.some(matches));
  for (const engine of visible) section.append(engineCard(engine));
  if (filtering && !visible.length) {
    section.append(el("p", { class: "hint", text: "No voice on this machine matches the filter." }));
  }
  if (missing.length) {
    section.append(el("details", { class: "vr-card vr-missing" }, [
      el("summary", { text: `Not set up on this machine (${missing.length})` }),
      el("ul", { class: "vr-missing-list" }, missing.map((engine) => el("li", {}, [
        el("strong", { text: engine.label }),
        el("span", { class: "hint", text: engine.install || "Not available." }),
      ]))),
    ]));
  }
  return section;
}

function render() {
  if (!root) return;
  const page = el("div", { class: "vr-page" });
  page.append(header());
  const body = el("main", { class: "shell vr-body" });
  body.append(el("div", { class: "hero vr-hero" }, [
    el("p", { class: "eyebrow" }, [el("span", { text: "voice" }), "room"]),
    el("h1", {}, ["Every voice here,", el("br"), el("em", { text: "and your own." })]),
    el("p", { class: "lede", text: "Listen to any voice, clone yours from a recording, or clone a speaker from the cleanest clips of one of your videos." }),
  ]));
  if (error) body.append(el("p", { class: "error", role: "alert", text: error }));
  if (notice) {
    const line = el("p", { class: "vr-status vr-notice", role: "status", text: notice });
    line.dataset.tone = noticeTone;
    body.append(line);
  }
  if (loading && !catalog) {
    body.append(el("p", { class: "hint", text: "Reading the voices on this machine…" }));
  } else {
    finder.render();
    body.append(mineSection(), cloneSection(), stockSection());
  }
  page.append(body);
  const scroll = window.scrollY || 0;
  root.replaceChildren(page);
  window.scrollTo(0, scroll);
}

window.addEventListener("pagehide", () => {
  myVoice.dispose();
  finder.dispose();
});
void load();
