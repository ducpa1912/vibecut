# T1 review · A timeline that shows the picture (REQ-20261126-01)

Owner: OpenCode. Branch `oc/t1-timeline-picture`. Base `8357186` (brief), code on
`e18280a`.

## Verdict

Build and test pass. Everything in the brief is implemented. Sign-off requested;
`good-to-go` for the founder hand test below. One limit is stated, not hidden:
there is no lock model, so no track locks were added. Thumbnails are ungraded
until G1 merges.

## What changed

1. **Small frames.** `/frame` takes optional `w` (64–320). The value snaps to
   96/160/240/320, the JPEG is resized to that width, and it is cached at
   `projects/<id>/frames/w<width>/frame_<ms>.jpg`, beside the full-size frame.
   No `w` behaves exactly as before. A value outside 64–320 is a 400.
2. **Filmstrip.** Each scene clip in the video lane draws tiles behind the
   waveform. Source seconds per tile is the smallest power of two that keeps a
   tile at least 48 px wide at the current zoom. Frame times sit on that grid
   (anchored at the clip start), so a zoom change reuses the same frame times.
   Only tiles intersecting the visible scroll window are created; scrolling
   fills the newly visible ones. Image beats (media clips) use their own file.
3. **Clip name.** Every video clip carries a dark tag with `S0n · duration`, or
   the media file name. A container query drops it when the clip is under 66 px.
4. **Track headers.** Fixed left column: `V · Video`, `S · Scenes`,
   `T · Script`, `A1`, `A2`, … with mute, solo and level in dB, and `FX`.
   `S` keeps the existing All marker, `T` opens Script Focus, `FX` adds an
   effect. Mute/solo moved from inside the audio block (same `audio-mute` /
   `audio-solo` actions) into the header, so the lane itself is cleaner.
   The `V` eye hides the picture in the preview only; its title says the render
   keeps every frame.
5. **Blade.** Select/blade toggle in the timeline bar, keys `V` and `B`, Escape
   returns to select. In blade mode a click on the video lane clip or on its
   scene block splits at that x through P-D's existing `clips/split`; the tool
   stays on blade. The lane shows a crosshair / col-resize cursor in blade mode.
   Clip drag is disabled while blade is on.
6. **Scene grid.** The Check strip toggles to a grid with thumbnail, scene
   number, duration badge and title. The search box keeps a scene when its
   transcript segments contain the words. Arrow keys move focus by grid row and
   column; Enter activates the tile (native button behaviour).
7. **Icons.** `icon()` now draws 1.5 px at 18 px and 1.25 px at 14 px, always
   `currentColor`. New `pointer` and `blade` glyphs are our own Lucide-style
   drawings. No SF Symbols. No fade-curve icons were added because no fade
   control was added in this loop.
8. **Layout and checks.** Numbers below.

Files: `duckcore/main.py` (`/frame` only), `static/duck/app.js`,
`static/duck/app.css`, new `tests/test_frame_thumbs.py`, this review. No
`MEMORY.md`, `TODO.md`, `PLAN.md`, `PRODUCT.md`, no app bundle, no founder media.

## Measured

- `python3 -m pytest -q tests` → **457 passed, 2 skipped** (includes 4 new
  frame tests). `node --check static/duck/app.js` → pass.
- Frame tests cover: snap 97 → 96, real JPEG size, cache reuse (second request
  does not call `extract_frame`), per-width cache folders, widths 10/63/321/4096
  → 400 with no cache or extraction, and no-`w` still returns the 640 px frame.
- **Layout**, `scripts/measure-layout.mjs`, real `app.js` + `app.css` with a fake
  API and a synthetic 160 s / 10-clip edit (no footage, no app bundle):

  | Size | h-scroll | off-screen controls | clipped controls |
  |---|---|---|---|
  | 1440×900 | false | 0 | 0 |
  | 1024×700 | false | 0 | 0 |

  The 11 reported overlaps are the intended `clip-name` tag over its own
  filmstrip tile (10) and the pre-existing Before/After placeholder. The first
  run found two real bugs, both fixed: an SFX block label clipped at 1024, and a
  duplicated full-width tile on the first 1440 paint.
