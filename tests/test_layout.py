"""P8.6 / P8.7: toolbar and settings panel (built by MainLayout in the app_components fixture)."""
from PyQt6 import QtWidgets

import MainLayout


def test_panel_strip_opens_closes_and_collapses(app_components):
    c = app_components
    gui, buttons = c.gui, c.panel_buttons
    scroll = gui.settings_panel.findChild(QtWidgets.QScrollArea, "settings_panel_scroll")
    assert set(buttons) == {entry[0] for entry in MainLayout.SECTIONS if entry}
    gui.show()
    for label in MainLayout.OPEN_AT_START:
        assert buttons[label].isChecked()

    buttons["Masks"].setChecked(True)
    masks = gui.draw_mask_groupbox
    assert masks.isVisible() and gui.inside_draw_mask_groupbox.isVisible()
    MainLayout._header_of(masks).click()  # the section header closes the section
    assert not buttons["Masks"].isChecked() and not masks.isVisible()

    for button in buttons.values():
        button.setChecked(False)
    assert not scroll.isVisible()  # everything closed: only the strip is left
    buttons["Export"].setChecked(True)
    assert scroll.isVisible() and gui.export_frame.isVisible()
    gui.hide()


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
