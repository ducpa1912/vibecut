# TODO — DuckSuite

Status as of 2026-11-11 (REQ-20261111-05). The order below is the build order in `PLAN.md`; work one
loop at a time, top to bottom. Done items stay listed so nothing is repeated by accident.

Items that came from a request carry its id (`REQ-YYYYMMDD-NN`), matching `MEMORY.md`. Items from a
review carry the review file. Items marked `PLAN` came from the 11 Nov code and data review.

**Do not start a full render before loop 4.** Fills are cold since `textfill.VERSION` 12; a 160 s
render takes hours on this Mac, and any fill change in loop 3 would make it cold again.

## Loop 3 — fill speed: founder decision open (REQ-20261111-04)

- [ ] REQ-20261111-04 · **founder decides:** bundle torch + `big-lama.pt` for MPS fill (4.6× faster on a
  real span, about +0.8 GB) or stay CPU. Numbers: `docs/duck/gpu-fill-bench.md`
- [ ] REQ-20261111-04 · if yes: PyInstaller build with torch, measure the real bundle size and launch time
- [ ] REQ-20261111-04 · if yes: `render_edit` passes the chosen device to `prepare_span`; CPU fallback stays
- [ ] REQ-20261111-04 · if yes: Settings row shows the real device and the reason when GPU is unavailable
- [ ] PLAN · repeat the MPS real-span run 3 times and on a 60 s span: variance, heat, memory

## Loop 4 — one full render of the review project

- [ ] **Render once and review**, with the loop 1 estimate on screen first. Check 0, 2, 10, 90, 157 s
  and OCR a 2 s scan: no burned-in text, no outline residue, no frozen patch at a cut.
- [ ] PLAN · record real wall-clock beside the estimate in the report row

## Loop 5 — a better fill for moving footage

- [ ] PLAN · researcher: licence table for video-inpaint candidates (STTN weights, ProPainter, others),
  clause quoted, commercial use yes/no. Nothing enters the build without it.
- [ ] **Fill model for moving footage.** LaMa is per-frame and cannot rebuild a plate it never saw;
  33 of 41 layers in the review project are `moving`. Bench the allowed candidates on those spans.
- [ ] **Fill confidence per line.** `quality` is binary from the mean motion; motion 11 and 31 are
  treated the same. Consider a third level or a score.

## Loop 6 — make the code match the rules

- [ ] PLAN · `script.rewrite`: remove the silent Ollama fallback and the `qwen3:4b` name; Apple
  Intelligence, else basic cleanup, stated in the UI
- [ ] PLAN · delete the unused `online_enabled` / `online_endpoint` settings
- [ ] REQ-20261111-02 · cloud STT paths (`groq`, `deepgram`, `openrouter`): code stays for after v1; add
  a test that none is reachable in a v1 build
- [ ] PLAN · render queue lists "Done" jobs whose file is gone (two on the review project after the
  disk cleanup); Play should not be offered for a missing file
- [ ] **Model pack manager polish.** LaMa, Whisper and Kokoro are wired. No in-app "verify all" or
  storage cleanup yet.

## Loop 7 — local model slots (REQ-20261111-03)

v1 is completely local: the user plugs in local models; no keys. Design: `docs/duck/BYOK-PLAN.md`.

- [ ] REQ-20261111-03 · `providers.py` registry + `Provider` interface, no behaviour change
- [ ] REQ-20261111-03 · transcription local slot: choose an MLX Whisper folder, validate, copy
- [ ] REQ-20261111-03 · rewrite local slot: base URL on this Mac (localhost only), `/v1/models` check
- [ ] REQ-20261111-03 · voice local slot: custom ONNX voice folder
- [ ] REQ-20261111-03 · fill local slot: custom ONNX inpaint model
- [x] REQ-20261111-02 · remove the `translation-nllb` pack and every download affordance
- [x] REQ-20261111-02 · custom CTranslate2 folder: choose, copy into app data, validate model.bin/config.json/sentencepiece
- [x] REQ-20261111-02 · Settings copy names no model and offers no link
- [x] REQ-20261111-03 · five roles in `.claude/agents/` and in `AGENTS.md`
- [x] REQ-20261111-03 · per-step BYOM/BYOK matrix in `AGENTS.md` and `docs/duck/BYOK-PLAN.md`

