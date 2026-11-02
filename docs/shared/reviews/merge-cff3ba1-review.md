# Merge review — `5947af3..cff3ba1`

Scope: the combined push on `feat/voice-extract-bundle` / `main` (47 files, ~7.9k lines), plus the planned R3 branches based on `7e998d1`.
Read-only review. No code, commits or `ROADMAP.md` changes. This file is the only write.

Method: read the hand-resolved merges and every changed call path end to end; ran the focused suites, Node syntax checks and small read-only probes. `git merge-tree` and `git merge-file --diff3` were used for the R3 conflicts. T4 was uncommitted when the review started and was committed as `21fc3d5` during it; the review uses that commit.

Tests run on `cff3ba1`:

```text
python3 -m pytest -q tests/test_voice_clone.py tests/test_voice_extract.py \
  tests/test_voice_extract_acceptance.py tests/test_tts.py tests/test_stt.py \
  tests/test_story_speech.py tests/test_silent_script.py tests/test_mix.py \
  tests/test_render_cache.py
169 passed, 6 skipped in 16.29s

python3 -m pytest -q tests/test_studio_js.py tests/test_workflow_routes.py \
  tests/test_edits.py tests/test_story_queue.py
87 passed in 4.36s

node --check static/studio/edit/layers/audio.js \
  static/studio/voiceclone.js static/studio/voiceroom.js
OK
```

## Summary

| Severity | Count |
|---|---:|
| blocker | 0 |
| high | 3 |
| medium | 6 |
| low | 9 |
| nit | 1 |

Verdict: **`main` is safe to build on, with caveats.** No blocker was found in the merged code; the combined suite passes and the two hand-resolved merges kept both sides. The damage is concentrated in the clone lifecycle: a deleted clone silently becomes a stock HeyGen voice, the extraction cache is invisible to pruning and grows on every upload, and Demucs uses one shared scratch directory, so concurrent extractions can delete each other's output. Fix those before the R3 merge, because the R3 render paths add more callers of the same extraction cache.

Top 3 actions:

1. **Make clone deletion safe.** A deleted sample must stop cached speech and must never fall back to `nadine`. Purge or namespace the per-clone voice cache, and fail loudly when a clone id is missing (F1).
2. **Make `voice_refs` and `cache/voice-clone` part of cache hygiene.** Add them to `CACHE_DIRS`, stop caching temp upload paths, and report their size (F2).
3. **Give Demucs a per-run scratch directory** (or a lock). One shared `cache/stems/run` cannot survive clone upload + render at the same time (F3).

## Findings

Sorted by severity, then confidence.

