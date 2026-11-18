# OpenCode done — 2026-11-18

Branch `ducksuite`, HEAD before this handoff: `1942237`. Nothing was pushed. Four item commits, one per item, followed by this record.

## 3A — Clean layer list — **PASS** (`49be5ff`)

The list had height 0 because its auto grid track collapsed inside `.inspector-body`. `grid-auto-rows: max-content` restores it; the layer head/list are first in the Clean inspector.

| Viewport | List | Rows | Visible | Row + Fill/Blur/Off |
|---|---:|---:|---:|---|
| 800×600 | 207 px | 6 | 6 | selected `cl_7b144258ac`; Fill → Fill, Blur → Blur, Off → Off |
| 1024×700 | 207 px | 6 | 6 | pass |
| 1280×800 | 207 px | 6 | 6 | pass |
| 1440×900 | 207 px | 6 | 6 | pass |
| 200 % (720×450) | 207 px | 6 | 5 | pass |

Script: `NODE_PATH="$(npm root -g)" node scripts/check-clean-layout.cjs --base "http://127.0.0.1:8813/?t=scratch-3a" --project prj_e95348a97316 --out build/opencode-3a`.
Other scroll children: **0** with `overflow-y:auto`, `clientHeight 0`, `scrollHeight > 10` on Edit, Clean, Preview, Render at 800×600.

The founder's "remove" wish is **not built**: today only Off exists (kept, greyed), and clicking a box on the video does not select a layer. Both are proposals in `TODO.md` under REQ-20261118-01.

## 3B — Silent missing transcript — **PASS** (`6693b3e`)

Cause: the Review project's stored check has `transcript` with 0 segments and `engine.stt_errors` for four failed routes (local speech returned no text, Whisper not installed, OpenRouter routes failed). The Edit box only rendered when cues existed.

Now the box always renders for a video scene, says **No transcript** + one plain sentence + next step, keeps **Hide/Show**, and at ≤1200 px sits under the picture. At 800×600: box y 280–479, picture y 63–266, timeline starts 486 — no overlap, no horizontal clipping. At 1280/1440 it sits beside the picture. At 200 % it is capped at 200 px and scrolls.

The full line-by-line transcript list remains gone (`1d48020`); the script lives in the timeline's Script lane / Script Focus. `transcriptRow()` is dead code. The old list is not restored without a founder decision.

## 3C — Core ML review and fix attempt — **FAIL on promotion, fixes landed** (`1b36a04`)

| Gate | Measured |
|---|---|
| Native abort | SIGABRT after 8 completed calls, on the **9th** function (512×256); **one run only** |
| Exact-bucket drift | **5–19/255**; every bucket above 3/255 |
| Coarse padding drift | **169/255**; gate refuses those runs |
| Warm speed | 0.57×–7.76× PyTorch; slower at 512×384, 384×512, 512×512 |
| Cold / cached load | 32.362 / 3.500 s Core ML; 2.801 / 2.395 s PyTorch |
| Peak RSS | 854,654,976 B vs 402,718,720 B |
| Real span | 15 frames: Core ML **fell back**; equal pixels are PyTorch's |
| Coverage | 9 of 42 review layers; 160 of 896 fitted sizes |

PyTorch stays the default. **VERSION is 17 again**: the default pixels are unchanged, and a Core ML clip carries its own `:coreml-gpu` stamp, so no existing cache is invalidated. Fixed: unknown engine names fall back to PyTorch; fallback/mixed clips are deleted after the encoder reads them. Compile destination and fallback-cache identity were already correct in `02d04a3`.

Not rerun: the abort and drift benchmarks — `coremltools` is absent from the system Python and `build/coreml-lama/venv` is gone. The 9th-function abort trigger remains unknown.

## 3D — commits `5c45c4f..HEAD` — **ACCEPT** (`1942237`)

No P0/P1. `c909766` really fixes both `bc89a5a` regressions (plain import sentences preserved; installed pack status is size-only and a test would fail if it hashed). `11e5e43` removed no file a test or code needs; 346 tests pass. No founder media or home path was added; 198 deleted binaries are historical media only.

P2 doc debts and P3s are listed in `docs/teams/loop-3d-commit-review/review.md` and `TODO.md`: loop-26 review statements reversed by `c909766`, the unreachable Core ML founder-test step, stale bundle size, Python/JS import-error mapper drift, dead test docstring.

## Team

- **reviewer**: independent 3D review, verdict accept with P2/P3s; read-only.
- **researcher/tester**: independent 3C evidence audit; read-only; could not run Core ML (no `coremltools`/venv).
- **creator**: advisory pass on 3A/3B screenshots. Notes: caption-less transcript box has an Opacity slider that does nothing; "MOVES" reads as position, not motion; most scene rows are unnamed; the empty After slot reads as failure; toast covers the timeline. Some captures were pre-final and the 800 transcript spill was fixed in `6693b3e`.
- OpenCode (this session) acted as engineer and tester; every number above was measured with the named command.

## What got worse

- 3A: layer list first means the before/after and Fill/Blur/Off sit below the fold at 800/200 %.
- 3B: at 800 the picture shrinks to 156×278 to make room; at 200 % the empty message scrolls inside a 200 px box.
- 3C: the 112 MiB Core ML package remains in the bundle while unused by default, and the native abort can still kill a process.
- 3D: text-only debt remains; no code regression accepted.

## Not tested

- Real clicks in the founder's app window; all UI work used a scratch data root and the shared Chromium.
- VoiceOver/keyboard order for the layer list and transcript.
- A real Core ML load/abort/drift run; FLOAT32 or 57-shape package; swap.
- A rebuilt app screen for the four commits; no build was run.
- 3D's bundle-size re-measure.

## Founder next steps

1. Run the Clean and transcript steps in `docs/teams/founder-test-all.md`; the layer list and empty box are ready to look at.
2. Decide the two REQ-20261118-01 proposals: add a real Remove layer action, and box-click selection.
3. Core ML remains opt-in and blocked; no promotion until the abort, ≤3/255, real-span parity and cold/warm speed gates pass.
4. The existing founder items still wait: FFmpeg contact, Vietnamese Whisper clip, Kokoro hash, microphone test, Native UI decisions.

Report rows were skipped as instructed; the rows that would have been added are the four item titles above with their test counts (346).
