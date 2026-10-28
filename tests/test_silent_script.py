"""Voice scripts for videos with no speech: brief, beats, timing, route."""

import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import audio
import settings_store
import silent_script as ss
import stt


def _scenes(count=30, length=6.0):
    return [
        {"id": index, "start": index * length, "end": (index + 1) * length,
         "ocr": "SALE" if index == 3 else "", "face": index % 2 == 0,
         "motion_score": 50, "hook": 40}
        for index in range(count)
    ]


def test_parse_brief_splits_exact_lines_from_guidance():
    brief = ss.parse_brief(
        'Cozy, slow Sunday. [script:"Some days you stay in."] warm tone '
        "[script: “And that is enough.”] [script:'Bye for now.']"
    )
    assert brief["script"] == ["Some days you stay in.", "And that is enough.", "Bye for now."]
    assert brief["guidance"] == "Cozy, slow Sunday. warm tone"


def test_beats_merge_short_cuts_and_split_long_shots():
    scenes = [
        {"id": 0, "start": 0.0, "end": 0.8}, {"id": 1, "start": 0.8, "end": 1.6},
        {"id": 2, "start": 1.6, "end": 3.0}, {"id": 3, "start": 3.0, "end": 30.0},
    ]
    beats = ss.build_beats(scenes, 30.0)
    assert beats[0]["start"] == 0.0 and beats[0]["end"] == 3.0
    assert beats[0]["scene_ids"] == [0, 1, 2]
    long_parts = [beat for beat in beats if beat["scene_ids"] == [3]]
    assert len(long_parts) == 4 and all(beat["end"] - beat["start"] <= ss.MAX_BEAT_S for beat in long_parts)
    assert beats[-1]["end"] == 30.0


def test_budget_and_timing_follow_the_language():
    assert ss.budget(4.0, "en") == 8
    assert ss.budget(4.0, "ja") == 20
    beats = [{"beat": 0, "start": 0.0, "end": 4.0, "scene": 0}]
    line = ss.timed_lines([{"beat": 0, "text": "Short line without a stop"}], beats, "en")[0]
    assert line["text"].endswith(".")
    assert 0.1 <= line["start"] < line["end"] <= 4.0


def test_exact_lines_are_kept_word_for_word_once():
    beats = [{"beat": i, "start": i * 5.0, "end": i * 5.0 + 5, "scene": i} for i in range(4)]
    lines = ss.timed_lines([
        {"beat": 0, "text": "Have you ever felt like everyone looks rich online?"},
        {"beat": 1, "text": "Because looking rich and being rich are not the same thing."},
        {"beat": 2, "text": "Debt hides."},
        {"beat": 3, "text": "But looking rich and being rich are not the same thing."},
    ], beats, "en")
    out = ss.enforce_exact(
        lines, ["Everyone looks rich online.", "But looking rich and being rich are not the same thing."],
        beats, "en",
    )
    assert [line["text"] for line in out] == [
        "Everyone looks rich online.",
        "Debt hides.",
        "But looking rich and being rich are not the same thing.",
    ]


def _job(tmp_path, scenes=None, has_audio=False):
    return {
        "id": "silent000001",
        "status": "ready",
        "source": {"name": "Một ngày ở nhà.mp4", "duration": 180.0, "has_audio": has_audio},
        "analysis": {"scenes": scenes or _scenes()},
    }


def test_write_script_saves_a_script_transcript_in_parts(tmp_path, monkeypatch):
    calls = []

    def fake_call(prompt, images, *, model, timeout):
        payload = json.loads(prompt.split("\n\n", 1)[1])
        calls.append(payload)
        beats = [beat["beat"] for beat in payload["beats"]]
        return json.dumps({"language": "vi", "lines": [
            {"beat": beat, "text": f"Câu số {beat}"} for beat in beats
        ] + [{"beat": 999, "text": "ngoài phần này"}]})

    monkeypatch.setattr(ss, "CHUNK_BEATS", 12)
    result = ss.write_script(
        _job(tmp_path), tmp_path, 'Ấm áp, chậm rãi. [script:"Chủ nhật ở nhà."]', call=fake_call,
    )
    assert result["language"] == "vi" and result["parts"] == 3
    # The beat outside a part is ignored; the exact line is placed verbatim.
    assert calls[0]["EXACT_LINES"] == ["Chủ nhật ở nhà."]
    assert "PREVIOUS_LINES" in calls[1]
    saved = stt.load_latest_transcript(tmp_path)
    assert saved["engine"] == "script" and saved["language"] == "vi"
    texts = [segment["text"] for segment in saved["segments"]]
    assert "Chủ nhật ở nhà." in texts
    assert all(text.endswith(".") for text in texts)
    assert saved["words"] and saved["words"][0]["start"] >= 0


def test_write_script_needs_a_brief(tmp_path):
    with pytest.raises(ss.ScriptError, match="Describe"):
        ss.write_script(_job(tmp_path), tmp_path, "   ")


def test_script_route_saves_brief_and_marks_the_job(tmp_path, monkeypatch):
    import app

    source = tmp_path / "source.mp4"
    source.write_bytes(b"v")
    job = {**_job(tmp_path), "id": "silentroute1", "created": 1.0, "options": {}}
    job["source"]["path"] = str(source)
    app.save_job(job)

    def fake_write(record, job_dir, brief, *, language=""):
        transcript = stt.build_transcript(
            engine="script", model="m", language="en",
            segments=[{"start": 0.1, "end": 2.0, "text": "Hello there."}],
            words=[], audio_duration=180.0, source_hash="brief:x",
        )
        stt.save_transcript(job_dir, transcript)
        return {"transcript": transcript, "brief": brief, "language": "en", "model": "m",
                "lines": 1, "exact_lines": 0, "images": 0, "parts": 1, "missing_exact": [],
                "beats": 30, "seconds": 0.1}

    monkeypatch.setattr(app.silent_script, "write_script", fake_write)
    api = TestClient(app.app)
    response = api.post("/api/jobs/silentroute1/script-brief", json={"brief": "Calm explainer."})
    assert response.status_code == 200, response.text
    assert "transcript" not in response.json()
    saved = app.load_job("silentroute1")
    assert saved["script_brief"]["brief"] == "Calm explainer."
    assert saved["analysis"]["engine"]["transcript_provider"] == "script"
    assert app._scripted(saved)
    cross = api.post("/api/jobs/silentroute1/script-brief", json={"brief": "x"}, headers={"sec-fetch-site": "cross-site"})
    assert cross.status_code == 403


def test_script_route_refuses_a_video_with_real_speech(tmp_path):
    import app

    job = {**_job(tmp_path, has_audio=True), "id": "speechroute1", "created": 1.0, "options": {}}
    job["analysis"]["transcript"] = {"segments": 12}
    job["analysis"]["engine"] = {"transcript_provider": "openrouter"}
    app.save_job(job)
    response = TestClient(app.app).post("/api/jobs/speechroute1/script-brief", json={"brief": "x"})
    assert response.status_code == 409


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_audio_bed_is_silence_for_a_source_without_sound(tmp_path):
    video = tmp_path / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2",
         "-c:v", "libx264", str(video)],
        check=True,
    )
    assert audio._has_audio_stream(str(video)) is False
    bed = audio._source_audio_bed(str(video), tmp_path)
    assert bed.is_file() and audio.media_duration(bed) == pytest.approx(2.0, abs=0.1)
