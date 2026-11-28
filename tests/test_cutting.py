"""Cutting section: drawn laser paths (line, rectangle, ellipse, triangle, hexagon) -> toolpath / DXF."""
import math

import ezdxf
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from core import cut_shapes
from core.toolpath import MOVE_BURN, MOVE_TRAVEL
from NCDataGeneration import dxf_polylines
from test_characterization import load_image

PPM = 10.0  # test_characterization.PIXEL_PER_MM


# --- pure geometry ---
@pytest.mark.parametrize("shape, corners", [("rectangle", 4), ("triangle", 3), ("hexagon", 6)])
def test_polygons_are_closed(shape, corners):
    p = cut_shapes.outline(shape, 20, 10)
    assert len(p) == corners + 1 and np.allclose(p[0], p[-1])
    assert np.allclose(p[:, 0].min(), -10) and np.allclose(p[:, 0].max(), 10)
    assert np.allclose(p[:, 1].min(), -5) and np.allclose(p[:, 1].max(), 5)


def test_line_and_mirrored_line():
    assert cut_shapes.outline("line", 4, 2).tolist() == [[-2, -1], [2, 1]]
    assert cut_shapes.outline("line", 4, 2, mirrored=True).tolist() == [[-2, 1], [2, -1]]


def test_ellipse_polygon_within_tolerance():
    rx, ry, tol = 300.0, 120.0, 0.1
    p = cut_shapes.outline("ellipse", 2 * rx, 2 * ry, tolerance=tol)
    assert np.allclose(p[0], p[-1])
    # every chord midpoint lies within the tolerance of the true curve (radial check on the unit circle scale)
    mid = (p[:-1] + p[1:]) / 2
    r = np.hypot(mid[:, 0] / rx, mid[:, 1] / ry)
    assert np.max((1 - r) * max(rx, ry)) <= tol + 1e-9


def test_to_mm_relative_to_center_y_up():
    assert cut_shapes.to_mm([[110, 40]], (100, 50), 10).tolist() == [[1.0, 1.0]]


# --- in the app ---
@pytest.fixture
def cutting(app_components):
    load_image(app_components, np.zeros((100, 200, 4), np.uint8))  # hatch centre (99.5, 49.5), 10 px/mm
    return app_components


def test_section_in_hatching_group(cutting):
    import MainLayout
    assert ("Cutting" in [label for label, _, _ in MainLayout.GROUPS["Hatching"][1]])
    gui = cutting.gui
    assert gui.cutting_frame.width() <= gui.images_frame.width() or not gui.cutting_frame.isVisible()
    assert gui.cutting_frame.minimumSizeHint().width() <= gui.images_frame.width()
    for button in list(gui.cut_shape_buttons.values()) + [gui.cut_delete_button, gui.cut_delete_all_button,
                                                           gui.cut_export_button, gui.cut_use_as_hatch_button]:
        assert not button.icon().isNull()


def test_fields_show_size_and_centre_relative_to_hatch_centre(cutting):
    m, gui = cutting.cutting, cutting.gui
    item = m.add_overlay("rectangle", (5, -2), 20, 10, rotation=30)
    assert gui.cut_list_widget.count() == 1 and gui.cut_list_widget.item(0).isSelected()
    assert gui.cut_width_spinbox.value() == pytest.approx(20)
    assert gui.cut_height_spinbox.value() == pytest.approx(10)
    assert gui.cut_x_spinbox.value() == pytest.approx(5) and gui.cut_y_spinbox.value() == pytest.approx(-2)
    assert gui.cut_rotation_spinbox.value() == pytest.approx(30)
    gui.cut_width_spinbox.setValue(30)  # resized around the centre
    assert item.size()[0] == pytest.approx(300) and m.center_mm(item) == pytest.approx((5, -2))
    gui.cut_x_spinbox.setValue(-1.5)
    assert m.center_mm(item) == pytest.approx((-1.5, -2))
    cutting.data_handler.undo_manager.undo()
    assert m.center_mm(item) == pytest.approx((5, -2))


