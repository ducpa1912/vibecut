"""Hook / Beat / Payoff roles reorder the cut and travel with the render.

The menu opens from the role label on left click and from the clip on
right-click. Choosing a role moves the clip and normalizes the array to
Hook > Beat > Payoff. The render request sends that exact clip list in that
order, not a story-arc reorder of it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def script() -> str:
    return (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")


def css() -> str:
    return (ROOT / "static" / "classic" / "style.css").read_text(encoding="utf-8")


def test_the_role_menu_is_hook_then_beat_then_payoff():
    js = script()
    assert 'const CLIP_ROLES = ["hook", "beat", "payoff"];' in js
    start = js.index("function openClipMenu")
    block = js[start:js.index("function closeClipMenu", start)]
    assert "CLIP_ROLES.map((role)" in block
    assert 'role="menuitemradio"' in block
    assert 'aria-checked="${role === current}"' in block
    assert "Change role" in block


def test_the_role_label_opens_the_menu_on_click_and_the_clip_on_right_click():
    js = script()
    click = js[js.index('dom.timeline.addEventListener("click"'):]
    click = click[:click.index('dom.timeline.addEventListener("dragstart"')]
    assert 'event.target.closest("[data-role-index]")' in click
    assert "openClipMenu(Number(role.dataset.roleIndex)" in click
    assert "rect.left, rect.bottom + 6, role" in click

    context = js[js.index('dom.timeline.addEventListener("contextmenu"'):]
    context = context[:context.index('dom.clipMenu.addEventListener("keydown"')]
    assert "event.preventDefault();" in context
    assert "openClipMenu(" in context
    assert 'clip.querySelector("[data-role-index]")' in context


def test_the_role_control_advertises_the_menu_and_a_caret():
    js = script()
    assert 'class="clip-role" data-role-index="${index}" aria-haspopup="menu" aria-controls="clip-menu"' in js
    assert 'aria-expanded="false"' in js
    sheet = css()
    assert '.clip-role::after { content: " ▾";' in sheet
    assert ".clip-role {" in sheet
    assert "border: 0;" in sheet[sheet.index(".clip-role {"):sheet.index(".clip-role::after")]


def test_escape_closes_the_menu_and_enter_or_space_selects():
    js = script()
    start = js.index('dom.clipMenu.addEventListener("keydown"')
    block = js[start:js.index('dom.timeline.addEventListener("click"', start)]
    assert 'event.key === "Escape"' in block
    assert "closeClipMenu({ restoreFocus: true })" in block
    assert 'event.key === "Enter" || event.key === " "' in block
    assert "event.stopPropagation();" in block
    assert 'event.key === "ArrowDown"' in block
    assert 'event.key === "ArrowUp"' in block


def test_a_payoff_demoted_to_beat_does_not_stay_last():
    js = script()
    start = js.index("function setClipRole(index, role)")
    block = js[start:js.index("function normalizePlanRoles", start)]
    assert 'role === "beat" && clips.length <= 2' in block
    assert "two-moment cut needs a hook and a payoff" in block
    assert "clips.length - 2" in block
    assert "clips.unshift(clip)" in block
    assert "clips.push(clip)" in block
    assert "normalizePlanRoles(clips);" in block


def test_normalization_keeps_one_hook_first_and_one_payoff_last():
    js = script()
    start = js.index("function normalizePlanRoles(clips)")
    block = js[start:js.index("function planClipsForRender", start)]
    assert 'index === 0 ? "hook"' in block
    assert 'index === clips.length - 1 ? "payoff"' in block
    assert 'clip.role =' in block


def test_the_render_payload_keeps_the_custom_clip_order_and_roles():
    js = script()
    assert "function planClipsForRender()" in js
    plan = js[js.index("function planClipsForRender()"):]
    plan = plan[:plan.index("function addSceneToPlan", plan.index("function planClipsForRender()"))]
    assert "state.plan.clips.map((clip) => ({ ...clip }))" in plan
    assert "normalizePlanRoles(clips);" in plan

    request_start = js.index("function renderRequestFor(")
    request = js[request_start:js.index("function renderSignatureOf", request_start)]
    assert "const clips = state.edited && state.plan ? planClipsForRender() : null;" in request
    assert 'order: clips ? "source" : state.order,' in request
    assert "hook_scene: clips ? clips[0]?.scene ?? null : state.overrideHook," in request
    assert "      clips," in request

    start = js.index("async function startRender(quality")
    block = js[start:js.index("async function startRenderAll", start)]
    assert "const body = renderRequestFor(target, quality);" in block
    assert "JSON.stringify({ ...body, force, request_sig: requestSig })" in block


def test_render_all_and_ab_use_the_edited_order():
    js = script()
    all_start = js.index("async function startRenderAll()")
    all_block = js[all_start:js.index("async function cancelRender", all_start)]
    assert 'const body = renderRequestFor(target, "final");' in all_block
    assert 'const body = renderRequestFor(state.target, "final");' in all_block
    assert "clips: null," in all_block

    ab_start = js.index("async function abHooks()")
    ab_block = js[ab_start:js.index("async function loadAudioEngines", ab_start)]
    assert "clipsForHook(hook.scene)" in ab_block
    assert 'order: "source",' in ab_block


def test_the_role_menu_head_and_checked_item_are_styled():
    sheet = css()
    assert ".clip-menu-head {" in sheet
    assert '.clip-menu button[role="menuitemradio"]::before' in sheet
    assert '.clip-menu button[aria-checked="true"]::before { content: "✓"; }' in sheet
