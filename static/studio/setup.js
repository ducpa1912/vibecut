/**
 * Studio — Setup.
 *
 * One place to see the engines this Mac can use, save the creator's own cloud
 * keys and check the optional model packs. Setup never reads a saved key back:
 * the server only reports whether a key exists and where it came from.
 *
 * Existing routes only:
 *   GET  /api/settings
 *   POST /api/settings          (secrets only)
 *   GET  /api/audio/engines
 *
 * Optional packs have no install route on this build, so the screen reports
 * what is already on disk. It never pretends a download happened.
 */

import { request } from "./api.js";
import { el, formatBytes } from "./ui.js";

const KEY_ROWS = [
  {
    id: "openrouter",
    title: "OpenRouter",
    copy: "One key for HeyGen, Fish Audio and Gemini voices, cloud music and AI text.",
    place: "sk-or-…",
  },
  {
    id: "minimax",
    title: "MiniMax",
    copy: "MiniMax Speech 2.8 Turbo and Music 3.0.",
    place: "MiniMax API key",
  },
  {
    id: "elevenlabs",
    title: "ElevenLabs",
    copy: "Premium multilingual voice-over and dub.",
    place: "ElevenLabs API key",
  },
];

const VOICE_LABELS = {
  say: "Apple voices",
  kokoro: "Kokoro",
  heygen: "HeyGen Voice Turbo",
  minimax: "MiniMax Speech",
  elevenlabs: "ElevenLabs",
  fish: "Fish Audio",
  gemini: "Gemini TTS",
};

const OPENROUTER_VOICES = ["heygen", "fish", "gemini"];
const LOCAL_VOICES = ["say", "kokoro"];
const CLOUD_VOICES = ["minimax", "elevenlabs"];

function sourceCopy(value) {
  if (value === "env") return "From an environment variable";
  if (value === "file") return "Saved on this Mac";
  return "Not set";
}

function engineTone(available) {
  return available ? "st-chip-ok" : "st-chip-busy";
}

function engineState(available) {
  return available ? "Ready" : "Needs setup";
}

function whisperRows(settings) {
  const models = settings?.runtime?.whisper_models;
  return Array.isArray(models) ? models : [];
}

function packRows(settings, engines) {
  const models = whisperRows(settings);
  const cached = models.filter((item) => item?.cached);
  const voice = Boolean(engines?.voices?.kokoro?.available);
  const separation = Boolean(engines?.separation?.demucs?.available);
  return [
    {
      id: "speech",
      title: "Speech Pack",
      size: 1900,
      installed: cached.length > 0,
      detail: cached.length
        ? `${models.find((item) => item?.cached)?.name || "Whisper large turbo"} is on this Mac.`
        : "Adds Whisper large turbo for accents and languages Apple Speech does not cover.",
    },
    {
      id: "voice",
      title: "Voice Pack",
      size: 700,
      installed: voice,
      detail: voice
        ? "Kokoro voices are ready offline."
        : "Adds offline Kokoro voices in English and Chinese.",
    },
    {
      id: "separation",
      title: "Separation Pack",
      size: 800,
      installed: separation,
      detail: separation
        ? "HTDemucs is ready for dub without the original voice."
        : "Optional. Only needed when a dub must remove the original voice.",
    },
  ];
}

