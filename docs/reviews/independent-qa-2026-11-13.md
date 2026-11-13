# Independent QA — 2026-11-13

## Follow-up: isolated interactive QA and synthetic renders

**Updated verdict: not ready for sign-off.** Total findings are now **P0 0 · P1 0 · P2 11 · P3 2**: the nine findings below plus four new P2 findings in this follow-up. The earlier static-only limitations below apply to the first review, not to this follow-up.

### Environment and actual workflow

- Started the current Python core and the actual web UI in a separate Chrome profile with a fresh temporary data root. The packaged WKWebView shell was **not** launched: its normal data root can resume queued jobs, and the founder project remains off-limits. Chrome is not a substitute for macOS WKWebView, VoiceOver, native picker, or real-device acceptance.
- Generated a 3-second 320×180, 24 fps `ffmpeg testsrc2` video with a 440 Hz audio track. Imported it into isolated project `prj_067a174ad383`, ran Check to completion, opened Edit, changed a detected layer to Blur, generated a proof, and rendered through the UI. Check found one scene and nine text tracklets. The fixture includes a timestamp and frame numbers; these detections must **not** be called false positives without further ground truth.
- Render 1, Blur: completed in 2.5 s; `ffprobe` reported H.264 1920×1080, 24 fps, AAC, 3.021322 s. The queue reported 0 checked frames and 1 unchecked line.
- Changed Cut to 1:1 Fill, changed that layer to Fill, and rendered again. Render 2 completed in 15.7 s; `ffprobe` reported H.264 1080×1080, 24 fps, AAC, 3.021322 s. The queue reported 0 checked frames and 1 unchecked line. A third, warm render completed in 1.2 s and also reported 1080×1080 at 24 fps. These are synthetic observations, not general speed measurements or fill-quality sign-off.
- Viewed the Render screen at browser viewport sizes 1024×700 and 1440×900. Both had document width equal to viewport width and no buttons with detected text overflow. Visually inspected the 1024×700 screenshot. This is not a full layout or accessibility audit.
- The temporary root, screenshots, source and render outputs are under `/private/var/folders/m_/jn7hsp456dvff8hrf0lmtgqm0000gn/T/opencode/duck-qa-isolated/`. They are synthetic artifacts, not committed evidence. No founder-project Check, render, or write occurred.

### New P2 — Finished-render Play opens the latest render, not the selected job

**Location:** `static/duck/app.js:3759`, `static/duck/app.js:4703`, `duckcore/main.py:1858`.

**Impact:** Older finished cards can play a different output. A user reviewing versions can approve the wrong render. If the newest job is not done, an older completed job can instead fail to play.

**Evidence:** The first isolated job produced 1920×1080; subsequent jobs produced 1080×1080. Clicking the oldest finished Play control opened a video whose `loadedmetadata` dimensions were **1080×1080**. The control passes only project and edit IDs, and the endpoint resolves the latest job for that edit rather than the selected queue job.

**Suggested fix:** Pass a queue job ID through the card and a job-specific authenticated media endpoint; verify ownership and file containment. Test multiple outputs for one edit, including when the latest job is running or failed.

### New P2 — Frame-rate selector does not control output

**Location:** `static/duck/app.js:3710`, `duckcore/render.py:940`.

**Impact:** A user selecting 30 fps from a 24 fps source receives 24 fps without an error; the control then silently resets.

**Evidence:** In the live isolated UI, selected `30 fps` and clicked Start render. The control reverted to `24 fps` after queue refresh. `ffprobe` on the resulting file returned `r_frame_rate=24/1`. The selector has no other `render-fps` handler, and the renderer chooses 24 or 30 from source fps.

**Suggested fix:** Persist a validated frame-rate setting and pass it into render, preview and check timing; or remove the selector and clearly show the automatic output rate.

### New P2 — Render settings show source-aspect size instead of Cut output

**Location:** `static/duck/app.js:1249`, `static/duck/app.js:3676`.

**Impact:** Render settings tell users the wrong resolution when they select a non-source aspect.

**Evidence:** After the live Cut was saved as `1:1`, Render settings displayed **1920 × 1080** for the 320×180 source. Both square outputs were independently measured by `ffprobe` as **1080×1080**. `outputSizeLabel` uses only source dimensions while `cutOutputSize` separately models Cut.

