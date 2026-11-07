# DuckClean build plan

Status: plan. Brand-new cloud product on branch `duckclean`, cut from Classic
`bb3e89e`. Worktree:
`/Users/happynghia/Public/Project/Code/drop_eval/vibecut-duckclean`.

Classic keeps shipping in its lane. DuckClean ports engine fixes from Classic;
it never merges the whole Classic lane, and `main` is not moved.

## 1. Decisions

| Decision | Choice |
|---|---|
| Product shape | Cloud-only, single-purpose auto-clean |
| Frontend | Static SPA on Cloudflare Pages |
| API | Cloudflare Workers + Hono, TypeScript |
| Database | Postgres (Neon or Supabase), Cloudflare Hyperdrive |
| Blob | Cloudflare R2 (S3 API, presigned URLs) |
| Queue / retry | Cloudflare Queues plus DB-backed job state |
| CPU worker | Docker image on Hugging Face (Spaces or Jobs) |
| GPU worker | Same Docker image, GPU tier on Hugging Face, then dedicated GPU cloud |
| Auth | OAuth through Clerk (Google, Apple, email link) with JWKS verification in Workers |
| Billing | Stripe metered usage, render-hour equivalent |
| Unit of work | Beat: scene-bounded span of 1–4 seconds |
| Reuse | `detect.py`, `textfill/`, `clean_source.py`, `pipeline.py` ported into `engine/` |
| Retired | Local runner, local custody, Apple Vision as the only OCR, whole-video blind render |

Provider choices are swappable behind interfaces. The worker contract, storage
keys, data model and billing unit are the parts that must not drift.

## 2. Repository layout

```
duckclean/
  web/                         # Vite + React + TypeScript SPA → Cloudflare Pages
  api/                         # Cloudflare Worker
    src/
      index.ts
      auth.ts                  # JWT/JWKS, user upsert
      routes/
        library.ts
        sources.ts
        detections.ts
        renders.ts
        previews.ts
        billing.ts
        webhooks.ts
      db/                      # queries + migrations entry
      r2.ts                    # presign GET/PUT, lifecycle
      queue.ts                 # enqueue, retry, dead letter
      worker_client.ts         # signed calls to CPU/GPU worker
      stripe.ts
      schemas.ts               # zod
    migrations/
      0001_init.sql
  worker/                      # Python render worker, one Docker image
    duckclean_worker/
      app.py                   # FastAPI: /health /v1/probe /v1/dissect /v1/detect /v1/render /v1/cancel
      contract.py              # pydantic request/response models
      storage.py               # R2/S3 client, presigned transfer
      beats.py                 # scene cut, beat split, concat plan
      frames.py                # extraction, tiling, downscale
      ocr.py                   # Linux OCR backend
      logos.py                 # open-vocab logo/watermark detection
      masks.py                 # glyph and region masks
      fill/
        lama.py
        propainter.py          # temporal video inpainting
        generative.py          # Flux Fill / SDXL inpainting
      render.py                # per-beat fill + encode
      assemble.py              # concat, audio mux, finalize
      usage.py                 # compute-seconds and device class
    Dockerfile
    requirements.txt
  engine/                      # ported Classic engine, no Classic routes
    detect.py
    clean_source.py
    pipeline.py
    textfill/
    vision/                    # optional macOS-only path, not used in cloud
  docs/duckclean/
```

`engine/` is a copy with a clear port log, not a git submodule and not a shared
package. Cloud code must not import Classic application modules.

## 3. Runtime topology

```
Browser (phone/desktop)
   │  HTTPS
   ├── Cloudflare Pages ── static SPA
   ├── API Worker ──────── OAuth, metadata, presigned URLs, jobs, billing
   │      │
   │      ├── Postgres
   │      ├── R2  ◄──── presigned PUT/GET ──── browser
   │      ├── Queues ── dispatch/retry
   │      └── Worker HTTP (HMAC + callback)
   │              │
   │      ┌───────┴────────┐
   │   CPU worker       GPU worker
   │   probe/dissect    fill/encode/assemble
   │   OCR/logo         LaMa/ProPainter/generative
   │      └───────┬────────┘
   │              └── R2 (read source, write beat/output)
   └── signed GET for proxy, previews, result
```

