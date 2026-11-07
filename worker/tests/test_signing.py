from __future__ import annotations

import pytest
from duckclean_worker.signing import SignatureError, sign, verify

SECRET = "test-secret-not-a-real-key"
BODY = b'{"job_id":"11111111-1111-4111-8111-111111111111"}'


def test_round_trip() -> None:
    header = sign(SECRET, BODY, timestamp=1_700_000_000)
    assert verify(SECRET, header, BODY, now=1_700_000_010) == 1_700_000_000


def test_tampered_body_is_rejected() -> None:
    header = sign(SECRET, BODY, timestamp=1_700_000_000)
    with pytest.raises(SignatureError, match="mismatch"):
        verify(SECRET, header, BODY + b" ", now=1_700_000_000)


def test_wrong_secret_is_rejected() -> None:
    header = sign(SECRET, BODY, timestamp=1_700_000_000)
    with pytest.raises(SignatureError, match="mismatch"):
        verify("another-secret", header, BODY, now=1_700_000_000)


def test_skew_over_five_minutes_is_rejected() -> None:
    header = sign(SECRET, BODY, timestamp=1_700_000_000)
    with pytest.raises(SignatureError, match="clock_skew"):
        verify(SECRET, header, BODY, now=1_700_000_301)


def test_skew_within_five_minutes_is_accepted() -> None:
    header = sign(SECRET, BODY, timestamp=1_700_000_000)
    assert verify(SECRET, header, BODY, now=1_700_000_300) == 1_700_000_000


def test_missing_or_malformed_header_is_rejected() -> None:
    with pytest.raises(SignatureError, match="missing"):
        verify(SECRET, None, BODY, now=1_700_000_000)
    for header in ("", "garbage", "t=abc,v1=deadbeef", "t=1700000000"):
        with pytest.raises(SignatureError):
            verify(SECRET, header, BODY, now=1_700_000_000)
