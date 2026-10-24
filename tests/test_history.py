import asyncio
import io
import json

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

import app
import audio
import history_store
import pipeline
import render


def make_job(job_id: str, tmp_path) -> dict:
    scenes = [{
        "id": 0,
        "start": 0.0,
        "end": 4.0,
        "dur": 4.0,
        "mid": 2.0,
        "hook": 70.0,
        "score": 70.0,
        "deep": True,
        "ocr": "",
        "speech": "Hello world.",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }]
    return {
        "id": job_id,
        "created": 1.0,
        "updated": 1.0,
        "status": "ready",
        "progress": 1.0,
        "message": "Ready",
        "error": None,
        "source": {
            "path": str(tmp_path / "source.mp4"),
            "name": "source.mp4",
            "duration": 60.0,
            "width": 1920,
            "height": 1080,
        },
        "options": {},
        "analysis": {
            "scenes": scenes,
            "hook_scene": 0,
            "deep_count": 1,
            "deep_scene_ids": [0],
            "engine": {"transcript_language": "en"},
        },
        "renders": {},
    }


@pytest.fixture
def job_env(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "DATA", tmp_path)
    job_id = "historyjob"
    job = make_job(job_id, tmp_path)
    directory = jobs / job_id
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job_id, job, directory


def fake_plan(target: int = 15) -> dict:
    return {
        "target": target,
        "total": 4.0,
        "hook_scene": 0,
        "auto": False,
        "clip_count": 1,
        "clips": [{
            "scene": 0,
            "start": 0.0,
            "end": 4.0,
            "dur": 4.0,
            "role": "hook",
        }],
        "_source_lang": "en",
    }


def patch_script(monkeypatch, *, fail: bool = False, warning: bool = False):
    monkeypatch.setattr(app, "_plan_for", lambda job, target, hook: fake_plan(target))
    monkeypatch.setattr(pipeline, "read_transcript", lambda directory: [])

    if fail:
        def boom(*args, **kwargs):
            raise RuntimeError("script boom")
        monkeypatch.setattr(audio, "build_script", boom)
    else:
        monkeypatch.setattr(audio, "build_script", lambda *args, **kwargs: [{
            "scene": 0,
            "clip": 0,
            "role": "hook",
            "duration": 4.0,
            "text": "Hello world.",
            "original": "Hello world.",
            "emotion": "warm",
            "rate": 1.0,
        }])

    if warning:
        def bad_adapt(*args, **kwargs):
            raise audio.AudioError("translation failed")
        monkeypatch.setattr(audio, "adapt_script", bad_adapt)
    else:
        def good_adapt(script, *args, **kwargs):
            for line in script:
                line["literal"] = "Xin chào."
                line["text"] = "Chào bạn."
                line["rewrite"] = "rules"
            return script
        monkeypatch.setattr(audio, "adapt_script", good_adapt)

    monkeypatch.setattr(audio, "refit_script", lambda script: script)
    monkeypatch.setattr(audio, "translation_status", lambda: {
        "provider": "opencode",
        "source": "en",
        "target": "vi",
        "lines": 1,
        "tried": ["openrouter"],
    })
    monkeypatch.setattr(audio, "rewrite_status", lambda: {
        "requested": True,
        "ok": True,
        "provider": "rules",
        "used": "rules",
        "fallback": False,
        "error": "",
        "attempts": [{"provider": "opencode", "error": ""}],
    })
    monkeypatch.setattr(audio, "scene_moods", lambda scenes, clips: ["warm"])


def run_script(job_id: str, **kwargs) -> dict:
    body = app.ScriptBody(
        target=kwargs.pop("target", 15),
        translate=kwargs.pop("translate", "vi"),
        mode=kwargs.pop("mode", "smooth"),
        **kwargs,
    )
    return app.audio_script(job_id, body)


