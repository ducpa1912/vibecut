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
