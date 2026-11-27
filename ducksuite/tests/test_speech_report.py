"""The plain speech failure (REQ-20261118-02 leftovers, loop P-A).

The speech report says the failure once; the engine's own words go to the log.
"""
from __future__ import annotations

import logging

from duckcore.engine import detect


def test_speech_engine_empty_message_is_plain_and_keeps_the_language(caplog) -> None:
    detail = "whisper model not installed at /models/whisper"
    with caplog.at_level(logging.WARNING, logger="duckcore.engine.detect"):
        warnings = detect._report_warnings(
            [],
            audio={
                "has_audio": True,
                "speech_state": "engine_empty",
                "speech_error": detail,
                "speech_language": "vi",
            },
            quality={},
            text={"confirmed": True},
            attested=True,
            sampled_error=None,
            truncated=False,
            lock=False,
        )
    found = [item for item in warnings if item["code"] == "speech_engine_empty"]
    assert len(found) == 1
    message = found[0]["message"]
    assert "Engine:" not in message
    assert "vi" in message
    assert detail not in message
    assert "Retry speech on this video" in message
    assert "re-importing is not needed" in message
    assert "Setup → Engines" in message
    assert detail in caplog.text


