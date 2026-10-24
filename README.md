# VibeCut

Self-hosted long-video → short-reel cutter. Drop a minutes- or hours-long video; VibeCut finds the hook, the beats and the crop, then cuts a 15, 30 or 60 second reel while keeping the original footage, audio and pacing.

Everything runs on this machine by default. No account, no cloud upload, no watermark. Cloud keys are optional and off until you add one.

**v0.11.0** · version history and checklist: [ROADMAP.md](ROADMAP.md).

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
- Optional: `mlx_whisper` for local speech transcription. Apple Speech is built in on macOS 26.
- Optional: **OpenCode Go** for DeepSeek V4.1 Flash intelligence. Use a project API key in Setup, or sign in with the OpenCode CLI. Cloud is off by default.

The Swift helper is compiled automatically on first use into `bin/vision_probe`.

## What it does

1. **Scan** — one ffmpeg pass detects scene cuts at low resolution, plus motion, brightness and onset signals.
2. **Shortlist** — every beat gets a cheap score. Short videos are read in full. Long videos keep the strongest beats, the payoff zone, long takes and even timeline coverage, up to `VIBECUT_DEEP_SCENES` (default 300) beats.
3. **Read** — the shortlist gets one still each; Apple Vision reads on-screen text, faces and attention saliency. Audio energy and onset density come from a mono 16 kHz track.
4. **Score** — visual sharpness, motion, audio, on-screen text, speech and subject presence are ranked. Black and frozen beats are tagged and pushed out of plans. The hook is the beat that stands alone best.
5. **Plan** — three cut plans (15s / 30s / 60s) share the same hook. Body beats stay in source order, a payoff beat lands at the end, and a spacing rule keeps the cut from clustering.
6. **Render** — each beat is cut as its own segment in parallel, then joined frame-accurately. A per-clip audio bed is muxed in, loudness-normalized to −14 LUFS, and written to `data/jobs/<id>/renders/`.

**Smart crop is bilateral.** Every beat stores an attention crop for 9:16, 4:5, 1:1 and 16:9. A portrait source cropped to 16:9 follows the subject on the vertical axis; a landscape source cropped to 9:16 follows it on the horizontal axis. Switching aspect is a true reframe with no re-analysis, and the crop stays per beat so shots remain stable.

## UI notes

