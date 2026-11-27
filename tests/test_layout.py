"""P8.6 / P8.7 / P9.3-P9.5 / P10: toolbar and settings panel (built by MainLayout in the app_components fixture)."""
import os
import sys
from pathlib import Path

import pytest
from PyQt6 import QtWidgets

import MainLayout
import Preferences


def test_panel_groups_and_sections_single_select(app_components):
    c = app_components
    gui, panel = c.gui, c.panel_buttons
    scroll = gui.settings_panel.findChild(QtWidgets.QScrollArea, "settings_panel_scroll")
    assert set(panel.group_buttons) == set(MainLayout.GROUPS)
    assert set(panel.sections) == {e[0] for _, entries in MainLayout.GROUPS.values() for e in entries}
    gui.show()
    panel.select_group("Image")
    assert panel.group_buttons["Image"].isChecked()
    assert all(panel.section_buttons[e[0]].isVisible() for e in MainLayout.GROUPS["Image"][1])
    assert not panel.section_buttons["Hatch"].isVisible()

    panel.group_buttons["Hatching"].click()  # single select between groups
    assert not panel.group_buttons["Image"].isChecked() and panel.group_buttons["Hatching"].isChecked()
    assert not gui.draw_mask_groupbox.isVisible()
    panel.section_buttons["Hatch"].setChecked(True)
    panel.section_buttons["Export"].setChecked(True)  # P10.6: one section at a time
    assert gui.export_frame.isVisible() and not gui.hatch_frame.isVisible()
    assert not panel.section_buttons["Hatch"].isChecked()
    assert gui.inside_contour_frame.parentWidget() is gui.hatch_frame  # Contours merged into Hatch (P9.4)
    assert Preferences.get("panel")["group"] == "Hatching"
    assert Preferences.get("panel")["open"]["Hatching"] == ["Export"]

    panel.group_buttons["Hatching"].click()  # clicking the active group closes the panel
    assert panel.group is None and not scroll.isVisible() and not panel.sub_strip.isVisible()
    panel.select_group("Hatching")  # the open subsection is remembered
    assert gui.export_frame.isVisible() and not gui.hatch_frame.isVisible()
    gui.hide()


def test_hiding_masks_section_resets_mask_tools(app_components):
    c = app_components
    panel = c.panel_buttons
    calls = []
    c.image_colorer.set_single_toggle_state = lambda name: calls.append(name)
    c.gui.show()
    panel.select_group("Image")
    panel.section_buttons["Masks"].setChecked(True)
    panel.section_buttons["Masks"].setChecked(False)
    assert calls == ['']
    calls.clear()
    panel.section_buttons["Color"].setChecked(True)
    panel.section_buttons["Color"].setChecked(False)
    assert calls == []  # colour tools stay active (hotkeys)
    c.gui.hide()


def test_toolbar_has_profiles_and_view_controls(app_components):
    gui = app_components.gui
    bar = gui.toolBar
    texts = [a.text() for a in bar.actions()]
    assert {"Load Image", "Save Image", "Reset Zoom", "Re-center", "Grid"} <= set(texts)
    assert any(t.startswith("Color Profile") for t in texts)
    assert not any(w.toolTip() == "Image operations" for w in bar.findChildren(QtWidgets.QToolButton))  # P9.6
    assert gui.machine_profile_combobox.parentWidget() is bar
    assert gui.zoom_spinbox.parentWidget() is bar


def test_p92_toolbar_pictograms_and_menus(app_components):
    gui = app_components.gui
    for action in (gui.actionLoad_Image, gui.actionSave_Image, gui.actionNew_Blank):
        assert not action.icon().isNull()
    file_menu = [a.text() for a in gui.basefunc_menu.actions()]
    settings_menu = [a.text() for a in gui.settings_menu.actions()]
    assert "Load: Pure White as Transparent" in settings_menu and "Load: Pure White as Transparent" not in file_menu
    assert "Make Bright Colors Transparent..." not in file_menu


def test_p96_bright_transparent_button_opens_the_operation(app_components, monkeypatch):
    calls = []
    monkeypatch.setattr(app_components.image_controller, "make_bright_transparent", lambda: calls.append(1))
    app_components.gui.bright_transparent_button.click()
    assert calls == [1]


