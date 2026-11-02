# Wave 4 review (Claude Code)

**Base:** `wave-4-base` (`c3d12f5`, 1190 tests).
**Result:** merged T1 → T4.

**Merge conflict:** one, the router include lines in `app.py`. Resolved by keeping both.

**Checks on `main` after review fixes:**
- 1243 tests pass, 7 skipped (opt-in live tests).
- `compileall` passes.
- `node --check` passes for Studio and Classic JS.

**Branch suites before merge:**

| Track | Passed | Skipped |
|---|---|---|
| T1 | 1203 | 7 |
| T2 | 1202 | 7 |
| T3 | 1215 | 7 |
| T4 | 1190 | 7 |

**Ownership:** every track stayed inside WORKPLAN plus the extensions in the Wave 4 prompt.
- `edits.py` was touched by both T1 (`audio.translate`) and T2 (Clean `tracklet_id` / `tracklet_kind`). The sections are separate, and both merged clean.
- `routes_cleanup.py` was touched by T2 (the residual route) and T3 (the `cleanup_enabled` default).

**Testing (founder rule):** no coder ran long jobs on the founder's videos. Their four manual tables are combined, in flow order, in `docs/studio/testing/w4-founder-checklist.md`.

## Fixes on `main` (`5962db1`)

1. **P1: story renders ignored the Edit's audio layer.**
   - Studio's Audio panel saved a bed, voice-over or dub, but `_queue_story_render` passed `audio_plan=None`, so it was never mixed.
   - Fix: it now passes `audio.plan_from_edit(edit["audio"])`.
   - `original` mode stays `None`, so captions-only Edits (including migrated ones) keep the legacy audio signature and artifact ids.
   - Tests: `test_story_render_mixes_the_edit_audio_layer`, `test_captions_only_edit_keeps_the_legacy_audio_path`.
2. **P1: a Classic caption edit was lost on migrated stories** (T3 known gap 1).
   - Classic updated `story_captions`, but the story's 9:16 Edit still pointed at the old track, so the next render burned the old captions.
   - Fix: `_set_story_track` now also patches the current 9:16 Edit to the new track through `routes_edits.patch_edit` (compare-and-swap, validation, history). Same track is a no-op. A refusal is logged and leaves the Edit as it was.
   - Test: `test_classic_caption_change_becomes_a_new_edit_version`.
3. **P2: migration could race with recovered workers.**
   - `migrate_all` rewrites `job.json` without the job lock, and it ran after `recover_jobs` had restarted workers.
   - Fix: it now runs first.
4. `docs/shared/cleanup.md` still said Clean was off by default. It now says on, with `VIBECUT_ENABLE_CLEANUP=0` to turn it off.

## Accepted

- **T1 packet v2:**
  - Writes `edit.json`, `audio.json`, `music.json`, layer assets and frame-endpoint covers.
  - Identity covers `edit.hash`, `transcript_id` and the audio/music hashes.
  - Review links show `Edit vN`.
  - `render_reel` beat-snaps using the locked bed's grid.
  - Dub `audio.translate` reaches `plan_from_edit`.
- **T2 preflight:**
  - `GET …/edits/{id}/preflight` returns markers for collision, face overlap, safe zone, residual text, caption density, loudness, voice fit, music licence and 4:5.
  - The residual route has a hard cap of 60 frames, a 240 s deadline and JSON errors, with no unhandled 500.
  - On save, Clean layers that name a `tracklet_kind` are re-checked against `cleanup_block_reason`.
- **T3:**
  - The startup migration gives legacy stories a captions-only 9:16 Edit. It is idempotent, never recreates an Edit after a Studio reset, and one bad job can't block the others.
  - Clean is on by default.
- **T4 Studio:**
  - Finish screen: 9:16/4:5 queues, pause/resume, versions A/B, publish kit, review links, and Apply to all.
  - Setup screen: keys, engines (HeyGen under OpenRouter) and pack status.
  - Clean auto-fill calls `POST /cleanup/layers`, so after the merge the server's `tracklet_id`/`tracklet_kind` are saved on each layer.
  - The Audio panel has brief → 2 candidates → A/B → lock.

## Open items → Wave 5

| # | Item | Owner |
|---|---|---|
| 1 | Founder checklist results (`docs/studio/testing/w4-founder-checklist.md` and `w3-live-checklist.md`), including render speed ≤ 2× and the residual check at 60 frames | founder → Claude records |
| 2 | Pack install/remove has no HTTP route. The built-in manifest has empty SHA-256 pins. Speech Pack detection relies on the model cache. | W5 T2 packaging |
| 3 | Perf on a 90-minute source: frame endpoint, proxy, residual sampling. Preflight samples 24 draft frames, so a one-frame ghost can be missed. | W5 T1 |
| 4 | Animation: arrow, underline and sticker draw-on are static. Beat snap only moves boundaries already within ±120 ms of a beat. | W5 (polish) or post-launch |
| 5 | The A/B music preview plays the raw bed, not a ducked mix. | W5 bug bash |
| 6 | Voice-fit data isn't saved on the Edit; preflight falls back to the rate. Loudness is only measured once a render exists. | W5 |
| 7 | Migration covers 9:16 only and runs at startup only. Stand-alone 15/30/60 caption tracks aren't migrated. | accepted |
| 8 | If a frame render fails, the packet cover silently falls back to `ffmpeg`/`poster`. | W5 bug bash |
| 9 | `MAX_CLEAN` 32; the Vision sampler failed once in W3; cloud music isn't verified (no MiniMax key, Lyria 401). | W5 / founder key |
| 10 | The HeyGen free tier ends 2026-11-30; after that the route should fall back to MiniMax. | check after date |

**Status:** feature-complete per WORKPLAN, so Wave 4's exit is feature freeze. Wave 5 is hardening only.
