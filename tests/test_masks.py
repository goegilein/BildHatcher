"""Masks after testing v2.0: lift off masks (P12.4), selection, imprint, and the Masks / Images section sizes."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

from test_characterization import load_image


def _image():
    """60 x 40 white image with a red block (10..19, 10..19) and a blue block (35..44, 10..19)."""
    img = np.full((40, 60, 3), 255, np.uint8)
    img[10:20, 10:20] = (220, 30, 30)
    img[10:20, 35:45] = (30, 60, 200)
    return img


def _mouse(c, kind, x_img, y_img):
    """Mouse event on the centre of image pixel (x_img, y_img)."""
    gui = c.gui
    point = gui.image_canvas.mapFromScene(gui.image_item.mapToScene(QtCore.QPointF(x_img + 0.5, y_img + 0.5)))
    viewport = gui.image_canvas.viewport()
    pos = QtCore.QPointF(point)
    buttons = QtCore.Qt.MouseButton.LeftButton
    return QtGui.QMouseEvent(kind, pos, QtCore.QPointF(viewport.mapToGlobal(pos)), QtCore.Qt.MouseButton.LeftButton,
                             buttons, QtCore.Qt.KeyboardModifier.NoModifier)


def _draw_rect_mask(c, x0, y0, x1, y1):
    """Draw a rectangle mask with the mouse (press, drag, release) like the user."""
    colorer = c.image_colorer
    colorer.mask_drawing_on, colorer.mask_shape_mode = True, "rectangle"
    Type = QtCore.QEvent.Type
    colorer.start_mask_rect(_mouse(c, Type.MouseButtonPress, x0, y0))
    colorer.update_mask_rect_preview(_mouse(c, Type.MouseMove, x1, y1))
    colorer.finish_mask_rect(_mouse(c, Type.MouseButtonRelease, x1, y1))
    colorer.mask_drawing_on = False


def _drag(c, start, end):
    """Drag with the left mouse button on the canvas from image pixel `start` to `end` (real view events)."""
    viewport = c.gui.image_canvas.viewport()
    Type, Button = QtCore.QEvent.Type, QtCore.Qt.MouseButton
    send = QtWidgets.QApplication.sendEvent
    send(viewport, _mouse(c, Type.MouseButtonPress, *start))
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    for point in (middle, end):
        send(viewport, _mouse(c, Type.MouseMove, *point))
    release = _mouse(c, Type.MouseButtonRelease, *end)
    send(viewport, QtGui.QMouseEvent(Type.MouseButtonRelease, release.position(), release.globalPosition(),
                                     Button.LeftButton, Button.NoButton, QtCore.Qt.KeyboardModifier.NoModifier))


def _lift(c, row):
    c.image_colorer.masks_list_widget.setCurrentRow(row)
    c.gui.move_masked_area_button.click()


@pytest.fixture
def masked(app_components):
    c = app_components
    c.gui.resize(1100, 800)
    c.gui.show()
    load_image(c, _image())
    # one image pixel = several screen pixels, so that the simulated clicks hit exact pixels
    view = c.gui.image_canvas
    view.resetTransform()
    view.scale(20, 20)
    QtWidgets.QApplication.processEvents()
    a = view.mapFromScene(c.gui.image_item.mapToScene(QtCore.QPointF(0, 0)))
    b = view.mapFromScene(c.gui.image_item.mapToScene(QtCore.QPointF(10, 0)))
    assert b.x() - a.x() >= 30, "image pixels too small on screen for exact clicks"
    yield c
    c.gui.hide()


def _mask_box(mask):
    ys, xs = np.nonzero(mask == 1)
    return xs.min(), ys.min(), xs.max(), ys.max()




RED, BLUE = (220, 30, 30), (30, 60, 200)


def test_a_new_mask_is_selected(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    assert c.data_handler.active_mask_index == 1
    assert c.image_colorer.masks_list_widget.currentRow() == 1


def test_lifting_a_mask_makes_a_floating_layer(masked):
    c = masked
    colorer, gui = c.image_colorer, c.gui
    _draw_rect_mask(c, 10, 10, 19, 19)
    before = c.data_handler.image_matrix.copy()
    assert not gui.imprint_mask_button.isEnabled() and not gui.move_masked_area_button.isChecked()
    _lift(c, 0)
    assert colorer.is_lifted(0)
    assert gui.move_masked_area_button.isChecked()               # the lift button now imprints
    assert "Imprint" in gui.move_masked_area_button.toolTip()
    assert gui.imprint_mask_button.isEnabled() and gui.actionImprint_Masks.isEnabled()
    assert c.data_handler.mask_overlays[0].pen().color().name().upper() in ("#FF6D00", "#C43C00")  # orange
    assert np.array_equal(c.data_handler.image_matrix, before)  # the image only changes with the imprint
    assert not c.data_handler.active_color_overlays             # not part of the colour imprint


def test_drag_and_drop_then_imprint_the_mask(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    start = _mask_box(c.data_handler.masks_list[0])
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))                                 # down by 12
    assert c.data_handler.mask_overlays[0].pos().y() > 0          # the frame follows
    c.gui.move_masked_area_button.click()                        # imprint this mask
    image = c.data_handler.image_matrix
    assert not c.image_colorer.is_lifted(0)
    assert tuple(image[27, 15][:3]) == RED and image[27, 15][3] == 255
    assert image[12, 15][3] == 0                                 # the old place became background
    assert _mask_box(c.data_handler.masks_list[0])[:2] == (start[0], start[1] + 12)  # the mask moved along
    assert c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)


def test_masks_lifted_and_moved_alternately(masked):
    """The scenario that failed with the old "move": mask 1, mask 2, mask 1 again – then imprint all."""
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    start_first, start_second = (_mask_box(m) for m in c.data_handler.masks_list)
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))
    _lift(c, 1)
    _drag(c, (40, 15), (40, 27))
    _drag(c, (15, 27), (27, 27))                                 # the first one again (still lifted)
    assert c.data_handler.active_mask_index == 0                 # dragging selects
    c.gui.imprint_mask_button.click()                            # imprint all masks
    image = c.data_handler.image_matrix
    assert tuple(image[27, 27][:3]) == RED and image[27, 27][3] == 255
    assert image[27, 15][3] == 0 and image[15, 15][3] == 0
    assert tuple(image[27, 40][:3]) == BLUE and image[15, 40][3] == 0
    first, second = c.data_handler.masks_list
    assert _mask_box(first)[:2] == (start_first[0] + 12, start_first[1] + 12)
    assert _mask_box(second)[:2] == (start_second[0], start_second[1] + 12)
    assert not c.image_colorer.lifted_indices() and not c.gui.imprint_mask_button.isEnabled()


def test_deleting_a_lifted_mask_puts_nothing_into_the_image(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    before = c.data_handler.image_matrix.copy()
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))
    c.image_colorer.masks_list_widget.setCurrentRow(0)
    c.image_colorer.delete_selected_mask()
    assert not c.data_handler.masks_list and not c.gui.imprint_mask_button.isEnabled()
    assert np.array_equal(c.data_handler.image_matrix, before)
    assert not [i for i in c.gui.image_item.childItems() if type(i).__name__ == "LiftedMaskItem"]


def test_no_drag_while_a_tool_is_on(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _lift(c, 0)
    c.gui.toggle_draw_button.click()                             # draw tool on: the click draws, nothing moves
    _drag(c, (15, 15), (15, 27))
    assert c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)
    c.image_colorer.set_single_toggle_state("")


def test_undo_imprint_drag_and_lift(masked):
    c = masked
    undo = c.image_colorer.undo_manager
    _draw_rect_mask(c, 10, 10, 19, 19)
    original = c.data_handler.image_matrix.copy()
    _lift(c, 0)
    _drag(c, (15, 15), (15, 27))
    c.gui.imprint_mask_button.click()
    assert not np.array_equal(c.data_handler.image_matrix, original)
    undo.undo()                                                  # imprint undone: lifted at the dragged place
    assert np.array_equal(c.data_handler.image_matrix, original)
    assert c.image_colorer.is_lifted(0) and c.data_handler.mask_overlays[0].pos().y() > 0
    undo.undo()                                                  # drag undone
    assert c.image_colorer.is_lifted(0) and c.data_handler.mask_overlays[0].pos() == QtCore.QPointF(0, 0)
    undo.undo()                                                  # lift undone
    assert not c.image_colorer.is_lifted(0)
    undo.redo()
    undo.redo()
    undo.redo()                                                  # and everything again
    image = c.data_handler.image_matrix
    assert tuple(image[27, 15][:3]) == RED and not c.image_colorer.is_lifted(0)


def test_masks_and_images_sections_have_taller_lists_and_imprint_buttons(app_components):
    gui = app_components.gui
    assert gui.masks_list_widget.minimumHeight() >= 200 and gui.images_ListWidget.minimumHeight() >= 220
    assert gui.imprint_mask_button.property("styleClass") == "ImprintButton"
    assert gui.actionImprint_Masks in gui.toolBar.actions()
    assert gui.imprint_mask_button.parentWidget() is gui.masks_list_widget.parentWidget()
    assert gui.toolbar_colors_label.parentWidget() is gui.toolBar
    load_image(app_components, _image())
    assert gui.toolbar_colors_label.text() == gui.number_of_colors_label.text().split(": ")[1] + " colors"
