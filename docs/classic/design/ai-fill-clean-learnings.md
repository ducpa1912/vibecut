# AI fill for Clean: learning from Studio

Status: C2a (Blur/Cover) is built; C2b (AI fill) is not built.
Source of lessons: Studio commits `7ce8dcf` (Clean/fill revamp) and `e274b45`
(license audit), plus the Studio `textfill/` package.
This document is a port checklist, not an instruction to copy Studio UI.

## 1. Current Classic state

Classic already has:

- Clean boxes stored on the cut (`job["classic_text"]["cuts"][clips_hash]`)
- box draw/move/resize, layers, eye toggle, undo/redo
- Blur, Cover and Crop methods
- `GET /api/classic/fill` status with model files and licenses
- locked AI-fill row when models are missing
- `POST /api/classic/jobs/{id}/fill/preview` that returns `409 model_missing`
  until the pack exists

Classic does **not** have:

- `textfill/` at all
- a render fill pre-pass
- a real fill preview
- a `fill` kind mapping to the Edit layer

Two current traps must be fixed before enabling AI fill:

1. `routes_classic.CLASSIC_CLEAN_KINDS["fill"]` currently maps to `"blur"`.
   Selecting AI fill saves a blur box. A real fill port must map to `"fill"`
   and add the engine (`method`) plus `tracklet_id`/`tracklet_kind`.
2. The fill preview route returns `501 not_implemented`. Enable it only when
   the model pack and the pre-pass are both present.

## 2. What AI fill actually is

AI fill is a **render pre-pass**, not a CSS effect:

1. The Edit has a Clean layer with `kind: "fill"`.
2. `compose_render` emits a fill plan for active segments: layer box, source
   ranges, engine.
3. `render.py` calls `textfill.prepare_span` once per active span.
4. `textfill` cuts that source span, runs STTN (video) or LaMa (per frame), and
   writes a cached filled clip.
5. The beat reads the filled clip instead of the source; the normal crop, motion,
   captions and overlays apply on top.

If any of those is missing, the UI can say “AI fill” but the render still blurs.

## 3. Model pack and licenses

| File | Engine | Size | License |
|---|---|---:|---|
| `sttn_infer_model.pth` | STTN, video/subtitle band | 66,271,967 B | Code MIT (researchmm/STTN); weights Apache-2.0 via YaoFANGUK/video-subtitle-remover |
| `lama_fp32.onnx` | LaMa, per-frame | 208,044,816 B | Apache-2.0 (Carve/LaMa-ONNX, big-lama) |

- Default Classic path: `~/vibecut-lanes/classic/models/fill` or
  `VIBECUT_FILL_MODELS`.
- Classic's `FILL_LICENSES` currently labels STTN as “MIT”; that is the code
  license only. The weights notice must say Apache-2.0 plus the MIT code notice.
- Include the two license texts and model source URLs in the Classic release.
- Missing model = explicit locked state; never silently fall back to Blur while
  claiming fill.

## 4. Schema lessons

Studio's final shape for one fill layer:

```json
{
  "id": "cl_fill_01",
  "kind": "fill",
  "method": "sttn",
  "box": {"x": 0.1, "y": 0.76, "w": 0.8, "h": 0.09},
  "ranges": [{"start": 12.0, "end": 18.0}],
  "tracklet_id": "trk_sub",
  "tracklet_kind": "subtitle",
  "label": "Remove subtitle",
  "z": 0,
  "color": "#000000",
  "opacity": 1,
  "radius": 12
}
```

What Classic actually shipped, and why it differs:

- Classic's own `method` already means `blur | cover | crop | fill` for every
  box. It cannot also mean the engine. A fill layer therefore stores
  `method: "fill"` **and** `engine: "sttn" | "lama"`. `engine` is present only
  on fill layers; a non-fill layer has none.
- `routes_classic._classic_clean_edit` translates a Classic fill layer into an
  Edit layer with `kind: "fill"` and `method: <engine>`, because that is the
  name `edits.normalize_clean` and `textfill` use. The translation happens at
  the boundary; the Edit document is never stored by Classic.
- The engine is validated only for fill layers: an unknown engine is an error,
  and an engine whose model or runtime is missing is refused on its own. STTN
  installed without LaMa still fills subtitles.
- A painter mask (`mask.strokes`) is a later Studio feature; box-only fill is
  enough for C2b. Do not invent a new mask shape in Classic.

Coordinate contract (as built in C2a):
- Classic stores every box **source-normalized**, not cut-space. Drawing and
  dragging convert with the crop the frame route returns in `X-VibeCut-Crop`;
  `X-VibeCut-Segment` names the segment that crop belongs to.
- A drawn box gets its clip's cut window as ranges; a scan box gets the scan's
  source ranges translated to cut ranges. `_cut_ranges_to_source` translates
  back for the Edit document, because `compose_render._active_window` compares
  source time.
- A range outside every clip is “not in this cut”, not a box.
- Stored boxes from before C2a are version 1 and are dropped on load with a
  `clean_reset` count, never reinterpreted.

## 5. Engine choice