Rules:

- Video bytes never traverse Pages or the API Worker.
- The browser uploads directly to R2 with a short-lived presigned PUT.
- The browser reads previews and downloads through short-lived presigned GETs.
- Workers read and write R2 directly with a scoped token.
- The API is the only writer of job state.

## 4. Data model

Postgres, UUID primary keys, `created_at`/`updated_at` on every table.

### Identity

```
users
  id, oauth_subject, email, display_name, avatar_url,
  plan, render_seconds_balance, storage_bytes_used,
  created_at, updated_at

oauth_accounts
  id, user_id, provider, subject, email, created_at
```

### Library and assets

```
library_items
  id, user_id, title, status, source_asset_id, proxy_asset_id,
  poster_asset_id, duration, width, height, fps, has_audio,
  codec, bytes, created_at, updated_at

source_assets
  id, user_id, library_item_id, r2_key, bytes, etag, sha256,
  probe_json, upload_status, created_at

proxy_assets
  id, source_asset_id, r2_key, width, height, fps, bytes, created_at
```

### Beats and detection

```
beats
  id, source_asset_id, index, start_s, end_s,
  frame_start, frame_end, boundary, status,
  has_target, confidence, created_at

detection_runs
  id, source_asset_id, revision, engine, model_versions_json,
  status, progress, frames_read, frames_skipped,
  coverage, truncated, error, started_at, finished_at

detection_groups
  id, run_id, beat_id, kind, lane, order_index,
  sample_text, box_json, confidence, member_count,
  included_default, low_confidence

detection_members
  id, group_id, text, ranges_json, range_mode,
  box_json, confidence, fill_keys, mask_asset_id,
  included_default, low_confidence

mask_assets
  id, run_id, group_id, member_id, kind,
  r2_key, frame_start, frame_end, provenance,
  model_version, created_at
```

`range_mode` is `ranges` or `whole_source`. Empty `ranges_json` never means the
whole video.

### Rendering and usage

```
render_jobs
  id, user_id, library_item_id, detection_run_id, revision,
  status, stage, progress, engine, device_class,
  selection_json, estimate_seconds, compute_seconds,
  output_asset_id, error_code, error_detail,
  idempotency_key, worker_id, parent_job_id,
  created_at, started_at, finished_at

render_segments
  id, render_job_id, beat_id, status, attempt,
  input_r2_key, output_r2_key, fill_seconds, encode_seconds,
  compute_seconds, error_code, updated_at

output_assets
  id, render_job_id, r2_key, bytes, duration, width, height,
  fps, has_audio, engine, created_at

usage_ledger
  id, user_id, render_job_id, device_class, model_tier,
  compute_seconds, weight, render_hours, stripe_meter_event_id,
  created_at

events
  id, user_id, job_id, type, payload_json, created_at
```

### Indexes that matter

- `library_items (user_id, created_at desc)`
- `beats (source_asset_id, index)`
- `detection_groups (run_id, lane, order_index)`
- `render_jobs (user_id, status, created_at)`
- `render_segments (render_job_id, beat_id)`
- `usage_ledger (user_id, created_at)`

## 5. API surface

