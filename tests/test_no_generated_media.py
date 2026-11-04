"""No test makes its own audio or video, and a missing file is never silent."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import real_media

TESTS = Path(__file__).resolve().parent
GENERATORS = re.compile(
    r"lavfi|sine=|aevalsrc|anoisesrc|anullsrc=|testsrc|color=c=|writeframes"
    r"|wave\.open\([^)]*[\"']wb?[\"']\)|\[\s*\"?say\"?\s*,"
)


def test_no_test_generates_audio_or_video():
    found = []
    for path in sorted([*TESTS.rglob("*.py"), *TESTS.rglob("*.mjs")]):
        if path.name == Path(__file__).name:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if GENERATORS.search(line):
                found.append(f"{path.relative_to(TESTS)}:{number}: {line.strip()}")
    assert not found, "Use real_media instead:\n" + "\n".join(found)


def test_a_missing_file_skips_and_names_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(real_media, "MEDIA", tmp_path)
    with pytest.raises(pytest.skip.Exception, match=r"data/media/speech\.wav") as caught:
        real_media.clip("speech.wav", tmp_path / "out.wav", 1.0)
    assert real_media.waiting_on(str(caught.value)) == ["speech.wav"]
    assert not (tmp_path / "out.wav").exists()
    real_media.asked.clear()


def test_the_list_for_the_founder_names_every_file():
    listed = (TESTS.parent / "docs" / "testing" / "real-media.md").read_text(encoding="utf-8")
    for name in real_media.CATALOG:
        assert f"`{name}`" in listed, name
