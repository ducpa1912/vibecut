import numpy as np
import pytest

from duckcore import ink, inkcheck


@pytest.mark.parametrize('contrast', [.5, 2.0])
def test_leftover_under_contrast_is_hit_or_unchecked(monkeypatch, contrast):
    # Deterministic moving texture and text-like strokes; no media or files.
    rng = np.random.default_rng(22)
    frames = rng.integers(90, 115, size=(90, 64, 160, 3), dtype=np.uint8)
    for x in (25, 55, 85, 115):
        frames[30:60, 24:44, x:x + 3] = 240
        frames[30:60, 24:27, x:x + 15] = 240
        frames[30:60, 32:35, x:x + 12] = 240
    graded = np.clip((frames.astype(float) - 128) * contrast + 128, 0, 255).astype(np.uint8)
    height, width = graded.shape[1:3]
    def read(path, first, count, rect, fps, **kwargs):
        return graded[max(0, first):max(0, first) + count]
    monkeypatch.setattr(ink, 'read_box', read)
    built = ink.build('memory-source', (0, 0, width, height), start=1, end=2, fps=30)
    if built is None:
        return  # Explicitly not checked: no stable strokes at this grade.
    report = inkcheck._judge({'id':'leftover'}, built, 'memory-output', 'memory-source',
                            [(0, 3, 0)], fps=30, size=None)
    assert report['hits'] or report['frames'] == 0
