import base64
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from duckcore import edits, grade, media, render
from duckcore.main import _proof_cache_key, create_app
from duckcore.store import ProjectStore


def chart(path):
    # 4,913 encoded RGB patches. Tile blue slices vertically and vary red across each row.
    pixels = np.rint(255*grade.grid(17)).astype(np.uint8).reshape(289, 17, 3)
    Image.fromarray(pixels).save(path)
    return pixels


def ffmpeg_rgb(path, chain, ffmpeg=None):
    cmd = [ffmpeg or media.ffmpeg(), "-v", "error", "-i", str(path)]
    if chain:
        cmd.extend(["-vf", chain])
    data = subprocess.check_output(cmd + ["-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    return np.frombuffer(data, np.uint8).reshape(289, 17, 3)


def test_legacy_and_neutral(tmp_path):
    old = {"exposure": 0, "saturation": 0, "contrast": 0, "temperature": 0}
    path = edits.edit_path(tmp_path, "prj_old", "ed_old")
    path.write_text(json.dumps({"cut": {"grade": old}}))
    assert edits.get_edit(tmp_path, "prj_old", "ed_old")["cut"]["grade"] == old
    assert grade.bake(old, tmp_path) is None
    assert grade.bake({"look": "Mono", "look_strength": 0}, tmp_path) is None
    assert not (tmp_path/"grade-cache").exists()
    defaults = edits.set_cut({})["cut"]["grade"]
    assert (defaults["tint"], defaults["look"], defaults["look_strength"]) == (0, None, 100)
    assert grade.normalize({"tint": -140, "look_strength": 140})["tint"] == -100
    with pytest.raises(ValueError):
        grade.normalize({"look": "../../invalid"})


@pytest.mark.parametrize("data", [
    b"LUT_1D_SIZE 4", b"LUT_3D_SIZE 1", b"LUT_3D_SIZE 66", b"LUT_3D_SIZE 2\n0 0 0",
    b"LUT_3D_SIZE 2\n" + b"NaN 0 0\n"*8, b"LUT_3D_SIZE 2\n" + b"inf 0 0\n"*8,
    b"DOMAIN_MIN 0.1 0 0\n", b"DOMAIN_MAX 2 2 2\n", b"LUT_3D_SIZE 2\n"*2,
])
def test_reject_bad_cube(tmp_path, data):
    path = tmp_path/"bad.cube"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        grade.import_lut(path, tmp_path)
    assert grade.list_luts(tmp_path) == []


def test_limit(tmp_path):
    f = tmp_path/"big.cube"
    with f.open("wb") as stream:
        stream.truncate(grade.MAX_BYTES+1)
    with pytest.raises(ValueError, match="20 MB"):
        grade.import_lut(f, tmp_path)


def test_import_and_cache(tmp_path):
    f = tmp_path/"My look.CUBE"
    values = grade.grid(2)[..., ::-1]
    np.savetxt(f, values.reshape(-1, 3), header="DOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\nLUT_3D_SIZE 2", comments="")
    saved = grade.import_lut(f, tmp_path)
    f.unlink()
    assert grade.list_luts(tmp_path) == [saved]
    settings = {"look": saved["id"]}
    first = grade.bake(settings, tmp_path)
    stamp = first.stat().st_mtime_ns
    assert grade.bake(settings, tmp_path).stat().st_mtime_ns == stamp
    table = grade.parse(first.read_bytes())
    np.testing.assert_allclose(table, grade.grid(33)[..., ::-1], atol=1e-6)
    tinted = grade.bake({**settings, "tint": 30}, tmp_path)
    assert first != tinted
    copied = tmp_path/"luts"/saved["id"]/saved["name"]
    copied.write_bytes(copied.read_bytes()+b"\n# new file revision")
    assert grade.bake(settings, tmp_path) != first
    copied.unlink()
    with pytest.raises(ValueError, match="missing"):
        grade.bake(settings, tmp_path)


def test_looks_and_filter_order(tmp_path):
    cubes = [grade.bake({"look": name}, tmp_path) for name in grade.LOOKS]
    assert len(set(cubes)) == 8
    mixed = grade.apply([[.5, .5, .5]], {"look": "Mono", "look_strength": 0})
    np.testing.assert_allclose(mixed, [[.5, .5, .5]])
    meta = {"width": 320, "height": 240}
    edit = {"cut": {"aspect": "16:9", "enhance": {"enabled": True, "sharpen": 60}}}
    chain = render._scale_filter(meta, 30, edit, cube=cubes[0])[2]
    assert chain.index("unsharp=") < chain.index("lut3d=file=") < chain.index("pad=")
    assert ":interp=tetrahedral" in chain and not any(f in chain for f in ("exposure=", "colorbalance=", "eq="))
    assert _proof_cache_key({}, edit, [], {}, "clean", cubes[0]) != _proof_cache_key({}, edit, [], {}, "clean", cubes[1])


@pytest.mark.parametrize("settings", [{}, {"exposure": 50}, {"temperature": -60, "tint": 30},
                                      {"look": "Teal and orange", "look_strength": 70}])
def test_chart_parity(tmp_path, settings):
    path = tmp_path/"chart.png"
    pixels = chart(path)
    cube = grade.bake(settings, tmp_path/"quote's, space: [test]")
    actual = ffmpeg_rgb(path, grade.filter_for(cube) if cube else None)
    expected = np.rint(255*grade.apply(pixels/255, settings)).astype(int)
    assert np.abs(actual.astype(int)-expected).max() <= 2


def test_routes(tmp_path):
    pic = tmp_path/"chart.png"
    source = chart(pic)
    pid = ProjectStore(tmp_path).create("Chart", pic)["id"]
    edit = edits.create_full(pid, {"meta": {"duration": 1}}, tmp_path)
    url = f"/api/projects/{pid}/edits/{edit['id']}"
    client = TestClient(create_app("token", tmp_path))
    auth = {"Authorization": "Bearer token"}
    assert client.get(url+"/grade/cube").status_code == 401
    assert client.get(url+"/grade/cube", headers=auth).json() == {"size": 0, "data": "", "hash": None}
    assert client.get("/api/grade/looks", headers=auth).json()["looks"] == list(grade.LOOKS)
    lut = tmp_path/"mono.cube"
    np.savetxt(lut, grade.grid(2).reshape(-1, 3), header="LUT_3D_SIZE 2", comments="")
    saved = client.post("/api/grade/luts", headers=auth, json={"path": str(lut)}).json()
    assert client.get("/api/grade/looks", headers=auth).json()["luts"] == [saved]
    settings = {"look": saved["id"], "tint": 30}
    assert client.patch(url+"/cut", headers=auth, json={"grade": settings}).status_code == 200
    result = client.get(url+"/grade/cube", headers=auth).json()
    table = np.frombuffer(base64.b64decode(result["data"]), dtype="<f4").reshape(33, 33, 33, 3)
    path = tmp_path/"grade-cache"/(result["hash"]+".cube")
    np.testing.assert_array_equal(grade.parse(path.read_bytes()), table)
    still = client.get(url+"/grade/still?t=token&time=0")
    assert still.status_code == 200
    rgb = np.asarray(Image.open(io.BytesIO(still.content)))
    assert np.array_equal(rgb, ffmpeg_rgb(pic, grade.filter_for(path)))
    assert not np.array_equal(rgb, source)


def test_local_file_picker_and_graded_filmstrip(tmp_path):
    source = tmp_path / "chart.png"
    chart(source)
    pid = ProjectStore(tmp_path).create("Chart", source)["id"]
    edit = edits.create_full(pid, {"meta": {"duration": 1}}, tmp_path)
    url = f"/api/projects/{pid}/edits/{edit['id']}"
    auth = {"Authorization": "Bearer token"}
    cube = tmp_path / "user.cube"
    np.savetxt(cube, grade.grid(2)[..., ::-1].reshape(-1, 3), header="LUT_3D_SIZE 2", comments="")
    with TestClient(create_app("token", tmp_path)) as client:
        route = "/api/grade/luts/file"
        assert client.post(route, params={"name":cube.name}, content=b"x").status_code == 401
        assert client.post(route, params={"name":"../bad.cube"}, headers=auth,
                           content=cube.read_bytes()).status_code == 400
        lut = client.post(route, params={"name":cube.name}, headers=auth, content=cube.read_bytes())
        assert lut.status_code == 200
        client.patch(url+"/cut", headers=auth, json={"grade":{"look":lut.json()["id"]}}).raise_for_status()
        response = client.get(url+"/grade/still?t=token&w=96")
        response.raise_for_status()
        assert Image.open(io.BytesIO(response.content)).width == 96
        assert client.get(url+"/grade/still?t=token&w=96").content == response.content
        assert client.get(url+"/grade/still?t=token&w=9999").status_code == 400
