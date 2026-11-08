# DuckClean contract (M0)

Status: **frozen** for M1. `HANDOFF.md` wins any conflict; this file records the
exact wire shapes and derived values the code depends on, and lists every
decision made while freezing so nothing is silently assumed.

Normative artifacts:

| Artifact | Path | Role |
|---|---|---|
| Schema | `api/migrations/0001_init.sql` | Tables, constraints, indexes |
| HTTP API | `api/openapi.yaml` | Wire shapes, status codes, tickets |
| Runtime validation | `api/src/schemas.ts` | zod mirror used by the Worker |
| Revision hashing | `api/src/canonical.ts` | Canonical JSON + revision hashes |
| Errors | `api/src/errors.ts` | One envelope, status and action per code |
| Worker wire | `worker/duckclean_worker/contract.py` | Pydantic models, route payloads |
| Worker signing | `worker/duckclean_worker/signing.py` | HMAC-SHA256 + skew |

A change to any wire shape changes this file in the same commit.

## 1. Decisions frozen in M0

These were open or under-specified in `plan.md`; the plan is updated to match.

1. **Previews are render jobs.** `render_jobs.kind` is `render` or `preview`, so
   preview and render share one state machine, one segment table and one cancel
   path. `GET /previews/{id}` looks up a `kind=preview` job by id.
2. **Groups span beats.** A group is a visual area or logo cluster and has no
   `beat_id`. Independence from beats is what lets a corner logo be one group
   across the whole video. Each member's ranges carry `beat_id`, so render
   planning is a direct group-by.
3. **Ranges carry frames, not seconds.** `[start_frame, end_frame)` plus
   `beat_id` and `beat_index`. Milliseconds are derived. Nothing that is hashed
   contains a float.
4. **Boxes are integer pixels in the source display frame** (rotation applied),
   not normalised floats. The UI normalises for the overlay; the renderer uses
   pixels directly. Integer boxes keep masks and hashes reproducible.
5. **Detection cadence is every frame.** `frame_policy` has exactly one value,
   `every_frame`. A beat whose frame cap is hit reports `truncated` and
   `frames_skipped`; it never silently samples.
6. **Masks are per member range**, stored as PNG/WebP in R2 with `provenance`
   and `model_version`. Render receives signed mask URLs, so no detection model
   runs during render.
7. **One package manager.** npm workspaces (`web`, `api`). No pnpm/Bun lockfile.
8. **Python packaging is `pyproject.toml`.** No `requirements.txt`; the image
   installs the package with `pip install .`.
9. **The worker image lands with the CPU worker (task 4).** M0 ships the wire
   contract, not a route that would fake a pipeline.
10. **Selection revision is separate from detection revision.** Detection
    revision identifies the reviewed result set; selection revision identifies
    the exact work (which members, which frames, which engine). Retries reuse
    completed segments by selection revision.
11. **M1 additions (0002).** `poster_assets` exists because a still has no fps
    or duration; `library_items.poster_asset_id` points at it. `worker_jobs`
    is dispatch and retry state only — source, beat, detection and render
    truth stays in their own tables. The worker gains `POST /v1/proxy`, and
    an upload can be re-signed while it is still pending.
12. **LaMa is CPU-only.** The fast clean path uses LaMa on the CPU worker. GPU
    is reserved for ProPainter and generative fill. The API planner resolves
    `lama` to `cpu`; the worker rejects `lama` with `gpu_standard` or
    `gpu_premium`. This is enforced in `api/src/schemas.ts` and
    `worker/duckclean_worker/contract.py`.

## 2. Identity and ownership

- Clerk JWT, verified against JWKS: issuer, audience, expiry, `sub`.
- `users.oauth_subject` is the only identity join. Email is mutable metadata.
- Every table except `users` carries `user_id`; every query filters by it.
- Cross-user access returns `404` for library items and `403` only where a
  resource is known to exist but is not the caller's. Never partial data.
- The `Authorization` header is never forwarded to R2 or to workers.

## 3. Error envelope

Every failure, from any route, is:

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

| Code | HTTP | Retryable | Default action |
|---|---|---|---|
| `unauthorized` | 401 | no | `sign_in` |
| `forbidden` | 403 | no | `contact_support` |
| `not_found` | 404 | no | `none` |
| `validation` | 400 | no | `none` |
| `conflict` | 409 | yes | `retry` |
| `too_large` | 413 | no | `upgrade_plan` |
| `unsupported_media` | 415 | no | `reupload` |
| `quota` | 402 | no | `upgrade_plan` |
| `rate_limited` | 429 | yes | `retry` |
| `stale_detection` | 409 | no | `reload_detection` |
| `worker_unavailable` | 503 | yes | `retry` |
| `source_unreadable` | 422 | no | `reupload` |
| `render_failed` | 500 | yes | `retry` |
| `cancelled` | 409 | yes | `retry` |
| `internal` | 500 | yes | `retry` |

`message` is safe to display. It never contains OCR text, filenames, storage
keys or signed URLs. `detail` is structured and loggable.

