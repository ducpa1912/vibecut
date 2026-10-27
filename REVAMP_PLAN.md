# VibeCut Studio — Revamp Plan

**Status:** Approved direction (founder decisions 2026-10-27). Replaces `BUILD_PLAN.md` as the build path.
**Baseline:** `main` at `1bedc66`.
**Goal:** build the complete product (Flow 1 and Flow 2 embedded in one workstation) before any launch work. This plan covers product and engineering only.

### Founder decisions recorded

| # | Decision |
|---|---|
| 1 | Approved: Check pre-fills the Clean layer; both flows live in one Edit document and one editor |
| 2 | Classic UI (`app.js` / `creator.js`) stays, hidden behind a setting, as a quick fallback |
| 3 | Own handle/logo cleanup is allowed with an own-footage attestation |
| 4 | Music = library + upload + cloud AI generation. No local music model |
| 5 | Build the completed product; sales/pricing is out of scope for this plan |
| 6 | Remove models and engines the product no longer needs (§9) |
| 7 | Detailed STT, TTS and music generation plans (§6–§8) |

---

## 1. What the product is

One local Mac workstation for turning long or finished video into short posts:

```text
IMPORT → CHECK → STORIES → EDIT → FINISH
```

| Step | Job | Built on |
|---|---|---|
| **Import** | file, path, URL; rights attestation | existing ingest, CAS source store |
| **Check** | what does this footage need? baked text, speech, music, faces, quality | new `detect.py`; existing Vision OCR/faces, transcript, scene scan |
| **Stories** | 3–6 stories with hook/payoff/evidence; sentence edits | existing Clip Set, selection, tighten |
| **Edit** | one editor per story: Clean, Text, Captions, Effects, Color, Audio | existing Smart Cut, Caption Studio, audio layer; new layers |
| **Finish** | render 9:16/4:5, versions, packet, review link, exports | existing artifacts, packets, shares, story queue |

**Flow 1 (clean old text)** and **Flow 2 (new hook, captions, effects, music, look)** are layers in the same per-story Edit document, not modes or screens. Check pre-fills the Clean layer when it finds baked text. If there is none, the Clean layer stays empty and the creator is simply in Flow 2.

**Platform:** macOS 26+ on Apple Silicon. This is required by the on-device SpeechAnalyzer STT (§6) and Apple Translation.

**Offline rule:**
- Import, Check, Stories, Edit, render and packet all work with the network off.
- Cloud is used only for features that say so in the UI: cloud music generation, cloud voices, optional cloud transcription, and AI text.
- Cloud features use the creator's own API keys.

---

## 2. Code review findings that shape this plan

Line refs are at `1bedc66`.

1. **One render core already exists.** `render.render_reel` (`render.py:864`) has one call site (`app.py:1845`):
   - per-scene `_segment` (crop + fades, cached, `render.py:354`)
   - → `_concat_video`
   - → `_burn_captions` (Pillow PNG overlays with `enable=between(t,…)`, `render.py:702`)
   - → `_audio_track` / `audio._duck_and_mix`
   - → `_mux`.

   Every new layer fits one of these stages, so no second renderer is needed.
2. **OCR geometry is thrown away.** The Swift probe returns a `box` per OCR line (`tools/vision_probe.swift:250`). `pipeline._apply_scene_read` (`pipeline.py:2471`) keeps only the joined text.
3. **OCR runs once per scene.** That is enough for hook scoring, not for text tracking.
4. **Word timings are interpolated, not measured:**
   - `captions.py:875` estimates word times;
   - `pipeline.transcribe` runs `mlx_whisper` without `--word-timestamps`;
   - `tools/transcribe_apple.swift:68` reads only the result-level `range`, although `.audioTimeRange` is already requested.
5. **Two UIs coexist:** `static/app.js` (5,490 lines) and `static/creator.js` (3,269 lines), both as classic scripts in one `index.html`.
6. **Flow 1/2 prototypes** (`cleanup.py`, `overlays.py`) are good validators, but they never render.
7. **The watermark guard is label-based** (`cleanup.py:46,167`). A box labelled `logo` passes.
8. **The engine sprawl is large:**
   - 12 TTS engines (`audio.py:483`);
   - 7 music engines, including 3 local models;
   - 6 translation providers, of which 3 are dead code: `translate_providers` filters them out at `audio.py:478`;
   - local LLM paths (`local-mlx`, `ollama`);
   - roughly 7 GB of model caches on the dev Mac (§9).