| Content | Recommended engine | Why |
|---|---|---|
| Subtitles / lower-third band | STTN | Trained on subtitle strips; temporal consistency |
| Arbitrary overlay text on complex backgrounds | LaMa | Better single-frame reconstruction; slower per frame |
| Mixed layers on one beat | One engine per beat | Studio's compiler picks the topmost active fill layer; mixed engines are warned |

Classic can expose an engine select when both are installed, defaulting to
STTN for `tracklet_kind == "subtitle"` and LaMa for manual overlay boxes.
Do not run both engines on the same span.

## 6. Port order for Classic C2b

1. **Import shared backend pieces.** Add Studio's `textfill/` package as
   shared backend code (additive, tested from Classic): `__init__.py`,
   `mask.py`, `sttn.py`, `lama.py`.
2. **Render hook.** Port the fill pre-pass from Studio `render.py`:
   `_prepare_fills`, fill cache keys, `textfill.release_fillers` after render.
   The cache key must include the model stamp and the fill layer signature.
3. **Compiler.** Ensure `compose_render` emits the fill plan for Classic cuts.
   If the shared compiler already has it, only pass the engine through.
4. **Schema.** Change `CLASSIC_CLEAN_KINDS["fill"] = "fill"`; carry `engine`,
   `tracklet_id`, `tracklet_kind`; validate through `edits.normalize_clean` by
   passing the engine as its `method` for fill layers only.
5. **Status.** Keep `GET /api/classic/fill`; add package/runtime checks so
   “installed” means model + torch/onnxruntime, not just a file on disk.
6. **Preview.** Replace the `501` stub with one LaMa frame:
   - body: clips, clean layers, overlays, effects, t, aspect (the unsaved box
     arrives inside `clean`; there is no separate `box` field)
   - compile the current cut with the box as a fill layer
   - extract the source frame, run `textfill.fill_frame`, return before/after
   - no save before preview; cache by edit hash + frame + model stamp
7. **UI.** Enable AI fill only when status is ready. Add engine select + a
   before/after preview. Keep Blur/Cover as fallbacks. Do not add Studio's
   paint UI in this step.
8. **Tests.** See section 8.

## 7. Failure modes already paid for

These were real Studio bugs or review findings; do not repeat them:

- **Mask saved as `None`.** Server validation reused the layer `radius` variable
  for the stroke radius, so the layer radius became `0.025` and the save failed
  with `clean[1].radius must be an integer`. Keep schema variable names distinct.
- **Stale fill cache.** `textfill.span_key` must hash the mask/box and model
  stamp. Otherwise painting more or changing the model reuses an old filled clip.
- **Squashed mask.** A normalized radius applied to width and height separately
  makes an ellipse. Use square pixels (`ry = rx`) when rasterizing.
- **Aspect mismatch.** A mask painted for one crop must not be applied to a
  different crop. Fall back to the box or drop the mask with a warning.
- **Duplicate seek.** A found-marker click must seek once; two handlers cause two
  frame loads.
- **Fake ready.** Missing models must disable AI fill and name the files.
- **Save before preview.** The preview must compile the unsaved box, not require
  a save first.
- **Wrong mapping.** `fill → blur` is the current Classic bug; a saved fill box
  must compile to `kind: "fill"`.

## 8. Classic acceptance tests

- Model pack missing: status locks AI fill, Blur/Cover still work, preview
  returns `409 model_missing`.
- Model pack ready: AI fill selectable; one box compiles to `kind: "fill"` with
  the chosen engine.
- Full render: a subtitle box changes pixels inside the box and leaves pixels
  outside it unchanged on a real fixture frame.
- Preview: before/after differs only inside the fill box; no save request.
- Engine defaults: a scan subtitle tick gets STTN, a manual overlay gets LaMa,
  and each falls back to the other engine when only that one is ready.
- Ranges: a fill active only in one clip does not touch another clip.
- Reload/undo: `method: "fill"` and `engine` survive save/reload; the Edit
  layer it compiles to carries `kind: "fill"` and `method: <engine>`; undo
  restores the prior layer.
- Cache: changing the engine, the box or the model file invalidates the fill.
- Rights: a watermark or screen-UI box still refuses AI fill, and the rights
  lock refuses a fill box without the attestation tick.
- License: About/notices show STTN Apache-2.0, LaMa Apache-2.0 and MIT code.

## 9. What not to port

- Studio's icon rail, Layers panel, timeline, paint mask and Edit document.
- Studio `routes_studio.py` or `static/studio/**`.
- Studio's paint-mask UI; Classic C2b only needs boxes.
- The Studio full-fill cache directory layout unless it is shared and versioned.
- Any model pack hosting of Demucs weights (unresolved license, unrelated to fill).

## 10. Definition of done for C2b

- `fill` no longer maps to blur.
- `textfill/` is present and tested from Classic.
- A real single-frame preview returns before/after.
- A real render fills every active frame in the box.
- Missing model state is honest and Blur/Cover remain usable.
- Model licenses/notices ship with the pack.
- Classic suite and a real-video founder pass are green.
