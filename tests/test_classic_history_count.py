"""History counts events once.

The summary used to say "1 render · 1 event" for the same render. It now says
"1 event" and shows the latest event inline while collapsed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_history_header_counts_events_once():
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert '`${entries.length} event${entries.length === 1 ? "" : "s"}`' in script
    assert "entry.type === \"render\"" in script
    assert "${renders} render" not in script
    assert "attempts`" not in script


def test_history_shows_the_latest_event_while_collapsed():
    page = (ROOT / "static" / "classic" / "index.html").read_text(encoding="utf-8")
    assert 'id="history-latest"' in page
    assert ">Activity <" in page or ">Activity\n" in page or "history-title" in page
    script = (ROOT / "static" / "classic" / "app.js").read_text(encoding="utf-8")
    assert "dom.historyLatest.textContent" in script
    assert "historyEventLabel(latest)" in script
