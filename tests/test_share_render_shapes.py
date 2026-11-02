"""C3: the old review-link lookup knows every render shape."""

import app
import render


def test_every_non_vertical_shape_has_a_file_token():
    for aspect in render.ASPECTS:
        if aspect == "9:16":
            continue
        assert f"_{aspect.replace(':', 'x')}" in app._OTHER_SHAPE_TOKENS, aspect


def test_a_916_lookup_never_picks_a_1610_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "JOBS", tmp_path)
    job = {"id": "j1", "renders": {
        "wide": {"status": "ready", "path": "reel_30_16x10.mp4", "updated": 2.0},
        "tall": {"status": "ready", "path": "reel_30.mp4", "updated": 1.0},
    }}
    assert app._find_share_render(job, 30, "9:16")["path"] == "reel_30.mp4"
    assert app._find_share_render(job, 30, "16:10")["path"] == "reel_30_16x10.mp4"
