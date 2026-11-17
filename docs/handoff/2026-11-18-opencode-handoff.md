# Handoff to OpenCode — 2026-11-18

Written by the DuckSuite sub-leader (Claude) on the founder's word: "write a totally handoff with a
detailed latest context for opencode, and tell them to spin out their agent teams to review, check &
fix it". You own the work below until you hand it back. Read this whole file before acting.

## 0. Read first, and what never to read

- Read: `AGENTS.md`, `CLAUDE.md`, `PLAN.md`, `MEMORY.md`, `TODO.md`, `PRODUCT.md`, and the review/brief
  files named below.
- **Never read or search** `old_memory.md`, `old_todo.md`, `old_plan.md`,
  `docs/reports/SESSION.html`, `docs/reports/ducksuite-product-progress.html` (not even grep, tail or a
  count). Write `old_*.md` by append only. Skip the report-row inserts this time (the anchor is
  unknown); list the rows you would have added in your review instead.

## 1. Where the build stands (verified 2026-11-18)

| Item | Value |
|---|---|
| Repo / branch | this folder, branch `ducksuite`. Never merge `main`. |
| HEAD | `11e5e43` chore: remove historical media and document cleanup |
| Remote `ducksuite` | `5c45c4f`. **Six local commits are unpushed** (`83d6782`, `bc89a5a`, `9785972`, `c909766`, `02d04a3`, `11e5e43`). Do not push; the sub-leader pushes after review. |
| Tests | 346 pass (per `docs/teams/coreml-default/review.md`); re-run and state your count. |
| `textfill.VERSION` | 18 (bumped for Core ML), but the default GPU engine is PyTorch. See 3C. |
| Default GPU fill | `DEFAULT_GPU_ENGINE = "pytorch"` in `duckcore/engine/textfill/__init__.py`; Core ML is opt-in with `DUCK_FILL_GPU_ENGINE=coreml`. |
| Core ML package | `build/coreml-lama/out/lama_fill.mlpackage` (11 functions, 117,375,506 bytes, gitignored); per-size packages in `build/coreml-lama/out/sizes/`; converter `scripts/coreml/convert_lama.py` (venv `build/coreml-lama/venv`, coremltools 9.0). |
| Review project | `prj_e95348a97316` (160 s, 1080×1920), edit `ed_38a4c36a3aae`. You may **read** it. Do **not** re-Check it and do not change it. Work on a copy under `build/<your-folder>/` for anything that writes. |
| Machine | M1, 8 GB. Swap was 4–9 GB used during conversions. Measure with that in mind; say the swap state next to every timing. |

Recent commits you must review rather than trust (section 3D):

- `bc89a5a` (2026-11-16) pack verify and import copy. It introduced two regressions; `c909766` claims to fix both
  (`docs/teams/coreml-default/regression-review.md`).
- `02d04a3` (2026-11-17) Core ML repair and fallback-cache isolation, with measurements
  (`docs/teams/coreml-default/review.md`, `measurements.md`, `founder-test.md`).
- `11e5e43` (2026-11-17) removed historical media at the founder's request (`docs/MEDIA-CLEANUP.md`).

## 2. Hard rules (unchanged)

Local only: no upload, telemetry or account. No model name in the UI. Do not hide a limit: measure it
and show it. Bump `textfill.VERSION` only when fill output changes, and say the next render is cold. A
new request gets a `REQ-YYYYMMDD-NN` in `MEMORY.md` plus `TODO.md` items before code. Keys go to the
Keychain. GPU only for renders; never stop a render mid-clip; no every-frame OCR. Never generate or
download test media; no founder frames, crops or paths in any commit. App Store, signing and
TestFlight are paused. Never ship NLLB or translation weights. The founder runs the app and every hand
test: you never click in the founder's app window. You may run a dev server on a scratch data root
(see `.claude/launch.json`, `duck-scratch-*`, token in the URL as `#t=<token>`) and drive it with the
shared Playwright. Commit with `git -c commit.gpgsign=false commit`; do not push.

## 3. The work, in order

### 3A. Bug, founder-visible: the Clean layer list is invisible, so a layer cannot be selected or turned off

Founder: "why i cannot select and change an auto scanned fill? like i want to remove it (not clean it
anymore)". Seen by the sub-leader on 2026-11-18 in an 800×600 window, review project, Edit → Clean tab.

