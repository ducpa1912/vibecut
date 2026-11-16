"""Loop 26: pack integrity, FFmpeg source offer, fill repair and import copy."""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
from pathlib import Path

import pytest

from duckcore import import_errors, licenses, packs

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 1. packs

def test_every_pack_file_has_an_exact_size_and_a_publisher_digest_or_none():
    unhashed = []
    for pack in packs.PACKS:
        for item in packs._files(pack):
            assert isinstance(item["size_bytes"], int) and item["size_bytes"] > 0
            sha256 = item.get("sha256") or ""
            git_sha1 = item.get("git_sha1") or ""
            assert not sha256 or re.fullmatch(r"[0-9a-f]{64}", sha256)
            assert not git_sha1 or re.fullmatch(r"[0-9a-f]{40}", git_sha1)
            if not (sha256 or git_sha1):
                unhashed.append(item["filename"])
            if "huggingface.co" in item["url"]:
                assert "/resolve/main/" not in item["url"], "pin Hugging Face files to a revision"
    # The two Kokoro files have no publisher hash (stated in the review).
    assert sorted(unhashed) == ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


def _fake_pack(monkeypatch, payload: bytes, **item):
    pack = {
        "id": "t", "name": "T", "purpose": "fill", "detail": "", "license": "x",
        "filename": "model.bin", "size_bytes": len(payload), "url": "https://example.invalid/m",
        **item,
    }
    monkeypatch.setattr(packs, "PACKS", (pack,))
    return pack


def _serve(monkeypatch, body: bytes):
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(url, timeout=0):
        calls.append(url)
        return Response(body)

    monkeypatch.setattr(packs.urllib.request, "urlopen", urlopen)
    return calls


def test_right_file_installs(tmp_path, monkeypatch):
    good = b"duck-model"
    pack = _fake_pack(monkeypatch, good, sha256=hashlib.sha256(good).hexdigest())
    _serve(monkeypatch, good)
    packs._download(tmp_path, pack)
    assert packs._PROGRESS["t"]["error"] == ""
    assert packs.installed_path(tmp_path, "t") is not None


def test_one_changed_byte_is_rejected_and_deleted(tmp_path, monkeypatch):
    good = b"duck-model"
    pack = _fake_pack(monkeypatch, good, sha256=hashlib.sha256(good).hexdigest())
    _serve(monkeypatch, b"duck-modeL")
    packs._download(tmp_path, pack)
    folder = tmp_path / "models" / "packs" / "t"
    assert packs._PROGRESS["t"]["error"] == packs.DAMAGED
    assert list(folder.iterdir()) == []
    assert packs.installed_path(tmp_path, "t") is None


def test_short_file_is_rejected_even_without_a_hash(tmp_path, monkeypatch):
    pack = _fake_pack(monkeypatch, b"0123456789", sha256="")
    _serve(monkeypatch, b"012345678")  # one byte short
    packs._download(tmp_path, pack)
    assert packs._PROGRESS["t"]["error"] == packs.DAMAGED
    assert list((tmp_path / "models" / "packs" / "t").iterdir()) == []


def test_installed_needs_the_exact_size(tmp_path, monkeypatch):
    _fake_pack(monkeypatch, b"x" * 1000, sha256="")
    folder = tmp_path / "models" / "packs" / "t"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"x" * 990)  # 99 %: accepted before loop 26
    assert packs.installed_path(tmp_path, "t") is None
    (folder / "model.bin").write_bytes(b"x" * 1000)
    assert packs.installed_path(tmp_path, "t") == folder


def test_installed_hash_is_checked(tmp_path, monkeypatch):
    body = b"correct"
    pack = _fake_pack(monkeypatch, body, sha256=hashlib.sha256(body).hexdigest())
    folder = tmp_path / "models" / "packs" / "t"
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"changed")
    assert packs.installed_path(tmp_path, "t") is None
    (folder / "model.bin").write_bytes(body)
    assert packs.installed_path(tmp_path, "t") == folder


