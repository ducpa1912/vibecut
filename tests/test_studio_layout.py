"""Studio shell layout rules that keep the main pane scrollable (QA #2)."""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "static" / "studio" / "studio.css"


def _top_level_rule(selector: str) -> dict[str, str]:
    """Declarations of the first top-level ``selector { … }`` block."""
    text = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif depth == 0 and text.startswith(selector, index):
            rest = text[index + len(selector):].lstrip()
            if rest.startswith("{"):
                body = rest[1:rest.index("}")]
                return {
                    key.strip(): value.strip()
                    for key, _, value in (
                        part.partition(":") for part in body.split(";") if ":" in part
                    )
                }
        index += 1
    raise AssertionError(f"{selector} not found at top level")


def test_shell_grid_row_is_bounded_at_every_width():
    rule = _top_level_rule(".st-shell")
    assert rule.get("grid-template-rows") == "minmax(0, 1fr)"
    assert rule.get("overflow") == "hidden"


def test_main_wrap_can_shrink_so_main_scrolls():
    wrap = _top_level_rule(".st-main-wrap")
    assert wrap.get("min-height") == "0"
    assert wrap.get("overflow") == "hidden"
    main = _top_level_rule(".st-main")
    assert main.get("overflow-y") == "auto"
    assert main.get("min-height") == "0"
