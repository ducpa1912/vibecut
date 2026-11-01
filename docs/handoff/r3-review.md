# Refactor round 3 review: founder-session fixes (Claude Code)

**Base:** `refactor-3-base` (`7e998d1`), with 1501 tests passing.
**Integration:** done on branch `rv/r3-integration` in its own worktree, because main had moved. The other session merged voice extraction (`cff3ba1`) while R3 was being built. Main was then fast-forwarded to `e057f65`.

**Checks on `main` (`e057f65`):**
- The full suite passes: 1638 tests collected, `pytest -x` exits 0.
- `node --check` passes for every Studio file and for Classic `static/app.js`.
- No R3 test server was left running, and port 8787 was untouched.

| Track | Branch HEAD | Work |
|---|---|---|
| T1 Dub and voice | `0d1e8ba` | Target and source language, editable script, Dub blocked while unsaved without a target, queue failure reason hook |
| T2 Library | `7d05365` | `GET /api/artifacts` (read-only over manifests), Finished and Sources tabs in "Your videos" |
| T3 Edit and Finish | `1aefd4c` | Back to Stories and Next: Finish (both wait for the save), queue idempotency, ETA smoothing, preflight for clip-set ids, frame at `t = duration` |
| T4 Progress and speech | `21fc3d5` | Stage-weighted progress with heartbeat and ETA, cancel that kills the ffmpeg/STT process group, auto-detected speech language, disk message in GB, in-place path reserve |

## Merge conflicts

