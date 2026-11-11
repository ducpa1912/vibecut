# TODO — DuckSuite

Status as of 2026-11-11, after `7a40d7d`. Ordered by what blocks a good render, then quality, then
polish. Done items stay listed so nothing is repeated by accident.

Items that came from a new request carry its id (`REQ-YYYYMMDD-NN`), matching `MEMORY.md`. Items from
a review carry the review file instead.

## P0 — blocks a clean render on the review project

- [ ] **Re-run Check on `prj_e95348a97316`.** The project's `check.json` predates the first-frame fix,
  so the 66 ms title at `0 s` has no clean layer and still shows in every render. Check is additive and
  keeps the layer choices made by the user.
- [ ] **Clean all after that Check.** The title layer should appear as `title`, `0.0–0.25 s`, quality
  `moving`; it will default to Blur because it is shorter than 0.5 s.
- [ ] **Render once and review.** Fills are cold after `textfill.VERSION` 12. A 160 s render can take
  hours. Budget for it, then check 0 s, 2 s, 10 s, 90 s, 157 s, and OCR a 2 s scan for leftovers.

## P1 — quality and honesty

- [ ] **Fill model for moving footage.** LaMa is per-frame and cannot rebuild a plate it never saw.
  The tighter hole bought +1.1 dB; the next real step is a different model, not another pad tweak.
  Candidates: STTN with better weights, ProPainter, a video diffusion inpaint, or an external render
  service. Needs a licence decision before it ships.
- [ ] **AI fill repair / reinstall path.** Settings shows the model path, problem text and a Reveal
  button. There is still no in-app repair because LaMa ships inside the bundle; the honest fix is a
  "reinstall DuckSuite" instruction, or a downloadable pack that can be re-fetched.
- [ ] **Verify a 9:16 project at 1440×900 and 1280×800.** The preview stage was changed to hug portrait
  media; the two review sizes were not re-measured after that change.
- [ ] **Fill confidence per line.** `quality` is binary (steady/moving) from the mean motion. A line
  with motion 11 and one with 31 are treated the same. Consider a third level or a score.

## P1 — layout balance (from `docs/teams/uiux-balance-01.md`)

- [ ] **Render screen restructure.** Two columns: Settings (320 px) plus Start render on the left, queue
  full width on the right, finished renders as cards instead of dense rows. Today the page ends at 60%
  height.
- [ ] **Edit inspector.** Add `5 of 9 layers` and a bottom fade so the clipped row reads as "more
  below". Today the fifth row is cut with no hint.
- [ ] **Timeline empty lanes.** Collapse a lane with no cues to one 32 px `+` row. Three of five lanes
  are empty on a silent project and read as missing data.
- [ ] **Portrait Preview width.** The player is framed now but still leaves ~300 px paper each side.
  Proposal: scene strip in a 300 px column beside the player.

## P1 — bring your own model and key (REQ-20261111-02)

- [x] REQ-20261111-02 · remove the `translation-nllb` pack and every download affordance
- [x] REQ-20261111-02 · custom CTranslate2 folder: choose, copy into app data, validate model.bin/config.json/sentencepiece
- [x] REQ-20261111-02 · Settings copy names no model and offers no link
- [ ] REQ-20261111-02 · BYOK store: macOS Keychain, never settings.json; redact in logs and errors
- [ ] REQ-20261111-02 · STT keys: OpenAI, Groq, Deepgram, OpenRouter
- [ ] REQ-20261111-02 · rewrite keys: OpenAI, Anthropic, OpenRouter, local Ollama
- [ ] REQ-20261111-02 · voice keys: ElevenLabs, OpenAI TTS
- [ ] REQ-20261111-02 · fill endpoints: user-supplied HTTP service, no key shipped
- [ ] REQ-20261111-02 · per-task switch and privacy banner before any upload

## P2 — performance and cost

- [ ] **Cold render cost.** `VERSION` 12 invalidates every stored fill. A 25 s slice ran 42 min and was
  stopped. Options: warm the cache in the background after Clean all, show a time estimate per layer,
  or cap fill work by keyframe plan.
- [ ] **Fill planner budget.** `fill_plan.keys` reaches 6/s. On dense captions that is the whole cost.
  Check whether 3/s looks the same on real footage.
- [ ] **First-frame read cost.** `pipeline._first_still` adds one ffmpeg seek per Check. Cheap today;
  measure on a 10-minute source.

## P2 — product

- [ ] **Timeline split and reorder.** Trim works; split, reorder and remove-silence do not.
- [ ] **Aspect switching / auto-frame.** Source aspect only. Deliberate v1 cut.
- [ ] **Manual microphone test** on a clean Mac. Recording compiles, never tested by hand.
- [ ] **Model pack manager polish.** LaMa, Whisper, Kokoro, NLLB are wired; Qwen and Demucs entries are
  removed. No in-app "verify all" or storage cleanup yet.
- [ ] **Import failure copy.** Errors are technical ("ffmpeg frame read failed"). Rewrite for a creator.

## Paused by decision

- [ ] **App Store gate.** Signing identity, team, store URLs, review contact, screenshot rights, nested
  code signing. Blocked before; work intentionally stopped until the product is good.
- [ ] **NLLB commercial licence.** CC-BY-NC-4.0. Keep it optional, or replace it before a paid build.
- [ ] **Merge `main`.** No common ancestor; not a merge target.

## Done

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
