# Review · R2 follow-ups — voice fallback shown, names right

Owner: OpenCode · branch `oc/r2-followups` · base `ccf4314` (brief `b296170`).
Request: REQ-20261125-03. A retired Kokoro voice falls back to the macOS default;
four places did not show or name that fallback.

## What changed

- `duckcore/main.py` — the dub handler names the track from the track's resolved
  `voice`, not the requested voice: `Dub · macOS default`, not `Dub · kokoro:…`.
  The notice was already spread into the track by `voice.build_track`; the
  preview and voice handlers already returned it unchanged.
- `static/duck/app.js`:
  - `generateVoice` shows the server notice as its own toast, then the success
    toast after the notice clears; the success toast uses `data.voice.voice`
    (the resolved voice) with `state.voiceName` only as a fallback.
  - `previewLine` shows `data.preview.message` as a toast when present.
  - the `/dub` call shows `data.dub.message`, else the existing success line.
- `mac/DuckSuite/DuckSuite/AppModel.swift` — the voice folder precheck now
  requires `kokoro-v1.0.onnx`, `voices-v1.0.bin` and `tokenizer.onnx`, matching
  `duckcore/model_slots.py` (`FILES['voice']` plus `VOICE_FRONTEND`). The
  existing message already names every missing file.
- `requirements-duck.txt` — removed `kokoro-onnx>=0.4`.
- `tests/test_voice_fallback.py` — new; `say`, `_synthesize`, `_to_wave`, `_fit`
  and `_duration` are stubbed. No real audio and no media files.

## Kokoro hits left after the grep

`grep -rn "kokoro_onnx\|kokoro-onnx" duckcore scripts mac requirements*.txt`:

- `duckcore/voice.py:36` — the retirement detector itself
  (`name.lower() in {… "kokoro-onnx"}`); required to recognise an old saved voice.
- `scripts/build-duckcore.sh:29` — `--exclude-module kokoro_onnx`; a build script,
  out of scope for this loop.

No hit in `mac/` or `requirements-duck.txt`.

## Pass or fail per item

1. Generate and preview — **pass**. Notice is the server's `message`, shown by
   `toast` unchanged. Success toast uses the resolved voice name.
2. Dub — **pass**. Track name is `Dub · macOS default`; the response carries
   `message`, the UI shows it.
3. Swift — **pass**. `tokenizer.onnx` added; files read from `model_slots.py`.
   `swiftc -parse` passes. The Swift UI was not opened, so the precheck was not
   clicked by hand.
4. Requirements — **pass**. `kokoro-onnx` removed; remaining hits listed above.
5. Tests — **pass**. The three fallback cases and the requirements check run with
   stubs.
6. Checks:
   - `python3 -m pytest -q tests` — 422 passed, 2 skipped.
   - `node --check static/duck/app.js` — passes.
   - `swiftc -parse mac/DuckSuite/DuckSuite/AppModel.swift` — passes.

## Not tested

- No app launch (per brief), so no on-screen look at the toast, the delayed
  success toast, or the Swift folder picker. Browser path not exercised; only
  `node --check` and source review.
- No real `say` render, no Kokoro folder import. Tests replace the audio steps.
- The new test count is 422 (was 418); the report row is the PO's to add.