| ID | Severity | Confidence | file:line | What is wrong | Evidence | Suggested fix | Missing test |
|---|---|---|---|---|---|---|---|
| F1 | high | high | `tts.py:929-951`, `voice_clone.py:287-303`, `audio.py:2996`, `tts.py:711` | Deleting a cloned voice does not stop it. New lines silently speak as stock HeyGen `nadine`; already cached lines keep playing the deleted clone's audio. Opening the Edit panel after deletion also auto-selects a stock voice and can save it over the edit. | Read end to end. Ran a temp-data script: create clone → delete → `tts.synthesize_line("heygen", voice_id, ...)`; captured request body had `voice: "nadine"` and no `input_references`. `delete_clone` only unlinks the sample and record; `synthesize_line` checks the cache before `is_clone`, so cached `.flac` files remain. `audio.js:362-380` replaces a missing clone with the first stock voice. | Add a tombstone so `_openrouter_voice` raises `AudioError("cloned voice was deleted")`; store clone speech under `CACHE/voice/<clone_id>/` (or include the sample hash in the key) and remove that directory in `delete_clone`. Clear the edit's voice when the id is gone instead of auto-picking stock. | `test_deleted_clone_never_speaks_as_a_stock_voice` (same text cached and new text), and `test_edit_panel_does_not_replace_a_missing_clone_with_stock`. |
| F2 | high | high | `audio.py:3416-3455`, `voice_extract.py:160-187`, `routes_voice_clone.py:91-94, 265-300, 468-485` | `cache/voice_refs` is never pruned or counted, and every “My voice” upload and range clone writes a new permanent entry. The cache fingerprint contains the resolved source path, and `_work_dir()` gives every request a fresh UUID, so upload entries can never be reused. An upload that triggers the residual-separation branch writes two entries. `cache/voice-clone` is also outside `CACHE_DIRS`, so a crashed request leaks there too. | Read end to end. `CACHE_DIRS = ("segments", "voice", "stems", "music", "masters", "translate")`; startup calls `audio.prune_cache()` (`app.py:3094`). `_fingerprint` includes `"path": str(source.resolve())`. `extract_clean_voice`/`find_voice_candidates` write the cache even with `use_cache=False`. Candidate output is then copied again into `data/jobs/<id>/voice-candidates`. | Add `voice_refs` and `voice-clone` to `CACHE_DIRS` (and `cache_usage`); key uploads by content hash, not temp path; pass `use_cache=False` for one-shot uploads if they must not persist; keep one copy (cache or job dir), not both. | `test_prune_cache_removes_voice_refs`; `test_my_voice_upload_leaves_no_permanent_cache_entry`; `test_cache_usage_includes_voice_refs`. |
| F3 | high | high | `audio.py:984-985, 1024`, `voice_extract.py:221`, `routes_voice_clone.py:278` | All Demucs separations share `CACHE/stems/run`. Each run starts with `rmtree` and ends with `rmtree`, so a render/speech separation, a candidate search and a “My voice” upload running together can delete each other's stems. The losing run fails with “Demucs finished but no … stem was found” or reads the other run's files. | Read `_separate_stem` end to end. `output_dir = CACHE / "stems" / "run"` is fixed; `separate_voice` is now called from the candidate worker, the clone upload path and render (`separate_vocals`). Demucs is installed in this checkout, so the path is live. Not executed concurrently during review. | Use `CACHE/stems/run-<uuid>` (or a lock around the Demucs section) and remove only that directory. | `test_two_concurrent_separations_do_not_share_scratch` (threads with fake `_run`). |
| F4 | medium | high | `stt.py:1796-1812`, `app.py:314-327` | An explicit language chosen at import is treated as the default and can be overridden by a title guess. `clean_options` stores `speech_language` but never sets `speech_language_explicit`; `speech_language_for` only trusts the explicit flag. | Ran: `stt.speech_language_for({"speech_language": "en"}, {"name": "東京の夜"})` → `"ja"`; adding `"speech_language_explicit": "en"` → `"en"`. Only `app.py:5945` (re-transcribe) sets the flag. | Set `speech_language_explicit` when the import request carries a language (or compare against the untouched settings default); keep the title guess only for the untouched default. | `test_import_explicit_english_beats_a_japanese_title`. |
| F6 | medium | high | `tts.py:493-503, 686-700, 925-951` | A clone id is engine-specific, but `_tts_voice_for` passes the preferred voice to whichever engine is primary. With an `auto`/legacy plan, a clone id can be sent to MiniMax/ElevenLabs as a normal voice id; on a HeyGen fallback the clone is replaced with the stock default and no warning is emitted. | Ran: `_tts_voice_for("minimax", clone_id, "heygen")` → `"female-shaonv"`; `_tts_voice_for("say", clone_id, "heygen")` → `"Samantha"`. `build_bed` uses this per candidate. The clone picker writes `engine: heygen`, so the common path is safe; legacy/API plans are not. | Treat `voice_clone.is_clone(voice)` as a constraint: keep HeyGen first or fail with a clear message; never pass a clone id to another engine. Emit a `_warnings` entry when a clone falls back. | `test_clone_voice_is_never_passed_to_a_non_heygen_engine`; `test_clone_fallback_engine_warns`. |
| F7 | medium | high | `app.py:6682-6686, 6721-6729` | A written script forces `voice_over` on every story render, even when the story's Edit explicitly saved `audio.mode = "original"`. `plan_from_edit` returns a keep-mode plan, the code turns it into `None`, and `_scripted` then inserts voice-over. | Read: `edit_audio_plan = audio.plan_from_edit(...)`; `mixer_mode("original") == "keep"` → set `None`; then `if edit_audio_plan is None and _scripted(job)` adds voice-over. A music-only video with a script and an explicit “keep the original sound” edit will speak over the music. | Distinguish “no audio layer” from “explicit keep”: only apply the scripted default when `edit is None` or `edit.get("audio")` is absent. Add an explicit opt-out flag if the creator can keep silence. | `test_scripted_job_with_edit_audio_original_keeps_the_original`. |
| F8 | medium | high | `routes_voice_clone.py:321-328`, `voice_extract.py:202-205, 793-840` | Candidate search accepts a job with no audio stream. `_source_audio_bed` now fabricates silence for that source, so the worker runs decode, Demucs and denoise over the whole video before VAD returns “No speech was found”. This is exactly the silent-video case the script feature creates. | Read: `start_candidate_search` checks `source.is_file()` only. `_decode` calls `_source_audio_bed`, which creates `anullsrc` silence when there is no audio stream. Demucs is available here. | Reject early when `source.has_audio` is false (and when `media_duration` is 0) with a clear 400. | `test_candidate_search_refuses_a_video_with_no_sound` and asserts no extraction worker starts. |
| F9 | medium | high | `app.py:5921-6000` (`/transcribe`), `app.py:6013-6060` + `silent_script.py:419-470` (`/script-brief`), `routes_voice_clone.py:239-317` (`/api/voices/clones`) | Three new routes do minutes of work inside the request handler with no queue task and no cancel: re-transcribe bypasses `analysis_pool`; script writing can run `ceil(beats/40)` model calls at 240 s each; My voice cleaning can run DeepFilterNet/Demucs synchronously. Re-transcribe can also run alongside analysis and compete for CPU/network. | Read: all are synchronous `def` routes; `write_script` loops chunks; `clone_my_voice` calls `extract_clean_voice(separate="best")`. Only the candidate search is submitted to a pool. | Run these on a small extraction/STT pool with progress and cancel, or at least cap time and show “continue in background”. For re-transcribe, reuse the analysis scheduler with a dedicated kind/key. | `test_transcribe_route_does_not_block_the_analysis_pool`; `test_script_brief_is_cancelable`. |
| F5 | medium | medium | `voice_clone.py:200-218, 309-322`, `routes_voice_clone.py:265, 300, 427, 429, 468, 485` | Clone samples are stored as `.mp3` but can contain a WAV container, then are sent as `data:audio/mpeg`. `prepare_sample()` chooses the muxer from the output suffix; the routes pass `sample.wav`, so ffmpeg writes MP3 frames in a RIFF/WAV wrapper. `speech_fields` declares `audio/mpeg` unconditionally. | Ran real ffmpeg: `prepare_sample(tone.m4a, sample.wav)` produced `RIFF…WAVE`; `ffprobe` reports `format_name=wav`, `codec_name=mp3`. Existing tests only call `prepare_sample` with `.mp3` and fake the clone sample bytes. Remote acceptance is unverified. | Name the prepared file `sample.mp3` (or add `-f mp3`), and derive the data-URI MIME from the actual file. | `test_clone_sample_is_a_real_mp3` (`ffprobe format_name == mp3`) and `test_speech_fields_mime_matches_the_sample`. |
| F10 | low | medium | `app.py:5921`, `routes_voice_clone.py:537-555, 599-620` | `POST /api/jobs/{id}/transcribe`, `POST /api/voices/clones/{id}/sample` and `POST /api/voices/sample` have no `_setup_origin_ok` check, while the other clone routes and `script-brief` do. They spend cloud credits and (for transcribe) rewrite job data. JSON content type makes a simple cross-site form hard, but the inconsistency removes the defence-in-depth the rest of the new surface has. | `grep -n "_setup_origin_ok"` shows the guard on `clone_my_voice`, `start_candidate_search`, `clone_video_voice`, `rename`, `delete`, `cancel`, `write_script_brief`; not on the three routes above. | Add `Request` + `_guard(request)` (or the app helper) to all three. | `test_cross_site_sample_and_transcribe_are_rejected`. |
| F12 | low | medium | `voice_extract.py:1226-1235, 1271-1319` | The candidate cache-hit path assumes candidate files are numbered `01..N` from the list length. A first run can skip a window (duration < `MIN_CLIP_SECONDS`) and store indices like `01, 03`; the next cache hit looks for `candidate-01/02`, and `_copy_cached` raises `FileNotFoundError`. | Read: `names = [f"candidate-{index + 1:02d}.wav" for index in range(len(cached["candidates"]))]` versus names built from `item["index"]` when writing. The gap requires a skipped window, so not reproduced. | Build the cache-hit names from each candidate's `index` (or never skip an index). | `test_candidate_cache_hit_after_a_skipped_window`. |
| F16 | low | medium | `audio.py:2798-2840` | The silent fallback depends on `ffprobe`. If `ffprobe` is missing, `_has_audio_stream` returns `True` (assume audio), and `_source_audio_bed` then runs ffmpeg with `-map 0:a:0`, which fails on a genuinely silent source. The scripted-story render then fails at the audio bed. | Read `_has_audio_stream`: no probe → `return True`; the silent branch is skipped. ffmpeg and ffprobe normally ship together, so this is a deployment edge case. | Detect the missing probe and use the silent fallback, or try the map and fall back to `anullsrc` on failure. | `test_silent_source_without_ffprobe_still_gets_a_silence_bed`. |
| F11 | low | high | `stt.py:763-786, 795-806` | The hallucination filter drops a single genuine “Bye.” (unconditional set) and drops “Okay.”/“You.”/“Thanks.” on their second occurrence, across Whisper and OpenRouter transcripts. A real closing line or repeated conversational word disappears from stories and captions. | `_HALLUCINATED_LINES` includes `"bye"`, `"bye bye"`, `"ta-da"`; `_REPEATED_ONLY_LINES` includes `"okay"`, `"you"`, `"thanks"` with `count >= 2`. The filter runs before segment/word construction. | Gate these on `no_speech_prob`/`compression_ratio`, or require 3+ repeats for short words; keep a single “bye” when speech confidence is normal. | `test_single_bye_is_kept`; `test_okay_twice_in_dialogue_is_kept`. |
| F13 | low | high | `routes_voice_clone.py:37-40, 345-353, 364-375` | The four `CANDIDATE_*` module dictionaries are unbounded and never pruned, and starting a second search overwrites `CANDIDATE_CANCELS[job_id]` so the first run can no longer be cancelled. Job deletion leaves the entries behind. | Read: no `pop` for `CANDIDATE_STAGES`/`CANDIDATE_CANCELS` on terminal state or job delete; `_candidate_state` reads these tables without a lock. | Keep one per-job record (stage, event, error, result) in a bounded LRU, cleared on job delete and on terminal completion; keep the event until the task is terminal. | `test_candidate_state_is_dropped_when_the_job_is_deleted`; `test_restarting_a_search_still_cancels_the_first_task`. |
| F14 | low | high | `voice_clone.py:74-76`, `audio.py:1398-1425`, `routes_voice_clone.py:561-596` | `voice_clone.available()` checks only the stored secret. It ignores `openrouter.enabled` and the auth quarantine, which `openrouter_media_available()` applies. The Voice Room can therefore offer cloning while speech is disabled/quarantined, create a clone (no network at creation) and only fail when the creator tries to speak. | Read both predicates. `voice_catalog` reports `clone_available = voice_clone.available()` while `tts.voice_engine_status()["heygen"]["available"]` is false in the same state. | Use `audio.openrouter_media_available()` for `voice_clone.available()` (or split “can store a sample” from “can speak”). | `test_voice_room_hides_cloning_when_the_key_is_disabled_or_quarantined`. |
| F15 | low | high | `static/studio/voiceclone.js:253-268`; `static/studio/voiceroom.js:141-146` | The server returns `warning`/`warnings` for a clone made from the raw recording, but the Setup panel and Voice Room drop them and say “Your voice is ready.” The Edit clone flow does show `record.warning`. | Compare `cloneFromVideo` handling in `audio.js:886` with `myVoice.submit` and `voiceroom.cloneVideo`, which ignore the field. `routes_voice_clone.py:315` returns both. | Show `record.warning` (and joined `warnings`) in the notice, with a “cleaned=false” hint. | `test_my_voice_panel_shows_the_server_cleaning_warning`. |
| F18 | low | high | `silent_script.py:29-30`, `admin/catalog.py:60-72` | The silent script hardcodes `google/gemini-3.5-flash-lite`, which is not in the OpenRouter admin catalog and not configurable. If that slug is retired or the admin changes the text routes, script writing breaks with a 502 while every other text feature follows the admin routes. | Read `MODEL` and the catalog; no `gemini-3.5` entry. `write_script_brief` passes the model through `write_script(model=MODEL)`. | Resolve the model from the `story_brief` (or a new `script`) workflow route, add it to the catalog, and keep a default only as a fallback. | `test_script_brief_uses_the_admin_story_brief_route`. |
| F19 | low | high | `tts.py:662-686`, `audio.py:3005` | `synthesize_story` is production-dead (only tests call it). It cannot carry clone metadata: `voice_candidates` returns only `engine`/`provider`/`model`, and no caller passes a clone voice through the route list. The real render path is `build_bed` → `synth_one`, which does handle clones. | `grep -rn "synthesize_story"` shows only `tts.py` and tests. `voice_candidates` return shape has no `voice`/`clone` field. | Either delete `synthesize_story` or make it take the voice separately and cover it with a clone test; document that routes never carry `input_references`. | `test_synthesize_story_with_a_clone_voice` (or remove the function). |
| F17 | nit | high | `audio.py:2840` | Adding `-map 0:a:0` changes multi-audio-stream sources from ffmpeg's default selection (most channels) to the first stream. Most files have one stream; a camera file with a scratch/comment track first would now mix the wrong audio under the voice. | Read the old command (no map) and the new one. | Probe the streams and map the intended audio stream (or keep ffmpeg's default selection); `0:a:0?` alone would silently produce no audio when the stream is missing. | `test_multi_audio_source_uses_the_intended_track`. |

