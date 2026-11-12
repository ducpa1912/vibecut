# PLAN — DuckSuite build order

Current plan only. Closed loops 1–4 and the ink-check loop are archived in `old_plan.md` (agents do
not read it). `PRODUCT.md` says what the product is, `TODO.md` holds the open checkboxes,
`MEMORY.md` the decisions in force, `AGENTS.md` the working contract.

## Where the build stands (measured 2026-11-12)

| Fact | Value |
|---|---|
| Branch / tests | `ducksuite`, 178 pass, `node --check` clean |
| Bundle | ≈ 981 MB (torch 565, GPU LaMa 196, sidecar 136, ffmpeg 41; no ONNX) |
| Dev Mac | M1, 8 GB RAM, macOS 26.7.2 |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips, edit `ed_38a4c36a3aae` |
| Clean layers | 42 fill · 0 blur; 32 `moving`; one founder layer `auto: false` |
| Fill | `textfill.VERSION` 17, GPU MPS default, CPU as an optional pack; hole = letter strokes |
| Leftover-text check | post-render, per letter against the source, 40 of 42 lines, 68–81 s quiet, 170–190 s under load |
| Last render | 0 leftover in 2,964 frame checks, 2 lines not checked; cold 620–847 s; estimate 6.7 % low, shown as a range |

## What is still wrong

1. **Fill is weak on moving footage** and that is most of the footage: LaMa fills one frame at a
   time and cannot rebuild a background it never saw. This is the product's main feature.
2. **The leftover check sees only lines that have a layer.** Text Check never found is not judged,
   and a line under 5 frames is reported as not checked. Cold render cost rose to 620–847 s (418 s before); the
   estimate now plans the fill's own runs and shows a range.
3. **Layout balance** is unfinished on Render, the inspector and the timeline.

## Rule for ordering

Every change to fill output bumps `textfill.VERSION` and makes the next full render cold. Finish
fill-changing decisions first, then pay for one render. Do not run a full render to prove a small
fix; render the span that shows it.

One loop = PO brief → engineer + tester → creator → PO sign-off → one commit with `MEMORY.md`,
`TODO.md`, a report row and `docs/teams/<loop>/review.md`.

## Loops

Brief loops 7 (ink check), 8 (moving fill), 9 (rules) and 10 (layout balance) are **closed**; the
PLAN loops still open are 7 (local model slots) and 8 ($29 readiness). Next: the founder tests by hand with
`docs/teams/loop-10-layout-balance/founder-test.md`.

### Loops 11–20 — founder UX and workflow (opened 2026-11-12)

| Loop | Work | Request | State |
|---|---|---|---|
| 11 | Proofs: blur not fill, opt-in, three steps, Re-clean → Clean Focus | REQ-20261112-01 | **closed 2026-11-12** |
| 12 | Transcript opacity + never blocks player time/volume | REQ-20261112-02 | **closed 2026-11-12** |
| 13 | Timeline zoom for beats and scenes | REQ-20261112-03 | building |
| 14 | Cut Focus phase 1: crop, aspect, resize, look presets moved | REQ-20261112-04 | queued |
| 15 | Safe zones on Preview, on the Cut output frame | REQ-20261112-05 | queued |
| 16 | Preview sequence: all scenes, or the story order | REQ-20261112-06 | queued |
| 17 | Story v1: whole-context thesis and non-contiguous beats on FoundationModels | REQ-20261112-07 | queued |
| 18 | Cut phase 2: grading sliders | REQ-20261112-04 | roadmap |
| 19 | Cut phase 3: enhance (lanczos, optional CoreML pack) | REQ-20261112-04 | roadmap |
| 20 | Optional local VLM scene captions for story | REQ-20261112-07 | roadmap |

Cut is one visual-treatment block, not a scene cut: output size, aspect, crop, resize, look,
enhance. Rules: crop normalised to the source frame; clean boxes stay source-normalised; fill runs
before crop/scale, so `textfill.VERSION` stays 17 and the fill cache stays valid.

Research, 2026-11-12: on macOS 26 the on-device model is text-only with 4,096 tokens; OS 27 adds
image input, not video; the 32K model is Private Cloud Compute, out of scope. Story must use the
transcript and chunk. Local video VLMs exist (Qwen3-VL on MLX) but are multi-GB and minutes per
clip, so they are an optional pack, never a default. Upscale: ffmpeg lanczos invents no detail;
Real-ESRGAN via CoreML is the plug-and-play candidate after a licence check and an M1/8 GB
benchmark.

### Loops 5 and 6 — closed 2026-11-12

- Loop 5 (moving fill): `docs/teams/loop-08-moving-fill/review.md`. No licensed engine; a user fill
  slot ships; bench in the review.
- Loop 6 (rules): `docs/teams/loop-09-rules/review.md`. Rewrite order fixed, dead settings removed,
  no cloud call with every key set, no model name in the UI, the Whisper loop cue dropped.

### Loop 7 — local model slots (`docs/duck/BYOK-PLAN.md`)

v1 is completely local: the user plugs in local models, no keys. Order: `providers.py` registry with
no behaviour change → Whisper folder, LLM base URL on this Mac, ONNX voice, ONNX fill. User keys stay
planned in `BYOK-PLAN.md` and are **not v1**.

### Loop 8 — $29 build readiness

SHA-256 per pack file, LGPL written source offer for ffmpeg, a smaller or per-language Whisper pack,
AI fill repair instruction, manual microphone test, creator-readable import errors.

### Loop 9 — layout balance (`docs/teams/uiux-balance-01.md`) — **closed 2026-11-12**

Review: `docs/teams/loop-10-layout-balance/review.md`. 9/9 acceptance; six screens measured at
1440×900 and 1280×800 (bottoms 87.3–100 %, 0 layout overlaps, no horizontal scroll, 0 clipped
buttons, portrait stage 70 % / 64.6 %), 16:9 fixture measured the same. Nothing left open here.

## Not in this plan

- App Store, signing, TestFlight, StoreKit: paused by decision.
- Cloud render plans ($5 / $20), render broker: deferred; nothing in the build uploads.
- User keys: planned, not v1.
- DuckClean, DuckClassic, DuckStudio: other lanes.
- Timeline split/reorder/remove-silence, aspect switching, auto-frame: after loop 9.

## Document map

| File | Role | Rule |
|---|---|---|
| `AGENTS.md` | contract, team, invariants | read first |
| `MEMORY.md` | direction and decisions in force | current only, < 80 lines |
| `TODO.md` | open checkboxes | current only |
| `PLAN.md` | build order for open loops | this file |
| `PRODUCT.md` | what DuckSuite is, shipped vs planned | current only |
| `old_memory.md`, `old_todo.md`, `old_plan.md` | frozen history | **agents do not read** |
| `docs/teams/*/review.md`, `BRIEF.md` | loop evidence | read the current loop's brief/review only |
| `docs/reports/*.html` | the human's progress record | **agents append, never read into context** |
| `docs/duck/BYOK-PLAN.md`, `GPU-FILL-PLAN.md` | design for loops 5–7 | active |
| `ROADMAP.md`, `docs/handoff/*` | 7 Nov plan | historical |
