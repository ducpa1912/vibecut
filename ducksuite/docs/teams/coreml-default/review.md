# Core ML default — REQ-20261116-02

Starting HEAD `9785972`; the authorized sub-leader implementation was preserved.
Regression repair is isolated in `c909766`: pack status uses exact sizes without
rehashing; creator-facing import errors retain their actual next steps.

## Correctness repairs

- Compiler temporary output ends in `.mlmodelc`, as coremltools requires.
  Existing compiled cache survives failure; old caches are removed after success.
- Package seeding compares content digests, not total byte count, so same-size
  replacement weights are installed. Digest work runs on seed, not Settings.
- Runtime fallback is Core ML → PyTorch GPU → CPU, including a PyTorch run-time
  failure after a successful fallback load.
- A fallback marks the primary-engine cache invalid. Its model results do not
  enter the primary saved-fill cache, and its span is written to a unique fallback
  path rather than the reusable primary clip path. Mixed spans are not learned
  as primary-engine timing samples. A later healthy Core ML run is cold.
- Removed the unqualified 1.35× product speed claim pending all-size measurements.
  Build default reads the merged package from `build/coreml-lama/out`.

## Measurement protocol

All outputs remain in gitignored `build/coreml-lama/evidence`. No footage or
weights enter the commit. No full render. Models run on Apple GPU; no Neural
Engine. The fallback chain is tested with stubs, not real CPU inference.

`scripts/coreml/bench_fillers.py` measures all 11 buckets plus 12 padding boundary
areas against PyTorch, 3 deterministic numpy pictures per area, and timed warm
runs. This measures max RGB error and mean error inside the hole; it is not a
claim of every-frame production render equality.

`scripts/coreml/bench_real_span.py` compares every frame of a 0.5-second real
source crop with two subtitle-shaped masks. This is a crop-level GPU benchmark,
not a full render or a production ink-mask quality proof.

`scripts/coreml/bench_load_memory.py` measures first and cached loads plus RSS
after each bucket in separate processes per engine. Peak RSS is process high
water, not total unified GPU memory. System load affects every timing.

## Measured result and verdict

All 11 functions merged into a 117,375,506-byte package. Measurements are in
`measurements.md` with raw JSON/logs under the evidence folder.

**NOT ACCEPTED AS DEFAULT.** Coarse padding differed by up to 169/255 and was
often slower. Exact buckets differed by up to 19/255 on these pictures, exceeding
the earlier 512-only 3/255 claim. The runtime now rejects coarse-padding shapes
before prediction and uses PyTorch instead. The real 15-frame crop then matched
exactly (max diff 0), but its guarded route was slower: 21.613 s vs 13.737 s.

The separate memory probe aborted natively in MPSGraph after eight bucket calls.
Peak recorded process RSS was 854.655 MB; first/cached load was 24.772/2.395 s.
This native failure cannot be caught by Python's fallback. Core ML code/package
remain intact and opt-in through `DUCK_FILL_GPU_ENGINE=coreml`; PyTorch remains
the safe default. No app rebuild/default promotion is claimed.

Corrected all-size rerun: 23 cases completed; all 10 coarse-padding cases
fell back and compared at max diff 0. Other cases ran the exact Core ML bucket.
Cold/cached load in this rerun: 32.362/3.500 s; PyTorch load 2.801 s.
Raw results: `buckets-safe.json`. This does not erase the separate native abort.

Final validation: 346 tests pass in 37.79 s, 5 existing TorchScript warnings;
JavaScript syntax, Python syntax and build-script shell syntax pass.

What got worse: the experimental engine has first-function load costs, numeric
drift, a native abort, and unsupported shapes use an uncached fallback span.
No default-engine speedup is claimed. No full production render or founder
window check. The package and all footage remain outside Git.

## Cache version

VERSION 18 is retained for the authorized pixel-changing engine. A merged
package is present, but default promotion is blocked as above. Existing fills
become cold once on this development branch even though the safe default stays
PyTorch; this is a known cost of retaining the authorized VERSION 18 experiment.
Loop 27's no-pixel-change work is separate and was not implemented.
