# Loop 4 (full render) — Senior PO brief to the build team

From: Senior PO (Claude Code session). To: the OpenCode team (PO, engineer, tester, creator).
Date: 2026-11-11. Branch `ducksuite`, HEAD `f101803`. Review folder: this one.

The founder ran the full render by hand. I reviewed the output. **Loop 4 does not pass yet.** Your job
is to close it: fix what the render exposed, prove it on a new full render, record it. Work on your
own, in as many internal loops as it takes, with your own PO gate on each. Send me **one** final
report at the end, not progress notes.

## What I measured (do not re-argue; re-measure if you doubt it)

Render `renders/ed_38a4c36a3aae_20261111-164411.mp4`, project `prj_e95348a97316`.

| Fact | Value | How |
|---|---|---|
| Output | 1080×1920, 30 fps, 160.03 s, 4779 frames, H.264/AAC | `ffprobe` |
| Wall clock | **851 s (14 min 11 s)**, queue row `rq_63ed06da41a0` | `render_queue.created/updated` |
| Estimate shown before Start | about 5 min 48 s, AI fill only, "first guess" | `render.estimate_edit` |
| Fill rate now stored | `lama_run_gpu` 1.52 s a unit (recent 1.21, 3.17, 1.52) | `fill_rates.json` |
| Spot frames 0, 2, 10, 90, 157 s | clean, no outline residue seen | looked at |
| OCR, 6 fps over the whole file (960 frames) + every frame of 0–10 s (300) | **2 frames with a burned-in subtitle** | `bin/vision_probe` |
| First attempt | **failed in 0.5 s**, queue row `rq_8ed3ee41c11d` | `render_queue` |

Evidence image: `leaks.jpg` (left to right: 95.567 s leak, 7.333 s leak, two frames of real bowl print).

## Findings

**F1 · P0 · a subtitle shows for one frame after its layer ends.**
- 7.333 s: "小馋猫叉开始催餐了". Layer `cl_fc7b1a26e1` ends 7.317 s.
- 95.567 s: "看咪能不能吃到里面的肉". Layer `cl_26c85fa9cd` ends 95.567 s.
- Both are the first frame after the range. `detect.SAMPLE_SLACK` (0.067 s) is not enough, and the
  render output is one frame later than the source (loop 2 saw the first frame doubled).
- Only 1,260 of 4,779 frames were read, so expect more of these.
- Wanted: edges that are right, not just wider. Guessing a bigger slack also grows the patches over
  frames with no text (the 0.066 s title is already covered for 0.317 s). Prefer reading the frames
  between the last reading that shows the line and the first that does not, and the same at the
  start. Also find and fix, or account for, the one-frame offset between source time and output.

**F2 · P0 · the first Start render failed** with "The LaMa (per frame) fill model is missing. Put
lama_fp32.onnx in …/models/fill" on a build whose default is GPU and whose CPU engine is optional.
- Suspect: two cores were polling one queue (the app's `duckcore` and a `duck_app.py` dev core on
  port 8799 started at 16:19, before the GPU-default commit). `RenderQueue._next`
  (`duckcore/render.py`) selects a queued row and the state change is a separate step, so two
  workers can take the same job, and a stale one can fail it.
- Wanted: root cause proven, not assumed. An atomic claim. An error that names the engine that was
  really chosen and never tells a GPU user to install a CPU file. A test for each.

**F3 · P1 · the estimate hides most of the wait.** It said about 5 min 48 s; the render took
14 min 11 s. The box counts AI fill only. Ground rule 4: do not hide a limit.
- Wanted: the box says what it covers and gives the whole render time once this Mac has a measured
  one. The finished job shows estimate and real time side by side.

**F4 · P1 · two defaults for one setting.** `render._fill_device` falls back to `"cpu"` when
`fill_device` is unset; `app_settings` reports `"gpu"`. With the CPU pack installed and the setting
unset, the render uses CPU while Settings says GPU. One default, one test.

**F5 · P2 · an SRT nobody asked for.** The render wrote `…-164411.srt` with one cue,
"I'm going to eat a little bit of chicken." at 1:30. The video has no such speech; Whisper made it
up during the re-Check. Find out why a sidecar is written when the user made no captions, and stop
a made-up transcript reaching an export without the user seeing it.

**Not a defect:** the low-confidence OCR hits at 114–118 s and 153–154 s are the print on the cat's
bowl ("…CANDIES"). Real scene text must stay. Your leak check must tell it apart from a subtitle.

## Acceptance — what I will check before I pass this to the founder

1. A tool in `scripts/` that OCRs **every frame** of a render and reports each frame where text from
   a Check tracklet is still visible, apart from scene text. It is run on the final render and its
   output is in the review.
2. New full render of the review project on GPU: **0 frames** with burned-in text out of all frames.
   No outline residue, no frozen patch at a cut, at 0, 2, 10, 90, 157 s and at five cuts you pick.
3. Total filled or blurred time does not grow past today's without a stated reason. Report seconds
   covered before and after. The title patch gets shorter, not longer.
4. F2: the failure is reproduced in a test, then fixed. Two workers on one queue run a job once.
5. F3: estimate and real wall clock of the final render, both recorded in the review and the report.
6. F4 and F5 closed or returned with a reason.
7. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass. Test count stated.

## Rules

- Contract: `AGENTS.md`. Each internal loop: brief → engineer + tester → creator → your PO → one
  commit with `MEMORY.md`, `TODO.md`, a report row on top. Push over HTTPS.
- A detection change needs re-Check, then Clean all, then render. **Keep the founder's own layer**
  (`auto: false`, Scene 01 · Title 01). Say what Clean all changed.
- Bump `textfill.VERSION` only if fill output changes, and say the render is then cold.
- GPU only. Do not install the CPU pack. A full render is about 14 min; budget for at least two.
- Before a render, make sure one core owns the queue. Stop only processes your own session started;
  ask the founder about any other.
- Do not open, edit or delete any other project. Do not delete the founder's render
  `…-164411.mp4`; it is the baseline.
- Never merge `main`. No App Store, signing or TestFlight work. v1 stays local: no keys, no upload.
- Report what you did not test. A pass that hides a gap is a fail.

## Final report to me (one message, when everything above is done)

- Verdict per finding F1–F5 and per acceptance item 1–7: pass / fail / not done, with the evidence.
- Commits (sha, one line each), test count, final render path, wall clock vs estimate.
- Frames with text: count out of total, and the list if not zero.
- Seconds covered by fill and blur, before and after.
- What you did not test, and anything you found and left.
- Write the same as `docs/teams/loop-06-full-render/review.md`.
