"""LaMa image fill through ONNX Runtime.

Model: ``lama_fp32.onnx`` from Carve/LaMa-ONNX (Apache 2.0), a port of
big-lama. Inputs ``image`` [1,3,H,W] in 0..1 and ``mask`` [1,1,H,W] (1 = fill);
output ``output`` [1,3,H,W] in 0..255.

The file declares H and W as 512, but the network has no fixed size. The session
loads a copy with that declaration removed, so a strip of text runs as a strip
and not as a square that is mostly padding. The time follows the pixels.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 512
# The network halves its input four times, and needs some picture to read.
# An input that is not a multiple of 16 makes the FFC skip join fail with a
# 62-by-63 broadcast error, so round every run size up to 16.
STEP = 16
MIN_SIDE = 64
MODEL_FILE = "lama_fp32.onnx"

# Protobuf wire types and the fields walked to reach an input's dimensions.
_VARINT, _LEN = 0, 2
_GRAPH, _INPUT, _OUTPUT, _VALUE_INFO = 7, 11, 12, 13


def _providers() -> list[str]:
    # CoreML takes only about half of this graph, in 585 pieces, so plain CPU
    # is the default. VIBECUT_FILL_LAMA_PROVIDER=coreml tries it first.
    choice = (os.environ.get("VIBECUT_FILL_LAMA_PROVIDER") or "cpu").strip().lower()
    if choice == "coreml":
        return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def _varint(data: memoryview, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, at
        shift += 7


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _fields(data: memoryview):
    """Yield (field, wire type, value, the field's bytes) for one message."""
    at = 0
    while at < len(data):
        start = at
        key, at = _varint(data, at)
        field, wire = key >> 3, key & 7
        if wire == _VARINT:
            value, at = _varint(data, at)
        elif wire == _LEN:
            size, at = _varint(data, at)
            value = data[at:at + size]
            at += size
        elif wire == 1:
            value = data[at:at + 8]
            at += 8
        elif wire == 5:
            value = data[at:at + 4]
            at += 4
        else:
            raise ValueError(f"Unknown protobuf wire type {wire}.")
        yield field, wire, value, data[start:at]


def _len_field(field: int, parts: list) -> list:
    size = sum(len(part) for part in parts)
    return [_encode_varint(field << 3 | _LEN), _encode_varint(size), *parts]


def _free_dimensions(shape: memoryview, name: str) -> list:
    """TensorShapeProto with its third and fourth dimensions named, not sized."""
    parts: list = []
    index = 0
    for field, _wire, _value, raw in _fields(shape):
        if field == 1:
            index += 1
            if index in (3, 4):
                label = f"{name}_{index}".encode("ascii")
                parts += _len_field(1, _len_field(2, [label]))
                continue
        parts.append(raw)
    return parts


def _rewrite_value_info(info: memoryview) -> list:
    """ValueInfoProto (name, type, tensor type, shape) with a free height and width."""
    name = "dim"
    parts: list = []
    for field, wire, value, raw in _fields(info):
        if field == 1 and wire == _LEN:
            name = bytes(value).decode("utf-8", "replace")
        if field != 2:
            parts.append(raw)
            continue
        type_parts: list = []
        for type_field, _w, type_value, type_raw in _fields(value):
            if type_field != 1:
                type_parts.append(type_raw)
                continue
            tensor_parts: list = []
            for tensor_field, _t, tensor_value, tensor_raw in _fields(type_value):
                if tensor_field == 2:
                    tensor_parts += _len_field(2, _free_dimensions(tensor_value, name))
                else:
                    tensor_parts.append(tensor_raw)
            type_parts += _len_field(1, tensor_parts)
        parts += _len_field(2, type_parts)
    return parts


def free_input_size(model: bytes) -> bytes:
    """The model bytes with no fixed height or width on its inputs and outputs."""
    data = memoryview(model)
    parts: list = []
    for field, _wire, value, raw in _fields(data):
        if field != _GRAPH:
            parts.append(raw)
            continue
        graph: list = []
        for graph_field, _w, graph_value, graph_raw in _fields(value):
            if graph_field in (_INPUT, _OUTPUT):
                graph += _len_field(graph_field, _rewrite_value_info(graph_value))
            elif graph_field != _VALUE_INFO:
                # Inner sizes recorded for 512 would conflict with any other size.
                graph.append(graph_raw)
        parts += _len_field(_GRAPH, graph)
    return b"".join(parts)


def fit(height: int, width: int) -> tuple[int, int]:
    """Size (h, w) that fits inside SIZE x SIZE and keeps the aspect."""
    scale = SIZE / float(max(height, width))
    return (
        max(1, min(SIZE, int(round(height * scale)))),
        max(1, min(SIZE, int(round(width * scale)))),
    )


def input_size(fit_h: int, fit_w: int, flexible: bool) -> tuple[int, int]:
    """The (h, w) the network runs at for a picture of this fitted size."""
    if not flexible:
        return SIZE, SIZE

    def rounded(value: int) -> int:
        return max(MIN_SIDE, (value + STEP - 1) // STEP * STEP)

    return rounded(fit_h), rounded(fit_w)


def run_units(height: int, width: int) -> float:
    """One run's work on an area of this size, as a share of a full 512 square."""
    run_h, run_w = input_size(*fit(height, width), True)
    return run_h * run_w / float(SIZE * SIZE)


def fit_images(area: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int]:
    """The picture and hole at the size an engine reads, and that (h, w)."""
    height, width = mask.shape
    fit_h, fit_w = fit(height, width)
    image = np.asarray(
        Image.fromarray(area).resize((fit_w, fit_h), Image.BICUBIC),
        dtype=np.uint8,
    )
    small = np.asarray(
        Image.fromarray(mask.astype(np.uint8) * 255).resize((fit_w, fit_h), Image.BILINEAR),
    ) > 0
    return image, small, fit_h, fit_w


def prepare_feed(area: np.ndarray, mask: np.ndarray, flexible: bool = True):
    """The picture and hole padded to a size LaMa runs at, and the size before it."""
    image, small, fit_h, fit_w = fit_images(area, mask)
    run_h, run_w = input_size(fit_h, fit_w, flexible)
    pad = ((0, run_h - fit_h), (0, run_w - fit_w))
    image = np.pad(image, pad + ((0, 0),), mode="edge")
    small = np.pad(small, pad, mode="constant")
    return image, small, fit_h, fit_w


def restore(result: np.ndarray, fit_h: int, fit_w: int, height: int, width: int) -> np.ndarray:
    """An engine's picture back at the work area's size, with its padding gone."""
    return np.asarray(
        Image.fromarray(result[:fit_h, :fit_w]).resize((width, height), Image.BICUBIC),
        dtype=np.uint8,
    )


class LamaFiller:
    def __init__(self, model_path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.flexible = False
        try:
            model = free_input_size(Path(model_path).read_bytes())
            self.session = ort.InferenceSession(
                model, sess_options=options, providers=_providers(),
            )
            self.flexible = True
        except Exception:  # noqa: BLE001 - the file as it is still works at 512.
            self.session = ort.InferenceSession(
                str(model_path), sess_options=options, providers=_providers(),
            )
        self.provider = self.session.get_providers()[0]

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Fill ``mask`` (H, W bool) in ``area`` (H, W, 3 uint8). Same size out."""
        height, width = mask.shape
        image, small, fit_h, fit_w = prepare_feed(area, mask, self.flexible)
        feed_image = (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        feed_mask = small.astype(np.float32)[None, None]
        result = self.session.run(None, {"image": feed_image, "mask": feed_mask})[0][0]
        result = np.clip(result.transpose(1, 2, 0), 0, 255).astype(np.uint8)
        return restore(result, fit_h, fit_w, height, width)