9. **ffmpeg 9.0.2 has every filter needed:** `eq`, `colortemperature`, `lut3d`, `vignette`, `noise`, `unsharp`, `gblur`, `drawbox`, `sidechaincompress`, `loudnorm`.

---

## 3. Core model: the Edit document

Each story gets a versioned **Edit**, stored like caption tracks today: immutable versions, with a pointer `job["story_edits"]["{set_id}:{story_id}:{aspect}"]`. Every edit creates a new version, and undo/restore use `history_store`.

```text
Edit (schema 1)
  id, version, parent, hash
  story_ref        set_id, story_id, clip snapshot hash
  aspect           9:16 | 4:5   (4:5 forks from 9:16, then diverges)
  clean            CleanLayer[]        Flow 1
  reframe          crop path ref + overrides
  motion           MotionFx[]          punch-in, snap zoom, push, shake
  color            ColorPlan           preset/LUT + sliders
  graphics         TextLayer[] + GraphicFx[]
  captions         caption track id + style id
  audio            AudioPlan           (§6–§8)
```

**Coordinate rule:**
- `clean` boxes use **source** coordinates and render before the crop.
- `graphics` and `captions` use **output** coordinates and render after the crop.
- `motion` changes the crop window itself.

**Identity:** the `artifacts.py` spec hash adds `edit.hash`. That hash covers:
- every layer;
- every referenced asset's content hash (LUT, sticker, font, music file, voice clip);
- the renderer version.

The same Edit always produces the same artifact id, so G2 lineage and pinned review links keep working.

### Layer catalogue

| Layer | Items | ffmpeg stage |
|---|---|---|
| **Clean** | `crop_guard`, `blur`, `plate`, `mask` (manual, keyframed in/out) | `_segment`, before crop |
| **Motion** | punch-in, snap zoom, slow push, shake (seeded) | `_segment`, crop-window keyframes |
| **Color** | 8 in-house `.cube` presets; exposure, contrast, saturation, temperature, vignette, grain, sharpen | `_segment`, after crop |
| **Graphics** | hook card, title, lower third, CTA/end card, emphasis word, arrow, circle, underline, progress bar, emoji/sticker (bundled set) | graphics pass |
| **Captions** | existing tracks/styles + word-pop, highlight, karaoke (real word timings) | graphics pass |
| **Audio** | original, voice-over, dub, music bed, ducking, per-sentence gain | `_audio_track` / mix |

**Never:**
- inpainting, `delogo`, generative repair, or platform watermark removal;
- stock B-roll, an SFX/template marketplace, or avatars;
- voice cloning;
- local music models;
- 1:1/16:9 output or full-source 4K cleanup.

---

## 4. Render pipeline

```text
_segment(scene)   source → [clean] → crop/reframe(+motion) → scale → [color] → fades   (cached)
_concat_video     unchanged
_burn_layers      captions + text + graphic FX as PNG / PNG-sequence overlays    (one encode, skipped if empty)
_audio_track      AudioPlan → stems → mix → loudnorm                            (§8.5)
_mux              unchanged
```

- **`compose_render.py` (new, pure):** compiles an Edit into per-segment filter strings and an overlay layer list. It makes no ffmpeg calls and is tested with golden strings.
- **`_segment`:** gains `pre_filters` and `post_filters`, and the cache key adds their hashes. Motion is expressed as keyframes in the existing `_path_expression`.
- **`_burn_captions` → `_burn_layers`:**
  - Static layers are single PNGs.
  - Animated layers (pop, type-on, progress bar, arrow draw-on, word-pop) are PNG sequences at the output fps.
  - Rasterized frames are cached by layer hash.
- **Frame endpoint:** `GET /api/jobs/{id}/edits/{edit_id}/frame?t=` runs the same compiled graph on one frame. It is the truth source for exact preview and for the cover JPEG.
- **Proxy:** a 540p proxy per story range for editor scrubbing.

---

## 5. Check (Detect)

Check runs after analysis and before Stories. It is advisory only, and the creator can always override it.

