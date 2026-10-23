# VibeCut

Self-hosted long-video → short-reel cutter. Drop a minutes- or hours-long video; VibeCut finds the hook, the beats and the crop, then cuts a 15, 30 or 60 second reel while keeping the original footage, audio and pacing.

Everything runs on this machine. No account, no cloud upload, no watermark.

**v0.6.0** · version history and checklist: [ROADMAP.md](ROADMAP.md).

## Run

```bash
cd vibecut
./run.sh
```

Open <http://127.0.0.1:8787>.

Requirements:

- `ffmpeg` / `ffprobe` on `PATH`
- Python 3.10+
- Python packages in `requirements.txt`
- macOS: `swiftc` (Xcode Command Line Tools) for Apple Vision text + face + saliency reading. Without it, crops fall back to center and on-screen text is skipped.
- Optional: `mlx_whisper` for local speech transcription. Without it, the speech toggle is disabled.

The Swift helper is compiled automatically on first use into `bin/vision_probe`.

## What it does

1. **Scan** — one ffmpeg pass detects scene cuts at low resolution, plus motion, brightness and onset signals.
2. **Shortlist** — every beat gets a cheap score. Short videos are read in full. Long videos keep the strongest beats, the payoff zone, long takes and even timeline coverage, up to `VIBECUT_DEEP_SCENES` (default 300) beats.
3. **Read** — the shortlist gets one still each; Apple Vision reads on-screen text, faces and attention saliency. Audio energy and onset density come from a mono 16 kHz track.
4. **Score** — visual sharpness, motion, audio, on-screen text, speech and subject presence are ranked. Black and frozen beats are tagged and pushed out of plans. The hook is the beat that stands alone best.
5. **Plan** — three cut plans (15s / 30s / 60s) share the same hook. Body beats stay in source order, a payoff beat lands at the end, and a spacing rule keeps the cut from clustering.
6. **Render** — each beat is cut as its own segment in parallel, then joined frame-accurately. A per-clip audio bed is muxed in, loudness-normalized to −14 LUFS, and written to `data/jobs/<id>/renders/`.

Portrait sources are left native. Landscape and square sources get a crop centered on the strongest face or salient object. The crop is per beat, not per frame, so shots stay stable.

## UI notes

- Choose a file, or expand **Use a local path instead** to analyze a huge file in place without copying it.
- **Smart crop** uses Vision subject tracking; turn it off for a center crop.
- **Read text & faces** adds OCR to hook scoring. It is separate from smart crop.
- **Transcribe speech** is off by default for videos over 15 minutes because local Whisper adds real time. Short clips default on.
- After analysis, pick 15 / 30 / 60, preview the cut timeline, render, download.
- **Draft** renders 540×960 fast for feel checks; **Render final** does 1080×1920. **All 15/30/60** queues every length.
- **Aspect** switches between 9:16, 4:5, 1:1 and 16:9. **Captions** burns OCR/speech text as styled overlays.
- **Edit cut** lets you reorder, trim and remove beats. **Save variant** stores that edit; variant chips reload or delete it.
- **Audio** panel: keep the original sound, replace the voice, dub over the original bed (Demucs), fully replace voice + music, or add music only. Pick the voice engine, target language, **script style** (faithful / smooth / viral), music source and mood; **Test voice** plays a sample.
- **Voice script** preview lists the deduped lines with role, emotion and fit flags. Show the literal translation, edit any line (only that line re-renders), or switch style and the script is rewritten for the slot using the **full transcript** as context (the whole story, then one complete sentence per selected beat), with connectors, a tightened hook and a payoff CTA. Numbers are validated so a rewrite cannot invent facts.
- **Per-clip mixer** below the script: voice and music dB per beat. **Beat sync** detects the bed BPM, snaps cuts to the grid (max 250 ms shift) and starts the loop on a beat.
- **Platform presets** (TikTok, Reels, Shorts, Square, Landscape) set aspect, captions and safe-zone caption margin. **A/B hooks** queues the three strongest hooks at once. **Story arc order** reorders beats as setup → proof → payoff.
- Music sources: your own track, CC0 library, Stable Audio Open Small or 1.0 with auto mood from the beats.
- Voice engines: Apple `say` (built in), Piper medium, Kokoro int8, ElevenLabs with your API key.
- Translation runs per render: Apple Translation framework, Ollama, or the offline Argos package. If no engine is ready, the panel offers **Offline translate setup (~250 MB)**.
- **Hook lab** lists the strongest opening candidates with their resulting cut length and a plain-language reason; click one to re-plan.
- Hover any timeline clip for the same **why** note; the drawer repeats it per beat. The hook panel explains why that beat is the opening, and the plan line explains the payoff.
- **CC · transcript** appears when Whisper ran; open it for timestamped lines with search, click a line to copy it.
- Click any scene to inspect scores, OCR, speech and crop, then **Use as hook** to re-plan.
- Long-video scenes outside the shortlist are read on demand when you click them.
- Renders are cached per plan + quality + aspect + captions + audio mix; an overridden hook gets its own slot. **Render again** forces a fresh encode. Cancel stops a running render.
- **SRT / VTT / EDL / XML** buttons export the caption file or the cut list for Resolve and Premiere.
- Speech: `transcribe_engine` is `auto` by default, which tries the on-device Apple SpeechAnalyzer (macOS 26, 0 MB) and falls back to mlx-whisper. Pick the speech language next to the toggle.