- **Frame requests, 160 s timeline** (synthetic, 10 × 16 s clips, lane ≈ 1210 px):
  one sweep 1× → 16× → 1× created **383** `<img>` elements and covered **73
  distinct `/frame?w=96` URLs**. With the browser cache (`max-age=300`) that is
  at most 73 core reads; the same frame time is asked again at a different zoom
  instead of a new time. The number is from the headless probe, not from the
  founder's 160 s project.
- **Interaction probe** (headless, fake API): headers `V S T A1 A2 A3 FX`; 10/10
  clips get film tiles and tags; `B` turns blade on, a mid-clip click answers
  `Clip split.` and blade stays on; Escape turns it off; the eye adds
  `Picture hidden in preview only` and its title mentions the render; the grid
  shows 10 tiles, search `Line 3` leaves 1 of 10, ArrowRight moves focus to
  `S03`, Enter selects index 2.

## What could not be verified

- **Founder's 160 s project.** Not opened, by rule 6. The request count above is
  from a synthetic project with the same duration. The real number needs the
  founder to run the hand test; the tile rule is deterministic, so it should
  scale with the same 48 px tile floor.
- **Real thumbnail bytes.** The probe served no frames, so picture quality and
  the resize/cache behaviour under real footage were checked only by the Python
  tests. Thumbnails are ungraded.
- **Media video clips** (a video beat in a story) keep their waveform but get no
  filmstrip: `/frame` reads the project source, not an edit's media file. Image
  beats do use their own picture.
- **Track locks.** There is no lock model in the backend, so nothing locks. The
  headers do not pretend otherwise.
- The app bundle was not built or opened; no full render was run.

## Notes for the PO

- **G1 plug-in point:** `filmstripMarkup()` and `syncFilmstrip()` both call
  `frameUrl(time, projectId, 96)`. When G1's graded still route lands, swap that
  single call to the graded still route and add the grade version to the frame
  cache name, or a grade change will keep stale thumbnails.
- Filmstrip DOM is rebuilt on each render; the browser cache and the snapped
  frame grid keep the core reads down. The per-clip grid is anchored at the clip
  start, so two clips of the same scene at different trims do not share a frame.
- No new package was needed.

## Founder hand test

1. Open a checked project on the Edit screen. Look at the video lane: each clip
   should show pictures behind the waveform and a dark `S0n · duration` tag.
2. Zoom in with `+` and out with `−` (and `Fit`). Pictures should stay in place,
   the lane should scroll, and no blank tiles should appear when you scroll.
3. Read the left column: `V Video` with an eye, `S Scenes`, `T Script`, one
   `A1/A2/…` row per track with M, S and a dB figure, and `FX`.
4. Press the `V` eye. The preview picture should turn to a dark
   "Picture hidden in preview only" panel; play still runs. Press it again.
5. Press `B` (or the blade button). The pointer changes; click the middle of a
   clip. It should split there, the toast says `Clip split.`, and the tool stays
   on blade. Press Escape; the pointer returns to normal.
6. Press `V` and confirm the select tool is on. Drag a clip to confirm moving
   still works in select mode.
7. On Check, press the grid button in the Scenes header. Tiles show a picture, a
   number and a duration. Type a word spoken in one scene; only matching scenes
   stay. Use arrow keys to move and Enter to select one.
8. At a 1024×700 window (and 1440×900) check that nothing in the timeline is cut
   off and the page does not scroll sideways.

## Bugs and revisions

None open from this loop. Two bugs found by measurement were fixed before the
commit (SFX label clip at 1024, duplicate first-paint film tile at 1440).