def test_fix_position(cutting):
    m, gui = cutting.cutting, cutting.gui
    item = m.add_overlay("ellipse", (0, 0), 10, 10)
    gui.cut_fix_checkbox.click()
    assert item.fixed and not (item.flags() & item.GraphicsItemFlag.ItemIsMovable)
    assert not gui.cut_x_spinbox.isEnabled() and not gui.cut_y_spinbox.isEnabled()
    m._on_position_edited()  # ignored while fixed
    assert m.center_mm(item) == pytest.approx((0, 0))
    gui.cut_height_spinbox.setValue(4)  # size still editable, the centre stays
    assert m.center_mm(item) == pytest.approx((0, 0)) and item.size()[1] == pytest.approx(40)
    assert "(fixed)" in gui.cut_list_widget.item(0).text()


def test_drawing_with_the_mouse_logic(cutting):
    m, gui = cutting.cutting, cutting.gui
    gui.cut_shape_buttons["line"].click()
    assert m.draw_shape == "line"
    m.start_drawing(QtCore.QPointF(50, 60))
    m.drag_drawing(QtCore.QPointF(90, 20))  # up to the right: mirrored line
    m.finish_drawing()
    assert m.draw_shape is None and not gui.cut_shape_buttons["line"].isChecked()
    [item] = m.store.items
    assert item.mirrored and item.size() == pytest.approx((40, 40))
    ends = item.image_outline()
    assert np.allclose(ends, [[50, 60], [90, 20]])
    cutting.data_handler.undo_manager.undo()
    assert not m.store.items and gui.cut_list_widget.count() == 0
    m.set_draw_shape("hexagon")
    m.start_drawing(QtCore.QPointF(10, 10))
    m.drag_drawing(QtCore.QPointF(30, 12), regular=True)  # Shift: regular hexagon
    m.finish_drawing()
    w, h = m.store.items[-1].size()
    assert h == pytest.approx(w * math.sqrt(3) / 2)


def test_click_without_drag_draws_nothing(cutting):
    m = cutting.cutting
    m.set_draw_shape("rectangle")
    m.start_drawing(QtCore.QPointF(10, 10))
    m.finish_drawing()
    assert not m.store.items


def test_use_selected_as_hatch(cutting):
    m = cutting.cutting
    rect = m.add_overlay("rectangle", (1, 2), 4, 2)
    circle = m.add_overlay("ellipse", (-3, 0), 2, 2)
    m.add_overlay("line", (0, 0), 5, 0)  # not selected: not used
    cutting.gui.image_scene.clearSelection()
    rect.setSelected(True)
    circle.setSelected(True)
    hatch = m.use_selected_as_hatch()
    assert hatch.type == "Cutting" and cutting.data_handler.hatch_data is hatch
    rect_path, circle_path = hatch.hatch_clusters[0].data[0].polylines
    assert rect_path[0, 3] == MOVE_TRAVEL and (rect_path[1:, 3] == MOVE_BURN).all()
    assert np.allclose(rect_path[0, :2], rect_path[-1, :2])  # closed
    assert sorted(map(tuple, np.round(rect_path[:-1, :2], 6))) == [(-1, 1), (-1, 3), (3, 1), (3, 3)]
    r = np.hypot(circle_path[:, 0] + 3, circle_path[:, 1])
    assert np.all(r <= 1 + 1e-9) and np.all(r >= 1 - cut_shapes.FLATTEN_TOLERANCE_MM - 1e-9)


def test_rotation_is_applied_to_the_toolpath(cutting):
    m = cutting.cutting
    m.add_overlay("line", (0, 0), 10, 0, rotation=90)  # canvas rotation 90° clockwise: horizontal -> vertical
    [path] = m.use_selected_as_hatch().hatch_clusters[0].data[0].polylines
    assert np.allclose(np.abs(path[:, 0]), 0, atol=1e-9) and sorted(np.round(path[:, 1], 6)) == [-5, 5]


