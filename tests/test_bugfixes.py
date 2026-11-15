"""Regression tests for bugs fixed in Phase 1 (IDs refer to REVISION_PLAN.md)."""
import ezdxf
from PyQt6 import QtWidgets

import NCDataGeneration
from HelperClasses import DBColorPalette
from test_characterization import load_image, make_test_image

DB_PALETTE = DBColorPalette([
    {"color_rgb": "0,0,0", "hatch_distance": 300, "hatch_pattern": "FixedMeander", "hatch_angle": 45,
     "laser_power": 50, "speed": 40},
    {"color_rgb": "255,255,255", "hatch_distance": 500, "hatch_pattern": "FixedMeander", "hatch_angle": 0,
     "laser_power": 10, "speed": 80},
])


def test_b02_b03_automatic_hatching_runs_in_thread_and_returns(app_components):
    c = app_components
    load_image(c, make_test_image())
    ok = c.image_hatcher.create_hatching(mode="automatic", db_color_palette=DB_PALETTE, hatch_pattern=None,
                                         cyl_rad_mm=100, hatch_mode="Flat", stepsize_mm=0.1)
    assert ok is True
    assert c.data_handler.hatch_data.type == "Image: database profile"
    assert c.data_handler.hatch_data.hatch_clusters[0].data


def test_b02_failed_automatic_hatching_does_not_hang(app_components, monkeypatch):
    c = app_components
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *args: warnings.append(args))
    load_image(c, make_test_image(width_px=600))  # 60 mm wide on a 5 mm radius cylinder: > 360 degrees
    ok = c.image_hatcher.create_hatching(mode="automatic", db_color_palette=DB_PALETTE, hatch_pattern=None,
                                         cyl_rad_mm=5, hatch_mode="CylEquidistX", stepsize_mm=0.1)
    assert ok is False
    assert warnings and "too wide" in warnings[0][2]


def test_b01_dxf_import_with_arc(app_components, tmp_path, monkeypatch):
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_arc(center=(5, 5), radius=3, start_angle=350, end_angle=10)  # crosses 0 degrees
    msp.add_circle(center=(20, 5), radius=2)
    path = tmp_path / "shapes.dxf"
    doc.saveas(path)
    monkeypatch.setattr(NCDataGeneration.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))

    hatcher = app_components.image_hatcher
    hatcher.contour_from_dxf()
    hatcher.contour_from_dxf()  # second import must replace, not append

    clusters = app_components.data_handler.hatch_data.hatch_clusters
    assert len(clusters) == 1
    polylines = clusters[0].data[0].polylines
    assert len(polylines) == 3
    import numpy as np
    arc = min((p for p in polylines if len(p) > 2), key=len)  # the 20 degree arc (the circle has more points)
    radii = np.hypot(arc[:, 0] - 5, arc[:, 1] - 5)
    assert np.allclose(radii, 3, atol=0.011) and arc[0, 0] > 7.9 and arc[-1, 0] > 7.9  # short arc across 0 degrees


def _straight_polyline(n):
    from core.toolpath import polyline
    return polyline([(float(i), 0.0, 0.0, 0 if i == 0 else 1) for i in range(n)])


def _layer(*polylines):
    from core.toolpath import Layer
    return Layer((0, 0, 0), list(polylines), speed=40, power=50)


def test_b10_maximize_lines_removes_all_points_on_a_straight_line():
    from core.postprocess import PostProcessor
    result = PostProcessor().maximize_line_length([_layer(_straight_polyline(11))])
    assert result[0].polylines[0][:, 0].tolist() == [0.0, 10.0]


def test_b11_drive_modes_handle_degenerate_polylines():
    import numpy as np
    from core.postprocess import PostProcessor
    line = _straight_polyline(4)
    duplicate = np.insert(line, 2, line[1], axis=0)  # zero-length segment
    single = _straight_polyline(1)
    for mode in ("Constant Drive", "Over Drive"):
        result = PostProcessor().set_drive_mode([_layer(duplicate, single)], mode)
        assert np.isfinite(np.concatenate(result[0].polylines)).all()
        assert len(result[0].polylines[1]) == 1


def test_b15_b17_rotation_updates_center_and_drops_masks(app_components):
    import numpy as np
    from PyQt6 import QtWidgets
    c = app_components
    load_image(c, make_test_image(width_px=120, height_px=80))
    mask = np.zeros((80, 120), dtype=np.uint8)
    mask[10:20, 10:20] = 1
    overlay = QtWidgets.QGraphicsRectItem(0, 0, 10, 10)
    c.gui.image_scene.addItem(overlay)
    c.data_handler.masks_list.append(mask)
    c.data_handler.mask_info.append({'type': 'rectangle', 'coords': (10, 10, 19, 19)})
    c.data_handler.mask_overlays.append(overlay)

    c.image_controller.rot_image_90_clockwise()

    assert c.data_handler.image_matrix.shape[:2] == (120, 80)
    assert c.data_handler.center_for_hatch == [79 / 2, 119 / 2]
    assert c.data_handler.masks_list == [] and c.data_handler.mask_overlays == []
    assert overlay.scene() is None


