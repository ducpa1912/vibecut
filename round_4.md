# VibeCut subtitle and text overlay — Round 4

**Date:** 2026-10-26  
**Question:** Should VibeCut build burned-in subtitle/text cleanup and new hook/caption overlays, and how should they enter the roadmap?  
**Baseline:** `b7596db` (paid-v1 trust fixes), after `dea6515`.  
**Status:** Feature-discovery round. **Simulated creator panel, not real customer interviews.** No feature code was changed.  
**Inputs:** [round_3.md](round_3.md), [PRD.md](PRD.md), [PLAN.md](PLAN.md), [ROADMAP_V1.md](ROADMAP_V1.md), [ROADMAP_V2.md](ROADMAP_V2.md), current code, and current local/remote research on video text removal.

---

## Key highlights

> **Key highlight:** Flow 1, source-less cleanup, is the paid expansion wedge — but deterministic only: crop, cover, blur, manual masks, text detection, quality report.

> **Key highlight:** Flow 2, new hook/caption overlays, is retention, not a paid wedge. Overlays are commodity.

> **Key highlight:** Paid 1.0 does not change. No cleanup or overlay feature enters the five-gate paid-v1 release.

> **Key highlight:** There is no clean plate in Flow 1. Removal reconstructs pixels; it does not restore them. The promise is **plausible clean**, never “restore.”

> **Key highlight:** Crop → cover → blur → repair. Most jobs should stop before repair. Temporal inpainting is conditional and alpha-lab only.

> **Key highlight:** Six of six panelists value cleanup more than overlays; all refuse watermark removal and cloud-only processing; review tolerance is 5–10 minutes per clip.

> **Key highlight:** Cleanup is a $149 one-time add-on; $99 for v1 owners in the first 90 days. Unlimited local jobs. No subscription, per-clip metering, credits, meter, cloud, or seats.

> **Key highlight:** Overlay Studio is conditional retention. Hook Cards are killed.

> **Key highlight:** Before cleanup code or sale: 10 real Mom Tests + paid concierge pilot. Before general sale: 60 clips, 12 sources, 10 creators, zero P0 smear.

> **Key highlight:** No cloud, no team seats, no watermark removal, no generative face/logo repair — ever.

---

## 1. The feature question

VibeCut has two different text problems:

### Flow 1 — source-less repurpose

The creator has only a finished long-form video with baked-in captions, titles, handles, logos, or old branding. There is no clean source, project, or clean plate.

They want to:

- remove the old text;
- hide it with crop/cover/blur;
- replace it with new text;
- reuse the footage in new cuts, aspects, or versions.

This is a pixel-reconstruction problem. The original background behind the text no longer exists in the file.

### Flow 2 — clean input

The video has no captions or text overlay. The creator wants VibeCut to create:

- a new hook;
- speech-timed captions;
- titles, lower thirds, CTA, end card;
- safe-zone-aware text for 9:16 and 4:5.

This is an overlay/compositing problem. It is the current Caption Studio extended.

### The honest product line

```text
Flow 1:  detect → track/classify → mask review → clean pass → overlay pass → quality report
Flow 2:  captions → hook/title/CTA → safe-zone preview → overlay pass
```

The two flows meet at a shared **overlay layer** and **text-safe render**, but they are not the same product risk.

---

## 2. Loop 1 — product and engineering

Loop 1 ran two independent evaluations:

- senior product lead;
- senior video/vision engineer.

They then reconciled the product thesis, technical redlines, and Mom Test.

### 2.1 Product independent position

#### Opportunity map

| Segment | Pain | Current workaround | Cost | Frequency | WTP |
|---|---|---|---|---|---|
| Archive repurposer | High: baked captions block reuse; project gone | Crop/zoom, black bar, blur, recut from source, VSR/ProPainter, cloud remover | 30 min–3 h per clip; artifacts | Monthly/quarterly batches | Medium: $99 add-on |
| Agency/localizer | Highest: client footage, rights, languages, re-overlay | Resolve/AE manual paint, cloud tools, VSR | Hours; upload/privacy conflict | Weekly | High: $300–$1k if it saves a day |
| Solo reposter | Medium: one old clip to Shorts | CapCut crop/cover | 15–60 min | Occasional | Low |
| Clean-input creator | Low removal pain; high overlay/hook pain | Caption Studio + CapCut/Submagic | Minutes | Every video | Bundled |

The product lead concluded:

- Flow 1 is the more acute pain.
- Flow 2 is more frequent and strategic.
- Current VibeCut ingests any video, but OCR is one still per scene; captions burn as image overlays; crop uses face/saliency, not text.
- There is no temporal text track, mask layer, or clean master.
- A finished short is not the current story unit; a finished long video can use the story engine, but old captions pollute every cut.

#### Product thesis

- **Flow 1 is a product line.**
- **Flow 2 is a feature.**
- Flow 1 has a different input, unit (clean master), quality bar (pixel repair), and support burden.
- Flow 2 extends the existing story workflow and compounds Caption Studio, speech-timed cues, immutable artifacts, and packet.
- Wedge recommendation: **Flow 2** (later overruled by the CTO).
- Flow 1 should follow paid v1 as a bounded add-on, not be smuggled into the gate.

#### Feature concepts

Small, near-term:

- baked-text collision check in preflight;
- text-safe crop;
- cover/blur band;
- OCR-to-SRT draft;
- hook card;
- lower third, CTA, end card, three templates;
- overlay layer separate from pixels.

Big, later:

- temporal text detection;
- mask review;
- inpainting/remove;
- replace/re-overlay;
- clean master versioning.

#### Packaging proposal

- Paid gate: no new product; at most advisory text collision + text-safe crop.
- 1.1: overlay layer, hook card, lower third, templates, text-safe reframe, OCR-to-SRT.
- 1.3/2.0: Clean Master add-on $99–$149, or $399 studio.
- Do not bundle Clean Master into $249.

#### Risks and guardrails

- refuse logo/watermark removal;
- only user-owned text;
- no public-figure text scrubbing;
- warn/refuse masks over faces/hands;
- always generate replacement SRT/transcript;
- provenance sidecar;
- local-only;
- no “restore” promise.

