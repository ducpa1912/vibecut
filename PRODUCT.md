# Product

> Status 2026-11-12: local-only macOS app, about 75 % complete by the founder's estimate (11 Nov; not restated since). 178 tests.
> Brief loops 7–9 (ink check, moving fill, rules) are closed; PLAN loops 7–9 are open. App Store
> work is paused. Build order: `PLAN.md`. Open work: `TODO.md`. Contract: `AGENTS.md`.

<!-- impeccable:product-schema 1 -->

**DuckSuite** is the offline macOS product. VibeCut Studio is the frozen reference codebase; where
this file and the build disagree, the build wins and this file is corrected.

## Platform

macOS 26.0+ on Apple silicon. The floor comes from SpeechAnalyzer and FoundationModels; lowering it
is a feature change. Distribution: Mac App Store, paused until the product is good. Web products come
later, in this order: DuckClean, DuckClassic, DuckStudio.

## Product family

| Product | Buyer | Job | Surface | Price |
|---|---|---|---|---|
| **DuckSuite** | Mac creator-editor | One long video → scenes found, old text cleaned, script/captions/voice, 1080p render | Mac app | **$29 one-time** |
| **DuckClean** | Anyone with one finished video and old text | Upload, clean burned-in text, download | Web (Classic lane) | Free trial; paid CPU; GPU waitlist |
| **DuckClassic** | Operator / automation buyer | Cloud clean and quick render, API, credits | Web | Credits |
| **DuckStudio** | Non-Mac creator or team | Full cloud suite | Web | Subscription / credits |

DuckSuite is the only product being built.

## DuckSuite

**One sentence:** DuckSuite turns one long video into the few clips you will actually post — old text
cleaned, captions timed, voice or dub added — on your Mac, for one price.

```text
Welcome → Check → Edit ⇄ Clean focus → Preview → Render
```

One project at a time. One 48 px toolbar: `Check · Edit · Preview · Render`, status, queue, settings.

- **Check** finds scene cuts, transcript, on-screen text and story candidates. It also reads frame 0,
  the frame after every cut and onset moments.
- **Edit** is a three-panel desk (scenes, preview with transcript overlay, inspector) over one
  timeline, with focus modes for Script, Audio, SFX and Clean.
- **Clean** gives one layer per text line: LaMa fill, Blur or Off. The fill hole is each letter's
  own strokes, grown 6 px, for as long as that letter is on screen. A line over a moving background
  is flagged `moves`.
- **Preview** plays before / compare / after. Proofs are optional; render never waits for one.
- **Render** writes one 1080p MP4 at the source aspect, 24 or 30 fps, through a local queue, then
  judges every cleaned letter on every frame near its line against the source, and reports frames
  checked, leftover found, lines it could not check, and flicker.

### Shipped, planned, deferred

| Area | In the build today | Planned (`PLAN.md`) | Deferred or cut |
|---|---|---|---|
| Import | One local file, picker or Finder drag; append to the same project | Creator-readable error copy (loop 8) | URL / path import |
| Check | Scenes, transcript, Vision OCR, stories, true first frame, cut/onset stills | — | Faces, saliency, music as product features |
| Clean | Ink hole, GPU LaMa default, CPU pack optional, `moves` flag, flash < 0.6 s → Blur, Clean all confirms and reports counts, stroke-shaped hole, post-render letter check with one refill | Better fill on moving footage (loop 5) | Model picker for the default |
| Script | Transcript, translate (en / vi / zh), rewrite (clean / short / punchy) with Apple Intelligence or a basic cleanup shown in the UI, captions + SRT | — | Publish kit, titles, hashtags |
| Voice | macOS voices, Kokoro pack, dub, music and SFX on one audio track | Manual microphone test (loop 8) | Voice cloning |
| Edit | Trim, stories, media beats, filters; layer count and a fade in the inspector; empty timeline lanes collapse to a `+` row | Split, reorder, remove silence | Grading, LUTs, keyframes |
| Render | Source aspect, 1080p, 24/30 fps, H.264/AAC, two-column screen with the estimate and the leftover-text check on the left, queue and finished cards on the right | — | Aspect switching, auto-frame, 4K, 60 fps, HDR, ProRes |
| Models | LaMa bundled (GPU); Whisper + Kokoro optional packs; translation from a user CTranslate2 folder; **a user fill model** (ONNX or TorchScript) runs in place of LaMa | Local slots for transcription, LLM URL and voice (PLAN loop 7); SHA-256 per pack (PLAN loop 8) | Any translation weights shipped or hosted by DuckSuite |
| Cloud | None. Nothing uploads | — | User keys after v1; cloud render plans |

