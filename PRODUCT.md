# Product

<!-- impeccable:product-schema 1 -->

Recorded 2026-11-07. This file supersedes the VibeCut Studio $249 plan. VibeCut Studio is the frozen reference codebase; **DuckSuite** is the new offline macOS product. The previous plan remains in git history and is marked historical in `PRD.md` and `docs/handoff/commercial-packaging-plan.md`.

Distribution: [docs/duck/DISTRIBUTION.md](docs/duck/DISTRIBUTION.md). Commercial: [docs/duck/COMMERCIAL.md](docs/duck/COMMERCIAL.md).

## Platform

macOS 26+ on Apple Silicon. DuckSuite ships through the Mac App Store. The web products ship later, in this order: DuckClean, DuckClassic, DuckStudio.

## Product family

| Product | Buyer | Job | Surface | Price |
|---|---|---|---|---|
| **DuckSuite** | Mac creator-editor | Dissect one long video, detect what is there, clean old text, add captions, voice or dub, cut a short, render 1080p, export. | Mac App Store app | **$29 one-time**; optional cloud render |
| **DuckClean** | Anyone with one finished video and old text | Upload, find burned-in text, clean it, download. No timeline. | Web, **shipped from the Classic lane** | Free trial; paid CPU; Express GPU waitlist |
| **DuckClassic** | Operator or automation buyer | Cloud clean/quick render, API, templates, credits. Not a pro editor. | Web | Credits |
| **DuckStudio** | Non-Mac creator or team | Full cloud suite: assets, edit, captions, voice, clean, publish, collaboration. | Web | Subscription or credits |

DuckSuite is the only product in Phase 1. The other three are roadmap, not launch scope.

## DuckSuite

**One sentence:** DuckSuite turns one long video into the few clips you will actually post — old text cleaned, captions timed, voice or dub added — on your Mac, for one price.

```text
Import → Analyze → Edit → Render → Export
```

- **Import** takes one local file: MP4, MOV or M4V. No path field, no URL downloader.
- **Analyze** has two tabs: **Moments** (Dissect) and **Footage check** (Detect).
- **Edit** holds the simple tools: Cut, Frame, Captions, Text, Clean, Voice, Music.
- **Render** produces one 1080p file at 24 or 30 fps, in 9:16, 4:5, 1:1 or 16:9.
- **Export** saves MP4, SRT and a cover image. No publish kit, no review links, no versions.

### Phase 1 must-haves

- **Smart stories are core.** One long video is segmented, read with local OCR and transcript, and ranked into story candidates with hook/payoff evidence. This is DuckSuite’s USP; it is not removed. There is no multi-set comparison UI at launch.
- **Dub is required.** Voice-over and dub both ship. Dub uses Apple Translation plus local TTS, with an editable script and three launch languages: English, Vietnamese and Chinese. If quality is weak, label it beta; do not cut it.
- **1080p only.** No 720p, 2K, 4K, 60 fps, HDR or ProRes.
- **24 and 30 fps only.** Source may be other rates; output is 24 or 30.
- **No LUTs, no colour grading.** The Color tool and LUT import are removed from DuckSuite. Simple brightness is not a feature; keep the picture as shot.
- **No publish kit.** No titles/hashtags/description generator, covers, review links, versions, apply-look or packet. Export files only.
- **Text clean is LaMa AI fill or explicit Blur.** No model picker, no GPU toggle, no STTN/Telea/Navier-Stokes in the local app.
- **Local is complete.** No account. No telemetry. No upload unless the user chooses Cloud render.
- **Core models are bundled.** LaMa ONNX, LGPL ffmpeg, ONNX Runtime and the prebuilt Apple helpers ship inside the app. Optional voice/dub language packs are data downloads with checksum and signature, never code.
- **Cloud render is optional.** Free CPU first, then paid CPU. GPU is a later evaluation, not a Phase 1 promise.

### Pricing

| Offer | Price | Includes |
|---|---:|---|
| DuckSuite app | **$29 one-time** | All local v1 tools; 1.x bug fixes and macOS compatibility |
| DuckSuite Render | **$5/month** | 10 render hours, CPU, 1080p, up to 3 concurrent |
| DuckSuite Render Plus | **$20/month** | 10 GPU render hours, 1080p, up to 3 concurrent — only after the GPU gate |
| Overage | **$0.50/render hour** CPU; **$2.50/render hour** GPU | No auto-charge |

**Render hour = one hour of worker wall-clock, not one hour of finished video.** The app shows an output estimate from measured speed. No unlimited plan.

## DuckClean

**DuckClean ships from the Classic lane, not Studio.**

- New `DUCKCLEAN` profile composed from `CLASSIC` in `core/profiles.py`.
- Entry point: `classic_app.py` / a thin `duckclean_app.py` that configures the profile before importing the shared backend.
- Reuses Classic's `check`, `cleanup`, `ai_fill` and render pieces.
- No Studio page, no stories, no Edit document, no Studio queue, no Studio timeline.
- Clean-only flow: upload → detect text → choose AI fill or blur → download.
- Free trial on HF free CPU. Paid CPU follows. Express is a T4/on-demand waitlist.
- Linux OCR must be tested on 40–60 real clips. If it fails, DuckClean uses a Mac OCR worker or stays Mac-assisted.

## DuckClassic

Cloud clean and quick render for operators and automation buyers.

- Credits, API render, templates, batch clean, quick queue.
- Not a pro video editor; no colour grading, no multi-track NLE, no publish suite.
- Reuses the DuckClean/DuckSuite render broker and worker image.