Base `/api/v1`. All routes require a verified session except `/health` and
webhooks. Every response carries a request id.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | API, DB, R2, worker fleet truth |
| GET | `/me` | User, plan, balance |
| POST | `/uploads` | Create upload ticket: presigned R2 PUT + asset record |
| POST | `/uploads/{id}/complete` | Finalize upload, enqueue probe |
| GET | `/library` | User library, cursor paginated |
| GET | `/library/{id}` | Item, source, proxy, detection, render state |
| DELETE | `/library/{id}` | Delete source, proxy, beats, masks, outputs |
| GET | `/library/{id}/play` | Short-lived proxy GET ticket |
| POST | `/library/{id}/detect` | Start detection with engine and scope |
| GET | `/library/{id}/detect` | Progress, coverage, groups |
| POST | `/library/{id}/detect/cancel` | Cancel detection |
| POST | `/library/{id}/render` | Start render: groups, overrides, revision, engine, device |
| GET | `/library/{id}/render` | Progress, stage, segments |
| POST | `/library/{id}/render/cancel` | Cancel render |
| GET | `/library/{id}/download` | Short-lived output GET ticket |
| POST | `/library/{id}/preview` | Pre-render ticket for selected groups |
| GET | `/previews/{id}` | Pre-render progress and ticket |
| GET | `/billing/estimate` | Render-hour estimate for a selection |
| GET | `/billing/usage` | Ledger and balance |
| POST | `/webhooks/stripe` | Meter events, payment state |
| POST | `/webhooks/worker` | Worker callbacks, HMAC verified |

Error envelope:

```json
{
  "error": {
    "code": "stale_detection",
    "message": "Detection changed. Review the new ranges.",
    "detail": {},
    "retryable": false,
    "action": "reload_detection"
  }
}
```

Codes: `unauthorized`, `forbidden`, `not_found`, `validation`, `quota`,
`stale_detection`, `worker_unavailable`, `source_unreadable`, `render_failed`,
`cancelled`, `rate_limited`.

## 6. Worker contract

One Docker image, two modes. Mode is chosen by environment and validated at
startup.

### Common

- `GET /health` → version, git sha, device, models present, ffmpeg version, busy.
- Auth: `X-DuckClean-Signature` HMAC-SHA256 over the raw body plus timestamp;
  reject skew over 300 seconds.
- Every call is idempotent by `job_id`.
- Every job response includes `compute_seconds`, `device_class`,
  `model_versions`, `input_bytes`, `output_bytes`.
- Progress is posted to the API callback with the same HMAC, at most once per
  second per job.
- Cancel is checked between frames, between beats and before each model call.

### `POST /v1/probe`

```json
{
  "job_id": "uuid",
  "input": {"url": "presigned", "bytes": 13810783, "sha256": "..."}
}
```

Returns probe fields: duration, width, height, fps, rotation, codec, audio
codec, has_audio, frame_count.

### `POST /v1/dissect`

```json
{
  "job_id": "uuid",
  "input": {"url": "presigned", "probe": {}},
  "beat": {"max_seconds": 4.0, "min_seconds": 1.0, "scene_threshold": 0.30}
}
```

Returns beats with `index`, `start_s`, `end_s`, `frame_start`, `frame_end`,
`boundary` (`scene` or `cap`), and a recommended detection cadence.

### `POST /v1/detect`

```json
{
  "job_id": "uuid",
  "input": {"url": "presigned", "probe": {}},
  "revision": "sha256-of-plan",
  "beats": [{"id": "uuid", "index": 0, "start_s": 0.0, "end_s": 3.2}],
  "detect": {
    "text": true,
    "logos": true,
    "regions": [{"box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1}}],
    "frame_policy": "every_frame",
    "max_width": 1920,
    "tile_small_text": true
  },
  "callback": {"url": "https://api/.../webhooks/worker", "secret_id": "..."}
}
```

Returns groups, members, boxes, ranges, masks, confidence, coverage and
truncation. Detection writes masks to R2; it does not return pixels.

### `POST /v1/render`

