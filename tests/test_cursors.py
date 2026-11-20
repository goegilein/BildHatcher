"""P11: canvas cursors for the colour tools and the pen outline."""
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets

import Tools
from test_characterization import load_image, make_test_image


def _stroke_pixels(width, a, b, size=24):
    """Pixels the colour pen paints for a stroke from pixel a to pixel b (rendered like the imprint)."""
    image = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
    pen = QtGui.QPen(QtGui.QColor("red"), width)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    path = QtGui.QPainterPath(QtCore.QPointF(a[0] + 0.5, a[1] + 0.5))
    path.lineTo(QtCore.QPointF(b[0] + 0.5, b[1] + 0.5))
    painter.drawPath(path)
    painter.end()
    return {(x, y) for y in range(size) for x in range(size) if image.pixel(x, y) != 0}


def _footprint_pixels(x, y, width):
    left, top, size = Tools.pen_footprint(x, y, width)
    return {(left + i, top + j) for i in range(size) for j in range(size)}


def test_pen_outline_matches_what_the_pen_paints():
    for width in range(1, 8):
        for b in ((11, 10), (10, 11), (9, 10), (10, 9)):  # to a neighbour pixel (the square caps turn with
            expected = _footprint_pixels(10, 10, width) | _footprint_pixels(*b, width)  # a diagonal stroke)
            assert _stroke_pixels(width, (10, 10), b) == expected, (width, b)


def test_tools_set_their_cursor_with_the_hot_spot_on_the_tip(app_components):
    c = app_components
    load_image(c, make_test_image())
    gui, colorer = c.gui, c.image_colorer
    viewport = gui.image_canvas.viewport()
    for button, hot in ((gui.toggle_draw_button, (1, 30)), (gui.flood_fill_button, (5, 26)),
                        (gui.replace_color_button, (1, 1)), (gui.pick_color_from_image_button, (1, 30))):
        button.click()
        cursor = viewport.cursor()
        assert cursor.shape() == QtCore.Qt.CursorShape.BitmapCursor, button.objectName()
        assert (cursor.hotSpot().x(), cursor.hotSpot().y()) == hot, button.objectName()
    colorer.set_single_toggle_state("")
    assert viewport.cursor().shape() == QtCore.Qt.CursorShape.ArrowCursor


def test_replace_pointer_has_the_active_colour():
    def tip_colour(hex_color):
        image = Tools.make_cursor("cursor-replace", (1, 1), hex_color).pixmap().toImage()
        return image.pixelColor(4, 8).name().upper()
    assert tip_colour("E53935") == "#E53935"
    assert tip_colour("1E88E5") == "#1E88E5"


def test_pen_outline_follows_the_mouse_and_the_pen_width(app_components):
    c = app_components
    load_image(c, make_test_image())
    gui = c.gui
    gui.resize(900, 700)
    gui.show()
    QtWidgets.QApplication.processEvents()
    gui.toggle_draw_button.click()
    gui.pen_width_spinbox.setValue(3)
    target = QtCore.QPointF(5.5, 7.5)  # centre of image pixel (5, 7)
    viewport_pos = gui.image_canvas.mapFromScene(gui.image_item.mapToScene(target))
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(viewport_pos),
                             QtCore.QPointF(gui.image_canvas.viewport().mapToGlobal(viewport_pos)),
                             QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(gui.image_canvas.viewport(), move)
    outline = c.canvas_cursors.footprint[1]
    assert outline.isVisible()
    rect = outline.path().boundingRect()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (4, 6, 3, 3)
    gui.pen_width_spinbox.setValue(4)
    rect = outline.path().boundingRect()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (4, 6, 4, 4)
    c.image_colorer.set_single_toggle_state("")
    assert not outline.isVisible()
    gui.hide()
