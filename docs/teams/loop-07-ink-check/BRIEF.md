# Loop 7 — catch every leftover text, and fill better

Senior PO brief, 2026-11-11. Founder request: no text left un-cleaned, the app finds leaks by
itself, and the bad fills get better. Do **not** OCR every frame; the app must not need that.

Run this with your own PO, engineer, tester and creator. Work in loops until every acceptance
item passes. Do not report between loops.

## The idea

Burned-in text is the only thing that sits on the same pixels while the picture changes. Build a
stroke map ("ink") for each line from the source, then score any frame against it. No OCR.

## What was measured (prototypes in this folder)

`proto_ink.py` — ink = pixels with a strong edge (gradient > 40) on more than 80 % of the line's
frames; score = share of ink pixels that still have a strong edge on a frame.

| Frame | Source | 16:44 render (leaks) | 19:15 render |
|---|---|---|---|
| after the 5.75–7.35 s line | 0.91 on the last text frame, 0.01 on the next | **0.90** | 0.00 |
| 95.567 s | 0.96, then 0.02 | **0.95** | 0.01 |
| other frames in the 1 s window | — | ≤ 0.03 | ≤ 0.03 |

About 1 s a line. Ink for the 5.75–7.35 s line is 8,716 of 50,787 px, 17 % of the padded box.

`proto_onset.py` — full-rate scan at 540×960 for strokes that appear and then stay 4 frames.
43 s for the 160 s video. At a band threshold of 150 px: 104 moments, 38 of 43 range starts
matched. Missed: three at 0.0 s (nothing before frame 0), 90.0 s, 151.5 s.

A blind whole-frame scan for still strokes does **not** work on this video: the camera is often
still and scene edges pass too. Do not ship that as a detector.

The prototypes are evidence, not product code. Rewrite them inside `duckcore`; they hard-code the
review project.

## Bad fills seen

- `bad-fill-0.5s.jpg`: 0.5–0.7 s of the 19:15 render. When the chopsticks cross the text, the
  output shows a hard-edged block of wrong picture. Causes: `mask.text_in_region` returns None on
  a busy frame, so the whole box is the hole; and `_fill_frames_by_runs` blends a fill made on
  other frames of the run.
- `bad-fill-150s.jpg`: the red stripe on the bowl bends where the text was. The model's guess.
- `follow.py` exists and nothing passes `follow_motion` to `prepare_span`; it never runs.

## Build

### A. Ink per line

1. One module that builds a line's ink from the source frames of its range, and scores a frame.
   Handle a steady shot, where scene edges are also still: ink must be the text, not the plate
   rim. State how (for example: edges that are absent just before the line starts and just after
   it ends).
2. Range start and end come from the ink: first and last frame where the score is high. This
   replaces the OCR match in `detect.refine_tracklet_edges` for lines that have ink; keep OCR as
   the fallback and say in the report which was used.

### B. Find text that Check never read

3. In Check: OCR frame 0, the first frame after every cut, and the moments the onset scan
   reports, on top of the 4 fps read. State the added Check time on the review project.

### C. Check the render, in the app

4. After a render, score each layer's ink on the output frames of its range plus 0.5 s each side.
   A hit is leftover text. Store per render: frames checked, frames with text, times.
5. On a hit, widen that layer's range to cover it and refill only that span, once. If it still
   hits, keep the render and show the times.
6. Render screen: "Checked N frames for leftover text: M found", with the times when M > 0.
   The cost of this check goes in the estimate (rule: do not hide a limit).

### D. Better fill

7. The line's ink, grown for outline and shadow, is the hole on every frame of the line. Remove
   the whole-box fallback for lines that have ink.
8. Where the picture under the hole changes fast between key frames, fill each frame on its own;
   no blend from other frames there. Put the added fills in the estimate.
9. Wire `follow_motion` for moving lines and measure it against today's output on the same spans
   (PSNR against a text-free reference where one exists, and the flicker number from 10). Ship it
   on only if it wins; record the numbers either way.
10. A flicker number per line: frame-to-frame change inside the hole against the same in the ring
    around it. Store it per render and list the lines above a stated limit on the Render screen.

## Acceptance

1. A test builds ink from synthetic frames (static text over a moving picture, and over a still
   picture) and scores text / no text correctly.
2. A test feeds a render with one leaked frame and the post-render check reports that frame.
3. A full GPU render of `prj_e95348a97316` after re-Check and Clean all: post-render check reports
   0 frames with text. Confirm with `scripts/ocr_render.py` on that one render as the outside
   proof; it must also say 0 leaks, and its scene-text list must hold no subtitle.
4. Inject proof: run the post-render check on the 16:44 render
   (`ed_38a4c36a3aae_20261111-164411.mp4`); it must report both known leaks (7.333 s, 95.567 s).
5. The 0.5–0.7 s span shows no hard-edged block. Put before/after frames in the review.
6. Total hole pixels over the render, before and after, in the review. It must go down.
7. Flicker number per line, before and after, in the review. No line gets worse without a reason.
8. Estimate against real wall-clock for a **cold** render, recorded. Bump `textfill.VERSION`.
9. No layer with `auto: false` is changed by re-Check (`cl_7b144258ac` is the founder's).
10. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.

## Rules

- `AGENTS.md` is the contract. Next free `REQ-20261111-NN` in `MEMORY.md` and prefixed `TODO.md`
  items before code. Behaviour + test + MEMORY + TODO + report row in one commit.
- Local only. GPU only; do not install the CPU pack. No new model, no download.
- Do not stop a render mid-clip. One core on the data root: check for another core before you
  queue a render, and stop only cores you started.
- Keep all existing renders; they are the baselines. Open no project other than
  `prj_e95348a97316`.
- Do not hide a limit: a one-frame text flash cannot be told from scenery without OCR. Say so in
  the UI copy or the review, with what the app does about it.
- Never merge `main`. No App Store work. Commit with `git -c commit.gpgsign=false commit`, push
  with `git push https://github.com/ducpa1912/vibecut.git ducksuite`.
- Write `docs/teams/loop-07-ink-check/review.md`: each acceptance item pass/fail with its number,
  what was not tested, commits.
