"""Hatch pattern generation (vectorized). Pure numpy, no Qt.

Coordinates: `labels` is the colour label image of a hatch cluster, flipped so that row 0 is the bottom row
(machine y up). Hatch positions are in pixels; emitted polylines are in mm relative to `center`.
Every function returns a list of polylines (float arrays (N, 4): x, y, z, move) for one colour label,
or None if `progress` returned True (cancelled).

Straight lines (meander, radial) are cut exactly at the pixel edges (`_line_segments`); circles and spirals
are sampled with the hatch precision as step (`_chains`).
"""
import random

import numpy as np

from core.toolpath import MOVE_TRAVEL, MOVE_BURN

OUTSIDE = -2  # label of samples outside the image / cylinder
_TWO_PI_36 = 2 * np.pi / 36


def label_colors(image):
    """image: int16 RGB (H, W, 3) with -1 for transparent pixels.
    Returns (labels (H, W) int32 with -1 for transparent, colours sorted by brightness descending)."""
    flat = image.reshape(-1, 3)
    opaque = flat[:, 0] >= 0
    labels = np.full(flat.shape[0], -1, dtype=np.int32)
    if not opaque.any():
        return labels.reshape(image.shape[:2]), []
    rgb = flat[opaque].astype(np.int32)
    keys, inverse = np.unique((rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2], return_inverse=True)  # 1-D: much faster than axis=0
    colors = np.stack([keys >> 16, (keys >> 8) & 255, keys & 255], axis=1)
    order = np.argsort(-colors.sum(axis=1), kind="stable")  # bright -> dark
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    labels[opaque] = rank[inverse.reshape(-1)]
    return labels.reshape(image.shape[:2]), [tuple(int(v) for v in colors[i]) for i in order]


def _pixel_index(v):
    """Pixel whose center is nearest (pixel i covers [i - 0.5, i + 0.5)). B30: the old loops' trunc-based rounding
    mapped [-1.5, 0) to pixel 0 and [0, 1.5) to pixel 1, shifting the low image edges by up to one pixel."""
    return np.floor(v + 0.5).astype(np.int64)


def _sample_labels(labels, x, y, outside):
    xr, yr = _pixel_index(x), _pixel_index(y)
    h, w = labels.shape
    inside = ~outside & (xr >= 0) & (xr < w) & (yr >= 0) & (yr < h)
    lab = np.full(len(x), OUTSIDE, dtype=np.int32)
    lab[inside] = labels[yr[inside], xr[inside]]
    return lab


def _cylinder_map(x, center_x, cyl_rad, hatch_mode):
    """CylEquidistX: arc-length -> chord mapping. Returns (x mapped, outside-cylinder flags)."""
    if hatch_mode != "CylEquidistX":
        return x, np.zeros(len(x), dtype=bool)
    u = (x - center_x) / cyl_rad
    outside = np.abs(x - center_x) > cyl_rad
    with np.errstate(invalid="ignore"):
        mapped = np.where(outside, x, np.arcsin(np.where(outside, 0, u)) * cyl_rad + center_x)
    return mapped, outside


