# Deep open-items plan

Status: Phase 0 — baseline audit and decisions  
Created: 2026-11-03  
Baseline commit: `3067c20`  
Source checkup: `docs/testing/studio-edit-deep-checkup.md`

This is a living plan. Append build, QC, QA, and test log entries. Do not delete older entries.

## Ground rules

- One item at a time.
- Plan the item.
- Build it.
- Run QC (code, contract, render) and QA (browser / real media).
- Run the automated suite.
- Append the result to the log.
- Ask the founder for a test after each phase.
- Do not call a phase complete until the founder test passes.

## Phase 0 — baseline and decisions

Goal: confirm the remaining gaps and lock the behaviour of each item.

### Baseline audit

| Item | Current state | Evidence |
|---|---|---|
| Painter mask | not implemented | Clean kinds are box-based; `mask` is a rectangular cover kind, not a brush |
| Cross-video audio under Voice-over/Dub | primary source only | `audio._source_audio_bed()` decodes one source; `original` mode uses `render._audio_track()` per clip |
| Photo upload browser test | missing | Route exists; no browser upload test |
| Optical flow / stabilization real-clip QA | missing | Filter-chain compile test only |
| HDR | disabled | `edits.normalize_output()` rejects `hdr: true` |
| Automated suite | 2040 passed, 11 skipped | `docs/testing/studio-edit-deep-checkup.md` |

### Decisions required

- Painter target, mask shape, model, time range, and cross-clip support.
- Voice-over/Dub policy for added clip audio.
- Dub “remove original” policy when the cut has multiple sources.
- Photo duration and motion.
- Optical-flow/stabilize real-media test clip, strength, and FPS policy.
- HDR: keep disabled or define a 10-bit milestone.

### Locked decisions

- Painter result: **AI fill / inpaint**.
- Painter engine: **Auto / STTN default**.
- Painter shape: **freehand output-space mask**, not a box.
- Painter home: **on the detected text layer**. Each detected text can stay as-is or switch to a paint-brush mask for less-impact inpainting.
- Painter timing: **one clean layer with start/end**. Default start at the playhead.
- Painter is non-destructive: it writes a layer and timestamp; it does not touch video or clips during edit.
- Added clip audio under Voice-over/Dub: **duck under voice by default**. Keep the layer and mix at render.
- Dub “remove original voice”: expose the choice in Edit; **ask again in the Finish queue**; keep every layer until render.
- Photos in Moments: **2.5s static clip, editable duration**.
- Photo overlays in Elements/FX: **free overlay**, default 2.5s at playhead; **keep PNG alpha**.
- Optical-flow/stabilize QA: **existing Studio media**.
- HDR: **keep disabled** with a precise tooltip and a documented 10-bit milestone.
- Phase test gate: **live 8795 + short checklist**.

### Build

No product code until Phase 0 is approved.

### QC

- Confirm no existing feature regresses.
- Confirm each decision is represented in the Edit schema.

### QA

- Founder reviews the plan and answers the questions.

### Test gate

- Founder confirms the phase 0 decisions.

### Log

- 2026-11-03: Phase 0 baseline audit recorded. No code changed. Questions sent.
- 2026-11-03: Decisions locked: AI fill/STTN painter on detected text layers, output-space mask with start/end; duck added audio under voice; Dub choice repeated in Finish queue; 2.5s editable photo clips plus free photo overlays with PNG alpha; existing media for optical/stabilize QA; HDR stays disabled; live checklist after each phase.
- 2026-11-03: Phase 0 awaiting founder approval. No product code changed.

## Phase 1 — painter mask

Goal: replace Clean’s box-only selection with a freehand mask.

Locked behaviour:

- Each detected text row gets two cleanup choices: keep the detected box, or replace it with a paint-brush mask.
- The brush writes a freehand mask on that Clean layer, in output-frame coordinates.
- The layer keeps its own start/end. Default start is the playhead.
- Edit writes only the layer. No video or clip is modified.
- Render uses AI fill / inpaint with Auto (STTN default) and the mask.
- One layer per detected text; the layer can be erased stroke-by-stroke.

Planned build:

- Brush tool in the preview, enabled from a detected text row.
- Mask points stored on the existing Clean layer.
- Output-space mask rasterized into the source-space mask at render.
- AI fill route accepts mask points, not only a box.
- Stroke undo and clear.
- Mask highlight on the preview.
- Mask survives save, reload, aspect switch, trim and render.

Planned QC:

- Schema round-trip.
- Mask survives a save/reload.
- Empty mask and tiny mask handling.
- Existing box Clean still works.
- Render parity between preview mask and rendered cut.

Planned QA:

- Draw a mask around burned-in text.
- Confirm highlight, erase, undo, and clear.
- Confirm preview and render agree.

Test gate:

- Founder test on one real clip.

Log:

