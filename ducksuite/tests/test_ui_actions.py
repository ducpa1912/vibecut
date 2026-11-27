"""Every control the UI draws has a handler (REQ-20261125-01 follow-up).

The "Write .srt file" switch rendered `data-action="caption-srt"` with no
handler, so it did nothing; the dead-code pass then removed its orphan helper.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "static" / "duck" / "app.js"


def test_every_data_action_is_handled() -> None:
    js = APP.read_text(encoding="utf-8")
    actions = set(re.findall(r'data-action="([\w-]+)"', js))
    assert actions, "no data-action found; the pattern is stale"
    missing = []
    for action in sorted(actions):
        rest = js.replace(f'data-action="{action}"', "")
        if not re.search(r"""['"]%s['"]""" % re.escape(action), rest):
            missing.append(action)
    assert missing == []


def test_the_srt_switch_patches_the_caption_track() -> None:
    js = APP.read_text(encoding="utf-8")
    assert "action === 'caption-srt'" in js
    assert "patchCaptions({ srt: target.checked })" in js