## Not verified

- **Remote OpenRouter contract for clones.** No live call was made. The `input_references` payload, the `provider.options.heygen.language` field and whether OpenRouter accepts the WAV bytes under `audio/mpeg` are unverified. F5 is the local half of that risk. A single real request with a 10 s sample would verify it.
- **OpenRouter STT request shape.** `input_audio` + `verbose_json` + `timestamp_granularities` was not sent to the service. `tests/test_story_speech.py` mocks the reply only.
- **Demucs race (F3).** Not executed concurrently; Demucs is installed, but running two real separations would write to the checkout cache. The code path is unambiguous.
- **Deleted-clone behavior in a browser.** F1's server half was run; the Edit-panel auto-pick is read-only evidence.
- **T1/T2/T3/T4 branch suites** were not run in their worktrees; only `git merge-tree`/`merge-file` and the branch diffs were used.

## R3 merge plan

`main` is at `cff3ba1`; all four branches are based on `7e998d1`. `git merge-tree --write-tree` against `cff3ba1`:

| Branch | Content conflicts |
|---|---|
| `rv/r3-t1-dub-voice` | `static/studio/edit/layers/audio.js` (1 hunk) |
| `rv/r3-t2-library` | none |
| `rv/r3-t3-edit-finish` | none |
| `rv/r3-t4-progress-speech` | `pipeline.py`, `stt.py` |

