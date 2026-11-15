"""ImageDocument: one image in the image list. The single source of truth for its pixels and pixel size."""
from dataclasses import dataclass

import numpy as np


@dataclass
class ImageDocument:
    image_matrix: np.ndarray           # (H, W, 3) uint8, the current (edited) image
    original_image_matrix: np.ndarray  # state for "restore", set on load / keep changes
    pixel_per_mm: float
    pixel_per_mm_original: float

    def __post_init__(self):
        # edits must never leak into the restore state
        if self.original_image_matrix is self.image_matrix:
            self.original_image_matrix = self.image_matrix.copy()
