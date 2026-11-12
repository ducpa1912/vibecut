from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from duckcore import edits
from duckcore.main import create_app
from duckcore.render import _scale_filter, cut_size

META = {"width": 1920, "height": 1080}


def test_set_cut_clamps_and_keeps_the_numbers() -> None:
    edit = {"id": "ed_cut"}
    out = edits.set_cut(edit, aspect="9:16", fit="fill", crop={"x": 0.9, "y": -1, "w": 0.5, "h": 2})
    assert out["cut"]["aspect"] == "9:16"
    assert out["cut"]["fit"] == "fill"
    assert out["cut"]["crop"] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}


def test_set_cut_rejects_a_bad_aspect_or_fit() -> None:
    for kwargs in ({"aspect": "21:9"}, {"fit": "stretch"}):
        try:
            edits.set_cut({"id": "ed_cut"}, **kwargs)
        except edits.EditError:
            pass
        else:  # pragma: no cover
            raise AssertionError(kwargs)


def test_cut_size_and_filters() -> None:
    assert cut_size(META) == (1920, 1080)
    assert cut_size(META, {"cut": {"aspect": "9:16"}}) == (1080, 1920)
    assert cut_size(META, {"cut": {"aspect": "1:1"}}) == (1080, 1080)
    out_w, out_h, chain = _scale_filter(META, 30, {"cut": {"aspect": "9:16", "fit": "fill"}})
    assert (out_w, out_h) == (1080, 1920)
    assert "force_original_aspect_ratio=increase" in chain and "crop=1080:1920" in chain
    _, _, crop_chain = _scale_filter(META, 30, {"cut": {"aspect": "source", "fit": "fit", "crop": {"x": 0.25, "y": 0.1, "w": 0.5, "h": 0.5}}})
    assert crop_chain.startswith("crop=960:540:480:108")


def test_cut_route_saves(tmp_path: Path) -> None:
    edit_dir = tmp_path / "projects" / "prj_cut" / "edits"
    edit_dir.mkdir(parents=True)
    (edit_dir / "ed_cut.json").write_text(json.dumps({"id": "ed_cut", "project_id": "prj_cut"}), encoding="utf-8")
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        saved = client.patch(
            "/api/projects/prj_cut/edits/ed_cut/cut",
            headers={"Authorization": "Bearer test-token"},
            json={"aspect": "4:5", "fit": "fill", "crop": None},
        )
        assert saved.status_code == 200
        assert saved.json()["edit"]["cut"] == {
            "aspect": "4:5", "fit": "fill", "crop": None,
            "grade": {"exposure": 0, "contrast": 0, "saturation": 0, "temperature": 0},
            "enhance": {"enabled": False, "sharpen": 0},
        }
        bad = client.patch(
            "/api/projects/prj_cut/edits/ed_cut/cut",
            headers={"Authorization": "Bearer test-token"},
            json={"aspect": "21:9", "fit": "fit", "crop": None},
        )
        assert bad.status_code == 400


def test_no_cut_keeps_the_old_source_chain() -> None:
    _, _, chain = _scale_filter(META, 30, None)
    assert chain == (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30"
    )


def test_grade_clamps_and_survives_the_route(tmp_path: Path) -> None:
    edit = {"id": "ed_grade"}
    out = edits.set_cut(edit, grade={"exposure": 250, "contrast": -140, "saturation": 40, "temperature": -20})
    assert out["cut"]["grade"] == {"exposure": 100, "contrast": -100, "saturation": 40, "temperature": -20}
    edit_dir = tmp_path / "projects" / "prj_grade" / "edits"
    edit_dir.mkdir(parents=True)
    (edit_dir / "ed_grade.json").write_text(json.dumps({"id": "ed_grade", "project_id": "prj_grade"}), encoding="utf-8")
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        saved = client.patch(
            "/api/projects/prj_grade/edits/ed_grade/cut",
            headers={"Authorization": "Bearer test-token"},
            json={"aspect": "source", "fit": "fit", "crop": None,
                  "grade": {"exposure": 25, "contrast": 10, "saturation": -10, "temperature": 50}},
        )
        assert saved.status_code == 200
        assert saved.json()["edit"]["cut"]["grade"]["temperature"] == 50


def test_grade_turns_into_ffmpeg_filters() -> None:
    _, _, chain = _scale_filter(META, 30, {"cut": {"grade": {"exposure": 100, "contrast": 50, "saturation": -50, "temperature": 100}}})
    assert "exposure=exposure=2.000" in chain
    assert "eq=contrast=1.500:saturation=0.500" in chain
    assert "colorbalance=rs=0.150:gs=0:bs=-0.150" in chain
    _, _, plain = _scale_filter(META, 30, {"cut": {"grade": {"exposure": 0, "contrast": 0, "saturation": 0, "temperature": 0}}})
    assert "exposure=" not in plain and "colorbalance=" not in plain and "eq=" not in plain


def test_enhance_clamps_and_only_lifts_a_small_source() -> None:
    out = edits.set_cut({"id": "ed_e"}, enhance={"enabled": True, "sharpen": 180})
    assert out["cut"]["enhance"] == {"enabled": True, "sharpen": 100}
    small = {"width": 640, "height": 360}
    _, _, chain = _scale_filter(small, 30, {"cut": {"enhance": {"enabled": True, "sharpen": 50}}})
    assert "flags=lanczos+accurate_rnd" in chain
    assert "unsharp=5:5:0.750:5:5" in chain
    _, _, big = _scale_filter(META, 30, {"cut": {"enhance": {"enabled": True, "sharpen": 50}}})
    assert "lanczos" not in big
    assert "unsharp" not in big
    _, _, off = _scale_filter(small, 30, {"cut": {"enhance": {"enabled": False, "sharpen": 50}}})
    assert "lanczos" not in off and "unsharp" not in off
