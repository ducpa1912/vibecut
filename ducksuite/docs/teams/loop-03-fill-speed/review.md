# Loop 3 — measure fill speed, then decide

Date: 2026-11-11 · `PLAN.md` loop 3 · REQ-20261111-04. Numbers: `docs/duck/gpu-fill-bench.md`.

## Brief

Measure CPU, CoreML and MPS on the same frames and on a real span; test 6 vs 3 fills a second; find
why the loop 1 estimate read 6× high. Decide from numbers. No fill output change.

## What changed

- `scripts/bench_fill.py`: `--device cpu|coreml|gpu`, `--model`; reports load, first fill, steady
  fill and peak RSS.
- `textfill.record_rate`: the stored rate is the middle of the last three fills, not a running
  average. 2 tests.
- Docs: `gpu-fill-bench.md` (new), corrections in `GPU-FILL-PLAN.md` and `AGENTS.md`.

## Acceptance

| Check | Result |
|---|---|
| One table, CPU / CoreML / MPS, same 10 frames | pass |
| Measured on this Mac | pass, under load (stated) |
| Peak memory under 8 GB | pass for RSS (≤ 877 MB); GPU-held memory not measured |
| 6/s vs 3/s decided | pass: flat 3/s doubles the runs; closed |
| Estimate calibrated | pass: cause found, rate rule changed, tested |
| Decision recorded | CoreML closed; MPS qualifies; packaging left to the founder |
| Suite | 92 passed; `node --check` passes |

## Not tested

- MPS on a real span was run once. No variance, no long-run heat or memory figure.
- Nothing was measured on a quiet Mac.
- PyInstaller with torch was not built; the +0.8 GB is the installed size, not the bundled one.
- The app's own stored rate still holds a 20.4 s blend until two more fills finish there.
- My first real-span batch ran the CPU job three times by mistake (a shell quoting error). It is
  reported as the variance measurement it turned out to be.
- Roles: one agent; `creator` and `product-owner` not spawned.

## Verdict

Pass. The decision on bundling torch is open and is the founder's.