### 1. `rv/r3-t2-library` — merge first

**Overlapping hunks.** `static/studio/shell.js`: T2 replaces the library dialog body (`#st-library-host`) and deletes `librarySearch`/`libraryList`/`loadLibrary`/`libraryRow`; `cff3ba1` adds `#st-voice-room` to the top actions. Auto-merge keeps both (verified in the merged tree: the Voice Room link is still at the top bar). No other file overlaps.

**Semantic clashes / gaps.**

- **The branch does not register its route.** `routes_library.router` is defined and `install(app)` exists, but no branch file calls either; `git grep routes_library rv/r3-t2-library` finds only the module and its docs. `library.js` calls `GET /api/artifacts`, so after a plain merge the Finished tab gets 404. `routes_library.install(app)` or `app.include_router(routes_library.router)` must be added in `app.py` (near the other router includes at ~3159). This is the one blocker in the R3 set.
- `openFinished(artifact)` sets the job and goes to Finish but cannot carry story/shape (the hash contract is only `#/<step>`); it opens the first story and default shape. No cff3ba1 conflict.
- T2 scans every job directory on each `/api/artifacts` request; unrelated to the voice work but a latency risk on a large data dir.

**Side to win.** Keep T2's shell rewrite (the old list code is removed cleanly). Add the app.py registration in the merge commit.

