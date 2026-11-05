import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("VIBECUT_DATA", tempfile.mkdtemp(prefix="vibecut-test-"))
os.environ.setdefault("VIBECUT_KEEP_AWAKE", "0")
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
def rights_lock_default_off(monkeypatch):
    """Keep older tests independent of the Setup rights lock.

    Most baseline tests predate the lock and assert unrelated import, queue or
    error behaviour. The default is off for them; rights tests save their own
    setting and read it back through ``rights.py``.
    """
    import rights
    import settings_store

    monkeypatch.setattr(rights, "DEFAULT_LOCK", False)
    monkeypatch.setitem(settings_store.DEFAULTS, "rights", {"lock": False})
    yield


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test gets its own settings and secrets files.

    The suite runs in one process and one temp data folder, so a test that
    saves the rights lock or a key used to leak it into the next test. Lane
    isolation needs the leak gone for good.
    """
    import settings_store

    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    yield


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