def test_b19_settings_roundtrip_by_text_and_legacy_index(app_components):
    import Settings
    gui = app_components.gui
    settings = app_components.settings
    gui.hatch_pattern_combobox.setCurrentText("Spiral")
    gui.hatch_angle_spinbox.setValue(12.5)
    saved = settings.collect_settings(Settings.HATCHING_SETTINGS)
    assert saved["hatch_pattern"] == "Spiral"

    gui.hatch_pattern_combobox.setCurrentText("Radial")
    gui.hatch_angle_spinbox.setValue(0)
    settings.apply_settings(saved)
    assert gui.hatch_pattern_combobox.currentText() == "Spiral"
    assert gui.hatch_angle_spinbox.value() == 12.5

    settings.apply_settings({"hatch_pattern": 3})  # pre-2.0 config stored the index
    assert gui.hatch_pattern_combobox.currentText() == "Circular"


def test_b20_combine_monochrome_uses_average_colour(app_components):
    import numpy as np
    c = app_components
    a = np.full((4, 4, 3), 255, dtype=np.uint8)
    b = a.copy()
    a[0, 0] = (200, 0, 0)
    b[1, 1] = (0, 0, 100)
    load_image(c, a, name="a")
    load_image(c, b, name="b")
    c.gui.images_ListWidget.selectAll()
    c.gui.monochrome_check.setChecked(True)
    c.image_controller.combine_images()
    combined = c.image_controller.get_active_image_matrix()
    assert combined[0, 0].tolist() == [100, 0, 50, 255] == combined[1, 1].tolist()
    assert (combined[2:, 2:] == 0).all()  # background stays transparent


def test_plotting_builds_one_line_item_per_visible_layer(app_components):
    import numpy as np
    from test_characterization import run_hatching
    c = app_components
    load_image(c, make_test_image())
    result = run_hatching(c, pattern="FixedMeander", angle=45.0)
    c.hatch_line_plotter.plot_hatch_lines()
    layers = [l for l in result.hatch_clusters[0].data if l.polylines]
    items = c.hatch_line_plotter.plot_line_items
    assert len(items) == len(layers)
    expected_rows = sum(l.point_count + len(l.polylines) - 1 for l in layers)  # + NaN separators
    assert sum(len(i.pos) for i in items) == expected_rows
    assert np.isfinite(items[0].pos).any()


def test_b28_image_center_maps_to_machine_origin(app_components):
    import numpy as np
    c = app_components
    load_image(c, np.full((20, 20, 3), 255, np.uint8))  # 10 px/mm, default center = middle of the image
    c.data_handler.contours_list = [[[5, 5], [14, 5], [14, 14], [5, 14]]]  # square centred in the image
    c.image_hatcher.contour_from_image()
    line = c.data_handler.hatch_data.hatch_clusters[0].data[0].polylines[0]
    assert sorted({round(v, 6) for v in line[:, 0]}) == [-0.45, 0.45]
    assert sorted({round(v, 6) for v in line[:, 1]}) == [-0.45, 0.45]  # was shifted by -0.1 (one pixel)


def test_b17_mask_outline_follows_pixel_size_change(app_components):
    import numpy as np
    from PyQt6 import QtWidgets
    c = app_components
    load_image(c, np.zeros((40, 60, 3), np.uint8))  # 10 px/mm
    overlay = QtWidgets.QGraphicsRectItem()
    c.gui.image_scene.addItem(overlay)
    c.data_handler.masks_list.append(np.zeros((40, 60), np.uint8))
    c.data_handler.mask_info.append({'type': 'rectangle', 'coords': (10, 5, 19, 14)})
    c.data_handler.mask_overlays.append(overlay)

    c.image_controller.set_active_pixel_per_mm(5.0)  # pixels twice as large on the canvas
    c.image_controller.set_handler_data(new_image=False)
    top_left = c.gui.image_item.mapFromScene(overlay.rect().topLeft())
    bottom_right = c.gui.image_item.mapFromScene(overlay.rect().bottomRight())
    assert (round(top_left.x(), 6), round(top_left.y(), 6)) == (10, 5)  # still on the mask pixels
    assert (round(bottom_right.x(), 6), round(bottom_right.y(), 6)) == (20, 15)


def test_p73_unhandled_exceptions_are_shown_not_fatal(qapp, monkeypatch):
    import main
    from PyQt6 import QtWidgets
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *args: shown.append(args))
    try:
        raise ValueError("boom")
    except ValueError as e:
        main.show_unhandled_exception(type(e), e, e.__traceback__)
    assert shown and "ValueError: boom" in shown[0][2]