### Known limits, stated plainly

- **LaMa cannot rebuild a background it never saw.** Most lines sit on moving footage; those carry a
  `moves` badge and can smear.
- **The leftover-text check judges only lines that have a clean layer.** A line under 5 frames long,
  or with no steady strokes, cannot be told from scenery: it is shown as "not checked", never as
  clean. Text that Check did not find is not judged.
- **GPU fill is fast, not instant.** Cold render on the review project: 698 s (11 min 38 s) for
  160 s of video; CPU fill is 4.6× slower or worse under load.
- **Vietnamese transcription needs the Whisper pack** (1.61 GB). Apple Speech does not transcribe it.
- **Apple Intelligence must be enabled** for rewrite; without it the rewrite is a basic cleanup.
- **macOS 26 only.**

### Decisions in force

- **$29 one-time.** No account, no in-app purchase. Restore is the App Store's, by Apple ID.
- **v1 is completely local.** No telemetry, no upload, no keys. A step may take a user-supplied local
  model; none requires a download.
- **One shipped model: LaMa.** Every other model step takes a local default or a user-supplied local
  model. The UI names no model for a user slot and links no download.
- **Text clean is LaMa fill or explicit Blur.** Never a silent switch to blur.
- **Dub is required**, with an editable script in English, Vietnamese and Chinese.
- **1080p, 24 or 30 fps.** No LUTs, no grading, no publish kit.
- **Do not hide a limit.** Measure it and show it.

### Pricing

| Offer | Price | State |
|---|---:|---|
| DuckSuite app | **$29 one-time** | The only offer being built |
| DuckSuite Render (CPU) | $5/month | Deferred |
| DuckSuite Render Plus (GPU) | $20/month | Deferred |

## Other lanes (roadmap, not being built)

- **DuckClean** — clean-only web flow from the Classic lane: upload → detect → fill or blur → download.
- **DuckClassic** — cloud clean and quick render, credits, API, templates, batch.
- **DuckStudio** — full cloud suite for non-Mac users; not Phase 1.

## Users

A solo creator-editor on Apple silicon with one long recording and a deadline, who values local
custody, a flat price and a file they keep.

## Operating context

One Mac, one project, one source. Footage may belong to a client: nothing leaves the Mac in v1. The
app must work offline after optional packs are installed. The reference machine is the smallest one:
M1, 8 GB. A limit that shows there is a product limit.

### Non-goals for v1

720p/2K/4K/60 fps/HDR/ProRes/10-bit · LUTs and grading · B-roll and stock libraries · multi-video
projects · publish kit and cover variants · batch, templates, API, automation · voice cloning,
generated music · a DuckSuite account, key or proxy · URL import · admin console, telemetry.

## Brand and craft

- The family name is **Duck**; the Mac product is **DuckSuite for Mac**.
- Copy is plain and honest: state the limit, give a route to fix the error, never present a score as
  proof.
- One accent: amber. Blue only for cloud status. Red only for destructive/error.
- Daylight workbench with a dark video canvas.
- WCAG 2.2 AA target: visible focus, 200 % zoom, keyboard paths, screen-reader labels, live regions,
  colour never the only signal. Test at 1024×700, 1280×800 and 1440×900.

## Product principles

1. **Local custody beats cloud convenience.**
2. **One object through every change.** No silent fork or overwrite.
3. **Fail visibly and recover.** Real reason, real time left. No fake ETA, no silent fallback.
4. **No silent quality downgrade.** Fill default; missing model fails visibly; blur is a choice.
5. **Sell hours, not infinity.** Any cloud plan has a visible cap and a measured cost.
6. **Ship the small thing.** A utility suite, not a mini-Studio.
7. **Build before planning more.** One plan, one loop, one commit.
