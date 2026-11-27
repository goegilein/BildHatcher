"""Open contours (gaps in the cut toolpath): detection, gap bridging and the closed "shapes" mode."""
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image
from PyQt6 import QtWidgets

from core import contours as C
from test_characterization import load_image

TEST_IMAGE = Path(__file__).parent / "Test_contour.png"  # 6 motifs; Canny loses pixels at almost every sharp corner


@pytest.fixture
def motifs():
    return np.asarray(Image.open(TEST_IMAGE).convert("RGBA"))


def _canny(rgba):
    rgb = rgba[..., :3].copy()
    rgb[rgba[..., 3] == 0] = 255
    return cv2.Canny(rgb, 50, 150)


def test_closed_square_is_not_open():
    square = np.array([[5, 5], [14, 5], [14, 14], [5, 14]])
    assert not C.is_open(square)
    assert C.find_open_contours([square]) == []


def test_traced_open_line_is_open_with_both_ends():
    edges = np.zeros((20, 30), np.uint8)
    cv2.line(edges, (3, 10), (25, 10), 255, 1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    [(index, gaps)] = C.find_open_contours(contours)
    assert sorted(gaps) == [(3, 10), (25, 10)]


def test_bridge_gaps_closes_a_ring_with_a_gap():
    edges = np.zeros((40, 40), np.uint8)
    cv2.rectangle(edges, (5, 5), (30, 30), 255, 1)
    edges[5, 15:17] = 0  # 2 px gap
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert len(C.find_open_contours(contours)) == 1
    bridged, n = C.bridge_gaps(edges)
    assert n >= 1
    contours, _ = cv2.findContours(bridged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert C.find_open_contours(contours) == []


def test_bridge_gaps_leaves_wide_gaps_open():
    edges = np.zeros((40, 40), np.uint8)
    cv2.rectangle(edges, (5, 5), (30, 30), 255, 1)
    edges[5, 12:22] = 0  # 10 px gap: a real opening, not a lost pixel
    bridged, n = C.bridge_gaps(edges)
    assert n == 0
    assert np.array_equal(bridged, edges)


def test_canny_contours_of_test_image_are_open(motifs):
    contours, _ = cv2.findContours(_canny(motifs), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert len(C.find_open_contours(contours)) >= 10  # the reported bug: detected, not silently cut


def test_bridged_canny_contours_of_test_image_are_closed(motifs):
    bridged, _ = C.bridge_gaps(_canny(motifs))
    contours, _ = cv2.findContours(bridged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert len(contours) == 6
    assert C.find_open_contours(contours) == []


@pytest.mark.parametrize("opaque", [False, True])
def test_shape_contours_of_test_image_are_closed(motifs, opaque):
    if opaque:  # same motifs flattened onto white: background found from the border colour
        rgb = motifs[..., :3].copy()
        rgb[motifs[..., 3] == 0] = 255
        motifs = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    contours = C.shape_contours(C.shape_mask(motifs))
    assert len(contours) == 6
    assert C.find_open_contours(contours) == []


def test_shapes_mode_default_and_closed_toolpath(app_components, motifs, monkeypatch):
    c = app_components
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    load_image(c, motifs)
    assert c.gui.contouring_mode_combobox.currentText() == "shapes"
    c.image_colorer.find_image_contours()
    assert len(c.data_handler.contours_list) == 6
    assert c.data_handler.open_contours == []
    c.image_hatcher.contour_from_image()
    assert not warnings
    for poly in c.data_handler.hatch_data.hatch_clusters[0].data[0].polylines:
        assert np.array_equal(poly[0, :2], poly[-1, :2])


def test_open_contours_are_flagged_in_toolpath(app_components, monkeypatch):
    c = app_components
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    load_image(c, np.zeros((20, 30, 4), np.uint8))
    c.data_handler.contours_list = [[[3, 10], [25, 10]], [[5, 5], [14, 5], [14, 14], [5, 14]]]  # open line, square
    c.image_hatcher.contour_from_image()
    assert len(c.image_hatcher.open_contours) == 1
    assert len(warnings) == 1 and "1 of 2 contours are not closed" in warnings[0][2]


def test_open_contour_is_marked_on_canvas(app_components):
    c = app_components
    img = np.zeros((20, 40, 4), np.uint8)
    img[10, 5:35] = (0, 0, 0, 255)  # a 1 px line: its outline is the line traced there and back, no closed cut
    load_image(c, img)
    c.gui.contouring_mode_combobox.setCurrentText("shapes")
    c.gui.draw_contour_button.click()  # show contours
    assert len(c.data_handler.open_contours) == 1
    assert c.image_colorer.contour_warning_item is not None and c.image_colorer.contour_warning_item.isVisible()
    c.gui.draw_contour_button.click()  # hide
    assert not c.image_colorer.contour_warning_item.isVisible()
