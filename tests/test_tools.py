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
    c.panel_buttons.select_group("Image Editing")
    c.panel_buttons.section_buttons["Text and Shapes"].setChecked(True)
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


def _mouse(kind, button, buttons, pos):
    from PyQt6 import QtCore, QtGui
    point = QtCore.QPointF(*pos)
    return QtGui.QMouseEvent(kind, point, point, button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)


def test_tool_wheel_hold_hover_release_selects(app_components):
    from PyQt6 import QtCore
    import time
    c = app_components
    wheel, viewport = c.tool_wheel, c.gui.image_canvas.viewport()
    Type, B = QtCore.QEvent.Type, QtCore.Qt.MouseButton
    c.gui.resize(1400, 900)
    c.gui.show()
    c.image_colorer.set_single_toggle_state('')
    centre = (viewport.width() / 2, viewport.height() / 2)
    assert wheel.on_canvas_event(_mouse(Type.MouseButtonPress, B.RightButton, B.RightButton, centre)) is True
    assert wheel.isVisible()
    # the "Fill" sector (index 1, upper right): move there with the button held, release
    import math
    a = math.radians(1 * 360 / len(Tools.TOOLS) - 90)
    target = (centre[0] + 60 * math.cos(a), centre[1] + 60 * math.sin(a))
    wheel.on_canvas_event(_mouse(Type.MouseMove, B.NoButton, B.RightButton, target))
    assert wheel.highlight == 1
    time.sleep(0.01)
    wheel.on_canvas_event(_mouse(Type.MouseButtonRelease, B.RightButton, B.NoButton, target))
    assert not wheel.isVisible() and c.image_colorer.active_tool == "Fill"

    # release in the centre after a while: cancel
    wheel.CLICK_MS = 0
    wheel.on_canvas_event(_mouse(Type.MouseButtonPress, B.RightButton, B.RightButton, centre))
    wheel.on_canvas_event(_mouse(Type.MouseButtonRelease, B.RightButton, B.NoButton, centre))
    assert not wheel.isVisible() and c.image_colorer.active_tool == "Fill"
    c.gui.hide()


def test_tool_wheel_short_click_stays_open_and_left_click_is_not_drawn(app_components):
    from PyQt6 import QtCore
    import math
    c = app_components
    wheel, viewport = c.tool_wheel, c.gui.image_canvas.viewport()
    Type, B = QtCore.QEvent.Type, QtCore.Qt.MouseButton
    c.gui.resize(1400, 900)
    c.gui.show()
    c.image_colorer.set_single_toggle_state('')
    wheel.CLICK_MS = 10_000
    centre = (viewport.width() / 2, viewport.height() / 2)
    wheel.on_canvas_event(_mouse(Type.MouseButtonPress, B.RightButton, B.RightButton, centre))
    wheel.on_canvas_event(_mouse(Type.MouseButtonRelease, B.RightButton, B.NoButton, centre))
    assert wheel.isVisible() and wheel.sticky  # short click: stays open
    a = math.radians(0 - 90)  # "Draw" sector at the top
    target = (centre[0] + 60 * math.cos(a), centre[1] + 60 * math.sin(a))
    press = _mouse(Type.MouseButtonPress, B.LeftButton, B.LeftButton, target)
    # through the event handler: the filter consumes it, the colour tools never see the click
    seen = []
    c.event_handler.canvas_event_callbacks.insert(0, lambda e: seen.append(e.type()))
    try:
        assert c.event_handler.eventFilter(viewport, press) is True
    finally:
        c.event_handler.canvas_event_callbacks.pop(0)
    assert Type.MouseButtonPress not in seen  # (selecting Draw changes the cursor, that event may pass)
    assert not wheel.isVisible() and c.image_colorer.active_tool == "Draw"
    c.gui.hide()
