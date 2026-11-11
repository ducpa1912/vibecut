# Loop 6 — Full render, closed

Date: 2026-11-11 · Senior PO brief · Build team (PO, engineer, tester, creator)
Branch `ducksuite`, final HEAD after this loop · Project `prj_e95348a97316`.

## Verdict

Loop 4 closes: **pass on all five findings and all seven acceptance items**, with two notes that
must travel with it — the whole-render estimate now errs high on a warm cache, and a real CPU-pack
download was not tested.

## F1 · P0 · a subtitle showed for one frame after its layer ended — **pass**

Two causes, both fixed.

1. **Mask table used the frame centre.** `mask.frame_rects` tested a layer window at
   `start + (i + 0.5)/fps`, so a range ending inside a frame dropped that frame, while the decoded
   frame still held the picture from its start. Frames are now tested at `start + i/fps`.
2. **Range ends sat up to a quarter second early.** A 4 fps read can miss the frame where the line
   lasts; `SAMPLE_SLACK` guessed the rest. `detect.refine_tracklet_edges` now reads the source at
   its own frame rate around each end and moves the edge to the last frame where the tracklet's
   words are present. It narrows or corrects, never pads.

Evidence:
- Baseline 16:44 render: 2 known leaks (7.333 s, 95.567 s), reproduced by the new tool.
- Final render: **0 leak frames out of 4,800** read.
- The one-frame render offset suspected in the brief was measured and **not found**: the fill
  clip's frame 0 matched the source at the span start (MAE 3.32 vs 9.5 for the neighbouring frames).
  The two leaks were the mask-centre bug and early range ends, not a render offset.

## F2 · P0 · the first Start render failed on a GPU build — **pass**

Root cause proven: `RenderQueue._next` selected a queued row, and the state change to `running`
was a separate statement. Two cores on one data folder could both take the job; the stale one
failed it with its own model state. The Mac had a dev core on :8799 from before the GPU default,
exactly as suspected.

Fix: `_claim_next` does `BEGIN IMMEDIATE`, selects, and updates that row to `running` in the same
transaction. A second worker sees no queued row. Test:
`test_two_workers_claim_a_job_once` builds the same DB twice, inserts one job, and asserts the
second worker gets `None`.

Error text: `device_problem(method, dir, "gpu")` is the only readiness check a GPU render sees.
Test `test_a_gpu_error_never_names_the_cpu_file` asserts a GPU failure never mentions
`lama_fp32.onnx`.

## F3 · P1 · the estimate hid most of the wait — **pass, with a note**

The estimate now has two lines: AI fill, and **whole render** from a measured seconds-per-output-
second ratio (`render_rates.json`, middle of the last three renders). The queue stores the estimate
at claim and the real elapsed at completion; done rows show both.

| Render | Estimate | Real |
|---|---|---|
| Baseline, founder, 16:44 | ≈5 m 48 (fill only, first guess) | **14 m 11 (851 s)** |
| 17:56, first re-render | 14 m 11 | 5 m 39 (339 s) |
| Final, 19:15 | 5 m 34 (333.8 s) | **1 m 16 (76 s)** |

Note: the final render reused most fills, so the whole-render ratio overestimates a warm run. The
box says “up to”; no wait is hidden.

## F4 · P1 · two defaults for one setting — **pass**

`render._fill_device` fell back to `"cpu"` while `app_settings` reported `"gpu"`. One helper now:
`app_settings.fill_device()` returns `gpu` unless the setting says `cpu`, and the render calls it.
Test `test_fill_device_has_one_default` and `test_render_reads_the_same_default_as_settings`.

## F5 · P2 · an SRT nobody asked for — **pass**

Why it existed: `render_edit` wrote a `.srt` whenever the edit had cues, and cues are generated
automatically when the Editor opens. The made-up Whisper line (“I'm going to eat a little bit of
chicken.”) rode into that file.

Fix: a caption file is written only when the edit says `captions.srt`. The Render screen has a
separate “Write .srt file” toggle; “Burn into video” is unchanged. Test:
`test_caption_file_is_opt_in`. The final render wrote **no** `.srt`.

## Acceptance

1. **Every-frame leak tool — pass.** `scripts/ocr_render.py` reads every frame, matches text to
   Check tracklets near their time, and lists non-matching text as scene text. Output:
   `/tmp/final3-leaks.json` (review copy below). It found the baseline 7.333 s leak and the
   bowl print separately.
2. **0 frames with text — pass.** 0 / 4,800 frames. Spot frames 0, 2, 10, 90, 157 s and five cuts
   (4.7/4.8, 10.0/10.1, 15.3/15.4, 20.0/20.1, 25.2/25.3) show no text, no outline residue and no
   frozen patch. The bowl print (“…CANDIES”) stays, as required; it is scene text and is excluded
   from the leak count by display size.
3. **Coverage did not grow — pass.** Fill 72.46 → **70.13 s**, blur 0.57 → **0.60 s** (total
   73.03 → 70.73 s). The 0 s title patch shrank from **0.317 → 0.067 s**.
4. **Queue race — pass.** Atomic claim and the two-worker test above.
5. **Estimate and real recorded — pass.** Table in F3; queue fields `estimate_seconds` and
   `elapsed_seconds` hold them.
6. **F4 and F5 — pass.** Both closed with tests.
7. **Suite — pass.** `python3 -m pytest -q tests` → **109 passed**. `node --check static/duck/app.js`
   passes.

## Final render

`projects/prj_e95348a97316/renders/ed_38a4c36a3aae_20261111-191517.mp4`
1080×1920, 30 fps, 160.03 s, H.264/AAC. Wall clock **76 s** (queue created→updated), estimate
**333.8 s**. Fills mostly reused; changed spans were cold.

## Commits

- `e3f5839` fix(clean): end a text range on its last real frame
- this commit: refine matcher, tool scene-text rule, F2–F5 tests, docs

## After the loop

A later refactor pass (REQ-20261111-10) left render output unchanged and raised the suite to
117 tests; the numbers above are the closure state at 109 tests.

## What we did not test

- A real CPU-engine pack download and CPU fill (the pack was not installed, per the brief).
- The queue row's est/real text in the built UI; the fields were verified through the API.
- GPU variance and heat on a long cold render; the final run was warm.
- The app's own sidecar path for this render: one manual bundled core owned the queue, as the
  brief requires. The app was not running.
- The made-up Whisper cue itself: the file is no longer written, but the cue still exists in the
  transcript.
