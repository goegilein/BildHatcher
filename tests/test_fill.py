"""P6.3: flood fill (core.fill) against a straightforward reference BFS."""
import collections
import time

import numpy as np

from core.fill import fill_region


def _reference(image, seed, accept, diagonal):
    h, w = image.shape[:2]
    x, y = seed
    out = np.zeros((h, w), bool)
    out[y, x] = True
    queue = collections.deque([(y, x)])
    steps = [(-1, 0), (1, 0), (0, -1), (0, 1)] + ([(-1, -1), (-1, 1), (1, -1), (1, 1)] if diagonal else [])
    while queue:
        cy, cx = queue.popleft()
        for dy, dx in steps:
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and not out[ny, nx] and accept(ny, nx):
                out[ny, nx] = True
                queue.append((ny, nx))
    return out


def test_modes_match_reference_bfs():
    rng = np.random.default_rng(5)
    palette = np.array([[0, 0, 0, 0], [200, 10, 10, 255], [205, 12, 10, 255], [10, 10, 200, 255]], np.uint8)
    for _ in range(20):
        img = palette[rng.integers(0, 4, size=(15, 18))]
        seed = (int(rng.integers(0, 18)), int(rng.integers(0, 15)))
        target = img[seed[1], seed[0]].astype(int)
        same = lambda y, x: np.array_equal(img[y, x], target)
        near = lambda y, x: np.linalg.norm(img[y, x].astype(int) - target) <= 10
        limit = palette[3]
        contours = rng.random((15, 18)) < 0.2
        contours[seed[1], seed[0]] = False
        fill_color = palette[1]
        near_fill = lambda y, x: (np.all(img[max(0, y - 1):y + 2, max(0, x - 1):x + 2] == fill_color, axis=-1)).any()
        cases = [
            ("Regular", {}, same, False),
            ("Include Diagonals", {}, same, True),
            ("Similar Color", {"tolerance": 10}, near, False),
            ("Diagonals + Similar", {"tolerance": 10}, near, True),
            ("To Color", {"limit_color": limit}, lambda y, x: not np.array_equal(img[y, x], limit), False),
            ("To Contours", {"contour_mask": contours}, lambda y, x: not contours[y, x], False),
            ("Fill Lines", {"tolerance": 1, "fill_color": fill_color}, lambda y, x: same(y, x) and near_fill(y, x), False),
        ]
        for mode, kwargs, accept, diagonal in cases:
            expected = _reference(img, seed, accept, diagonal)
            assert np.array_equal(fill_region(img, seed, mode, **kwargs), expected), mode


def test_b32_colour_independent_modes_respect_the_mask_region():
    img = np.zeros((10, 10, 4), np.uint8)
    region = np.zeros((10, 10), bool)
    region[2:5, 2:5] = True
    out = fill_region(img, (3, 3), "To Color", limit_color=[1, 2, 3, 255], region=region)
    assert np.array_equal(out, region)
    out = fill_region(img, (3, 3), "To Contours", contour_mask=np.zeros((10, 10), bool) | (np.arange(10) == 9), region=region)
    assert np.array_equal(out, region)


def test_large_fill_is_fast():
    img = np.zeros((2000, 2000, 4), np.uint8)
    t = time.perf_counter()
    assert fill_region(img, (0, 0), "Regular").all()
    assert time.perf_counter() - t < 1.0  # the old Python BFS needed minutes for 4 million pixels


def test_flood_fill_at_creates_overlay(app_components):
    from core import image_doc
    from test_characterization import load_image, make_test_image
    c = app_components
    load_image(c, image_doc.from_rgb(make_test_image()))
    c.image_colorer.set_active_color([0, 255, 0])
    c.image_colorer.flood_fill_at(30, 30, "Regular")  # inside the red rectangle
    c.image_colorer.imprint_color_overlays()
    img = c.data_handler.image_matrix
    assert (img[10:46, 10:56] == [0, 255, 0, 255]).all() and img[5, 5, 3] == 0


def test_p64_mask_shapes_match_former_pixel_loops():
    from ImageEditing import _fill_mask_shape
    rng = np.random.default_rng(9)
    for _ in range(50):
        h, w = 30, 40
        x0, x1 = sorted(rng.integers(-5, 45, 2))
        y0, y1 = sorted(rng.integers(-5, 35, 2))
        for shape in ("rectangle", "ellipse"):
            new = np.zeros((h, w), np.uint8)
            _fill_mask_shape(new, shape, x0, y0, x1, y1)
            old = np.zeros((h, w), np.uint8)
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            for y in range(max(0, y0), min(h, y1 + 1)):
                for x in range(max(0, x0), min(w, x1 + 1)):
                    if shape == "rectangle" or (rx > 0 and ry > 0 and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1):
                        old[y, x] = 1
            assert np.array_equal(new, old), (shape, x0, y0, x1, y1)
