# Cloud architecture · simpler deployment

Date: 2026-11-04
Companion: [distribution plan](distribution-plan.md) · [license audit](licensing-audit.md)

## 1. Current architecture constraint

VibeCut is currently a **single Python process** with:

- FastAPI/Uvicorn serving UI, API, uploads and status
- four in-process thread pools: analysis (1), ingest (2), render (1), voice (1)
- a fifth Check pool (1)
- local JSON job records, local media files, local cache and SQLite admin
- ffmpeg/PyTorch/ONNX/Demucs/Whisper as subprocesses or in-process libraries

That is not a horizontally scalable multi-tenant design. Do not start with
Kubernetes and a queue you do not need. The cheapest correct cloud is **one
instance per tenant** with a persistent volume and a reverse proxy.

## 2. Recommended deployment ladder

### Phase 1 — single-tenant VM + Docker Compose (recommended first)

```text
Internet
  │ HTTPS
  ▼
Caddy / nginx  ──►  VibeCut container (1 process)
                      ├── FastAPI + static UI
                      ├── analysis/render/voice/check pools
                      ├── ffmpeg subprocesses
                      ├── /data volume (jobs, edits, settings, shares)
                      └── models volume (fill packs)
```

- 4 vCPU, 8–16 GB RAM, 100–200 GB SSD for a light single-user/team instance.
- One container, one volume, one reverse proxy. No Redis, no Postgres, no
  Kubernetes.
- `VIBECUT_TOKEN` set; Caddy terminates TLS; no direct port exposure.
- Healthcheck `/api/health`; restart policy `unless-stopped`.
- Back up `/data` daily; exclude cache directories where safe.
- Pin the image digest and record the SBOM/source-offer pack.

`docker-compose.yml` becomes: `vibecut` + `caddy`; add a named volume and
healthcheck. The current compose file is close; add Caddy/TLS and a real
healthcheck.

### Phase 2 — managed container

Fly.io / Render / Railway / ECS/Fargate with a persistent volume:

- one always-on instance (volume is attached to one machine)
- one region near the media source
- no autoscaling while state is local; a second instance would see different
  jobs
- object-storage backup job for `/data`

This is operationally simpler than Kubernetes but still single-tenant.

### Phase 3 — split only when measurements demand it

Add an external queue and worker split only when render throughput is the
bottleneck:

- API service: FastAPI, uploads, status, reads
- render worker: pulls jobs, writes artifacts
- shared Postgres/object storage for job state and media
- Redis/SQS for queueing
- auth and per-tenant isolation before any shared deployment

This is a code project, not a compose-file change. Do not pretend the current
in-process pools scale horizontally.

## 3. What to run in the container

| Component | Cloud choice |
|---|---|
| Python/FastAPI/uvicorn | Required |
| ffmpeg/ffprobe | Required; choose GPL-compliant or LGPL build (see plan) |
| yt-dlp | Required for URL import; plain package, no GPL extras |
| Pillow/NumPy | Required |
| STTN + LaMa | Optional build profile; Apache-2.0 models + torch/onnxruntime |
| Demucs | **Exclude** until weights are cleared |
| RoFormer | Preferred separation if needed |
| Whisper | Optional; Linux has no Apple Speech, so local STT needs mlx-whisper only on macOS; use cloud STT on Linux |
| Kokoro | Optional; ONNX CPU |
| DeepFilter/Silero | Optional; permissive |
| Apple Vision/Speech | Not available on Linux; use cloud OCR/STT or accept fallback |
| `say` TTS | macOS only |
| xhs_get | Never in the image |

## 4. Storage and data

| Path | Contents | Backup |
|---|---|---|
| `/data/jobs` | job records, sources, artifacts, edits, renders | Yes, critical |
| `/data/settings.json`, `/data/secrets.json` | settings and provider keys | Yes, encrypted |
| `/data/admin` | admin SQLite + audit log | Yes |
| `/data/models` | STTN/LaMa/packs | Re-downloadable; checksum |
| `/data/cache` | segment/layer/fill caches | Optional, regenerable |
| `/data/shares.json` | review tokens | Yes |

Use a volume, not container-local disk. Back up to an S3-compatible bucket with
versioning. Encrypt secrets at rest; never bake API keys into the image.

## 5. Security baseline

- Bind only through the reverse proxy; no public 8787.
- Set `VIBECUT_TOKEN`; use HTTPS; admin routes require HTTPS.
- Non-root container, read-only root filesystem, writable `/data` and `/tmp`.
- Limit upload size (`VIBECUT_MAX_UPLOAD_GB`) and disk quota.
- No `xhs_get`, no user cookies in logs.
- Redact tokens/URLs; keep provider keys server-side.
- Egress allowlist for model downloads/APIs if the environment supports it.
- One tenant per instance until real authentication exists. The shared bearer
  token is not multi-user auth.

## 6. Scaling rules

| Symptom | First action | Not this |
|---|---|---|
| Render queue long | bigger CPU / fewer concurrent jobs / lower quality | add replicas with local volumes |
| Analysis slow | raise CPU, profile ffmpeg/PyTorch | Kubernetes by default |
| Many tenants | separate instances or build auth + object storage + queue | share one volume |
| Fill slow | GPU worker or LaMa only | bundle Demucs because it is installed |
| Disk full | cache retention + backups | delete the only copy of jobs |

Keep `VIBECUT_RENDER_WORKERS` low. ffmpeg already saturates CPU; oversubscription
makes every render slower.

## 7. Deployment runbook (Phase 1)

```bash
# build and push a pinned image
docker build --build-arg WITH_FILL=sttn,lama -t registry/vibecut:VERSION .
docker push registry/vibecut:VERSION

# on the VM
mkdir -p /srv/vibecut/data /srv/vibecut/models
# place models in /srv/vibecut/models/fill
# set VIBECUT_TOKEN, VIBECUT_DATA=/data, VIBECUT_FILL_MODELS=/data/models/fill
docker compose pull
docker compose up -d
curl -fsS https://HOST/api/health
```

Acceptance:
- health reports ffmpeg + expected models
- one upload → analysis → edit → render
- one Clean fill (if enabled)
- one URL import with no GPL/AGPL downloader sidecar
- `/data` survives container replacement
- backup restore tested
- SBOM/source-offer/notices attached to the image digest

## 8. Cloud license posture

- **Hosted SaaS (no image/binaries to users):** GPL ffmpeg runs server-side;
  no GPL source offer is triggered by normal use. Keep notices in the image and
  do not use AGPL components. Charge for the service, not the binary.
- **Customer-hosted image/VM:** binary distribution. Ship GPL source/offer or
  build LGPL-only. Never label a GPL image as LGPL.
- **Model packs:** STTN/LaMa Apache-2.0; Whisper MIT; Kokoro Apache-2.0;
  RoFormer MIT; Demucs excluded. Include hashes and source URLs.
- **Apple-only features** are not available in Linux cloud. Do not advertise
  Apple OCR/STT parity there.

## 9. Simpler alternative: desktop-first, cloud later

If the near-term buyer is a single creator, the simplest “cloud” is a remote
Mac mini running the existing app behind Tailscale/Cloudflare Tunnel. It keeps
Apple Vision/Speech and VideoToolbox, avoids Linux OCR gaps, and uses the same
single-tenant model. It is not a multi-tenant SaaS, but it is a much smaller
step than rebuilding the backend. Use this only with a clear support and
security policy.
