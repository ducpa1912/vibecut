"""Layout at 1024x700, 200 % zoom and the Edit frame timecode (REQ-20261115-02 P2).

Loop pc-layout-small measured the reachable screens under headless Chrome with
`scripts/measure-layout.mjs`. Two defects were CSS cascade problems, so they are
pinned here by rule and by rule order:

* below 760 px the absolutely centred workflow tabs sat on top of Import and
  Search, and the (already renamed) engine pill still showed;
* the later two-column `.workspace.render` rule beat the 980 px single-column
  rule, leaving a 146 px queue column at 200 % zoom.

The Edit bar now carries the frame timecode as text, not only as a tooltip.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "duck" / "app.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "duck" / "app.js").read_text(encoding="utf-8")
MEASURE = (ROOT / "scripts" / "measure-layout.mjs").read_text(encoding="utf-8")


def test_edit_bar_draws_the_frame_timecode_as_text() -> None:
    assert "function playerBar({ timecode = false } = {})" in JS
    assert '<span class="player-tc" data-player-tc title="Frame timecode">' in JS
    # Only the Edit bar asks for it: Check, Clean and the modal player keep the
    # layout they had at 1440x900 and 1280x800.
    assert JS.count("playerBar({ timecode: true })") == 1
    assert "const tc = bar.querySelector('[data-player-tc]');" in JS
    assert "tc.textContent = frameTimecode(video.currentTime, fps);" in JS
    assert "state.check?.result?.meta?.fps" in JS


def test_timecode_and_clock_stay_on_one_line() -> None:
    assert ".player-time { font: 11px var(--mono); white-space: nowrap; opacity: .92; flex: 0 0 auto; }" in CSS
    assert ".player-tc {" in CSS
    rule = CSS[CSS.index(".player-tc {"):CSS.index(".player-tc {") + 260]
    assert "flex: 0 0 auto" in rule
    assert "white-space: nowrap" in rule


def test_small_toolbar_override_comes_after_the_centred_tabs_rule() -> None:
    base = CSS.index(".toolbar-tabs {")
    assert "position: absolute" in CSS[base:base + 120]
    override = CSS.rindex(".toolbar-tabs { position: static; transform: none;")
    assert override > base, "the small-size toolbar rule must win the cascade"
    small = CSS[override:]
    assert "flex: 1 0 100%" in small  # the tabs take their own centred row
    assert ".toolbar { height: auto; min-height: 48px; flex-wrap: wrap;" in CSS
    assert ".toolbar-engine { display: none; }" in CSS


def test_render_uses_one_column_below_980_after_the_two_column_rule() -> None:
    two_column = CSS.index(".workspace.render { grid-template-columns: 320px minmax(0, 1fr);")
    single = CSS.index("@media (max-width: 980px) {\n  .workspace.render { grid-template-columns: minmax(0, 1fr); }")
    assert single > two_column, "the single-column rule must come after the two-column one"
    assert ".render-queue-head { flex-wrap: wrap;" in CSS
    assert ".render-queue-head > div { flex: 0 0 auto; }" in CSS


def test_measurement_script_covers_the_small_sizes_and_the_timecode() -> None:
    assert '"1440x900,1280x800,1024x700,512x350"' in MEASURE
    assert '"settings", "welcome"' in MEASURE
    assert '"import",' in MEASURE
    assert "const offscreen = [];" in MEASURE
    assert "const cutLabels = [];" in MEASURE
    assert "const timecode = (() => {" in MEASURE
    assert "probe340: probeAt(340)" in MEASURE
    assert "probe132: probeAt(132)" in MEASURE
    assert "barFits: bar.scrollWidth <= bar.clientWidth + 1" in MEASURE
    assert "@container (max-width: 300px)" in CSS
    assert ".player-volume { display: none; }" in CSS[CSS.index("@container (max-width: 300px)"):]
