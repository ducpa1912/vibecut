import pytest

from duckcore import packs
from duckcore.engine import stt


@pytest.mark.parametrize(("language", "expected"), [("vi-VN", "vi"), ("", "auto")])
def test_command(language, expected):
    cmd = stt._whisper_args("runner", "sample.wav", "weights.bin", "out", language, ["Hà Nội"])
    assert cmd == ["runner", "-m", "weights.bin", "-f", "sample.wav", "-l", expected,
                   "-ojf", "-of", "out", "--prompt", "Hà Nội"]
    assert "--prompt" not in stt._whisper_args("runner", "in", "model", "out", language, None)


def test_full_json_word_timing():
    data = {"result": {"language": "vi"}, "transcription": [
        {"text": " Xin chào!", "offsets": {"from": 100, "to": 1500}, "tokens": [
            {"text": "[_BEG_]", "p": 0.99},
            {"text": " Xin", "p": 0.8, "offsets": {"from": 100, "to": 500}},
            {"text": " ch", "p": 0.9, "offsets": {"from": 500, "to": 700}},
            {"text": "ào!", "p": 0.8, "offsets": {"from": 700, "to": 1500}},
        ]}]}
    result = stt._cpp_payload(data)
    assert result["language"] == "vi"
    assert [(w["w"], w["start"], w["end"]) for w in result["words"]] == [
        ("Xin", .1, .5), ("chào!", .5, 1.5)]


def test_old_pack_update_preserves_old_files(tmp_path, monkeypatch):
    entry = dict(packs._entry("speech-whisper"), size_bytes=4)
    monkeypatch.setattr(packs, "PACKS", [entry])
    folder = packs._folder(tmp_path, entry)
    old = folder / "weights.safetensors"
    old.write_bytes(b"previous")
    row, = packs.status(tmp_path)
    assert row["needs_update"] and not row["installed"] and "update" in row["detail"]
    (folder / packs.SPEECH_WEIGHTS).write_bytes(b"lmgg")
    assert stt._weights(tmp_path) == folder / packs.SPEECH_WEIGHTS
    packs.remove(tmp_path, "speech-whisper")
    assert old.read_bytes() == b"previous"


def test_status_rejects_data_root_runner(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pack = root / "models/packs/speech-whisper"
    pack.mkdir(parents=True)
    rogue = pack / "whisper-cli"
    rogue.touch(mode=0o755)
    monkeypatch.setenv("PATH", str(pack))
    monkeypatch.delenv("DUCK_HELPER_DIR", raising=False)
    assert stt._whisper_binary(root) is None
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    binary = helpers / "whisper-cli"
    binary.symlink_to(rogue)
    monkeypatch.setenv("DUCK_HELPER_DIR", str(helpers))
    assert stt.whisper_problem(root) == "Missing speech helper and speech weights."
    binary.unlink()
    binary.touch(mode=0o755)
    assert stt.whisper_problem(root) == "Missing speech weights."
    monkeypatch.setattr(stt, "_weights", lambda _: pack / "data.bin")
    assert not stt.whisper_problem(root)
    binary.unlink()
    assert stt.whisper_problem(root) == "Missing speech helper."


def test_frozen_sidecar_ignores_host_runner(tmp_path, monkeypatch):
    app = tmp_path / "DuckSuite.app"
    helpers = app / "Contents/Resources/Helpers"
    helpers.mkdir(parents=True)
    monkeypatch.setattr(stt.sys, "frozen", True, raising=False)
    monkeypatch.setattr(stt.sys, "executable", str(app / "Contents/Resources/duckcore/duckcore"))
    (tmp_path / "whisper-cli").touch(mode=0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("DUCK_HELPER_DIR", str(tmp_path))
    assert stt._whisper_binary() is None
    binary = helpers / "whisper-cli"
    binary.touch(mode=0o755)
    assert stt._whisper_binary() == str(binary.resolve())


def test_engine_status_updates_as_pack_changes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from duckcore.main import create_app

    entry = dict(packs._entry("speech-whisper"), size_bytes=4)
    monkeypatch.setattr(packs, "PACKS", [entry])
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    monkeypatch.setenv("DUCK_HELPER_DIR", str(helpers))
    root = tmp_path / "scratch"
    with TestClient(create_app("test", root)) as client:
        def speech():
            response = client.get("/api/engine", headers={"Authorization": "Bearer test"})
            response.raise_for_status()
            return response.json()["speech"]

        assert not speech()["whisper"]
        (helpers / "whisper-cli").touch(mode=0o755)
        assert speech()["whisper_problem"] == "Missing speech weights."
        weights = packs._folder(root, entry) / packs.SPEECH_WEIGHTS
        weights.write_bytes(b"lmgg")
        assert speech()["whisper"]
        weights.unlink()
        assert not speech()["whisper"]