## 4. State machines

```
library_item   uploading -> uploaded -> probing -> dissecting -> ready
               uploading -> upload_incomplete        (lifecycle reaper, 24 h)
               any (non-terminal) -> failed
               any -> deleting -> (deleted_at set)

detection_run  queued -> running -> succeeded | failed | cancelled
               succeeded + truncated=true is a partial scan, not "no text"

render_job     queued -> planning -> rendering -> assembling -> finalizing -> ready
               any (non-terminal) -> cancelled | failed

render_segment pending -> running -> done | failed | lost | cancelled
```

A cancelled job never exposes an output. A failed or cancelled job bills only
the compute the worker reported.

## 5. Tickets and storage

| Ticket | Method | TTL | Scope |
|---|---|---|---|
| Upload | `PUT` | 15 min | One object, exact key, no listing; content type is signed |
| Upload re-sign | `PUT` | 15 min | Same pending object and item; `409` once completed |
| Play (proxy) | `GET` | 10 min | Proxy object |
| Mask overlay | `GET` | 10 min | One mask object |
| Download | `GET` | 10 min | Final output, attachment filename |
| Worker input | `GET` | 15 min | Source object |
| Worker output | `PUT` | 60 min | Job output or `.part` object |

Key layout:

```
u/{user_id}/src/{asset_id}/source.{ext}
u/{user_id}/src/{asset_id}/proxy.mp4
u/{user_id}/src/{asset_id}/poster.jpg
u/{user_id}/detect/{run_id}/mask/{mask_id}.png
u/{user_id}/render/{job_id}/beat/{beat_index:05d}.mp4
u/{user_id}/render/{job_id}/beat/{beat_index:05d}.mp4.part
u/{user_id}/render/{job_id}/final.mp4
u/{user_id}/render/{job_id}/final.mp4.part
u/{user_id}/preview/{job_id}.mp4
```

Lifecycle: abandoned uploads 24 h; masks with their revision (superseded
revisions 7 days); beat segments deleted after successful assembly; `.part`
deleted on cancel, failure or 24 h; outputs per plan retention.

Completion is decided by R2 `HEAD`, never by the client. A missing object, a
size that differs from the declared ticket, or a mismatched client ETag is
`source_unreadable` with `detail.reason` (`missing_object`, `size_mismatch`,
`etag_mismatch`), action `reupload`, and the item becomes `upload_incomplete`.
The client-reported `bytes` must equal the ticket; a different value is
`validation` before any HEAD.

## 6. Canonical JSON and revisions

All hashes use canonical JSON (`api/src/canonical.ts`, mirrored in the worker):

- UTF-8, object keys sorted by code point, no insignificant whitespace.
- Numbers must be **safe integers**. Floats throw. Times are milliseconds or
  frame indices, never seconds.
- Arrays keep their given order unless the hasher sorts them (selection does).
- Non-plain objects, `undefined` and `NaN` throw.

### 6.1 Beat manifest hash

```json
{
  "v": 1,
  "source": { "sha256": "…", "bytes": 13810783, "frame_count": 167,
              "width": 1440, "height": 2560 },
  "params": { "fps_num": 30, "fps_den": 1, "max_seconds_milli": 4000,
              "min_seconds_milli": 1000, "scene_threshold_milli": 300 },
  "beats": [ { "index": 0, "start_frame": 0, "end_frame": 60,
               "boundary": "start" } ]
}
```

`beat_manifest_hash = sha256(canonical_json(above))`. The hasher rejects a
manifest whose beats do not start at frame 0, tile contiguously, and end at
`source.frame_count`.

### 6.2 Detection revision

```json
{
  "v": 1,
  "source_sha256": "…",
  "beat_manifest_hash": "…",
  "detect": { "text": true, "logos": true, "tile_small_text": true,
              "frame_policy": "every_frame", "max_width": 1920,
              "min_confidence_milli": 350, "regions": [],
              "scope_beat_indexes": null },
  "engine": { "ocr": "paddleocr", "logo": "grounding_dino",
              "segmentation": "sam2" },
  "models": { "ocr": "ppocrv5-2026.1", "logo": "grounding-dino-1.0" }
}
```

The API computes it; clients never send model versions. A different OCR model
version is a different revision even when the boxes look identical.

### 6.3 Selection revision

Input is the normalised selection. Normalisation happens inside the hasher so
argument order can never change the revision:

1. Drop `range_mode=ranges` members with no non-empty range.
2. Sort ranges by `(beat_index, start_frame, end_frame)`; merge overlapping and
   touching ranges per beat.
3. Sort members by `member_id`, groups by `group_id`, regions by `region_id`.
4. Drop groups left with no members.

```json
{
  "v": 1,
  "detection_revision": "…",
  "groups": [ { "group_id": "…", "engine": "lama",
                "device_class": "cpu",
                "members": [ { "member_id": "…", "range_mode": "ranges",
                               "ranges": [ { "beat_index": 0,
                                             "start_frame": 10,
                                             "end_frame": 40 } ] } ] } ],
  "manual_regions": [],
  "render": { "kind": "render", "codec": "h264", "pixel_format": "yuv420p",
              "crf": 18, "preset": "medium", "width": 1440, "height": 2560,
              "fps": "source", "audio": "source",
              "resolution_scale_milli": 1000, "time_limit_s": null }
}
```

