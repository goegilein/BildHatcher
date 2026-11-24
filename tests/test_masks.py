"""Mask bugs found while testing v2.0 (moving masks, selection, imprint) and the Masks / Images section sizes."""
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


def _move_selected_mask(c, dx, dy, start=(15, 15)):
    colorer = c.image_colorer
    colorer.move_mask_on = True
    Type = QtCore.QEvent.Type
    colorer.on_move_mask_press(_mouse(c, Type.MouseButtonPress, *start))
    colorer.on_move_mask_drag(_mouse(c, Type.MouseMove, start[0] + dx, start[1] + dy))
    colorer.on_move_mask_release(_mouse(c, Type.MouseButtonRelease, start[0] + dx, start[1] + dy))


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


def test_a_new_mask_is_selected(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    assert c.data_handler.active_mask_index == 1
    assert c.image_colorer.masks_list_widget.currentRow() == 1


def test_deleting_a_moved_mask_still_allows_the_imprint(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _move_selected_mask(c, 0, 15)
    assert c.data_handler.active_color_overlays  # cut-out + moved pixels wait for the imprint
    assert c.gui.imprint_mask_button.isEnabled()
    c.image_colorer.delete_selected_mask()
    assert not c.data_handler.masks_list
    c.image_colorer.imprint_color_overlays()  # failed before (index of the deleted mask)
    image = c.data_handler.image_matrix
    assert not c.data_handler.active_color_overlays
    assert tuple(image[27, 15][:3]) == (220, 30, 30) and image[27, 15][3] == 255  # moved down by 15
    assert image[12, 15][3] == 0  # the old place became background


def test_a_second_mask_moves_itself_and_the_first_keeps_its_move(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _move_selected_mask(c, 0, 15)                 # first mask, not imprinted
    _draw_rect_mask(c, 35, 10, 44, 19)            # new mask: selected automatically
    _move_selected_mask(c, 0, 15, start=(40, 15))  # moved the old one before
    c.image_colorer.imprint_color_overlays()
    first, second = c.data_handler.masks_list
    assert _mask_box(first)[1] >= 24 and _mask_box(second)[1] >= 24  # both masks moved down
    image = c.data_handler.image_matrix
    assert tuple(image[27, 15][:3]) == (220, 30, 30)
    assert tuple(image[27, 40][:3]) == (30, 60, 200)
    assert image[12, 40][3] == 0


def test_masks_and_images_sections_have_taller_lists_and_imprint_buttons(app_components):
    gui = app_components.gui
    assert gui.masks_list_widget.minimumHeight() >= 200 and gui.images_ListWidget.minimumHeight() >= 220
    assert gui.imprint_mask_button.property("styleClass") == "ImprintButton"
    assert gui.imprint_mask_button.parentWidget() is gui.masks_list_widget.parentWidget()
    assert gui.toolbar_colors_label.parentWidget() is gui.toolBar
    load_image(app_components, _image())
    assert gui.toolbar_colors_label.text() == gui.number_of_colors_label.text().split(": ")[1] + " colors"


def test_moving_masks_alternately_moves_their_moved_pixels(masked):
    """Mask 1 moved, mask 2 moved, mask 1 moved again – all without imprint: the second move of mask 1 must take
    its already moved pixels, not what the unimprinted image has at that place."""
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)                      # red block
    _draw_rect_mask(c, 35, 10, 44, 19)                      # blue block
    start_first, start_second = (_mask_box(m) for m in c.data_handler.masks_list)
    c.image_colorer.masks_list_widget.setCurrentRow(0)
    _move_selected_mask(c, 0, 12)                           # red down by 12
    c.image_colorer.masks_list_widget.setCurrentRow(1)
    _move_selected_mask(c, 0, 12, start=(40, 15))           # blue down by 12
    c.image_colorer.masks_list_widget.setCurrentRow(0)
    _move_selected_mask(c, 12, 0, start=(15, 27))           # red right by 12 (from its moved place)
    c.image_colorer.imprint_color_overlays()
    image = c.data_handler.image_matrix
    assert tuple(image[27, 27][:3]) == (220, 30, 30) and image[27, 27][3] == 255   # red at its final place
    assert image[27, 15][3] == 0 and image[15, 15][3] == 0                         # its earlier places are empty
    assert tuple(image[27, 40][:3]) == (30, 60, 200)                               # blue moved once
    first, second = c.data_handler.masks_list
    assert _mask_box(first)[:2] == (start_first[0] + 12, start_first[1] + 12)   # the masks moved along
    assert _mask_box(second)[:2] == (start_second[0], start_second[1] + 12)
