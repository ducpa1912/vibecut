/**
 * Audio layer controls.
 *
 * Saves a valid `AudioPlan` on the current Edit: mode, ducking, loudness, the
 * chosen voice and one music bed. Voice and music use the existing local audio
 * routes (voices, sample, library, upload). No cloud call happens unless the
 * creator presses Preview on a cloud voice.
 *
 * The inspector has no generic audio setter, so changes are written with the
 * Edit PATCH route. The local Edit object is updated in place, which keeps the
 * editor's next save on the new head.
 */

import { request } from "../../api.js";
import { ensureCheckStyles } from "../../check.js";
import { el, formatDuration } from "../../ui.js";
import {
  AUDIO_LABELS,
  clamp,
  clone,
  numberOr,
  round,
} from "../model.js";
import {
  getCurrentEdit,
  patchEdit,
  syncMediaCookie,
} from "../api.js";

const ENGINE_LABELS = {
  say: "Apple voices · on this Mac",
  kokoro: "Kokoro · Voice Pack",
  minimax: "MiniMax · cloud",
  elevenlabs: "ElevenLabs · cloud",
  fish: "Fish Audio · cloud",
  gemini: "Gemini TTS · cloud",
};

const MODE_HELP = {
  original: "Keep the source sound exactly as it is.",
  original_bed: "Keep the source sound and add a music bed under the speech.",
  voice_over: "Speak a new voice line over the source. Music stays ducked.",
  dub: "Replace the spoken lines with a translated voice. The original is ducked.",
  music_only: "Turn the original sound off and use the music bed alone.",
};

function currentJobId() {
  try {
    const raw = localStorage.getItem("vibecut.studio.job");
    if (!raw) return "";
    const value = JSON.parse(raw);
    return value && typeof value === "object" && value.id ? String(value.id) : "";
  } catch (_) {
    return "";
  }
}

function tokenValue() {
  try {
    return localStorage.getItem("vibecut_token") || "";
  } catch (_) {
    return "";
  }
}

function baseName(path) {
  const value = String(path || "");
  const parts = value.split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : value;
}

function field(label, control, hint = "") {
  const wrapper = el("label", { class: "st-field" }, [
    el("span", { text: label }),
    control,
  ]);
  if (hint) wrapper.append(el("small", { class: "st-field-hint", text: hint }));
  return wrapper;
}

