# Loop 7 review — catch every leftover text, and fill better

Senior PO brief: `BRIEF.md` in this folder. Project: `prj_e95348a97316`, edit
`ed_38a4c36a3aae`. One core at a time; GPU fills only; no CPU pack installed.

**Verdict: 10 of 10 acceptance items pass.** Two real leaks that both the app and the OCR
tool had missed were found by eye during the loop and are fixed. What was not tested and
what the check cannot see are listed below.

Commits: `f223061` (ink module, render check, fill hole, frame-grid alignment, Check extra
stores, tests, the brief folder and its before/after images) and the docs commit that carries
this review (`MEMORY.md`, `TODO.md`, the product report and this file).

## What shipped

| Part | Where | Note |
|---|---|---|
| Ink build and score | `duckcore/ink.py` | Edges strong on ≥80 % of the line's frames, weak in the 0.45 s windows before and after it, so a still plate rim is not ink. Score = share of ink that still has a strong edge. |
| Onset scan | `duckcore/ink.py` | Full-rate 540 px scan for strokes that appear and stay; feeds Check's extra reads. |
| Detection edges | `duckcore/engine/detect.py` | First and last ink frame set the range; reaches one frame back from the first reading and `SAMPLE_SLACK` past the last. OCR stays as the fallback for lines with no ink. |
| Post-render check | `duckcore/inkcheck.py` | Scores each fill/blur layer's ink on the output of its range ±0.5 s; a frame at or above 0.85 is a hit. Flicker = frame change inside the hole ÷ the ring around it. |
| Retry | `duckcore/render.py` | A hit widens the layer's ranges and refills once; a second hit keeps the render and shows the times. |
| Fill hole | `duckcore/engine/textfill/mask.py` | `ink_box` (ink bbox grown 6 px) replaces the whole OCR box for lines that have ink; the wide shadow pad stays for blur. |
| Frame-grid alignment | `mask.frame_start()` | ffmpeg seeks to the first frame at or after the cut, so the plan is anchored there. Before, a boundary frame took the previous line's hole. |
| Check coverage | `detect.run_check` + `pipeline.read_text_samples` | frame 0, the frame after every cut, and the onset moments; 62 extra stills on this project. |
| UI | `static/duck/app.js` | `Leftover text · Checked N frames · M found`, hit times, lines above flicker 2.2, and the check cost in the estimate. |

`textfill.VERSION` 15 (fill output changed: the hole and the frame plan).

## Acceptance

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Ink test: static text over a moving picture and over a still picture, scores text / no text | **pass** | `tests/test_ink.py` (5 tests): stroke map holds the text and not the moving background; a steady rim present inside and outside is excluded; score 0.97 on text, < 0.2 on a blank frame. |
| 2 | A test feeds a render with one leaked frame and the check reports it | **pass** | `tests/test_inkcheck.py`: builds a 2 s video with ffmpeg, one frame keeps the line, check reports one hit at 1.0 s. |
| 3 | Full GPU render after re-Check and Clean all: 0 frames with text, OCR proof 0 leaks and no subtitle in its scene list | **pass** | Render `ed_38a4c36a3aae_20261111-235452.mp4`: 2,936 frames checked, **0 hits**. `scripts/ocr_render.py`: 4,780 frames, **0 leaks**; 295 weak scene reads (`NES®`, `SNES`), none matched to a tracklet and none a subtitle. |
| 4 | The 16:44 render reports both known leaks | **pass** | 7.35 s (0.96) and 95.567 s (0.96), plus 91.834/91.867 (0.95/0.96) and 116.334 (0.98) — five real leaks, all matched by the OCR tool of loop 4. |
| 5 | The 0.5–0.7 s span shows no hard-edged block, before/after in the review | **pass** | `before-after-0.5-0.7.jpg`, `before-0.5-0.7.jpg`, `after-0.5-0.7.jpg` (0.50, 0.55, 0.60, 0.65, 0.70 s; left 19:15, right this render). The bright hard-edged rectangle is gone; see the limit below. |
| 6 | Total hole pixels before and after, it must go down | **pass** | 84,652,279 → 47,611,085 px over the 42 layers, ratio **0.562**. |
| 7 | Flicker per line, before and after; no line worse without a reason | **pass** | 37 shared lines. Max 1.67 → 1.36, mean 1.06 → 1.02, lines above 1.5: 2 → 0. Two lines rose: `cl_dcab835dfa` 0.71 → 1.06 and `cl_70903a9b4b` 0.90 → 0.99; the tighter hole moves the fill's own texture into the ring. None above the 2.2 limit. |
| 8 | Cold render estimate vs real wall clock, recorded; `VERSION` bumped | **pass** | Estimate 420.8 s; real **418.2 s** (queue `elapsed_seconds`, cold cache at `VERSION` 15). `textfill.VERSION` 13 → 15 (14 was the ink hole, 15 the frame plan). |
| 9 | No `auto: false` layer is changed by re-Check | **pass** | `cl_7b144258ac` still 0.0–0.067 s, kind `fill`, `enabled`, `auto: false`, after re-Check and Clean all. |
| 10 | `pytest` and `node --check` pass | **pass** | 127 passed; `node --check static/duck/app.js` clean. |

