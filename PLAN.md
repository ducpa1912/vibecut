# PLAN — DuckSuite build order

Written 2026-11-11 (REQ-20261111-05). This is the one active plan. Planning is closed: the next
commits are code. `PRODUCT.md` says what the product is, `TODO.md` holds the checkboxes for the
loops below, `AGENTS.md` is the working contract.

## Where the build stands (measured 2026-11-11)

| Fact | Value | Source |
|---|---|---|
| Branch / tests | `ducksuite`, 117 pass | `python3 -m pytest -q tests` |
| Bundle | 981 MB (torch 565, GPU model 196, sidecar 136, ffmpeg 41; no ONNX) | `du -sh build/DuckSuite-Xcode.app` |
| Dev Mac | M1, 8 GB RAM, macOS 26.7.2, 13 GB free disk | `sysctl`, `sw_vers`, `df` |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips | `edits/ed_38a4c36a3aae.json` |
| Clean layers | 42: 40 fill, 2 blur; **34 moving, 8 steady**; all `auto: true` (after loop 2) | same file |
| Fill seconds | 64 s of 160 s; 50 s of that on moving footage | same file |
| Fill engine | PyTorch MPS on the GPU (default); CPU via the optional `fill-lama-cpu` pack | `textfill/lama.py:_providers` |
| Cold render | fill ≈ 28 min on CPU at the measured ~6 s a unit, up to ~2 h when the Mac is busy; ≈ 4.5 min on MPS (one run) | `docs/duck/gpu-fill-bench.md` |
| Fill cache | every stored fill is stale since `textfill.VERSION` 12 | `textfill/__init__.py` |
| Renders on disk | baseline + three loop 4 renders; final 19:15 has 0 leaks | `renders/` |

## What is actually wrong

1. **Fill is slow and weak on moving footage, and that is most of the footage.** 33 of 41 layers are
   `moving`. LaMa fills one frame at a time on the CPU. This is the product's main feature.
2. **The cost is measured but never shown.** *(Fixed in loop 1.)* `textfill.estimate_summary` and `estimate_span` had no
   caller; `fill_rates.json` is written and never read by the UI. A user can start a 4-hour render
   with no warning. This breaks ground rule 4.
3. **The resume cache can switch itself off on this Mac.** Saved fills stop being written below
   10 GiB free (`SAVED_MIN_FREE`); the disk has 13 GB. A stopped long render would lose its work.
4. **The 0 s title is the smallest open defect** (66 ms, 2 frames) and the old P0 paid a full cold
   render to prove it. A 3 s render proves the same thing.
5. **Code that contradicts the rules.** `script.rewrite` silently falls back to an Ollama endpoint
   and names `qwen3:4b`; `online_enabled` / `online_endpoint` settings are stored and unused; the
   cloud STT paths are reachable only through environment variables but have no test saying so.

## Rule for ordering

Every change to fill output bumps `textfill.VERSION` and makes the next full render cold. So: show
the cost first, prove detection on a short span, finish every fill-changing decision, **then** pay
for one full render. Do not run a full render between loops 1 and 4.

## Build loops

One loop = PO brief → engineer + tester → creator → PO sign-off → one commit with `MEMORY.md`,
`TODO.md`, a report row and `docs/teams/<loop>/review.md`.

### Loop 1 — show the render cost (code, no render) — **done 2026-11-11**

- Wire `estimate_summary` to the Render screen and the Clean all dialog: fill seconds, layer count,
  estimated time on this Mac, from the measured rate when one exists, the seed otherwise (labelled).
- Warn before Start render when free disk is under the saved-fill floor.
- Accept: the Render screen for the review project shows an estimate in hours/minutes before Start;
  a test covers the endpoint with a measured rate and with none; no fill output change, no bump.

### Loop 2 — prove the title fix on a short span — **done 2026-11-11**

- Re-run Check on the review project, then Clean all.
- Render 0–3 s only (short edit or trimmed range), not the whole video.
- Accept: a `title` tracklet at 0.0–0.25 s, y ≈ 0.321; its layer is `blur` (flash under 0.5 s); no
  layer with `auto: false` changed (there are none today, so the other layers may be re-planned);
  counts reported as fill · blur · off; frame 0 of the 3 s render has no title.

### Loop 3 — measure fill speed, then decide — **done 2026-11-11; GPU bundled, CPU default**

Result: `docs/duck/gpu-fill-bench.md`. MPS 50 s vs CPU 232–864 s on clip 1; CoreML closed; flat
3 fills/s closed; estimate fixed. Founder chose to bundle the GPU path and keep both chips; CPU
stays the default. Shipped in REQ-20261111-06: torch + `big-lama.pt`, CPU/GPU in Render settings,
bundle 1.2 GB, real GPU render proof, 98 tests.