function storyLanguage(ctx) {
  const story = ctx.getStory();
  const text = [
    ...(Array.isArray(story?.sentences) ? story.sentences.map((line) => line.text || "") : []),
    story?.title || "",
    story?.hook?.text || "",
  ].join(" ");
  const cjk = (text.match(/[\u3400-\u9fff]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  const kana = (text.match(/[\u3040-\u30ff]/g) || []).length;
  const hangul = (text.match(/[\uac00-\ud7af]/g) || []).length;
  if (kana >= 2) return "ja";
  if (hangul >= 2) return "ko";
  if (cjk >= 4 && cjk > latin * 0.5) return "zh";
  return "en";
}

function licenseLabel(license) {
  if (!license) return "No licence note";
  if (typeof license === "string") return license;
  if (typeof license === "object") {
    return String(license.license || license.type || license.name || "Licence noted");
  }
  return "Licence noted";
}

export function mountAudioPanel(host, ctx) {
  ensureCheckStyles();
  let disposed = false;
  const edit = ctx.getEdit();
  let plan = clone(edit?.audio || { mode: "original" });
  if (!AUDIO_LABELS[plan.mode]) plan.mode = "original";
  let engines = null;
  let engineError = "";
  let voiceList = [];
  let voiceError = "";
  let voicesLoading = false;
  let selectedEngine = plan.voice?.engine || "";
  let selectedVoice = plan.voice?.voice || "";
  let selectedRate = numberOr(plan.voice?.rate, 1);
  let library = [];
  let libraryError = "";
  let libraryLoading = true;
  let selectedTrack = typeof plan.music?.track === "string" ? plan.music.track : "";
  let previewLoading = false;
  let uploadLoading = false;
  let notice = "";
  let noticeTone = "";
  let dirty = false;
  let saving = false;
  let saveTimer = 0;
  let revision = 0;
  let saveNode = null;

  function setSaveStatus(message, tone = "") {
    if (!saveNode || !saveNode.isConnected) return;
    saveNode.textContent = message;
    saveNode.dataset.tone = tone;
  }

  function setNotice(message, tone = "") {
    notice = message || "";
    noticeTone = tone;
  }

  function scheduleSave() {
    dirty = true;
    revision += 1;
    setSaveStatus("Unsaved changes", "dirty");
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => { void save(); }, 450);
  }

  function voicePlan() {
    if (!selectedEngine || !selectedVoice) return null;
    const existing = plan.voice && typeof plan.voice === "object" ? clone(plan.voice) : {};
    return {
      ...existing,
      engine: selectedEngine,
      voice: selectedVoice,
      rate: round(clamp(selectedRate, 0.5, 2), 3),
    };
  }

  function musicPlan() {
    if (!selectedTrack) return null;
    const existing = plan.music && typeof plan.music === "object"
      && plan.music.track === selectedTrack
      ? clone(plan.music)
      : {};
    const track = library.find((item) => item.id === selectedTrack);
    let source = track?.source || "";
    if (!source) {
      source = selectedTrack.startsWith("/")
        ? "library"
        : existing.source === "generated" ? "generated" : "upload";
    }
    return {
      ...existing,
      source,
      track: selectedTrack,
      name: track?.name || existing.name || baseName(selectedTrack),
      license: track?.license === undefined ? (existing.license ?? null) : track.license,
    };
  }

  function syncEditorChrome() {
    const undo = document.getElementById("st-edit-undo");
    if (undo) undo.disabled = !ctx.getEdit()?.parent;
    const lane = document.querySelector(".st-tl-track-audio .st-tl-bar span");
    if (lane) lane.textContent = AUDIO_LABELS[plan.mode] || "Original sound";
    const tab = document.querySelector('.st-inspector-tab[data-tab="audio"]');
    if (tab) {
      let count = tab.querySelector(".st-tab-count");
      const active = plan.mode && plan.mode !== "original";
      if (active) {
        if (!count) {
          count = document.createElement("small");
          count.className = "st-tab-count";
          tab.append(count);
        }
        count.textContent = "1";
      } else if (count) {
        count.remove();
      }
    }
  }

  function buildPlan() {
    const next = {
      mode: AUDIO_LABELS[plan.mode] ? plan.mode : "original",
      duck_db: round(clamp(numberOr(plan.duck_db, -12), -60, 0), 3),
      loudness: {
        lufs: round(clamp(numberOr(plan.loudness?.lufs, -14), -30, -5), 3),
        true_peak: round(clamp(numberOr(plan.loudness?.true_peak, -1.5), -9, 0), 3),
      },
    };
    const voice = voicePlan();
    if (voice) next.voice = voice;
    const music = musicPlan();
    if (music) next.music = music;
    return next;
  }

  async function save() {
    if (disposed || saving || !dirty) return;
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = 0;
    }
    const jobId = currentJobId();
    const current = ctx.getEdit();
    if (!jobId || !current) {
      dirty = false;
      setSaveStatus("Not saved", "bad");
      setNotice("This panel could not find the open video. Reopen the story from Stories.", "bad");
      render();
      return;
    }
    saving = true;
    dirty = false;
    const revisionAtStart = revision;
    setSaveStatus("Saving…", "busy");
    let attempt = 0;
    let failure = null;
    while (!disposed && attempt < 2) {
      try {
        const result = await patchEdit(jobId, ctx.getEdit().id, { audio: buildPlan() });
        if (!result?.edit) throw new Error("The server did not return the saved edit.");
        Object.assign(current, result.edit);
        if (revision === revisionAtStart) {
          plan = clone(result.edit.audio || plan);
        } else {
          current.audio = clone(buildPlan());
        }
        setSaveStatus("Saved", "ok");
        syncEditorChrome();
        break;
      } catch (error) {
        if (error?.status === 409 && attempt === 0) {
          attempt += 1;
          try {
            const fresh = await getCurrentEdit(
              jobId,
              current.story_ref?.set_id,
              current.story_ref?.story_id,
              current.aspect,
            );
            if (fresh?.edit) {
              Object.assign(current, fresh.edit);
              continue;
            }
          } catch (inner) {
            failure = inner;
            break;
          }
        }
        failure = error;
        break;
      }
    }
    saving = false;
    if (failure) {
      dirty = true;
      setSaveStatus("Not saved", "bad");
      setNotice(failure?.message || "Could not save the audio settings.", "bad");
      if (!disposed) render();
      return;
    }
    if (noticeTone === "bad") {
      notice = "";
      noticeTone = "";
      if (!disposed) render();
    }
    if (dirty && !disposed) scheduleSave();
  }

  async function loadVoices(engine) {
    if (!engine) {
      voiceList = [];
      return;
    }
    voicesLoading = true;
    voiceError = "";
    try {
      const result = await request(`/api/audio/voices?engine=${encodeURIComponent(engine)}`);
      voiceList = Array.isArray(result?.voices) ? result.voices : [];
      if (selectedVoice && !voiceList.some((voice) => String(voice.id) === selectedVoice)) {
        selectedVoice = "";
      }
      if (!selectedVoice && voiceList.length) {
        const language = storyLanguage(ctx);
        const preferred = voiceList.find(
          (voice) => String(voice.lang || "").toLowerCase().startsWith(language),
        );
        selectedVoice = String((preferred || voiceList[0]).id);
      }
    } catch (error) {
      voiceList = [];
      voiceError = error?.message || "Could not list voices for this engine.";
    } finally {
      voicesLoading = false;
    }
  }

  async function loadEngines() {
    engineError = "";
    try {
      const result = await request("/api/audio/engines");
      engines = result?.voices && typeof result.voices === "object" ? result.voices : {};
      const available = Object.entries(engines)
        .filter(([, value]) => value?.available)
        .map(([key]) => key);
      if (!available.length) {
        selectedEngine = "";
        voiceError = "No voice engine is ready. Add a key in Setup, or use the built-in Apple voices.";
      } else {
        if (!selectedEngine || !engines[selectedEngine]?.available) {
          selectedEngine = available[0];
        }
        await loadVoices(selectedEngine);
      }
    } catch (error) {
      engineError = error?.message || "Could not read voice engines.";
    }
    if (!disposed) render();
  }

  async function loadLibrary() {
    libraryLoading = true;
    libraryError = "";
    try {
      const result = await request("/api/audio/music?source=library");
      const tracks = Array.isArray(result?.tracks) ? result.tracks : [];
      library = tracks;
      if (selectedTrack && !tracks.some((track) => String(track.id) === selectedTrack)) {
        library = [{
          id: selectedTrack,
          name: plan.music?.name || baseName(selectedTrack),
          moods: [],
          source: plan.music?.source || "upload",
          license: plan.music?.license || null,
          missing: true,
        }, ...tracks];
      }
    } catch (error) {
      libraryError = error?.message || "Could not read the music library.";
    } finally {
      libraryLoading = false;
    }
    if (!disposed) render();
  }

  function chooseEngine(engine) {
    selectedEngine = engine;
    selectedVoice = "";
    voiceList = [];
    setNotice("");
    render();
    void loadVoices(engine).then(() => { if (!disposed) render(); });
  }

  function chooseVoice(voice) {
    selectedVoice = voice;
    setNotice("");
    scheduleSave();
  }

  function chooseTrack(track) {
    selectedTrack = track;
    if (track && plan.mode === "original") plan.mode = "original_bed";
    setNotice("");
    scheduleSave();
    render();
  }

  async function previewVoice() {
    if (previewLoading) return;
    const jobId = currentJobId();
    if (!jobId || !selectedEngine || !selectedVoice) {
      setNotice("Choose a voice before previewing.", "bad");
      render();
      return;
    }
    previewLoading = true;
    setNotice("Making a short voice sample…", "");
    render();
    try {
      syncMediaCookie();
      const text = String(
        ctx.getStory()?.hook?.text
        || ctx.getStory()?.title
        || "This is how your story will sound.",
      ).replace(/\s+/g, " ").trim().slice(0, 120);
      const headers = { "Content-Type": "application/json", Accept: "audio/wav" };
      const token = tokenValue();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/voice/sample`, {
        method: "POST",
        headers,
        credentials: "same-origin",
        body: JSON.stringify({
          engine: selectedEngine,
          voice: selectedVoice,
          rate: selectedRate,
          text,
        }),
      });
      if (!response.ok) {
        let detail = "";
        try {
          const payload = await response.json();
          detail = typeof payload?.detail === "string" ? payload.detail : "";
        } catch (_) {
          detail = "";
        }
        throw new Error(detail || `The voice sample failed (${response.status}).`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      const done = () => URL.revokeObjectURL(url);
      audio.addEventListener("ended", done, { once: true });
      audio.addEventListener("error", done, { once: true });
      await audio.play();
      setNotice("Playing the voice sample.", "ok");
    } catch (error) {
      setNotice(error?.message || "Could not make a voice sample.", "bad");
    } finally {
      previewLoading = false;
      if (!disposed) render();
    }
  }

  async function uploadMusic(file) {
    if (!file || uploadLoading) return;
    const jobId = currentJobId();
    if (!jobId) {
      setNotice("This panel could not find the open video.", "bad");
      render();
      return;
    }
    uploadLoading = true;
    setNotice(`Storing ${file.name}…`, "");
    render();
    try {
      syncMediaCookie();
      const form = new FormData();
      form.append("file", file);
      const headers = { Accept: "application/json" };
      const token = tokenValue();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/audio/music-upload`, {
        method: "POST",
        headers,
        credentials: "same-origin",
        body: form,
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }
      if (!response.ok) {
        const detail = typeof payload?.detail === "string" ? payload.detail : "";
        throw new Error(detail || `The music upload failed (${response.status}).`);
      }
      if (!payload?.path) throw new Error("The upload came back without a track.");
      const added = {
        id: payload.path,
        name: payload.name || baseName(payload.path),
        moods: [],
        source: "upload",
        license: null,
        duration: payload.duration,
      };
      if (!library.some((track) => String(track.id) === added.id)) {
        library = [added, ...library];
      }
      selectedTrack = added.id;
      if (plan.mode === "original") plan.mode = "original_bed";
      dirty = true;
      revision += 1;
      setNotice("Music added and selected.", "ok");
      await save();
    } catch (error) {
      setNotice(error?.message || "Could not upload that music.", "bad");
    } finally {
      uploadLoading = false;
      if (!disposed) render();
    }
  }

  function modeCard() {
    const select = el("select", { "aria-label": "Audio mode" });
    for (const [value, label] of Object.entries(AUDIO_LABELS)) {
      select.append(el("option", { value, text: label, selected: value === (plan.mode || "original") }));
    }
    select.addEventListener("change", () => {
      plan.mode = select.value;
      scheduleSave();
      render();
    });
    const card = el("div", { class: "st-card st-check-card" }, [
      el("h3", { text: "Sound" }),
      field("Mode", select),
      el("p", { class: "st-hint", text: MODE_HELP[plan.mode] || MODE_HELP.original }),
    ]);
    return card;
  }

  function musicCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Music bed" }));
    card.append(el("p", { class: "st-hint", text: "Library candidates from this Mac. Uploads stay in this job. No cloud generation runs here." }));
    if (libraryLoading) {
      card.append(el("p", { class: "st-hint", text: "Reading the music library…" }));
    } else if (libraryError) {
      card.append(el("p", { class: "st-error", text: libraryError }));
    } else {
      const list = el("div", { class: "st-layer-list", style: "margin-top:9px" });
      const none = el("button", {
        class: `st-layer-row${selectedTrack ? "" : " is-active"}`,
        type: "button",
        "aria-pressed": selectedTrack ? "false" : "true",
      }, [
        el("span", { class: "st-layer-badge", text: "None" }),
        el("span", { class: "st-layer-name", text: "No music bed" }),
      ]);
      none.addEventListener("click", () => chooseTrack(""));
      list.append(none);
      for (const track of library.slice(0, 40)) {
        const active = String(track.id) === selectedTrack;
        const moods = Array.isArray(track.moods) ? track.moods.slice(0, 3).join(" · ") : "";
        const name = String(track.name || baseName(track.id));
        const row = el("button", {
          class: `st-layer-row${active ? " is-active" : ""}`,
          type: "button",
          "aria-pressed": active ? "true" : "false",
          title: track.id,
        }, [
          el("span", { class: "st-layer-badge", text: licenseLabel(track.license) }),
          el("span", { class: "st-layer-name" }, [
            el("strong", { text: name, style: "color:var(--st-text);font-weight:500" }),
            el("small", { text: moods || (track.duration ? formatDuration(track.duration) : "Library") }),
          ]),
        ]);
        row.addEventListener("click", () => chooseTrack(String(track.id)));
        list.append(row);
      }
      card.append(list);
      if (library.length > 40) card.append(el("p", { class: "st-hint", text: `Showing 40 of ${library.length} tracks.` }));
      if (!library.length) card.append(el("p", { class: "st-hint", text: "The library is empty. Add your own track below." }));
    }

    const uploadRow = el("div", { class: "st-layer-add", style: "margin-top:9px" });
    const file = el("input", { type: "file", accept: "audio/*,.wav,.mp3,.m4a,.aac,.flac,.ogg,.opus,.aiff,.aif", "aria-label": "Upload music" });
    file.style.minWidth = "0";
    file.style.flex = "1 1 auto";
    const upload = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: uploadLoading ? "Uploading…" : "Upload",
      disabled: uploadLoading,
    });
    upload.addEventListener("click", () => {
      const chosen = file.files && file.files[0];
      if (!chosen) {
        setNotice("Choose an audio file first.", "bad");
        render();
        return;
      }
      void uploadMusic(chosen);
    });
    uploadRow.append(file, upload);
    card.append(uploadRow);
    card.append(el("p", { class: "st-field-hint", text: "WAV, MP3, M4A, AAC, FLAC, OGG or AIFF. The track is copied into this job." }));
    return card;
  }

  function voiceCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Voice" }));
    card.append(el("p", { class: "st-hint", text: "One voice per story. Used by Voice-over and Dub. Cloud voices use your own key." }));

    if (engineError) card.append(el("p", { class: "st-error", text: engineError }));
    const available = engines
      ? Object.entries(engines).filter(([, value]) => value?.available).map(([key]) => key)
      : [];
    if (!engines && !engineError) {
      card.append(el("p", { class: "st-hint", text: "Reading voice engines…" }));
    } else if (!available.length) {
      card.append(el("p", { class: "st-hint", text: "No voice engine is ready on this Mac." }));
    } else {
      const engine = el("select", { "aria-label": "Voice engine" });
      for (const key of available) {
        engine.append(el("option", {
          value: key,
          text: ENGINE_LABELS[key] || key,
          selected: key === selectedEngine,
        }));
      }
      engine.addEventListener("change", () => chooseEngine(engine.value));

      const voice = el("select", { "aria-label": "Voice", disabled: voicesLoading || !voiceList.length });
      if (voicesLoading) {
        voice.append(el("option", { value: "", text: "Reading voices…" }));
      } else if (!voiceList.length) {
        voice.append(el("option", { value: "", text: "No voices installed" }));
      } else {
        voice.append(el("option", { value: "", text: "Choose a voice", selected: !selectedVoice }));
        for (const item of voiceList) {
          const id = String(item.id || "");
          voice.append(el("option", {
            value: id,
            text: `${item.name || id}${item.lang ? ` · ${item.lang}` : ""}`,
            selected: id === selectedVoice,
          }));
        }
      }
      voice.addEventListener("change", () => chooseVoice(voice.value));

      const rate = el("input", {
        type: "number", min: "0.5", max: "2", step: "0.05",
        value: String(selectedRate),
        "aria-label": "Voice rate",
      });
      rate.addEventListener("input", () => {
        selectedRate = clamp(numberOr(rate.value, 1), 0.5, 2);
        scheduleSave();
      });

      card.append(el("div", { class: "st-control-grid" }, [
        field("Engine", engine),
        field("Voice", voice),
        field("Rate", rate, "1.0 is the recorded pace."),
      ]));
      if (voiceError) card.append(el("p", { class: "st-error", text: voiceError }));

      const preview = el("button", {
        class: "st-btn st-btn-ghost st-btn-small",
        type: "button",
        text: previewLoading ? "Making sample…" : "Preview voice",
        disabled: previewLoading || !selectedVoice,
      });
      preview.addEventListener("click", () => { void previewVoice(); });
      card.append(el("div", { class: "st-layer-add", style: "margin-top:9px" }, [preview]));
      card.append(el("p", { class: "st-field-hint", text: "The sample speaks the story hook, or a short test line when the hook is empty." }));
    }
    return card;
  }

  function mixCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Mix" }));

    const duck = el("input", {
      type: "range", min: "-60", max: "0", step: "1",
      value: String(Math.round(numberOr(plan.duck_db, -12))),
      "aria-label": "Music duck",
    });
    const duckValue = el("span", {
      class: "st-mono st-range-value",
      text: `${Math.round(numberOr(plan.duck_db, -12))} dB`,
    });
    duck.addEventListener("input", () => {
      plan.duck_db = clamp(numberOr(duck.value, -12), -60, 0);
      duckValue.textContent = `${Math.round(plan.duck_db)} dB`;
      scheduleSave();
    });

    const lufs = el("input", {
      type: "number", min: "-30", max: "-5", step: "0.5",
      value: String(numberOr(plan.loudness?.lufs, -14)),
      "aria-label": "Loudness target",
    });
    lufs.addEventListener("input", () => {
      plan.loudness = { ...(plan.loudness || {}), lufs: clamp(numberOr(lufs.value, -14), -30, -5) };
      scheduleSave();
    });
    const peak = el("input", {
      type: "number", min: "-9", max: "0", step: "0.1",
      value: String(numberOr(plan.loudness?.true_peak, -1.5)),
      "aria-label": "True peak target",
    });
    peak.addEventListener("input", () => {
      plan.loudness = { ...(plan.loudness || {}), true_peak: clamp(numberOr(peak.value, -1.5), -9, 0) };
      scheduleSave();
    });

    card.append(el("div", { class: "st-range-row" }, [
      el("span", { class: "st-field-label", text: "Music duck" }),
      duck,
      duckValue,
    ]));
    card.append(el("p", { class: "st-field-hint", text: "Negative values lower the music under speech. −12 dB is the default." }));
    card.append(el("div", { class: "st-control-grid", style: "margin-top:9px" }, [
      field("Loudness (LUFS)", lufs, "Target −14 for social video."),
      field("True peak (dBTP)", peak, "Target −1.5 or lower."),
    ]));
    return card;
  }

  function render() {
    host.replaceChildren();
    const head = el("div", { class: "st-card st-check-card" }, [
      el("h3", { text: "Audio" }),
      el("p", { class: "st-hint", text: "One sound setup per story: the source sound, a voice, one music bed, ducking and a loudness target." }),
    ]);
    saveNode = el("span", {
      class: "st-edit-save",
      role: "status",
      "aria-live": "polite",
      text: saving ? "Saving…" : dirty ? "Unsaved changes" : "Saved",
      dataset: { tone: saving ? "busy" : dirty ? "dirty" : "ok" },
    });
    head.append(el("div", { style: "margin-top:8px" }, [saveNode]));
    if (notice) {
      head.append(el("p", {
        class: noticeTone === "bad" ? "st-error" : "st-status",
        text: notice,
      }));
    }
    host.append(head);
    host.append(modeCard());
    host.append(musicCard());
    host.append(voiceCard());
    host.append(mixCard());
    host.append(el("p", { class: "st-hint", text: "The mix is stored in this edit. Voice and music are rendered by the audio build; nothing is sent to a cloud service unless you press Preview on a cloud voice." }));
  }

  render();
  void loadEngines();
  void loadLibrary();

  return () => {
    if (saveTimer) window.clearTimeout(saveTimer);
    if (dirty && !saving) {
      const jobId = currentJobId();
      const current = ctx.getEdit();
      if (jobId && current) {
        void patchEdit(jobId, current.id, { audio: buildPlan() }).catch(() => {});
      }
    }
    disposed = true;
  };
}
