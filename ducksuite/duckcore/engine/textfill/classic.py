"""Classic inpainting through OpenCV: Telea and Navier-Stokes.

No model and no network: these spread the colours at a hole's edge into it. They
are far faster than LaMa and suit thin holes on plain or soft backgrounds, such
as the strokes of a caption. A wide hole or a detailed background smears.
"""

from __future__ import annotations

import numpy as np

# Pixels around each hole pixel the methods read. Small keeps strokes crisp.
RADIUS = 3


class ClassicFiller:
    def __init__(self, method: str):
        import cv2

        self._inpaint = cv2.inpaint
        self._flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS

    def fill(self, area: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Fill ``mask`` (H, W bool) in ``area`` (H, W, 3 uint8). Same size out."""
        return self._inpaint(area, mask.astype(np.uint8) * 255, RADIUS, self._flag)