def _line_segments(labels, target, p0, direction, t_max, center, ppm, hatch_mode, cyl_rad, min_len):
    """Exact segments of the straight line p0 + t * direction (0 <= t <= t_max) through the pixels of `target` (P4.5).

    The line is cut at every pixel boundary it crosses (pixel i covers [i - 0.5, i + 0.5)), so segment ends lie on
    the pixel edges, independent of any sampling step. For CylEquidistX the line is straight in the unmapped x and
    the boundaries are mapped back with the inverse of the cylinder mapping.
    Segments shorter than min_len are dropped and gaps shorter than min_len are bridged (pixel corners).
    """
    h, w = labels.shape
    (x0, y0), (dx, dy) = p0, direction
    cx = center[0]
    cyl = hatch_mode == "CylEquidistX"
    eps = 1e-9

    if cyl:
        to_image = lambda xt: np.arcsin(np.clip((xt - cx) / cyl_rad, -1, 1)) * cyl_rad + cx
        to_line = lambda xm: np.sin((xm - cx) / cyl_rad) * cyl_rad + cx
        x_lo, x_hi = max(-0.5, cx - cyl_rad * np.pi / 2), min(w - 0.5, cx + cyl_rad * np.pi / 2)
        x_lo, x_hi = to_line(x_lo), to_line(x_hi)
    else:
        to_image = to_line = lambda v: v
        x_lo, x_hi = -0.5, w - 0.5

    # parameter range of the line inside the image (Liang-Barsky clip)
    t0, t1 = 0.0, t_max
    for p, d, lo, hi in ((x0, dx, x_lo, x_hi), (y0, dy, -0.5, h - 0.5)):
        if abs(d) < eps:
            if not lo <= p < hi:
                return []
        else:
            a, b = (lo - p) / d, (hi - p) / d
            t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    if t1 - t0 < eps:
        return []

    # every pixel boundary crossing between t0 and t1
    cuts = [np.array([t0, t1])]
    for p, d, mapped in ((x0, dx, to_image), (y0, dy, lambda v: v)):
        if abs(d) < eps:
            continue
        a, b = sorted((mapped(p + t0 * d), mapped(p + t1 * d)))
        bounds = np.arange(np.ceil(a - 0.5), np.floor(b - 0.5) + 1) + 0.5
        bounds = bounds[(bounds > a) & (bounds < b)]
        line_bounds = to_line(bounds) if mapped is to_image else bounds
        cuts.append((line_bounds - p) / d)
    t = np.unique(np.concatenate(cuts))

    mid = (t[:-1] + t[1:]) / 2
    xi = np.clip(np.floor(to_image(x0 + mid * dx) + 0.5).astype(np.int64), 0, w - 1)
    yi = np.clip(np.floor(y0 + mid * dy + 0.5).astype(np.int64), 0, h - 1)
    inside = labels[yi, xi] == target
    if not inside.any():
        return []
    edges = np.diff(np.concatenate([[0], inside.astype(np.int8), [0]]))
    t_start, t_end = t[np.flatnonzero(edges == 1)], t[np.flatnonzero(edges == -1)]

    keep = np.concatenate([[True], t_start[1:] - t_end[:-1] >= min_len])  # bridge short gaps
    t_start, t_end = t_start[keep], t_end[np.concatenate([keep[1:], [True]])]
    keep = t_end - t_start >= min_len  # drop pixel-corner clips
    t_start, t_end = t_start[keep], t_end[keep]

    cy = center[1]
    out = []
    for ts, te in zip(t_start, t_end):
        out.append(np.array([
            [(to_image(x0 + ts * dx) - cx) / ppm, (y0 + ts * dy - cy) / ppm, 0, MOVE_TRAVEL],
            [(to_image(x0 + te * dx) - cx) / ppm, (y0 + te * dy - cy) / ppm, 0, MOVE_BURN]]))
    return out


def _reverse(segments):
    """Meander: walk the segments of a line backwards (end becomes the travel target)."""
    out = []
    for seg in reversed(segments):
        seg = seg[::-1].copy()
        seg[0, 3], seg[1, 3] = MOVE_TRAVEL, MOVE_BURN
        out.append(seg)
    return out


