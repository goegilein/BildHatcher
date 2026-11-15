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
