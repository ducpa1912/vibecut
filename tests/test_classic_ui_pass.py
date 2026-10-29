"""The Classic UI pass keeps the primary actions visible and the text legible."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page() -> str:
    return (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_the_player_and_download_come_before_the_edit_form():
    html = page()
    assert html.index('id="player-wrap"') < html.index('id="audio-panel"')
    assert 'id="result-ready"' in html
    assert 'id="result-ready-download"' in html
    assert 'id="audio-panel" class="audio-panel edit-panel">' in html
    assert "dom.resultReady.hidden = true" in script()
    assert "dom.resultReady.hidden = false" in script()


def test_result_title_is_a_hook_line_with_the_filename_in_the_meta():
    js = script()
    assert "function resultHeading()" in js
    assert "updateResultHeading()" in js
    assert "dom.resultMeta.textContent = `${fileStem(job.source.name)}" in js
    assert "dom.resultTitle.title = state.job.source.name" in js
    assert "-webkit-line-clamp: 2;" in css()


def test_recent_cuts_group_sources_and_open_a_full_list():
    js = script()
    html = page()
    assert "function groupRecent(jobs)" in js
    assert "function recentLabel(name)" in js
    assert "recentGroupOpened(group)" in js
    assert "Opened ${printRecentTime(opened)}" in js
    assert "rest.slice(0, 5)" in js
    assert 'id="recent-all"' in html
    assert 'id="recent-all-panel"' in html
    assert "data-delete-id" in js


def test_audio_modes_are_a_segmented_control_with_a_description():
    html = page()
    for label in ("Original", "New voice-over", "Dub voice", "Music only", "New voice + music"):
        assert f">{label}</button>" in html
    assert 'id="audio-mode-desc"' in html
    assert "AUDIO_MODE_META" in script()
    assert "min-height: 44px;" in css()


def test_copy_is_a_one_line_note_outside_voice_modes():
    assert 'id="audio-copy-note"' in page()
    assert 'id="audio-copy-switch"' in page()
    assert "dom.audioCopyForm.hidden = !rewriteMode" in script()
    assert "dom.audioCopyNote.hidden = rewriteMode" in script()


def test_moments_and_roles_are_readable_and_explained():
    html = page()
    assert 'id="clip-menu"' in html
    assert "Change role" in script()
    assert ".moment-check {" in css()
    assert "width: 32px;" in css()
    assert "font-size: 11px; }" in css()
    assert "--payoff: #d9d7cf;" in css()
    assert "border-style: dashed;" in css()
    assert 'class="moments-legend"' in html


def test_activity_is_one_count_and_one_latest_event():
    html = page()
    js = script()
    assert 'id="history-latest"' in html
    assert "history-title" in html and ">Activity<" in html
    assert '`${entries.length} event${entries.length === 1 ? "" : "s"}`' in js
    assert "dom.historyLatest.textContent" in js
    assert "max-height: 320px;" in css()


def test_dim_text_is_raised_in_classic_and_creator():
    assert "--dim: #9a999f;" in css()
    assert "--dim: #9a999f;" in (ROOT / "static" / "classic" / "creator.css").read_text(encoding="utf-8")
