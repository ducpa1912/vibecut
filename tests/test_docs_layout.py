"""Lane documentation lives in its own folder and no old plan remains."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_each_lane_has_its_own_documentation_folder():
    assert (DOCS / "classic" / "plan.md").is_file()
    assert (DOCS / "classic" / "design" / "embedded-studio.md").is_file()
    assert (DOCS / "classic" / "testing").is_dir()
    assert (DOCS / "studio" / "handoff").is_dir()
    assert (DOCS / "studio" / "testing").is_dir()
    assert (DOCS / "voice-room" / "testing").is_dir()
    assert (DOCS / "shared" / "branching.md").is_file()
    assert (DOCS / "shared" / "platform-capabilities.md").is_file()
    assert (DOCS / "shared" / "vi-glossary.md").is_file()


def test_the_old_plan_and_flat_testing_folder_are_gone():
    assert not (DOCS / "classic-plan.md").exists()
    assert not (DOCS / "handoff").exists()
    assert not (DOCS / "testing").exists()


def test_the_docs_index_links_to_each_lane():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    assert "classic/plan.md" in index
    assert "classic/design/embedded-studio.md" in index
    assert "studio/handoff/" in index
    assert "voice-room/testing/" in index
    assert "shared/platform-capabilities.md" in index
    assert "shared/vi-glossary.md" in index
