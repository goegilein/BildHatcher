"""
Characterization ("golden master") tests for the hatching -> post-processing -> G-code pipeline.

They pin down the output of the code as it was before the 2.0 revision (REVISION_PLAN.md, P0.6),
so ports and refactors can be checked for unintended behaviour changes.

Regenerate golden files (only when an output change is intended and documented in the plan):
    UPDATE_GOLDEN=1 python -m pytest tests/test_characterization.py
"""
import difflib
import os
import random
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PyQt6 import QtCore

from core import image_doc
from core.image_doc import ImageDocument
from core import gcode

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"
PIXEL_PER_MM = 10.0


# --------------------------------------------------------------------------- helpers

def make_test_image(width_px=120, height_px=80):
    """Deterministic, non-antialiased test image: three coloured shapes on white."""
    img = np.full((height_px, width_px, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (55, 45), (220, 30, 30), thickness=-1)
    cv2.circle(img, (int(width_px * 0.7), int(height_px * 0.45)), 22, (30, 60, 200), thickness=-1)
    triangle = np.array([[20, height_px - 8], [60, height_px - 8], [40, 50]], dtype=np.int32)
    cv2.fillPoly(img, [triangle], (90, 90, 90))
    return img


def load_image(c, image_matrix, ppm=PIXEL_PER_MM, name="test.png"):
    """Mimics ImageControlling.BaseFunctions.load_image without the file dialog (pure white -> transparent)."""
    image_matrix = image_doc.from_rgb(image_matrix) if image_matrix.shape[2] == 3 else image_matrix
    ctrl = c.image_controller
    ctrl.changeing_image = True
    ctrl.add_listbox_item(ImageDocument(image_matrix.copy(), image_matrix.copy(), ppm, ppm), name, set_selected=True)
    ctrl.changeing_image = False
    ctrl.set_handler_data(new_image=True)
    ctrl.update_dimension_fields()


def run_hatching(c, pattern, angle=45.0, dist_mode="ColorRanged", dist_min=300, dist_max=700,
                 hatch_mode="Flat", cyl_rad=100.0, precision=0.1, seed=1234):
    """Runs the hatcher synchronously (no worker thread) with the given GUI settings."""
    gui = c.gui
    gui.hatch_pattern_combobox.setCurrentText(pattern)
    gui.hatch_angle_spinbox.setValue(angle)
    gui.hatch_dist_mode_combobox.setCurrentText(dist_mode)
    gui.hatch_dist_min_spinbox.setValue(dist_min)
    gui.hatch_dist_max_spinbox.setValue(dist_max)
    gui.hatch_mode_combobox.setCurrentText(hatch_mode)
    gui.cyl_rad_spinbox.setValue(cyl_rad)
    gui.hatch_precision_spinbox.setValue(precision)

    hatcher = c.image_hatcher
    hatcher.worker = SimpleNamespace(progress=SimpleNamespace(emit=lambda *_: None))  # stub: no thread
    hatcher.hatching_cancelled = False
    hatcher._last_progress = 0

    random.seed(seed)
    result = hatcher.create_hatching_worker(**hatcher.collect_hatch_settings("manual"))
    assert result is not None, "hatching returned no result"
    hatcher.hatching_finished(result)
    return result


def run_parser(c, post_processing="None", power_format="scaled", speed_format="max",
               min_power=10, max_power=80, min_speed=20, max_speed=60,
               laser_mode="constant", air_assist="off", power_mode="half", offset=(0, 0, 0)):
    """Creates a process block from the active hatch data and renders its G-code body."""
    gui = c.gui
    gui.post_processing_combobox.setCurrentText(post_processing)
    gui.power_format_combobox.setCurrentText(power_format)
    gui.speed_format_combobox.setCurrentText(speed_format)
    gui.min_power_spinbox.setValue(min_power)
    gui.max_power_spinbox.setValue(max_power)
    gui.min_speed_spinbox.setValue(min_speed)
    gui.max_speed_spinbox.setValue(max_speed)
    gui.laser_mode_combobox.setCurrentText(laser_mode)
    gui.air_assist_combobox.setCurrentText(air_assist)
    gui.power_mode_combobox.setCurrentText(power_mode)
    gui.offset_x_spinbox.setValue(offset[0])
    gui.offset_y_spinbox.setValue(offset[1])
    gui.offset_z_spinbox.setValue(offset[2])

    parser = c.parser
    parser.process_listWidget.clear()
    parser.add_process_block(1)
    block = parser.process_listWidget.item(0).data(QtCore.Qt.ItemDataRole.UserRole)

    lines = [f"; hatch type: {c.data_handler.hatch_data.type}"]
    for idx, cluster in enumerate(block.hatch_data.hatch_clusters):
        lines.append(f"; cluster {idx} ref_position {[round(float(v), 6) for v in cluster.ref_position]}")
        lines.extend(gcode.generate_gcode(block, idx))
    return "\n".join(lines) + "\n"


def assert_golden(name, text):
    path = GOLDEN_DIR / f"{name}.gcode"
    if UPDATE_GOLDEN or not path.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        if not UPDATE_GOLDEN:
            pytest.skip(f"golden file {path.name} created")
        return
    expected = path.read_text(encoding="utf-8")
    if text != expected:
        diff = "".join(list(difflib.unified_diff(
            expected.splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile=f"golden/{path.name}", tofile="actual", n=1))[:60])
        pytest.fail(f"output differs from golden file {path.name}:\n{diff}")


# --------------------------------------------------------------------------- tests

FLAT_PATTERNS = [
    ("flat_fixed_meander_45", dict(pattern="FixedMeander", angle=45.0)),
    ("flat_fixed_meander_0", dict(pattern="FixedMeander", angle=0.0)),
    ("flat_fixed_meander_90", dict(pattern="FixedMeander", angle=90.0, dist_mode="Fixed")),
    ("flat_random_meander", dict(pattern="RandomMeander")),
    ("flat_crossed_meander_30", dict(pattern="CrossedMeander", angle=30.0)),
    ("flat_circular", dict(pattern="Circular")),
    ("flat_spiral", dict(pattern="Spiral")),
    ("flat_radial", dict(pattern="Radial")),
]


@pytest.mark.parametrize("name,hatch_kwargs", FLAT_PATTERNS, ids=[n for n, _ in FLAT_PATTERNS])
def test_flat_patterns(app_components, name, hatch_kwargs):
    load_image(app_components, make_test_image())
    run_hatching(app_components, **hatch_kwargs)
    assert_golden(name, run_parser(app_components))


POST_PROCESSING = [
    ("post_maximize_lines", dict(pattern="Circular"), "Maximize Lines"),
    ("post_constant_drive", dict(pattern="FixedMeander", angle=0.0), "Constant Drive"),
    ("post_over_drive", dict(pattern="FixedMeander", angle=30.0), "Over Drive"),
]


@pytest.mark.parametrize("name,hatch_kwargs,post", POST_PROCESSING, ids=[n for n, _, _ in POST_PROCESSING])
def test_post_processing(app_components, name, hatch_kwargs, post):
    load_image(app_components, make_test_image())
    run_hatching(app_components, **hatch_kwargs)
    assert_golden(name, run_parser(app_components, post_processing=post, speed_format="scaled",
                                   offset=(1.5, -2.0, 0.25)))


CYLINDRICAL = [
    # 60 mm wide image on a 20 mm radius cylinder -> split into 2 clusters
    ("cyl_equidist_x_meander", dict(pattern="FixedMeander", angle=0.0, hatch_mode="CylEquidistX", cyl_rad=20.0)),
    ("cyl_equidist_rad_meander", dict(pattern="FixedMeander", angle=60.0, hatch_mode="CylEquidistRad", cyl_rad=20.0)),
]


@pytest.mark.parametrize("name,hatch_kwargs", CYLINDRICAL, ids=[n for n, _ in CYLINDRICAL])
def test_cylindrical(app_components, name, hatch_kwargs):
    load_image(app_components, make_test_image(width_px=600, height_px=80))
    result = run_hatching(app_components, **hatch_kwargs)
    assert len(result.hatch_clusters) == 2
    assert_golden(name, run_parser(app_components))


def test_contours_from_image(app_components):
    c = app_components
    load_image(c, make_test_image())
    c.gui.contouring_mode_combobox.setCurrentText("only external")
    c.gui.contour_sensitivity_spinbox.setValue(50)
    c.gui.contour_thickness_spinbox.setValue(1)
    c.gui.contour_space_spinbox.setValue(1)
    c.image_colorer.find_image_contours()
    assert c.data_handler.contours_list, "no contours found"
    c.image_hatcher.contour_from_image()
    assert_golden("contours_from_image", run_parser(c))


def test_test_structure_to_process_block(app_components):
    c = app_components
    c.gui.test_structure_combobox.setCurrentText("Filled Squares Horz.")
    c.gui.structnum_pwr_spinbox.setValue(2)
    c.gui.structnum_speed_spinbox.setValue(2)
    c.gui.struct_size_spinbox.setValue(1.0)
    c.gui.struct_hDist_spinbox.setValue(0.25)
    c.test_structure.create_test_structure()
    assert_golden("test_structure_filled_squares_horz",
                  run_parser(c, power_format="test", speed_format="test"))


@pytest.mark.parametrize("pattern", ["FixedMeander", "Radial"])
def test_full_bleed_image(app_components, pattern):
    """Colours touching all image edges (B30: edge pixels at the low edges were shifted)."""
    img = np.zeros((40, 60, 3), np.uint8)
    img[:, :30] = (220, 30, 30)
    img[:, 30:] = (30, 60, 200)
    load_image(app_components, img)
    run_hatching(app_components, pattern=pattern, angle=30.0)
    assert_golden(f"full_bleed_{pattern.lower()}", run_parser(app_components))
