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

- From the local app: open `/_ductator/` on a loopback bind and choose
  **Create admin**.
- From a terminal:

```bash
python3 admin_cli.py create-admin --email admin@example.com
python3 admin_cli.py reset-password
```

The bootstrap route is rejected on a non-loopback bind. The admin email may be
changed later in **Access**; changing the password revokes other sessions.

## Authentication

- Email + password login.
- Password hashing: stdlib `hashlib.scrypt`.
- Session cookie: `HttpOnly`, `SameSite=Strict`, path `/_ductator`, 12-hour
  absolute lifetime, 30-minute idle timeout.
- CSRF header on every mutating request.
- Login rate limiting per email/IP.
- No SMTP, no magic links, and no email provider are required. The optional
  magic-link path is intentionally not exposed until an SMTP sender is added.

## Keys

The **Keys** tab manages the AI providers used by this project:

- OpenCode Go
- OpenRouter
- MiniMax
- Groq
- OpenAI
- Deepgram
- ElevenLabs
- Cartesia

Secrets stay in `data/secrets.json` with mode 0600. The console shows only a
masked value with the first five and last five characters. Full values are
never returned by the API. Environment-managed keys are read-only in the UI;
change the environment to rotate them.

Cobalt and XHS sidecar credentials remain in the existing Setup drawer.

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
catalog. Arbitrary model IDs are rejected by the server.

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

Catalogs are cached under `data/admin/model_catalog.json` for 15 minutes. A
failed refresh keeps the last good list. If no list is available, the UI shows
a catalog error instead of allowing free text.

Each card controls:

- ordered routes
- reasoning (`none`/`low`/`medium`/`high`/`max`, text workflows)
- max output tokens
- timeout seconds

Changes apply to new requests; no restart is required. The existing Setup
Intelligence panel shows a read-only route summary and links to the admin
console for editing.

## Logs

### Pipeline log

A persistent per-attempt log of model calls:

- workflow, route index, provider, model, reasoning
- status, latency, input/output tokens, fallback, sanitized error

It contains no prompts, user content, API keys, cookies, or raw provider
responses.

### Admin log

Every `/_ductator/api/*` request is logged, plus semantic entries for:

- bootstrap/login/logout and failed login
- key update/clear/test
- model route/reasoning/token/timeout changes and resets
- account email/password changes
- settings changes made through the existing Setup drawer, actor `setup`
- audit view/export

The log is append-only with a SHA-256 hash chain. Secret values are redacted;
key changes record only the masked value. The log can be exported as JSONL and
integrity-checked from the UI.

## Security notes

- Admin auth is independent of `VIBECUT_TOKEN`; the admin prefix is exempted
  from the app-token middleware and guarded by the admin session.
- Admin mutations require the CSRF header.
- The admin page is `noindex`, no-store, and not linked from the public app.
- The admin database is under `data/admin/` with directory mode 0700 and DB
  mode 0600.
- Do not expose `/_ductator/` on a shared network without a reverse-proxy
  access policy. The default product is a local app.
