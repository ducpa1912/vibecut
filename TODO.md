# TODO — DuckSuite open work

Only open work lives here; done items and closed loops are in `old_todo.md` (agents do not read it).
Order follows `PLAN.md`. One loop at a time, top to bottom. Every item carries its request id
(`REQ-YYYYMMDD-NN`, from `MEMORY.md`) or its brief/review path.

## Now


- Historical media outputs and scratch footage/projects were removed at the founder's request; retain analysis and recreate authorized scratch data for future measurements (`docs/MEDIA-CLEANUP.md`).

- [ ] REQ-20261116-02 · resolve native Core ML MPSGraph abort and exact-bucket drift (max 19/255); coarse padding max 169/255 is refused; do not promote default until reviewed. 3C review: VERSION back to 17, fallback clips deleted, unknown engine falls to PyTorch; promotion still fails.

- [ ] Founder, by hand, one sitting: `docs/teams/founder-test-all.md` (loops 10–26, fix-02, fix-04;
  each step names its loop; includes story playback, the microphone and the three model slots).

## REQ-20261126-01 — Adopt from Editroom (2026-11-26)

Plan: `docs/plans/2026-11-26-editroom-adoption.md`. Order after P-B: P-D (+W1) → P-E → G1 → T1.

- [ ] REQ-20261126-01 · G1 core: one baked grade cube, `lut3d` render, user .cube LUTs, 8 ported looks with MIT notice, tint, cube/still routes (Codex, started 2026-11-26, brief `docs/teams/g1-grade-cube-core/BRIEF.md`)
- [ ] REQ-20261126-01 · G1 preview: WebGL pass with the same cube, still-frame fallback, look menu and LUT picker in the inspector (after T1 releases `app.js`)
- [ ] REQ-20261126-01 · T1 filmstrip per clip, clip names, track headers, blade tool, scene grid + search, icon style (OpenCode, started 2026-11-26, brief `docs/teams/t1-timeline-picture/BRIEF.md`)

## REQ-20261125-03 — App Store readiness plan (2026-11-25)

Plan: `docs/plans/2026-11-25-app-store-readiness.md`. Lanes (2026-11-26): Codex the heavy work (release, licensing, in-app Whisper, split + reorder); OpenCode small bounded fixes; PO review/merge.

- [ ] REQ-20261125-03 · R3 notices generated from the bundle; test for unlisted components; LaMa entry fixed (Codex)
- [ ] REQ-20261125-03 · R4 trim the bundle; R5 release mode without runtime swiftc (Codex)
- [ ] REQ-20261125-03 · R6 Mac App Store signing and validation, no upload (Codex, needs D1 Gate A, D2)
- [ ] REQ-20261125-03 · P-B follow-ups: whisper.cpp JSON has no no-speech / compression / log-prob scores, so those three transcript guards never fire on Whisper (the repeated-line guard still works): measure on the founder's Vietnamese clip; replace the dev-only Vietnamese steps in `founder-test-all.md` with the GGML pack and update steps (`docs/teams/pb-whisper-in-app/review.md`)
- [ ] REQ-20261125-03 · P-E founder hand test (14 steps in `docs/teams/pe-layer-remove-select/review.md`); removed layers can't be restored from the UI yet (ids kept in `removed_clean`)
- [ ] REQ-20261125-03 · P-D founder hand test (steps in `docs/teams/pd-split-reorder-silence/review.md`); the timeline has no general undo; remove-silence keeps time where overlapping sources cancel in the mix
- REQ-20261125-03 · 2026-11-26 founder: "the heavy lifting should be on codex side". Lanes rebalanced: P-B and P-D move to Codex; OpenCode keeps small bounded fixes (P-A, P-C, P-E)
- [ ] REQ-20261125-03 · S1 store listing and review notes (PO); F1 founder hand test; R7 TestFlight (Gate B)
- [ ] REQ-20261125-03 · founder decisions D1–D9 (plan section D)

## REQ-20261121-01 — Choose Core ML or PyTorch per render (2026-11-21)

- [ ] REQ-20261121-01 · founder speed test on a quiet Mac: same edit, once per engine (script in `docs/teams/render-engine-choice/review.md`)

## REQ-20261118-01 — Clean layers and the missing transcript (2026-11-18)


## Loop 27 — fill and check cost, no pixel change (REQ-20261115-02 P5, REQ-20261111-11)

- [ ] Build the ink store and span units during Check: the first estimate of a project is 144.8 s of
  background work today.
- [ ] Share the leftover check's decode with the render (measured 52.8 s). The check is 68–81 s quiet,
  170–190 s when the Mac is busy (load 18).
- [ ] Crop the fill decode (measured 35–50 s): only with an every-frame proof of identical pixels.
- [ ] Cold render 620–847 s (418 s before the crossing rule); model time 702 s of an instrumented
  1,091 s. Fewer key frames (a third of model time) changes pixels: needs a `VERSION` bump, not loop 27.
- [ ] REQ-20261111-11 · D8 per-frame fill where the picture changes fast: not shipped, no number.
- [ ] REQ-20261111-11 · D9 `follow_motion` for moving lines: wire, measure, ship only if it wins.
- [ ] Fill confidence per line: `quality` is binary from mean motion; a third level only if it wins.
- [ ] REQ-20261111-11 · two lines are not checked: `cl_7b144258ac` (2 frames) and `cl_a47d0aa1c1`
  (no steady strokes). The Render screen says so; no rule judges them yet.