def test_script_history_persists_and_restore_returns_snapshot(job_env, monkeypatch):
    job_id, _job, directory = job_env
    patch_script(monkeypatch)

    result = run_script(job_id, overrides={"0": "Edited line."})
    script_id = result["script_id"]
    assert script_id

    listing = app.get_history(job_id)
    assert listing["count"] == 3
    entry = next(item for item in listing["entries"] if item["type"] == "script")
    assert entry["id"] == script_id
    assert entry["type"] == "script"
    assert entry["status"] == "ok"
    assert entry["target"] == 15
    assert entry["style"] == "smooth"
    assert entry["source_lang"] == "en"
    assert entry["target_lang"] == "vi"
    assert entry["provider"] == "opencode"
    assert entry["tried"] == ["openrouter", "opencode"]
    assert entry["script_id"] == script_id
    assert entry["clip_hash"]

    detail = app.get_history_entry(job_id, script_id)
    snapshot = detail["snapshot"]
    assert snapshot["original_lines"] == ["Hello world."]
    assert snapshot["literal_lines"] == ["Xin chào."]
    assert snapshot["final_lines"][0]["text"] == result["lines"][0]["text"]
    assert snapshot["overrides"] == {"0": "Edited line."}
    assert snapshot["translation"]["provider"] == "opencode"
    assert snapshot["rewrite"]["provider"] == "rules"
    assert snapshot["target"] == 15
    assert snapshot["style"] == "smooth"

    before = (directory / "job.json").read_text(encoding="utf-8")
    restored = app.restore_history_entry(job_id, script_id)
    assert restored["restored"] is True
    assert restored["entry"]["id"] == script_id
    assert restored["snapshot"]["final_lines"][0]["text"] == result["lines"][0]["text"]
    assert (directory / "job.json").read_text(encoding="utf-8") == before

    # A reopened job reads the same history from disk, not from job.json.
    assert app.load_job(job_id)["id"] == job_id
    again = app.get_history(job_id)
    assert next(item for item in again["entries"] if item["type"] == "script")["id"] == script_id


def test_failed_script_attempt_is_recorded_without_overwriting(job_env, monkeypatch):
    job_id, _job, _directory = job_env
    patch_script(monkeypatch)
    first = run_script(job_id, overrides={"0": "Kept line."})
    first_id = first["script_id"]

    patch_script(monkeypatch, warning=True)
    fallback = run_script(job_id)
    assert fallback["warning"] == "translation failed"
    entries = app.get_history(job_id)["entries"]
    fallback_entry = next(item for item in entries if item["type"] == "script")
    assert fallback_entry["status"] == "fallback"
    assert fallback_entry["warning"] == "translation failed"
    assert any(item["id"] == first_id for item in entries)

    patch_script(monkeypatch, fail=True)
    with pytest.raises(RuntimeError):
        run_script(job_id)

    entries = app.get_history(job_id)["entries"]
    assert entries[0]["status"] == "failed"
    assert "script boom" in entries[0]["error"]
    assert any(item["status"] == "fallback" for item in entries)
    assert any(item["id"] == first_id for item in entries)
    old = app.get_history_entry(job_id, first_id)
    assert old["snapshot"]["final_lines"][0]["text"] == first["lines"][0]["text"]