def test_git_blob_sha1_is_checked(tmp_path):
    body = b'{"a": 1}\n'
    blob = hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()
    path = tmp_path / "config.json"
    path.write_bytes(body)
    assert packs.verify_file(path, {"size_bytes": len(body), "git_sha1": blob})
    path.write_bytes(b'{"a": 2}\n')
    assert not packs.verify_file(path, {"size_bytes": len(body), "git_sha1": blob})


def test_network_failure_says_try_again(tmp_path, monkeypatch):
    pack = _fake_pack(monkeypatch, b"abc", sha256="")

    def urlopen(url, timeout=0):
        raise OSError("connection reset")

    monkeypatch.setattr(packs.urllib.request, "urlopen", urlopen)
    packs._download(tmp_path, pack)
    assert packs._PROGRESS["t"]["error"] == packs.STOPPED
    assert "connection reset" in packs._PROGRESS["t"]["detail"]


# ---------------------------------------------------------------- 2. FFmpeg offer

def test_source_offer_matches_the_build_script_and_the_file():
    script = (ROOT / "scripts" / "build-ffmpeg-lgpl.sh").read_text()
    start = script.index('PKG_CONFIG_PATH="/opt/homebrew/opt/dav1d')
    end = script.index("\nmake ", start)
    assert script[start:end].strip() == licenses.FFMPEG_CONFIGURE.strip()
    assert f'FFMPEG_VERSION:-{licenses.FFMPEG_VERSION}' in script
    offer = licenses.FFMPEG_SOURCE_OFFER
    assert f"ffmpeg-{licenses.FFMPEG_VERSION}.tar.xz" in offer
    assert "three years" in offer and "<contact address>" in offer
    assert (ROOT / "Licenses" / "FFmpeg-SOURCE.txt").read_text() == offer


def test_source_offer_route(tmp_path):
    from fastapi.testclient import TestClient
    from duckcore.main import create_app

    client = TestClient(create_app("t", tmp_path))
    assert client.get("/api/licenses/ffmpeg-source").status_code == 401
    body = client.get("/api/licenses/ffmpeg-source", headers={"Authorization": "Bearer t"}).json()
    assert body["version"] == licenses.FFMPEG_VERSION
    assert body["text"] == licenses.FFMPEG_SOURCE_OFFER


def test_settings_shows_the_offer_line():
    source = (ROOT / "static" / "duck" / "app.js").read_text()
    assert f"FFmpeg {licenses.FFMPEG_VERSION} · LGPL 2.1" in source
    assert 'data-action="ffmpeg-source"' in source
    assert "action === 'ffmpeg-source'" in source


# ---------------------------------------------------------------- 4. fill repair

def test_fill_repair_line_per_engine():
    source = (ROOT / "static" / "duck" / "app.js").read_text()
    repair = re.search(r"function fillRepairText\(kind\) \{.*?\n\}", source, re.S).group()
    status = re.search(r"function fillStatusText\(\) \{.*?\n\}", source, re.S).group()
    subprocess.run(["node", "-e", repair + status + """
const assert = require('node:assert/strict');
assert.match(fillRepairText('builtin'), /reinstall DuckSuite/);
assert.match(fillRepairText('cpu'), /Remove .*CPU fill engine.*Download it again/);
assert.match(fillRepairText('user'), /Clear on Your fill model.*Choose the folder again/);
let state = {engine: {fill: {ready: false, problem: 'lama_fp32.onnx is missing.'}}};
assert.equal(fillStatusText(), 'lama_fp32.onnx is missing. Next step: reinstall DuckSuite to restore the built-in fill files.');
state = {engine: {fill: {ready: true}}};
assert.equal(fillStatusText(), 'Local fill');
for (const kind of ['builtin', 'cpu', 'user']) assert.doesNotMatch(fillRepairText(kind), /lama|LaMa|onnx/i);
"""], check=True)
    assert "fillRepairText('cpu')" in source and "fillRepairText('user')" in source


