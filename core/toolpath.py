"""Toolpath data model (replaces the per-point `Point` objects).

HatchData -> HatchCluster.data: list[Layer] -> Layer.polylines: list[ndarray (N, 4)]

Each polyline row is (x, y, z, move) in mm. `move` is one of the MOVE_* codes; the first row of a
polyline is the travel move to its start. Colour, speed and power are the same for a whole layer
(one colour of the image), so they live on the Layer instead of on every point.
"""
from dataclasses import dataclass, field

import numpy as np

MOVE_TRAVEL = 0  # laser off, layer speed (G0)
MOVE_BURN = 1    # laser on, layer speed and power (G1)
MOVE_RAPID = 2   # laser off at the machine's rapid speed (lead-in moves of the drive post-processing)

X, Y, Z, MOVE = 0, 1, 2, 3


@dataclass
class Layer:
    color: tuple            # (r, g, b) ints 0..255
    polylines: list = field(default_factory=list)  # list of float ndarrays with shape (N, 4)
    speed: float = None     # mm/s, set by apply_speed_and_power
    power: float = None     # percent, set by apply_speed_and_power

    @property
    def point_count(self):
        return sum(len(p) for p in self.polylines)


def polyline(rows):
    """Build a polyline array from a sequence of (x, y, z, move) rows."""
    return np.asarray(rows, dtype=np.float64).reshape(-1, 4)
