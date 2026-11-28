"""ImageDocument and the RGBA image conventions (REVISION_PLAN.md section 2).

Images are uint8 RGBA arrays (H, W, 4) with a binary alpha: 255 = opaque (hatched), 0 = transparent
(background, never hatched). Transparent pixels are always stored as (0, 0, 0, 0), so a whole pixel can be
compared as one value. `normalize` establishes this invariant and is applied whenever an image is stored.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

TRANSPARENT = (0, 0, 0, 0)
ALPHA_THRESHOLD = 128  # alpha >= threshold counts as opaque when binarizing


def normalize(image):
    """Copy of `image` as RGBA with binary alpha and zeroed transparent pixels. Accepts gray, RGB or RGBA."""
    image = np.asarray(image)
    if image.ndim == 2:
        image = np.stack([image] * 3, axis=-1)
    if image.shape[2] == 3:
        return np.dstack([image.astype(np.uint8), np.full(image.shape[:2], 255, np.uint8)])
    image = image.astype(np.uint8, copy=True)
    opaque = image[..., 3] >= ALPHA_THRESHOLD
    image[..., 3] = np.where(opaque, 255, 0)
    image[~opaque] = 0
    return image


def from_rgb(rgb, white_is_background=True):
    """RGB image -> RGBA; pure white becomes transparent if white_is_background."""
    rgba = normalize(rgb)
    if white_is_background:
        rgba[np.all(rgba[..., :3] == 255, axis=-1)] = 0
    return rgba


def from_rgba(rgba):
    """RGBA with arbitrary alpha -> binary alpha; kept pixels are composited over white so soft edges keep their look."""
    rgba = np.asarray(rgba, dtype=np.float32)
    a = rgba[..., 3:4] / 255
    rgb = rgba[..., :3] * a + 255 * (1 - a)
    return normalize(np.dstack([np.round(rgb), rgba[..., 3]]).astype(np.uint8))


def opaque_mask(image):
    return image[..., 3] > 0


def rgb_filled(image, fill=255):
    """RGB copy with transparent pixels set to `fill` (input for filters that need every pixel)."""
    rgb = image[..., :3].copy()
    rgb[image[..., 3] == 0] = fill
    return rgb


def with_rgb(image, rgb):
    """New RGBA image with the colours of `rgb` and the alpha of `image`."""
    return normalize(np.dstack([np.asarray(rgb, dtype=np.uint8), image[..., 3]]))


def composite(image, background=255):
    """RGB image with transparent pixels replaced by `background` (for formats without alpha)."""
    return rgb_filled(image, background)


@dataclass
class ImageDocument:
    image_matrix: np.ndarray           # (H, W, 4) uint8 RGBA, the current (edited) image
    original_image_matrix: np.ndarray  # state for "restore", set on load / keep changes
    pixel_per_mm: float
    pixel_per_mm_original: float
    center: Optional[list] = None          # hatch centre (x, y) in image pixels; None: the middle of the image
    center_shape: Optional[tuple] = None   # (H, W) of the image the centre was set for

    def __post_init__(self):
        # normalize() copies, so edits can never leak into the restore state
        self.image_matrix = normalize(self.image_matrix)
        self.original_image_matrix = normalize(self.original_image_matrix)

    def default_center(self):
        h, w = self.image_matrix.shape[:2]
        return [(w - 1) / 2, (h - 1) / 2]

    def hatch_center(self):
        """The hatch centre (x, y) in image pixels. Set for another pixel size of the image: scaled along when the
        image was only scaled (upscaling), else the middle of the image."""
        h, w = self.image_matrix.shape[:2]
        if self.center is None or self.center_shape is None:
            return self.default_center()
        h0, w0 = self.center_shape
        if (h0, w0) == (h, w):
            return [float(self.center[0]), float(self.center[1])]
        kx, ky = w / w0, h / h0
        if abs(kx - ky) <= 0.01 * kx:
            return [(self.center[0] + 0.5) * kx - 0.5, (self.center[1] + 0.5) * ky - 0.5]
        return self.default_center()

    def set_center(self, x, y):
        self.center = [float(x), float(y)]
        self.center_shape = tuple(self.image_matrix.shape[:2])
