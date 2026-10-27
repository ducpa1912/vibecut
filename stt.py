"""Cloud speech-to-text helpers.

This Wave 1 module owns only the cloud STT provider list and credential
lookups that used to live in ``audio.py``.  It makes no network call at import
time and contains no local transcription engine.

Transcription itself still lives in ``pipeline.py``; Wave 2 track E1 moves the
cloud request code here.  Keeping the key helpers in one module means the
network contract has a single obvious home once that move lands.
"""

from __future__ import annotations

import settings_store

CLOUD_STT_PROVIDERS = ("groq", "openai", "deepgram")


def cloud_stt_key(provider: str) -> str:
    """Return the stored key for one cloud STT provider, or an empty string."""
    name = str(provider or "").strip().lower()
    if name not in CLOUD_STT_PROVIDERS:
        return ""
    return settings_store.get_secret(name)


def openai_key() -> str:
    return cloud_stt_key("openai")


def groq_key() -> str:
    return cloud_stt_key("groq")


def deepgram_key() -> str:
    return cloud_stt_key("deepgram")
