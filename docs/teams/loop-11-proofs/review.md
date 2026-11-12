# Loop 11 review — proofs are quick, optional and step by step

**Verdict: pass.** Request REQ-20261112-01.

## 1 — A proof is a blur, not a fill

`GET /clean/preview?mode=blur` rewrites every enabled layer to `kind: "blur"` before the render
path runs. Fill layers never reach `textfill.prepare_span`, and no fill cache is written.

| Probe | Result |
|---|---|
| Blur proof, 1920×1080, one line | **0.98 s** cold, **0.02 s** cached |
| Clean (fill) mode on the same dev Mac with no fill model installed | **500**, the model is missing |
| Files written under `projects/<id>/fill` | **0** |
| `textfill.VERSION` | **17** (unchanged) |
| `proof_layers()` unit test | enabled fill/blur become blur; Off stays Off; the source is not mutated |

The proof no longer previews the LaMa output. It is labelled **blur proof** in the status card, the
step tags, the button and the proof caption, so the limit is not hidden.

## 2 — No proof starts by itself

`startPreviewClean` now runs from a click only. Removed at: opening Preview, opening Clean, selecting
a scene, a Fill/Blur/Off change, a brush apply, Clean all, and Re-clean.

| Probe (network log) | 1440×900 | 1280×800 |
|---|---|---|
| `/clean/preview` requests on opening Edit | **0** | **0** |
| on opening Preview | **0** | **0** |
| on opening Clean | **0** | **0** |
| after a Fill/Blur/Off change | **0** | **0** |
| after Prove this scene | **1** | **1** |

Waiting now reads **No proof yet — a proof is a fast blur; press Prove this scene**, not “Cleaning…”.

## 3 — Three steps

`1 · Detect` draws the live boxes on the source frame, `2 · Compare` is the split, `3 · Review` is
the blurred frame. Step 2 and 3 are disabled until a proof exists.

| Probe | 1440×900 | 1280×800 |
|---|---|---|
| Step chips | **3** | **3** |
| Detect boxes at the proof frame | **1** (scene 01, fixture) | **1** |
| Step 2 / 3 reachable after a proof | yes | yes |

The boxes use the same frame as the proof (`proofTime`) and the same geometry the render uses
(`track` when present, else `box`).

## 4 — Re-clean opens Clean Focus on that scene

`Re-clean this scene` sets the scene and its first layer, leaves Preview, and lands on `#/…/clean`
with the box editor open. Probe: `hash` ends `/clean`, Clean screen present, **4** box fields, the
scene's layers listed.

## 5 — Edit the fill box

`PATCH /clean/{layer}/box` takes four normalised numbers, clamps them to the frame, marks the layer
`auto: false`, and **drops the per-frame track** so the render and the proof agree.

| Probe | Result |
|---|---|
| Save x = 0.3, w = 0.2 | reloads as `0.3 / 0.32 / 0.2 / 0.06` |
| `track` after the save | **null** |
| x = 0.5 with w = 0.535 | stored **0.465** (clamped, not rejected) |
| Missing layer | **404** |
| Empty W/H in the UI | rejected before the request |
| Re-check (`clean/from-check`) | keeps the manual box and its geometry |

## 6 — Nothing else moved

Bottoms **87.3–100 %**; layout overlaps **0**; step/control overlaps **0**; clipped buttons **0**;
no horizontal scroll; pictures **99.8 %** (16:9), **95.8 / 95.2 %** (9:16 Preview), **99.8 %**
(Edit). Captures `after-*`, `portrait-*`, `proof-detect/compare/review-*` at both sizes, looked at.

**183 tests**, `node --check` clean, Xcode build passes.

## What got worse

- The step strip sits on the picture (top centre; below the corner tag in portrait), so it covers a
  small part of the frame while reviewing.
- A proof is still one frame per scene, now at the first active line rather than the scene middle.
  A scene whose text appears later is proven at its first line.
- The per-scene Prove button moved from the scenes header to the Preview sidebar: in portrait the
  header wrapped on four lines with it there.

## Not tested

- A fill proof on a Mac with the fill model installed (this dev core has none), and any proof on the
  founder's project (no writes were made there).
- Real clicks in the app window; keyboard focus order and VoiceOver on the step strip.
- 1024×700.
