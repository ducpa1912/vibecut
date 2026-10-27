# Wave 3 review (Claude Code)

**Base:** `wave-3-base` (`12ff50e`, 1088 tests).
**Result:** merged T1 → T4 with no conflicts.

**Checks on `main` after review fixes:**
- 1190 tests pass, 7 skipped (opt-in live tests).
- `compileall` passes.
- `node --check` passes for Studio and Classic JS.

**Branch suites before merge:**

| Track | Passed | Skipped |
|---|---|---|
| T1 | 1138 | 1 |
| T2 | 1103 | 5 |
| T3 | 1119 | 3 |
| T4 | 1088 | 1 |

**Ownership:** every track stayed inside its WORKPLAN list plus the declared exceptions:
- T1: the story-render handler in `app.py`, and `artifacts.py` (the `edit_hash` input only);
- T2: `detect.py` (`screen_text` and the rights gate) and the Clean rights gate in `routes_edits.py`;
- T3: `packs.py` discovery, the Whisper lookup in `stt.py` and the Kokoro lookup in `tts.py`;
- T4: `edit/inspector.js` wiring.

## Live results on the founder's videos

Both runs used merged `main` with `VIBECUT_ENABLE_CLEANUP=1`. Each run went: import → analysis → rights → Check → `/cleanup/layers` → Edit (Clean + `golden_hour` + `punch_in` + hook text + `star` sticker) → story render → residual.

| | A: JOYLO (AV1 1440×2560, 53 s) | B: rednote (H.264 720×1280, 89 s) |
|---|---|---|
| Check | `clean_then_compose`; tracklets: `screen_text` 123, `subtitle` 5, `title` 3, `watermark` 1 | `clean_then_compose`; tracklets: `subtitle` 2, `screen_text` 13, `title` 2 |
| Clean before rights | 409 "Own-footage attestation missing…" | 409, same message |
| Clean after rights | 13 layers; 124 refused (screen text and watermark) | 5 layers; 13 refused |
| Story render | ready; the response carries the current `edit_id` and `edit_hash` | ready, same |
| Residual OCR | 0.0% (3-frame recheck) | 0.0% (3-frame recheck); **500 once at 60 frames** (see open items) |

The track handoffs report these numbers, measured by each track on its own branch:

| Track | Fixture A | Fixture B |
|---|---|---|
| T1 render time | 1.91× story length | 1.27× story length |
| T1 frame-vs-final SSIM | 0.974–0.987 | 0.965–0.976 (JPEG q=2 plus a second H.264 encode, not a layer difference) |
| T2 residual OCR | 0.0% over 52 frames | 0.0% over 60 frames |
| T3 audio | dub to Chinese with `say`: slot fit 10/10, −14.03 LUFS | zh STT 437 words, −14.21 LUFS, SNR 59 dB |

My render wall times (A 94 s, B 87 s) ran while the full suite and the live pytest ran at the same time, so they are not valid timings. Re-timing is on the founder checklist (`docs/testing/w3-live-checklist.md`).

## Fixes on `main` (`f5a26ce`)

1. **P1: blur crashed ffmpeg on caption-sized boxes.**
   - Error: `boxblur=24:2` failed with "Invalid chroma_param radius value 24".
   - Fix: luma and chroma radius are now capped per box from the box's short side. 4:2:0 chroma is half size.
   - Test: `test_blur_radius_is_capped_for_small_boxes`. Golden tests updated.
2. **P1: the sticker raster hash included the absolute asset path.**
   - The same Edit got a different hash in each checkout or install. This broke the T1 golden test after merge.
   - Fix: the hash now uses the asset id and its content hash only.
3. **P2: beat snap failed for uploaded beds.**
   - Fix: `/api/audio/beats` resolves `job_id` + a job-relative track inside the job folder (traversal refused) and returns beat `times`.
   - Studio Effects sends `job_id`.
   - Tests added.
4. **P2: `edits.MAX_TIMELINE` was 3600 s**, so a Clean range past one hour was refused on a 90-minute source. It is now 4 h.

## Also on `main` after the merge (`4c4f98e`, founder request)

- HeyGen Voice Turbo (free) via OpenRouter is the first voice route. The free tier ends 2026-11-30.
- Fixed a bug where every OpenRouter voice engine took the first OpenRouter route's model.

## Accepted as is

- **T1:** the story render and the story queue render the current Edit. A stale or missing Edit falls back to the plan path. `edit_hash` is in the artifact spec only when an Edit is present, so legacy artifact ids are unchanged.
- **T2:** the rights record lives in `job["rights"]`. Every Clean save is gated per REVAMP §178. Jobs from before Wave 3 that have no record still pass.
- **T3:** AudioPlan modes and ducking follow §8.4. `music.json` follows §8.5. The music API is `/api/jobs/{id}/music/*`. Engines look in the installed packs first.
- **T4:** Clean auto-fill uses the server's `clean_prefill` (`enabled && !blocked`), so T2's `screen_text` and watermark policy applies after the merge.

## Open items and carry-overs

| # | Item | Owner |
|---|---|---|
| 1 | Residual returned 500 once on B at `max_frames=60` while the machine was loaded. It could not be reproduced at 3 frames. The founder re-runs it; the stack trace is needed. The route also needs a frame cap and timeout for long sources. | founder check, then W4 T2 (preflight uses residual) |
| 2 | Edit Clean layers carry no tracklet kind. A hand-drawn box over a watermark is only gated by rights, not by kind. Store `tracklet_id`/`kind` on Clean layers and re-check them on save. | W4 T2 |
| 3 | Studio Clean still builds layers in the browser. Switch it to `POST /cleanup/layers`. Note that `/cleanup/*` is still behind `VIBECUT_ENABLE_CLEANUP`, so decide the default before the feature freeze. | W4 T4 (Studio) / founder decision |
| 4 | Studio Audio does not call T3's `/music/brief`, `/music/candidates` or `/music/lock` yet, and has no candidate A/B preview. | W4 T4 (Studio). `edit/**` is frozen in W4, so this needs a narrow exception. |
| 5 | `render_reel` does not auto-apply the beat grid. Arrow, underline and sticker draw-on animation is static. | W4 T1, or W5 |
| 6 | The Edit `audio` schema has no translate target for dub (`plan_from_edit`). | W4 T1 (packet/identity) with core |
| 7 | `MAX_CLEAN` is 32. Screen recordings exceed it; the UI caps and explains this. | W5 |
| 8 | Check's Vision sampler failed once and then succeeded (T4 saw this). | W5 bug bash |
| 9 | Cloud music is not verified: OpenRouter Lyria returned 401 and there is no MiniMax key. | founder key, then manual check |
