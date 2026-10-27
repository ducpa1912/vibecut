"""Check reports progress per sampled frame (QA #16)."""

from __future__ import annotations

import pipeline


def test_text_samples_report_frame_n_of_m(tmp_path, monkeypatch):
    frames = [{"file": f"{index:05d}.jpg", "t": index * 1.0} for index in range(60)]
    monkeypatch.setattr(pipeline, "extract_text_frames", lambda *args, **kwargs: frames)
    monkeypatch.setattr(pipeline.vision, "available", lambda: True)
    batches = []

    def probe(directory, files=None):
        batches.append(len(files))
        return {path.name: {"text": []} for path in files}

    monkeypatch.setattr(pipeline.vision, "probe_images", probe)
    seen = []
    result = pipeline.read_text_samples(
        "/tmp/none.mp4", tmp_path, 60.0, fps=1.0,
        progress=lambda fraction, message: seen.append((round(fraction, 3), message)),
    )
    assert len(result["frames"]) == 60
    assert batches == [24, 24, 12]
    assert seen[0][1] == "Pulling frames to read text"
    assert [message for _f, message in seen[1:]] == [
        "Reading text · frame 24 / 60",
        "Reading text · frame 48 / 60",
        "Reading text · frame 60 / 60",
    ]
    fractions = [fraction for fraction, _m in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0


def test_run_check_maps_sampler_progress_into_its_band(tmp_path):
    import detect

    calls = []

    def sampler(path, job_dir, duration, *, fps, max_frames, progress):
        progress(0.5, "Reading text · frame 5 / 10")
        return {"frames": [], "vision": True, "fps": fps}

    report = detect.run_check(
        "j1",
        {"id": "j1", "status": "ready", "source": {"path": "/tmp/x.mp4", "duration": 10.0},
         "analysis": {"scenes": []}},
        tmp_path,
        sampler=sampler,
        audio_extractor=lambda *args, **kwargs: None,
        progress=lambda fraction, message: calls.append((round(fraction, 3), message)),
    )
    assert report is not None
    assert (0.35, "Reading text · frame 5 / 10") in calls
