"""Phase 3: transparency is the background (REVISION_PLAN.md section 2)."""
import numpy as np
from PIL import Image

from core import image_doc
from test_characterization import load_image, make_test_image, run_hatching


def test_normalize_binarizes_alpha_and_zeroes_transparent_pixels():
    rgba = np.array([[[10, 20, 30, 0], [10, 20, 30, 127], [10, 20, 30, 128], [10, 20, 30, 255]]], np.uint8)
    out = image_doc.normalize(rgba)
    assert out[0].tolist() == [[0, 0, 0, 0], [0, 0, 0, 0], [10, 20, 30, 255], [10, 20, 30, 255]]
    assert image_doc.normalize(np.zeros((1, 1, 3), np.uint8))[0, 0].tolist() == [0, 0, 0, 255]


def test_load_png_with_alpha_and_rgb_with_white_option(app_components, tmp_path):
    ctrl = app_components.image_controller
    rgba = np.zeros((2, 2, 4), np.uint8)
    rgba[0, 0] = (100, 0, 0, 255)
    rgba[0, 1] = (100, 0, 0, 200)  # soft edge -> opaque, composited over white
    rgba[1, 0] = (255, 255, 255, 255)  # opaque white in an alpha image stays opaque
    Image.fromarray(rgba, "RGBA").save(tmp_path / "a.png")
    img, _ = ctrl.read_image_file(str(tmp_path / "a.png"))
    assert img[0, 0].tolist() == [100, 0, 0, 255]
    assert img[0, 1].tolist() == [133, 55, 55, 255]  # 100*200/255 + 255*55/255
    assert img[1, 0].tolist() == [255, 255, 255, 255]
    assert img[1, 1].tolist() == [0, 0, 0, 0]

    rgb = np.full((1, 2, 3), 255, np.uint8)
    rgb[0, 0] = (1, 2, 3)
    Image.fromarray(rgb, "RGB").save(tmp_path / "b.png")
    assert ctrl.read_image_file(str(tmp_path / "b.png"), True)[0][0].tolist() == [[1, 2, 3, 255], [0, 0, 0, 0]]
    assert ctrl.read_image_file(str(tmp_path / "b.png"), False)[0][0].tolist() == [[1, 2, 3, 255], [255, 255, 255, 255]]


def test_save_keeps_alpha_for_png_and_composites_jpeg(app_components, tmp_path):
    ctrl = app_components.image_controller
    img = np.zeros((2, 2, 4), np.uint8)
    img[0, 0] = (10, 20, 30, 255)
    ctrl.write_image_file(str(tmp_path / "x.png"), img, 10)
    assert np.array_equal(np.array(Image.open(tmp_path / "x.png")), img)
    ctrl.write_image_file(str(tmp_path / "x.bmp"), img, 10)
    assert np.array(Image.open(tmp_path / "x.bmp"))[1, 1].tolist() == [255, 255, 255]


def test_opaque_white_is_hatched_transparent_is_not(app_components):
    c = app_components
    img = image_doc.from_rgb(make_test_image(), white_is_background=False)  # white is a real colour now
    load_image(c, img)
    colors = [layer.color for layer in run_hatching(c, pattern="FixedMeander", angle=0.0).hatch_clusters[0].data]
    assert (255, 255, 255) in colors

    load_image(c, image_doc.from_rgb(make_test_image()))
    colors = [layer.color for layer in run_hatching(c, pattern="FixedMeander", angle=0.0).hatch_clusters[0].data]
    assert (255, 255, 255) not in colors and len(colors) == 3


def test_transparent_fill_overlay_erases_on_imprint(app_components):
    c = app_components
    load_image(c, image_doc.from_rgb(make_test_image()))
    colorer = c.image_colorer
    colorer.set_active_color(list(image_doc.TRANSPARENT))
    region = np.zeros((80, 120), bool)
    region[10:20, 10:20] = True  # inside the red rectangle
    c.data_handler.active_color_overlays.append(colorer._create_overlay_from_mask(region))
    colorer.imprint_color_overlays()
    result = c.data_handler.image_matrix
    assert (result[10:20, 10:20] == 0).all()
    assert result[30, 30].tolist() == [220, 30, 30, 255]  # rest of the rectangle untouched


def test_colour_fill_on_transparent_area_becomes_opaque(app_components):
    c = app_components
    load_image(c, image_doc.from_rgb(make_test_image()))
    colorer = c.image_colorer
    colorer.set_active_color([0, 200, 0])
    region = np.zeros((80, 120), bool)
    region[0:3, 0:3] = True  # background corner
    c.data_handler.active_color_overlays.append(colorer._create_overlay_from_mask(region))
    colorer.imprint_color_overlays()
    assert (c.data_handler.image_matrix[0:3, 0:3] == [0, 200, 0, 255]).all()


def test_quantize_ignores_background_and_invert_keeps_alpha(app_components):
    c = app_components
    load_image(c, image_doc.from_rgb(make_test_image()))
    before = c.data_handler.image_matrix.copy()
    c.gui.color_count_spinbox.setValue(2)
    c.image_adjuster.quantize_image_color()
    after = c.data_handler.image_matrix
    assert np.array_equal(after[..., 3], before[..., 3])
    assert c.data_handler.get_unique_color_count() == 2  # 3 shapes -> 2 colours, background not counted

    c.image_adjuster.invert_colors()
    c.image_adjuster.invert_colors()  # B29: second invert must restore the current image, not a stale copy
    assert np.array_equal(c.data_handler.image_matrix, after)


def test_bright_colours_to_transparent_with_undo(app_components):
    c = app_components
    img = np.array([[[250, 250, 250], [231, 231, 231], [230, 230, 230], [0, 0, 0]]], np.uint8)
    load_image(c, image_doc.from_rgb(img))
    c.image_controller.make_bright_transparent(230)
    assert c.data_handler.image_matrix[0, :, 3].tolist() == [0, 0, 255, 255]
    c.data_handler.undo_manager.undo()
    assert c.data_handler.image_matrix[0, :, 3].tolist() == [255, 255, 255, 255]
