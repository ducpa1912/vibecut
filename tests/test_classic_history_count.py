"""History counts renders, not every worker row.

One Rewrite writes a script, a translation and a rewrite row. Calling all of
them "attempts" made one render look like eight tries.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_history_header_counts_renders_and_events():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert 'entry.type === "render"' in script
    assert '`${renders} render${renders === 1 ? "" : "s"} · ${entries.length} event${entries.length === 1 ? "" : "s"}`' in script
    assert "attempts`" not in script