#### Product metrics

- Flow 2: overlay adoption ≥30%; hook edit <2 min; zero safe-zone collisions; no repair increase.
- Flow 1: OCR recall ≥95%; mask review <5 min/10 min; completion ≥40%; ≥70% no visible artifact; 60s cleaned <20 min on M1/16GB.
- Kill if completion <40%, median >20 min, >25% visible artifacts, render >4× realtime, or any gate slips.

### 2.2 Engineering independent position

#### Feasibility by mode

| Mode | What it really does | Quality | Failure modes | Verdict |
|---|---|---|---|---|
| Crop/reframe | Moves old text outside 9:16/4:5 | High; no synthesis | Cuts subject or text remains inside crop | Ship first |
| Blur/cover | Blur, plate, branded band, new caption plate | Reliable, visibly fixed | Mask drift, obvious patch, face/UI cover, edge flicker | Ship |
| Temporal inpainting | ProPainter/STTN/E2FGVI-style flow/propagation | Medium on small masks/static/texture; poor on faces/hands/motion | Ghosting, smearing, texture swimming, scene-cut jumps | Beta only |
| Generative removal | Diffusion/video inpainting | Good stills, unstable motion | Identity drift, hallucinated objects, flicker, huge memory | Do not ship on M1/16GB |
| Re-overlay | Cover old text, add new captions/hook/overlay | Highest control | Double text if cover fails; occlusion; style mismatch | Ship |

**Hard truth:** no clean plate. Removal reconstructs pixels. Say **“plausible clean,”** never “restore.”

#### Pipeline

```text
Import
  mode = repurpose | clean
  ↓
Detect text        Apple Vision OCR boxes, 2–6 fps + scene cuts + tile retry
  ↓
Track/classify     static/moving; subtitle/overlay/watermark/logo/credit
                   project box into each output crop; outside-crop = no clean
  ↓
Mask review        OCR box + stroke mask; brush edit; face/hand overlap warning
  ↓
Clean pass         crop > cover > blur > LaMa/temporal inpaint
                   per exported range and aspect; cached per segment
  ↓
Overlay pass       new captions, hook, title, CTA, lower third, z-order
  ↓
Artifact + packet  quality report, provenance, removal log
```

Where it runs:

- detection in analysis worker;
- mask review in UI;
- clean/overlay in single render worker;
- never concurrent on 16GB;
- clean only exported ranges/stories, not a full 90-minute source;
- for repurpose clips ≤3 minutes, full-source detection may be acceptable;
- for 30–120-minute sources, sample scenes.

#### Models and local Mac reality

| Component | Choice | M1/16GB |
|---|---|---|
| OCR/detection | Apple Vision, existing Swift helper | Ship; weak on tiny/outlined/vertical/stylized text |
| Mask tracking | OCR box + stroke threshold + optical flow; SAM 2.1 tiny only hard masks | Ship basic; SAM optional |
| Image fill | LaMa via Core ML | Beta; seconds per 1080p frame; flicker without temporal stabilization |
| Video inpainting | ProPainter/ProPainterX; E2FGVI/STTN older | Beta/research; 720p ~8–12GB with memory-efficient settings; 1080p ~24GB; minutes per 10s |
| Diffusion video | DiffuEraser class | No; reported 33GB / 314s for 250 frames at 720p on L20 |

**Ship on M1/16GB:** Vision detection, crop/cover/blur, LaMa image pass, overlay compositor.  
**Fallback:** cover only.  
**Do not ship:** 1080p inpainting, diffusion removal, SAM every frame, 4K, automatic moving-text removal, “one-click erase anything.”

#### Data model changes

Add to `job.json` and artifact manifests:

| Entity | Key fields |
|---|---|
| `TextObservation` | frame time, normalized box, text, confidence, script, candidates |
| `TextTracklet` | kind `subtitle/overlay/watermark/logo/credit`, time range, boxes, motion, confidence, review state |
| `MaskTrack` | tracklet IDs, keyframes/RLE masks, feather, hash, model |
| `TextLayer` | kind `hook/title/overlay/subtitle/cta/watermark`, text, start/end, box, style, z, animation, safe zone, origin, hash |
| `OverlayTrack` | versioned layer list, style hash, layer hash |
| `CleanMaster` | scope, range, method, mask hash, model/version, resolution, status, quality report |
| `QualityReport` | residual text, flicker, ghosting, face/hand overlap, cuts, confidence, flags |
| `Provenance` | rights attestation, removal log, input C2PA hash, output manifest, tool version |

Distinguish **subtitle** (speech-timed, SRT-able), **overlay** (design text, not speech), and **watermark** (rights/provenance). Keep `CaptionTrack`; add `kind`.

Add `render_kind`, `clean_hash`, `text_layers_hash`, `mask_hash`, `quality_report_id` to `ArtifactSpec`. Packet gets `overlays.json`, clean disclosure, and provenance.

#### Quality and acceptance

- 60 real clips + 20 synthetic pairs (clean clip → burn known text → remove).
- Categories: bottom/top/center captions; static/moving overlays; logos/watermarks; text over faces/hands; patterned backgrounds; pans/cuts; compressed/dark; CJK/stylized fonts; 3–8 seconds; 720p/1080p.
- OCR line recall ≥95%, box IoU ≥0.85 at confidence ≥0.5.
- Mask temporal IoU ≥0.90; no unlabeled face/hand overlap.
- Residual OCR text ≤0.5% of output frames.
- Human: 3 blind raters, 5-point scale; mean ≥4.0; no clip <3; ≥90% “no obvious defect at 1× playback.”
- Temporal p95 warped-frame error ≤2× surrounding background; no visible pulse/banding.
- Synthetic VMAF drop ≤2 versus clean source at matching bitrate.
- First 100 outputs 100% review; then 20% sample. Fail if >10% need mask re-edit or >5% rejected for flicker/ghosting.

#### Safety and rights

