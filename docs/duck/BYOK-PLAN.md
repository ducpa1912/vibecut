# BYOK / BYOM plan

Status: plan. The translation-model half is shipped in `REQ-20261111-02`; the key half is not.
Rule: DuckSuite ships no key, no default cloud provider and no proxy. Local is the default; a user
who adds a key opts that one task into their own provider.

## Two different things

- **BYOM — bring your own model.** A folder or file the user obtained. DuckSuite validates it and
  loads it. No download, no model name in the UI, no licence shipped by us. Translation is the first
  case: a CTranslate2 folder with `model.bin`, `config.json`, `sentencepiece.bpe.model`. Copied into
  app data so the sandboxed core can read it.
- **BYOK — bring your own key.** A secret the user pastes for a hosted provider. Stored in the
  macOS Keychain, never in `settings.json`, never in logs, never in an error string.

## Task matrix

| Task | Local default today | With BYOM | With BYOK | Priority |
|---|---|---|---|---|
| Transcription | Apple Speech, Whisper pack | Whisper pack (any MLX model folder) | OpenAI, Groq, Deepgram, OpenRouter | P1 |
| Translation | Apple Translation | CTranslate2 folder | DeepL, OpenAI, OpenRouter | Done / P2 |
| Rewrite / script | Apple Intelligence | — | OpenAI, Anthropic, OpenRouter, local Ollama | P1 |
| Voice-over | `say`, Kokoro pack | Kokoro voices | ElevenLabs, OpenAI TTS | P2 |
| Clean / fill | LaMa (bundled) | — | HTTP fill endpoint (user-run service) | P3 |
| OCR | Apple Vision | — | — | — |
| Scene detect | ffmpeg | — | — | — |

`stt.py` already contains Groq, Deepgram and OpenRouter code paths behind `cloud_stt_key()`. No UI
exposes a key today, so they are unreachable. The BYOK work is the store, the UI and the switch.

## Key storage

- Keychain, one item per `provider.task` pair, `kSecClassGenericPassword`, service
  `com.ducksuite.app.keys`, account `<task>.<provider>`.
- The sidecar is sandboxed; the Swift shell reads the item and passes it to the core over the local
  socket, or the core uses the `security` CLI with the same service. Pick one and keep it in one
  module.
- `settings.json` stores only: provider id, task, enabled flag, last four characters for display.
- Redaction: one helper used by every log line and every error body. A 32-character secret never
  appears in a toast.
- Delete removes the Keychain item and the display stub.

## UI

Settings → **Connections**, one row per provider:

```
OpenAI          [ key ••••abcd ]  [Test]  [Remove]
  Used for:  [x] rewrite   [ ] transcription   [ ] voice
```

- Paste field is a password field; after save it shows the last four only.
- `Test` makes the smallest legal request and reports pass/fail without echoing the key.
- A row is off until the user ticks a task. Nothing is used implicitly.
- The first time a task with a key runs, one dialog: “This sends <audio|text> to <provider>. Continue?”
  Store the answer per provider. No dialog for local tasks.

## Privacy copy

- Default state stays: nothing leaves the Mac.
- A key changes that for one task only. Say which data, which provider, and how to remove it.
- No analytics, no key validation against our servers, no proxy. The request goes from the Mac to
  the provider.

## App Store

- User-supplied keys are not digital goods; no IAP needed.
- Do not ship a shared key, a relay endpoint, or a “free tier” that hides our key in the binary.
- Guideline 5.1.1: the privacy policy must name every provider the app can call.
- The app remains functional with zero keys: Apple Vision, Speech, Translation, `say`, LaMa.

## Code seams

```
duckcore/providers.py      registry: id, task, label, test(), call(), secret_name
duckcore/secrets.py        Keychain get/set/delete + redaction helper
duckcore/engine/stt.py     cloud paths already exist; gate on secrets.get("stt.<provider>")
duckcore/script.py         rewrite provider beside rewrite_apple
duckcore/voice.py          TTS provider beside say/kokoro
duckcore/main.py           GET /api/providers, POST /api/providers/{id}/key, /test
static/duck/app.js         Connections section, consent dialog
```

## Rollout

1. `secrets.py` + Keychain item + redaction + tests. No UI yet.
2. Connections UI with one provider (OpenAI) for rewrite. Consent dialog.
3. Transcription providers (the cloud code already exists).
4. Voice providers.
5. Fill endpoint, last: it moves pixels off the machine, which is the strongest promise to break.

## Acceptance

- No secret in `settings.json`, logs, error bodies or crash reports.
- Every cloud task is off until a key exists and is ticked.
- Removing a key returns the task to the local default without a restart.
- A build with zero keys passes the full test suite and every local flow.
