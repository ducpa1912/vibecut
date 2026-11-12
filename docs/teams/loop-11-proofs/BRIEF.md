# Loop 11 brief — proofs are quick, optional and step by step

Request: **REQ-20261112-01**. Founder, 2026-11-12, by hand on the Review project.

> "Proofs become so slow, i said proofs just need to be a quick blur no need to run LaMa AI Fill
> Clean for proof, it took too long. Make it optional not auto, so user can decide to run a proof
> check, and proof check should be step by step, detect (blur area)/ compare the slip screen, also
> re-clean this scene will take back to clean focus in that specific scene, and user can either
> edit the fill box area, use paint brush or just ask the tool to re-check & re-apply clean again."

## What must exist after this loop

1. **A proof is a blurred frame, not a LaMa fill.** `GET /clean/preview` takes `mode=blur`; every
   active clean layer is drawn as a blur, no fill model runs, no fill cache is written. The default
   `mode` is unchanged (`clean`) so a proof of the fill is still possible on request.
2. **No proof starts by itself.** Opening Preview or Clean, selecting a scene, changing Fill/Blur/Off
   and applying a brush must not request a proof. Only an explicit button does.
3. **Three steps, visible:** `1 Detect` (source frame with the layer boxes), `2 Compare` (split
   before/after of the blur), `3 Review` (after frame). The step is named in the UI.
4. **Re-clean this scene opens Clean Focus on that scene**, with its layer selected, offering the
   three routes: edit the box, paint a mask, or re-check and re-apply.
5. **Box editing exists** for a clean layer: four normalised fields, saved, reflected in the next
   proof and the next render.
6. Render output is untouched, `textfill.VERSION` stays 17, the ink store is not read by a proof.

## Acceptance a human can see

- Press "Prove this scene": the picture comes back in under ~2 s and the text is blurred, not filled.
- No spinner on its own when Preview opens.
- The step chips read Detect, Compare, Review and move.
- "Re-clean this scene" lands on Clean with the same scene and line highlighted.
- An edited box moves the blur on the proof.

## Probes

| Probe | Pass |
|---|---|
| `textfill.fill_frame` / `prepare_span` called during a blur proof | 0 calls (spy) |
| Proof request on route open, scene change, clean action, brush apply | 0 |
| One blur proof, wall time, 1080p source | measure and report |
| Layer box saved through the API, reloaded, used by the proof | box equals what was sent |
| Render of an untouched edit | same pixels as before the loop |

## Out of scope

- Fill quality, fill speed, `textfill.VERSION`, the ink store.
- Story, Cut, safe zones, timeline zoom, preview sequence (loops 13–17).
