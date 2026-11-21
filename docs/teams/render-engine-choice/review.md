# Render engine choice — REQ-20261121-01 (2026-11-21)

Founder: "Can i test on the render phase, where i choose render CoreML or Pytorch. Keep the flag."
Also: the earlier Core ML timings ran while the Mac was busy, so they may understate Core ML.
Built by the sub-leader. Fill output for the default engine is unchanged: `VERSION` stays 17.

**Verdict: pass for code and tests. Not yet tested by hand in the real app (founder step below).**

## What changed

| Piece | Change |
|---|---|
| Choice | Render (and Clean) → AI fill engine → GPU now shows **PyTorch · Core ML · test**. Saved as `fill_gpu_engine` in `settings.json` (no key, no secret). Default PyTorch. |
| Flag | `DUCK_FILL_GPU_ENGINE` still wins. When it is set, both buttons are disabled and the line says the launch flag decides. |
| Routing | Before: the first box size Core ML had no function for raised, and `_GpuOrCpu` moved the **whole rest of the span** to PyTorch, so a "Core ML render" mostly timed PyTorch. Now `_CoreMLRouted` sends each box to Core ML when `fits()` (exact bucket, same rule as before), else to PyTorch for that box only. The route depends on the size alone, so the clip is still a valid cache entry under the `:coreml-gpu` stamp. A real Core ML error stops Core ML for that span and the clip is not cached (as before). |
| Counts | Each filled span returns `gpu_engine`, `coreml_areas`, `gpu_areas`, `fill_seconds`. `render_edit` sums them into `<render>.fill.json`; the finished job's message says e.g. "Core ML test: Core ML filled 9 of 42 boxes, PyTorch the rest · fill 412 s · 1 reused". The Latest render card adds "took N s from queue to file". |
| Estimate | The estimate key includes the engine, so switching re-estimates. A Core ML span does not teach the learned fill rate, so the PyTorch estimate stays clean; the Core ML estimate uses the PyTorch rate. |
| Status | `/api/engine` fill adds `coreml_ready`, `coreml_problem`, `gpu_engine_flag`. |

Files: `duckcore/engine/textfill/__init__.py`, `coreml_fill.py` (`fits`), `duckcore/app_settings.py`,
`duckcore/main.py`, `duckcore/render.py`, `static/duck/app.js`, `tests/test_render_engine_choice.py`.

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | Default is PyTorch; the choice selects Core ML; unknown → PyTorch; no package → PyTorch | pass (tests) |
| 2 | The flag overrides the choice both ways | pass (tests) |
| 3 | Setting stored, validated (400 on a bad name), shown in the snapshot; route applies it at once | pass (tests, TestClient) |
| 4 | The render reads the saved choice before it fills | pass (test on `_fill_device`) |
| 5 | Per-box routing: fits → Core ML, miss → PyTorch for that box only, counts right, clip cached | pass (tests, fake engines through the real `prepare_span`) |
| 6 | A Core ML failure → PyTorch, not cached; the wrapper sees the mix | pass (tests) |
| 7 | Done message names the engine and counts | pass (tests) |
| 8 | UI control: five states (PyTorch, Core ML, flag, no Core ML, CPU) | pass: HTML rendered in Node from the real functions; not seen in a real window (needs a project) |
| 9 | Built app core reports and switches the engine | pass: the rebuilt bundle on a scratch root says PyTorch fresh, Core ML after the PATCH, Core ML after a restart, PyTorch with `DUCK_FILL_GPU_ENGINE=pytorch` over a saved Core ML |
| 10 | Real Core ML render speed vs PyTorch | **not tested**: founder step |
| — | Full suite | 373 passed |

## Limits that stay (shown in the UI line)

- Core ML only has exact functions for 11 sizes; in the review project 9 of 42 layers fit
  (3C review). The rest are PyTorch boxes, and the message counts them.
- The native MPSGraph abort (`shape.count = 0 != strides.count = 4`, one recorded run) cannot be
  caught in Python. If it happens, the app's core stops and the render fails.
- Core ML pixels differ from PyTorch up to 19/255 (exact buckets), so the first Core ML render is a
  full fill and its clips live beside the PyTorch ones.

## Founder speed test (by hand, Mac otherwise quiet)

1. Quit other heavy apps. Open `build/DuckSuite-Xcode.app` normally (no flag).
2. Open the review project, edit, then **Render**. Under AI fill engine pick **GPU**, then **PyTorch**.
   Render. Write down the Latest render line: the "fill N s" and "took N s".
3. Pick **Core ML · test**. Render the same edit again. Write down the same two figures and the
   "Core ML filled X of Y boxes".
4. Render the Core ML one a second time: it should say the clips were reused (no new fill).
5. If the app stops during step 3, note the time; that is the known Core ML abort.

Note: PyTorch clips of an edit already rendered since 2026-11-15 are reused, so step 2 may show
"no new fill". For a fair pair, compare against a PyTorch render that filled (or a new edit).

## Not tested

- A real Core ML fill inside the built app (needs a project and the founder's footage).
- The control in a real window at the narrow and 200 % sizes (loop 28 covers layout).

## Report row

- `docs/reports/ducksuite-product-progress.html`: not added; the insert anchor is not named (same as
  fix-01 to fix-04).

## Commits

- this commit (code, tests, docs).
