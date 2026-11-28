"""Del deletes the selected overlays (text / geometry, cutting) or the selected mask."""
import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QTest

from test_characterization import load_image
from test_masks import _draw_rect_mask, masked  # noqa: F401  (fixture)


def _press_delete(c, widget=None):
    gui = c.gui
    gui.activateWindow()
    (widget or gui.image_canvas.viewport()).setFocus()
    QtWidgets.QApplication.processEvents()
    QTest.keyClick(widget or gui.image_canvas.viewport(), QtCore.Qt.Key.Key_Delete)
    QtWidgets.QApplication.processEvents()


def _shown(c):
    load_image(c, np.full((100, 200, 4), (200, 40, 40, 255), np.uint8))
    c.gui.resize(1200, 800)
    c.gui.show()
    QtWidgets.QApplication.processEvents()


def test_del_deletes_selected_text_geometry_and_cut_overlays(app_components):
    c, gui = app_components, app_components.gui
    _shown(c)
    text = c.overlay_store.add_text_field()
    geometry = c.overlay_store.add_geometry_item()
    keep = c.overlay_store.add_text_field()
    c.overlay_manager._sync_data_handler_lists()
    c.overlay_manager._update_overlay_list()
    cut = c.cutting.add_overlay("rectangle", (0, 0), 4, 2)
    cut_keep = c.cutting.add_overlay("ellipse", (3, 0), 2, 2)
    gui.image_scene.clearSelection()
    for item in (text, geometry, cut):
        item.setSelected(True)
    _press_delete(c)
    assert c.overlay_store.all_items() == [keep] and c.cutting.store.items == [cut_keep]
    assert gui.tg_overlay_list_widget.count() == 1 and gui.cut_list_widget.count() == 1
    c.data_handler.undo_manager.undo()  # (undo as with the delete buttons)
    assert cut in c.cutting.store.items
    gui.hide()


def test_del_while_typing_deletes_text_not_overlays(app_components):
    c, gui = app_components, app_components.gui
    _shown(c)
    cut = c.cutting.add_overlay("rectangle", (0, 0), 4, 2)
    cut.setSelected(True)
    gui.cut_width_spinbox.setFocus()
    assert c.delete_key.delete() is None
    assert cut in c.cutting.store.items
    gui.hide()


def test_del_deletes_the_selected_mask(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    _draw_rect_mask(c, 35, 10, 44, 19)
    c.gui.masks_list_widget.setCurrentRow(0)
    assert c.data_handler.active_mask_index == 0
    _press_delete(c, c.gui.masks_list_widget)
    assert len(c.data_handler.masks_list) == 1 and c.gui.masks_list_widget.count() == 1
    _press_delete(c)  # nothing selected any more: nothing happens
    assert len(c.data_handler.masks_list) == 1


def test_mask_list_focus_means_the_mask_not_the_overlays(masked):
    c = masked
    _draw_rect_mask(c, 10, 10, 19, 19)
    c.gui.masks_list_widget.setCurrentRow(0)
    cut = c.cutting.add_overlay("rectangle", (0, 0), 1, 1)
    cut.setSelected(True)
    c.gui.masks_list_widget.setFocus()
    assert c.delete_key.delete() == "mask"
    assert not c.data_handler.masks_list and cut in c.cutting.store.items


def test_delete_buttons_name_the_hotkey(app_components):
    gui = app_components.gui
    for button in (gui.delete_mask_button, gui.delete_tg_overlay_button, gui.cut_delete_button):
        assert button.toolTip().endswith("(Del)")
