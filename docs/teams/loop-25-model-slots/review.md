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
