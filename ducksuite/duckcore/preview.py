"""Clean preview for one frame of an edit."""

from __future__ import annotations


def proof_layers(layers: list[dict], mode: str = "clean") -> list[dict]:
    """Layers a proof draws: blur mode turns every enabled layer into a blur.

    Off stays Off. The source layers are not mutated, and a blur proof never
    reaches the fill engine or writes a fill cache entry.
    """
    if str(mode or "clean").strip().lower() != "blur":
        return list(layers)
    return [
        {**layer, "kind": "blur"}
        for layer in layers
        if isinstance(layer, dict) and layer.get("enabled") is not False
    ]


