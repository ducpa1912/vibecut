# Smart reshape: direction and plan

Date: 2026-11-05
Status: direction recorded; not built
Related: `clean-fill-revision-plan.md`, `ui-revamp-plan.md`

## 1. Decision

**Shape belongs to Edit.** A shape changes the crop, the frame, every mask and
every layer, so it is a look decision, not an export setting.

- Edit owns aspect and output size, with `9:16`, `4:5`, `1:1`, `16:9`, `16:10`.
- Finish shows the shape and size from Edit. It does not change them.
- Finish keeps quality tiers for the render: `360p`, `540p draft`, `720p`,
  `1080p final`, `2K` (1440p), `4K` (2160p).
- If an Edit carries an explicit `output.width/height`, that size wins over the
  Finish quality preset. The Finish screen does not show this yet; it is a
  follow-up before the quality tiers ship.
- Edit's resolution menu now offers the same low and high tiers: `360p`,
  `540p`, `720p`, `1080p`, `1440p`, `4K`, plus custom.

Why:

- A shape change moves the crop window, which moves every Clean box and mask.
- A shape change can expose text that Clean removed in the other frame.
- A shape change changes what "full frame" means for text, stickers and effects.
- Export settings belong in Finish; composition belongs in Edit.

## 2. What smart reshape means

Today a shape change crops one picture to fit. Smart reshape changes the layout:

- Split screen: top and bottom, or left and right.
- Focus area: one part of the picture fills the frame.
- Cut to centre: keep the subject centred while the frame changes.

This is a composition pass, not a crop preset. It chooses a layout per scene,
or one layout for the whole cut.

## 3. Preview is mandatory

Smart reshape must ship with preview, not after it.

- The Edit preview renders the reshape layout exactly as the final render will.
- Before/After compares the plain crop with the reshape layout.
- Per-scene preview: step through scenes, see the chosen template on each.
- The preview uses the same compiler as the render. No second layout path.
- If the preview cannot match the render, the feature is not ready.

## 4. Masks and removed text

This is the hard part. Smart reshape must respect everything Clean did.

- Clean layers and masks stay in **source** coordinates, as they do now.
- A reshape maps each source region into the new layout.
- A mask that hid a logo or subtitle must hide the same pixels after reshape.
- If a layout duplicates a source region (mirror, split, repeat), every copy
  needs the mask, not just the first.
- If a layout crops away a cleaned area, that is fine; nothing is re-exposed.
- If a layout shows a source region twice at different scales, the fill and
  brush masks must scale with it.
- AI fill spans are keyed by source time and source rects. Reshape must not
  invalidate them unless the model input changes.
- `crop_guard` layers mean "keep this out of the crop". Reshape has to honour
  that rule in the new layout, not only in the old crop.
- Preview must show the clean result, not the raw source, so a user cannot
  approve a layout that reveals removed text.

Acceptance: a clip with a top subtitle, a bottom logo and a brushed mask, run
through every template, shows no removed text in any preview frame or render
frame.

## 5. Proposed data

```json
"reshape": {
  "mode": "off | template | auto",
  "default": "crop",
  "scenes": {
    "0": {"template": "split_top_bottom", "focus": {"x": 0.5, "y": 0.35, "w": 0.6, "h": 0.5}},
    "7": {"template": "focus", "focus": {"x": 0.4, "y": 0.2, "w": 0.5, "h": 0.7}}
  }
}
```

Rules:

- Absent or `off` keeps today's crop.
- `template` names one layout. The scene map overrides the default.
- `focus` is a source-normalised rect. It is the region the layout must keep.
- Unknown keys are rejected, like the rest of the Edit schema.
- A reshape hash joins the render cache key, so changing one scene re-renders
  that scene only.

## 6. Compiler

The reshape pass runs before the crop, in the same place `reframe.scenes` runs.

```text
source frame
  -> reshape layout (one or more source windows)
  -> scene crop / framing
  -> motion
  -> clean fill and layers (source space, mapped)
  -> output frame
```

Each segment declares:

- its layout template,
- the source rects it reads,
- the output rects it writes,
- the mask transform for each source rect.

`compose_render` owns this. `render.py` only consumes segments.

## 7. Phases

| Phase | Work | Gate |
|---|---|---|
| 0 | Shape and size live in Edit; Finish is read-only | Done in `finish.js` |
| 1 | Reshape preview panel: template, per-scene, Before/After | Preview matches a still frame from the render |
| 2 | Templates: split top/bottom, split left/right, focus, cut to centre | Each template renders one real clip |
| 3 | Mask-aware mapping for Clean, brush, fill and crop guard | No removed text in any template |
| 4 | Layer mapping for text, stickers, effects and captions | Layers follow their source window |
| 5 | Render integration and per-scene cache keys | One scene change re-renders one scene |
| 6 | Auto mode: choose a template from the subject and text layout | Opt-in, preview first |

Do not start with auto mode. Templates plus preview come first.

## 8. Risks

- Text at a split boundary may be cut in half. The preview must show it.
- Duplicated source regions multiply Clean work. Cache each source window once.
- A mask in a duplicated region must be applied to every copy.
- Motion and stabilization run before reshape today. Their order must be fixed
  before templates ship, or the preview will disagree with the render.
- 4K doubles memory per frame on an 8 GB Mac. Fill and reshape at 4K need a
  memory guard and an honest estimate.
- Quality and output size can disagree. One source of truth must win; this plan
  makes Edit's explicit size win, and Finish says when that happens.

## 9. Quality tiers

| Value | Label | 9:16 |
|---|---|---|
| `360` | 360p | 360×640 |
| `draft` | 540p draft | 540×960 |
| `720` | 720p | 720×1280 |
| `final` | 1080p final | 1080×1920 |
| `1440` | 2K | 1440×2560 |
| `2160` | 4K | 2160×3840 |

Encoder levels: 1080p and below use H.264 level 4.2; 2K uses 5.0; 4K uses 5.1.
VideoToolbox bitrates: 1M, 3M, 6M, 10M, 20M, 40M.

The render cache key already carries quality and encoder, so a 4K render never
reuses a 1080p segment.
