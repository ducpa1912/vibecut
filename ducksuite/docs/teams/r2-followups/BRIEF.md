# R2 follow-ups · voice fallback shown, names right (REQ-20261125-03)

Owner: **OpenCode**. Folder `drop_eval/ducksuite-opencode`, branch `oc/r2-followups`.
Founder, 2026-11-26: "R2 follow-ups". R2 (`d7e7f07`) took the Kokoro voice out of v1. A saved Kokoro voice now
falls back to the macOS default voice: `duckcore/voice.py` `_resolve_voice` returns a notice
`{"message": ...}`. Four places still don't match.

## Files you own
- `static/duck/app.js`: only `generateVoice`, `previewLine` and the dub call that uses `/dub`. Codex
  does not touch `app.js` in its loop.
- `duckcore/main.py`: only the dub handler (about lines 1580–1612) and the two voice handlers
  (`/voice/preview` about line 1522, `POST /voice` about line 1901) if they drop the notice.
- `duckcore/voice.py`: only to pass the notice through. `build_track` and `preview_line` already compute it.
- `mac/DuckSuite/DuckSuite/AppModel.swift`: only the `task == "voice"` file list (about line 167).
- `requirements-duck.txt` line 7.
- `tests/test_voice_fallback.py` (new), `docs/teams/r2-followups/review.md`.

Do **not** touch `duckcore/engine/stt.py`, `duckcore/packs.py`, `duckcore/model_slots.py`,
`engine_status` in `main.py`, the build scripts, or the transcription line in `AppModel.swift`.
Codex is changing those in P-B.

## Done looks like
1. **Generate and preview.** When the server returns a fallback notice, the UI shows its message
   as a toast. The message is the server's text, not a new string in `app.js`. The success toast
   names the voice actually used.
2. **Dub.** The dub track's `name` is `Dub · <voice actually used>`: the resolved name, not the
   requested one. The response carries the notice, and the UI shows it the same way.
3. **Swift.** The user's voice folder precheck asks for the same files the core needs today.
   Read `duckcore/model_slots.py` for the voice slot (it needs `tokenizer.onnx`). Don't guess.
   The error names the missing files.
4. **Requirements.** Remove `kokoro-onnx` from `requirements-duck.txt`. Run
   `grep -rn "kokoro_onnx\|kokoro-onnx" duckcore scripts mac requirements*.txt` and list in
   the review every hit that is left.
5. **Tests.** `tests/test_voice_fallback.py` covers, with `say` and the audio steps stubbed:
   - the dub track name and notice from a saved Kokoro voice;
   - the preview and generate responses carrying the notice;
   - the notice being absent for an ordinary macOS voice.
   Also check that `requirements-duck.txt` has no Kokoro. No real audio, no media files.
6. **Checks.** These pass:
   - `python3 -m pytest -q tests`
   - `node --check static/duck/app.js`
   - `swiftc -parse` on `AppModel.swift`, or say in the review why it couldn't run.

   **Do not open the app. Do not start the server on the PO's port.** If you check by hand, use
   your own port 8821 and `build/scratch-root`.

## Notes
- Base: `ducksuite` at `ccf4314` or later.
- Commit on `oc/r2-followups` with `git -c commit.gpgsign=false commit`. Don't push.
- Write `docs/teams/r2-followups/review.md`: what changed, pass or fail for each item, and what
  wasn't tested. Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`.