- Import attestation: “I own this footage or have permission.” Store hash and timestamp.
- Detect platform marks/credits. Block removal of TikTok/CapCut/YouTube/Instagram watermarks and third-party credits.
- Classify watermark vs subtitle. Unknown rights → cover/crop only, never generative erase.
- Removal log: track, range, method, model, operator, attestation.
- Preserve C2PA input; write `provenance.json`; current `-map_metadata -1` strips metadata — change for repurpose outputs.
- No C2PA compliance claim until signing/validation exists.

#### Build sequence

- **MVP (3–5 weeks):** repurpose crop/cover/blur + manual mask review + Flow 2 overlay studio + artifact/provenance schema + quality badge `Covered`, `Clean (synthetic)`, `Original text remains`.
- **Beta (6–10 weeks):** LaMa image pass with temporal stabilization for static/slow shots; 720p, ≤10s windows; clean master; per-segment cache; batch 3–5; quality confidence/fallback.
- **Big bet:** ProPainter-class local port, moving text, face-aware masks, 24GB+ hardware gate. Research preview only.
- **Cut:** arbitrary moving text, face/hand reconstruction, 4K, full-source cleaning, third-party watermarks, diffusion, real time.

#### Hardest engineering questions

1. Does “clean” mean plausible or pixel-true?
2. Will creators review masks for 1–3 minutes per clip?
3. Is demand removing your own text, or repurposing other people’s videos?

### 2.3 Product–engineering reconciliation

The product lead read the engineering report and revised:

- prior ranking holds: **Flow 1 product line, Flow 2 wedge**;
- engineering changes shape, not ranking;
- no clean plate; promise **plausible clean**;
- inpainting is not the base product; **crop → cover → blur → repair**;
- premium Clean Master has two tiers: **Lite** (crop/cover/blur/manual masks) and **Pro** (temporal repair);
- ProPainter-class needs ~24GB; the ICP is M1/16GB; Pro is a niche add-on;
- re-overlay is the safest bridge and strongest common core;
- clean master must be a first-class artifact with `clean_hash`, `mask_hash`, method, model ID, quality report;
- watermark/subtitle classification and ownership attestation are mandatory.

#### Reconciled scope tiers

| Tier | Scope |
|---|---|
| Paid v1 | Text Check advisory + Safe Crop only if existing behavior; no mask UI, no inpaint, no clean-master artifact, no new flow |
| 1.1 | Overlay Studio, Caption Rescue, text-safe reframe, `overlays.json`, overlay hash |
| 1.3 | Clean Master Lite add-on: crop/cover/blur, manual masks, quality badge, clean master artifact, LaMa static/slow-shot repair at 720p ≤10s beta |
| 2.0 | Clean Master Pro: ProPainter-class temporal repair, 1080p, longer windows, 24GB+; never “pixel-true” |
| Alpha lab | moving text, SAM hard masks, 4K, full-source cleaning, generative removal, C2PA, VMAF gates |

#### Reconciled feature names

- **Text Check** — flags burned-in text before it collides with new captions.
- **Safe Crop** — frames the subject and keeps old text out of the shot.
- **Cover Old Text** — plate, blur, or crop over old words; visibly a fix.
- **Repair Clip (Beta)** — rebuilds short, simple backgrounds under old captions; shows where it may fail.
- **Clean Master** — protected cleaned cut with mask, method, quality report.
- **Caption Rescue** — OCR old captions into editable draft SRT with uncertain lines marked.
- **Overlay Studio** — hooks, lower thirds, CTAs, end cards, safe-zone checks.
- **Hook Cards** — three editable openings; later killed by CTO.
- **Quality Report** — what was detected, changed, and must be reviewed.

#### What the product must not promise

No “restore,” “remove any text,” “invisible,” “one click,” “works on every font/moving shot,” “full 90-minute clean,” “4K,” “real time,” “no quality loss,” “platform-safe,” “undetectable,” or “C2PA compliant.”

No third-party watermark/logo removal. No face/hand reconstruction. No diffusion quality on 16GB. No clean master without a quality report and human review. No claim that metadata stripping is provenance.

### 2.4 Mom Test script

Given verbatim to creators:

1. Tell me about the last video you reused that you had already finished. Where did the file come from, and did you still have the original project?
2. What text was already on screen in that video — captions, titles, handles, logos? What did you need to do with it?
3. Walk me through what you actually did, step by step. What tools did you open, and in what order?
4. How long did it take, and what did it cost — your time, someone else’s time, or money?
5. What went wrong with the result? What did you try next?
6. When the original project was gone, what did you do instead?
7. Whose video was it, and who owned the words or logos on screen? Did anyone have to approve the reuse?
8. How did you check the result before it went out? Did you watch every frame, spot-check, or send it to someone?
9. How often has this come up in the last month, and what kind of videos were they?
10. Tell me about the last time you added a hook or text overlay to a clean video. What did you use, and what did you have to fix afterward?

### 2.5 Hypotheses

- **H1 — frequency/cost.** Source-less reuse with baked text is recurring, expensive, unresolved.
  - Falsified if most reuse still has the original project, cleanup is under 10 minutes and acceptable, or it happens less than monthly.
- **H2 — plausible clean is enough.** Creators accept crop/cover/blur when repair is imperfect.
  - Falsified if they demand invisible, pixel-true repair; reject visible covers; or judge at 100% and reject any artifact.
- **H3 — rights/review.** Creators own the footage/text and will review masks.
  - Falsified if most examples are third-party videos, watermark stripping, or if they refuse frame review.

---

## 3. Mom Test interviews

Three creator interviews were run with the same script. These are simulated personas, not real customers.

### 3.1 Solo repurposer

- 6 years weekly interview podcast and YouTube; repurposes old episodes.
- Last job: 42-minute interview from 2021. Project existed, media offline.
- Burned-in captions, lower third, old handle, logo bug, expired sponsor end card, client logo on wall.
- Workflow: Premiere → 1080×1920 sequence, 178% scale → CapCut auto-captions → fixed names → re-export after audio drift.
- Cost: 3h20 across two nights; skipped the second clip. CapCut $9.99/mo.
- Failures: captions over mouth, hands cropped, 120ms audio drift, “kiln” → “kill,” “Márta” → “Marta.”
- No-project case: downloaded own Vimeo upload, cut in CapCut; another screen-recorded playback, too soft, never posted.
- Rights: mostly own; guest releases; old client reuse rights lapsed; one client said organic only, one never replied, did not post.
- QC: full watch on phone, muted, safe zones, guest name check; not every frame.
- Frequency: 4 in 30 days (podcast, client interview, tutorial).
- Overlay: clean 40s clip; CapCut template under TikTok UI, font reset, covered face; three fixes.
- Would pay: $15–20/mo or $8–10/clip; $99/10 if two clean without touch-up; not per minute.
- Never: watermark, cloud, voice cloning, crop cutting hands/faces, tool making rights calls.
- Mask review: 5 min/clip for up to 5 clips/week; at 10, no.

