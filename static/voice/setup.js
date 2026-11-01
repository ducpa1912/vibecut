/**
 * Voice Room — this app's Setup.
 *
 * Copies the useful parts of the archive Setup: OpenRouter and OpenCode keys,
 * model choices, and what runs on this Mac. Everything saves through the
 * existing /api/settings route, so it lands in this server's VIBECUT_DATA
 * folder. The Voice lane runs on its own data folder, which makes its keys
 * separate from Studio and Classic.
 */

import {
  announceChange,
  errorDetail,
  request,
  syncTokenCookie,
  tokenValue,
} from "./api.js";
import { el } from "./ui.js";

const OPENROUTER_TEXT_MODELS = [
  ["deepseek/deepseek-v4.1-flash:floor", "DeepSeek V4.1 Flash · floor"],
  ["deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash"],
  ["google/gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"],
];

const ENGINE_LABELS = {
  say: "Apple say · on this Mac",
  kokoro: "Kokoro · Voice Pack",
  heygen: "OpenRouter · HeyGen Voice Turbo",
  fish: "OpenRouter · Fish S2.1",
  gemini: "OpenRouter · Gemini Flash-Lite",
  minimax: "MiniMax Speech 2.8",
  elevenlabs: "ElevenLabs",
};

const EXTRACTION_LABELS = {
  separation: "Voice separation",
  denoise: "Denoise",
  vad: "Speech detection",
  diarization: "Speaker filter",
};

const LOCAL_VOICE_IDS = ["say", "kokoro"];
const OPENROUTER_VOICE_IDS = ["heygen", "fish", "gemini"];
const CLOUD_VOICE_IDS = ["minimax", "elevenlabs"];

function sourceCopy(source) {
  if (source === "env") return "From environment";
  if (source === "file") return "Saved on this Mac";
  return "Not set";
}

function secondsCopy(value) {
  const seconds = Math.max(0, Math.round(Number(value) || 0));
  return seconds > 0 ? `${seconds}s` : "";
}

