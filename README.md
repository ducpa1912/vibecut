# VibeCut

VibeCut is a self-hosted, local-first long-video → short-reel cutter. Drop a
minutes- or hours-long video; VibeCut scans it, reads the frames and speech,
finds a hook, builds 15 / 30 / 60 second cuts, reframes the subject, optionally
replaces the audio, and renders the reel on your machine.

Everything runs locally by default. There is no account, no cloud upload, and
no watermark. Cloud providers are optional and inactive until a key is saved.
The source is proprietary and closed-source; see [LICENSE](LICENSE) and
[docs/licensing.md](docs/licensing.md).

**v0.13.0** · [Roadmap](ROADMAP.md) · [Admin console](docs/admin.md) ·
[URL ingest](docs/url-ingest.md) · [Cloud speech](docs/cloud-speech.md)

## Quick start

Requirements:

- `ffmpeg` and `ffprobe` on `PATH`
- Python 3.11+
- Packages in `requirements.txt`
- macOS: `swiftc` from Xcode Command Line Tools for Apple Vision OCR, face and
  saliency reading. Without it, crops fall back to center and on-screen text is
  skipped.
- Optional: `mlx_whisper` for local speech transcription. Apple Speech is built
  in on macOS 26.
- Optional: OpenCode Go for DeepSeek V4.1 Flash. Enter a project key in Setup,
  or sign in with the OpenCode CLI.

```bash
cd vibecut
./run.sh
```

Open <http://127.0.0.1:8787>.

`run.sh` uses `.venv/bin/python` when present and otherwise the system
`python3`. If the core packages are missing, it installs `requirements.txt`
first. To run without the wrapper:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The Swift helpers are compiled on first use into `bin/vision_probe` and the
other `bin/*` helpers. `bin/`, `data/`, `sample/`, and generated music are
gitignored.

## First-run checklist

1. Open the main app and choose a local file, a local path, or a URL.
2. Open **Setup** if you want cloud intelligence, transcription, voice, music,
   or URL sidecar settings.
3. Open `/_ductator/` to create the single local admin account, manage AI keys,
   inspect provider catalogs, edit ordered model routes, and read logs.
4. Render a draft, check the cut, then render a final.

The main app and the admin console are deliberately separate surfaces. Setup is
the normal user configuration drawer. The admin console is the operational
control room and is not linked from the public app.

## What it does

VibeCut keeps one local job record per source. The pipeline is:

1. **Probe** the source with `ffprobe` and store duration, dimensions, fps,
   audio presence, and a fingerprint.
2. **Scan** with one low-resolution ffmpeg pass. It detects scene cuts plus
   motion, brightness and audio-onset signals.
3. **Shortlist** beats. Short videos are read in full. Long videos keep strong
   beats, the payoff zone, long takes and even timeline coverage, up to
   `VIBECUT_DEEP_SCENES` (default 300). Other scenes are read lazily when
   clicked.
4. **Read** one still per shortlisted beat. Apple Vision reads on-screen text,
   faces and attention saliency. Audio energy and onset density come from a
   mono 16 kHz track.
5. **Score** visual sharpness, motion, audio, on-screen text, speech and subject
   presence. Black and frozen beats are tagged and pushed out of plans.
6. **Plan** 15 / 30 / 60 second cuts. Plans share a hook, keep body beats in
   source order, land a payoff at the end, and avoid clustering.
7. **Edit** in Smart Cut: reorder, trim, remove, add Moments, choose an
   alternate hook, apply story-arc order, save variants, and compare A/B hooks.
8. **Replace audio** when wanted: rewrite and translate the script, synthesize
   voice, add music, mix stems, and snap cuts to a beat grid.
9. **Render** each beat as a segment, join frame-accurately, mux the audio bed,
   normalize to −14 LUFS, and cache the result.
10. **Deliver** the MP4, SRT/VTT captions, EDL/FCP7 XML, and a read-only review
    link.

### Local-first behaviour

- Jobs, sources, renders, caches, settings, secrets, and logs stay under
  `data/` by default.
- No account, login, cloud workspace, analytics, or telemetry is required.
- Cloud calls happen only when a provider route is configured and a key exists.
- The render path uses local ffmpeg; Apple Vision and MLX are local.
- The main app is bound to `127.0.0.1` unless `VIBECUT_HOST` changes it.

## URLs and paths

| Path | Purpose |
|---|---|
| `/` | Main application and Setup drawer. |
| `/static/*` | Plain HTML/CSS/JS assets. No build step. |
| `/_ductator/` | Password-only admin console. |
| `/_ductator` | 307 redirect to `/_ductator/`. |
| `/_ductator/api/*` | Admin JSON API. Session cookie and CSRF required. |
| `/docs/url-ingest.md` | Built-in copy of the URL-ingest guide. |
| `/api/health` | Health and capability report. Public even when a token is set. |
| `/r/{token}` | Read-only review page for a rendered reel. |
| `/r/{token}/video` | Review MP4 download/stream. |
| `/r/{token}/captions.srt` | Review SRT captions. |

The review token is a capability. Anyone with the URL can view that render.
Tokens live in `data/shares.json`; there is no account or per-viewer permission.
To revoke a link, remove its token entry from that file while the server is
stopped. Treat review links as shareable secrets.

## Setup drawer

Open **Setup** in the main app. Setup is not the admin console. It saves user
preferences and optional keys, but it cannot edit workflow model routes.

| Section | What it controls |
|---|---|
| **Intelligence** | OpenCode Go model settings; OpenRouter fallback settings; translation mode; rewrite and story-brief toggles. |
| **Transcription** | Spoken language. Provider, model order, and fallbacks are admin-owned transcription routes. |
| **Voice over** | MiniMax key and voice readiness. Provider order is admin-owned. Local Kokoro/Piper/say can be configured as fallback routes. |
| **Music** | Music generation availability and route readiness. Provider order is admin-owned. |
| **Video links** | yt-dlp quality, codec, container, audio, cookie source and browser; optional Cobalt fallback URL; optional xhs_get URL and token. |