### 3.2 Client-focused editor

- 10 years; 2-person post shop; $125/hr.
- Last job: 38-minute fitness class; client master only, no project; editor left, drive decommissioned.
- Text: burned white captions bottom third, logo bug top right, coach lower third, old end card.
- Workflow: Premiere selects → Resolve patch replacement → 4:5 crop for ~60% → AE tracked mask/clean plate for rest → logo rebuild in Illustrator → grade → QC.
- Cost: 7 hours, $875; Marco 2 hours on logo, $90; one revision.
- Failures: Resolve smeared sleeve on moving fabric; tracked mask + clean plate took 40 min for 6 seconds; logo weight caught by client.
- No source: no relink, rebuilt off export, graded H.264, kept flat to avoid breakup.
- Rights: client owns footage/wordmark; talent release organic only, not paid; brand manager approved; no paid approval, stayed organic.
- QC: full watch 1x headphones, frame-step every cut/caption edge at 200%, phone + 55-inch TV; client caught logo.
- Frequency: 4 in 30 days; 3 had no project.
- Overlay: Premiere Essential Graphics/AE; font fallback, Instagram caption zone, keyframe popped; re-rendered twice.
- Would pay: $15–20/clip for clean removal on flat backgrounds, no faces/hair; $150/10; not >$40/mo.
- Never: changed/redrawn logo, smeared faces/hands, client footage uploaded without DPA, render not frame-checkable.
- Mask review: 5–10 min/clip, max 2 clips/job; beyond that rebuild or charge.

### 3.3 Course creator

- 8 years courses/cohorts; 40 lessons, 12 webinars; burned captions, old branding.
- Last job: 21:40 lesson from 2021; no project; export only.
- Text: yellow auto-captions bottom third, title card, old serif wordmark top right, URL, name lower third; logo over moving bookshelf.
- Workflow: Descript transcript → CapCut 4:5 crop → Canva title/end cards → CapCut assemble → LinkedIn.
- Cost: 3h40 first, 70 min second; Descript $24/mo, Canva $15/mo, CapCut free; VA quote $40/clip skipped.
- Failures: ghost captions at bottom, stacked captions, 9:16 cut hands, 1:1 forehead clipped, “cohort” → “co-hurt” four times, “ROI” → “are oh eye,” low loudness.
- No source: export is source of truth; transcribe MP4, cut inside one framing; use webinar slide/Canva frame for clean background.
- Rights: own solo; guest CPA segment had written permission; Epidemic Sound license; no resale of Canva art.
- QC: full watch twice (muted + headphones), first/last 3 sec frame-by-frame, VA $12 “does this look old” pass; guest held 5 days.
- Frequency: 6 clips in 30 days from four sources; twice a week; 18–35 min talking heads.
- Overlay: clean 48s phone Q&A; CapCut + Canva hook; under Instagram UI, wrong font, captions on chin; moved top 15%.
- Would pay: $20/clip at 10+ or $99 one-time; not $50/mo for 20 minutes of credits.
- Never: invented claims, misheard names/numbers, changed meaning, watermark, output that looks 2018.
- Mask review: 5 min for guest/logo/long clips; batch 10 = 50 min, would skip plain talking heads.

### 3.4 Cross-interview read

| Hypothesis | Read |
|---|---|
| H1 frequency/cost | Confirmed: 4–6 clips/month, 3h20–7h per source, $875 client job. Cash ceiling is modest: $15–20/clip, $99–150/10, $15–30/mo |
| H2 plausible clean enough | Falsified for automatic removal. Crop solves ~60%; ghost captions, captions over mouth, smeared faces/logos, 40 min for 6 seconds. Clean only on flat/static backgrounds and edge text |
| H3 rights/review | Confirmed hard. All refuse watermark and invented claims; two refuse cloud; client editor needs DPA; review 5–10 min, 2–5 clips |

**Common failure:** crop is the reliable 60%; the rest is manual masks and quality review. That is the gap.

---

## 4. Loop 2 — creator panel

The three Mom Test creators were joined by:

- a YouTuber with 250k subscribers;
- a short-form influencer with 1.2M TikTok/Instagram followers;
- a viral content marketer running high-volume testing.

Each did separate research/discovery before reading the Mom Test and evaluating the features.

### 4.1 What the panel researched

**Removal/hiding tools:**

- Premiere + AE Content-Aware Fill / tracked masks;
- Resolve Studio Patch Replacer / Fusion;
- Mocha Pro planar tracking;
- CapCut crop/cover/blur;
- ffmpeg delogo/blur boxes;
- Runway/Kling/Pika/Firefly cloud inpainting;
- open-source VSR/ProPainter/E2FGVI/STTN/LaMa;
- cloud caption/watermark removers (HitPaw, Media.io, Veed).

**Overlay creation tools:**

- CapCut auto-captions/templates;
- Descript transcript editing/captions;
- Premiere MOGRTs/Essential Graphics;
- Canva hook cards/lower thirds;
- AE for animated overlays;
- Opus/Submagic cloud auto-clip.

**Common research read:**

- crop/cover is cheap, local, reliable for edge text;
- tracked masks/AE are local but expert/slow;
- cloud inpainting is fast on simple shots but privacy/quality risk;
- local open-source inpainting is promising but slow/flickery;
- overlays are already commodity at $0–$25/mo;
- no panelist has a trusted local workflow that removes baked text without wrecking face/logo or uploading client footage.

### 4.2 Panel evaluations

#### Solo repurposer