| Signal | Method | Cost, 90-min source on M1 |
|---|---|---|
| Text presence/position | keep Vision OCR boxes; added 0.5 fps sampled pass, fast recognition | ~3–5 min |
| Text tracklets | cluster by position and persistence; refine at 2–4 fps inside chosen story ranges | per story, at edit time |
| Text kind | rules: band + text change rate 1–5 s → `subtitle`; long-lived/large → `title`; small persistent corner → `handle_or_logo`; platform mark pattern → `watermark` | negligible |
| Speech ratio | word-level transcript coverage (§6) | already computed |
| Music presence | energy / spectral flatness in non-speech spans | ~1 min |
| Faces | existing Vision face boxes | already computed |
| Quality | resolution, bitrate, compression, orientation | instant |
| Rights | attestation at import: "I own this footage or have the right to edit it" | — |

`POST/GET /api/jobs/{id}/check` returns a `SourceReport` with:
- tracklets (kind, box, time ranges, confidence);
- audio, faces and quality;
- a recommendation: `clean_then_compose` | `compose` | `music_first`;
- warnings.

| Finding | Clean layer pre-fill |
|---|---|
| Subtitles in the lower band | `plate` under the new captions, or `crop_guard` when the crop avoids them at ≤1.5× upscale |
| Mid-frame burned captions | `blur` + `plate`, with a quality warning |
| Titles / lower thirds | `blur` or `mask` per tracklet |
| Own handle/logo, attested | `crop_guard` / `blur`, off by default, user enables |
| Platform watermark | never; message: "Use your original file — it has no watermark." |
| Rights not attested | Clean layer locked; Compose allowed |

**Policy in code:**
- `cleanup` refuses layers that target a `watermark` tracklet.
- It refuses `handle_or_logo` targets unless the own-footage attestation is present.
- These checks key on the detected kind, not the user label. Tests cover both.

**Plate is the main tool.** Burned-in subtitles almost always sit where the new captions go. A styled plate behind the new captions hides them with no upscale and no smear.

---

## 6. STT plan (transcription)

### 6.1 Purpose

STT feeds:
- story selection;
- captions (word timing);
- word-pop/karaoke styles;
- speech ratio for Check;
- dub/translation input;
- voice-over slot timing.

Caption sync is the visible quality bar, so **word-level timing is required, not optional.**

### 6.2 Engines (final set)

| Order | Engine | Where | Size | Word timing | When used |
|---|---|---|---|---|---|
| 1 | **Apple SpeechAnalyzer** (`SpeechTranscriber`) | on-device, macOS 26 | 0 MB in app (OS language asset) | yes, `.audioTimeRange` per run | default for supported locales |
| 2 | **Whisper large-v3-turbo** (`mlx-whisper`) | on-device, optional **Speech Pack** download | ~1.6 GB | yes, `--word-timestamps True` | locales Apple lacks; user picks "Higher accuracy" |
| 3 | **Deepgram nova-3** | cloud, user key | 0 | yes, plus diarization | opt-in per job; speaker labels |
| 4 | **Groq whisper-large-v3-turbo** | cloud, user key | 0 | yes | opt-in per job; fast cloud fallback |

**Removed:**
- `mlx-community/whisper-small-mlx`, replaced by turbo;
- OpenAI `whisper-1` (duplicates Groq at higher cost);
- the `auto` cloud ladder that silently picks a provider. Cloud is always an explicit choice.

### 6.3 Transcript v2 schema

```text
Transcript
  id, source_hash, engine, model, language, created, hash
  segments[]  start, end, text, speaker?, confidence
  words[]     w, start, end, confidence, segment, speaker?
  quality     coverage, mean_confidence, low_conf_words, drift_ms_p95
```

- The transcript is stored at `jobs/<id>/transcript/transcript_v2.json`.
- It is immutable: a re-run creates a new id.
- Caption tracks record the `transcript_id` they came from.
- Caption cues are built from `words[]`. `captions.py` interpolation becomes a fallback for legacy jobs only.

### 6.4 Pipeline details

1. **Audio prep:** 16 kHz mono, loudness-normalized, cached by source hash.
2. **Language:**
   - The user picks one at import, or "Auto".
   - "Auto" runs language ID on 3 × 20 s samples (Whisper pack if installed; otherwise Apple locale probe).
   - If they disagree, it asks.
