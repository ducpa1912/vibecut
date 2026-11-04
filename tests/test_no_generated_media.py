"""Tests read the founder's real files. They never make video, sound or pictures."""

from __future__ import annotations

import re
from pathlib import Path

import real_media

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

FORBIDDEN = re.compile(
    r'"lavfi"|aevalsrc|anoisesrc|testsrc|writeframes|VideoWriter|imwrite'
    r'|wave\.open\([^)]*"wb"\)|Image\.(new|fromarray)\([^\n]*\.save\('
    r'|\["say", |sf\.write'
)


def test_no_test_generates_media():
    offenders = []
    for path in sorted(TESTS.rglob("*")):
        if path.suffix not in {".py", ".mjs", ".js"} or path == Path(__file__):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == [], "Use tests/real_media.py instead:\n" + "\n".join(offenders)


def test_every_needed_file_is_listed_for_the_founder():
    doc = (ROOT / "docs" / "classic" / "testing" / "real-media.md").read_text(encoding="utf-8")
    for stem in real_media.NEEDS:
        assert f"`{stem}`" in doc, stem


def test_a_missing_file_names_itself_and_never_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(real_media, "MEDIA_DIR", tmp_path)
    try:
        real_media.real_file("music")
    except BaseException as error:  # pytest.skip raises outside Exception
        assert "REAL MEDIA NEEDED: data/media/music.*" in str(error)
    else:
        raise AssertionError("a missing file must not pass")