Buttons such as **Test OpenCode**, **Check local STT**, **Live STT**,
**Check TTS**, and **Live TTS** report what is ready. Live tests use a local
sample and do not write a user job.

### Keys and precedence

The admin console manages the eight AI provider keys:

- OpenCode Go
- OpenRouter
- MiniMax
- Groq
- OpenAI
- Deepgram
- ElevenLabs
- Cartesia

Cobalt and xhs_get credentials remain in the existing Setup drawer because
they are optional URL sidecars, not AI model providers.

Keys are stored in `data/secrets.json` with mode `0600`. The API never returns
a complete key. Short keys become fixed bullets; longer keys show a short
prefix and suffix. Environment-managed keys are read-only in the UI.

Precedence:

- Most providers use the environment first, then `data/secrets.json`.
- OpenRouter is project-first: a key saved in Setup beats a global
  `OPENROUTER_API_KEY`. This prevents a stale global key from hiding the
  project key.
- Use a normal OpenRouter inference key. Management/provisioning keys cannot
  call chat or inference and are rejected by **Test OpenRouter**.

Common environment key names:

```text
OPENCODE_GO_API_KEY   OPENROUTER_API_KEY   MINIMAX_API_KEY
GROQ_API_KEY          OPENAI_API_KEY       DEEPGRAM_API_KEY
ELEVENLABS_API_KEY    CARTESIA_API_KEY
VIBECUT_COBALT_API_KEY
VIBECUT_XHS_GET_TOKEN
```

