# TODO — DuckSuite open work

Only open work lives here; done items and closed loops are in `old_todo.md` (agents do not read it).
Order follows `PLAN.md`. One loop at a time, top to bottom. Every item carries its request id
(`REQ-YYYYMMDD-NN`, from `MEMORY.md`) or its brief/review path.

## Now

- [ ] Founder, by hand, one sitting: `docs/teams/founder-test-all.md` (loops 10–26, fix-02, fix-04;
  each step names its loop; includes story playback, the microphone and the three model slots).

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

## Loop 28 — layout odds (REQ-20261115-02 P2)

- [ ] 1024×700 and 200 % zoom measured on the six screens: overlaps, clipped buttons, horizontal scroll.
- [ ] Open and capture the story media player and the render playback window (never opened yet).
- [ ] Frame timecode beside the time on the Edit bar (today a tooltip only, `98e1edf`).
- [ ] Copy text in the transcript menu checked against the real clipboard.

## Waiting on the founder (REQ-20261111-02, `docs/teams/loop-26-ready-29/review.md`)

- [ ] Fill `<contact address>` in `duckcore/licenses.py` and `Licenses/FFmpeg-SOURCE.txt`.
- [ ] Whisper pack (1.61 GB, required for `vi`): a short Vietnamese clip the founder owns, to compare
  today's pack with turbo-4bit (0.46 GB) before any switch.
- [ ] Kokoro: the two files have no publisher hash (exact size only); a publisher hash closes it.
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
- [ ] Timeline split and reorder; remove-silence. Trim works, the rest does not.
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
