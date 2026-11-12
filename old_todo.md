# ARCHIVE — TODO history, done lists and finished loops

Frozen copy of `TODO.md` as it stood on 2026-11-12, before the working documents were cut
back to current direction and open work. **Agents must not read this file.** It exists so
nothing is lost; the human can search it if needed.

---

# TODO — DuckSuite

Status as of 2026-11-11 (REQ-20261111-05). The order below is the build order in `PLAN.md`; work one
loop at a time, top to bottom. Done items stay listed so nothing is repeated by accident.

Items that came from a request carry its id (`REQ-YYYYMMDD-NN`), matching `MEMORY.md`. Items from a
review carry the review file. Items marked `PLAN` came from the 11 Nov code and data review.

**Loop 4 is done.** Fills are warm for the review project at `textfill.VERSION` 13; a full render
takes about a minute when only a few spans change, minutes when cold. Do not run one to prove a
small fix; render the span that shows it.

## Loop 3 — fill speed: GPU default, CPU as a pack (REQ-20261111-04/07)

- [x] REQ-20261111-04 · founder decision: bundle torch + `big-lama.pt`; GPU is the default
- [x] REQ-20261111-04 · PyInstaller build with torch; bundle measured at 981 MB
- [x] REQ-20261111-04 · `render_edit`/`render_frame` pass the device; `estimate_edit` follows it
- [x] REQ-20261111-07 · CPU is an optional 198 MB pack; Render and Clean Focus disable it until installed
- [x] REQ-20261111-07 · bundle ships no ONNX and no Kokoro weights; onnxruntime kept for both packs
- [ ] REQ-20261111-07 · real CPU-pack download and CPU fill on a clean machine
- [ ] PLAN · repeat the MPS real-span run 3 times and on a 60 s span: variance, heat, memory

### Loop 4 internal loop A — edges and the leak tool
- [x] `scripts/ocr_render.py` OCRs every frame and matches text to Check tracklets; scene text apart
- [x] range ends refined at source frame rate (`detect.refine_tracklet_edges`), never widened
- [x] mask frame membership uses the frame start, not its centre; `textfill.VERSION` 13
- [x] tests: last frame inside a range gets a hole; 108 pass
- [x] re-Check and re-render: 0 leaks in 4,800 frames (final render 19:15)

## Loop 4 — one full render of the review project — **done 2026-11-11** (`docs/teams/loop-06-full-render/review.md`)

- [x] **Render once and review**, with the loop 1 estimate on screen first. Check 0, 2, 10, 90, 157 s
  and OCR a 2 s scan: no burned-in text, no outline residue, no frozen patch at a cut.
- [x] PLAN · record real wall-clock beside the estimate: 76 s vs 333.8 s

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

## Loop 7 — ink check: catch leftover text without OCR (REQ-20261111-11)

Brief: `docs/teams/loop-07-ink-check/BRIEF.md`. Review: `docs/teams/loop-07-ink-check/review.md`.

- [x] REQ-20261111-11 · `duckcore/ink.py`: ink build/score/grow/box, onset scan; 5 tests
- [x] REQ-20261111-11 · detection edges from ink, OCR fallback; first hot frame reached back one frame
- [x] REQ-20261111-11 · `duckcore/inkcheck.py`: post-render score, hit list, flicker per line
- [x] REQ-20261111-11 · ink box is the fill hole on every frame; `span_key` and `VERSION` 15
- [x] REQ-20261111-11 · queue stores checked frames, hits, times, flicker; Render screen shows them
- [x] REQ-20261111-11 · Check also reads frame 0, the frame after each cut, and onset moments (62 extra)
- [x] REQ-20261111-11 · one refill retry on a hit, then keep the render and show the times
- [x] REQ-20261111-11 · fill plan aligned to the decoded frame grid (ffmpeg lands on the next frame)
- [x] REQ-20261111-11 · estimate carries the check cost; cold path takes fill + check + encode
- [x] REQ-20261111-11 · tests: ink, post-render check on a real one-leak video, extra Check times
- [ ] REQ-20261111-11 · D8 per-frame fill where the picture changes fast: not shipped, no number
- [ ] REQ-20261111-11 · D9 `follow_motion` for moving lines: not shipped, not measured

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

### 11 Nov — refactor pass (REQ-20261111-10)
- [x] `duckcore/textmatch.py`: one comparison rule for clustering, edge refinement and the leak tool
- [x] `refine_tracklet_edges`: pure `edge_end_from_hits`, dead start branch removed, logging not prints
- [x] `mask.frame_keys` window end matches `frame_rects` (frame start, exclusive end)
- [x] Queue: a live worker keeps its job on restart; claim sets `worker_pid`; one estimate probe
- [x] `RenderQueue._row` is `dict(row)`; settings snapshot and estimate read the device once
- [x] Leak tool probes duration and frame rate instead of assuming 30 fps
- [x] 117 tests pass; JS clean

