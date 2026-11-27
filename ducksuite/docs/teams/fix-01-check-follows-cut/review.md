# Fix 01 review — the leftover check follows the Cut

**Verdict: pass (engineer + tester evidence, no founder test yet).** Revision of the leftover check
(REQ-20261111-11) against the Cut (REQ-20261112-04). Finding #1 of
`docs/reviews/2026-11-13-loops-07-19.md`.

## Fault

The check read the source scaled straight to the output size. Cut crop, aspect, fit pad or crop,
sharpen and grade change the output's pixels, so it compared the wrong pixels. Measured on the
test video (30 frames of untouched text):

| Output | Before | After |
|---|---|---|
| crop + letterbox + contrast −30 | 0 hits, "does not line up", not checked | **30 hits** |
| contrast −40 only | **0 hits, checked = clean (wrong)** | **30 hits** |
| contrast −20 only | 30 hits | 30 hits |

## Change

- `render._picture_plan` is the one plan for the render chain and the check. `render.check_view`
  returns an `ink.View`: the render's picture filters without `fps`, plus where a source pixel lands
  (crop corner, scale, pad or fill offset). `None` when the output is the source.
- `ink.read_box` runs a `View`'s chain; a bare `(w, h)` still means a stretch.
- `inkcheck.search_rect` carries the box into output pixels and cuts it to the frame;
  `layer_inks` reports "the Cut leaves this line out of the frame" for a line cropped away.
- The ink store key holds the whole view, so a changed Cut rebuilds the check's ink.
- Fill output is unchanged: `textfill.VERSION` stays 17, no cold render.

## Acceptance

| Check | Result |
|---|---|
| Leftover text in a cropped, letterboxed, graded render is found | pass (`test_text_left_in_a_cropped_graded_render_is_found`) |
| A clean render through the same Cut has no hits | pass |
| A line the Cut crops away is not checked, with the reason | pass |
| Store keys differ for no view, a view, a stretch | pass |
| `check_view` chain = render chain minus `fps`; corners map onto the picture | pass (`tests/test_cut.py`) |
| Full suite | **204 pass** (198 before) |

## Not tested

- A real render of `prj_e95348a97316` with a Cut. Only synthetic videos; no full render was run.
- `fill` Cut on a real source (mapping tested in numbers only).
- The extra check time: the ink is rebuilt in output pixels whenever a Cut is set (as for any
  output size other than the source), and it is not stored on disk by the check.
- Report row in `docs/reports/ducksuite-product-progress.html`: not added; the insert anchor is not
  named in `AGENTS.md`, and the file is not read by agents.
