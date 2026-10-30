"""A ready render reveals the player once, and mobile keeps the cut order.

The player scroll fires on the transition from an active render to a ready
one, keyed by the render record so repeated panel updates do not repeat it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page() -> str:
    return (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_the_player_scrolls_only_on_the_ready_transition():
    js = script()
    assert "const revealPlayer = state.renderWasActive === true && !active;" in js
    assert "state.renderWasActive = !!active;" in js
    start = js.index("function updateRenderPanel()")
    block = js[start:js.index("function renderAudioNote", start)]
    assert "state.playerScrollKey !== record.key" in block
    assert "state.playerScrollKey = record.key;" in block


def test_the_ready_scroll_still_targets_the_player():
    js = script()
    assert 'dom.playerWrap.scrollIntoView({ behavior: "smooth", block: "center" })' in js


def test_a_new_render_clears_the_scroll_key():
    js = script()
    for name in ("async function startRender(quality", "async function startRenderAll()", "async function abHooks()"):
        start = js.index(name)
        block = js[start:start + 1200]
        assert "state.playerScrollKey = null;" in block


def test_a_new_job_resets_the_scroll_and_render_transition():
    js = script()
    start = js.index("function prepareResult(job)")
    block = js[start:js.index("dom.momentsFull.hidden = true", start)]
    assert "state.playerScrollKey = null;" in block
    assert "state.renderWasActive = null;" in block


def test_moments_sit_before_smart_cut_and_the_player_before_edit():
    html = page()
    assert html.index('id="moments-section"') < html.index('class="export-panel smart-cut-panel"')
    assert html.index('id="player-wrap"') < html.index('id="moments-section"')
    assert html.index('id="moments-section"') < html.index('id="audio-panel"')


def test_mobile_moments_stack_heading_controls_legend_rail():
    sheet = css()
    start = sheet.rindex("@media (max-width: 680px)")
    block = sheet[start:sheet.index("@media (max-width: 480px)", start)]
    assert ".moments-head { flex-direction: column; align-items: stretch; gap: 10px; }" in block
    assert ".scene-tools { flex-direction: row;" in block
    assert ".moments-section { display: flex; flex-direction: column; }" in block
    assert ".moments-rail { order: 3; }" in block
