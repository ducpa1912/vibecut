# CLAUDE.md — DuckSuite

The full contract is `AGENTS.md`. Read it first, then `PLAN.md`, `MEMORY.md` and `TODO.md`. This file only
repeats what matters at the start of a session.

## State

- Branch `ducksuite`, repo root is this directory. Never merge `main`; unrelated histories.
- 92 tests. 377 MB app bundle. macOS 26.0, Apple silicon.
- App Store work is paused. Do not start signing or TestFlight.
- Planning is closed. Loops 1–3 are done. Open decision: bundle torch for MPS fill (4.6× faster, about +0.8 GB). Next is
  loop 4 in `PLAN.md`: one full render. No full
  render before loop 4.

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
Project under work: `prj_e95348a97316` (160 s, 1080×1920).

## Team

Five subagents in `.claude/agents/`: `product-owner` (brief + sign-off), `creator` (real use, advisory),
`engineer` (code + tests), `tester` (repro + pass/fail), `researcher` (cited facts). Spawn the PO for
the brief, the engineer and tester for the work, the creator for the result, the PO for sign-off.
A tester fail blocks sign-off. The user is final. Every loop writes `docs/teams/<loop>/review.md`.

## Models and keys

v1 is completely local: every step can take a user-supplied local model; none require a download.
User keys are planned for after v1, not built. LaMa is the only shipped
model. Translation takes a CTranslate2 folder, user-supplied. Keys go to the Keychain, never
`settings.json`. No step names a model in the UI. Plan: `docs/duck/BYOK-PLAN.md`.

## Hard rules

1. Local only. No upload, no telemetry, no DuckSuite account.
2. No translation weights shipped or hosted. The user supplies a CTranslate2 folder.
3. Do not hide a limit. Measure it and show it.
4. Old report entries are never deleted; new ones go on top.
5. A new request gets a `REQ-YYYYMMDD-NN` entry in `MEMORY.md` and prefixed items in `TODO.md`
   before code. Revision attaches to the request that created the thing.
6. Definition of done: behaviour + test + MEMORY + TODO + report in one commit.
7. Bump `textfill.VERSION` when fill output changes, and warn that the next render is cold.
8. Never merge `main`. Never resume App Store work. Never ship NLLB.

## First move

Read the four documents, run the tests, then say back the branch, the test result and the exact
first action. Do not edit before that.