**Order reason.** It is the most isolated branch. Landing it first lets the one-line app.py registration be added before T3 makes app.py hot again.

### 2. `rv/r3-t3-edit-finish` — merge second

**Overlapping hunks.** `app.py` only: cff3ba1 adds `retranscribe_job`, `write_script_brief`, `_scripted` and the scripted branch in `_queue_story_render`; T3 adds `StoryRenderBackend.error`, the queue identity/ETA code, `create_story_queue` idempotency and the `_queue_render_locked_impl` duplicate-attach. Git merges both; no content conflict.

**Semantic clashes git will not flag.**

- **A queued item is not frozen.** T3's `StoryRenderBackend.start` calls `_queue_story_render` when the item starts, not when the queue is created; that call recomputes the edit and cff3ba1's `_scripted` voice-over at start time. Writing or changing a script while the story is queued therefore changes what the queued item renders, while `_story_queue_identity` (`job, set, story, aspect, quality`) stays the same. This is not data loss, but the queue row's identity no longer describes the plan that will run. Include the render/audio signature in the identity, or snapshot the edit/audio at queue time.
- **T3's `_queue_render_locked_impl` early return is additive.** `if existing.get("artifact_id") and not force: return existing` only applies to an active record under the same `record_key`, which already includes the audio signature. A newly written script changes that signature, so it still gets its own render. Keep the early return narrow; do not widen it to a different record key.
- T1's `story_queue.py` `_failure_text` expects `StoryRenderBackend.error`; T3 supplies it. Merge T3 before T1 so the hook exists, or accept that T1 alone still says “Render failed.”

