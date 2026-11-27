# Local-only speech and network audit — REQ-20261118-02 (2026-11-18)

Founder: "Yes, send it" (to the sub-leader's question "Send the local-only fix for Check's speech to
OpenCode?"). Hard rule 1: local only, no upload, no telemetry, no account. Built by OpenCode with its
agent team; the sub-leader verifies.

## What was found (sub-leader, 2026-11-18)

- The review project's stored Check (`prj_e95348a97316/check.json`, `result.engine.stt_errors`) lists
  four speech routes: `apple` (no transcript returned), `whisper` (not available), then **`openrouter`
  twice** (ffmpeg not on PATH; then "No transcript returned").
- No audio left the Mac this time. `duckcore/engine/stt.py` `_cloud_speech` (around line 1467) makes
  the mp3, then returns None when `settings_store.get_secret(name)` is empty. Keys come only from
  environment variables (`duckcore/engine/settings_store.py` `_SECRET_ENV`: OPENROUTER_API_KEY,
  GROQ_API_KEY, DEEPGRAM_API_KEY, MINIMAX_API_KEY, ELEVENLABS_API_KEY).
- **The gap:** a core started from a shell with one of those variables set would POST the audio to
  openrouter.ai, api.groq.com or api.deepgram.com. These routes are legacy from vibecut:
  `CLOUD_STT_PROVIDERS`, `workflow_config.py` (`STT_PROVIDERS`, `TEXT_PROVIDERS`, `TTS_PROVIDERS`,
  `MUSIC_PROVIDERS`), `usage_store.py`, `pipeline.py:1443`.

## Do

1. Find how the route list for a DuckSuite Check is built and why `openrouter` was in it. Read only
   the stored `check.json`; do not re-Check the review project.
2. Make DuckSuite unable to reach a cloud speech, text, voice or music service at runtime, whatever is
   in the environment, settings files or saved route lists. Prefer removing the cloud code paths from
   the DuckSuite core. If something must stay, make it unreachable and say why in the review.
3. Audit **every** outbound network call in `duckcore/` and `static/duck/`. The only allowed ones are:
   - pack downloads the user starts in Settings (`packs.py`, fixed URLs, hash-checked);
   - user model slots to a loopback URL (`model_slots.py`): confirm non-loopback hosts are refused;
   - anything else the founder already approved, named with its commit.
   List each call site, its host and the verdict in the review.
4. When every local speech route fails, Check says so plainly in its report and in the Edit
   Transcript box, as today, with no model name. It never tries a cloud route.
5. Tests:
   - with every key variable above set to a dummy value and `urllib.request.urlopen` patched to fail
     the test if called, a Check speech pass with failing local engines makes **no** network call;
   - route resolution never returns a cloud provider for any input, including the names `openrouter`,
     `groq`, `deepgram`, `auto` and saved route lists that contain them;
   - model slots refuse a non-loopback URL.
6. Docs:
   - `MEMORY.md`: REQ-20261118-02 with its outcome;
   - `TODO.md`;
   - `docs/teams/local-only-stt/review.md`: the call-site table, pass or fail per item, what got worse,
     what was not tested;
   - `PRODUCT.md`, if a row claims cloud speech.

## Rules

- One commit. Do not push. Fill output is unchanged: `VERSION` stays 17.
- Another Claude session is committing Edit-screen work in this repo right now (commits `907d4b6` to
  `3552137`, mostly `static/duck/app.js` and `app.css`). Touch only the files this brief needs, stage
  only your own files, and never stash, reset or switch branches.
- Never read `old_*.md` or `docs/reports/*.html`. No founder media in Git.
