"""One rule for comparing OCR readings."""

from __future__ import annotations

from duckcore import textmatch


def test_a_single_misread_character_still_matches() -> None:
    assert textmatch.same_text("小馋猫又开始催餐了", "小馋猫叉开始催餐了")


def test_punctuation_and_width_do_not_matter() -> None:
    assert textmatch.same_text("喂！", "喂!")
    assert textmatch.same_text("咪餐 派送中~", "咪餐派送中")


def test_a_partial_read_matches() -> None:
    assert textmatch.same_text("咪餐派送中", "咪餐派送中~")


def test_unrelated_lines_do_not_match() -> None:
    assert not textmatch.same_text("今天吃鱼", "排骨加一")
    assert not textmatch.same_text("", "喂")
    assert not textmatch.same_text("喂", "    ")


def test_compact_keeps_cjk_and_digits() -> None:
    assert textmatch.compact("排骨 + 1") == "排骨1"
    assert textmatch.normalize("  Hello   WORLD ") == "hello world"