## Loop 8 — $29 build readiness (REQ-20261111-02)

- [ ] REQ-20261111-02 · SHA-256 per pack file; `packs.py` currently accepts ≥98% of the expected size
- [ ] REQ-20261111-02 · LGPL written source offer for the bundled ffmpeg, beside the licence text
- [ ] REQ-20261111-02 · shrink the Whisper pack or make it per-language (1.61 GB today; required for `vi`)
- [ ] **AI fill repair / reinstall path.** LaMa ships inside the bundle, so the honest fix is a
  "reinstall DuckSuite" instruction beside the existing path, problem text and Reveal button.
- [ ] **Manual microphone test** on a clean Mac. Recording compiles, never tested by hand.
- [ ] **Import failure copy.** Errors are technical ("ffmpeg frame read failed"). Rewrite for a creator.
- [x] REQ-20261111-02 · decide purchase shape: $29 paid app, no StoreKit, restore by Apple ID
- [x] REQ-20261111-02 · decide platform floor: macOS 26.0, Apple silicon

## Loop 9 — layout balance (from `docs/teams/uiux-balance-01.md`)

- [ ] **Render screen restructure.** Two columns: Settings (320 px) plus Start render on the left, queue
  full width on the right, finished renders as cards instead of dense rows. Today the page ends at 60%
  height. The loop 1 estimate lives in the left column.
- [ ] **Edit inspector.** Add `5 of 9 layers` and a bottom fade so the clipped row reads as "more
  below". Today the fifth row is cut with no hint.
- [ ] **Timeline empty lanes.** Collapse a lane with no cues to one 32 px `+` row. Three of five lanes
  are empty on a silent project and read as missing data.
- [ ] **Portrait Preview width.** The player is framed now but still leaves ~300 px paper each side.
  Proposal: scene strip in a 300 px column beside the player.
- [ ] **Verify a 9:16 project at 1440×900 and 1280×800.** The preview stage was changed to hug portrait
  media; the two review sizes were not re-measured after that change.

## Later

- [ ] **Cold render cost, beyond the estimate.** Warm the cache in the background after Clean all, or
  cap fill work by keyframe plan. Revisit with the loop 3 numbers.
- [ ] **First-frame read cost.** `pipeline._first_still` adds one ffmpeg seek per Check. Cheap today;
  measure on a 10-minute source.
- [ ] PLAN · title blur runs 0.0–0.317 s for a 0.066 s title; about 7 frames carry a soft patch with
  no text under it. Consider an exact end for a first-frame-only reading.
- [ ] **Short flashes after the first frame.** Only the first frame gets an exact read; a title under
  250 ms at a later cut can still fall between 4 fps samples. Measure before fixing.
- [ ] **Timeline split and reorder.** Trim works; split, reorder and remove-silence do not.
- [ ] **Aspect switching / auto-frame.** Source aspect only. Deliberate v1 cut.
- [ ] **Every loop writes `docs/teams/<loop>/review.md`** (REQ-20261111-03; standing rule, starts with loop 1).

## Paused by decision

- [ ] **App Store gate.** Signing identity, team, store URLs, review contact, screenshot rights, nested
  code signing. Blocked before; work intentionally stopped until the product is good.
