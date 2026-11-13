# AGENTS.md — DuckSuite

Read `PLAN.md` (the build order), `MEMORY.md` (direction and decisions in force), `TODO.md` (open
work) and `PRODUCT.md` (what the product is) before touching code. Planning is closed: work the loops
in `PLAN.md` in order.

## Context budget — what to read, what not to

The session compacts when too much is pulled in. Read the four working documents, this contract, and
the current loop's `BRIEF.md` and `review.md`. Nothing else.

- **Never open, print or search** `old_memory.md`, `old_todo.md`, `old_plan.md`. They are outdated
  instructions kept as frozen snapshots; nothing in them is a rule or a task any more. Write to them
  only to archive closed content.
- **Never read** `docs/reports/SESSION.html` or `docs/reports/ducksuite-product-progress.html`, and
  never read another loop's review. The two HTML files are for the human to track the work: an agent
  only writes to them, with a scripted insert at the known anchor that prints nothing. Do not load
  them to "get up to speed".
- `PRODUCT.md`, `TODO.md` and `MEMORY.md` hold only the latest direction of the app and the work
  that is not finished. Anything done or superseded leaves them in the commit that closes it.
- **Keep the working documents small.** `MEMORY.md` stays under ~80 lines, `TODO.md` lists only open
  work, `PLAN.md` only open loops. When a loop closes, move its request entry, done items and closed
  plan text into the matching `old_*.md` in the same commit. Archives are write-only for agents.
- Never re-read a file you just wrote, and never dump a whole document to find one line: `grep` it.

## What this is

DuckSuite is an offline macOS video editor. A local Python core does analysis, clean, and render; a
WKWebView UI is the product surface; a thin Swift shell owns the window, disk access, and the sidecar.
One project is open at a time. No account, no upload, no telemetry, no downloaded executable code.

```
duckcore/        Python core: check, clean, render, packs, stt, translation
static/duck/     UI: app.js, app.css, index.html, extracted helpers
mac/DuckSuite/   Swift shell (window, import bridge, sidecar launch)
scripts/         build, sign, bench
tests/           pytest suite + node helper tests
docs/            reports, team reviews, plans
```

## Ground rules

1. Local only. Nothing leaves the Mac. Model packs are data, not code.
2. Do not start App Store, signing, or TestFlight work unless the user asks. It is paused by decision.
3. Merge target is this branch, `ducksuite`. `main` has no common ancestor and lives in another
   worktree. Never merge it.
4. Do not hide a limit. If fill cannot rebuild what it covers, measure it and say so in the UI.
5. Old information is never deleted. The report keeps every entry (new on top); closed request
   entries, done items and closed loops move to `old_memory.md`, `old_todo.md`, `old_plan.md`.
6. Existing comments in code are payload. Do not shorten or delete one you were not asked to change.

## Request intake — the factory loop

Every request enters the same pipeline. Classify it before touching code.

**New request** — a capability, screen, data flow or behaviour that does not exist yet.
Example from this project: "put the transcript panel inside the video preview panel".
That needs a new panel, state and data flow, so it is new.

**Revision** — a change to something that already exists: polish, spacing, wording, a
regression, a bug in shipped behaviour. Example: "revise the UI/UX", "the inspector is too busy".

Rule of thumb: if the request can be answered with a screenshot of an existing screen, it is a
revision. If it needs a new panel, state, endpoint or data flow, it is new.

### For a new request

Do this before writing code.

1. **`MEMORY.md`** — append one entry under `## Request log` (keep the file under ~80 lines; move
   closed entries to `old_memory.md` when their loop closes):

   ```md
   ### REQ-20261111-01 · 2026-11-11
   **Request:** <the user's words, verbatim>
   **Read as:** <one sentence: what must exist after this>
   **Response:** <what the agent said it would build, or the decision taken>
   **Outcome:** <filled when done: what shipped, test count, follow-up id if any>
   ```

