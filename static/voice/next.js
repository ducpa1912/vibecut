/**
 * Voice Room — new shell.
 *
 * One persistent shell with a left rail on desktop and bottom tabs on mobile.
 * Library, Create, Compare, Recent and Settings are views, not a long page.
 * The old page stays at /voices; this one is /voices?ui=new.
 */

import { listJobs, request } from "./api.js";
import { el, formatDuration } from "./ui.js";
import { cloneKey, isFavorite, stockKey, toggleFavorite } from "./favorites.js";
import { createClipFinder } from "./clipfinder.js";
import { createComparePanel } from "./compare.js";
import { createRecentPanel, recentKey, recordRecent } from "./recent.js";
import { createVoiceSetup } from "./setup.js";
import {
  createMyVoicePanel,
  deleteClone,
  isStopped,
  playClone,
  playVoice,
  renameClone,
  stopPlayback,
} from "./voiceclone.js";

const DEFAULT_LINE = "Hi, this is how I sound in VibeCut. Short, clear and easy to follow.";
const LINE_KEY = "vibecut.voice.testline.v1";
const RATE_KEY = "vibecut.voice.rate.v1";
const VIEWS = ["library", "create", "compare", "recent", "settings"];
const NAV = [
  ["library", "Library", "01"],
  ["create", "Create", "02"],
  ["compare", "Compare", "03"],
  ["recent", "Recent", "04"],
  ["settings", "Settings", "05"],
];
const RATES = [0.8, 0.9, 1, 1.1, 1.15, 1.2, 1.3, 1.4];

const root = document.getElementById("vg-root");

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch (_) {
    return fallback;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch (_) {
    /* storage can be unavailable */
  }
}

function setTestLine(value, source = "") {
  testLine = String(value ?? "");
  store(LINE_KEY, testLine);
  if (source !== "player" && playerRefs?.line) playerRefs.line.value = testLine;
  if (source !== "compare" && compareLineEl) compareLineEl.value = testLine;
  const count = document.querySelector(".vg-line-count");
  if (count) count.textContent = `${testLine.length}/300`;
}

