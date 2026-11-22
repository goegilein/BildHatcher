"""Fixes made on main while v2.0 was built, ported into the v2 structure."""
import numpy as np
import pytest

from core.postprocess import PostProcessor
from ImageUpscaling import ImageUpscaler


def test_constant_drive_length_has_a_100_percent_buffer_and_decelerates_from_rapid():
    length = PostProcessor.const_drive_length
    assert length(35, 0, 3000) == pytest.approx(2 * 35**2 / 6000)              # lead-out: stop from burn speed
    assert length(100, 35, 3000) == pytest.approx(2 * (100**2 - 35**2) / 6000)  # lead-in: from rapid to burn speed
    assert length(10, 50, 3000) == 0.1                                            # never below 0.1 mm


def test_scale2x_keeps_the_palette_and_rounds_stair_steps():
    image = np.zeros((4, 4, 4), np.uint8)
    image[..., 3] = 255
    for y in range(4):
        image[y, : y + 1] = (200, 30, 40, 255)  # staircase
    out = ImageUpscaler.scale2x(image)
    assert out.shape == (8, 8, 4)
    assert {tuple(p) for p in out.reshape(-1, 4)} == {tuple(p) for p in image.reshape(-1, 4)}
    nearest = np.repeat(np.repeat(image, 2, axis=0), 2, axis=1)
    assert not np.array_equal(out, nearest)  # the diagonal is smoothed


def test_palette_preserving_upscale_any_factor():
    upscaler = ImageUpscaler.__new__(ImageUpscaler)
    rng = np.random.default_rng(1)
    palette = np.array([[0, 0, 0, 255], [255, 255, 255, 255], [10, 200, 30, 0]], np.uint8)
    upscaler.image_matrix = palette[rng.integers(0, 3, (5, 7))]
    from core import image_doc
    colours = {tuple(p) for p in image_doc.normalize(upscaler.image_matrix).reshape(-1, 4)}  # (transparent canonical)
    for scale in (1, 2, 3, 4):
        out = upscaler.palette_preserving_upscale(scale)
        assert out.shape[:2] == (5 * scale, 7 * scale)
        assert {tuple(p) for p in out.reshape(-1, 4)} <= colours


def test_image_dialogs_remember_the_last_folder(app_components, tmp_path, monkeypatch):
    from PyQt6 import QtWidgets
    from test_characterization import make_test_image
    import cv2
    controller = app_components.image_controller
    path = tmp_path / "sub" / "pic.png"
    path.parent.mkdir()
    cv2.imwrite(str(path), make_test_image(width_px=20, height_px=10)[..., ::-1])
    folders = []

    def open_dialog(parent, title, directory, *args, **kwargs):
        folders.append(directory)
        return (str(path), "") if len(folders) == 1 else ("", "")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", open_dialog)
    controller.load_image()   # first time: no folder yet
    controller.load_image()   # then the folder of the loaded image
    assert folders == ["", str(path.parent)]

    saved = []

    def save_dialog(parent, title, default, *args, **kwargs):
        saved.append(default)
        return "", ""
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", save_dialog)
    controller.save_image()
    assert saved == [str(path.parent / "pic")]
