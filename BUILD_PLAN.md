# VibeCut — Detect / Dissect / Compose Build Plan

**Status:** New product direction for founder approval.  
**Date:** 2026-10-26.  
**Supersedes:** the Flow 1/Flow 2 classification in `round_4.md` and `ROADMAP_V2.md`. Paid 1.0 scope is unchanged.  
**Baseline:** `main` at `f059086`; 870 tests pass.

---

## 1. The correction

The previous review treated Flow 2 as “retention, not a paid wedge” and Flow 1 as a deterministic add-on. That is wrong for the product we are building.

**VibeCut is one sophisticated creator workstation:**

```text
DETECT → DISSECT → COMPOSE → FINISH
```

### Detect

Before cutting, inspect the source and decide what workflow it needs:

- baked-in captions?
- old titles, handles, logos, lower thirds?
- clean video with no text?
- speech, music, silence?
- faces, safe zones, scene quality?
- rights/ownership?
- recommended path: Flow 1, Flow 2, or Both.

### Dissect

The existing SmartCut and scene editor:

- find 3–6 stories;
- show hook, payoff, evidence;
- edit/reorder/exclude sentences;
- scene trim and timeline;
- voice and audio controls.

### Compose

Two paths into the same editor:

- **Flow 1 — Clean old captions:** detect, mask, crop/cover/blur, clean master, quality report; then continue to Compose.
- **Flow 2 — New overlay:** hook, captions, visual SFX, music generation, filter editor, voice; built on the current SmartCut/Caption Studio UI/UX.
- **Both:** clean the selected story, then add new overlays.

### Finish

Render, packet, versions, review links, exports.

Detect is not a separate product. It is the front door. Flow 1 and Flow 2 are not separate products. They are two paths through the same workstation.

---

## 2. What Flow 2 actually is

Flow 2 is **the current UI/UX, extended** — not a new planner or a retention sidecar.

The existing screens stay:

- Clip Set / story cards
- Smart Cut / scene editor
- Caption Studio
- Audio: voice, music, mixer
- Packet
- Preflight
- Artifacts & shares

Add to the same editor:

### 2.1 Caption and text overlays

- hook cards;
- title cards;
- lower thirds;
- CTA and end cards;
- emphasis words;
- safe-zone preview for 9:16 and 4:5;
- z-order and collision warnings;
- one overlay plan shared by preview, burn, SRT, and packet.

### 2.2 Visual SFX

Not stock B-roll. Local, deterministic graphics and motion:

| Type | Examples |
|---|---|
| Motion | punch-in, pop, slide, shake, snap zoom |
| Graphics | arrow, circle, underline, progress bar, callout, emoji/sticker |
| Text effects | emphasis, highlight, type-on, word pop |
| Timing | start/end, duration, easing, z-order |
| Safety | face overlap, caption collision, platform safe zone |

### 2.3 Music generation

Use the current audio layer:

- generated bed per story;
- local or optional provider route;
- beat sync;
- duck under voice;
- license/provenance metadata;
- regenerate, preview, lock, replace;
- no mandatory cloud.

### 2.4 Filter editor

- presets/LUTs;
- exposure, contrast, saturation, temperature;
- vignette, grain, sharpness;
- per-story or per-scene;
- before/after preview;
- filter hash in artifact and packet.

### 2.5 Voice

Current voice-over/dub/TTS remains. Flow 2 should not create a second voice system.

### 2.6 Packet

`packet.json` gains:

```text
overlays.json
sfx.json
filters.json
music_plan.json
caption_track
compose_version
```

The packet remains one handoff folder, not a cloud project.

---

## 3. What Flow 1 actually is

Flow 1 is a cleanup pre-pass inside the same workstation.

```text
detect old text
→ review text tracks / masks
→ crop / cover / blur
→ clean master
→ dissect stories
→ compose new captions/SFX/music/filter
→ finish
```

### 3.1 Detect old text

- OCR boxes over time;
- classify subtitle, title, lower third, logo, watermark, credit;
- sample frames and scene cuts;
- confidence and missed-text warnings;
- user-drawn boxes when detection is wrong.

