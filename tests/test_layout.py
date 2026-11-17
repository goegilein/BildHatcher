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


def test_toolbar_has_image_menu_profiles_and_view_controls(app_components):
    gui = app_components.gui
    bar = gui.toolBar
    texts = [a.text() for a in bar.actions()]
    assert {"Load Image", "Save Image", "Reset Zoom", "Re-center", "Grid"} <= set(texts)
    assert any(t.startswith("Color Profile") for t in texts)
    image_button = next(w for w in bar.findChildren(QtWidgets.QToolButton) if w.toolTip() == "Image operations")
    menu_texts = [a.text() for a in image_button.menu().actions()]
    assert "Make Bright Colors Transparent..." in menu_texts and "Rotate 90°" in menu_texts
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
