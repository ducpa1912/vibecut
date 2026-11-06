# Clean and AI fill

Updated 2026-11-06. This page starts with how Studio removes burned-in text today.
The original planning API is documented after it and is still in use.

## How Studio cleans text

1. **Scan.** `detect.py` samples the video at 4 frames a second, up to 3600 frames,
   and reads text at 1280 wide. Each line gets one tracklet with its own box and time. Weak reads are
   kept when a neighbouring frame reads the same words, and repeats are dropped.
   Logos on objects start unticked.
2. **Plan.** `plan_fills` measures how much the picture changes around each line
   against the video's own noise floor, and saves `fill_plan` on the tracklet.
   A line within four times the noise gets one fill. A moving line gets up to six
   fills a second. Clean layers copy this as `fill_keys`. Drawn boxes and old scans
   have no plan, so they adapt while rendering: three fills a second when the
   picture holds still, up to six when it moves, and more only at a cut. Press
   **Scan again** on an old scan to get a plan.
3. **Layers.** A Clean layer is AI fill or blur, on a box or painted mask, with its
   own time. Up to 1000 layers (`edits.MAX_CLEAN`). All found text can be cleaned;
   a watermark, handle or logo needs a tick for that video.
4. **Fill.** `textfill/` runs before the cut, one clip per beat, in
   `jobs/<id>/fill/<key>.mp4`. Only the area holding text goes to the model, and a
   mask finds the letters inside the box. Motion is checked only near the text,
   and a jump starts a new fill.
5. **Saved fills.** Each LaMa or MI-GAN result goes to `jobs/<id>/fill/saved/` as it
   finishes, named by the model, crop and hole. After a stop, the run replays and
   only the missing fills reach the model. A later edit reuses every fill it still
   asks for. They are tidied after 14 days, past 2 GB across all videos, or when free
   disk drops below 10 GB, which also stops new ones being saved.

## Render choices

Finish offers three choices when a moment has AI fill. None changes the Edit, and a
choice other than the default makes a new render and leaves the plain one alone.

- **AI model.** For this render only. Clean keeps its own model.

- **AI fill on CPU or GPU.** The GPU option runs LaMa or MI-GAN through PyTorch on the
  Apple GPU. If the GPU fails, the render carries on with the CPU. On plain arrays on
  an M1 8 GB Mac, LaMa on the GPU took 0.36 s against 2.37 s at 304×512, and matched
  the CPU's picture to within 1 level out of 255. It uses more memory.
- **Follow camera motion.** One fill moves with the camera, its light is matched to
  the picture around the text, and real pixels replace it as they come into view. When
  the area around the text stops matching, such as a hand crossing it, the shot goes
  back to key frames for a while. It needs OpenCV.

A drawn box of 5% of the picture or more says what it costs. When the scan has found
text inside it, **Clean only the N lines inside** swaps it for tight boxes.

| Engine | Default | Notes |
|---|---|---|
| LaMa | Yes | Per frame, flexible input up to 512 on the longest side. CPU uses `lama_fp32.onnx` and `onnxruntime`. GPU uses `big-lama.pt` and `torch` |
| MI-GAN | No | Per frame, always reads a 512 square, so LaMa is faster on thin lines on the same chip. `migan_traced.pt` and `torch`, on CPU or GPU |
| STTN | No | Video model, heavier. Needs `torch` |
| Telea, Navier-Stokes | No | OpenCV, about a fifth of a second a frame, smear on detail. Optional, needs `opencv-python-headless` |

Moving backgrounds can still distort, because LaMa fills each frame alone. Timings
and the founder's review are in `docs/testing/studio-clean-fill-retest.md`. Settings
are listed in `README.md` under Configuration.

# Cleanup planning API

Deterministic cleanup planning for a finished video with baked-in text. It returns
a plan only: it does not render, modify, or queue media.

## Enable

Cleanup is **on by default** since Wave 4; the rights attestation gates it.
To turn it off, set:

```bash
VIBECUT_ENABLE_CLEANUP=0
```

Accepted off values: `0`, `false`, `no`, `off`. When the flag is off, the
endpoint returns `404`. **The gate runs in HTTP middleware before FastAPI
parses the body**: malformed JSON, a missing body, or a wrong `Content-Type`
still returns `404` when cleanup is off. When the flag is on, those malformed
requests return `422`. No cloud provider is called and no new dependency is
required.

## Endpoint

```http
POST /api/jobs/{job_id}/cleanup/plan
Content-Type: application/json
```

```json
{
  "artifact_id": "art_0123456789abcdef01234567",
  "aspect": "9:16",
  "method": "cover",
  "boxes": [
    {"x": 0.08, "y": 0.70, "w": 0.84, "h": 0.20}
  ],
  "attestation": true,
  "range": {"start": 0.0, "end": 8.0}
}
```

Send `artifact_id` **or** `story_id`; sending both is rejected. If neither is
sent, the plan uses the job source. `range` is optional and uses absolute
source seconds. It must stay inside the selected artifact/story span.

### Body

| Field | Required | Meaning |
|---|---|---|
| `aspect` | yes | Output aspect: `9:16`, `4:5`, `1:1`, or `16:9`. |
| `method` | yes | `crop`, `cover`, or `blur`. |
| `boxes` | no | Manual normalized boxes (`0..1`, top-left origin). Explicit boxes override OCR. |
| `attestation` | yes | `true` or a non-empty ownership/permission statement. |
| `range` | no | `{start, end}` in absolute source seconds. |
| `artifact_id` | no | Finished render to clean. |
| `story_id` | no | Clip-set story to clean when no artifact exists. |

