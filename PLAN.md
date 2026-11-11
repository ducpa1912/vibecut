# PLAN — DuckSuite build order

Current plan only. Closed loops 1–4 and the ink-check loop are archived in `old_plan.md` (agents do
not read it). `PRODUCT.md` says what the product is, `TODO.md` holds the open checkboxes,
`MEMORY.md` the decisions in force, `AGENTS.md` the working contract.

## Where the build stands (measured 2026-11-12)

| Fact | Value |
|---|---|
| Branch / tests | `ducksuite`, 155 pass, `node --check` clean |
| Bundle | ≈ 981 MB (torch 565, GPU LaMa 196, sidecar 136, ffmpeg 41; no ONNX) |
| Dev Mac | M1, 8 GB RAM, macOS 26.7.2 |
| Review project | `prj_e95348a97316`, 160 s, 1080×1920, 35 clips, edit `ed_38a4c36a3aae` |
| Clean layers | 42 fill · 0 blur; 32 `moving`; one founder layer `auto: false` |
| Fill | `textfill.VERSION` 17, GPU MPS default, CPU as an optional pack; hole = letter strokes |
| Leftover-text check | post-render, per letter against the source, 40 of 42 lines, ≈ 60–70 s |
| Last render | 0 leftover in 2,964 frame checks, 2 lines not checked; cold 698 s |

## What is still wrong

1. **Fill is weak on moving footage** and that is most of the footage: LaMa fills one frame at a
   time and cannot rebuild a background it never saw. This is the product's main feature.
2. **The leftover check sees only lines that have a layer.** Text Check never found is not judged,
   and a line under 5 frames is reported as not checked. Cold render cost rose to 698 s and the
   estimate does not know about crossings.
3. **Code that contradicts the rules:** `script.rewrite` silently falls back to Ollama and names
   `qwen3:4b`; `online_enabled` / `online_endpoint` are stored and unused; cloud STT paths have no
   test saying they are unreachable in a v1 build.
4. **Layout balance** is unfinished on Render, the inspector and the timeline.

## Rule for ordering

Every change to fill output bumps `textfill.VERSION` and makes the next full render cold. Finish
fill-changing decisions first, then pay for one render. Do not run a full render to prove a small
fix; render the span that shows it.

One loop = PO brief → engineer + tester → creator → PO sign-off → one commit with `MEMORY.md`,
`TODO.md`, a report row and `docs/teams/<loop>/review.md`.

## Loops

### Loop 5 — a better fill for moving footage

- Researcher first: licence table for the candidates, quoted clause, commercial use yes/no.
- Bench the allowed candidates on the moving spans (`scripts/bench_fill.py`).
- Alternative with no licence: the custom ONNX fill slot (loop 7), user-supplied.
- Accept: a candidate beats LaMa on moving spans by a stated dB at a stated cost, or the doc records
  that none does and the UI keeps the `moves` warning.

### Loop 6 — make the code match the rules

- Rewrite: no silent fallback, no model name in a user-facing string; Apple Intelligence, else basic
  cleanup, stated in the UI.
- Delete the unused online settings; test that cloud STT is unreachable in a v1 build.
- Accept: tests for each; `grep` finds no model name in user-facing copy.

### Loop 7 — local model slots (`docs/duck/BYOK-PLAN.md`)

v1 is completely local: the user plugs in local models, no keys. Order: `providers.py` registry with
no behaviour change → Whisper folder, LLM base URL on this Mac, ONNX voice, ONNX fill. User keys stay
planned in `BYOK-PLAN.md` and are **not v1**.

### Loop 8 — $29 build readiness

SHA-256 per pack file, LGPL written source offer for ffmpeg, a smaller or per-language Whisper pack,
AI fill repair instruction, manual microphone test, creator-readable import errors.

### Loop 9 — layout balance (`docs/teams/uiux-balance-01.md`)

Render screen two columns, inspector count + fade, collapsed empty lanes, portrait scene strip,
9:16 verified at 1440×900 and 1280×800.

## Not in this plan

- App Store, signing, TestFlight, StoreKit: paused by decision.
- Cloud render plans ($5 / $20), render broker: deferred; nothing in the build uploads.
- User keys: planned, not v1.
- DuckClean, DuckClassic, DuckStudio: other lanes.
- Timeline split/reorder/remove-silence, aspect switching, auto-frame: after loop 9.

## Document map

| File | Role | Rule |
|---|---|---|
| `AGENTS.md` | contract, team, invariants | read first |
| `MEMORY.md` | direction and decisions in force | current only, < 80 lines |
| `TODO.md` | open checkboxes | current only |
| `PLAN.md` | build order for open loops | this file |
| `PRODUCT.md` | what DuckSuite is, shipped vs planned | current only |
| `old_memory.md`, `old_todo.md`, `old_plan.md` | frozen history | **agents do not read** |
| `docs/teams/*/review.md`, `BRIEF.md` | loop evidence | read the current loop's brief/review only |
| `docs/reports/*.html` | the human's progress record | **agents append, never read into context** |
| `docs/duck/BYOK-PLAN.md`, `GPU-FILL-PLAN.md` | design for loops 5–7 | active |
| `ROADMAP.md`, `docs/handoff/*` | 7 Nov plan | historical |
