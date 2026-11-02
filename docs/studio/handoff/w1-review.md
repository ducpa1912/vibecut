# Wave 1 review (Claude Code)

**Base:** `wave-1-base` (`2ab7ab3`, 870 tests). **Result:** merged in order T1 → T2 → T3 → T4. After the merge, `main` has 1004 tests passing, `compileall` passes, and `node --check` passes on `static/studio/*.js`.

All four branches stayed inside their WORKPLAN §3 ownership lists. The only `app.py` changes were import and include lines.

## T1 Core model (`rv/w1-t1-core`): fixed on branch (`135f1d7`)
1. **P1: concurrent saves could fork the version chain.**
   - Cause: `_persist` set the pointer without checking that the head was still the edit's parent. Two quick saves from the editor (autosave plus a click) would leave an orphaned version, and the later save would silently win.
   - Fix: the pointer is now set with compare-and-swap inside `update_job`. A stale head returns 409, and history is only appended after the pointer moves.
   - Test: `test_stale_head_is_refused_instead_of_forking`.
2. **P1: `DELETE` hard-deleted every immutable version and its history.**
   - Why that's wrong: rendered artifacts will reference `edit.hash` (Wave 4), so deleting versions breaks lineage.
   - Fix: `DELETE` now only clears the story/aspect pointer. Versions stay on disk.
   - Test: `test_delete_clears_pointer_and_keeps_immutable_versions`.
3. **Carry-over for W2 T1:**
   - Motion compiles to `zoompan` after the scale. `zoompan` rounds x/y to whole pixels, so a slow push can jitter.
   - Check it in a real render, and switch to a crop-window expression on the scaled frame if it visibly steps.

## T2 Audio split (`rv/w1-t2-audio-split`): fixed on branch (`4047029`)
1. **P2: callers outside T2's files still used removed engines.**
   - `app.py`: removed the dead `_install_argos_safe`. The `/api/audio/music` and `/api/audio/beats` defaults change from `cc0` to `library`.
   - `cli.py`: removed the `argos`/`marian`/`ollama` and `cc0`/`stable-*`/`musicgen` choices, plus the Argos audit and removal hints.
   - On `main` after the merge: removed the Classic `cc0` `<option>` in `static/index.html`.
2. **Carry-over for W2 T3 (settings migration):**
   - `workflow_config._TEXT_ROUTES` still lists `local-mlx`.
   - The founder's `data/settings.json` puts `local-mlx` first for `story_brief`.
   - It's harmless at runtime because `_workflow_text` skips unknown providers, but the admin dropdowns still offer it. Migrate it and remove it.
3. **Carry-over for docs:** README still documents Argos/Marian/Ollama/`cc0`/MusicGen/`VIBECUT_LLM_URL`. Fix this with the W2 T3 engine-removal docs.
4. **Carry-over for W2 T3:** Classic `static/app.js` still labels removed engines (`argos`, `stable-small`, `musicgen-small`, `cc0`). Selecting one fails safe (empty list or no music). Remove them together with the TTS removals.

## T3 Check backend (`rv/w1-t3-check`): accepted as is
- OCR boxes are top-left normalized. This matches `normalizeBounds` in `tools/vision_probe.swift`.
- The run is async on its own single-worker scheduler.
- `job.json` stores only the report path, not the report.
- Watermark and handle policy key on the detected kind, and an unconfirmed text pass never reports "clean".

## T4 Studio shell (`rv/w1-t4-studio-shell`): accepted as is
- `innerHTML` only receives constant copy.
- Token handling matches Classic (Bearer header; cookie for GETs).
- **Live smoke test (temporary data dir):**
  - Studio is the default, and the rail shows the 5 steps.
  - Classic scripts don't load in Studio mode.
  - `?classic=1` loads Classic, and `?studio=1` returns to Studio.
  - No console errors other than the existing `favicon.ico` 404.
- **Carry-over for W3 T2:** rights attestation is stored in `localStorage` only. The Clean backend must store it on the job and enforce it on the server.
