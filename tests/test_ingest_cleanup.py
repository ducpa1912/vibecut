"""Restart cleanup for URL-ingest temporary files."""

from __future__ import annotations

import app


def test_recover_jobs_removes_ytdlp_dotless_partials(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    sources = tmp_path / "sources"
    jobs.mkdir()
    sources.mkdir()
    monkeypatch.setattr(app, "JOBS", jobs)
    monkeypatch.setattr(app, "SOURCES", sources)

    dotless = sources / "ingest-job-123.mp4.part"
    dotless.write_bytes(b"partial")
    hidden = sources / ".ingest-job-456.mp4"
    hidden.write_bytes(b"partial")

    app.recover_jobs()

    assert not dotless.exists()
    assert not hidden.exists()