def test_p97_color_section_compact_and_stable(app_components):
    c = app_components
    gui, panel = c.gui, c.panel_buttons
    gui.show()
    panel.select_group("Image")
    panel.section_buttons["Color"].setChecked(True)
    section = gui.image_color_frame
    sizes = set()
    for i in range(gui.flood_fill_mode_combobox.count()):  # fill options must not resize the section
        gui.flood_fill_mode_combobox.setCurrentIndex(i)
        c.app.processEvents() if hasattr(c, "app") else None
        sizes.add((section.sizeHint().width(), section.sizeHint().height()))
    assert len(sizes) == 1
    tools = [gui.toggle_draw_button, gui.flood_fill_button, gui.replace_color_button]
    assert len({b.size().toTuple() if hasattr(b.size(), "toTuple") else (b.width(), b.height()) for b in tools}) == 1
    assert len({b.y() for b in tools}) == 1  # side by side
    assert not hasattr(gui, "recolor_laser_label")
    gui.draw_contour_button.click()
    assert gui.draw_contour_button.isChecked()
    gui.draw_contour_button.click()
    assert not gui.draw_contour_button.isChecked()
    gui.hide()


def test_p98_text_section_properties_on_top_and_style_toggles(app_components):
    gui, panel = app_components.gui, app_components.panel_buttons
    gui.show()
    panel.select_group("Text")
    assert gui.groupBox_11.y() < gui.groupBox_12.y()  # properties above the overlay list
    for name in ("text_bold_checkbox", "text_italic_checkbox", "text_underline_checkbox", "text_strike_checkbox"):
        button = getattr(gui, name)
        assert isinstance(button, QtWidgets.QPushButton) and button.isCheckable() and not button.icon().isNull()
    seen = []
    gui.text_bold_checkbox.setEnabled(True)  # normally enabled by selecting a text overlay
    gui.text_bold_checkbox.toggled.connect(seen.append)
    gui.text_bold_checkbox.click()
    assert seen == [True]
    gui.text_bold_checkbox.click()
    assert not gui.label_25.pixmap().isNull()
    gui.hide()


def test_p98_color_buttons_keep_a_visible_icon(app_components):
    from PyQt6 import QtGui
    c = app_components
    button = c.gui.fill_color_button
    assert button.property("iconName") == "text-fill-color"
    c.overlay_manager.set_fill_color(QtGui.QColor(255, 255, 255))  # white button -> dark icon
    dark = button.icon().pixmap(20, 20).toImage()
    c.overlay_manager.set_fill_color(QtGui.QColor(0, 0, 0))  # black button -> light icon
    light = button.icon().pixmap(20, 20).toImage()
    assert dark != light


def test_p10_panel_has_one_fixed_width_and_every_section_fits(app_components):
    gui, panel = app_components.gui, app_components.panel_buttons
    gui.show()
    width = panel.sections[MainLayout.WIDTH_SECTION].width()
    assert width == panel.width
    widths = set()
    for group, (_, entries) in MainLayout.GROUPS.items():
        panel.select_group(group)
        for label, *_ in entries:
            panel.section_buttons[label].setChecked(True)
        QtWidgets.QApplication.processEvents()
        widths.add(panel.scroll.width())
    assert len(widths) == 1  # the panel has the same width for every group
    assert {section.width() for section in panel.sections.values()} == {width}
    headers = [b for b in gui.settings_panel.findChildren(QtWidgets.QPushButton)
               if b.property("styleClass") == "MenuButton"]
    assert headers == []
    gui.hide()