- [ ] **Cloud render plans** ($5 / $20). Founder decision of 2026-11-06; nothing in the build uploads.
- [ ] **User keys (BYOK), after v1.** Planned in `docs/duck/BYOK-PLAN.md`, not built in v1:
  - [ ] REQ-20261111-03 · Keychain store + redaction; never `settings.json`, logs or error strings
  - [ ] REQ-20261111-03 · Connections UI with per-task consent; off until ticked
  - [ ] REQ-20261111-02 · STT keys: OpenAI, Groq, Deepgram, OpenRouter
  - [ ] REQ-20261111-02 · rewrite keys: OpenAI, Anthropic, OpenRouter
  - [ ] REQ-20261111-02 · voice keys: ElevenLabs, OpenAI TTS
  - [ ] REQ-20261111-04 · fill endpoint, last: user URL, consent that frames leave the Mac, never default
- [x] **Translation licence.** Resolved by shipping no weights: the user supplies a CTranslate2 folder.
- [ ] **Merge `main`.** No common ancestor; not a merge target.

## Done

### 11 Nov — loop 3, fill speed measured (`docs/teams/loop-03-fill-speed/review.md`)
- [x] REQ-20261111-04 · `bench_fill.py --device cpu|coreml|gpu --model`
- [x] REQ-20261111-04 · CPU 2.09 s, CoreML 67.88 s, MPS 0.74 s per fill on the same 10 frames; same PSNR/SSIM
- [x] REQ-20261111-04 · real span, clip 1 cold: MPS 50 s; CPU 189–864 s for the identical job
- [x] REQ-20261111-04 · CoreML EP closed (32× slower than CPU)
- [x] REQ-20261111-04 · cache key already separates devices (`method_stamp`); no key change needed
- [x] PLAN · flat 3 fills/s doubles the runs (121 vs 61); the scan plan stays
- [x] PLAN · estimate fixed: stored rate is the middle of the last three fills; project ≈ 28 min of fill, not 2 h 45 min

### 11 Nov — loop 2, title proof on a short span (`docs/teams/loop-02-title-short-span/review.md`)
- [x] Re-Check: `title` tracklet at 0 s, y 0.321; 42 tracklets
- [x] Clean all: title layer `blur`; fill 40 · blur 2 · off 0; no `auto: false` layer existed
- [x] Rendered clip 1 (0–4.75 s) and OCR'd all 142 frames
- [x] Bug found and fixed: 3 frames leaked subtitles at line edges; ranges now reach a full step back and `SAMPLE_SLACK` forward
- [x] Flash limit 0.5 → 0.6 s so a line read once still gets Blur
- [x] Re-render: 0 of 142 frames with text

### 11 Nov — loop 1, show the render cost (`docs/teams/loop-01-render-cost/review.md`)
- [x] PLAN · `GET …/render/estimate` returns the fill estimate for an edit; `textfill.estimate_summary` has a caller
- [x] PLAN · Render screen shows fill seconds, layer count and estimated time above Start render
- [x] PLAN · Clean all dialog shows the estimate; the toast after Clean all carries the new one
- [x] PLAN · estimate says "measured on this Mac" or "first guess" from `fill_rates.json`
- [x] PLAN · warning when free disk is under `SAVED_MIN_FREE` (10 GiB)
- [x] PLAN · 5 tests: measured rate, seed rate, no fill layers, low disk, route
- [x] Review project reads: up to 2 h 45 min for 60 s of fill in 40 layers, measured rate

### 11 Nov — final documentation pass
- [x] REQ-20261111-05 · `PLAN.md`: one build order, nine loops, measured state, document map
- [x] REQ-20261111-05 · `PRODUCT.md` matches the build: shipped / planned / deferred, known limits
- [x] REQ-20261111-05 · `TODO.md` reordered into the loops; duplicate BYOK items merged
- [x] REQ-20261111-05 · `ROADMAP.md` marked historical; stale NLLB lines corrected

### 11 Nov — team and model plugins
- [x] REQ-20261111-03 · five roles: product owner, creator, engineer, tester, researcher
- [x] REQ-20261111-03 · Claude Code subagents in `.claude/agents/`
- [x] REQ-20261111-03 · BYOM/BYOK matrix for every model-backed step
- [x] REQ-20261111-03 · slot contract: validate, copy into app data, never name or download a model

