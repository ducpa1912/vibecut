"""Render hooks: segment filters, motion, layers, frame endpoint and proxy."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app
import audio
import captions
import compose_render
import edits
import pipeline
import render

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")

CLIPS = [
    {"scene": 0, "start": 0.0, "end": 2.0, "dur": 2.0, "role": "hook"},
]
SCENES = [
    {
        "id": 0,
        "start": 0.0,
        "end": 2.0,
        "dur": 2.0,
        "crops": {"9:16": {"cx": 0.5, "cy": 0.5}},
    },
]


def _story_ref() -> dict:
    return {
        "set_id": "cs_1",
        "story_id": "s1",
        "clip_hash": edits.clip_snapshot_hash(CLIPS),
        "title": "Story one",
        "duration": 2.0,
        "clip_count": 1,
    }


def _edit(**overrides) -> dict:
    value = {"story_ref": _story_ref(), "aspect": "9:16", "created": 1.0}
    value.update(overrides)
    return edits.build_edit(**value)


def _compiled(edit: dict, *, size=(540, 960), motion_engine="perspective") -> dict:
    return compose_render.compile_edit(
        edit,
        clips=CLIPS,
        source={"width": 1920, "height": 1080},
        scenes=SCENES,
        size=size,
        motion_engine=motion_engine,
    )


def _plan() -> dict:
    return {"target": 2, "clips": list(CLIPS), "_scenes": list(SCENES)}


# ---------------------------------------------------------------- unit: segment


def test_segment_cache_key_includes_filter_hashes():
    meta = {"fingerprint": "abc", "duration": 10.0, "size": 1000}
    scene = {"crop": {"cx": 0.5, "cy": 0.5}}
    base = render._segment_cache_key(
        meta, scene, 0.0, 60, 540, 960, "draft", "libx264", True, True,
    )
    same = render._segment_cache_key(
        meta, scene, 0.0, 60, 540, 960, "draft", "libx264", True, True,
        pre_filters=["drawbox=x=1:y=2:w=3:h=4:color=0x000000@1.000:t=fill"],
        post_filters=["eq=brightness=0.100:contrast=1.080:saturation=0.950"],
    )
    repeated = render._segment_cache_key(
        meta, scene, 0.0, 60, 540, 960, "draft", "libx264", True, True,
        pre_filters=["drawbox=x=1:y=2:w=3:h=4:color=0x000000@1.000:t=fill"],
        post_filters=["eq=brightness=0.100:contrast=1.080:saturation=0.950"],
    )
    other_pre = render._segment_cache_key(
        meta, scene, 0.0, 60, 540, 960, "draft", "libx264", True, True,
        pre_filters=["drawbox=x=9:y=2:w=3:h=4:color=0x000000@1.000:t=fill"],
        post_filters=["eq=brightness=0.100:contrast=1.080:saturation=0.950"],
    )
    other_post = render._segment_cache_key(
        meta, scene, 0.0, 60, 540, 960, "draft", "libx264", True, True,
        pre_filters=["drawbox=x=1:y=2:w=3:h=4:color=0x000000@1.000:t=fill"],
        post_filters=["eq=brightness=0.200:contrast=1.080:saturation=0.950"],
    )
    assert base != same
    assert same == repeated
    assert other_pre != same
    assert other_post != same


def test_segment_applies_pre_before_crop_and_post_after_scale(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"segment")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    output = tmp_path / "out" / "000.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    pre = ["drawbox=x=1:y=2:w=3:h=4:color=0x000000@1.000:t=fill"]
    post = ["eq=brightness=0.100:contrast=1.080:saturation=0.950"]
    cached = render._segment(
        "source.mp4",
        {"width": 1920, "height": 1080, "fingerprint": "abc", "duration": 2.0},
        {"crop": {"cx": 0.5, "cy": 0.5}},
        0.0, 2.0, 60, output, True, True, 540, 960, "draft", "libx264",
        tmp_path / "cache",
        crop={"x": 656, "y": 0, "w": 608, "h": 1080},
        pre_filters=pre,
        post_filters=post,
    )
    assert cached is False
    vf = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert vf.startswith(pre[0])
    assert ",crop=608:1080:656:0," in vf
    assert vf.index("scale=540:960") > vf.index("crop=608:1080")
    assert vf.index(post[0]) > vf.index("scale=540:960")
    assert vf.endswith("fade=t=out:st=1.600:d=0.4")
    assert output.is_file()


def test_segment_reuses_cache_when_filters_repeat(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"segment")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    args = dict(
        source="source.mp4",
        meta={"width": 1920, "height": 1080, "fingerprint": "abc", "duration": 2.0},
        scene={},
        start=0.0,
        duration=2.0,
        frames=60,
        first=False,
        last=False,
        out_w=540,
        out_h=960,
        quality="draft",
        encoder="libx264",
        cache_dir=tmp_path / "cache",
        crop={"x": 656, "y": 0, "w": 608, "h": 1080},
        pre_filters=["drawbox=x=1:y=2:w=3:h=4:color=0x000000@1.000:t=fill"],
        post_filters=["eq=brightness=0.100:contrast=1.080:saturation=0.950"],
    )
    assert render._segment(output=tmp_path / "a.mp4", **args) is False
    assert render._segment(output=tmp_path / "b.mp4", **args) is True
    assert len(calls) == 1


# ---------------------------------------------------------------- unit: compose


def test_motion_perspective_push_golden():
    edit = _edit(motion=[{"kind": "push", "start": 0.0, "end": 2.0}])
    segment = _compiled(edit)["segments"][0]
    assert segment["motion_engine"] == "perspective"
    assert segment["scale_filter"] == "scale=540:960:flags=lanczos"
    z = (
        "if(lt((on/30),0.000),1.000,if(lt((on/30),2.000),"
        "1.000+(0.060)*(1-cos(PI*((on/30)-0.000)/2.000000))/2,1.060))"
    )
    assert segment["post_filter"] == (
        f"perspective=x0='(((W-W/({z}))/2)+0)':"
        f"y0='(((H-H/({z}))/2)+0)':"
        f"x1='(W-((W-W/({z}))/2)+0)':"
        f"y1='(((H-H/({z}))/2)+0)':"
        f"x2='(((W-W/({z}))/2)+0)':"
        f"y2='(H-((H-H/({z}))/2)+0)':"
        f"x3='(W-((W-W/({z}))/2)+0)':"
        f"y3='(H-((H-H/({z}))/2)+0)':"
        "interpolation=cubic:eval=frame"
    )
    assert segment["filter"].endswith(segment["post_filter"])


def test_motion_perspective_punch_in_uses_path_keyframes():
    edit = _edit(motion=[{
        "kind": "punch_in", "start": 0.2, "end": 1.8,
        "amount": 0.08, "ramp": 0.3,
    }])
    segment = _compiled(edit)["segments"][0]
    payload = segment["post_filter"]
    assert payload.startswith("perspective=x0='")
    assert "if(lt((on/30),0.200),1.000" in payload
    assert "1.000+(0.080)*(1-cos(PI*((on/30)-0.200)/0.300000))/2" in payload
    assert payload.endswith("interpolation=cubic:eval=frame")


def test_motion_perspective_shake_is_subpixel_and_gated():
    edit = _edit(motion=[{"kind": "shake", "start": 0.0, "end": 2.0, "seed": 7}])
    segment = _compiled(edit)["segments"][0]
    payload = segment["post_filter"]
    assert "perspective=" in payload
    assert "1.0391" in payload
    assert "5.400*sin(2*PI*7.000*on/30+0.122)*between(on,0,60)" in payload
    assert "9.600*cos(2*PI*7.000*on/30+0.122)*between(on,0,60)" in payload
    assert "zoompan" not in payload


def test_motion_snap_zoom_perspective_golden():
    edit = _edit(motion=[{"kind": "snap_zoom", "start": 0.0, "end": 2.0}])
    segment = _compiled(edit)["segments"][0]
    assert "if(lt(on,0),1.000,1.1200)" in segment["post_filter"]


def test_motion_zoompan_engine_keeps_wave1_chain():
    edit = _edit(motion=[{"kind": "push", "start": 0.0, "end": 2.0}])
    segment = _compiled(edit, motion_engine="zoompan")["segments"][0]
    assert segment["motion_engine"] == "zoompan"
    assert segment["scale_filter"] == "scale=540:960:flags=lanczos"
    assert "s=540x960" in segment["post_filter"]
    assert "perspective" not in segment["post_filter"]


def test_no_motion_reports_none_and_keeps_color():
    edit = _edit(color={"preset": "warm_film"})
    segment = _compiled(edit)["segments"][0]
    assert segment["motion_engine"] == "none"
    assert segment["post_filter"].startswith("eq=brightness=0.020")
    assert "perspective" not in segment["post_filter"]


def test_draft_size_scales_geometry_and_fonts_stay_normalized():
    edit = _edit(graphics=[{
        "type": "text", "kind": "hook", "text": "STOP",
        "start": 0.0, "end": 2.0,
    }])
    compiled = _compiled(edit, size=(540, 960))
    assert compiled["canvas"] == {"w": 540, "h": 960}
    layer = compiled["overlays"][0]
    assert layer["rect"] == {"x": 0.12, "y": 0.05, "w": 0.76, "h": 0.16}
    assert layer["raster"]["mode"] == "static"


def test_layer_raster_modes_and_hashes():
    edit = _edit(graphics=[
        {"type": "text", "kind": "hook", "text": "STOP", "start": 0.0, "end": 2.0},
        {"type": "fx", "kind": "progress_bar", "start": 0.0, "end": 2.0},
    ])
    layers = _compiled(edit)["overlays"]
    text = next(item for item in layers if item["type"] == "text")
    bar = next(item for item in layers if item["kind"] == "progress_bar")
    assert text["raster"]["mode"] == "static"
    assert text["raster"]["frames"] == 1
    assert text["raster"] == {
        "mode": "static", "frames": 1, "fps": 30,
        "hash": "lyh_8dae0b3b4f251b7b51e1f392",
    }
    assert bar["raster"]["mode"] == "sequence"
    assert bar["raster"]["frames"] == 60
    assert bar["raster"]["fps"] == 30
    assert bar["raster"] == {
        "mode": "sequence", "frames": 60, "fps": 30,
        "hash": "lyh_128941560d0d14db71e1b35e",
    }
    assert text["raster"]["hash"].startswith("lyh_")
    # A static layer's pixels do not depend on its in/out point.
    moved = _edit(graphics=[
        {"type": "text", "kind": "hook", "text": "STOP", "start": 0.5, "end": 1.5},
    ])
    moved_text = _compiled(moved)["overlays"][0]
    assert moved_text["raster"]["hash"] == text["raster"]["hash"]
    changed = _edit(graphics=[
        {"type": "text", "kind": "hook", "text": "GO", "start": 0.0, "end": 2.0},
    ])
    changed_text = _compiled(changed)["overlays"][0]
    assert changed_text["raster"]["hash"] != text["raster"]["hash"]


# ---------------------------------------------------------------- unit: layers


def test_layer_png_cache_is_keyed_by_layer_hash(tmp_path, monkeypatch):
    edit = _edit(graphics=[{
        "type": "text", "kind": "hook", "text": "STOP",
        "start": 0.0, "end": 2.0,
    }])
    layer = _compiled(edit)["overlays"][0]
    cache = tmp_path / "layers"
    first = render._layer_png(layer, 540, 960, cache)
    assert first is not None and first.is_file()

    original = render._render_layer_image
    def explode(*args, **kwargs):
        raise AssertionError("cache hit must not redraw the layer")

    monkeypatch.setattr(render, "_render_layer_image", explode)
    second = render._layer_png(layer, 540, 960, cache)
    assert second == first
    monkeypatch.setattr(render, "_render_layer_image", original)
    other = dict(layer)
    other["text"] = "GO"
    assert render._layer_png(other, 540, 960, tmp_path / "layers2") != first


def test_layer_sequence_writes_one_png_per_output_frame(tmp_path):
    edit = _edit(graphics=[{
        "type": "fx", "kind": "progress_bar", "start": 0.0, "end": 2.0,
    }])
    layer = _compiled(edit)["overlays"][0]
    cache = tmp_path / "layers"
    first = render._layer_png(
        layer, 540, 960, cache, frame_index=0, frame_count=60,
    )
    assert first is not None
    for index in range(60):
        path = render._layer_png(
            layer, 540, 960, cache, frame_index=index, frame_count=60,
        )
        assert path is not None and path.is_file()
    assert len(list(first.parent.glob("*.png"))) == 60
    # Early and late frames differ: the bar grows.
    early = np.asarray(Image.open(cache / first.parent.name / "00001.png"))
    late = np.asarray(Image.open(cache / first.parent.name / "00060.png"))
    assert int((late[:, :, 3] > 200).sum()) > int((early[:, :, 3] > 200).sum())


def test_burn_layers_is_skipped_when_empty(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("empty layer list must not start ffmpeg")

    monkeypatch.setattr(render, "_run", explode)
    count = render._burn_layers(
        tmp_path / "in.mp4", [], tmp_path / "out.mp4", tmp_path,
        540, 960, 2.0, "draft", "libx264",
    )
    assert count == 0
    assert not (tmp_path / "out.mp4").exists()


def test_burn_layers_is_one_encode_with_sequence_offset(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    edit = _edit(graphics=[
        {"type": "text", "kind": "hook", "text": "STOP", "start": 0.0, "end": 2.0},
        {"type": "fx", "kind": "progress_bar", "start": 0.0, "end": 2.0},
    ])
    layers = _compiled(edit)["overlays"]
    count = render._burn_layers(
        tmp_path / "in.mp4", layers, tmp_path / "out.mp4", tmp_path,
        540, 960, 2.0, "draft", "libx264",
        cache_dir=tmp_path / "layers",
    )
    assert count == 2
    cmd = captured["cmd"]
    assert cmd.count("-filter_complex") == 1
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("overlay=") == 2
    assert "setpts=PTS-STARTPTS+0.000/TB" in graph
    assert "-framerate" in cmd and "30" in cmd
    assert cmd[cmd.index("-t") + 1] == "2.000000"
    assert cmd[cmd.index("-map") + 1] == "[v2]"


# ---------------------------------------------------------------- fixtures: jobs


def _write_job(jobs: Path, source_path: Path, meta: dict) -> Path:
    job_dir = jobs / "job1"
    job_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "id": "job1",
        "status": "ready",
        "created": 1.0,
        "updated": 1.0,
        "source": {
            "name": source_path.name,
            "path": str(source_path),
            "duration": float(meta.get("duration") or 2.0),
            "width": int(meta.get("width") or 1920),
            "height": int(meta.get("height") or 1080),
            "fingerprint": meta.get("fingerprint") or "fixture",
        },
        "analysis": {"scenes": list(SCENES)},
        "clip_sets": [{
            "id": "cs_1",
            "stories": [{
                "id": "s1",
                "title": "Story one",
                "start": 0.0,
                "end": 2.0,
                "dur": 2.0,
                "clips": list(CLIPS),
            }],
        }],
        "renders": {},
    }
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job_dir


def _env(tmp_path, monkeypatch, source_path: Path, meta: dict) -> dict:
    data = tmp_path / "data"
    jobs = data / "jobs"
    jobs.mkdir(parents=True)
    monkeypatch.setattr(app, "DATA", data)
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", data / "sources")
    monkeypatch.delenv("VIBECUT_TOKEN", raising=False)
    job_dir = _write_job(jobs, source_path, meta)
    return {
        "data": data,
        "jobs": jobs,
        "dir": job_dir,
        "client": TestClient(app.app),
        "job_id": "job1",
        "source": source_path,
        "meta": meta,
    }


def _save_current(env: dict, edit: dict) -> dict:
    edits.save_edit(env["dir"], edit)
    path = env["dir"] / "job.json"
    job = json.loads(path.read_text(encoding="utf-8"))
    edits.set_pointer(job, edit)
    path.write_text(json.dumps(job), encoding="utf-8")
    return edit


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _env(tmp_path, monkeypatch, Path("/tmp/vibecut-t1-source.mp4"), {
        "duration": 2.0, "width": 1920, "height": 1080, "fingerprint": "fixture",
    })


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg is not installed")
    root = tmp_path_factory.mktemp("t1-media")
    source = root / "source.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=0x203040:s=1920x1080:r=30:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
        "-vf", (
            "drawbox=x=100:y=100:w=300:h=300:c=red:t=fill,"
            "drawbox=x=1500:y=700:w=200:h=200:c=blue:t=fill"
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
    ], check=True)
    return source, pipeline.probe(source)


@pytest.fixture
def real_env(tmp_path, monkeypatch, media):
    source, meta = media
    return _env(tmp_path, monkeypatch, source, meta)


# ---------------------------------------------------------------- routes: errors


def test_frame_unknown_edit_is_404(env):
    response = env["client"].get("/api/jobs/job1/edits/ed_unknown/frame?t=1")
    assert response.status_code == 404


def test_frame_bad_time_is_422(env):
    edit = _save_current(env, _edit())
    client = env["client"]
    for query in ("t=-1", "t=9", "t=nan", "t=inf", ""):
        response = client.get(f"/api/jobs/job1/edits/{edit['id']}/frame?{query}")
        assert response.status_code == 422, query


def test_frame_bad_quality_is_422(env):
    edit = _save_current(env, _edit())
    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1&quality=cinema",
    )
    assert response.status_code == 422


def test_frame_stale_story_is_409(env):
    edit = _save_current(env, _edit())
    path = env["dir"] / "job.json"
    job = json.loads(path.read_text(encoding="utf-8"))
    job["clip_sets"][0]["stories"][0]["clips"][0]["start"] = 0.5
    path.write_text(json.dumps(job), encoding="utf-8")
    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=0.5",
    )
    assert response.status_code == 409


def test_proxy_unknown_edit_is_404(env):
    response = env["client"].get("/api/jobs/job1/edits/ed_unknown/proxy")
    assert response.status_code == 404


def test_proxy_stale_story_is_409(env):
    edit = _save_current(env, _edit())
    path = env["dir"] / "job.json"
    job = json.loads(path.read_text(encoding="utf-8"))
    job["clip_sets"][0]["stories"][0]["clips"][0]["end"] = 1.5
    path.write_text(json.dumps(job), encoding="utf-8")
    response = env["client"].get(f"/api/jobs/job1/edits/{edit['id']}/proxy")
    assert response.status_code == 409


def test_frame_route_returns_jpeg_from_render(env, monkeypatch):
    edit = _save_current(env, _edit(color={"preset": "warm_film"}))
    calls = {}

    def fake_frame(source, meta, job_dir, compiled, at, **kwargs):
        calls.update({
            "source": source, "at": at, "quality": kwargs.get("quality"),
            "aspect": kwargs.get("aspect"), "compiled": compiled,
        })
        return b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"

    monkeypatch.setattr(render, "render_story_frame", fake_frame)
    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1.25&quality=final",
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"
    assert calls["quality"] == "final"
    assert calls["aspect"] == "9:16"
    assert calls["at"] == pytest.approx(1.25)
    assert calls["compiled"]["canvas"] == {"w": 1080, "h": 1920}


def test_frame_route_uses_aspect_canvas_for_draft(env, monkeypatch):
    edit = _save_current(env, _edit(aspect="4:5"))
    calls = {}

    def fake_frame(source, meta, job_dir, compiled, at, **kwargs):
        calls["canvas"] = compiled["canvas"]
        return b"\xff\xd8jpeg\xff\xd9"

    monkeypatch.setattr(render, "render_story_frame", fake_frame)
    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1.0",
    )
    assert response.status_code == 200
    assert calls["canvas"] == {"w": 540, "h": 676}


def test_proxy_route_returns_mp4_and_reuses_build(env, monkeypatch):
    edit = _save_current(env, _edit())
    calls = []
    target = env["dir"] / "proxies" / "fake.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"proxy-bytes")

    def fake_proxy(source, meta, job_dir, clips, **kwargs):
        calls.append(kwargs)
        return target

    monkeypatch.setattr(render, "build_story_proxy", fake_proxy)
    response = env["client"].get(f"/api/jobs/job1/edits/{edit['id']}/proxy")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"proxy-bytes"
    assert calls[0]["aspect"] == "9:16"


# ---------------------------------------------------------------- real ffmpeg


def _extract_frame(video: Path, frame: int, output: Path) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", str(output),
    ], check=True)
    return output


def _gray(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.float64)


def _window_sum(values: np.ndarray, size: int) -> np.ndarray:
    pad = size // 2
    padded = np.pad(values, pad, mode="edge")
    integral = np.zeros((padded.shape[0] + 1, padded.shape[1] + 1))
    integral[1:, 1:] = padded.cumsum(axis=0).cumsum(axis=1)
    return (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )


def _ssim(first: np.ndarray, second: np.ndarray, size: int = 7) -> float:
    assert first.shape == second.shape
    count = float(size * size)
    mean_a = _window_sum(first, size) / count
    mean_b = _window_sum(second, size) / count
    var_a = _window_sum(first * first, size) / count - mean_a * mean_a
    var_b = _window_sum(second * second, size) / count - mean_b * mean_b
    cov = _window_sum(first * second, size) / count - mean_a * mean_b
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    score = (
        (2 * mean_a * mean_b + c1) * (2 * cov + c2)
        / ((mean_a ** 2 + mean_b ** 2 + c1) * (var_a + var_b + c2))
    )
    return float(score.mean())


@needs_ffmpeg
def test_real_edit_render_and_frame_endpoint_match(real_env):
    env = real_env
    edit = _save_current(env, _edit(
        clean=[{
            "kind": "plate",
            "box": {"x": 0.05, "y": 0.72, "w": 0.6, "h": 0.12},
        }],
        motion=[{
            "kind": "punch_in", "start": 0.2, "end": 1.8,
            "amount": 0.08, "ramp": 0.3,
        }],
        color={"preset": "warm_film"},
        graphics=[
            {"type": "text", "kind": "hook", "text": "STOP", "start": 0.0, "end": 2.0},
            {"type": "fx", "kind": "progress_bar", "start": 0.0, "end": 2.0},
        ],
    ))
    source, meta = real_env["source"], real_env["meta"]
    result = render.render_reel(
        str(source), meta, env["dir"], _plan(), "Test", lambda *args: None,
        quality="final", aspect="9:16", edit=edit,
    )
    assert result["width"] == 1080 and result["height"] == 1920
    assert result["duration"] == pytest.approx(2.0, abs=0.1)
    assert result["layers"] == 2
    assert result["layer_count"] == 2
    final = env["dir"] / "renders" / result["path"]
    assert final.is_file() and final.stat().st_size > 1024

    final_frame = _extract_frame(final, 30, env["data"] / "final.png")
    pixels = np.asarray(Image.open(final_frame).convert("RGB"))
    top = pixels[96:403, 130:950]
    assert int((top > 230).all(axis=2).sum()) > 100, "text layer is missing"
    plate = pixels[1380:1600, 20:1000]
    assert float(plate.mean()) < 45, "plate is missing"

    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1.0&quality=final",
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    frame_path = env["data"] / "frame.jpg"
    frame_path.write_bytes(response.content)
    assert Image.open(frame_path).size == (1080, 1920)

    score = _ssim(_gray(final_frame), _gray(frame_path))
    assert score >= 0.97, f"frame/final SSIM too low: {score:.4f}"

    draft = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1.0&quality=draft",
    )
    assert draft.status_code == 200
    assert Image.open(io.BytesIO(draft.content)).size == (540, 960)


@needs_ffmpeg
def test_perspective_motion_is_smoother_than_zoompan(tmp_path):
    source = tmp_path / "dot.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30:d=2",
        "-vf", "drawbox=x=1050:y=480:w=20:h=20:c=white:t=fill",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
        "-pix_fmt", "yuv420p", str(source),
    ], check=True)
    meta = pipeline.probe(source)
    edit = _edit(motion=[{"kind": "push", "start": 0.0, "end": 2.0}])
    centroids = {}
    for engine in ("zoompan", "perspective"):
        compiled = compose_render.compile_edit(
            edit, clips=CLIPS, source=meta, size=(540, 960),
            motion_engine=engine,
        )
        segment = compiled["segments"][0]
        video = tmp_path / f"{engine}.mp4"
        render._segment(
            str(source), meta, {}, 0.0, 2.0, 60, video, False, False,
            540, 960, "draft", "libx264", tmp_path / "cache",
            crop=segment["crop"],
            pre_filters=segment["pre_filters"],
            post_filters=segment["post_filters"],
        )
        frames = tmp_path / f"{engine}-frames"
        frames.mkdir()
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video),
            "-fps_mode", "passthrough", str(frames / "%03d.png"),
        ], check=True)
        xs = []
        for path in sorted(frames.glob("*.png")):
            pixels = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
            mask = pixels > 180
            ys, x = np.nonzero(mask)
            weights = pixels[mask] - 180
            xs.append(float((x * weights).sum() / weights.sum()))
        centroids[engine] = float(np.diff(xs).std())
    assert centroids["perspective"] < centroids["zoompan"] * 0.5, centroids


@needs_ffmpeg
def test_real_proxy_is_540p_and_reused(real_env):
    env = real_env
    edit = _save_current(env, _edit())
    first = env["client"].get(f"/api/jobs/job1/edits/{edit['id']}/proxy")
    assert first.status_code == 200
    assert first.headers["content-type"] == "video/mp4"
    assert len(first.content) > 1024
    proxy = next((env["dir"] / "proxies").glob("*.mp4"))
    info = pipeline.probe(proxy)
    assert (info["width"], info["height"]) == (540, 960)
    assert info["duration"] == pytest.approx(2.0, abs=0.1)
    assert info["has_audio"] is True
    mtime = proxy.stat().st_mtime_ns
    second = env["client"].get(f"/api/jobs/job1/edits/{edit['id']}/proxy")
    assert second.status_code == 200
    assert second.content == first.content
    assert proxy.stat().st_mtime_ns == mtime


# ---------------------------------------------------------------- beat grid


def _beat_edit(start: float) -> dict:
    return {
        "audio": {"mode": "dub"},
        "motion": [{"kind": "punch_in", "start": start, "end": start + 1.0}],
        "graphics": [],
    }


def test_edit_beat_grid_uses_only_the_locked_bed(tmp_path, monkeypatch):
    audio_plan = {
        "mode": "dub",
        "music": {"source": "library", "locked_hash": "a" * 64},
    }
    calls = {"locked": [], "grid": []}
    monkeypatch.setattr(
        audio, "resolve_locked_track",
        lambda job_dir, digest: (calls["locked"].append(digest), tmp_path / "bed.wav")[1],
    )
    monkeypatch.setattr(
        audio, "beat_grid",
        lambda path: (calls["grid"].append(path), {"bpm": 120.0, "beats": [1.0, 2.0]})[1],
    )

    assert render.edit_beat_grid(tmp_path, _beat_edit(1.0), audio_plan) == {
        "bpm": 120.0, "beats": [1.0, 2.0],
    }
    assert calls["locked"] == ["a" * 64]
    assert calls["grid"] == [tmp_path / "bed.wav"]

    off_beat = render.edit_beat_grid(tmp_path, _beat_edit(1.5), audio_plan)
    assert off_beat is None

    unlocked = render.edit_beat_grid(
        tmp_path, _beat_edit(1.0),
        {"mode": "dub", "music": {"source": "library"}},
    )
    assert unlocked is None


def test_edit_beat_grid_ignores_original_audio_and_missing_bed(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "resolve_locked_track", lambda *args: None)
    monkeypatch.setattr(audio, "resolve_music_track", lambda *args: None)
    monkeypatch.setattr(audio, "beat_grid", lambda *args: {"bpm": 120.0, "beats": [1.0]})
    assert render.edit_beat_grid(
        tmp_path, _beat_edit(1.0), {"mode": "original"},
    ) is None
    assert render.edit_beat_grid(
        tmp_path, _beat_edit(1.0),
        {"mode": "dub", "music": {"source": "library", "locked_hash": "b" * 64}},
    ) is None


def test_render_reel_passes_the_locked_beat_grid_to_compile(tmp_path, monkeypatch):
    grid = {"bpm": 120.0, "beats": [1.0, 2.0]}
    captured: dict = {}

    monkeypatch.setattr(render, "edit_beat_grid", lambda *args: grid)

    def fake_compile(edit, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after compile")

    monkeypatch.setattr(compose_render, "compile_edit", fake_compile)
    with pytest.raises(RuntimeError, match="stop after compile"):
        render.render_reel(
            str(tmp_path / "source.mp4"),
            {"path": str(tmp_path / "source.mp4"), "duration": 2.0},
            tmp_path,
            {"target": 2, "clips": [{"scene": 0, "start": 0.0, "end": 2.0}]},
            "Title",
            lambda *args: None,
            edit={"audio": {"mode": "dub"}},
            audio_plan={"mode": "dub", "music": {"locked_hash": "a" * 64}},
        )
    assert captured["beats"] == grid


# ---------------------------------------------------------------- multiline captions (QA #1)


def _multiline_track():
    return captions.CaptionTrack(
        id="cap_multi",
        job_id="job1",
        version=1,
        target=2,
        cues=[
            captions.CaptionCue(
                id="c1", start=0.0, end=2.0,
                text="THAT DOESN'T MEAN THAT\nYOUR RESPONSE HAS TO",
                clip_index=0,
            ),
        ],
        style=captions.normalize_style({}),
        style_id="bold",
        clip_hash=edits.clip_snapshot_hash(CLIPS),
        clip_windows=[{"index": 0, "scene": 0, "start": 0.0, "end": 2.0, "duration": 2.0}],
        created=1.0,
    )


def _measure():
    return render.ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def test_wrap_caption_keeps_stored_line_breaks():
    font = render._caption_font(48)
    lines = render._wrap_caption(
        _measure(), "THAT DOESN'T MEAN THAT\nYOUR RESPONSE HAS TO", font, 2000,
    )
    assert lines == ["THAT DOESN'T MEAN THAT", "YOUR RESPONSE HAS TO"]


def test_wrap_caption_breaks_between_words_then_characters():
    draw = _measure()
    font = render._caption_font(48)
    width = int(draw.textlength("HELLO WORLD", font=font)) + 2
    lines = render._wrap_caption(draw, "HELLO WORLD AGAIN\r\nNEXT", font, width)
    assert lines == ["HELLO WORLD", "AGAIN", "NEXT"]
    narrow = int(draw.textlength("ABC", font=font)) + 1
    pieces = render._wrap_caption(draw, "ABCDEFGHI", font, narrow)
    assert "".join(pieces) == "ABCDEFGHI" and len(pieces) >= 3
    assert all(draw.textlength(piece, font=font) <= narrow for piece in pieces)


def test_multiline_caption_layer_rasterizes_two_rows():
    layer = {
        "type": "caption", "kind": "caption",
        "text": "FIRST LINE\nSECOND LINE",
        "rect": {"x": 0.07, "y": 0.7, "w": 0.86, "h": 0.14},
        "style": {"size": 64, "color": "#ffffff"},
        "opacity": 1.0,
    }
    image = render._render_text_layer(layer, 1080, 1920)
    alpha = np.asarray(image)[..., 3]
    rows = np.nonzero(alpha.max(axis=1) > 0)[0]
    assert rows.size > 0
    assert (np.diff(rows) > 1).any(), "expected two separate text rows"


def _white_pixels_low(pixels: np.ndarray) -> int:
    lower = pixels[int(pixels.shape[0] * 0.6):]
    return int((lower > 230).all(axis=2).sum())


@needs_ffmpeg
def test_real_frame_and_render_burn_a_multiline_caption(real_env):
    env = real_env
    track = _multiline_track()
    captions.save_track(env["dir"], track)
    edit = _save_current(env, _edit(captions={"track_id": track.id, "style_id": "bold"}))

    response = env["client"].get(
        f"/api/jobs/job1/edits/{edit['id']}/frame?t=1.0&quality=draft",
    )
    assert response.status_code == 200, response.text
    frame = np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"))
    assert _white_pixels_low(frame) > 200, "caption missing from the frame"

    plan = _plan()
    plan["_caption_track"] = {
        "track_id": track.id,
        "style_id": track.style_id,
        "style": track.style,
        "cues": [cue.to_dict() for cue in track.cues],
    }
    source, meta = env["source"], env["meta"]
    result = render.render_reel(
        str(source), meta, env["dir"], plan, "Test", lambda *args: None,
        quality="draft", aspect="9:16", edit=edit,
    )
    final = env["dir"] / "renders" / result["path"]
    assert final.is_file()
    still = _extract_frame(final, 30, env["data"] / "multi.png")
    pixels = np.asarray(Image.open(still).convert("RGB"))
    assert _white_pixels_low(pixels) > 200, "caption missing from the render"


@needs_ffmpeg
def test_custom_output_size_border_and_audio_fade_render(real_env):
    env = real_env
    edit = _save_current(env, _edit(
        output={"width": 540, "height": 960, "fps": 30},
        border={"width": 8, "color": "#ff0000", "radius": 0},
        audio={"mode": "original", "fade": {"in": 0.4, "out": 0.4}},
    ))
    source, meta = env["source"], env["meta"]
    result = render.render_reel(
        str(source), meta, env["dir"], _plan(), "Custom", lambda *args: None,
        quality="final", aspect="9:16", edit=edit,
        audio_plan=audio.plan_from_edit(edit["audio"]),
    )
    assert result["width"] == 540 and result["height"] == 960
    final = env["dir"] / "renders" / result["path"]
    assert final.is_file() and final.stat().st_size > 1024
    still = _extract_frame(final, 30, env["data"] / "custom.png")
    pixels = np.asarray(Image.open(still).convert("RGB"))
    red = tuple(int(value) for value in pixels[0, 0])
    assert red[0] > 220 and red[1] < 30 and red[2] < 30


def test_reverse_and_freeze_clip_intents_compile():
    edit = _edit(
        sequence=[
            {"scene": 0, "start": 0.0, "end": 1.0, "role": "hook", "reverse": True},
            {"kind": "freeze", "scene": 0, "start": 1.0, "end": 2.0, "role": "beat"},
        ],
    )
    clips = [
        {"scene": 0, "start": 0.0, "end": 1.0, "role": "hook", "reverse": True},
        {"kind": "freeze", "scene": 0, "start": 1.0, "end": 2.0, "role": "beat"},
    ]
    compiled = compose_render.compile_edit(
        edit, clips=clips, source={"width": 1920, "height": 1080}, scenes=SCENES,
        size=(540, 960),
    )
    assert compiled["segments"][0]["reverse"] is True
    assert compiled["segments"][1]["freeze"] is True


@needs_ffmpeg
def test_reverse_and_freeze_render(real_env):
    env = real_env
    clips = [
        {"scene": 0, "start": 0.0, "end": 1.0, "role": "hook", "reverse": True},
        {"kind": "freeze", "scene": 0, "start": 1.0, "end": 2.0, "role": "beat"},
    ]
    edit = _save_current(env, _edit(sequence=clips))
    result = render.render_reel(
        str(env["source"]), env["meta"], env["dir"],
        {"target": 3, "clips": clips, "_scenes": list(SCENES)},
        "Reverse", lambda *args: None,
        quality="draft", aspect="9:16", edit=edit,
    )
    assert result["duration"] == pytest.approx(2.0, abs=0.15)
    assert (env["dir"] / "renders" / result["path"]).is_file()
