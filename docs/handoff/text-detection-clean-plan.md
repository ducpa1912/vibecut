# Text detection and Clean: quality first

Date: 2026-11-06
Status: revised plan
Trigger: one 89-second job held **2.0 GB of AI-fill cache** and 49 Clean layers,
with junk reads such as `-500Z`, `CPA/`, `CPAI`.

## 1. Rule

**Every real text gets the highest-quality clean.** AI fill is the default and
stays the default. No downgrade to blur for low confidence, busy background,
small text or crop position. No skip based on those.

Precision work decides **what is text**. Quality work never decides **how well
to clean it**.

- A real text block is AI-filled.
- A doubtful read is shown for review, not silently blurred or dropped.
- A text outside the story is not cleaned because it is not on screen, not
  because it is hard.
- Blur remains a user choice, never an automatic fallback.
- If the fill model is missing, the job says AI fill is unavailable. It does
  not quietly produce a blur.

The 1m30s job that takes under 25 minutes locally is acceptable. The target is
not to make Clean cheap. The target is to stop fitting the plan to OCR noise.

## 2. What overfitting means here

- One layer per OCR observation instead of one per real text.
- One-frame, low-confidence reads become layers.
- Whole boxes repainted instead of glyph masks.
- Every keyframe cached as an uncompressed array.
- No measurement of false positives, duplicate tracklets or cache per job.

That produced 49 layers and 2 GB of cache for 89 seconds. Detection precision
and cache format are the fixes. Clean quality is not reduced.

## 3. Detection: find real text, not every read

### 3.1 Multi-frame consensus

- OCR at 4–6 fps in candidate regions.
- Cluster observations by IoU, time gap and text similarity.
- Keep a text only when it appears in at least 3 observations over at least
  0.5 s.
- A single-frame read becomes a review suggestion, not an auto layer.

### 3.2 Script-aware junk filter

Keep real words and real CJK runs. Reject OCR noise:

- Latin tokens with no vowels above two letters;
- strings with no letters or CJK;
- random mixed case (`CPAI`, `CPA/`) and stray `-500Z`;
- trailing slash / leading hyphen-digit patterns;
- OCR confidence below 0.55 unless multi-frame agreement is strong;
- second-pass OCR at 2×; keep only text read twice with different preprocessing.

Thresholds come from a labelled corpus, not one video.

### 3.3 Speech match

- Baked subtitles usually match the transcript.
- Fuzzy-match tracklet text to transcript words in the same time range.
- Boost a match; flag a caption-band read with no speech for review.
- A flag does not downgrade or skip the clean. It only controls auto-apply.

### 3.4 Block, not line

- Merge stacked OCR lines into one subtitle block.
- One tracklet = one text block over its lifetime.
- Split only when the layout changes.
- A 25-beat story should not produce 49 layers from one subtitle lane.

### 3.5 Persistence

- Prefer text that persists. A B-roll sign that flashes is still reviewable.
- Do not use persistence to choose blur or to skip.
- Use it to rank the review list and to merge observations.

## 4. Auto-clean: highest quality

- One Clean layer per real tracklet.
- Ranges = the tracklet lifetime.
- Default method = AI fill for every accepted text.
- Fill at the best available model and device. GPU when available; LaMa,
  MI-GAN or STTN as the user chooses.
- Mask from OCR lines and glyph segmentation, not the full box.
- Keep the line mask and the block box; the fill uses the tight mask.
- Show the plan before applying only when detection is uncertain. Confidence
  controls **review**, not method.

No layer-per-minute cap, no 20-minute cap, no 500 MB cap. The plan shows:
texts, layers, cleaned seconds, estimated time, cache estimate. The user can
proceed, because 25 minutes for 90 seconds is acceptable.

## 5. Cache: stop wasting space without limiting quality

The 2 GB came from `textfill._SavedFills`: one uncompressed `.npy` per model
keyframe, under a global 2 GB cap with no per-job view.

Fix the format and reuse:

1. Store filled holes as compressed PNG/WebP, or one compressed clip per span.
2. One artifact per span, not per frame and per layer.
3. Global fill cache keyed by
   `source hash + span + mask hash + method + model`.
4. Deduplicate identical spans across layers and jobs.
5. Delete with the job; no orphan previews or saved fills.
6. Show per-job cache use. Warn at a soft threshold; never drop a fill the
   current render needs.
7. Keep the current 25-minute local run acceptable. Compression is the win, not
   a smaller clean.

The same 89-second job should compress to well under 200 MB without reducing
the filled area or model quality.

## 6. Online Clean API

Goal: optional remote AI fill at **less than $0.05 per second of cleaned
footage**, with equal or better quality than local LaMa.

### 6.1 What to send

Only the spans that contain text. Not the whole 90 seconds.

- Upload each span (source video range + mask video) or a single montage of
  spans.
- Receive the filled span.
- Splice it back locally at the exact frame.
- Keep original audio locally.

If 90 seconds contains 20 seconds of text, the price is for 20 cleaned seconds,
not 90.

### 6.2 Candidate APIs

Prices read from provider pages on 2026-11-06. They change; recheck before
committing. A "run" is one provider call; frame counts and run time decide the
real per-second figure.