@pytest.mark.skipif(sys.platform != "win32", reason="measures with the real Windows fonts")
def test_p10_no_section_is_wider_than_images_with_real_fonts():
    """The offscreen test platform has no real fonts (text gets far too wide), so measure in a real window."""
    import json
    import subprocess
    probe = Path(__file__).with_name("layout_probe.py")
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    out = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True, env=env, timeout=120,
                         cwd=Path(__file__).parents[1])
    assert out.returncode == 0, out.stderr[-2000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    images = result["Images"]
    too_wide = {label: width for label, width in result.items() if width > images}
    assert not too_wide, f"sections wider than Images ({images}px): {too_wide}"


def test_p10_pictograms_come_from_the_ui_and_exist():
    import re
    from PathManager import get_gui_file_path
    ui_text = get_gui_file_path("BildHatcher.ui").read_text(encoding="utf-8")
    used = set(re.findall(r"icons/([\w-]+)\.svg", ui_text))
    assert len(used) > 60
    missing = [name for name in used if not get_gui_file_path("icons").joinpath(f"{name}.svg").exists()]
    assert not missing
    sources = get_gui_file_path("icons").joinpath("SOURCES.md").read_text(encoding="utf-8")
    assert all(f"| {name} |" in sources for name in used)  # every icon has its origin / licence listed


def test_p10_panel_buttons_have_a_text_or_a_pictogram_with_tooltip(app_components):
    gui, panel = app_components.gui, app_components.panel_buttons
    for label, section in panel.sections.items():
        for button in section.findChildren(QtWidgets.QAbstractButton):
            if button.text().strip():
                continue
            if button.objectName() in ("",) or button.parent() is gui.default_color_buttons_layout.parentWidget()                     and not button.objectName():
                continue  # colour swatches
            assert not button.icon().isNull(), (label, button.objectName())
            assert button.toolTip(), (label, button.objectName())
    assert gui.images_ListWidget.parentWidget() is gui.inside_images_frame
    assert gui.keep_changes_button.toolTip().startswith("Set as original")
    assert not hasattr(gui, "selected_laser_label")
    assert gui.inside_jcode_settings_frame.parentWidget() is gui.laser_settings_frame
    assert gui.inside_contour_frame.parentWidget() is gui.hatch_frame


def test_p10_export_formats_short_names_and_old_configs(app_components):
    import Settings
    gui = app_components.gui
    items = [gui.power_format_combobox.itemText(i) for i in range(gui.power_format_combobox.count())]
    assert items == ["max", "scaled", "test"]
    settings = Settings.Settings(gui)
    if settings is not None:
        settings.apply_settings({"power_format": "color-scaled", "speed_format": "constant (max. Val.)"})
        assert gui.power_format_combobox.currentText() == "scaled"
        assert gui.speed_format_combobox.currentText() == "max"



def test_p105_show_hide_toggles_switch_their_pictogram(app_components):
    from PyQt6 import QtGui
    gui = app_components.gui
    on, off = QtGui.QIcon.State.On, QtGui.QIcon.State.Off
    for button in (gui.show_image_center_button, gui.draw_contour_button):
        assert button.isCheckable()
        icon = button.icon()
        assert icon.pixmap(20, 20, QtGui.QIcon.Mode.Normal, off).toImage() != \
            icon.pixmap(20, 20, QtGui.QIcon.Mode.Normal, on).toImage(), button.objectName()
    gui.show_image_center_button.click()
    assert gui.show_image_center_button.isChecked() and not gui.show_image_center_button.text()
    gui.show_image_center_button.click()
    assert not gui.show_image_center_button.isChecked()
    grid = next(a for a in gui.toolBar.actions() if a.text() == "Grid")
    assert grid.isCheckable() and not grid.icon().isNull()


def test_p106_spin_boxes_always_show_slim_arrows(app_components):
    gui = app_components.gui
    boxes = gui.findChildren(QtWidgets.QAbstractSpinBox)
    assert boxes and all(b.buttonSymbols() == QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows for b in boxes
                         if b.objectName() and not b.objectName().startswith("qt_"))
    assert "url(icons:spin-up.svg)" in QtWidgets.QApplication.instance().styleSheet()
    from PyQt6 import QtCore
    assert QtCore.QFile.exists("icons:spin-up.svg") and QtCore.QFile.exists("icons:spin-down.svg")


def test_p106_spin_box_arrow_click_steps_the_value(app_components):
    from PyQt6 import QtCore
    from PyQt6.QtTest import QTest
    gui = app_components.gui
    box = gui.pen_width_spinbox
    gui.show()
    app_components.panel_buttons.select_group("Image")
    app_components.panel_buttons.section_buttons["Color"].setChecked(True)
    QtWidgets.QApplication.processEvents()
    box.setEnabled(True)
    box.setValue(3)
    option = QtWidgets.QStyleOptionSpinBox()
    box.initStyleOption(option) if hasattr(box, "initStyleOption") else None
    option.initFrom(box)
    option.subControls = QtWidgets.QStyle.SubControl.SC_SpinBoxUp | QtWidgets.QStyle.SubControl.SC_SpinBoxDown
    up = box.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_SpinBox, option,
                                    QtWidgets.QStyle.SubControl.SC_SpinBoxUp, box)
    assert 0 < up.width() <= 16
    QTest.mouseClick(box, QtCore.Qt.MouseButton.LeftButton, pos=up.center())
    assert box.value() == 4
    gui.hide()


