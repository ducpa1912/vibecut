# Loop 8 — a better fill for moving footage (PLAN.md loop 5)

Senior PO brief, 2026-11-11. Start only after loop 7 is committed and its review is written.
Run with your own PO, researcher, engineer and tester. Do not report between loops.

## State on restart (2026-11-12) — read this first

The Senior PO stopped this loop once, reviewed loop 7 and rebuilt it (commit `8d1a9c8`). Read
`docs/teams/loop-07-ink-check/review.md`, revision 2, before any code. What changed under you:

- `duckcore/ink.py` and `duckcore/inkcheck.py` are rewritten. The fill hole is each letter's
  strokes grown 6 px, only on the frames that letter is on screen (`TextMasks(strokes=, base=)`,
  `prepare_span(..., strokes=)`). `span_key` holds `ink_rect` and `ink_key`.
- `textfill.VERSION` is 17. 155 tests pass. A cold render of the review project takes 698 s.
- No fill is carried across a frame where something crosses the text (`_picture_moved`,
  `crossed`). Do not undo this.
- Your unfinished custom-fill work from the first start is on local branch `loop8-wip` (commit
  `f87730e`). It predates all of the above. Do not merge or rebase it. Read its diff, then write
  the slot again by hand on `ducksuite`, on top of the new `prepare_span`.
- Never read or search `old_memory.md`, `old_todo.md`, `old_plan.md`. Never read
  `docs/reports/SESSION.html` or `docs/reports/ducksuite-product-progress.html`; only insert a row
  with a script that prints nothing.
- Also open in `TODO.md` and in scope here if cheap: the render estimate does not count the extra
  fills at crossings. Measure it against a real cold render and fix the estimate, or record the gap.

## Why

34 of 42 clean layers on the review project are `moving`. LaMa fills one frame at a time and
guesses structure (see `docs/teams/loop-07-ink-check/bad-fill-150s.jpg`). Loop 7 made the hole
small and added the flicker number; this loop asks whether another engine beats LaMa on what is
left.

## Build

1. **Researcher first.** One table in `docs/duck/moving-fill-licences.md`: each video-inpaint
   candidate (STTN weights, ProPainter, E2FGVI, any other found), licence of the code, licence of
   the weights, the quoted clause, the URL, commercial use yes / no / unclear. "Unclear" counts as
   no. No model enters the build, the repo or this Mac's bundle without a yes row.
2. **Bench only the yes rows** with `scripts/bench_fill.py` on the moving spans of
   `prj_e95348a97316`, GPU, with loop 7's ink holes: PSNR on a text-free reference (burn a known
   caption onto clean footage from the same video, then remove it), the loop 7 flicker number,
   seconds per output second, peak memory. Peak memory must stay under 8 GB on this Mac.
3. **The path that needs no licence:** a custom fill slot. The user points the app at a local
   ONNX or TorchScript fill model folder; the app loads it in place of LaMa. No model name in the
   UI. The model is never downloaded by the app and never committed. Its stamp goes in `span_key`.
4. Decide from the table. Either a candidate ships as an optional user-supplied model through the
   slot, or the doc records that none wins and the `moves` warning stays.

## Acceptance

1. The licence table exists, every row has a quoted clause and a URL.
2. The bench table exists, measured on this Mac, with the four numbers for LaMa and each allowed
   candidate. If no candidate is allowed, the table holds LaMa alone and says so.
3. A stated verdict: "candidate X beats LaMa by N dB and M flicker at T× the time", or "none does".
4. The custom fill slot loads a user folder, falls back to LaMa with a plain message when the
   folder is wrong, and is covered by a test with a stub model.
5. No weights are added to git, to the bundle or to any pack. `git diff --stat` shows no file over
   1 MB.
6. If fill output changes for a default user: `textfill.VERSION` bump and a cold-render warning.
   If it does not, say so.
7. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.

## Rules

Same as loop 7's brief. In addition: downloading a candidate to a scratch folder outside the repo
for the bench is allowed only for a yes row; delete it after the bench and say so in the review.
Never ship NLLB. Write `docs/teams/loop-08-moving-fill/review.md`.
