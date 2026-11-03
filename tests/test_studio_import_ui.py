"""Studio Import: one file drop plus one link-or-path field.

The source tabs were removed because File, Path and Link compete for the same
job. The read options are always visible instead of hiding behind a summary.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT = (ROOT / "static" / "studio" / "import.js").read_text(encoding="utf-8")


def test_one_location_field_handles_links_and_paths():
    assert 'id="st-location-input"' in IMPORT
    assert "Or use a link or full path" in IMPORT
    assert "/^https?:\\/\\//i.test(value) ? \"url\" : \"path\"" in IMPORT
    assert "st-tab-path" not in IMPORT
    assert "st-url-input" not in IMPORT
    assert "st-path-input" not in IMPORT


def test_read_options_are_always_visible():
    assert '<section class="st-options-panel"' in IMPORT
    assert "What to read" in IMPORT
    assert "<details" not in IMPORT
    assert "<summary>" not in IMPORT


def test_file_choice_and_location_choice_clear_each_other():
    assert "dom.locationInput.value = \"\";" in IMPORT
    assert "selectedFile = null;" in IMPORT
    assert "dom.fileCard.hidden = true;" in IMPORT
