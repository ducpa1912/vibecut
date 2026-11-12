# Loop 8 review — revision 3, A–C (Senior PO, 2026-11-12)

## A. The ink store lost the letters — fixed, proof below

`_save_ink` wrote five of the eight fields of `ink.Ink`; `settled`, `glyphs` and `spans` were lost,
so a stored line had one whole-line hole. The store now writes **every field**, listed in
`inkcheck.STORE_FIELDS`, and `ink.STORE_VERSION` is **2**. A file that is old, cut or unreadable
(`zipfile.BadZipFile` included, a new format is rebuilt, not trusted).

- Test: a line with two letters that end on different frames keeps `pieces()`, `reach`, `settled`
  and the layer's `ink_key` through the store (`test_the_store_keeps_every_letter_of_an_ink`).
- Test: a new field on `Ink` fails the suite until the store knows it
  (`test_a_new_ink_field_must_be_stored`, comparing `dataclasses.fields(Ink)` with `STORE_FIELDS`).
- **Proof, 42 of 42**: with the store deleted, every layer's `ink_key` from the frames (94.6 s) equals
  the key from the warm store (0.2 s). The store holds 42 files, 178,666 bytes.
- **One render with the warm store** (`ed_38a4c36a3aae_20261112-104149.mp4`): **0 leftovers, 2,964
  frame checks, 40 of 42 lines checked**; the two not checked are the same as `20261112-024716`
  (`cl_7b144258ac` under 5 frames, `cl_a47d0aa1c1` no steady strokes). **24 of 24 filled spans were
  reused** — the log has no `fill span` line at all; the render took 112 s plus a 192 s check.
- **Letterless clips deleted: 24.** They were found by key: every `fill/*.mp4` whose key is not
  reachable with the correct inks. 24 correct-key clips remain, one per filled span.
- The store is capped at **512 MiB**, oldest files out (`_prune_store`).

## B. The estimate worker could die — fixed

Trimming now only removes **ready** jobs, never a working one; the worker catches any error around
the result update as well, so a vanished job cannot kill the thread. Tests: 20 jobs leave the
working one in place; a job that raises does not stop the next one (`wait_for_estimate` returns its
result).

## C. The estimate key ignored the engine — fixed

`_estimate_key` now carries the same layer fields as the ink store (box, track, mask, ink_rect,
ranges, kind), the chosen chip and the engine stamp from `engine_choice`. Test: setting a valid user
model folder changes the key; the old estimate is stale and re-measured.

## Gates for A–C

**178 tests**, `node --check` clean, app builds. No fill output change, `textfill.VERSION` stays 17.

---

# Loop 8 review — revision 2 (Senior PO, 2026-11-12)

The estimate was right and slow: 66.7 s inside the request, 24 s every later call, and again in
the queue. It is now stored, shared, and answered at once. Measured on `prj_e95348a97316` through
the built app's server (`build/DuckSuite-Xcode.app/Contents/Resources/duckcore/duckcore`), no app
window, no re-Check.

## Acceptance

| Item | Number | Result |
|---|---|---|
| Warm call (nothing changed) | **0.084 s, 0.092 s, 0.257 s** (three calls, and one 0.28 s on the run before) | pass |
| First call ever (ink store and units cleared) | request **0.669 s**; background work **144.8 s** | pass |
| One layer's range changed | ready in **19.7 s**; cold 144.8 s, one third is 48.3 s | pass |
| Queue to first fill frame | **8.2 s** (the estimate was ready); before this revision the queue ran the estimate itself: 66.7 s + a 24 s ink build ≈ 90 s | pass |
| Unchanged edit total | **790.4 s**, the same figure as `85482ac` at the same stored rate | pass |
| Fill output / `VERSION` | no change; **17** | pass |
| Tests / JS / build | **173 passed**, `node --check` clean, `./scripts/build-xcode-dev.sh` builds | pass |

The range shown: **549.0–843.9 s**, from the recent rate samples (this Mac rendered the same edit
cold in 620.6 s and 847.2 s). The estimate itself is 790.4 s.

## What changed

1. **One ink store.** `inkcheck.build_inks(..., data_root=...)` stores each layer's ink as
   `.npz` under `<data root>/ink/`, keyed by `ink.STORE_VERSION`, the source stamp, the size, and
   that layer alone. The estimate, the queue and the render read the same store. Test: a second
   call reads no frame; a changed layer rebuilds only itself (2 builds for 2 versions).
2. **The dry run is paid once.** `units_key()` now hashes only the layers on screen in a span. A
   changed layer re-plans the spans it touches; every other span's units stay stored and are never
   decoded. Test: `units_override` returns without calling `dry_units`.
3. **The request does not block.** `GET …/render/estimate` answers in at most 0.3 s: `ready`, or
   `working` with progress. One daemon worker thread and one queue; a second request joins the job;
   the render queue calls `wait_for_estimate()` and takes the result instead of measuring again.
4. **The UI says it.** `Measuring the fill… N%` while working, the last figure marked as old, and a
   range instead of one number. No model name. Polled every 0.7 s.
5. **No fill lock, no GPU.** The estimate only decodes and counts; it never enters `prepare_span`,
   so the fill lock and the model are untouched while a render runs.

## The measurement, in order

- Cleared `ink/` and `render_estimate_units.json`, started the built server, `GET` once: 0.669 s,
  `working`; polled to `ready` at 144.8 s (42 layers of ink, 24 spans decoded once).
- Three warm `GET`s: 0.084–0.257 s, all `ready`, total 790.4 s.
- Changed one layer's end by +0.05 s through the edit file (the layer API has no range patch): the
  first response was `working`, `stale: true`, old figure 790.4 s; ready in **19.7 s**.
- Submitted a render with the estimate ready: first fill frame at **8.2 s**, render finished in
  492.3 s, estimate 790.4 s, check 2,919 frames, 0 hits.
- The two test layers were restored to their original ranges afterwards.

## What got worse

- The first-ever work is **144.8 s** (it was 66.7 s blocking). It now runs in the background, but a
  project with no store waits that long for its first figure.
- A changed layer still costs **19.7 s** (one ink rebuild + the spans it touches decoded), not 0.
- Every server restart re-reads the ink store (~1 s) and keeps job results in memory (capped at 16).
- The range is wide (549–844 s) because the two cold renders on this Mac were 620.6 s and 847.2 s.

## Not tested

- The Render screen in the app window: the JS is syntax-checked and the payload shape is covered by
  the endpoint, but the "Measuring the fill…" line and the range were not read on screen.
- Two edits estimated at once (one worker serialises them; only one project is open in v1).
- A server restart while a job runs; the job is lost and the next call starts it again.
- The estimate during a heavy render on the same machine: it decodes only, but CPU contention was
  not measured.

---

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
