# DuckClean todo

Status: as of the M2 merge (`699b41d`) plus this documentation update.
Checked items are done. Unchecked items are not done.

## Done

### Product decisions

- [x] DuckClean is a separate product branch, not Classic.
- [x] Single purpose: automatic, best-quality AI removal of text, logos and
  burnt-in images.
- [x] Cloud-only. No local runner, no desktop renderer, no phone transport limit.
- [x] Full-length output with source audio, duration, display size and fps.
- [x] Beat dissection: scene-bounded 1–4 s spans.
- [x] Detect frame by frame; render only beats with selected targets.
- [x] Generate pixels when removal needs invented content.
- [x] OAuth, user library, render jobs and blob storage.
- [x] Commercial model: render-hour equivalent.
- [x] LaMa CPU-only; ProPainter/generative GPU.

### Repository and contracts

- [x] Orphan branch `duckclean` in `ducpa1912/vibecut`.
- [x] Pushed `origin/duckclean`; `main` and `classic` not moved.
- [x] Deleted the old `vibecut-duckclean` and `vibecut-classic` worktrees.
- [x] M0 contract: `api/openapi.yaml`, `contract.md`, canonical JSON, errors.
- [x] Postgres migrations `0001`, `0002`, `0003`.
- [x] Server-owned groups, members, boxes, ranges, masks, revision.
- [x] Explicit `range_mode`; empty ranges never mean whole source.
- [x] Worker HMAC contract and clock-skew checks.
- [x] Clerk JWT/JWKS verification.
- [x] 390/1024/1440 layout direction.

### M1

- [x] Clerk sign-in gate; honest setup state without a key.
- [x] Library list, item detail, poster, facts and playback.
- [x] Direct browser-to-R2 upload with real byte progress, rate, ETA, cancel,
  retry.
- [x] Probe and proxy/poster worker routes.
- [x] R2 HEAD verification for upload, proxy and poster.
- [x] Signed play tickets.
- [x] Postgres/Hyperdrive path and local PGlite path.
- [x] R2 binding, presigned S3 signer, local MinIO endpoint.
- [x] Env examples, worker `.env`, R2 CORS, Dockerfile, HF Space metadata.
- [x] `npm run m1:doctor`.
- [x] M1 tests.

### M2

- [x] Scene-cut beat dissection with deterministic manifest hash.
- [x] RapidOCR detection, 2×2/3×3 tiled OCR.
- [x] Tracklets, grouping by visual area, masks, low-confidence retention.
- [x] Coverage with `frames_read`, `frames_skipped`, `truncated`,
  `effective_fps`.
- [x] Scope selection; unread beats stay `pending`.
- [x] Detection retry after a failed job without orphaning a run.
- [x] Beat reset on a new detection revision.
- [x] Engine truth: RapidOCR only; PaddleOCR rejected.
- [x] Detection API, cancel, UI panel and polling.
- [x] Masks uploaded to R2.
- [x] Worker `DetectError` mapped to non-retryable payload error.
- [x] Local PGlite + MinIO dev stack.
- [x] M2 tests, including truncation and scope.

### Operations and quality

- [x] `make check`: lint, typecheck, API tests, worker tests, build.
- [x] CI installs `worker[dev,ocr]`.
- [x] `npm audit --omit=dev` clean.
- [x] Clerk React 6 migration; `Show` for signed-in/out.
- [x] Font dependency moved to `web`.
- [x] Provider comparison: Clerk/WorkOS/Supabase/Better Auth; R2/B2/Hetzner/
  Wasabi; Neon/Supabase/Railway/Render/DO.
- [x] Corrected three-scale hosting/GPU cost model.
- [x] Real attached clip verified text-free: all 167 frames, zero OCR lines.
- [x] `AGENTS.md`, `memory.md`, `todo.md`, `SESSION.html`, Freebuff handoff.

## Blocked by accounts or credentials

- [ ] Create Clerk app; set publishable key and issuer.
- [ ] Create Postgres (Neon or local); run migrations; create Hyperdrive.
- [ ] Create R2 bucket `duckclean-media`; apply CORS; create R2 token.
- [ ] Create `duckclean-jobs` and `duckclean-jobs-dlq` queues.
- [ ] `npx wrangler login`.
- [ ] Deploy CPU worker to Hugging Face.
- [ ] Deploy API Worker.
- [ ] Deploy Pages.
- [ ] Real phone upload → probe → proxy → playback acceptance.
- [ ] Real phone review → render → download acceptance.

## Detection and acceptance

- [ ] Obtain a real clip with known subtitle text and calibrate OCR.
- [ ] Real clip with a 0.2-second text flash.
- [ ] Real clip with a small corner watermark/logo.
- [ ] Real clip with two lines of text in one area.
- [ ] Real clip with text over motion.
- [ ] Real clip with text at the first and last frame.
- [ ] Real clip with a burnt-in image/sticker.
- [ ] Confirm a genuinely text-free real clip returns zero groups and no render.
- [ ] Record missed regions, false boxes, boxes per group, confidence and timing.
- [ ] Compare local worker output with Classic `bb3e89e` evidence.

## M3 — review workspace