function iconSvg(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "18");
  svg.setAttribute("height", "18");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const paths = {
    mic: ["M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z", "M5 11a7 7 0 0 0 14 0", "M12 18v3"],
    upload: ["M12 16V4", "m7 9 5-5 5 5", "M5 20h14"],
    video: ["M4 6h11v12H4z", "m15 10 5-3v10l-5-3z"],
    plus: ["M12 5v14", "M5 12h14"],
  };
  for (const d of paths[name] || []) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function viewFromHash() {
  const value = String(window.location.hash || "").replace(/^#\/?/, "");
  return VIEWS.includes(value) ? value : "library";
}

let view = viewFromHash();
let createTab = "record";
let catalog = null;
let settings = null;
let jobs = [];
let loading = true;
let error = "";
let notice = "";
let noticeTone = "";
let query = "";
let filter = "all";
let engineFilter = "";
let languageFilter = "";
let testLine = String(stored(LINE_KEY, DEFAULT_LINE));
let rate = Number(stored(RATE_KEY, "1"));
if (!Number.isFinite(rate) || !RATES.includes(rate)) rate = 1;

let playPhase = "idle";
let playKey = "";
let playLabel = "";
let playPlayer = null;
let playToken = 0;

let mainEl = null;
let playerRefs = null;
let navButtons = [];
let tabButtons = [];
let compareLineEl = null;

function setNotice(message, tone = "") {
  notice = message || "";
  noticeTone = tone;
  updatePlayer();
}

function langOf(voice) {
  return String(voice?.lang || voice?.language || "").toLowerCase().replace("_", "-").split("-")[0] || "multi";
}

function cloneName(item) {
  return item?.name || "Cloned voice";
}

function stockName(voice) {
  return voice?.name || String(voice?.id || "Default");
}

function isPlaying(key) {
  return playPhase !== "idle" && playKey === key;
}

function haltPlayback() {
  if (playPlayer) {
    try { playPlayer.pause(); } catch (_) { /* already closed */ }
  }
  stopPlayback();
  playToken += 1;
  playPhase = "idle";
  playKey = "";
  playLabel = "";
  playPlayer = null;
}

function syncPlayButtons() {
  for (const button of document.querySelectorAll("[data-play-key]")) {
    const active = isPlaying(button.dataset.playKey);
    button.classList.toggle("is-on", active);
    button.textContent = active ? "■" : "▶";
    button.setAttribute("aria-label", `${active ? "Stop" : "Play"} ${button.dataset.label || "voice"}`);
  }
}

function updatePlayer() {
  if (!playerRefs) return;
  const active = playPhase !== "idle";
  playerRefs.dot.dataset.phase = playPhase;
  playerRefs.strong.textContent = active ? playLabel : (notice || "Nothing playing");
  playerRefs.detail.textContent = active
    ? (playPhase === "generating" ? "Generating sample…" : "Playing preview")
    : (noticeTone === "bad" ? "Needs attention" : "Pick a voice to preview");
  playerRefs.stop.disabled = !active;
  syncPlayButtons();
  if (view === "compare") comparePanel.render();
  if (view === "recent") recentPanel.render();
}

function stopVoice() {
  const active = playPhase !== "idle";
  haltPlayback();
  if (active) setNotice("Stopped.");
  updatePlayer();
}

async function startPlayback({ key, label, pending, start, entry }) {
  haltPlayback();
  const token = playToken;
  playPhase = "generating";
  playKey = key;
  playLabel = label;
  setNotice(pending);
  updatePlayer();
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
      playLabel = "";
      playPlayer = null;
      setNotice(failed ? `Could not play ${label}.` : "", failed ? "bad" : "");
      updatePlayer();
    };
    player.addEventListener("ended", () => finish(false), { once: true });
    player.addEventListener("error", () => finish(true), { once: true });
    if (player.ended || player.error) {
      finish(Boolean(player.error));
      return;
    }
    if (entry) recordRecent(entry);
    setNotice(`Playing ${label}.`, "ok");
    updatePlayer();
  } catch (cause) {
    if (token !== playToken) return;
    playToken += 1;
    playPhase = "idle";
    playKey = "";
    playLabel = "";
    playPlayer = null;
    if (isStopped(cause)) {
      setNotice("Stopped.");
    } else {
      const message = cause?.message || `Could not play ${label}.`;
      setNotice(message, "bad");
      if (/openrouter|quarantin|auth|key/i.test(message)) void loadAll();
    }
    updatePlayer();
  }
}

function playSelection({ kind, engine = "", voice = "", id = "", label }) {
  const key = kind === "clone" ? `clone:${id}` : `${engine}:${voice}`;
  if (isPlaying(key)) {
    stopVoice();
    return;
  }
  const entry = kind === "clone"
    ? { kind: "clone", engine: "heygen", voice: id, clone: id, label }
    : { kind: "stock", engine, voice: String(voice), label };
  const lineText = String(testLine || "").trim() || DEFAULT_LINE;
  void startPlayback({
    key,
    label,
    pending: kind === "clone" ? `Speaking the test line as ${label}…` : `Making a sample of ${label}…`,
    start: () => (kind === "clone" ? playClone(id, lineText) : playVoice(engine, voice, lineText, rate)),
    entry,
  });
}

function replayRecent(entry) {
  if (entry.kind === "clone") {
    const item = (catalog?.clones || []).find((row) => row.voice_id === (entry.clone || entry.voice));
    if (!item) {
      setNotice("That cloned voice is no longer in the library.", "bad");
      return;
    }
    playSelection({ kind: "clone", id: item.voice_id, label: cloneName(item) });
    return;
  }
  playSelection({ kind: "stock", engine: entry.engine, voice: entry.voice, label: entry.label });
}

const myVoice = createMyVoicePanel({
  hasKey: () => Boolean(settings?.secrets?.openrouter),
  onChange: () => { void loadCatalog(); },
  sampleText: () => testLine,
  title: "Record or upload",
  list: false,
  description: "",
});

const finder = createClipFinder({
  jobs: () => jobs,
  available: () => Boolean(settings?.secrets?.openrouter),
  onCloned: () => { void loadCatalog(); setNotice("Voice cloned. It is in the library.", "ok"); },
  onNotice: (message, tone) => setNotice(message, tone),
});

