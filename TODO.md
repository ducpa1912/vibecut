# TODO — DuckSuite open work

Only open work lives here; done items and closed loops are in `old_todo.md` (agents do not read it).
Order follows `PLAN.md`. One loop at a time, top to bottom. Every item carries its request id
(`REQ-YYYYMMDD-NN`, from `MEMORY.md`) or its brief/review path.

## Now

- [ ] Founder, by hand: `docs/teams/loop-10-layout-balance/founder-test.md` (the whole app in the
  new layout, the fill model folder, "Measuring the fill…", the "not checked" count).

## Founder hand-test 2026-11-12 — workflows

One loop per request, each ends in its own commit. Cut phases 18–19 are roadmap, not now.


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

## Cut — phase 3 (open)

- [ ] REQ-20261112-04 · loop 19: enhance 360p→1080p with lanczos, honest "no new detail" label; optional CoreML pack only after licence check and an M1/8 GB benchmark

## Layout — open after brief loop 10

- [ ] The player bar shows `mm:ss`; the old overlay showed the frame timecode. Put frames back on
  the Edit bar if the founder misses them.
- [ ] Not opened in the layout loop: the story media player (no media beat in the review project)
  and the render playback window. Same bar code; not seen.
- [ ] Copy text in the transcript menu was not checked against the real clipboard.
- [ ] 1024×700 and browser zoom not measured.

## Fill and leftover check — open after brief loops 7–9

- [ ] Fill confidence per line: `quality` is binary from mean motion; consider a third level or score.
- [ ] REQ-20261111-11 · D9 `follow_motion` for moving lines: wire, measure, ship only if it wins.
- [ ] REQ-20261111-11 · two lines are not checked: `cl_7b144258ac` (2 frames) and `cl_a47d0aa1c1`
  (no steady strokes). The Render screen says so; no rule judges them yet.
- [ ] REQ-20261111-11 · cold render 620–847 s on this Mac (418 s before the crossing rule); model
  time is 702 s of an instrumented 1,091 s. Measured, not built:
  crop the fill decode (35–50 s, needs an every-frame proof); share the check's decode (52.8 s);
  fewer key frames (about a third of the model time, changes pixels, needs a `VERSION` bump).
- [ ] REQ-20261111-11 · first estimate of a project is 144.8 s of background work: build the ink
  store and the span units during Check.
- [ ] REQ-20261111-11 · leftover check 68–81 s quiet, 170–190 s when the Mac is busy (load 18):
  the check and a render compete for the same cores; measure with the app alone before tuning.
- [ ] The stored transcript of `prj_e95348a97316` still holds three made-up cues: the founder runs
  Check again; it can move clean-layer ranges.

## Loop 7 — local model slots (REQ-20261111-03)

Design: `docs/duck/BYOK-PLAN.md`. v1 is local only; no keys.

- [ ] REQ-20261111-03 · `providers.py` registry + `Provider` interface, no behaviour change
- [ ] REQ-20261111-03 · transcription local slot: choose an MLX Whisper folder, validate, copy
- [ ] REQ-20261111-03 · rewrite local slot: base URL on this Mac (localhost only), `/v1/models` check
- [ ] REQ-20261111-03 · voice local slot: custom ONNX voice folder
- [x] REQ-20261111-03 · fill local slot: shipped in brief loop 8 (`7bda48d`); founder test open above

## Loop 8 — $29 build readiness (REQ-20261111-02)

- [ ] SHA-256 per pack file; `packs.py` accepts ≥98 % of the expected size today
- [ ] LGPL written source offer for the bundled ffmpeg, beside the licence text
- [ ] Shrink the Whisper pack or make it per-language (1.61 GB; required for `vi`)
- [ ] AI fill repair / reinstall instruction beside the existing problem text and Reveal button
- [ ] Manual microphone test on a clean Mac; recording compiles, never tested by hand
- [ ] Import failure copy: technical errors ("ffmpeg frame read failed") rewritten for a creator

## Later

- [ ] Cold render cost beyond the estimate: warm the cache after Clean all, or cap fill work by plan.
- [ ] `pipeline._first_still` adds one ffmpeg seek per Check; measure on a 10-minute source.
- [ ] Title blur runs 0.0–0.317 s for a 0.066 s title: about 7 frames carry a soft patch; consider an
  exact end for a first-frame-only reading.
- [ ] Short flashes after the first frame: a title under 250 ms at a later cut can fall between
  4 fps samples. Measure before fixing.
- [ ] Timeline split and reorder; remove-silence. Trim works, the rest does not.
- [ ] Aspect switching / auto-frame: source aspect only, deliberate v1 cut.

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
