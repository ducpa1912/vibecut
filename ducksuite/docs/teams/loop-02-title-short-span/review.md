# Loop 2 — prove the title fix on a short span

Date: 2026-11-11 · `PLAN.md` loop 2 · Project `prj_e95348a97316`.

## Brief

The first-frame detection fix was proven on the source only. Re-run Check, Clean all, and render a
short span to see the 66 ms title gone, without paying for a full cold render.

## What happened

1. **Re-Check** through the API on the dev core (145 s; Whisper ran this time and found 3 speech
   segments, language `en`). 42 tracklets: 41 `subtitle`, 1 `title` at 0.0–0.25 s, y 0.321,
   text "人吃啥咪吃啥".
2. **Clean all**: 42 layers, the title layer `blur`, all `auto: true`.
3. **Render of clip 1 only** (0–4.75 s, cut at a clip boundary so the fill is reusable), 189 s.
   Every one of its 142 frames was OCR'd.
   - Title: gone on the first frames.
   - **Bug found: 3 frames still showed subtitles** — frames 4 and 5 (a line coming on) and frame 39
     (a line going off).
4. **Cause.** A layer's range put each edge half a sample step from the reading (`_run_range`).
   With the true first frame now read at 0.0 s, the lines that come on at 0.066 s were first read
   at 0.25 s, so their layers started at 0.125 s and two frames were bare. Before the first-frame
   fix the same layers started at 0.0 s, so this was a regression of that fix. The trailing frame
   is the sampler reading a frame late.
5. **Fix.** `detect._run_range` reaches back a whole step and `SAMPLE_SLACK` (0.067 s) past the last
   reading. `clean.FILL_SHORT_SECONDS` moves 0.5 → 0.6 so a line read once is still a flash and
   gets Blur (one such line at 107 s had flipped to Fill).
6. **Re-Check, Clean all, render clip 1 again** (93 s). All 142 frames OCR'd: **0 with text.**

## Acceptance

| Check | Result | Evidence |
|---|---|---|
| `title` tracklet at 0 s, y ≈ 0.321 | pass | `trk_0abb5fe1e7`, 0.0–0.25 s before the edge fix, 0.0–0.317 s after |
| Title layer is `blur` | pass | `cl_7b144258ac`, kind `blur` |
| No `auto: false` layer changed | pass | there were none; all 42 are `auto: true` |
| Counts reported | pass | `fill 40 · blur 2 · off 0`, 34 moving |
| Frame 0 of the short render has no title | pass | OCR empty on frames 1–3; still looked at |
| No burned-in text in the span | pass after fix | 0 of 142 frames; 3 of 142 before |
| Suite | pass | 90 passed; `node --check` passes |

## Not tested, and what it cost

- Only clip 1 (4.75 s of 160 s). Edge leaks elsewhere are covered by the same code but were not
  rendered. Loop 4 OCRs the full render.
- Every range is now about 0.19 s longer. Review project: 42 layers, 34 moving (was 35 of 42 after
  the first Clean all). More frames are filled or blurred, including a few with no text on them.
- The title blur now runs 0.0–0.317 s. The title is on screen for 0.066 s, so about 7 frames carry a
  soft patch with no title under it. It is visible as a smear if you step frame by frame.
- Clean all was run through the API and `clean.apply_report`, not by clicking the dialog. The toast
  with the new estimate (loop 1) is still unseen.
- The render was a direct `render.render_edit` call on an in-memory copy of the edit with one clip.
  The queue was avoided because another dev core (port 8799, same data root) is also polling it.
  The file's audio track is the full 160 s; that is this shortcut, not a product path.
- Roles: one agent did brief, code and test; `creator` and `product-owner` were not spawned.

## Found on the way, not fixed

- **The loop 1 estimate reads high.** It said "up to about 19 min" for clip 1; the render took 189 s
  cold. `fill_rates.json` still holds 10.7 s a unit from 4 short runs and was not updated by these
  renders. The 2 h 44 min for the whole project is therefore likely several times too high. Logged
  for loop 3.
- **Fill needs `DUCK_FILL_MODELS` outside the app.** The dev core cannot fill without it pointing at
  `build/DuckSuite-Xcode.app/Contents/Resources/base-models`.
- **The previous Check's engine record lists `openrouter` among the STT providers tried** (it failed
  before any request: "ffmpeg is not installed"). It is not in the new Check's record. Loop 6 adds
  the test that it cannot be reached.

## Verdict

Pass. The title is gone on a real render, and a 3-frame subtitle leak the old spot checks could
not see is fixed and tested.
