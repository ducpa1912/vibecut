# Loop 27 — fill and check cost, no pixel change (REQ-20261115-02 P5, REQ-20261111-11)

Written by the sub-leader on 2026-11-16. HEAD `5c45c4f`, 324 tests. Build team: OpenCode, one
phase; the sub-leader verifies every number. Order given 2026-11-16 by the Senior PO on the
founder's word. **No fill output change: `textfill.VERSION` stays 17.** Fewer key frames, D8, D9 and
a third confidence level are **not** in this loop.

## Today (measured on the review project, `MEMORY.md`)

- First estimate of a project: 144.8 s of background work (`render.estimate_edit` →
  `inkcheck.build_inks` + the span units in `<data root>/render_estimate_units.json`).
- Leftover check after a render: 68–81 s quiet (`render._check_output` → `inkcheck.check` →
  `inkcheck._judge`, which calls `ink.read_box` on the source **and** the output per line).
- Cold render 620–847 s; measured and not built: shared check decode 52.8 s, cropped fill decode
  35–50 s.

## Rules

- GPU only. Never stop a render mid-clip. At most **one** cold render in the whole loop, and the
  report says before it starts that it costs 10–14 minutes.
- **Do not re-Check `prj_e95348a97316`** and do not change it. Measure on a **copy** of it in a
  scratch data root under `build/loop27-evidence/` (gitignored), or on tests' own synthetic arrays.
  Never generate or download test media. No founder frames, crops or paths in any commit.
- No every-frame OCR. Local only. No model name in the UI.
- Every number in the review is measured by you and states the command that produced it.

## 1. Warm first estimate after Check

At the end of a successful Check (`duckcore/check.py`, `_run`), build the ink store and the span
units for the project's current edit, the same work `estimate_edit` does, so that the first
`estimate_status` call for that edit returns `state: ready` in under 1 s. Check's progress line says
what it is doing ("Preparing the render estimate"). A failure here never fails Check: it logs and
leaves the estimate to run later as today. Cancel still works during this step.
**Accept:** a test with stubs: after Check, `estimate_status(..., wait=0)` is `ready` without new
ink work. Measured on the copy: first estimate after a fresh Check, in seconds (target < 1 s), and
the seconds this step adds to Check. Both numbers in the review.

## 2. Share the leftover check's decode with the render

The check reads the output it just wrote, and the source again, through ffmpeg per line. Keep the
boxes the check needs while the render already has the frames (source boxes from the fill read, and
output boxes from the frames sent to the encoder), so the check does not decode again. Memory is
bounded and stated (8 GB Mac); when the bound is hit, fall back to today's read for that line and
count it. The judge's inputs must be byte-identical to today's reads (same `check_view`, same
colour conversion, same frame index alignment, incl. the encoder's output fps).
**Accept:** a test that the shared boxes equal `ink.read_box` arrays exactly on a synthetic clip;
on the copy, per stage seconds before and after (fill, encode, check); the check report is the same:
**0 leftover, 40 of 42 lines checked**, same frame count (2,964 or as measured before on the copy).

## 3. Crop the fill decode — only with proof

Decode only the area the fill needs (the layers' search rects plus the model's context margin)
instead of the full frame. **Build it only if** an every-frame comparison on all of the review
project's fill spans (on the copy) shows the filled output pixels are identical (max abs diff 0)
to the full-size decode. Write the proof as a script under `scripts/` and its result in the review.
If any frame differs, do not ship it: report the first differing frame number and the max diff.

## Done

One commit: code + tests + `docs/teams/loop-27-cost/review.md` (pass/fail per item with the measured
numbers, what got worse, what was not tested) + `TODO.md` (remove what passes) + `MEMORY.md` (outcome
under REQ-20261111-11, stand table figures). pytest and `node --check static/duck/app.js` pass;
state the count. Do not push. Do not edit `old_*.md` or `docs/reports/*`.
