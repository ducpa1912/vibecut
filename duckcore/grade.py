"""Local colour cubes in encoded RGB, stored as [blue, green, red, channel].

The recipe, built-in looks, LookMath and look-first composition are ported
from Editroom's ColorGrade.swift at e0cbfd2. See Licenses/Editroom-MIT.txt.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import numpy as np

SIZE = 33
MAX_BYTES = 20_000_000
SLIDERS = ("exposure", "contrast", "saturation", "temperature", "tint")
LOOKS = ("Warm film", "Golden hour", "Film print", "Teal and orange",
         "Pastel", "Bleach bypass", "Mono", "Cool night")
LUMA = np.array([.2126, .7152, .0722])
LUT_ID = re.compile(r"lut_[a-f0-9]{64}")


def normalize(settings):
    values = settings or {}
    def slider(name, lower, default):
        try:
            value = float(values.get(name, default))
        except (TypeError, ValueError) as exc:
            raise ValueError("Grade values must be finite numbers.") from exc
        if not math.isfinite(value):
            raise ValueError("Grade values must be finite numbers.")
        return round(max(lower, min(100, value)))

    look = values.get("look") or None
    if look is not None and (not isinstance(look, str) or
                             (look not in LOOKS and not LUT_ID.fullmatch(look))):
        raise ValueError("Choose a built-in look or an imported LUT.")
    return {**{key: slider(key, -100, 0) for key in SLIDERS},
            "look": look, "look_strength": slider("look_strength", 0, 100)}


def _luma(rgb):
    return (rgb @ LUMA)[..., None]


def _recipe(rgb, exposure=0, temperature=0, tint=0, shadows=(0, 0, 0),
            midtones=(0, 0, 0), highlights=(0, 0, 0), lift=(0, 0, 0),
            contrast=0, fade=0, saturation=0):
    c = rgb * 2 ** exposure + np.array([temperature * .0024, -tint * .002, -temperature * .0024])
    l = _luma(c).clip(0, 1)
    c += (1-l)*shadows + 4*l*(1-l)*midtones + l*highlights + lift
    c = (c-.5) * (1 + contrast * .012) + .5
    c = c * (1-fade) + fade
    l = _luma(c)
    return l + (c-l) * (1 + saturation / 100)


def _contrast(c, k):
    x = c.clip(0, 1)
    return (x + 2*k*(x*x*(3-2*x)-x)).clip(0, 1)


def _saturate(c, amount):
    l = _luma(c)
    return (l + amount*(c-l)).clip(0, 1)


def _split(c, shadows, highlights):
    l = _luma(c).clip(0, 1)
    return ((c + (1-l)**2 * shadows).clip(0, 1) + l*l*highlights).clip(0, 1)


def _hue_band(c, center, width, shift, saturation, value=1):
    r, g, b = np.moveaxis(c, -1, 0)
    v = c.max(axis=-1)
    d = v - c.min(axis=-1)
    den = np.where(d > 1e-6, d, 1)
    hue = np.select([r == v, g == v], [(g-b)/den, 2+(b-r)/den], default=4+(r-g)/den)
    hue = np.where(d > 1e-6, 60*hue % 360, 0)
    s = d / np.where(v > 0, v, 1)
    distance = abs((hue-center+180) % 360 - 180)
    weight = np.where(distance < width, .5+.5*np.cos(distance*np.pi/width), 0) * np.minimum(1, s*2.5)
    h = (hue + shift*weight) % 360 / 60
    s = (s * (1+(saturation-1)*weight)).clip(0, 1)
    v = (v * (1+(value-1)*weight)).clip(0, 1)
    # HSV to RGB, with the red, green and blue ramps 120 degrees apart.
    k = (h[..., None] + np.array([5, 3, 1])) % 6
    return v[..., None] * (1 - s[..., None] * np.minimum(k, 4-k).clip(0, 1))


def _look(c, name):
    if name == "Warm film":
        return _recipe(c, contrast=8, saturation=-8, temperature=18, lift=(.02, 0, -.02), fade=.03)
    if name == "Golden hour":
        return _saturate(_contrast(_split(c, (-.012, 0, .03), (.085, .04, -.06)), .08), 1.08)
    if name == "Teal and orange":
        return _recipe(c, contrast=12, saturation=10, shadows=(-.05, .01, .05), highlights=(.06, .01, -.05))
    if name == "Pastel":
        c = .14 + .86*_contrast(c.clip(0, 1)**.8, -.36)
        return _saturate(_split(c, (.03, 0, .05), (.01, 0, .012)), .8)
    if name == "Bleach bypass":
        return (_contrast(_saturate(c.clip(0, 1), .42), .42) + (-.01, 0, .008)).clip(0, 1)
    if name == "Mono":
        return _recipe(c, contrast=14, saturation=-100)
    if name == "Cool night":
        return _recipe(c, exposure=-.25, contrast=6, saturation=-15, temperature=-22)
    if name == "Film print":
        c = (c.clip(0, 1) + (.1260, .0872, .1130)).clip(0, 1)**.9273
        c = _hue_band(c, 28, 22, 4.3723, 1.1754)
        c = _hue_band(c, 110, 60, -6.7912, .8993)
        c = _hue_band(c, 210, 45, -3.0058, 1.0943)
        c = _split(c, (-.2338, -.1982, -.2908), (-.1016, -.0275, -.0710))
        c = _saturate(_contrast(c, .1846), .8248)
        return .035 + .965*_hue_band(c, 356, 20, 0, 1.0324, 1.0304)
    raise ValueError("Unknown look.")


def grid(size):
    b, g, r = np.meshgrid(*[np.linspace(0, 1, size)]*3, indexing="ij")
    return np.stack((r, g, b), axis=-1)


def _sample(table, rgb):
    pos = rgb.clip(0, 1) * (len(table)-1)
    index = np.minimum(pos.astype(int), len(table)-2)
    r, g, b = np.moveaxis(index, -1, 0)
    fr, fg, fb = np.moveaxis(pos-index, -1, 0)[..., None]
    out = np.zeros_like(pos)
    for z, wz in enumerate((1-fb, fb)):
        for y, wy in enumerate((1-fg, fg)):
            for x, wx in enumerate((1-fr, fr)):
                out += wz*wy*wx*table[b+z, g+y, r+x]
    return out


def apply(rgb, settings, user_table=None):
    g = normalize(settings)
    c = np.asarray(rgb, dtype=np.float64)
    if g["look"] and g["look_strength"]:
        looked = _look(c, g["look"]) if g["look"] in LOOKS else _sample(user_table, c)
        c = c + (looked-c) * (g["look_strength"]/100)
    return _recipe(c, exposure=g["exposure"]/50, contrast=g["contrast"]/2,
                   temperature=g["temperature"]/2, tint=g["tint"]/2,
                   saturation=g["saturation"]).clip(0, 1)


def _read(path):
    path = Path(path)
    if path.suffix.lower() != ".cube" or not path.is_file():
        raise ValueError("Choose a local .cube file.")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES+1)
    if len(data) > MAX_BYTES:
        raise ValueError("The LUT file exceeds 20 MB.")
    return data


def parse(data):
    table = None
    count = 0
    for raw in data.decode("utf-8-sig").splitlines():
        fields = raw.partition("#")[0].split()
        if not fields or fields[0] == "TITLE":
            continue
        tag = fields[0]
        if tag == "LUT_1D_SIZE":
            raise ValueError("Choose a 3D LUT. This LUT is one-dimensional.")
        if tag == "LUT_3D_SIZE":
            if len(fields) != 2 or not fields[1].isdigit() or not 2 <= int(fields[1]) <= 65 or table is not None:
                raise ValueError("Specify one LUT_3D_SIZE from 2 to 65.")
            size = int(fields[1])
            table = np.empty((size**3, 3), dtype=np.float32)
            continue
        if tag in ("DOMAIN_MIN", "DOMAIN_MAX"):
            if list(map(float, fields[1:])) != [float(tag == "DOMAIN_MAX")]*3:
                raise ValueError("Only LUT domains from 0 to 1 are supported.")
            continue
        if table is None or count >= len(table) or len(fields) != 3:
            raise ValueError("Invalid 3D cube header or sample count.")
        table[count] = fields
        count += 1
    if table is None or count != len(table) or not np.isfinite(table).all():
        raise ValueError("The LUT needs exactly size³ finite RGB triples.")
    return table.reshape(size, size, size, 3)


def _atomic(path, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
    try:
        write(tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def import_lut(path, root):
    path = Path(path)
    data = _read(path)
    parse(data)
    identifier = "lut_" + hashlib.sha256(path.name.encode() + b"\0" + data).hexdigest()
    dest = Path(root)/"luts"/identifier/path.name
    _atomic(dest, lambda tmp: tmp.write_bytes(data))
    return {"id": identifier, "name": path.name}


def list_luts(root):
    return [{"id": p.parent.name, "name": p.name} for p in sorted((Path(root)/"luts").glob("*/*"))
            if LUT_ID.fullmatch(p.parent.name) and p.is_file() and p.suffix.lower() == ".cube"]


def bake(settings, data_root):
    g = normalize(settings)
    if not g["look_strength"]:
        g["look"] = None
    if not g["look"]:
        g["look_strength"] = 100
        if not any(g[k] for k in SLIDERS):
            return None
    data = None
    digest = hashlib.sha256(b"ducksuite-grade-v1\0" + json.dumps(g, sort_keys=True).encode())
    if g["look"] and g["look"] not in LOOKS:
        files = [p for p in (Path(data_root)/"luts"/g["look"]).glob("*") if p.suffix.lower() == ".cube"]
        if len(files) != 1:
            raise ValueError("The imported LUT is missing. Import it again.")
        data = _read(files[0])
        digest.update(data)
    path = Path(data_root)/"grade-cache"/(digest.hexdigest()+".cube")
    if not path.exists():
        table = apply(grid(SIZE), g, parse(data) if data is not None else None)
        _atomic(path, lambda tmp: np.savetxt(tmp, table.reshape(-1, 3), fmt="%.9f",
                                               header=f"LUT_3D_SIZE {SIZE}", comments=""))
    return path


def payload(path):
    if path is None:
        return {"size": 0, "data": "", "hash": None}
    values = parse(_read(path)).astype("<f4", copy=False)
    return {"size": len(values), "data": base64.b64encode(values.tobytes()).decode("ascii"),
            "hash": path.stem}


def filter_for(path):
    # FFmpeg first parses the filtergraph, then parses its option values.
    escaped = str(path.resolve())
    for special in ("\\':", "\\'[],;"):
        escaped = "".join("\\" + c if c in special else c for c in escaped)
    return f"lut3d=file={escaped}:interp=tetrahedral"
