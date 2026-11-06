# Clean video and Clean cut — build contract

Status: active build. Base: Classic `70e51dd` (LaMa only; STTN is retired).

This is the single contract for the build loop. A phase is not done until the
developer, QC, QA, tester and product owner each pass it. Do not mark a phase
done because tests pass; the product owner gate is separate.

## Current truth

- Classic has no rights gate, attestation, watermark refusal or per-video tick.
- AI fill is LaMa only. STTN is retired and must not be reintroduced.
- Clean methods: AI fill, Blur, Crop guard on a cut. Crop guard does nothing on
  a whole video at original size, so Source Clean offers AI fill and Blur.
- Clean layers are source-space boxes with optional brush masks and source-time
  ranges. The Edit clean schema is authoritative.
- The source is never modified. Every result is a new file.
- No timeline. Moments are the cut model.
- UI type floor is 11 px.

## Phase 1 — Source Clean backend

### Build

1. **Extraction-only job**
   - `POST /api/jobs/upload` and `POST /api/jobs/path` accept a `mode` of
     `clean` (default remains `reel`).
   - `_new_job` gains an `analyze` flag. When false it does not submit
     `run_analysis`; it sets status `source_ready`, message `Source ready`,
     `analysis` stays `None`, and the source probe fields are present.
   - Existing upload, path and URL jobs keep their current behaviour.

2. **Source plan**
   - One helper returns the full-source clip:
     `{scene: 0, start: 0, end: duration, dur: duration, role: "source"}`.
   - Source Clean uses those clips for the existing Clean save, check, estimate,
     preview and render bodies.
   - `classicPlanClips` in the browser later uses the same shape.

3. **Check without analysis**
   - `POST /api/jobs/{id}/check` accepts `source_ready` jobs with no analysis.
   - `detect.run_check` already samples the whole source when `scenes` is empty;
     do not invent a fake scene unless a real dependency requires it.
   - `GET /api/jobs/{id}/check` works for `source_ready`.
   - Check must report text boxes and ranges in source time.

4. **Source clean renderer**
   - New module `clean_source.py` (or an equally small dedicated module) with
     start, run, get and cancel.
   - Routes:
     - `POST /api/classic/jobs/{id}/clean/source/render`
     - `GET /api/classic/jobs/{id}/clean/source`
     - `POST /api/classic/jobs/{id}/clean/source/cancel`
   - Input is the existing Clean layer list. Validate with
     `routes_classic.normalize_classic_clean` or the shared Edit validator.
   - Output keeps the source display width, height and fps. Decoded pixels are
     upright; no rotation tag is copied. Video is encoded H.264/yuv420p; source
     audio is copied when present.
   - Fill uses `textfill.prepare_span` over `[0, duration]`; the returned filled
     clip is video-only. Mux the source audio over it.
   - Blur uses the same box-blur geometry as the cut renderer. Reuse
     `compose_render._clean_filters` where possible so the pixels match.
   - Crop guard is rejected or ignored in source mode with a plain reason; do
     not silently crop the source.
   - Cache the final file by source fingerprint, duration, layers, method and
     model stamp. A second run with the same input reuses it.
   - Cancel deletes the `.part` file and leaves no partial result.
   - Record stage timings: check, fill, encode, mux.
   - Release fill model sessions when the run ends, fails or cancels.

5. **Estimate and preview**
   - The existing `fill/estimate`, `fill/sample` and `fill/preview` endpoints
     must accept the full-source clip and return a useful estimate/preview.
   - Preview must use a source-aspect frame, not a 9:16 crop. Add a source frame
     route if the existing cut frame route cannot produce original dimensions.
   - Preview uses the same fill engine as the render and releases the model
     after one frame.

6. **Start analysis later**
   - `POST /api/jobs/{id}/analyze` starts `run_analysis` for a `source_ready`
     job. It is idempotent while analysis is active.
   - This is the handoff for **Make a reel**. Full merge behaviour is Phase 3.

### Acceptance for Phase 1

- Upload a file with `mode=clean`; the job returns `source_ready`, has no
  analysis and does not run the analysis pipeline.
- `POST /check` succeeds on that job and returns text rows in source time.
- Render returns a ready MP4 at the source width and height, with audio.
- Second render with the same layers is cached.
- Cancel leaves no `.part` file and no ready result.
- `POST /analyze` moves the job through analysis to `ready`.
- Full suite green. Classic tests green.

### Do not

- Do not touch the Classic page or its JavaScript in this phase.
- Do not reintroduce STTN.
- Do not change the existing 15/30/60 render behaviour.
- Do not add rights checks.
- Do not generate or commit media files.

## Phase 2 — Ingest and Source Clean UI

### Build

- Ingest action row: primary **Clean video**, secondary **Dissect video**.
- Clean video uploads with `mode=clean`, shows extraction progress, then opens
  Source Clean directly. No analysis wait.
- Source Clean opens the result screen in `cleanScope = "source"`:
  - frame on the left at source aspect;
  - Clean rail on the right;
  - Edit, moments, Smart Cut, audio, text, effects and script hidden;
  - no Edit | Clean switch in source mode; a back action returns to ingest.