const comparePanel = createComparePanel({
  catalog: () => catalog,
  play: (engine, voice, label) => playSelection({ kind: "stock", engine, voice, label }),
  playMine: (item) => playSelection({ kind: "clone", id: item.voice_id, label: cloneName(item) }),
  playback: () => ({ phase: playPhase, key: playKey }),
});

const recentPanel = createRecentPanel({
  isSpeaking: (entry) => isPlaying(recentKey(entry)),
  onPlay: replayRecent,
});

const setup = createVoiceSetup({
  getSettings: () => settings,
  onChanged: () => loadAll(),
});

function header() {
  const clone = el("button", {
    class: "vg-primary", type: "button",
    on: { click: () => navigate("create") },
  }, [iconSvg("plus"), "Clone a voice"]);
  return el("header", { class: "vg-header" }, [
    el("div", { class: "vg-brandline" }, [
      el("a", { class: "vg-brand", href: "/" }, ["VibeCut"]),
      el("span", { class: "vg-domain", text: "Voice Room" }),
    ]),
    el("div", { class: "vg-header-actions" }, [
      el("a", { class: "vg-oldui", href: "/voices", text: "Old UI" }),
      clone,
    ]),
  ]);
}

function navButton([name, label, index], withIndex = true) {
  const button = el("button", {
    type: "button",
    "data-view": name,
    "aria-current": view === name ? "page" : "false",
    on: { click: () => navigate(name) },
  }, [
    withIndex ? el("span", { class: "vg-nav-index", text: index }) : null,
    el("span", { text: label }),
  ]);
  if (view === name) button.classList.add("is-on");
  return button;
}

function rail() {
  navButtons = NAV.map((item) => navButton(item));
  return el("nav", { class: "vg-rail", "aria-label": "Voice Room" }, [
    el("div", { class: "vg-nav" }, navButtons),
  ]);
}

function tabs() {
  tabButtons = NAV.map((item) => navButton(item, false));
  return el("nav", { class: "vg-tabs", "aria-label": "Voice Room views" }, tabButtons);
}

function buildPlayer() {
  const dot = el("span", { class: "vg-phase", dataset: { phase: "idle" } });
  const strong = el("strong", { text: "Nothing playing" });
  const detail = el("span", { text: "Pick a voice to preview" });
  const line = el("input", {
    type: "text", maxLength: 300, value: testLine, "aria-label": "Test line",
  });
  line.addEventListener("input", () => {
    setTestLine(line.value, "player");
  });
  const rateSelect = el("select", { "aria-label": "Rate" });
  for (const value of RATES) {
    rateSelect.append(el("option", {
      value: String(value), text: `${value.toFixed(2)}×`, selected: value === rate,
    }));
  }
  rateSelect.addEventListener("change", () => {
    rate = Number(rateSelect.value) || 1;
    store(RATE_KEY, rate);
  });
  const stop = el("button", {
    class: "vg-stop", type: "button", text: "Stop",
    on: { click: stopVoice },
  });
  stop.disabled = true;
  const node = el("div", { class: "vg-player" }, [
    el("div", { class: "vg-player-status" }, [
      dot,
      el("div", { class: "vg-player-copy" }, [strong, detail]),
    ]),
    el("div", { class: "vg-player-controls" }, [
      el("label", { class: "vg-line" }, [el("span", { text: "Line" }), line]),
      el("label", { class: "vg-rate" }, [el("span", { text: "Rate" }), rateSelect]),
    ]),
    stop,
  ]);
  playerRefs = { dot, strong, detail, line, rateSelect, stop };
  return node;
}

function updateNav() {
  for (const button of navButtons.concat(tabButtons)) {
    const on = button.dataset.view === view;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-current", on ? "page" : "false");
  }
}

function navigate(next) {
  if (!VIEWS.includes(next)) next = "library";
  view = next;
  const hash = next === "library" ? "" : `#${next}`;
  window.history.replaceState(null, "", hash || window.location.pathname + window.location.search);
  updateNav();
  renderView();
}