`VIBECUT_OPENCODE_API_KEY` is also accepted for OpenCode. See
[Configuration](#configuration).

### OpenCode Go without a key

Leave the OpenCode key blank to use the local OpenCode login:

```bash
opencode auth login
opencode models | grep opencode-go/deepseek-v4.1-flash
```

VibeCut calls the local OpenCode service, creates a short-lived session pinned
to `deepseek-v4.1-flash` at the `low` variant, generates the text, and deletes
the session. If OpenCode is missing or not signed in, the configured fallback
routes run.

## Admin console

The admin console is a single-account, password-only local control room at
`/_ductator/`. There is no signup, SMTP, magic link, email provider, user
account system, or second admin registration.

Full details: [docs/admin.md](docs/admin.md).

### Bootstrap and reset

Create the first admin in one of two ways:

1. Open `/_ductator/` from a direct loopback request and choose **Create
   admin**.
2. Use the CLI:

```bash
python3 admin_cli.py create-admin --email admin@example.com
python3 admin_cli.py reset-password
python3 admin_cli.py show
```

Administration is intentionally local. Bootstrap requires:

- an actual loopback client
- a loopback `Host` and `Origin`
- `VIBECUT_HOST` set to a loopback address
- no proxy forwarding headers

Bootstrap is rejected for remote clients even when the app is bound to
`0.0.0.0` or behind a tunnel. Use the CLI inside the host or container to create
the admin when remote bootstrap is impossible.

Passwords are at least 12 characters. Password changes revoke other sessions.

### Authentication and security

- Email + password login. The email must match the single admin.
- Password hashing uses stdlib `hashlib.scrypt`.
- Session cookie is `HttpOnly`, `SameSite=Strict`, path `/_ductator`, with a
  12-hour absolute lifetime and 30-minute idle timeout.
- Mutating admin requests require `X-VibeCut-Admin-CSRF`.
- Login rate limits have separate per-IP and per-email buckets.
- Admin auth is independent of `VIBECUT_TOKEN`.
- The admin page, redirect, `/static/admin.*`, and admin API responses send
  `no-store`, `noindex`, `DENY` framing, `no-referrer`, `nosniff`, and a strict
  CSP.
- Remote admin access requires HTTPS. Cleartext remote admin traffic is
  rejected. `VIBECUT_ADMIN_TRUST_PROXY=1` is only for a TLS-terminating proxy
  you control.
- Admin SQLite lives under `data/admin/` with directory mode `0700`, database
  mode `0600`, and a signed audit anchor/key in the same directory.

### Keys tab

The Keys tab lists the eight AI providers, whether each key exists, whether it
came from the environment or file, and a masked value. Environment-managed keys
cannot be rotated from the UI; change or unset the environment variable.

Saving or clearing a key clears provider quarantine/breakers and model, voice,
and music caches so a rotated key is usable immediately. A blank save is
rejected; **Clear** is explicit.

### Models tab

Seven workflows have ordered fallback routes:

- Story brief
- Script rewrite
- Translation
- Hook ranking
- Voice-over
- Music
- Transcription

Each route has a provider and a model selected from a searchable, strict
catalog. Arbitrary model IDs are rejected by the server. Validation is scoped to
the workflow kind: TTS routes cannot use music models, rewrite/translate/STT
models stay in their own kind, empty routes are rejected, and ordered duplicates
with different models are preserved.

Each workflow also stores:

- reasoning level (`none`, `low`, `medium`, `high`, `max` for text workflows)
- maximum output tokens
- timeout in seconds

Defaults are intentionally local-friendly:

| Workflow | Default routes |
|---|---|
| Story brief | OpenCode Go DeepSeek V4.1 Flash → OpenRouter DeepSeek → MLX Qwen |
| Script rewrite | OpenCode Go DeepSeek V4.1 Flash → OpenRouter DeepSeek → MLX Qwen |
| Translation | OpenCode Go → OpenRouter |
| Hook ranking | OpenCode Go → OpenRouter |
| Voice-over | MiniMax Speech 2.8 Turbo → OpenRouter Fish → OpenRouter Gemini → local Kokoro → Apple say → Piper |
| Music | MiniMax Music 3.0 |
| Transcription | Apple SpeechAnalyzer → mlx-whisper |

Catalog sources:

| Provider | Source |
|---|---|
| OpenRouter | `GET https://openrouter.ai/api/v1/models` |
| OpenCode Go | `opencode models`, filtered to `opencode-go/` |
| OpenAI | `GET https://api.openai.com/v1/models` |
| Groq | `GET https://api.groq.com/openai/v1/models` |
| Ollama | `GET http://127.0.0.1:11434/api/tags` |
| ElevenLabs | `GET https://api.elevenlabs.io/v1/models` |
| MLX | local catalog |
| MiniMax, Deepgram, Cartesia, Apple | built-in catalogs |

Catalogs are cached at `data/admin/model_catalog.json` for 15 minutes. A failed
refresh keeps the last good list. If no list is available, the UI reports the
catalog error instead of allowing free text. Changes apply to new requests; no
restart is required.

The runtime resolves the same ordered list for every worker. No hidden provider
ladder is appended after the configured routes. TTS, music, transcription and
hook ranking therefore fail over in the order the admin selected.

### Pipeline log

The Pipeline tab records one row per model attempt for all seven workflows. A
row includes workflow, route index, provider, model, reasoning, status, latency,
input/output tokens when exposed by the provider, fallback flag, sanitized error,
and request/job id when available.

It does not store prompts, user content, API keys, cookies, or raw provider
responses. Workflow filtering is a case-insensitive partial match.

### Admin log

The admin log is append-only with a SHA-256 hash chain. Semantic actions are
shown by default:

- bootstrap, login, logout, failed login
- key update, clear, test
- model route, reasoning, token, timeout changes and resets
- account email/password changes
- Setup changes, actor `setup`
- audit view, export, verify

Raw `http.request` rows are retained but hidden behind **Include raw HTTP
rows**. Export is full JSONL, not a truncated page.

Writes use `BEGIN IMMEDIATE` with busy retries so multiple processes share one
chain. A separate signed head/count anchor detects tail truncation and invalid
anchors. Old rows are archived under `data/admin/audit-archive/` before
retention prunes them; the anchor moves to the new retention base. Secret values,
URL query strings, fragments, and cookie paths are redacted; key changes record
only the masked value. Audit retention is 365 days and pipeline retention is 90
days.

## Workflow

### 1. Ingest

The main screen accepts:

- **Drop a video** — upload. The default ceiling is 20 GB
  (`VIBECUT_MAX_UPLOAD_GB`).
- **Use a local path instead** — analyze a file in place without copying it.
- **Paste a video link** — URL ingest through yt-dlp, with optional Cobalt or
  xhs_get sidecars.

Uploads are stored in the content-addressed source store
(`data/sources/<hash>/`) and hardlinked into the job directory. A cross-volume
copy is used when hardlinking is impossible.

Ingest options:

- **Smart crop** — Vision subject tracking. Turn off for a center crop.
- **Read text & faces** — OCR for hook scoring and captions. Separate from crop.
- **Transcribe speech** — off by default for videos over 15 minutes; short
  clips default on.
- **Transcription language** — from Setup. Apple Speech needs an explicit locale;
  auto language goes to Whisper.

### 2. Analyze

The job record moves through `queued`, `downloading`, `scanning`, `reading`,
`scoring`, `ready`, `failed`, `interrupted`, or `cancelled`. Analysis runs on
one analysis worker. URL downloads use a separate ingest pool. A restart marks
interrupted analysis and renders `interrupted`; completed analysis and renders
stay on disk. Retry requeues analysis, and a render retry reuses cached
segments instead of resuming a partial ffmpeg file.

Progress, message, error, source metadata and analysis timings are written to
`job.json`. The public job response redacts the local source path.

### 3. Smart Cut and Moments

After analysis:

- Pick **15 / 30 / 60** seconds.
- Preview the cut timeline.
- Open **Moments** for compact thumbnails, a scrub slider, the automatic hook,
  the payoff and used-clip badges. Click to preview, drag into Smart Cut, or
  expand the collage.
- Edit the cut: drag to reorder, drag an edge to trim, drag out to remove, or
  drop a moment to add. The hook stays first and the payoff stays last.
- Use **Hook lab** to compare the strongest opening candidates with their
  resulting cut length and a plain-language reason.
- Hover a timeline clip for its **why** note. The drawer repeats the reasoning
  per beat.
- **Story arc order** reorders beats as setup → proof → payoff.
- **Platform presets** set aspect, captions and safe-zone caption margin:
  TikTok, Reels, Shorts, Square, Landscape.
- **A/B hooks** queues the three strongest hooks at once.
- **Save variant** stores an edited cut; variant chips reload or delete it.
- **Keyboard editing**: `←/→` select, `Alt+←/→` reorder, `−/+` trim, `Del`
  remove, `e` edit, `s` save, `r` draft, `Space` play.

Bilateral smart crop stores attention crops for 9:16, 4:5, 1:1 and 16:9. A
portrait source cropped to 16:9 follows the subject on the vertical axis; a
landscape source cropped to 9:16 follows it on the horizontal axis. Switching
aspect is a true reframe with no re-analysis. **Track crop** samples extra
frames and smooths a per-aspect path used by the renderer.

### 4. Audio

Audio modes are tabs:

| Mode | What happens |
|---|---|
| Original | Nothing changes. The original audio is the bed. |
| Voice-over | New voice over the original audio; the original voice is ducked underneath. |
| Dub | Demucs removes the original voice; music/SFX stay; new voice replaces it. |
| Music | Original audio removed; new music only. |
| Full Replace | New voice plus new music; original audio removed. |

The audio panel is three steps:

1. **Rewrite** — runs only when you press **▶ Rewrite**. It translates the full
   script, then rewrites the cut. Styles: literal, smooth, viral, fun, creative,
   sad, chill, faithful.
2. **Voice** — choose a voice from the admin voice-over route. **Use my
   recording** appears in Voice-over, Dub and Full Replace; it fits your
   recording to the cut and is not voice cloning. **Live TTS** tests the engine.
3. **Music** — choose your own upload, a library/CC0 track, MiniMax Music, or
   OpenRouter Lyria 3. **Use my sound** accepts your own file. AI sources use an
   automatic mood prompt built from the cut. The normal picker hides Stable
   Audio and MusicGen, which remain advanced legacy options.

**Automation mixer**: one section per clip, a music lane and a voice lane. The
lane starts at 100% (0 dB). Click to add a node, drag anywhere in time or gain,
double-click to remove, **Reset 100%** clears, and **Flatten** returns every
node to 100%. The curve is cosine and the same curve runs in ffmpeg. Original
audio and the Demucs music stem are drawn behind the lanes.

**Beat sync** detects the bed BPM, snaps cuts to the grid (maximum 250 ms shift)
and starts the loop on a beat.

**Translation** is a Setup mode, not a visible engine: **Auto** (online → local),
**Local first**, **Local only**, **Online only**. The visible online providers
are OpenCode and OpenRouter; local is Apple Translation with Argos available as
an advanced fallback. Apple batches are split and retried. Translations are
cached in `data/cache/translate`.

The voice script builder strips fillers and stage directions, drops
near-duplicate lines, prefers speech over on-screen text, fits each line to its
slot, and tags a small emotion that changes the speaking rate.

**Usage** under the result title sums tokens, STT minutes, TTS characters and
estimated cost per job. Estimates are visibility, not a hard billing system.

### 5. Render and deliver

- **Draft** renders 540×960 for a fast check. **Render final** renders 1080×1920.
- **All 15/30/60** queues every length.
- **Aspect** switches between 9:16, 4:5, 1:1 and 16:9.
- **Captions** burns OCR/speech text as styled overlays.
- **Render again** forces a fresh encode. **Cancel** stops a running render.
- Renders are cached per plan, quality, aspect, captions, audio mix and hook.
  An overridden hook gets its own render slot.
- **Download** the MP4. **SRT / VTT / EDL / XML** export captions or cut lists
  for Resolve and Premiere.
- **Review link** creates a read-only page with the rendered video and SRT.
- **History** stores every translation, rewrite, render and upload attempt with
  provider, model, status, latency, cost, warning/error and script snapshot.
  Restore a script as overrides on the current cut, copy original/final text, or
  re-download a render. Failed attempts stay visible.

Rendered files live in `data/jobs/<id>/renders/`. A render is a conventional
H.264 MP4 at 30 fps. The renderer cuts each beat separately, joins with the
concat demuxer, muxes the audio bed, and writes a poster frame.

## URL ingest: yt-dlp first, sidecars optional

The URL bar is for public internet links. Use **Use a local path instead** for
files already on the machine. Private, loopback, link-local and reserved IP
literals are rejected. A URL checker cannot stop DNS rebinding, redirects or a
hostile extractor, so treat URL ingest as a privileged network feature.

### yt-dlp (default)

The normal path is the native Python **yt-dlp** API. It needs no Node, Docker,
Cobalt server, or cloud upload. It downloads the best matching video + audio,
prefers H.264/MP4 for editor compatibility, then starts dissection only after
the download completes.

- Common sites: YouTube, TikTok, Instagram, X, Reddit, Vimeo and direct media.
- Playlist links return a picker of up to 200 entries. Choose one entry; bulk
  playlist download is not implemented.
- Cookie source: `none`, a Netscape `cookies.txt`, or a browser profile.
  Cookie-file paths are stored; cookie contents are not.
- Progress and cancel are supported. Cancel removes the temporary file and
  marks the attempt failed.
- Site extractors change often. Update with
  `python -m pip install -U yt-dlp` when a previously working site fails.

### Cobalt (optional fallback)

Cobalt is a separate AGPL-3.0 service. It is not bundled, not imported, and not
started by VibeCut. It is contacted only when:

- `ingest.provider` is explicitly `cobalt`, or
- `auto` mode tries yt-dlp, yt-dlp fails, and **Fallback after yt-dlp** is
  enabled with a Cobalt URL.

The hosted `api.cobalt.tools` service is rejected; configure your own instance.
Cobalt code and assets stay outside this repository. See
[docs/url-ingest.md](docs/url-ingest.md) and
[docs/licensing.md](docs/licensing.md).

### xhs_get / RedNote (optional sidecar)

xhs_get is a separate GPL-3.0 program for RedNote / Xiaohongshu. It is not
bundled. VibeCut calls its HTTP API for a single note.

- The RedNote cookie stays in xhs_get; VibeCut never reads its cookie file.
- Setup can open sign-in, copy the invite link, hand off a cookie, and check the
  session.
- A `friends` mode access token is optional and stays in the sidecar.
- A link must contain `xsec_token`; a bare `/explore/<id>` will not work.
- xhs_get is never used for non-RedNote links.

URL sidecar routing and failure details are in
[docs/url-ingest.md](docs/url-ingest.md).

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

`render` reuses the newest analyzed job for a file when one exists. `--target`
can be repeated. `--encoder auto|videotoolbox|libx264` overrides the default.
Audio replacement: `--audio-mode keep|full|bed|voice|music`,
`--translate <lang>`, `--translate-provider auto|opencode|apple_fm|argos|marian|ollama`,
`--voice-engine`, `--voice`, `--music`.

## API reference

All routes are local by default. JSON errors use `{"detail": "..."}`. Job IDs
are 12 lowercase hex characters. `target` is 15, 30 or 60. `quality` is `final`
or `draft`. `aspect` is `9:16`, `4:5`, `1:1` or `16:9`. `order` is `source` or
`arc`.

When `VIBECUT_TOKEN` is set, supply it as:

```text
Authorization: Bearer <token>
?token=<token>
vibecut_token cookie
```

`/`, `/static/*`, `/docs/url-ingest.md`, `/api/health`, `/r/*`, and the admin
prefix have separate rules. `/api/*` on a non-loopback bind without a token is
rejected. Review links are capability URLs and do not require the app token.

### Pages and review

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Main application. |
| GET | `/_ductator/` | Admin console page. |
| GET | `/_ductator` | Redirect to `/_ductator/`. |
| GET | `/docs/url-ingest.md` | URL-ingest guide. |
| GET | `/api/health` | Health, ffmpeg, Vision, Whisper, encoder, OpenCode, data path. |
| GET | `/r/{token}` | Read-only review page. |
| GET | `/r/{token}/video` | Review video. |
| GET | `/r/{token}/captions.srt` | Review captions. |

### Setup and ingest

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/settings` | Public settings, key status, paths, runtime readiness. |
| POST | `/api/settings` | Save allowed Setup sections. Rejects `workflows`; admin owns routes. |
| POST | `/api/settings/test` | Test OpenCode, OpenRouter, STT, TTS, or ingest providers. |
| GET | `/api/settings/tts-test/{engine}.wav` | Download a generated TTS test clip. |
| GET | `/api/ingest/status` | yt-dlp, Cobalt and xhs_get status; public ingest settings. |
| POST | `/api/ingest/xhs/cookie` | Forward a RedNote cookie to xhs_get. Not stored by VibeCut. |
| GET | `/api/ingest/xhs/invite` | Build an xhs_get invite URL. |
| POST | `/api/ingest/xhs/invite` | Build an xhs_get invite URL with a supplied URL/token. |
| POST | `/api/ingest/xhs/check` | Check xhs_get service and session. |

### Jobs and analysis

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/inspect` | Probe a local path without creating a job. |
| POST | `/api/url/inspect` | Inspect a URL, provider chain and playlist choices. |
| POST | `/api/jobs/upload` | Multipart upload; fields `file` and JSON `options`. |
| POST | `/api/jobs/path` | Create a job from a local path. |
| POST | `/api/jobs/from-url` | Create a background URL-ingest job. |
| GET | `/api/jobs` | Recent jobs, newest first, capped at 24. |
| GET | `/api/jobs/{job_id}` | Public job record, analysis, renders, usage. |
| GET | `/api/jobs/{job_id}/usage` | Usage/cost summary for one job. |
| GET | `/api/jobs/{job_id}/status` | Poll status, progress, message, renders. |
| POST | `/api/jobs/{job_id}/url/cancel` | Request cancellation of a URL download. |
| GET | `/api/jobs/{job_id}/history` | History summaries; optional `limit` 1–200. |
| GET | `/api/jobs/{job_id}/history/{entry_id}` | One history summary and snapshot. |
| DELETE | `/api/jobs/{job_id}/history/{entry_id}` | Delete one history entry. |
| POST | `/api/jobs/{job_id}/history/{entry_id}/restore` | Return a snapshot; client applies it. |
| POST | `/api/jobs/{job_id}/scene/{scene_id}/read` | Deep-read a scene on demand; may re-plan. |
| GET | `/api/jobs/{job_id}/thumb/{scene_id}` | Scene thumbnail. |
| GET | `/api/jobs/{job_id}/media/{filename}` | Render MP4 or poster; filename must be `reel_*.mp4`/`.jpg`. |
| POST | `/api/jobs/{job_id}/retry` | Idempotently retry interrupted/failed analysis or renders. |
| DELETE | `/api/jobs/{job_id}` | Delete a finished job directory. |

### Batches

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/batches` | Create and start a sequential batch; max 10 items. |
| GET | `/api/batches` | Recent batch manifests with counts and progress. |
| GET | `/api/batches/{batch_id}` | One batch manifest and item states. |
| POST | `/api/batches/{batch_id}/resume` | Requeue paused work; done items and outputs stay. |
| POST | `/api/batches/{batch_id}/cancel` | Cancel pending work and best-effort stop the active job. |

Batch items take exactly one of `path` or `url` plus an `options` object.
`options.targets` (`[15, 30, 60]`) queues renders after analysis; without it the
item completes when analysis is ready.

### Cut planning and editing

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs/{job_id}/plan` | Build a cut plan from target/hook/clips/order. |
| GET | `/api/jobs/{job_id}/hooks` | Hook candidates with thumb, score, reason and plan length. |
| POST | `/api/jobs/{job_id}/variants` | Save an edited cut variant. |
| DELETE | `/api/jobs/{job_id}/variants/{variant_id}` | Delete a variant. |
| GET | `/api/jobs/{job_id}/transcript` | Timestamped transcript and search segments. |
| POST | `/api/jobs/{job_id}/share` | Create a review link for a ready render. |
| GET | `/api/jobs/{job_id}/mixer` | Reel-time clip sections and audio envelopes. |
| POST | `/api/jobs/{job_id}/ab` | Queue one render for each of the top three hooks. |
| GET | `/api/jobs/{job_id}/export/{kind}` | `srt`, `vtt`, `edl` or `xml` export. |

### Audio

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/audio/engines` | Local/cloud voice and music engine readiness. |
| GET | `/api/audio/voices?engine=...` | Voices for one engine. |
| GET | `/api/audio/music?source=...` | Library/CC0/generated tracks. |
| GET | `/api/audio/translate/status` | Translation provider readiness. |
| POST | `/api/audio/translate/install` | Legacy install endpoint; returns Apple Translation guidance. |
| GET | `/api/jobs/{job_id}/audio/moods` | Scene moods and music prompt for a cut. |
| POST | `/api/jobs/{job_id}/audio/voice-upload` | Upload a voice recording for fitting. |
| POST | `/api/jobs/{job_id}/audio/music-upload` | Upload a music bed. |
| POST | `/api/jobs/{job_id}/voice/sample` | Synthesize a voice sample WAV. |
| GET | `/api/audio/beats?source=...&track=...` | BPM and beat grid for a library track. |
| GET | `/api/audio/licenses` | Music license registry and strict-mode flag. |
| GET | `/api/sources` | Content-addressed source library and sizes. |
| POST | `/api/jobs/{job_id}/audio/script` | Rewrite/translate and fit the voice script. |

### Render, clean and delete

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs/{job_id}/render` | Queue one target render. |
| POST | `/api/jobs/{job_id}/render-all` | Queue 15, 30 and 60 renders. |
| POST | `/api/jobs/{job_id}/render/{target}/cancel` | Cancel a render by query key. |
| POST | `/api/jobs/{job_id}/clean` | Delete work files, renders, or both; source and `job.json` stay. |

### Admin API

Prefix: `/_ductator/api`. All routes except `GET /bootstrap` and `POST
/bootstrap` require a session. Mutations also require
`X-VibeCut-Admin-CSRF`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/_ductator/api/bootstrap` | Whether an admin exists and whether local bootstrap is allowed. |
| POST | `/_ductator/api/bootstrap` | Create the single admin from a direct loopback request. |
| POST | `/_ductator/api/login` | Email/password login; returns CSRF and expiry. |
| POST | `/_ductator/api/logout` | Delete the session. |
| GET | `/_ductator/api/me` | Current admin, CSRF, expiry, bootstrap state. |
| GET | `/_ductator/api/overview` | Keys, workflows, recent audit, recent pipeline rows. |
| GET | `/_ductator/api/keys` | Masked AI keys, sources and settings paths. |
| POST | `/_ductator/api/keys/{name}` | Save or clear one AI key. |
| POST | `/_ductator/api/keys/{name}/test` | Test a key where a live check exists. |
| GET | `/_ductator/api/catalog` | Searchable provider catalog; optional `provider`, `workflow`, `refresh`. |
| GET | `/_ductator/api/workflows` | All routes, labels, kinds, providers and reasoning values. |
| POST | `/_ductator/api/workflows/{name}` | Validate and save one ordered workflow. |
| POST | `/_ductator/api/workflows/{name}/reset` | Reset one workflow to defaults. |
| GET | `/_ductator/api/audit` | Audit entries; filters `actor`, `action`, `resource_type`, `include_http`. |
| GET | `/_ductator/api/audit/export` | Full JSONL audit export. |
| GET | `/_ductator/api/audit/verify` | Verify hash chain and signed anchor. |
| GET | `/_ductator/api/pipeline` | Pipeline entries; filters `workflow`, `provider`, `status`, `job_id`. |
| POST | `/_ductator/api/account` | Change admin email and/or password; revokes other sessions. |

### Request body notes

Job options (`options` in upload/path/from-url):

```json
{
  "ocr": true,
  "transcribe": true,
  "smart_crop": true,
  "crop_tracking": true,
  "transcribe_engine": "auto",
  "speech_language": "en"
}
```

`POST /api/jobs/from-url`:

```json
{
  "url": "https://example.com/video",
  "provider": "auto",
  "options": {"ocr": true, "transcribe": false},
  "ingest_options": {"quality": "1080", "codec": "h264", "container": "mp4"}
}
```

Plan/render body (`PlanBody`):

```json
{
  "target": 30,
  "hook_scene": 4,
  "force": false,
  "quality": "final",
  "aspect": "9:16",
  "encoder": "auto",
  "captions": true,
  "clips": [{"scene": 4, "start": 12.0, "end": 15.2, "role": "hook"}],
  "audio": {"mode": "voice", "voice": {"engine": "kokoro", "voice": "af_heart"}},
  "preset": "tiktok",
  "order": "source",
  "caption_margin": 0.12,
  "script_id": "a1b2c3d4e5f6"
}
```

`clips` is optional. When omitted, VibeCut builds the automatic plan. When
provided, each clip must reference a scene and be at least 0.2 seconds.

Script body (`POST /api/jobs/{job_id}/audio/script`):

```json
{
  "target": 30,
  "hook_scene": 4,
  "clips": [],
  "translate": "vi",
  "provider": "auto",
  "mode": "smooth",
  "rewrite_provider": "auto",
  "force_translate": false,
  "order": "source",
  "overrides": {}
}
```

Clean body: `{"profile": "workfiles" | "renders" | "all"}`.

Admin key body:

```json
{"value": "sk-...", "clear": false}
```

Workflow body:

```json
{
  "routes": [
    {"provider": "opencode-go", "model": "deepseek-v4.1-flash"},
    {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash"}
  ],
  "reasoning": "low",
  "max_output_tokens": 3200,
  "timeout_s": 300
}
```

## Storage

Default data root: `data/`. Override with `VIBECUT_DATA`.

```text
data/
  settings.json                 Preferences; mode 0600
  secrets.json                  Optional keys; mode 0600
  shares.json                   Review-link capabilities; mode 0600
  admin/
    admin.sqlite3               Admin users, sessions, audit, pipeline log
    audit.key                   HMAC key for the signed audit anchor
    audit.head.json             Signed head/count anchor
    audit.head.lock             Cross-process anchor lock
    model_catalog.json          Cached provider catalogs
    audit-archive/              Archived audit JSONL before retention
  jobs/<id>/
    job.json                    Portable job state, analysis, plans, renders
    source.<ext>                Hardlink to the source store (or a copy)
    thumbs/                     Scene stills, 00000.jpg style
    tracking/                   Crop tracking samples
    transcript/transcript.json  Timestamped speech transcript
    audio/                      Uploaded/fitted audio and script artifacts
    renders/                    reel_*.mp4 and reel_*.jpg
    history/
      index.json                Capped summaries
      <entry_id>.json           Full per-entry snapshot
  sources/<hash>/
    source.<ext>                Content-addressed upload
    meta.json                   Original name, size, creation time
  cache/
    segments/                   Content-addressed render segments
    beats/                      BPM and beat grids
    rewrite/                    Rewrite memo
    brief/                      Story-brief memo
    waveforms/                  Mixer RMS envelopes
    voice/                      Cached voice lines (FLAC)
    stems/                      Demucs instrumental beds
    music/                      Generated/cached music beds
    masters/<job_id>/           Video masters before audio mux
    translate/                  Translation memo
    stt-test/                   Live STT test clip/transcript
    voice-test/                 Live TTS test clips
  models/kokoro/                Optional Kokoro model files
  voices/piper/                 Optional Piper voices
assets/music/
  library/                      User library tracks
  cc0/                          CC0 tracks
  generated/                    AI beds kept as reusable library tracks
bin/                            Compiled Swift helpers and local tools
```

The source store uses a SHA-1 content digest (first 16 hex characters). Jobs
hardlink the stored file; if the filesystem cannot hardlink, VibeCut copies it.
`GET /api/sources` lists entries and link counts. `VIBECUT_SOURCES_GC_DAYS`
(default 30) removes unreferenced uploads; referenced hardlinks are kept.

### Retention and cleanup

| Control | Default | Effect |
|---|---|---|
| `VIBECUT_RETENTION_DAYS` | `0` (keep) | Delete whole jobs older than this. |
| `VIBECUT_JOB_CLEAN_DAYS` | `0` (off) | Delete job work files after this age. |
| `VIBECUT_CACHE_DAYS` | `14` | Age-prune caches. |
| `VIBECUT_CACHE_MAX_GB` | `2` | LRU cap across caches. |
| `VIBECUT_KEEP_RENDERS` | `1` | Newest finals kept per target/aspect/captions/mix. |
| `VIBECUT_KEEP_DRAFTS` | `0` | Keep drafts after a final exists. |
| `VIBECUT_SOURCES_GC_DAYS` | `30` | Remove unreferenced source-store entries. |
| `VIBECUT_HISTORY_MAX` | `50` | History entries per job; hard maximum 200. |

**Clean** in the job header deletes work files (thumbs, transcript, audio) or
renders while keeping `source` and `job.json`. `python3 cli.py audit` prints
installed engines, models and cache sizes with removal hints.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VIBECUT_HOST` | `127.0.0.1` | Bind address. |
| `VIBECUT_PORT` | `8787` | HTTP port. |
| `VIBECUT_DATA` | `./data` | Data root. |
| `VIBECUT_TOKEN` | unset | Shared app token for `/api/*` and UI media. |
| `VIBECUT_MAX_UPLOAD_GB` | `20` | Upload ceiling. |
| `VIBECUT_URL_MAX_GB` | `4` | Cobalt/xhs_get download ceiling. |
| `VIBECUT_DEEP_SCENES` | `300` | Deep-read shortlist size. |
| `VIBECUT_ENCODER` | `auto` | `auto`, `videotoolbox` or `libx264`. |
| `VIBECUT_RENDER_WORKERS` | `4` | Parallel segment workers. |
| `VIBECUT_CAPTION_FONT_FILE` | system font | Caption TTF/TTC. |
| `VIBECUT_HISTORY_MAX` | `50` | Per-job history entries, capped at 200. |
| `VIBECUT_ADMIN_TRUST_PROXY` | unset | Set `1` only behind a TLS-terminating proxy. |

Model and local engine variables:

| Variable | Default | Meaning |
|---|---|---|
| `VIBECUT_OPENCODE_API_KEY` / `OPENCODE_GO_API_KEY` | unset | OpenCode Go key. |
| `VIBECUT_OPENROUTER_API_KEY` | unset | OpenRouter key. |
| `VIBECUT_MINIMAX_API_KEY` | unset | MiniMax TTS/music key. |
| `VIBECUT_GROQ_API_KEY` | unset | Groq STT/TTS/text key. |
| `VIBECUT_OPENAI_API_KEY` | unset | OpenAI STT/TTS/text key. |
| `VIBECUT_DEEPGRAM_API_KEY` | unset | Deepgram STT/TTS key. |
| `VIBECUT_ELEVENLABS_API_KEY` | unset | ElevenLabs TTS key. |
| `VIBECUT_CARTESIA_API_KEY` | unset | Cartesia TTS key. |
| `VIBECUT_COBALT_API_KEY` | unset | Optional Cobalt instance key. |
| `VIBECUT_XHS_GET_TOKEN` | unset | Optional xhs_get friends-mode token. |
| `VIBECUT_OPENCODE_BIN` | `opencode` on `PATH` | OpenCode CLI path. |
| `VIBECUT_MLX_REWRITE_MODEL` | `mlx-community/Qwen2.5-3B-Instruct-4bit` | MLX rewrite model. |
| `VIBECUT_LLM_URL` | unset | Ollama `/api/generate` URL. |
| `VIBECUT_LLM_MODEL` | `qwen2.5:3b` | Ollama model. |
| `VIBECUT_REWRITE_CONTEXT_CHARS` | `6000` | Transcript context cap. |
| `VIBECUT_WHISPER_MODEL` | `mlx-community/whisper-small-mlx` | MLX Whisper model. |
| `VIBECUT_GROQ_STT_MODEL` | route/default | Groq STT model override. |
| `VIBECUT_OPENAI_STT_MODEL` | route/default | OpenAI STT model override. |
| `VIBECUT_GROQ_TTS_MODEL` | route/default | Groq TTS model override. |
| `VIBECUT_OPENAI_TTS_MODEL` | route/default | OpenAI TTS model override. |
| `VIBECUT_OPENROUTER_QUARANTINE_SECONDS` | `300` | OpenRouter auth-failure quarantine. |
| `VIBECUT_PROVIDER_BREAKER_FAILURES` | `3` | Failures before a provider breaker opens. |
| `VIBECUT_PROVIDER_BREAKER_SECONDS` | `90` | Breaker cooldown. |
| `VIBECUT_AUDIO_LICENSE` | `normal` | `strict` requires music/voice license metadata. |

Environment keys are read-only in the admin UI. A project key saved for
OpenRouter overrides its environment variable; for other providers the
environment wins.

### Running with a token

When `VIBECUT_TOKEN` is set, the UI asks for it once and stores it in
`localStorage`. Media and thumbnail URLs carry `?token=` so the video player
keeps working. This is a shared bearer secret, not multi-user authentication.
For network use, put VibeCut behind a reverse proxy and use the proxy's access
controls as well.

## Docker

```bash
docker compose up --build
```

The container uses `libx264`, Debian ffmpeg and DejaVu fonts, mounts `./data`
at `/data`, and serves port `8787`. Apple Vision and MLX Whisper are
macOS-only, so the container falls back to center crop and no Apple speech. Set
`VIBECUT_TOKEN` for any non-loopback use. The container binds `0.0.0.0`, so
admin bootstrap from a remote browser is rejected; create the admin with
`docker compose exec vibecut python3 admin_cli.py create-admin --email ...`.
Remote admin access requires HTTPS.

## Legacy and compatibility

VibeCut keeps some older paths for existing jobs and advanced installs:

- **Stable Audio / MusicGen** stay in `audio.py`, `tools/music_generate.py`, and
  `tools/musicgen_generate.py` for advanced/legacy music plans, but are hidden
  from the normal music picker.
- **Argos / Marian / Ollama translation** remain as advanced local fallbacks.
  The normal visible translation providers are OpenCode, OpenRouter and Apple.
- **Local LLM hook ranking** is available only through a configured `ollama`
  route and `VIBECUT_LLM_URL`.
- **Cobalt and xhs_get** are optional external sidecars. They are never
  bundled, imported, or required for common URLs.
- **Old settings** are migrated on load. v0.7 OpenRouter settings are copied to
  OpenCode when no OpenCode section exists.
- **Old jobs** without variants, history, crop tracking, or newer render keys
  keep working; missing optional fields are treated as empty/defaults.
- **Old renders** remain in `data/jobs/<id>/renders/`. Review links can fall
  back to matching render filenames produced by the CLI.
- **Old `data/cache` entries** are pruned by age/LRU and are not required for a
  job to load.

No Stripe, billing, cloud provisioning, GCP, Decodo, YouTube Data API, social
publishing, team accounts, cloud sync, or hosted render farm is included.

## Limits

- Hook selection is local heuristics plus optional configured model reranking.
  It does not understand irony or brand safety.
- Crop is per beat with optional tracking. A subject moving across a long take
  can still drift; split the source or edit the cut.
- Captions come from OCR and speech. If subtitles are already burned in, turn
  captions off to avoid doubles.
- Translation and rewrite quality depend on the configured model. Preview
  before publishing.
- AI music/TTS availability depends on provider accounts and keys. MiniMax
  music is limited to accounts with access.
- The render cache identity covers target, quality, aspect, captions, audio mix
  and hook. Changing a platform preset on the same aspect should use **Render
  again** if you need a separately retained file.
- Analysis and render pools are in-process. A restart marks interrupted work
  `interrupted`; retry requeues it. Partial analysis and partial ffmpeg output
  are not resumed, but finished render segments come from the cache.
- Private batches run sequentially, at most ten items, under
  `data/batches/<batch_id>.json`. A restart pauses an active batch and keeps
  completed outputs; resume requeues the remaining work.
- The app is localhost-first. `VIBECUT_TOKEN` is a shared secret, not a
  multi-user permission model.
- Review links are bearer capabilities without expiry or revocation UI.

## Tests and release checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
python3 -m compileall -q app.py audio.py pipeline.py settings_store.py workflow_config.py admin
node --check static/app.js
node --check static/admin.js
python3 scripts/check_proprietary_deps.py
git diff --check
```

`requirements-dev.txt` adds `pytest` and `httpx2`, which Starlette's
`TestClient` needs. Runtime installs do not need them.

Current suite: **553 tests**. The optional beat-grid test skips when `librosa`
is not installed. The tests use temporary `VIBECUT_DATA` directories and do not
require ffmpeg for the fast unit set. The dependency audit checks direct
requirements, sidecar imports, and the installed yt-dlp floor. Two existing
warnings are expected: `setuptools` and `stable-audio-tools` lack usable
license metadata.

## Documentation

- [Admin console](docs/admin.md)
- [URL ingest and sidecars](docs/url-ingest.md)
- [URL ingest QA](docs/url-ingest-qa.md)
- [Cloud speech and provider costs](docs/cloud-speech.md)
- [Audio replacement](docs/audio-replacement.md)
- [Local models](docs/local-models.md)
- [History API](docs/history-api.md)
- [Rewrite prompt](docs/rewrite-prompt.md)
- [Licensing and distribution](docs/licensing.md)
- [Cloud plan](docs/cloud-plan.md)
- [Roadmap](ROADMAP.md)

## License

VibeCut is proprietary and closed-source. No open-source license is granted for
the VibeCut source, UI, prompts, or build scripts. Third-party components keep
their own licenses. Cobalt, xhs_get, yt-dlp, ffmpeg, model weights and optional
engines have separate terms; see [docs/licensing.md](docs/licensing.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The default build does not include Cobalt or xhs_get. Running them as separate
services is optional. If you distribute a build that bundles a sidecar, follow
the source-offer, license-text, branding and separate-process requirements in
[docs/licensing.md](docs/licensing.md).
