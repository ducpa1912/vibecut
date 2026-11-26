# T1 · A timeline that shows the picture (REQ-20261126-01)

Owner: **OpenCode**. Folder `drop_eval/ducksuite-opencode`, branch `oc/t1-timeline-picture`.
Founder, 2026-11-26: "Start T1". Plan: `docs/plans/2026-11-26-editroom-adoption.md` (T1, Icons).
Base: `ducksuite` at `e18280a` or later. You own `static/duck/app.js` for this loop. Codex is on
G1 core and doesn't touch `static/duck/`.

## Why
The Edit timeline shows clips as plain blocks: a video lane with the waveform (P-D), a scene lane,
script, audio and effects. You can't see which picture is where. Editroom (MIT, read only)
handles this three ways:
- **a filmstrip on each clip**, with the clip's name;
- **track headers**;
- **a blade tool**.

Take the method from it. Don't copy its Swift.

## Files you own
- `static/duck/app.js`: the Edit timeline (`timelinePanel`, `timelineSceneRanges`, the lanes
  and their actions), the scene strip (`sceneTile`, `sceneStripControls`) and the `icon()` set.
- `static/duck/app.css`: the timeline, scene strip and icon rules.
- `duckcore/main.py`: only the `/frame` route (about line 805), to add a small-thumbnail size.
- `tests/test_frame_thumbs.py` (new), `docs/teams/t1-timeline-picture/review.md`.

Stay out of P-D's split, reorder and remove-silence logic, and out of P-E's Clean code. Use
them; don't change them.

## Done looks like
1. **Small frames.** `/frame` takes an optional width `w` (64–320, rounded to a fixed set such as
   96/160/240/320). It returns a small JPEG and caches it beside today's full-size frames, under
   a separate name. Without `w`, it behaves as today. A test covers the size, the cache reuse,
   and a `w` outside the range.
2. **Filmstrip.** Each video clip on the timeline shows thumbnail tiles behind its waveform.
   - Spacing rule, from Editroom: the source seconds per tile is the **smallest power of two**
     that keeps a tile at least one thumbnail wide at the current zoom.
   - Frame times snap to that grid, so zooming reuses cached frames instead of asking for new ones.
   - Only tiles in view are requested.
   - Images show as clips (`media` clips) use their own picture.
   - Measure how many frame requests a zoom in and out on the 160 s project makes, and put the
     number in the review.
3. **Clip name.** Each clip shows a small name tag: the scene number and duration, or the media
   file name. It's readable over the picture, with a dark backing. Dropped when the clip is too
   narrow.
4. **Track headers.** A fixed header column on the left of the lanes: V for video, S for scenes,
   T for script, A1, A2 and so on for audio, FX for effects.
   - Audio headers keep today's mute and solo (`audio-mute`, `audio-solo`) and show the track's
     level in dB.
   - Video gets an eye toggle that hides the picture in preview only. It never changes the render;
     say so in its title.
   - Nothing here locks tracks: there's no lock model yet. Say so in the review.
5. **Blade tool.** A select/blade toggle in the timeline bar, plus the keys `V` and `B`, the way
   editors do it.
   - In blade mode, a click on a video clip splits there, through P-D's existing split, and the
     tool stays on blade.
   - Escape goes back to select.
   - The pointer shows which mode is on.
6. **Scene grid.** The Check scene strip can switch to a grid: a thumbnail, a duration badge and
   the scene number.
   - A search box filters scenes by transcript words inside the scene, using the existing
     transcript.
   - Keyboard: the arrow keys move between tiles, and Enter selects one.
7. **Icons.** One stroke style for the timeline and scene icons you touch (the set is Lucide,
   ISC): 1.5 px at 18 px, 1.25 px at 14 px, `currentColor`. Add small fade-curve icons only if
   a fade control already exists where you add them. Don't add SF Symbols or any other set.
8. **Layout and checks.**
   - Run `scripts/measure-layout.mjs` on the Edit screen at 1024×700 and 1440×900: no clipped
     controls, no horizontal page scroll.
   - The full suite and `node --check static/duck/app.js` pass.
   - The review has numbered founder hand-test steps. **Do not open the app.** Don't open founder
     projects. Don't make media.

## Notes
- The thumbnails are ungraded for now. Once G1 merges, its graded still route can feed them. Say
  in the review where that would plug in.
- Commit on `oc/t1-timeline-picture` with `git -c commit.gpgsign=false commit`. Don't push.
  Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`.
- If you check anything by hand, use port 8821 and `build/scratch-root` only.
