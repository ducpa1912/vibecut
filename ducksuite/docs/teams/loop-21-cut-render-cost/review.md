# Loop 21 — render cost with a Cut

Request: REQ-20261115-01, A/B. Baseline: `4c07225`; starting HEAD: `b93cd47`.

## Scope and method

The leftover check now passes `data_root` through to the View-keyed ink store.
Render, proof, and estimate select fill layers with `inkcheck.search_rect` and the
check's existing empty-rectangle test. Blur and the check's layer count stay unchanged.

Measurements use independent scratch roots under `build/loop21-evidence/`, copied
from the interrupted session's scratch copy of `prj_e95348a97316`. Source media is
the scratch file under `/tmp/duck-loop21-root/imports/`. The new edit is
`ed_loop21`, with three clips covering 0–15.375 seconds. Neither the app's data
root nor `ed_38a4c36a3aae` was changed. GPU/MPS was asserted for every fill call.

The inherited measurement script already imported `pipeline` correctly. No
completed measurement report existed. Its fixture included a synthetic outside
layer; this measurement removes that layer and uses real detected text instead.
The crop is x=0, y=0.505, w=1, h=0.495, with `fit: "fill"`. It removes
`cl_537bb64ceb` and keeps part of `cl_6a7de36175`. An exploratory padded run was
stopped and excluded: padding kept the search rectangle in the output frame.
Both final roots start without fill or ink caches and with the same copied
historical fill/render rates. Estimates precede rendering. Each root renders twice.

## Cache version decision

Keep `textfill.VERSION = 17`. `duckcore/engine/textfill/__init__.py:626–638`
includes every selected layer's box, ink rectangle/key, ranges, tracklet, mask,
key rate, track, and large flag in `span_key`. Removing a layer changes that key;
a regression test verifies it. Edits whose layer set changes get a cold fill for
those spans. Unaffected span keys remain valid.

The ink-store key serializes the entire View at `duckcore/inkcheck.py:141–144`,
including its filter chain. Crop and grade therefore have different keys.
Adding grade to the same crop also changes the key at identical output dimensions.
The round-trip test compares all eight `Ink` dataclass fields, including a
nonuniform mask, fractional fps, glyphs, and spans.

## Acceptance

1. **PASS — A regression test.** On `4c07225`, the second `_check_output` builds
   the ink again: 2 `layer_inks` calls across two checks. After: 1 total, 0 on the
   second check. The test exercises the render-to-check forwarding path.
2. **PASS — check time.** Before: 63.2 s / 57.2 s for render 1 / render 2.
   After: 50.0 s / 37.1 s. Real View ink builds: before 12 / 12, after 12 / 0.
3. **PASS — equality.** Both before and after reports agree across their two
   renders in all 10 semantic fields (only elapsed `seconds` is excluded):
   629 frame judgments, 10 checked lines, 0 hits, 2 not-checked lines with the
   exact out-of-frame reason, and identical per-line flicker values.
4. **PASS — B regression tests.** Both `render_edit` and `estimate_edit` pass
   exactly 2 of 3 fill layers for crop and 9:16 Fill; the partial line stays.
   Pad passes all 3. Separate geometry cases cover the same decisions.
5. **FAIL — fill and estimate.** Before cold fill calls total 280.386 s,
   11 selected fill layers; total render 358.867 s. The historical estimate
   range is 112.3–144.8 s: the baseline already exceeds its upper bound.
   After: 285.663 s fill, 10 selected fill layers, 349.232 s total. The after
   estimate is 109.5–140.8 s; real time exceeds the upper bound by 208.432 s
   (148.0%). Fill units fall 151.26 → 146.04, but fill wall time rises 5.277 s
   (1.88%). This run does not demonstrate a fill speedup. No estimate was tuned.
   Warm total render: 65.166 → 43.029 s; warm fill lookup: 0.021 → 0.017 s.
6. **PASS under the brief's changed-key allowance — kept pixels.** All 39
   frames through 1.3 s in kept line `cl_6a7de36175`'s search rectangle
   (51, 0, 1035, 188): max absolute RGB difference 105/255, mean 3.925957/255.
   Output is not pixel-identical. All 3 fill-span keys changed with the layer
   set, so no old clip can mask this difference. This measures decoded final
   output, including encoding differences; it does not isolate LaMa numerics.
