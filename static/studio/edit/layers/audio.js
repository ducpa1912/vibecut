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
import { CONSENT_COPY, cloneFromVideo, cancelVoiceCandidates, findVoiceCandidates, voiceCandidateAudioUrl, voiceCandidateState } from "../../../voice/voiceclone.js";

const ENGINE_LABELS = {
  say: "Apple voices · on this Mac",
  kokoro: "Kokoro · Voice Pack",
  minimax: "MiniMax · cloud",
  elevenlabs: "ElevenLabs · cloud",
  heygen: "HeyGen Voice Turbo · free until 30 Nov 2026",
  fish: "Fish Audio · cloud",
  gemini: "Gemini TTS · cloud",
};

const MODE_HELP = {
  original: "Keep the source sound exactly as it is.",
  original_bed: "Keep the source sound and add a music bed under the speech.",
  voice_over: "Speak a new script in the story's own language, with the chosen voice.",
  dub: "Translate each line into your target language, then speak it with the chosen voice.",
  music_only: "Turn the original sound off and use the music bed alone.",
};

// A small local list keeps Dub useful without another network call. The
// backend accepts any two- or three-letter code, so a future picker can grow.
export const DUB_LANGUAGES = [
  ["en", "English"],
  ["es", "Spanish"],
  ["fr", "French"],
  ["de", "German"],
  ["pt", "Portuguese"],
  ["it", "Italian"],
  ["ja", "Japanese"],
  ["ko", "Korean"],
  ["zh", "Chinese"],
  ["hi", "Hindi"],
  ["ar", "Arabic"],
];

const LANGUAGE_LABELS = Object.fromEntries(DUB_LANGUAGES);

export function languageLabel(code) {
  const value = String(code || "").trim();
  if (!value) return "Choose a language";
  return LANGUAGE_LABELS[value.split("-")[0].toLowerCase()] || value;
}

/** Why a Dub edit cannot save or queue, or "" when the edit is usable. */
export function dubBlockReason(mode, target) {
  if (String(mode || "") !== "dub") return "";
  if (String(target || "").trim()) return "";
  return "Dub needs a target language. Choose one, then save or queue again.";
}

/**
 * The voice_room switch: true only when the build lists the feature.
 * Accepts the page's VIBECUT_EDITION object, a features list, or a string;
 * with no argument it reads the page, then the <html data-features> string.
 */
export function voiceRoomOn(edition) {
  const value = edition === undefined ? currentEdition() : edition;
  const features = typeof value === "string"
    ? value.split(/[\s,]+/)
    : Array.isArray(value)
      ? value
      : typeof value?.features === "string"
        ? value.features.split(/[\s,]+/)
        : Array.isArray(value?.features)
          ? value.features
          : [];
  return features.some((item) => String(item || "").trim() === "voice_room");
}

function currentEdition() {
  const win = typeof globalThis !== "undefined" ? globalThis.window : undefined;
  if (win?.VIBECUT_EDITION) return win.VIBECUT_EDITION;
  const doc = typeof globalThis !== "undefined" ? globalThis.document : undefined;
  const text = doc?.documentElement?.dataset?.features;
  return typeof text === "string" ? text : undefined;
}

/**
 * One editable script row per scene.
 *
 * Clips are the output order. Each clip names its source sentence in `why`,
 * so the text comes from the story transcript even when the clip has no scene
 * id. Rows are keyed the way ``audio.build_script`` keys a line: the scene id
 * as a string, or "None" when Python's ``str(scene)`` would be None.
 */
export function storyScriptLines(story) {
  const sentences = Array.isArray(story?.sentences) ? story.sentences : [];
  const byId = new Map(sentences.map((row) => [String(row?.id ?? ""), row]));
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  const rows = new Map();

  function add(rawScene, text, role) {
    const value = String(text || "").replace(/\s+/g, " ").trim();
    if (!value) return;
    const hasScene = rawScene !== null && rawScene !== undefined
      && String(rawScene).trim() !== "";
    const key = hasScene ? String(rawScene).trim() : "None";
    const existing = rows.get(key);
    if (!existing) {
      rows.set(key, {
        key,
        scene: hasScene ? rawScene : null,
        text: value,
        role: role || "beat",
      });
      return;
    }
    if (!existing.text.includes(value)) existing.text = `${existing.text} ${value}`;
  }

  clips.forEach((clip, index) => {
    const sentence = sentenceForClip(clip, byId);
    const scene = clip?.scene
      ?? sentence?.scene
      ?? (Array.isArray(sentence?.scenes) ? sentence.scenes[0] : null);
    const role = clip?.role || (index === 0 ? "hook" : index === clips.length - 1 ? "payoff" : "beat");
    add(scene, sentence?.text || clip?.why || "", role);
  });

  if (!rows.size) {
    sentences.forEach((sentence, index) => {
      const scene = sentence?.scene
        ?? (Array.isArray(sentence?.scenes) ? sentence.scenes[0] : null);
      const role = index === 0 ? "hook" : index === sentences.length - 1 ? "payoff" : "beat";
      add(scene, sentence?.text || "", role);
    });
  }
  return [...rows.values()];
}

function sentenceForClip(clip, byId) {
  const match = /Sentence\s+([A-Za-z0-9_-]+)/.exec(String(clip?.why || ""));
  return match ? byId.get(match[1]) || null : null;
}

/**
 * Merge Dub settings into an existing translate object.
 *
 * Only Dub writes translate. Unrelated stored fields (for example a saved
 * style) stay as they were; source and target are the two the picker owns.
 */
export function mergeTranslatePlan(mode, existing, source, target, style = "smooth") {
  if (String(mode || "") !== "dub") return null;
  const base = existing && typeof existing === "object" ? clone(existing) : {};
  return {
    ...base,
    source: String(source || "").trim(),
    target: String(target || "").trim(),
    mode: String(style || base.mode || "smooth"),
  };
}

/** Trim, drop blank lines and cap one override per scene; blank = machine text. */
export function cleanScriptOverrides(values) {
  const out = {};
  for (const [key, text] of Object.entries(values || {})) {
    const scene = String(key ?? "").trim();
    const line = String(text ?? "").replace(/\s+/g, " ").trim();
    if (!scene || !line) continue;
    out[scene] = line.slice(0, 600);
  }
  return out;
}