- 2026-11-03: Build complete. Added `mask` points to Clean layers, output-space painter tool, detected-text Paint action, source-space mask conversion, `textfill` mask rectangles, mask highlight, clear-mask, and mask persistence.
- 2026-11-03: QC passed. Mask schema round-trip, output-space → source-space conversion, mask rectangle generation, and Save/reload browser test.
- 2026-11-03: Browser QA passed. `tests/browser/fill_flow.spec.mjs` now creates a 13-point painter mask on a detected subtitle, saves it, and reads the points back from the Edit.
- 2026-11-03: Full suite: **2043 passed, 11 skipped**. Impeccable detector: **0 findings** on the changed Edit files.
- 2026-11-03: First founder live test failed: Paint was visible but no orange mask appeared. Automated painter test still passes with 13 saved points. Suspect a cached old `preview.js` because the Paint tool was added after the previous module version. Added a versioned `preview.js` import and bumped the page/CSS to `20261103-12`. Awaiting retest.
- 2026-11-03: Wireframe mismatch reported separately. Phase 1 remains open until the founder names the exact layout delta and retests Paint.
- 2026-11-03: Mask schema moved to stroke objects (`{space, aspect, strokes:[{id, r, points}]}`) with a flat-point legacy adapter on save and render.
- 2026-11-03: Fixed mask loss on save: `normalize_clean` reused the layer `radius` name for the stroke radius, so the validator rejected the saved layer with `clean[N].radius must be an integer`. Stroke radius now has its own name.
- 2026-11-03: Fixed Paint with no target: the toolbar creates a visible paint layer at the playhead. The found-row brush reuses the linked paint layer, and Shift-click adds another Clean layer for the same found text.
- 2026-11-03: Compact Clean: removed the long intro, Rights card when attested, warnings card, huge found rows, and the side “Preview this frame” block. Found rows now seek and highlight on click; only the tick box changes removal.
- 2026-11-03: Found markers are drawn in the existing Clean timeline lane, same colour, and can link to one or several Clean layers.
- 2026-11-03: Engine Before/After now runs on the preview stage for the selected Clean layer only. It posts draft Clean layers with `layer_ids`, compiles on the same scene, and never saves the Edit first.
- 2026-11-03: QC: painter mask round-trip (flat + stroke), scoped fill preview, found-list browser flow, compare overlay, and compact Clean UI tests pass.
- 2026-11-03: Review fixes: found rows now carry tracklet ranges so row click seeks; the miss notice survives render; Space/Enter on the tick does not activate the row. Clean tab teardown no longer clears timeline markers. Playhead-to-source mapping sets paint layer ranges after a trim. Cancelled paint strokes clear ghost dots and a stale paint target is dropped when another layer is selected. Duplicate found-marker seek removed.
- 2026-11-03: Render fixes: `textfill.span_key` now hashes the mask, so painting more or clearing a mask cannot reuse an old filled clip. Mask radius is round on both axes. Saved `mask.aspect` must match the Edit aspect or the box is used. Mask points outside the crop are dropped, and more than 20 strokes is a clear save error.

## Phase 2 — cross-video audio under Voice-over/Dub

Goal: added clip audio is handled intentionally when the main audio plan is Voice-over or Dub.

Locked behaviour:

- Original audio under Voice-over/Dub is built from every clip’s own source.
- Added clip audio ducks under the voice by default.
- Every audio layer stays in the Edit. Nothing is stripped during edit.
- Dub’s remove-original choice appears in Edit and repeats in the Finish queue.
- Render applies the final mix choice.

Planned build:

- Build the original bed from every clip’s own source, not only the primary video.
- Pass that bed into the mixer.
- Add per-clip ducking according to the existing duck setting.
- Keep original-only mode unchanged.
- Add the remove-original choice to Edit and the Finish queue.

Planned QC:

- A two-source cut produces a bed containing both sources in order.
- Voice-over ducks the bed at the chosen level.
- Dub respects the remove-original policy.
- Silence and missing-audio assets are handled.

Planned QA:

- Two real clips, one primary and one added.
- Voice-over and Dub comparison.

Test gate:

- Founder listens to both mixes.

Log:

- pending.

## Phase 3 — photo upload browser QA

Goal: prove a real photo can be uploaded, added, previewed, saved, and rendered from the browser.

Locked behaviour:

- A photo in Moments is a 2.5s static clip with editable duration.
- A photo in Elements/FX is a free overlay, 2.5s at the playhead, with editable position, size and rotation.
- Transparent PNG keeps its alpha.

Planned build:

- Browser test fixture with a real JPEG/PNG.
- Browser upload through the Photos tab.
- Assert the asset tile appears and the clip is added.
- Assert the saved Edit contains the asset and file clip.
- Assert the render uses the photo clip.
- Add the photo overlay object and its timeline lane.

Planned QC:

- Unsupported format error.
- Very large image.
- HEIC failure message if the host lacks HEIC decode.
- Portrait and landscape image crop.

Planned QA:

- Founder uploads a real photo.

Test gate:

- Founder confirms the photo appears as a 2.5s clip.

Log:

- pending.

## Phase 4 — optical flow and stabilization real-media QA

Goal: verify the filters on a long real clip, not just a compile string.

Locked behaviour:

- QA uses existing Studio media, not a new synthetic clip.
- Strength defaults to 0.5.
- Optical flow does not force 60fps; it follows the chosen output FPS.

Planned build:

- A reproducible 15–30s segment from existing Studio media.
- Compare off/on and strength levels.
- Check render time, file size and artifacts.
- Record the FPS used by the test.

Planned QC:

- No dropped frames or black frames.
- Audio stays in sync.
- Stabilize does not crop out the subject.
- Output FPS matches the setting.

Planned QA:

- Founder watches the rendered comparison.

Test gate:

- Founder accepts the on/off comparison.

Log:

- pending.

## Phase 5 — HDR decision

Goal: either ship real HDR or keep it disabled with a clear product line.

Locked decision: **keep HDR disabled** for this pass.

Planned build if disabled:

- Keep the disabled button and replace the tooltip with the supported-output explanation.
- Document the 10-bit milestone and the SDR-only limitation.
- Add a test that `hdr: true` is rejected with the current message.

Test gate:

- Founder chooses.

Log:

- pending.

## Global verification

Run after each phase:

```bash
python3 -m pytest -q -p no:cacheprovider
```

Browser checks:

```bash
python3 -m pytest -q -p no:cacheprovider \
  tests/test_browser_edit_layout.py \
  tests/test_browser_trim.py \
  tests/test_browser_fill_flow.py
```

No phase ships with a failing full suite.