export function createVoiceSetup({ getSettings, onChanged = () => {} }) {
  const node = el("section", { class: "vr-section vr-setup", id: "voice-setup", "data-panel": "setup" });
  let engines = null;
  let busy = "";
  let notice = "";
  let noticeTone = "";
  let open = false;
  let userToggled = false;
  let loadEnginesBusy = false;
  let libraryCard = null;
  let libraryRefs = null;
  let libraryFile = null;
  let libraryConsent = false;
  let libraryBusy = "";
  let libraryStatus = "";
  let libraryTone = "";

  function settings() {
    return getSettings() || null;
  }

  function setNotice(message, tone = "") {
    notice = message || "";
    noticeTone = tone;
    render();
  }

  function openSetup() {
    userToggled = true;
    open = true;
    render();
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadEngines() {
    if (engines || loadEnginesBusy) return;
    loadEnginesBusy = true;
    try {
      engines = await request("/api/audio/engines");
    } catch (_) {
      engines = null;
    } finally {
      loadEnginesBusy = false;
      render();
    }
  }

  async function saveSecret(name, input) {
    const value = String(input?.value || "").trim();
    if (!value) {
      setNotice(`Enter the ${name === "openrouter" ? "OpenRouter" : "OpenCode"} key first.`, "bad");
      return;
    }
    busy = `secret:${name}`;
    setNotice(`Saving the ${name === "openrouter" ? "OpenRouter" : "OpenCode"} key…`);
    try {
      await request("/api/settings", { method: "POST", body: { secrets: { [name]: value } } });
      if (input) input.value = "";
      await onChanged();
      setNotice(
        `${name === "openrouter" ? "OpenRouter" : "OpenCode"} key saved for this app. The auth quarantine is cleared.`,
        "ok",
      );
    } catch (cause) {
      setNotice(cause?.message || "Could not save the key.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function clearSecret(name) {
    busy = `secret:${name}`;
    setNotice("Removing the saved key…");
    try {
      await request("/api/settings", { method: "POST", body: { secrets: { [name]: "" } } });
      await onChanged();
      setNotice("Saved key removed. This app will use the environment key, if there is one.", "ok");
    } catch (cause) {
      setNotice(cause?.message || "Could not remove the key.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function saveModel(model) {
    busy = "model";
    setNotice("Saving the OpenRouter text model…");
    try {
      await request("/api/settings", {
        method: "POST",
        body: { settings: { openrouter: { model } } },
      });
      await onChanged();
      setNotice("OpenRouter text model saved for this app.", "ok");
    } catch (cause) {
      setNotice(cause?.message || "Could not save the model.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function test(kind) {
    busy = `test:${kind}`;
    setNotice(`Testing ${kind === "openrouter" ? "OpenRouter" : "OpenCode"}…`);
    try {
      const result = await request("/api/settings/test", {
        method: "POST",
        body: { kind },
      });
      const detail = result?.detail || (result?.ok ? "Ready." : "No reply.");
      await onChanged();
      setNotice(detail, result?.ok ? "ok" : "bad");
    } catch (cause) {
      setNotice(cause?.message || "The test failed.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  function authHeaders(accept) {
    const headers = { Accept: accept };
    const token = tokenValue();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async function responseError(response, fallback) {
    let payload = null;
    try {
      const text = await response.text();
      try {
        payload = text ? JSON.parse(text) : null;
      } catch (_) {
        payload = text;
      }
    } catch (_) {
      payload = null;
    }
    return new Error(errorDetail(payload) || fallback || `Request failed (${response.status}).`);
  }

  function attachmentName(header) {
    const match = /filename="?([^";]+)"?/i.exec(String(header || ""));
    return match ? match[1].trim() : "";
  }

  function backupName() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return `vibecut-voice-library-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.zip`;
  }

  function syncLibrary() {
    if (!libraryRefs) return;
    const busy = Boolean(libraryBusy);
    libraryRefs.download.disabled = busy;
    libraryRefs.pick.disabled = busy;
    libraryRefs.consent.checked = libraryConsent;
    libraryRefs.restore.disabled = busy || !libraryFile || !libraryConsent;
    libraryRefs.download.textContent = libraryBusy === "export" ? "Preparing…" : "Download backup";
    libraryRefs.restore.textContent = libraryBusy === "import" ? "Restoring…" : "Restore backup";
    libraryRefs.status.textContent = libraryStatus;
    libraryRefs.status.dataset.tone = libraryTone;
  }

  function setLibraryStatus(message, tone = "") {
    libraryStatus = message || "";
    libraryTone = tone;
    syncLibrary();
  }

  async function downloadLibrary() {
    if (libraryBusy) return;
    libraryBusy = "export";
    setLibraryStatus("Building the backup…");
    try {
      syncTokenCookie();
      const response = await fetch("/api/voices/library/export", {
        method: "GET",
        headers: authHeaders("application/zip"),
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw await responseError(response, "Could not build the backup.");
      const blob = await response.blob();
      const name = attachmentName(response.headers.get("Content-Disposition")) || backupName();
      const url = URL.createObjectURL(blob);
      const link = el("a", { href: url, download: name });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setLibraryStatus(`Saved ${name}.`, "ok");
    } catch (cause) {
      setLibraryStatus(cause?.message || "Could not build the backup.", "bad");
    } finally {
      libraryBusy = "";
      syncLibrary();
    }
  }

  async function restoreLibrary() {
    if (libraryBusy) return;
    if (!libraryFile) {
      setLibraryStatus("Choose a backup ZIP first.", "bad");
      return;
    }
    if (!libraryConsent) {
      setLibraryStatus("Confirm you have permission to restore these voices.", "bad");
      return;
    }
    libraryBusy = "import";
    setLibraryStatus("Restoring voices…");
    try {
      const form = new FormData();
      form.append("file", libraryFile, libraryFile.name || "voice-library.zip");
      form.append("consent", "true");
      syncTokenCookie();
      const response = await fetch("/api/voices/library/import", {
        method: "POST",
        headers: authHeaders("application/json"),
        body: form,
        credentials: "same-origin",
      });
      let payload = null;
      try {
        const text = await response.text();
        payload = text ? JSON.parse(text) : null;
      } catch (_) {
        payload = null;
      }
      if (!response.ok) {
        throw new Error(errorDetail(payload) || "Could not restore the backup.");
      }
      libraryFile = null;
      libraryConsent = false;
      if (libraryRefs?.pick) libraryRefs.pick.value = "";
      const imported = Math.max(0, Number(payload?.imported) || 0);
      const skipped = Math.max(0, Number(payload?.skipped) || 0);
      const already = Math.max(0, Number(payload?.already) || 0);
      const voices = `${imported} voice${imported === 1 ? "" : "s"}`;
      const parts = [`Restored ${voices}.`];
      if (already) parts.push(`${already} ${already === 1 ? "was" : "were"} already here.`);
      if (skipped) parts.push(`Skipped ${skipped}.`);
      setLibraryStatus(parts.join(" "), skipped ? "bad" : "ok");
      announceChange();
      await onChanged();
    } catch (cause) {
      setLibraryStatus(cause?.message || "Could not restore the backup.", "bad");
    } finally {
      libraryBusy = "";
      syncLibrary();
    }
  }

  function libraryCardNode() {
    if (libraryCard) {
      syncLibrary();
      return libraryCard;
    }
    const pick = el("input", {
      type: "file", accept: ".zip,application/zip",
      "aria-label": "Voice library ZIP",
    });
    pick.addEventListener("change", () => {
      libraryFile = pick.files && pick.files[0] ? pick.files[0] : null;
      if (libraryFile) setLibraryStatus(`Ready to restore ${libraryFile.name}.`);
      syncLibrary();
    });
    const consent = el("input", { type: "checkbox", checked: libraryConsent });
    consent.addEventListener("change", () => {
      libraryConsent = Boolean(consent.checked);
      syncLibrary();
    });
    const download = el("button", {
      class: "ghost small", type: "button", text: "Download backup",
      on: { click: () => { void downloadLibrary(); } },
    });
    const restore = el("button", {
      class: "primary small", type: "button", text: "Restore backup",
      on: { click: () => { void restoreLibrary(); } },
    });
    const status = el("p", {
      class: "vr-status vr-library-status", role: "status",
    });
    libraryCard = el("div", { class: "vr-card vr-setup-card vr-setup-wide vr-library" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Library backup" }),
          el("p", { class: "hint", text: "A copy of your cloned voices. Names and samples only; settings and keys stay out." }),
        ]),
      ]),
      el("div", { class: "vr-library-download" }, [
        el("div", {}, [
          el("strong", { text: "Back up this Mac's voices" }),
          el("p", { class: "hint", text: "Downloads a ZIP with a manifest and every clone sample." }),
        ]),
        download,
      ]),
      el("div", { class: "vr-library-restore" }, [
        el("label", { class: "vr-field" }, [
          el("span", { text: "Voice library ZIP" }),
          pick,
        ]),
        el("label", { class: "vr-consent vr-library-consent" }, [
          consent,
          el("span", { text: "I have permission to restore these voices." }),
        ]),
        el("div", { class: "vr-actions" }, [restore]),
      ]),
      status,
    ]);
    libraryRefs = { download, restore, pick, consent, status };
    syncLibrary();
    return libraryCard;
  }

  function keyCard({ name, title, copy, placeholder, source, hasKey, runtime, model }) {
    const save = el("button", {
      class: "ghost small", type: "button",
      text: busy === `secret:${name}` ? "Saving…" : "Save key",
      disabled: Boolean(busy),
    });
    const input = el("input", {
      type: "password", autocomplete: "off", spellcheck: "false",
      placeholder, "aria-label": `${title} key`,
    });
    save.addEventListener("click", () => { void saveSecret(name, input); });
    const testButton = el("button", {
      class: "ghost small", type: "button",
      text: busy === `test:${name}` ? "Testing…" : "Test key",
      disabled: Boolean(busy),
    });
    testButton.addEventListener("click", () => { void test(name); });
    const remove = hasKey && source === "file" ? el("button", {
      class: "ghost small danger", type: "button",
      text: "Remove saved key",
      disabled: Boolean(busy),
    }) : null;
    remove?.addEventListener("click", () => { void clearSecret(name); });
    const status = el("span", {
      class: `vr-chip${hasKey ? " is-cloud" : ""}`,
      text: sourceCopy(source),
    });
    return el("div", { class: "vr-card vr-setup-card" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [el("h3", { text: title }), el("p", { class: "hint", text: copy })]),
        status,
      ]),
      runtime?.error ? el("p", { class: "error", role: "alert", text: `${runtime.error}${runtime.blocked ? ` Retry in ${secondsCopy(runtime.retry_in)}.` : ""}` }) : null,
      model || null,
      el("label", { class: "vr-field" }, [
        el("span", { text: `${title} API key` }),
        input,
      ]),
      el("div", { class: "vr-actions" }, [save, testButton, remove]),
      el("p", { class: "hint", text: source === "env"
        ? "The environment key is active. A key saved here overrides it for this app only."
        : "The key is stored in this app's secrets file, not in Studio or Classic." }),
    ]);
  }

  function openRouterCard(state) {
    const runtime = state?.runtime?.openrouter || {};
    const current = String(state?.settings?.openrouter?.model || OPENROUTER_TEXT_MODELS[0][0]);
    const select = el("select", { "aria-label": "OpenRouter text model" }, OPENROUTER_TEXT_MODELS.map(
      ([id, label]) => el("option", { value: id, text: label, selected: current === id }),
    ));
    if (!OPENROUTER_TEXT_MODELS.some(([id]) => id === current)) {
      select.append(el("option", { value: current, text: `${current} · saved`, selected: true }));
    }
    const save = el("button", {
      class: "ghost small", type: "button",
      text: busy === "model" ? "Saving…" : "Save model",
      disabled: Boolean(busy),
    });
    save.addEventListener("click", () => { void saveModel(select.value); });
    const model = el("div", { class: "vr-setup-model" }, [
      el("label", { class: "vr-field" }, [el("span", { text: "Text model · rewrite, translation, story brief" }), select]),
      el("div", { class: "vr-actions" }, [save]),
      el("p", { class: "hint", text: "Voice cloning uses HeyGen Voice Turbo through OpenRouter. The voice list below shows every speech engine." }),
    ]);
    return keyCard({
      name: "openrouter",
      title: "OpenRouter",
      copy: "One key for HeyGen voice cloning, Fish, Gemini, cloud music and AI text.",
      placeholder: "sk-or-…",
      source: state?.sources?.openrouter || "",
      hasKey: Boolean(state?.secrets?.openrouter),
      runtime,
      model,
    });
  }

  function openCodeCard(state) {
    const runtime = state?.runtime || {};
    const mode = runtime.opencode_mode || "off";
    const hasKey = Boolean(state?.secrets?.opencode);
    const status = mode === "api" ? "Direct API key"
      : mode === "local" ? "Local login"
        : "Not ready";
    const card = keyCard({
      name: "opencode",
      title: "OpenCode",
      copy: "Used for rewriting, story briefs and translation. A saved key is used by this app only.",
      placeholder: "oc_sk_…",
      source: state?.sources?.opencode || "",
      hasKey,
      runtime: null,
      model: null,
    });
    card.querySelector(".vr-chip").textContent = status;
    card.append(el("p", { class: "hint", text: `Model: ${runtime.opencode_model || "deepseek-v4.1-flash"} · reasoning ${runtime.opencode_variant || "low"} · locked by the server.` }));
    return card;
  }

  function enginesCard() {
    const card = el("div", { class: "vr-card vr-setup-card vr-setup-wide" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "Engines" }),
          el("p", { class: "hint", text: "Local engines work offline. Cloud engines use the keys above." }),
        ]),
        el("button", {
          class: "ghost small", type: "button", text: "Refresh",
          on: { click: () => { engines = null; void loadEngines(); } },
        }),
      ]),
    ]);
    if (!engines) {
      card.append(el("p", { class: "hint", text: "Reading this Mac…" }));
      return card;
    }
    function engineGroup(title, ids, hint) {
      const grid = el("div", { class: "vr-setup-engines" });
      for (const id of ids) {
        const item = engines.voices?.[id];
        if (!item) continue;
        grid.append(el("div", { class: "vr-setup-engine" }, [
          el("div", { class: "vr-setup-engine-head" }, [
            el("strong", { text: ENGINE_LABELS[id] || id }),
            el("span", { class: `vr-chip${item.available ? " is-cloud" : ""}`, text: item.available ? "Ready" : "Needs setup" }),
          ]),
          el("p", { class: "hint", text: item.install || "" }),
        ]));
      }
      return el("div", { class: "vr-setup-group" }, [
        el("div", { class: "vr-setup-group-head" }, [
          el("h4", { text: title }),
          hint ? el("p", { class: "hint", text: hint }) : null,
        ]),
        grid,
      ]);
    }
    card.append(
      engineGroup("On this Mac", LOCAL_VOICE_IDS, "Built in or installed as a pack."),
      engineGroup("OpenRouter voices", OPENROUTER_VOICE_IDS, "All three share the OpenRouter key. HeyGen does the cloning."),
      engineGroup("Cloud voices", CLOUD_VOICE_IDS, "Use your own MiniMax or ElevenLabs key."),
    );
    const extraction = engines.extraction || {};
    const rows = Object.entries(extraction).filter(([key]) => EXTRACTION_LABELS[key]);
    if (rows.length) {
      const list = el("div", { class: "vr-setup-engines" });
      for (const [key, value] of rows) {
        const ready = Boolean(value);
        list.append(el("div", { class: "vr-setup-engine" }, [
          el("div", { class: "vr-setup-engine-head" }, [
            el("strong", { text: EXTRACTION_LABELS[key] }),
            el("span", { class: `vr-chip${ready ? " is-cloud" : ""}`, text: ready ? String(value) : "Not installed" }),
          ]),
        ]));
      }
      card.append(el("div", { class: "vr-setup-group" }, [
        el("div", { class: "vr-setup-group-head" }, [
          el("h4", { text: "Voice extraction" }),
          el("p", { class: "hint", text: "Cleans a clone reference from a video or recording." }),
        ]),
        list,
      ]));
    }
    return card;
  }

  function configCard(state) {
    const paths = state?.paths || {};
    return el("div", { class: "vr-card vr-setup-card vr-setup-wide" }, [
      el("div", { class: "vr-card-head vr-setup-head" }, [
        el("div", {}, [
          el("h3", { text: "This app's config" }),
          el("p", { class: "hint", text: "Setup writes only to this server's data folder. Studio and Classic keep their own keys and models." }),
        ]),
      ]),
      el("dl", { class: "vr-setup-paths" }, [
        el("dt", { text: "Settings" }), el("dd", { text: paths.settings || "this app's data folder" }),
        el("dt", { text: "Secrets" }), el("dd", { text: paths.secrets || "this app's data folder" }),
      ]),
    ]);
  }

  function render() {
    const state = settings();
    const runtime = state?.runtime || {};
    if (!userToggled) open = !state || !state.secrets?.openrouter
      || Boolean(runtime.openrouter?.error) || Boolean(runtime.openrouter?.blocked);
    const button = el("button", {
      class: "ghost small", type: "button",
      text: open ? "Hide setup" : "Open setup",
      "aria-expanded": open ? "true" : "false",
    });
    button.addEventListener("click", () => {
      userToggled = true;
      open = !open;
      render();
    });
    const head = el("div", { class: "vr-section-head" }, [
      el("div", {}, [
        el("p", { class: "eyebrow" }, [el("span", { text: "setup" }), "this app"]),
        el("h2", { text: "Keys, models and this Mac" }),
        el("p", { class: "hint", text: "OpenRouter, OpenCode and the local engines. Saved only in this app's data folder." }),
      ]),
      button,
    ]);
    const children = [head];
    if (notice) children.push(el("p", { class: "vr-status", role: "status", "data-tone": noticeTone, text: notice }));
    if (open) {
      if (!state) {
        children.push(el("p", { class: "hint", text: "Reading this app's setup…" }));
      } else {
        children.push(el("div", { class: "vr-setup-grid" }, [
          openRouterCard(state),
          openCodeCard(state),
          enginesCard(),
          configCard(state),
          libraryCardNode(),
        ]));
      }
    } else if (state) {
      const runtimeState = state.runtime?.openrouter || {};
      const source = sourceCopy(state.sources?.openrouter);
      const summary = state.secrets?.openrouter
        ? (runtimeState.error ? `OpenRouter needs attention: ${runtimeState.error}` : `OpenRouter key: ${source}.`)
        : "No OpenRouter key saved for this app yet.";
      children.push(el("p", { class: "hint", text: summary }));
    }
    node.replaceChildren(...children);
  }

  render();
  void loadEngines();

  return { node, render, open: openSetup };
}
