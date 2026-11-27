# R2 · No GPL code in the app (REQ-20261125-03)

Owner: **Codex**, after R1 (merged `f994af4`). Folder `drop_eval/ducksuite-codex`, branch `cx/r2-gpl-out`.
**D9 decided 2026-11-26: Kokoro is dropped from v1** (founder: "Codex R2"). Start now.
Plan: `docs/plans/2026-11-25-app-store-readiness.md` (B1).

## Why
`libespeak-ng.dylib` and `libpcaudio.0.dylib` (GPL-3) ship in `duckcore/_internal`, because
`kokoro_onnx` pulls them in for phonemes. GPL-3 code can't ship in a closed, paid App Store app.

## Files you own
- `scripts/build-duckcore.sh` and `build/pyinstaller-spec/duckcore.spec`, the Kokoro lines
- `duckcore/voice.py`, `duckcore/packs.py` and `duckcore/model_slots.py`, only what hides or removes the Kokoro route
- `scripts/scan-bundle-gpl.sh` (new)
- `tests/test_no_gpl.py` (new)
- `docs/teams/r2-gpl-out/review.md`

`static/duck/app.js` is **not** yours in this loop. If a Kokoro control must go from the UI, list
it in the review and the PO will route it.

## Done looks like
1. `kokoro_onnx`, `phonemizer`/espeak-ng and pcaudio are gone from the PyInstaller build.
   `find <app> -iname '*espeak*' -o -iname '*pcaudio*'` finds nothing.
2. Voice still works with macOS voices and the user's own ONNX voice folder. The Kokoro pack is
   hidden from the pack list, and the core never offers it. A saved setting that names Kokoro
   falls back to a macOS voice with a plain message, not an error.
3. `scripts/scan-bundle-gpl.sh <app>` exits 1 when any bundled file or dist-info licence says
   GPL or AGPL. LGPL is listed but allowed: FFmpeg is LGPL and ships as a separate executable.
   The build runs it.
4. `tests/test_no_gpl.py` covers the voice fallback and the scan on a fake bundle.
5. Full suite and `node --check` pass. The bundle size before and after is in the review.
   **Do not open the app.**

## Notes
- Base: `ducksuite` at `b5c7041` or later. R1's `scripts/check-bundle-helpers.sh` already runs in
  `build-duck-dev.sh`. Run the GPL scan next to it, and don't change the FFmpeg block.
- Your `build/ffmpeg-lgpl` from R1 is still in your folder, so the build passes the FFmpeg check.
- `PRODUCT.md` still lists the Kokoro pack. Don't edit it: list the lines in your review and the
  PO will update it.
- Commit on `cx/r2-gpl-out` with `git -c commit.gpgsign=false commit`. Don't push. Don't open the app.