- `bench_fill.py --device cpu|gpu --model`; CPU vs CoreML EP vs MPS on the same 10 frames.
- Same bench: `fill_plan.keys` 6/s vs 3/s on a moving span.
- Calibrate the estimate: loop 2 rendered clip 1 in 189 s against an estimate of 19 min. Find why
  `fill_rates.json` was not updated and make the figure honest before loop 4.
- Output `docs/duck/gpu-fill-bench.md`. Decide: CoreML, bundle torch, or stay CPU; 6/s or 3/s.
- Accept: one table, measured on this Mac, peak memory under 8 GB; the decision recorded. If
  anything ships: `device` in `span_key`, `VERSION` bump, Settings shows the real device.

### Loop 4 — one full render of the review project — **done 2026-11-11**

- Only after loops 1–3. The estimate from loop 1 is on screen before Start.
- Result: `docs/teams/loop-06-full-render/review.md`. Final render 19:15, 0 leaks in 4,800 frames;
  fill 72.46 -> 70.13 s, blur 0.57 -> 0.60 s; title 0.317 -> 0.067 s; 76 s vs 333.8 s estimate.
  A later refactor pass left output unchanged (117 tests).

### Loop 5 — a better fill for moving footage

- Researcher first: licences for the video-inpaint candidates (STTN weights, ProPainter, others),
  quoted clause, commercial use yes/no. No model enters the build without that table.
- Then bench the allowed candidates with `bench_fill.py` on the moving spans of the review project.
- Alternative that needs no licence: the custom ONNX fill slot (BYOM) so the user plugs one in.
- Accept: a candidate beats LaMa on moving spans by a stated dB at a stated time cost, or the doc
  records that none does and the UI keeps the `moves` warning.

### Loop 6 — make the code match the rules

- Rewrite: remove the silent Ollama fallback and the model name; Apple Intelligence, else basic
  cleanup, said in the UI. The local LLM endpoint returns later as an explicit slot (loop 7).
- Delete the unused `online_enabled` / `online_endpoint` settings.
- Cloud STT: the code stays for after v1; add a test that no provider is reachable in a v1 build.
- Accept: tests for each; `grep` finds no model name in a user-facing string.

### Loop 7 — local model slots (`docs/duck/BYOK-PLAN.md`)

v1 is completely local (founder decision, 2026-11-11): the user plugs in local models, no keys.
Order: `providers.py` registry with no behaviour change → local slots: Whisper folder, LLM base
URL on this Mac, ONNX voice, ONNX fill. User keys (Keychain, Connections UI, consent, key
providers, fill endpoint) stay planned in `BYOK-PLAN.md` and are **not v1**.

### Loop 8 — $29 build readiness

SHA-256 per pack file, LGPL written source offer for ffmpeg, a smaller or per-language Whisper
pack, AI fill repair instruction.

### Loop 9 — layout balance (`docs/teams/uiux-balance-01.md`)

Render screen two-column, inspector count + fade, collapse empty timeline lanes, portrait strip,
9:16 check at 1440×900 and 1280×800.

## Not in this plan

- App Store, signing, TestFlight, StoreKit: paused by decision.
- Cloud render ($5 / $20 plans), render broker: deferred; nothing in the build uploads.
- User keys (BYOK): planned, not v1. v1 makes no request to a host other than this Mac, except
  the optional pack downloads the user starts.
- DuckClean, DuckClassic, DuckStudio: later products, other lanes.
- Timeline split / reorder / remove-silence, aspect switching, auto-frame: after loop 9.

## Document map

| File | Role | State |
|---|---|---|
| `PLAN.md` | build order | **active** |
| `TODO.md` | checkboxes for the loops | **active** |
| `PRODUCT.md` | what DuckSuite is, shipped vs planned | **active** |
| `AGENTS.md`, `CLAUDE.md` | contract, team, invariants | **active** |
| `MEMORY.md` | request log | **active** |
| `docs/duck/BYOK-PLAN.md`, `GPU-FILL-PLAN.md` | design for loops 3 and 7 | **active** |
| `docs/teams/uiux-balance-01.md` | input for loop 9 | **active** |
| `ROADMAP.md`, `docs/handoff/ducksuite-phase1-plan.md` | 7 Nov 14-day plan | historical |
| `docs/duck/CLEAN-QUALITY-PLAN.md` | 7 Nov clean loops | historical; superseded by loops 3–5 |
| `docs/duck/APPSTORE-*.md`, `APP-REVIEW-NOTES.md`, `DISTRIBUTION.md` | store work | paused |
| `docs/duck/COMMERCIAL.md` | pricing incl. cloud render | deferred beyond the $29 app |
| `docs/reports/*.html` | evidence, newest on top | record |
