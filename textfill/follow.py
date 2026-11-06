"""Keep one AI fill lined up with the camera, and reuse the pixels it reveals.

The text stays put on the screen while the picture moves under it. So one fill,
moved with the camera, can last for many frames, and as the camera moves, real
pixels that were under the text come into view and replace the model's guess.
The picture around the text decides whether the moved fill still fits. When it
stops fitting, such as when a hand crosses it, the caller makes a new fill.
"""

from __future__ import annotations

import importlib.util

import numpy as np

# Long side of the picture used to find the motion. The fill moves at full size.
TRACK_SIDE = 480
MAX_POINTS = 160
MIN_POINTS = 12
MIN_INLIERS = 0.5
# Mean change (0..255) around the text after moving the fill and matching light.
RESIDUAL_LIMIT = 10.0
# The most a fill's brightness is shifted, per channel, to match the picture.
LIGHT_LIMIT = 40.0
# Pixels this close to the text may hold its shadow, so they are not reused.
TEXT_MARGIN_PX = 4
# Motion below this many pixels reveals nothing new.
REVEAL_MIN_PX = 1.5


def problem() -> str | None:
    """Why following the camera cannot run here, or None."""
    if importlib.util.find_spec("cv2") is None:
        return "Following the camera needs the OpenCV package on this Mac."
    return None


class FollowedFill:
    """One fill of one work area, moved from its key frame to later frames."""

    def __init__(self, key_crop: np.ndarray, fill: np.ndarray, hole: np.ndarray, ring_out: np.ndarray):
        import cv2

        self.cv2 = cv2
        self.height, self.width = hole.shape
        self.hole = hole
        self.plate = fill.copy()
        # Plate pixels the model made, which a real pixel may still replace.
        self.guessed = hole.copy()
        self.around = ~ring_out
        self.scale = min(1.0, TRACK_SIDE / float(max(self.height, self.width)))
        self.key_gray = self._gray(key_crop)
        self.points = self._find_points(hole)
        self.last_moved = None

    def _gray(self, crop: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        if self.scale >= 1.0:
            return gray
        size = (max(8, int(round(self.width * self.scale))), max(8, int(round(self.height * self.scale))))
        return cv2.resize(gray, size, interpolation=cv2.INTER_AREA)

    def _find_points(self, hole: np.ndarray):
        cv2 = self.cv2
        allowed = (~hole).astype(np.uint8) * 255
        size = self.key_gray.shape[1], self.key_gray.shape[0]
        allowed = cv2.resize(allowed, size, interpolation=cv2.INTER_NEAREST)
        points = cv2.goodFeaturesToTrack(self.key_gray, MAX_POINTS, 0.01, 7, mask=allowed)
        if points is None or len(points) < MIN_POINTS:
            return None
        return points

    def _matrix(self, crop: np.ndarray) -> np.ndarray | None:
        """How the picture moved since the key frame, or None if it cannot be told."""
        if self.points is None:
            # A plain background has nothing to track, and nothing to misplace.
            return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        cv2 = self.cv2
        gray = self._gray(crop)
        flags = cv2.OPTFLOW_USE_INITIAL_FLOW if self.last_moved is not None else 0
        moved, status, _error = cv2.calcOpticalFlowPyrLK(
            self.key_gray, gray, self.points, self.last_moved,
            winSize=(21, 21), maxLevel=3, flags=flags,
        )
        if moved is None or status is None:
            return None
        good = status.ravel() == 1
        if int(good.sum()) < MIN_POINTS:
            return None
        matrix, inliers = cv2.estimateAffinePartial2D(
            self.points[good], moved[good], method=cv2.RANSAC, ransacReprojThreshold=2.0,
        )
        if matrix is None or inliers is None or float(inliers.mean()) < MIN_INLIERS:
            return None
        self.last_moved = moved
        matrix = matrix.copy()
        matrix[:, 2] /= self.scale
        return matrix

    def fill_for(self, crop: np.ndarray, hole: np.ndarray) -> np.ndarray | None:
        """The fill lined up with this frame, or None when it no longer fits."""
        matrix = self._matrix(crop)
        if matrix is None:
            return None
        cv2 = self.cv2
        size = (self.width, self.height)
        moved = cv2.warpAffine(self.plate, matrix, size, flags=cv2.INTER_LINEAR)
        whole = np.full((self.height, self.width), 255, dtype=np.uint8)
        covered = cv2.warpAffine(whole, matrix, size, flags=cv2.INTER_NEAREST) == 255
        # The fill has to reach every pixel of the text.
        if (hole & ~covered).any():
            return None
        light = np.zeros(3, dtype=np.float32)
        check = self.around & covered
        sampled = check[::4, ::4]
        if sampled.any():
            change = crop[::4, ::4][sampled].astype(np.float32) - moved[::4, ::4][sampled].astype(np.float32)
            light = np.clip(change.mean(axis=0), -LIGHT_LIMIT, LIGHT_LIMIT)
            if float(np.abs(change - light).mean()) > RESIDUAL_LIMIT:
                return None
        self._take_real_pixels(crop, matrix, light)
        out = np.clip(moved.astype(np.float32) + light, 0, 255).astype(np.uint8)
        out[~covered] = crop[~covered]
        return out

    def _take_real_pixels(self, crop: np.ndarray, matrix: np.ndarray, light: np.ndarray) -> None:
        """Replace the model's guess with pixels this frame has revealed."""
        if not self.guessed.any():
            return
        shift = max(abs(float(matrix[0, 2])), abs(float(matrix[1, 2])))
        turn = max(abs(float(matrix[0, 0]) - 1.0), abs(float(matrix[0, 1])))
        if shift < REVEAL_MIN_PX and turn * max(self.width, self.height) < REVEAL_MIN_PX:
            return
        cv2 = self.cv2
        size = (self.width, self.height)
        inverse = cv2.invertAffineTransform(matrix)
        kernel = np.ones((TEXT_MARGIN_PX * 2 + 1, TEXT_MARGIN_PX * 2 + 1), dtype=np.uint8)
        text = cv2.dilate(self.hole.astype(np.uint8), kernel) > 0
        clear = (~text).astype(np.uint8) * 255
        clear_back = cv2.warpAffine(clear, inverse, size, flags=cv2.INTER_NEAREST) == 255
        take = self.guessed & clear_back
        if not take.any():
            return
        back = cv2.warpAffine(crop, inverse, size, flags=cv2.INTER_LINEAR)
        self.plate[take] = np.clip(back[take].astype(np.float32) - light, 0, 255).astype(np.uint8)
        self.guessed[take] = False
