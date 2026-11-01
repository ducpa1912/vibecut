/**
 * Voice Room — every voice this machine can speak, and voice cloning.
 *
 * A page of its own (`/voices`), opened from the Voice Room link in Classic's
 * top bar when the `voice_room` feature is on. One page holds:
 *
 *   * Your voices: the creator's clones, with Play, Rename and Delete.
 *   * Clone a voice: from a recording or a file (voiceclone.js), or from a
 *     video through the clean-clip finder (clipfinder.js).
 *   * Compare voices: two selectors on the same test line (compare.js).
 *   * Stock voices: each engine with the voices it has here (Apple voices,
 *     Kokoro, cloud engines with a saved key, HeyGen Voice Turbo), played
 *     with a test line.
 *   * Favorites: a star on every stock voice and clone, kept in this browser
 *     (favorites.js).
 *
 * Routes:
 *   GET  /api/voices/catalog
 *   POST /api/voices/sample
 *   GET  /api/settings, GET /api/jobs
 *   /api/voices/clones and /api/jobs/{id}/voices/* (voiceclone.js)
 */

import { listJobs, request } from "./api.js";
import { el } from "./ui.js";
import { cloneKey, isFavorite, stockKey, toggleFavorite } from "./favorites.js";
import { createClipFinder } from "./clipfinder.js";
import { createComparePanel } from "./compare.js";
import { createRecentPanel, recentKey, recordRecent } from "./recent.js";
import { createVoiceSetup } from "./setup.js";
import {
  createMyVoicePanel,
  deleteClone,
  isStopped,
  listClones,
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
let query = "";
let language = "";
let favoritesOnly = false;
let paintClones = () => {};
let playPhase = "idle";
let playKey = "";
let playPlayer = null;
let playToken = 0;
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
  hasKey: () => Boolean(settings?.secrets?.openrouter),
  onChange: () => { void loadCatalog(); },
  sampleText: () => testLine,
  title: "From a recording or a file",
  list: false,
  description: "",
  trim: true,
});

const finder = createClipFinder({
  jobs: () => jobs,
  available: () => Boolean(settings?.secrets?.openrouter),
  onCloned: () => { void loadCatalog(); },
  onNotice: (message, tone) => { setNotice(message, tone); render(); },
});

const setup = createVoiceSetup({
  getSettings: () => settings,
  onChanged: () => load(),
});