## DuckStudio

Full cloud suite for non-Mac users.

- Assets, editing, captions, voice, clean, publish, collaboration.
- Not Phase 1. Do not build shared tenancy, accounts or team features before DuckSuite and DuckClean are paying.

## Users

### DuckSuite

A solo creator-editor on Apple Silicon with one long recording or one finished video and a deadline. They want the few clips they will post, not a clip farm. They value local custody, a flat price and a file they keep.

### DuckClean

A repurposer with one finished video and old burned-in text. They do not want a timeline. They want upload, clean, download.

### DuckClassic

An operator or automation buyer who wants repeatable cloud clean/render through a simple UI or API.

### DuckStudio

A non-Mac creator or small team that wants the full suite without installing anything.

## Positioning

DuckSuite is the local Mac essential toolkit for creators who will not upload client footage or pay per clip. It does the few jobs that matter — dissect, detect, clean, voice, dub, edit, export — and leaves the pro NLE and the publish suite to other products.

## Operating context

- One Mac, one project, one source. Long sessions; renders can take far longer than the video when AI fill runs.
- Footage may belong to a client. Custody, deletion and honest cloud consent matter.
- The app must work offline after models are installed and the app is purchased.
- The Mac App Store is the only Phase 1 distribution channel. No Sparkle, no license key, no direct DMG.
- App Review is a gate, not a final step. Sandbox, bundled code, model distribution and StoreKit are designed in from Day 1.

## Capabilities and constraints

- **Dissect:** scene cuts, transcript, 3–8 moment candidates, hook/payoff evidence, manual moment builder.
- **Detect:** on-screen text, faces, saliency, speech, music, basic quality warnings. No score.
- **Clean:** one layer per real text; LaMa AI fill default; explicit Blur; manual box; before/after; no silent blur fallback.
- **Voice-over:** local TTS with Apple voices and Kokoro. No cloud keys, no cloning.
- **Dub:** Apple Translation plus local TTS; editable script; three launch languages; beta label.
- **Edit:** trim, split, reorder, remove silence; 9:16, 4:5, 1:1, 16:9; auto-frame; captions; text; music.
- **Render:** 1080p, 24/30 fps, MP4 H.264/AAC; local queue; optional cloud render.
- **Export:** MP4, SRT, cover JPG; Save, Reveal, Share, Copy captions.
- **Models:** bundled core; optional data packs with SHA-256 and signature.
- **Cloud:** opt-in per project; free CPU then paid CPU; GPU only after benchmark.
- **App Store:** sandboxed, StoreKit 2, no downloaded executable code, LGPL ffmpeg, prebuilt Apple helpers.

### Non-goals for DuckSuite v1

- 720p, 2K, 4K, 60 fps, HDR, ProRes, 10-bit.
- LUTs, colour grading, effects, motion keyframes, borders, stickers.
- B-roll, stock assets, photo import, multi-video projects.
- Publish kit, titles/hashtags/description, cover variants, review links, versions, apply-look, packet.
- Batch across projects, templates, API, automation.
- Voice cloning, cloud voices, generated music, cloud provider keys.
- URL/XHS/path import.
- Multi-set comparison UI, strength score, queue-all from Moments. Smart story finding itself stays.
- STTN/MI-GAN/Telea/Navier-Stokes picker, GPU toggle, follow-camera toggle.
- Admin console, Classic, LAN review links, telemetry, analytics.

## Brand commitments

- The family name is **Duck**. The Mac product is **DuckSuite for Mac**. The cloud products always carry their descriptor: **DuckClean**, **DuckClassic**, **DuckStudio**.
- The duck is a mark, not a mascot. No cartoon behaviour in the product.
- Copy is plain and honest: state the limit, give a route to fix the error, never present a score as proof.
- One accent: amber. Blue only for cloud status. Red only for destructive/error.
- DuckSuite feels like a daylight workbench with a dark video canvas. DuckClean is white and calm. DuckClassic is dense and quick. DuckStudio is dark and full.

## Evidence on hand

- Existing VibeCut Studio code: local pipeline, Apple Vision/Speech, LaMa/MI-GAN/STTN, render queue, Classic lane.
- Founder decisions, 2026-11-06/07: $29 Mac App Store app; $5/$20 render; dub required; 1080p only; 24/30 fps; no LUTs/colour grading; no publish kit; DuckClean from Classic lane.
- No signed app proof, no App Store approval, no 20-source DuckSuite benchmark, no paying DuckSuite customers, no measured GPU render, no Linux OCR proof.

Do not invent proof. The roadmap gates are the evidence plan.

## Product principles

1. **Local custody beats cloud convenience.** The Mac app is complete without an account.
2. **One object through every change.** A project, edit, render and export never silently fork or overwrite.
3. **Fail visibly and recover.** Show the real reason and the real time left. No fake ETA, no silent fallback.
4. **No silent quality downgrade.** AI fill default; missing model fails visibly; blur is an explicit choice.
5. **Sell hours, not infinity.** Every cloud plan has a visible cap and a measured cost.
6. **Ship the small thing.** DuckSuite is a five-tool utility suite, not a mini-Studio.

## Accessibility and inclusion

WCAG 2.2 AA is the target for DuckSuite and DuckClean: visible focus, 200% zoom, keyboard paths, screen-reader labels, live regions for render/queue/model download, colour never the only signal, reduced motion, and captions for sample videos. Minimum 12 px labels, 13 px panel body, 15 px body. Test at 1024×700, 1280×800 and 1440×900.