`range_mode=whole_source` stays a marker in the hash and is expanded against the
beat manifest by the render planner. Empty ranges never mean the whole video:
the database rejects that combination and so does the worker contract.

## 7. Beats

### 7.1 Dissection (deterministic)

1. Scene pass: ffmpeg at 480 px height, `select='gt(scene,0.30)'`, PTS taken per
   frame.
2. Cut points: `0`, scene timestamps, `frame_count`.
3. Snap every cut to `round(t * fps_num / fps_den)`, clamp to
   `[0, frame_count]`, drop duplicates.
4. Split any span longer than `max_seconds` into the fewest equal pieces that
   are all at least `min_seconds` where possible.
5. Merge a span shorter than `min_seconds` into the next span when the result
   stays within `max_seconds`; otherwise into the previous span; otherwise leave
   it short and count it as-is.
6. Assign boundaries: first `start`, scene-cut starts `scene`, cap splits `cap`,
   last `end`.
7. Assert contiguity and `sum(end_frame - start_frame) == frame_count`.

Same source hash + same params + same fps ⇒ same manifest hash.

### 7.2 Per-beat work plan

The API expands the selection, not the worker:

- A range `[start, end)` in beat *i* clamps to the beat's own frame span.
- A beat with at least one clamped range is a **fill beat**.
- A beat with none is a **passthrough beat**: identical H.264/yuv420p encode
  parameters, no model call.
- Segment key: `sha256(selection_revision + ":" + beat_index + ":" + engine +
  ":" + params_hash)`. A retry reuses a `done` segment only when the key matches
  and the object still exists (`HEAD`).

## 8. Worker contract

One Docker image, CPU and GPU modes, selected by environment and validated at
startup.

```
GET  /health
POST /v1/probe
POST /v1/proxy
POST /v1/dissect
POST /v1/detect
POST /v1/render
POST /v1/preview
POST /v1/cancel
```

- Signature: `X-DuckClean-Signature: t=<unix>,v1=<hex>`, HMAC-SHA256 over
  `b"<t>." + raw_body`; `X-DuckClean-Key-Id` names the rotation. Skew over 300 s
  is rejected before the digest is compared.
- Idempotent by `job_id`; a repeated call returns the stored result.
- Progress callback: same signature, monotonic `seq`, at most one per second.
  The API ignores a duplicate `seq`.
- Cancel is checked between frames, between beats, before each model call and
  before each upload. On cancel the worker deletes `.part` objects and reports
  consumed compute.
- Every response carries `usage: { compute_seconds, device_class,
  model_versions, input_bytes, output_bytes }`.
- `POST /v1/proxy` returns the written proxy and poster facts
  (`width`, `height`, `duration_ms`, `fps_num`, `fps_den`, `bytes`, and the
  poster's `frame_index`). The API verifies the proxy's `HEAD` size before it
  records the derivative; a worker response alone is not proof.
- Detection returns groups/members/ranges/mask refs and coverage; it never
  returns pixels.
- A missing engine or model is reported (`available: false` with a reason) and
  disables that option. It never silently downgrades to a worse engine.

Coverage must satisfy `frames_read + frames_skipped == frames_total`. Truncated,
`ocr_unavailable` and `logo_model_unavailable` are separate flags from "no
targets". A beat that cannot be read is `failed`, not empty.

## 9. Billing

```
weight(cpu)          = 0.10
weight(gpu_standard) = 1.00
weight(gpu_premium)  = 2.50

render_hours = compute_seconds * weight / 3600
```

`usage_ledger.render_hours` is a generated column, so the stored number cannot
drift from the formula. One ledger row per metered job, deduped by
`idempotency_key`; one Stripe meter event keyed by that same row. Detection and
preview are metered at their own device weight. Estimates come from a measured
rate table, are labelled `is_estimate: true`, and are never used as the charge.

## 10. Limits (v1)

| Limit | Value |
|---|---|
| Upload bytes | 5,000,000,000 |
| Duration | 1,800 s |
| Display width / height | 4,096 px |
| Frame rate | 60 fps |
| Containers | mp4, mov, webm, mkv |
| Detection width cap | 1,920 px (request max 3,840) |
| Concurrent renders per user | 1 |
| Active detection runs per item | 1 |

Exceeding a limit is an explicit error (`too_large`, `unsupported_media`,
`quota`), never a silent truncation.

## 11. Frozen vs open

Frozen: table shapes and constraints, error envelope, revision inputs, ticket
TTLs, storage keys, worker route names and `usage`, the range rule, segment
semantics.

Open, to be settled with measurements: OCR backend choice (PaddleOCR vs
RapidOCR), logo model, rate-table constants, retention windows, and the point at
which clean beats are stream-copied instead of re-encoded.