- [ ] REQ-20261115-01 · a short edit's estimate is not reliable: the same 3-clip span measured
  171–601 s cold (loop 21 R2).

## REQ-20261116-01 — LaMa on Core ML (experiment)

- [ ] REQ-20261116-01 · 512 test done (1.35× PyTorch, ±3/255, `docs/teams/coreml-lama-test/review.md`).
  Next: flexible sizes 64–512, real review-project spans, second-load time, how the core calls Core
  ML without PyTorch, and what happens to the TorchScript user slot, MI-GAN and STTN.

## Loop 3D — commit review debts (2026-11-18)

- [ ] Fix the loop-26 review's publisher-digest/sparse-file statements (reversed by `c909766`).
- [ ] `docs/teams/coreml-default/founder-test.md`: the Core ML Settings step needs the env var or is dropped.
- [ ] Re-measure the app bundle and update the stale ≈981 MB figures.
- [ ] Align the Python and JS import-error mappers; `\bpath\b` has no JS twin.
- [ ] Fix the Core ML test module docstring (says default, asserts PyTorch).

## Loop 28 — layout odds (REQ-20261115-02 P2)

- [ ] Open and capture the story media player and the render playback window (never opened yet). Needs footage: moved to the founder hand test (steps in `docs/teams/pc-layout-small/review.md`).
- [ ] Copy text in the transcript menu checked against the real clipboard. Needs footage: founder hand test.

## Waiting on the founder (REQ-20261111-02, `docs/teams/loop-26-ready-29/review.md`)

- [ ] Fill `<contact address>` in `duckcore/licenses.py` and `Licenses/FFmpeg-SOURCE.txt`.
- [ ] Speech pack (GGML, 1.62 GB, required for `vi`; whisper.cpp in the app since P-B): a short Vietnamese clip the founder owns, to check P-B and compare
  today's pack with turbo-4bit (0.46 GB) before any switch.
- [ ] Manual microphone test on a clean Mac (step in `founder-test-all.md`).
- [ ] The stored transcript of `prj_e95348a97316` holds three made-up cues: the founder runs Check
  again; it can move clean-layer ranges.

## Native UI (planned 2026-11-12)

Decision open: SwiftUI + AppKit bridges (recommended) or AppKit only. Freeze the web UI, or run both.
Cutover screen by screen behind a flag (recommended), or one branch merged at the end. XCUITest may
tap its own app instance (recommended), or frames and screenshots only. Plan: `PLAN.md`, Native UI.

- [ ] N1 · shell: window, toolbar, navigation, tokens, Settings, Welcome/projects, API client, models
- [ ] N1 · remove WKWebView from the launch path behind a flag; old UI still reachable
- [ ] N2 · Check: native player, scene strip, progress, transcript/OCR tables
- [ ] N3 · Edit desk: three panes, AVPlayer, transcript + opacity, inspector tabs, Cut Focus
- [ ] N4 · Edit timeline: AppKit lanes, 1x-16x, playhead, trim/split/slip, audio
- [ ] N5 · Clean: compare, layers, box edit, brush, proof steps, Re-clean route
- [ ] N6 · Preview: sequence player, safe zones, proofs, story picker
- [ ] N7 · Render: queue, estimate, progress, leftover report, playback
- [ ] N8 · delete the web UI and WKWebView; parity audit with XCUITest
- [ ] N1-N8 · XCUITest measurement: 1024×700, 1280×800, 1440×900; no headless Chrome

## Cut and story — open after brief loops 14–20

- [ ] REQ-20261112-04 · loop 19: CoreML super-resolution pack is research only. Before any build: a
  licence check of the weights and an M1/8 GB benchmark. Neither has been done.
- [ ] REQ-20261112-07 · loop 20: optional local VLM scene captions for story (roadmap; multi-GB,
  minutes per clip, an optional pack only, never a default).

## Later

- [ ] Model pack manager polish: an in-app "verify all" and storage cleanup. Dropped from this file
  in loop 6/9; restored 2026-11-13.
- [ ] Cold render cost beyond the estimate: warm the cache after Clean all, or cap fill work by plan.
- [ ] `pipeline._first_still` adds one ffmpeg seek per Check; measure on a 10-minute source.
- [ ] Title blur runs 0.0–0.317 s for a 0.066 s title: about 7 frames carry a soft patch; consider an
  exact end for a first-frame-only reading.
- [ ] Short flashes after the first frame: a title under 250 ms at a later cut can fall between
  4 fps samples. Measure before fixing.
- [ ] Auto-frame remains a deliberate v1 cut.

## Paused by decision

- [ ] App Store gate: signing, team, store URLs, review contact, nested signing. Paused; do not start.
- [ ] Cloud render plans ($5 / $20): deferred; nothing in the build uploads.
- [ ] User keys (BYOK), after v1, per `docs/duck/BYOK-PLAN.md`: Keychain store + redaction,
  Connections UI with consent, STT/rewrite/voice keys, fill endpoint last.
- [ ] Merge `main`: no common ancestor; never a merge target.

## Standing

- [ ] Every loop writes `docs/teams/<loop>/review.md` (verdict, pass/fail per acceptance, what was
  not tested, commits).
- [ ] Every loop appends one row to `docs/reports/ducksuite-product-progress.html` without reading
  the file into context (scripted insert, newest on top).
