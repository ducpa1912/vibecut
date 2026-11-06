"""Moments looks like a collage at both sizes and keeps its labels legible.

Expanded view is a scrolling grid of cards, the collapsed rail keeps a score
chip, the count is one compact line, and the payoff role is neutral dashed
rather than a second bright accent.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page() -> str:
    return (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_the_expanded_list_is_a_scrolling_collage():
    sheet = css()
    start = sheet.index(".moments-list {")
    block = sheet[start:sheet.index("}", start)]
    assert "display: grid;" in block
    assert "repeat(auto-fill, minmax(132px, 1fr))" in block
    assert "max-height: 430px;" in block
    assert "overflow-y: auto;" in block


def test_the_collapsed_rail_keeps_a_score_chip():
    js = script()
    start = js.index("dom.momentsRail.innerHTML = railScenes.map")
    block = js[start:js.index("if (dom.momentsFull", start)]
    assert 'class="moment-score">${Math.round(scene.hook)}' in block
    sheet = css()
    assert ".moment-card .moment-score {" in sheet
    assert "background: rgba(0, 0, 0, 0.62);" in sheet


def test_the_count_is_one_compact_line_and_show_all_has_the_total():
    js = script()
    start = js.index("function updateMomentControls")
    block = js[start:js.index("function setMomentsExpanded", start)]
    assert '`${total} moment${total === 1 ? "" : "s"} · ${order}`' in block
    assert '`Show all ${total}`' in block
    assert "deep" not in block
    assert "showing" not in block


def test_the_legend_names_hook_and_payoff():
    html = page()
    start = html.index('class="moments-legend"')
    block = html[start:html.index("</div>", start)]
    assert ">HOOK</span>" in block
    assert ">PAYOFF</span>" in block
    assert "legend-hook" in block
    assert "legend-payoff" in block


def test_moment_times_are_twelve_pixels_and_have_a_chip():
    sheet = css()
    start = sheet.index(".moment-card .moment-time {")
    block = sheet[start:sheet.index("}", start)]
    size = re.search(r"font-size:\s*([0-9.]+)px", block)
    assert size and float(size.group(1)) >= 12, block
    assert "background: rgba(0, 0, 0, 0.66);" in block
    assert "color: #fff;" in block


def test_the_payoff_border_is_neutral_and_dashed():
    sheet = css()
    assert ":root { --payoff: #d9d7cf; }" in sheet
    block = sheet[sheet.index(".scene-card.is-payoff,"):]
    block = block[:block.index("}", block.index(".moment-row.is-payoff"))]
    assert "border-color: var(--payoff);" in block
    assert "border-style: dashed;" in block
    assert "box-shadow: none;" in block
    assert "#b8ff6a" not in block


def test_the_select_stays_32_pixels_at_every_width():
    sheet = css()
    assert ".moment-check {" in sheet
    assert "width: 32px;" in sheet
    assert '@media (pointer: coarse)' in sheet
    coarse = sheet[sheet.index("@media (pointer: coarse)"):]
    assert ".moment-check { width: 32px; height: 32px; }" in coarse


def test_mobile_puts_heading_then_legend_then_rail_in_order():
    sheet = css()
    marker = ".moments-section { display: flex; flex-direction: column; }"
    found = sheet.index(marker)
    start = sheet.rindex("@media (max-width: 680px)", 0, found)
    block = sheet[start:sheet.index("@media (max-width: 480px)", start)]
    assert ".moments-section { display: flex; flex-direction: column; }" in block
    assert ".moments-head { order: 1; }" in block
    assert ".moments-legend { order: 2; }" in block
    assert ".moments-rail { order: 3; }" in block
    assert ".moments-full { order: 4; }" in block