**Suggested fix:** Use the Cut-aware output-size calculation in Render settings, including even dimensions, and cover every aspect and source orientation.

### New P2 — All-unchecked leftover report is hidden

**Location:** `static/duck/app.js:3686`, `static/duck/app.js:3700`.

**Impact:** When no frames can be checked, Render displays “No check yet” and omits the unchecked-line count even after the check ran. The user cannot see that the completed render contains unverified lines.

**Evidence:** Each of the three completed synthetic jobs reported `checked_frames: 0` and `check_unchecked: 1` in `/api/queue`, while the live Render panel displayed **Leftover: No check yet**. The selector requires a truthy `checked_frames` before it will display any report.

**Suggested fix:** Represent whether a check ran independently of its checked-frame count; display zero checked and the unchecked count/reasons, including check failure states.

### Earlier findings: follow-up evidence

- **Stale proof:** reproduced interactively. Generated a blur proof, selected 1:1 Cut, then returned to Clean. The image was still marked “After · blur proof” and its data URL was byte-for-byte identical to the pre-Cut proof. This confirms the client invalidation defect; it does not independently establish the separate server source-key collision.
- **Queue focus loss:** reproduced in the isolated Render screen. Focused the Show button while a job was updating. Seven seconds later `document.activeElement` was `BODY` and the original button was disconnected.
- **Duplicate enqueue:** reproduced deterministically using two threads, two SQLite connections, a temporary separate queue database, and a barrier immediately after both lookups. The real `RenderQueue.enqueue` returned two distinct IDs and left **2 queued rows** for the same project/edit. The barrier forces the race; it does not estimate its frequency in normal use.
- The prior crop-origin and estimate-key probes remain valid; no rendered-pixel crop-edge comparison or end-to-end timing-cache measurement was performed in this follow-up.

### Remaining limits

No packaged-app, native import picker, real project, Vietnamese transcription, microphone, VoiceOver, physical keyboard, long video, source replacement, multi-core endurance, or every-frame OCR acceptance test was performed. The fill render's one unchecked layer prevents claiming text-removal quality. The test suite was not rerun in this follow-up; the first review's **214 passed** result remains historical. No code, test, configuration, or other document was edited.

## Verdict

**Not ready for sign-off.** The automated suite passes, but code inspection and small, read-only probes found correctness and recovery defects. No full render, app interaction, product change, or founder-project access was performed. This is a targeted review, not an exhaustive audit of every requested file or commit.

Severity: **P0 0 · P1 0 · P2 7 · P3 2**. P2 includes user-visible wrong output, misleading proof or estimate, and concurrency/recovery defects. Evidence marked static has not been reproduced in the running app.

## Findings

### P2 — Cut changes leave old proofs visible

**Location:** `static/duck/app.js:1757`, `static/duck/app.js:4216`, `static/duck/app.js:4227`.

**Impact:** After proving a scene, changing crop, aspect, fit, grade, or enhancement can leave the previous data-URL proof displayed as the current result. Users can approve a frame that no longer represents their Cut.

**Evidence:** Static trace: `saveCut` increments `cleanVersion` and renders but does not clear `previewCache`; proofs are cached by scene ID as data URLs, and non-forced proof runs skip cached scenes. The server's Cut-aware key is not consulted for an already cached data URL. Introduced by Cut work in `2739a58`; additional Cut fields were added in `4cda799` and `464cbac`.

**Suggested fix:** Invalidate affected proofs and cancel in-flight proof requests when Cut changes; alternatively key the client cache by the full proof inputs and reject stale responses.

### P2 — Crop coordinates at zero are shifted two pixels

**Location:** `duckcore/render.py:157`, `duckcore/render.py:178`.

**Impact:** Crops starting at the top or left edge silently exclude two source pixels and include pixels beyond the requested region. The output and displayed crop can disagree, especially for fine framing and edge text.

