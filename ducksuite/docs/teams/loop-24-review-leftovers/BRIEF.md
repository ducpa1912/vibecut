# Loop 24 — code-review leftovers #6, #7, #9, #10, #11 (REQ-20261115-02, P1 rerun)

Written by the sub-leader on 2026-11-15. HEAD `0c4e7f8`, 265 tests. Build team: OpenCode, one
phase only. Findings: `docs/reviews/2026-11-13-loops-07-19.md`. Loop 23 shipped the dead SFX modal,
the grade test, the aspect line, one resident custom model, and Play hidden on Render's own cards.
This loop finishes the rest. Rules are loop 23's (`docs/teams/loop-23-oneshot/BRIEF.md`, "Rules for
every phase"); no fill pixel changes, `textfill.VERSION` stays 17.

## #6 — stories from long scenes (`duckcore/story.py`)

A beat is a whole scene and a story must be 15–90 s, so a source whose scenes are each > 90 s can
never make a story, and the fallback raises too. Batch runs up to N × 240 s of model calls inside
one HTTP request.

- A beat may be a **part of a scene**, cut on transcript sentence boundaries (start/end of the
  transcript cues), still inside that scene.
- `fallback_story` never raises: it returns a story, or a plain reason shown in the UI.
- Batch runs as a background job with progress, like the estimate; the request returns at once.
**Accept:** a test with three 120 s scenes and a transcript → a story of 15–90 s whose beats start
and end on cue boundaries; the fallback test returns a story; the batch request returns in < 1 s and
its job reaches done in a test with a stubbed model.

## #7 — the estimate must not load the user's model (`textfill.engine_choice`)

Building the estimate key loads torch/onnx to prove the model loads.
- The key uses the file's path, size and mtime (and a cheap header check: TorchScript zip /
  ONNX magic bytes); loading happens only when a fill runs.
- A file that later fails to load still fails visibly at fill time, with the existing message.
**Accept:** a test that estimates with a custom model and counts 0 calls to `custom.open_filler`;
a test that a bad file still gives the plain error at fill time.

## #9 — sequence overshoot (`setupSequencePlayer`, loop 16)

Beat ends are found on `timeupdate` (~4 Hz), so each non-contiguous beat overshoots by up to
~250 ms of unrelated footage.
- Stop each segment on time: `requestVideoFrameCallback` where present, else a timer scheduled at
  the segment's end from `currentTime` and `playbackRate`, re-armed on seek, pause and rate change.
**Accept:** a node test of the scheduling logic (seek, pause, rate 2×); a measured overshoot on a
real player: serve the core on the scratch root (`build/loop24-evidence/`, copy of
`prj_e95348a97316`) and play a 3-beat story in a browser (allowed until N1 opens); overshoot per
beat as a number, **≤ 1 frame (42 ms)**, before and after.

## #10 — the ONNX fill slot without onnxruntime (`custom.py`)

The slot is offered but the bundle may ship no `onnxruntime`, so a `.onnx` model always reports
"needs the onnxruntime package".
- First establish the fact: is `onnxruntime` importable by the **built** sidecar
  (`build/DuckSuite-Xcode.app`)? State how you checked.
- If it is not: Settings says plainly that an ONNX model needs a package DuckSuite does not include
  and that a TorchScript `.pt` works; choosing a folder with only `model.onnx` gives that reason, not
  "In use". If it is: nothing changes, and say so.
**Accept:** tests for both cases (importable / not), with the importer patched.

## #11 — Play on a missing render, every path (`app.js`)

Loop 23 hid Play on Render's cards. Every other place that offers Play or opens a render must honour
`output_missing` too: the Welcome latest-render card, the queue rows, the render playback window and
any `play-render` action. List every path you found (grep) in the review.
**Accept:** a node test per path; the core's download route still 404s.

## Done

One commit: code + tests + `docs/teams/loop-24-review-leftovers/review.md` (pass/fail per finding
with its number, what got worse, what was not tested) + `TODO.md` ticks + `MEMORY.md` Outcome line on
REQ-20261115-02. pytest (265 today) and `node --check` pass. Do not push.