3. **Chunking:**
   - 10-minute chunks with 5 s overlap; words in the overlap are de-duplicated by time.
   - Each chunk is cached by `audio_hash + engine + model + chunk index`.
   - A crash resumes at the last finished chunk (G3).
4. **Apple helper:** iterate `result.text.runs` and read each run's `audioTimeRange` to emit `words[]`. Keep segment-level results as `segments[]`.
5. **Whisper:** add `--word-timestamps True`, and keep the existing hallucination filters (compression, no-speech, logprob).
6. **Vocabulary:**
   - a per-job and global list of names/brands;
   - passed to Apple as `contextualStrings` and to Whisper as `initial_prompt`;
   - then a post-pass correction using the same `vision.correct_ocr_text` approach.
7. **Confidence UI:** words below 0.5 confidence are underlined in the caption editor, and "Review 7 unsure words" jumps through them.
8. **Speakers:**
   - Labels exist only when diarization exists (the Deepgram option).
   - Locally, there are no speaker labels and no guessing.
   - Captions can color by speaker when labels exist.
9. **Re-transcribe one story range:** with a different engine, without redoing the whole source.

### 6.5 Acceptance

**English WER:**
- ≤ 8% on a 10-source set with Apple;
- ≤ 6% with the Whisper pack.

**Word timing error:**
- median ≤ 60 ms;
- p95 ≤ 150 ms against hand-marked words on 5 clips.

**90-min source on an M1 with 16 GB:**
- Apple ≤ 10 min;
- Whisper turbo ≤ 25 min.

Network-off transcription works with Apple and the Whisper pack.

---

## 7. TTS plan (voice-over and dub)

### 7.1 Uses

1. **Voice-over:** speak a written or rewritten script over a story.
2. **Dub:** translate the story sentences and speak them in the original sentence slots.
3. **Hook VO:** one spoken hook line over the hook card.

### 7.2 Engines (final set)

| Engine | Where | Size | Languages | Role |
|---|---|---|---|---|
| **MiniMax Speech 2.8 Turbo** | cloud, user key | 0 | multilingual incl. zh/vi | default cloud |
| **ElevenLabs** (multilingual v2 / flash) | cloud, user key | 0 | multilingual | premium English/EU |
| **OpenRouter TTS** (Gemini Flash-Lite TTS, Fish S2.1) | cloud, OpenRouter key | 0 | multilingual | one-key path; free tier |
| **Kokoro v1.0 / v1.1-zh** | on-device, optional **Voice Pack** | ~700 MB | en, zh (+ ja, es, fr, hi, it, pt) | offline quality voice |
| **Apple `say`** (Premium/Enhanced voices) | on-device, built in | 0 in app | OS voices | always-available offline fallback |

**Removed:**
- Piper (lower quality, duplicates Kokoro; 181 MB of voices);
- OpenAI TTS, Groq Orpheus, Deepgram Aura and Cartesia (four extra cloud integrations with overlapping voices, and each adds keys, tests and failure modes).

**Never:** voice cloning, cloned "your voice", avatars.

### 7.3 Behaviour

- **Voice picker:**
  - one list grouped by Offline / Cloud, filtered by the story language;
  - 5-second preview per voice;
  - the catalogue is cached for 24 h.
- **Per-sentence synthesis:** each sentence is a cache unit keyed by `engine + model + voice + text + rate + language`.
- **One voice per story:**
  - If any sentence fails on engine X, the **whole story** falls to the next engine in the ladder.
  - Voices are never mixed mid-story.
  - The UI says which engine was used.
- **Slot fitting (dub and VO-over-sentences):**
  - `atempo` is applied within 0.90–1.15× to fit the source slot.
  - Outside that range, the sentence is flagged "Too long by 1.4 s" with **Shorten** (AI rewrite of the translation) or **Allow overlap**.
- **Levels:** voice is normalized to −16 LUFS before mixing.
- **Dub with background:**
  - Original speech is ducked by default (−18 dB under the dub).
  - "Remove original voice" needs voice/background separation (§8.6).
- **Provenance:** packet `audio.json` records engine, model, voice id, and an `ai_voice: true` flag so the creator can apply platform AI-content labels.