const compare = createComparePanel({
  catalog: () => catalog,
  play: (engine, voice, label) => play(engine, voice, label),
  playMine: (item) => playMine(item),
  playback: () => ({ phase: playPhase, key: playKey }),
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

/** Stock filters compose: favorites, language, then the text search. */
function matchesStock(engine, voice) {
  if (favoritesOnly && !isFavorite(stockKey(engine.id, voice.id))) return false;
  return matches(voice);
}

async function loadCatalog() {
  try {
    catalog = await request("/api/voices/catalog");
  } catch (cause) {
    const clones = (await listClones().catch(() => null))?.voices || [];
    catalog = { engines: [], clones, clone_available: false };
    error = cause?.message || "Could not read the voices on this machine.";
  }
  render();
}

async function load() {
  loading = true;
  error = "";
  render();
  const [stateResult, voicesResult, recentResult] = await Promise.allSettled([
    request("/api/settings"),
    request("/api/voices/catalog"),
    listJobs({ limit: 30 }),
  ]);
  if (stateResult.status === "fulfilled") {
    settings = stateResult.value;
  } else {
    error = stateResult.reason?.message || "Could not read this app's setup.";
  }
  if (voicesResult.status === "fulfilled") {
    catalog = voicesResult.value;
  } else {
    const clones = (await listClones().catch(() => null))?.voices || [];
    catalog = { engines: [], clones, clone_available: false };
    error = error || voicesResult.reason?.message || "Could not read the voices on this machine.";
  }
  const recent = recentResult.status === "fulfilled" ? recentResult.value : { jobs: [] };
  jobs = (recent?.jobs || []).filter((job) => job.status === "ready" && !job.source_deleted && !job.source_missing);
  loading = false;
  render();
}

function isPlaying(key) {
  return playPhase !== "idle" && playKey === key;
}

/** Pause the player and forget the row that owned it, without re-rendering. */
function haltPlayback() {
  if (playPlayer) {
    try { playPlayer.pause(); } catch (_) { /* already closed */ }
  }
  stopPlayback();
  playToken += 1;
  playPhase = "idle";
  playKey = "";
  playPlayer = null;
}

/** Stop from a row button or the test card: same state, same player. */
function stopVoice() {
  const active = playPhase !== "idle";
  haltPlayback();
  if (active) setNotice("Stopped.");
  render();
}

/**
 * generating → playing → idle. The row keeps Stop while the sample is made and
 * while the Audio object is speaking; ended/error clears it back to Play.
 */
async function startPlayback({ key, label, pending, start, entry = null }) {
  haltPlayback();
  const token = playToken;
  playPhase = "generating";
  playKey = key;
  setNotice(pending);
  render();
  try {
    const player = await start();
    if (token !== playToken) {
      try { player?.pause(); } catch (_) { /* superseded */ }
      return;
    }
    playPlayer = player;
    playPhase = "playing";
    const finish = (failed) => {
      if (token !== playToken) return;
      playToken += 1;
      playPhase = "idle";
      playKey = "";
      playPlayer = null;
      if (failed) setNotice(`Could not play ${label}.`, "bad");
      else setNotice(`Finished ${label}.`, "ok");
      render();
    };
    player.addEventListener("ended", () => finish(false), { once: true });
    player.addEventListener("error", () => finish(true), { once: true });
    if (player.ended || player.error) {
      finish(Boolean(player.error));
      return;
    }
    // The sample is speaking now: only a real start earns a recent entry.
    if (entry) recordRecent(entry);
    setNotice(`Playing ${label}.`, "ok");
    render();
  } catch (cause) {
    if (token !== playToken) return;
    playToken += 1;
    playPhase = "idle";
    playKey = "";
    playPlayer = null;
    if (isStopped(cause)) {
      setNotice("Stopped.");
    } else {
      const message = cause?.message || `Could not play ${label}.`;
      setNotice(message, "bad");
      if (/openrouter|quarantin|auth|key/i.test(message)) void load();
    }
    render();
  }
}

async function play(engine, voice, label) {
  const key = `${engine}:${voice}`;
  if (isPlaying(key)) {
    stopVoice();
    return;
  }
  await startPlayback({
    key,
    label,
    pending: `Making a sample of ${label}…`,
    start: () => playVoice(engine, voice, testLine, rate),
    entry: { kind: "stock", engine, voice: String(voice), label },
  });
}

function playMine(item) {
  const key = `clone:${item.voice_id}`;
  if (isPlaying(key)) {
    stopVoice();
    return;
  }
  void startPlayback({
    key,
    label: item.name || "this voice",
    pending: `Speaking the test line as ${item.name}…`,
    start: () => playClone(item.voice_id, testLine, rate),
    entry: {
      kind: "clone",
      engine: "heygen",
      voice: item.voice_id,
      clone: item.voice_id,
      label: item.name || "this voice",
    },
  });
}

function replayRecent(entry) {
  if (entry.kind === "clone") {
    playMine({ voice_id: entry.clone || entry.voice, name: entry.label });
    return;
  }
  void play(entry.engine, entry.voice, entry.label);
}

function recentSection() {
  return createRecentPanel({
    isSpeaking: (entry) => isPlaying(recentKey(entry)),
    onPlay: replayRecent,
  }).node;
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
  const setupButton = el("button", { class: "ghost small", type: "button", text: "Setup" });
  setupButton.addEventListener("click", () => { setup.open(); });
  const views = settings?.edition?.views || [];
  return el("header", { class: "shell topbar vr-top" }, [
    el("a", { class: "brand", href: "/" }, ["VibeCut", el("span", { class: "brand-mark" })]),
    el("div", { class: "topbar-right" }, [
      el("span", { class: "vr-room", text: "Voice Room" }),
      el("a", { href: "/", text: "Back to VibeCut" }),
      el("a", { href: "?ui=new", text: "New UI" }),
      views.includes("studio") ? el("a", { href: "/?studio=1", text: "Open Studio" }) : null,
      setupButton,
      refresh,
    ]),
  ]);
}

/** A real button with a 44 px target; ★ when saved, ☆ when not. */
function starButton({ key, label, onChange = () => {} }) {
  const name = String(label || "").trim() || "this voice";
  const saved = isFavorite(key);
  const action = `${saved ? "Remove" : "Add"} ${name} ${saved ? "from" : "to"} favorites`;
  const button = el("button", {
    class: `vr-star${saved ? " is-on" : ""}`,
    type: "button",
    text: saved ? "★" : "☆",
    "aria-label": action,
    "aria-pressed": saved ? "true" : "false",
    title: action,
  });
  button.addEventListener("click", () => {
    const now = toggleFavorite(key);
    const next = `${now ? "Remove" : "Add"} ${name} ${now ? "from" : "to"} favorites`;
    button.textContent = now ? "★" : "☆";
    button.classList.toggle("is-on", now);
    button.setAttribute("aria-pressed", now ? "true" : "false");
    button.setAttribute("aria-label", next);
    button.title = next;
    onChange(now);
  });
  return button;
}

function cloneRow(item, repaint) {
  const id = item.voice_id;
  const name = item.name || "Cloned voice";
  const busy = Boolean(cloneBusy);
  const star = starButton({
    key: cloneKey(id),
    label: name,
    onChange: () => { if (favoritesOnly) repaint(); },
  });
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
    row.append(el("div", { class: "vr-mine-copy" }, [input]), el("div", { class: "vr-actions" }, [star, save, cancel]));
    const fresh = renameFresh;
    renameFresh = false;
    window.setTimeout(() => {
      input.focus();
      if (fresh) input.select();
      else input.setSelectionRange(input.value.length, input.value.length);
    }, 0);
    return row;
  }
  const speaking = isPlaying(`clone:${id}`);
  const playButton = el("button", {
    class: "ghost small", type: "button",
    text: speaking ? "Stop" : "Play",
    disabled: busy && !speaking, "aria-label": `${speaking ? "Stop" : "Play"} ${item.name}`,
  });
  playButton.addEventListener("click", playMine.bind(null, item));
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
    el("div", { class: "vr-actions" }, [star, playButton, renameButton, deleteButton]),
  );
  return row;
}