**Side to win.** T3's queue changes; keep the identity decision explicit if the product wants the queue to keep the plan it was created with.

### 3. `rv/r3-t1-dub-voice` — merge third

**Conflicting hunk.** One conflict in `static/studio/edit/layers/audio.js`, in the panel's dispose function:

- `cff3ba1`: `stopClonePlayer(); stopClonePoll();`
- T1: `if (dirty && !saving && !dubBlockReason(plan.mode, targetLang)) {`

**Combine:** keep both. The result is `stopClonePlayer(); stopClonePoll(); if (dirty && !saving && !dubBlockReason(...))`. Choosing either side alone loses clone cleanup or the Dub guard.

**Overlapping but auto-merged.**

- `audio.js` `render()`/`voiceCard`: cff3ba1's `cloneBlock()` lives inside `voiceCard`; T1 moves `voiceCard` before `musicCard` and adds `dubCard`/`scriptCard`. The clone block moves with the voice card. T1's `storyLanguage` wrapper still exists for `cloneVideoVoice`.
- `audio.py`: T1 adds `script_overrides` to `plan_from_edit` and the `translate.source` override in `build_bed`; cff3ba1's `_source_audio_bed` signature and `voice_candidates` are in different regions. Clean.
- `edits.py` whitelist: only T1 changes it; no conflict.

**Semantic clashes.**

- **Dub can block the clone save.** T1 makes `save()` refuse a Dub edit with no target. cff3ba1's `useClonedVoice` ends in `scheduleSave()`. If the open edit is a legacy Dub without a target, cloning a voice sets the engine/voice but the save is refused; the UI says “Not saved — choose a target” and the clone pick is lost until the creator fixes the target. Show that as a notice in the clone flow, or refuse the clone until the edit is valid.
- **Script rows and clones are independent.** T1's `scriptPlan()` uses `ctx.getStory()` sentences; the silent-script transcript produces them, so no loss. No code conflict, but a manual check is worth adding: clone a voice on a scripted story, edit a line, render.
- **Queue error hook** needs T3 (above).

**Side to win.** Combine the dispose hunk; keep T1's Dub refusal and cff3ba1's clone state.

### 4. `rv/r3-t4-progress-speech` — merge last

**Conflicting hunks.**

- `pipeline.py` around the `speech_language` assignment in `analyze_source`: cff3ba1 has `speech_language = stt.speech_language_for(options, meta)`; T4 has `tracker.emit("speech", 0.0, "Preparing the speech read")` immediately before it. Keep both statements; the conflict is adjacency, not a real choice.
- `stt.py` where cff3ba1 inserts `_VI_LETTERS`/`guess_language`/`speech_language_for` just before `no_speech_transcript`, whose default T4 changes from `"en"` to `""`. Keep cff3ba1's block and T4's signature.

**Semantic clashes.**

- **Two language policies.** `pipeline.analyze_source` uses cff3ba1's `speech_language_for` (configured default → `"en"`, plus title guess). T4's `pipeline.retry_speech` uses its own `_speech_language` (untouched default `en` → `""`, auto). The same job can import in one language and retry in another. `speech_language_explicit` is only set by cff3ba1's re-transcribe route, not by import, so T4's “explicit” branch does not fire for import.
- **T4's Apple skip is disabled by cff3ba1.** T4 skips Apple when the requested language is empty and an auto-capable route follows. After the merge, `speech_language_for` almost always returns a non-empty language, so Apple still runs an English locale on a Chinese clip and can return a wrong transcript that blocks the fallback. This is the exact B-scenario in T4's handoff.
- **Two retry paths.** cff3ba1's `POST /api/jobs/{id}/transcribe` and T4's `pipeline.retry_speech` (no route) both re-read speech with different language/error handling. Pick one: make the route call `retry_speech`, or delete one.

**Combine recommendation.** One resolver in `stt.py`: explicit flag wins; title guess next; if the configured value is the untouched default `"en"`, return `""` (auto) so T4's Apple skip works; otherwise return the configured value. Keep T4's `errors`, `progress` and `start_new_session` changes. Keep T4's `no_speech_transcript(language="")`.

