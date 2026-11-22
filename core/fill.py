"""Flood fill on RGBA images (P6.3). Pure numpy/OpenCV, no Qt."""
import cv2
import numpy as np

MODES = ("Regular", "Include Diagonals", "Similar Color", "Diagonals + Similar", "To Contours", "To Color", "Fill Lines")


def fill_region(image, seed, mode="Regular", tolerance=0, fill_color=None, limit_color=None, region=None, contour_mask=None):
    """Pixels reached by a flood fill from seed=(x, y). Returns a bool mask (H, W).

    Regular / Include Diagonals       same RGBA as the seed pixel (4- / 8-connected)
    Similar Color / Diagonals + Similar  RGBA distance to the seed colour <= tolerance
    To Contours                       everything up to the contour pixels (contour_mask)
    To Color                          everything up to pixels of limit_color
    Fill Lines                        seed colour, but only where fill_color lies within `tolerance` pixels
    region: optional bool mask the fill must stay inside (active mask / background of all masks).
    """
    x, y = seed
    image = np.asarray(image)
    target = image[y, x].astype(np.int32)
    if mode in ("Regular", "Include Diagonals"):
        allowed = np.all(image == target, axis=-1)
    elif mode in ("Similar Color", "Diagonals + Similar"):
        diff = image.astype(np.int32) - target
        allowed = np.einsum("ijk,ijk->ij", diff, diff) <= tolerance * tolerance
    elif mode == "To Contours":
        if contour_mask is None or not contour_mask.any():
            return np.zeros(image.shape[:2], dtype=bool)  # no contours: nothing to fill up to
        allowed = ~contour_mask
    elif mode == "To Color":
        allowed = ~np.all(image == np.asarray(limit_color), axis=-1)
    elif mode == "Fill Lines":
        size = 2 * int(tolerance) + 1
        near_fill = cv2.dilate(np.all(image == np.asarray(fill_color), axis=-1).astype(np.uint8), np.ones((size, size), np.uint8))
        allowed = np.all(image == target, axis=-1) & near_fill.astype(bool)
    else:
        raise ValueError(f"Unknown fill mode {mode!r}")
    if region is not None:
        allowed &= region.astype(bool)  # B32: also for the colour-independent modes
    allowed[y, x] = True  # the clicked pixel is always filled
    connectivity = 8 if mode in ("Include Diagonals", "Diagonals + Similar") else 4
    _, labels = cv2.connectedComponents(allowed.astype(np.uint8), connectivity=connectivity)
    return labels == labels[y, x]
