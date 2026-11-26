# P-A · Settings → Workflows leftovers and a plain speech failure — review

Loop: `pa-settings-leftovers` · branch `oc/pa-settings-leftovers` · port 8821 · data root
`build/scratch-root`

## Verdict

Good to go. 390 tests pass, `node --check static/duck/app.js` passes.

## What changed

| File | Change |
|---|---|
| `static/duck/app.js` | Settings now has a **Workflows** section. Each of the five workflows gets one plain line: Script rewrite, Silent-video script, Voice-over, Music, Transcription. No list is drawn, so an empty ladder can never appear as an empty list. The notes use live facts (`engine.rewrite`, `engine.speech.default`, voice count); music and the silent-video script say plainly that this build has no provider. One sentence under the rows: “Workflows run on this Mac. There is nothing to choose in this build.” No model, folder or pack name appears. |
| `duckcore/engine/detect.py` | `speech_engine_empty` message is now `Speech was not read (language: <lang>). Retry speech on this video; re-importing is not needed. If it still fails, check Setup → Engines.` The `Engine: <detail>` suffix is gone. The detail is written to `duckcore.engine.detect` at warning level instead. |
| `tests/test_settings_workflows.py` | New. The speech message has no `Engine:`, keeps the language, keeps the retry and Setup → Engines steps, keeps the detail out of the report and in the log. `workflowRows` is extracted from `app.js` and run under node: five rows, no steps/routes property, no model names, and the right note for the ready and off states. The `workflowsMarkup` source is checked for `<ul>/<ol>/<li>/<select>`. A guard test also fails if a local text or music provider ships without this screen being revisited. |
| `docs/teams/pa-settings-leftovers/workflows.png` | Screenshot of the new section at 1440×900. |

## A fact the brief assumed wrong

Settings → Workflows did **not** exist on `oc/pa-settings-leftovers`. The old local admin console
(which held the workflow route cards) is not in this branch; `static/duck/app.js` has no workflow
markup at all, and `/api/settings` has no `workflows` field. So there was no empty ladder to hide.
I did not restore the admin route editor: that needs a new API field and settings writes, and v1 is
local-only. Instead the Settings screen states, in one line per workflow, what runs and where the
gaps are. This is the “one plain line” option, chosen over hiding because a missing section leaves a
buyer asking where their workflows went; five short rows answer that without drawing a ladder.

## Measured

- `python3 -m pytest -q tests` → **390 passed**, 5 existing torch deprecation warnings.
- `node --check static/duck/app.js` → pass.
- Core launched on port 8821 with `build/scratch-root`; Settings opened in headless Chrome (CDP) at
  1440×900; screenshot `docs/teams/pa-settings-leftovers/workflows.png`. The app was not opened.
- Scratch data only; no founder project or Containers data was read.

## Not verified

- The real app and a real Check with a failing speech engine were not run (rules: no app, no founder
  media). The speech message is tested by calling `_report_warnings` with the same `audio` shape the
  pipeline passes.
- The rewrite-ready branch is tested under node but the screenshot shows the dev-core state
  (“Off in this build.”) because the Apple rewrite helper is not present outside the app. In the app
  the same row reads “On-device writer.” while the helper answers ready.
- Layout at 1024×700 and 200 % zoom was not measured for the new section. It uses the existing
  `.settings-grid` and `.kv` rows and spans one column at 1440×900.
- No native/WKWebView rendering check. The section is plain `.kv` markup already used by the same
  modal.
- The detail log is not surfaced to the user anywhere; it is only in the core log, by design.

## PO review (2026-11-26)

- **Speech failure: accepted.** The `detect.py` change and its test are merged.
- **Workflows section: withdrawn.** The item is closed as moot. The empty ladders were in the
  admin console, which was removed earlier, so there was nothing left to hide. The new section
  listed "Music" and "Silent-video script", but `PRODUCT.md` names generated music and the admin
  console as non-goals, and the silent-video script is not a v1 feature. The Models section
  already shows transcription, writing and voice. `app.js` is unchanged from `ducksuite`, the
  workflow tests are removed, and the speech test moved to `tests/test_speech_report.py`.
- The revision was sent to OpenCode, but its client hung with no output, so the PO made the
  revision during the merge.
