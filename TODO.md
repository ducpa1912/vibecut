# TODO — DuckSuite open work

Only open work lives here; done items and closed loops are in `old_todo.md` (agents do not read it).
Order follows `PLAN.md`. One loop at a time, top to bottom. Every item carries its request id
(`REQ-YYYYMMDD-NN`, from `MEMORY.md`) or its brief/review path.

## Queue — briefs waiting

- [ ] `docs/teams/loop-08-moving-fill/BRIEF.md` — read the brief, then build it as loop 8
- [ ] `docs/teams/loop-09-rules/BRIEF.md` — read the brief after loop 8 signs off

## Loop 5 — better fill for moving footage

- [ ] Researcher: licence table for video-inpaint candidates (STTN weights, ProPainter, others),
  clause quoted, commercial use yes/no. Nothing enters the build without it.
- [ ] Bench the allowed candidates on the moving spans of the review project (`bench_fill.py`).
  LaMa cannot rebuild a plate it never saw; 32 of 42 lines are `moving`.
- [ ] Alternative without a licence: the custom ONNX fill slot (loop 7).
- [ ] Fill confidence per line: `quality` is binary from mean motion; consider a third level or score.
- [ ] REQ-20261111-11 · D8 per-frame fill where the picture changes fast: no measured win yet.
- [ ] REQ-20261111-11 · D9 `follow_motion` for moving lines: wire, measure, ship only if it wins.

## Loop 6 — make the code match the rules

- [ ] `script.rewrite`: remove the silent Ollama fallback and the `qwen3:4b` name; Apple
  Intelligence, else basic cleanup, stated in the UI.
- [ ] Delete the unused `online_enabled` / `online_endpoint` settings.
- [ ] REQ-20261111-02 · cloud STT paths (`groq`, `deepgram`, `openrouter`): code stays for after v1;
  add a test that none is reachable in a v1 build.
- [ ] Render queue lists "Done" jobs whose file is gone; Play must not be offered for a missing file.
- [ ] Model pack manager polish: in-app "verify all" and storage cleanup.

## Loop 7 — local model slots (REQ-20261111-03)

Design: `docs/duck/BYOK-PLAN.md`. v1 is local only; no keys.

- [ ] REQ-20261111-03 · `providers.py` registry + `Provider` interface, no behaviour change
- [ ] REQ-20261111-03 · transcription local slot: choose an MLX Whisper folder, validate, copy
- [ ] REQ-20261111-03 · rewrite local slot: base URL on this Mac (localhost only), `/v1/models` check
- [ ] REQ-20261111-03 · voice local slot: custom ONNX voice folder
- [ ] REQ-20261111-03 · fill local slot: custom ONNX inpaint model

## Loop 8 — $29 build readiness (REQ-20261111-02)

- [ ] SHA-256 per pack file; `packs.py` accepts ≥98 % of the expected size today
- [ ] LGPL written source offer for the bundled ffmpeg, beside the licence text
- [ ] Shrink the Whisper pack or make it per-language (1.61 GB; required for `vi`)
- [ ] AI fill repair / reinstall instruction beside the existing problem text and Reveal button
- [ ] Manual microphone test on a clean Mac; recording compiles, never tested by hand
- [ ] Import failure copy: technical errors ("ffmpeg frame read failed") rewritten for a creator

## Loop 9 — layout balance (`docs/teams/uiux-balance-01.md`)

- [ ] Render screen restructure: Settings (320 px) + Start render left, queue full width right,
  finished renders as cards. The estimate lives in the left column.
- [ ] Edit inspector: `5 of 9 layers` plus a bottom fade so the clipped row reads as "more below".
- [ ] Timeline empty lanes: collapse a lane with no cues to one 32 px `+` row.
- [ ] Portrait Preview width: scene strip in a 300 px column beside the player.
- [ ] Verify a 9:16 project at 1440×900 and 1280×800.

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
