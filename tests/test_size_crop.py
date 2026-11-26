"""Size & Center section and "crop transparent background" (found while testing v2.0)."""
import numpy as np
from PyQt6 import QtWidgets

from test_characterization import load_image


def _rgba(h, w):
    return np.zeros((h, w, 4), np.uint8)  # all transparent


def test_crop_keeps_one_pixel_of_background_all_around(app_components):
    c = app_components
    image = _rgba(30, 40)
    image[10:15, 20:28] = (200, 30, 30, 255)
    load_image(c, image)
    c.image_controller.crop_background()
    cropped = c.data_handler.image_matrix
    assert cropped.shape[:2] == (5 + 2, 8 + 2)
    assert (cropped[1:-1, 1:-1, 3] == 255).all()
    border = np.concatenate([cropped[0], cropped[-1], cropped[:, 0], cropped[:, -1]])
    assert (border[:, 3] == 0).all()


def test_crop_adds_the_background_pixel_where_the_content_touches_the_edge(app_components):
    c = app_components
    image = _rgba(30, 40)
    image[0:6, 30:40] = (30, 60, 200, 255)   # touches the top and the right edge
    load_image(c, image)
    c.image_controller.crop_background()
    cropped = c.data_handler.image_matrix
    assert cropped.shape[:2] == (6 + 2, 10 + 2)
    assert (cropped[0, :, 3] == 0).all() and (cropped[:, -1, 3] == 0).all()
    assert (cropped[1:7, 1:11, 3] == 255).all()


def test_pixel_size_field_shows_its_value_as_tooltip(app_components):
    c = app_components
    image = _rgba(123, 4567 // 10)
    image[5:10, 5:10] = (0, 0, 0, 255)
    load_image(c, image)
    edit = c.gui.image_resolution_edit
    assert edit.toolTip() == edit.text() + " px" and "123" in edit.toolTip()


def test_center_buttons_are_one_left_aligned_row(app_components):
    gui = app_components.gui
    buttons = [gui.show_image_center_button, gui.set_image_center_button, gui.reset_image_center_button]
    layout = buttons[0].parentWidget().layout()
    row = next(layout.itemAt(i).layout() for i in range(layout.count())
               if layout.itemAt(i).layout() is not None and layout.itemAt(i).layout().indexOf(buttons[0]) >= 0)
    assert isinstance(row, QtWidgets.QHBoxLayout)
    assert [row.itemAt(i).widget() for i in range(3)] == buttons
    assert row.itemAt(3).spacerItem() is not None  # the free space goes to the right