### 7.4 Acceptance

- 20 dubbed sentences: ≥ 90% fit without flag at 0.90–1.15×.
- No mid-story voice change in fault-injection tests.
- Network-off VO works with Kokoro or `say`.
- Re-render with the same text and voice is a cache hit, with an identical audio hash.

---

## 8. Music plan

### 8.1 Sources

| Source | Where | Licence handling |
|---|---|---|
| **Library** | creator's own folder (`~/Library/Application Support/VibeCut/music/`), plus drag-drop upload | creator attests per track: own / licensed / CC (with attribution text) |
| **Upload per job** | existing `audio/music-upload` | same attestation |
| **Cloud generation** | MiniMax Music 3.0 (default), Lyria 3 Clip/Pro via OpenRouter | provider, model, request id, prompt, date, and provider-terms URL stored with the file |

**Removed:**
- all local music models: MusicGen Small, Stable Audio Open Small, Stable Audio 1.0;
- the `cc0` bucket, merged into Library with a CC licence type.

### 8.2 Generation flow

1. **Brief:** built from the story by the AI text route:
   - mood (from transcript tone), energy curve (hook → payoff), genre hint;
   - target BPM range;
   - `instrumental: true` always;
   - duration = story length + 4 s tail.

   The brief is editable as plain fields (Mood, Energy, Genre, Tempo), not as a raw prompt.
2. **Generate 2 candidates** in parallel. Preview both against the story with ducking applied.
3. **Pick, lock or regenerate.** Locked tracks are content-hashed into the Edit, and regenerate keeps history.
4. **Cache:** by `provider + model + brief hash + seed`. A cache hit costs nothing.
5. **"Apply to all stories":** same brief per story, generated per story length.

The cloud features are hidden without a key. Library and upload always work.

### 8.3 Fitting the music to the story

- **Beat grid:** existing `audio.beat_grid`. Trim the start to a downbeat; end on a bar line with a 1.5 s fade.
- **Too short:** loop at bar boundaries with existing `_music_loop`, using a crossfade.
- **Too long:** trim at a bar plus fade.
- **Beat sync (optional):** snap cut points and motion FX (punch-in, shake) to the nearest beat within ±120 ms.

### 8.4 Audio modes per story

| Mode | Original | Voice | Music |
|---|---|---|---|
| Original | on | — | — |
| Original + bed (default when Check finds no music) | on | — | ducked bed |
| Voice-over | ducked or off | TTS | ducked bed |
| Dub | ducked (or removed, §8.6) | TTS | original bed or new bed |
| Music only (no-speech sources) | off | — | full |

### 8.5 Mix

- **Ducking:** sidechain (`sidechaincompress`) keyed on speech/voice; default −12 dB with 150 ms attack and 400 ms release, using the existing `_duck_and_mix`.
- **Gain:** per-sentence music gain is kept (`music_mix_expression`).
- **Loudness:** final `loudnorm` to −14 LUFS integrated, −1.5 dBTP.
- **Packet `music.json`:** source type, file hash, licence/attestation, provider metadata, brief, BPM, and in/out points.

### 8.6 Voice/background separation (dub "remove original voice" only)

- HTDemucs is kept as an **optional Separation Pack** (~800 MB including its runtime). It is not bundled.
- Without it, dub uses ducking only.

### 8.7 Acceptance

- Generated bed fits story length ±0.1 s.
- Music never covers speech: speech-band SNR ≥ 12 dB in ducked spans.
- Every packet with music has a complete `music.json`.
- Network-off: library/upload path renders.

---

## 9. Model and engine removal plan

### 9.1 What ships

| Tier | Contents | Size |
|---|---|---|
| **Built in (app bundle)** | Python runtime, ffmpeg (with §2 filters), Vision/Speech/Translation helpers (Swift), `say` | no model weights |
| **Speech Pack** (optional) | `mlx`, `mlx-whisper`, Whisper large-v3-turbo | ~1.9 GB |
| **Voice Pack** (optional) | `onnxruntime`, `kokoro-onnx`, Kokoro v1.0 + v1.1-zh | ~0.8 GB |
| **Separation Pack** (optional) | `torch` (CPU/MPS), `demucs`, HTDemucs weights | ~0.8 GB |