- Choose a file, or expand **Use a local path instead** to analyze a huge file in place without copying it.
- **Smart crop** uses Vision subject tracking; turn it off for a center crop.
- **Read text & faces** adds OCR to hook scoring. It is separate from smart crop.
- **Transcribe speech** is off by default for videos over 15 minutes because local Whisper adds real time. Short clips default on.
- After analysis, pick 15 / 30 / 60, preview the cut timeline, render, download.
- **Draft** renders 540×960 fast for feel checks; **Render final** does 1080×1920. **All 15/30/60** queues every length.
- **Aspect** switches between 9:16, 4:5, 1:1 and 16:9. Each aspect uses its own attention crop, so landscape→portrait and portrait→landscape both reframe without re-analysis. **Track crop** samples two extra frames per beat and smooths a per-aspect crop path; renders follow it per frame. **Captions** burns OCR/speech text as styled overlays.
- **Moments** sits above **Smart Cut**: compact horizontal thumbnails, scrub slider, orange auto-hook, neon-green payoff, used-clip check badges. Click previews, drag into Smart Cut, **Expand** for the full collage.
- **Smart Cut** replaces Build. Drag clips to reorder, drag an edge to trim, drag out to remove, drop a moment to add. Hook stays first; payoff stays last. Advanced (aspect, captions, arc, A/B, variants, render-all) is collapsed under one row; Render + Draft stay primary.
- **Audio modes** are tabs: **Original · Voice-over · Dub · Music · Full Replace**. **Voice-over** puts a new voice over the original audio; **Dub** replaces only the original voice and keeps the music/SFX; **Music** replaces the original audio; **Full Replace** uses a new voice plus new music.
- **Audio panel** is three steps: **1 Rewrite · 2 Voice · 3 Music**. Rewrite runs only when you press **▶ Rewrite**; it translates the full script, then rewrites the cut. If translation is on, every line shows original + translation; copy buttons copy either script. Translation engine and rewrite worker stay internal. Styles: smooth, viral, fun, creative, sad, chill, faithful.
- **Use my recording** appears only in Voice-over, Dub and Full Replace; it hides translation/voice controls and fits the recording to the cut. **Use my sound** accepts your own music file; **Generate** uses MiniMax Music or OpenRouter Lyria 3.
- **Edit cut** lets you reorder, trim and remove beats. **Save variant** stores that edit; variant chips reload or delete it. Keyboard: `←/→` select, `Alt+←/→` reorder, `−/+` trim, `Del` remove, `e` edit, `s` save, `r` draft, `Space` play.
- **Automation mixer** above the audio controls: time ruler with one section per clip, a music lane and a voice lane. The lane starts at 100% (0 dB); click to add a node, drag it anywhere in time or gain, double-click to remove, **Reset 100%** clears, **Flatten** puts every node back at 100%. The curve is cosine, so nodes are smooth peaks, and the same curve runs in ffmpeg. The original audio plus the Demucs music stem are drawn behind the lanes so a sudden loud, mute or dip is visible. **Beat sync** detects the bed BPM, snaps cuts to the grid (max 250 ms shift) and starts the loop on a beat.
- **Platform presets** (TikTok, Reels, Shorts, Square, Landscape) set aspect, captions and safe-zone caption margin. **A/B hooks** queues the three strongest hooks at once. **Story arc order** reorders beats as setup → proof → payoff.
- Music sources: your own upload, library/CC0, **MiniMax Music**, or **OpenRouter Lyria 3**. Stable Audio/MusicGen remain advanced legacy options.
- Voice engines: Apple `say`, Piper, Kokoro local; **MiniMax Speech 2.8 Turbo** → **OpenRouter Fish S2.1 Pro Free** → **OpenRouter Gemini 3.8 Flash-Lite TTS**. Setup only exposes these plus local.
- Translation is a **Setup mode**, not a visible engine: **Auto** (online → local), **Local first** (Apple → Argos → online), **Local only**, **Online only**. Online is OpenCode → OpenRouter; local is Apple → Argos. Apple batches are split and retried.
- **Hook lab** lists the strongest opening candidates with their resulting cut length and a plain-language reason; click one to re-plan.
- Hover any timeline clip for the same **why** note; the drawer repeats it per beat. The hook panel explains why that beat is the opening, and the plan line explains the payoff.
- **CC · transcript** appears when Whisper ran; open it for timestamped lines with search, click a line to copy it.
- Click any scene to inspect scores, OCR, speech and crop, then **Use as hook** to re-plan.
- Long-video scenes outside the shortlist are read on demand when you click them.
- Renders are cached per plan + quality + aspect + captions + audio mix; an overridden hook gets its own slot. **Render again** forces a fresh encode. Cancel stops a running render.
- **SRT / VTT / EDL / XML** buttons export the caption file or the cut list for Resolve and Premiere. **Review link** copies a read-only page with the rendered video and SRT.
- **Rewrite model** is internal: OpenCode Go DeepSeek V4.1 Flash → OpenRouter DeepSeek → local MLX/Ollama → rules. The Rewrite button is the only trigger.
- Speech is local: **Apple SpeechAnalyzer (macOS 26) → mlx-whisper**. Pick the local provider and Whisper model in Setup; no cloud STT key exists.
- **Usage** under the result title sums tokens, STT minutes, TTS characters and estimated cost per job. **Live STT** and **Live TTS** exercise local engines with a sample clip.
- **History** stores every translation, rewrite, render and upload attempt: provider, model, status, latency, cost, warning/error and script snapshot. Restore a script as overrides on the current cut, copy original/final text, or re-download a render. Failed attempts stay visible.

## Setup · optional cloud

Click **Setup** in the top bar. Nothing leaves the machine until a key is saved.
Keys live in `data/secrets.json` (0600). OpenRouter project keys override the environment; other providers use env first.

| Section | What you can set |
|---|---|
| Intelligence | OpenCode Go default. OpenRouter DeepSeek fallback. Translation mode (Auto / Local first / Local only / Online only), rewrite/story brief toggles. |
| Transcription | Local only: Auto / Apple / Whisper, spoken language, Whisper model. No cloud STT keys. |
| Voice over | MiniMax Speech 2.8 Turbo, OpenRouter Fish/Gemini fallback, local Kokoro/Piper/say. Live TTS test. |

Buttons **Test OpenCode**, **Check local STT**, **Live STT**, **Check TTS**, **Live TTS** show what is ready. Live tests generate a local sample, call the local/cloud engine, and show the transcript or play the audio.
Costs, model choices and the fallback ladder: [docs/cloud-speech.md](docs/cloud-speech.md).

Environment keys:

```
OPENCODE_GO_API_KEY   OPENROUTER_API_KEY   MINIMAX_API_KEY
```

The API never returns a speech key; it only reports whether one is configured
and whether it came from the environment or the local file. Environment keys
win, so a key seen by the server is shown read-only in Setup.

