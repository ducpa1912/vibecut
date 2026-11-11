# Loop 8 review — a better fill for moving footage

Brief: `BRIEF.md`. Project: `prj_e95348a97316`, edit `ed_38a4c36a3aae`. GPU only. Loop 7 rev 2
(`8d1a9c8`) is the base: per-letter ink strokes, `textfill.VERSION` 17.

**Verdict: 7 of 7 acceptance items pass. No other engine may ship: the table says no for every
candidate. The path that needs no licence — a user-supplied fill model — is built, tested and
compiles in the app.**

Commits: this commit (licence table, custom fill slot, crossing count in the estimate, tests,
review, docs). The brief was committed first at `a448850`.

## Acceptance

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Licence table, every row quoted with a URL | **pass** | `docs/duck/moving-fill-licences.md`: 9 engines, each with code licence, weights licence, a quoted clause and a URL. |
| 2 | Bench on the yes rows; four numbers; LaMa alone if none allowed | **pass** | No yes row, so the table holds LaMa alone. 3 moving spans (30–34, 65–69, 130–134 s), **21 frames**, GPU MPS: PSNR **22.04 → 26.57**, SSIM 0.6456 → 0.7917, **0.48 → 0.44 s/frame**, peak RSS **620 MB**. Flicker (the shipped render, loop 7 rev 2): max **1.82**, mean **0.93**, 2 lines over 1.5. |
| 3 | A stated verdict | **pass** | "None does." No candidate is allowed; the custom slot is the only route. LaMa with loop 7's ink hole beats the old box hole by **+4.53 dB** and **8 % less time** on the same frames. |
| 4 | Custom slot: loads a user folder, falls back with a plain message, test with a stub model | **pass** | `duckcore/engine/textfill/custom.py` (`model.onnx` image/mask, or `model.pt` TorchScript), stamp in `span_key`, `prepare_span` loads it before the key and falls back to LaMa with the reason; Settings refuses a bad folder with a 400 and a plain message. `tests/test_custom_fill.py`: 8 tests, including a TorchScript stub model that fills a hole. |
| 5 | No weights added; no file over 1 MB | **pass** | Added: `custom.py` 7.4 KB, `test_custom_fill.py` 6.5 KB, one markdown table. `git diff --stat` has no binary and nothing near 1 MB. |
| 6 | `VERSION` bump only if default output changes | **pass** | Default fill output is unchanged: the slot only runs when a user sets a folder. `textfill.VERSION` stays **17**; no cold-render warning. |
| 7 | `pytest`, `node --check` | **pass** | **163 passed**; `node --check static/duck/app.js` clean; `./scripts/build-xcode-dev.sh` builds and signs the app (the Swift picker compiles). |

## The licence reading

No candidate is allowed. ProPainter, E2FGVI and MAT are non-commercial; DiffuEraser runs ProPainter
as its prior and inherits that; VideoPainter is bound to the CogVideoX licence; STTN, FGT and FGVC
publish permissive **code** with checkpoints that carry **no separate grant** — "unclear counts as
no". The full table and quotes are in `docs/duck/moving-fill-licences.md`.

## The bench

| Engine / hole | Frames | PSNR | SSIM | MAE | s / frame | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|
| LaMa, old box hole | 21 | 22.04 | 0.6456 | 14.61 | 0.48 | — |
| LaMa, ink hole (loop 7) | 21 | 26.57 | 0.7917 | 6.68 | 0.44 | 620 MB |

Measured with `scripts/bench_fill.py --spans "30.0:34.0,65.0:69.0,130.0:134.0" --frames 24
--variants baseline,ink --device gpu`. The run kept 21 of the 24 picks: three windows had fewer
text-free times than asked. At 30 fps, 0.44 s a frame is **13.2 s of model work per second of
output**; a render blends fills and skips frames with no text, so the real render is far cheaper
(698 s for 160 s, all fills included). Peak RSS stays well under the 8 GB limit. The synthetic
caption has no temporal ink, so the bench measures the engine and the letter-shaped hole; the
per-letter stroke *frames* are measured on the real render by the loop 7 check.

The flicker number comes from the shipped render, not the bench: isolated frames cannot give a
frame-to-frame figure. Loop 7 rev 2 measured max 1.82, mean 0.93 over 40 lines, none over 2.2.

## The custom fill slot

- Contract: ONNX `image` [1,3,H,W] 0–1 and `mask` [1,1,H,W] 1 = fill, or a TorchScript module called
  as `model(image, mask)`. Output 0–255 or 0–1 (read from the maximum). A fixed-size ONNX graph gets
  its feed resized; everything else uses the strip the pipeline already prepares.
- Loaded once per file stamp, cached; the stamp (`size:mtime:custom`) goes into `span_key`, so a new
  file never reuses an old clip.
- A folder that is wrong is refused in Settings with a plain message. If the file disappears or
  fails to load at render time, the span is filled with LaMa and the reason is logged and returned
  in the span result; the render is not lost.
- Settings and the picker name no model, download nothing, and copy the chosen folder into app
  data (`models/fill-custom/<folder>`), so the sandboxed core can read it.

## The estimate, and the gap that remains

The brief asked for the crossing cost in the estimate, measured, not guessed. `count_crossings()`
now reads the source at a quarter size, 10 fps, with the fill's own predicate (`_picture_moved`),
counts one event per crossing after a 0.3 s quiet, and caches the result per span
(`render_crossings.json`).

- Measured on this project: **35 crossings across 22 spans** (1–3 per span).
- Effect on the estimate: fill **298.4 → 310.1 s**, total **483.5 s** (the total is still set by the
  whole-render ratio path).
- Cost of the scan: **11.6 s** the first time, 0.3 s after, because the counts are cached.

**The estimate is still low against the one cold render we have: 483.5 s against 698 s (−31 %).**
The crossing frames account for only 11.7 s of that. The rest is the loop 7 per-letter stroke plan:
the estimate plans runs from the box table, while the render starts a new run whenever the set of
letters on screen changes. That is a separate gap, measured here but not fixed: fixing it needs the
stroke frames at estimate time (about 1–2 s per span), which the estimate does not build. Recorded
in `TODO.md`; no factor was invented.

## What got worse

- The estimate takes 11.6 s on its first pass over a project (0.3 s after the counts are cached).
- Nothing in the output: no `VERSION` bump, no cold render.

## Not tested

- The custom slot in the built app end to end: settings, picker, a real user model, a wrong file
  during a render. The loader, the fallback and the settings route are covered by tests; the Swift
  build proves it compiles.
- A bench with a licensed candidate: none is allowed, so the table has LaMa alone.
- The 698 s cold render against the new 483.5 s estimate: the crossing count is measured, the
  per-letter stroke part is not; no new cold render was run (the fill output did not change).
- A source that is not constant frame rate; the crossing scan assumes the fixed grid.