Packs:
- download from VibeCut's own release host;
- are pinned by SHA-256 and installed under Application Support;
- show their size before download;
- can be removed from Setup.

No pack is needed for the core flow.

### 9.2 AI text routes (rewrite, translate, hook titles, music brief)

| Keep | Remove |
|---|---|
| OpenRouter (user key) | `local-mlx` (`tools/rewrite_mlx.py`, `mlx_lm`) |
| Apple Foundation Models / Apple Translation (on-device, macOS 26) as the offline route | `ollama` (`VIBECUT_LLM_URL`) |
| deterministic `rules` fallback for rewrite | Marian / opus-mt, Argos (dead code since `audio.py:478`) |
| OpenCode Go: **dev-only**, hidden unless `VIBECUT_DEV=1` | — |

### 9.3 Code removal (one PR per row, each with tests)

| Area | Remove | Files |
|---|---|---|
| Local music | MusicGen, Stable Audio, `stable_audio_available`, `musicgen_available`, `cc0` bucket | `audio.py`, `tools/musicgen_generate.py`, `tools/music_generate.py`, `requirements-music.txt`, Setup UI rows |
| TTS | Piper, OpenAI, Groq, Deepgram, Cartesia voices | `audio.py` (`_piper_voice`, `_openai_voice`, `_groq_voice`, `_deepgram_voice`, `_cartesia_voice`, key getters, `engine_status` rows), `workflow_config.TTS_PROVIDERS`, admin model pickers |
| STT | whisper-small default, OpenAI STT, `auto` cloud ladder | `pipeline.py` (`transcribe_cloud`, defaults), `workflow_config.STT_PROVIDERS` |
| Text/translate | `local-mlx`, `ollama`, Marian, Argos | `audio.py` (`translate_providers`, `rewrite_models`), `tools/rewrite_mlx.py`, `workflow_config.TEXT_PROVIDERS` |
| Settings | migration: removed engines map to the nearest kept engine (piper → kokoro → say; openai/groq/deepgram/cartesia TTS → minimax; whisper-small → turbo pack or apple). Stale keys are deleted from `secrets.json` after the user confirms in Setup | `settings_store.py`, `admin/store.py` |
| Tests/docs | update `tests/test_vibecut.py` (44 refs), `test_workflow_routes.py`, `test_admin.py`; README engine tables | tests, README |

Removed engines must also disappear from:
- the admin console (`/_ductator/`) provider dropdowns;
- `/api/audio/engines`;
- the masked-key list.

### 9.4 Local cleanup on the dev Mac

These are measured on 2026-10-27 and are re-downloadable. Delete them only after the code removal lands. Each is listed for explicit confirmation before deletion.

| Path | Size | Action |
|---|---|---|
| `~/.cache/huggingface/hub/models--facebook--musicgen-small` | 4.4 GB | delete |
| `~/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx` | 918 MB | delete after turbo pack works |
| `data/voices/piper` | 181 MB | delete |
| `~/.cache/huggingface/hub/models--Helsinki-NLP--opus-mt-zh-vi` | 12 KB | delete |
| `assets/music/generated` | 1 MB | delete (dev outputs) |
| `~/.cache/huggingface/hub/models--adefossez--HTDemucs` | 160 MB | keep → becomes Separation Pack source |
| `data/models/kokoro` | 699 MB | keep → becomes Voice Pack source |
| Homebrew Python 3.11 packages (`torch` 587 MB, `transformers`, `stable-audio-tools`, `piper`) | ~0.9 GB | **check other projects first**: they are global, not a VibeCut venv. Remove only `stable-audio-tools` and `piper-tts` after confirming |

---

## 10. Studio UI

The app shell has a left rail with five steps: **Import · Check · Stories · Edit · Finish**. Classic UI stays reachable from Settings → "Use Classic editor" (decision 2).