- The panel shows "6 of 6 layers", then nothing, then "Paint a mask". The six `.layer-row` buttons
  exist in the DOM (Title 01 · Blur, Subtitle 02–06 · Fill), but `.layer-list` has **height 0**.
- Cause: `.inspector-body` is a CSS grid with a fixed height (`.edit-clean .inspector-body { flex: 1;
  overflow: auto; }`, `static/duck/app.css:1294`) and auto rows. `.layer-list` has
  `max-height: 232px; overflow-y: auto` (`app.css:1722`), so its automatic minimum size is 0 and its
  grid track collapses to 0 px when the panel is shorter than its content.
- Tried in the browser only (no file changed): `.inspector-body { grid-auto-rows: max-content; }` brings
  the list back at 207 px with all rows clickable. Check whether that is the right fix, or whether a
  `min-height` on the list is better, and look for every other scroll child that collapses the same way
  (`.proof-list`, `.clean-scene-list`, Clean Focus, Preview, Render, Settings).
- Accept: at 800×600, 1024×700, 1280×800, 1440×900 and 200 % zoom, the layer list shows at least
  three rows or all of them, rows select, and Fill / Blur / Off changes the selected layer. Add a test
  if the repo has a UI-layout test pattern; otherwise a Playwright script under `scripts/` with its
  output in the review. Screenshots of the review project stay in `build/` (gitignored), never in Git.
- Also answer, in the review, the founder's wish to "remove" a layer: today there is only **Off**
  (kept, greyed). Clicking a box on the video does not select a layer. Do not build either; put them in
  `TODO.md` as proposals under a new REQ for the founder to decide.

### 3B. Bug, founder-visible: "where is my script in the preview panel?"

- Edit shows a **Transcript** box beside the video (`static/duck/app.js:1476`) only when
  `overlayCuesForTime()` returns lines. For the review project it returns none: captions are 0 cues
  and the saved Check transcript is empty (`language: null`, `provider: null`, 0 segments, empty text).
  So the box is not rendered at all and nothing says why.
- Fix the silent part: when there is no transcript, show the box with one plain sentence saying why
  and the next step (for example: Check found no speech it could read; how to transcribe again). No
  model name. When the user pressed Hide, it must still be obvious how to show it again.
- Find out why Check stored an empty transcript with no provider: the speech step did not run, failed
  silently, or found no speech (the clip is Mandarin). Read the logs and the code path
  (`duckcore/engine/stt*`, `duckcore/check.py`); reproduce on a **copy** of the project in a scratch
  data root, never by re-Checking the original. If it failed silently, that breaks "do not hide a
  limit": make the failure visible.
- Note: the full line-by-line transcript list beside the preview was removed on 2026-11-09 in
  `1d48020` (Edit desk rebuild); the full script now lives in the timeline's Script lane (Edit / Script
  Focus). `transcriptRow()` is dead code. Say this in the review; do not bring the old list back
  without a founder decision.

### 3C. Core ML GPU fill (REQ-20261116-01, REQ-20261116-02)

The founder asked on 2026-11-16: "put CoreML GPU in as default option, i will use it for founder test
later". `02d04a3` measured it and **refused to make it the default**:

- An Apple MPSGraph native abort (`shape.count = 0 != strides.count = 4`, SIGABRT) after eight bucket
  predictions in one process. Python cannot catch it, so it would kill a render.
- Pixel drift up to 19/255 at the exact buckets (the 512-only test showed 3/255), and up to 169/255
  when a run was padded up to a coarser bucket. Coarse padding is now refused and falls back to PyTorch.
- Speed: 1.3–2.5× faster than PyTorch at the exact buckets, but slower once the fallback is counted.
  Cold load 25–33 s, cached 2.4–3.5 s.

Your job: an **independent** review and an attempt to fix it.

1. Reproduce the abort with `scripts/coreml/bench_load_memory.py`. Find the trigger: many functions
   loaded at once in one process, a particular bucket, memory pressure, or the multifunction package
   itself. Try one loaded function at a time (release the others), one package per bucket, or a
   per-process load.
