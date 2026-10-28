"""Phase B 1c: the "Your videos" library pages with Load more."""

from __future__ import annotations

from pathlib import Path

from test_r3_t2_library import add_artifact, library, make_job  # noqa: F401
from test_r3_t2_library_static import STUDIO, needs_node, run_module


def test_artifacts_say_when_more_rows_wait(library):
    job = make_job(library.jobs, "job1", stories={f"s{index}": f"Story {index}" for index in range(5)})
    for index in range(5):
        add_artifact(job, story_id=f"s{index}", aspect="9:16", created=float(index + 1))
    first = library.get("/api/artifacts?limit=2").json()
    assert first["has_more"] is True and len(first["artifacts"]) == 2
    middle = library.get("/api/artifacts?limit=2&offset=2").json()
    assert middle["has_more"] is True
    last = library.get("/api/artifacts?limit=2&offset=4").json()
    assert last["has_more"] is False and len(last["artifacts"]) == 1
    seen = [row["artifact_id"] for page in (first, middle, last) for row in page["artifacts"]]
    assert len(set(seen)) == 5


@needs_node
def test_next_offset_and_label():
    out = run_module("library.js", """
        return [
          m.nextOffset({total: 130, offset: 0, has_more: true}, 60),
          m.nextOffset({total: 130, offset: 120, has_more: false}, 130),
          m.nextOffset({total: 45, offset: 30}, 45),
          m.nextOffset({total: 45, offset: 0}, 30),
          m.nextOffset({}, 30),
          m.moreLabel(130, 60),
          m.moreLabel(10, 10),
          m.PAGE_SIZE,
          m.SOURCES_PAGE_SIZE,
        ];
    """)
    assert out == [60, None, None, 30, None, "Load more (70 more)", "Load more", 60, 30]


def test_both_tabs_page_with_load_more():
    text = (STUDIO / "library.js").read_text(encoding="utf-8")
    assert "artifactsPath({ query, limit: PAGE_SIZE, offset })" in text
    assert "listJobs({ query, limit: SOURCES_PAGE_SIZE, offset })" in text
    assert text.count("moreButton(data, offset +") == 2
    assert "st-library-more" in text
