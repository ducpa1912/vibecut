# Local-only speech and network audit — REQ-20261118-02

**Verdict: PASS** — DuckSuite cannot reach a cloud speech, text, voice or music service, whatever the
environment holds. One commit, not pushed, `VERSION` 17, fill output untouched.

## What was found

The review project's stored Check (`prj_e95348a97316/check.json`, read only, never re-Checked) listed
four speech attempts: `apple` ("No transcript returned."), `whisper` ("Speech engine is not
available."), then `openrouter` twice (`ffmpeg is not installed or not on PATH.`, then "No transcript
returned."). The route came from `workflow_config.DEFAULT_WORKFLOWS["stt"]`, whose third entry was
`{"provider": "openrouter", "model": "openai/whisper-large-v3-turbo"}` under the comment "Cloud
fallback for machines without a local engine", and from `STT_PROVIDERS` listing `openrouter`.
`stt._cloud_speech` built the mp3 and read the key from the environment through `_SECRET_ENV`, so no
audio left this time only because no key was set.

## What changed

| File | Change |
|---|---|
| `duckcore/engine/stt.py` | Deleted `_cloud_speech`, `transcribe_cloud`, `_multipart`, `_deepgram_payload`, `_stt_workflow_model`, the three key getters, `CLOUD_STT_PROVIDERS`, `OPENROUTER_STT_MODEL`, the three endpoint URLs and the `urllib`/`base64` imports. `normalize_engine` returns `None` for any name outside `apple`/`whisper`, so `resolve_routes` can only ever yield those two. `_whisper_env` now always sets `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` / no telemetry, so an uncached model fails the read instead of reaching the hub. |
| `duckcore/engine/workflow_config.py` | `STT_PROVIDERS=("apple","whisper")`, `TTS_PROVIDERS=("local",)`, `TEXT_PROVIDERS=()` and `MUSIC_PROVIDERS=()`; `DEFAULT_WORKFLOWS` keeps only local routes. A saved cloud route is dropped by `_normalize_route` and the local default is restored. |
| `duckcore/engine/pipeline.py` | Removed `_cloud_speech`, the `transcribe_cloud` alias, `CLOUD_STT_PROVIDERS`, the `urllib` import and the cloud dispatcher branch. `stt_error` is the plain “Speech was not read.”, the stage line says the same, and `llm_rank_hooks` no longer owns a text-service call (`llm_available()` is always False). |
| `duckcore/engine/settings_store.py` | `_SECRET_ENV` is empty and `get_secret` returns "". The settings API (`settings_path`, `load_settings`, `save_settings`) is unchanged. |
| `duckcore/engine/usage_store.py` | Cloud price tables and per-call rates are empty/zero; the ledger API is unchanged. |
| `tests/test_local_only_network.py` | New, 8 tests, written before the fix. |

## Every outbound call site

**`duckcore/`**

| file:line | host / URL | trigger | verdict |
|---|---|---|---|
| `packs.py:201` | 5 fixed URLs: `github.com/thewh1teagle/kokoro-onnx`, `huggingface.co/Carve/LaMa-ONNX`, `huggingface.co/mlx-community/whisper-large-v3-turbo` | `POST /api/packs/{id}/download` ← Settings button | **allowed** — user-started pack download, fixed URL per pack id, size + sha256/git-sha1 checked |
| `model_slots.py:68` | loopback only (`127.0.0.1`, `localhost`) | a user model slot save/check | **allowed** — `providers.local_base_url` refuses any other host, credentials or query before the request is built; redirects refused |
| `main.py:2152` | `bind("127.0.0.1", port)` | sidecar start | **inert** — inbound listener, no outbound call |
| `providers.py:5` | none (`urlsplit`) | URL validation | **inert data** |
| `licenses.py:37-40` | `ffmpeg.org` | none | **documentation** (source offer text) |
| `workflow_config.py:29-31` | none (migration map) | normalization | **inert data** — no route can resolve to it |

**`static/duck/`**

| file:line | host | trigger | verdict |
|---|---|---|---|
| `app.js:195` | same-origin `127.0.0.1:<port>` sidecar | every `/api/*` call | **allowed** — local route with the launch token |
| `app.js:679` | relative `/api` preview URL | Clean preview | **allowed** — local route |
| `app.js:2219, 2282, 4456, 4486, 4943, 5046` | relative `/api/...` | sfx upload, audio file, append, project upload, music, SRT | **allowed** — local routes |
| `index.html:8,20` | `/assets/app.css`, `/assets/app.js` | page load | **local asset** |

No `WebSocket`, `EventSource`, `XMLHttpRequest` or `sendBeacon` exists in `static/duck`, and no
`http(s)://` literal remains there.

## Brief items

| Item | Result |
|---|---|
| 1. Find how the route list was built, why `openrouter` was in it, read only `check.json` | **PASS** — default STT ladder plus `STT_PROVIDERS`; stored Check read, project never re-Checked |
| 2. Make any cloud speech/text/voice/music service unreachable | **PASS** — code deleted, not gated; empty ladders where no local model ships |
| 3. Audit every outbound call in `duckcore/` and `static/duck/` | **PASS** — table above; only pack downloads and loopback slots remain |
| 4. Plain failure copy, no model name | **PASS** — `stt_error` = “Speech was not read.”; Edit transcript box says “No speech was read. Run Check again, or add a speech engine in Settings.” |
| 5. Tests: no call with keys set, routes never cloud, slots refuse non-loopback | **PASS** — 8 tests; on the pre-fix tree the same file gives 5 failed, 3 passed, the first failure printing `https://openrouter.ai/api/v1/audio/transcriptions` |
| 6. Docs | **PASS** — this file, `MEMORY.md`, `TODO.md`; `PRODUCT.md` needs no edit (line 67 already reads “Cloud · None. Nothing uploads”) |

## Verification

```
python3 -m pytest -q tests                     # 361 passed
python3 -m pytest -q tests/test_local_only_network.py   # 8 passed
python3 -c "import duckcore.engine.pipeline, duckcore.engine.stt, duckcore.engine.workflow_config"  # ok
grep -rnE "openrouter|api\.groq\.com|api\.deepgram\.com|elevenlabs|minimax" --include=*.py duckcore  # no hits
node --check static/duck/app.js                # pass (not touched)
```

Regression proof: the same test file run against `git archive HEAD` (the pre-fix tree) fails 5 of 8,
with the network assertion naming openrouter. Group 3 (model slots) passed before and still passes —
`model_slots.py` was already loopback-only and is untouched.

## What got worse

- Settings → Workflows now shows empty ladders for text, music and the story script; no local model
  ships for those, so the empty list is the truth, but the screen does not explain it yet.
- An uncached Whisper model id now fails the read instead of downloading weights mid-Check. That is
  the local-only rule, but a user who typed a model id by hand will see a failed read.
- `stt_error` is always the plain sentence, so “pack not installed” no longer appears in the engine
  summary; `stt_errors[]` keeps the detail for diagnostics.

## What was not tested

- No Check or render was run on the review project; the no-network proof uses a 1 s synthetic WAV.
- Apple Speech and the bundled Whisper were stubbed to fail in the test; a real successful read was
  not exercised this round.
- The test patches `urllib.request.urlopen`; a raw socket or `build_opener` call inside the speech
  pass would not be caught by group 1 (group 3 covers `build_opener` only for model slots).
- Nothing was measured on the Swift shell or WKWebView; the audit is the Python core and the shipped
  front-end bundle.

## Reviewer

Signed off after one reject (docs gate and the dead `audio._workflow_text` body). The reviewer's
call-site table, the two test runs and the diff findings are recorded above; the remaining LOW notes
are open in `TODO.md`.