### 11 Nov — user-set layers are findable (`REQ-20261111-08`)
- [x] Clean Focus `All` / `Yours N` filter, scene and strip badges
- [x] `YOURS` badge on layer rows in Clean and Edit
- [x] `plan_summary.mine`; Clean all toast says how many settings were kept
- [x] Filtered rows keep the real scene index; selecting one opens the right scene

### 11 Nov — GPU default, CPU pack (`docs/teams/loop-05-gpu-default/review.md`)
- [x] REQ-20261111-07 · GPU shipped as the default; CPU optional download, SHA-256 verified
- [x] REQ-20261111-07 · model seeding into `models/fill`; packs and the bundle share one folder
- [x] REQ-20261111-07 · CPU/GPU control in Render and Clean Focus
- [x] REQ-20261111-07 · final bundle GPU render: 1 s clip in 9.4 s, OCR clean
- [x] REQ-20261111-07 · local cleanup ≈ 1.2 GB (Kokoro, ONNX, STTN/MI-GAN, CPU fills)
- [x] REQ-20261111-07 · 101 tests pass

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

## Loop 8 closed items (2026-11-12)

- [x] Licence table for video-inpaint candidates, clause and URL per row: none allowed.
- [x] Bench the allowed candidates: none, so LaMa alone on 3 moving spans, 21 frames.
- [x] Custom fill slot (no licence needed) for a user ONNX or TorchScript model.
- [x] Crossings measured into the estimate (35 on the review project, +11.7 s).

## Loop 9 closed items (2026-11-12)

## Loop 6 — make the code match the rules

- [ ] `script.rewrite`: remove the silent Ollama fallback and the `qwen3:4b` name; Apple
  Intelligence, else basic cleanup, stated in the UI.
- [ ] Delete the unused `online_enabled` / `online_endpoint` settings.
- [ ] REQ-20261111-02 · cloud STT paths (`groq`, `deepgram`, `openrouter`): code stays for after v1;
  add a test that none is reachable in a v1 build.
- [ ] Render queue lists "Done" jobs whose file is gone; Play must not be offered for a missing file.
- [ ] Model pack manager polish: in-app "verify all" and storage cleanup.


- [x] `script.rewrite`: no local-model fallback, no model name; Apple Intelligence, else basic cleanup.
- [x] `online_enabled` / `online_endpoint` removed; an old file still loads.
- [x] No cloud STT reachable in a v1 build; guard test with every key set.
- [x] No user-facing string names a model (grep empty).
- [x] Whisper loop cue dropped by a tested rule (repeated line, ≥ 8 s, ≥ 1.2 s a word).

- [x] Estimate from the fill's own run plan (loop 8 revision 1): `dry_units` walks the same
  `fill_frames_lama`; 790.4 s against 847.2 s real (−6.7 %), worst span 1.75x.
- [x] A custom model no longer teaches the LaMa rate; estimate and render share `engine_choice`.

## Loop 10 closed items (2026-11-12)

## Loop 10 — layout balance (`docs/teams/uiux-balance-01.md`) — closed 2026-11-12

- [x] Render screen restructure: Settings (320 px) + Start render left, queue full width right,
  finished renders as cards. The estimate lives in the left column.
- [x] Edit inspector: `5 of 9 layers` plus a bottom fade so the clipped row reads as "more below".
- [x] Timeline empty lanes: collapse a lane with no cues to one 32 px `+` row.
- [x] Portrait Preview width: scene strip in a 300 px column beside the player.
- [x] Verify a 9:16 project at 1440×900 and 1280×800.



## Loop 11 — proofs (closed 2026-11-12)

- [x] REQ-20261112-01 · loop 11: proofs are a blurred frame, clicked by the user, never auto
- [x] REQ-20261112-01 · loop 11: Detect / Compare / Review steps with a step label
- [x] REQ-20261112-01 · loop 11: Re-clean this scene opens Clean Focus on that scene, with box edit, brush and re-apply

## Loop 12 — transcript (closed 2026-11-12)

- [x] REQ-20261112-02 · loop 12: transcript opacity slider, 30–100 %, persisted
- [x] REQ-20261112-02 · loop 12: transcript never covers the player time, volume, scrub or full screen

## Loop 13 — timeline zoom (closed 2026-11-12)

- [x] REQ-20261112-03 · loop 13: timeline zoom fit–16x, adaptive ruler, internal scroll

## Loop 14 — Cut Focus phase 1 (closed 2026-11-12)

- [x] REQ-20261112-04 · loop 14: Cut tab and Cut Focus shell with Output (crop, aspect, resize) and Look
- [x] REQ-20261112-04 · loop 14: move Warm / Cool / B&W / Vivid out of SFX into Cut
- [x] REQ-20261112-04 · loop 18: grading sliders (exposure, contrast, saturation, temperature)
- [x] REQ-20261112-04 · loop 19: enhance 360p→1080p, lanczos label, optional CoreML pack after licence and benchmark
