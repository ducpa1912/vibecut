# Detection report — real attached clip

File: `/Users/happynghia/Downloads/人好猫坏！.mp4`
MD5: `57a6d164422eeb95a9517cf4727dd1b6`
Size: 13,810,783 bytes

This report is real-file evidence collected with the current local engine. It is
ground truth for this file. It is not evidence that the cloud detector is good
or bad, because the cloud detector uses a different OCR backend.

## Probe

| Field | Value |
|---|---|
| Duration | 5.572 s |
| Display size | 1440 × 2560 |
| Frame rate | 30 fps |
| Video | HEVC |
| Audio | AAC |
| Rotation | 0° |

## Detector runs

### Default path, 4 fps

- Frames read: 22
- Sample fps: 3.948
- Apple Vision: available
- OCR lines: 0
- Tracklets: 0
- `text.present`: false
- `text.confirmed`: true
- `clean_prefill`: empty

### 2 fps

- Frames read: 11
- Apple Vision: available
- OCR lines: 0
- Tracklets: 0

### Every frame

- Extracted all 167 frames at 30 fps.
- Apple Vision read all 167.
- OCR lines: 0 on every frame.

## Conclusion

**This clip contains no baked-in text.** Zero detections are correct. There is
no false negative to fix on this file, and DuckClean must not invent boxes or
render a “cleaned” file for it.

The visible content is a kitten on a bed; the filename is not on-screen text.
The full-resolution top and bottom strips were also checked, with no watermark
or caption.

`text.confirmed: true` means the OCR pass ran and the OCR backend was available.
It does **not** mean text was found. The UI must say **No text found** and
explain that the scan was complete; it must not say “cleaned” and must not start
a render.

## Cloud caveat

The cloud worker runs on Linux. Apple Vision is macOS-only and is not the
production OCR path. The production detector uses a Linux OCR stack (PaddleOCR
PP-OCRv5, or RapidOCR as the ONNX fallback) plus an open-vocabulary logo
detector. This clip's zero result must be reproduced with that stack before the
cloud detector is trusted on text-free video.

The local limits that motivated the cloud rewrite:

1. **Global 4 fps sampling.** Text under about 0.25 s can be missed. Cloud
   detection reads every frame inside a beat instead.
2. **Global frame cap.** Long clips drop below 4 fps. Cloud detection caps per
   beat, not per video, and reports coverage.
3. **Confidence floor.** Small, low-contrast or stylised text can be dropped
   before grouping. Cloud detection keeps low-confidence candidates and marks
   them.
4. **Tracklet cap.** Dense subtitle video can truncate. Truncation is reported
   separately from “no text.”
5. **Text only.** The current engine does not detect logos, watermarks or
   burnt-in images. Cloud detection adds an open-vocabulary region pass and a
   user-drawn region path.
6. **No manual fallback in the current flow.** DuckClean keeps manual range and
   region add as a first-class tool.

## Real-media calibration pack

Use real user clips with known content. No generated media.

| Clip | What it tests | Expected |
|---|---|---|
| One subtitle line for 2 s | Basic text detection and tight box | One group, one member, one range |
| Text visible for 0.2 s | Frame-by-frame beat scan | Detected inside the beat |
| Small corner watermark | Tiled OCR and small text | Group marked, mask tight |
| Two lines in one area | Grouping without stacking | One group, two members, separate boxes |
| Text over motion | Temporal tracking and fill plan | Box follows the line, fill keys increase |
| Logo across whole video | Logo detection and persistent group | One group, member ranges across beats |
| Large burnt-in sticker | User box plus generative fill | Region removed, no readable remnant |
| Text at first and last frame | Beat boundary handling | Both beats flagged |
| Truly text-free clip | Empty result honesty | Zero groups, no render |

For each clip, record:

- what a human sees,
- detected groups, members, boxes, masks and timings,
- missed regions and false boxes,
- frames read, frames skipped and coverage,
- OCR and logo model versions,
- detection compute-seconds,
- whether the pre-render showed leftovers,
- render quality at 100% zoom.

## Reproduce the local evidence

```bash
# default 4 fps
python3 - <<'PY'
from pathlib import Path
import pipeline, detect
src = Path('/Users/happynghia/Downloads/人好猫坏！.mp4')
meta = pipeline.probe(src)
job = {'id': 'probe', 'status': 'ready', 'source': {'path': str(src), **meta}, 'analysis': None}
report = detect.run_check(
    'probe', job, Path('/tmp/duckclean-detect'),
    sampler=pipeline.read_text_samples,
    sample_text=True, fps=4,
)
print(len(report.get('tracklets') or []))
PY
```

Every frame was also extracted with `ffmpeg -vf fps=30` and read with
`vision.probe_images`; all 167 records had zero text lines.

## Reproduce on the cloud worker

Once the CPU worker exists, the same file must be:

1. uploaded to R2,
2. probed and dissected into beats,
3. detected with the Linux OCR and logo stack,
4. compared against this report.

Pass condition: zero groups, zero masks, beats marked complete, coverage 100%,
and no render offered.
