"""Image tool bar row (ImageBar): Images / Size / Center drop-downs, the hatch centre per image, grid at the centre."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

import MainLayout
import Preferences
from test_characterization import load_image

PPM = 10.0  # test_characterization.PIXEL_PER_MM


def _image(h=100, w=200, color=(200, 40, 40)):
    img = np.zeros((h, w, 4), np.uint8)
    img[10:-10, 10:-10] = (*color, 255)
    return img


def _select(c, row):
    c.gui.images_ListWidget.clearSelection()
    c.gui.images_ListWidget.item(row).setSelected(True)


# --- panel: Images and Size left it, Text moved into Image Editing ---
def test_panel_groups_after_the_move():
    assert list(MainLayout.GROUPS) == ["Image Editing", "Hatching", "Automation"]
    icon, entries = MainLayout.GROUPS["Image Editing"]
    assert icon == "group-image-edit"
    assert [e[0] for e in entries] == ["Adjust", "Color", "Masks", "Text and Shapes"]
    every = [e[2] for _, entries in MainLayout.GROUPS.values() for e in entries]
    assert "images_frame" not in every and "size_frame" not in every


def test_old_remembered_panel_state_is_mapped(app_components, qapp):
    import main
    before = Preferences.get("panel")
    Preferences.put("panel", {"group": "Text", "open": {"Image": ["Images"], "Text": ["Text"]},
                              "pinned": ["Images", "Text", "Masks"]})
    try:
        gui = main.create_main_window()
        c = main.create_components(gui)
        panel = MainLayout.build(gui, c)
        assert panel.group == "Image Editing" and panel.group_buttons["Image Editing"].isChecked()
        assert panel.pinned == {"Text and Shapes", "Masks"}
        assert panel.open["Image Editing"] in ([], ["Adjust"], ["Color"], ["Masks"], ["Text and Shapes"])
        gui.deleteLater()
    finally:
        Preferences.put("panel", before)


# --- the tool bar row ---
def test_second_toolbar_row_left_with_values(app_components):
    c, gui = app_components, app_components.gui
    bar = gui.image_toolBar
    assert gui.toolBarArea(bar) == QtCore.Qt.ToolBarArea.TopToolBarArea and gui.toolBarBreak(bar)
    widgets = [bar.widgetForAction(a) for a in bar.actions() if not a.isSeparator()]
    assert widgets == [c.image_bar.images_button, gui.toolbar_image_name_label, gui.toolbar_colors_label,
                       c.image_bar.size_button, gui.toolbar_size_label,
                       c.image_bar.center_button, gui.toolbar_center_label]
    for button in (c.image_bar.images_button, c.image_bar.size_button, c.image_bar.center_button):
        assert button.isCheckable() and not button.icon().isNull() and button.toolTip()
    assert gui.toolbar_image_name_label.text() == "No image"

    load_image(c, _image(), name="horse")  # 200 x 100 px at 10 px/mm
    assert gui.toolbar_image_name_label.text() == "horse"
    assert gui.toolbar_colors_label.text() == "1 colors"
    assert gui.toolbar_size_label.text() == "20.00 x 10.00 mm"
    assert gui.toolbar_center_label.text() == "X 9.95 / Y 4.95 mm"
    gui.width_spinbox.setValue(40)  # the size follows edits
    gui.width_spinbox.editingFinished.emit()
    assert gui.toolbar_size_label.text() == "40.00 x 20.00 mm"


def test_dropdowns_stay_open_until_clicked_again(app_components):
    c, gui = app_components, app_components.gui
    bar = c.image_bar
    load_image(c, _image())
    gui.resize(1400, 900)
    gui.show()
    QtWidgets.QApplication.processEvents()
    assert not gui.images_frame.isVisible()
    bar.images_button.click()
    assert gui.images_frame.isVisible() and gui.images_ListWidget.isVisible()
    bar.size_button.click()
    bar.center_button.click()
    assert gui.image_dimension_frame.isVisible() and gui.groupBox_2.isVisible()
    assert not gui.size_frame.isVisible()
    # a click on the canvas (or anywhere else) does not close them
    QtWidgets.QApplication.sendEvent(gui.image_canvas.viewport(), QtCore.QEvent(QtCore.QEvent.Type.FocusIn))
    QtWidgets.QApplication.processEvents()
    assert all(d.holder.isVisible() for d in bar.dropdowns)
    # side by side under the bar, from left to right, not on top of each other
    rects = [d.holder.geometry() for d in bar.dropdowns]
    assert all(r.top() >= bar.mapTo(gui, QtCore.QPoint(0, bar.height())).y() for r in rects)
    assert rects[0].right() < rects[1].left() and rects[1].right() < rects[2].left()
    tabs = gui.visualization_tabWidget.tabBar()  # the canvas tabs stay reachable
    assert all(r.top() > tabs.mapTo(gui, QtCore.QPoint(0, tabs.height())).y() for r in rects)
    bar.size_button.click()  # closes only this one
    assert not gui.image_dimension_frame.isVisible() and gui.images_frame.isVisible()
    bar.images_button.click()
    bar.center_button.click()
    assert not any(d.holder.isVisible() for d in bar.dropdowns)
    gui.hide()


# --- hatch centre: editable, a property of every image ---
def test_center_can_be_typed_in(app_components):
    c, gui = app_components, app_components.gui
    load_image(c, _image())
    assert gui.h_center_spinbox.isEnabled() and gui.v_center_spinbox.isEnabled()
    gui.h_center_spinbox.setValue(3)
    gui.v_center_spinbox.setValue(7.5)
    assert c.data_handler.center_for_hatch == pytest.approx([30, 75])
    assert gui.toolbar_center_label.text() == "X 3.00 / Y 7.50 mm"
    assert c.cutting.hatch_center() == pytest.approx((30, 75))  # every user of the centre sees it


def test_every_image_keeps_its_own_center(app_components):
    c, gui = app_components, app_components.gui
    load_image(c, _image(), name="a")
    c.image_sizer.set_image_center_mm(2, 3)
    load_image(c, _image(60, 80, (40, 40, 200)), name="b")
    assert c.data_handler.center_for_hatch == pytest.approx([79 / 2, 59 / 2])  # a new image: its middle
    c.image_sizer.set_image_center_mm(1, 1)
    _select(c, 0)
    assert c.data_handler.center_for_hatch == pytest.approx([20, 30])
    assert gui.h_center_spinbox.value() == pytest.approx(2) and gui.v_center_spinbox.value() == pytest.approx(3)
    assert gui.toolbar_image_name_label.text() == "a" and gui.toolbar_center_label.text() == "X 2.00 / Y 3.00 mm"
    _select(c, 1)
    assert c.data_handler.center_for_hatch == pytest.approx([10, 10])
    assert c.image_controller.get_active_img_obj().center == pytest.approx([10, 10])


def test_center_moves_with_rotation_mirror_crop_and_copies(app_components):
    c = app_components
    ctrl = c.image_controller
    load_image(c, _image(100, 200))
    c.image_sizer.set_image_center_mm(5, 2)  # (50, 20) px
    ctrl.rot_image_90_clockwise()  # 100 x 200 (h x w) -> 200 x 100: (x, y) -> (h - 1 - y, x)
    assert c.data_handler.center_for_hatch == pytest.approx([79, 50])
    ctrl.mirror_image_horizontal()
    assert c.data_handler.center_for_hatch == pytest.approx([20, 50])
    ctrl.add_image()  # a copy keeps the centre
    assert c.data_handler.center_for_hatch == pytest.approx([20, 50])
    ctrl.crop_background()  # content from pixel 10 on, one pixel of background kept: offset 9
    assert c.data_handler.image_matrix.shape[:2] == (182, 82)
    assert c.data_handler.center_for_hatch == pytest.approx([11, 41])


def test_reset_center_goes_back_to_the_middle(app_components):
    c, gui = app_components, app_components.gui
    load_image(c, _image())
    c.image_sizer.set_image_center_mm(1, 1)
    gui.reset_image_center_button.click()
    assert c.data_handler.center_for_hatch == pytest.approx([99.5, 49.5])


# --- grid at the centre ---
def _grid_lines(c):
    return [i for i in c.gui.image_scene.items()
            if isinstance(i, QtWidgets.QGraphicsLineItem) and i.zValue() == c.image_sizer.GRID_Z]


def test_grid_is_aligned_to_the_center_with_thick_axes(app_components):
    c, gui = app_components, app_components.gui
    mover = c.image_sizer
    load_image(c, _image())
    mover.set_image_center_mm(3, 2)
    gui.grid_distance_spinbox.setValue(5)
    assert not mover.showing_image_center
    mover.toggle_grid()
    ox, oy = c.data_handler.image_to_scene_coords(30, 20)
    axes = [line for line in _grid_lines(c) if line.pen().width() == mover.GRID_AXIS_WIDTH]
    assert len(axes) == 2 and all(line.pen().isCosmetic() for line in axes)
    vertical = next(line.line() for line in axes if line.line().dx() == 0)
    horizontal = next(line.line() for line in axes if line.line().dy() == 0)
    assert vertical.x1() == pytest.approx(ox) and horizontal.y1() == pytest.approx(oy)
    step = 5 * c.data_handler.default_pixel_per_mm
    xs = sorted(line.line().x1() for line in _grid_lines(c) if line.line().dx() == 0)
    assert all(((x - ox) / step) == pytest.approx(round((x - ox) / step)) for x in xs)  # every line on the raster
    assert any(x < ox for x in xs) and any(x > ox for x in xs)

    gui.h_center_spinbox.setValue(4)  # the grid follows the centre
    ox2, _ = c.data_handler.image_to_scene_coords(40, 20)
    axes = [line for line in _grid_lines(c) if line.pen().width() == mover.GRID_AXIS_WIDTH]
    assert {round(line.line().x1(), 6) for line in axes if line.line().dx() == 0} == {round(ox2, 6)}
    mover.toggle_grid()
    assert not _grid_lines(c)


def test_new_icons_exist():
    from PathManager import get_gui_file_path
    for name in ("group-image-edit", "image-size", "image-center"):
        for folder in (get_gui_file_path("icons"), get_gui_file_path("icons") / "light"):
            assert (folder / f"{name}.svg").exists(), (folder, name)


# --- names, rename, tool bar order ---
def test_image_names_have_no_file_extension(app_components, tmp_path):
    from PIL import Image
    import ImageControlling
    assert ImageControlling.image_name("C:/x/Horse.Head.png") == "Horse.Head"
    path = tmp_path / "Pferd.png"
    Image.fromarray(_image()).save(path)
    c = app_components
    c.image_controller.load_image(str(path))
    assert c.gui.images_ListWidget.item(0).text() == "Pferd"
    assert c.gui.toolbar_image_name_label.text() == "Pferd"


def test_every_list_can_rename_its_entries(app_components):
    c, gui = app_components, app_components.gui
    load_image(c, _image(), name="a")
    lists = [gui.images_ListWidget, gui.masks_list_widget, gui.tg_overlay_list_widget, gui.process_listWidget,
             gui.cut_list_widget]
    for widget in lists:
        assert widget.contextMenuPolicy() == QtCore.Qt.ContextMenuPolicy.CustomContextMenu, widget.objectName()
        assert widget._rename is not None
    # images: the name shows in the tool bar
    gui.images_ListWidget._rename.rename(gui.images_ListWidget.item(0), "  Logo  ")
    assert gui.images_ListWidget.item(0).text() == "Logo" and gui.toolbar_image_name_label.text() == "Logo"
    assert not gui.images_ListWidget._rename.rename(gui.images_ListWidget.item(0), "   ")  # empty: unchanged
    assert gui.images_ListWidget.item(0).text() == "Logo"
    # text and shapes: kept when the list is rebuilt
    tg = c.overlay_manager
    c.overlay_store.add_text_field()
    tg._update_overlay_list()
    gui.tg_overlay_list_widget._rename.rename(gui.tg_overlay_list_widget.item(0), "Title")
    c.overlay_store.add_text_field()
    tg._update_overlay_list()
    assert [gui.tg_overlay_list_widget.item(i).text() for i in range(2)] == ["Title", "textbox #2"]
    # cutting shapes: the name, "(fixed)" stays a marker
    m = c.cutting
    item = m.add_overlay("rectangle", (0, 0), 4, 2)
    widget = gui.cut_list_widget
    widget._rename.rename(widget.item(0), "Outer cut")
    gui.cut_fix_checkbox.click()
    assert widget.item(0).text() == "Outer cut  (fixed)" and widget._rename.current_name(widget.item(0)) == "Outer cut"
    assert item.list_name == "Outer cut"
    # process blocks: the entry text
    gui.process_listWidget.addItem("1x Hatch")
    gui.process_listWidget._rename.rename(gui.process_listWidget.item(0), "Background")
    assert gui.process_listWidget.item(0).text() == "Background"


def test_toolbar_order_zoom_and_separated_grid(app_components):
    gui = app_components.gui
    bar = gui.toolBar
    entries = []
    for action in bar.actions():
        widget = bar.widgetForAction(action)
        entries.append("|" if action.isSeparator() else (widget.objectName() if isinstance(widget, QtWidgets.QAbstractSpinBox)
                                                         else action.text()))
    i = entries.index("Reset Zoom")
    assert entries[i:i + 6] == ["Reset Zoom", "zoom_spinbox", "Re-Center Image", "|", "Grid",
                                gui.grid_distance_spinbox.objectName()]
    center = next(a for a in bar.actions() if a.text() == "Re-Center Image")
    assert center.toolTip() == "Re-Center Image"


def test_image_bar_is_movable(app_components):
    c, gui = app_components, app_components.gui
    bar = gui.image_toolBar
    assert bar.isMovable() and gui.toolBar.isMovable()
    gui.resize(1400, 900)
    gui.show()
    gui.removeToolBar(bar)  # moved to the bottom: the drop-downs open upwards
    gui.addToolBar(QtCore.Qt.ToolBarArea.BottomToolBarArea, bar)
    bar.show()
    QtWidgets.QApplication.processEvents()
    c.image_bar.size_button.click()
    QtWidgets.QApplication.processEvents()
    holder = c.image_bar.size.holder
    assert holder.isVisible() and holder.geometry().bottom() < bar.mapTo(gui, QtCore.QPoint(0, 0)).y()
    gui.hide()