function emptyState(title, copy, actionLabel, action) {
  const box = el("div", { class: "vg-empty" }, [
    el("strong", { text: title }),
    el("span", { text: copy }),
  ]);
  if (actionLabel) {
    const button = el("button", {
      class: "vg-secondary", type: "button", text: actionLabel,
      on: { click: action },
    });
    box.append(button);
  }
  return box;
}

function stockVoices(engine) {
  return (engine?.voices || []).filter((voice) => voice && !voice.clone);
}

function matchesVoice(voice) {
  if (languageFilter && langOf(voice) !== languageFilter) return false;
  if (!query) return true;
  const hay = `${voice?.name || ""} ${voice?.id || ""} ${voice?.lang || voice?.language || ""}`.toLowerCase();
  return hay.includes(query.toLowerCase());
}

function starFor(key, label, onChange) {
  const saved = isFavorite(key);
  const button = el("button", {
    class: `vg-star${saved ? " is-on" : ""}`, type: "button",
    text: saved ? "★" : "☆",
    "aria-label": `${saved ? "Remove" : "Add"} ${label} ${saved ? "from" : "to"} favorites`,
    "aria-pressed": saved ? "true" : "false",
    title: "Favorite",
  });
  button.addEventListener("click", () => {
    const now = toggleFavorite(key);
    button.textContent = now ? "★" : "☆";
    button.classList.toggle("is-on", now);
    button.setAttribute("aria-pressed", now ? "true" : "false");
    button.setAttribute("aria-label", `${now ? "Remove" : "Add"} ${label} ${now ? "from" : "to"} favorites`);
    onChange(now);
  });
  return button;
}

function cloneRow(item, repaint) {
  const id = item.voice_id;
  const name = cloneName(item);
  const playKey = `clone:${id}`;
  const play = el("button", {
    class: "vg-play", type: "button", text: isPlaying(playKey) ? "■" : "▶",
    "data-play-key": playKey, "data-label": name,
    "aria-label": `${isPlaying(playKey) ? "Stop" : "Play"} ${name}`,
    on: { click: () => playSelection({ kind: "clone", id, label: name }) },
  });
  const star = starFor(cloneKey(id), name, (now) => {
    if (!now && filter === "favorites") repaint();
  });
  const meta = [
    item.source === "video" ? "From a video" : "My voice",
    item.sample_seconds ? `${formatDuration(item.sample_seconds)} sample` : "",
    item.language || "",
  ].filter(Boolean).join(" · ");
  const main = el("div", { class: "vg-row-main" });
  if (renamingId === id) {
    const input = el("input", {
      type: "text", maxLength: 64, value: renameValue, "aria-label": `New name for ${name}`,
    });
    const save = el("button", { type: "button", text: "Save" });
    const cancel = el("button", { type: "button", text: "Cancel" });
    const commit = async () => {
      const next = input.value.trim();
      if (!next || next === name) {
        renamingId = "";
        repaint();
        return;
      }
      try {
        const record = await renameClone(id, next);
        Object.assign(item, record);
        renamingId = "";
        repaint();
        setNotice(`Renamed to ${record?.name || next}.`, "ok");
      } catch (cause) {
        setNotice(cause?.message || "Could not rename the voice.", "bad");
      }
    };
    save.addEventListener("click", () => { void commit(); });
    cancel.addEventListener("click", () => { renamingId = ""; repaint(); });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void commit();
      if (event.key === "Escape") { renamingId = ""; repaint(); }
    });
    main.append(el("div", { class: "vg-rename" }, [input, save, cancel]));
    window.setTimeout(() => { input.focus(); input.select(); }, 0);
  } else {
    main.append(el("strong", { text: name }), el("span", { class: "vg-row-meta", text: meta }));
  }
  const menu = el("details", { class: "vg-menu" }, [
    el("summary", { text: "⋯", "aria-label": `More actions for ${name}` }),
    el("div", {}, [
      el("button", {
        type: "button", text: "Rename",
        on: { click: () => { renamingId = id; renameValue = name; repaint(); } },
      }),
      el("button", {
        class: "is-danger", type: "button", text: "Delete",
        on: {
          click: async () => {
            if (!window.confirm(`Delete “${name}”? Its sample is removed from this Mac.`)) return;
            try {
              await deleteClone(id);
              if (isPlaying(playKey)) stopVoice();
              if (catalog?.clones) catalog.clones = catalog.clones.filter((row) => row.voice_id !== id);
              setNotice(`Deleted ${name}.`, "ok");
              repaint();
            } catch (cause) {
              setNotice(cause?.message || "Could not delete the voice.", "bad");
            }
          },
        },
      }),
    ]),
  ]);
  return el("div", { class: "vg-row", "data-clone": id }, [play, main, star, menu]);
}

