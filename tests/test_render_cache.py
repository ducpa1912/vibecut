"""Render performance helpers and the Studio read cache.

The render tests cover the one-overlay caption track, the decoder choice and
the decode/scale order. The last section imports the shipped ``api.js`` under
Node. It fakes ``fetch``, so it never touches a server or the network; this
is the only place the JS cache is tested because R1 T4 owns no JS test file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import render

STUDIO = Path(__file__).resolve().parents[1] / "static" / "studio"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


def _png(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"png")
    return path


def _caption_layers(count: int, *, overlap: bool = False) -> list[dict]:
    layers = []
    for index in range(count):
        start = index * 1.0
        end = start + (1.5 if overlap else 0.6)
        layers.append({
            "id": f"cap{index:02d}",
            "type": "caption",
            "kind": "caption",
            "text": f"line {index}",
            "start": start,
            "end": end,
            "rect": {"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15},
            "raster": {"mode": "static", "frames": 1, "fps": 30},
            "z": 50,
        })
    return layers


# ---------------------------------------------------------------- overlay track


def test_still_overlay_track_fills_gaps_and_total(tmp_path):
    first = _png(tmp_path, "a.png")
    second = _png(tmp_path, "b.png")
    track = render._still_overlay_track(
        [(1.0, 2.0, first), (3.0, 4.0, second)], 5.0, tmp_path, (40, 20),
    )
    assert track is not None and track.is_file()
    text = track.read_text()
    assert text.count("file '") == 5  # blank, cue, blank, cue, trailing blank
    assert "duration 1.000000" in text
    assert (tmp_path / "overlay-blank.png").is_file()
    durations = [
        float(line.split()[1])
        for line in text.splitlines() if line.startswith("duration ")
    ]
    assert sum(durations) == pytest.approx(5.0, abs=1e-5)


def test_still_overlay_track_refuses_overlaps(tmp_path):
    assert render._still_overlay_track(
        [(0.0, 2.0, _png(tmp_path, "a.png")),
         (1.0, 3.0, _png(tmp_path, "b.png"))],
        4.0, tmp_path, (40, 20),
    ) is None


def test_burn_captions_uses_one_overlay_for_many_cues(tmp_path, monkeypatch):
    cues = [(index * 1.0, index * 1.0 + 0.6, f"line {index}") for index in range(12)]
    pngs = [_png(tmp_path, f"cap{index}.png") for index in range(12)]
    monkeypatch.setattr(render, "_caption_pngs", lambda *args, **kwargs: pngs)
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    render._burn_captions(
        tmp_path / "in.mp4", cues, tmp_path / "out.mp4", tmp_path,
        540, 960, 12.0, "draft", "libx264",
    )
    cmd = captured["cmd"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("overlay=") == 1
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "concat"
    assert cmd[cmd.index("-map") + 1] == "[v1]"


def test_burn_captions_keeps_chain_when_cues_overlap(tmp_path, monkeypatch):
    cues = [(0.0, 2.0, "one"), (1.0, 3.0, "two")]
    pngs = [_png(tmp_path, "a.png"), _png(tmp_path, "b.png")]
    monkeypatch.setattr(render, "_caption_pngs", lambda *args, **kwargs: pngs)
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    render._burn_captions(
        tmp_path / "in.mp4", cues, tmp_path / "out.mp4", tmp_path,
        540, 960, 4.0, "draft", "libx264",
    )
    graph = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert graph.count("overlay=") == 2


def test_caption_runs_split_on_a_graphic_and_keep_short_runs():
    captions = _caption_layers(8)
    graphic = {
        "id": "txt1", "type": "text", "kind": "hook", "text": "HOOK",
        "start": 0.0, "end": 8.0,
        "rect": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2},
        "raster": {"mode": "static", "frames": 1, "fps": 30},
    }
    more = [dict(layer, id=f"cap{index + 8:02d}", start=layer["start"] + 8.0,
                 end=layer["end"] + 8.0) for index, layer in enumerate(captions)]
    runs = render._caption_runs(captions + [graphic] + more)
    assert runs == {0: 7, 9: 16}


def test_burn_layers_collapses_contiguous_captions(tmp_path, monkeypatch):
    layers = _caption_layers(10)
    counter = {"n": 0}

    def fake_png(layer, out_w, out_h, cache_dir, frame_index=0, frame_count=1, fps=30):
        counter["n"] += 1
        return _png(tmp_path, f"layer-{counter['n']}.png")

    monkeypatch.setattr(render, "_layer_png", fake_png)
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    burned = render._burn_layers(
        tmp_path / "in.mp4", layers, tmp_path / "out.mp4", tmp_path,
        540, 960, 20.0, "draft", "libx264",
        cache_dir=tmp_path / "layers",
    )
    cmd = captured["cmd"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert burned == 10
    assert graph.count("overlay=") == 1
    assert cmd[cmd.index("-f") + 1] == "concat"
    # The group is rendered once, not once per cue plus again on fallback.
    assert counter["n"] == 10


def test_burn_layers_keeps_chain_when_captions_overlap(tmp_path, monkeypatch):
    layers = _caption_layers(10, overlap=True)

    def fake_png(layer, out_w, out_h, cache_dir, frame_index=0, frame_count=1, fps=30):
        return _png(tmp_path, f"{layer['id']}.png")

    monkeypatch.setattr(render, "_layer_png", fake_png)
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    burned = render._burn_layers(
        tmp_path / "in.mp4", layers, tmp_path / "out.mp4", tmp_path,
        540, 960, 20.0, "draft", "libx264",
        cache_dir=tmp_path / "layers",
    )
    graph = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert burned == 10
    assert graph.count("overlay=") == 10


# ---------------------------------------------------------------- decode/scale


def test_decoder_args_leave_the_av1_decoder_to_ffmpeg(monkeypatch):
    monkeypatch.delenv("VIBECUT_DECODER", raising=False)
    assert render._decoder_args({"codec": "av1"}) == []
    assert render._decoder_args({"codec": "av01"}, 2) == ["-threads", "2"]
    assert render._decoder_args({"codec": "h264"}) == []


def test_decoder_args_allow_videotoolbox_or_software(monkeypatch):
    monkeypatch.setenv("VIBECUT_DECODER", "videotoolbox")
    assert render._decoder_args({"codec": "av1"}) == ["-hwaccel", "videotoolbox"]
    monkeypatch.setenv("VIBECUT_DECODER", "software")
    assert render._decoder_args({"codec": "hevc"}) == []


def test_crop_filter_drops_frames_before_scaling_above_30fps(monkeypatch):
    crop = {"x": 0, "y": 0, "w": 608, "h": 1080}
    fast = render._crop_filter({"width": 1920, "height": 1080, "fps": 60}, crop, 540, 960)
    slow = render._crop_filter({"width": 1920, "height": 1080, "fps": 24}, crop, 540, 960)
    assert fast.index("fps=30") < fast.index("scale=540:960")
    assert slow.index("scale=540:960") < slow.index("fps=30")


def test_segment_puts_decoder_and_seek_before_input(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, timeout=None, cwd=None, cancel_event=None):
        captured["cmd"] = list(cmd)
        Path(cmd[-1]).write_bytes(b"segment")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render, "_run", fake_run)
    output = tmp_path / "out" / "000.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    render._segment(
        "source.mp4",
        {"width": 2560, "height": 1440, "fps": 30, "codec": "av1",
         "fingerprint": "abc", "duration": 4.0},
        {}, 1.0, 4.0, 120, output, False, False, 1080, 1920,
        "final", "libx264", tmp_path / "cache",
        crop={"x": 875, "y": 0, "w": 810, "h": 1440},
        decode_threads=2,
    )
    cmd = captured["cmd"]
    input_at = cmd.index("-i")
    assert cmd.index("-ss") < input_at
    assert cmd.index("-threads") < input_at
    assert cmd[cmd.index("-threads") + 1] == "2"


# ---------------------------------------------------------------- api.js cache

NO_PAGE = (
    "globalThis.document = {cookie: '', readyState: 'complete',"
    " getElementById: () => null, addEventListener: () => {},"
    " documentElement: {dataset: {}}};\n"
    "globalThis.localStorage = {getItem: () => null, setItem: () => {},"
    " removeItem: () => {}};\n"
    "globalThis.window = {addEventListener: () => {}, location: {hash: ''}};\n"
)


def run_api(body: str):
    url = (STUDIO / "api.js").as_uri()
    script = NO_PAGE + (
        "const calls = [];\n"
        "globalThis.__calls = calls;\n"
        "globalThis.fetch = async (path) => {\n"
        "  calls.push(String(path));\n"
        "  const payload = String(path).endsWith('/clip-sets') ? {clip_sets: []}\n"
        "    : String(path).endsWith('/check') ? {status: 'done'}\n"
        "    : String(path).endsWith('/edits') ? {edits: [], pointers: {}}\n"
        "    : {id: 'j1', updated: (globalThis.__stamp || 1), status: 'ready'};\n"
        "  return {ok: true, status: 200, text: async () => JSON.stringify(payload)};\n"
        "};\n"
        f"const m = await import({json.dumps(url)});\n"
        f"const out = await (async () => {{ {body} }})();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@needs_node
def test_api_cache_serves_repeated_step_reads_once():
    out = run_api("""
        await m.getJob("j1");
        await m.getJob("j1");
        await m.listClipSets("j1");
        await m.listClipSets("j1");
        await m.getCheckReport("j1");
        await m.getCheckReport("j1");
        await m.listEdits("j1");
        await m.listEdits("j1");
        return {calls, stats: m.readCacheStats()};
    """)
    assert out["calls"] == [
        "/api/jobs/j1",
        "/api/jobs/j1/clip-sets",
        "/api/jobs/j1/check",
        "/api/jobs/j1/edits",
    ]
    assert out["stats"]["hits"] == 4
    assert out["stats"]["misses"] == 4


@needs_node
def test_api_cache_write_invalidates_every_read():
    out = run_api("""
        await m.getJob("j1");
        await m.request("/api/jobs/j1/edits", {method: "POST", body: {}});
        await m.getJob("j1");
        return {calls, stats: m.readCacheStats()};
    """)
    assert out["calls"] == [
        "/api/jobs/j1",
        "/api/jobs/j1/edits",
        "/api/jobs/j1",
    ]
    assert out["stats"]["writes"] == 1


@needs_node
def test_api_cache_drops_derived_reads_when_updated_changes():
    out = run_api("""
        await m.getJob("j1");
        await m.listClipSets("j1");
        await m.getCheckReport("j1");
        await m.listEdits("j1");
        globalThis.__stamp = 2;
        await m.getJob("j1", {fresh: true});
        const before = calls.length;
        await m.listClipSets("j1");
        await m.getCheckReport("j1");
        await m.listEdits("j1");
        return {after: calls.slice(before)};
    """)
    assert out["after"] == [
        "/api/jobs/j1/clip-sets",
        "/api/jobs/j1/check",
        "/api/jobs/j1/edits",
    ]


@needs_node
def test_api_cache_skips_status_artifacts_and_media():
    out = run_api("""
        await m.request("/api/jobs/j1/packets");
        await m.request("/api/jobs/j1/packets");
        await m.request("/api/jobs/j1/artifacts");
        await m.request("/api/jobs/j1/artifacts");
        await m.request("/api/jobs/j1/frame?t=1.000&quality=draft");
        await m.request("/api/jobs/j1/frame?t=1.000&quality=draft");
        await m.getJobStatus("j1");
        await m.getJobStatus("j1");
        return {calls, stats: m.readCacheStats()};
    """)
    assert out["calls"] == [
        "/api/jobs/j1/packets",
        "/api/jobs/j1/artifacts",
        "/api/jobs/j1/artifacts",
        "/api/jobs/j1/frame?t=1.000&quality=draft",
        "/api/jobs/j1/frame?t=1.000&quality=draft",
        "/api/jobs/j1/status",
        "/api/jobs/j1/status",
    ]
    assert out["stats"]["hits"] == 1


@needs_node
def test_api_cache_coalesces_concurrent_job_reads():
    out = run_api("""
        globalThis.__stamp = 2;
        const jobs = await Promise.all([m.getJob("j1"), m.getJob("j1")]);
        return {calls, stats: m.readCacheStats(), ids: jobs.map((job) => job.id)};
    """)
    assert out["calls"] == ["/api/jobs/j1"]
    assert out["stats"]["coalesced"] == 1
    assert out["ids"] == ["j1", "j1"]


@needs_node
def test_shell_job_stamp_and_change_helpers():
    url = (STUDIO / "shell.js").as_uri()
    script = NO_PAGE + (
        f"const m = await import({json.dumps(url)});\n"
        "process.stdout.write(JSON.stringify({\n"
        "  legacy: m.jobUpdatedAt({updated: 12.5}),\n"
        "  modern: m.jobUpdatedAt({updated_at: 'abc'}),\n"
        "  missing: m.jobUpdatedAt({}),\n"
        "  changed: m.jobChanged({updated: 1}, {updated: 2}),\n"
        "  same: m.jobChanged({updated_at: 'x'}, {updated_at: 'x'}),\n"
        "}));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == {
        "legacy": "12.5", "modern": "abc", "missing": "",
        "changed": True, "same": False,
    }


@needs_node
def test_api_cache_never_freezes_a_running_check_poll():
    out = run_api("""
        const states = ["running", "running", "ready"];
        globalThis.fetch = async (path) => {
          calls.push(String(path));
          const status = states.shift() || "ready";
          const payload = {status, progress: status === "ready" ? 1 : 0.4};
          return {ok: true, status: status === "ready" ? 200 : 202,
                  text: async () => JSON.stringify(payload)};
        };
        const seen = [];
        for (let i = 0; i < 4; i += 1) seen.push((await m.getCheckReport("j1")).status);
        return {calls, seen};
    """)
    # Each running poll reaches the server; only the finished report is cached.
    assert out["seen"] == ["running", "running", "ready", "ready"]
    assert len(out["calls"]) == 3