- [ ] Real timeline: group rows, tight member bars, playhead, seek.
- [ ] Include/exclude per group and member.
- [ ] Manual range add/edit and manual region for burnt images.
- [ ] Frame/video preview tickets.
- [ ] Blur pre-render of selected beats.
- [ ] Label the pre-render as diagnostic, not final.
- [ ] Mobile-first review at 390, 768, 1024, 1440.
- [ ] 44px targets, no horizontal page scroll, primary action in first viewport.
- [ ] Keyboard controls and focus rings.
- [ ] Low-confidence review state.
- [ ] Long-source chunking instead of the 600-frame cap.
- [ ] Per-beat parallel detection.
- [ ] Group/member stable IDs and revision display.
- [ ] 300+ range performance test.

## M4 — preview and selection

- [ ] Render selection contract: group IDs + overrides + revision.
- [ ] Stale revision returns `409 stale_detection`.
- [ ] Pre-render cache by selection revision.
- [ ] Blur preview with source playback.
- [ ] Cheap LaMa preview on demand, labeled.
- [ ] Real progress and cancel for preview.
- [ ] No preview pretends to be the final file.

## M5 — render

- [ ] LaMa CPU clean path per selected beat.
- [ ] ProPainter GPU path for moving text/logos.
- [ ] Generative fill for large/complex regions.
- [ ] Per-beat segment render, parallel assembly, audio mux.
- [ ] Full-length output at source size/fps/audio.
- [ ] Cancel leaves no `.part`.
- [ ] Cached repeat returns the same output.
- [ ] Download ticket.
- [ ] GPU worker deployment (RunPod or Modal).
- [ ] Real render acceptance on a subtitled clip.
- [ ] Real logo removal acceptance.
- [ ] Real burnt-image/generative acceptance.
- [ ] Quality check at 100% zoom.

## M6 — billing and accounts

- [ ] Stripe product/meter.
- [ ] Render-hour estimate based on measured rates.
- [ ] Usage ledger from worker compute seconds.
- [ ] Idempotent meter events.
- [ ] Plan quotas, storage limits and retention.
- [ ] Billing page: estimate, actual use, balance.
- [ ] Failed/cancelled jobs bill only consumed compute.
- [ ] Free-tier abuse and rate limits.

## M7 — best-quality engines

- [ ] Automatic logo/watermark detection (Grounding DINO/OWLv2 + SAM 2).
- [ ] Per-range and per-frame masks.
- [ ] Temporal mask tracking.
- [ ] ProPainter/E2FGVI quality tuning.
- [ ] Flux Fill/SDXL generative keyframes and propagation.
- [ ] Engine selection truth and readiness.
- [ ] Model licensing and redistribution review.

## Operations and security

- [ ] Rate limits: uploads, detection, render, concurrent jobs.
- [ ] R2 lifecycle: abandoned uploads, masks, segments, outputs.
- [ ] Source deletion and user delete.
- [ ] Worker callback HMAC rotation.
- [ ] R2 CORS production origins.
- [ ] No secrets in logs, OCR text, filenames or signed URLs.
- [ ] Backups and restore for Postgres.
- [ ] Error monitoring and request IDs.
- [ ] Cost alerts and spend caps.
- [ ] Worker cold-start and capacity plan.
- [ ] Legal/licensing: ffmpeg/libx264, PaddleOCR/RapidOCR, LaMa,
  ProPainter, Flux Fill, model weights.
- [ ] Privacy policy for uploaded video.
- [ ] Real user media retention policy.

## Documentation

- [x] Cloud roadmap and plan.
- [x] Contract and worker contract.
- [x] Detection report.
- [x] Infrastructure runbook.
- [x] Provider comparison.
- [x] Hosting/GPU cost model.
- [x] M1 surface brief.
- [x] Freebuff handoff.
- [x] AGENTS.md, memory.md, todo.md.
- [ ] Session HTML fully reviewed after every future milestone.
- [ ] Update docs when the 600-frame cap, logo model, per-range masks or render
  engines change.

## Software factory workflow

- [x] Define request intake and classification in `AGENTS.md`.
- [x] Define the `REQ-YYYYMMDD-NN` memory template.
- [x] Define the linked todo checklist template.
- [x] Define revision/bugfix exceptions.
- [x] Record `REQ-20261111-01` in `memory.md`.
- [ ] Enforce the workflow on the next totally new request before code.
- [ ] Keep memory as decision history, not a task list.
- [ ] Keep todo as actionable plan, not a transcript.
- [ ] Move REQ sections to Done only when every acceptance item is complete.
- [ ] Fill the REQ commit hash at ship time.
- [ ] Update `SESSION.html` only at milestone boundaries.

## Merge checklist

- [x] Typecheck, lint, mypy, ruff, build.
- [x] API and worker tests.
- [x] Audit clean.
- [x] Secret files ignored.
- [x] No `web/dist`, `.dev`, caches or model files staged.
- [x] Branch pushed to `origin/duckclean`.
- [ ] Live M1 smoke test with real credentials.
- [ ] Real-media M2 acceptance.
- [ ] M3 review acceptance before render work.
