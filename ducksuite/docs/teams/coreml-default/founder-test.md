# Core ML default — founder check

Run only after the measurement review and rebuilt bundle are accepted.

Blocked as of 2026-11-17: native MPSGraph abort and measured numeric drift.
PyTorch remains default. Do not run this as an accepted Core ML default test yet.

1. Open the rebuilt DuckSuite app. In Render, confirm GPU is selected and its
   note says “Apple GPU through Core ML”. If it names only Apple GPU, the
   package is missing or the runtime is unavailable; report that before rendering.
2. Expect the first render after VERSION 18 to be cold. Use a short edit with
   one subtitle line, not the full review video, for the initial check.
3. Render and play that job's own output. Inspect the whole subtitle interval
   and its first/last frames for leftover letters, flicker, smearing and crossings.
4. Repeat the same short render. Confirm the output and leftover report remain
   consistent and note elapsed times for both runs. Do not infer cold speed from
   the second run.
5. Keep the moving-background limitation visible: a faster engine cannot invent
   scenery the source never showed. Record both visible defects and the timings.
6. Send the job's report and engine/log details to the verifier. Never upload
   footage or put founder frames into Git.
