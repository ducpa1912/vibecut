# Studio UI revamp — P2 found text and fill preview (2026-11-02)

Base: `1c6fc43` (P1 Layers and editable boxes). Branch: `studio`.

## Summary

Remove text now starts from the text Check actually found. The panel lists
each region with a thumbnail of the frame, the words read, its time and a
tick. Watermarks and screen-recording UI stay visible but greyed, with the
server's reason, and cannot be ticked.

Ticked regions are removed with one action and one method: **AI fill**,
**Blur** or **Cover**. AI fill offers the two engines the server reports as
ready (STTN for video, LaMa per frame). The chosen ticks and method go to the
existing auto-clean route, so the rights gate and watermark refusals still
live on the server.

With AI fill, **Preview this frame** runs LaMa on the current frame only and
shows a before/after slider. The full render still fills every frame.

## What changed

### Server

- `GET /api/fill/status` — which fill engines are present on this Mac, the
  default, and whether the single-frame preview is available. The UI never
  offers AI fill when its model is missing.
- `GET /api/jobs/{id}/check/tracklets/{tracklet_id}/thumb` — a small crop of
  the source frame around one found region. The panel requests it lazily and
  caches it per Check report.
- `POST /api/jobs/{id}/edits/{edit_id}/auto-clean` now accepts
  `tracklet_ids`, `method` (`auto`, `ai`, `blur`, `cover`) and
  `fill_method`. Only ticked ids are sent, and the server maps them to the
  chosen kind. `auto` keeps the old behaviour.
- `POST /api/jobs/{id}/edits/{edit_id}/fill-preview` — one LaMa fill of the
  current frame, returned as before/after JPEG data URLs. It uses the same
  source crop, scale, clean pre-filters, colour filters and overlays as the
  render. Results are cached by Edit hash, frame and model stamp.
- `textfill.fill_frame` — the one-frame LaMa path used by that route.

### Editor

- `static/studio/edit/layers/clean.js`
  - found-text list with thumbnails, ticks, Select all / Clear ticks and
    greyed reasons for watermarks and screen UI;
  - method and engine pickers; Remove all sends only the ticks;
  - AI-fill preview with a before/after slider and client-side cancel;
  - found regions are pushed to the preview as dashed boxes before they
    become Clean layers.
- `static/studio/edit/index.js` — keeps the found rows for the preview,
  saves before the fill preview, and preserves the inspector scroll position
  while ticking or previewing.
- `static/studio/edit/preview.js` — draws found text on the preview, skips
  regions already added as Clean layers, and colours ticked, unticked and
  refused boxes differently.
- `static/studio/edit/edit.css` — found list, thumbnail, tick, method,
  compare-stage and slider styling.

## Verified

- Node: `autoCleanRequest` sends `tracklet_ids`, `method` and `fill_method`.
- Server: ticks select only the requested tracklets; AI/Blur/Cover set the
  right kinds; unknown methods are rejected; status reports missing and ready
  models; thumbnail returns a JPEG crop; fill-preview returns different
  before/after JPEGs and reuses the cache.
- Node: `textfill.fill_frame` changes only the masked pixels and names a
  missing LaMa model.
- Mounted Chromium at 1280×900 with a synthetic Check report:
  - three found rows, two blocked with “Never removed”;
  - thumbnail visible, one allowed tick, AI fill + LaMa chosen by default;
  - Remove all sends only `trk_sub` with `ai`/`lama`;
  - the added Clean layer appears in Layers and the timeline;
  - Preview this frame shows the before/after slider and moves it.
- P1 layout and draw/move/resize/delete browser tests still pass.
- Full suite: **2011 passed, 12 skipped, 1 deselected**. The deselected
  Voice Room browser test also fails on `88eeab9`.

## Known limits

- The single-frame preview always uses LaMa. STTN is available for the full
  render, not for one frame.
- Cancel stops the browser request; the server fill already in flight may
  finish and cache its result.
- The preview keeps the saved Edit as the source of truth. The panel saves
  before asking, so a just-ticked removal is included.
- The compare uses the draft-sized frame (540×960 for 9:16) and the render's
  overlays; the final render is still the authority.

## Next

P3 is polish: spacing and type scale across Edit, icons, layer colours,
keyboard shortcuts with a `?` sheet, and empty states. P4 brings Import,
Moments and Finish into the same frame.
