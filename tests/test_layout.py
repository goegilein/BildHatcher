"""P8.6 / P8.7 / P9.3-P9.5 / P10: toolbar and settings panel (built by MainLayout in the app_components fixture)."""
import os
import sys
from pathlib import Path

import pytest
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