def test_render_history_queued_ready_failed_cancelled(job_env, monkeypatch):
    job_id, job, directory = job_env
    monkeypatch.setattr(app, "_valid_script_id", lambda job_id, plan, script_id: script_id)
    submitted = []
    monkeypatch.setattr(
        app.render_pool, "submit",
        lambda *args, **kwargs: submitted.append((args, kwargs)),
    )
    audio_plan = {
        "mode": "full",
        "script_id": "script123",
        "translate": {"source": "en", "target": "vi", "provider": "opencode"},
    }
    plan15 = fake_plan(15)
    queued = app._queue_render(
        job_id, job, plan15, "final", "9:16", None, False, audio_plan, False,
        preset="tiktok", script_id="script123",
    )
    assert queued["status"] == "queued"
    entry = history_store.list_entries(directory)[0]
    assert entry["type"] == "render"
    assert entry["status"] == "queued"
    assert entry["target"] == 15
    assert entry["aspect"] == "9:16"
    assert entry["quality"] == "final"
    assert entry["audio_sig"]
    assert entry["script_id"] == "script123"

    def ready_reel(*args, **kwargs):
        return {
            "path": "reel_15.mp4",
            "poster": "reel_15.jpg",
            "duration": 4.0,
            "width": 1080,
            "height": 1920,
            "size": 1234,
            "has_audio": True,
            "clip_count": 1,
            "quality": "final",
            "aspect": "9:16",
            "encoder": "libx264",
            "captions": False,
            "caption_count": 0,
            "cached": 0,
            "used_assets": [],
        }

    monkeypatch.setattr(render, "render_reel", ready_reel)
    app.run_render(
        job_id, 15, plan15, "key15", quality="final", aspect="9:16",
        audio_plan=audio_plan, audio_sig=queued["audio_sig"],
        preset="tiktok", script_id="script123",
    )
    entries = history_store.list_entries(directory)
    assert entries[0]["status"] == "ready"
    assert entries[0]["path"] == "reel_15.mp4"
    assert entries[0]["aspect"] == "9:16"
    assert entries[0]["quality"] == "final"
    assert entries[0]["script_id"] == "script123"
    detail = history_store.get_entry(directory, entries[0]["id"])
    assert detail["snapshot"]["render"]["path"] == "reel_15.mp4"

    plan30 = fake_plan(30)
    app._queue_render(
        job_id, job, plan30, "final", "9:16", None, False, audio_plan, False,
        script_id="script123",
    )

    def failed_reel(*args, **kwargs):
        raise RuntimeError("render boom")

    monkeypatch.setattr(render, "render_reel", failed_reel)
    app.run_render(
        job_id, 30, plan30, "key30", quality="final", aspect="9:16",
        audio_plan=audio_plan, audio_sig=queued["audio_sig"],
        script_id="script123",
    )
    entries = history_store.list_entries(directory)
    assert entries[0]["status"] == "failed"
    assert "render boom" in entries[0]["error"]

    plan60 = fake_plan(60)
    app._queue_render(
        job_id, job, plan60, "final", "9:16", None, False, audio_plan, False,
        script_id="script123",
    )

    def cancelled_reel(*args, **kwargs):
        raise render.RenderCancelled("stopped")

    monkeypatch.setattr(render, "render_reel", cancelled_reel)
    app.run_render(
        job_id, 60, plan60, "key60", quality="final", aspect="9:16",
        audio_plan=audio_plan, audio_sig=queued["audio_sig"],
        script_id="script123",
    )
    entries = history_store.list_entries(directory)
    assert entries[0]["status"] == "cancelled"
    assert entries[0]["script_id"] == "script123"


def test_history_cap_prunes_old_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBECUT_HISTORY_MAX", "3")
    job_dir = tmp_path / "capped"
    job_dir.mkdir()
    for index in range(5):
        history_store.append(
            job_dir,
            {"id": f"e{index}", "type": "test", "status": "ok"},
            {"index": index},
        )

    entries = history_store.list_entries(job_dir)
    assert [entry["id"] for entry in entries] == ["e4", "e3", "e2"]
    history = job_dir / "history"
    assert (history / "e2.json").is_file()
    assert (history / "e4.json").is_file()
    assert not (history / "e0.json").exists()
    assert not (history / "e1.json").exists()
    assert history_store.get_entry(job_dir, "e2")["snapshot"] == {"index": 2}
    assert history_store.get_entry(job_dir, "e0") is None
    assert history_store.delete_entry(job_dir, "e4") is True
    assert history_store.get_entry(job_dir, "e4") is None


