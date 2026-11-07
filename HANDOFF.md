# DuckClean handoff

You are the coding agent for **DuckClean**, a cloud-only product that removes
baked-in text, logos and burnt-in images from video.

This repository is intentionally new. It contains the product plan and real-file
detection evidence, and no legacy application code. Build the cloud product from
this document and the docs in `docs/duckclean/`.

## Repository

- Remote: `https://github.com/ducpa1912/vibecut.git`
- Branch: `duckclean`
- Local path: `/Users/happynghia/Public/Project/Code/drop_eval/duckclean`
- This is a standalone orphan branch. It shares no history with `classic` or
  `main`.
- Push only to `origin/duckclean`. Never push to `main` or `classic`.

## Mission

Given a real user video:

1. Upload it from desktop or phone.
2. Probe it.
3. Dissect it into small beats.
4. Detect text, logos and burnt-in images frame by frame per beat.
5. Let the user review and edit detections on a timeline.
6. Show a pre-render check with blur.
7. Remove the selected regions with AI fill.
8. Assemble and download the cleaned full-length video.

DuckClean is not Classic. There is no reel cutter, no Studio, no Smart Cut, no
local runner, no desktop renderer. Rendering is cloud-only, so a phone can do
the full flow.

## Read first

- `docs/duckclean/roadmap.md` — product, flow, scope, milestones, billing.
- `docs/duckclean/plan.md` — architecture, data model, API, worker contract,
  beat pipeline, detection and fill stack.
- `docs/duckclean/detection-report.md` — real-file evidence and the calibration
  pack.
- `docs/duckclean/contract.md` — the frozen M0 wire contract: revisions,
  tickets, state machines, limits and the decisions taken while freezing it.

If a decision below conflicts with a doc, this handoff wins. Update the docs in
the same change.

## Stack decisions

Do not add the Classic FastAPI app.

| Layer | Choice |
|---|---|
| Frontend | Vite + React + TypeScript SPA on Cloudflare Pages |
| API | Cloudflare Workers + Hono, TypeScript |
| Database | Postgres (Neon or Supabase) via Cloudflare Hyperdrive |
| Blob | Cloudflare R2, presigned PUT/GET, S3 API |
| Queue | Cloudflare Queues plus DB-backed job state |
| Auth | Clerk OAuth: Google, Apple, email link; verify JWT via JWKS |
| CPU worker | Python FastAPI Docker image on Hugging Face |
| GPU worker | Same image, GPU tier on Hugging Face; later dedicated GPU cloud |
| Billing | Stripe metered usage, render-hour equivalent |
| Unit of work | Beat: scene-bounded span, 1–4 seconds |

Video bytes never pass through Pages or the API Worker. The browser uploads
directly to R2. Workers read and write R2. The browser downloads through signed
URLs.

## Beat pipeline

- Dissect with an ffmpeg scene pass; cut long shots at 4 seconds; snap
  boundaries to frame indices; produce a deterministic beat manifest.
- Detect every frame inside each beat at native fps, capped at 1920 px wide.
- Add a tiled OCR pass for small corner text.
- Add an open-vocabulary logo/watermark pass.
- Accept a user-drawn region for burnt-in images.
- Merge observations into tracklets inside a beat; join continuous tracklets
  across adjacent beats.
- Build groups and members server-side. One group per visual text area or logo
  cluster. Each line keeps its own tight box and time range.
- Rasterise glyph and region masks into R2.
- Mark `has_target` on each beat.
- Render only beats with selected targets. Passthrough beats are encoded with
  the same H.264/yuv420p parameters and concatenated in order.
- Mux the original audio once. Output keeps source duration, display size, fps
  and audio.

## Required data model

Minimum tables:

- `users`, `oauth_accounts`
- `library_items`, `source_assets`, `proxy_assets`
- `beats`
- `detection_runs`, `detection_groups`, `detection_members`, `mask_assets`
- `render_jobs`, `render_segments`, `output_assets`
- `usage_ledger`, `events`

Hard rule: `range_mode` is `ranges` or `whole_source`. An empty range list never
means “remove the whole video.”

Every query filters by `user_id`. Never trust a client-supplied user id.

## API minimum

Base `/api/v1`.

- `GET /health`
- `GET /me`
- `POST /uploads`, `POST /uploads/{id}/complete`
- `GET /library`, `GET /library/{id}`, `DELETE /library/{id}`
- `GET /library/{id}/play`
- `POST /library/{id}/detect`, `GET`, `POST /cancel`
- `POST /library/{id}/render`, `GET`, `POST /cancel`
- `POST /library/{id}/preview`, `GET /previews/{id}`
- `GET /library/{id}/download`
- `GET /billing/estimate`, `GET /billing/usage`
- `POST /webhooks/stripe`, `POST /webhooks/worker`

Use one error envelope:

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

## Worker contract

One Docker image, CPU and GPU modes.

- `GET /health`
- `POST /v1/probe`
- `POST /v1/dissect`
- `POST /v1/detect`
- `POST /v1/render`
- `POST /v1/preview`
- `POST /v1/cancel`

Requirements:

- HMAC-SHA256 signature over the raw body plus timestamp; reject skew over
  300 seconds.