2. **`TODO.md`** — add the plan under the right priority. Every item carries the request id:

   ```md
   - [ ] REQ-20261111-01 · transcript panel docks inside the video preview
   - [ ] REQ-20261111-01 · scene change updates the docked transcript
   ```

3. Implement, test, then tick the items and fill `Outcome`. Name the change, not the sha of the
   commit that contains the record; a commit cannot contain its own hash. In the same commit, move
   the closed entry to `old_memory.md` and the done items to `old_todo.md`, so the working files
   hold only open work.
4. Add the loop to `docs/reports/ducksuite-product-progress.html` on top, old entries kept. Do it
   with a scripted insert against the known anchor; do not read the file into context.

### For a revision

No new entry body. Add one line to the request that created the thing if the plan changes, and a
TODO line only when it creates new work. It still gets a commit and a report line.

### Never batch

One request, one MEMORY entry, one TODO block, one commit. A second request during the same turn
gets its own id and its own block, even when the code lands together.

## Team

Five roles. Claude Code loads them from `.claude/agents/` and can spawn them by name; other harnesses
use the same prompts from this file.

| Role | Owns | Gate |
|---|---|---|
| `product-owner` | Brief, acceptance criteria, screen review, sign-off | Final gate before commit |
| `creator` | Taste, flow and output as a real creator | Advisory; notes are required |
| `engineer` | Code, tests, invariants | Tests and syntax must pass |
| `tester` | Reproduction, failing test first, build and real-app check | A fail blocks sign-off |
| `researcher` | Apple API availability, licences, sizes, costs | Facts cited, never guessed |

One loop:

1. `product-owner` writes the brief: request id, what must exist, acceptance a human can see.
2. `engineer` implements and tests. `tester` reproduces first when it is a bug.
3. `creator` uses the real app or the real render and files three time costs and two wrong looks.
4. `tester` reports pass/fail per acceptance check, plus anything untested.
5. `product-owner` signs off or returns it with the findings.
6. One commit: code + test + `MEMORY.md` + `TODO.md` + a report row.

The creator is advisory, not a veto. A tester fail blocks sign-off. The user is the final authority;
disagreement escalates to them, not to a vote. Every loop writes `docs/teams/<loop>/review.md` with
verdict, good-to-go, revisions and bugs.

## Model plugins — BYOM and BYOK on every step

v1 is completely local: a step runs on its local default or on a local model the user plugs in.
User keys are planned for after v1 and are not built. The full design has three sources per step: a
local default, a user-supplied local model, or a user's key. No step requires a download. DuckSuite ships one model, LaMa, because Clean is the product; it
ships no key, no translation weights and no proxy.

| Step | Local default | Local model you can plug in | User key |
|---|---|---|---|
| Transcribe | Apple Speech | Whisper/MLX folder | OpenAI, Groq, Deepgram, OpenRouter |
| Translate | Apple Translation | CTranslate2 folder (shipped) | DeepL, OpenAI |
| Rewrite | Apple Intelligence | local LLM endpoint (Ollama, llama.cpp) | OpenAI, Anthropic, OpenRouter |
| Voice | `say`, Kokoro pack | Kokoro voices, custom ONNX | ElevenLabs, OpenAI TTS |
| Clean fill | LaMa (bundled) | custom ONNX inpaint model | user-run HTTP fill service |
| OCR | Apple Vision | — | — |
| Scene cuts | ffmpeg | — | — |

Contract:

- Registry in `duckcore/providers.py`; each provider implements `status()`, `prepare()`, `run()`, and
  declares the task it serves, the files it needs and whether it needs a secret.
- Settings store a path, a provider id and an enabled flag. Never a key. Keys live in the Keychain
  through one helper, never in `settings.json`, logs or error strings.
- A user-supplied folder is validated and copied into app data so the sandboxed core can read it.
- The UI never names a model for a user-supplied slot, and never links to a download DuckSuite
  provides.
