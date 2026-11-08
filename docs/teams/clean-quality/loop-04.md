# Clean quality loop 4

Date: 2026-11-08
Status: partial pass. Crash fixed. One title frame still fails.

## What changed

| Change | Result |
|---|---|
| LaMa run sizes round to 16 px, not 8 | Fixes the ONNX FFC broadcast crash (`62 by 63`) on 512×500 and 512×504 runs. Scene 03 now renders. |
| Full detected line box is the default hole | Removes glyph-edge halos and the dark seat hole on scene 03. Tight glyph masks stay behind `VIBECUT_FILL_TEXT_MASK=1` for comparison. |
| Proof cache version 9 | Old proofs made with the tight mask are not shown again. |
| Loop 4 tests | `test_clean_loop4.py` covers 16 px run sizes, the 512×500 case, and the default mask. |

## Evidence

Same test video, 46 s, 1080 × 1080, 24 fps.

| Frame | Before | After loop 4 |
|---|---|---|
| Scene 01, 1.8 s | Large title over sky | Clean. No dark component, no text remnant. |
| Scene 03, 8.625 s | `answers` over a train seat | Clean. Seat and armrest reconstruct naturally. No dark hole. |
| Scene 01, 3.5 s | `wrong room` title over grass | **Fail.** `wrong` is filled; the second line `room` remains. |
| Scene 07, 25.875 s | Title over mountain | Clean. |

## Remaining failure: scene 01 at 3.5 s

The detector records the bottom title as one tracklet, `wrong`, with a box from
y 0.699 to 0.886. The second line, `room`, starts around y 0.78 and extends to
y 0.99 and x 0.57. It is outside the box, so no fill layer covers it.

Attempts:

- Expanding every fill box by 120 px merged all title layers into one area and
  made LaMa paint mush over most of the frame. Rejected.
- Per-frame fills (`VIBECUT_FILL_LAMA_KEYS=0`) did not remove the line. The
  hole, not temporal carry, is the cause. Rejected as a fix.
- Box fill with `DUCK_EDGE_TEXT=1` is the next experiment: the edge OCR pass
  does read `room` at this time, and a full-line box may now fill it without
  the ghost seen under the tight mask.

## Next

1. Run the edge-text pass by default, then regenerate tracklets for the test
   video and confirm a `room` layer at 3.5 s.
2. Group stacked large-title lines into one layer when their boxes overlap by
   more than half a line and both are large text. Do not merge caption and logo
   lines that are far apart.
3. Re-run the four fixed frames and record MAD, percent within 10 levels, and
   dark-component count before closing Clean P1.
4. Keep `Needs review` visible when OCR confidence is low; never let a failed
   fill become a silent render.