### 3.2 Clean

- crop: move old text outside the output frame;
- cover: plate, blur, or branded band;
- manual mask;
- clean master for selected story ranges only;
- quality report: residual text, face overlap, ghosting risk, method, confidence;
- no generative face/logo removal;
- no watermark removal;
- no full-source 4K promise.

### 3.3 Compose

After cleanup, the same Flow 2 editor opens. The output is not a separate “cleaned video” product. It is a clean source for the same story packet.

### 3.4 Quality gate

Cleanup is not sold as “restore.” It must pass:

- 60 clips / 12 sources / 10 creators;
- zero P0 face/logo smear, ghost caption, caption over mouth, drift;
- ≥90% no visible artifact at 1×;
- 100% static edge text clean;
- residual OCR ≤0.5%;
- review ≤5 min static / ≤10 min moving;
- completion ≥80%.

Until then, Flow 1 is beta and not a paid promise.

---

## 4. Detect before Dissect

### 4.1 Source Check screen

Add a new first screen before Clip Set:

```text
SOURCE REPORT
  [video thumbnail] 42:18 · 1080p · speech 94% · music 18%
  Old captions: 14 tracks · 2 logos · 1 lower third
  Faces: 3 speakers · Safe zones: 9:16, 4:5
  Rights: attestation required
  Recommendation: CLEAN OLD TEXT → COMPOSE
  [Clean old text] [Caption & compose] [Both] [Skip]
```

### 4.2 Detection signals

| Signal | Source | Use |
|---|---|---|
| Text boxes | Apple Vision OCR / sampled frames | Flow 1 route |
| Text type | position, persistence, motion, styling | subtitle/overlay/logo/watermark |
| Speech | transcript / STT | captions, story quality |
| Music | audio energy / stems | music generation recommendation |
| Scenes | ffmpeg scene scan | dissect |
| Faces | Vision face boxes | safe zones, mask warnings |
| Quality | bitrate/resolution/compression | cleanup risk |
| Rights | user attestation | watermark/third-party guard |

### 4.3 Routing

| Source state | Recommended path |
|---|---|
| Baked captions/text detected | Flow 1 → Compose |
| No baked text, speech present | Flow 2 → Compose |
| Baked text plus clean areas | Both |
| No speech, music-led | Flow 2 with music-first |
| Rights unclear | Block cleanup; allow compose only |

The user can override. Detect is advisory, not a prison.

### 4.4 API

```http
POST /api/jobs/{job_id}/detect
GET  /api/jobs/{job_id}/detect
```

Response:

```json
{
  "source_report": {},
  "recommended_flow": "cleanup_compose",
  "text_tracks": [],
  "audio": {},
  "faces": [],
  "warnings": [],
  "confidence": 0.0
}
```

No render. No cleanup. No cloud.

---

## 5. Architecture

### 5.1 New/changed modules

```text
detect.py / routes_detect.py          # source report + route
cleanup.py / routes_cleanup.py        # Flow 1 plan + clean master
overlays.py / routes_overlays.py      # Flow 2 text layers
visual_sfx.py                         # motion/graphics definitions
filters.py                            # LUT/color plan
music_plan.py                         # generated bed + ducking/beat sync
compose.py / routes_compose.py        # unified compose plan
render_compose.py                     # crop → filter → overlays → captions → audio
packet.py                             # overlays/sfx/filters/music manifest
static/detect.js                      # source check UI
static/compose.js                     # overlay/SFX/filter/music UI
```

### 5.2 Data model

```text
SourceReport
  source_hash, duration, speech, music, scenes, faces
  text_tracks[], recommended_flow, warnings, attestation

TextTracklet
  kind: subtitle|title|lower_third|logo|watermark|credit
  boxes[], time_range, confidence, review_state

CleanMaster
  artifact_id, scope, method, mask_hash, quality_report, provenance

OverlayLayer
  kind, text, start, end, anchor, box, z, style, safe_zone

SfxLayer
  kind, asset/shape, start, end, anchor, intensity, easing

FilterPlan
  preset, exposure, contrast, saturation, temperature, vignette, grain

MusicPlan
  provider/local, prompt, bpm, beat_grid, duck, gain, license

ComposePlan
  source_report_id, clean_master_id?, overlays, sfx, filters, music, voice
  version, hash
```

