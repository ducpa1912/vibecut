# Studio Edit — deep-feature test checkup

Date: 2026-11-03  
Branch: `studio`  
Baseline before this checkup: `15bd699`  
Current worktree: deep-feature pass after the three-panel rebuild

## 1. What was checked

This pass covers the deep items that followed the Elements / Preview / Layers rebuild:

- custom output size
- true output frame rate
- border render
- audio fade render
- reversed clips
- frozen clips
- mosaic clean regions
- optical-flow and stabilization settings
- cross-video file clips and photo assets
- the four-column LUT grid
- the media picker and photo upload surface

The founder’s real Studio media was not used as a write target. Render tests use isolated fixtures.

## 2. Final suite

Command:

```bash
python3 -m pytest -q -p no:cacheprovider
```

Result:

```text
2040 passed, 11 skipped, 5 warnings in 116.64s (0:01:56)
```

Exit code: `0`.

The skips are host/tool-gated tests (Playwright or optional media tools), not product failures.

Warnings are dependency deprecations from `paramiko`, `audioread` and Python’s `aifc`; none come from Studio code.

## 3. Targeted deep tests

### Output size, FPS, border and fade

`tests/test_render_layers.py::test_custom_output_size_border_and_audio_fade_render`

Covered:

- `output.width = 540`
- `output.height = 960`
- `output.fps = 60`
- border width `8`, colour `#ff0000`
- audio fade in/out `0.4s`
- final probe reports `60fps`
- first pixel is red after encoding

Result: **passed**.

### Reverse and freeze

`tests/test_render_layers.py::test_reverse_and_freeze_render`

Covered:

- one reversed scene clip
- one 1s freeze clip
- final duration is 2s
- the rendered file exists

Result: **passed**.

### Cross-video file clip

`tests/test_render_layers.py::test_file_clip_renders_from_its_asset`

Covered:

- an asset copied to `job/assets/a1.mp4`
- `edit.assets`
- `sequence` with `kind: "file"`
- per-clip source resolution in the renderer
- per-clip audio resolution
- final render succeeds

Result: **passed**.

### Optical flow and stabilization

`tests/test_render_layers.py::test_optical_flow_and_stabilize_compile_into_the_filter_chain`

Covered:

- `output.optical_flow`
- `output.stabilize`
- `output.strength`
- generated segment filter contains `deshake=` and `minterpolate=`

Result: **passed**.

### Schema validation

`tests/test_edits.py::test_output_resolution_and_audio_fade_are_valid`

Covered:

- custom width/height/fps
- optical flow, stabilization and strength
- audio fade
- rejects odd dimensions
- rejects unsupported fps
- rejects HDR
- rejects an invalid fade

Result: **passed**.

`tests/test_edits.py::test_file_assets_and_file_clips_are_valid`

Covered:

- `edit.assets`
- `kind: "file"` sequence clips
- rejects path traversal
- rejects a missing asset reference

Result: **passed**.

## 4. Browser check

Viewports checked:

| Viewport | Result | Preview canvas | Errors |
|---|---:|---:|---:|
| 1440×900 | pass | 268×476 | 0 |
| 1280×720 | pass | 188×334 | 0 |
| 1024×680 | pass | layout pass | 0 |
| 390×844 | pass | 200×356 | 0 |

Browser checks:

- page does not scroll
- three-panel layout stays in the viewport
- timeline stays below the panels
- Elements / Preview / Layers mobile switcher works
- Clean draw, move, resize and delete still work
- transcript seek still works
- shortcuts dialog opens
- text preset adds a text layer, undo and redo work
- focus mode enters and exits
- resolution menu opens; optical-flow, stabilize and strength controls are present
- no console or page errors

Commands:

```bash
python3 -m pytest -q -p no:cacheprovider tests/test_browser_edit_layout.py
python3 -m pytest -q -p no:cacheprovider tests/test_browser_trim.py
python3 -m pytest -q -p no:cacheprovider tests/test_browser_fill_flow.py
```

Result: **passed**.

## 5. Deterministic detector

The Impeccable detector still reports the two pre-existing pulsing-dot warnings in `static/studio/studio.css`:

- working-step dot
- finish skeleton dot

Both are outside the Edit surface. No new Edit-surface detector findings.

## 6. Feature matrix

| Feature | UI | Save | Render | Test |
|---|---:|---:|---:|---:|
| Elements / Preview / Layers | yes | n/a | n/a | browser |
| Moments, FX, Text, Audio | yes | yes | n/a | source + browser |
| Aspect selector inside Preview | yes | yes | yes | browser |
| Custom resolution | yes | yes | yes | render |
| 24 / 30 / 60 FPS | yes | yes | yes | render |
| Border | yes | yes | yes | render |
| Audio fade | yes | yes | yes | render |
| Reverse | yes | yes | yes | render |
| Freeze | yes | yes | yes | render |
| Mosaic | yes | yes | yes | compile |
| Optical flow | yes | yes | yes | compile |
| Stabilize | yes | yes | yes | compile |
| Cross-video file clip | yes | yes | yes | render |
| Photo asset | yes | yes | yes | source + render path |
| LUT grid | yes | yes | existing renderer | source |
| Painter mask | no | no | no | not implemented |

## 7. Known gaps and risks

1. **Painter mask is still not implemented.** Clean is still box-based. The media and render paths are ready for a mask asset, but the mask renderer is not.
2. **Cross-video audio with voice-over or dub.** Original source audio is handled per clip. The voice/music bed builder is still written around the primary source; a mixed multi-clip voice/dub bed needs a dedicated pass.
3. **Photo assets are converted to 2.5s MP4 clips at add time.** This is deliberate: it keeps the renderer to one media type. It costs one transcode per photo.
4. **Asset extraction is re-encoded.** Cross-video scenes are copied into `job/assets` as H.264/AAC clips. This is slower than stream copy but avoids keyframe and codec edge cases.
5. **Optical flow/stabilization are compiled into the filter chain but not visually QA’d on a long real clip yet.** Short render tests cover filter compilation.
6. **HDR remains disabled by design.** The schema rejects `hdr: true`.
7. **The photo upload route has source-level coverage and a render path test, but no browser upload test yet.** Add one when a HEIC/JPEG fixture is in the browser suite.
8. **The founder’s real media was not modified by this checkup.** Browser checks only opened Edit and menus; render tests used fixtures.

## 8. Reproduce

```bash
# full suite
python3 -m pytest -q -p no:cacheprovider

# deep render checks only
python3 -m pytest -q -p no:cacheprovider \
  tests/test_render_layers.py::test_custom_output_size_border_and_audio_fade_render \
  tests/test_render_layers.py::test_reverse_and_freeze_render \
  tests/test_render_layers.py::test_file_clip_renders_from_its_asset \
  tests/test_render_layers.py::test_optical_flow_and_stabilize_compile_into_the_filter_chain

# browser checks
python3 -m pytest -q -p no:cacheprovider \
  tests/test_browser_edit_layout.py \
  tests/test_browser_trim.py \
  tests/test_browser_fill_flow.py
```

## 9. Verdict

The deep render paths are green on the automated suite and on isolated real ffmpeg renders.

The remaining blocker is the painter mask. Everything else requested for the deep pass is implemented and tested.