## CLI

```bash
python3 cli.py analyze clip.mp4
python3 cli.py render clip.mp4 --target 30 --captions
python3 cli.py render --job 0c354657dc1a --target 15 --quality draft
python3 cli.py batch ./footage --out ./reels --targets 15 30
python3 cli.py watch ./inbox --out ./reels
python3 cli.py jobs
python3 cli.py clean --all                 # delete work files, source stays
python3 cli.py clean --job <id> --profile renders
python3 cli.py sources [--gc]              # content-addressed source store
python3 cli.py audit                       # what is installed and how big
```

`render` reuses the newest analyzed job for a file when one exists. `--target` can be repeated. `--encoder auto|videotoolbox|libx264` overrides the default. Audio replacement: `--audio-mode keep|full|bed|voice|music`, `--translate <lang>`, `--translate-provider auto|apple_fm|argos|marian|ollama`, `--voice-engine`, `--voice`, `--music`.

Optional local LLM hook ranking: point `VIBECUT_LLM_URL` at an Ollama `/api/generate` endpoint and set `VIBECUT_LLM_MODEL` (default `llama3.1`). Hook lab reorders candidates when the model answers; any failure falls back to the deterministic score.

## Docker

```bash
docker compose up --build
```

The container uses `libx264` and DejaVu fonts, mounts `./data`, and serves on port 8787. Apple Vision and MLX Whisper are macOS-only, so the container falls back to center crop and no speech.

## Long videos

- Scene scan decodes at reduced analysis fps: 8 fps under 20 min, 6 fps under 1 h, 4 fps beyond.
- Beats are capped at roughly 1,400–2,000 moments. Long static stretches are split at 6–20 s depending on source length.
- Deep-read defaults to 300 beats; everything else is read lazily on click.
- Upload limit is 20 GB by default. Local-path mode avoids the copy entirely.
- A 60s plan can land slightly under 60s when the source has too few unique beats. The UI reports the planned length before rendering.
- Interrupted jobs and renders are marked failed on restart; completed analysis and renders stay on disk.

## Audio replacement

The render panel can rebuild the audio track:

| Mode | What happens |
|---|---|
| Keep original | Nothing changes (default) |
| Full replace | Original audio is dropped. New voice + new music. No Demucs needed |
| Dub over original bed | Demucs removes the original voice, the instrumental bed stays, the new voice is dubbed over it |
| Voice only | Original voice replaced, no new music |
| Music only | Original audio dropped, only the new music bed |

Voice engines: Apple `say` (0 MB, built in), Piper medium (~170 MB), Kokoro int8
(~220 MB), ElevenLabs (set `VIBECUT_ELEVENLABS_API_KEY`).

Music sources: your own folder `assets/music/library`, CC0 folder
`assets/music/cc0`, Stable Audio Open Small (~2 GB) or Stable Audio Open 1.0
(~6 GB). Both AI sources use an auto mood prompt built from the cut's beats.

Translation happens once per render, on the cleaned and de-duplicated lines.
Provider order is automatic: whatever is already working first (Argos offline
pair, Apple Translation language pack, Marian/opus-mt, Ollama), then the ones
that need a first-use download. The panel shows which engine will run and can
force one. Translations are cached per job in
`data/jobs/<id>/audio/translation.<lang>.json`.

Voice script: Whisper repeats the same sentence on overlapping beats, so the
script builder strips fillers and stage directions, drops near-duplicates,
prefers speech over on-screen text, cuts each line to the room the beat has,
and tags a small emotion (energetic / calm / warm / punchy) that changes the
speaking rate. Lines are fit into their slot with up to 1.35× tempo plus a
trim, so they never overlap the next line. Preview the result under **Voice
script** in the audio panel.

Voice lines are cached in `data/cache/voice`, Demucs stems in
`data/cache/stems`, generated music in `data/cache/music` and kept for reuse in
`assets/music/generated`. Render files carry an audio signature and hook suffix
so different mixes and hooks never overwrite each other. With
`VIBECUT_AUDIO_LICENSE=strict`, every music asset must ship a
`.license.json` sidecar; used assets are recorded on the render.

Full design notes and the free/paid tool list: [`docs/audio-replacement.md`](docs/audio-replacement.md).

## Storage