Box: `{"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.2, "label": "caption"}`.
Boxes must stay inside the frame, have positive width/height, and number at
most 64. Additional request fields are rejected.

### Text detection

1. Explicit `boxes` are used as-is.
2. Otherwise exact OCR geometry is read from the job analysis scene fields
   `ocr_boxes`, `text_boxes`, `ocr_regions`, `text_regions`, or `ocr_lines`.
3. If scene OCR text exists but no geometry was retained, the plan creates an
   approximate bottom-center region, sets `detection.approximate = true`,
   lowers `detection_confidence`, raises `residual_risk`, and adds a warning.
4. If no text is detected, `cover` and `blur` are rejected because they would
   do nothing. `crop` is allowed as a reframe with a warning.

### Methods

- `crop` trims text that touches a frame edge, then fits and scales the target
  aspect. Text in the frame interior can remain; the quality report says so.
- `cover` fills each box with opaque black.
- `blur` describes an isolated region blur (radius 24).

The plan's `filter_chain` is pure declarative data for a future renderer. It is
not executed and is not an ffmpeg command.

## Response

```json
{
  "plan": {
    "schema_version": 1,
    "kind": "cleanup_plan",
    "job_id": "job1",
    "source": {
      "type": "artifact",
      "artifact_id": "art_...",
      "story_id": "st_...",
      "clip_set_id": null,
      "media": "artifacts/art_.../reel.mp4",
      "aspect": "9:16",
      "width": 1080,
      "height": 1920,
      "duration": 8.0,
      "range": {"start": 0.0, "end": 8.0},
      "clips": []
    },
    "aspect": "9:16",
    "method": "cover",
    "boxes": [
      {
        "x": 0.08,
        "y": 0.7,
        "w": 0.84,
        "h": 0.2,
        "label": "",
        "source": "explicit",
        "confidence": 1.0
      }
    ],
    "detection": {
      "source": "explicit",
      "approximate": false,
      "confidence": 1.0,
      "ocr_scene_ids": []
    },
    "crop": null,
    "filter_chain": [
      {
        "filter": "drawbox",
        "box": {"x": 0.08, "y": 0.7, "w": 0.84, "h": 0.2},
        "rect": {"x": 86, "y": 1344, "w": 907, "h": 384},
        "color": "black",
        "opacity": 1.0,
        "thickness": "fill",
        "description": "drawbox=x=86:y=1344:w=907:h=384:color=black@1.0:t=fill"
      }
    ],
    "quality_report": {
      "detection_confidence": 1.0,
      "method": "cover",
      "residual_risk": "low",
      "face_overlap_warning": false,
      "review_required": true,
      "limitations": ["..."]
    },
    "warnings": ["Plan only: no media was modified, rendered, or queued."],
    "limitations": ["..."],
    "attestation": {
      "required": true,
      "accepted": true,
      "statement": "User attested ownership or permission to edit."
    }
  },
  "quality_report": {
    "detection_confidence": 1.0,
    "method": "cover",
    "residual_risk": "low",
    "face_overlap_warning": false,
    "review_required": true,
    "limitations": ["..."]
  },
  "warnings": ["Plan only: no media was modified, rendered, or queued."]
}
```

`quality_report` always contains:

| Field | Meaning |
|---|---|
| `detection_confidence` | `0..1`; manual boxes are `1.0`, approximate OCR is low. |
| `method` | Canonical method (`crop`, `cover`, `blur`). |
| `residual_risk` | `low`, `medium`, or `high`. |
| `face_overlap_warning` | True when a cleanup region touches a detected face. |
| `review_required` | Always true in this prototype. |
| `limitations` | Explicit scope limits. |

## Status codes

| Code | Case |
|---|---|
| `200` | Plan returned. No job mutation. |
| `404` | Feature flag off (checked before body parsing); job, artifact, or story missing. |
| `409` | Artifact not ready, media missing, analysis not ready, or ambiguous story id. |
| `422` | Invalid box/aspect/range, malformed body while enabled, unsupported method, watermark/inpaint intent, or missing attestation. |

## Watermark policy

- There is **no automatic watermark detection**. Scene OCR reads on-screen text
  and may not preserve geometry; it is not a watermark classifier.
- Cleanup targets are explicit operator boxes (or OCR text geometry when
  retained). The ownership attestation is required for every plan.
- Methods and box labels that explicitly name a watermark are refused, even
  with an attestation. Do not use this API to remove a third-party watermark.
- Detection is intent-level only: there is no content classifier proving that a
  box is or is not a watermark. The operator is responsible for owning the
  content or having permission to edit it.

## Limits

- **Plausible cleanup, not restoration.** Covered, blurred, or cropped pixels
  are not recovered. There is no temporal reconstruction.
- **No watermark removal.** Supplying a watermark method or labelled box is
  rejected. There is no automatic watermark detection and no guarantee that
  every text overlay is removed.
- **No generative repair.** No inpainting, face repair, logo repair, or
  generative fill.
- **Review is required.** OCR detection is advisory and approximate when exact
  boxes are absent. A human must review the plan and every output.
- **No render path.** This prototype does not add a paid UI or alter paid v1
  behavior.
