# Loop 9 — make the code match the rules (PLAN.md loop 6)

Senior PO brief, 2026-11-11. Start only after loop 8 is committed and its review is written.
Run with your own PO, engineer and tester. Do not report between loops.

## Why

v1 is completely local and no step names a model in the UI. Parts of the code say otherwise.

## Build

1. **Rewrite.** Remove the silent Ollama fallback in `script.rewrite` and the `qwen3:4b` name.
   Order is: Apple Intelligence when the Mac has it, else basic cleanup. The UI says which one
   ran. A local LLM endpoint comes back later as an explicit slot; do not build it here.
2. **Dead settings.** Delete `online_enabled` and `online_endpoint` from settings, defaults, UI
   and tests. An old `settings.json` that still holds them must load without error.
3. **Cloud speech-to-text.** The code stays for after v1. Add a test that a v1 build reaches no
   provider: with every related environment variable set, no request leaves this Mac.
4. **Model names.** No user-facing string names a model. Find them with `grep` over
   `static/duck` and every string the API returns to the UI, and fix what is found.
5. **Whisper cue.** The made-up line ("I'm going to eat a little bit of chicken.") is still in the
   review project's transcript. Find why a cue was produced where nobody speaks, and say in the
   review whether a rule can drop it; fix only if the fix is small and tested.

## Acceptance

1. A test for each of 1–3.
2. The `grep` command and its empty result are in the review.
3. A network guard test: rewrite and transcription run with sockets to any host other than
   this Mac blocked, and pass.
4. No fill output change, no `textfill.VERSION` bump. If one is needed, stop and say why.
5. `PLAN.md`, `TODO.md`, `PRODUCT.md`, `CLAUDE.md` state the new test count and that loops 7–9 are
   done.
6. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.

## Rules

Same as loop 7's brief. Write `docs/teams/loop-09-rules/review.md`.

## Final report (this is the only message the Senior PO reads)

Loop 7 is closed by the Senior PO (commit `8d1a9c8`); do not reopen it. The same read rules as
loop 8's "State on restart" apply. After loop 9, reply once with one report for loops 8 and 9:

- Per loop: verdict, each acceptance item pass/fail with its measured number, commits.
- The final render path, wall-clock against estimate, frames checked and frames with text.
- Every figure that got worse, and why.
- What was not tested.

## Revision 1 (Senior PO, 2026-11-12) — after review of `59e6732`

**The Whisper loop rule drops real speech.** In `_whisper_payload` a line said twice, where one
copy is slow (≥ 8 s, ≥ 1.2 s a word), loses every copy. A speaker who repeats a line once after a
long pause loses both.

- A made-up loop is local: the copies follow each other. Drop only copies that belong to one run
  of back-to-back segments with the same line, where that run holds a slow copy. The same line
  elsewhere in the video stays.
- Read the review project's three made-up cues first and write down what else sets them apart
  (gap between copies, word timing, any score the pack does return). Use what you measured; do not
  add a threshold you did not measure.
- Tests: (a) the review project's pattern is dropped; (b) the same line 60 s apart, one copy slow,
  keeps both; (c) a chorus line three times at speaking pace keeps all three; (d) one slow line,
  not repeated, is kept.
- The stored transcript of `prj_e95348a97316` still holds the made-up cues. Do not re-Check that
  project. Say in the review that the founder must run Check again and that it can move layer
  ranges.

Add a "Revision 1" section on top of `review.md`. One commit, with `MEMORY.md`, `TODO.md`, the
test count in `CLAUDE.md`, `PLAN.md` and `MEMORY.md`, and the scripted report row.