**Evidence:** Read-only Python probe: `_picture_plan({'width':1920,'height':1080,'fps':30}, {'cut':{'crop':{'x':0,'y':0,'w':0.5,'h':0.5}}})['parts'][0]` returned `crop=960:540:2:2`. `_even` enforces a minimum of two for coordinates as well as sizes. The Cut code arrived in `2739a58`.

**Suggested fix:** Round offsets to even values with minimum zero, separately from positive dimensions; test all four boundaries and compare preview with render.

### P2 — Estimate work cache collides for changed manual layers

**Location:** `duckcore/engine/textfill/__init__.py:389`, `duckcore/render.py:849`.

**Impact:** Changing a box, brush mask, track, or fill plan can reuse a previous span's work units. This can misstate render time even though the outer estimate key changes. The shared store can also collide between projects where IDs and other included fields match.

**Evidence:** Read-only Python probe returned `True` for equality of `units_key` for layers with the same ID and time range but boxes `{x:0,y:0,w:.1,h:.1}` and `{x:.5,y:.5,w:.4,h:.4}`. The key includes neither box nor mask, track, fill plan, source identity, method, or device; `estimate_span` accepts the cached value as `units_override`. This affects the recent estimate changes in `5272a82`.

**Suggested fix:** Key units by all inputs used by the dry planner, including source, geometry, plan, method and device, or cache a demonstrably device-independent normalized measure with explicit versioning.

### P2 — Enqueue deduplication is not atomic

**Location:** `duckcore/render.py:1481`.

**Impact:** Simultaneous requests or two cores can both see no active job for the same edit and insert separate queued jobs. The atomic claim at `duckcore/render.py:1619` prevents two workers claiming the *same row*, not duplicate rows. This can render the same edit twice and contradict the one-job claim.

**Evidence:** Static SQL trace: the `SELECT` precedes the `INSERT` without `BEGIN IMMEDIATE` or a uniqueness constraint. Python sqlite's implicit write transaction does not protect that preceding read. Not reproduced with concurrent clients in this review.

**Suggested fix:** Serialize lookup and insertion in one immediate transaction, and add a database-enforced active-job uniqueness invariant if feasible; test concurrent independent connections.

### P2 — Queue updates can remove keyboard focus

**Location:** `static/duck/app.js:486`, `static/duck/app.js:5391`.

**Impact:** On Welcome or Render, a changed queue update replaces the whole screen, removing the focused control while a user is navigating or editing. Render progress can repeatedly disrupt keyboard access.

**Evidence:** Static trace: polling every 2.5 seconds at `static/duck/app.js:5404` calls `refreshQueue`, which calls `render()` whenever queue progress or `updated` changes. `render()` replaces `app.innerHTML` without general focus restoration. No live keyboard or VoiceOver session was permitted.

**Suggested fix:** Update queue nodes in place or preserve and restore focus and relevant input state; test keyboard navigation during progress updates.

### P2 — Failed sidecar handshake can leave a live orphan

**Location:** `mac/DuckSuite/DuckSuite/AppModel.swift:64`, `mac/DuckSuite/DuckSuite/Sidecar.swift:162`.

**Impact:** A slow or malformed handshake throws after starting the core, but the newly created sidecar is stored only after `start()` succeeds. The catch does not stop the process. Retrying can leave another core running against the same data root.

**Evidence:** Static lifecycle trace: `Sidecar.start()` calls `process.run()` before the timeout/JSON checks; `AppModel.start()` assigns `self.sidecar` only after the call returns, and `Sidecar` has no deinitializer calling `stop()`. `AGENTS.md:205` independently describes orphaned processes after handshake trouble. Not reproduced by launching the app.

**Suggested fix:** Stop and reap the process on every handshake failure, including timeout and malformed output; cover retries and shutdown with a controlled helper.

### P2 — Proof cache does not identify the source video

**Location:** `duckcore/main.py:1254`, `duckcore/append.py:577`.

**Impact:** A source replacement or append can reuse a JPEG produced from the prior source when edit ID, active layers, clip scope, Cut and timestamp match. This is most visible when replacement changes frames in an otherwise unchanged span; append normally preserves earlier content but may re-encode it.

**Evidence:** Static trace: the proof hash contains clean layers, clip scope, mode and Cut, but no source fingerprint or file stamp. Append changes the project's source path through `store.update_source` without changing this key. This risk depends on the resulting matching scope and was not verified with a real append.

