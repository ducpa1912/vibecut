# Loop 22 — grade check and stated output frame rate

Starting HEAD: `acb4347`. Request: REQ-20261115-01 C/D.

## Verdict

Measured C3 pass: all seven leftover cases hit; all seven filled cases are clean.
No thresholds or check behavior changed. `ink.EDGE=40`, `inkcheck.SAME=20`, and
`textfill.VERSION=17` remain unchanged. D uses one core rate function.
The initial results below are historical; Revision 1 supersedes the fixture and fps fallback findings.

## Acceptance

- C1 PASS: two real clips, 0–1.2 s and 1.3–2.8 s, totaling 2.7 s. Scratch edit
  IDs `ed_loop22_*`, two judged fill lines. The measuring script alone excludes
  `cl_537bb64ceb` from fill selection; `cl_6a7de36175` stays filled. GPU settings
  and bundled LaMa used. Source and output are entirely under `build/loop22-evidence`.
- C2 PASS with N/A comparisons explained below: seven Cuts, two lines each,
  50 judged frames per line/case. Table follows.
- C3 PASS: 7/7 leftover hits, 0/7 filled false hits. No failing cell required a stop.
- C4 PARTIAL / FAIL literal fixture requirement: two real-frame contrast tests
  pass, but no real media fixture existed in `tests` before this work. Added a
  small compressed array of real source crops rather than inventing video.
  This differs from “already in the repo's tests” and requires verifier acceptance.
- D1 PASS: one `render.output_fps` function supplies render, proof, estimate and
  the estimate-status payload. Eight rate cases pass: 23.976/24 → 24;
  25/29.97/50/60/0/unknown → 30. JS no longer selects the output rate.
- D2 PASS: Node assertions cover same-rate 24 and 29.97, 25 → 30 (5 repeated
  frames per second), and 60 → 30 (30 dropped frames per second). No selector.
- D3 PASS via the brief's fallback only: no valid 24/25/60 fps source found in
  `tests`, `build`, or `/tmp/duck-loop21-root`. Node copy tests pass. No Render
  screen captures exist; no founder-window interaction occurred. Other disk
  locations were not exhaustively searched.

## C2 matrix

Differences are RGB maximum-channel gap averaged over a glyph zone, captured
at the production judge immediately before its SAME comparison. Max/median
aggregate all eligible glyph/nudge comparisons. Edge share is mean output
strong-edge presence on the built ink mask across frames read by the judge.
Each row judges 50 frames. These are observations, not threshold calibration.

| Cut | Leftover verdict | Max / median gap | Ink above EDGE | Filled verdict | Max / median gap | Ink above EDGE |
|---|---|---:|---:|---|---:|---:|
| none | hit | 48.377 / 12.244 | 79.041% | clean | N/A | 0.277% |
| contrast −50 | hit | 32.896 / 10.983 | 77.072% | clean | N/A | 0.031% |
| contrast +50 | hit | 63.045 / 10.846 | 78.355% | clean | N/A | 0.597% |
| contrast +100 | hit | 70.413 / 10.944 | 78.644% | clean | N/A | 0.775% |
| exposure −1 | hit | 51.463 / 17.421 | 78.768% | clean | N/A | 0.276% |
| exposure +1 | hit | 52.550 / 17.563 | 78.894% | clean | N/A | 0.284% |
| Enhance 2× | hit | 42.078 / 12.495 | 78.132% | clean | N/A | 0.063% |

N/A means the filled line had no eligible glyph comparisons: output presence
failed the gate before SAME. It is not a fabricated zero difference. Enhance
uses a centered half-width/half-height crop, with sharpening enabled at 50.

## Evidence and limits

Raw matrix: `build/loop22-evidence/matrix.json`; measurement harness:
`build/loop22-evidence/measure.py`; log: `build/loop22-evidence/measure.log`.
The harness instruments `_judge` with Python tracing without changing product
code. The original real-frame fixture was removed in Revision 1; current tests use numpy strokes.

What got worse: the UI briefly says “Reading the output frame rate…” until
the core estimate payload arrives. The new real-frame fixture increases test
data size. No render-quality regression was measured in this matrix.

Not tested: manual Render screen layout, full render, CPU fill, unseen media,
or more grade combinations. No new synthetic video was created by loop 22's
measurement or new tests. The existing full test suite includes synthetic-video
tests; those pre-existing tests were run for required regression verification.
The full app was not rebuilt. Render screen capture paths: none (D3 fallback).

This commit contains code, tests and documents. Its hash is in the handoff;
no push is authorized. Full suite: 252 passed, 6 existing TorchScript warnings,
25.22 s. `node --check static/duck/app.js` passed. Fixture size: 3,319,205 bytes.

## Revision 1 — no founder frames in git; fps survives estimate failure

Starting HEAD: `c5c4026`. The sub-leader restored loop 22 changes to the working
tree before this revision. No reset was performed. The replacement commit
includes all loop 22 changes and no founder frames.

- R1 PASS: both founder-frame fixture files removed. Two contrast cases (−50
  and +100) use deterministic numpy strokes on textured backgrounds entirely
  in memory, exercising real `ink.build` and `inkcheck._judge`. No fixture is
  read and no media file is written. The accepted real-frame matrix above is
  preserved as numbers only. `git check-ignore` confirms both the measurement
  script and source media under `build/loop22-evidence` are ignored.
- R2 PASS: `get_edit` enriches existing source metadata without writing to disk;
  `save_edit` supplies the same field for new and changed edits. Both call the
  single `render.output_fps` rule. JS reads `edit.source.output_fps` first.
  Node checks cover failed estimates at 25 → 30 and 24 → 24; a core test covers
  loading legacy metadata and recomputing the rate on save.
- R3 PASS: 253 tests passed in 25.47 s, 6 existing TorchScript warnings;
  `node --check static/duck/app.js` passed. MEMORY and TODO reflect the final revision.

What got worse: edit source metadata now carries one additional derived field.
No new timing or visual regression was measured. The 3.3 MB footage fixture is
absent from the replacement commit. No UI layout changes were needed.

Not tested: no new renders, manual Render screen captures, app rebuild, or GPU
benchmarks in this revision. The original C matrix remains the measured media
evidence; numpy tests are regression coverage, not new real-media measurements.
VERSION remains 17. No push; exact replacement hash is in the handoff.