| Provider | Model | Input | Price | Per cleaned second | Notes |
|---|---|---|---|---|---|
| Replicate | ProPainter | video + mask | ~$0.039 per run, L40S $0.000975/s | ~$0.012–0.015/s | Flow-based video inpainting, subvideos of 80 frames, best quality fit for text |
| fal | VOID Video Inpainting | video + mask or prompt | $0.05 per video; $0.10 pass 2; +$0.05 SAM-3 mask | ~$0.008–0.023/s | Up to ~197 frames per run; generative, may invent background; test on text |
| Runway | Aleph 2.0 | prompt edit | $0.28/s | no | Over budget |
| fal | Wan / Kling / Veo video models | prompt | $0.05–$0.40/s | no | Generative; not mask-accurate |
| Replicate | Wan 2.1 / official video | prompt | $0.09–$0.25/s | no | Generative; not mask-accurate |
| Self-hosted | ProPainter / E2FGVI | video + mask | H100 $4.50/h on fal, RTX Pro 6000 $2.99/h | depends on throughput | Cheapest at volume after a benchmark |

Estimates:

- **ProPainter, 90 seconds all text**: 34 runs of ~80 frames at $0.039 ≈
  **$1.33** (≈ $0.015/s). Under the $4.50 budget.
- **ProPainter, 20 seconds of text**: 8 runs ≈ **$0.31**.
- **VOID, 90 seconds, one pass**: ~15 runs at $0.05 ≈ **$0.75**; pass 2 and mask
  can raise it to ~$2.25.
- **Runway Aleph**: 90 × $0.28 = **$25.20**, rejected.

The cheap options are ProPainter-style mask inpainting and VOID. ProPainter is
the safer quality bet for text; VOID needs a visual test.

### 6.3 Provider interface

```text
POST /api/jobs/{id}/clean/remote-estimate
  -> spans, cleaned seconds, provider price, estimate, quality warning

POST /api/jobs/{id}/clean/remote
  -> job, edit, provider, consent, budget
  -> queued remote fills; local render continues
```

- `CleanProvider` contract: `estimate(spans)`, `submit(span, mask)`,
  `status(id)`, `fetch(id)`, `cancel(id)`.
- One provider call per span chunk; overlaps blended locally.
- Remote result is verified: frame count, resolution, mask alignment.
- If remote fails, fall back to local AI fill. Never to blur.
- Cache remote results in the same global fill cache.
- Store provider, model, price and job id in the manifest.

### 6.4 Decisions for the user

- Upload only text spans, not the whole source.
- Explicit consent per job; show provider, bytes and estimate.
- Per-job budget is a warning/confirmation, not a technical cap.
- Keep local AI fill as the default; remote is an option for speed.

### 6.5 Quality gate

Run the same 5 clips through local LaMa, local STTN, remote ProPainter and
remote VOID. Compare:

- OCR residual inside the cleaned area;
- changed pixels outside the text mask;
- temporal flicker between frames;
- background texture and edge continuity;
- total time and cost per cleaned second.

Accept a provider only if it matches local quality on text and stays under
$0.05 per cleaned second.

### 6.6 Sources

- Replicate ProPainter: <https://replicate.com/jd7h/propainter>
  (model page: ~$0.039 per run, L40S, 80-frame subvideos).
- fal VOID: <https://fal.ai/models/fal-ai/void-video-inpainting>
  ($0.05 per video, pass 2 $0.10, SAM-3 mask +$0.05).
- Runway API pricing: <https://dev.runway.com/pricing>
  (Aleph 2.0 $0.28 per second).
- Replicate GPU pricing: <https://replicate.com/pricing>
  (L40S $0.000975/s).
- fal serverless GPU pricing: <https://fal.ai/pricing>
  (H100 from $4.50/h).

## 7. Metrics

| Metric | Target |
|---|---|
| False text tracklets | < 1 per minute |
| Duplicate tracklets | 0 |
| Layers per real text | 1 |
| Auto-applied doubtful text | 0 |
| Changed pixels outside text | < 10% |
| Residual text after clean | < 1 per clip |
| Cache per cleaned second | < 2 MB/s after compression |
| Local clean time | <= 25 min for 90 s |
| Remote cost | < $0.05 per cleaned second |

No cap on real layers. A video with 30 real texts gets 30 AI fills.

## 8. Phases

| Phase | Work | Gate |
|---|---|---|
| 1 | Instrument false text, layers, cleaned seconds, cache bytes | Numbers match disk |
| 2 | Multi-frame consensus + junk filter + speech match | Corpus false positives < 1/min |
| 3 | Block tracklets and review queue | One layer per real text |
| 4 | Tight glyph masks, always AI fill | Quality equal or better |
| 5 | Compressed keyframe cache + global dedupe | 89 s job under 200 MB |
| 6 | Provider interface + estimate/consent | Estimate matches invoice |
| 7 | ProPainter remote test | < $0.05/cleaned s, quality gate |
| 8 | VOID remote test | Same gate; keep only if it wins |

## 9. Non-goals

- No blur fallback for hard text.
- No skipping text because it is small, busy, low-confidence or near a crop.
- No hard cap that lowers quality.
- No per-video threshold tuning.
- No generative prompt editing of the whole frame.
- No remote upload without explicit consent.