OpenCode Go can use a **project API key** entered in Setup. It is written only
to this project's `data/secrets.json` (0600, gitignored) and is never returned
by the API. When a key is configured, VibeCut uses the direct OpenCode Go
endpoint exclusively and does not borrow the shared local login.

Alternatively, leave the key blank. VibeCut can use the local OpenCode login.
Install the OpenCode CLI, run `opencode auth login`, connect **OpenCode Go**,
then check:

```bash
opencode models | grep opencode-go/deepseek-v4.1-flash
```

VibeCut calls the local OpenCode service, creates a short-lived session pinned
to `deepseek-v4.1-flash` with the `low` variant, generates the text, and deletes
the session. If OpenCode is missing or not signed in, rewrite falls back to
local MLX / Ollama / rules.

The first rewrite of a job can take tens of seconds because the model reads the
full transcript and reasons at the `low` level. The result is cached per line
and context; later renders are instant.

Translation is enabled by default. If you see **No translation provider
worked**, open **Setup → Intelligence**, check **Translation**, or pick
**OpenCode Go** in the audio panel's **Translate engine** list.

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

`render` reuses the newest analyzed job for a file when one exists. `--target` can be repeated. `--encoder auto|videotoolbox|libx264` overrides the default. Audio replacement: `--audio-mode keep|full|bed|voice|music`, `--translate <lang>`, `--translate-provider auto|opencode|apple_fm|argos|marian|ollama`, `--voice-engine`, `--voice`, `--music`.

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
| Original | Nothing changes (default) |
| Voice-over | New voice over the original audio; original voice is ducked underneath |
| Dub | Demucs removes the original voice; music/SFX stay; new voice replaces it |
| Music | Original audio removed; new music only |
| Full Replace | New voice + new music; original audio removed |

**Use my recording** appears in Voice-over, Dub and Full Replace. It hides
translation and voice-engine controls and fits the uploaded recording to the
cut length. It is not voice cloning. **Use my sound** accepts your own music
file; it is looped/trimmed to the cut.

Voice engines: MiniMax Speech 2.8 Turbo → OpenRouter Fish S2.1 Pro Free →
OpenRouter Gemini 3.8 Flash-Lite TTS; local Kokoro/Piper/say.

Music sources: your own upload, library/CC0, MiniMax Music, OpenRouter Lyria 3,
or advanced legacy Stable Audio/MusicGen. AI sources use an auto mood prompt
built from the cut.

Stable Audio/MusicGen remain in the code as advanced legacy options but are
not shown in the normal music picker. The normal AI path is MiniMax Music →
OpenRouter Lyria 3.

Translation runs only from **▶ Rewrite**, on the full transcript and then the
cut lines. Setup chooses the mode: **Auto** (online → local), **Local first**
(Apple → Argos → online), **Local only**, **Online only**. Online is OpenCode →
OpenRouter; local is Apple → Argos. Apple batches are split and retried.
Translations are cached in `data/cache/translate`, keyed by provider.

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
| `VIBECUT_MLX_REWRITE_MODEL` | `mlx-community/Qwen2.5-3B-Instruct-4bit` | MLX rewrite model |
| `VIBECUT_LLM_MODEL` | `qwen2.5:3b` | Ollama rewrite model |
| `VIBECUT_REWRITE_CONTEXT_CHARS` | `6000` | Transcript context cap |
| `VIBECUT_AUDIO_LICENSE` | `normal` | `strict` blocks music/voice without license metadata |
| `VIBECUT_TOKEN` | unset | Require this bearer token for the API |
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
data/cache/rewrite/     rewrite memo per line, style and context
data/cache/brief/       story brief per transcript and model
data/cache/waveforms/   RMS envelopes for the mixer lanes
tools/rewrite_mlx.py    local MLX small-model worker
data/cache/voice/       cached voice lines
data/cache/stems/       cached Demucs instrumental beds
data/cache/music/       cached AI music beds
```

## Limits

- Hook selection is local heuristics plus optional local LLM reranking. It does not understand irony or brand safety.
- The crop is per beat. A subject that walks across a long take may drift out of the crop; split the source or edit the cut.
- Captions come from OCR and speech. If the source already burns in subtitles, turn captions off to avoid doubles.
- No music generation, no synthetic voice, no transitions. The original audio and pacing are the vibe.
- Docs: [local models](docs/local-models.md) · [cloud plan](docs/cloud-plan.md).
- The server is localhost-first. `VIBECUT_TOKEN` is a simple shared secret, not multi-user auth; put a reverse proxy in front for network use.
