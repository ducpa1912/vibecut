# G1 preview · REQ-20261126-01

The Edit player draws source frames with the current saved 33³ cube. The WebGL 2 shader reads four texels per pixel and uses tetrahedral interpolation. Changing the look or sliders commits the grade to the edit. On a seek or video frame, the canvas takes the video's framing and preserves separate visual effects. A graded poster covers startup. Without WebGL 2, or after context loss, playback pauses and the viewer displays a labelled core-rendered still that follows seeks.

Cut Focus exposes the eight built-in looks and local LUTs, strength, five adjustments, reset and copy/paste of an edit's grade. Grades belong to the whole edit in the current model. Applying different looks to individual clips needs a per-clip model and render support. Filmstrip tiles use the same grade and request small PNGs. The core validates a selected local file before importing it and caches thumbnails by cube, source size and modification time, source time and width.

## Measured colour

Headless Chrome WebGL 2 using SwiftShader on the 4,913-patch RGB PNG, compared channel by channel against the bundled LGPL FFmpeg lut3d output. Run python3 scripts/bench_grade_preview.py from the Codex worktree.

| Saved grade | Maximum absolute channel difference, out of 255 |
|---|---:|
| Exposure +50 | 0 |
| Temperature −60 and tint +30 | 1 |
| Teal and orange at 70% | 1 |

With WebGL disabled, the scratch Edit screen listed None plus eight looks, saved Teal and orange and displayed the labelled graded still at the chart's frame. The core test also exercises file import, thumbnail width and repeated reads. Both JavaScript modules passed syntax checks, all four Swift shell files type-checked for arm64 macOS 26, and pytest passed 477 tests. The bundle-helper test skipped in the Codex worktree because it has no Xcode app bundle.

## Founder check on a future build

1. Open Cut, select a built-in look, adjust strength and tint, and scrub and play. Compare the viewer, timeline tiles and export on the same frame.
2. Choose a local .cube, then reopen the edit. Confirm the LUT name and saved values survive.
3. Verify on native WKWebView with real footage. The automated comparison uses software WebGL and an RGB chart; hardware video decoding, display colour management, full-screen playback and the native file dialog still need the Mac hand test.