- A step with no plugin stays on its default. Every local flow works with zero keys.

Design and rollout: `docs/duck/BYOK-PLAN.md`.

## Run

```bash
# Full local build: core, static, helpers, LaMa, ad-hoc signature.
./scripts/build-xcode-dev.sh
open build/DuckSuite-Xcode.app

# Core only, for UI work in a browser.
python3 duck_app.py --data-root \
  "$HOME/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite" \
  --port 8799
# The launch token is read from stdin. UI: http://127.0.0.1:8799/?t=<token>
```

App data root: `~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite`
Projects live in `projects/<id>/`, renders in `projects/<id>/renders/`, fill cache in `projects/<id>/fill/`.

## Test

```bash
python3 -m pytest -q tests      # 219 pass (2026-11-13)
node --check static/duck/app.js
./bin/vision_probe <dir>        # OCR on real frames, JSON lines
python3 scripts/bench_fill.py --project prj_... --frames 10   # fill quality, ground truth
```

A change is not done until pytest passes, `node --check` passes, and the real screen was looked at.

## Environment gotchas (this Mac)

- A restarted harness resets `PATH` to `/usr/bin:/bin:/usr/sbin:/sbin`. Put these back first:
  ```bash
  export PATH="/Users/happynghia/.nvm/versions/node/v26.11.1/bin:/opt/homebrew/bin:$PATH"
  ```
- `ffmpeg` / `ffprobe`: bundled at `build/DuckSuite-Xcode.app/Contents/Resources/Helpers`, also in
  `/opt/homebrew/bin`. The app reads the bundled ones.
- The git remote is SSH and fails. Push over HTTPS:
  ```bash
  git push https://github.com/ducpa1912/vibecut.git ducksuite
  ```
  The repo is named `vibecut`; the product branch is `ducksuite`.
- The commit signing key needs a passphrase. Use `git -c commit.gpgsign=false commit`.
- Outside the app the core finds no fill model. For a dev core or a script that renders, set
  `DUCK_FILL_MODELS="$PWD/build/DuckSuite-Xcode.app/Contents/Resources/base-models"`.
- The sidecar handshake times out after 12 s. If the app window is blank, check for an orphan
  `Resources/duckcore/duckcore` process and kill it before relaunching.

## Platform

- The app is macOS 26.0, Apple silicon only. FoundationModels (26.0) and SpeechAnalyzer
  (`anyAppleOS 26`) set the floor; Translation alone would allow 15.0. The target and
  `LSMinimumSystemVersion` are 26.0. Lowering it is a feature change, not a flag.
- The bundle is ≈ 981 MB: torch 565 MB, GPU LaMa 196 MB, sidecar 136 MB, ffmpeg/ffprobe 41 MB.
  LaMa cannot move to a download without shipping an app whose main feature is missing.

## Invariants

- Clean layer boxes are normalized to the source frame; ranges are absolute source time.
- The fill cache key includes `textfill.VERSION`. Bump it whenever fill output changes, or old clips
  are reused and the render silently keeps the previous look. A bump makes the next render cold and
  slow; say so.
- Blur uses the wide shadow pad, fill uses the tight one (`layer_rect`). Do not merge them.
- Check must read the true first frame (`pipeline._first_still`). Some titles live under 100 ms.
- A layer's range reaches a whole sample step before its first reading and `SAMPLE_SLACK` past its
  last (`detect._run_range`). Half a step leaked two frames of text. Prove edge changes by OCR on
  every frame of a short render, not on spot frames.
- Proofs are optional. Render never waits for a proof.
- OCR comparison is `duckcore.textmatch.same_text`; never add a second rule.
- The render queue claims a job and sets `worker_pid` in one transaction. Never reintroduce
  select-then-update, and only requeue a running job whose worker is gone.
