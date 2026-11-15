# Loop 26 — $29 readiness (PLAN loop 8, REQ-20261111-02; REQ-20261115-02 P4)

Written by the sub-leader on 2026-11-15. HEAD `b9ad447`, 286 tests. Build team: OpenCode, one
phase. Rules as loop 23 ("Rules for every phase"). No fill change: `textfill.VERSION` stays 17.
The microphone hand step is already in `docs/teams/founder-test-all.md` (loop 23); nothing to do.

## 1. SHA-256 for every pack file (`duckcore/packs.py`)

Today only `lama_fp32.onnx` has a hash, and a file is accepted at ≥ 98 % of its size
(`packs.py:116`, `:186`).
- Every file of every pack (`kokoro-v1.0.onnx`, `voices-v1.0.bin`, `lama_fp32.onnx`,
  `weights.safetensors`, `config.json`) carries `sha256` and an exact `size_bytes`.
- **The hash comes from the publisher**, never from a download you hashed yourself and never
  guessed: the Hugging Face API (`/api/models/<repo>/tree/main` or `?blobs=true`, the LFS
  `sha256`/`oid`) and the GitHub release asset `digest`. In the review, list each file with its hash
  and the exact URL you read it from. If a publisher gives no hash for a file, say so and stop for
  that file: do not invent one (keep its current behaviour and mark it failed).
- A download whose size or hash differs is deleted and the pack shows a plain error
  ("The download was damaged. Try again."); nothing partial stays on disk. The 98 % rule goes.
- "Installed" means every file exists with the exact size; the full hash runs once after download,
  not on every Settings open.
**Accept:** tests (no network; a small temporary file and its own hash): right file → installed;
one byte changed → rejected and deleted; short file → rejected; a test that every `PACKS` file has a
64-hex `sha256` and an integer size.

## 2. LGPL source offer for the bundled ffmpeg

`Licenses/FFmpeg-LGPL-2.1.txt` exists; `scripts/build-ffmpeg-lgpl.sh` builds FFmpeg 7.1.1.
- Add `Licenses/FFmpeg-SOURCE.txt`: version, the exact configure line (read from the script, not
  retyped by hand: a test compares them), the source tarball URL and its SHA-256 as published by
  ffmpeg.org (cite where), and a written offer to provide the source on request for three years,
  with a contact placeholder `<contact address>` for the founder to fill. No personal email in the
  repo.
- Settings shows it where the licences are listed (an "About" or licences block; add one line if
  none exists): "FFmpeg 7.1.1 · LGPL 2.1 · source offer" opening the text.
- The build copies the file into the app bundle beside the licence (check the Xcode build script).
**Accept:** a test that the file names the version and the configure line matches the script; a node
test that Settings renders the line.

## 3. Whisper pack options — research only, no change

The pack is `whisper-large-v3-turbo`, 1.61 GB, required for Vietnamese. **Do not build hosting,
do not change the pack, do not download or generate audio.** From published sources only (model
cards, the Whisper paper, benchmark pages — cite each URL):
- size of the smaller options that run in MLX (e.g. small, medium, a quantised turbo);
- their published Vietnamese word error rate (state the dataset);
- published Apple-silicon speed if any; mark "not published" where there is none.
Write a table and one recommendation in the review. Nothing in code.

## 4. Fill repair instruction

Where the fill engine shows its problem text and **Reveal**, add one plain line with the next step
(for the built-in engine: reinstall DuckSuite; for the CPU pack: Remove, then Download again; for
the user fill model: Clear, then Choose again). No model name.
**Accept:** a node test per case.

## 5. Import error copy

Every technical message an import can show (grep `media.py`, `append.py`, `main.py` and the import
paths in `app.js`: `ffmpeg frame read failed`, probe failures, unsupported codec, no video stream,
no audio, unreadable file, disk full, …) maps to a creator sentence with a next step, e.g. "This
video could not be read. Export it again as H.264 or HEVC MP4 and try again." The technical text
stays in the log, not the toast. List every message and its mapping in the review.
**Accept:** a test per mapped message; an unknown message falls back to one plain sentence.

## Done

One commit: code + tests + `docs/teams/loop-26-ready-29/review.md` (pass/fail per item with numbers,
the hash sources, the Whisper table, what got worse, what was not tested) + `TODO.md` (tick the
loop 8 items that pass and the P4 line) + `MEMORY.md` Outcome on REQ-20261111-02. pytest and
`node --check static/duck/app.js` pass; state the count. Do not push.
