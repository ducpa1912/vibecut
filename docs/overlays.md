# Flow 2 overlay plans

Flow 2 adds **clean input plus new hook, title, caption, lower-third and CTA
overlays** to a finished cut. It is a local retention feature, not a paid
wedge. This document covers the gated planning API only. No overlay is burned
into a render by this prototype.

## Scope and non-goals

In scope:

- Deterministic overlay plans for `9:16` and `4:5` output.
- Text, timing, z-order, anchor, box, style, opacity and safe-zone metadata.
- Advisory safe-zone and analysis-face warnings.
- Local-only JSON output that can be written to `overlays.json`.

Out of scope, deliberately:

- No Hook Cards and no template library, template SKU or paid overlay pack.
- No cloud, accounts, seats, publishing, analytics or remote storage.
- No changes to paid-v1 caption or render behavior.
- No static creator UI. The API is gated and headless.
- No ffmpeg invocation, media write or burn. A later render slice can consume
  the plan, but this module does not.

## Feature flag

The entire surface is off by default. Every route returns `404` unless the
environment variable is explicitly truthy:

```bash
VIBECUT_ENABLE_OVERLAYS=1
```

Accepted on values: `1`, `true`, `yes`, `on` (case-insensitive). Anything
else, including unset, keeps the routes hidden. When off, even a malformed
request returns `404`; no overlay capability is advertised.

## API contract

```
POST /api/jobs/{job_id}/overlays/plan
Content-Type: application/json
```

Request:

```json
{
  "story_id": "s1",
  "artifact_id": null,
  "aspect": "9:16",
  "layers": [
    {
      "kind": "hook",
      "text": "Stop scrolling",
      "start": 0.0,
      "end": 3.0,
      "anchor": "top-center",
      "box": {"w": 0.76, "h": 0.16},
      "z": 1,
      "style": {"color": "#ffffff", "weight": 800},
      "safe_zone": true,
      "opacity": 1.0
    }
  ]
}
```

`story_id` and `artifact_id` are optional. Omit both to plan against the job's
source duration and all analysis scenes.

- `story_id` must match a story in the job's stored clip sets. The plan uses
  the story's duration and records `clip_set_id` and `story_title`.
- `artifact_id` must be an existing artifact manifest in this job. The plan
  uses the artifact's duration and story id.
- Supplying both is allowed only when the artifact belongs to that story.
- `aspect` is required and must be `9:16` or `4:5`; an artifact must match the
  requested aspect.

Response:

```json
{
  "plan": {
    "schema_version": 1,
    "job_id": "job1",
    "story_id": "s1",
    "artifact_id": null,
    "clip_set_id": "cs_1",
    "story_title": "Story one",
    "aspect": "9:16",
    "duration": 30.0,
    "canvas": {"w": 1080, "h": 1920},
    "safe_zones": {
      "safe_area": {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.87},
      "reserved": [
        {"name": "top-ui", "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.05},
        {"name": "bottom-ui", "x": 0.0, "y": 0.92, "w": 1.0, "h": 0.08},
        {"name": "right-ui", "x": 0.88, "y": 0.3, "w": 0.12, "h": 0.62}
      ]
    },
    "limits": {"max_layers": 12, "max_text_length": 160, "max_lines": 4},
    "count": 1,
    "layers": [
      {
        "id": "ov01",
        "kind": "hook",
        "text": "Stop scrolling",
        "start": 0.0,
        "end": 3.0,
        "duration": 3.0,
        "anchor": "top-center",
        "box": {"w": 0.76, "h": 0.16},
        "rect": {"x": 0.12, "y": 0.05, "w": 0.76, "h": 0.16},
        "z": 1,
        "style": {
          "font": "sans",
          "size": 44,
          "weight": 800,
          "color": "#ffffff",
          "background": "none",
          "stroke": "#000000",
          "align": "center",
          "uppercase": false,
          "shadow": true
        },
        "safe_zone": true,
        "opacity": 1.0
      }
    ],
    "hash": "ov_0123456789abcdef0123456789abcdef"
  },
  "warnings": [],
  "hash": "ov_0123456789abcdef0123456789abcdef"
}
```

`plan` is ready to serialize as `overlays.json`. The top-level `hash` equals
`plan.hash`. The hash is SHA-256 over canonical JSON of the plan **without**
the `hash` field, prefixed with `ov_` and truncated to 32 hex characters.
Layer order, generated ids and auto z values are deterministic.

