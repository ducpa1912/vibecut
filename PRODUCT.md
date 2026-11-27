# VibeCut Classic

Classic is a second supported VibeCut product, separate from Studio. It turns a
source video into either a clean video or a short reel built from moments. It
has no editing timeline. Clean has a range timeline for detected text.

Classic has no rights gate, attestation tick, watermark refusal or per-video
settings lock. The founder is responsible for having permission to edit the
footage; the UI carries a plain responsibility notice.

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
- **Review before spend.** A scan prepares candidates. It does not render until
  the operator has reviewed them and pressed the clean action.
- **On-device first.** Vision, speech and AI fill run locally where available.
  Cloud AI is used only where a route is configured and a native engine is
  absent.
- **Quiet dark interface.** One accent, one primary action, readable type at
  11 px minimum, and no decorative chrome.

## Clean workspace

Clean is one bounded workstation, not a long scrolling page.

- **Frame**: the largest element, source aspect in Source Clean and the cut
  aspect in Cut Clean. The frame is sized from its own compartment, never from
  the whole window, so its box handles stay reachable.
- **Phases**: a four-step strip in the top bar — **Scan → Review → Clean →
  Render**. The first three report state. **Render** is a shortcut to the same
  reviewed primary action and stays disabled until a row is ticked or a layer
  exists.
- **Selected box**: clicking any box on the frame — saved or auto-scanned —
  selects its region row and timeline bar, scrolls both into view, and exposes
  **Unselect** plus the **AI / Blur** method toggle at the box's outside
  top-right corner. A first drag or resize of an auto-scanned box creates its
  Clean layer; a plain click only selects it. The row and bar keep the time
  inputs, so the range can be extended or trimmed.
- **Regions**: a scrollable list beside the frame. It contains detected text,
  manual boxes and brush masks. Selecting a row seeks the frame, highlights the
  row and its box, and keeps the list in place.
- **Timeline**: a compact strip under the frame and regions. It has one ruler,
  one row per lane, zoom from 1× to 32×, Fit, horizontal scrolling and a
  playhead. Bars are slim; labels appear on hover, selection or keyboard focus.
- **Actions**: one primary action. AI fill status is a chip with an engine menu
  and a Fill options popover that opens upward in Clean.
- **Type floor**: 11 px for every visible label, including row times and ruler
  ticks.

On desktop the workspace is bounded to 960 px and centred. At 1280×800 the
verified layout uses a 248×440 frame, a 139 px timeline, a 44 px lane area, a
51 px region row, and a page exactly 800 px tall. No page scroll and no console
errors.

## Clean video flow

- Ingest offers **Clean video** as the primary action and **Dissect video** as
  the secondary action.
- Clean video uploads and probes the source only. It does not run Smart Cut
  analysis.
- Clean opens on the full source with its frame, regions and one primary action.
- Clean review defaults to **Review first**: **Find text** scans only, and
  **Clean N texts & render** applies the ticked rows and renders. **One click**
  is an opt-in Setup choice that scans, cleans and renders in one action.
- A scan never adds a layer or starts a render on its own.
- High-confidence rows are ticked by default. Low-confidence rows stay visible
  with a plain **review** note.
- Method: AI fill with LaMa by default. Blur, MI-GAN, Telea and Navier-Stokes
  are exposed when installed. Missing models disable only that engine and name
  the recovery.
- LaMa runs on the Apple GPU through PyTorch MPS when `big-lama.pt` and PyTorch
  are present; otherwise it runs on the CPU through ONNX Runtime. Apple
  Intelligence is not an AI-fill engine in Classic.
- Cancel removes the partial file. Nothing partial is ever offered as a result.
- Result: **Download**, **Make a reel**, **Clean again**.
- Nothing found: no wasted render. Say so and offer **Make a reel**.

## Clean review queue

Classic can prepare several files without rendering any of them.

- Select multiple videos in the drop area or use **Add folder**.
- The queue processes files one at a time: upload as `source_ready`, run Check,
  convert detected rows into AI fill layers, and save a source review record.
- No Clean render starts. Every prepared file waits for a human review.
- The first completed file opens in Source Clean. Each completed row offers
  **Review**.
- Completed job IDs persist across reloads. File handles do not: a reload cannot
  resume an unprocessed local file. Re-add it.
- Failures are shown per file and do not stop the rest of the queue.

## Clean cut flow

- After analysis, the result screen has an **Edit | Clean** switch.
- Clean is a focus mode: frame, region list and compact timeline. Audio, text,
  effects, script and moments are one switch away in Edit.
- Editing features are not removed. Clean only changes the mode.
- Found rows are one per distinct text and do not overlap in time within a lane.
- Clicking a row seeks to its start − 0.5 seconds, highlights the box, and opens
  the row detail on double-click.
- Rows outside the cut say **Not in this cut** and do not move the playhead.
- The top-bar work-file cleanup is renamed **Clean work files…** and lives in
  the job overflow, so it cannot be confused with text removal.

## Success

- From ingest to a downloaded clean video: three clicks in One click, four in
  Review first (Find text, review, Clean, Download). No page scroll at 1280×800
  or 1440×900.
- From the result screen to a downloaded clean cut: three clicks, no page scroll.
- A real clip's Before/After preview matches the rendered file.
- The full suite is green. No skipped acceptance because a real file is absent
  may be called done.
- Only the founder may record acceptance.

## Boundaries

- No editing timeline. Clean has a range timeline for detected text.
- No rights gate, attestation, watermark refusal or per-video tick.
- No Cover / Plate method.
- No Studio page imports.
- No new AI model beyond the shared fill engines.
- No automatic `main` merge. Classic ships on its own branch with signed
  commits through `scripts/ship-lane.sh`.

## Platform

Web app served by a local Python server. macOS is the primary target; Windows
and Linux run the same UI with cloud AI where native engines are absent. The
interface is English with a curated Vietnamese translation. Rendering, files
and caches stay on the machine.

Last updated: 2026-11-18. Clean workspace usability revision and review queue
are built in the working tree. Founder clean-video acceptance is **PENDING**.
