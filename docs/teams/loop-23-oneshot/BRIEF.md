# Loop 23 — one-shot of the open plans, except the native UI (REQ-20261115-02)

Written by the sub-leader on 2026-11-15. HEAD `3e9bf8c`, 253 tests. Build team: OpenCode, one
prompt, five phases in this order. Verifier: the sub-leader, per phase.

The founder's words: "except the native UI, tell opencode to oneshot from 2 loop to 6 Layout odds
and ends". That is: PLAN loop 7, PLAN loop 8, the fill and check work, the 2026-11-13 code-review
leftovers, and the layout odds and ends. **Not** N1–N8, App Store, cloud, user keys, CoreML
super-resolution, VLM captions.

## Rules for every phase

- **One phase = one commit** (`git -c commit.gpgsign=false commit`), code + tests + a section in
  `docs/teams/loop-23-oneshot/review.md` (pass/fail per item with its number, what got worse, what
  was not tested) + `TODO.md` ticks. Do not push. If a phase fails, commit what passes, mark the
  rest failed, and go on to the next phase. Never leave the tree dirty between phases.
- pytest and `node --check static/duck/app.js` pass at every commit; state the count.
- Local only, no keys, no upload, no telemetry. No model name in the UI. No download link that
  DuckSuite provides. Keys are not v1.
- Scratch data root only (`build/loop23-evidence/`, gitignored), never the app container; never edit
  `ed_38a4c36a3aae` in place; **no founder footage in any commit**; no generated video media
  (in-memory numpy arrays in tests are fine). GPU only. Short spans, no full 160 s render.
- Never read `old_*.md` or `docs/reports/*.html`. Do not click in the founder's app window.
- Do not bend a measure to pass. A speed claim needs an equality proof beside it.
- `textfill.VERSION` (17) moves **at most once**, in phase 5, and only if fill pixels change.

## P1 — code-review leftovers (`docs/reviews/2026-11-13-loops-07-19.md`)

Read findings #6, #7, #9, #10, #11 there and fix each in the module that owns it, test first:
long-scene stories (#6), the resident user model (#7), sequence overshoot (#9), the ONNX fill slot
offered when onnxruntime is absent (#10), Play offered on a Done job whose file is gone (#11; the
card says the file is missing and offers no Play). Also: remove the dead SFX filter modal;
make `tests/test_loop22_grade.py` fail when no strokes build at **either** grade; correct the stale
`TODO.md` line "Aspect switching / auto-frame: source aspect only" (Cut aspect shipped in loop 14;
auto-frame stays a v1 cut). **Accept:** one failing-then-passing test per finding.

## P2 — layout odds and ends

1. Edit player bar: show frame timecode (`mm:ss:ff` at the source fps) beside `mm:ss`, without
   widening the bar at 1280×800. Node test for the format at 23.976, 25, 30.
2. Open the story media player and the render playback window on the scratch root (serve the core:
   `python3 duck_app.py --data-root build/loop23-evidence/root --port 8799`; a browser capture is
   allowed until N1 opens). Capture 1440×900 PNGs; state any control that does not work.
3. Measure 1024×700 and 200 % zoom on all six screens: bottom reach, horizontal scroll, overlaps,
   clipped buttons — the loop 10 measures. Fix what fails; capture before/after.
4. Copy text in the transcript menu: test the clipboard call in node; add the real-clipboard step to
   `docs/teams/founder-test-all.md`.
**Accept:** capture paths listed in the review; every measure as a number.

## P3 — PLAN loop 7, local model slots (REQ-20261111-03, `docs/duck/BYOK-PLAN.md`)

1. `duckcore/providers.py` registry with `status()`, `prepare()`, `run()`, the task, the files and
   `needs_secret` (always False in v1). Route the existing steps through it **with no behaviour
   change**: the existing tests pass unmodified.
2. Transcription slot: choose an MLX Whisper folder, validate its files, copy into app data, use it.
3. Rewrite slot: a base URL on this Mac only (`127.0.0.1`/`localhost`/`::1`; any other host is
   refused), checked with `GET /v1/models`; Apple Intelligence stays the default.
4. Voice slot: a custom ONNX voice folder, validated and copied.
Each slot: Settings row like "Your fill model" (None / In use · file / Not usable · reason, Choose,
Clear), names no model, links no download. **Accept:** per slot, a test for valid, invalid and
cleared; a test that a non-local URL is refused; a test that settings.json holds a path, a provider
id and a flag, never a secret.

## P4 — PLAN loop 8, $29 readiness (REQ-20261111-02)

1. SHA-256 for **every** file of every pack in `packs.py`; a download whose hash differs is
   rejected and deleted; the ≥98 % size rule goes. Hashes come from the publisher's own files (state
   the source of each), never guessed. Test: a wrong byte fails.
2. LGPL written source offer for the bundled ffmpeg beside its licence text (version, configure
   line, how to get the source); shown in Settings → About.
3. Whisper pack: measure the per-language and smaller options (size, Vietnamese accuracy on a public
   sample you cite, M1 speed). **Do not build hosting or change the pack**; write the numbers and a
   recommendation in the review.
4. Fill repair: beside the existing problem text and **Reveal**, a plain instruction to reinstall.
5. Import errors: every technical message (`ffmpeg frame read failed`, probe failures, codec) maps to
   a creator sentence with a next step. Test every mapped message.
6. Microphone: add a click-by-click step to `docs/teams/founder-test-all.md`; it is a hand test.

## P5 — fill and check (REQ-20261111-11)

Measure before changing; ship only what wins, each with an every-frame equality or quality proof.
1. Share the check's decode with the render (52.8 s measured): no pixel change; prove equal reports.
2. Crop the fill decode (35–50 s): prove the output frames identical (max diff 0) on a short span.
3. First estimate of a project (144.8 s): build the ink store and span units during Check, in the
   background; Check's own time must not grow by more than 5 %.
4. The two unchecked lines (`cl_7b144258ac`, 2 frames; `cl_a47d0aa1c1`, no steady strokes): a rule
   that judges them, or a stated reason why none can; never counted as clean.
5. D9 `follow_motion` for moving lines and D8 per-frame fill where the picture changes fast: run
   `scripts/bench_fill.py` with ground truth before/after; ship only if it wins, else record the
   numbers and leave it off.
6. Fill confidence per line: a three-level `quality` (steady / moves / fast) from measured motion,
   shown as the existing badge text; no silent switch to blur.
7. Fewer key frames: only if bench quality holds within its noise; it changes pixels.
If any of 5–7 ship, bump `textfill.VERSION` to 18 **once**, and say the next render is cold.

## Out of scope

Native UI N1–N8; App Store/signing; cloud; user keys; CoreML super-resolution; VLM captions; a
`main` merge; changes to `ink.EDGE` / `inkcheck.SAME`.

## Reply

Once, at the end of P5: per phase, each item pass or fail with its number, what got worse, what was
not tested, capture paths, the `textfill.VERSION` decision, and the five commit hashes.