### The two leaks found inside the loop

Both were visible in the 21:43 render, neither was reported by the app's check, and the OCR
proof saw only one of them:

| Time | What | Why | Fix |
|---|---|---|---|
| 93.733 s | The first frame of 看咪能不能吃到里面的肉 kept 看 and 肉 | The clip cut at 93.625 s is 0.008 s off the 30 fps grid; ffmpeg decodes from 93.633 s while the plan used 93.625 s, so that frame was filled with the *previous* line's hole | `mask.frame_start()` anchors the plan to the decoded grid |
| 4.767 s | The first frame of 西兰花一块 kept two ghosted glyphs (47 % of the line) | The line fades in; the first frame carrying text scores below the hit line, so the range started one frame late | Range reaches one frame back from the first ink reading (`detect.refine_tracklet_edges`) |

After the fix the final render scores 0.01 at 4.767 s and 0.00 at 93.733 s, and the OCR proof
finds 0 leaks in 4,780 frames.

## Numbers

- Check cost: 181 s → **227 s** (+46 s) with 62 extra OCR stills.
- Post-render check: 21–37 s for 42 layers; the estimate shows 92.4 s from a 2.2 s/layer seed, so
  the figure is honest-high.
- Cold render: 418.2 s real for 2,936 filled frames; the next render with a warm cache took
  about 100 s end to end (render + check).
- Unrelated but recorded: Clean all now picks fill 42 · blur 0 (was fill 41 · blur 1). One line
  that used to default to blur now fills.

## Limits — not hidden

1. **The check reads whole lines.** A fill that leaves two glyphs of eleven scores about 0.2 and
   is **not** reported. The two leaks above are exactly that class; the check's hits came from
   wider-line frames, not from these. The fill fix removes the class found here, but the next
   partial leftover of that shape will be found by eye or by the OCR proof, not by the check.
   The Render screen says so.
2. **A still scene edge inside the line's box can score as ink.** Measured on this project: a
   sticker and a plate rim reach 0.75–0.78 on filled frames. The hit line sits at 0.85: every
   real leak measured here is 0.94+.
3. **A one-frame text flash and scenery are indistinguishable without OCR.** Unchanged from the
   brief; stated in the UI copy.
4. **A window-based glyph detector was built, measured and rejected.** It found the two real
   leaks *and* fired on a still emoji edge inside a box (0.87–0.99) on both older renders. A
   false "leftover text" on a clean render is worse than a missed partial line, so it is not in
   the build; the numbers are in this review so the next loop can pick it up with a better
   false-positive guard.

## Not tested / not shipped

- **D8 per-frame fill where the picture changes fast**: not shipped. The fill already runs per
  frame where motion and the key plan ask for it; no span was measured against the old blend, so
  there is no number to justify the extra fills or their cost.
- **D9 `follow_motion`**: not shipped, not measured. `follow_motion` still reaches
  `prepare_span`, but nothing on the review spans was compared with it on, so no win to ship.
- The extra OCR frames were proven to run (62 stills, +46 s) but no line was found *only* by
  them on this project; the value is coverage of the class, not a catch here.
- The 0.5–0.7 s span: the hard-edged block is gone, but a **soft rectangular patch** remains on
  the plate where the fine grain was rebuilt. It has no hard edge and matches the plate's tone;
  it is a model limit, not a mask leak.
- The Render screen was read in the real UI (local core, project open, Render tab): it shows
  `Leftover text · Checked 2936 frames · 0 found`, the 7m 1s whole-render note and the check note
  with both limits. The new lines were not re-read at 1280×800.

## Team notes

- **product-owner:** brief items A, B, C, D7 and D10 pass; D8 and D9 are recorded as not
  shipped with the reason. Signature item: one render, 0 hits, 0 OCR leaks, estimate within
  0.6 %.
- **creator:** three time costs — Check grew 46 s, the check adds ~30 s to a render, and a cold
  render is ~7 min on this Mac. Two wrong looks observed and judged: the ghosted boundary frame
  at 4.767 s (fixed), and the soft plate patch in the 0.5–0.7 s span (still there, listed above).
  No objection to shipping.
- **tester:** every acceptance item reproduced from the files named in the table; a leak found
  after sign-off was returned, fixed and re-proven on a fresh render.
- **engineer:** 127 tests, `node --check` clean, no CPU pack installed, no new model, no
  download, local only.
