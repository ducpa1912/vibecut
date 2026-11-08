# DuckClean roadmap

DuckClean is a cloud-only product with one job: produce the cleanest possible
removal of baked-in text, logos and burnt-in images from video. It accepts a
full-length video, finds the regions that need removal, renders only the beats
that contain them, and returns the complete video with everything else
untouched.

DuckClean is its own lane and its own product. It is not Classic, not Studio,
not a reel cutter, not a local runner. There is no desktop install, no local
render path and no phone limitation: rendering runs on cloud workers, so a
phone can upload, review, render and download.

Status: **M1 code complete** — signed-in library, direct-to-R2 upload, probe,
proxy and playback. Live cloud resources are not provisioned yet. M2 is beat
dissection and detection.

## Product promise

- One purpose: remove text, logos and burnt-in images as cleanly as the current
  best model allows.
- Cloud only. The browser never needs a local renderer.
- Full-length output: same duration, display size, frame rate and audio as the
  source.
- Only beats that contain text, logos or images are rendered and re-encoded.
  Clean beats pass through with minimal or no processing.
- The user reviews detections and the pre-render before spending render time.
- When removal needs invented pixels, DuckClean generates them with a
  generative fill engine instead of smearing the region.
- Real user media only. No stock clip, no fake voice, no fake progress, no fake
  success.

## The flow

1. **Upload a local video** from desktop or phone, directly to cloud storage.
2. **Probe it** — duration, display size, fps, audio, rotation, codec.
3. **Dissect it into beats** — scene-bounded spans of roughly 1–4 seconds.
4. **Detect per beat, frame by frame** — text lines, logos, watermarks and
   burnt-in images, with boxes, masks and timestamps.
5. **Review and edit** the detected ranges, groups and masks on a timeline.
6. **Review the pre-render** — a fast cloud pass that blurs or fills the
   selected regions so missed or wrong detections are visible before the final
   render.
7. **Remove text with AI fill** — only on the beats that need it.
8. **Assemble and download** the cleaned full-length video.

## Cloud architecture

| Layer | Responsibility |
|---|---|
| Cloudflare Pages | Static frontend. No video bytes, no secrets. |
| API (Cloudflare Workers) | OAuth session, library, upload signing, job records, billing, worker dispatch. |
| Postgres | Users, library, beats, detections, jobs, usage ledger. |
| Cloudflare R2 | Source video, proxy, posters, beat clips, masks, outputs. S3-compatible, no egress fee. |
| CPU worker | ffmpeg probe, beat dissection, frame extraction, OCR/logo detection and LaMa clean fill. |
| GPU worker | ProPainter video inpainting, generative fill, heavy encode and assembly. |
| Hugging Face | Hosting for the first CPU worker; RunPod/Modal for GPU render. |
| Stripe | OAuth-adjacent billing and metered render-hour usage. |

The worker is a Docker image behind a small HTTP contract. Hugging Face runs it
now; the same image moves to a dedicated GPU cloud later without changing the
API or the frontend.

## Beat model

A **beat** is the unit of detection and rendering. Beats come from scene cuts
plus a hard maximum length, so no single beat is too large to read or render.

- Detection reads every frame inside a beat at native frame rate, capped by
  resolution and cost.
- A beat is marked **text-bearing** only when detection finds text, a logo or a
  burnt-in image inside it.
- Text-bearing beats are rendered. Clean beats are passed through or quickly
  encoded with no model work.
- Beats are rendered in parallel and concatenated in order, then the original
  audio is muxed back.
- Costs scale with the amount of video that actually contains something to
  remove, not with total video length.

## Commercial model

Billing is by **render-hour equivalent** — weighted cloud compute time, not
wall-clock time or seat count.

- 1 render-hour equivalent = 3600 weighted compute-seconds.
- CPU seconds carry a low weight; standard GPU seconds are the reference;
  premium GPU and generative fill carry a higher weight.
- The worker reports compute-seconds and device class per job.
- The API writes a usage ledger row and a Stripe meter event.
- The user sees an estimate before render and a real charge after render.
- Failed or cancelled jobs bill only the compute actually consumed.
- Storage limits and retention are plan attributes; video egress from R2 costs
  nothing.

## v1 scope

### In

