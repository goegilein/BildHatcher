"""P8.6 / P8.7 / P9.3-P9.5: toolbar and settings panel (built by MainLayout in the app_components fixture)."""
from PyQt6 import QtWidgets

import MainLayout
import Preferences


def test_panel_groups_single_select_sections_multi_select(app_components):
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
    for label in ("Hatch", "Export"):  # several subsections at once
        panel.section_buttons[label].setChecked(True)
    assert gui.hatch_frame.isVisible() and gui.export_frame.isVisible()
    assert gui.inside_contour_frame.parentWidget() is gui.hatch_frame  # Contours merged into Hatch (P9.4)
    assert Preferences.get("panel")["group"] == "Hatching"
    assert {"Hatch", "Export"} <= set(Preferences.get("panel")["open"]["Hatching"])

    panel.group_buttons["Hatching"].click()  # clicking the active group closes the panel
    assert panel.group is None and not scroll.isVisible() and not panel.sub_strip.isVisible()
    panel.select_group("Hatching")  # the open subsections are remembered
    assert gui.hatch_frame.isVisible() and gui.export_frame.isVisible()
    gui.hide()


def test_panel_keeps_natural_width_and_has_no_section_headers(app_components):
    gui, panel = app_components.gui, app_components.panel_buttons
    gui.show()
    panel.select_group("Automation")
    scroll = panel.scroll
    assert scroll.width() < 700  # sized to the content, not stretched
    assert gui.inside_jcode_settings_frame.parentWidget() is gui.laser_settings_frame
    headers = [b for b in gui.settings_panel.findChildren(QtWidgets.QPushButton)
               if b.property("styleClass") == "MenuButton"]
    assert headers == []
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


def test_p96_images_section_pictograms(app_components):
    gui = app_components.gui
    names = [entry[0] for entry in MainLayout.IMAGE_BUTTONS]
    for name in names:
        button = getattr(gui, name)
        assert button.text() == "" and button.toolTip() and not button.icon().isNull()
        assert button.window() is gui
    assert gui.keep_changes_button.toolTip().startswith("Set as original")
    assert not hasattr(gui, "monochrome_check")
    assert gui.images_ListWidget.parentWidget() is gui.inside_images_frame


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
    assert button.property("iconName") == "paint"
    c.overlay_manager.set_fill_color(QtGui.QColor(255, 255, 255))  # white button -> dark icon
    dark = button.icon().pixmap(20, 20).toImage()
    c.overlay_manager.set_fill_color(QtGui.QColor(0, 0, 0))  # black button -> light icon
    light = button.icon().pixmap(20, 20).toImage()
    assert dark != light