**Suggested fix:** Include the actual source fingerprint or a reliable source generation ID in the proof key; test a changed source with identical edit and time.

### P3 — Always-on layers are omitted from proof scope

**Location:** `duckcore/main.py:225`, `duckcore/engine/textfill/mask.py:236`.

**Impact:** A layer with no ranges is always active in the fill planner, but `_active_clean` omits it from the proof. Proofs can therefore show uncleaned content where the render applies fill. Normal newly created manual and detected layers have ranges, so impact depends on older or externally supplied edits.

**Evidence:** Read-only Python probe: `_active_clean({'clean':[{'id':'x','kind':'blur','box':{'x':0,'y':0,'w':.2,'h':.2}}]}, 1)` returned `[]`; `layer_windows` explicitly treats absent ranges as always on.

**Suggested fix:** Share one active-window rule across proof, blur and fill, including no-range and boundary cases; test legacy edits.

### P3 — Current product and agent documents contradict shipped behavior and each other

**Location:** `PRODUCT.md:64`, `PRODUCT.md:91`, `PRODUCT.md:121`, `AGENTS.md:181`, `AGENTS.md:213`, `AGENTS.md:231`.

**Impact:** Planning and QA can reject shipped grading, use an obsolete test baseline, or misjudge bundle size and model packaging. `PRODUCT.md` lists grading as both shipped and prohibited; `AGENTS.md` says 117 tests and approximately 377 MB with a 198 MB LaMa, but also describes a 981 MB GPU bundle. `PLAN.md:11` and this run report 214 tests.

**Evidence:** Direct comparison of the cited lines with `duckcore/render.py:209` and test results below. The actual bundle was not measured in this review.

**Suggested fix:** Reconcile current shipped/planned language and update or remove stale measured values after measuring the actual current build.

## Commands and results

Initial `git status --porcelain`: empty. The test command below disables bytecode and pytest's repository cache to preserve the tree; pytest and its synthetic media tests still use temporary files outside the repository. It is otherwise the requested suite.

| Command | Result |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests` | **214 passed, 6 warnings in 25.92s**. Warnings: PyTorch `torch.jit.script`, `save`, and `load` deprecations, two each. |
| `node --check static/duck/app.js` | Exit 0; no output. |
| `node --check scripts/measure-layout.mjs` | Exit 0; no output. |
| `git status --porcelain` before report | Exit 0; no output. Final status is checked separately after report creation. |

No optional Xcode build: `scripts/build-xcode-dev.sh:29` removes and replaces the built app, and earlier steps also write generated build files. That conflicts with read-only scope.

## Scope and limits

- Read the required current documents, the last 20 commit subjects and their file statistics, and targeted code in the requested areas. Reviewed selected changes and invariants, not every line of every listed module, script, test, or commit. No blanket security, queue-race, filter-chain, fill-quality, or accessibility sign-off is implied.
- Checked fill span keys for version, model stamp, device and layer fields; checked the atomic queue-claim path and manual box clearing of track. These observations do not establish correctness under all inputs.
- No app window clicks, real-screen assessment, VoiceOver/keyboard exercise, build, model inference, Check, project write, or real-project render. Automated tests produced short synthetic media in temporary test directories; no full product render was started.
- No access to the founder project. No proof of source-replacement collision, queue race, focus loss, or sidecar timeout in a live app; those findings are explicitly static traces.
- Historical archive documents, HTML reports, and other loops' reviews were not opened under repository instructions. No product code, tests, or configuration were changed.

## Document claims not independently verified

- `PLAN.md:12-18`: bundle size, GPU speed, 2,964 frame checks, cold-render range, and leftover counts.
- `PLAN.md:98-100`: screen measurements and zero-overlap/clipped-button claims.
- `MEMORY.md:26` and `PLAN.md:71-76`: licensing and Apple model/platform research claims.
- `PRODUCT.md:3`: founder's 75% completion estimate; `PRODUCT.md:132`: WCAG 2.2 AA target has not been audited here.
- `MEMORY.md:50-51`: measured estimate accuracy and ink-store behavior under a real workload.
