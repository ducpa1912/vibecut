"""Classic Sound preview routes stay local, bounded and cached by prompt."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app
import audio
import music
import routes_classic as routes


def _write_fake(path: Path, size: int = 2048) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\0" * max(0, size - 4))
    return path


@pytest.fixture
def preview_env(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    job_root = tmp_path / "jobs" / "job1"
    job_root.mkdir(parents=True)
    library = tmp_path / "music"
    library.mkdir()
    track = library / "calm.wav"
    _write_fake(track)
    raw = tmp_path / "raw.wav"
    _write_fake(raw)

    monkeypatch.setattr(audio, "CACHE", cache)
    monkeypatch.setattr(audio, "MUSIC_DIRS", {"library": library, "generated": library})
    monkeypatch.setattr(app, "_job_dir", lambda job_id: job_root)
    monkeypatch.setattr(app, "load_job", lambda job_id: {"id": job_id})
    monkeypatch.setattr(routes, "_write_preview", lambda source, target, seconds: _write_fake(target))
    return {
        "cache": cache,
        "job_root": job_root,
        "library": library,
        "track": track,
        "raw": raw,
    }


def test_preview_length_is_hard_bounded():
    assert routes._preview_seconds(None) == 12.0
    assert routes._preview_seconds(1) == 3.0
    assert routes._preview_seconds(999) == 20.0
    assert routes._preview_seconds("nope") == 12.0


def test_uploaded_bgm_must_stay_inside_the_job(preview_env):
    outside = preview_env["job_root"].parent / "secret.wav"
    _write_fake(outside)
    with pytest.raises(HTTPException) as exc:
        routes._job_file("job1", "../secret.wav")
    assert exc.value.status_code == 400
    assert "inside this job" in exc.value.detail


def test_library_track_must_stay_inside_the_music_folder(preview_env):
    with pytest.raises(HTTPException) as exc:
        routes._library_track("library", "/etc/passwd", [])
    assert exc.value.status_code == 400
    assert "outside the music library" in exc.value.detail


def test_the_bgm_route_serves_a_cached_local_preview(preview_env, monkeypatch):
    calls = []
    original = routes._cached_preview

    def counted(label, source, seconds):
        calls.append((label, source, seconds))
        return original(label, source, seconds)

    monkeypatch.setattr(routes, "_cached_preview", counted)
    first = routes.classic_bgm_preview(
        "job1", source="library", track=str(preview_env["track"]), seconds=12,
    )
    second = routes.classic_bgm_preview(
        "job1", source="library", track=str(preview_env["track"]), seconds=12,
    )
    assert first.path == second.path
    assert first.headers["x-vibecut-preview"] == "miss"
    assert second.headers["x-vibecut-preview"] == "hit"
    assert len(calls) == 2


def test_generated_music_is_cached_by_prompt(preview_env, monkeypatch):
    calls = []

    def fake_generate(engine, prompt, seconds, timeout=None):
        calls.append({"engine": engine, "prompt": prompt, "seconds": seconds, "timeout": timeout})
        return preview_env["raw"]

    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {
            "minimax-music": {"available": True},
            "lyria-clip": {"available": False},
        },
    })
    monkeypatch.setattr(music, "generate_music", fake_generate)

    body = routes.MusicPreviewBody(
        engine="minimax-music", prompt="warm cinematic", moods=["warm"], seconds=12,
    )
    first, first_state = routes._generated_music_preview(body)
    second, second_state = routes._generated_music_preview(body)

    assert first == second
    assert (first_state, second_state) == ("miss", "hit")
    assert len(calls) == 1
    assert calls[0]["seconds"] == 12.0
    assert calls[0]["timeout"] == routes.PREVIEW_TIMEOUT
    assert "12-second instrumental preview" in calls[0]["prompt"]


def test_a_new_prompt_generates_a_new_cached_preview(preview_env, monkeypatch):
    calls = []

    def fake_generate(engine, prompt, seconds, timeout=None):
        calls.append(prompt)
        return preview_env["raw"]

    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {"minimax-music": {"available": True}, "lyria-clip": {"available": False}},
    })
    monkeypatch.setattr(music, "generate_music", fake_generate)

    routes._generated_music_preview(routes.MusicPreviewBody(engine="minimax-music", prompt="calm"))
    routes._generated_music_preview(routes.MusicPreviewBody(engine="minimax-music", prompt="upbeat"))
    assert len(calls) == 2


def test_generated_music_without_a_key_is_refused_with_a_clear_reason(preview_env, monkeypatch):
    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {
            "minimax-music": {"available": False},
            "lyria-clip": {"available": False},
        },
    })
    with pytest.raises(HTTPException) as exc:
        routes._generated_music_preview(
            routes.MusicPreviewBody(engine="minimax-music", prompt="warm"),
        )
    assert exc.value.status_code == 409
    assert "use my BGM" in exc.value.detail


def test_the_generated_route_reports_its_cache_header(preview_env, monkeypatch):
    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {"minimax-music": {"available": True}, "lyria-clip": {"available": False}},
    })
    monkeypatch.setattr(music, "generate_music", lambda *args, **kwargs: preview_env["raw"])
    body = routes.MusicPreviewBody(engine="minimax-music", prompt="soft piano")
    response = routes.classic_music_preview("job1", body)
    assert response.headers["x-vibecut-preview"] == "miss"
    assert response.media_type == "audio/wav"
    assert response.filename == "music-preview.wav"


def test_the_route_keeps_the_prompt_short_and_moods_bounded(preview_env, monkeypatch):
    seen = {}

    def fake_generate(engine, prompt, seconds, timeout=None):
        seen["prompt"] = prompt
        return preview_env["raw"]

    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {"minimax-music": {"available": True}, "lyria-clip": {"available": False}},
    })
    monkeypatch.setattr(music, "generate_music", fake_generate)
    routes._generated_music_preview(routes.MusicPreviewBody(
        engine="minimax-music",
        prompt="x" * 900,
        moods=[f"m{i}" for i in range(20)],
        seconds=12,
    ))
    assert len(seen["prompt"]) <= 340
    assert seen["prompt"].count("m") < 20


def test_the_bgm_route_is_registered_and_bounded(preview_env):
    client = TestClient(app.app)
    response = client.get(
        "/api/classic/jobs/job1/sound/bgm-preview",
        params={"source": "library", "track": str(preview_env["track"]), "seconds": 12},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-vibecut-preview"] == "miss"
    assert response.headers["content-type"].startswith("audio/wav")
    assert len(response.content) > 512


def test_the_generated_route_is_registered_and_returns_audio(preview_env, monkeypatch):
    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {"minimax-music": {"available": True}, "lyria-clip": {"available": False}},
    })
    monkeypatch.setattr(music, "generate_music", lambda *args, **kwargs: preview_env["raw"])
    client = TestClient(app.app)
    response = client.post(
        "/api/classic/jobs/job1/sound/music-preview",
        json={"engine": "minimax-music", "prompt": "warm", "moods": ["warm"], "seconds": 12},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-vibecut-preview"] in {"hit", "miss"}
    assert response.headers["content-type"].startswith("audio/wav")


def test_a_slow_ai_preview_does_not_block_a_local_bgm_preview(preview_env, monkeypatch):
    import threading

    started = threading.Event()
    release = threading.Event()

    def slow_generate(engine, prompt, seconds, timeout=None):
        started.set()
        release.wait(5)
        return str(preview_env["raw"])

    monkeypatch.setattr(music, "generate_music", slow_generate)
    monkeypatch.setattr(audio, "engine_status", lambda: {
        "music": {"minimax-music": {"available": True}},
    })
    worker = threading.Thread(
        target=routes._generated_music_preview,
        args=(routes.MusicPreviewBody(engine="minimax-music", prompt="calm piano"),),
    )
    worker.start()
    try:
        assert started.wait(5)
        done = threading.Event()

        def local():
            routes._cached_preview("bgm", preview_env["track"], 12.0)
            done.set()

        threading.Thread(target=local).start()
        assert done.wait(2), "a local BGM preview waited behind the AI music call"
    finally:
        release.set()
        worker.join(5)
