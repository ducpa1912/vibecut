# Product

> Status 2026-11-11: the build is local-only and about 70% complete by the founder's own estimate. App Store work is paused. Build order: `PLAN.md`. Open work: `TODO.md`. Contract: `AGENTS.md`.

<!-- impeccable:product-schema 1 -->

Recorded 2026-11-07, revised 2026-11-11 (REQ-20261111-05) to match the build and the decisions taken since. VibeCut Studio is the frozen reference codebase; **DuckSuite** is the offline macOS product. Where the 7 Nov record and the build disagree, this file now says which is shipped, which is planned and which is deferred.

Distribution: [docs/duck/DISTRIBUTION.md](docs/duck/DISTRIBUTION.md) (paused). Commercial: [docs/duck/COMMERCIAL.md](docs/duck/COMMERCIAL.md).

## Platform

macOS 26.0+ on Apple silicon. The floor comes from SpeechAnalyzer and FoundationModels; lowering it is a feature change. The intended channel is the Mac App Store; that work is paused until the product is good. The web products come later, in this order: DuckClean, DuckClassic, DuckStudio.

## Product family

| Product | Buyer | Job | Surface | Price |
|---|---|---|---|---|
| **DuckSuite** | Mac creator-editor | Take one long video, find the scenes, clean old text, edit script, captions and voice, render 1080p. | Mac app | **$29 one-time** |
| **DuckClean** | Anyone with one finished video and old text | Upload, find burned-in text, clean it, download. No timeline. | Web, **shipped from the Classic lane** | Free trial; paid CPU; Express GPU waitlist |
| **DuckClassic** | Operator or automation buyer | Cloud clean/quick render, API, templates, credits. Not a pro editor. | Web | Credits |
| **DuckStudio** | Non-Mac creator or team | Full cloud suite: assets, edit, captions, voice, clean, publish, collaboration. | Web | Subscription or credits |

DuckSuite is the only product being built. The other three are roadmap.

## DuckSuite

**One sentence:** DuckSuite turns one long video into the few clips you will actually post — old text cleaned, captions timed, voice or dub added — on your Mac, for one price.

```text
Welcome → Check → Edit ⇄ Clean focus → Preview → Render
```

One project at a time. One 48 px toolbar: `Check · Edit · Preview · Render`, status, queue, settings. No project tabs.

- **Check** finds scene cuts, transcript, on-screen text and story candidates. The editor opens while it runs.
- **Edit** is a three-panel desk (scenes, preview with transcript overlay, inspector) over one timeline, with focus modes for Script, Audio, SFX and Clean.
- **Preview** plays before / compare / after. Proofs are optional; render never waits for one.
- **Render** writes one 1080p MP4 at the source aspect, 24 or 30 fps, through a local queue.

### What is shipped, planned, deferred

| Area | In the build today | Planned (`PLAN.md`) | Deferred or cut |
|---|---|---|---|
| Import | One local file, picker or Finder drag; append to the same project | Creator-readable error copy | URL / path import |
| Check | Scenes, transcript, Vision OCR, stories; true first frame read | — | Faces, saliency, music detection as product features |
| Clean | One layer per text line; LaMa fill or Blur or Off; `moves` flag; flash under 0.5 s defaults to Blur; Clean all confirms and reports counts | Time estimate before render (loop 1); faster fill (loop 3); better fill on moving footage (loop 5) | Model picker for the default; GPU toggle |
| Script | Transcript, translate (en / vi / zh), rewrite (clean / short / punchy), captions with style and SRT | Rewrite without the hidden Ollama fallback (loop 6) | Publish kit, titles, hashtags |
| Voice | macOS voices, Kokoro pack, dub, music and SFX rows on one audio track | Manual microphone test | Voice cloning |
| Edit | Trim, stories, media beats, filters | Split, reorder, remove silence | Colour grading, LUTs, keyframes |
| Render | Source aspect, 1080p, 24/30 fps, H.264/AAC, queue scoped to the project | Render screen layout (loop 9) | 9:16 / 4:5 / 1:1 / 16:9 switching, auto-frame, 4K, 60 fps, HDR, ProRes |
| Models | LaMa bundled; Whisper and Kokoro as optional data packs; translation from a user-supplied CTranslate2 folder | Local slots for Whisper, LLM URL, ONNX voice, ONNX fill; user keys in the Keychain (loop 7); SHA-256 per pack (loop 8) | Any translation weights shipped or hosted by DuckSuite |
| Cloud | None. Nothing uploads. | User-key providers, off until ticked, consent per task | Cloud render plans, render broker |
| Store | No StoreKit code. $29 paid app restores through the buyer's Apple ID | — | Signing, TestFlight, review: paused |

The "in the build" column follows the Done list in `TODO.md` and the code read on 2026-11-11; it was not re-tested by hand in this revision.

### Known limits, stated plainly