```text
┌ stories ┐┌──────── preview (9:16 / 4:5) ─────────┐┌ inspector ┐
│ S1 ✓    ││ live canvas + safe zones              ││ selected  │
│ S2      ││ old-text boxes toggle (Clean)         ││ layer     │
└─────────┘└───────────────────────────────────────┘└───────────┘
 ┌ timeline ───────────────────────────────────────────────────┐
 │ Video    ▇▇▇▇|▇▇▇▇▇|▇▇▇   sentences: trim / reorder / exclude │
 │ Clean    ░░░░░░░░░░░       tracklets, per-range on/off       │
 │ Text     [HOOK]   [lower third]      [CTA]                  │
 │ Captions ▫▫▫▫▫▫▫▫▫▫▫▫      unsure words underlined           │
 │ Effects     ⊕punch  ↗arrow   ⊕shake (beat-snapped)          │
 │ Color    [Warm Film]                                        │
 │ Audio    original ~~ voice ~~ music ≈≈ (duck)               │
 └─────────────────────────────────────────────────────────────┘
```

- **Plain language.** No "v1/v2", "plan", "flow", "artifact" or "matrix" in the primary UI.
- **"Apply to all stories"** covers caption style, text style, color preset, music brief and voice.
- **Inline preflight:** collision, face overlap, safe zone, residual old text, caption density, loudness, voice-fit flags and missing music licence appear as timeline markers.
- **Code:**
  - `static/studio/` uses native ES modules with no build step.
  - Each panel is its own file: `shell.js`, `import.js`, `check.js`, `stories.js`, `edit/preview.js`, `edit/timeline.js`, `edit/layers/{clean,text,captions,effects,color,audio}.js`, `finish.js`, `setup.js` (engines and packs), `api.js`, `studio.css`.
  - `app.js` and `creator.js` are frozen except for fallback bug fixes.

---

## 11. Modules and file ownership

| Module | Status | Track |
|---|---|---|
| `edits.py`, `routes_edits.py`, `compose_render.py`; `render.py` (only owner) | new / change | **A — Core** |
| `detect.py`, `routes_check.py`; `pipeline.py` OCR boxes + sampled pass (only owner of `pipeline.py` except STT functions) | new / change | **B — Check** |
| `cleanup.py` (tracklet → Clean layer, kind policy, residual-OCR report) | change | **C — Clean** |
| `overlays.py` → text layers; `fx.py`; `color.py` + `assets/luts/`; sticker set | change / new | **D — Compose** |
| `stt.py` (new; moves transcription out of `pipeline.py`), `tools/transcribe_apple.swift` | new / change | **E1 — STT** |
| `tts.py` (new; moves voices out of `audio.py`) | new | **E2 — TTS** |
| `music.py` (new; moves music out of `audio.py`), mixer stays in `audio.py` | new / change | **E3 — Music & mix** (owner of `audio.py`) |
| `packs.py` (download, verify, install, remove), engine removal PRs (§9.3), settings migration | new / change | **F — Engines & packs** |
| `packet.py`, `artifacts.py`, `preflight.py` | change | **G — Finish** |
| `static/studio/**` (one owner for `shell.js` + `index.html`; panel owners per file) | new | **H — Studio UI** |
| `.app` bundle, signing, launchd, diagnostics, pack hosting | new `packaging/` | **I — Mac** (from day 0) |
| `app.py` include lines; merges | — | principal |

Splitting `audio.py` (4,863 lines) into `stt.py`, `tts.py` and `music.py` is what lets E1, E2 and E3 work in parallel. E3 does the split first, in M0, as a pure move with no behavior change and all tests green.

---

## 12. Milestones

