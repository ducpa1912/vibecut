# Loop 25 — local slots

Starting HEAD `00f3a49`. VERSION 17 unchanged. No push.

1. PARTIAL/FAIL strict routing: existing steps registered as local dispatch wrappers;
   legacy policy remains inside each step. 272 existing tests passed unmodified
   before slots were added (29.98 s), matching the 272-test starting baseline.
   Voice pack calls also register separately. Individual transcription engines
   and rewrite fallback choices remain inside legacy functions, so the full
   choice-routing requirement is not claimed. Cloud providers are not registered.
2. PASS for tested slot contract: files validated, copied to models/stt-user,
   missing weights rejected without changing settings, Clear restores defaults.
   Stubbed MLX receives the selected path and Vietnamese language. Existing
   default transcription tests remain passing. Real weights were not run.
3. PASS for tested slot contract: loopback validation, 2-second HTTP timeout,
   no redirects, first listed model used, explicit error on selected-server
   failure. A real loopback HTTP stub returned its rewritten line. Unset slot
   makes 0 HTTP calls. State text hides server model ids.
4. PASS for tested slot contract: validates model and readable voices archive,
   copies to models/voice-user, lists Your voice entries only while selected;
   stub synthesis receives copied model paths. Valid/invalid/Clear covered.
5. FAIL visual acceptance: three Settings rows and native folder bridge added;
   persisted records contain only path/provider/enabled (asserted). Founder
   steps added. Browser inspected None states at 1000×700; 1440×900 and nine
   state captures remain missing. Browser screenshot failed with “Screenshot
   needs a visible tab” after focus. Capture paths: none. No model names or
   download links added to the new rows; existing pack UI is unchanged.

Validation: 279 tests pass, 5 existing warnings, 36.66 s. Node syntax and Swift
frontend parse pass. Full native build was not run. Seven new slot tests pass.

What got worse: selected writing endpoint status adds up to two seconds to
Settings loading. Replacing local folders retains old copied generations;
Clear disables rather than deleting those files. Native folder import and core
copy can temporarily duplicate model storage. Registry wraps legacy dispatch
rather than fully separating each engine into a provider.

Not tested: real MLX/Kokoro weights, native picker in the app, nine visual states,
full build, public network (forbidden), any render. No founder media committed.
This loop is not ready for acceptance: items 1 and 5 remain incomplete.

## Revision 1

Starting HEAD `1ab3a07`. The sub-leader accepts original items 1–4; the preceding
verdict is historical. No changes to fill output or VERSION 17.

- R1 PASS: `/v1/models` keeps its 2-second timeout; completions use 300 seconds.
  The real loopback stub delays completions 3 seconds and succeeds. Rewrite
  displays a working line explaining that the local server may take minutes.
  Completed user rewrites are labelled “your writing model”, not basic cleanup.
- R2 PASS: Settings starts a daemon reachability check, returns immediately,
  and caches its result for less than 30 seconds. A server that never answers
  produced snapshot latencies 0.031267 / 0.000298 / 0.000240 seconds, all below
  0.3 seconds. Expired results are not served as current; the UI says checking.
- R3 PASS: choose-choose-clear leaves 0 folders in each managed slot directory
  and 0 picker import folders, tested for transcription and voice. Replacement
  retains one current folder. An external source directory survives Clear.
  Only direct children of the two managed slot directories are deleted; picker
  imports are removed only after successful copying and settings persistence.
- R4 PASS: `build/loop25-evidence/states.py` provides all 3 tasks × 3 states.
  `git check-ignore` confirms the script is ignored. In-use folder fixtures are
  status-only, not usable inference weights; the writing in-use option runs a
  local stub server until interrupted. Reopen Settings after selecting a state;
  allow a background check and reopen for the writing state.
- R5 PASS: 283 tests passed in 32.74 s, 5 existing TorchScript warnings;
  `node --check static/duck/app.js` passed.

Core command (launch token is provided on stdin):

```bash
python3 duck_app.py --data-root build/loop25-evidence/root --port 8799
```

State command: `python3 build/loop25-evidence/states.py TASK STATE`, where TASK is
transcription/rewrite/voice and STATE is none/in-use/not-usable. Keep the writing
in-use process running for its capture. The sub-leader owns the nine captures.

What got worse: failed writing-server state may take up to 30 seconds to refresh;
first Settings load can say checking until reopened. A rewrite may occupy its
request worker for up to 300 seconds. No cancellation support added.
Not tested: real weights, native folder-picker execution, new screen captures,
or a full native build. No new footage, renders, model downloads, or keys.

## Revision 2

Starting HEAD `5e91bf6`. `.claude/launch.json` untouched.

- R6 PASS: explicit `checking` state is neutral (“Checking…”). Pending checks
  carry start times; a check still pending after 2.5 s returns a URL-specific
  timeout rather than staying pending forever. Actual refusing and never-answering
  HTTP servers both returned Not usable on the next open after 3 seconds:
  3.036839 s and 3.030863 s respectively. Snapshot latency during a check was
  0.027872 / 0.000287 / 0.000227 s. The prior 36-second symptom was not
  reproduced locally; the pending-state deadline explicitly prevents it.
- R7 PASS: rendered production Settings markup and stylesheet in a same-origin
  1440×900 browser iframe. Changed only the nine status texts and button presence
  to cover the state matrix, then measured getBoundingClientRect. None/In use
  rows are 45 px; only the long writing failure is 48.59375 px. All Choose/Clear
  pairs have identical top coordinates (0 px vertical separation).
- R8 PASS: ready writing slot makes Local engine → Rewrite say “Your writing
  model” and hides the contradictory default-engine unavailable note. Node
  executes actual Settings markup for checking and ready states.
- R9 PASS: 286 tests pass in 36.18 s, 5 existing TorchScript warnings; JavaScript
  syntax passes. VERSION remains 17.

| Slot | None height px | In use height px | Not usable height px |
|---|---:|---:|---:|
| Transcription | 45 | 45 | 45 |
| Writing | 45 | 45 | 48.59375 |
| Voice | 45 | 45 | 45 |

Layout change: Settings uses one column when the new model rows are present,
with a nonwrapping label and action group plus a wrapping status column.
What got worse: Settings is taller and requires more vertical scrolling.
Pending status can report a timeout before a very slow/trickling server finally
finishes; that worker can subsequently update the cached result.
Not tested: founder's app window, native build, inference, or smaller viewport
layout. Browser measurement used real DOM/CSS with state fixtures, not nine
independent live API configurations. No new captures required or saved.
