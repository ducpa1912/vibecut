import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("VIBECUT_DATA", tempfile.mkdtemp(prefix="vibecut-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def reset_cloud_circuits():
    """Keep module-level auth quarantine and provider breakers per-test."""
    import audio

    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()
    yield
    audio.clear_openrouter_quarantine()
    audio.reset_provider_breaker()


@pytest.fixture(autouse=True)
def generous_test_volume(monkeypatch):
    """Keep tests independent of the workstation's real free space.

    Disk-specific tests override ``disk.usage`` locally to exercise 412s.
    """
    import disk

    gib = 1024 ** 3
    monkeypatch.setattr(
        disk, "usage", lambda path: (100 * gib, 10 * gib, 90 * gib)
    )
    yield


@pytest.fixture(autouse=True)
def sources_present(monkeypatch):
    """Most tests use placeholder source paths; treat them as present.

    Missing-source tests restore ``app._source_exists`` to the real check.
    """
    import app

    monkeypatch.setattr(app, "_source_exists", lambda path: True)
    yield