### 11 Nov — disk cleanup
- [x] deleted the local NLLB pack (601 MB); only Whisper and Kokoro remain
- [x] deleted the two pre-fix renders and the 25 s slice (331 MB); next render is the first with the title fix

### 11 Nov — bring your own model
- [x] REQ-20261111-02 · NLLB pack, download button and model names removed
- [x] REQ-20261111-02 · native folder picker copies any CTranslate2 folder into app data and validates it
- [x] REQ-20261111-02 · `GET /api/translation/model` reports ready/missing; legacy `nllb` setting migrates
- [x] REQ-20261111-02 · BYOK plan at `docs/duck/BYOK-PLAN.md`
- [x] REQ-20261111-02 · $29 restore and macOS 26 floor researched from the installed SDK

### 11 Nov — request intake
- [x] REQ-20261111-01 · classify new request vs revision; log new ones in `MEMORY.md`
- [x] REQ-20261111-01 · plan with request ids in `TODO.md`; close the loop in the same commit

### 11 Nov — fill quality loop
- [x] Ground-truth benchmark (`scripts/bench_fill.py`): paint a caption on text-free frames, score PSNR/SSIM.
- [x] Fixed the benchmark to score every variant over one region, so a too-small hole cannot win by hiding its outline.
- [x] Tighter fill hole: pad 0.06 → 0.04, outline 0.18 → 0.10. +1.1 dB PSNR, +0.02 SSIM, 17% lower error, same time. Blur keeps the wide pad.
- [x] Cache `VERSION` 11 → 12; test asserts fill hole is tighter than blur hole and still covers the box.
- [x] Second project (1504×1120) confirms +0.8 dB.
- [x] Real-span re-fill at 90 s and 157 s: no outline residue.

### 11 Nov — layout balance
- [x] Scene titles no longer paint over thumbnails (66 px image in a 54 px column).
- [x] Portrait Preview is a dark player that hugs the frame, at `72vh`.
- [x] Transcript placeholder hidden when the frame has no cues.
- [x] Welcome panels stretch to the window instead of ending at 640 px.

### 10–11 Nov — bad render review
- [x] Check reads the true first frame; a 66 ms title at 0 s is now detected end to end.
- [x] Top display type classifies as `title`, not a word-pop caption.
- [x] Per-layer `quality`/`motion`, "moves" badge, inspector note, Render readiness warning.
- [x] Flash under 0.5 s defaults to Blur; `auto` flag keeps user choices across Clean all.
- [x] Clean all confirms first and reports fill/blur/off counts.
- [x] Render queue scoped to the open project with an All projects toggle.
- [x] One import action on Welcome; toolbar Import hidden there.
- [x] Disabled Fill/Blur/Off styling; real AI fill problem text.
- [x] Rendered output reviewed: captions gone at 2 s, 10 s, 90 s; 0 s title pending re-Check.

### 10 Nov — earlier loops
- [x] Local model packs; HF cache removed (1.5 GB freed); Kokoro ONNX wired.
- [x] Finder drag/drop import via a native drop target.
- [x] NLLB-200 600M int8 optional pack, Apple → NLLB fallback, custom CTranslate2 path.
- [x] Proofs optional; render unlocked immediately; one proof on Preview.
- [x] Story inheritance, media beats, reorder/remove; per-row audio trim, fades, mute/solo.
- [x] Script/Caption split, transcript move, media inspector, truthful states.

### 9 Nov — shell and flow
- [x] Custom 48 px toolbar with a hidden native title bar and window drag.
- [x] Player no longer rebuilt on Check progress; Check can run while the player keeps playing.
- [x] Three-screen revamp: Edit desk, Clean focus, Preview/Render.
- [x] Progress report created, then extended five times without deleting old entries.
