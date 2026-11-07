# DuckSuite — Clean quality enhancement plan

Date: 2026-11-07  
Scope: LaMa Fill quality, text detection density, temporal consistency, proof gates.  
Team: product owner + engineer + tester only. No designer, no new UI modes.

## Current state

- Text pass: `CHECK_SAMPLE_FPS = 4.0` (four frames per second), max 3600 frames, frame width 1280.
- The code comment in `extract_text_frames` still says “2 fps”; the constant is 4.0. Fix the comment.
- Scene cuts: 8/5/4 fps scan depending on duration.
- Crop tracking: two stills per deep scene.
- Clean preview: one frame per scene midpoint.
- Render: per-frame fill.

## Observed on the fixed test video

Fixture: `check-smoke`, 46 s, 1080×1080, 24 fps.

| Scene | Observable |
|---|---|
| 01 | Large “if you’re the smartest person in the room” title leaves a dark artifact after Fill |
| 04 | “unchallenged” remains in the proof |
| 08 | “was” remains in the proof |
| 07 | “obviously” is removed cleanly; this is the verified control |

The artifact is not a UI bug. It is a mask/fill/tracking quality bug. The UI correctly exposes the result and does not silently fall back.

## Root-cause hypotheses

1. **Mask too tight.** Line boxes cut glyph edges and antialiasing; LaMa sees black glyph pixels as context and fills dark.
2. **Large display text is treated like a subtitle.** Huge stylized type needs a different detector, dilation, and crop scale.
3. **Tracklet start/end is sampled, not frame-accurate.** 4 fps can miss the first/last frame where text appears or changes.
4. **Static box across a moving/scaling title.** One box cannot cover every frame of an animated title.
5. **No per-frame mask propagation.** Fill plans are line-level, not frame-level.
6. **No quality gate.** A proof is marked generated even when text or a dark artifact remains.
7. **Preview proves a midpoint, not the hard frame.** The worst frame may be the first or last frame of the text range.

## Sampling decision: do not lower the whole scan to 1 fps

One frame per second globally is a **quality regression**, not an enhancement. Burned-in captions can last under half a second; the detector already notes that 2 fps missed some. 1 fps would miss more onsets, produce holes, and create more artifacts.

Use **adaptive sampling**:

```text
Pass 1 — discovery:   1–2 fps + scene boundary frames
Pass 2 — refinement:  8–12 fps only inside detected text ranges
Pass 3 — edges:       first/last frame of each text range, frame-accurate
```

- Short source or short text range: refine every frame.
- Long source: coarse discovery across the whole file, fine pass only around text.
- Test 1 / 2 / 4 / 8 / 12 fps on the same fixture and record quality vs time.
- Pick the lowest density that reaches zero residual text and zero dark artifact.

This gives “scan further” where it matters without scanning a two-hour file at 30 fps.

## Quality metrics

Every loop produces the same numbers for the same fixture.

| Metric | Target |
|---|---|
| Residual text | OCR on cleaned frame finds no text inside the mask; score 0 |
| Dark artifact | Mask-region luminance not below 35% of surrounding ring; black-pixel ratio ≤ 2% |
| Color shift | No visible ΔE / SSIM drop outside the mask |
| Temporal flicker | Masked-region frame-to-frame difference ≤ the surrounding ring |
| Mask coverage | ≥ 98% of text pixels, including 2–4 px dilation and antialiased edges |
| Clean proof | Product approves every scene before it is called verified |
| Time | Check time ≤ 2× current, or refinement runs in the background |

## Enhancement loops

### Loop 1 — Baseline and harness

**Engineer**
- Freeze `check-smoke` as the torture test.
- Instrument mask coverage, residual OCR, black-artifact score, color delta, temporal diff.
- Export per-scene before / fill / clean frames.
- Fix the 2 fps vs 4 fps comment.

**Tester**
- Build a repeatable test script for the same fixture.
- Record baseline for all 12 scenes.
- Add failure cases: first frame, last frame, scene cut, large title, small subtitle.

