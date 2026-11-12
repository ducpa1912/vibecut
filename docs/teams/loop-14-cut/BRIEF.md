# Loop 14 brief — Cut Focus, phase 1

Request: **REQ-20261112-04**.

> "Plan for a Cut Edit option and a Cut Focus block, move color grading, preset filter into this
> block with also crop, enhance quality so 360p can be select to expand to 1080p here."
> Later: "Cut just a naming, it mean anything video from resolution, filter, color grading,
> cropping, resize."

## What must exist in phase 1

1. A **Cut** tab in the Edit inspector and a **Cut Focus** dock, same pattern as Script/Audio/SFX.
2. **Output**: aspect `Source / 9:16 / 1:1 / 4:5 / 16:9`, Fit/Fill framing, crop as four normalized
   numbers, Reset crop. The output size is named.
3. **Look**: Warm, Cool, B&W, Vivid move out of SFX into Cut; the old SFX entry points are gone.
4. The Edit player shows the chosen framing; the render and the proof frames use the same Cut.
5. Source-aspect projects render exactly as before.

## Not in phase 1

Grading sliders (loop 18), upscaling and the optional AI pack (loop 19).

## Acceptance

| Probe | Pass |
|---|---|
| Cut tab and Cut Focus | present; 5 tabs; the four presets live in Cut |
| Choose 9:16 | player ratio 0.5625; label “Output 1080 × 1920”; render-size frame 1080×1920 |
| Apply a crop | player shows the cropped ratio; render path uses the same crop |
| No cut | source chain unchanged |
| Changing Cut | a new proof is generated, never a reused one |
