# Loop 8 review — revision 1 (Senior PO, 2026-11-12)

Three faults from the review of `7bda48d`, and the founder script. All fixed in the commit that
carries this section.

## Fault 1 — the estimate planned a different fill

The estimate planned box runs; the fill runs the real per-frame plan (ink ranges, crossings, still
lines). Now the estimate calls **the same function the render calls**:
`textfill.dry_units()` walks `fill_frames_lama` on the decoded span with the same holes, the same
run rules and the same motion test, and a filler that only counts (`_CountingFiller`). No model
runs and no constant is fitted. Units are model work plus frames × frame cost, exactly what
`record_rate` learns.

**Measured against a cold render** (`ed_38a4c36a3aae_20261112-074517.mp4`, 847.2 s wall clock,
fill spans 688.5 s):

| Span start (s) | Estimated fill (s) | Real fill (s) | Ratio |
|---:|---:|---:|---:|
| 0.00 | 59.6 | 42.9 | 1.39 |
| 4.75 | 33.0 | 25.9 | 1.27 |
| 10.06 | 45.2 | 48.1 | 0.94 |
| 15.38 | 37.7 | 38.2 | 0.99 |
| 19.62 | 59.5 | 80.1 | 0.74 |
| 25.27 | 47.0 | 56.4 | 0.83 |
| 81.73 | 9.6 | 14.6 | 0.66 |
| 87.38 | 27.9 | 29.4 | 0.95 |
| 89.25 | 58.6 | 64.1 | 0.91 |
| 93.62 | 29.3 | 33.4 | 0.88 |
| 98.00 | 10.3 | 5.9 | **1.75** |
| 100.50 | 14.6 | 13.6 | 1.07 |
| 105.08 | 24.7 | 30.8 | 0.80 |
| 109.67 | 27.1 | 39.6 | 0.68 |
| 114.25 | 10.7 | 12.1 | 0.88 |
| 119.38 | 15.4 | 12.1 | 1.27 |
| 124.50 | 17.6 | 14.8 | 1.19 |
| 137.88 | 22.3 | 25.4 | 0.88 |
| 141.06 | 14.3 | 13.3 | 1.08 |
| 144.25 | 7.5 | 5.4 | 1.39 |
| 146.00 | 1.2 | 2.3 | 0.52 |
| 148.00 | 3.3 | 3.8 | 0.87 |
| 149.88 | 38.3 | 39.8 | 0.96 |
| 154.95 | 35.0 | 36.5 | 0.96 |

- **Total: 790.4 s estimated against 847.2 s real, −6.7 %** (within 15 %).
- Fill only: 649.7 s against 688.5 s, −5.6 %.
- No span is off by more than 2×. The worst is **98.00 s at 1.75×**: a 5.9 s span where two runs ran
  together in the real fill (10 planned, 9 real); the model ran faster than the median rate there.
  The `0.00` span (1.39×) is the first span, which pays the model load.
- Runs now match almost exactly: 85/85, 54/54, 70/69, 75/75, 100/99, 104/104, 116/115.

Cost of the estimate: **66.7 s** the first time for the whole edit (ink build + a decode of every
span), 24 s after because the per-span units are cached in `render_estimate_units.json`. The old
`crossing_frames` scan is deleted; its 10 fps set could not express "moved since the run started".

## Fault 2 — a custom model taught the LaMa speed

`record_rate` was called for every span, including a user model's. Now `_learn_rate()` skips a
custom engine (and a resumed clip). Test: `test_a_user_model_never_teaches_the_default_rate` —
`_learn_rate(..., custom=Path("/x/model.onnx"))` leaves no rate file; the default call writes one.

## Fault 3 — estimate and render could pick different engines

`estimate_span` stamped a custom model by its path even when it could not load, while
`prepare_span` fell back to LaMa. Both now call `textfill.engine_choice()`, which loads the model
(or returns the plain reason) once and is cached. Test:
`test_a_model_that_cannot_load_is_not_chosen_anywhere` — a folder with a file that is not a graph
gives `(None, reason)` and the default stamp.

## Founder script

`docs/teams/loop-08-moving-fill/founder-test.md`: pick a good folder, a wrong one, clear it; what
must be seen at each step. Not run by the agent (as asked).

## Gates

**170 tests**, `node --check` clean, app builds. No fill output change: the real fill still uses
its own pixel test (`moved_at` defaults to None), `textfill.VERSION` stays **17**. No render was
started twice on the same span.

---

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
