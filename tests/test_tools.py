"""P9.10: hotkeys for the colour tools and the active-tool indicator."""
from PyQt6 import QtWidgets

import Tools


def _key(c, letter):
    """Fire the hotkey (offscreen there is no active window for real key events to reach a shortcut)."""
    shortcut = c.tools.shortcuts[letter]
    assert shortcut.key().toString() == letter and shortcut.isEnabled()
    shortcut.activated.emit()
    QtWidgets.QApplication.processEvents()


def test_hotkeys_switch_tools_even_with_hidden_section(app_components):
    c = app_components
    gui, colorer = c.gui, c.image_colorer
    gui.show()
    gui.activateWindow()
    c.panel_buttons.select_group(None)  # panel closed: the Color section is hidden
    assert not gui.toggle_draw_button.isVisible()
    gui.setFocus()

    _key(c, "D")
    assert colorer.color_drawing_on and colorer.active_tool == "Draw" and gui.toggle_draw_button.isChecked()
    _key(c, "F")
    assert colorer.flood_fill_color_on and not colorer.color_drawing_on
    _key(c, "R")
    assert colorer.replace_color_on and colorer.active_tool == "Replace"
    _key(c, "P")
    assert colorer.choose_color_on
    _key(c, "P")  # same key again: off, like clicking the button again
    assert colorer.active_tool == ""
    _key(c, "T")
    assert colorer.active_color[3] == 0
    gui.hide()


def test_hotkeys_ignored_while_typing(app_components):
    c = app_components
    gui = c.gui
    gui.show()
    c.panel_buttons.select_group("Text")
    gui.text_input_lineedit.setEnabled(True)
    gui.text_input_lineedit.setFocus()
    QtWidgets.QApplication.processEvents()
    assert Tools.typing_focus() or not gui.text_input_lineedit.hasFocus()
    before = c.image_colorer.active_tool
    if gui.text_input_lineedit.hasFocus():
        assert c.tools.trigger("toggle_draw_button") is False
        assert c.image_colorer.active_tool == before
    gui.hide()


def test_more_colors_hotkey_opens_the_dialog(app_components, monkeypatch):
    c = app_components
    asked = []
    monkeypatch.setattr(c.image_colorer, "select_color", lambda: asked.append(1) or [10, 20, 30])
    c.gui.show()
    c.gui.setFocus()
    _key(c, "C")
    assert asked == [1] and c.image_colorer.active_color[:3] == [10, 20, 30]
    c.gui.hide()


def test_indicator_follows_tool_and_colour(app_components):
    c = app_components
    indicator = c.gui.toolBar.findChild(QtWidgets.QLabel, "active_tool_indicator")
    assert indicator is not None
    c.image_colorer.set_active_color([0, 0, 255])
    assert "R0 G0 B255" in indicator.toolTip()
    c.tools.trigger("flood_fill_button", from_key=False)
    assert "Active tool: Fill" in indicator.toolTip()
    c.tools.trigger("flood_fill_button", from_key=False)
    assert "Active tool: none" in indicator.toolTip()
    assert "(D)" in c.gui.toggle_draw_button.toolTip()
