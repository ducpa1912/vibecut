# BYOK / BYOM plan

Scope (founder decision, 2026-11-11): **v1 is completely local.** Local model slots (BYOM) are v1.
User keys (BYOK) are planned here and built after v1.

Status: translation BYOM is shipped (`REQ-20261111-02`). The key half and the other local-model
slots are planned.
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

| Task | Local default today | Local model slot (BYOM) | Key slot (BYOK) | Priority |
|---|---|---|---|---|
| Transcription | Apple Speech, Whisper pack | any MLX Whisper folder | OpenAI, Groq, Deepgram, OpenRouter | P1 |
| Translation | Apple Translation | CTranslate2 folder (**shipped**) | DeepL, OpenAI | Done / P2 |
| Rewrite / script | Apple Intelligence | local LLM base URL (Ollama, llama.cpp) | OpenAI, Anthropic, OpenRouter | P1 |
| Voice-over | `say`, Kokoro pack | Kokoro voices, custom ONNX voice | ElevenLabs, OpenAI TTS | P2 |
| Clean / fill | LaMa (bundled) | custom ONNX inpaint model | HTTP fill service the user runs | P3 |
| OCR | Apple Vision | — | — | — |
| Scene detect | ffmpeg | — | — | — |

## Local model slots

A slot is a folder or a URL the user provides. DuckSuite never downloads it and never names it.

| Slot | Input | Validation | Store |
|---|---|---|---|
| Translation | folder | `model.bin`, `config.json`, `sentencepiece.bpe.model` | copied to `models/translation/<name>` |
| Transcription | folder | `weights.safetensors` + `config.json` | copied to `models/speech/<name>` |
| Rewrite | base URL | `/v1/models` answers | URL only, no copy |
| Voice | folder | `*.onnx` + voices file | copied to `models/voice/<name>` |
| Fill | folder or URL | ONNX input shape / `/health` | copied or URL |

Rules for every slot: validate on choose, report missing items by name, keep the default when the
slot is empty, and never ship or link a specific model.

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
duckcore/providers.py      registry: id, task, kind (local|key), label, status(), run()
duckcore/secrets.py        Keychain get/set/delete + redaction helper
duckcore/engine/stt.py     cloud paths exist; gate on secrets.get("stt.<provider>")
duckcore/nllb.py           custom CTranslate2 folder (shipped)
duckcore/script.py         rewrite provider beside rewrite_apple
duckcore/voice.py          TTS provider beside say/kokoro
duckcore/engine/textfill   custom ONNX filler beside lama
duckcore/main.py           GET /api/providers, POST /api/providers/{id}/key, /test
static/duck/app.js         Connections section, model slot picker, consent dialog
```

One interface for both kinds:

```python
class Provider:
    id: str; task: str; kind: str          # "local" | "key"
    def status(self) -> dict: ...          # ready, detail, files missing
    def run(self, payload: dict) -> dict: ...
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
