"""P8.2 / P8.3: CIELAB palettes and the pixel-art clean-up (no Qt)."""
import cv2
import numpy as np

from core import palette

COLORS = [(220, 30, 30), (30, 60, 200), (240, 200, 40)]


def _anti_aliased_image(seed=0):
    """Three flat shapes with anti-aliased, blurred and noisy edges on a transparent background."""
    small = np.full((60, 80, 3), 255, np.uint8)
    truth = np.full((60, 80), -1, np.int32)
    cv2.circle(small, (22, 30), 14, COLORS[0], -1, lineType=cv2.LINE_AA)
    cv2.circle(truth.view(np.int32), (22, 30), 14, 0, -1)
    cv2.rectangle(small, (40, 8), (70, 30), COLORS[1], -1)
    truth[8:31, 40:71] = 1
    tri = np.array([[40, 52], [75, 52], [57, 34]], np.int32)
    cv2.fillPoly(small, [tri], COLORS[2], lineType=cv2.LINE_AA)
    cv2.fillPoly(truth.view(np.int32), [tri], 2)
    img = cv2.resize(small, (240, 180), interpolation=cv2.INTER_CUBIC)  # soft, blended edges
    truth = cv2.resize(truth, (240, 180), interpolation=cv2.INTER_NEAREST)
    img = np.clip(img.astype(int) + np.random.default_rng(seed).normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    rgba = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    background = np.all(img > 235, axis=-1)
    rgba[background] = 0
    return rgba, truth


def _opaque_colors(img):
    return {tuple(c) for c in img[img[..., 3] > 0][:, :3]}


def test_p82_kmeans_quantize_in_lab_finds_the_colours():
    rgb = np.repeat(np.array(COLORS, np.uint8), [500, 300, 200], axis=0)
    out = palette.kmeans_quantize(rgb, 3)
    assert {tuple(c) for c in out} == set(COLORS)


def test_p83_cleanup_gives_exactly_the_shape_colours_without_edge_blends():
    img, truth = _anti_aliased_image()
    out = palette.pixel_art_cleanup(img, n_colors=3, min_region=6)
    colors = _opaque_colors(out)
    assert len(colors) == 3
    for color in colors:  # each palette colour is (almost) one of the drawn colours, not a blend
        assert min(np.abs(np.array(color, int) - np.array(c)).max() for c in COLORS) <= 6
    assert np.array_equal(out[..., 3], img[..., 3])  # transparency untouched
    # every shape keeps its pixels; extra pixels only in its opaque anti-aliased rim (<= 4 px outside the shape)
    for i, color in enumerate(COLORS):
        nearest_color = min(colors, key=lambda c: np.abs(np.array(c, int) - color).sum())
        area = np.all(out[..., :3] == nearest_color, axis=-1) & (out[..., 3] > 0)
        true_area = truth == i
        rim = cv2.dilate(true_area.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        assert (area & true_area).sum() > 0.95 * true_area.sum()
        assert not (area & ~rim).any()


def test_p83_no_small_islands_left():
    img, _ = _anti_aliased_image(seed=1)
    out = palette.pixel_art_cleanup(img, n_colors=3, min_region=6)
    for color in _opaque_colors(out):
        mask = (np.all(out[..., :3] == color, axis=-1) & (out[..., 3] > 0)).astype(np.uint8)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        assert (stats[1:, cv2.CC_STAT_AREA] >= 6).all()


def test_p83_better_than_plain_quantization_at_edges():
    """Plain k-means puts edge blends into the clusters; the clean-up must have far fewer pixels off their shape."""
    img, truth = _anti_aliased_image()
    opaque = img[..., 3] > 0
    plain = img.copy()
    plain[opaque, :3] = palette.kmeans_quantize(img[opaque][:, :3], 3)
    clean = palette.pixel_art_cleanup(img, n_colors=3, min_region=6)

    def wrong_pixels(out):
        cols = sorted(_opaque_colors(out))
        idx = np.full(truth.shape, -1)
        for c in cols:
            i = int(np.argmin([np.abs(np.array(c, int) - np.array(k)).sum() for k in COLORS]))
            idx[np.all(out[..., :3] == c, axis=-1) & opaque] = i
        return int(((idx != truth) & opaque & (truth >= 0)).sum())

    assert wrong_pixels(clean) < wrong_pixels(plain)