- Fill ships GPU-first: torch and `big-lama.pt` are bundled (981 MB total); GPU is the default.
  CPU is an optional 198 MB download (`fill-lama-cpu`) that installs `lama_fp32.onnx` into
  `models/fill`; the CPU button stays disabled until it is installed. onnxruntime stays for that pack
  and for Kokoro. `seed_models` hardlinks the bundle model into app data so both share one folder.
  CoreML EP is 32× slower and closed. Cache keys separate devices through `method_stamp` (`:gpu`).
- CPU fill time swings up to 4.6× with load on an 8 GB Mac. Never quote one run as the speed.
- A line over a moving background is flagged (`quality: "moving"`), not silently switched to blur.
  Only a flash under 0.6 s, a line read once, defaults to blur.
- DuckSuite ships no translation weights and hosts no translation download. The user supplies a
  CTranslate2 folder; Settings copies it into app data and validates the three files.
- `clean.patch_layer` marks a layer `auto: false`; Clean all must keep the user's Fill/Blur/Off choice.
- Clean all is destructive-ish: it confirms first and reports `fill · blur · off` counts.

## Change recipe

0. Classify the request with **Request intake** above. New request: log it in `MEMORY.md` and
   plan it in `TODO.md` first.
1. Pick the next open loop in `PLAN.md`; its checkboxes are in `TODO.md`.
2. Reproduce it; write the failing test first when the bug is in Python.
3. Fix small, in the module that owns the behaviour.
4. `pytest`, `node --check`, then rebuild and look at the real screen at 1440×900.
5. Commit in Conventional Commits, then push with the HTTPS URL above. One loop = one commit.
6. Close the loop in the same commit: tick `TODO.md`, fill `Outcome` in `MEMORY.md`, add the entry
   to `docs/reports/ducksuite-product-progress.html` on top.

Definition of done: behaviour + test + `MEMORY.md`, `TODO.md`, the loop's `review.md` and a report
row in one commit. Closed content is archived in `old_*.md` in that same commit; the working files
stay current and small. A commit that changes behaviour but leaves the documents stale is not done.

## Where the evidence lives

Working documents (read these): `PLAN.md`, `MEMORY.md`, `TODO.md`, `PRODUCT.md`, this file.

- `old_memory.md`, `old_todo.md`, `old_plan.md` — outdated, frozen. **Agents do not read or search them.**
- `docs/reports/ducksuite-product-progress.html` — the human's product report, newest on top.
  **Append only; never read into context.**
- `docs/reports/SESSION.html` — the human's session record. **Write only, scripted insert; never read.**
- `docs/teams/<loop>/BRIEF.md` and `review.md` — the current loop only.
- `docs/duck/BYOK-PLAN.md` — bring-your-own-key/model design and rollout.
- `docs/duck/GPU-FILL-PLAN.md` — LaMa on CoreML/MPS/cloud, with the packaging cost.
- `docs/duck/gpu-fill-bench.md` — the measured CPU / CoreML / MPS numbers and the estimate fix.
- `docs/teams/uiux-balance-01.md` — layout balance review and proposals.
- `scripts/bench_fill.py` — fill quality benchmark with ground truth.
- `tests/` — behaviour contract. `tests/test_clean_loop2.py` covers layer planning and the fill hole.

## Known traps

- Do not start a throwaway HTTP server to read an HTML file. Open the file.
- Do not judge fill quality from one frame. Use the benchmark, then check a real span.
- Do not trust `check.json` after a detection change; the project must be re-Checked.
- A full render after a cache bump can take hours. Warn before starting one.
- Do not run a full render to prove a small fix. Render the short span that shows it; the one full
  render is loop 4 in `PLAN.md`.
- Saved fills stop being written under 10 GiB free disk (`SAVED_MIN_FREE`). Check `df` before a long
  render.
- The Whisper pack is 1.61 GB and is the only transcription path for Vietnamese. Treat a first
  run as a download step, not an instant start.