def test_p106_no_color_undo_button_and_imprint_in_toolbar(app_components, monkeypatch):
    gui = app_components.gui
    assert not hasattr(gui, "undo_color_button")
    bar_actions = gui.toolBar.actions()
    assert gui.actionImprint_Colors in bar_actions and gui.actionImprint_Overlays in bar_actions
    for action, button in ((gui.actionImprint_Colors, gui.imprint_color_overlays_button),
                           (gui.actionImprint_Overlays, gui.imprint_selected_tg_overlays_button)):
        was = button.isEnabled()
        button.setEnabled(False)
        assert not action.isEnabled()
        button.setEnabled(True)
        assert action.isEnabled() and not action.icon().isNull()
        button.setEnabled(was)
    from PyQt6 import QtGui
    stand_in, clicks = QtWidgets.QPushButton(), []  # (the real imprint opens dialogs)
    stand_in.clicked.connect(lambda *_: clicks.append(1))
    action = MainLayout.mirror_button(QtGui.QAction("x"), stand_in)
    action.trigger()
    stand_in.setEnabled(False)
    action.trigger()  # disabled: nothing happens
    assert clicks == [1] and not action.isEnabled()


def test_p106_font_preview_while_hovering_the_dropdown(app_components):
    """P10.6: hovering a font in the open dropdown previews it on the text selected in the scene.

    The Windows 11 style has no list mouse tracking (hover never changes the current row, `highlighted` is not
    emitted), so the preview follows mouse moves over the list; closing without a choice restores the font."""
    from PyQt6 import QtCore, QtGui
    from TextandGeometries import TextFieldOverlay
    c = app_components
    combo = c.gui.font_family_combobox
    added = []
    for family in ("Courier New", "Times New Roman"):  # the offscreen test platform may list a single font
        if combo.findText(family) < 0:
            combo.addItem(family)
            added.append(family)
    original = combo.itemText(0)
    row = next(i for i in range(combo.count()) if QtGui_family(combo.itemText(i)) != QtGui_family(original))
    item = TextFieldOverlay(font_family=original)
    item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    c.gui.image_scene.addItem(item)
    item.setSelected(True)  # selected in the scene, not the overlay store's active item
    combo.setCurrentIndex(0)
    combo.showPopup()
    view = combo.view()
    rect = view.visualRect(combo.model().index(row, 0))
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(rect.center()),
                             QtCore.QPointF(view.viewport().mapToGlobal(rect.center())), QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(view.viewport(), move)
    assert item.font.family() == QtGui_family(combo.itemText(row))
    combo.hidePopup()  # closed without choosing: back to the original font
    assert item.font.family() == QtGui_family(original)
    c.gui.image_scene.removeItem(item)
    for family in added:
        combo.removeItem(combo.findText(family))


def QtGui_family(name):
    from PyQt6 import QtGui
    return QtGui.QFont(name).family()