def _chains(lab, target, x, y, center, ppm):
    """Point chains (circle / spiral): every sample inside the colour is a point, runs of >= 2 samples."""
    inside = lab == target
    if not inside.any():
        return []
    edges = np.diff(np.concatenate([[0], inside.astype(np.int8), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    cx, cy = center[0], center[1]
    out = []
    for s, e in zip(starts, ends):
        if e - s < 2:
            continue
        line = np.empty((e - s, 4))
        line[:, 0] = (x[s:e] - cx) / ppm
        line[:, 1] = (y[s:e] - cy) / ppm
        line[:, 2] = 0
        line[:, 3] = MOVE_BURN
        line[0, 3] = MOVE_TRAVEL
        out.append(line)
    return out


def meander(labels, target, center, ppm, theta, hatch_distance, step_size, hatch_mode="Flat", cyl_rad=None, progress=None):
    """Parallel lines at angle theta (degrees), alternating direction."""
    theta = np.mod(theta, 180)
    theta_rad = np.radians(theta)
    cos_theta, sin_theta = np.cos(theta_rad), np.sin(theta_rad)
    height, width = labels.shape
    hatch_x_finished = hatch_y_finished = False
    if theta == 0:
        max_lines = height / hatch_distance
        step_start_y, step_start_x = hatch_distance, 1
        hatch_x_finished = True
    elif theta == 90:
        max_lines = width / hatch_distance
        step_start_x, step_start_y = hatch_distance, 1
        hatch_y_finished = True
    else:
        step_start_y = np.abs(hatch_distance / cos_theta)
        step_start_x = np.abs(hatch_distance / sin_theta)
        max_lines = height / step_start_y + width / step_start_x

    min_y, max_y = -np.ceil(step_start_y), height + np.ceil(step_start_y)
    min_x, max_x = -np.ceil(step_start_x), width + np.ceil(step_start_x)
    if cos_theta >= 0:
        hatch_start_x, incline = max_x, -1
    else:
        hatch_start_x, incline = min_x, 1
    hatch_start_y = min_y

    polylines = []
    line_dir = 1
    line_count = 0
    while True:
        segments = _line_segments(labels, target, (hatch_start_x, hatch_start_y), (-cos_theta, -sin_theta), np.inf,
                                  center, ppm, hatch_mode, cyl_rad, step_size / 2)
        polylines.extend(segments if line_dir == 1 else _reverse(segments))
        line_dir *= -1

        # next line: first move along y, then along x
        if not hatch_y_finished:
            hatch_start_y += step_start_y
            if hatch_start_y >= max_y:
                hatch_y_finished = True
        elif not hatch_x_finished:
            if not hatch_start_y >= max_y:
                hatch_start_y = max_y + 1  # 90 degree case: y has to be set manually
            hatch_start_x += incline * step_start_x
            if (hatch_start_x <= min_x or incline == 1) and (hatch_start_x >= max_x or incline == -1):
                hatch_x_finished = True
        else:
            return polylines

        line_count += 1
        if progress is not None and progress(line_count / max_lines):
            return None


def circular(labels, target, center, ppm, hatch_distance, step_size, hatch_mode="Flat", cyl_rad=None, progress=None, rng=random):
    """Concentric circles around center, each with a random start angle (0-19 degrees)."""
    height, width = labels.shape
    max_rad = np.ceil(np.sqrt((height / 2) ** 2 + (width / 2) ** 2)) + np.ceil(hatch_distance)
    polylines = []
    hatch_rad = hatch_distance / 10  # the start radius is smaller
    while hatch_rad <= max_rad:
        angle_res = min(step_size / hatch_rad, _TWO_PI_36)
        start_angle = np.deg2rad(np.floor(rng.uniform(0, 20)))
        angles = np.linspace(start_angle, start_angle + 2 * np.pi, int(np.ceil(2 * np.pi / angle_res)))
        x, outside = _cylinder_map(center[0] + hatch_rad * np.cos(angles), center[0], cyl_rad, hatch_mode)
        y = center[1] + hatch_rad * np.sin(angles)
        polylines.extend(_chains(_sample_labels(labels, x, y, outside), target, x, y, center, ppm))
        hatch_rad += hatch_distance
        if progress is not None and progress(hatch_rad / max_rad):
            return None
    return polylines


def spiral(labels, target, center, ppm, hatch_distance, step_size, hatch_mode="Flat", cyl_rad=None, progress=None):
    """Archimedean spiral around center, one turn per hatch distance."""
    height, width = labels.shape
    max_rad = np.ceil(np.sqrt((height / 2) ** 2 + (width / 2) ** 2)) + np.ceil(hatch_distance)
    polylines = []
    hatch_rad_avg = hatch_distance / 2
    while hatch_rad_avg + hatch_distance / 2 <= max_rad:
        angle_res = min(step_size / hatch_rad_avg, _TWO_PI_36)
        n = int(np.ceil(2 * np.pi / angle_res))
        angles = np.linspace(0, 2 * np.pi, n)
        radii = np.linspace(hatch_rad_avg - hatch_distance / 2, hatch_rad_avg + hatch_distance / 2, n)
        x, outside = _cylinder_map(center[0] + radii * np.cos(angles), center[0], cyl_rad, hatch_mode)
        y = center[1] + radii * np.sin(angles)
        polylines.extend(_chains(_sample_labels(labels, x, y, outside), target, x, y, center, ppm))
        hatch_rad_avg += hatch_distance
        if progress is not None and progress(hatch_rad_avg / max_rad):
            return None
    return polylines


def radial(labels, target, center, ppm, hatch_distance, step_size, hatch_mode="Flat", cyl_rad=None, progress=None):
    """Rays from center outwards, alternating direction."""
    height, width = labels.shape
    max_rad = np.ceil(np.sqrt((height / 2) ** 2 + (width / 2) ** 2)) + np.ceil(hatch_distance)
    angle_res = np.atan(hatch_distance / max_rad) * 2
    angles = np.linspace(0, 2 * np.pi, int(np.ceil(2 * np.pi / angle_res)))
    cx, cy = center[0], center[1]

    polylines = []
    line_dir = 1
    for ray_count, angle in enumerate(angles, start=1):
        segments = _line_segments(labels, target, (cx, cy), (np.cos(angle), np.sin(angle)), max_rad,
                                  center, ppm, hatch_mode, cyl_rad, step_size / 2)
        polylines.extend(segments if line_dir == 1 else _reverse(segments))
        line_dir *= -1
        if progress is not None and progress(ray_count / len(angles)):
            return None
    return polylines