- **H1:** half confirmed. 4–6 clips/month, recurring; cash willingness $10–20/mo or $8–20/clip; if H1 assumed high volume/$50+/mo, falsified.
- **H2:** confirmed as pain, not solution. Crop solves ~60%; automated repair plausible only for static lower thirds/stable plates; not faces/hands/moving logos.
- **H3:** confirmed. Rights gate reuse; review gate output; 5 min/clip, max 2–5.
- **Flow:** cleanup more valuable; overlays commodity.
- **Price:** $19/mo for 20 clips, $8/clip; $99/10 if two clean without touch-up; no separate overlay pay.
- **Must:** Safe Crop, Cover Old Text, Text Check, Clean Master with confidence.
- **Nice:** Caption Rescue, Repair Clip Beta, Overlay Studio.
- **Never:** Hook Cards standalone, generative face/logo, rights automation, cloud-only, auto-posting.
- **Quality:** 1080p, no ghost edges/smears, text gone through full shot, audio within a frame, one review pass <5 min; reject after two bad clips.
- **Build first:** Safe Crop + Cover Old Text + Text Check + Clean Master, batch, SRT, risky-shot flags.
- **Abandon:** one smeared face/ghost caption on client work; two of three clips still need AE; price ceiling low.

#### Client editor

- **H1:** confirmed. 4/30d, 7h/$875; price per clip, not subscription; solo caps $15–20/mo; course wants $99 one-time.
- **H2:** falsified as stated. Best automatic result 60% via crop; every panelist hit ghosts, mouths, or drift; clean only flat/static/edge.
- **H3:** confirmed hard. All refuse watermarks; two refuse cloud; all refuse invented claims/misheard names; review 5 min, 2–5 clips, batch.
- **Flow:** cleanup valuable; overlay no. Mogrts faster, font/legal control; template library is a liability on client work.
- **Price:** $15–20/clip, $150/10, not above $30/mo.
- **Must:** Safe Crop; Cover Old Text on flat backgrounds; Text Check; OCR-to-SRT.
- **Nice:** Clean Master report for client sign-off; Overlay Studio; Hook Cards.
- **Never:** automatic Repair Clip on faces/hair/moving fabric; logo redraw.
- **Quality:** 100% on 55-inch TV and phone; no ghost edge on moving garment; no grain shift; text gone within 1–2 frames; names <2% WER; 5 min/clip, 2 client clips.
- **Build first:** crop, cover static backgrounds, Text Check, OCR-to-SRT; before/after and change list.
- **Abandon:** passes at 50% but fails on client TV; >10 min handling; upload required; cannot approve mask.

#### Course creator

- **H1:** confirmed. 4–6 clips/month; 70 min–7h; $875 client job.
- **H2:** half-confirmed/half-falsified. Clean needs tracked masks/40-min fixes; crop alone fails center text/faces.
- **H3:** confirmed stronger. DPA, 2–5 clips, hard refusal.
- **Flow:** cleanup more valuable; overlays cheap in CapCut/Canva; old burned captions stop posting.
- **Price:** $15/clip, $120/10, $99 one-time; no $50/mo.
- **Must:** Cover Old Text, Text Check, Safe Crop, Caption Rescue.
- **Nice:** Repair Clip Beta until proven; Clean Master report; Overlay Studio; Hook Cards.
- **Never:** auto-publish, generative face replacement, cloud-only, watermark.
- **Quality:** no ghost lines at 100%; no warped face/hands/logo; names/numbers 100%; first/last 3 frames; -14 LUFS; 5 min/clip, 5/week.
- **Build first:** Text Check + Safe Crop + Cover Old Text + Caption Rescue.
- **Abandon:** flicker, invented words, >5 min/clip, AE skills, file leaves Mac.

#### YouTuber

- **H1:** confirmed on pain, capped on volume. 4–6/30d; 3h20–7h; $20–30/mo or $6–10/clip; $99/10; falsified if H1 assumes daily high volume.
- **H2:** falsified. Crop fixes layout, not burned text; ghost captions, 40 min AE for 6s.
- **H3:** confirmed. All refuse watermark/cloud, smeared faces/logos, invented claims; 5–10 min review.
- **Flow:** cleanup matters; overlays commodity; masters exist but archive/client cleanup 6–10/month; overlays weekly but not new money.
- **Price:** $20–30/mo for 10 cleaned clips + overlays; $6–10/clip; client pass-through $15–20; burst 8–12/month; $99/10 trial.
- **Must:** Safe Crop, Cover Old Text, Caption Rescue, Text Check.
- **Nice:** Repair Clip Beta manual, Overlay Studio, Clean Master.
- **Never:** Hook Cards, auto-publish, cloud-only client upload, face/logo smearing, generated names/claims.
- **Quality:** no ghosting, no caption over mouth, names right, lip-sync ±1 frame, 1080×1920/4:5, faces not soft; 95% usable first pass; one re-render.
- **Rights:** owned/licensed/permitted; no training; delete after export; local option.
- **Build first:** Safe Crop → Cover Old Text → Caption Rescue → Text Check; then local Repair for moving shots; Overlay after trust.
- **Abandon:** one bad client clip, ghost/wrong name/upload without consent, or review >5 min.

#### Influencer

- **H1:** partly confirmed. 4–6 clips/30d; $15–20/clip ceiling; $99 one-time appetite, not subscription loyalty.
- **H2:** confirmed only edge text; falsified for centered/moving/faces/logos. “Ghost captions”/“smeared” decisive.
- **H3:** confirmed. Watermark/cloud/invented claims/misheard names hard refusals; 5–10 min; client editor needs approval control.
- **Flow:** cleanup is the blocker; overlays are cheap and fast; cleanup first, overlays retention.
- **Price:** $20–30/mo solo for 5 clips/week; $3–5/clip batch; $99 lifetime converts faster than subscription; client editor needs 3 seats/review and $40–60/mo; but VibeCut refuses seats.
- **Must:** Text Check, Safe Crop, Cover Old Text, Caption Rescue, Clean Master.
- **Nice:** Repair Clip Beta, Overlay Studio, Hook Cards.
- **Never:** watermark, cloud-only, auto-publish, invented claims, face/logo replacement without approval.
- **Quality:** no ghosting on phone at arm’s length; no caption over mouth; sync within a frame; names correct/flagged.
- **Rights:** no watermark/training/cloud without per-file consent/export log.
- **Build first:** Text Check, Safe Crop, Cover Old Text as one local cleanup pass with before/after; then Caption Rescue.
- **Abandon:** one bad client delivery; forced cloud.

