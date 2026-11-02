# Refactor round 2 review: atomic trim (Claude Code)

**Base:** `refactor-2-base` (`d5d7590`), with 1415 tests passing.
**Result:** merged T1 → T4 with no conflicts (`app.py` auto-merged), plus the fixes below.

**Checks on `main` (`567fb87`):**
- 1491 tests pass, 7 skipped.
- `compileall` passes.
- `node --check` passes.
- The Playwright drag test (`tests/test_browser_trim.py`) runs and passes. It starts and stops its own server; none is left running.

| Track | Branch HEAD | Suite on branch |
|---|---|---|
| T1 Trim transaction | `fde70fe` | 1445 passed |
| T2 Captions + fail-closed | `8750ceb` | 1436 passed |
| T3 Studio trim | `4c79cc9` | 1415 passed (JS only) |
| T4 Acceptance + browser | `2307015` | 1415 passed + 2 skipped modules (they waited for T1/T2) |

## Fixes on `main`

1. **P0: every real trim failed with `caption_rebuild_failed`.**
   - The problem: `routes_trim` called `caption_reflow.rebuild_for_story` without `job_dir`. Reflow then looked for the old track under `captions.DATA` instead of the app's data dir. The T1 and T2 branch tests each faked the other side, so only the merged acceptance tests caught it (13 failed).
   - The fix: pass `job_dir=_job_dir(job_id)`.
2. **P1: motion layers didn't ripple.**
   - The problem: punch-ins and zooms are output-timed, like graphics, so a start trim left them on the wrong words.
   - The fix:
     - `routes_trim` ripples `motion` with the same rule.
     - `normalize_motion` takes an optional `hidden` flag, stored only when set, so old hashes are unchanged.
     - `compose_render` skips hidden motion layers.
   - Tests: `test_start_trim_ripples_motion_layers_too`, `test_motion_without_hidden_hashes_as_before`.
3. **P1: render could drop hand-fixed caption text** (T2 known gap 1).
   - The problem: when `prepare_render` rounded clip ends by under a frame, the story track's `clip_hash` stopped matching. The render rebuilt the track from the transcript, losing manual fixes.
   - The fix: the new `_caption_track_for_cut` retimes the track's own cues through the clips and saves a child track. This applies only when every clip length moves by less than 0.05 s. A beat-synced cut keeps the rebuild path.
   - Tests: `tests/test_caption_track_for_cut.py`.
4. **Test updates:**
   - T1's fake reflow now accepts `job_dir`.
   - One acceptance test counted `kept` alone. The contract says `kept` means the same time and `moved` means shifted, so a later start counts survivors as `moved`; the test now checks `kept + moved`.

## Accepted

- **T1:**
  - `trim.py`: pool, mapping through the clips, ripple, receipt.
  - `routes_trim.py`: GET, trim (with `dry_run`), undo and rebind.
  - Commit and rollback: one `update_job` commit under `app.LOCK`, with a revision and aspect-head compare-and-swap. Sidecars are written first and orphaned on failure.
  - Story pins are stored as `pin`, because `anchor` is already the layout anchor. `anchor` is accepted as an alias.
- **T2:**
  - `caption_reflow.py`: cues are mapped through source time, and manual text is kept.
  - A cached track whose clip hash doesn't match is rejected.
  - A stale or unreadable Edit returns 409 `edit_stale` for story render, the Finish queue and the packet. There is no plan fallback while a pointer exists.
  - `stale` is added to the Edit payload.
- **T3:**
  - One duration source from the trim result: header, preview, scrubber, playhead and timeline.
  - Both-direction handles over the pool, with a `dry_run` readout while dragging.
  - Stories ± calls the trim route.
  - Undo trim, the receipt panel, the stale badge with Repair, and Repair from Finish on `edit_stale`.
  - The Hook card is pinned to the story start.
  - The localStorage job-id lookup is gone from the timeline.
- **T4:** all 8 round_5 "tests required" groups, plus the mounted drag test.

## Open items

- **Classic** still changes ranges through `PATCH /clip-sets`. It bumps the revision, and render then fails closed with Repair. Classic has no trim UI.
- **The packet check is per story, not per aspect.** A stale 4:5 blocks a 9:16-only packet.
- **The timeline shows the whole ±90 s pool,** so a short story can look small on the axis.
- **localStorage job-id reads remain in some Studio files:** `shell.js`, `effects.js`, `clean.js` and `audio.js`.
- **Story pins:** `story_start` keeps its output offset even when the story gets shorter.
- **Founder tests:** the manual tables are in `docs/studio/handoff/r2-t1.md` through `r2-t4.md`, each under "Founder manual test", for videos A and B.
- **Deferred per round_5:** A/B compare, the approved-version lock, transcript-range trim and word-boundary trim.