function mineSection(number = "01") {
  const clones = catalog?.clones || [];
  const list = el("div", { class: "vr-clone-list" });
  const paint = () => {
    const shown = favoritesOnly ? clones.filter((item) => isFavorite(cloneKey(item.voice_id))) : clones;
    if (shown.length) {
      list.replaceChildren(el("ul", { class: "vr-mine-list" }, shown.map((item) => cloneRow(item, paint))));
    } else {
      const message = clones.length
        ? "No favorite cloned voices yet."
        : "No cloned voices yet. Clone one below.";
      list.replaceChildren(el("p", { class: "hint vr-empty", text: message }));
    }
  };
  paintClones = paint;
  paint();
  const section = el("section", { class: "vr-section", "data-panel": "your-voices" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: number }), "your voices"]),
        el("h2", { text: "Cloned voices" }),
        el("p", { class: "hint", text: "Stored on this Mac. Play sends the sample to HeyGen through OpenRouter." }),
      ]),
    ]),
    list,
  ]);
  if (clones.length && !catalog?.clone_available) {
    section.append(el("p", {
      class: "hint",
      text: "These clones are kept on this Mac. OpenRouter is not ready, so Play needs Setup fixed first.",
    }));
  }
  return section;
}

function cloneSection(number = "02") {
  myVoice.render();
  return el("section", { class: "vr-section", "data-panel": "clone" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: number }), "clone a voice"]),
        el("h2", { text: "Clone a voice" }),
        el("p", { class: "hint", text: "Use 30 seconds to 3 minutes of clear speech. Clone only your own voice or a speaker who gave permission." }),
      ]),
    ]),
    el("div", { class: "vr-clone-grid" }, [
      el("section", { class: "vr-card", "data-panel": "my-voice" }, [myVoice.node]),
      finder.node,
    ]),
  ]);
}

