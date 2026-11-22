"""core.postprocess unit tests (no Qt)."""
import numpy as np

from core.postprocess import PostProcessor, simplify_indices
from core.toolpath import Layer, polyline, MOVE_TRAVEL, MOVE_BURN, MOVE_RAPID


def _dist_to_polyline(points, poly):
    """Max distance of points to the polyline `poly` (2-D)."""
    best = np.full(len(points), np.inf)
    for a, b in zip(poly[:-1], poly[1:]):
        ab = b - a
        t = np.clip(((points - a) @ ab) / max(ab @ ab, 1e-30), 0, 1)
        best = np.minimum(best, np.linalg.norm(points - (a + t[:, None] * ab), axis=1))
    return best.max()


def test_p53_rdp_keeps_shape_within_tolerance():
    angles = np.linspace(0, np.pi, 400)
    arc = np.column_stack([10 * np.cos(angles), 10 * np.sin(angles), np.zeros(400)])
    keep = simplify_indices(arc, 0.01)
    assert keep[0] == 0 and keep[-1] == 399 and len(keep) < 80  # 400 -> ~65 points (optimum ~36)
    assert _dist_to_polyline(arc[:, :2], arc[keep, :2]) <= 0.01


def test_p53_maximize_lines_on_layers():
    line = polyline([(0, 0, 0, MOVE_TRAVEL), (1, 0.001, 0, MOVE_BURN), (2, 0, 0, MOVE_BURN), (2, 5, 0, MOVE_BURN)])
    out = PostProcessor().maximize_line_length([Layer((0, 0, 0), [line])])
    assert out[0].polylines[0][:, :2].tolist() == [[0, 0], [2, 0], [2, 5]]
    assert out[0].polylines[0][:, 3].tolist() == [MOVE_TRAVEL, MOVE_BURN, MOVE_BURN]


def test_p54_drive_mode_corner_and_collinear_points():
    # straight run with a collinear point, then a 90 degree corner
    line = polyline([(0, 0, 0, MOVE_TRAVEL), (5, 0, 0, MOVE_BURN), (10, 0, 0, MOVE_BURN), (10, 10, 0, MOVE_BURN)])
    layer = Layer((0, 0, 0), [line], speed=50, power=40)
    for mode in ("Constant Drive", "Over Drive"):
        out = PostProcessor().set_drive_mode([layer], mode)[0].polylines[0]
        assert out[0, 3] == MOVE_RAPID and out[0, 0] < 0  # lead-in before the start
        assert not ((out[:, 0] == 5) & (out[:, 1] == 0)).any()  # collinear point dropped
        travel_after_corner = out[(out[:, 3] == MOVE_TRAVEL) & (out[:, 0] > 10)]
        assert len(travel_after_corner)  # lead-out beyond the corner in x
        assert out[-1, 3] == MOVE_TRAVEL and out[-1, 1] > 10  # lead-out after the end
        assert np.isfinite(out).all()