### Layer fields

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | `hook`, `title`, `caption`, `lower_third`, `cta` |
| `text` | yes | NFC text, trimmed; whitespace inside each line collapses; 1-4 lines |
| `start`, `end` | yes | Seconds in output time; `end > start`; minimum 0.2s |
| `anchor` | no | `top-left` … `bottom-right`; `center` is the centered shorthand |
| `box` | no | Normalized `{w,h}` or `{width,height}`; defaults per kind |
| `z` | no | Integer 0-99; omitted layers receive the next free value |
| `style` | no | Whitelisted typography object; defaults are merged |
| `safe_zone` | no | Boolean intent flag stored in the plan; warnings are always advisory |
| `opacity` | no | 0-1, default 1 |

Default anchors and boxes:

| Kind | Anchor | Box `w × h` |
|---|---|---|
| `hook` | `top-center` | 0.76 × 0.16 |
| `title` | `center` | 0.76 × 0.14 |
| `caption` | `bottom-center` | 0.76 × 0.12 |
| `lower_third` | `bottom-left` | 0.64 × 0.14 |
| `cta` | `center` | 0.64 × 0.10 |

Anchored boxes use edge margins: left 0.05, right 0.12, top 0.05, bottom 0.08.
Center anchors center the box. The result is included as `rect` in normalized
output coordinates. A frame coordinate is `0..1`, with `y=0` at the top.

Style keys: `font` (`sans`, `serif`, `mono`), `size` (12-160), `weight`
(100-900), `color` (`#rgb`, `#rrggbb`, `#rrggbbaa`), `background` (same or
`none`), `stroke` (same or `none`), `align` (`left`, `center`, `right`),
`uppercase` and `shadow` (booleans). Unknown keys are rejected. Colors are
lowercased and short hex is expanded.

### Validation

- At least 1 and at most 12 layers.
- Empty or whitespace-only text is rejected; text is capped at 160 characters
  and 4 normalized lines.
- `start >= 0`, `end > start`, `end - start >= 0.2`, and `end` must fit the
  story/artifact duration, or the source duration when no context is supplied.
- `z` must be an integer in `0..99`. Explicit duplicate z values are rejected.
  Omitted z values are assigned from the lowest free slot.
- Duplicate layer ids are rejected. Missing ids become `ov01`, `ov02`, …
- Two layers with the same kind and case-insensitive normalized text may not
  overlap in time. The same text may repeat in a non-overlapping window.
- Box width is `0.05..1.0`, height is `0.03..1.0`.

HTTP behavior:

| Status | Case |
|---|---|
| `200` | Valid plan |
| `400` | Unsupported aspect |
| `404` | Flag off, job missing, story missing, or artifact missing |
| `409` | Artifact aspect or story conflicts with the request |
| `422` | Layer validation or malformed request body |

The route is read-only. It never writes `job.json`, `overlays.json`, renders,
or any other file. It never calls a network service.

## Safe-zone rules

All rectangles are normalized to the output frame.

| Aspect | Canvas | Top UI | Bottom UI | Right action rail |
|---|---|---|---|---|
| `9:16` | 1080×1920 | y `0.00-0.05` | y `0.92-1.00` | x `0.88-1.00`, y `0.30-0.92` |
| `4:5` | 1080×1350 | y `0.00-0.05` | y `0.93-1.00` | x `0.88-1.00`, y `0.30-0.93` |

Safe areas:

- `9:16`: `{x: 0.05, y: 0.05, w: 0.90, h: 0.87}`.
- `4:5`: `{x: 0.05, y: 0.05, w: 0.90, h: 0.88}`.

A layer gets a `safe_zone` warning when more than 0.5% of its box area
intersects a reserved zone, or when it falls outside the safe area without
touching a named zone. Warnings do not alter the plan and do not reject the
request. They are advisory platform heuristics, not guarantees: platform UI
changes and per-account chrome still matter.

## Face overlap warnings

If the job analysis has scene face boxes, the planner maps them through the
scene crop for the requested aspect and compares them with each layer's rect
when their time windows overlap. Face boxes may come from either
`scene.faces[]` or `scene.attention.face`; low-confidence and tiny boxes are
ignored.

A warning is emitted when at least 5% of the overlay box overlaps a mapped
face:

```json
{
  "code": "face_overlap",
  "severity": "warning",
  "layer_id": "ov01",
  "scene_id": 7,
  "face_count": 1,
  "overlap": 0.42,
  "message": "Title overlay overlaps a detected face in scene 7."
}
```

This is intentionally coarse. Layer times are compared with source scene
times; the story edit order is not reconstructed. Treat the warning as a
prompt to preview, not a hard collision result.

## Hash and storage

The deterministic hash covers the normalized plan metadata, layers, rects,
style, safe zones and context. Warnings are excluded so new analysis does not
change overlay identity. The same request produces the same hash across
processes and runs.

The endpoint returns the plan; it does not persist it. A caller that wants an
`overlays.json` can write `response["plan"]` atomically in its own slice.
