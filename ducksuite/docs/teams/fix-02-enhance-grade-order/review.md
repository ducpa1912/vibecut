# Fix 02 review — enhance follows the crop, the grade stops at the bars

**Verdict: pass (tests and ffmpeg probes; the app UI was not opened).** Revision of Cut enhance and
grading (REQ-20261112-04, loops 18–19). Findings #2 and #3 of `docs/reviews/2026-11-13-loops-07-19.md`.

## Faults

| # | Fault | Before | After |
|---|---|---|---|
| 2 | Enhance compared the output with the whole source. A 50 % crop of 1080×1920 back to 1080×1920 (2× upscale) | no `lanczos`, no `unsharp` | `flags=lanczos+accurate_rnd`, `unsharp=5:5:0.900:5:5` |
| 2 | The Cut card's output with a crop was the crop's own pixels, so it never offered enhance on a crop and "Output W × H" was wrong | `540 × 960` | `1080 × 1920` (as `render.cut_size`) |
| 3 | Grade ran after `pad`: contrast −50 on a letterboxed frame | bars at **63** (grey) | bars **≤ 16** (black), picture 127 |

## Change

- `render._picture_plan`: upscale = the kept picture (crop or source) drawn larger (`scale > 1`, with
  `min` for fit and `max` for fill), the same scale the check's view uses.
- Order is now crop → scale → (crop to fill) → sharpen → grade → pad. Fill mode has no bars.
- An unreadable grade now falls back to contrast 1 and saturation 1 (was contrast 0, a grey frame).
  Not reachable through the API, which validates the numbers.
- `app.js` `cutOutputSize` mirrors `render.cut_size` (a crop no longer sets the output);
  `enhanceInfo` uses the same scale rule and says "The crop is W×H" when cropped.
- `PROOF_VERSION` 10 → 11: proof frames of graded letterboxed edits change, so the old JPEGs are not reused.
- Fill output is unchanged: `textfill.VERSION` stays 17, no cold render. Render pixels change only
  for edits with a crop + enhance, or a grade with letterbox bars.

## Acceptance

| Check | Result |
|---|---|
| Cropped upscale gets Lanczos and Sharpen; no crop at the same size gets neither | pass (`test_a_cropped_upscale_gets_lanczos_and_sharpen`) |
| `pad` comes after `eq` and `colorbalance` | pass |
| Graded letterboxed frame through ffmpeg: bars black, picture grey | pass (`test_letterbox_bars_are_black_in_a_graded_render`) |
| Check view still equals the render chain minus `fps` | pass |
| Full suite / `node --check` | **207 pass** / clean |

## Not tested

- The Cut card in the running app: no server was started (the founder runs it). Founder step: on a
  9:16 project, Cut → crop to half → Enhance shows "540×960 → 1080×1920" with the Lanczos toggle,
  and the output label reads 1080 × 1920; set 16:9 fit with contrast −50 and the proof's bars stay black.
- A real render; the CSS player preview still grades the whole player box (labelled approximate).
- Report row in `docs/reports/ducksuite-product-progress.html`: not added, the anchor is not named.
