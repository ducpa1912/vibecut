# Loop 18 brief — Cut grading

Request: **REQ-20261112-04** (revision: Cut phase 2).

> "move color grading, preset filter into this block".

## What must exist

1. Four grade sliders in **Cut → Look**: Exposure, Contrast, Saturation, Temperature, each −100…+100,
   default 0, with reset.
2. The values live in `edit.cut.grade` and survive a reload.
3. The render applies them with ffmpeg, after crop and scale, before the frame-rate filter.
4. The player previews them live and says it is approximate.
5. No grade → the old render chain, unchanged.

## Acceptance

| Probe | Pass |
|---|---|
| Neutral | no `exposure`, `eq` or `colorbalance` filter added |
| Exposure +100 | proof frame mean luminance rises |
| Saturation −100 | proof frame chroma collapses |
| Temperature +100 | mean R−B rises |
| UI | 4 sliders; input updates the player filter; change saves; reset returns 0 |
