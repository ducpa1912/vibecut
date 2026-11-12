# Loop 18 review — Cut grading

**Verdict: pass.** Request REQ-20261112-04, phase 2.

## Controls

Cut → Look: **Exposure, Contrast, Saturation, Temperature**, −100…+100, default 0, **Reset grade**.
The player filter updates on input; the value is saved on change.

## Render path

Filters are appended after crop/scale and before `setsar,fps`:

| Slider | ffmpeg |
|---|---|
| Exposure | `exposure=exposure=` −2…+2 EV |
| Contrast | `eq=contrast=` 0…2 |
| Saturation | `eq=saturation=` 0…3 |
| Temperature | `colorbalance=rs=±0.15:bs=∓0.15` |

Neutral values add no filter; `test_no_cut_keeps_the_old_source_chain` still passes.

## Measured on a proof frame through the render path (1920×1080)

| Grade | Mean luminance | Mean chroma | Mean R−B |
|---|---|---|---|
| Neutral | 126.2 | 192.3 | −5.7 |
| Exposure +100 | **131.6** | 191.8 | −5.2 |
| Saturation −100 | 124.7 | **2.6** | 0.9 |
| Temperature +100 | 127.2 | 196.0 | **−2.2** (warmer) |

## UI probe

4 sliders present; moving Exposure to +80 changes the player filter to `brightness(1.4)` live; the
saved edit reports `exposure: 80`; Reset returns every slider to 0 and the filter to neutral.
Capture `grade-sliders-1440x900.jpg`.

**197 tests**, `node --check`, Xcode build.

## What got worse

- The player preview is CSS (`brightness/contrast/saturate/sepia/hue-rotate`), the render is ffmpeg.
  They agree in direction, not in pixels; the UI says so.
- Temperature is a simple red/blue balance, not a colour-managed white balance.
- The grade row adds four lines to the Look card.
- Grading applies to the whole edit; per-scene grades are not built.

## Not tested

- A full render with grade (only proof frames through the render path).
- Contrast by pixel measurement (filter-string test only).
- HDR/10-bit sources, 1280×800 capture, real clicks.