export function mount(host, ctx = {}) {
  let disposed = false;
  let settings = null;
  let engines = null;
  let loading = true;
  let error = "";
  let notice = "";
  let noticeTone = "";
  let saving = "";
  let keyDraft = { openrouter: "", minimax: "", elevenlabs: "" };

  host.replaceChildren(el("p", { class: "st-hint", text: "Reading this Mac…" }));

  function keyStatus(id) {
    const has = Boolean(settings?.secrets?.[id]);
    return {
      has,
      source: sourceCopy(settings?.sources?.[id]),
    };
  }

  function engineCard(id) {
    const item = engines?.voices?.[id] || {};
    const available = Boolean(item?.available);
    const isHeyGen = id === "heygen";
    const card = el("div", { class: "st-setup-engine" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: VOICE_LABELS[id] || id }),
        el("span", { class: `st-chip ${engineTone(available)}`, text: engineState(available) }),
        isHeyGen ? el("span", { class: "st-chip st-chip-busy", text: "Free until 30 Nov 2026" }) : null,
      ]),
      el("p", { class: "st-hint", text: item.install || "Cloud voice." }),
    ]);
    return card;
  }

  function group(title, ids, hint = "") {
    const card = el("div", { class: "st-setup-group" });
    card.append(el("div", { class: "st-setup-group-head" }, [
      el("h4", { text: title }),
      hint ? el("p", { class: "st-hint", text: hint }) : null,
    ]));
    for (const id of ids) {
      if (engines?.voices?.[id]) card.append(engineCard(id));
    }
    return card;
  }

  function keysCard() {
    const card = el("div", { class: "st-setup-section" });
    card.append(el("div", { class: "st-setup-section-head" }, [
      el("h3", { text: "Keys" }),
      el("p", { class: "st-hint", text: "Keys stay on this Mac. Setup never shows a saved key again. An environment variable also counts." }),
    ]));
    for (const row of KEY_ROWS) {
      const status = keyStatus(row.id);
      const input = el("input", {
        type: "password",
        value: "",
        autocomplete: "off",
        spellcheck: "false",
        placeholder: row.place,
        "aria-label": `${row.title} key`,
      });
      input.value = "";
      input.addEventListener("input", () => { keyDraft[row.id] = input.value; });
      const save = el("button", {
        class: "st-btn st-btn-ghost st-btn-small",
        type: "button",
        text: saving === row.id ? "Saving…" : "Save key",
        disabled: saving === row.id,
      });
      save.addEventListener("click", () => { void saveKey(row.id, input, save); });
      const clear = el("button", {
        class: "st-btn st-btn-quiet st-btn-small",
        type: "button",
        text: "Remove saved key",
        disabled: saving === row.id || !status.has || settings?.sources?.[row.id] === "env",
        title: settings?.sources?.[row.id] === "env"
          ? "This key comes from an environment variable."
          : "",
      });
      clear.addEventListener("click", () => { void clearKey(row.id, clear); });
      card.append(el("div", { class: "st-setup-key" }, [
        el("div", { class: "st-setup-key-head" }, [
          el("strong", { text: row.title }),
          el("span", { class: `st-chip ${status.has ? "st-chip-ok" : ""}`, text: status.source }),
        ]),
        el("p", { class: "st-hint", text: row.copy }),
        el("div", { class: "st-setup-key-form" }, [
          input,
          el("div", { class: "st-setup-key-actions" }, [save, clear]),
        ]),
      ]));
    }
    return card;
  }

  function enginesCard() {
    const card = el("div", { class: "st-setup-section" });
    card.append(el("div", { class: "st-setup-section-head" }, [
      el("h3", { text: "Engines" }),
      el("p", { class: "st-hint", text: "Voices, music, transcription and translation. Offline engines work with the network off." }),
    ]));
    card.append(
      group("On this Mac", LOCAL_VOICES, "Built in or installed as a pack."),
      group("Cloud voices", CLOUD_VOICES, "Use the creator's own key."),
      group("OpenRouter voices", OPENROUTER_VOICES, "All three share the OpenRouter key. HeyGen is first in the voice picker."),
    );

    const models = whisperRows(settings);
    const transcription = el("div", { class: "st-setup-group" });
    transcription.append(el("div", { class: "st-setup-group-head" }, [el("h4", { text: "Transcription" })]));
    const active = models.find((item) => item?.current);
    transcription.append(el("div", { class: "st-setup-engine" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: "Apple Speech" }),
        el("span", { class: "st-chip st-chip-ok", text: "Built in" }),
      ]),
      el("p", { class: "st-hint", text: "On-device, word-level timing, no download." }),
    ]));
    transcription.append(el("div", { class: "st-setup-engine" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: "Whisper large turbo" }),
        el("span", {
          class: `st-chip ${models.some((item) => item?.cached) ? "st-chip-ok" : "st-chip-busy"}`,
          text: models.some((item) => item?.cached) ? "On this Mac" : "Needs Speech Pack",
        }),
      ]),
      el("p", { class: "st-hint", text: active ? `Current model: ${active.name || active.id}` : "Higher accuracy for accents and languages Apple does not cover." }),
    ]));
    card.append(transcription);

    const music = el("div", { class: "st-setup-group" });
    music.append(el("div", { class: "st-setup-group-head" }, [el("h4", { text: "Music" })]));
    for (const [id, item] of Object.entries(engines?.music || {})) {
      const available = Boolean(item?.available);
      const label = id === "library" ? "Your music library"
        : id === "minimax-music" ? "MiniMax Music 3.0"
          : id === "lyria-clip" ? "Lyria on OpenRouter" : id;
      music.append(el("div", { class: "st-setup-engine" }, [
        el("div", { class: "st-setup-engine-head" }, [
          el("strong", { text: label }),
          el("span", { class: `st-chip ${engineTone(available)}`, text: engineState(available) }),
        ]),
        el("p", { class: "st-hint", text: item?.install || "" }),
      ]));
    }
    card.append(music);
    return card;
  }

  function packsCard() {
    const card = el("div", { class: "st-setup-section" });
    card.append(el("div", { class: "st-setup-section-head" }, [
      el("h3", { text: "Packs" }),
      el("p", { class: "st-hint", text: "Optional downloads. No pack is needed for Import, Check, Stories, Edit or a basic render." }),
    ]));
    for (const pack of packRows(settings, engines)) {
      card.append(el("div", { class: "st-setup-pack" }, [
        el("div", { class: "st-setup-engine-head" }, [
          el("strong", { text: pack.title }),
          el("span", {
            class: `st-chip ${pack.installed ? "st-chip-ok" : ""}`,
            text: pack.installed ? "Installed" : "Not installed",
          }),
          el("span", { class: "st-mono st-hint", text: formatBytes(pack.size * 1024 * 1024) }),
        ]),
        el("p", { class: "st-hint", text: pack.detail }),
        el("p", {
          class: "st-field-hint",
          text: pack.installed
            ? "Already on this Mac. This screen only reports the pack; removal waits for the Mac packaging screen."
            : "Pack download is not wired into this Studio build yet. This screen reports what is already on disk.",
        }),
      ]));
    }
    return card;
  }

  function render() {
    if (disposed) return;
    if (loading) {
      host.replaceChildren(el("p", { class: "st-hint", text: "Reading this Mac…" }));
      return;
    }
    host.replaceChildren();
    const wrap = el("div", { class: "st-setup" });
    const head = el("div", { class: "st-setup-head" }, [
      el("div", {}, [
        el("p", { class: "st-eyebrow", text: "Studio setup" }),
        el("h2", { text: "Engines, keys and packs" }),
        el("p", { class: "st-hint", text: "Everything here is optional except the built-in Apple tools. Cloud features use your own keys." }),
      ]),
      (() => {
        const refresh = el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Refresh" });
        refresh.addEventListener("click", () => { void load(true); });
        return refresh;
      })(),
    ]);
    wrap.append(head);
    if (error) wrap.append(el("p", { class: "st-error", role: "alert", text: error }));
    if (notice) {
      const line = el("p", { class: "st-status", text: notice, role: "status" });
      line.dataset.tone = noticeTone;
      wrap.append(line);
    }
    wrap.append(enginesCard(), keysCard(), packsCard());
    host.append(wrap);
  }

  async function load(refresh = false) {
    loading = true;
    error = "";
    if (refresh) {
      notice = "";
      noticeTone = "";
    }
    render();
    try {
      const [state, engineState] = await Promise.all([
        request("/api/settings"),
        request("/api/audio/engines"),
      ]);
      if (disposed) return;
      settings = state;
      engines = engineState;
    } catch (cause) {
      if (disposed) return;
      error = cause?.message || "Could not read setup.";
    } finally {
      loading = false;
      if (!disposed) render();
    }
  }

  async function saveKey(id, input, button) {
    const value = String(keyDraft[id] || "").trim();
    if (!value) {
      notice = `Enter a ${id} key first.`;
      noticeTone = "bad";
      render();
      return;
    }
    saving = id;
    notice = `Saving the ${id} key…`;
    noticeTone = "";
    button.disabled = true;
    render();
    try {
      settings = await request("/api/settings", {
        method: "POST",
        body: { secrets: { [id]: value } },
      });
      if (disposed) return;
      keyDraft[id] = "";
      settings = await request("/api/settings");
      engines = await request("/api/audio/engines");
      notice = `${id === "openrouter" ? "OpenRouter" : id === "minimax" ? "MiniMax" : "ElevenLabs"} key saved. Cloud features are ready.`;
      noticeTone = "ok";
    } catch (cause) {
      if (disposed) return;
      notice = cause?.message || "Could not save the key.";
      noticeTone = "bad";
    } finally {
      saving = "";
      if (!disposed) render();
    }
  }

  async function clearKey(id, button) {
    saving = id;
    notice = "Removing the saved key…";
    noticeTone = "";
    button.disabled = true;
    render();
    try {
      settings = await request("/api/settings", {
        method: "POST",
        body: { secrets: { [id]: "" } },
      });
      if (disposed) return;
      engines = await request("/api/audio/engines");
      notice = "Saved key removed. Cloud features that need it are hidden again.";
      noticeTone = "ok";
    } catch (cause) {
      if (disposed) return;
      notice = cause?.message || "Could not remove the key.";
      noticeTone = "bad";
    } finally {
      saving = "";
      if (!disposed) render();
    }
  }

  void load();

  return () => {
    disposed = true;
  };
}