function testCard() {
  const line = el("textarea", { rows: 2, maxLength: 300, value: testLine, "aria-label": "Test line" });
  line.addEventListener("input", () => { testLine = line.value.trim() || DEFAULT_LINE; });
  const speed = el("input", { type: "range", min: "0.7", max: "1.4", step: "0.05", value: String(rate), "aria-label": "Rate" });
  const speedValue = el("span", { class: "mono hint", text: `${rate.toFixed(2)}×` });
  speed.addEventListener("input", () => {
    rate = Number(speed.value) || 1;
    speedValue.textContent = `${rate.toFixed(2)}×`;
  });
  const stop = el("button", { class: "ghost small", type: "button", text: "Stop" });
  stop.addEventListener("click", () => stopVoice());
  return el("div", { class: "vr-card vr-test" }, [
    el("label", { class: "vr-field" }, [el("span", { text: "Test line · used by every Play" }), line]),
    el("div", { class: "vr-rate" }, [el("span", { class: "hint", text: "Rate" }), speed, speedValue, stop]),
  ]);
}

/** Stock voices only: clones live in "your voices", not under each engine. */
function stockVoices(engine) {
  return (engine?.voices || []).filter((voice) => !voice.clone);
}

function voiceRow(engine, voice, repaint) {
  const id = String(voice.id ?? "");
  const label = voice.name || id || "Default";
  const key = `${engine.id}:${id}`;
  const speaking = isPlaying(key);
  const button = el("button", {
    class: "ghost small", type: "button",
    text: speaking ? "Stop" : "Play",
    "aria-label": `${speaking ? "Stop" : "Play"} ${label}`,
  });
  button.addEventListener("click", () => { void play(engine.id, id, label); });
  const star = starButton({
    key: stockKey(engine.id, id),
    label,
    onChange: () => { if (favoritesOnly) repaint(); },
  });
  return el("li", { class: "vr-voice" }, [
    el("div", { class: "vr-voice-name" }, [
      el("strong", { text: label }),
      el("span", { class: "mono hint", text: voice.lang || "" }),
    ]),
    el("div", { class: "vr-actions" }, [star, button]),
  ]);
}

function engineCard(engine, repaint) {
  const voices = stockVoices(engine);
  const shown = voices.filter((voice) => matchesStock(engine, voice));
  const open = !collapsed.has(engine.id) || Boolean(query || language || favoritesOnly);
  const toggle = el("button", {
    class: "vr-engine-head", type: "button", "aria-expanded": open ? "true" : "false",
  }, [
    el("strong", { text: engine.label }),
    el("span", { class: `vr-chip${engine.local ? "" : " is-cloud"}`, text: ENGINE_NOTES[engine.id] || (engine.local ? "On this Mac" : "Cloud") }),
    el("span", { class: "mono hint", text: `${shown.length}${shown.length !== voices.length ? ` / ${voices.length}` : ""} voices` }),
    el("span", { class: "vr-caret", "aria-hidden": "true", text: open ? "▾" : "▸" }),
  ]);
  toggle.addEventListener("click", () => {
    if (collapsed.has(engine.id)) collapsed.delete(engine.id);
    else collapsed.add(engine.id);
    repaint();
  });
  const card = el("section", { class: "vr-card vr-engine", "data-engine": engine.id }, [toggle]);
  if (engine.error) card.append(el("p", { class: "error", text: engine.error }));
  if (open) {
    if (shown.length) {
      card.append(el("ul", { class: "vr-voices" }, shown.map((voice) => voiceRow(engine, voice, repaint))));
    } else {
      card.append(el("p", { class: "hint", text: "No voice matches the filter." }));
    }
  }
  return card;
}

