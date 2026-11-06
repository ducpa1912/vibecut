"""Classic has a narrow-screen layout, not only a desktop one."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_page_declares_a_mobile_viewport():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in page
    assert "width=device-width" in page


def test_narrow_breakpoints_exist_and_stack_the_actions():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 480px)" in css
    assert "@media (pointer: coarse)" in css
    block = css[css.index("@media (max-width: 680px)"):]
    block = block[:block.index("@media (max-width: 480px)")]
    for rule in (
        ".topbar {",
        "flex-wrap: wrap;",
        ".action-row,",
        ".result-actions {",
        ".creator-tabs { flex-wrap: nowrap;",
        ".setup-panel { width: calc(100vw - 16px)",
        ".audio-grid { grid-template-columns: 1fr; }",
    ):
        assert rule in block, rule


def test_small_phones_drop_the_low_priority_chrome():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    block = css[css.index("@media (max-width: 480px)"):]
    block = block[:block.index("@media (pointer: coarse)")]
    assert ".local-pill," in block
    assert ".health { display: none; }" in block
    assert ".recent-grid { grid-template-columns: 1fr; }" in block


def test_the_dropdown_never_wider_than_the_screen():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "Math.min(Math.max(rect.width, 240), window.innerWidth - 24)" in script
    assert "Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))" in script


def test_the_moments_gallery_sits_before_the_smart_cut():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert page.index('id="moments-section"') < page.index('class="export-panel smart-cut-panel"')


def test_a_finished_render_scrolls_the_player_into_view_once():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "const revealPlayer = state.renderWasActive === true && !active;" in script
    assert 'scrollIntoViewSafe(dom.playerWrap, { behavior: "smooth", block: "center" })' in script


def test_mobile_result_actions_use_three_columns():
    css = (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")
    marker = "grid-template-columns: repeat(3, minmax(0, 1fr));"
    found = css.index(marker)
    start = css.rindex("@media (max-width: 680px)", 0, found)
    block = css[start:css.index("@media (max-width: 480px)", start)]
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in block
    assert ".result-actions .primary," in block
    assert ".result-actions .ghost { width: 100%; min-height: 44px;" in block
