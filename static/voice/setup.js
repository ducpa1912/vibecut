/**
 * VibeCut Voice — Setup.
 *
 * This is the one Setup for the app. It copies the original Studio layout:
 *
 *   Keys      OpenRouter, MiniMax, ElevenLabs. Save or remove one key per
 *             provider. Setup never reads a saved key back.
 *   Voices    Local, cloud and one OpenRouter row. HeyGen, Fish and Gemini
 *             share the OpenRouter key; they are not separate setups.
 *   Speech    Local Whisper, with its install hint.
 *   Library   Backup/restore and a portable .vcutvoice import.
 *
 * Routes: GET/POST /api/settings, GET /api/audio/engines,
 * GET /api/voices/readiness, the voice library ZIP and persona routes.
 */

import {
  announceChange,
  errorDetail,
  request,
  syncTokenCookie,
  tokenValue,
} from "./api.js";
import { el } from "./ui.js";
import { importPersona } from "./voiceclone.js";

const KEY_ROWS = [
  {
    id: "openrouter",
    title: "OpenRouter",
    copy: "One key for HeyGen Voice Turbo (cloning), Fish, Gemini, cloud music and text. The voices share this key; there is no separate key per model.",
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

const ENGINE_LABELS = {
  say: "Apple voices",
  kokoro: "Kokoro",
  minimax: "MiniMax Speech",
  elevenlabs: "ElevenLabs",
  heygen: "HeyGen Voice Turbo",
  fish: "Fish Audio",
  gemini: "Gemini TTS",
};

const LOCAL_VOICES = ["say", "kokoro"];
const CLOUD_VOICES = ["minimax", "elevenlabs"];
const OPENROUTER_VOICES = ["heygen", "fish", "gemini"];

function sourceCopy(value) {
  if (value === "env") return "From an environment variable";
  if (value === "file") return "Saved on this Mac";
  return "Not set";
}

function engineState(item, cloud) {
  if (item?.available) return "Ready";
  return cloud ? "Needs key" : "Needs setup";
}

export function createVoiceSetup({ getSettings, onChanged = () => {} }) {
  const node = el("section", { class: "vr-section vr-setup", id: "voice-setup", "data-panel": "setup" });
  let engines = null;
  let enginesBusy = false;
  let whisper = null;
  let whisperBusy = false;
  let notice = "";
  let noticeTone = "";
  let saving = "";
  const keyDraft = { openrouter: "", minimax: "", elevenlabs: "" };
  let libraryFile = null;
  let libraryConsent = false;
  let libraryBusy = "";
  let libraryStatus = "";
  let libraryTone = "";
  let personaFile = null;
  let personaConsent = false;
  let personaName = "";
  let personaBusy = false;
  let personaStatus = "";
  let personaTone = "";

  function settings() {
    return getSettings() || null;
  }

  function setNotice(message, tone = "") {
    notice = message || "";
    noticeTone = tone;
  }

  async function loadEngines() {
    if (engines || enginesBusy) return;
    enginesBusy = true;
    try {
      engines = await request("/api/audio/engines");
    } catch (_) {
      engines = null;
    } finally {
      enginesBusy = false;
      render();
    }
  }

  async function loadWhisper() {
    if (whisperBusy) return;
    whisperBusy = true;
    try {
      const result = await request("/api/voices/readiness");
      whisper = (result?.items || []).find((item) => item.id === "whisper") || null;
    } catch (_) {
      whisper = null;
    } finally {
      whisperBusy = false;
      render();
    }
  }

  async function saveKey(row, input) {
    const value = String(input?.value || keyDraft[row.id] || "").trim();
    if (!value) {
      setNotice(`Paste the ${row.title} key first.`, "bad");
      render();
      return;
    }
    saving = row.id;
    setNotice(`Saving the ${row.title} key…`);
    render();
    try {
      await request("/api/settings", { method: "POST", body: { secrets: { [row.id]: value } } });
      keyDraft[row.id] = "";
      if (input) input.value = "";
      // The key changes what the engines can do; read them again.
      engines = null;
      whisper = null;
      await Promise.all([loadEngines(), loadWhisper()]);
      await onChanged();
      setNotice(`${row.title} key saved for this app only.`, "ok");
    } catch (cause) {
      setNotice(cause?.message || `Could not save the ${row.title} key. Check it and try again.`, "bad");
    } finally {
      saving = "";
      render();
    }
  }

  async function clearKey(row) {
    saving = row.id;
    setNotice(`Removing the saved ${row.title} key…`);
    render();
    try {
      await request("/api/settings", { method: "POST", body: { secrets: { [row.id]: "" } } });
      engines = null;
      whisper = null;
      await Promise.all([loadEngines(), loadWhisper()]);
      await onChanged();
      setNotice(`${row.title} saved key removed. This app will use the environment key, if there is one.`, "ok");
    } catch (cause) {
      setNotice(cause?.message || `Could not remove the ${row.title} key.`, "bad");
    } finally {
      saving = "";
      render();
    }
  }

  function keyRow(row, state) {
    const has = Boolean(state.secrets?.[row.id]);
    const source = state.sources?.[row.id] || "";
    const input = el("input", {
      type: "password", autocomplete: "off", spellcheck: "false",
      placeholder: row.place, "aria-label": `${row.title} key`,
      disabled: Boolean(saving),
    });
    input.value = keyDraft[row.id] || "";
    input.addEventListener("input", () => { keyDraft[row.id] = input.value; });
    const save = el("button", {
      class: "primary small", type: "button",
      text: saving === row.id ? "Saving…" : "Save key",
      disabled: Boolean(saving),
    });
    save.addEventListener("click", () => { void saveKey(row, input); });
    const remove = el("button", {
      class: "ghost small danger", type: "button", text: "Remove saved key",
      disabled: Boolean(saving) || !has || source === "env",
      title: source === "env" ? "This key comes from an environment variable." : "",
    });
    remove.addEventListener("click", () => { void clearKey(row); });
    return el("div", { class: "vr-key", "data-key": row.id }, [
      el("div", { class: "vr-key-head" }, [
        el("strong", { text: row.title }),
        el("span", { class: `vr-chip${has ? " is-cloud" : ""}`, text: sourceCopy(source) }),
      ]),
      el("p", { class: "hint", text: row.copy }),
      el("div", { class: "vr-key-form" }, [input, save, remove]),
    ]);
  }

  function keysCard(state) {
    const card = el("div", { class: "vr-card vr-setup-card" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Keys" }),
          el("p", { class: "hint", text: "Saved on this Mac in this app's own secrets file. Setup never shows a saved key again; an environment variable also counts." }),
        ]),
      ]),
    ]);
    for (const row of KEY_ROWS) card.append(keyRow(row, state));
    return card;
  }

  function engineRow(id) {
    const item = engines?.voices?.[id] || {};
    const cloud = !LOCAL_VOICES.includes(id);
    const detail = item.available
      ? (cloud ? "Ready with the key saved in Keys." : (item.install || "Ready on this Mac."))
      : (item.install || "Needs setup.");
    return el("div", { class: "vr-setup-engine", "data-engine": id }, [
      el("div", { class: "vr-setup-engine-head" }, [
        el("strong", { text: ENGINE_LABELS[id] || id }),
        el("span", { class: `vr-chip${item.available ? " is-cloud" : ""}`, text: engineState(item, cloud) }),
      ]),
      el("p", { class: "hint", text: detail }),
    ]);
  }

  function group(title, rows, hint = "") {
    return el("div", { class: "vr-setup-group" }, [
      el("div", { class: "vr-setup-group-head" }, [
        el("h4", { text: title }),
        hint ? el("p", { class: "hint", text: hint }) : null,
      ]),
      el("div", { class: "vr-setup-engines" }, rows),
    ]);
  }

  function openRouterRow() {
    const available = OPENROUTER_VOICES.some((id) => engines?.voices?.[id]?.available);
    const install = engines?.voices?.heygen?.install || "Add an OpenRouter key in Keys above.";
    return el("div", { class: "vr-setup-engine", "data-engine": "openrouter-voices" }, [
      el("div", { class: "vr-setup-engine-head" }, [
        el("strong", { text: "OpenRouter voices" }),
        el("span", { class: `vr-chip${available ? " is-cloud" : ""}`, text: available ? "Ready" : "Needs key" }),
      ]),
      el("p", { class: "hint", text: "HeyGen Voice Turbo (cloning), Fish and Gemini share the OpenRouter key. One key; no per-model setup." }),
      available ? null : el("p", { class: "hint", text: install }),
    ]);
  }

  function whisperRow() {
    if (!whisper) {
      return el("div", { class: "vr-setup-engine" }, [
        el("div", { class: "vr-setup-engine-head" }, [
          el("strong", { text: "Local Whisper" }),
          el("span", { class: "vr-chip", text: whisperBusy ? "Checking…" : "Unknown" }),
        ]),
        el("p", { class: "hint", text: "Used for language detection and line checks." }),
      ]);
    }
    const ready = whisper.state === "ready";
    const check = el("button", {
      class: "ghost small", type: "button", text: "Check again",
      disabled: whisperBusy,
    });
    check.addEventListener("click", () => { void loadWhisper(); });
    return el("div", { class: "vr-setup-engine", "data-engine": "whisper" }, [
      el("div", { class: "vr-setup-engine-head" }, [
        el("strong", { text: "Local Whisper" }),
        el("span", { class: `vr-chip${ready ? " is-cloud" : ""}`, text: ready ? "Ready" : "Failed" }),
      ]),
      el("p", { class: "hint", text: whisper.detail || "" }),
      el("div", { class: "vr-key-form" }, [check]),
    ]);
  }

  function voicesCard() {
    const card = el("div", { class: "vr-card vr-setup-card" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Voices" }),
          el("p", { class: "hint", text: "What this Mac and your keys can speak with. A key turns its voices Ready; no extra setup per model." }),
        ]),
      ]),
    ]);
    if (!engines) {
      card.append(el("p", { class: "hint", text: enginesBusy ? "Reading this Mac…" : "Could not read the voices on this Mac. Reload the page." }));
    } else {
      card.append(
        group("On this Mac", LOCAL_VOICES.map(engineRow), "Built in or installed as a pack."),
        group("Cloud voices", CLOUD_VOICES.map(engineRow), "Use your own key from Keys."),
        group("OpenRouter", [openRouterRow()], "One key, three voices."),
        group("Speech to text", [whisperRow()], "Runs on this Mac."),
      );
    }
    return card;
  }

  async function downloadLibrary() {
    if (libraryBusy) return;
    libraryBusy = "export";
    libraryStatus = "Building the backup…";
    libraryTone = "";
    render();
    try {
      syncTokenCookie();
      const headers = { Accept: "application/zip" };
      const token = tokenValue();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch("/api/voices/library/export", {
        method: "GET", headers, credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) {
        let payload = null;
        try { payload = JSON.parse(await response.text()); } catch (_) { payload = null; }
        throw new Error(errorDetail(payload) || "Could not build the backup. Try again.");
      }
      const blob = await response.blob();
      const match = /filename="?([^";]+)"?/i.exec(String(response.headers.get("Content-Disposition") || ""));
      const name = match ? match[1] : "vibecut-voice-library.zip";
      const url = URL.createObjectURL(blob);
      const link = el("a", { href: url, download: name });
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      libraryStatus = `Saved ${name}.`;
      libraryTone = "ok";
    } catch (cause) {
      libraryStatus = cause?.message || "Could not build the backup. Try again.";
      libraryTone = "bad";
    } finally {
      libraryBusy = "";
      render();
    }
  }

  async function restoreLibrary() {
    if (libraryBusy) return;
    if (!libraryFile) {
      libraryStatus = "Choose a backup ZIP first.";
      libraryTone = "bad";
      render();
      return;
    }
    if (!libraryConsent) {
      libraryStatus = "Tick the box to confirm you have permission to restore these voices.";
      libraryTone = "bad";
      render();
      return;
    }
    libraryBusy = "import";
    libraryStatus = "Restoring voices…";
    libraryTone = "";
    render();
    try {
      const form = new FormData();
      form.append("file", libraryFile, libraryFile.name || "voice-library.zip");
      form.append("consent", "true");
      syncTokenCookie();
      const headers = { Accept: "application/json" };
      const token = tokenValue();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch("/api/voices/library/import", {
        method: "POST", headers, body: form, credentials: "same-origin",
      });
      let payload = null;
      try { payload = JSON.parse(await response.text()); } catch (_) { payload = null; }
      if (!response.ok) throw new Error(errorDetail(payload) || "Could not restore the backup. Check it and try again.");
      libraryFile = null;
      libraryConsent = false;
      const imported = Number(payload?.imported) || 0;
      const skipped = Number(payload?.skipped) || 0;
      const already = Number(payload?.already) || 0;
      const parts = [`Restored ${imported} voice${imported === 1 ? "" : "s"}.`];
      if (already) parts.push(`${already} ${already === 1 ? "was" : "were"} already here.`);
      if (skipped) parts.push(`Skipped ${skipped}.`);
      libraryStatus = parts.join(" ");
      libraryTone = skipped ? "bad" : "ok";
      announceChange();
      await onChanged();
    } catch (cause) {
      libraryStatus = cause?.message || "Could not restore the backup. Check it and try again.";
      libraryTone = "bad";
    } finally {
      libraryBusy = "";
      render();
    }
  }

  function libraryCard() {
    const pick = el("input", { type: "file", accept: ".zip,application/zip", "aria-label": "Voice library ZIP", disabled: Boolean(libraryBusy) });
    pick.addEventListener("change", () => {
      libraryFile = pick.files?.[0] || null;
      libraryStatus = libraryFile ? `Ready to restore ${libraryFile.name}.` : "";
      libraryTone = "";
      render();
    });
    const consent = el("input", { type: "checkbox", checked: libraryConsent, id: "vr-library-consent", disabled: Boolean(libraryBusy) });
    consent.addEventListener("change", () => { libraryConsent = Boolean(consent.checked); render(); });
    const download = el("button", { class: "ghost small", type: "button", text: libraryBusy === "export" ? "Preparing…" : "Download backup", disabled: Boolean(libraryBusy) });
    download.addEventListener("click", () => { void downloadLibrary(); });
    const restore = el("button", { class: "primary small", type: "button", text: libraryBusy === "import" ? "Restoring…" : "Restore backup", disabled: Boolean(libraryBusy) || !libraryFile || !libraryConsent });
    restore.addEventListener("click", () => { void restoreLibrary(); });
    return el("div", { class: "vr-card vr-setup-card vr-setup-wide" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Library" }),
          el("p", { class: "hint", text: "Move your cloned voices to another Mac with a ZIP. Names and samples only; keys stay out." }),
        ]),
        download,
      ]),
      el("label", { class: "vr-field" }, [el("span", { text: "Backup ZIP" }), pick]),
      el("label", { class: "vr-consent", for: "vr-library-consent" }, [consent, el("span", { text: "I have permission to restore these voices." })]),
      el("div", { class: "vr-actions" }, [restore]),
      el("p", { class: "vr-status", role: "status", "data-tone": libraryTone, text: libraryStatus }),
    ]);
  }

  async function importVoiceFile() {
    if (personaBusy) return;
    if (!personaFile) {
      setNotice("Choose a .vcutvoice file first.", "bad");
      render();
      return;
    }
    if (!personaConsent) {
      setNotice("Tick the box to confirm you have permission to import this voice.", "bad");
      render();
      return;
    }
    personaBusy = true;
    personaStatus = "Importing the voice…";
    personaTone = "";
    render();
    try {
      const result = await importPersona(personaFile, { consent: true, name: personaName });
      const voice = result?.voice || {};
      if (result?.imported) {
        personaStatus = `Imported “${voice.name || "the voice"}”.`;
        personaTone = "ok";
      } else {
        personaStatus = `“${voice.name || "That voice"}” is already in this library.`;
        personaTone = "";
      }
      personaFile = null;
      personaConsent = false;
      personaName = "";
      announceChange();
      await onChanged();
    } catch (cause) {
      personaStatus = cause?.message || "Could not import that voice file. Check it and try again.";
      personaTone = "bad";
    } finally {
      personaBusy = false;
      render();
    }
  }

  function personaCard() {
    const pick = el("input", { type: "file", accept: ".vcutvoice,application/zip", "aria-label": "Portable voice file", disabled: personaBusy });
    pick.addEventListener("change", () => {
      personaFile = pick.files?.[0] || null;
      personaStatus = personaFile ? `Ready to import ${personaFile.name}.` : "";
      personaTone = "";
      render();
    });
    const name = el("input", { type: "text", maxLength: 64, value: personaName, placeholder: "Keep the file's name", "aria-label": "Name for the imported voice", disabled: personaBusy });
    name.addEventListener("input", () => { personaName = name.value; });
    const consent = el("input", { type: "checkbox", checked: personaConsent, id: "vr-persona-consent", disabled: personaBusy });
    consent.addEventListener("change", () => { personaConsent = Boolean(consent.checked); render(); });
    const go = el("button", { class: "primary small", type: "button", text: personaBusy ? "Importing…" : "Import voice file", disabled: personaBusy || !personaFile || !personaConsent });
    go.addEventListener("click", () => { void importVoiceFile(); });
    return el("div", { class: "vr-card vr-setup-card vr-setup-wide vr-persona" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Voice file" }),
          el("p", { class: "hint", text: "A .vcutvoice file holds the name, language, consent record, licence tag and a preview. It can speak only when the recording was included." }),
        ]),
      ]),
      el("div", { class: "vr-persona-grid" }, [
        el("label", { class: "vr-field" }, [el("span", { text: "Voice file" }), pick]),
        el("label", { class: "vr-field" }, [el("span", { text: "Name (optional)" }), name]),
      ]),
      el("label", { class: "vr-consent", for: "vr-persona-consent" }, [consent, el("span", { text: "I have permission to import and use this voice." })]),
      el("div", { class: "vr-actions" }, [go]),
      el("p", { class: "vr-status", role: "status", "data-tone": personaTone, text: personaStatus }),
    ]);
  }

  function render() {
    const state = settings();
    const head = el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "setup" }), "this app"]),
        el("h2", { text: "Setup" }),
        el("p", { class: "hint", text: "One place for keys, voices and the library. This app keeps its own settings and never touches Studio or Classic." }),
      ]),
      el("button", {
        class: "ghost small", type: "button", text: "Reload",
        on: {
          click: () => {
            engines = null;
            whisper = null;
            void loadEngines();
            void loadWhisper();
            void onChanged();
          },
        },
      }),
    ]);
    const children = [head];
    if (notice) children.push(el("p", { class: "vr-status", role: "status", "data-tone": noticeTone, text: notice }));
    if (!state) {
      children.push(el("p", { class: "hint", text: "Reading this app's setup…" }));
    } else {
      children.push(el("div", { class: "vr-setup-grid" }, [
        keysCard(state),
        voicesCard(),
        libraryCard(),
        personaCard(),
      ]));
    }
    node.replaceChildren(...children);
  }

  function openSetup() {
    render();
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  render();
  void loadEngines();
  void loadWhisper();

  return { node, render, open: openSetup };
}
