"""User-supplied translation model wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckcore import nllb


def test_nllb_missing_model_is_actionable(tmp_path: Path) -> None:
    assert nllb.model_dir(tmp_path) is None
    with pytest.raises(ValueError, match="Choose a CTranslate2 model folder"):
        nllb.translate_lines(
            ["Hello"], source="en", target="vi", data_root=tmp_path,
        )


def test_nllb_custom_model_folder_is_used(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "custom-nllb"
    model.mkdir()
    for name in ("model.bin", "config.json", "sentencepiece.bpe.model"):
        (model / name).write_bytes(b"x")
    monkeypatch.setattr(nllb, "_settings", lambda _root: {
        "translation_engine": "custom",
        "translation_model_path": str(model),
    })
    assert nllb.model_dir(tmp_path) == model


def test_nllb_language_codes_cover_targets() -> None:
    assert nllb.LANGUAGE_CODES == {
        "en": "eng_Latn",
        "vi": "vie_Latn",
        "zh": "zho_Hans",
        "ja": "jpn_Jpan",
    }


def test_no_translation_pack_is_offered() -> None:
    """DuckSuite ships and hosts no translation weights; the user supplies them."""
    from duckcore import packs

    assert all(pack["id"] != "translation-nllb" for pack in packs.PACKS)