```json
{
  "job_id": "uuid",
  "input": {"url": "presigned", "probe": {}},
  "beats": [{"id": "uuid", "index": 0, "start_s": 0.0, "end_s": 3.2,
             "has_target": true}],
  "selection": {
    "revision": "sha256",
    "groups": [{"group_id": "uuid", "member_ids": ["uuid"],
                "engine": "lama", "device": "gpu"}]
  },
  "output": {
    "url": "presigned-put",
    "codec": "h264",
    "pixel_format": "yuv420p",
    "crf": 18,
    "fps": "source",
    "audio": "source"
  },
  "assemble": {"strategy": "parallel_beats", "max_parallel": 4},
  "callback": {"url": "https://api/.../webhooks/worker", "secret_id": "..."}
}
```

Returns `output_asset_id` metadata, per-beat timings, compute seconds and
model versions. Partial beat artifacts are deleted after assembly.

### `POST /v1/preview`

Same shape as render with `output.resolution_scale` 0.5, `output.crf` 28,
`engine` forced to `blur` or `lama_preview`, and a hard time limit.

### `POST /v1/cancel`

`{"job_id": "uuid"}` → `{"cancelled": true, "status": "cancelling"}`. The worker
stops at the next safe boundary, deletes `.part` objects and reports final
usage.

## 7. Beat pipeline

### 7.1 Ingest

1. Browser asks `POST /uploads` with filename, bytes, content type.
2. API checks quota, extension, and declared size; creates `source_assets` row;
   returns presigned PUT with a 15-minute TTL.
3. Browser PUTs directly to R2 with progress.
4. `POST /uploads/{id}/complete` verifies the object with R2 HEAD (bytes, etag)
   and enqueues probe.
5. CPU worker probes, writes `probe_json`, API creates a proxy (720p H.264) and
   poster, then marks the item `ready`.

Failure handling: abandoned uploads are deleted by an R2 lifecycle rule after
24 hours. Incomplete items are marked `upload_incomplete`.

### 7.2 Dissect

- One ffmpeg scene pass at 480p with `select='gt(scene,0.30)'`.
- Scene boundaries become beat boundaries.
- Long shots are cut at `max_seconds = 4.0`; short shots under
  `min_seconds = 1.0` may merge with a neighbour.
- Beat boundaries are snapped to frame indices so render segments align.
- Output is a deterministic beat manifest with stable indices. A re-dissect with
  the same source and parameters produces the same manifest hash.

### 7.3 Detect

Per beat, independently, so beats parallelize:

1. Extract every frame at native fps, capped by `max_width = 1920` and a
   per-beat frame cap.
2. Global OCR pass per frame.
3. Tiled OCR pass for small corner text when `tile_small_text` is on: 2×2 or
   3×3 tiles with 10% overlap.
4. Logo/watermark pass: open-vocabulary detection with prompts
   `logo`, `watermark`, `channel bug`, plus region prompts when the user drew a
   box.
5. Merge observations into tracklets inside the beat.
6. Join tracklets across adjacent beats when text, box and time are continuous.
7. Build groups and members server-side. One group per visual text area or
   logo cluster. Members keep their own tight boxes and time ranges.
8. Rasterise glyph masks and region masks; upload masks to R2.
9. Mark each beat `has_target` and write the aggregate coverage.

Detection output must include:

- `frames_read`, `frames_skipped`, `effective_fps`, `coverage`,
- `truncated`, `ocr_available`, `logo_model_available`,
- per-group confidence, per-member confidence and low-confidence flags,
- `provenance` for each mask: `ocr`, `logo`, `user_box`, `manual`.

A beat with no detections is a valid empty result. A beat that could not be read
is `failed`, not empty.

### 7.4 Grouping rules

- One visual text area = one group, even when lines change.
- Multiple subtitle lines in the same area share a group row; each line keeps
  its own member, box and time.
- A logo that persists across beats is one group with members per beat or per
  range.
- A user-drawn region becomes a group with `provenance: user_box`.
- Lanes are assigned to prevent overlap in the review timeline.
- Group and member ids are stable across re-renders of the same revision.

### 7.5 Render