function stockSection(number = "03") {
  const engines = catalog?.engines || [];
  const ready = engines.filter((engine) => engine.available);
  const missing = engines.filter((engine) => !engine.available);
  const total = ready.reduce((sum, engine) => sum + stockVoices(engine).length, 0);

  const languages = new Set();
  for (const engine of ready) for (const voice of stockVoices(engine)) languages.add(langOf(voice));
  const search = el("input", { type: "search", value: query, placeholder: "Search voices", "aria-label": "Search voices" });
  const lang = el("select", { "aria-label": "Language" }, [
    el("option", { value: "", text: "All languages", selected: !language }),
    ...[...languages].filter((code) => code !== "multi").sort().map(
      (code) => el("option", { value: code, text: code, selected: code === language }),
    ),
  ]);
  const favoriteFilter = el("button", {
    class: `ghost small vr-favorites-filter${favoritesOnly ? " is-on" : ""}`,
    type: "button",
    text: "Favorites",
    "aria-pressed": favoritesOnly ? "true" : "false",
    title: "Show only favorite voices",
  });

  const list = el("div", { class: "vr-stock-list" });
  const paint = () => {
    const filtering = Boolean(query || language || favoritesOnly);
    const visible = ready.filter((engine) => !filtering || stockVoices(engine).some((voice) => matchesStock(engine, voice)));
    const nodes = visible.map((engine) => engineCard(engine, paint));
    if (filtering && !visible.length) {
      nodes.push(el("p", {
        class: "hint vr-empty",
        text: favoritesOnly ? "No favorite voice on this machine matches the filter." : "No voice on this machine matches the filter.",
      }));
    }
    if (missing.length) {
      nodes.push(el("details", { class: "vr-card vr-missing" }, [
        el("summary", { text: `Not set up on this machine (${missing.length})` }),
        el("ul", { class: "vr-missing-list" }, missing.map((engine) => el("li", {}, [
          el("strong", { text: engine.label }),
          el("span", { class: "hint", text: engine.install || "Not available." }),
        ]))),
      ]));
    }
    list.replaceChildren(...nodes);
  };

  // Filter in place: the input keeps focus, caret and IME composition.
  let composing = false;
  let debounce = 0;
  const applySearch = () => {
    query = search.value.trim();
    paint();
  };
  search.addEventListener("compositionstart", () => {
    composing = true;
    window.clearTimeout(debounce);
  });
  search.addEventListener("compositionend", () => {
    composing = false;
    window.clearTimeout(debounce);
    applySearch();
  });
  search.addEventListener("input", () => {
    // Keep the model in sync now; only the repaint waits for the debounce.
    query = search.value.trim();
    if (composing) return;
    window.clearTimeout(debounce);
    debounce = window.setTimeout(paint, 120);
  });
  lang.addEventListener("change", () => {
    window.clearTimeout(debounce);
    query = search.value.trim();
    language = lang.value;
    paint();
  });
  favoriteFilter.addEventListener("click", () => {
    favoritesOnly = !favoritesOnly;
    favoriteFilter.classList.toggle("is-on", favoritesOnly);
    favoriteFilter.setAttribute("aria-pressed", favoritesOnly ? "true" : "false");
    window.clearTimeout(debounce);
    query = search.value.trim();
    paint();
    paintClones();
  });

  const section = el("section", { class: "vr-section", "data-panel": "stock-voices" }, [
    el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: number }), "stock voices"]),
        el("h2", { text: "Voices on this machine" }),
        el("p", { class: "hint", text: `${total} voices across ${ready.length} engines. Local voices work offline; cloud voices use your keys.` }),
      ]),
      el("div", { class: "vr-filters" }, [search, lang, favoriteFilter]),
    ]),
    testCard(),
    list,
  ]);
  paint();
  return section;
}

function render() {
  if (!root) return;
  paintClones = () => {};
  const page = el("div", { class: "vr-page" });
  page.append(header());
  const body = el("main", { class: "shell vr-body" });
  body.append(el("div", { class: "hero vr-hero" }, [
    el("p", { class: "eyebrow" }, [el("span", { text: "voice" }), "room"]),
    el("h1", {}, ["Every voice here,", el("br"), el("em", { text: "and your own." })]),
    el("p", { class: "lede", text: "Preview the voices on this Mac, clone your own, or pull a clean reference from a video." }),
  ]));
  if (error) body.append(el("p", { class: "error", role: "alert", text: error }));
  if (notice) {
    const line = el("p", { class: "vr-status vr-notice", role: "status", text: notice });
    line.dataset.tone = noticeTone;
    body.append(line);
  }
  setup.render();
  body.append(setup.node);
  if (loading && !catalog) {
    body.append(el("p", { class: "hint", text: "Reading the voices on this machine…" }));
  } else {
    finder.render();
    compare.render();
    const clones = catalog?.clones || [];
    if (clones.length) {
      body.append(mineSection("01"), cloneSection("02"), compare.node, recentSection(), stockSection("03"));
    } else {
      body.append(cloneSection("01"), compare.node, recentSection(), stockSection("02"));
    }
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