7. **PASS — regression suite.** 238 pytest tests passed (6 TorchScript
   deprecation warnings); JavaScript syntax check passed. The strengthened
   round-trip test also passed in the 10-test focused rerun and final full suite.

## Limits and sign-off

No full 160-second render, CPU render, app rebuild, or manual app-screen check.
No UI code changes. Grade/threshold calibration remains loop 22.
Final verifier: the sub-leader; no push is authorized.

**Verdict: NOT GOOD TO GO for loop closure.** A/B behavior and regression tests
are implemented, but acceptance 5 fails. The requested implementation/evidence
commit records that failure; it is not product-owner sign-off. Revision needed:
investigate why historical estimate rates understate these scratch runs before
claiming acceptance 5. Load and the test suite overlapped parts of measurement;
these are observed wall times, not a controlled quiet-machine speed comparison.

Creator advisory: inspected five-frame contact sheets from both real renders.
Three time costs: cold render 349.232 s, repeat render 43.029 s, repeat check
37.1 s. Two visible limitations: the deliberate crop cuts food/utensils at the
top edge, and moving utensils remain blurred. Neither is evidence of a new
regression. Pixel comparison above is the measured before/after difference.

What got worse: cold fill wall time +1.88%; kept-region pixels changed; all
three spans become cold because the selected layer set participates in each
span key, including spans after the removed line ends. Estimate upper-bound
error remains large. No full-video quality claim follows from this short span.

Commits: baseline `4c07225`, brief/start `b93cd47`; implementation is the commit
containing this review (`perf(render): reuse Cut inks and skip hidden fills`).
Its exact hash is reported in the handoff, since a commit cannot contain its own hash.

Engineer review: the change uses the check's `search_rect` and its existing
four-pixel emptiness threshold. Native tiny boxes are retained rather than
misclassified as removed by the Cut. Disabled layers and blur selection follow
their previous paths. The store's optional argument preserves existing callers.
Tests exercise both real planning entry points, not only the helper. On the
baseline, 7 of the 10 new tests fail; all 10 pass with the change.

Reproduction artifacts (gitignored): `build/loop21-evidence/before/measurement.json`,
`after/measurement.json`, `pixels.json`, `pytest-final.txt`, `baseline-A.txt`, and
the three `loop21_*.py` measurement scripts. Timing wraps real `prepare_span`
calls, including planning, model work, and saved-clip lookup; it is not GPU-kernel
time. Check timing is the renderer's own sidecar measurement. No timing threshold
or calibration was changed to make these runs pass.

## Revision 1 — span-local keys and short-render costs

Starting HEAD: `83fde5b`; prior implementation: `1b039c9`.

R1 uses the actual `frame_rects` walk to collect layers contributing rectangles,
including the existing one-extra-frame allowance. Estimate and prepare use the
same selection. The mask table and fill inputs remain unchanged. A key schema
marker (`layer_scope: span-rects-v1`) invalidates old clips once; VERSION stays
17 because the pixels do not change. Subsequent line changes invalidate only
spans where that line contributes rectangles.

R2 diagnosis: `remember_render_time` overwrote the entire rate file, deleting
the check samples just recorded. The estimate therefore repeatedly fell back
to 2.2 seconds per line. Whole-video ratios also mixed cold and warm runs and
scaled fixed initialization/encoding costs by video duration. Historical fill
rates in the original benchmark were 0.5428–0.7575 s/unit; the actual after-run
rates were 1.5006–2.3199 s/unit. The 148% miss cannot honestly be attributed
solely to fixed overhead or model loading.

The fix preserves check samples and records measured fill, check and residual
overhead separately, with cold-span count. Short estimates reuse measurements
only for the same source, selected layers, clips, Cut and device, and the same
cold/warm state. The range retains the documented one-third machine variation.
Unknown edits retain the existing fallback; no universal first-run accuracy is
claimed. Historical full-render evidence (790.4 s against 847.2 s) is unchanged.

Another concrete R2 defect: `estimate_span` tested CPU-model availability before
looking for a GPU cached clip. On this GPU-only installation it reported 0/3
cached spans while `prepare_span` reused 3/3. It now checks the selected device.

