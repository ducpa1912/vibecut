# Studio UI revamp — P1 Layers and boxes (2026-11-01)

Base: `85aeb49` (P0 fixed frame and text scan). Branch: `studio`.

## Summary

Edit now has a **Layers** list on the left and draws every Remove-text box on
the preview. A box can be created by drawing on the picture, moved, resized
from eight handles, and deleted with Delete — no percentage fields needed.

The list groups in timeline order: Remove text, Text, Captions, Effects,
Colour, Audio. Each group has a + button. Rows show the layer name, its time
and an eye toggle; Clean rows also warn when the box sits outside the current
crop. Clicking a row, a timeline bar, or a box on the picture selects the same
layer in all three places. Delete removes the selected layer.

## What changed

- `static/studio/edit/layers-panel.js` (new) — the grouped Layers list, +,
  row selection, eye toggles, warnings and Delete.
- `static/studio/edit/canvas-tools.js` (new) — pure crop and box geometry:
  source↔output mapping, source-time mapping through the story clips, scene
  crops, move/resize clamped to the source, handle hit-testing.
- `static/studio/edit/preview.js` — draws Clean boxes (dashed, coloured by
  method), selected outline and 8 handles, edge markers for boxes outside the
  crop; Select / Draw box tools; pointer drag, resize and delete feedback.
- `static/studio/edit/index.js` — Layers panel wiring, add/remove/hide,
  Delete key, box callbacks, local preview-only hidden layers.
- `static/studio/edit/timeline.js` — + on every track header; bars already
  selected layers, and now Clean track labels use the same words as Layers.
- `static/studio/edit/edit.css` — three-column frame (Layers, preview,
  timeline, settings), Layers styling, preview tool styling.
- `static/studio/edit/model.js` — Clean labels become “Remove text”, the
  timeline lane is “Remove text” / “Colour”.
- `static/studio/edit/layers/clean.js` — `manualLayer` accepts a drawn box,
  so Add box and Draw box create the same layer.
- Tests: `tests/test_studio_layers.py`, plus a mounted draw/move/resize/delete
  check in `tests/browser/edit_layout.spec.mjs`.

## Verified

- Geometry under Node: centre crop matches `compose_render._base_crop` for a
  1920×1080 source in 9:16; auto mode uses the active scene crop; box/frame
  round-trips; move and resize clamp; output time maps through clips.
- Mounted Chromium at 1280×720 and 1024×680: the layout still fits with the
  Layers list, settings stay on the right, timeline stays visible.
- Mounted Chromium at 1280×720: Draw box on the preview → one Clean row and
  one timeline bar; drag moves the box; drag the bottom-right handle resizes
  it; Delete removes the row and bar. No number fields involved.
- Focused suite: 62 passed.
- Full suite: 1994 passed, 12 skipped, 1 deselected
  (`test_voice_room_page.py::test_voice_room_page_in_chromium`, which also
  fails on `88eeab9`).

## Not in P1

Found-text thumbnails with ticks and the AI-fill before/after preview are P2.
The narrow-window icon rail for Layers, full inspector-by-selection and the
keyboard help sheet are P3.
