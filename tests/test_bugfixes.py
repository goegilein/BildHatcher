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
                                         cyl_rad_mm=100, hatch_mode="Flat", stepsize_mm=0.1, white_threshold=254)
    assert ok is True
    assert c.data_handler.hatch_data.type == "Image: database profile"
    assert c.data_handler.hatch_data.hatch_clusters[0].data


def test_b02_failed_automatic_hatching_does_not_hang(app_components, monkeypatch):
    c = app_components
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *args: warnings.append(args))
    load_image(c, make_test_image(width_px=600))  # 60 mm wide on a 5 mm radius cylinder: > 360 degrees
    ok = c.image_hatcher.create_hatching(mode="automatic", db_color_palette=DB_PALETTE, hatch_pattern=None,
                                         cyl_rad_mm=5, hatch_mode="CylEquidistX", stepsize_mm=0.1, white_threshold=254)
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
    polylines = clusters[0].data[0]
    assert len(polylines) == 3
    arc = next(p for p in polylines if len(p) not in (2, 101))
    assert len(arc) == 7  # 20 degree sweep -> ceil(20/360*100)=6 segments -> 7 points