**Order reason.** Merge last: it changes the shared STT defaults and the language policy, and the other three branches do not touch `stt.py`/`pipeline.py`. Doing it last keeps that policy decision in one place.

### Final recommended order

`rv/r3-t2-library` → `rv/r3-t3-edit-finish` → `rv/r3-t1-dub-voice` → `rv/r3-t4-progress-speech`, with the T2 route registration added in the first merge and the T3 queue identity widened before T1 relies on the error hook.

## Checked and fine

- **Hand-resolved `tts.py` conflict.** The HeyGen status entry kept both sides: `available` and `clone` use `audio.openrouter_media_available()`, while the chat breaker is no longer consulted for speech. `list_voices` for heygen/fish/gemini uses media availability. Nothing from either side was dropped on this path.
- **Hand-resolved `audio.py` `_source_audio_bed`.** The silent-source branch (duration-based `anullsrc`) and the `channels`/`rate`/`name` options are both present. Callers are consistent: `build_bed` keeps the stereo 48 kHz default; `voice_extract._decode` asks for mono 48 kHz `source.wav`. `separate_vocals` delegates to `_separate_stem("no_vocals", model="htdemucs")` with the same cache name, so existing stem caches still hit.
- **Media vs chat OpenRouter gating.** `tts.list_voices`, `voice_engine_status`, `audio.engine_status["lyria-clip"]` and `music.generation_available` use `openrouter_media_available()`/key+breaker. Chat paths (`llm_available`, rewrite, translate, `audio.openrouter_status`) keep `openrouter_available()`. No reversed gate was found. STT readiness deliberately checks the key only (F14 covers the clone mismatch).
- **Clone render path with a live clone.** `build_bed` → `voice_candidates` keeps HeyGen first; `_tts_voice_for` returns the clone id for the primary; `synthesize_line` → `_openrouter_voice` detects `is_clone`, drops `voice`, adds `input_references`, and uses `response_format: pcm`. Covered by `test_clone_is_sent_as_openrouter_input_reference` and `test_stock_voice_request_is_unchanged`.
- **Consent.** Both clone routes reject without `consent`; `voice_clone.create_clone` re-checks it. The UI requires a tick. `CONSENT_COPY` is explicit about sending the sample to OpenRouter/HeyGen.
- **Path handling on new routes.** `_job_dir` rejects empty, `/` and `..`; the candidate index is an `int` bounded to 1..5; clone ids are `^clone_[a-f0-9]{24}$` and `sample_path` is never built from an unvalidated id; `FileResponse` filenames are fixed (`candidate-XX.wav`, `cloned-voice.wav`). `_read_candidate_report` catches the `HTTPException` docstring path.
- **`_guard` coverage where it exists.** My voice upload, candidate start/cancel, video clone, rename and delete all call `_setup_origin_ok`; the cross-site delete test covers the pattern. F10 lists the three new POSTs that do not.
- **`audio.js` clone state.** `useClonedVoice` re-applies `heygen` and the clone id after `loadEngines`/`loadVoices`; the clone block is hidden when HeyGen has no clone capability; `dispose()` stops the poll timer and the preview player; `pollCandidates` checks `disposed` after every await. No leak or stale render was found.
- **Silent script + silence bed.** `_scripted` inserts a voice-over plan for a scripted job; `build_bed` asks `_source_audio_bed` for the silent source, which now returns silence instead of an ffmpeg failure. `test_audio_bed_is_silence_for_a_source_without_sound` covers the bed; `test_script_route_saves_brief_and_marks_the_job` covers the transcript/engine marker.
- **Check-report cache fix.** `inProgress` refuses to cache `queued`/`running`/`complete:false` payloads; the new Node test asserts three server calls and two cached reads. The rest of the read-through cache still coalesces in-flight requests.
- **Music fallback.** `generation_available` uses admin routes plus one fallback per unconfigured provider, filters by key/breaker, and `build_bed` warns and continues when the bed is optional (`voice_path` present or `original_bed`). `render.py` copies `_warnings` into the render result and `app.run_render` stores it on the history row.
- **Voice extraction engine.** `_separate_stem` validates the model name, uses the right output glob for `htdemucs_ft`, keeps the old cache name for the instrumental, and removes the scratch directory on success. The pipeline's cache version, fingerprint inputs and report shape are consistent across `extract_clean_voice` and `find_voice_candidates`.
- **Scope of the hand-resolved conflicts.** No function was renamed or removed by either resolution; the only ordering change is that `synthesize_story` now uses `voice_candidates` when `routes is None`, while `build_bed` uses the same function. No caller of the old `separate_vocals` signature was left behind.

