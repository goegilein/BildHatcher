"""Only one canvas tool at a time: choosing a tool ends the active one (Tools.SingleActiveTool)."""
import numpy as np
import pytest
from PyQt6 import QtCore

from test_characterization import load_image

# how to switch each tool on, as the user does (buttons, the cutting shapes)
SWITCH_ON = {
    "color": lambda c: c.gui.toggle_draw_button.click(),
    "mask": lambda c: c.gui.rectangle_mask_button.click(),
    "text": lambda c: c.gui.add_text_button.click(),
    "geometry": lambda c: c.gui.add_geometry_button.click(),
    "center": lambda c: c.gui.set_image_center_button.click(),
    "cutting": lambda c: c.gui.cut_shape_buttons["ellipse"].click(),
}
GROUP = {"mask": "color"}  # mask tools belong to the colour tools (one state machine)


@pytest.fixture
def tools(app_components):
    load_image(app_components, np.full((50, 80, 4), (200, 40, 40, 255), np.uint8))
    return app_components


@pytest.mark.parametrize("first", list(SWITCH_ON))
@pytest.mark.parametrize("second", list(SWITCH_ON))
def test_a_new_tool_ends_the_old_one(tools, first, second):
    if first == second:
        return
    c = tools
    SWITCH_ON[first](c)
    assert c.single_tool.active() == [GROUP.get(first, first)]
    SWITCH_ON[second](c)
    assert c.single_tool.active() == [GROUP.get(second, second)]


def test_the_ended_tool_is_really_off(tools):
    c, gui = tools, tools.gui
    gui.toggle_draw_button.click()
    gui.cut_shape_buttons["line"].click()
    assert not gui.toggle_draw_button.isChecked() and not c.image_colorer.color_drawing_on
    assert gui.cut_shape_buttons["line"].isChecked() and c.cutting.draw_shape == "line"
    assert gui.image_canvas.viewport().cursor().shape() == QtCore.Qt.CursorShape.CrossCursor
    gui.add_text_button.click()
    assert c.cutting.draw_shape is None and not gui.cut_shape_buttons["line"].isChecked()
    assert c.overlay_manager.mode == c.overlay_manager.MODE_ADD_TEXT
    gui.set_image_center_button.click()
    assert c.overlay_manager.mode == c.overlay_manager.MODE_IDLE and not gui.add_text_button.isChecked()
    assert c.image_sizer.setting_image_center
    gui.polygon_mask_button.click()
    assert not c.image_sizer.setting_image_center and not gui.set_image_center_button.isChecked()
    assert c.image_colorer.mask_drawing_on


def test_hotkey_tool_ends_a_drawing_tool(tools):
    c, gui = tools, tools.gui
    c.cutting.set_draw_shape("rectangle")  # (also when switched on in code)
    assert c.single_tool.active() == ["cutting"]
    c.tools.trigger("flood_fill_button")  # hotkey F
    assert c.single_tool.active() == ["color"] and not gui.cut_shape_buttons["rectangle"].isChecked()