### 5.3 Render graph

```text
source / clean master
→ crop/reframe
→ filter
→ visual SFX
→ overlays
→ captions
→ audio mix (voice/music/duck)
→ encode
→ artifact + packet
```

### 5.4 Artifact identity

Hash:

- source fingerprint;
- clean master hash;
- crop/aspect;
- filter plan;
- overlay/SFX layers;
- caption track/style;
- music/voice plan;
- encoder/quality.

A re-render never changes a pinned review link.

---

## 6. Pricing

The market signal is **$20–$50 per short clip or more**. Do not ignore it; do not turn local software into a credit meter.

### Recommended packaging

| Offer | Price hypothesis | What it is |
|---|---|---|
| **Base 1.0** | $249 one-time | Story workflow, captions, packet |
| **VibeCut Pro** | $399–$499 one-time | Detect + Flow 2 Compose + Flow 1 cleanup, local |
| **Studio** | $799 | 3 Mac licenses, same local product, no shared team workspace |
| **Done-for-you** | $25–$50/clip | Founder/contract editor uses VibeCut; separate service |

- No subscription for the local app.
- No per-clip meter in the app.
- No credits.
- Cleanup/Compose are part of Pro, not a second meter.
- Test the $20–50/clip signal as a service/agency offer before locking software pricing.
- 30-day refund.

The Pro price is deliberately below the equivalent of 10 clips at $40/clip. The creator buys ownership, not a meter.

---

## 7. Build waves and sub-agent roster

### Wave 0 — Architecture lock (2–3 days, 3 agents)

| Agent | Deliverable |
|---|---|
| Data/API architect | SourceReport, ComposePlan, CleanMaster, artifact hashes, schema |
| Editor integration lead | Screen map, file ownership, current SmartCut/Caption/Audio reuse |
| QA fixture lead | 20-source corpus, 60-clip cleanup set, acceptance rubric |

No merge of feature code. Output: `ARCHITECTURE.md` addendum, interface contracts, fixtures.

### Wave 1 — Detect (4–5 days, 4 agents, parallel)

| Agent | Branch | Files |
|---|---|---|
| OCR/text track | `feat/detect-text` | `detect.py`, OCR tests |
| Audio/scene/face signals | `feat/detect-signals` | signal adapters |
| Route/decision engine | `feat/detect-route` | recommendation + warnings |
| Detect UI | `feat/detect-ui` | `static/detect.js`, source report panel |

**Exit:** 20 sources report text/clean/mixed correctly; no cloud; default off until QA.

### Wave 2 — Flow 2 Compose (10–14 days, 5 agents, parallel)

| Agent | Branch | Files |
|---|---|---|
| Overlay/text layers | `feat/compose-text` | `overlays.py` extension |
| Visual SFX | `feat/compose-sfx` | `visual_sfx.py`, renderer |
| Filter editor | `feat/compose-filter` | `filters.py` |
| Music/voice plan | `feat/compose-music` | `music_plan.py`, `audio.py` integration |
| SmartCut UI | `feat/compose-ui` | `static/compose.js`, panels, preview |

**Exit vertical slice:** clean video → detect → SmartCut → hook/caption + one SFX + one filter + generated music → render → packet.

### Wave 3 — Flow 1 Cleanup (10–14 days, 4 agents, parallel)

| Agent | Branch | Files |
|---|---|---|
| Text tracking/masks | `feat/cleanup-mask` | `cleanup.py` extension |
| Cleanup renderer | `feat/cleanup-render` | crop/cover/blur, clean master |
| Cleanup UI | `feat/cleanup-ui` | mask review, quality report |
| Quality/provenance | `feat/cleanup-quality` | residual text, face/logo warnings |

**Exit:** baked-text video → detect → cleanup selected stories → same Compose → render. No generative/watermark.

### Wave 4 — Finish/integration (5–7 days, 3 agents)

