# VibeCut admin console

The admin console lives at:

```text
/_ductator/
```

It is password-only, local-first, and deliberately separate from the user Setup
drawer. There is no signup, no user account system, and no second admin
registration.

## Bootstrap

The first admin is created only when no admin account exists:

- From the local app: open `/_ductator/` from a direct loopback request and
  choose **Create admin**.
- From a terminal:

```bash
python3 admin_cli.py create-admin --email admin@example.com
python3 admin_cli.py reset-password
```

Bootstrap requires the actual request client to be loopback, a loopback `Host`
and `Origin`, `VIBECUT_HOST` to be loopback, and no proxy forwarding headers.
It is rejected for remote clients even when the app is bound to `0.0.0.0` or is
behind a tunnel. The admin email may be changed later in **Access**; changing
the password revokes other sessions.

## Authentication

- Email + password login. The email must be present and match the single admin.
- Password hashing: stdlib `hashlib.scrypt`. Passwords are at least 12
  characters in the web UI, CLI creation, and CLI password reset.
- Session cookie: `HttpOnly`, `SameSite=Strict`, path `/_ductator`, 12-hour
  absolute lifetime, 30-minute idle timeout.
- CSRF header on every mutating request.
- Login rate limiting has separate per-IP and per-email buckets, with a bounded
  in-memory map and expiration.
- No SMTP, magic links, signup, or user accounts exist. There is no hidden
  magic-link path.

## Keys

The **Keys** tab manages the eight AI providers used by this project:

- OpenCode Go
- OpenRouter
- MiniMax
- Groq
- OpenAI
- Deepgram
- ElevenLabs
- Cartesia

Secrets stay in the configured data directory (`secrets.json`, default `data/secrets.json`) with mode 0600. The console returns only a
masked value: short keys become fixed bullets, longer keys show a short
recognisable prefix/suffix. A complete value is never returned by the API,
audit log, export, or database. Environment-managed keys are read-only in the
UI and rejected by the save endpoint; change the environment to rotate them.

Saving or clearing a key clears provider quarantine/breakers and model/voice/
music caches so a rotated key is usable immediately. XHS sidecar credentials
remain in the existing Setup drawer.

## Models

The **Models** tab is an ordered fallback-route editor for each worker:

- Story brief
- Script rewrite
- Translation
- Hook ranking
- Voice-over
- Music
- Transcription

Each route has a provider and a model selected from a **searchable, strict**
catalog. Arbitrary model IDs are rejected by the server. Validation is scoped
to the workflow kind: TTS routes cannot use music models, rewrite/translate/STT
cannot use each other's models, empty routes are rejected, and duplicate
provider routes with different models keep their order.

The runtime resolves the same ordered list for every worker. TTS, music,
transcription, hook ranking, story brief, rewrite, and translation use only
configured providers/models and record each attempt in the pipeline log. Local
languages/voices are selected from the route model where applicable; no hidden
provider ladder is appended.

**Admin routes are the source of truth.** Legacy Setup fields (`opencode.model`,
`openrouter.model`, `minimax.tts_model`, `stt.model`, and the like) are mirrors
of the first admin route, kept for old callers and UI summaries. Saving an admin
route updates the mirror. Setup cannot lock or override an admin model choice.

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

OpenRouter's general `/models` endpoint does not list every transcription
model. The built-in catalog carries the current speech-to-text collection
(for example `microsoft/mai-transcribe-2` and
`nvidia/nemotron-3.5-transcribe`) and merges it into the cached catalog on every
read, so a catalog refresh is not required to see those rows.

Catalogs are cached under `data/admin/model_catalog.json` for 15 minutes. A
failed refresh keeps the last good list. If no list is available, the UI shows
a catalog error instead of allowing free text.

Each card controls:

- ordered routes
- reasoning (`none`/`low`/`medium`/`high`/`max`, text workflows)
- max output tokens
- timeout seconds

Changes apply to new requests; no restart is required. The existing Setup
drawer shows a read-only summary of all seven workflow routes. It does not edit
routes and does not link to the admin console; open `/_ductator/` directly so
the admin URL stays unlinked from the public app.

## Logs

### Pipeline log

A persistent per-attempt log of model calls for all seven workflows: story
brief, script rewrite, translation, hook ranking, voice-over, music, and
transcription. Each row records:

- workflow, route index, provider, model, reasoning
- status, latency, input/output tokens when the provider exposes them,
  fallback, sanitized error
- request/job id where available

It contains no prompts, user content, API keys, cookies, or raw provider
responses. Filtering by workflow is a case-insensitive partial match.

### Admin log

Semantic actions are shown by default:

- bootstrap/login/logout and failed login
- key update/clear/test
- model route/reasoning/token/timeout changes and resets
- account email/password changes
- settings changes made through the existing Setup drawer, actor `setup`
- audit view/export/verify

Raw `http.request` rows are retained but hidden behind **Include raw HTTP
rows** so routine requests do not drown the audit view. Export is a full JSONL
export, not a truncated page.

The log is append-only with a SHA-256 hash chain. Writes use `BEGIN IMMEDIATE`
with busy retries, so multiple processes share one chain. A separate signed
head/count anchor detects tail truncation and invalid anchors. Old rows are
archived under `data/admin/audit-archive/` before retention prunes them; the
anchor moves to the new retention base, so verification stays valid. Secret
values, URL query strings, fragments, and cookie paths are redacted; key changes
record only the masked value.

## Security notes

- Admin auth is independent of `VIBECUT_TOKEN`; the admin prefix is exempted
  from the app-token middleware and guarded by the admin session.
- Admin mutations require the CSRF header.
- The admin page, redirect, `/static/admin.*`, and admin API responses send
  `no-store`, `noindex`, `DENY` framing, `no-referrer`, and a strict CSP.
- Remote admin access requires HTTPS. Cleartext admin traffic is rejected for
  non-loopback clients; `VIBECUT_ADMIN_TRUST_PROXY=1` is only for deployments
  that terminate TLS in front of VibeCut.
- The admin database is under `data/admin/` with directory mode 0700, DB mode
  0600, and a signed audit anchor/key in the same directory. `settings.json`
  and `secrets.json` are written with mode 0600.
- Setup is not an admin substitute: it cannot write workflow routes or bypass
  the catalog validator, and Setting writes reject cross-site/cross-origin
  requests.
- The default product is a local app. If `/_ductator/` is exposed through a
  tunnel, use the tunnel's access policy in addition to the HTTPS requirement.