def test_export_dxf(cutting, tmp_path):
    m = cutting.cutting
    m.add_overlay("hexagon", (10, 0), 4, 2)
    m.add_overlay("ellipse", (0, 5), 6, 2, rotation=45)
    m.add_overlay("line", (0, 0), 3, 4)
    for item in m.store.items:
        item.setSelected(True)
    path = m.export_selected_dxf(str(tmp_path / "cut.dxf"))
    doc = ezdxf.readfile(path)
    kinds = sorted(e.dxftype() for e in doc.modelspace())
    assert kinds == ["ELLIPSE", "LINE", "LWPOLYLINE"] and doc.units == ezdxf.units.MM
    ellipse = next(e for e in doc.modelspace() if e.dxftype() == "ELLIPSE")
    assert tuple(ellipse.dxf.center)[:2] == pytest.approx((0, 5))
    assert math.hypot(*tuple(ellipse.dxf.major_axis)[:2]) == pytest.approx(3) and ellipse.dxf.ratio == pytest.approx(1 / 3)
    hexagon = next(p for p in dxf_polylines(doc.modelspace()) if len(p) == 7)  # imported again: closed polygon
    assert hexagon[:, 0].min() == pytest.approx(8) and hexagon[:, 0].max() == pytest.approx(12)


def test_delete_selected_and_all(cutting, monkeypatch):
    m, gui = cutting.cutting, cutting.gui
    a = m.add_overlay("rectangle", (0, 0), 2, 2)
    m.add_overlay("triangle", (3, 0), 2, 2)
    gui.image_scene.clearSelection()
    a.setSelected(True)
    gui.cut_delete_button.click()
    assert len(m.store.items) == 1 and a.scene() is None
    cutting.data_handler.undo_manager.undo()
    assert len(m.store.items) == 2 and a.scene() is not None
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    gui.cut_delete_all_button.click()
    assert not m.store.items and gui.cut_list_widget.count() == 0


def test_list_and_canvas_selection_stay_in_sync(cutting):
    m, gui = cutting.cutting, cutting.gui
    a = m.add_overlay("rectangle", (0, 0), 2, 2)
    b = m.add_overlay("ellipse", (3, 0), 2, 2)
    gui.cut_list_widget.item(0).setSelected(True)
    gui.cut_list_widget.item(1).setSelected(False)
    assert a.isSelected() and not b.isSelected()
    b.setSelected(True)
    assert gui.cut_list_widget.item(1).isSelected()
    assert not gui.cut_width_spinbox.isEnabled()  # two selected: no single size to edit


def test_drawing_with_real_mouse_events(cutting):
    from PyQt6.QtTest import QTest
    m, gui = cutting.cutting, cutting.gui
    gui.resize(1200, 800)
    gui.show()
    QtWidgets.QApplication.processEvents()
    viewport = gui.image_canvas.viewport()

    def view_point(x, y):  # image pixel -> viewport position
        return gui.image_canvas.mapFromScene(gui.image_item.mapToScene(QtCore.QPointF(x, y)))

    gui.cut_shape_buttons["rectangle"].click()
    a, b = view_point(20, 20), view_point(80, 60)
    QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(viewport, b)
    QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, b)
    [item] = m.store.items
    xs, ys = item.image_outline()[:, 0], item.image_outline()[:, 1]
    scale = gui.image_canvas.transform().m11() * gui.image_item.scale()
    assert abs(xs.min() - 20) <= 1 / scale + 0.5 and abs(xs.max() - 80) <= 1 / scale + 0.5
    assert abs(ys.min() - 20) <= 1 / scale + 0.5 and abs(ys.max() - 60) <= 1 / scale + 0.5
    assert m.draw_shape is None


def test_cutting_hatch_is_plotted_and_exported(cutting):
    from test_characterization import run_parser
    m = cutting.cutting
    m.add_overlay("rectangle", (0, 0), 4, 2)
    m.use_selected_as_hatch()
    cutting.hatch_line_plotter.plot_data()
    gcode = run_parser(cutting)
    assert gcode.count("G1") >= 4  # the four burnt edges of the rectangle
