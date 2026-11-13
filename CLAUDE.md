# CLAUDE.md — DuckSuite

The full contract is `AGENTS.md`. Read it first, then `PLAN.md`, `MEMORY.md`, `TODO.md` and
`PRODUCT.md`. This file only repeats what matters at the start of a session.

## Read, and do not read

- Read: `AGENTS.md`, `PLAN.md`, `MEMORY.md`, `TODO.md`, `PRODUCT.md`, and the current loop's
  `docs/teams/<loop>/BRIEF.md` / `review.md`.
- **Never read or search** `old_memory.md`, `old_todo.md`, `old_plan.md`: they are outdated
  instructions, and reading them overloads the context until the session compacts.
- **Never read** `docs/reports/SESSION.html`, `docs/reports/ducksuite-product-progress.html`, or
  another loop's review. The two HTML files are for the human to track the work: an agent only
  writes to them, with a scripted insert that prints nothing.
- `PRODUCT.md`, `TODO.md` and `MEMORY.md` hold only the latest direction of the app and the work
  that is not finished. Keep them small: `MEMORY.md` < ~80 lines, `TODO.md` only open work,
  `PLAN.md` only open loops. Moving closed content into `old_*.md` is part of closing a loop.

## OpenCode

Every prompt Claude sends or queues to OpenCode runs at **high** reasoning effort. The variant goes
on the model: `-m 'opencode-go/deepseek-v4.1-flash#high'`. The default is medium; do not use it.

```bash
~/.opencode/bin/opencode run -s <session> -m 'opencode-go/deepseek-v4.1-flash#high' --auto "<prompt>"
```

- One prompt at a time for each session; queue the next one behind it, never beside it.
- Killing the `opencode run` client does not stop the work: the background service keeps running
  the session. To stop it: `~/.opencode/bin/opencode api POST /api/session/<session>/interrupt`.
- Do not edit the repo while an OpenCode session is working in it.

## State

- Branch `ducksuite`; repo root is this directory. Never merge `main`; unrelated histories.
- 228 tests pass (2026-11-13). Bundle ≈ 981 MB. macOS 26.0, Apple silicon. GPU fill (MPS) is the default; CPU is
  an optional pack.
- App Store work is paused. Do not start signing or TestFlight.
- Planning is closed. Brief loops 7–19 are closed (ink check through Cut enhance); loop 20 (VLM
  story captions) is roadmap. PLAN loops 7–8 are still open: local model slots, $29 readiness.
- The 2026-11-13 code review (`docs/reviews/2026-11-13-loops-07-19.md`) fixed #1–#5 and #8 (fix-01
  to fix-03); its open low findings are in `TODO.md`.
- `textfill.VERSION` 17; the last render has 0 leftover text, 40 of 42 lines checked. The ink store
  (`<data root>/ink`, `ink.STORE_VERSION` 2) must hold every field of `ink.Ink`. Branch `loop8-wip`
  is superseded by `7bda48d`.

## Commands

```bash
export PATH="/Users/happynghia/.nvm/versions/node/v26.11.1/bin:/opt/homebrew/bin:$PATH"
./scripts/build-xcode-dev.sh
open build/DuckSuite-Xcode.app
python3 -m pytest -q tests
node --check static/duck/app.js
git -c commit.gpgsign=false commit
git push https://github.com/ducpa1912/vibecut.git ducksuite
```

Data root: `~/Library/Containers/com.ducksuite.app/Data/Library/Application Support/DuckSuite`.
Project under work: `prj_e95348a97316` (160 s, 1080×1920), edit `ed_38a4c36a3aae`.

## Team

Five subagents in `.claude/agents/`: `product-owner` (brief + sign-off), `creator` (real use,
advisory), `engineer` (code + tests), `tester` (repro + pass/fail), `researcher` (cited facts). A
tester fail blocks sign-off. The user is final. Every loop writes `docs/teams/<loop>/review.md`.

## Models and keys

v1 is completely local: every step can take a user-supplied local model; none require a download.
User keys are planned for after v1, not built. LaMa is the only shipped model. Translation takes a
CTranslate2 folder, user-supplied. Keys go to the Keychain, never `settings.json`. No step names a
model in the UI. Plan: `docs/duck/BYOK-PLAN.md`.

## Hard rules

1. Local only. No upload, no telemetry, no DuckSuite account.
2. No translation weights shipped or hosted. The user supplies a CTranslate2 folder.
3. Do not hide a limit. Measure it and show it.
4. Old information is never deleted: closed entries move to `old_*.md`, report entries stay on top.
5. A new request gets a `REQ-YYYYMMDD-NN` entry in `MEMORY.md` and prefixed items in `TODO.md`
   before code. Revision attaches to the request that created the thing.
6. Definition of done: behaviour + test + `MEMORY.md` + `TODO.md` + `docs/teams/<loop>/review.md` +
   a scripted report row, in one commit.
7. Bump `textfill.VERSION` when fill output changes, and warn that the next render is cold.
8. Never merge `main`. Never resume App Store work. Never ship NLLB.

## First move

Read the working documents, run the tests, then say back the branch, the test result and the exact
first action. Do not edit before that.