# ---------------------------------------------------------------- 5. import copy

MAPPED = [
    ("ffmpeg frame read failed.\n[h264 @ 0x7f8] error while decoding", import_errors.UNREADABLE),
    ("Could not read a frame from this source.", import_errors.UNREADABLE),
    ("ffprobe is not installed or bundled.", "Reinstall DuckSuite"),
    ("[mov,mp4 @ 0x1234abcd] moov atom not found", "incomplete or damaged"),
    ("source.mov: Invalid data found when processing input", "incomplete or damaged"),
    ("Decoder (codec prores_raw) not found for input stream #0:0", "format DuckSuite cannot read"),
    ("Unsupported codec with id 0 for input stream 1", "format DuckSuite cannot read"),
    ("Output file #0 does not contain any stream", "no video picture"),
    ("The new clip does not match the master streams.", "differs from the project"),
    ("ffmpeg could not join the videos. Error opening output file", "could not be joined"),
    ("Could not read the video durations.", "how long this video is"),
    ("The joined video has no duration.", "how long this video is"),
    ("Scene detection failed: list index out of range", "find the scenes"),
    ("The Check result is unreadable.", "Run Check again"),
    ("The upload failed: Connection reset by peer", "could not be copied"),
    ("The upload failed: [Errno 28] No space left on device", "free disk space"),
    ("The read could not start: boom", "could not start reading"),
]


@pytest.mark.parametrize("technical,expected", MAPPED)
def test_each_technical_message_maps_to_a_creator_sentence(technical, expected):
    message = import_errors.creator_message(technical)
    assert expected in message
    assert "ffmpeg" not in message.lower() and "errno" not in message.lower()
    assert message.endswith(".")


def test_file_access_errors_map_to_creator_copy():
    for text in ("Permission denied", "read-only file system", "/Users/me/video.mov: No such file or directory"):
        message = import_errors.creator_message(text)
        assert message != text
        assert message.endswith(".")


@pytest.mark.parametrize("plain", [
    "Use MP4, MOV or M4V.",
    "Wait for Check to finish first.",
    "The video is larger than 8 GB.",
    "That video is already this project's source.",
])
def test_plain_messages_pass_through(plain):
    assert import_errors.creator_message(plain) == plain


@pytest.mark.parametrize("unknown", [
    "Traceback (most recent call last): KeyError 'x'",
    "subprocess returned non-zero exit status 1",
    "/Users/someone/Library/x.mov: weird failure\nmore",
    "",
])
def test_unknown_technical_text_falls_back(unknown):
    assert import_errors.creator_message(unknown) == import_errors.FALLBACK


def test_upload_route_shows_the_creator_sentence(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from duckcore.main import create_app
    from duckcore import store as store_module

    def broken(self, name, source):
        raise ValueError("[mov,mp4 @ 0xdeadbeef] moov atom not found")

    monkeypatch.setattr(store_module.ProjectStore, "create", broken)
    client = TestClient(create_app("t", tmp_path))
    response = client.post(
        "/api/projects/upload", content=b"not a video",
        headers={"Authorization": "Bearer t", "x-filename": "clip.mp4"},
    )
    assert response.status_code == 400
    assert "incomplete or damaged" in response.json()["detail"]
    assert "moov" not in response.json()["detail"]


def test_append_job_failure_keeps_the_detail(monkeypatch):
    from duckcore import append

    def fail(*args, **kwargs):
        raise append.AppendError("ffmpeg could not join the videos. Conversion failed!")

    monkeypatch.setattr(append, "append_locked", fail)
    job_id = "job-test"
    append._JOBS[job_id] = {"id": job_id, "state": "queued"}
    append._run_job(job_id, "p", "/nowhere.mp4", "full", None, Path("/nowhere"), None, None, False)
    job = append._JOBS.pop(job_id)
    assert job["state"] == "failed"
    assert "could not be joined" in job["error"]
    assert "Conversion failed" in job["detail"]