- OAuth sign-in (Google, Apple, email link) and per-user library.
- Direct-to-R2 upload from desktop and phone, with real progress.
- Probe, hard limits and disk/cost preflight.
- Beat dissection with scene boundaries and a maximum beat length.
- Frame-by-frame cloud detection for text, plus logo/watermark detection.
- Burnt-in image removal from a user-drawn box in v1.
- Server-owned groups, members, boxes, masks, ranges and revision.
- Timeline review with include/exclude, seek, range edit and manual add.
- Pre-render check with blur or a cheap fill, streamed from the cloud.
- AI fill on selected beats: LaMa on CPU for the fast clean path; ProPainter or
  generative fill on GPU for moving or hard regions.
- Generative fill on demand for large or complex regions.
- Parallel beat rendering, assembly, audio mux and download.
- Cancel, retry, per-beat resume and cached output.
- Render-hour estimate, usage ledger and Stripe metering.
- Responsive review workspace: phone, tablet and desktop.
- Cloudflare Pages frontend; HF-hosted worker; R2 storage.

### Later

- Dedicated GPU cloud with reserved capacity and lower latency.
- Automatic logo and watermark detection without a user box.
- Multi-language and stylised text models.
- Batch jobs and team libraries.
- Browser-side lightweight preview editing beyond selection.
- Signed desktop uploader for very large masters.
- Resumable multipart upload for files over 5 GB.

## Milestones

| Milestone | Outcome | Acceptance |
|---|---|---|
| M0 — Contract and evidence | Frozen API, data model, worker contract, real-media pack | OpenAPI and schema signed; real clips with text, logo and burnt image collected |
| M1 — Accounts and library | OAuth, user library, direct R2 upload, proxy playback | Real phone uploads a clip, sees it in the library, plays the proxy |
| M2 — Beats and detection | CPU worker splits beats and detects frame by frame | Real subtitled clip returns beats, groups, boxes, masks and coverage; clean beats marked empty |
| M3 — Review workspace | Timeline, groups, masks, include/exclude, manual add | Phone review shows preview, timeline and primary action in one viewport; no horizontal scroll |
| M4 — Pre-render check | Cloud blur/fill pre-render on selected beats | Missed text, wrong box and overlapping masks are visible; no final render starts |
| M5 — Selective render | GPU fill on text-bearing beats, assembly, download | Output is full length; clean beats unchanged or near-identical; audio preserved |
| M6 — Billing and launch | Render-hour estimate, usage ledger, Stripe metering, limits | Charge matches worker compute; failed jobs bill actual use only |
| M7 — Best-quality engine | Generative fill for large regions; automatic logo detection | Real logo and burnt-image clips pass visual acceptance |

## Acceptance tests use real media

The acceptance pack must contain real user video, not generated clips:

- a clip with one subtitle line for two seconds,
- a clip with text that appears for under 0.25 seconds,
- a clip with a small corner logo,
- a clip with a large burnt-in image or sticker,
- a clip with moving text over motion,
- a clip that genuinely contains no text.

For each clip, record detections, missed regions, false boxes, render time,
render-hour cost, output correctness and whether clean beats changed.

## Metrics

- Upload to playable proxy under 60 seconds for a 1-minute 1080p clip.
- Beat dissection completes before detection starts streaming results.
- Detection reports coverage: frames read, frames skipped, model, confidence.
- Clean beats: PSNR above 45 dB against the source after assembly, or a
  stream-copied beat that is byte-identical in video payload.
- Text-bearing beats: no readable text remains on the selected regions in a
  human review at 100% zoom.
- Render cost proportional to text-bearing duration.
- Cancel leaves no output object and bills only consumed compute.
- Phone: full upload → review → render → download on a real phone.
- No request carries video bytes to the frontend host.

## Product principles

These are design rules, not compromises to negotiate away.

1. **Best removal first.** If a region needs invented content, generate it.
   Do not ship a smear as the default.
2. **Selective work.** Detect every beat, render only beats with something to
   remove.
3. **Full-length, source-faithful output.** DuckClean is not a reel cutter.
4. **Cloud-native, phone-capable.** Rendering is remote, so the device is only
   a browser.
5. **Real media only.** No demo clip, stock footage, fake voice, fake frame or
   fake progress.
6. **Truthful states.** Missing model, empty beat, low confidence, truncated
   scan and failed render are distinct states.
7. **No hidden spend.** The user sees the estimate, the real use and the
   remaining balance.