2. Drift: try `compute_precision=FLOAT32` for the buckets that drift most (`512×384`, `512×512`).
   Report time and size against drift. Exact run sizes (every multiple of 16, which is 57 shapes) would
   remove the padding; measure what that costs in package size and conversion time (about 2 min of
   Core ML passes per size, plus the trace, on this Mac).
3. Promote Core ML to the default **only** if there is no abort across a run of every bucket repeated
   at least 3 times, max drift is ≤ 3/255 on the bench pictures, every-frame max diff is small on a
   real span (copy of the review project, `scripts/coreml/bench_real_span.py`), and it is faster cold
   and warm. Otherwise PyTorch stays the default and the review says exactly what blocks Core ML.
4. **VERSION check:** `VERSION` is 18 while the default output is still PyTorch's, which is unchanged.
   That makes every render cold for no pixel change. Decide whether to return to 17 (the cache stamp
   already carries `:coreml-gpu` for Core ML clips) or to keep 18, and justify it. If promotion does
   happen, `VERSION` must differ from 17.
5. The founder's hand test is `docs/teams/coreml-default/founder-test.md`; it stays blocked until
   item 3 passes. Then rebuild with `./scripts/build-xcode-dev.sh` (it copies the package) and update
   that file with the steps.

### 3D. Review the last six commits

Run a code review of `5c45c4f..HEAD`: correctness, tests that really test the claim, docs that match
the code, no founder media or paths in Git (`git log -p` for image or video files and home-folder
paths). Confirm `c909766` really fixes both `bc89a5a` regressions (no full hash on every Settings
open; plain import sentences kept) and that `11e5e43` removed nothing a test or a doc still needs.

### 3E. Then the planned loops

Loop 27 (P5 cost, no pixel change), brief `docs/teams/loop-27-cost/BRIEF.md`, never built: the
OpenCode run on 2026-11-16 hung for 9 h with an empty log. Then loop 28 (P2 layout), whose
1024×700 / 200 % zoom item overlaps 3A. Start loop 27 only after 3A–3D are committed and reviewed.

### 3F. Waiting on the founder (do not build)

FFmpeg compliance:
- ship the source in the app;
- add an "About and licences" link in Settings with the LGPL sentence;
- get THIRD_PARTY_NOTICES into the Xcode build and correct its FFmpeg section;
- rebuild FFmpeg without the home-folder path in its configure string.

The founder has decided these, but they need a REQ entry. Also on the founder:
- the FFmpeg contact address;
- the Vietnamese clip for the Whisper comparison;
- the Kokoro hash;
- the mic test;
- the three Native UI decisions;
- the founder hand test (`docs/teams/founder-test-all.md`).

## 4. Spin out your agent teams

Do not do this alone in one thread. Use your sub-agents (task tool) as a team, with the role briefs in
`.claude/agents/*.md` as their instructions (read those files and pass the relevant one to each agent):

| Agent | Role | Works on |
|---|---|---|
| reviewer (`product-owner.md` + a code-review brief) | independent review, sign-off or reject | 3D, then every fix before commit |
| tester (`tester.md`) | reproduce, write the failing test or script first, pass/fail with evidence | 3A at all window sizes, 3B on a project copy, 3C abort and drift |
| engineer (`engineer.md`) | code and tests | 3A, 3B, 3C fixes |
| researcher (`researcher.md`) | cited facts only | Core ML multifunction and MPSGraph abort reports, coremltools FFT/flexible-shape limits |
| creator (`creator.md`) | advisory taste pass | 3A and 3B copy and layout |

Rules for the team:
- Run independent work in parallel, but never two writers on the same files.
- A tester fail blocks sign-off.
- Every number is measured and names its command.
- Each item (3A, 3B, 3C, 3D) is one commit, following the Definition of done in `AGENTS.md`:
  - behaviour and tests;
  - `MEMORY.md` (a REQ entry for the founder's two questions: REQ-20261118-01) and `TODO.md`;
  - `docs/teams/<loop>/review.md`.
- Keep `MEMORY.md` under about 80 lines.
- The founder's two questions belong to REQ-20261118-01. The Core ML work stays under REQ-20261116-02.

## 5. When you finish

Write `docs/handoff/2026-11-18-opencode-done.md`:
- each item, with pass or fail, its commit, and what was measured;
- what got worse;
- what was not tested;
- the founder's next hand steps.

Then stop. Do not push and do not start loop 28.
