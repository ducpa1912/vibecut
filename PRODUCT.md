# VibeCut Classic

Classic is a second supported VibeCut product, separate from Studio. It turns a
source video into either a clean video or a short reel built from moments. It
has no timeline, no rights gate, no attestation tick and no watermark refusal.
The founder is responsible for having permission to edit the footage; the UI
carries a plain responsibility notice.

## Two deliverables

1. **Clean video** — remove baked-in text from the whole source and download it
   at the source's display dimensions and frame rate, with upright pixels and
   the source audio. Rotation metadata is not copied; the decoded picture is
   already upright.
2. **Clean cut** — remove text from a 15 / 30 / 60 second reel built from
   moments, then render the reel.

Both use the same Clean layer: source-space boxes, optional brush masks, source
time ranges, method and engine. Clean layers from a whole-video pass remain
usable when a cut is made later.

## People

The audience is mixed:

- a solo founder cleaning their own clips repeatedly,
- a freelance editor handling unfamiliar client footage,
- a non-technical operator running a one-off job.

The default path must be safe for a first-timer and fast for a repeat user. A
first-timer must be able to say what will be removed before the render starts.

## Product principles

- **Fewest clicks to a result.** One primary action per screen. No modal for a
  reversible task.
- **The source is never modified.** Cleaning writes a new file. Excluding or
  cancelling leaves the source untouched.
- **Honest states.** Name the missing model, the outside-cut row, the failed
  scan and the cancelled render. Never show a fake success.
- **The frame is the render.** Preview and output use the same fill engine and
  the same layer data; the preview releases the model after one frame.
- **On-device first.** Vision and fill run locally where available. Cloud AI is
  used only where a route is configured and a native engine is absent.
- **Quiet dark interface.** One accent, one primary action, readable type at
  11 px minimum, and no decorative chrome.

## Clean video flow

- Ingest offers **Clean video** as the primary action and **Dissect video** as
  the secondary action.
- Clean video uploads and probes the source only. It does not run Smart Cut
  analysis.
- Clean opens on the full source with its frame, rows and one sticky action.
- Primary action: **Find text & clean** — scan, fill and encode.
- High-confidence rows inside the source are ticked by default. Low-confidence
  rows stay visible behind a review path.
- Method: AI fill with LaMa by default; Blur and Crop guard are available.
  Missing models disable AI fill only and say why.
- Video under three minutes runs in one action. Video of three minutes or more
  scans first, then shows the fill estimate and waits for a second click. No
  modal.
- Cancel removes the partial file. Nothing partial is ever offered as a result.
- Result: **Download**, **Make a reel**, **Clean again**.
- Nothing found: no wasted render. Say so and offer **Make a reel**.

## Clean cut flow

- After analysis, the result screen has an **Edit | Clean** switch.
- Clean is a focus mode: frame on the left, one rail on the right, one sticky
  action. Audio, text, effects, script and moments are one switch away in Edit.
- Editing features are not removed. Clean only changes the mode.
- Found rows are one per distinct text and do not overlap in time within a lane.
- Clicking a row opens its moment, seeks to start minus 0.5 seconds and
  highlights the box. Rows outside the cut say **Not in this cut** and do not
  move. Double-click opens the row detail.
- The top-bar work-file cleanup is renamed **Clean work files…** and lives in
  the job overflow, so it cannot be confused with text removal.

## Success

- From the ingest screen to a downloaded clean video: three clicks, no scroll.
- From the result screen to a downloaded clean cut: three clicks, no scroll.
- A real clip's before/after preview matches the rendered file.
- Full test suite green. No skipped acceptance because a real file is absent
  may be called done.

## Boundaries

- No timeline.
- No rights gate, attestation, watermark refusal or per-video tick.
- No Cover / Plate method.
- No Studio page imports.
- No new AI model.
- No automatic `main` merge. Classic ships on its own branch with signed
  commits through `scripts/ship-lane.sh`.

## Platform

Web app served from a local Python server. macOS is the primary target; Windows
and Linux run the same UI with cloud AI where native engines are absent. The
interface is English with a curated Vietnamese translation. Rendering, files
and caches stay on the machine.

Last updated: 2026-11-05, Classic at `70e51dd`.