- Idempotent by `job_id`.
- Progress callbacks to the API, at most once per second.
- Cancel checked between frames, between beats and before model calls.
- Every response reports `compute_seconds`, `device_class`, `model_versions`,
  input bytes and output bytes.
- Workers pull from R2 with short-lived presigned URLs and put output with a
  presigned PUT.
- Partial objects use `.part`; delete them on cancel or failure.

## Detection stack

Apple Vision is macOS-only. Do not build the cloud detector on it.

- Text: PaddleOCR PP-OCRv5, or RapidOCR on ONNX if packaging Paddle is too
  heavy.
- Tiling: 2×2 or 3×3 with 10% overlap for small text and corner marks.
- Logos/watermarks: Grounding DINO or OWLv2 with prompts `logo`, `watermark`,
  `channel bug`; optional SAM 2 mask refinement.
- User-drawn region always wins for burnt-in images.
- Keep low-confidence candidates and mark them; do not silently drop them.
- Store masks as PNG/WebP in R2 with `provenance` and model version.
- Distinguish `no targets`, `scan truncated`, `OCR unavailable` and `detect
  failed`.

## Fill stack

- `blur` — pre-render diagnostic and honest fallback.
- `lama` — fast fill for still or slow text and small logos.
- `propainter` — default best for moving text and larger regions.
- `generative` — Flux Fill or SDXL inpainting for large/complex regions that
  need invented content.
- `cover` — explicit user-requested cover only.

A missing engine disables the option with a reason. Never silently downgrade.

## Billing

Render-hour equivalent:

```
weight(cpu) = 0.10
weight(gpu_standard) = 1.00
weight(gpu_premium) = 2.50

render_hours = compute_seconds * weight / 3600
```

- Worker reports compute-seconds by device class.
- API writes a `usage_ledger` row and an idempotent Stripe meter event.
- Show an estimate before render; bill actual compute after.
- Cancelled and failed jobs bill only consumed compute.
- Detection and preview are metered too.

## Milestones

1. **M0 Contract** — migrations, OpenAPI, worker schemas, beat manifest,
   selection revision, error codes. Freeze before UI code.
2. **M1 Accounts and library** — OAuth, user library, presigned upload, proxy,
   real phone upload.
3. **M2 Beats and detection** — CPU worker probe, dissect, OCR, logo detection,
   masks, groups, coverage.
4. **M3 Review** — responsive timeline, groups, tight bars, include/exclude,
   manual range and region.
5. **M4 Pre-render** — cloud blur/fill preview of selected beats.
6. **M5 Render** — GPU fill on selected beats, parallel segments, concat, audio
   mux, download.
7. **M6 Billing and launch** — estimate, ledger, Stripe, quotas, retention.
8. **M7 Best quality** — ProPainter, generative fill, automatic logo detection.

## First three tasks

1. Scaffold the monorepo: `web/`, `api/`, `worker/`, `docs/`. Add local dev
   commands, TypeScript and Python lint/format, and CI.
2. Write `api/migrations/0001_init.sql` and the OpenAPI bundle for the routes
   above. Include the exact group/member/revision/preview/ticket schemas.
3. Build the API skeleton: Clerk JWT verification, `GET /health`, `GET /me`,
   presigned upload, R2 HEAD verification, library list/detail, and a persisted
   job record.

Do not start the review UI before the contract and upload path exist.

## Product constraints

- Cloud only. No local runner, no desktop install, no LAN renderer.
- Phone must complete upload → review → render → download.
- Full-length output, source-faithful. Not a reel.
- Selective work: render only beats with selected targets.
- Real media only for acceptance. No stock clip, no generated demo, no fake
  voice, no fake frame, no fake progress, no fake success.
- No hidden spend. Show estimate, actual usage and balance.
- Classic is reference only. Port `detect.py`, `textfill/` and `clean_source.py`
  deliberately into `engine/`; never merge the Classic lane.

## Reference

Classic is reference only. It lives on `origin/classic` in this same repo at
commit `bb3e89e`. There is no Classic worktree.

```bash
git fetch origin classic
mkdir -p engine
git archive origin/classic \
  detect.py clean_source.py pipeline.py textfill \
  | tar -x -C engine
```

Adapt the ported files. Do not import Classic app modules.

- `detect.py` — tracklets, ranges, fill planning.
- `clean_source.py` — full-source fill, encode, audio mux, cancel, cache.
- `textfill/` — LaMa, masks, estimate, cache.
- `pipeline.py` — probe and frame sampling.

## Acceptance

- Real phone uploads a 60-second 1080p clip and plays the proxy.
- A subtitled clip returns beats, groups, members, boxes, masks, coverage and a
  revision.
- A 0.2-second text flash is found in a frame-by-frame beat scan.
- A corner logo is found and masked.
- A burnt-in image is removable from a user box.
- Clean beats measure above 45 dB PSNR against the source after assembly, or
  are stream-copied unchanged.
- Text-bearing beats have no readable text at 100% zoom.
- Cancel leaves no output and no `.part`; retry resumes completed beats.
- Ledger seconds match worker compute within 2%.
- Cross-user access returns `403` or `404`.
- No video bytes touch Pages or the API Worker.
- No fake media, voice, progress or success anywhere.