function stockRow(engine, voice) {
  const id = String(voice.id ?? "");
  const label = stockName(voice);
  const playKey = `${engine.id}:${id}`;
  const play = el("button", {
    class: "vg-play", type: "button", text: isPlaying(playKey) ? "■" : "▶",
    "data-play-key": playKey, "data-label": label,
    "aria-label": `${isPlaying(playKey) ? "Stop" : "Play"} ${label}`,
    on: { click: () => playSelection({ kind: "stock", engine: engine.id, voice: id, label }) },
  });
  const star = starFor(stockKey(engine.id, id), label, (now) => {
    if (!now && filter === "favorites") paintLibraryList();
  });
  return el("div", { class: "vg-row is-stock", "data-voice": `${engine.id}:${id}` }, [
    play,
    el("div", { class: "vg-row-main" }, [
      el("strong", { text: label }),
      el("span", { class: "vg-row-meta", text: `${engine.label || engine.id} · ${voice.lang || "multi"}` }),
    ]),
    star,
  ]);
}

let paintLibraryList = () => {};

function buildLibrary() {
  const node = el("div", { class: "vg-view" });
  const count = el("p", { class: "vg-result" });
  const search = el("input", {
    class: "vg-search", type: "search", value: query,
    placeholder: "Search voices", "aria-label": "Search voices",
  });
  search.addEventListener("input", () => { query = search.value.trim(); paintLibraryList(); });

  const engine = el("select", { class: "vg-select", "aria-label": "Engine" }, [
    el("option", { value: "", text: "All engines", selected: !engineFilter }),
    ...((catalog?.engines || []).filter((row) => row.available).map((row) => el("option", {
      value: row.id, text: row.label, selected: row.id === engineFilter,
    }))),
  ]);
  engine.addEventListener("change", () => { engineFilter = engine.value; paintLibraryList(); });

  const languages = new Set();
  for (const row of catalog?.engines || []) for (const voice of stockVoices(row)) languages.add(langOf(voice));
  for (const row of catalog?.clones || []) languages.add(langOf(row));
  const language = el("select", { class: "vg-select", "aria-label": "Language" }, [
    el("option", { value: "", text: "All languages", selected: !languageFilter }),
    ...[...languages].filter((code) => code !== "multi").sort().map((code) => el("option", {
      value: code, text: code, selected: code === languageFilter,
    })),
  ]);
  language.addEventListener("change", () => { languageFilter = language.value; paintLibraryList(); });

  const filters = el("div", { class: "vg-seg" });
  for (const [name, label] of [["all", "All"], ["favorites", "Favorites"], ["clones", "Clones"], ["stock", "Stock"]]) {
    const button = el("button", {
      type: "button", text: label, "aria-pressed": filter === name ? "true" : "false",
    });
    button.classList.toggle("is-on", filter === name);
    button.addEventListener("click", () => {
      filter = name;
      for (const row of filters.children) {
        const on = row.textContent === label;
        row.classList.toggle("is-on", on);
        row.setAttribute("aria-pressed", on ? "true" : "false");
      }
      paintLibraryList();
    });
    filters.append(button);
  }

  const list = el("div", { class: "vg-list" });
  const head = el("div", { class: "vg-view-head" }, [
    el("div", {}, [
      el("h1", { text: "Voice library" }),
      el("p", { text: "Preview, clone and compare the voices available on this Mac." }),
    ]),
    el("div", { class: "vg-actions" }, [
      el("button", {
        class: "vg-primary", type: "button",
        on: { click: () => navigate("create") },
      }, [iconSvg("plus"), "Clone a voice"]),
    ]),
  ]);

  function group(title, rows, open = true) {
    const details = el("details", { class: "vg-group" });
    if (open) details.open = true;
    details.append(el("summary", { class: "vg-group-head" }, [
      el("h2", { text: title }),
      el("span", { text: `${rows.length}` }),
    ]));
    details.append(el("div", { class: "vg-rows" }, rows));
    return details;
  }

  paintLibraryList = () => {
    const clones = catalog?.clones || [];
    const engines = (catalog?.engines || []).filter((row) => row.available);
    const cloneRows = [];
    if (filter !== "stock" && (!engineFilter || engineFilter === "heygen")) {
      for (const item of clones) {
        if (filter === "favorites" && !isFavorite(cloneKey(item.voice_id))) continue;
        if (!matchesVoice(item)) continue;
        cloneRows.push(cloneRow(item, paintLibraryList));
      }
    }
    const groups = [];
    let stockCount = 0;
    if (filter !== "clones") {
      for (const row of engines) {
        if (engineFilter && row.id !== engineFilter) continue;
        const voices = stockVoices(row).filter((voice) => {
          if (filter === "favorites" && !isFavorite(stockKey(row.id, voice.id))) return false;
          return matchesVoice(voice);
        });
        if (!voices.length) continue;
        stockCount += voices.length;
        groups.push(group(row.label || row.id, voices.map((voice) => stockRow(row, voice)), Boolean(query || engineFilter || filter === "stock")));
      }
    }
    const total = cloneRows.length + stockCount;
    count.textContent = `${total} ${total === 1 ? "voice" : "voices"}${cloneRows.length ? ` · ${cloneRows.length} cloned` : ""}`;
    list.replaceChildren();
    const firstRun = filter === "all" && clones.length === 0
      && !query && !engineFilter && !languageFilter;
    if (cloneRows.length) {
      list.append(group("Your voices", cloneRows, true));
    } else if (firstRun) {
      list.append(emptyState(
        "No cloned voices yet",
        "Record, upload or use a video to make the first one.",
        "Create a voice",
        () => navigate("create"),
      ));
    }
    list.append(...groups);
    if (!total && !firstRun) {
      list.append(emptyState(
        filter === "favorites" ? "No favorite voices match" : "No voices match",
        "Change the filters or add a favorite.",
      ));
    }
  };

  node.append(head, el("div", { class: "vg-toolbar" }, [
    search, filters, engine, language,
  ]), count, list);
  paintLibraryList();
  return node;
}

