# Loop 24 — review leftovers

Starting HEAD `f62fe7e`. VERSION remains 17; no fill-pixel algorithm changes.

## Findings

- #6 PASS for tested cases: three 120-second scenes become cue-boundary candidates;
  fallback produces 15–90 seconds. Empty/short context returns a plain reason.
  Background request test returns under 1 second and reaches done with a 150 ms
  stub. UI requests background work and polls status; batch progress advances.
  Saved clips use beat bounds, not the original whole scene bounds.
- #7 PASS: estimate/key tests count 0 custom.open_filler calls. Header inspection
  uses TorchScript ZIP signature / ONNX protobuf IR-version prefix (ONNX has no
  universal magic number). File identity includes path, size, mtime. Fill raises
  the existing plain load error instead of silently selecting default pixels.
- #9 PARTIAL/FAIL strict real-story acceptance: scheduling Node checks cover seek,
  pause and 2× rate. A real browser video, served by the scratch core, measured
  three non-contiguous beats at source 1, 4 and 8 s, each 0.8 s long. Old
  timeupdate overshoot: 207.447 / 211.911 / 207.274 ms. End timer: 0 / 0 / 0 ms
  positive overshoot (≤42 ms). This was a directly instrumented real video
  element, not the product's full three-beat Story UI, so that gate is not claimed.
- #10 PASS: onnxruntime IS importable by the built sidecar. Launched
  `build/DuckSuite-Xcode.app/Contents/Resources/duckcore/duckcore` with scratch
  `build/loop24-evidence/built-root`, port 18824. PATCH /api/settings with a
  scratch model.onnx passed `custom.problem`'s actual import and returned
  ready=true. The file was a header probe, not a usable inference model. Response:
  `build/loop24-evidence/built-onnx.json`. Both importer cases pass tests.
  No unavailable-runtime Settings change is needed on this build.
- #11 PASS: Welcome latest selector excludes
  missing outputs; compact queue suppresses Play and states the missing file;
  doneCard/renderQueueRow retain guards; playRender refuses absent/missing jobs
  before opening playback. Node covers selector, doneCard, renderQueueRow and
  action/modal entry, compact queue and Welcome full markup each have Node assertions.
  Existing download route remains unchanged and tested.

## Limits and regressions

What got worse: custom-model load failures now stop fill instead of falling back;
path-sensitive custom stamps invalidate previous custom clips. Background jobs
are memory-only and do not survive sidecar restart. Long-scene splitting uses
complete transcript cues; a single cue longer than 90 s remains unusable.

Not tested: real custom-weight inference, built-sidecar ONNX inference, manual
Story UI overshoot, every playback markup path, model batch cancellation or
restart persistence. No app-container writes or founder-window clicks. Source
video was copied into `build/loop24-evidence/root/imports/review/source.mp4`;
no media is committed. No generated video or full render was needed.

The loop remains incomplete because #9 has an unfulfilled product-UI verification gate.
Validation: 272 tests pass in 27.48 s, 5 existing warnings; node syntax passes. Commit hash in handoff.