/**
 * The Edit audio object. Optional keys are omitted when empty so an Edit
 * without translate or a script hashes exactly as before.
 */
export function buildAudioPlan({
  mode = "original",
  duck_db,
  loudness,
  voice = null,
  music = null,
  translate = null,
  scriptOverrides = null,
  modeChosen = false,
} = {}) {
  const next = {
    mode: AUDIO_LABELS[mode] ? mode : "original",
    duck_db: round(clamp(numberOr(duck_db, -12), -60, 0), 3),
    loudness: {
      lufs: round(clamp(numberOr(loudness?.lufs, -14), -30, -5), 3),
      true_peak: round(clamp(numberOr(loudness?.true_peak, -1.5), -9, 0), 3),
    },
  };
  if (voice) next.voice = voice;
  if (music) next.music = music;
  if (translate) next.translate = translate;
  const overrides = cleanScriptOverrides(scriptOverrides);
  if (Object.keys(overrides).length) next.script_overrides = overrides;
  // Marks a mode the creator picked, so a picked "original" on a scripted
  // story keeps the sound instead of the default voice-over.
  if (modeChosen) next.mode_chosen = true;
  return next;
}

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

export function detectStoryLanguage(story) {
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

function storyLanguage(ctx) {
  return detectStoryLanguage(ctx.getStory());
}

function storySeconds(ctx) {
  const story = ctx.getStory();
  const direct = Number(story?.dur ?? story?.duration);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  const total = clips.reduce((sum, clip) => {
    const dur = Number(clip?.dur);
    if (Number.isFinite(dur) && dur > 0) return sum + dur;
    return sum + Math.max(0, numberOr(clip?.end, 0) - numberOr(clip?.start, 0));
  }, 0);
  return total > 0 ? total : 30;
}

function briefTarget(seconds) {
  const value = numberOr(seconds, 30);
  if (value <= 22) return 15;
  if (value <= 45) return 30;
  return 60;
}

function briefPrompt(brief) {
  const tempo = brief?.tempo || {};
  const low = Math.round(numberOr(tempo.min, 90));
  const high = Math.round(numberOr(tempo.max, 112));
  const energy = String(brief?.energy?.shape || "steady").replace(/_/g, " to ");
  const seconds = Math.max(8, Math.round(numberOr(brief?.duration, numberOr(brief?.seconds, 30))));
  return `${brief?.genre || "cinematic ambient"} instrumental bed, ${brief?.mood || "cinematic"} mood, ${energy} energy, ${low}-${high} BPM, no vocals, clean loop, ${seconds} seconds`;
}

function lockPath(entry) {
  return String(entry?.path || entry?.file || "");
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
  let engineData = null;
  let engineError = "";
  let voiceList = [];
  let voiceError = "";
  let voicesLoading = false;
  let selectedEngine = plan.voice?.engine || "";
  let selectedVoice = plan.voice?.voice || "";
  let selectedRate = numberOr(plan.voice?.rate, 1);
  let cloneOpen = false;
  let cloneBusy = false;
  let cloneConsent = false;
  let cloneName = "";
  let cloneStart = "";
  let cloneEnd = "";
  let cloneManual = false;
  let cloneCandidate = 0;
  let cloneTask = null;
  let cloneError = "";
  let clonePollTimer = 0;
  let clonePlayer = null;
  let clonePlaying = 0;
  let library = [];
  let libraryError = "";
  let libraryLoading = true;
  let selectedTrack = typeof plan.music?.track === "string" ? plan.music.track : "";
  let previewLoading = false;
  let uploadLoading = false;
  let musicBrief = plan.music?.brief && typeof plan.music.brief === "object"
    ? clone(plan.music.brief)
    : null;
  let briefLoading = false;
  let briefError = "";
  let candidates = [];
  let candidateBusy = false;
  let candidateError = "";
  let candidatePreview = -1;
  let candidatePlayer = null;
  let lockedTracks = [];
  let lockedLoading = false;
  let lockedError = "";
  let initialOverrides = plan.script_overrides && typeof plan.script_overrides === "object"
    ? clone(plan.script_overrides)
    : {};
  let scriptSaved = new Set(Object.keys(initialOverrides));
  let scriptValues = clone(initialOverrides);
  let scriptTouched = new Set();
  let sourceLang = String(plan.translate?.source || storyLanguage(ctx) || "en");
  let targetLang = String(plan.translate?.target || "");
  let translateStyle = String(plan.translate?.mode || "smooth");
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
    const result = {
      ...existing,
      source,
      track: selectedTrack,
      name: track?.name || existing.name || baseName(selectedTrack),
      license: track?.license === undefined ? (existing.license ?? null) : track.license,
    };
    if (source === "generated" && musicBrief) result.brief = clone(musicBrief);
    return result;
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

  function translatePlan() {
    return mergeTranslatePlan(plan.mode, plan.translate, sourceLang, targetLang, translateStyle);
  }

  function scriptPlan() {
    if (plan.mode !== "voice_over" && plan.mode !== "dub") return null;
    const values = clone(initialOverrides);
    for (const row of storyScriptLines(ctx.getStory())) {
      const touched = scriptTouched.has(row.key);
      const saved = scriptSaved.has(row.key);
      const own = scriptValues[row.key];
      if (plan.mode === "dub") {
        const line = touched || saved ? own : "";
        if (String(line || "").trim()) values[row.key] = String(line);
        else if (touched) delete values[row.key];
        continue;
      }
      // Voice-over starts from the transcript. Only a changed line is saved;
      // a line the creator cleared stays blank, which tells the render to use
      // the transcript again.
      if (!touched && !saved) continue;
      const line = touched || saved ? own : "";
      if (String(line || "").trim()) values[row.key] = String(line);
      else if (touched) delete values[row.key];
    }
    return cleanScriptOverrides(values);
  }

  function buildPlan() {
    return buildAudioPlan({
      mode: plan.mode,
      duck_db: plan.duck_db,
      loudness: plan.loudness,
      voice: voicePlan(),
      music: musicPlan(),
      translate: translatePlan(),
      scriptOverrides: scriptPlan(),
      modeChosen: Boolean(plan.mode_chosen),
    });
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
    const blocked = dubBlockReason(plan.mode, targetLang);
    if (blocked) {
      setSaveStatus("Not saved — choose a target", "bad");
      if (!disposed) render();
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
        if (/^clone_[a-f0-9]{24}$/.test(selectedVoice)) {
          // Keep the deleted clone in the plan so the render fails with a clear
          // reason instead of quietly speaking in a stock voice.
          setNotice("This story's cloned voice was deleted. Pick another voice.", "bad");
          return;
        }
        selectedVoice = "";
      }
      if (!selectedVoice && voiceList.length) {
        // A cloned voice is never picked silently; the creator chooses it.
        const stock = voiceList.filter((voice) => !voice.clone);
        const pool = stock.length ? stock : voiceList;
        const language = storyLanguage(ctx);
        const preferred = pool.find(
          (voice) => String(voice.lang || "").toLowerCase().startsWith(language),
        );
        selectedVoice = String((preferred || pool[0]).id);
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
      engineData = result && typeof result === "object" ? result : null;
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
    if (!disposed) {
      void loadLockedTracks();
      if (!musicBrief) void ensureBrief(true);
    }
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

  function generationAvailable() {
    const music = engineData?.music || {};
    return ["minimax-music", "lyria-clip"].some((key) => Boolean(music[key]?.available));
  }

  async function ensureBrief(quiet = false) {
    const jobId = currentJobId();
    if (!jobId || briefLoading) return;
    briefLoading = true;
    briefError = "";
    if (!quiet) setNotice("Reading the story for a music brief…");
    try {
      const target = briefTarget(storySeconds(ctx));
      const result = await request(
        `/api/jobs/${encodeURIComponent(jobId)}/music/brief?target=${target}`,
      );
      if (disposed) return;
      if (result?.brief && typeof result.brief === "object") {
        musicBrief = clone(result.brief);
        if (!quiet) setNotice("Music brief ready. Edit the four fields, then generate two beds.", "ok");
      }
    } catch (error) {
      if (disposed) return;
      briefError = error?.message || "Could not build a music brief from this story.";
    } finally {
      briefLoading = false;
      if (!disposed) render();
    }
  }

  function editBriefField(key, value) {
    if (!musicBrief) return;
    if (key === "mood" || key === "genre") musicBrief[key] = String(value || "").slice(0, 80);
    if (key === "energy") {
      musicBrief.energy = { ...(musicBrief.energy || {}), shape: String(value || "hook_payoff") };
    }
    if (key === "tempo") {
      const low = clamp(numberOr(value?.min, 90), 40, 200);
      const high = clamp(numberOr(value?.max, 112), 40, 200);
      musicBrief.tempo = { min: Math.min(low, high), max: Math.max(low, high) };
    }
    musicBrief.prompt = briefPrompt(musicBrief);
    setNotice("Brief changed. Generate again to hear the new direction.");
    render();
  }

  async function generateCandidates() {
    const jobId = currentJobId();
    if (!jobId || candidateBusy) return;
    if (!generationAvailable()) {
      setNotice("Cloud generation needs a MiniMax or OpenRouter key.", "bad");
      render();
      return;
    }
    if (!musicBrief) {
      await ensureBrief();
      if (!musicBrief) {
        setNotice(briefError || "Read a music brief first.", "bad");
        render();
        return;
      }
    }
    candidateBusy = true;
    candidateError = "";
    setNotice("Generating two music candidates. This can take a minute…");
    render();
    try {
      const result = await request(
        `/api/jobs/${encodeURIComponent(jobId)}/music/candidates`,
        { method: "POST", body: { brief: musicBrief, count: 2 } },
      );
      if (disposed) return;
      candidates = Array.isArray(result?.candidates) ? result.candidates : [];
      if (!candidates.length) throw new Error("No music candidate came back.");
      setNotice("Two candidates ready. Preview A and B, then use one.", "ok");
    } catch (error) {
      if (disposed) return;
      candidateError = error?.message || "Could not generate music candidates.";
      setNotice(candidateError, "bad");
    } finally {
      candidateBusy = false;
      if (!disposed) render();
    }
  }

  function stopCandidatePreview() {
    if (candidatePlayer) {
      try {
        candidatePlayer.pause();
        candidatePlayer.removeAttribute("src");
        candidatePlayer.load();
      } catch (_) {
        /* A failed stop must not block the panel. */
      }
    }
    candidatePlayer = null;
    candidatePreview = -1;
  }

  async function previewCandidate(index) {
    const jobId = currentJobId();
    if (!jobId) return;
    if (candidatePreview === index) {
      stopCandidatePreview();
      render();
      return;
    }
    stopCandidatePreview();
    try {
      syncMediaCookie();
      candidatePlayer = new Audio(
        `/api/jobs/${encodeURIComponent(jobId)}/music/candidates/${index}?v=${Date.now()}`,
      );
      candidatePlayer.addEventListener("ended", () => {
        candidatePreview = -1;
        candidatePlayer = null;
        if (!disposed) render();
      }, { once: true });
      await candidatePlayer.play();
      candidatePreview = index;
      setNotice(`Playing candidate ${index === 0 ? "A" : "B"}. Ducking is applied when the story renders.`, "ok");
    } catch (error) {
      stopCandidatePreview();
      setNotice(error?.message || "Could not play that candidate.", "bad");
    }
    if (!disposed) render();
  }

  async function lockCandidate(index) {
    const jobId = currentJobId();
    const candidate = candidates[index];
    if (!jobId || !candidate || candidateBusy) return;
    candidateBusy = true;
    candidateError = "";
    setNotice(`Locking candidate ${index === 0 ? "A" : "B"} into this story…`);
    render();
    try {
      const result = await request(
        `/api/jobs/${encodeURIComponent(jobId)}/music/lock`,
        {
          method: "POST",
          body: {
            path: String(candidate.path || ""),
            source_type: "generated",
            brief: musicBrief,
            provider: {
              provider: candidate.provider || candidate.descriptor || "",
              model: candidate.model || "",
              prompt: musicBrief?.prompt || "",
            },
            licence: candidate.licence || candidate.license || null,
          },
        },
      );
      if (disposed) return;
      const locked = result?.locked;
      if (!locked?.file) throw new Error("The lock response came back without a file.");
      applyLocked(locked);
      await loadLockedTracks();
      setNotice(`Candidate ${index === 0 ? "A" : "B"} locked. It is content-hashed into the edit.`, "ok");
      await save();
    } catch (error) {
      if (disposed) return;
      candidateError = error?.message || "Could not lock that candidate.";
      setNotice(candidateError, "bad");
    } finally {
      candidateBusy = false;
      if (!disposed) render();
    }
  }

  function applyLocked(entry) {
    const file = String(entry?.file || entry?.path || "");
    if (!file) throw new Error("That locked bed has no file.");
    const music = {
      ...clone(entry),
      track: file,
      source: String(entry?.source || "generated"),
      license: entry?.licence ?? entry?.license ?? null,
    };
    plan.music = music;
    selectedTrack = file;
    if (plan.mode === "original") plan.mode = "original_bed";
    if (!library.some((track) => String(track.id) === file)) {
      library = [{
        id: file,
        name: entry?.file ? baseName(entry.file) : "Locked music",
        moods: [],
        source: music.source,
        license: music.license,
        duration: entry?.duration,
      }, ...library];
    }
    dirty = true;
    revision += 1;
    setNotice("Music bed selected. It will be used by the next render.", "ok");
    render();
  }

  async function loadLockedTracks() {
    const jobId = currentJobId();
    if (!jobId) return;
    lockedLoading = true;
    lockedError = "";
    try {
      const result = await request(`/api/jobs/${encodeURIComponent(jobId)}/music/locked`);
      lockedTracks = Array.isArray(result?.locked) ? result.locked : [];
    } catch (error) {
      lockedTracks = [];
      lockedError = error?.message || "Could not read locked music.";
    } finally {
      lockedLoading = false;
    }
    if (!disposed) render();
  }

  async function chooseLocked(entry) {
    try {
      applyLocked(entry);
      await save();
    } catch (error) {
      setNotice(error?.message || "Could not use that locked bed.", "bad");
      render();
    }
  }

  async function useClonedVoice(voiceId) {
    selectedEngine = "heygen";
    selectedVoice = voiceId;
    await loadEngines();
    selectedEngine = "heygen";
    await loadVoices("heygen");
    selectedVoice = voiceId;
    scheduleSave();
    if (!disposed) render();
  }

  function stopClonePlayer() {
    if (clonePlayer) clonePlayer.pause();
    clonePlayer = null;
    clonePlaying = 0;
  }

  function stopClonePoll() {
    if (clonePollTimer) window.clearTimeout(clonePollTimer);
    clonePollTimer = 0;
  }

  function cloneStageCopy(task) {
    if (!task) return "";
    if (task.state === "failed") return task.error || "The voice search failed.";
    if (task.state === "cancelled") return "Search cancelled.";
    if (task.state === "done") return "";
    const stage = String(task.stage || task.state || "");
    if (stage === "queued") return "Queued behind other work…";
    if (stage === "preparing" || stage === "starting") return "Finding the speech and removing music…";
    if (stage === "scoring") return "Scoring speech windows…";
    if (stage === "exporting") return "Cutting the best clips…";
    return "Working…";
  }

  async function pollCandidates(jobId) {
    try {
      const state = await voiceCandidateState(jobId);
      if (disposed) return;
      cloneTask = state;
      if (state.state === "queued" || state.state === "running") {
        clonePollTimer = window.setTimeout(() => { void pollCandidates(jobId); }, 1500);
      } else {
        cloneBusy = false;
        clonePollTimer = 0;
        cloneError = state.state === "failed"
          ? (state.error || "The voice search failed.")
          : state.state === "cancelled" ? "Search cancelled." : "";
      }
      render();
    } catch (error) {
      if (disposed) return;
      cloneBusy = false;
      clonePollTimer = 0;
      cloneError = error?.message || "Could not read the voice search.";
      render();
    }
  }

  async function findClips() {
    if (cloneBusy) return;
    const jobId = currentJobId();
    if (!jobId) {
      setNotice("This panel could not find the open video.", "bad");
      render();
      return;
    }
    stopClonePlayer();
    stopClonePoll();
    cloneBusy = true;
    cloneError = "";
    cloneTask = null;
    cloneCandidate = 0;
    cloneConsent = false;
    render();
    try {
      const state = await findVoiceCandidates(jobId);
      if (disposed) return;
      cloneTask = state;
      if (state.state === "queued" || state.state === "running") {
        clonePollTimer = window.setTimeout(() => { void pollCandidates(jobId); }, 1200);
      } else {
        cloneBusy = false;
      }
    } catch (error) {
      if (disposed) return;
      cloneBusy = false;
      cloneError = error?.message || "Could not start the voice search.";
    }
    if (!disposed) render();
  }

  async function cancelClips() {
    const jobId = currentJobId();
    if (!jobId) return;
    stopClonePoll();
    try {
      const state = await cancelVoiceCandidates(jobId);
      if (disposed) return;
      cloneTask = state;
      cloneError = "Search cancelled.";
    } catch (error) {
      if (!disposed) cloneError = error?.message || "Could not cancel the search.";
    } finally {
      cloneBusy = false;
      if (!disposed) render();
    }
  }

  function selectCandidate(index) {
    cloneCandidate = Number(index) || 0;
    cloneManual = false;
    render();
  }

  async function playCandidate(item) {
    const jobId = currentJobId();
    if (!jobId || !item?.index) return;
    if (clonePlaying === item.index && clonePlayer) {
      stopClonePlayer();
      render();
      return;
    }
    stopClonePlayer();
    syncMediaCookie();
    const player = new Audio(voiceCandidateAudioUrl(jobId, item.index));
    clonePlayer = player;
    clonePlaying = item.index;
    const done = () => {
      if (clonePlayer === player) {
        clonePlayer = null;
        clonePlaying = 0;
        if (!disposed) render();
      }
    };
    player.addEventListener("ended", done, { once: true });
    player.addEventListener("error", done, { once: true });
    render();
    try {
      await player.play();
    } catch (error) {
      done();
      setNotice(error?.message || "Could not play that clip.", "bad");
      render();
    }
  }

  async function cloneVideoVoice() {
    if (cloneBusy) return;
    const jobId = currentJobId();
    if (!jobId) {
      setNotice("This panel could not find the open video.", "bad");
      render();
      return;
    }
    if (!cloneConsent) {
      setNotice("Confirm you are the speaker, or have their permission, before cloning.", "bad");
      render();
      return;
    }
    const body = { name: cloneName.trim(), consent: true, language: storyLanguage(ctx) };
    let picked = null;
    if (cloneManual) {
      const start = Number.parseFloat(cloneStart);
      const end = Number.parseFloat(cloneEnd);
      if (Number.isFinite(start) && start >= 0) body.start = start;
      if (Number.isFinite(end) && end > 0) body.end = end;
    } else {
      if (!cloneCandidate) {
        setNotice("Pick one of the voice clips first.", "bad");
        render();
        return;
      }
      body.candidate = cloneCandidate;
      picked = (cloneTask?.candidates || []).find((item) => item.index === cloneCandidate);
    }
    cloneBusy = true;
    setNotice(
      cloneManual
        ? "Cleaning that stretch of the video…"
        : "Cloning the voice clip you picked…",
      "",
    );
    render();
    try {
      const record = await cloneFromVideo(jobId, body);
      cloneConsent = false;
      cloneOpen = false;
      stopClonePlayer();
      await useClonedVoice(record.voice_id);
      const which = picked ? `clip ${picked.index} (${formatDuration(picked.start)}–${formatDuration(picked.end)})` : "the time range you chose";
      const warning = record.warning ? ` ${record.warning}` : "";
      setNotice(`Cloned “${record.name}” from ${which} and picked it for this story.${warning} Press Preview voice to hear it.`, "ok");
    } catch (error) {
      setNotice(error?.message || "Could not clone the video voice.", "bad");
    } finally {
      cloneBusy = false;
      if (!disposed) render();
    }
  }

  function candidateCard(item) {
    const selected = cloneCandidate === item.index;
    const play = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: clonePlaying === item.index ? "Stop" : "Play",
      disabled: false,
    });
    play.addEventListener("click", () => { void playCandidate(item); });
    const pick = el("button", {
      class: `st-btn ${selected ? "st-btn-primary" : "st-btn-ghost"} st-btn-small`,
      type: "button",
      text: selected ? "Selected" : "Use this clip",
      disabled: cloneBusy,
    });
    pick.addEventListener("click", () => selectCandidate(item.index));
    const score = Number(item.score);
    const card = el("div", { class: "st-voice-clone-row" }, [
      el("div", { class: "st-setup-engine-head" }, [
        el("strong", { text: `Clip ${item.index}` }),
        el("span", { class: `st-chip ${selected ? "st-chip-ok" : ""}`, text: Number.isFinite(score) ? `Score ${Math.round(score)}` : "Scored clip" }),
        el("span", { class: "st-mono st-hint", text: `${formatDuration(item.start)}–${formatDuration(item.end)} · ${Math.round(Number(item.duration) || 0)}s` }),
      ]),
      el("p", { class: "st-field-hint", text: `${formatDuration(item.start)}–${formatDuration(item.end)} in the video.` }),
    ]);
    const warnings = Array.isArray(item.warnings) ? item.warnings : [];
    for (const warning of warnings.slice(0, 2)) {
      card.append(el("p", { class: "st-field-hint", text: warning }));
    }
    card.append(el("div", { class: "st-setup-key-actions" }, [play, pick]));
    return card;
  }

  function cloneBlock() {
    const ready = Boolean(engines?.heygen?.clone);
    const block = el("div", { class: "st-voice-clone-edit" });
    const toggle = el("button", {
      class: "st-btn st-btn-ghost st-btn-small",
      type: "button",
      text: cloneOpen ? "Hide voice cloning" : "Clone the video's voice",
      disabled: cloneBusy,
    });
    toggle.addEventListener("click", () => { cloneOpen = !cloneOpen; render(); });
    block.append(el("div", { class: "st-layer-add", style: "margin-top:9px" }, [toggle]));
    if (!cloneOpen) return block;
    if (!ready) {
      block.append(el("p", { class: "st-field-hint", text: "Add an OpenRouter key in Setup to clone the speaker of this video. Your own voice lives in Setup → My voice." }));
      return block;
    }
    const name = el("input", { type: "text", maxLength: 64, value: cloneName, placeholder: "Video voice", "aria-label": "Cloned voice name" });
    name.addEventListener("input", () => { cloneName = name.value; });
    block.append(el("label", { class: "st-field" }, [el("span", { text: "Name" }), name]));

    const find = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: cloneBusy ? "Finding clips…" : (cloneTask?.candidates?.length ? "Find the best voice clips again" : "Find the best voice clips"),
      disabled: cloneBusy,
    });
    find.addEventListener("click", () => { void findClips(); });
    block.append(el("div", { class: "st-layer-add" }, [find]));

    const stageCopy = cloneStageCopy(cloneTask);
    if (stageCopy) {
      block.append(el("p", { class: "st-field-hint", role: "status", text: stageCopy }));
    }
    if (cloneError) {
      block.append(el("p", { class: "st-error", role: "alert", text: cloneError }));
    }
    const candidates = Array.isArray(cloneTask?.candidates) ? cloneTask.candidates : [];
    if (candidates.length) {
      block.append(el("p", { class: "st-field-hint", text: "Listen, then pick the clip with the clearest single voice and the least music. The cleaned clip becomes the clone reference." }));
      block.append(el("div", { class: "st-voice-clone-list" }, candidates.map(candidateCard)));
    } else if (cloneTask?.state === "done") {
      block.append(el("p", { class: "st-field-hint", text: "No clean speech clips were found. Try a range with one speaker, or pick the time range yourself." }));
    }
    if (cloneBusy && cloneTask && (cloneTask.state === "queued" || cloneTask.state === "running")) {
      const cancel = el("button", {
        class: "st-btn st-btn-quiet st-btn-small",
        type: "button",
        text: "Cancel search",
      });
      cancel.addEventListener("click", () => { void cancelClips(); });
      block.append(el("div", { class: "st-layer-add" }, [cancel]));
    }

    const manualToggle = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: cloneManual ? "Hide the time range" : "Choose the time range yourself",
    });
    manualToggle.addEventListener("click", () => { cloneManual = !cloneManual; render(); });
    block.append(el("div", { class: "st-layer-add", style: "margin-top:6px" }, [manualToggle]));

    if (cloneManual) {
      const start = el("input", { type: "number", min: "0", step: "1", value: cloneStart, placeholder: "auto", "aria-label": "Clone from (seconds)" });
      start.addEventListener("input", () => { cloneStart = start.value; });
      const end = el("input", { type: "number", min: "0", step: "1", value: cloneEnd, placeholder: "auto", "aria-label": "Clone to (seconds)" });
      end.addEventListener("input", () => { cloneEnd = end.value; });
      block.append(el("div", { class: "st-control-grid" }, [
        field("From (s)", start, "Source time. Empty uses all speech."),
        field("To (s)", end, "Pick a stretch where only one person talks."),
      ]));
      block.append(el("p", { class: "st-field-hint", text: "This range is cleaned first; if cleaning fails, the raw cut is used and the response says so." }));
    }

    const tick = el("input", { type: "checkbox", checked: cloneConsent, id: "st-voice-consent-video" });
    tick.addEventListener("change", () => { cloneConsent = Boolean(tick.checked); render(); });
    const go = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: cloneBusy ? "Cloning…" : (cloneManual ? "Clone that range" : "Clone this voice"),
      disabled: cloneBusy || !cloneConsent || (!cloneManual && !cloneCandidate),
    });
    go.addEventListener("click", () => { void cloneVideoVoice(); });
    block.append(
      el("label", { class: "st-voice-clone-consent", for: "st-voice-consent-video" }, [
        tick, el("span", { text: CONSENT_COPY.video }),
      ]),
      el("div", { class: "st-layer-add" }, [go]),
    );
    return block;
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
      const previous = plan.mode;
      plan.mode = select.value;
      plan.mode_chosen = true;
      // A script written for one mode is the wrong language for the other:
      // Voice-over lines are source-language, Dub lines are translated.
      if ((previous === "dub") !== (plan.mode === "dub")) {
        initialOverrides = {};
        scriptSaved = new Set();
        scriptValues = {};
        scriptTouched = new Set();
      }
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

  function briefCard() {
    const card = el("div", { class: "st-card st-check-card" });
    const head = el("div", { class: "st-layer-stage-head" }, [
      el("h3", { text: "Music brief" }),
      el("span", { class: "st-mono st-hint", text: musicBrief?.seconds ? `${Math.round(numberOr(musicBrief.seconds, 0))} s` : "" }),
    ]);
    const read = el("button", {
      class: "st-btn st-btn-quiet st-btn-small",
      type: "button",
      text: briefLoading ? "Reading…" : musicBrief ? "Read again" : "Read the story",
      disabled: briefLoading,
    });
    read.addEventListener("click", () => { void ensureBrief(); });
    head.append(read);
    card.append(head);
    card.append(el("p", { class: "st-hint", text: "Four plain fields. The cloud prompt is built from them; you never edit a raw prompt." }));
    if (briefError) card.append(el("p", { class: "st-error", text: briefError }));
    if (!musicBrief) {
      if (!briefError) card.append(el("p", { class: "st-hint", text: "Read the story to get a mood, energy, genre and tempo suggestion." }));
      return card;
    }

    const mood = el("input", {
      type: "text", maxlength: "80", value: musicBrief.mood || "",
      "aria-label": "Music mood",
    });
    mood.addEventListener("change", () => editBriefField("mood", mood.value));
    const genre = el("input", {
      type: "text", maxlength: "80", value: musicBrief.genre || "",
      "aria-label": "Music genre",
    });
    genre.addEventListener("change", () => editBriefField("genre", genre.value));
    const energy = el("select", { "aria-label": "Music energy" });
    for (const [value, label] of [
      ["hook_payoff", "Hook then payoff"],
      ["rise", "Slow rise"],
      ["steady", "Steady"],
      ["calm", "Calm"],
    ]) {
      energy.append(el("option", {
        value, label, selected: String(musicBrief.energy?.shape || "hook_payoff") === value,
      }));
    }
    energy.addEventListener("change", () => editBriefField("energy", energy.value));
    const tempoMin = el("input", {
      type: "number", min: "40", max: "200", step: "1",
      value: String(numberOr(musicBrief.tempo?.min, 90)),
      "aria-label": "Tempo low",
    });
    const tempoMax = el("input", {
      type: "number", min: "40", max: "200", step: "1",
      value: String(numberOr(musicBrief.tempo?.max, 112)),
      "aria-label": "Tempo high",
    });
    const commitTempo = () => editBriefField("tempo", { min: tempoMin.value, max: tempoMax.value });
    tempoMin.addEventListener("change", commitTempo);
    tempoMax.addEventListener("change", commitTempo);
    const tempo = el("div", { class: "st-range-row" }, [
      el("span", { class: "st-field-label", text: "Tempo" }),
      tempoMin,
      el("span", { class: "st-hint", text: "to" }),
      tempoMax,
      el("span", { class: "st-hint", text: "BPM" }),
    ]);
    card.append(el("div", { class: "st-control-grid" }, [
      field("Mood", mood),
      field("Genre", genre),
      field("Energy", energy),
      field("Tempo", tempo),
    ]));
    card.append(el("p", { class: "st-field-hint", text: musicBrief.prompt || briefPrompt(musicBrief) }));
    return card;
  }

  function candidateRows() {
    const wrap = el("div", { class: "st-layer-list", style: "margin-top:9px" });
    if (candidateError) wrap.append(el("p", { class: "st-error", text: candidateError }));
    if (!candidates.length && !candidateBusy) {
      wrap.append(el("p", { class: "st-hint", text: "Two candidates appear here. Preview both against the story, then use one." }));
      return wrap;
    }
    candidates.forEach((candidate, index) => {
      const letter = index === 0 ? "A" : "B";
      const failed = Boolean(candidate.error);
      const selected = String(candidate.file || baseName(candidate.path)) === baseName(selectedTrack);
      const row = el("div", { class: `st-layer-row st-layer-row-static${selected ? " is-active" : ""}` }, [
        el("span", { class: "st-layer-badge", text: letter }),
        el("span", { class: "st-layer-name" }, [
          el("strong", { text: failed ? "Candidate failed" : `Candidate ${letter}`, style: "display:block;color:var(--st-text);font-weight:500" }),
          el("small", {
            text: failed
              ? String(candidate.error).slice(0, 220)
              : [candidate.provider, candidate.model, candidate.seed !== undefined ? `seed ${candidate.seed}` : ""].filter(Boolean).join(" · ") || "Generated bed",
          }),
        ]),
      ]);
      const actions = el("div", { class: "st-layer-add", style: "margin:0;flex:0 0 auto" });
      if (!failed) {
        const preview = el("button", {
          class: "st-btn st-btn-ghost st-btn-small",
          type: "button",
          text: candidatePreview === index ? "Stop" : `Preview ${letter}`,
        });
        preview.addEventListener("click", () => { void previewCandidate(index); });
        const use = el("button", {
          class: "st-btn st-btn-primary st-btn-small",
          type: "button",
          text: selected ? "Used" : `Use ${letter}`,
          disabled: selected || candidateBusy,
        });
        use.addEventListener("click", () => { void lockCandidate(index); });
        actions.append(preview, use);
      }
      row.append(actions);
      wrap.append(row);
    });
    if (candidateBusy) wrap.append(el("p", { class: "st-hint", text: "Working on the cloud request…" }));
    return wrap;
  }

  function cloudCard() {
    const card = el("div", { class: "st-card st-check-card" });
    const ready = generationAvailable();
    card.append(el("div", { class: "st-layer-stage-head" }, [
      el("h3", { text: "Generate a bed" }),
      el("span", { class: `st-chip ${ready ? "st-chip-ok" : "st-chip-busy"}`, text: ready ? "Cloud ready" : "Needs key" }),
    ]));
    if (!ready) {
      card.append(el("p", { class: "st-warning", text: "Cloud generation needs a MiniMax or OpenRouter key." }));
      card.append(el("p", { class: "st-hint", text: "Library tracks and uploads still work offline. Add a key in Setup to generate two new beds here." }));
      return card;
    }
    card.append(el("p", { class: "st-hint", text: "Two instrumental beds from the brief above. Each is cached by provider, model, brief and seed." }));
    const generate = el("button", {
      class: "st-btn st-btn-primary st-btn-small",
      type: "button",
      text: candidateBusy ? "Generating…" : "Generate two candidates",
      disabled: candidateBusy || briefLoading || !musicBrief,
    });
    generate.addEventListener("click", () => { void generateCandidates(); });
    card.append(el("div", { class: "st-layer-add", style: "margin-top:9px" }, [generate]));
    card.append(candidateRows());
    return card;
  }

  function lockedCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("div", { class: "st-layer-stage-head" }, [
      el("h3", { text: "Locked beds" }),
      lockedLoading ? el("span", { class: "st-hint", text: "Reading…" }) : null,
    ]));
    if (lockedError) card.append(el("p", { class: "st-error", text: lockedError }));
    if (!lockedTracks.length && !lockedLoading) {
      card.append(el("p", { class: "st-hint", text: "Generated and library beds you lock are copied into this job and kept in this list." }));
      return card;
    }
    const list = el("div", { class: "st-layer-list", style: "margin-top:9px" });
    for (const entry of lockedTracks.slice(0, 20)) {
      const path = lockPath(entry);
      const active = path && path === selectedTrack;
      const row = el("button", {
        class: `st-layer-row${active ? " is-active" : ""}`,
        type: "button",
        "aria-pressed": active ? "true" : "false",
        title: path,
      }, [
        el("span", { class: "st-layer-badge", text: entry.source === "generated" ? "AI" : "Locked" }),
        el("span", { class: "st-layer-name" }, [
          el("strong", { text: baseName(path) || "Locked bed", style: "color:var(--st-text);font-weight:500" }),
          el("small", { text: entry.brief?.mood ? `${entry.brief.mood} · ${entry.brief.genre || ""}` : licenseLabel(entry.licence || entry.license) }),
        ]),
      ]);
      row.addEventListener("click", () => { void chooseLocked(entry); });
      list.append(row);
    }
    card.append(list);
    return card;
  }

  function libraryCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Library and upload" }));
    card.append(el("p", { class: "st-hint", text: "Your own tracks always work, with the network off." }));
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

  function musicCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Music bed" }));
    card.append(el("p", { class: "st-hint", text: "Pick a library track, upload your own, or generate two candidates from a four-field brief. Locking copies the bed into this job." }));
    card.append(briefCard());
    card.append(cloudCard());
    card.append(lockedCard());
    card.append(libraryCard());
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
            text: `${item.clone ? "★ " : ""}${item.name || id}${item.lang ? ` · ${item.lang}` : ""}`,
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
      if (selectedEngine === "heygen") {
        card.append(el("p", { class: "st-field-hint", text: "HeyGen Voice Turbo is free until 30 Nov 2026 on OpenRouter. It is a first-class voice, not a fallback." }));
      }

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
    if (engines && voiceRoomOn()) card.append(cloneBlock());
    return card;
  }

  function languageOptions(select, selected, emptyLabel = "") {
    if (emptyLabel) {
      select.append(el("option", {
        value: "", text: emptyLabel, selected: !selected,
      }));
    }
    const known = new Set(DUB_LANGUAGES.map(([code]) => code));
    for (const [code, label] of DUB_LANGUAGES) {
      select.append(el("option", {
        value: code,
        text: label,
        selected: code === String(selected || "").split("-")[0].toLowerCase(),
      }));
    }
    const current = String(selected || "").split("-")[0].toLowerCase();
    if (current && !known.has(current)) {
      select.append(el("option", {
        value: String(selected), text: languageLabel(selected), selected: true,
      }));
    }
  }

  function dubCard() {
    const card = el("div", { class: "st-card st-check-card" });
    card.append(el("h3", { text: "Dub" }));
    card.append(el("p", {
      class: "st-hint",
      text: "Dub translates the script into another language. Voice-over keeps the story's own language and only changes the voice.",
    }));
    const blocked = dubBlockReason(plan.mode, targetLang);
    if (blocked) {
      card.append(el("p", { class: "st-warning", text: blocked }));
      card.append(el("p", {
        class: "st-field-hint",
        text: "This edit was saved without a target, so a render will fail. Pick a target here to fix it.",
      }));
    }

    const source = el("select", { "aria-label": "Dub source language" });
    languageOptions(source, sourceLang);
    source.addEventListener("change", () => {
      sourceLang = source.value;
      scheduleSave();
    });

    const target = el("select", { "aria-label": "Dub target language" });
    languageOptions(target, targetLang, "Choose a target language");
    target.addEventListener("change", () => {
      targetLang = target.value;
      scheduleSave();
      render();
    });

    card.append(el("div", { class: "st-control-grid" }, [
      field("Spoken language", source, "Detected from the story. Confirm it before Dub."),
      field("Target language", target, "Required. Dub cannot save or queue without it."),
    ]));
    if (targetLang && sourceLang && targetLang.split("-")[0] === sourceLang.split("-")[0]) {
      card.append(el("p", {
        class: "st-warning",
        text: "The target matches the source, so Dub will re-speak the same language instead of translating.",
      }));
    }
    card.append(el("p", {
      class: "st-field-hint",
      text: "Translated captions are deferred. Captions stay in the source language until Dub renders end to end.",
    }));
    return card;
  }

  function scriptCard() {
    const card = el("div", { class: "st-card st-check-card" });
    const dub = plan.mode === "dub";
    card.append(el("h3", { text: dub ? "Dub script" : "Voice-over script" }));
    card.append(el("p", {
      class: "st-hint",
      text: dub
        ? "This is the translated script. A line you write here wins over machine translation; a blank line uses the machine translation."
        : "Edit the words the voice speaks. A blank line uses the transcript.",
    }));
    if (dub) {
      card.append(el("p", {
        class: "st-field-hint",
        text: "Write each line in the target language. The source line stays visible for reference.",
      }));
    }

    const rows = storyScriptLines(ctx.getStory());
    if (!rows.length) {
      card.append(el("p", {
        class: "st-hint",
        text: "No transcript lines are available for this story. Turn on Speech during Import to write a script here.",
      }));
      return card;
    }

    const list = el("div", { class: "st-layer-list", style: "margin-top:9px" });
    rows.forEach((row, index) => {
      const saved = scriptSaved.has(row.key);
      const touched = scriptTouched.has(row.key);
      const value = touched || saved
        ? String(scriptValues[row.key] ?? "")
        : dub ? "" : row.text;
      const role = row.role && row.role !== "beat" ? ` · ${row.role}` : "";
      const wrap = el("div", { class: "st-field", style: "margin-bottom:10px" }, [
        el("span", {
          class: "st-field-label",
          text: `Line ${index + 1}${role}`,
        }),
      ]);
      if (dub) {
        wrap.append(el("small", {
          class: "st-field-hint",
          style: "display:block;margin:2px 0 4px",
          text: `Source: ${row.text}`,
        }));
      }
      const area = el("textarea", {
        rows: "2",
        maxlength: "600",
        "aria-label": `${dub ? "Dub" : "Voice-over"} line ${index + 1}`,
        placeholder: dub ? "Leave blank to use the machine translation." : "Leave blank to use the transcript.",
        style: "width:100%;min-height:58px;resize:vertical",
      });
      area.value = value;
      area.addEventListener("input", () => {
        scriptTouched.add(row.key);
        scriptValues[row.key] = area.value;
        scheduleSave();
      });
      wrap.append(area);
      list.append(wrap);
    });
    card.append(list);
    card.append(el("p", {
      class: "st-field-hint",
      text: dub
        ? "Clear a line to return it to machine translation."
        : "Clear a line to return to the transcript.",
    }));
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
    const blocked = dubBlockReason(plan.mode, targetLang);
    const head = el("div", { class: "st-card st-check-card" }, [
      el("h3", { text: "Audio" }),
      el("p", { class: "st-hint", text: "Voice first, then one music bed. The source sound, ducking and loudness stay in the same edit." }),
    ]);
    saveNode = el("span", {
      class: "st-edit-save",
      role: "status",
      "aria-live": "polite",
      text: saving
        ? "Saving…"
        : blocked
          ? (dirty ? "Not saved — choose a target" : "Saved edit needs a target")
          : dirty ? "Unsaved changes" : "Saved",
      dataset: { tone: saving ? "busy" : blocked ? "bad" : dirty ? "dirty" : "ok" },
    });
    head.append(el("div", { style: "margin-top:8px" }, [saveNode]));
    if (blocked) head.append(el("p", { class: "st-warning", text: blocked }));
    if (notice) {
      head.append(el("p", {
        class: noticeTone === "bad" ? "st-error" : "st-status",
        text: notice,
      }));
    }
    host.append(head);
    host.append(modeCard());
    host.append(voiceCard());
    if (plan.mode === "dub") host.append(dubCard());
    if (plan.mode === "dub" || plan.mode === "voice_over") host.append(scriptCard());
    host.append(musicCard());
    host.append(mixCard());
    host.append(el("p", { class: "st-hint", text: "The mix is stored in this edit. Voice and music are rendered by the audio build; nothing is sent to a cloud service unless you press Preview on a cloud voice." }));
  }

  render();
  void loadEngines();
  void loadLibrary();

  return () => {
    if (saveTimer) window.clearTimeout(saveTimer);
    stopCandidatePreview();
    stopClonePlayer();
    stopClonePoll();
    if (dirty && !saving && !dubBlockReason(plan.mode, targetLang)) {
      const jobId = currentJobId();
      const current = ctx.getEdit();
      if (jobId && current) {
        void patchEdit(jobId, current.id, { audio: buildPlan() }).catch(() => {});
      }
    }
    disposed = true;
  };
}