- Rail:
  - source time, duration, frame count, engine;
  - found rows, high-confidence ticked by default;
  - a visible review path for low-confidence rows;
  - one sticky action: **Find text & clean**.
- One-action pipeline:
  - scan, apply the auto-ticked rows, render;
  - under 3 minutes runs through;
  - 3 minutes or more scans, then shows **Clean N texts · ~X** and waits for
    the second click;
  - progress names the stage: Finding text, Cleaning, Encoding;
  - cancel leaves no partial file.
- Nothing found: no render. Say **No baked-in text found** and offer **Make a
  reel**.
- Models missing: AI fill is disabled, Blur remains, the reason is visible.
- Ready: **Download**, **Make a reel**, **Clean again**.
- Rows: click seeks to start − 0.5 s and highlights the box; double-click opens
  the detail strip. Source mode has no moment label.
- Before/After is in place on the frame, not a second image column.
- No second scan card in source mode.

### Acceptance for Phase 2

- Add a file, click Clean video, reach Source Clean without analysis.
- Primary action scans, cleans and renders in one click for a short clip.
- A 3-minute-plus clip scans, shows the estimate, then renders on the second
  click.
- Download returns the full-length, original-size file.
- Every state above has real copy and a recovery action.
- No console errors. Works at 1440×900 and 1280×800.

## Phase 3 — Make a reel handoff and layer carry-over

### Build

- **Make a reel** calls `POST /analyze`, polls, then opens the normal result.
- Source Clean layers are stored once and merged into the cut's Clean layers
  without duplicating rows or boxes.
- A later cut can exclude or edit a carried layer; the source copy is unchanged.
- Source layers never force a cut to re-render until the user asks.

### Acceptance for Phase 3

- Clean a whole video, click Make a reel, wait for analysis, and see the source
  Clean layers on the cut.
- No duplicate layers. Ranges map to the cut correctly.
- Editing a cut layer does not change the source clean record.
- Full suite green.

## Phase 4 — Cut Clean focus mode

### Build

- Result screen has **Edit | Clean**. Edit is unchanged.
- Clean hides audio, text, effects, script, moments and Smart Cut; frame and one
  rail remain. One switch back restores Edit with its state.
- Merge the separate **Find text on screen** card into Clean. One scan entry.
- Rename the top-bar work-file **Clean** to **Clean work files…** and move it to
  the job overflow.
- Rail uses the same rows, detail strip, sticky action, high-confidence defaults
  and before/after behaviour as Source Clean.
- Cut primary: **Clean N texts & render**.
- Clicking an outside-cut row says **Not in this cut** and does not move.
- Double-click opens the row detail.
- One primary action per screen. Type floor 11 px.

### Acceptance for Phase 4

- Edit keeps every existing feature and state.
- Clean reaches the cut frame and rows with one click from Edit.
- Clean N texts & render reaches a rendered cut with one click.
- Outside-cut rows behave as specified.
- No duplicate scan control remains.
- Full suite green.

## Phase 5 — Polish and final gate

- Type, spacing, focus rings, keyboard, reduced motion, 11 px floor.
- Responsive: 1440×900 and 1280×800; rail becomes a bottom sheet under 1100 px.
- Copy review: controls name the action; errors name the problem and recovery.
- Playwright: no console errors, no horizontal overflow, click counts.
- Full suite green.
- Real-clip acceptance: founder-provided media, before/after matches preview and
  render, full-length download plays, cancel leaves no `.part`.
- Docs updated. Signed commits. `main` not moved.

## Deferred and carry-forward

- Real founder media acceptance and a real LaMa model pack are deferred to the
  Phase 5 gate. Synthetic temp clips prove the pipeline, not the final quality.
- Rotation metadata is not copied. The decoded pixels are upright at the
  display size. If a source must keep its rotation tag, that is a separate
  pass; do not claim it in copy.
- Phase 2 must gate **No baked-in text found** on `text.confirmed`, not only on
  tracklet count, so a failed OCR pass cannot look like a clean source.
- Phase 2 must persist Source Clean layers through the existing Clean save route
  with the source clip, so Phase 3 can merge them into a cut.
- Phase 2 must treat a `ready` Source Clean record with a missing file as
  failed and offer a re-run, not a dead download.
- The source frame route paints Blur only. The filled "after" frame comes from
  `/fill/preview`; Phase 2 must pair them so the frame looks filled.
- A raw encoder failure can still expose ffmpeg text. Map it to a plain
  "Clean could not encode this source" message in a later copy pass.
- Phase 5: opening the cut at 0:00 can show the source's black fade; start the
  preview on the first usable frame or explain the fade.
- Phase 5: raw analysis detail can reach the frame tooltip; keep diagnostics in
  the detail strip, not in founder-facing hover copy.
- Phase 5: normalize Clean identity tokens across reloads and carried layers so
  the same text and box never compare as two identities.

## Review loop

Each phase runs: developer -> QC -> QA -> tester -> product owner. A failing
gate returns to the same developer with the findings. Record the verdict in the
commit message or the phase notes, not only in chat.