| # | Name | Length | Tracks | Exit |
|---|---|---|---|---|
| **M0** | Contracts + split | 1 week | A, B, E3, F, H, QA | Schemas: `Edit`, `SourceReport`, `Transcript v2`, `AudioPlan`, pack manifest. `audio.py` split (pure move). Studio screen map. Fixture corpora (§13). Engine removal PRs for dead code (Marian/Argos/Ollama/local-mlx). |
| **M1** | Engine | 2 weeks | A, B, E1, E2, E3, F, I | One Edit with color + text + motion + plate renders through the existing pipeline. Frame endpoint SSIM ≥ 0.98 vs final. OCR boxes kept; tracklets on 10 fixtures. Word timings from Apple + Whisper. TTS/music removals landed with settings migration. Packs install/verify/remove. |
| **M2** | Flow 2 slice | 2 weeks | A, D, E1–E3, G, H | Studio shell + Stories + Edit (Text, Captions with word-pop, Color, Audio). Clean 90-min source → 3–6 stories → hook, captions, 1 FX, 1 preset, generated music (2 candidates, lock), VO → 9:16 + 4:5 → packet → reload, same bytes. |
| **M3** | Flow 1 slice + full FX + dub | 2 weeks | B, C, D, E2, H | Check screen live. Baked-caption source → plate/blur/crop_guard → new captions → render; residual-OCR report. Full effects set, beat-snapped. Dub with slot fitting and Shorten. |
| **M4** | Finish | 1 week | G, H | Packet v2 (`edit.json`, `audio.json`, `music.json`, layer assets, cover from frame endpoint). Versions/review links show Edit version. Inline preflight. Apply to all. Setup screen for engines and packs. |
| **M5** | Hardening | 2 weeks | all | M1/16GB perf budget. Old-job migration (a caption track becomes an Edit with captions only). Classic UI behind setting. Signed/notarized `.app` on a clean Mac; packs download on a clean Mac. Diagnostics, rollback build. Dev-Mac cleanup (§9.4) after confirmation. |
| **M6** | Product proof | 3–4 weeks | founder, QA | 10 creators (≥4 with baked-text sources), every §13 gate. Done = product complete. |

**Total:** about 13–15 weeks to product proof. Track I runs from day 0. **Feature freeze at M5 start.**

---

## 13. Acceptance

**Check:**
- **Corpus:** 30 sources: 12 baked text, 10 clean, 5 mixed, 3 music-only.
- **Zero false "clean"** on any of the 17 sources with visible text.
- **At most 1 false "needs cleaning"** across the 10 clean sources.
- **Kind accuracy:** subtitle vs title ≥ 90%.
- **Platform watermarks:** 100% refused.
- **Speed:** ≤ 6 min extra on 90 min.

**Flow 2:**
- 20-story visual pass by 3 editors.
- Zero unwarned text over faces or in the platform UI zone.
- Captions within ±80 ms of speech after edits.
- Same Edit gives the same artifact identity.
- Packet reload is byte-identical.

**Flow 1:**
- **Sample:** 60 clips / 12 sources.
- **Zero P0s:** no face/logo smear, no visible old-caption ghost at 1×, no new captions over old ones.
- **Residual old-text OCR:** ≤ 0.5% of sampled frames.
- **Review time:** ≤ 5 min static / ≤ 10 min moving.
- **Below the gate:** Flow 1 is labelled "Beta" in-app.

**STT / TTS / Music:** §6.5, §7.4, §8.7.

**Stories (unchanged from PRD):**
- 20 sources.
- Floor 3 postable (2 for 20–29 min).
- Mean ≥ 4/6.
- Within 0.5 of OpusClip.

**Performance (M1 Mac, 16 GB):**
- Analysis + Check + Apple STT on 90 min ≤ 35 min.
- Story render ≤ 2× duration with all layers.
- Editor actions < 100 ms.
- Frame preview ≤ 1.5 s.

**Trust:**
- G1–G5 unchanged.
- G2 lineage extends to `edit.hash`, `transcript_id` and audio/music hashes.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Preview and export differ | Frame endpoint runs the compiled graph; SSIM test in CI |
| Render time grows with layers | Clean/color/motion in the cached segment pass; one graphics encode; skip when empty |
| Cleanup looks bad on mid-frame text | Plate-first; quality report; "Beta" until the 60-clip gate passes |
| Detect misses text | Conservative thresholds; zero false-clean gate; manual boxes always available |
| Editor becomes an NLE | Fixed layer catalogue; sentence-level timeline; in/out easing only |
| Cleaning others' footage | Attestation gate; watermark refused by kind; logo/handle needs own-footage attestation |
| Apple STT locale gaps | Whisper Speech Pack; per-story re-transcribe |
| Cloud music/voice provider changes terms or API | Two music providers, three cloud TTS; provider metadata saved per file; library/upload/offline voices always work |
| macOS 26 minimum excludes older Macs | Stated up front; required for on-device STT/translation |
| Removing engines breaks saved settings | Migration with mapping table and tests; Classic UI keeps working |
| `audio.py` split causes regressions | Pure move first (M0), full suite green before any behaviour change |
| Parallel tracks conflict | One owner per shared file; ES-module UI; principal owns `app.py` |
