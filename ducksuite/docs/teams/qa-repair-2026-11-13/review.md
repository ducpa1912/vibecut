# QA repair review — 2026-11-13

**Verdict: all 9 findings addressed.** 5 are covered by new tests; 4 are code changes verified by
trace and build.

| # | Finding | Fix | Evidence |
|---|---|---|---|
| 1 | Cut change left old proof data-URLs | `saveCut` clears `previewCache`/`previewStatus` and cancels the run | code trace; not re-probed in a browser (fixture root was lost) |
| 2 | Crop at 0 shifted 2 px | `_even_offset` allows 0 for x/y, `_even` keeps ≥2 for w/h | test: `crop=960:540:0:0`; second crop `960:270:480:540` |
| 3 | Estimate units key ignored geometry | key now carries box, track, mask, kind, method, fill keys, method, device and source stamp | test: box/device/source each change the key |
| 4 | Enqueue not atomic | `BEGIN IMMEDIATE` around lookup + insert | test: 8 concurrent calls → **1** job |
| 5 | Queue refresh dropped focus | `render()` records a focus signature and restores it after `innerHTML` | code trace; keyboard not exercised |
| 6 | Failed handshake orphaned the core | `Sidecar.start()` calls `stop()` on every throw; `deinit` stops too | Xcode build passes |
| 7 | Proof key omitted source identity | `_proof_cache_key` includes size + mtime_ns of the source file | test: rewritten source → new key |
| 8 | Always-on layers missing from proofs | `_active_clean` treats no ranges as always on | test |
| 9 | Docs contradicted shipped state | AGENTS tests **219**, bundle **≈981 MB**; PRODUCT “no grading” corrected | direct read |

## Regression gates

- **219 tests** pass (was 214; +5 in `tests/test_qa_fixes.py`), 6 PyTorch warnings.
- `node --check static/duck/app.js` passes.
- `./scripts/build-xcode-dev.sh` builds, so the Swift change compiles.

## Not tested

- The two UI fixes in a real browser: stale proofs after a Cut change, and focus across a queue
  refresh. The `/tmp` review fixture was removed, and the founder project is off-limits.
- A live sidecar handshake failure.