#### Viral content marketer

- **H1:** confirmed. 6–10/30d, $15–20/clip, $150/10, $875/class.
- **H2:** falsified as “clean enough.” Crop ~60%; ghosts, mouth, drift, 40 min for 6s.
- **H3:** confirmed. All refuse watermark/cloud; review 5–10 min; client editor needs seats.
- **Flow:** cleanup is the wedge; overlays commodity; cleanup first, overlays retention or churn.
- **Price:** $20–30/mo solo; $8–12/clip; $150/10; $99 one-time converts; client editor 3 seats at $40–60/mo; VibeCut refuses.
- **Must:** Cover Old Text, Safe Crop, Clean Master, Caption Rescue, local.
- **Nice:** Text Check, Overlay Studio, Hook Cards, Repair Beta until proven.
- **Never:** watermark, forced cloud, invented claims, auto-publish.
- **Quality:** no ghosting/smeared face/logo; captions never over mouth; names ≥95%; sync within a frame; source resolution.
- **Rights:** local, no watermark, no invented claims, export log.
- **Build first:** local pass: old text + safe crop + caption rescue + clean master export.
- **Abandon:** one bad client smear/ghost, watermark, forced cloud.

### 4.3 Panel synthesis

#### Hypotheses

| Hypothesis | Verdict |
|---|---|
| H1 frequency/cost | Confirmed but modest. 4–6 clips/month, 3h20–7h per source; cash ceiling $15–20/clip, $99–150/10, $15–30/mo. Not daily high-volume |
| H2 automatic clean enough | Falsified except edge text + crop/cover. Faces, logos, moving text, mouths fail; 60% crop is the reliable ceiling; 40 min for 6s is not product |
| H3 rights/review | Confirmed. 6/6 refuse watermark/cloud; 5–10 min review, 2–5 clips; client editor needs DPA; all refuse invented claims/misheard names |

#### Flow value

- **6/6 say source-less cleanup is more valuable than new overlays.**
- Overlay Studio/Hook Cards are commodity: CapCut, Descript, Canva cover them.
- Cleanup is the blocker and the budget line.
- Overlay creation is retention, not acquisition.

#### Price signals

- $15–20/clip;
- $99–$150/10;
- $15–30/mo;
- $99 one-time;
- client editor $150/10;
- influencer/agency wants seats, which VibeCut refuses.

#### Feature ranking

| Rank | Feature | Panel read |
|---|---|---|
| 1 | Safe Crop | Most reliable; often removes edge text; no synthesis |
| 2 | Cover Old Text | Honest fallback; plate/blur/crop; not invisible |
| 3 | Text Check | Prevents double-caption output; advisory |
| 4 | Caption Rescue | OCR-to-SRT draft; saves typing; human review required |
| 5 | Clean Master | Quality report/provenance; trust, not magic |
| 6 | Repair Clip Beta | Conditional; only static/slow; alpha-lab |
| 7 | Overlay Studio | Commodity; retention only |
| 8 | Hook Cards | Commodity; killed |

#### Quality/review bar

- No ghost lines, smeared faces, changed logos, invented claims, misheard names.
- 1080p, 9:16/4:5, audio sync within a frame.
- 5 min review per clip; 2–5 clips per batch; client editor needs frame-level review.
- One bad clip kills trust.

#### Rights bar

- 6/6 refuse watermark removal.
- 6/6 refuse cloud-only for client footage.
- Ownership attestation, no third-party marks, no face/logo reconstruction.
- Client editor needs DPA; VibeCut can’t serve that with no accounts/cloud.

---

## 5. Loop 3 — founder and CTO

### 5.1 Founder verdict

The founder/CEO read the panel and decided:

1. **Paid v1: no change.** Cleanup is a real repair job, not a $249 switching trigger. 4–6 jobs/month at $99/10 and failures on faces/logos/moving text do not justify delaying the five gates. The paid v1 story job has the higher price and clearer trigger.
2. **Fund the long-source story flow first.** Refuse to call source-less cleanup a wedge until 20 real clips pass with zero smears. Refuse to call Overlay Studio or Hook Cards a wedge at all. Engineering is right: Flow 1 stays alpha-lab until quality proves itself.
3. **Cleanup is an add-on.** Not free, not a product line, not a separate product. Same local app, same buyer, separate $99/10 SKU. It becomes a product line only if 20% of paid v1 buyers run 10 cleanups in 90 days and support stays under 10 minutes per clip.
4. **Price:** paid v1 $249/$149; cleanup $99/10, $15 single, no subscription, no unlimited, no watermark, no cloud. Do not charge $20/mo for cleanup; four jobs/month. Do not price $150/10 for a client editor we cannot serve without seats/DPA.
5. **Three conditions before selling cleanup:**
   - 20-clip quality gate: 10 faces/skin tones/glasses, 5 logos/URLs, 5 moving text/ghost captions; zero face/logo smear; unremovable artifacts flagged; median review ≤5 min; Safe Crop, Cover Old Text, Text Check, Caption Rescue, Clean Master report.
   - Local-only and rights-safe: no cloud, no generative face/logo, no watermark, no training; 720p/24GB limits disclosed; original preserved.
   - Honest report and remedy: never say “clean” without verification; refund if a smear is missed or review >10 min. No “automatic clean enough” for faces/logos/moving text.
6. **Kill:** Overlay Studio, Hook Cards, Repair Clip Beta as a separate SKU, generative face/logo removal, watermark removal, cloud-only cleanup, auto-publish, team seats/review in v1. Seats are a separate studio SKU with DPA, not paid-v1.
7. **Wall:** “If I have to explain the smear, it is not clean.”
8. **As creator:** yes at $99/10 for archive/client clips; would not pay $20/mo for four jobs; walks if one face smears or footage leaves Mac.