| Agent | Branch | Files |
|---|---|---|
| Unified render | `feat/finish-render` | `render_compose.py` |
| Packet/versions | `feat/finish-packet` | packet manifest, versions |
| Performance | `feat/finish-perf` | proxy/cache/ETA, M1/16GB |

### Wave 5 — QA/QC/tester/principal (3–5 days, 4 agents)

| Agent | Gate |
|---|---|
| QA lead | Acceptance, 20-source, 60-clip cleanup, Flow2 vertical slice |
| QC/security | No cloud, watermark removal, generative faces, token leak, default-on |
| Independent tester | Full pytest, compileall, JS, smoke, merge count |
| Principal engineer | Merge only after all gates; resolve conflicts; final suite |

**Parallelism rule:** no two agents edit the same file. New modules + routers; `app.py` gets only import/include lines. UI splits by JS module. Principal owns app.py/CI conflicts.

---

## 8. Acceptance

### Flow 2

- clean 90-minute source → detect → 3–6 stories;
- edit story/sentences;
- add hook, captions, 2 visual SFX, 1 filter, generated music;
- render 9:16 and 4:5;
- packet includes overlays/SFX/filter/music;
- close/reopen, same packet;
- no cloud or account.

### Flow 1

- finished video with baked captions → detect reports text tracks;
- crop/cover/blur on selected stories;
- quality report; no face/logo smear;
- new captions/hook/SFX/filter/music;
- render/packet;
- old captions do not ghost.

### Detect

- 20 sources: 8 baked text, 6 clean, 4 mixed, 2 no speech;
- correct flow recommendation ≥90%;
- no false “clean” on visible captions;
- no false “remove” on clean footage;
- user override always available.

### Quality

- 1.0 gates unchanged;
- Flow 1 60-clip gate;
- Flow 2 20-story visual/caption gate;
- performance: 90-minute analysis ≤30 min; story compose render ≤2× duration; UI <100ms.

---

## 9. What not to build

- accounts, cloud sync, login, team seats;
- publishing, scheduling, OAuth, platform APIs;
- analytics, virality, trends, retention ledger;
- generic stock B-roll or SFX marketplace;
- avatars, voice cloning, face replacement;
- watermark removal;
- generative face/logo repair;
- full-source 4K cleanup;
- auto-post or auto-resume;
- a second NLE;
- a template shop.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Detect falsely says clean | Conservative thresholds; test 20 mixed sources; user override |
| Cleanup smears face/logo | Crop/cover/blur first; no generative; 60-clip gate; quality report |
| Visual SFX becomes a template shop | Fixed, local, deterministic effects; no marketplace |
| Filter editor becomes a color suite | Basic controls + presets only |
| Music/voice adds cloud dependency | Local/optional providers; no mandatory cloud |
| Too many agents conflict | File ownership + waves + principal merge |
| UI becomes bloated | Current SmartCut base; tabs/inline; no second app |
| Pro price too high | Test $20–50/clip service; adjust; 30-day refund |

---

## 11. Open decisions

1. Is Flow 1 included in Pro or a separate add-on? Recommendation: included in Pro, not metered.
2. Pro price: $399 or $499?
3. Does Flow 2 ship before Flow 1? Recommendation: yes, vertical slice first.
4. 4:5 required for first cohort? Recommendation: yes, client work.
5. Does music generation support local-only first? Recommendation: yes; cloud optional.
6. Exact Mac minimum: M1/16GB recommendation.
7. Rights attestation wording and watermark policy.
8. Which SFX set ships first: punch-in, arrow, circle, progress bar, emoji.

---

## 12. Next step

Approve the plan. Then start **Wave 0** with three read-only agents:

1. data/API architect;
2. editor integration lead;
3. QA fixture lead.

Wave 0 produces the interface contracts and fixtures. Wave 1 starts only after those contracts are signed. No feature code merges before QA, QC, tester, and principal merge.

**One-sentence product promise:**

> VibeCut detects what the footage needs, cuts the stories, cleans old captions when necessary, and composes the hook, captions, visual effects, music, and filter — locally, in one workstation.
