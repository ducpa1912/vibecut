# Product

<!-- impeccable:product-schema 1 -->

Recorded 2026-11-06 from `PRD.md`, `FOUNDER_BRIEF.md`, `ROADMAP.md`, the Studio code and the founder's answers. This file describes VibeCut Studio. Classic is a second product with its own roadmap and release (`docs/handoff/lane-split-decisions.md`).

## Platform

web

A browser page served by a local Python app on the creator's Mac. The planned paid build wraps it as a signed Mac app.

## Users

Two users count equally.

- **Long-recording creator.** A technical solo creator-editor on Apple Silicon with 20–120-minute podcasts, interviews, courses or livestreams, shipping 3–10 shorts a week, sometimes with client footage and a deadline. The job is to find the moments worth posting, fix them and hand over a finished file without opening an editing suite.
- **Repurposer.** Someone reworking a finished video for a new platform, shape or language. The job is to remove old burned-in text, reframe, add new captions, voice and music, and render the whole video or part of it.

Both value local files and flat cost. Neither will accept a meter, a watermark or a mandatory cloud. A small studio with one operator is a secondary case, with no seats, comments or approvals.

## Product Purpose

VibeCut Studio is a local Mac workstation that takes one video through four steps:

```text
Import → Moments → Edit → Finish
```

- **Import** takes a file, a path or a link, then reads scenes, speech and on-screen text.
- **Moments** finds moments worth posting, or opens the whole video for editing.
- **Edit** holds one document per moment and shape, with Clean, Framing, Motion, Color, Text, Captions and Audio layers on one timeline.
- **Finish** reviews the frame, renders through a queue that can stop and resume, and builds publish kits and review links.

Success means the creator gets the few pieces they will actually post, with text, captions and copy already right, from their own machine.

**Planned paid v1, not yet shipped.** One eligible 30–120-minute recording gives at least three stories you would post, each with captions and a packet that is still there tomorrow, or your money back (two stories for 20–29 minutes). $249 one-time. It stays blocked until gates G1–G5, the 20-source benchmark and the founder's acceptance pass. See `PRD.md` and `ROADMAP.md`.

## Positioning

The local Mac video workstation for creators who will not upload client footage or pay per clip. The heavy work, including AI text removal, runs on the creator's own machine, and every render is a file they keep.

## Operating Context

- Long sessions on one Mac, often leaving a render running while doing something else.
- macOS on Apple Silicon. The founder's test machine is an Apple M1 with 8 GB.
- Renders can take far longer than the video when AI fill runs, so progress, honest time left and safe stopping are part of the job.
- Footage may belong to a client, so custody and deletion matter.
- The founder tests by hand on real files. Automated tests are code checks only.

## Capabilities and Constraints

- **Text removal:** the scan finds each line of on-screen text with its own box and time, and plans the fill per line from how much the picture moves around it. Layers can be AI fill or blur. LaMa is the default engine; STTN, Telea and Navier-Stokes are optional.
- **Rights:** all found text can be cleaned. A watermark, handle or logo needs a tick for that video.
- **Shapes and quality:** 9:16, 4:5, 1:1, 16:9 and 16:10; six quality tiers from 360p to 4K.
- **Import limits, per video:** 10 GB per upload and 2 GB per XHS download, plus a free-disk check.
- **Local first:** import, scan, edit, render and packet work with the network off. Cloud is opt-in for music, voice, transcription and AI text, with the creator's own key.
- **Refused for the Mac product:** accounts, cloud sync, seats, subscriptions, credits, publishing or platform APIs, analytics, virality scores, telemetry, auto-posting, generative face or logo repair, avatars, stock B-roll, and silently overwriting or retargeting a finished render. A render that stops never restarts by itself; resume is one click.
- **Undecided:** the hosted render-as-a-service plan in `docs/raas-distribution-plan.md` is plan only and would reverse some rules above for a different buyer. Founder sign-off is required first.
- **Undecided:** voice cloning is refused in `ROADMAP.md`, yet Studio ships a gated `voice_clone` feature in Setup. The founder has yet to decide which stands.
- **Terms:** a moment is what the creator cuts; "story" remains the unit in queues and publish kits. Avoid version jargon and "artifact" in the interface.

## Brand Commitments

The name is VibeCut, and this product is VibeCut Studio. The source is proprietary. Copy is plain and honest: it states real limits, gives a route to fix an error, and never presents a score as proof.

## Evidence on Hand

- The founder's dogfood report: `FOUNDER_BRIEF.md`.
- Founder sessions and panel reviews: `docs/testing/founder-session-1/`, `round_6.md`.
- Founder's review of a real AI fill render, 6.5/10 on the old code: `docs/testing/studio-clean-fill-retest.md`.

Absent, and not to be invented: the 20-source benchmark, customer testimonials, paying customers, signed-app proof, and any measured keeper rate.

## Product Principles

1. **The creator's few real posts beat more clips.** Judge features by what gets posted, not how much gets generated.
2. **One object through every change.** An edit, retry, reload or shape change never silently forks or overwrites a result.
3. **Local custody and flat cost.** The creator's files stay theirs, with no meter.
4. **Fail visibly and recover.** Show the real reason and the real time left, and do not lose finished work when something stops.
5. **Show evidence, never sell a score.**

## Accessibility & Inclusion

WCAG 2.2 AA is the paid-v1 target: visible focus, 200% zoom, screen-reader labels and live regions for render and queue, colour never the only signal, reduced motion, and a keyboard path instead of drag-only actions. Supported widths are in `PRD.md` §9.