- **AI fill is slow.** LaMa runs per frame on the CPU. On an M1 with 8 GB, a 160 s video with 64 s of text can take hours on a cold cache. The app does not yet show that estimate before a render starts.
- **AI fill is weak on moving footage.** It cannot rebuild a background it never saw. In the review project 33 of 41 text lines sit on moving footage. Those lines carry a `moves` badge.
- **Vietnamese transcription needs the Whisper pack** (1.61 GB). Apple Speech does not transcribe Vietnamese.
- **Apple Intelligence must be enabled** for rewrite; without it the rewrite is a basic cleanup.
- **macOS 26 only.**

### Decisions in force

- **$29 one-time.** No account, no in-app purchase, no login. Restore is the App Store's, by Apple ID.
- **Local is complete.** No telemetry, no upload path. A user key opts one task into that user's own provider, after consent.
- **One shipped model: LaMa.** Every other model step takes a local default, a user-supplied local model, or a user key. No step requires a download. The UI names no model for a user slot and links no download.
- **Text clean is LaMa fill or explicit Blur.** A line over a moving background is flagged, never silently switched to blur.
- **Dub is required**, with an editable script and three languages: English, Vietnamese, Chinese.
- **1080p, 24 or 30 fps.** No LUTs, no colour grading, no publish kit.
- **Do not hide a limit.** Measure it and show it.

### Pricing

| Offer | Price | State |
|---|---:|---|
| DuckSuite app | **$29 one-time** | The only offer being built. All local tools; 1.x bug fixes and macOS compatibility |
| DuckSuite Render (CPU) | $5/month | Deferred. Founder decision of 2026-11-06; nothing in the build |
| DuckSuite Render Plus (GPU) | $20/month | Deferred behind a GPU benchmark |

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

- One Mac, one project, one source. Long sessions; a render can take far longer than the video when AI fill runs.
- Footage may belong to a client. Custody and deletion matter; nothing leaves the Mac without a key the user added and a consent the user gave.
- The app must work offline after optional packs are installed.
- The reference machine is the smallest one: M1, 8 GB RAM. A limit that shows there is a product limit.

### Non-goals for DuckSuite v1

- 720p, 2K, 4K, 60 fps, HDR, ProRes, 10-bit.
- LUTs, colour grading, motion keyframes.
- B-roll libraries, stock assets, multi-video projects.
- Publish kit, titles/hashtags/description, cover variants, review links, versions.
- Batch across projects, templates, API, automation.
- Voice cloning, generated music.
- A DuckSuite account, a DuckSuite key, a proxy, or any shipped provider key.
- URL/XHS/path import.
- Multi-set comparison UI, strength score, queue-all from stories.
- Admin console, Classic, LAN review links, telemetry, analytics.

## Brand commitments

- The family name is **Duck**. The Mac product is **DuckSuite for Mac**. The cloud products always carry their descriptor: **DuckClean**, **DuckClassic**, **DuckStudio**.
- The duck is a mark, not a mascot. No cartoon behaviour in the product.
- Copy is plain and honest: state the limit, give a route to fix the error, never present a score as proof.
- One accent: amber. Blue only for cloud status. Red only for destructive/error.
- DuckSuite feels like a daylight workbench with a dark video canvas. DuckClean is white and calm. DuckClassic is dense and quick. DuckStudio is dark and full.

## Evidence on hand

- 83 automated tests; a ground-truth fill benchmark (`scripts/bench_fill.py`): the tighter fill hole gained +1.1 dB PSNR on the review project and +0.8 dB on a second one.
- One review project, 160 s, 1080×1920: captions were gone at 2 s, 10 s and 90 s in the last render; the 0 s title fix is proven on the source but not yet in a render.
- Session record and request log: `docs/reports/SESSION.html`, `MEMORY.md`.
- Not on hand: a render made with the current fill version, a measured GPU or CoreML fill, a signed app, an App Store review, a clean-Mac install, a manual microphone test, a second tester, a paying customer.

Do not invent proof. `PLAN.md` is the evidence plan.

## Product principles

1. **Local custody beats cloud convenience.** The Mac app is complete without an account.
2. **One object through every change.** A project, edit, render and export never silently fork or overwrite.
3. **Fail visibly and recover.** Show the real reason and the real time left. No fake ETA, no silent fallback.
4. **No silent quality downgrade.** AI fill default; missing model fails visibly; blur is an explicit choice.
5. **Sell hours, not infinity.** Any future cloud plan has a visible cap and a measured cost.
6. **Ship the small thing.** DuckSuite is a utility suite, not a mini-Studio.
7. **Build before planning more.** One plan (`PLAN.md`), one loop, one commit.

## Accessibility and inclusion

WCAG 2.2 AA is the target for DuckSuite and DuckClean: visible focus, 200% zoom, keyboard paths, screen-reader labels, live regions for render/queue/model download, colour never the only signal, reduced motion, and captions for sample videos. Minimum 12 px labels, 13 px panel body, 15 px body. Test at 1024×700, 1280×800 and 1440×900.
