# Colour LUTs

Eight in-house 3D LUTs, generated from `edits.COLOR_PRESETS` by `color.py`:
`warm_film`, `cool_fade`, `vivid_pop`, `soft_matte`, `golden_hour`,
`teal_orange`, `mono_contrast`, `clean_bright`.

Each file is a 17³ `.cube` (Adobe/ffmpeg `lut3d` format) carrying the tonal part
of the look: exposure, contrast, saturation and temperature. Vignette, grain
and sharpen stay as ffmpeg filters, because they are spatial.

Regenerate or verify:

```python
import color
color.ensure_luts()          # writes only missing or stale files
color.lut_asset("warm_film") # {"path": "...", "hash": "<sha256-prefix>"}
```

Do not hand-edit a `.cube`: `color.lut_asset()` refuses a file whose bytes do
not match the generator.
