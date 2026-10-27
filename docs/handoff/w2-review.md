# Wave 2 review (Claude Code)

**Base:** `wave-2-base` (`eb13302`, 1004 tests).
**Result:** merged T1 → T4.

**Checks on `main`:**
- 1088 tests pass, 1 skipped (the live STT test, opt-in).
- `compileall` passes.
- `node --check` passes for Studio and Classic JS.

**Live end-to-end run** on a real server, with a 29 s synthetic talk video that has a burned-in "OLD CAPTION":
- import, then analysis with Apple STT;
- Check returned `clean_then_compose` and found the caption as a tracklet with a correct box;
- clip set, then an Edit with a plate, `warm_film`, a punch-in and a hook;
- frame endpoint in 1.3 s: the plate covers the old caption across the whole 9:16 crop, and the hook text renders literally;
- 540p proxy in 6.2 s;
- the Studio Edit screen loads with preview and controls, and no console errors other than `favicon.ico`.

## T1 Render hooks: accepted as is
- `perspective` motion has about 7× less step jitter than `zoompan` (measured), and the legacy path is unchanged.
- There is a real-ffmpeg render test, and the frame endpoint matches the final render at SSIM ≥ 0.98.
- **Carry-over (W3):** nothing calls `render_reel(edit=…)` yet. The story render (`POST …/stories/{story_id}/render`) and the story queue must render the story's current Edit for its aspect. Assigned to W3 T1.
- **Carry-over (W5 perf):** the frame endpoint renders the whole containing segment for one frame (cached), and the proxy builds synchronously in the request. This is fine at the sizes tested; re-measure on a 90-minute source.

## T2 STT: fixed on branch (`6b8c0ff`)
1. **P0: the new Apple helper aborted on every real run.**
   - It failed with `freed pointer was not the last allocation` (exit 134) whenever it was built with `-O`, which is how `_apple_transcribe_helper` builds it. It works at `-Onone`.
   - Cause: walking `AttributedString` runs inside the `for try await` loop, which hits task-allocator misuse in the optimized async frame.
   - Fix: run-walking moved into a synchronous `@inline(never)` helper.
   - Verified live: 12 words with real timings and confidence, with and without `--vocabulary`.
   - The unit tests use a fake helper, so they could not catch this. Added the opt-in `test_live_apple_helper_emits_word_timings` (`VIBECUT_LIVE_STT=1`).
2. The ownership exception for `tests/test_audio_split.py` is accepted: the W1 assertion was invalidated by this track's mandate.

## T3 TTS + engine removal + packs: fixed on branch (`45d93de`) and on `main`
1. **P1: the migration dropped the founder's Whisper fallback.**
   - The old STT route `auto: whisper-small-mlx` became `apple`, was de-duplicated, and disappeared.
   - Fix: an `auto` route that names a Whisper model now migrates to `whisper` with large-v3-turbo. The default `stt.model` is now turbo.
   - Test added. Verified on a copy of the founder's real `data/settings.json`: STT routes are now `apple` then `whisper` turbo, `local-mlx` and `piper` are gone, and the file is written back exactly once.
2. **P2 (on `main`, in files T3 didn't own):** removed engines were still live.
   - `audio.engine_status()` still listed Piper, OpenAI, Groq, Deepgram and Cartesia voices. It now uses `tts.voice_engine_status()`.
   - The dead adapters (`_piper_voice`, `_openai_voice`, `_groq_voice`, `_deepgram_voice`, `_cartesia_voice`), `piper_available`, `cartesia_key` and the Piper voice dir are removed from `tts.py` and `audio.py`, along with their tests.
   - Also cleaned: `app.py` `TTS_PROVIDERS`, the settings-test candidate lists, the `cli.py` `--voice-engine` choices, and the Piper row in `admin/catalog.py`.
   - The Groq and Deepgram keys stay, because they are STT providers.
3. **Carry-over (W3 T3 / W4 T4):** packs install and verify, but no engine finds its runtime inside an installed pack yet. `mlx_whisper` is still found on `PATH`, and Kokoro still loads from `data/models/kokoro`. Engine discovery must check `packs.pack_dir(...)` first.
4. **Carry-over (W5 T2):** the built-in pack manifest has empty `sha256` pins and no URLs. Installs correctly refuse until release packaging publishes pinned archives.

## T4 Studio Edit: accepted; wired on `main`
- `static/studio/edit.js` is now a re-export of `./edit/index.js`. T4 could not edit the shell's placeholder.
- No interpolation into `innerHTML`. Saves handle the W1 409 contract with one reload-and-retry.