Initial revision measurement (retained, not discarded): cold range 232.8–465.6 s,
actual 601.171 s; warm incorrectly reported range 232.8–801.5 s, actual 41.176 s.
The first run exposed the GPU cache-detection defect above. Its second span
took 364.631 s, versus 75.206 and 100.082 s for the other two. These results
remain evidence of load sensitivity, not a basis for claiming constant overhead.

R1 **PASS**: toggling `cl_6a7de36175`, present only in clip 1, re-filled exactly
1/3 spans; clips 2 and 3 reused their keys. Calls: 69.895 s, 0.008 s, 0.005 s.
Unit tests cover separated spans, changed geometry, an empty span, extra-frame
selection, identical rectangle tables, and estimate/render key agreement.

R3 **PASS**: a dropped line saves fill only on frames where no kept line is on
screen. A top crop (x=0, y=0, w=1, h=0.42; Fill) leaves all three scratch spans
without a kept fill line. Clip 1 fill cost falls from 75.206 s to 0 s; all three
fall from 539.919 s to 0 s. The empty-fill render finishes in 4.129 s. This is a
deliberate diagnostic crop, not a recommended composition.

R2 **FAIL**: pre-run warm range 27.5–54.9 s, real 20.048 s (7.452 s below
the lower bound). Pre-run cold range 400.8–801.6 s, real 171.251 s (229.549 s
below the lower bound). GPU cache detection is now correct: warm 3/3 cached,
cold 0/3. Cold fill calls: 45.156, 38.622, 43.847 s. The learned component
estimate overshoots after load subsides. No bounds were widened to pass.
Separating cold/warm and preserving overhead measurements fixes concrete
defects but does not meet the requested range accuracy on this Mac.

R4 **PASS**: 242 pytest tests pass, 6 existing TorchScript deprecation warnings;
`node --check static/duck/app.js` passes. Four new tests cover the revision.

**Verdict: NOT GOOD TO GO.** R1/R3/R4 pass; R2 remains open. This commit records
the implementation and failed independent validation, not loop closure.
What got worse: every old fill clip becomes cold once; the learned estimate
now overstates these validation runs rather than understating them. Cost
samples add one small local JSON file (at most 12 records). The initial cold
run rose to 601.171 s under load, then fell to 171.251 s; no stable speedup
claim can be made from those timings.

Commit references: starting brief `83fde5b`, previous implementation `1b039c9`;
revision is the commit containing this section, with its hash in the handoff.

Validation protocol: preserve the initial revision run and import its actual
component timings into the scratch cost store before the next validation.
Record each estimate before rendering. Validate warm first, then rename the
scratch fill directory (including saved fills) and validate genuinely cold.
Do not change bounds after seeing validation results. The broad one-third
range is existing documented machine variability, not a fitted threshold.
This validates learned estimates; it does not prove first-ever estimates.

Not tested: full 160-second render, CPU, app rebuild/manual UI, model-load time
in isolation, or a universal estimate for a previously unseen edit. No app
container writes. All new renders are GPU, three clips / 15.375 s, in
`build/loop21-evidence/revision`. Original baseline evidence stays intact.

## Revision 2 — remove the rejected estimate memo

Starting HEAD: `cd4581c`; reviewed implementation: `551b677`.

- **R2a PASS:** removed `_cost_samples`, `_remember_cost`, `_cost_key`, the
  sample-based estimate branch/result key, render timing collection for that
  store, its writer, the scratch `render_costs.json`, and the rejected test.
  R1 span-local keys, GPU `device_problem` cache detection, and preservation of
  other rates-file fields remain covered by the three revision tests.
- **R2b PASS:** a short edit's estimate is not reliable on this Mac: the same
  3-clip span measured 171–601 s cold. This limit remains open in `TODO.md`.
  No UI change. Historical measurements above remain the evidence.
- **R2c PASS:** 241 pytest tests pass; `node --check static/duck/app.js` passes.
  MEMORY Outcome records A, B, R1 and R3 shipped, with R2 an open limit.

What got worse: identical-edit timing samples no longer influence the estimate;
that rejected path failed its measured range checks. No new performance or
pixel regression is claimed or measured. VERSION remains 17.

Not tested: no new renders, GPU benchmarks, full render, app rebuild, or manual
UI checks in this revision, as requested. Previous timing evidence is unchanged.
Revision 2 is ready for verifier review; R2 accuracy is explicitly not solved.
One commit contains code, tests and these documents; no push. The handoff gives
the commit hash, which cannot be embedded in its own commit.
