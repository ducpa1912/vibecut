"""A moment card select adds or removes the beat without opening the drawer.

The card itself opens the scene drawer. The select is a real button inside the
card, so a click or Enter on it only toggles Smart Cut membership. This file
also keeps the drawer's own Add/Remove actions covered.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_the_select_is_a_button_with_a_checkbox_role():
    js = script()
    start = js.index("function momentCheck(scene, checked)")
    block = js[start:js.index("function updateMomentControls", start)]
    assert '<button type="button" class="moment-check' in block
    assert 'role="checkbox"' in block
    assert 'aria-checked="${checked}"' in block
    assert "Add to Smart Cut" in block
    assert "Remove from Smart Cut" in block
    assert "tabindex=\"0\"" not in block


def test_a_moment_card_is_a_div_so_the_select_is_not_nested_in_a_button():
    js = script()
    assert '<button class="moment-card ' not in js
    rail = js[js.index("dom.momentsRail.innerHTML = railScenes.map"):]
    rail = rail[:rail.index("if (dom.momentsFull")]
    assert 'class="moment-card ' in rail
    assert 'role="button" tabindex="0"' in rail
    assert 'data-moment-scene="${scene.id}"' in rail


def test_the_card_select_toggles_before_the_drawer_branch():
    js = script()
    for container in ("dom.momentsRail", "dom.momentsList"):
        start = js.index(f'{container}.addEventListener("click"')
        block = js[start:js.index("});", start)]
        assert "event.stopPropagation();" in block
        assert "toggleMomentSelection(" in block
        assert block.index("toggleMomentSelection(") < block.index("openDrawer(")


def test_a_select_click_keeps_the_rail_position_and_keyboard_focus():
    js = script()
    start = js.index("function toggleMomentSelection(sceneId)")
    block = js[start:js.index("function moveClip", start)]
    assert "dom.momentsRail.scrollLeft = railScroll" in block
    assert "dom.momentsList.scrollTop = listScroll" in block
    assert 'querySelector(`[data-moment-toggle="${sceneId}"]`)' in block
    assert "focus({ preventScroll: true })" in block


def test_a_quick_scan_select_does_not_open_the_drawer():
    js = script()
    start = js.index("function addSceneToPlan(sceneId")
    block = js[start:js.index("function removeSceneFromPlan", start)]
    quick = block[block.index('if (scene.deep === false) {'):]
    quick = quick[:quick.index("}")]
    assert "deep-read this moment" in quick
    assert "openDrawer(" not in quick


def test_enter_or_space_on_the_card_opens_details_but_not_on_the_select():
    js = script()
    start = js.index("const momentKeydown = (event) => {")
    block = js[start:js.index("dom.momentsRail.addEventListener(\"keydown\"", start)]
    assert 'event.key !== "Enter" && event.key !== " "' in block
    assert 'event.target.closest("[data-moment-toggle]")' in block
    assert "event.stopPropagation();" in block
    assert "openDrawer(Number(card.dataset.momentScene));" in block


def test_the_drawer_keeps_add_and_remove_actions():
    js = script()
    assert 'data-add-scene="${scene.id}"' in js
    assert 'data-remove-scene="${scene.id}"' in js
    start = js.index('dom.drawer.addEventListener("click"')
    block = js[start:js.index('document.addEventListener("keydown"', start)]
    assert "addSceneToPlan(Number(add.dataset.addScene))" in block
    assert "removeSceneFromPlan(Number(remove.dataset.removeScene))" in block


def test_the_select_hit_area_is_32_pixels():
    sheet = css()
    blocks = re.findall(r"\.moment-check\s*\{([^}]*)\}", sheet)
    assert blocks
    assert any("width: 32px;" in block and "height: 32px;" in block for block in blocks)