function buildCreate() {
  const node = el("div", { class: "vg-view" });
  const panel = el("div", { class: "vg-create-panel" });
  const head = el("div", { class: "vg-view-head" }, [
    el("div", {}, [
      el("h1", { text: "Create a voice" }),
      el("p", { text: "Use 30 seconds to 3 minutes of clear speech. Clone only your own voice, or a speaker who gave you permission." }),
    ]),
  ]);
  const tabs = el("div", { class: "vg-seg vg-create-tabs" });
  const paint = () => {
    tabs.replaceChildren();
    for (const [name, label, icon] of [
      ["record", "Record or upload", "mic"],
      ["video", "From a video", "video"],
    ]) {
      const button = el("button", {
        type: "button", "aria-pressed": createTab === name ? "true" : "false",
      }, [iconSvg(icon), el("span", { text: label })]);
      button.classList.toggle("is-on", createTab === name);
      button.addEventListener("click", () => { createTab = name; paint(); });
      tabs.append(button);
    }
    panel.replaceChildren();
    if (createTab === "record") {
      myVoice.render();
      panel.append(myVoice.node);
    } else {
      finder.render();
      panel.append(finder.node);
    }
  };
  const quick = el("div", { class: "vg-quick" });
  const quickCard = (icon, title, copy, action) => {
    const button = el("button", { class: "vg-quick-card", type: "button" }, [
      el("span", { class: "vg-quick-icon" }, [iconSvg(icon)]),
      el("strong", { text: title }),
      el("span", { text: copy }),
    ]);
    button.addEventListener("click", action);
    return button;
  };
  quick.append(
    quickCard("mic", "Record my voice", "Use the microphone", () => {
      createTab = "record";
      paint();
      window.setTimeout(() => {
        myVoice.node.querySelector(".st-voice-clone-recorder .st-btn")?.click();
      }, 0);
    }),
    quickCard("upload", "Upload a recording", "WAV, MP3, M4A or video", () => {
      createTab = "record";
      paint();
      window.setTimeout(() => {
        myVoice.node.querySelector('input[type="file"]')?.click();
      }, 0);
    }),
    quickCard("video", "Use a video", "Find clean speech", () => {
      createTab = "video";
      paint();
    }),
  );
  paint();
  node.append(head, quick, tabs, panel);
  return node;
}