### 5.2 CTO verdict

The CTO overruled the founder on price and the product lead on the wedge.

#### Final feature verdict

- **Flow 1: BUILD — deferred out of paid v1.**
  - Build now? No. No cleanup code enters 1.0.
  - Build after 1.0: Text Check, Safe Crop, Caption Rescue → free 1.1 trust fixes.
  - Cover Old Text + Clean Master → paid 1.3 add-on.
  - Alpha-lab only: Repair Clip Beta, manual-mask LaMa, 720p, ≤10s, 24GB, off by default, not sold.
  - Reject: full automatic text removal, generative face/logo removal, watermark removal, “clean anything.”
- **Flow 2: DEFER — not a paid feature.**
  - Overlay Studio ships at 1.2 as included retention only if 1.1 usage proves demand.
  - Hook Cards: rejected.
- **Paid v1 gets nothing from either flow.** The five gates remain binary.

#### Wedge

**Flow 1 cleanup is the wedge. Flow 2 overlay is not.**

Reason: 6/6 creators value cleanup more; archive repurposing is recurring, embarrassing, poorly served locally. CapCut/Descript/Canva own overlays.

But the wedge is narrow:

> Private, deterministic cleanup of owned talking-head footage with static/edge text, a visible quality report, and ≤5-minute review.

Not “AI remove anything.” Crop, cover, blur, manual mask, text detection, collision warning, and refusal when quality fails. General face/logo/moving-text removal is the false promise that failed H2.

Paid v1’s wedge remains the local story packet. Cleanup is the post-1.0 paid expansion wedge, not a reason to delay 1.0.

#### Packaging and price

**One model: “Cleanup Kit,” $149 one-time add-on to a paid v1 license. $99 for v1 owners in the first 90 days. Unlimited local jobs. 30-day refund. Not standalone. No subscription, per-clip price, credits, meter, watermark, or seats.**

Rejected:

- $99/10 and $150/10: metering contradicts flat local product; refund/support exposure.
- $15–20/clip: service anchor.
- $15–30/mo: subscription.
- $399 studio: implies seats/team product.

The client editor gets better economics: $149 once, unlimited. Leave short-term cash on the table to protect trust.

#### Feature sequence

| Release | Ship | Status |
|---|---|---|
| **1.0** | None of the eight | Paid v1, fix-only |
| **1.1** | Text Check, Safe Crop, Caption Rescue | Free trust fixes |
| **1.2** | Overlay Studio | Included retention; no SKU; defer if usage absent |
| **1.3** | Cover Old Text, Clean Master | Paid $149 add-on; deterministic only |
| **1.3 alpha-lab** | Repair Clip Beta | Invite-only, off by default, beta, not sold |
| **Killed** | Hook Cards | Commodity; never paid wedge |

Why 1.1 free: protects paid v1 caption promise; prerequisites for cleanup; charges for diagnosis before fix is bad. Builds dataset/trust.

Why Overlay Studio not paid: table stakes; build text layer, z-order, safe zones, packet hash only if retention data demands. No Hook Cards SKU, no hook matrix relaunch.

#### Quality and rights gates

**Sale gate: 60 clips from 12 sources and 10 creators.** Twenty is internal smoke, never sale.

- 100% zero P0: no face smear, logo smear, ghost caption, caption over mouth, visible drift.
- ≥90% no visible artifact at 1×.
- 100% static edge text clean.
- Residual OCR ≤0.5%.
- Review median ≤5 min static, ≤10 moving.
- Completion ≥80%.
- 100% quality report/rights attestation.

Rights gates:

1. Written ownership/permission attestation per source.
2. No watermark removal, DRM bypass, third-party logo removal.
3. Own-logo cover allowed only with attestation.
4. No generative face/voice alteration, no synthetic presenter.
5. No cloud upload, account, telemetry, publishing.
6. Every crop/cover/mask recorded with source hash, timestamp, method, model.
7. Refuse/refund any job failing attestation or impossible to clean without explanation.

#### Team/agency/cloud

**No seats, review, or cloud.** One license per Mac, one operator.

Client editors get versioned local links and ZIP packets, not comments/approvals/shared workspaces/SSO/audit logs/DPAs/cloud. That disqualifies part of the agency segment. Accept it. Adding seats/cloud creates a different product, gate, support burden, and the exact trust objection the panel raised.

Multiple Macs = multiple licenses. No team billing, shared library, remote review.

#### Validation before code or sale

**10 real Mom Tests, not six simulated personas.** One finished captioned video per creator. Paid concierge pilot at $99/10 before 1.3 code.

Must prove:

- 8/10 call output postable without explanation.
- 8/10 would pay $149 once or $99 launch.
- Median review ≤5 min static, ≤10 moving; 9/10 under 10 min.
- Zero accepted face/logo smear; zero watermark-removal requests fulfilled.
- 7/10 prefer cleanup over overlay after seeing both.
- Support ≤30 min/clip.
- At least 4/10 bring archive footage with baked captions; 3/10 client work.

If first four fail: **do not write 1.3 code.**

Then 60-clip automated gate before general sale. The 10-clip pilot proves demand/review economics; 60-clip gate proves quality. Neither substitutes.

#### Risks

1. One smear kills trust → deterministic only; manual override; zero P0; refund; never market generative.
2. Scope delays paid v1 → 1.0 freeze; no cleanup code before five gates; 1.3 separate.
3. Support/refund eats add-on → fixed $149, 30-day refund, supported macOS/format, review caps, pause sales if SLA slips.
4. Rights/legal exposure → attestation, no watermark/third-party logo/DRM, no generative faces, counsel-reviewed terms, audit report.
5. Commodity pressure from CapCut/Descript/Canva → compete on local custody, batch story packet, cleanup report; kill Hook Cards.

#### CTO quote

> “We will sell the local story packet in 1.0, make deterministic cleanup the post-1.0 paid wedge at $149 once, give overlays away as retention, and refuse clouds, seats, watermark removal, and generative smear in every release.”

---

## 6. Rebuilt roadmap

The CTO rebuilt the full roadmap in [ROADMAP_V2.md](ROADMAP_V2.md). Summary:

| Phase | Version | Scope | Gate |
|---|---|---|---|
| 0 | 0.14–0.15 | Free alpha; trust core; signed Mac beta | 3 clean Macs, 10 pilots, 20-source benchmark, no P0 |
| 1 | 1.0 “Postable Set” | Paid story workflow; no cleanup/overlay | Five gates + 20-source + dogfood + CTO sign-off |
| 2 | 1.1 “Same Object” | Trust fixes: Text Check, Safe Crop, Caption Rescue, cover previews, logs, CI | 30 days no P0; zero trust refunds |
| 3 | 1.2 “Overlay Studio” | Hook/caption overlays, templates, safe zones | Conditional on ≥30% usage; no SKU |
| 4 | 1.3 “Cleanup Kit” | Crop, cover, blur, manual masks, text detection, quality report | 10 real Mom Tests + pilot; 60-clip gate; $149/$99 |
| 5 | 2.0 | Selection Edge, Repost Library, Chapters | Separate conditional gates |
| 6 | Alpha-lab | Repair Clip Beta, 720p/≤10s/24GB, not sold | Promote only through separate gate |

### Outstanding ledger

**Verify/close at `b7596db`:** auth/admin, disk, story caption lineage, 4:5, versions, crash/timeout/queue, packet pin/reload, job index/search, delete receipt.

**Still open for 1.0:** signed `.app`/notarization/license/launchd, 20-source proof, story-item retry, packet artifact refs, stale queued-manifest reconciliation, review-token re-copy, screenshot QA, macOS CI, all-JS checks, 24h soak, logs/diagnostics, rollback.

**1.1:** exact cover previews, legacy caption-count normalization, packet metadata persistence, source purge audit, rotating logs, full macOS CI, screenshot regression, 100-job search p95.

**1.2:** Overlay Studio conditional. **1.3:** Cleanup Kit gated. **2.0:** Selection Edge, Repost Library, Chapters conditional. **Alpha-lab:** Repair Clip Beta. **Killed:** Hook Cards, hook/cover matrix, cleanup/overlay in 1.0.

---

## 7. Final verdict

> **VibeCut 1.0 sells the local story packet. 1.1 makes text safe. 1.2 gives overlays away. 1.3 sells deterministic cleanup at $149 once. Generative removal, watermark removal, clouds, seats, and “clean anything” are not the product.**

### What changes now

- No code change to paid 1.0.
- No cleanup/overlay feature in 1.0.
- 1.1 gets Text Check, Safe Crop, Caption Rescue as free trust fixes.
- Cleanup starts only after 10 real Mom Tests + paid concierge pilot.
- If cleanup passes, 1.3 Cleanup Kit at $149/$99.
- Overlay Studio is conditional 1.2 retention.

### What does not change

- Five paid-v1 gates.
- Local-first, no cloud, no accounts, no team seats.
- No watermark removal.
- No generative face/logo repair.
- No subscription, credits, meter, or per-clip pricing.
- Hook Cards killed.
- No cleanup/overlay in 1.0.

### Next validation

1. Recruit 10 real creators, one finished captioned video each.
2. Run the exact Mom Test script; do not pitch.
3. Run the paid concierge pilot at $99/10.
4. Measure postable, price, review time, smear rate, support.
5. If the first four conditions pass, build the deterministic Cleanup Kit.
6. Run the 60-clip/12-source/10-creator gate.
7. Only then sell the $149 add-on.

---

## Appendix A — Rights and safety

- Ownership/permission attestation per source.
- No watermark/DRM/third-party logo removal.
- Own-logo cover only with attestation.
- No generative face/voice alteration.
- No cloud/account/telemetry/publishing.
- Removal log with source hash, method, model, timestamp.
- Original preserved; output provenance sidecar.
- Refuse and refund if attestation fails.
- Always provide a replacement SRT/transcript when captions are removed; never treat OCR of removed text as the new transcript.
- Disclose SSD physical-erase limits; app-level deletion only.

## Appendix B — Quality gates

### Concierge pilot

- 10 real creators; one finished captioned video each.
- 8/10 postable without explanation.
- 8/10 pay $149 or $99.
- 9/10 review under 10 min; median ≤5 static/≤10 moving.
- Zero accepted face/logo smear.
- Zero watermark-removal requests fulfilled.
- 7/10 prefer cleanup over overlay.
- Support ≤30 min/clip.
- 4/10 archive, 3/10 client work.

### General sale

- 60 clips / 12 sources / 10 creators.
- Zero P0: face/logo smear, ghost caption, caption over mouth, drift.
- ≥90% no visible artifact at 1×.
- 100% static edge text clean.
- Residual OCR ≤0.5%.
- Review ≤5 static/≤10 moving.
- Completion ≥80%.
- 100% quality report/rights attestation.

## Appendix C — Open questions

1. Exact macOS minimum and Apple Silicon/8GB support.
2. Native Swift launcher vs bundled Python runtime.
3. Model bundle size and licensing.
4. Cleanup add-on EULA, refunds, rights attestation wording.
5. 90-day $99 window start date.
6. Overlay usage threshold and whether Overlay Studio stays free.
7. Merchant of Record/tax/refund processor.
8. Support engineer before seat 51.

## Appendix D — Research signals

Current local/remote research during this round:

- local VSR/ProPainter/E2FGVI/STTN/LaMa pipelines for burned-in subtitle removal;
- Apple Vision OCR for macOS; PaddleOCR/RapidOCR alternatives;
- ProPainter/E2FGVI quality vs speed; CUDA/VRAM limits; 720p/1080p memory;
- commercial cloud removers (Runway, HitPaw, Media.io, Veed) and their privacy/quality limits;
- OCR-to-SRT local tools; burned-in subtitle OCR;
- overlay commodity: CapCut, Descript, Canva, Premiere MOGRTs;
- local-only, source-less, reviewable cleanup remains the gap.

These are research signals, not validated vendor claims or customer evidence.

---

*Round 4 complete. Simulated panel; no feature code changed. CTO roadmap in [ROADMAP_V2.md](ROADMAP_V2.md).* 
