# Publishing VibeCut: open source + cloud

## Shape

Open-core:

- **`vibecut` (open source)** — the full local pipeline, UI, CLI, Docker. This is
  the same code the cloud runs.
- **`vibecut-cloud` (proprietary)** — accounts, billing, queueing, object
  storage, autoscaling workers, admin, abuse tooling. No video logic lives here,
  it imports the same core package.
- Suggested license: **AGPL-3.0** for the core if hosted competitors are a
  concern, or **Apache-2.0** if adoption matters more. Decide before the first
  public release; relicensing later needs every contributor's consent.
- Keep the job bundle format portable (`job.json`, plan, audio plan) so a user
  can move work between self-hosted and cloud.

## Cloud architecture

```
browser (same static UI)
   │ presigned upload → R2/S3
   ▼
FastAPI API ── Postgres (jobs, users, billing)
   │        └─ Redis / SQS queue
   ▼
workers (autoscaled)
   ├─ CPU: probe, scan, thumbs, ffmpeg segments, concat
   ├─ GPU: ASR, vision/OCR, Demucs, music generation
   └─ mux: audio beds + master reuse per job
   ▼
R2/S3 results → signed URLs / CDN
```

Key points:

- Uploads go straight to object storage with presigned URLs; the API never
  proxies gigabytes.
- Workers pull jobs from a queue, heartbeat, and write progress to Postgres.
  Cancellation is a queue message plus a worker signal.
- Reuse the local caches in cloud form: content-addressed sources, segment cache,
  video masters, audio beds. Cross-user caching only for identical source hashes
  with explicit opt-in.
- One region first; R2 has no egress fees, which matters for video.

## Apple-only features need cross-platform swaps

| Local engine | Cloud replacement |
|---|---|
| Apple Vision (OCR/faces/saliency) | PaddleOCR / Florence-2 + InsightFace/YOLO |
| SpeechAnalyzer / mlx-whisper | faster-whisper (large-v3-turbo) |
| Apple Translation / MLX / Ollama | Marian/NLLB + a small hosted LLM for rewrite |
| Apple `say`, Piper, Kokoro | Kokoro/Piper on workers, ElevenLabs as paid option |
| VideoToolbox | NVENC on GPU workers, libx264 CPU fallback |
| Apple FM | small local model (Qwen 3B) or a hosted API for premium |

The provider layer already isolates this; cloud config picks engines.

## Multi-tenant rules

- Per-tenant bucket prefixes and signed URLs; no filesystem paths in the API.
- One container per job, no shell interpolation of names, duration/size caps.
- Quotas: minutes analyzed, render minutes, storage, concurrent jobs.
- Metering: GPU-seconds and CPU-seconds per job, recorded with the job.
- Billing: Stripe subscriptions + credit packs; free tier with monthly minutes.
- Retention: source deleted after N days, derivatives after M days; user can
  delete immediately. Backups separate from the hot bucket.
- Moderation: upload scanning, CSAM/copyright reporting path, voice-clone
  consent recorded per asset.

## Unit economics (rough)

For a 10-minute 1080p source:

| Step | Compute | Cost at spot/on-demand |
|---|---|---|
| scan + metadata | 20–40 s CPU | ~$0.001 |
| ASR (faster-whisper) | 10–25 s GPU | ~$0.002–0.004 |
| stills + vision | 10–20 s GPU | ~$0.002–0.004 |
| Demucs (optional) | 15–40 s GPU | ~$0.003–0.006 |
| 3 renders (master + mux) | 30–60 s CPU/GPU | ~$0.003–0.01 |
| storage | ~200–400 MB | ~$0.002–0.01 / month |

So ~$0.01–0.03 compute per 10-minute job before margin; GPU minutes dominate.
Price at 3–5× compute plus storage, or use a flat credit model that hides spikes.

## Rollout phases

1. **OSS hardening (2–3 weeks)** — tests, Docker, docs, provider configs, job
   bundle import/export, deterministic renders.
2. **Cloud alpha (invite only)** — API + queue + workers + R2, no billing, one
   region, 10–20 users. Goal: parity on a real 20-minute source.
3. **Cloud beta** — auth, Stripe, quotas, metering, cancellation, retention,
   abuse tooling, status page.
4. **Scale** — GPU autoscaling, CDN, multi-region storage, per-plan concurrency,
   analytics on pipeline timings.
5. **Enterprise** — SSO, audit log, on-prem license of the cloud control plane,
   custom model routing.

## Risks

- Compute spikes on long 4K sources; enforce duration/resolution caps per plan.
- Model licenses: Llama community, Gemma terms, XTTS CPML (non-commercial) and
  Stable Audio weights — the cloud must not ship non-commercial models.
- Voice cloning consent and deepfake abuse; gate behind verification and
  provenance metadata.
- Apple parity: Vision/Speech/FM features need alternatives in the cloud; be
  explicit about the quality difference.
- Open-source competition: AGPL plus hosted-only features (queue, billing,
  collaboration) is the usual defensible split.
