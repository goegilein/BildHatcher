"""Cutting: geometry of the drawn laser paths (outline only, 2-D). Pure numpy / ezdxf.

A shape is given in its local frame: centred at (0, 0), width w and height h in image pixels, y pointing down
(as on the canvas). The item on the canvas maps it to image pixels (position = centre, rotation); toolpath and DXF
use mm relative to the hatch centre with y pointing up (same convention as the contours, NCDataGeneration).
"""
import math

import ezdxf
import numpy as np

SHAPES = ("line", "rectangle", "ellipse", "triangle", "hexagon")
CLOSED = {"rectangle", "ellipse", "triangle", "hexagon"}
FLATTEN_TOLERANCE_MM = 0.01  # max. deviation of the flattened ellipse from the true curve (as for DXF imports)
MIN_ELLIPSE_SEGMENTS = 16


def ellipse_segments(rx, ry, tolerance):
    """Number of polygon segments so that the chords deviate at most `tolerance` from the ellipse (same unit)."""
    r = max(abs(rx), abs(ry))
    if r <= tolerance:
        return MIN_ELLIPSE_SEGMENTS
    step = 2 * math.acos(1 - tolerance / r)  # chord angle with sagitta = tolerance on the largest radius
    return max(MIN_ELLIPSE_SEGMENTS, math.ceil(2 * math.pi / step))


def outline(shape, w, h, mirrored=False, tolerance=0.5):
    """(N, 2) float array of the outline in the local frame. Closed shapes end at their start point.
    mirrored: a line runs from bottom left to top right instead of top left to bottom right.
    tolerance: max. chord deviation of the ellipse polygon (local units, i.e. image pixels)."""
    a, b = w / 2, h / 2
    if shape == "line":
        points = [(-a, b), (a, -b)] if mirrored else [(-a, -b), (a, b)]
    elif shape == "rectangle":
        points = [(-a, -b), (a, -b), (a, b), (-a, b)]
    elif shape == "triangle":
        points = [(0, -b), (a, b), (-a, b)]
    elif shape == "hexagon":
        points = [(-a, 0), (-a / 2, -b), (a / 2, -b), (a, 0), (a / 2, b), (-a / 2, b)]
    elif shape == "ellipse":
        n = ellipse_segments(a, b, tolerance)
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        points = np.column_stack([a * np.cos(t), b * np.sin(t)])
    else:
        raise ValueError(f"unknown shape {shape!r}")
    points = np.asarray(points, dtype=np.float64)
    if shape in CLOSED:
        points = np.vstack([points, points[:1]])
    return points


def to_mm(points, center, pixel_per_mm):
    """Image pixels (x right, y down) -> mm relative to the hatch centre (x right, y up)."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    return np.column_stack([(p[:, 0] - center[0]) / pixel_per_mm, (center[1] - p[:, 1]) / pixel_per_mm])


def write_dxf(path, entities):
    """Write the cut shapes as a DXF (mm). entities: dicts with "shape" and, in mm (toolpath coordinates),
    "points" (outline, for lines / polygons) or "center", "axis_x", "axis_y" (ellipse: centre and the two half axes
    as vectors). Ellipses are written as true ELLIPSE entities, lines as LINE, the polygons as closed LWPOLYLINE."""
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for e in entities:
        if e["shape"] == "ellipse":
            ax, ay = np.asarray(e["axis_x"], float), np.asarray(e["axis_y"], float)
            major, minor = (ax, ay) if np.linalg.norm(ax) >= np.linalg.norm(ay) else (ay, ax)
            ratio = np.linalg.norm(minor) / np.linalg.norm(major) if np.linalg.norm(major) > 0 else 1.0
            if ratio == 0:  # degenerate: a flat ellipse is a line there and back
                c = np.asarray(e["center"], float)
                msp.add_line(tuple(c - major), tuple(c + major))
                continue
            msp.add_ellipse(tuple(e["center"]), major_axis=tuple(major), ratio=float(min(ratio, 1.0)))
        elif e["shape"] == "line":
            p = np.asarray(e["points"], float)
            msp.add_line(tuple(p[0]), tuple(p[-1]))
        else:
            p = np.asarray(e["points"], float)
            if len(p) > 1 and np.allclose(p[0], p[-1]):
                p = p[:-1]
            msp.add_lwpolyline([tuple(v) for v in p], close=True)
    doc.saveas(path)