**Product**
- Define pass/fail in plain language: no dark black artifact, no visible text, no unnatural image.
- Approve the metric thresholds.

**Exit**
- Baseline report with images and scores.
- Product accepts the test harness.

### Loop 2 — Mask and tracklet

**Engineer**
- Expand line masks: ascenders, descenders, stroke dilation, antialiased edge.
- Separate large display text from subtitles/lower thirds.
- Per-frame mask propagation inside a tracklet; no static box.
- Union mask across the text range; correct the first and last frame.
- Re-clean scene 01.

**Tester**
- Compare residual OCR and black-artifact score on scenes 01, 04, 08, 07.
- Check mask coverage at the worst frame.
- Verify no new halo around the fill.

**Product**
- Review scene 01 before/after at full size.
- Reject any dark blob, visible glyph, or unnatural fill.

**Exit**
- Scene 01 artifact gone.
- No P1 on the fixture.
- Product approves the proof.

### Loop 3 — Adaptive scan

**Engineer**
- Add coarse discovery and fine refinement passes.
- Add scene-boundary and text-edge frames.
- Make range start/end frame-accurate.
- Bench 1 / 2 / 4 / 8 / 12 fps on the same fixture.

**Tester**
- Measure residual text, artifact score, and check time per cadence.
- Verify short caption and large title recall.
- Confirm no missed text at scene cuts.

**Product**
- Pick the quality/time point.
- Confirm “scan further” means better text edges, not lower global fps.

**Exit**
- Chosen cadence documented.
- No missed text on the fixture.
- Product accepts the time budget.

### Loop 4 — Fill, blend, temporal consistency

**Engineer**
- LaMa crop at higher resolution for large text.
- Color/lighting match around the mask.
- Feather the fill; no hard rectangle.
- Temporal smoothing across adjacent frames.
- Add a reject path: if the fill is dark or text remains, mark `Needs review` and offer Retry / Blur / Off.
- Never silently write a bad fill.

**Tester**
- Run the artifact/color/temporal metrics on every scene.
- Render a short segment containing scene 01 and scene 07.
- Compare preview frame and rendered frame.
- Verify failed fill stays failed, not blur.

**Product**
- Scene-by-scene approval.
- Confirm no unnatural image and no dark artifact on the same test video.

**Exit**
- Zero P1 on the fixture.
- Render proof matches preview proof.
- Product signs the clean proof.

### Loop 5 — Release proof

**Engineer**
- Run the final pipeline on 20 clips: large titles, subtitles, lower thirds, logos, motion, scene cuts.
- Produce 1080p render proofs.
- Record M1 8 GB performance.

**Tester**
- UAT: import → Check → Clean → Preview → Render.
- Regression: Fill / Blur / Off, no silent fallback, proof gate.
- Verify App Store screenshots use verified clean scenes only.

**Product**
- Final sign-off.
- Reject any “Clean” marketing claim that the fixture cannot prove.

**Exit**
- Zero P1.
- All scenes approved or explicitly marked Blur/Off.
- App Store proof and review notes ready.

## Review record per loop

Path: `docs/teams/clean-quality/loop-XX.md`

Each record contains:

- verdict: APPROVED / NEEDS REVISION / BLOCKED;
- before / fill / clean image;
- metric table for the same fixture;
- good to go;
- needs revision;
- bug list with severity;
- failed items;
- product decision.

## Session plan

One session, three roles, sequential loops:

- `Team — Clean Quality / Product`
- `Team — Clean Quality / Engineer`
- `Team — Clean Quality / Tester`

Loop order: 1 → 2 → 3 → 4 → 5. No loop starts until the previous product gate passes. The same fixture is used in every loop.

## Stop conditions

- Any dark black artifact on the fixture: P1, loop does not pass.
- Any residual text on a verified scene: P1.
- Any unnatural color/halo: P1.
- Any silent blur fallback: P0.
- Product rejects a scene: loop continues.
- Tester cannot reproduce a pass: loop continues.
