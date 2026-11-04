"""Captions feature contract: tracks, styles and cue building."""

from core.contracts import FeatureContract

FEATURE = FeatureContract(
    id="captions",
    version="1.0.0",
    requires_core=">=1.0,<2.0",
    api="CaptionTrack, normalize_style, build_cues, load_track, save_track",
)

from captions import (  # noqa: E402
    CaptionCue,
    CaptionError,
    CaptionStyleError,
    CaptionTrack,
    CaptionValidationError,
    apply_margin,
    build_cues,
    clip_hash,
    load_track,
    normalize_style,
    parse_srt,
    save_track,
    style_hash,
)

__all__ = [
    "CaptionCue", "CaptionError", "CaptionStyleError", "CaptionTrack",
    "CaptionValidationError", "FEATURE", "apply_margin", "build_cues",
    "clip_hash", "load_track", "normalize_style", "parse_srt", "save_track",
    "style_hash",
]