1. **`static/studio/edit/layers/audio.js` (T1 vs voice extraction on main):** kept both sides of the cleanup: the clone player and poll stop, and T1's no-autosave-while-Dub-has-no-target rule.
2. **`pipeline.py` and `stt.py` (T4 vs main's `stt.speech_language_for`):** combined them.
   - An explicit job language wins.
   - Otherwise a title written in another script wins (main's `guess_language`).
   - Otherwise the default `en` means auto-detect (T4's `_speech_language`).
   - Main's version alone would still force English on video B, whose title is in Latin script.
   - `no_speech_transcript` now defaults to `""`.

## Fixes on `main` (in the `e057f65` merge commit)

1. **P1: queue could hand back an old render.**
   - T3 added a branch to `_queue_render_locked_impl` that returned the active render whenever the artifact id differed.
   - The render key already covers story, shape, quality, captions and audio, so a different artifact under the same key means the Edit changed during the render. The queue would then mark the new request done with the old cut.
   - Reverted to the 409. The double Queue-all case is already handled at the queue level by identity (`_active_queue_for`).
2. **P1: Apple speech could stall for up to an hour.**
   - T4's cancel-aware path passed `stdout=PIPE, stderr=PIPE` to `_child_run`, which never reads them. A helper that writes more than the pipe buffer would block until the timeout.
   - Only the return code and the output file are read, so both are now `DEVNULL`.
3. **The library route was not registered** (T2 gap 1): `routes_library.install(app, JOBS)` in `app.py`.

## Accepted outside the owned-file list

- **T1 `edits.py`:** `audio.translate.source` and `audio.script_overrides`. Both are stored only when set, so older Edits hash as before.
- **T1 `audio.py`:** passes `script_overrides` through in `plan_from_edit`, uses the confirmed source language, and gives a clearer Dub refusal.
- **T3 `routes_edits.py`:** the frame route accepts `t` up to the end of the story plus one frame and clamps it.

## Open items

- **T1:**
  - Edits saved before R3 can still queue a Dub with no target. The queue row now shows the server's reason instead of "Render failed."
  - Translated captions are still deferred.
  - The language list is short (11 codes), and source detection is a script heuristic.
- **T2:**
  - Open in Finish does not carry the story or shape.
  - Older renders without a manifest are not listed.
  - There is no "load more" (60 rows, up to 200 through the API).
  - The list does not refresh while the dialog stays open.
- **T4:**
  - The speech-only retry route is missing (`pipeline.retry_speech` exists).
  - Check itself has no cancel (`routes_check.py`), and its ETA is calculated in the browser.
  - The Import screen has no Cancel or ETA control.
  - Vision cancel waits for the current batch of up to 8 frames.
- **Founder manual tests:** the "Founder manual test" tables in `docs/handoff/r3-t1.md` through `r3-t4.md`. They use videos A and B.
- **Deferred per round 6:** client approval and delivery log, the per-source rights record, one shared read for Import and Check, and Studio engine routing.

## Phase B (studio lane) status

Items 1a–1d close the T2 and T4 open items above; 2 and 3 are the Phase B follow-ups.

| Item | Commit | Founder test |
|---|---|---|
| 1a speech-only retry (`POST /api/jobs/{id}/transcribe`) | `fd8b8d8` | `docs/testing/studio-b1a-speech-retry.md` |
| 1b Check cancel, Import read ETA and Cancel, upload ETA and Cancel | `a7e0f50` | `docs/testing/studio-b1b-cancel-eta.md` |
| 1c Library "Load more" | `c269f15` | `docs/testing/studio-b1c-library-more.md` |
| 1d Open in Finish carries set, story, shape and cut | `19faef5` | `docs/testing/studio-b1d-open-in-finish.md` |
| 2 Finish shows render warnings | `0ecc18d` | `docs/testing/studio-b2-render-warnings.md` |
| 3 Edit hides voice cloning unless `voice_room` is on | `73bbab2` | `docs/testing/studio-b3-clone-gate.md` |

Still open:

- **Check's ETA** is still computed in the browser.
- **Vision cancel** still waits for the current frame batch (up to 8 frames).
- **The library list** does not refresh while the dialog stays open.
- **Older renders without a manifest** are not listed.
- **Setup's My voice panel** is not gated by `voice_room`; only the Edit clone block is.

## Studio rebuild (2026-10-29)

The founder's first real runs (recordings in `~/vibecut-lanes/recordings/studio/`) reshaped Studio. OpenCode built it on `studio`; Claude reviewed it.

**Built:**

| Commit | What |
|---|---|
| `9e243d7` | Lane scripts: `lane.sh`, `serve.sh`, `record.sh`, `ship.sh`, `integrate.sh` |
| `cf2a7e6` | Check folded into **Moments** (Import → Moments → Edit → Finish). Moment cards show a frame, old-text boxes and a music tag. Lengths up to 180 s, plus a custom range. 720p quality. Finish opens on a **Review** card. |
| `9e6c755` | Tests for 3-minute moments |
| `0c2c688` | The recorder saves the trace when the tab closes |
| `faed7c9` | **Add story** builder (click-to-pick scene collage, build log, no duplicates). Shape per moment card. **+ Add to queue** and **Start edit** on each card. Shapes 9:16, 4:5, 1:1, 16:9, 16:10. Platform safe zones (Instagram, TikTok, YouTube Shorts, Facebook Reels). Text, Captions, Effects and Colour merged into **Texts & Effects**. Clean defaults to blur. Path import can reveal the file in Finder. |
| `470838e` | Responsive rail and top bar. A stale `#/finish` with no video goes back to Import. |

**Fixed in review:**

| Commit | What |
|---|---|
| `9dc2988` | The Add story collage squashed every frame to a 30 px strip, and the dialog had no padding. Edit said "Step 4". Finish kept "Reading renders…" on screen forever (an older bug). |
| `38a7eda` | Check's Cancel (1b) was lost when Check moved into Moments. The scan card has **Cancel scan** again, resumes a running scan after reload, and **Scan again** really re-scans. |

## Studio plan (revised 2026-10-29, superseded below)

The founder tests by hand with real files. Each step below ends with a founder recording, not a generated test.

1. **Lane plumbing:** one set of lane scripts with the data in `~/vibecut-lanes/studio`. Then integrate `classic` and `voice-room` into studio, and move `main`.
2. **Founder test script:** rewritten from the founder's own recordings only (`docs/testing/`).
3. **Editor revision:** the founder said the Editor "needs a lot of revision". Not started.
4. **Queue in Edit:** the founder asked for the queue to live in Edit. Today Moments has **+ Add to queue**, but the queue view is still in Finish.
5. **Custom shape:** any ratio, not only the five presets.
6. **Clean:** it blurs old text. It does not remove it (no inpainting).
7. **Still open from Phase B:**
   - Check's ETA is computed in the browser.
   - Vision cancel waits for a frame batch.
   - The library does not refresh while it stays open.
   - Older renders without a manifest are not listed.
   - Setup's My voice panel is not gated by `voice_room`.

## Studio review (2026-11-01)

**Built since `d5a4bd2`** (OpenCode, at the founder's request):

| Commit | What |
|---|---|
| `78afd48`, `09d9877` | One header (brand, four steps, Menu); Edit inspector as drawer or sheet; Finish in Review, Render and Publish stages; Add story became **Add moment** |
| `3009924` | Clean **Remove (interpolate)**: ffmpeg `delogo` replaces the black cover |
| `e0c0aac` | **Auto subtitles** (`routes_auto_subs.py`) and **Remove all detected text** (`/edits/{id}/auto-clean`) |
| `3edca8d`, `e8f3256`, `c709e8f` | CI: Classic and Voice paths, portable render and voice tests, Node 24 |
| `4d1c20d`, `3491ab1` | `classic` and `voice-room` merged into studio (2026-10-31) |
| `851de42` | `/openapi.json` works again (XHS cookie body defined before its route) |

**Fixed in this review:**

| Commit | What |
|---|---|
| `56244cb` | The one-time data move left job sources at the old `vibecut-studio/data` path, so the founder's test video read "Original file missing". Moved copies are now found under today's data folder. |
| `e09e645` | Remove all detected text added layers for text anywhere in the video; it now adds only text on screen during the moment, clipped to it. |
| `4f3849f` | At 800 px the header squeezed "04 Finish" to "4" behind the video name; steps keep their labels and the name truncates. |
| `268fce8` | C3: the old review-link lookup could hand a 16:10 file to a 9:16 link. |

**Review notes, not bugs:**

- `e8f3256` changed `voice_clone.py` (voice-room's file) to cap a sample to its window. The change is right, and voice-room has it since the 10-31 merge, but a studio commit should not have touched it.
- The delogo "too small" warning cannot trigger: `_box_rect` already keeps boxes at least 2 px.
- Auto subtitles validates `aspect` but does not use it. It also builds every story's track in one request, which can be slow on a long set.
- `static/studio/check.js` is no longer mounted; it is dead code with old copy.

## Studio plan (revised 2026-11-01)

In order, with the reason for each place.

1. **Sources the founder can trust.** Show where each source lives, offer Relink when it is missing, and decide how long a cloud build keeps an import (the founder named 7 days). *Why first:* "Original file missing" stopped the founder's last run, and every later test needs the source.
2. **A founder pass on today's build.** The founder records one full run on 8795. `scripts/record.sh` should also log each click (selector and label), because traces hold snapshots but no clicks. Then rewrite `studio-founder-pass-1.md` from that run, and settle OpenCode's four script questions. *Why:* the next three items need evidence of where the founder struggles, not guesses.
3. **Queue in Edit.** Add to queue, the queue list and per-item status move from Finish into Edit; Finish keeps Review and Publish. *Why:* the founder asked for it twice, and it is a contained change.
4. **Editor revision.** Scope it from step 2's recording: the founder said it "needs a lot of revision". Bring in C1 (single-word caption cues, in shared `captions.py`): merge a cue under about 3 words into its neighbour. Studio's auto subtitles show the same problem. *Why here:* the biggest build, done once the recording shows what to fix.
5. **Moments quality.** First measure suggestions against the founder's own picks (usable / usable after edit / unusable). Then change the custom builder so it no longer bans every unselected scene, and add beat-level candidates and a semantic rerank. *Why after the editor:* a better ranking matters only once a moment can be finished well.
6. **Shared core with classic.**
   - F4: a running rewrite keeps going after a setting change. It needs a cancel event through `audio.py`, for the subprocess and the cloud call. Do it with classic, after classic's beta pass.
   - C3: done (`268fce8`).
7. **Clean beyond interpolation.** Generative inpainting for busy backgrounds needs a model choice and a cost decision from the founder. Until then, delogo plus review at 1×.
8. **Custom shape.** Any ratio beyond the five presets. It touches render, safe zones and every layer.
9. **Leftovers:**
   - Check's ETA is computed in the browser.
   - Vision cancel waits for a frame batch.
   - The library does not refresh while it stays open.
   - Older renders without a manifest are not listed.
   - Setup's My voice panel is not gated by `voice_room`.
   - Studio's Edit clip finder now searches only the first 2:00 (voice-room note): pass `full` or say so in the panel.
   - Remove `check.js`.
   - Use or drop the auto subtitles `aspect` field.

**Integration risks** (dry check on 2026-11-01: studio merges `origin/classic` `940bfcb` and `origin/voice-room` `742e281` with no conflicts, separately and together):

- **Launch scripts:** voice-room keeps its own `voice-serve.sh`, `voice-record.sh` and the Finder `.command` launchers, beside the unified set (`c8f8913`). They agree today because both read `scripts/lane-env.sh voice`. Voice-room should switch to `serve.sh` / `record.sh` when it next takes studio, or two sets will drift.
- **voice-room merged classic once** (`caa6758`, 10-29 19:51). Classic commits reach studio by two paths. Git merges them cleanly, but a classic revert would also need reverting in voice-room.
- **Classic shared changes:**
  - four feature branches merged into classic (moments, sound, copy, texts and effects);
  - text-layer constants in `app.py` (`94dfb47`);
  - 16:10 in `render.py`.

  All are already in studio since `4d1c20d`. The new classic commits touch only classic files and docs.
- **Old ship scripts:** classic and voice-room still carry the old `ship.sh` that moves `main`. Only `ship-lane.sh` is safe there.