1. API expands the selection (`group_ids`, `member_ids`, overrides, revision)
   into a per-beat work plan.
2. Beats without selected targets are **passthrough beats**.
3. Beats with selected targets are **fill beats**.
4. Fill beats are dispatched to GPU workers, `max_parallel = 4` by default.
5. Each fill beat is rendered to a uniform H.264/yuv420p segment at source
   size and fps.
6. Passthrough beats are encoded with identical parameters and no model call.
7. Segments are concatenated in beat order and the original audio is muxed.
8. Output is uploaded to R2, verified, and the job becomes `ready`.

Why encode passthrough beats: uniform parameters make concat deterministic
across sources and beat counts. The model cost stays proportional to
text-bearing beats; encoding is cheap by comparison. A later optimization may
stream-copy clean beats when source codec and parameters already match.

### 7.6 Cancellation and resume

- Cancel sets a flag; each worker checks between frames and beats.
- Completed beat segments are kept for retry; `.part` files are deleted.
- A cancelled job never produces a downloadable output.
- On worker loss, the API marks in-flight beats `lost` and retries up to two
  times with a new worker.
- Resume reuses completed segments by `(revision, beat_id, engine, params)`.

## 8. Detection stack

Apple Vision is macOS-only and cannot run on a Linux cloud worker. The cloud
detector needs its own stack; the local evidence in `detection-report.md` is
ground truth for that clip, not the production path.

### Text

- Primary: PaddleOCR PP-OCRv5, ONNX or Paddle runtime, CPU-friendly.
- Fallback: RapidOCR (onnxruntime) when Paddle packaging is too heavy.
- Tiling for small text and corner watermarks.
- Per-frame reads inside beats, not 4 fps global sampling.
- Confidence floor per model, with low-confidence candidates retained and
  marked, not dropped.

### Logos, watermarks, burnt-in images

- Open-vocabulary detector: Grounding DINO or OWLv2 with text prompts.
- Optional segmentation refinement: SAM 2 on detected boxes for tight masks.
- User-drawn region is always accepted as ground truth and skips detection.
- A persistent logo becomes one tracked group; masks are per frame or per range.

### Masking

- Text: glyph mask from the OCR box plus a small dilation, not the whole box.
- Logo/image: region mask from segmentation; fall back to the box with a
  feathered edge.
- Masks are stored as PNG/WebP in R2 and referenced by `mask_assets`.
- Masks carry the model version so a cache hit cannot mix model versions.

### Calibration

The current detector's limits are known: global 4 fps sampling, a frame cap, a
confidence floor and a tracklet cap. Cloud beats remove the sampling
compromise: each beat is read frame by frame. The remaining risk is model
quality on stylised, low-contrast, non-Latin and animated text. Calibrate on
real clips with known text, and keep a human review step before spend.

## 9. Fill engines

| Engine | Use | Device | Notes |
|---|---|---|---|
| `blur` | Pre-render diagnostic and honest fallback | CPU/GPU | Never sold as AI fill |
| `lama` | Still or slow-moving text, logos, small regions | GPU | Fast, good for smooth backgrounds |
| `propainter` | Moving text, logos, larger regions, temporal coherence | GPU | Best default for video |
| `generative` | Large or complex regions needing invented content | GPU | Flux Fill or SDXL inpainting, keyframes plus propagation |
| `cover` | Opaque object, deliberate cover-up | CPU/GPU | Only when the user asks |

Default: `propainter` when available, `lama` as the fast path, `generative` on
demand. A missing engine disables the option with a reason; it never silently
falls back to a worse result.

## 10. Storage layout

```
u/{user_id}/src/{asset_id}/source.{ext}
u/{user_id}/src/{asset_id}/proxy.mp4
u/{user_id}/src/{asset_id}/poster.jpg
u/{user_id}/detect/{run_id}/mask/{mask_id}.png
u/{user_id}/render/{job_id}/beat/{beat_index}.mp4
u/{user_id}/render/{job_id}/final.mp4
u/{user_id}/preview/{preview_id}.mp4
```

