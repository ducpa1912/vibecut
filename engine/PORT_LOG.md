# Port log

Every entry is a deliberate port. Nothing is copied without a reason and a test.

Reference: `origin/classic` in this repository, commit `bb3e89e`. There is no
Classic worktree.

```bash
git fetch origin classic
git archive origin/classic detect.py clean_source.py pipeline.py textfill \
  | tar -x -C engine
```

## Status

M0: no ports yet. The worker contract is frozen and the cloud paths are being
built in `worker/` first; ports happen when the equivalent cloud behaviour is
needed and a real clip can verify it.

## Planned entries

### `pipeline.probe`

- Source: Classic `pipeline.py`.
- Take: ffprobe field extraction, rotation handling, frame count derivation.
- Drop: local path assumptions, project directory layout, Apple-only code.
- Contract: `ProbeInfo` in `worker/duckclean_worker/contract.py`.
- Verification: real clip probe matches ffprobe; frame count matches
  `round(duration * fps)` within one frame.

### `detect` tracklets and ranges

- Source: Classic `detect.py`.
- Take: tracklet merge across frames, range building, fill planning thresholds.
- Drop: 4 fps global sampling, global frame cap, silent confidence dropping,
  Apple Vision dependency.
- Contract: `FrameRange`, `DetectedMember`, `DetectedGroup`; ranges are
  frame-based and beat-scoped.
- Verification: a 0.2-second text flash is found by the cloud detector; no
  tracklet cap truncates dense subtitles without setting `truncated`.

### `clean_source` fill, encode, audio mux, cancel

- Source: Classic `clean_source.py`.
- Take: encode parameters, audio mux from source once, cancel checks, resume
  cache keyed by plan hash.
- Drop: whole-video blind render, local output handling.
- Contract: `RenderBeat`, `RenderOutput`, `RenderedSegment`, segment keys.
- Verification: clean beats above 45 dB PSNR or stream-copied; output duration,
  display size, fps and audio match the source; cancel leaves no output and no
  `.part`.

### `textfill/` mask and estimator

- Source: Classic `textfill/`.
- Take: mask dilation and feather, LaMa preprocessing, cost estimator shape.
- Drop: local model paths, macOS-only assumptions.
- Contract: `MaskResult`, `WorkerMaskRef`.
- Verification: masks carry `provenance` and `model_version`; a model version
  change invalidates a cache hit by revision.