def test_p1210_pinned_sections_stay_visible_in_every_group(app_components):
    c = app_components
    gui, panel = c.gui, c.panel_buttons
    gui.show()
    panel.select_group("Image")
    panel.section_buttons["Masks"].setChecked(True)
    pin = panel.pin_buttons["Masks"]
    assert pin.parentWidget() is gui.draw_mask_groupbox and pin.isCheckable() and not pin.text()
    assert pin.x() > gui.draw_mask_groupbox.width() // 2 and pin.y() < 20          # top right
    pin.click()                                                                     # pin it
    assert "Masks" in panel.pinned
    panel.section_buttons["Color"].setChecked(True)                                 # another section of the group
    assert gui.draw_mask_groupbox.isVisible() and gui.image_color_frame.isVisible()
    panel.select_group("Hatching")                                                  # another group
    panel.section_buttons["Hatch"].setChecked(True)
    assert gui.draw_mask_groupbox.isVisible() and gui.hatch_frame.isVisible()
    panel.select_group(None)                                                        # even with the panel closed
    assert gui.draw_mask_groupbox.isVisible()
    import Preferences
    assert Preferences.get("panel")["pinned"] == ["Masks"]
    panel.select_group("Hatching")
    pin.click()                                                                     # unpinned: closes at once
    assert not gui.draw_mask_groupbox.isVisible()
    panel.select_group("Image")
    panel.section_buttons["Masks"].setChecked(True)
    pin.click()
    pin.click()                                                                     # unpinned while active: stays
    assert gui.draw_mask_groupbox.isVisible()
    gui.hide()


def test_p1210_pin_pictogram_outline_and_filled(app_components):
    from PyQt6 import QtGui
    pin = app_components.panel_buttons.pin_buttons["Images"]
    icon = pin.icon()
    off = icon.pixmap(16, 16, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off).toImage()
    on = icon.pixmap(16, 16, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On).toImage()
    assert off != on
    assert pin.property("styleClass") == "PinButton"


def _row_of(widget):
    """The horizontal layout a widget sits in, and its items as widget / "spacer"."""
    layout = widget.parentWidget().layout()
    found = []

    def search(lay):
        for i in range(lay.count()):
            child = lay.itemAt(i).layout()
            if child is not None:
                if child.indexOf(widget) >= 0:
                    found.append(child)
                search(child)
    if layout.indexOf(widget) >= 0:
        found.append(layout)
    search(layout)
    row = found[0]
    return row, [row.itemAt(i).widget() or "spacer" for i in range(row.count())]


def test_p1211_export_buttons_left_aligned(app_components):
    gui = app_components.gui
    row, items = _row_of(gui.export_button)
    assert isinstance(row, QtWidgets.QHBoxLayout)
    assert items == [gui.add_process_block_button, gui.remove_process_block_button, gui.export_button, "spacer"]


def test_p1211_image_colors_row_order_and_rename(app_components):
    gui = app_components.gui
    row, items = _row_of(gui.imprint_color_overlays_button)
    assert isinstance(row, QtWidgets.QHBoxLayout)
    assert items == [gui.clean_up_image_colors_button, gui.recolor_from_database_button, "spacer",
                     gui.imprint_color_overlays_button, gui.restore_uncolored_image_button]
    assert gui.restore_uncolored_image_button.toolTip().startswith("Delete all active color overlays")


def test_grid_distance_allows_400_mm(app_components):
    spin = app_components.gui.grid_distance_spinbox
    spin.setValue(400)
    assert spin.maximum() >= 400 and spin.value() == 400


def test_wheel_never_changes_spinboxes_or_dropdowns(qapp):
    from PyQt6 import QtCore, QtGui, QtWidgets
    from CustomUiElements import WheelBlocker
    WheelBlocker.install(qapp)
    panel = QtWidgets.QWidget()
    spin, combo = QtWidgets.QSpinBox(panel), QtWidgets.QComboBox(panel)
    spin.setValue(5)
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(1)
    for widget in (spin, combo):
        for delta in (120, 120):  # one direction: without the blocker the value would move
            event = QtGui.QWheelEvent(QtCore.QPointF(2, 2), QtCore.QPointF(2, 2), QtCore.QPoint(), QtCore.QPoint(0, delta),
                                      QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                                      QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            QtWidgets.QApplication.sendEvent(widget, event)
    assert spin.value() == 5 and combo.currentIndex() == 1