Lifecycle:

- Abandoned uploads: delete after 24 hours.
- Source and proxy: keep while the library item exists; delete with the item.
- Masks: keep with the detection revision; delete superseded revisions after 7
  days.
- Beat segments: delete after successful assembly.
- Outputs: plan-based retention (for example 7 days on free, 30 days paid),
  then delete; the user can re-render.
- `.part` objects: delete on cancel, failure or 24-hour lifecycle.

## 11. Auth, security and quotas

- OAuth through Clerk. Worker verifies JWTs against JWKS, caches keys, checks
  issuer, audience, expiry and subject.
- `users.oauth_subject` is the only identity join; email is mutable metadata.
- Every query filters by `user_id`. No client-supplied user id is trusted.
- Presigned URLs: PUT 15 minutes, GET 10 minutes, single object, no listing.
- R2 token is scoped to the bucket prefix; no admin token near the worker.
- Worker HMAC secret rotated per deployment; callback URL is allowlisted.
- Upload validation: declared bytes, actual bytes, ffprobe readability,
  duration and resolution limits.
- Rate limits per user: uploads, detection starts, render starts, concurrent
  jobs (1 render per user in v1).
- Quotas: max duration, max resolution, storage bytes, monthly render hours.
- Logs exclude OCR text, filenames and signed URLs. Log ids, sizes, timings and
  error codes.
- No third-party analytics scripts on the app origin.

## 12. Billing

Unit: render-hour equivalent.

```
weight(cpu)         = 0.10
weight(gpu_standard)= 1.00
weight(gpu_premium) = 2.50

render_hours = compute_seconds * weight / 3600
```

- The worker reports `compute_seconds` by device class for detection, preview
  and render separately.
- The API writes one `usage_ledger` row per job segment.
- Stripe receives a meter event keyed by `render_job_id`, idempotent.
- Estimate = predicted beat count × per-beat model cost from a measured rate
  table, plus encode. The estimate is shown before start and labeled as an
  estimate.
- Cancelled and failed jobs bill actual compute, never the estimate.
- Detection and preview are metered too, at their own weight.
- Plan attributes: included render hours, storage bytes, output retention.

## 13. Frontend

Static SPA on Pages. Same build works on phone, tablet and desktop.

Screens:

1. **Landing / sign in** — what DuckClean removes, OAuth entry.
2. **Library** — user videos, status, duration, last render.
3. **Upload** — file picker, direct-to-R2 progress, real limits.
4. **Processing** — probe, dissect, detect with per-beat progress.
5. **Review** — the product: preview, timeline, groups, masks, include/exclude.
6. **Pre-render check** — blur or cheap fill playback of selected beats.
7. **Render** — stage, percent from real segments, estimate, cancel.
8. **Result** — real output facts, preview, download, clean again.
9. **Account** — plan, usage, render-hour balance, storage.

Review workspace:

- Preview uses the cloud proxy with signed GET; overlays use normalized boxes.
- Timeline: one row per group, tight bars per member, violet playhead, blue
  included ranges, dashed excluded ranges, amber low confidence.
- Phone: preview, playhead, timeline and the primary action in the first
  viewport; 44px targets; no horizontal page scroll; sheets for details.
- Desktop: two columns, preview and timeline left, group list and inspector
  right.
- Include/exclude per group and per member; manual add range; manual region for
  burnt images.
- Engine picker: Auto, LaMa, ProPainter, Generative, Blur, with real readiness
  and device class.
- Pre-render is a separate, labeled playback. Normal review never pretends to
  be the final file.

States that must exist: uploading, upload failed, probing, dissecting,
detecting, detection truncated, no targets, low confidence, preview building,
render queued, rendering, segment retry, assembling, ready, cancelled, failed,
out of quota, worker unavailable, session expired.

