"""Phase 4: Cut Clean focus mode wiring.

These are source checks: the browser spec drives the screen, while this file
proves the page carries one Edit | Clean switch, one scan entry, one primary
cut-clean action, cut-time rows and the job overflow that keeps work-file
cleanup away from text removal.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page() -> str:
    return (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def styles() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def i18n() -> str:
    return (ROOT / "static" / "classic" / "i18n.js").read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    assert start in text, start
    body = text[text.index(start):]
    assert end in body, end
    return body[:body.index(end)]


def top_actions(html: str) -> str:
    return between(html, '<div class="result-actions">', '<div class="editor-pane editor-pane-preview">')


def test_the_result_top_bar_reads_finish_help_mode_then_overflow():
    html = page()
    actions = top_actions(html)
    assert actions.index('id="finish-cut"') < actions.index('id="shortcuts-open"')
    assert actions.index('id="shortcuts-open"') < actions.index('id="result-mode"')
    assert actions.index('id="result-mode"') < actions.index('id="job-menu-wrap"')
    assert ">Edit</button>" in actions
    assert ">Clean</button>" in actions
    assert 'data-result-mode="edit"' in actions
    assert 'data-result-mode="clean"' in actions
    assert 'id="job-menu-open"' in actions
    assert 'aria-expanded="false"' in actions
    assert 'id="job-menu"' in actions


def test_work_file_cleanup_is_renamed_and_lives_in_the_overflow():
    html = page()
    assert '>Clean work files…</button>' in html
    assert 'id="clean-profile"' in html
    menu = between(html, 'id="job-menu"', "</div>")
    assert 'id="clean-profile"' in menu
    assert 'id="clean-job"' in menu
    assert 'id="delete-job"' in menu
    # No top-level button that could be mistaken for text removal.
    actions = top_actions(html)
    assert '<button id="clean-job" class="ghost">Clean</button>' not in actions
    assert '<button id="delete-job" class="ghost danger">Delete</button>' not in actions
    script_text = script()
    assert 'dom.cleanJob.textContent = "Clean work files…";' in script_text
    assert "function bindJobMenu()" in script_text
    assert 'dom.jobMenuOpen.setAttribute("aria-expanded", on ? "true" : "false")' in script_text


def test_source_clean_has_no_edit_clean_switch():
    css = styles()
    assert "body.source-mode .result-actions { display: none !important; }" in css
    assert "body.source-mode #clean-scan { display: none !important; }" in css
    js = script()
    assert "if (dom.resultMode) dom.resultMode.hidden = Boolean(on);" in js
    assert 'dom.sourceBack?.addEventListener("click", resetToIngest);' in js


def test_clean_is_a_focus_mode_not_a_removal():
    css = styles()
    for rule in (
        "body.cut-clean-mode .editor-pane-timeline { display: none !important; }",
        "body.cut-clean-mode .editor-pane-settings > *:not(#clean-panel) { display: none !important; }",
        "body.cut-clean-mode .hook-panel,",
        "body.cut-clean-mode .player-wrap,",
        "body.cut-clean-mode .result-ready,",
    ):
        assert rule in css
    js = script()
    assert 'document.body.classList.toggle("cut-clean-mode", enabled);' in js
    assert "function setResultMode(mode)" in js
    assert "function applyCleanMode(on)" in js
    assert "state.resultMode = enabled ? \"clean\" : \"edit\";" in js
    assert ">Clean again</button>" in page()


def test_one_scan_entry_replaces_the_text_scan_card():
    html = page()
    assert 'id="text-scan"' not in html
    assert 'id="text-scan-start"' not in html
    assert html.count('id="clean-scan-start"') == 1
    assert html.count('id="clean-scan-status"') == 1
    assert html.count('id="clean-scan-cancel"') == 1
    js = script()
    assert "if (!jobId || !dom.textScanStatus) return;" in js
    assert "if (!dom.textScanStart) return;" in js
    assert "paintTextScan();" in js
    assert 'getElementById("text-scan")' not in js


def test_cut_clean_has_one_primary_action_and_no_second_renderer():
    js = script()
    run = between(js, "async function runCutClean(options = {})", "async function cancelCutClean()")
    assert "await startTextScan(true);" in run
    assert "ensureCutFoundTicks();" in run
    assert "await persistClassicText(classicPlanClips());" in run
    assert 'await startRender("final");' in run
    assert 'state.cutCleanPhase = "Finding text";' in run
    assert 'state.cutCleanPhase = "Cleaning";' in run
    assert 'state.cutCleanPhase = "Rendering";' in run
    assert "/render/render" not in run
    assert "duration >= 180" not in run
    assert "SOURCE_CONFIDENCE_MIN" in js
    assert "cleanRowCutStart(row) !== null" in js
    assert 'label = `Clean ${ticked} text${ticked === 1 ? "" : "s"} & render`;' in js
    assert 'label = "Find text & clean";' in js
    assert '"No baked-in text found. Nothing was rendered."' in js
    assert 'label = "Render cut";' in js
    assert 'dom.cutCleanRun.textContent = label ? tr(label) : "";' in js
    assert "cancelCutClean" in js
    assert "await cancelTextScan();" in js
    assert "await cancelRender();" in js
    assert "function cleanAgainCut()" in js


def test_cut_rows_show_cut_time_and_outside_rows_do_not_move():
    js = script()
    rows = between(js, "function cleanRowCutStart(row)", "function cleanRowTimeLabel(row)")
    assert "if (row.manual) return row.ranges.length ? row.ranges[0].start : 0;" in rows
    assert "const mapped = cleanCutRanges(row.ranges);" in rows
    assert "return mapped.length ? mapped[0].start : null;" in rows
    assert "if (state.cleanScope === \"source\" || row.manual) return row.ranges || [];" in rows
    assert "return cleanCutRanges(row.ranges);" in rows
    assert "Not in this cut" in js
    focus = between(js, "function focusCleanRow(row)", "function resetSourceConfirmation()")
    outside = focus.index("if (cutStart === null)")
    move = focus.index("state.classicText.t = Math.max(0, cutStart - 0.5);")
    assert outside < move
    assert "Not in this cut. Add the moment to Smart Cut first." in focus
    assert "cleanRowTimeLabel(row)" in js


def test_before_sends_no_clean_layers_and_after_sends_the_layers():
    js = script()
    frame = between(js, "async function refreshCleanFrame(force = false)", "function cleanCropHeader(response)")
    assert "const sideMode = sourceScope || cutCleanActive();" in frame
    assert "cleanFrameBody(sideMode && side === \"before\" ? [] : activeClean)" in frame
    assert "const key = sideMode ? `${cleanFrameKey(body)}|${side}` : cleanFrameKey(body);" in frame
    assert "if (side === \"after\" && activeFill.length)" in frame
    before = between(js, 'dom.cleanPreviewBefore?.addEventListener("click"', 'dom.cleanPreviewAfter?.addEventListener("click"')
    after = between(js, 'dom.cleanPreviewAfter?.addEventListener("click"', "dom.cleanPreviewPlay?.addEventListener")
    assert 'state.classicText.previewSide = "before";' in before
    assert "scheduleCleanFrame(true);" in before
    assert 'state.classicText.previewSide = "after";' in after
    assert "scheduleCleanFrame(true);" in after


def test_hidden_and_visible_applied_rows_use_the_right_words():
    js = script()
    assert 'aria-label="${row.hidden ? "Excluded" : "Already cleaned"}: ${esc(row.text)}"' in js
    assert '${row.hidden ? "Excluded" : "Already cleaned"}' in js
    assert 'checked disabled aria-label=' in js


def test_one_primary_per_screen_and_no_nested_cards_in_the_rail():
    css = styles()
    assert "body.cut-clean-mode .clean-found-actions [data-found-apply] { display: none !important; }" in css
    assert "body.cut-clean-mode .clean-found," in css
    assert "border-radius: 0;" in css
    assert "font-size: 11px;" in css
    js = script()
    assert 'dom.cutCleanRun.hidden = ready;' in js
    assert "if (dom.cutCleanResultActions) dom.cutCleanResultActions.hidden = !(ready || stale || failed);" in js
    assert 'dom.cutCleanDownload.href = withToken(record.url);' in js


def test_model_missing_keeps_blur_and_names_the_reason():
    js = script()
    assert "function cutCleanEngineLabel()" in js
    assert '"Blur · AI fill unavailable"' in js
    assert "state.fill?.engines?.lama?.reason || state.fill?.note || \"\"" in js
    assert "if (method === \"fill\" && !fillEngineReady()) method = \"blur\";" in js


def test_the_job_overflow_is_a_plain_tab_popover():
    html = page()
    menu = between(html, 'id="job-menu"', "</div>")
    assert 'role="menu"' not in menu
    assert 'role="menuitem"' not in menu
    assert 'id="clean-profile"' in menu
    js = script()
    assert "function setJobMenu(open, options = {})" in js
    assert "const restoreFocus = Boolean(options.restoreFocus);" in js
    assert "setJobMenu(false, { restoreFocus: true });" in js
    menu_js = between(js, "function bindJobMenu()", "function bindChrome()")
    outside = between(menu_js, "document.addEventListener(\"mousedown\"", "document.addEventListener(\"keydown\"")
    assert "setJobMenu(false);" in outside
    assert "restoreFocus" not in outside
    assert "if (dom.result && !dom.result.hidden) dom.jobMenuOpen.focus();" in menu_js


def test_cut_clean_stale_render_keeps_the_file_but_not_the_result():
    js = script()
    assert "function renderStaleFor(record)" in js
    assert "const staleState = recordReady ? renderStaleFor(record)" in js
    assert "const stale = Boolean(recordReady && staleState.stale);" in js
    assert "const ready = Boolean(recordReady && !stale);" in js
    assert "Changed since this render. The older file is still available; render again to update it." in js
    assert 'label = `Clean ${cleanCount} text${cleanCount === 1 ? "" : "s"} & render again`;' in js
    assert 'const downloadLabel = tr(stale ? "Download older file" : "Download");' in js
    assert "Download older file" in js
    assert "dom.cutCleanAgain.hidden = stale;" in js
    action = between(js, "async function cutCleanPrimaryAction()", "async function verifySourceCleanMedia(record)")
    assert "const staleRecord = record?.status === \"ready\" && renderStaleFor(record).stale;" in action
    assert "const staleNeedsReview = staleRecord && review.needsReview && review.applied === 0;" in action
    assert action.index("if (staleRecord && !staleNeedsReview)") < action.index('if (state.textScan?.status === "ready" && review.needsReview')
    css = styles()
    assert "body.cut-clean-mode #render-stale" not in css
    assert "body.cut-clean-mode .speech-notice { display: none !important; }" in css


def test_review_label_and_action_share_one_predicate():
    js = script()
    assert "function cutCleanReviewState(rows, ticks)" in js
    assert "needsReview: available.length > 0 && ticked === 0 && applied === 0" in js
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "const review = cutCleanReviewState(rows, ticks);" in paint
    assert "} else if (needsReview && applied === 0 && !failed) {" in paint
    assert "const staleNeedsReview = stale && needsReview && applied === 0;" in paint
    assert "} else if (stale && !staleNeedsReview && cleanCount) {" in paint
    action = between(js, "async function cutCleanPrimaryAction()", "async function verifySourceCleanMedia(record)")
    assert "const review = cutCleanReviewState(rows, state.classicText.foundTicks);" in action
    assert "review.needsReview" in action
    assert "review.applied === 0 && !failedRecord" in action
    assert "Review the low-confidence rows." in action
    assert "Review the found text. Tick the rows to remove" in action
    # A drawn layer does not count as an applied scan layer.
    assert 'classicCleanLayers().filter((layer) => layer.source === "scan").length' in js


def test_clean_stashes_and_restores_edit_draw_mode():
    js = script()
    assert "if (!wasClean) state.editDrawMode = state.classicText.drawMode;" in js
    assert 'state.classicText.drawMode = false;' in js
    assert "state.classicText.drawMode = Boolean(state.editDrawMode);" in js
    assert "editDrawMode: false," in js


def test_the_type_floor_covers_the_cut_clean_chrome():
    css = styles()
    for selector in (".stage-kicker {", ".clean-box-tag {", "\n.clean-file-state {"):
        start = css.index(selector) + (1 if selector.startswith("\n") else 0)
        block = css[start:css.index("}", start)]
        assert "font-size: 11px;" in block, selector


def test_no_baseline_keeps_the_record_current_and_uses_its_own_copy():
    js = script()
    assert 'if (!baseline) return { stale: false, noBaseline: true };' in js
    assert "const noBaseline = Boolean(recordReady && staleState.noBaseline);" in js
    assert 'summary += ` · ${tr("No render baseline on this browser. Render again to confirm this cut matches.")}`;' in js
    assert "dom.renderStale.textContent = tr(\"No render baseline on this browser. Render again to confirm this cut matches.\");" in js


def test_run_notices_survive_a_ready_record_and_reach_clean_status():
    js = script()
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "setCutCleanNote" in paint
    assert 'else if (recordReady) state.cutCleanNote = "";' not in paint
    run = between(js, "async function runCutClean(options = {})", "async function cancelCutClean()")
    assert "function setCutCleanNote(message)" in js
    assert 'setCutCleanNote("Cleaning stopped before render. Nothing was rendered.");' in run
    assert 'setCutCleanNote("No box was added. Check the fill engine or tick a text row again.");' in run
    assert 'setCutCleanNote("Render did not start. Check the render note in Edit.");' in run
    assert "setCleanStatus(state.cutCleanNote);" in js


def test_failed_render_keeps_clean_again_and_applied_wins_over_review():
    js = script()
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "if (dom.cutCleanResultActions) dom.cutCleanResultActions.hidden = !(ready || stale || failed);" in paint
    assert "dom.cutCleanAgain.hidden = stale;" in paint
    assert "cleanCount = ticked || applied || review.available.length;" in paint
    assert "} else if (needsReview && applied === 0 && !failed) {" in paint
    assert "const staleNeedsReview = stale && needsReview && applied === 0;" in paint
    assert "} else if (stale && !staleNeedsReview && cleanCount) {" in paint
    assert "} else if (applied) {" in paint
    assert "} else if (failed) {" in paint


def test_review_browser_fixture_uses_all_high_confidence_rows():
    spec = (ROOT / "tests" / "browser" / "classic_cut_clean.spec.mjs").read_text(encoding="utf-8")
    assert "const HIGH_SCAN" in spec
    assert "confidence: 0.9" in spec
    assert "allHighScan = true;" in spec
    assert 'document.querySelectorAll("#clean-found .clean-found-row").length === 4' in spec
    assert 'page.locator("#clean-found [data-found-none]").click()' in spec
    assert "const B1_SCAN" in spec
    assert "b1Scan = true;" in spec
    assert "Clean 4 texts & render" in spec
    assert "Review 1 low-confidence" in spec


def test_ticked_high_rows_render_even_when_a_low_row_is_unticked():
    js = script()
    review = between(js, "function cutCleanReviewState(rows, ticks)", "function setCutCleanNote(message)")
    assert "const low = available.filter((row) => (" in review
    assert "needsReview: available.length > 0 && ticked === 0 && applied === 0" in review
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    ticked = paint.index("} else if (ticked) {")
    needs = paint.index("} else if (needsReview && applied === 0 && !failed) {")
    assert ticked < needs
    assert 'label = `Clean ${ticked} text${ticked === 1 ? "" : "s"} & render`;' in paint
    assert 'label = review.low' in paint
    assert '`Review ${review.low} low-confidence`' in paint
    assert '`Review ${review.available.length} text${review.available.length === 1 ? "" : "s"}`' in paint
    action = between(js, "async function cutCleanPrimaryAction()", "async function verifySourceCleanMedia(record)")
    assert 'const reviewRow = review.low' in action
    assert 'querySelector(".clean-found-row.is-low")' in action


def test_clean_ranges_merge_before_signature_and_save():
    js = script()
    helper = between(js, "function mergeCleanRanges(ranges)", "function cleanPayloadLayers()")
    assert "Math.round(start * 1000) / 1000" in helper
    assert "item.start <= last.end + 1e-6" in helper
    payload = between(js, "function cleanPayloadLayers()", "function cleanCutTotal()")
    assert "ranges: mergeCleanRanges(layer.ranges || [])" in payload
    record = between(js, "function cutCleanRenderRecord()", "function ensureCutFoundTicks()")
    assert 'const existing = findRender("final");' in record
    assert 'if (existing?.status === "ready") return existing;' in record


def test_cancel_waits_for_an_active_record():
    js = script()
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "dom.cutCleanCancel.hidden = !(scanActive" in paint
    assert 'state.cutCleanPhase === "Cleaning"' in paint
    assert "|| renderActive);" in paint
    assert 'state.cutCleanPhase === "Rendering"\n        || renderActive' not in paint


def test_clean_fill_paths_wrap_in_the_rail():
    css = styles()
    assert ".clean-file-name { font-family: var(--mono); font-size: 11px; min-width: 0; overflow-wrap: anywhere; word-break: break-word; }" in css
    assert ".clean-file-meta { color: var(--dim); min-width: 0; overflow-wrap: anywhere; word-break: break-word; }" in css
    locked = between(css, "\n.clean-fill-locked {", "}")
    assert "min-width: 0;" in locked
    assert "overflow-wrap: anywhere;" in locked
    assert "word-break: break-word;" in locked
    assert ".clean-fill-locked > div { min-width: 0; }" in css
    assert ".clean-fill-locked p," in css
    state = between(css, "\n.clean-file-state {", "}")
    assert "min-width: 0;" in state
    assert "overflow-wrap: anywhere;" in state


def test_edit_focus_and_settings_scroll_are_captured_and_restored():
    js = script()
    assert "state.editFocusElement = active;" in js
    assert "state.editSettingsScroll = pane.scrollTop;" in js
    assert "function editSettingsPane()" in js
    assert "target.focus({ preventScroll: true });" in js
    assert "pane.scrollTop = scrollTop;" in js
    assert "Edit restored. The previous control is no longer available, so focus is on Edit." in js
    assert 'document.addEventListener("focusin", (event) => {' in js
    assert 'state.editFocusElement = element;' in js
    assert 'dom.resultModeClean?.addEventListener("pointerdown", captureEditFocus);' in js
    assert "if (clean) captureEditFocus();" in js


def test_new_and_reloaded_clean_layers_share_the_server_defaults():
    js = script()
    assert 'const CLEAN_DEFAULT_COLOR = "#0b0d12";' in js
    assert "const CLEAN_DEFAULT_OPACITY = 1;" in js
    assert "const CLEAN_DEFAULT_RADIUS = 24;" in js
    box = between(js, "function addCleanBox(options = {})", "function deleteCleanBox(id)")
    assert "color: options.color || CLEAN_DEFAULT_COLOR," in box
    assert "opacity: Number.isFinite(Number(options.opacity)) ? Number(options.opacity) : CLEAN_DEFAULT_OPACITY," in box
    assert "radius: Number.isFinite(Number(options.radius)) ? Number(options.radius) : CLEAN_DEFAULT_RADIUS," in box
    payload = between(js, "function cleanPayloadLayers()", "function cleanCutTotal()")
    assert "color: layer.color || CLEAN_DEFAULT_COLOR," in payload
    assert "opacity: Number.isFinite(Number(layer.opacity)) ? Number(layer.opacity) : CLEAN_DEFAULT_OPACITY," in payload
    assert "radius: Number.isFinite(Number(layer.radius)) ? Number(layer.radius) : CLEAN_DEFAULT_RADIUS," in payload


def test_review_label_names_low_rows_and_focuses_one():
    js = script()
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "? `Review ${review.low} low-confidence`" in paint
    assert '`Review ${review.available.length} text${review.available.length === 1 ? "" : "s"}`' in paint
    action = between(js, "async function cutCleanPrimaryAction()", "async function verifySourceCleanMedia(record)")
    assert "const reviewRow = review.low" in action
    assert 'querySelector(".clean-found-row.is-low")' in action


def test_target_change_retriggers_the_cut_auto_tick_after_clean_data_loads():
    js = script()
    plan = between(js, "async function refreshPlan()", "function setSort(sort)")
    assert "renderPlan();" in plan
    render = between(js, "function renderPlan()", "function clipWidth(clip)")
    assert "state.classicText.pendingTickReset = cutKey;" in render
    assert "cutKey !== state.classicText.loadedKey" in render
    apply = between(js, "function applyClassicTextCut(cut, key = \"\")", "async function refreshClassicText(force = false)")
    assert "state.classicText.pendingTickReset === key" in apply
    assert "state.classicText.foundTicks = new Set();" in apply
    assert "state.classicText.foundTicksInit = false;" in apply
    assert 'if (resetTicks && state.textScan?.status === "ready") ensureCutFoundTicks();' in apply
    stored = between(js, "function applyStoredFoundTicks(rows, options = {})", "function fillEngineReady()")
    assert "if (Number(row.confidence) < SOURCE_CONFIDENCE_MIN) continue;" in stored
    assert "return cleanRowCutStart(row) !== null;" in stored


def test_cut_clean_preview_readout_is_cut_time():
    js = script()
    meta = between(js, "function updateCleanPreviewMeta()", "// The stage frame is the real render")
    assert '? `Source ${fmtTime(cleanSourceTimeAt(t), 2)}`' in meta
    assert ': `Cut ${fmtTime(t, 2)}`;' in meta


def test_edit_type_floor_covers_moment_scan_and_text_time():
    css = styles()
    moment = between(css, "\n.moment-scan {", "}")
    assert "font-size: 11px;" in moment
    text_time = between(css, "\n.text-time span {", "}")
    assert "font-size: 11px;" in text_time
    small = [
        line.strip() for line in css.splitlines()
        if line.strip().startswith("font-size:") and line.strip() in {
            "font-size: 8px;", "font-size: 9px;", "font-size: 10px;",
        }
    ]
    assert not small, small


def test_clean_ticks_use_stable_identities_and_storage():
    js = script()
    identity = between(js, "function cleanRowIdentity(row)", "function tickHash(value)")
    assert 'return `manual:${row.layer_id || String(row.key || "").replace(/^manual:/, "")}`;' in identity
    assert "if (row.tracklet_id) return `tracklet:${row.tracklet_id}`;" in identity
    assert 'return `text:${text}|${rect}`;' in identity
    assert "Math.round(number * 10000) / 10000" in js
    store = between(js, "function cleanTickStorageKey(report = state.textScan?.report)", "function fillEngineReady()")
    assert "classic-clean-ticks:${state.job.id}:${state.cleanScope}:${cutKey}:${tickHash(textScanReportKey(report))}" in store
    assert "function saveFoundTicks()" in store
    assert "function clearStoredFoundTicks(key = state.classicText.tickStoreKey)" in store
    assert "function applyStoredFoundTicks(rows, options = {})" in store
    assert "if (seen.has(identity)) continue;" in store
    paint = between(js, "function renderCleanFound()", "function addCleanFromScan(entry, method, engine)")
    assert "const identity = cleanRowIdentity(row);" in paint
    assert "ticks.has(identity)" in paint
    assert 'data-found-tick="${esc(identity)}"' in paint
    apply = between(js, "function applyFoundTicks()", "function renderCleanLayers()")
    assert "const byIdentity = new Map(rows.map((row) => [cleanRowIdentity(row), row]));" in apply
    assert ".map((identity) => byIdentity.get(identity))" in apply
    handler = between(js, 'dom.cleanFound?.addEventListener("change"', "dom.cleanFound?.addEventListener(\"keydown\"")
    assert "const identity = tick.dataset.foundTick || \"\";" in handler
    assert "state.classicText.foundTicks.add(identity);" in handler
    assert "saveFoundTicks();" in handler
    assert "clearStoredFoundTicks();" in js


def test_new_report_clears_storage_but_ordinary_refresh_keeps_it():
    js = script()
    refresh = between(js, "async function refreshTextScan()", "async function startTextScan(runAgain = false)")
    assert "previousKey !== textScanReportKey(next.report)" in refresh
    assert "clearStoredFoundTicks();" in refresh
    start = between(js, "async function startTextScan(runAgain = false)", "async function cancelTextScan()")
    assert "clearStoredFoundTicks();" in start
    assert 'if (next.status === "ready" && state.cleanScope === "cut") ensureCutFoundTicks();' in start


def test_source_ticks_use_the_same_identity_helpers():
    js = script()
    source = between(js, "function ensureSourceFoundTicks()", "async function estimateSourceClean")
    assert "applyStoredFoundTicks(cleanScanRows(), { source: true });" in source
    run = between(js, "async function runSourceCleanSteps(options = {})", "function sourceCleanErrorText(error)")
    assert "const tickedRows = tickedRowsFor(rows, state.classicText.foundTicks, { source: true });" in run
    assert "tickedRows.map((row) => rows.indexOf(row))" in run


def test_empty_confirmed_report_is_render_only_from_paint_and_action():
    js = script()
    assert "function cutCleanEmptyConfirmed(rows)" in js
    assert "function cutCleanNoInsideFound(rows)" in js
    assert "cutCleanReportReady() && cutCleanFoundRows(rows).length === 0" in js
    paint = between(js, "function paintCutClean()", "async function runCutClean(options = {})")
    assert "const emptyConfirmed = cutCleanEmptyConfirmed(rows);" in paint
    assert '} else if (emptyConfirmed) {\n      label = "Render cut";' in paint
    assert paint.index('} else if (ready) {\n        summary = `Clean cut ready') < paint.index('} else if (emptyConfirmed) {\n        summary = "No baked-in text found.')
    assert paint.index('if (stale) {\n        summary = "Changed since this render.') < paint.index('} else if (emptyConfirmed) {\n        summary = "No baked-in text found.')
    action = between(js, "async function cutCleanPrimaryAction()", "async function verifySourceCleanMedia(record)")
    assert "const emptyConfirmed = cutCleanEmptyConfirmed(rows);" in action
    assert "if (emptyConfirmed) {" in action
    assert action.index("if (emptyConfirmed) {") < action.index("review.needsReview")
    assert "cutCleanNotFound" not in js


def test_empty_clean_again_renders_instead_of_returning():
    js = script()
    again = between(js, "async function cleanAgainCut()", "async function cutCleanPrimaryAction()")
    assert "const emptyConfirmed = cutCleanEmptyConfirmed(rows);" in again
    assert "await runCutClean({ renderOnly: true });" in again
    assert "No baked-in text found. Re-rendering with the existing Clean boxes." in again
    assert "No baked-in text found. Rendering the cut without Clean boxes." in again


def test_vietnamese_carries_the_new_copy():
    vi = i18n()
    for english, vietnamese in (
        ("Clean work files…", "Dọn tệp làm việc…"),
        ("Delete job…", "Xóa job…"),
        ("Job actions", "Thao tác job"),
        ("Render cut", "Render bản cắt"),
        ("Not in this cut", "Không có trong bản cắt này"),
        ("Already cleaned", "Đã làm sạch"),
        ("Excluded", "Đã loại trừ"),
        ("Rendering", "Đang render"),
        ("Download older file", "Tải tệp cũ"),
    ):
        assert f'"{english}": "{vietnamese}"' in vi
    assert '"This file is older than the current Clean changes."' in vi
    # The work-file wording no longer steals the Clean mode's translation.
    assert '"Clean": "Dọn dẹp"' not in vi
    assert '"Clean": "Làm sạch"' in vi
    assert "/^Clean (\\d+) texts? & render$/" in vi
    assert "/^Review (\\d+) low-confidence$/" in vi
