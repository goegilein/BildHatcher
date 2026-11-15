"""core.hatching unit tests (no Qt). The patterns themselves are covered by the golden files."""
import numpy as np

from core import hatching


def test_label_colors_sorts_bright_to_dark_and_skips_transparent():
    img = np.array([[[10, 10, 10], [-1, -1, -1]], [[200, 0, 0], [10, 10, 10]]], np.int16)
    labels, colors = hatching.label_colors(img)
    assert colors == [(200, 0, 0), (10, 10, 10)]
    assert labels.tolist() == [[1, -1], [0, 1]]


def test_label_colors_all_transparent():
    labels, colors = hatching.label_colors(np.full((2, 2, 3), -1, np.int16))
    assert colors == [] and (labels == -1).all()


def test_b30_lines_are_symmetric_on_a_full_square():
    from core.toolpath import X
    labels = np.zeros((20, 20), np.int32)  # one colour everywhere, pixel centers 0..19 -> image spans -0.5..19.5
    lines = hatching.meander(labels, 0, (9.5, 9.5), 1.0, 0.0, 4.0, 0.25)
    xs = np.concatenate([line[:, X] for line in lines])
    # image edges at -10 / +10 mm; both line ends within one sampling step (0.25) of them
    assert abs(xs.max() - 10.0) <= 0.25
    assert abs(xs.min() + 10.0) <= 0.25  # was -10.625: low edge shifted by more than one pixel


def test_p44_random_seed_makes_random_patterns_reproducible(app_components):
    from test_characterization import load_image, make_test_image, run_hatching

    def hatch(pattern, seed, global_seed):
        app_components.gui.random_seed_spinbox.setValue(seed)
        result = run_hatching(app_components, pattern=pattern, seed=global_seed)  # seed= seeds the global random module
        return [np.concatenate(layer.polylines) for layer in result.hatch_clusters[0].data]

    load_image(app_components, make_test_image())
    for pattern in ("RandomMeander", "Circular"):
        a, b = hatch(pattern, 42, 1), hatch(pattern, 42, 2)
        assert all(np.array_equal(x, y) for x, y in zip(a, b))  # fixed seed: independent of global state
        c, d = hatch(pattern, 0, 1), hatch(pattern, 0, 2)
        assert not all(x.shape == y.shape and np.array_equal(x, y) for x, y in zip(c, d))  # 0 = random


def _segment_check(lines, labels, target, center, ppm):
    """Fraction of interior points of the burn segments that are not in `target`, and the burnt length in px."""
    bad = total = 0
    length = 0.0
    for line in lines:
        a, b = line[0, :2] * ppm + center, line[-1, :2] * ppm + center
        length += np.linalg.norm(b - a)
        t = np.linspace(0.01, 0.99, 100)[:, None]
        pts = a + t * (b - a)
        xi, yi = np.floor(pts[:, 0] + 0.5).astype(int), np.floor(pts[:, 1] + 0.5).astype(int)
        ok = (xi >= 0) & (xi < labels.shape[1]) & (yi >= 0) & (yi < labels.shape[0])
        bad += np.count_nonzero(~ok) + np.count_nonzero(labels[yi[ok], xi[ok]] != target)
        total += len(t)
    return bad / max(total, 1), length


def _reference_length(labels, target, p0, d, t_max=200.0, step=0.001):
    """Burnt length of the same line by very fine sampling."""
    t = np.arange(0, t_max, step)
    x, y = p0[0] + t * d[0], p0[1] + t * d[1]
    xi, yi = np.floor(x + 0.5).astype(int), np.floor(y + 0.5).astype(int)
    ok = (xi >= 0) & (xi < labels.shape[1]) & (yi >= 0) & (yi < labels.shape[0])
    return np.count_nonzero(labels[yi[ok], xi[ok]] == target) * step


def test_p45_exact_segments_stay_inside_their_colour_and_cover_it():
    rng = np.random.default_rng(3)
    labels = np.kron(rng.integers(-1, 3, size=(4, 5)), np.ones((10, 10), int)).astype(np.int32)  # 40 x 50 px blocks
    center = np.array([24.5, 19.5])
    for target in (0, 1, 2):
        for theta in (0.0, 30.0, 90.0, 135.0):
            lines = hatching.meander(labels, target, center, 1.0, theta, 3.0, 0.5)
            bad, length = _segment_check(lines, labels, target, center, 1.0)
            assert bad == 0
        # one ray, compared with fine sampling (corners shorter than precision/2 may be bridged or dropped)
        lines = hatching._line_segments(labels, target, center, (np.cos(0.3), np.sin(0.3)), 100.0, center, 1.0,
                                        "Flat", None, 0.25)
        _, length = _segment_check(lines, labels, target, center, 1.0)
        assert abs(length - _reference_length(labels, target, center, (np.cos(0.3), np.sin(0.3)))) < 0.5