## Status after the R3 merge (Claude Code, 2026-10-28)

The R3 branches were merged into `main` by another session while this review ran (`2bc2f58` T1 → `fa0a1ac` T2 → `b638e9c` T3 → `e057f65` T4; handoff in `docs/studio/handoff/r3-review.md`). Re-checked against `18582f3`:

- **Resolved in that merge:** T2 route registration (`routes_library.install(app, JOBS)`); the `audio.js` dispose conflict (both clone cleanup and the Dub guard are kept); the `pipeline.py`/`stt.py` conflict (one language order: explicit, then title script, then default `en` = auto).
- **Re-verified in code on `main`, still open:** F1 (`delete_clone` removes only the record and sample), F2 (`CACHE_DIRS` has no `voice_refs`/`voice-clone`; the fingerprint uses the resolved temp path), F3 (fixed `CACHE/stems/run`), F5 (`sample.wav` output with the libmp3lame codec; this predates the merge and comes from the original clone route).
- **Still open from the R3 notes:** two speech re-read paths (`POST /api/jobs/{id}/transcribe` and the route-less `pipeline.retry_speech`); F4 depends on whether import sets `speech_language_explicit`. Re-check it with the new resolver before fixing.
- **Fixed on `fix/clone-findings`:**
  - F1: a deleted clone raises "This cloned voice was deleted" before the line cache and before any request. The Edit panel keeps the missing clone and warns instead of auto-picking a stock voice.
  - F2: `voice_refs` and `voice-clone` are now in `CACHE_DIRS`. Files up to 256 MB are keyed by a full content hash, not the temp path.
  - F3: each Demucs run gets its own `stems/run-<id>` folder. Prune drops only run folders older than 2 h.
  - F5: `prepare_sample` forces the MP3 container. Old WAV-wrapped samples are sent as `audio/wav`.
  - F12: the candidate cache-hit names files by each candidate's index.
  - Not covered: the Edit panel change has no JS test.
- **Fixed on `fix/review-mediums`:**
  - F4: `clean_options` marks a language as explicit when it differs from Setup or is flagged. The Setup default that Classic sends is not explicit.
  - F6: a clone always starts on HeyGen. Other engines get their own default voice, never the clone id. A warning is recorded when a fallback engine read lines.
  - F7: a new `audio.mode_chosen` flag, stored only when true, marks an "original" the creator picked. Only that opts a scripted story out of voice-over. The report's suggested fix would not work: every Edit stores `mode: "original"` by default.
  - F8: the clip search and the video clone refuse a source with `has_audio: false`.
  - F9: re-transcribe, script writing and the clip search run on a new one-worker `voice_pool`, separate from analysis.
    - The request answers within 20 s, or returns 202 and the page polls `GET /api/jobs/{id}/voice-tasks/{kind}`.
    - `DELETE` on the same path cancels and drops the result.
    - My voice cleaning reads at most the first 6 minutes of the upload.
    - `/transcribe` now has the origin guard (part of F10).
  - Not covered: there is no cancel button in the UI yet (the API exists), and the Stories polling is not checked in the browser.

## Low findings status (fix/review-lows)

- F10: `/sample` routes now guarded; `/transcribe` was already guarded by the F9 fix.
- F11: "bye", "bye bye" and "ta-da" join the repeat-only set; short filler is dropped from the third repeat, never when Whisper's scores say confident speech.
- F12: already fixed on main (cache-hit names come from each candidate's `index`).
- F13: one lock, a 64-job cap on stage/result/error tables, cancel switches released when a search ends, `forget_job` on job delete.
- F14: `voice_clone.available()` also requires `audio.openrouter_media_available()`.
- F15: Setup My voice and Voice Room show `warning`/`warnings`, or a raw-recording note when `cleaned` is false.
- F16: with no ffprobe, a failed decode falls back to silence (a cancel still raises).
- F17: the audio bed maps the stream with the most channels, first on a tie, which is ffmpeg's default pick.
- F18: new `script` workflow (OpenRouter only, default `google/gemini-3.5-flash-lite`, now in the admin catalog); `silent_script` reads it, with `MODEL` as fallback.
- F19: `synthesize_story` and `StoryVoice` removed with their story-only tests.

Tests: `tests/test_review_lows.py`. Full suite 1662 passed, 10 skipped.
