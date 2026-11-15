# Loop 25 — local model slots (PLAN loop 7, REQ-20261111-03; REQ-20261115-02 P3 rerun)

Written by the sub-leader on 2026-11-15. HEAD `b109e45`, 272 tests. Build team: OpenCode, one
phase. Design: `docs/duck/BYOK-PLAN.md` (keys are **not** v1; build only the local slots). Rules as
loop 23 ("Rules for every phase"); no fill change, `textfill.VERSION` stays 17.

What exists: `duckcore/providers.py` (a `Provider` contract, a `Registry`, `local_base_url`) that
nothing uses yet; the fill slot ("Your fill model", `app_settings.fill_model_status`,
`fill_model_path`) is the pattern every new slot copies: Settings row, state line **None** /
**In use · file** / **Not usable · reason**, **Choose**, **Clear**, the folder validated and copied
into app data, a red toast on a bad folder, the state unchanged.

## 1. Registry, no behaviour change

Register the four steps that already run — transcription (Apple Speech, the Whisper pack), rewrite
(Apple Intelligence, basic cleanup), voice (`say`, the Kokoro pack), clean fill (LaMa, the user fill
model) — and route each step's choice through `providers`. **The existing tests pass unmodified**
(state the count before any slot is added). Cloud STT code paths in `stt.py` are not registered
and stay unreachable with keys unset, exactly as today.

## 2. Transcription slot — "Your transcription model"

A folder holding an MLX Whisper model (`config.json` plus `weights.npz` or `*.safetensors`).
Validate the files, copy into `<data root>/models/stt-user/`, and when set, transcription uses it in
place of the pack, for every language. Settings stores the path, a provider id and an enabled flag.
**Accept:** tests for a valid folder, a folder missing weights (reason names the missing file), and
Clear; a test that Check calls the user model when set (stub `mlx_whisper`), and the pack when not.

## 3. Rewrite slot — "Your writing model"

A base URL on this Mac only (`providers.local_base_url`), checked with `GET /v1/models` (2 s timeout);
the first model id it lists is used with `POST /v1/chat/completions`. When set and reachable, it
replaces Apple Intelligence for rewrite (`script.rewrite`) — this is the user's explicit choice, not
a fallback; with no slot set, the order stays Apple Intelligence → basic cleanup, and nothing tries a
local endpoint on its own. Unreachable at rewrite time → a plain error that names the URL, no silent
switch. The state line never shows the server's model id.
**Accept:** tests: loopback accepted, a LAN or public host refused, `/v1/models` down → "Not usable",
a rewrite with a stub server returns its lines, no request is made when the slot is unset
(patch the HTTP client and count 0 calls).

## 4. Voice slot — "Your voice model"

A folder with a Kokoro-format ONNX model and its voices file (the same two files the Kokoro pack
uses). Validate, copy into `<data root>/models/voice-user/`, and list its voices as
`Your voice · <voice id>` in the voice menu beside the built-in ones. `onnxruntime` is importable in
the built sidecar (loop 24).
**Accept:** tests for valid, missing-voices-file and Clear; the voice list shows the user voices
only when set; synthesis routes to the user files (stub `kokoro_onnx`).

## 5. Everywhere

- No step names a model in the UI; no link to a download; no key field; `settings.json` holds a
  path, a provider id and a flag, never a secret (a test reads the file).
- Settings → Models: the three new rows look like "Your fill model" (same height, same states).
  Capture Settings at 1440×900 on the scratch root (`build/loop25-evidence/`, core served with
  `python3 duck_app.py --data-root build/loop25-evidence/root --port 8799`; browser capture allowed
  until N1 opens) with each row in each of its three states, and list the paths.
- Add to `docs/teams/founder-test-all.md`, part 10: one click-by-click step per slot.

## Done

One commit: code + tests + `docs/teams/loop-25-model-slots/review.md` (pass/fail per item with
numbers, what got worse, what was not tested, capture paths) + `TODO.md` (tick the four
REQ-20261111-03 items and the P3 line) + `MEMORY.md` Outcome. pytest and `node --check` pass; state
the count. Do not push.

## Revision 1 — 2026-11-15 (sub-leader review of `397c44b`)

Verified by the sub-leader: 279 tests pass, `node --check` clean; read `model_slots.py`, the
`stt.py`, `script.py`, `providers.py` and Swift diffs. Items 2–4 accepted in their tested contract;
item 1 accepted as a minimal registry (each step registered and dispatched; engine choice stays in
the step), not a refactor. Four defects:

R1. **The writing slot can never finish a real rewrite.** `model_slots.request` uses `timeout=2`
    for `/v1/chat/completions` too; a local LLM rewriting a script takes tens of seconds. Keep 2 s
    for `/v1/models`; give completions a long timeout (≥ 300 s) and, if the server streams or is
    slow, a plain progress line. Test: a stub server that answers completions after 3 s succeeds.
R2. **Settings blocks up to 2 s per load** when the writing server is down, because `status()` calls
    `/v1/models` every time. Cache the reachability result (≤ 30 s) or check it in the background;
    Settings must answer in < 0.3 s with the server down. Test with a server that never answers.
R3. **Old copies pile up.** Every Choose copies into a new `uuid` folder and Clear/replace leaves
    the old one; the Swift picker also leaves `slot-imports/<uuid>` behind after the core copies it.
    Replace and Clear delete the previous copy (only inside `models/stt-user` and
    `models/voice-user`); the picker's import folder is removed after the core copy succeeds. Test:
    choose twice, clear → 0 folders left.
R4. **No captures.** Leave a script `build/loop25-evidence/states.py` (gitignored) that puts the
    scratch root into each of the nine Settings states in turn; the sub-leader takes the captures.
    Say which command serves the core on that root.
R5. pytest and `node --check` pass (state the count); `review.md` Revision 1 section; one commit;
    do not push.