## 14. Acceptance

Use the real-media pack; no generated clips.

Contract:

- A real phone uploads a 60-second 1080p clip and plays the proxy.
- A real subtitled clip returns beats, groups, members, boxes, masks, coverage
  and `revision`.
- A genuinely text-free clip returns empty groups and never starts a render.
- `range_mode` prevents accidental whole-video removal.

Detection:

- Every frame inside a beat is read or explicitly reported skipped.
- A 0.2-second text flash is found in a full-frame beat scan.
- A corner logo is found and masked.
- A burnt-in image is removable from a user box.
- Missed text is visible in the pre-render.

Render:

- Output duration, display size, fps and audio match the source.
- Clean beats are stream-copied or measure above 45 dB PSNR against the source.
- Text-bearing beats have no readable text at 100% zoom.
- Cancel leaves no output object and no `.part`.
- Retry resumes completed beats without re-billing them.

Billing and security:

- Ledger seconds match worker-reported compute within 2%.
- Stripe meter event is idempotent across retries.
- Every cross-user access returns `403` or `404`, never data.
- No video bytes touch Pages or the API Worker.
- Signed URLs expire and cannot be replayed after expiry.

Product:

- Phone: upload → review → render → download without a desktop.
- No stock media, fake voice, fake frame, fake progress or fake success.
- Every model state is real: present, missing, loading, failed.

## 15. Build order

1. **Freeze the contract** — migrations, OpenAPI, worker request/response,
   beat manifest, selection revision, error codes.
2. **API and auth skeleton** — Clerk JWT verification, user upsert, library,
   presigned upload, R2 HEAD verification.
3. **CPU worker** — probe, proxy, dissect, health; deploy to HF CPU.
4. **Detection** — OCR backend, tiling, logo detection, masks, groups, coverage,
   callback progress.
5. **Review UI** — library, upload, detection stream, timeline, masks,
   include/exclude.
6. **Pre-render** — blur/cheap fill from the cloud, labeled playback.
7. **GPU render** — LaMa per selected beat, parallel segments, concat, audio
   mux, download.
8. **Billing** — estimate, ledger, Stripe meter, quotas, plan limits.
9. **Best-quality engine** — ProPainter, then generative fill for hard regions.
10. **Real-media acceptance and launch** — phone flow, cancel, retry, retention.

## 16. Risks and open decisions

- **OCR quality in the cloud.** Apple Vision is not portable. PaddleOCR or
  RapidOCR must be benchmarked on real stylised and non-Latin text before the
  review UI is declared good.
- **Logo and burnt-image detection.** Open-vocabulary detectors are weaker than
  text OCR. v1 ships user-box removal for burnt images and treats automatic
  logo detection as a quality target, not a guarantee.
- **Temporal coherence.** Per-frame LaMa can flicker on moving text. ProPainter
  is the default best path; generative fill must be keyframed and propagated.
- **HF worker limits.** Spaces sleep, disk is ephemeral, and GPU quota is
  shared. The worker must stream from R2, tolerate cold starts and report
  capacity. Dedicated GPU is the fix when volume grows.
- **Concat correctness.** Uniform segment parameters are mandatory. Any beat
  with different size, fps or pixel format breaks the output.
- **Audio sync.** Beat boundaries are frame-snapped; audio is muxed from the
  source once, not per beat.
- **Cost accuracy.** The estimate is a rate table, not a promise. Show it as an
  estimate and bill actual compute.
- **Large files.** A single presigned PUT is fine under 5 GB. Above that, add
  multipart upload before accepting master files.
- **Licensing.** PaddleOCR, LaMa, ProPainter, Flux Fill and ffmpeg/libx264 all
  need a redistribution and commercial-use review before launch.
- **Classic drift.** `detect.py`, `textfill/` and `clean_source.py` are copied
  into `engine/`. Port fixes deliberately; do not merge the Classic lane.
