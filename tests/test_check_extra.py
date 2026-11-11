"""Check reads the moments the 4 fps pass cannot land on (loop 7, build B)."""

from __future__ import annotations

from duckcore.engine import detect


def test_cut_frames_are_added_off_the_sample_grid(monkeypatch) -> None:
    monkeypatch.setenv("DUCK_ONSET_SCAN", "0")
    scenes = [{"start": 0.0}, {"start": 10.1}]
    moments = detect._extra_text_times(
        "/nonexistent.mp4",
        scenes,
        160.0,
        fps=30.0,
        window=(0.0, 160.0),
        cadence=4.0,
    )
    assert 10.133 in moments
    # Frame 0 is already the pass's first still.
    assert 0.0 not in moments


def test_a_moment_on_a_sample_frame_is_not_read_twice(monkeypatch) -> None:
    monkeypatch.setenv("DUCK_ONSET_SCAN", "0")
    moments = detect._extra_text_times(
        "/nonexistent.mp4",
        [{"start": 10.25 - 1.0 / 30.0}],  # + one frame lands on the 10.25 sample
        160.0,
        fps=30.0,
        window=(0.0, 160.0),
        cadence=4.0,
    )
    assert moments == []


def test_the_onset_scan_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("DUCK_ONSET_SCAN", "0")
    moments = detect._extra_text_times(
        "/nonexistent.mp4", [], 160.0, fps=30.0, window=(0.0, 160.0), cadence=4.0,
    )
    assert moments == []
