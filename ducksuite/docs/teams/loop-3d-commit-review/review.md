# Loop 3D review — commits `5c45c4f..HEAD`

**Verdict: accept.** No P0/P1. The two `bc89a5a` regressions are really fixed; the media cleanup broke no test; no founder media or home path was added. Four P2 doc debts and three P3s remain, listed below.

## What was checked

- `git diff 5c45c4f..HEAD` and `git log --stat`; 198 deleted binaries are historical media only; no image/video/model file was added.
- Added lines contain only two synthetic `/Users/...` fixture strings, no founder path.
- `python3 -m pytest -q tests` → **346 passed**; `node --check static/duck/app.js` clean.
- `c909766` plain import sentences: the `bc89a5a` mapper fails all four test sentences; HEAD passes.
- `c909766` pack status: installed paths are size-only again; a test patches `verify_file` to raise and would fail at `bc89a5a`.
- `11e5e43`: the full suite still passes after the media removal; no test or code references a removed file.

## P2 — text-only debts

1. `duckcore/engine/textfill/__init__.py:43` (old line) claimed Core ML was the default and within 3/255. Fixed in 3C: VERSION 17, PyTorch default, drift recorded.
2. `docs/teams/loop-26-ready-29/review.md` says installed files run the publisher-digest check and the sparse-file test expects rejection; `c909766` reversed both. That loop-26 review needs a correction note.
3. `docs/teams/coreml-default/founder-test.md` asks for a Settings line that only appears with `DUCK_FILL_GPU_ENGINE=coreml`; the app sets no such variable. The step cannot pass as written.
4. Bundle figures still say ≈981 MB while the built app is 1.1 GB with the 112 MiB Core ML package. Update after a measured size.

## P3 — remaining

- `duckcore/import_errors.py:61` added a bare `\bpath\b` rule; the JS twin has no such rule, so the two mappers disagree.
- `tests/test_coreml_fill.py:1` module docstring says Core ML is the default while the default test asserts PyTorch; fix the docstring.
- `docs/teams/*` image links to files removed by `11e5e43` lack local notes (only `docs/MEDIA-CLEANUP.md` mentions the cleanup).

## What I could not verify

- A real Core ML run or native abort (no `coremltools`, no venv).
- The rebuilt app's Settings copy and the 1440×900 screen for the six commits; no rebuild was done here.
- The sub-leader's push order; do not push is still in force.

## Good-to-go list

- `c909766` fixes both regressions, with tests that fail on the old code.
- `11e5e43` removed only media/analysis links; tests and code are intact.
- No founder media or home path entered Git.
