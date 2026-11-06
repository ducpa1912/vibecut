"""Phase 2: Ingest and Source Clean UI wiring.

These are source/DOM wiring checks: the browser suite needs the founder's real
media and a running server, while this file proves the page carries the clean
entry, routes extraction-only jobs away from analysis, and gates the one-action
pipeline on the thresholds the product contract names.
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


def test_ingest_offers_clean_video_as_primary_and_dissect_as_secondary():
    html = page()
    assert '<button id="clean-video" class="primary" disabled>' in html
    assert '<button id="analyze" class="ghost" disabled>' in html
    assert html.index('id="clean-video"') < html.index('id="analyze"')

    js = script()
    assert 'dom.cleanVideo?.addEventListener("click", startCleanVideo);' in js
    assert 'if (dom.cleanVideo) dom.cleanVideo.disabled = disabled;' in js
    upload = between(js, "function uploadFile(", "// ---------------------------------------------------------------- health")
    assert 'form.append("mode", mode);' in upload
    assert 'uploadFile(\n          state.file, options, updateUploadProgress, rights, "clean",' in js
    assert 'path: state.localPath, options, rights, mode: "clean",' in js


def test_extraction_only_jobs_open_source_clean_without_analysis_polling():
    js = script()
    routing = between(js, "async function openJob(id)", "function prepareResult(job)")
    assert 'if (job.status === "source_ready")' in routing
    assert 'job.status === "source_ready" || job.mode === "clean"' not in routing
    assert "await prepareSourceClean(job);" in routing
    assert "startAnalysisPoll(job.id)" not in between(
        routing, 'if (job.status === "source_ready"', "if (job.status === \"ready\")",
    )

    source = between(js, "async function prepareSourceClean(job)", "function prepareResult(job)")
    assert "startAnalysisPoll" not in source
    assert "prepareResult(" not in source
    assert 'state.cleanScope = "source";' in source
    assert "state.plan = sourcePlanForJob(job);" in source


def test_source_plan_clips_and_guarded_scene_access():
    js = script()
    clips = between(js, "function classicPlanClips()", "function classicLayerId(")
    assert 'if (state.cleanScope === "source") return [sourceClipForJob(state.job)];' in clips

    drawer = between(js, "function openDrawer(sceneId)", "async function readScene(")
    assert 'if (state.cleanScope === "source" || !state.job?.analysis?.scenes) return;' in drawer

    scene = between(js, "function sceneById(id)", "function thumbUrl(scene)")
    assert "const scenes = state.job.analysis?.scenes;" in scene
    assert "if (!Array.isArray(scenes)) return null;" in scene


def test_one_action_pipeline_has_the_named_gates():
    js = script()
    assert "const SOURCE_CONFIDENCE_MIN = 0.65;" in js
    assert "Number(row.confidence) < SOURCE_CONFIDENCE_MIN" in js
    assert "report.text && report.text.confirmed === true" in js
    assert "duration >= 180" in js
    assert "/fill/estimate" in js
    assert "/clean/source/render" in js
    assert "/clean/source/cancel" in js
    assert "setTimeout(tick, 700)" in js
    assert 'method: "PUT"' in js
    assert "classicPlanClips(), clean: layers" in js
    assert "cancelling" in js

    run = between(js, "async function runSourceClean(options = {})", "function sourceCleanErrorText(error)")
    assert "await startTextScan(true);" in run
    assert "No baked-in text found" in js
    assert "await persistClassicText(classicPlanClips());" in run
    assert "await startSourceCleanRender();" in run
    assert "if (sourceCleanActive(state.sourceClean) || state.sourceCleanBusy) return;" in run
    assert "state.sourceCleanBusy = true;" in run
    assert "state.sourceCleanPhase = \"Finding text\";" in run
    assert "sourceCleanApplied" not in js
    assert "Phase 3" not in js
    assert "Text was found but is not cleaned yet" in js
    assert "const scannedRows = cleanScanRows().length;" in js
    assert "AI fill needs its model pack. Blur works on the whole video now." in js
    assert 'if (event.target.closest("input, select, button")) return;' in js
    assert "restored?.focus();" in js
    assert "estimating…" in js
    assert "estimate unavailable" in js
    assert "state.sourceCleanPhase = \"Estimating\";\n      paintSourceClean();" in js
    assert "state.sourceCleanPollToken" in js
    assert "state.sourceCleanRunCancelled = true;" in js
    assert "function textScanReportKey(report)" in js
    assert "function leaveSourceTextBeforeCut()" in js
    assert "Scanning the whole video…" in js
    assert "function textScanFromHttp(status, data)" in js
    assert "function cleanThumbStyle(box)" in js
    assert "return `background-size:${size.toFixed(1)}% ${(100 / h).toFixed(1)}%;`" in js
    assert 'if (reported === "cancelled") return { status: "cancelled", report: data };' in js
    assert 'if (reported === "failed") return { status: "failed", report: data };' in js
    assert 'if (reported === "idle" || data?.report === null) return { status: "idle", report: null };' in js
    assert "next = textScanFromHttp(answer.status, answer.data);" in js
    assert "return textScanFromHttp(status, data);" in js
    assert "Back to source clean" in page()
    assert "api(`/api/classic/jobs/${state.job.id}/clean/source/cancel`" in js
    assert "/check/cancel" in js
    assert "Scan cancelled. Nothing was cleaned or rendered. Scan again when ready." in js


def test_source_rows_frame_and_box_cap_are_wired():
    js = script()
    assert "/frame/source" in js
    assert "X-VibeCut-Width" in js
    assert "X-VibeCut-Height" in js
    assert "setSourceAspect" in js
    assert "cleanFrameBody" in js and 'state.cleanScope === "source"' in js
    assert 'const outside = !sourceScope && cutStart === null;' in js
    assert "click a row to jump to the text" in js
    assert "const cap = sourceScope ? 200 : 24;" in js
    assert 'state.cleanScope !== "source" && !classicTextSupported()' in js
    assert "Whole video" in js
    assert "sourceCleanStageFor" in js


def test_source_rail_reuses_the_clean_panel_and_names_every_state():
    html = page()
    assert html.count('id="clean-found"') == 1
    assert html.count('id="clean-layers"') == 1
    assert html.count('id="clean-empty"') == 1
    assert html.count('id="clean-status"') == 1
    assert html.count('id="clean-fill"') == 1

    for marker in (
        'id="source-back"',
        'id="progress-source"',
        'id="source-clean-head"',
        'id="source-clean-action"',
        'id="source-clean-run"',
        'id="source-clean-cancel"',
        'id="source-clean-summary"',
        'id="source-clean-progress"',
        'id="source-clean-stage"',
        'id="source-clean-result"',
        'id="source-clean-download"',
        'id="source-clean-reel"',
        'id="source-clean-again"',
        'id="progress-download"',
        'id="progress-retry"',
    ):
        assert marker in html, marker

    js = script()
    assert "dom.sourceBack?.addEventListener(\"click\", resetToIngest);" in js
    assert "dom.sourceCleanRun?.addEventListener(\"click\", sourceCleanPrimaryAction);" in js
    assert "dom.sourceCleanCancel?.addEventListener(\"click\", cancelSourceCleanRender);" in js
    assert "dom.sourceCleanReel?.addEventListener(\"click\", makeReelFromSource);" in js
    assert "dom.sourceCleanAnalysisBack?.addEventListener(\"click\", backToSourceClean);" in js
    assert "await api(`/api/jobs/${job.id}/analyze`, { method: \"POST\" });" in js
    assert "Analysis started" in js
    assert "function startSourceReelPoll(id)" in js
    assert "setTimeout(tick, 1000)" in js
    assert "if (state.sourceCleanReelStarted) return;" in js
    assert "Source Clean layers added." in js
    assert "Open the cut from Recent cuts" not in js
    assert 'id="source-clean-analysis-back"' in html
    assert "await persistClassicText(classicPlanClips());" in js
    assert "async function prepareResult(job)" in js
    assert "deletedClean: new Map()" in js
    assert "function pendingCleanDeletes(" in js
    assert "function cleanIdentityToken(" in js
    assert "sourceAnalysisStoppedNote" in js
    assert "Already cleaned" in js
    assert "Excluded" in js
    assert "The clean file is missing. Render it again; no Download is offered." in js

    css = styles()
    assert "body.source-mode .result-actions { display: none !important; }" in css
    assert "body.source-mode .editor-pane-timeline { display: none !important; }" in css
    assert "body.source-mode .editor-pane-settings > *:not(#clean-panel)" in css
    assert ".source-clean-action {" in css
    assert "position: sticky;" in css
    assert "@media (min-width: 1100px)" in css
    assert "@media (max-width: 1099px)" in css


def test_vietnamese_dictionary_covers_the_new_ingest_and_source_copy():
    words = i18n()
    for english, vietnamese in (
        ("Clean video", "Làm sạch video"),
        ("Find text & clean", "Tìm chữ & làm sạch"),
        ("Make a reel", "Tạo reel"),
        ("Clean again", "Làm sạch lại"),
        ("Whole video", "Toàn bộ video"),
        ("Finding text", "Đang tìm chữ"),
        ("Source Clean layers added.", "Đã thêm các lớp Làm sạch nguồn."),
        ("Retry analysis", "Thử phân tích lại"),
        ("Analysis was cancelled.", "Phân tích đã bị hủy."),
        ("Analysis was interrupted.", "Phân tích đã bị gián đoạn."),
        ("Analysis stopped before it could build the cut.", "Phân tích đã dừng trước khi dựng được bản cắt."),
        ("Download the source clean file, or retry.", "Tải tệp làm sạch nguồn, hoặc thử lại."),
    ):
        assert f'"{english}": "{vietnamese}"' in words, english
