# P-A · Settings → Workflows leftovers and a plain speech failure (REQ-20261118-02 leftovers)

Owner: **OpenCode**. Folder `drop_eval/ducksuite-opencode`, branch `oc/pa-settings-leftovers`,
port 8821, data root `build/scratch-root` in that folder. Read `AGENTS.md` → "Three agents" first.

## Why
After the local-only change (REQ-20261118-02), two things a buyer would see were left over:
- Settings → Workflows shows empty text, music and script ladders and doesn't say why.
- The Check speech failure in `duckcore/engine/detect.py` (~line 1861) adds ` Engine: <detail>`,
  so the report repeats the failure in engine words.

## Files you own
- `static/duck/app.js`, only the Settings → Workflows section
- `duckcore/engine/detect.py`, the `speech_engine_empty` message only
- `duckcore/engine/workflow_config.py`, only if the ladders' data needs a flag
- `tests/test_settings_workflows.py` (new); add the speech-message test there too
- `docs/teams/pa-settings-leftovers/review.md`

## Done looks like
1. **Workflows.** A ladder with no step a buyer can choose is not drawn as an empty list. Either
   hide it, or draw one plain line that says nothing is set up and why. For example: "Text uses
   the on-device writer. Nothing to choose." Pick whichever reads plainer and explain the pick
   in the review. Never name a model in the UI.
2. **Speech failure.** The report says the failure once, in plain words, e.g. `Speech was not
   read (language: vi). Retry speech on this video; re-importing is not needed. If it still
   fails, check Setup → Engines.` The engine detail goes to the log, not the message.
3. Tests:
   - the message has no `Engine:` and still holds the language;
   - the Workflows section draws no empty ladder (a string test on `app.js` is fine, in the
     style of `tests/test_ui_actions.py`).
4. `python3 -m pytest -q tests` and `node --check static/duck/app.js` pass.
5. Run the core on port 8821 with the scratch data root, open
   `http://127.0.0.1:8821/?t=<token>` in a headless browser, take a screenshot of Settings →
   Workflows, and save it to `docs/teams/pa-settings-leftovers/workflows.png`. Scratch data only:
   no founder projects. **Do not open the app.**
6. Commit on `oc/pa-settings-leftovers` with `git -c commit.gpgsign=false commit`. Don't push.
   Don't edit `MEMORY.md`, `TODO.md` or `PLAN.md`.
