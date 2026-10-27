"""Burned-in text honours weight and outline and draws colour emoji (QA #12)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import compose_render
import render

HAS_SANS = Path(render.SYSTEM_SANS).is_file() or Path(render.SYSTEM_SANS_STATIC).is_file()
HAS_EMOJI = Path(render.EMOJI_FONT).is_file()
needs_sans = pytest.mark.skipif(not HAS_SANS, reason="macOS system sans is not installed")
needs_emoji = pytest.mark.skipif(not HAS_EMOJI, reason="Apple Color Emoji is not installed")


def _layer(text: str, **style) -> dict:
    return {
        "type": "text", "kind": "hook", "text": text,
        "rect": {"x": 0.05, "y": 0.1, "w": 0.9, "h": 0.12},
        "style": {"size": 72, "color": "#ffffff", "stroke": "none", **style},
        "opacity": 1.0,
    }


def _ink(image: Image.Image) -> int:
    return int((np.asarray(image)[..., 3] > 128).sum())


@needs_sans
def test_weight_changes_the_drawn_stroke_mass():
    light = render._render_text_layer(_layer("Weight test", weight=300), 1080, 1920)
    heavy = render._render_text_layer(_layer("Weight test", weight=800), 1080, 1920)
    assert _ink(heavy) > _ink(light) * 1.3


@needs_emoji
def test_emoji_draws_in_colour_not_as_a_box():
    image = render._render_text_layer(_layer("QA hook 🔥"), 1080, 1920)
    pixels = np.asarray(image).astype(int)
    visible = pixels[..., 3] > 200
    spread = pixels[..., :3].max(axis=2) - pixels[..., :3].min(axis=2)
    # White text has no saturation; a colour emoji does.
    assert int((visible & (spread > 60)).sum()) > 200


@needs_emoji
def test_runs_split_text_emoji_and_wide_scripts():
    fonts = render._text_fonts(64, "sans", 800)
    runs = fonts.runs("Go 🎬 世界")
    assert [text for text, _font in runs][0] == "Go "
    assert any(font is None and "🎬" in text for text, font in runs)
    cjk = next(font for text, font in runs if "世" in text)
    if fonts.fallbacks:
        assert cjk is not fonts.primary or fonts._has_glyph(fonts.primary, "世")
    assert fonts.width("Go 🎬") > fonts.width("Go ")


def test_outline_width_follows_the_style():
    assert render._stroke_px({"stroke_width": 6}, 72, 1920) == 6
    assert render._stroke_px({"stroke_width": 6}, 36, 960) == 3
    assert render._stroke_px({"stroke_width": 0}, 72, 1920) == 0
    assert render._stroke_px({}, 50, 1920) == 4


def test_caption_track_outline_font_and_weight_reach_the_layer():
    style, anchor = compose_render._caption_overlay_style({"style": {
        "font_size": 80, "stroke_width": 6, "stroke_color": "#112233", "font": "sans",
    }})
    assert style["stroke"] == "#112233" and style["stroke_width"] == 6
    assert style["weight"] == 700 and style["font"] == "sans"
    assert anchor == "bottom-center"
    plain, _ = compose_render._caption_overlay_style({"style": {"stroke_width": 0}})
    assert plain["stroke_width"] == 0


@needs_sans
def test_outline_is_drawn_when_set():
    bare = render._render_text_layer(_layer("Outline", weight=700), 1080, 1920)
    outlined = render._render_text_layer(
        _layer("Outline", weight=700, stroke="#000000", stroke_width=8), 1080, 1920,
    )
    assert _ink(outlined) > _ink(bare) * 1.2
