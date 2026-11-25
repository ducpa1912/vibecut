# R1 · FFmpeg back in the app, and the build fails without it (REQ-20261125-03)

Owner: **Codex**. Folder `drop_eval/ducksuite-codex`, branch `cx/r1-ffmpeg-back`, port 8831.
Read `AGENTS.md` → "Three agents" first. Plan: `docs/plans/2026-11-25-app-store-readiness.md` (B2).

## Why
Every build since 2026-11-23 printed `warning: LGPL ffmpeg not copied`. `build/ffmpeg-lgpl` no
longer exists, so the app falls back to `shutil.which("ffmpeg")`. On a buyer's Mac there is no
FFmpeg, so Check and Render fail. AV1 input (`libdav1d`) is missing too.

## Files you own
- `scripts/build-ffmpeg-lgpl.sh`
- `scripts/build-duck-dev.sh`, the FFmpeg, FFprobe and dav1d block only (lines ~92–111)
- `scripts/check-bundle-helpers.sh` (new)
- `tests/test_bundle_helpers.py` (new)
- `docs/teams/r1-ffmpeg-back/review.md`

Touch nothing else. `duckcore/media.py` is read only: if `_tool` needs a change, say so in the
review and don't make it.

## Done looks like
1. `scripts/build-ffmpeg-lgpl.sh` builds FFmpeg 7.1.1 and FFprobe into `build/ffmpeg-lgpl`:
   - LGPL only: no `--enable-gpl` and no `--enable-nonfree`.
   - With dav1d.
   - Neither binary links anything under `/opt/homebrew` or a home folder (check with `otool -L`).
   - libdav1d is referenced as `@loader_path/libdav1d.7.dylib` or linked statically.
   - `strings` on each binary finds no `/Users/` path.
   - The build log is at `build/ffmpeg-lgpl/BUILD.txt`, with the configure line and `ffmpeg -version`.
2. In `build-duck-dev.sh`, a missing FFmpeg, FFprobe or dav1d is an **error** that exits non-zero,
   not a warning. A developer build may skip the error only with `DUCK_ALLOW_NO_FFMPEG=1`, and
   then it prints the warning it prints today.
3. `scripts/check-bundle-helpers.sh <app>` exits 1 unless all of these hold:
   - `Contents/Helpers/{ffmpeg,ffprobe,libdav1d.7.dylib}` exist and are executable where needed;
   - `ffmpeg -version` runs from inside the bundle;
   - its configure line has no `--enable-gpl` or `--enable-nonfree`;
   - `otool -L` shows no `/opt/homebrew` or `/Users/` path.
   `build-duck-dev.sh` runs it before signing.
4. `tests/test_bundle_helpers.py`:
   - runs the check script against a fake bundle in `tmp_path` (good, missing ffprobe, a GPL
     configure line);
   - is skipped, with a reason, when the real bundle isn't built.
5. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.
6. Build the app **once** into your own folder, e.g. `DUCK_APP_OUT` or the script's default under
   your `build/`, run the check script on it, and paste the output in the review. **Do not open
   the app.**

## Notes
- The FFmpeg tarball comes from ffmpeg.org (the script already does this). Network is allowed for
  this build step only, never for the app.
- Keep the tarball at `build/ffmpeg-src/ffmpeg-7.1.1.tar.xz`. The LGPL source offer (U3) will ship it.
- Do not change `textfill.VERSION`. No fill pixels change.
- Commit on `cx/r1-ffmpeg-back` with `git -c commit.gpgsign=false commit`. Don't push.