- Video masters are cached per `(plan, quality, aspect, captions)` in
  `data/cache/masters`. Every extra language or voice mix only muxes a small
  audio track onto the same master, so a second language costs ~2 s and a few MB.
- Voice lines are cached as mono 32 kHz FLAC, Demucs stems as 48 kHz FLAC.
- Thumbnails are 360 px, and the scene scan drops to 5 fps between 15 and 40
  minutes, 4 fps beyond.
- Caches are age-pruned and LRU-capped (`VIBECUT_CACHE_MAX_GB`, default 2 GB).
- Renders keep the newest final per mix; drafts go once a final exists.
- **Clean** in the job header removes work files (thumbs, transcript, audio) or
  renders, keeping `source` and `job.json`. `python3 cli.py audit` prints every
  installed engine, model and cache with its size and removal hint.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VIBECUT_HOST` | `127.0.0.1` | Bind address |
| `VIBECUT_PORT` | `8787` | Port |
| `VIBECUT_DATA` | `./data` | Job data directory |
| `VIBECUT_MAX_UPLOAD_GB` | `20` | Upload ceiling |
| `VIBECUT_DEEP_SCENES` | `300` | Deep-read shortlist size |
| `VIBECUT_ENCODER` | `auto` | `auto`, `videotoolbox` or `libx264` |
| `VIBECUT_RENDER_WORKERS` | `4` | Parallel segment workers |
| `VIBECUT_CAPTION_FONT_FILE` | system font | Caption TTF/TTC |
| `VIBECUT_RETENTION_DAYS` | `0` (keep) | Delete jobs older than this |
| `VIBECUT_CACHE_DAYS` | `14` | Prune caches older than this |
| `VIBECUT_CACHE_MAX_GB` | `2` | LRU cap across all caches |
| `VIBECUT_JOB_CLEAN_DAYS` | `0` (off) | Auto-delete job work files after this |
| `VIBECUT_KEEP_RENDERS` | `1` | Newest finals kept per target/aspect/captions/mix |
| `VIBECUT_KEEP_DRAFTS` | `0` | Keep drafts once a final exists |
| `VIBECUT_SOURCES_GC_DAYS` | `30` | Source store GC age for unreferenced uploads |
| `VIBECUT_AUDIO_LICENSE` | `normal` | `strict` blocks music/voice without license metadata |
| `VIBECUT_TOKEN` | unset | Require this bearer token for the API |
| `VIBECUT_ELEVENLABS_API_KEY` | unset | ElevenLabs voice over |
| `VIBECUT_LLM_URL` | unset | Optional Ollama endpoint for hook ranking |
| `VIBECUT_LLM_MODEL` | `llama3.1` | Optional local LLM model |
| `VIBECUT_WHISPER_MODEL` | `mlx-community/whisper-small-mlx` | MLX Whisper model |

When `VIBECUT_TOKEN` is set, the UI asks for it once and stores it in `localStorage`. Media and thumbnail URLs carry `?token=` so the video player keeps working.

## Files

```
app.py                  FastAPI routes, job store, queues, retention, auth
pipeline.py             probe, scan, shortlist, stills, features, scoring, plans
render.py               parallel segments, cache, audio bed, concat, captions
audio.py                voice engines, translation, Demucs stems, music, mix
vision.py               compiles/runs the Swift frame reader
cli.py                  analyze / render / batch / watch
tools/vision_probe.swift  OCR + face + saliency
tools/translate_apple.swift  on-device Apple translation helper
tools/tts_kokoro.py     Kokoro ONNX voice worker
tools/music_generate.py Stable Audio music worker
assets/music/           library + cc0 track folders
static/                 plain HTML/CSS/JS UI
tests/                  fast unit tests (no ffmpeg)
data/jobs/<id>/         job.json, source, thumbs, transcript, audio, renders
exports.py              SRT, VTT, EDL and FCP7 XML cut exports
tools/transcribe_apple.swift  on-device SpeechAnalyzer transcription (macOS 26)
data/sources/<hash>/    content-addressed uploads, hardlinked into jobs
assets/music/generated/ AI beds kept as reusable library tracks
data/cache/segments/    content-addressed segment cache
data/cache/beats/       BPM and beat grids per track
data/cache/rewrite/     rewrite memo per line, style and provider
data/cache/voice/       cached voice lines
data/cache/stems/       cached Demucs instrumental beds
data/cache/music/       cached AI music beds
```

## Limits

- Hook selection is local heuristics plus optional local LLM reranking. It does not understand irony or brand safety.
- The crop is per beat. A subject that walks across a long take may drift out of the crop; split the source or edit the cut.
- Captions come from OCR and speech. If the source already burns in subtitles, turn captions off to avoid doubles.
- No music generation, no synthetic voice, no transitions. The original audio and pacing are the vibe.
- The server is localhost-first. `VIBECUT_TOKEN` is a simple shared secret, not multi-user auth; put a reverse proxy in front for network use.