function buildCompare() {
  comparePanel.render();
  const line = el("textarea", {
    class: "vg-line-hero", rows: 3, maxLength: 300, value: testLine,
    "aria-label": "Line to compare",
    placeholder: "Type the line both voices should say",
  });
  compareLineEl = line;
  line.addEventListener("input", () => setTestLine(line.value, "compare"));
  const count = el("span", { class: "vg-line-count", text: `${line.value.length}/300` });
  line.addEventListener("input", () => { count.textContent = `${line.value.length}/300`; });
  const lineCard = el("div", { class: "vg-compare-line" }, [
    el("div", { class: "vg-compare-line-head" }, [
      el("div", {}, [
        el("h1", { text: "Compare voices" }),
        el("p", { text: "Type the line once. Both voices read the same words at the same rate." }),
      ]),
      el("span", { class: "vg-compare-line-tag", text: "Shared line" }),
    ]),
    line,
    el("div", { class: "vg-compare-line-foot" }, [
      el("span", { text: "This line is also used by every Play in the library." }),
      count,
    ]),
  ]);
  return el("div", { class: "vg-view vg-compare-view" }, [lineCard, comparePanel.node]);
}

function buildRecent() {
  recentPanel.render();
  return el("div", { class: "vg-view" }, [recentPanel.node]);
}

function buildSettings() {
  setup.render();
  const node = el("div", { class: "vg-view" }, [setup.node]);
  window.setTimeout(() => setup.open(), 0);
  return node;
}

function renderView() {
  if (!mainEl) return;
  compareLineEl = null;
  mainEl.replaceChildren();
  if (loading && !catalog) {
    mainEl.append(el("div", { class: "vg-view" }, [el("p", { class: "hint", text: "Reading this Mac…" })]));
    return;
  }
  if (error) {
    mainEl.append(el("div", { class: "vg-view" }, [el("p", { class: "error", role: "alert", text: error })]));
  }
  if (view === "library") mainEl.append(buildLibrary());
  else if (view === "create") mainEl.append(buildCreate());
  else if (view === "compare") mainEl.append(buildCompare());
  else if (view === "recent") mainEl.append(buildRecent());
  else if (view === "settings") mainEl.append(buildSettings());
  updateNav();
}

function shell() {
  mainEl = el("main", { class: "vg-main" });
  const node = el("div", { class: "vg-shell" }, [
    header(),
    rail(),
    mainEl,
    buildPlayer(),
    tabs(),
  ]);
  root.replaceChildren(node);
  updatePlayer();
}

async function loadAll() {
  loading = !catalog;
  error = "";
  if (!catalog) renderView();
  const [settingsResult, catalogResult, jobsResult] = await Promise.allSettled([
    request("/api/settings"),
    request("/api/voices/catalog"),
    listJobs({ limit: 40 }),
  ]);
  if (settingsResult.status === "fulfilled") settings = settingsResult.value;
  else error = settingsResult.reason?.message || "Could not read this app's setup.";
  if (catalogResult.status === "fulfilled") catalog = catalogResult.value;
  else error = error || catalogResult.reason?.message || "Could not read the voices on this machine.";
  jobs = jobsResult.status === "fulfilled"
    ? (jobsResult.value?.jobs || []).filter((job) => job.status === "ready" && !job.source_deleted && !job.source_missing)
    : [];
  loading = false;
  renderView();
  updatePlayer();
}

async function loadCatalog() {
  try {
    catalog = await request("/api/voices/catalog");
    error = "";
    renderView();
  } catch (cause) {
    setNotice(cause?.message || "Could not read the voices on this machine.", "bad");
  }
}

window.addEventListener("hashchange", () => {
  const next = viewFromHash();
  if (next === view) return;
  view = next;
  renderView();
});

shell();
void loadAll();
