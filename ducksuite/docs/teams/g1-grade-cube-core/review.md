# G1 core review

**Core acceptance passed.** Rendering, the graded still and the preview payload use the same cached 33³ cube. The next render of a graded edit is cold for graded output and proofs. Source-space fill data remains reusable. The WebGL viewer, look menu and native file picker belong to the preview loop after P-E.

## Grade and cache

The five sliders are signed integers from −100 to 100. Exposure maps to −2…+2 stops. Temperature adds up to ±0.12 to red and subtracts it from blue. Positive tint reduces green by up to 0.10. Contrast scales about 0.5 by 0.4…1.6. Saturation scales distance from Rec.709 luma by 0…2. Look strength mixes the selected look with its input before the user adjustments. Wheels and fade default to zero for user adjustments. The port preserves their place in the recipe for built-in looks that use them.

The cache digest includes a recipe version, normalized settings and the contents of the selected user LUT. Inactive looks and neutral adjustments bypass baking. Graded retry segments and still proofs use the digest. Sharpen precedes the grade, padding follows it, and blur keeps its existing position. Earlier four-slider edits load without rewriting their files. Imported 3D LUTs accept sizes 2–65 and unit input domains. The app validates the complete local file before publishing its copy.

## Measurements

The RGB PNG chart contained all 4,913 combinations of 17 equally spaced, byte-rounded levels per channel. Each output channel was compared against the direct NumPy recipe rounded to an 8-bit value. The executable was the local LGPL FFmpeg 7.1.1 build.

| Grade | Largest absolute channel error, out of 255 | Mean absolute channel error |
|---|---:|---:|
| Neutral | 0 | 0.000 |
| Exposure +50 | 0 | 0.000 |
| Temperature −60, tint +30 | 1 | 0.314 |
| Teal and orange, 70% | 1 | 0.440 |

At exposure +50, the previous FFmpeg filter moved chart channels by 60.18 levels on average (maximum 127). G1 reproduced those outputs exactly. At temperature +50, the previous filter moved channels by 0.21 levels on average (maximum 13). G1 differs from those outputs by 9.51 levels on average (maximum 16). Input gray (128,128,128) stayed gray under the previous temperature filter and became (143,128,112) under G1.

All eight NumPy looks also matched the pinned Swift implementation on RGB (0.83,0.34,0.13), with a largest absolute channel difference below 4 × 10⁻¹⁶. The MIT notice is in Licenses/Editroom-MIT.txt.

## Preview handoff

- GET `/api/grade/looks` returns ordered `looks` names and `luts` records with `id` and `name`. POST `/api/grade/luts` with `{"path":"/local/file.cube"}` returns the imported record. Save its ID in the edit's grade.
- PATCH the existing edit `/cut` route with the full Cut settings. The grade accepts `tint`, nullable `look` and `look_strength` in addition to the previous four sliders. Strength defaults to 100.
- GET `/api/projects/{project_id}/edits/{edit_id}/grade/cube` returns `{size,data,hash}`. Decode the base64 data as little-endian float32 RGB triples in blue/green/red grid order, red changing fastest. Use tetrahedral interpolation on encoded RGB to match FFmpeg. Neutral returns size 0, empty data and a null hash. These JSON routes use the existing bearer token.
- Without WebGL, display the PNG from the edit's `/grade/still?time=<source seconds>` route using the existing media token or session cookie. The image carries the source picture with the grade applied. Disable the CSS grade on both paths so the viewer cannot apply the look twice.

## Verification

468 tests passed. The bundled-helper test skipped because this checkout lacks DuckSuite-Xcode.app. Node syntax validation passed for static/duck/app.js. Core route tests exercised import, save, cube retrieval and still pixels. Native UI, WebGL and real footage remain for the preview loop and founder testing.
