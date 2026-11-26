# P-B · Whisper inside the app (REQ-20261125-03)

Owner: **Codex**. Folder `drop_eval/ducksuite-codex`, branch `cx/pb-whisper-in-app`.
**D3 decided 2026-11-26: Vietnamese speech stays in v1, with whisper.cpp built into the app**
(founder chose "P-B Whisper in app"). Start now.
Plan: `docs/plans/2026-11-25-app-store-readiness.md` (B4).

## Why
The speech pack downloads weights only. `duckcore/engine/stt.py` (`_whisper_binary`,
`_whisper_command`, about lines 407–426) looks for an `mlx_whisper` program or module, and the
app has neither. So Vietnamese Check and dub don't work for a buyer. A downloaded runner would
break App Store guideline 2.5.2, which bans downloaded executable code. The runner has to ship
inside the signed app, and the pack can only hold data.

## Files you own
- `scripts/build-whisper-cpp.sh` (new): builds whisper.cpp from source and stages it into `build/whisper-cpp`
- `scripts/build-duck-dev.sh` and `scripts/build-xcode-dev.sh`: only the lines that copy and check the helper
- `scripts/check-bundle-helpers.sh` and `tests/test_bundle_helpers.py`: add `whisper-cli`
- `duckcore/engine/stt.py`: the Whisper command, its arguments, and reading the JSON it writes
- `duckcore/packs.py`: the `speech-whisper` entry
- `duckcore/main.py`: only `engine_status` (about line 464)
- `duckcore/model_slots.py`: only if the speech slot names mlx
- `tests/test_whisper_cpp.py` (new), `tests/test_model_slots.py` (the mlx stub)
- `docs/teams/pb-whisper-in-app/review.md`

`static/duck/app.js` is **not** yours in this loop. If a UI line has to change, list it in the
review and the PO will route it. Don't edit `PRODUCT.md`, `MEMORY.md`, `TODO.md` or `PLAN.md`.

## Done looks like
1. **Build.** `scripts/build-whisper-cpp.sh` builds a pinned whisper.cpp release tag (record
   the tag and the commit) with Metal and the Metal library embedded. It checks the licence is
   MIT. It produces one `whisper-cli` that needs only system libraries; check with `otool -L`.
   The script fails if `/Users/` appears in the binary's strings, and it writes `BUILD.txt`
   like `build-ffmpeg-lgpl.sh` does.
2. **Bundle.** Both build scripts copy `whisper-cli` next to ffmpeg. That is `Contents/Helpers`
   in the dev app and `Contents/Resources/Helpers` in the Xcode app. A missing `whisper-cli` is
   an error unless `DUCK_ALLOW_NO_WHISPER=1` is set. `check-bundle-helpers.sh` checks it, and
   `scan-bundle-gpl.sh` still exits 0.
3. **Runner.** `stt.py` runs the bundled `whisper-cli`. It finds it the way the ffmpeg helper
   is found, and falls back to PATH for development only. It never runs a program from the data
   root or the pack.
   - Map today's arguments: language, initial prompt from the vocabulary, and word-level timing.
     Use JSON output with token timestamps, such as `-ojf`; check the exact flags against the
     pinned release.
   - Map the JSON into the same payload `_whisper_payload` returns today, so
     `build_transcript`, the hallucination guard and the timeout and heartbeat behave the same.
   - Cancelling still kills the child process. No network access, ever.
4. **Pack.** `speech-whisper` downloads a GGML weights file and nothing that can run.
   - Default file: `ggml-large-v3-turbo.bin` from `ggerganov/whisper.cpp` on Hugging Face. It
     is the same model as today, converted. Pin a commit URL, and record the real size and the
     SHA-256 you measured.
   - Don't switch to a quantised file. The founder compares those on their own clip first.
   - An install of the old safetensors pack shows as "needs update" with a plain message, and its
     files are left in place. Never delete user data.
5. **Status.** `engine_status` reports Whisper ready only when both the helper and the weights
   are present. Without them it says which one is missing, in words, and names no model.
6. **Tests.** `tests/test_whisper_cpp.py` covers:
   - the command line for: language, no language, and vocabulary;
   - JSON mapping from a small JSON fixture that you write by hand as text;
   - a missing helper and missing weights;
   - the old-pack state;
   - that the code never takes a runner from the data root.

   Don't make or download any audio or video. The full suite and `node --check
   static/duck/app.js` pass.
7. **Real run.** One run of the real `whisper-cli` on the `samples/jfk.wav` file that comes with
   whisper.cpp, using a small GGML model downloaded into your scratch root only. Put the words,
   the time taken and the `otool -L` output in the review. The Vietnamese check is the
   founder's, by hand, on their own clip. Write those steps in the review.
8. **Review.** It lists the bundle size before and after, the helper size, the pack size, and
   anything you could not verify. **Do not open the app.**

## Notes
- Base: `ducksuite` at `4ebc3d4` or later. R1's helper check and R2's GPL scan already run in
  `build-duck-dev.sh`. Add to them; don't replace them.
- mlx-whisper stays allowed only as a development fallback if it's already installed. The app
  must not need it. If you remove the fallback, say so in the review.
- Apple Speech stays first for the languages it covers. Don't change the routing.
- Commit on `cx/pb-whisper-in-app` with `git -c commit.gpgsign=false commit`. Don't push.
  Don't open the app.
