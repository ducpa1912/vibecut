# Edit UI revamp — plan

Status: P0 to P4 built (`ui-revamp-p0.md` to `ui-revamp-p4.md`). Recorded look: `DESIGN.md`.

## P0
1. Remove the obsolete Moment bar. Story selector moves into Preview head.
2. Left rail becomes icon-only: Moments (library), Element (sparkles), Text (T), Audio (music).
3. Moments actions become `Import` and `Add scenes`.
   - Import: compact square modal for Photo / Full video, with drop, file pick, link/path.
   - Add scenes: compact modal with `This Project` and `Library`; groups by video, scenes sorted by time, selected video highlighted, small thumbs, `Cut another video`.
4. Preview Back / Forward step to previous / next scene.
5. Clean: `Check this scene` filters the Check report to the active scene; `Scan video` runs the whole pass. Row click seeks only. Brush creates/uses a paint layer and disables the row. Detail fields fold.
6. Fill models: start the Studio server with the lane model folder so STTN and LaMa report ready.

## P1
7. Preview: visible layout border, view zoom + pan + fit, span In/Out at sentence edges.
8. Audio tab: Library / Upload / GenAI music only.
9. Narrative: Original / Voice-Over / Dub mode buttons; music removed; voice controls compact.
10. Captions: style and lines folded by default.
11. Look: note only; full grading/filter revamp is deferred.

## Deferred deep dives
- Each rail item (Moments, Element, Text, Audio) still needs its own full deep-dive pass; this pass only revamps Moments, with Audio/Narrative structure as the first split.
- Element/FX panel.
- Color grading + filters: LUT import, before/after, per-scene look, preset previews.
- Voice clone model setup and advanced clone controls.
- Original-sound speed control: needs an `audio.speed` schema field and a render-time `atempo` path. Fade, loudness and peak already work.
- Scene-scoped backend OCR pass (current `Check this scene` filters the existing report).

## Acceptance
- No Moment bar; Story selector works in Preview and flushes saves.
- Rail has four icons with tooltips and aria labels.
- Both Moments modals open over Edit; duplicate scene add blocked; groups sorted by video/time.
- Prev/next goes to scene boundaries.
- Detected row click does not expand; painted row cannot start another paint.
- Audio/Narrative split holds; no BGM controls under Narrative.
- Caption panel starts folded.
- Full test suite green.


## Built
- Moment bar removed; Story selector lives in Preview and uses the existing save-flush switch path.
- Left rail is icon-only with Moments / Element / Text / Audio; labels stay in `aria-label` and `title`.
- Moments has `Import` and `Add scenes`.
  - Import mini modal: Photo / Full video, drop or file pick, link/full-path field, Import button. Links use the downloader; local paths attach in place.
  - Add scenes modal: This Project / Library, video groups, time-sorted thumbnails, selected video state, used-scene dedupe, `Cut another video`.
  - Backend: `POST /assets/video`, `POST /assets/video-path`, `POST /assets/video-url`.
- Preview Back / Forward step to scene boundaries; story selector, zoom, Fit, drag-to-pan when zoomed, In / Out span.
- Clean: `Check this scene` and `Scan video`, no duplicate scan while running. Row click only seeks. Brush creates/reuses the paint layer, then disables. Box/timing folds.
- Audio tab is music-only (`Library / Upload / GenAI`). Narrative is voice-only with Original / Voice-Over / Dub tabs.
- Captions style and lines start folded; each cue keeps its time fields behind a Time fold. Look has a deferred-revamp note and folded fine-tune controls.
- Fill models: server started with `VIBECUT_FILL_MODELS=~/vibecut-lanes/studio/models/fill`; `/api/fill/status` reports STTN and LaMa ready.

## Verification
- Full suite: **2054 passed, 11 skipped**.
- Browser: Edit layout + scene stepping + Import mini + Add scenes modal; fill flow still passes.
- `Check this scene` now runs a source-time scoped OCR pass (`start`/`end` on `/check`); `Scan video` runs the full pass. Report scope is reused, so pressing the same scope twice does not re-run.

## Clean revision (2026-11-04)
`clean-fill-revision-plan.md` changes the Clean lines above:
- Clean offers AI fill and Blur only, set per box. Cover and Mosaic are gone.
- Found text and layers read as one row per text, with its time pieces inside. Layers outside the moment fold into one line.
- Opening Clean brings the Clean lane into view. The timeline resizes by its top edge, and Clean and timeline text is at least 11 px.
