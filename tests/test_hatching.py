"""core.hatching unit tests (no Qt). The patterns themselves are covered by the golden files."""
import numpy as np

from core import hatching


def test_label_colors_sorts_bright_to_dark_and_skips_transparent():
    img = np.array([[[10, 10, 10], [-1, -1, -1]], [[200, 0, 0], [10, 10, 10]]], np.int16)
    labels, colors = hatching.label_colors(img)
    assert colors == [(200, 0, 0), (10, 10, 10)]
    assert labels.tolist() == [[1, -1], [0, 1]]


def test_label_colors_all_transparent():
    labels, colors = hatching.label_colors(np.full((2, 2, 3), -1, np.int16))
    assert colors == [] and (labels == -1).all()
