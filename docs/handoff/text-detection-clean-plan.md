# Text detection and Clean: stop over-cleaning

Date: 2026-11-06
Status: plan
Trigger: one 89-second job held **2.0 GB of AI-fill cache** and 49 Clean layers.
The notes still showed junk reads: `-500Z`, `CPA/`, `CPAI`.

## 1. What "overfitting" means here

The pipeline is fitting the Clean plan to OCR noise, not to text:

- one layer per OCR observation instead of one per text that persists;
- low-confidence, one-frame reads become layers;
- the whole text box is repainted, not only the glyphs;
- every layer and keyframe is cached as an uncompressed array;
- nothing caps layers, filled area or cache per job.

That produces 49 layers, four residual-text notes that are OCR junk, and a 2 GB
cache for a short video. Better detection is the first fix; the cache format is
the second.

## 2. Where the 2 GB came from

The fill span cache writes one H.264 clip per beat. That is bounded.

The keyframe cache is the problem:

- `textfill._SavedFills` writes **one uncompressed `.npy` per model keyframe**.
- The array is the crop area the model saw, not a compressed image.
- A 720p crop can be hundreds of KB per frame. Hundreds of keyframes reach
  gigabytes.
- `SAVED_MAX_BYTES = 2 GB` is a **global** cap, so one job can take it all.
- There is no per-job cap and no UI warning.

So a job can spend 2 GB to save a fill that a compressed clip would hold in tens
of MB.

## 3. Detection plan

### 3.1 Multi-frame consensus

Do not trust one OCR read.

- Sample OCR at 4–6 fps in the candidate regions.
- Cluster observations by box IoU, time gap and text similarity.
- Keep a tracklet only when it has at least 3 observations and at least 0.5 s
  of screen time.
- A single-frame read becomes a suggestion, never an auto-Clean layer.

### 3.2 Script-aware junk filter

Current filter accepts some garbage because it only checks confidence and token
shape. Add:

- reject Latin tokens with no vowels above two characters;
- reject strings with no letters or CJK characters;
- reject mixed-case random strings (`CPAI`, `CPA/`, `-500Z`);
- reject a trailing slash or a leading hyphen followed by digits;
- require OCR confidence `>= 0.55`, or `>= 0.40` with multi-frame agreement;
- second-pass OCR at 2× on the crop; keep only text read twice with different
  preprocessing.

Tune against labelled clips, not one video.

### 3.3 Speech correlation

Baked subtitles usually match the transcript.

- Fuzzy-match tracklet text to transcript words in the same time range.
- Boost confidence on a match.
- Penalise random caption-band text with no speech match.
- Do not auto-clean non-speech text unless the user ticks it.

### 3.4 Block, not line

- Merge OCR lines that form one subtitle block: same area, stacked lines, close
  time ranges.
- One tracklet = one text block over its lifetime.
- Split only when the layout changes, not when a line changes.
- Target: at most 6 auto-clean layers per minute.

### 3.5 Visual persistence

A logo or UI label persists. A B-roll sign flashes.

- Require either a speech match or 1.5 s of stable pixels.
- Exclude dynamic text unless explicitly selected.
- Use the existing classifier (`subtitle`, `title`, `lower_third`,
  `handle_or_logo`, `watermark`, `credit`, `screen_text`) as a prior, not a
  verdict.

## 4. Auto-clean plan

- One layer per tracklet, ranges = the tracklet lifetime.
- Default to the **line mask** from OCR boxes, not the full box.
- Use the text mask when available; fill glyphs, not the background.
- Choose the method by confidence and cost:
  - high-confidence subtitle, busy background → AI fill;
  - small or low-confidence text, static background → blur;
  - a text behind the crop → skip.
- Show a plan before applying:
  - number of texts, layers, seconds, estimated fill time and cache size;
  - warn above 6 layers/min, 20 minutes, or 500 MB.
- Re-scan a few frames after Clean; if residual text or overfill appears, do not
  apply the plan automatically.

## 5. Cache plan

1. **Replace `.npy` keyframes** with compressed holes:
   - PNG/WebP for the filled crop, or a single compressed clip per span.
   - Keep the manifest separate; never store full raw frames.
2. **Per-job cap**: default 512 MB, hard cap 2 GB, LRU within the job.
3. **Global fill cache** keyed by:
   `source hash + span + mask hash + method + model signature`.
4. **One cache artifact per span**, not per frame and per layer.
5. **Delete with the job**; no orphan previews, proxies or saved fills.
6. **Show usage** in Storage: fill, spans, previews, proxies.

Expected: the same 89-second job should stay under 100 MB of fill cache.

## 6. Metrics

Measure on a labelled corpus, not on one clip:

| Metric | Target |
|---|---|
| False text tracklets | < 1 per minute |
| Auto-clean layers | <= 6 per minute |
| Fill cache | < 100 MB per minute of cut |
| Fill time | record before and after |
| Changed pixels outside text | < 10% |
| Residual text after clean | < 1 per clip |
| Duplicate tracklets | 0 |

Log these per job and show them in Check/Clean.

## 7. Phases

| Phase | Work | Gate |
|---|---|---|
| 1 | Instrument: tracklets, layers, cache bytes, fill seconds | Numbers match disk |
| 2 | Multi-frame consensus + junk filter + speech match | Labelled clips pass |
| 3 | Block merge and auto-clean budget | <= 6 layers/min |
| 4 | Line masks + method choice | Overfill under 10% |
| 5 | Compressed keyframe cache + per-job cap | < 100 MB/min |
| 6 | Global fill cache and job-delete cleanup | Same source reuses fills |
| 7 | Plan preview and residual check | No auto-apply above budget |

## 8. Non-goals

- No per-video threshold tuning. Thresholds live in settings and are tested on
  the corpus.
- No second model. Detection quality comes from consensus, not a bigger net.
- No silent auto-clean. Above the budget, the user sees the plan first.

## 9. Files

- `detect.py` — OCR filter, merge, tracklets.
- `cleanup.py` — tracklet-to-layer plan, merge rules.
- `routes_studio.py` — auto-clean route and budget.
- `textfill/__init__.py` — keyframe cache, span cache, pruning.
- `static/studio/edit/layers/clean.js` — plan summary and warnings.
- `tests/test_auto_clean.py`, `tests/test_clean_r0.py`, `tests/test_textfill.py`.
