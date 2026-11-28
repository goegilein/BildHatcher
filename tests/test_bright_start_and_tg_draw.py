"""Bright mode start loads the bright pictograms; text / geometry overlays are drawn where the mouse is."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtTest import QTest

import theme
from test_characterization import load_image


def _image_of(icon):
    return icon.pixmap(20, 20).toImage()


def test_bright_start_uses_the_bright_pictograms(qapp):
    import main
    before = theme.MODE
    theme.apply(qapp, "light")
    try:
        gui = main.create_main_window()
        light = QtGui.QIcon(str(theme.icon_dir("light") / "crop.svg"))
        dark = QtGui.QIcon(str(theme.icon_dir("dark") / "crop.svg"))
        assert _image_of(light) != _image_of(dark)  # (the check below can tell them apart)
        assert _image_of(gui.crop_background_button.icon()) == _image_of(light)
        gui.deleteLater()
    finally:
        theme.apply(qapp, before)


@pytest.mark.parametrize("kind", ["geometry", "text"])
def test_text_and_geometry_start_at_the_clicked_point(app_components, kind):
    c, gui = app_components, app_components.gui
    load_image(c, np.zeros((100, 200, 4), np.uint8))  # 10 px/mm: the image item is scaled on the canvas
    assert gui.image_item.scale() != 1
    gui.resize(1200, 800)
    gui.show()
    QtWidgets.QApplication.processEvents()
    gui.image_canvas.resetTransform()
    gui.image_canvas.scale(10, 10)
    gui.image_canvas.centerOn(gui.image_item.mapToScene(QtCore.QPointF(70, 45)))
    QtWidgets.QApplication.processEvents()
    viewport = gui.image_canvas.viewport()

    def view_point(x, y):
        return gui.image_canvas.mapFromScene(gui.image_item.mapToScene(QtCore.QPointF(x, y)))

    (gui.add_geometry_button if kind == "geometry" else gui.add_text_button).click()
    QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                     view_point(50, 30))
    QTest.mouseMove(viewport, view_point(90, 60))
    QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       view_point(90, 60))
    [item] = c.overlay_store.all_items()
    top_left = item.mapToParent(item._rect.topLeft())  # in image pixels
    assert (top_left.x(), top_left.y()) == pytest.approx((50, 30), abs=0.5)
    assert (item._rect.width(), item._rect.height()) == pytest.approx((40, 30), abs=0.5)
    gui.hide()