def test_history_never_stores_secrets(tmp_path):
    job_dir = tmp_path / "secrets"
    job_dir.mkdir()
    history_store.append(
        job_dir,
        {
            "id": "sec",
            "type": "test",
            "status": "ok",
            "api_key": "sk-abcdefghijklmnop",
            "usage": {"input_tokens": 7, "output_tokens": 3},
            "note": "Bearer abcdefghijklmnop",
        },
        {
            "nested": {
                "token": "tok_12345678",
                "authorization": "Bearer xyz1234567890",
                "safe": "ok",
            },
            "apiKey": "sk-zyxwvutsrqponmlk",
            "usage": {"input_tokens": 7},
        },
    )
    text = (job_dir / "history" / "sec.json").read_text(encoding="utf-8")
    index_text = (job_dir / "history" / "index.json").read_text(encoding="utf-8")
    assert "sk-" not in text
    assert "sk-" not in index_text
    assert "abcdefghijklmnop" not in text
    assert "abcdefghijklmnop" not in index_text
    assert "xyz1234567890" not in text
    assert '"authorization"' not in text
    assert '"token"' not in text
    assert '"input_tokens":7' in text
    assert '"input_tokens":7' in index_text
    data = json.loads(text)
    assert data["entry"]["usage"]["input_tokens"] == 7
    assert data["snapshot"]["nested"]["safe"] == "ok"


def test_old_job_without_history_is_empty_and_public_job_stays_small(job_env):
    job_id, job, _directory = job_env
    assert app.get_history(job_id) == {"entries": [], "count": 0}
    assert "history" not in app.public_job(job)
    assert "history" not in app.public_status(job)


def test_history_http_routes(job_env):
    job_id, _job, _directory = job_env
    entry = app._record_upload_history(
        job_id, "voice", "ok", "take.wav",
        path="audio/take.wav", duration=1.5, size=12,
    )
    client = TestClient(app.app)
    listing = client.get(f"/api/jobs/{job_id}/history")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["entries"][0]["id"] == entry["id"]

    detail = client.get(f"/api/jobs/{job_id}/history/{entry['id']}")
    assert detail.status_code == 200
    assert detail.json()["snapshot"]["path"] == "audio/take.wav"

    restored = client.post(f"/api/jobs/{job_id}/history/{entry['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["restored"] is True
    assert restored.json()["snapshot"]["duration"] == 1.5

    deleted = client.delete(f"/api/jobs/{job_id}/history/{entry['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": entry["id"]}
    assert client.get(f"/api/jobs/{job_id}/history/{entry['id']}").status_code == 404


def test_voice_upload_records_success_and_failure(job_env, monkeypatch):
    job_id, _job, directory = job_env

    def fake_store(temp, job_dir):
        output = job_dir / "audio" / "uploaded_voice_test.wav"
        output.write_bytes(b"RIFF")
        return output

    monkeypatch.setattr(audio, "store_uploaded_voice", fake_store)
    monkeypatch.setattr(audio, "media_duration", lambda path: 1.25)
    upload = UploadFile(file=io.BytesIO(b"RIFF"), filename="take.wav")
    result = asyncio.run(app.upload_voice_audio(job_id, upload))
    assert result["duration"] == 1.25
    entry = history_store.list_entries(directory)[0]
    assert entry["type"] == "upload"
    assert entry["status"] == "ok"
    assert entry["kind"] == "voice"
    assert entry["path"] == result["path"]
    assert entry["path"].startswith("audio/uploaded_voice_")
    assert entry["duration"] == 1.25

    bad = UploadFile(file=io.BytesIO(b"nope"), filename="notes.txt")
    with pytest.raises(HTTPException):
        asyncio.run(app.upload_voice_audio(job_id, bad))
    entry = history_store.list_entries(directory)[0]
    assert entry["type"] == "upload"
    assert entry["status"] == "failed"
    assert entry["kind"] == "voice"
    assert entry["name"] == "notes.txt"
